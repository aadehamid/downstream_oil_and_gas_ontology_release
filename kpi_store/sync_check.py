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

For a Neo4j database, equal counts are not enough: a property can change while the counts stay. So the check also
computes the database's graph hash, as the load does, and compares it with the hash its marker holds. A database
whose hash differs reads changed. --quick leaves the hash out, and each Neo4j line then says "counts only".

The technical graph gets a tech: line per store when its file is known: --tech-graph <tech-graph.nq>, or the
file the runner fetched into <run folder>/tech-graph/. Each line is the technical graph's own judgement
(kpi_store.tech_graph), which reads the store's copy back and compares its content with the file. Without a file
each tech: line reads "not checked", and the command does not pass: a technical graph nobody compared is not
current. --no-tech-graph leaves the technical graph out on purpose; one line says so, and the other lines decide.

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
TECH_FOLDER = "tech-graph"   # in the run folder: the technical graph's file as the runner last fetched it
NOT_CHECKED, LEFT_OUT = "not checked", "left out"
NO_FILE = ("no tech-graph.nq was named or fetched, so its content was not compared; name the file with --tech-graph, "
           "or let the runner's report step fetch it")
NEO4J_STORES = ("neo4j", "enterprise")
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


def read_neo4j(session, store, newest, code, quick=False):
    """(marker, counts, the live graph hash or None, the logical models' lm: row or None) of one Neo4j database.
    The hash is computed only for a marked database, and not with quick."""
    marker, counts = code.ss.read_neo4j(session, store)
    live_hash = code.lv.hash_graph(session)[0] if marker and not quick else None
    files = code.lm.models(newest)
    if not files:
        return marker, counts, live_hash, None
    nodes, edges = code.lm.graph_rows(files)
    return marker, counts, live_hash, code.lm.drift({store: code.lm.read_marker(session)}, code.lm.digest(files),
                                                    code.lm.content(nodes, edges))[0]


def judge_hashes(rows, markers, hashes, quick=False):
    """The rows with each Neo4j database that drift read as current judged by its content too: its live graph hash
    must equal the hash its marker holds. With quick the row stays and says that only counts were compared."""
    judged = []
    for store, status, why in rows:
        if store in NEO4J_STORES and status == "current":
            marked = (markers.get(store) or {}).get(local_load.MARKER_HASH)
            if quick:
                why += " (counts only: --quick left the graph hash out)"
            elif not marked:
                status, why = "changed", "its marker holds no graph hash, so its content cannot be compared; load it again"
            elif hashes.get(store) != marked:
                status, why = "changed", "its content differs from the graph it was marked with, although the counts are equal"
            else:
                why += f"; graph hash {marked[:12]} equal to the marker's"
        judged.append((store, status, why))
    return judged


def read_stores(stores, local, newest, code, connect=local_load.connect, client_for=workspace_client, quick=False):
    """(markers, live, lm rows, live graph hashes) for sync_stores.drift and judge_hashes. A store that cannot be
    read, or whose settings are missing, reads as unreachable with the reason; the others are still read."""
    ss = code.ss
    markers, live, models, hashes = {}, {}, [], {}
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
                    markers[store], live[store], hashes[store], row = read_neo4j(session, store, newest, code, quick)
                models += [row] if row else []
            else:
                neo4j = local.need("neo4j_enterprise")
                with connect(neo4j) as driver, copy_enterprise.open_target(driver, neo4j.database) as session:
                    markers[store], live[store], hashes[store], row = read_neo4j(session, store, newest, code, quick)
                models += [row] if row else []
        except Exception as err:
            markers[store], live[store] = None, _why(err, ss)
    return markers, live, models, hashes


def check(local, release_root, stores=STORES, ref=WORKTREE, extra_graphs=(), code=None, quick=False, tech_graph_files=None,
          no_tech_graph=False, **readers):
    """[(line name, status, why)] for the named stores, then the lm: rows, then the technical graph's rows: one
    tech: row per store judged against its files; without files, one per store that reads "not checked", which is
    never current; with no_tech_graph, one row that says it was left out on request. Reads only."""
    code = code or local_load.release_code(release_root)
    if tech_graph_files:   # its named graphs are no part of the release, so the ontology's own check leaves them out
        from . import tech_graph
        extra_graphs = tuple(extra_graphs) + tuple(tech_graph.jena_apart(tech_graph_files))
    want = expected(release_root, code.ss, ref, extra_graphs)
    markers, live, models, hashes = read_stores(stores, local, want["newest"], code, quick=quick, **readers)
    rows = judge_hashes(code.ss.drift(markers, live, want, stores), markers, hashes, quick)
    rows += [("lm:" + store, status, why) for store, status, why in models]
    if no_tech_graph:
        rows.append(("tech", LEFT_OUT, "the technical graph was left out on request"))
    elif tech_graph_files:
        rows += tech_rows(stores, local, tech_graph_files, release_root, code, **readers)
    else:
        rows += [("tech:" + store, NOT_CHECKED, NO_FILE) for store in stores]
    return rows


