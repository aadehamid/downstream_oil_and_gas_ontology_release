"""Says whether each store holds the release in this folder: current, or behind.

    py -m kpi_store.sync_check --stores <local settings file> [--store jena] [--ref worktree] [--json]

The stores, and how each is read:
  databricks  the marker row in epm_store_markers and the rows per graph of epm_triples, through the Databricks
              SDK's statement execution on the SQL warehouse [databricks] warehouse_id names in kpi_store.toml.
              The SDK signs in with the Databricks CLI profile of the local settings (OAuth). No token is read.
  jena        the graph names and each graph's triple count, from the dataset's SPARQL query URL
  neo4j       the local database's marker (a node labelled EpmStoreMarker) and its counts
  enterprise  the same, in the one database [neo4j.enterprise] names

What a current store holds comes from this folder's files: the catalog, the projection manifest and the release
packages. --ref worktree, the default, reads the files as they are and needs no Git. Another --ref reads them at
that Git ref. The judgement is the release's own (sync_stores.drift): a store is current, behind (loaded from another release),
changed (its content moved since it was marked), unmarked, empty or unreachable. A Neo4j database also gets an
lm: line for its logical models when the release holds any.

This command only reads. Exit 0 when every line reads current, 1 otherwise, 2 on bad settings.
Needs rdflib; databricks-sdk for databricks; neo4j for the two Neo4j databases.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import copy_enterprise
from . import load_databricks as ldb
from . import load_fuseki
from . import load_neo4j as local_load
from . import local_settings as ls
from . import settings as settings_module

STORES = ("databricks", "jena", "neo4j", "enterprise")
WORKTREE = "worktree"
STATEMENT_WAIT_SECONDS = 300


# ---- Databricks, through the SDK's statement execution ------------------------------------------------

def workspace_client(profile):
    """The SDK's client, signed in through the Databricks CLI profile (unified authentication). No token is read."""
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient(profile=profile)


def _state(response):
    state = getattr(getattr(response, "status", None), "state", None)
    return getattr(state, "value", state)


def statement_runner(client, warehouse_id, wait_seconds=STATEMENT_WAIT_SECONDS, sleep=time.sleep):
    """run_sql(statement) -> list of row dicts, on one SQL warehouse. Values arrive as text (the API's JSON_ARRAY
    format), so a caller converts a count itself. A statement that does not succeed raises RuntimeError."""
    def run_sql(statement):
        response = client.statement_execution.execute_statement(statement=statement, warehouse_id=warehouse_id,
                                                                wait_timeout="30s")
        waited = 0
        while _state(response) in ("PENDING", "RUNNING"):
            if waited >= wait_seconds:
                raise RuntimeError(f"the statement did not finish within {wait_seconds} seconds")
            sleep(2)
            waited += 2
            response = client.statement_execution.get_statement(response.statement_id)
        if _state(response) != "SUCCEEDED":
            raise RuntimeError(f"the statement ended as {_state(response)}")
        columns = [c.name for c in response.manifest.schema.columns]
        result, rows = response.result, []
        while result is not None:
            rows += list(result.data_array or [])
            following = getattr(result, "next_chunk_index", None)
            result = client.statement_execution.get_statement_result_chunk_n(response.statement_id, following) if following else None
        return [dict(zip(columns, row)) for row in rows]
    return run_sql


def read_databricks(settings, run_sql, ss):
    """(marker or None, [total rows], {graph: rows}) of the triple table. Every statement passes the load's Gate,
    which refuses anything outside the KPI Store's schemas."""
    gate = ldb.Gate(settings, run_sql)
    marker = ldb.read_marker(gate, settings)
    if marker is None:
        return None, [0], {}
    rows = gate.run(f"SELECT graph, count(*) AS n FROM {settings.triples_table} GROUP BY graph")
    held = ss.rows_per_graph((row["graph"], int(row["n"])) for row in rows)
    return marker, [sum(held.values())], held


# ---- reading the stores ---------------------------------------------------------------------------

def expected(release_root, ss, ref=WORKTREE, extra_graphs=()):
    """What a current store holds. The worktree is read with the load's own reader, which orders correction
    versions; another ref is read by sync_stores at that Git ref."""
    if ref in (None, WORKTREE):
        want = ldb.expected(release_root, ss)
        want["jena_graphs"] = ss.jena_graphs(want["newest"])
    else:
        want = ss.expected_for(ref, ("jena",))
    return want | {"jena_apart": tuple(extra_graphs)}