def tech_graph_file(local, argument=None):
    """The technical graph's file: the one named, else the one the runner last fetched. None when there is none."""
    from . import tech_graph
    if argument:
        path = Path(argument)
        if not path.is_file():
            raise ls.LocalSettingsError(f"the technical graph file {path} is missing")
        return path
    path = local.run_folder / TECH_FOLDER / tech_graph.GRAPH_FILE if local.run_folder else None
    return path if path is not None and path.is_file() else None


def tech_rows(stores, local, graph_files, release_root, code, connect=local_load.connect, client_for=workspace_client):
    """[("tech:<store>", status, why)] of the technical graph in each named store, judged by kpi_store.tech_graph
    against the graph files. A store that cannot be read reads as unreachable."""
    from . import tech_graph
    rows = []
    for store in stores:
        try:
            if store == "databricks":
                settings = settings_module.load(local.need("settings"))
                if not settings.warehouse_id:
                    raise ls.LocalSettingsError("set [databricks] warehouse_id in kpi_store.toml to read the technical graph table")
                gate = ldb.Gate(settings, statement_runner(client_for(local.need("databricks").profile), settings.warehouse_id))
                status, why = tech_graph.status_delta(gate, settings, graph_files, release_root)
            elif store == "jena":
                status, why = tech_graph.status_jena(local.need("fuseki").query_url, graph_files, release_root)
            elif store == "neo4j":
                neo4j = local.need("neo4j_local")
                with connect(neo4j) as driver, driver.session(database=neo4j.database) as session:
                    status, why = tech_graph.status_neo4j(session, graph_files, release_root)
            else:
                neo4j = local.need("neo4j_enterprise")
                with connect(neo4j) as driver, copy_enterprise.open_target(driver, neo4j.database) as session:
                    status, why = tech_graph.status_neo4j(session, graph_files, release_root)
        except Exception as err:
            status, why = "unreachable", _why(err, code.ss)
        rows.append(("tech:" + store, status, why))
    return rows


def lines(rows):
    return [f"{store:<15} {status:<11} {why}" for store, status, why in rows]


def all_current(rows):
    """True when every row reads current. A row left out on request does not decide; a row not checked is not
    current."""
    return all(status == "current" for _, status, _ in rows if status != LEFT_OUT)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kpi_store.sync_check", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--store", action="append", choices=STORES, help="read and judge only these stores (default: all four)")
    ap.add_argument("--ref", default=WORKTREE, help="whose files say what is current: worktree (the default; needs "
                    "no Git) or a Git ref")
    ap.add_argument("--extra-graphs", help="the JSON file of graphs outside the release that the Fuseki load was given")
    ap.add_argument("--tech-graph", help="the technical graph's file, tech-graph.nq (default: the one the runner "
                    "last fetched into the run folder)")
    ap.add_argument("--no-tech-graph", action="store_true",
                    help="leave the technical graph out on purpose; without this, a technical graph with no file to "
                         "compare reads not checked and the command does not pass")
    ap.add_argument("--quick", action="store_true",
                    help="compare a Neo4j database's counts only, not its graph hash; each such line says so")
    ap.add_argument("--json", action="store_true", help="print the rows as JSON")
    args = ap.parse_args(argv)
    try:
        local = ls.load(ls.locate(args.stores), release_root=Path(args.release))
        extra = load_fuseki.read_extra_graphs(args.extra_graphs) if args.extra_graphs else {}
        if args.no_tech_graph and args.tech_graph:
            raise ls.LocalSettingsError("give --tech-graph or --no-tech-graph, not both")
        tech = None if args.no_tech_graph else tech_graph_file(local, args.tech_graph)
        rows = check(local, Path(args.release), tuple(args.store or STORES), args.ref, tuple(extra), quick=args.quick,
                     tech_graph_files=[tech] if tech else None, no_tech_graph=args.no_tech_graph)
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