def _why(err, ss):
    if isinstance(err, (ls.LocalSettingsError, copy_enterprise.Refused, settings_module.SettingsError)):
        return str(err)   # this code's own words
    return ss.reason(err)   # the error's name, never its message, which can carry an address


def read_neo4j(session, store, newest, code):
    """(marker, counts, the logical models' lm: row or None) of one Neo4j database."""
    marker, counts = code.ss.read_neo4j(session, store)
    files = code.lm.models(newest)
    if not files:
        return marker, counts, None
    nodes, edges = code.lm.graph_rows(files)
    return marker, counts, code.lm.drift({store: code.lm.read_marker(session)}, code.lm.digest(files),
                                         code.lm.content(nodes, edges))[0]


def read_stores(stores, local, newest, code, connect=local_load.connect, client_for=workspace_client):
    """(markers, live, lm rows) for sync_stores.drift. A store that cannot be read, or whose settings are missing,
    reads as unreachable with the reason; the others are still read."""
    ss = code.ss
    markers, live, models = {}, {}, []
    for store in stores:
        try:
            if store == "databricks":
                settings = settings_module.load(local.need("settings"))
                if not settings.warehouse_id:
                    raise ls.LocalSettingsError("set [databricks] warehouse_id in kpi_store.toml to read the triple table")
                run_sql = statement_runner(client_for(local.need("databricks").profile), settings.warehouse_id)
                markers[store], live[store], live["databricks_graphs"] = read_databricks(settings, run_sql, ss)
            elif store == "jena":
                markers[store], live[store] = None, ss.read_jena(local.need("fuseki").query_url)
            elif store == "neo4j":
                neo4j = local.need("neo4j_local")
                with connect(neo4j) as driver, driver.session(database=neo4j.database) as session:
                    markers[store], live[store], row = read_neo4j(session, store, newest, code)
                models += [row] if row else []
            else:
                neo4j = local.need("neo4j_enterprise")
                with connect(neo4j) as driver, copy_enterprise.open_target(driver, neo4j.database) as session:
                    markers[store], live[store], row = read_neo4j(session, store, newest, code)
                models += [row] if row else []
        except Exception as err:
            markers[store], live[store] = None, _why(err, ss)
    return markers, live, models


def check(local, release_root, stores=STORES, ref=WORKTREE, extra_graphs=(), code=None, **readers):
    """[(line name, status, why)] for the named stores, then the lm: rows. Reads only."""
    code = code or local_load.release_code(release_root)
    want = expected(release_root, code.ss, ref, extra_graphs)
    markers, live, models = read_stores(stores, local, want["newest"], code, **readers)
    rows = code.ss.drift(markers, live, want, stores)
    return rows + [("lm:" + store, status, why) for store, status, why in models]


def lines(rows):
    return [f"{store:<13} {status:<11} {why}" for store, status, why in rows]


def all_current(rows):
    return all(status == "current" for _, status, _ in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kpi_store.sync_check", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--store", action="append", choices=STORES, help="read and judge only these stores (default: all four)")
    ap.add_argument("--ref", default=WORKTREE, help="whose files say what is current: worktree (the default; needs "
                    "no Git) or a Git ref")
    ap.add_argument("--extra-graphs", help="the JSON file of graphs outside the release that the Fuseki load was given")
    ap.add_argument("--json", action="store_true", help="print the rows as JSON")
    args = ap.parse_args(argv)
    try:
        local = ls.load(ls.locate(args.stores))
        extra = load_fuseki.read_extra_graphs(args.extra_graphs) if args.extra_graphs else {}
        rows = check(local, Path(args.release), tuple(args.store or STORES), args.ref, tuple(extra))
    except (ls.LocalSettingsError, load_fuseki.FusekiError) as err:
        print(f"sync check: {err}", file=sys.stderr)
        return 2
    except (local_load.LoadError, ldb.ov.ReleaseError) as err:
        print(f"sync check: FAILED. {err}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps([{"store": s, "status": status, "why": why} for s, status, why in rows], indent=2))
    else:
        print("\n".join(lines(rows)))
    return 0 if all_current(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
