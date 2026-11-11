"""Copies the verified graph from the local Neo4j to one named database on Neo4j Enterprise, and checks the copy.

    py -m kpi_store.copy_enterprise --stores <local settings file> [--replace]

The Enterprise server has no plugin, so the copy is plain Cypher over the driver (the ontology-to-lpg skill's
copy_graph.py). Run the local load first (kpi_store.load_neo4j): the copy takes only the graph whose hash equals
the load report's.

What this command may touch on Enterprise, enforced in code:
- It writes to ONE database: the one [neo4j.enterprise] database names (businessprocessarchitecturegraph). Every
  session is opened on that name, and the server must answer that this is the database it opened. The system
  database is refused.
- It never creates, drops, starts, stops or alters a database, an alias, a user or a role, and it drops nothing:
  every statement passes one guard that refuses such a statement before it is sent.
- A database that already holds nodes is replaced only on an explicit decision: --replace, or the database's name
  typed at the prompt, which first shows what the database holds. When it holds any node that is not the KPI
  Store's, the command stops and changes nothing, whatever was decided. The KPI Store's nodes carry one of the
  labels in OWN_LABELS; the replace deletes those nodes only.

After the copy, in the target database: the graph hash must equal the local graph's, the counts must equal the
load report's, the release records are written and read back, each node's and relationship's release tag is
checked, the module graph and the logical models are written, and the marker (a node labelled EpmStoreMarker)
is written last. A second run finds the marker and an equal hash, and changes nothing.

No password is printed. Needs rdflib and neo4j. Exit 0 when the copy is current or passed, 1 when it was refused
or a check failed, 2 on bad settings.
"""
import argparse
import io
import json
import re
import sys
from pathlib import Path

from . import load_databricks as ldb
from . import load_neo4j as local_load
from . import local_settings as ls
from . import ontology_view as ov

STORE = "enterprise"   # the name the target database's marker carries
# The labels of the nodes the KPI Store writes: the ontology, its release records and module graph, the marker, and
# the logical models with their marker. A node with none of them is someone else's.
OWN_LABELS = ("Resource", "ModuleRelease", "Module", "EpmStoreMarker", "LogicalModel", "LogicalModelMarker")
BATCH = 1000
QUERY_TIMEOUT = 600
# Administration of the server, a change of database inside a statement, and any DROP.
FORBIDDEN = re.compile(
    r"\b(CREATE|ALTER|START|STOP|RENAME|GRANT|DENY|REVOKE|ENABLE|DEALLOCATE|REALLOCATE)\b[^;]*?"
    r"\b(DATABASE|ALIAS|SERVER|USER|ROLE|PRIVILEGE)S?\b|^\s*USE\b|\bDROP\b|\bTERMINATE\b", re.IGNORECASE)


class Refused(Exception):
    """The copy was refused or a check failed. The message says why and what was, or was not, changed."""


# ---- the one target database ------------------------------------------------------------------------

def checked_name(name):
    """The target database's name, from the settings. Refuses an empty name and the system database."""
    name = (name or "").strip()
    if not name or name.lower() == ls.SYSTEM_DATABASE:
        raise Refused("[neo4j.enterprise] database must name the target database, and never the system database")
    return name


def check_statement(statement):
    """Raises Refused for a statement this command must never send to Enterprise."""
    text = getattr(statement, "text", statement)
    if not isinstance(text, str) or FORBIDDEN.search(text):
        raise Refused("refused: a statement that would administer the server, change database or drop something "
                      "was not sent to Enterprise")


class _Guarded:
    """Passes run() through check_statement. Everything else goes to the wrapped session or transaction."""

    def __init__(self, inner):
        self._inner = inner

    def run(self, query, parameters=None, **kwargs):
        check_statement(query)
        return self._inner.run(query, **kwargs) if parameters is None else self._inner.run(query, parameters, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TargetSession(_Guarded):
    """The only way this module talks to Enterprise: a session on the named database whose every statement, in or
    out of a transaction, passes the guard."""

    def __init__(self, session, database):
        super().__init__(session)
        self.database = database

    def begin_transaction(self, *args, **kwargs):
        return _Guarded(self._inner.begin_transaction(*args, **kwargs))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._inner.close()


def open_target(driver, name):
    """A TargetSession on the named database. The server must confirm the name: a default database, or an alias that
    leads elsewhere, is refused before anything is read or written."""
    name = checked_name(name)
    session = driver.session(database=name)
    try:
        opened = session.run("CALL db.info() YIELD name RETURN name").single()["name"]
    except Exception as err:
        session.close()
        if type(err).__name__ in ("DatabaseNotFound", "ClientError") and "NotFound" in str(getattr(err, "code", "")):
            raise Refused(f"the server has no database named {name}. This command never creates one: ask the "
                          "server's administrator, or correct [neo4j.enterprise] database") from None
        raise
    if str(opened).lower() != name.lower():
        session.close()
        raise Refused(f"the server opened the database {opened}, not {name}; nothing was read or written. "
                      "Name the database itself in [neo4j.enterprise] database, not an alias")
    return TargetSession(session, name)


# ---- what the target holds, and the decision to replace it ----------------------------------------

def holdings(session, own=OWN_LABELS):
    """What the database holds: {"nodes", "own": {own label: nodes}, "foreign": {label or "(no label)": nodes},
    "foreign_nodes"}. A node is foreign when it carries none of the own labels."""
    held = {"nodes": 0, "own": {}, "foreign": {}, "foreign_nodes": 0}
    for row in session.run("MATCH (n) RETURN labels(n) AS labels, count(*) AS n").data():
        labels, n = row["labels"], row["n"]
        held["nodes"] += n
        mine = [label for label in own if label in labels]
        if mine:
            held["own"][mine[0]] = held["own"].get(mine[0], 0) + n
        else:
            held["foreign_nodes"] += n
            for label in labels or ["(no label)"]:
                held["foreign"][label] = held["foreign"].get(label, 0) + n
    return held


def describe(counts):
    return ", ".join(f"{n} {label}" for label, n in sorted(counts.items())) or "nothing"


def decide(held, database, replace=False, confirm=None):
    """"empty" or "replace". Raises Refused when the database holds foreign nodes, whatever was decided, and when it
    holds the KPI Store's nodes and nobody decided to replace them. confirm(text) asks a person and returns
    what they typed."""
    if not held["nodes"]:
        return "empty"
    if held["foreign_nodes"]:
        raise Refused(f"the database {database} holds {held['foreign_nodes']} node(s) that are not the KPI Store's, "
                      f"by label: {describe(held['foreign'])}. Nothing was changed, and this command will not "
                      "delete them. Check [neo4j.enterprise] database, or ask the owner of those nodes")
    what = f"the database {database} holds {held['nodes']} node(s) of the KPI Store, by label: {describe(held['own'])}"
    if replace:
        return "replace"
    if confirm is not None and confirm(f"{what}.\nType the database's name to replace them, or press Enter to stop: ").strip() == database:
        return "replace"
    raise Refused(f"{what}. Nothing was changed. Run the command again with --replace to replace them")


def remove_own(session, own=OWN_LABELS, batch=BATCH):
    """Deletes the KPI Store's nodes, one own label at a time, in batches. Never every node."""
    for label in own:
        session.run(f"MATCH (n:{label}) CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS OF {int(batch)} ROWS").consume()


# ---- the checks after the copy ----------------------------------------------------------------------

def check_tags(target, out, cfg_doc, code):
    """The release tag of every node and relationship, checked as module_tags.py check does, and the module graph
    written as module_tags.py modules does. Returns the number of problems' kinds that failed."""
    from rdflib import Graph
    try:
        manifest = json.loads((Path(out) / local_load.RUN_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused(f"there is no {local_load.RUN_MANIFEST} in {out}; run the local Neo4j load first") from None
    packages = code.mt.read_packages([entry["path"] for entry in manifest["data"]])
    inferred = Graph().parse(str(Path(out) / local_load.INFERRED), format="nt")
    prefixes = dict(code.build.load_config(cfg_doc["projection_config"]).prefixes)
    run = lambda statement, **params: target.run(statement, params).data()   # noqa: E731
    _, _, problems = code.mt.check(run, *code.mt.expected_tags(packages, inferred), prefixes, cfg_doc.get("separator"))
    failed = sorted(kind for kind, items in problems.items() if items)
    if failed:
        raise Refused(f"the copy's release tags differ from the packages' ({', '.join(failed)}); no marker was written")
    modules, requirements = code.mt.module_rows(packages)
    run(code.mt.CLEAR_MODULES)
    run(code.mt.MODULES, mods=modules)
    run(code.mt.REQUIRES, reqs=requirements)
    return len(modules)


def write_records(target, out, code):
    """Writes the run's release records to the target and reads them back (release_record.py write and check)."""
    try:
        content = json.loads((Path(out) / local_load.RECORDS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused(f"there is no {local_load.RECORDS} in {out}; run the local Neo4j load first") from None
    problems, _ = code.rr.write(target, content)
    problems = problems or code.rr.check(target, content)
    if problems:
        raise Refused(f"the release records could not be written to the target: {problems[0]}")
    return len(content["records"])


# ---- the copy ------------------------------------------------------------------------------------

def copy(local, release_root, replace=False, confirm=None, code=None, connect=local_load.connect, extra_loads=(),
         own_labels=OWN_LABELS, log=None):
    """The whole step. Returns a dict whose "status" is "current" (nothing was changed) or "copied". Raises
    Refused when the copy is refused or a check fails.

    extra_loads are functions (session, store name) -> dict that load a subgraph of their own after the logical
    models and before the marker; own_labels must then also name that subgraph's labels. The technical graph
    joins here."""
    code = code or local_load.release_code(release_root)
    source_cfg, target_cfg = local.need("neo4j_local"), local.need("neo4j_enterprise")
    out = local.need("projection_out")
    database = checked_name(target_cfg.database)
    want = ldb.expected(release_root, code.ss)
    try:
        report = local_load.read_report(out, code, want)
    except local_load.LoadError as err:
        raise Refused(str(err)) from None
    cfg_doc = local_load.run_config(release_root, local, "")
    sep = cfg_doc.get("separator", code.lv.N10S_SEP)
    result = {"store": STORE, "database": database}
    with connect(source_cfg) as source_driver, connect(target_cfg) as target_driver, \
            source_driver.session(database=source_cfg.database) as raw_source, \
            open_target(target_driver, database) as guarded:
        source, target = code.lv.Timed(raw_source, QUERY_TIMEOUT), code.lv.Timed(guarded, QUERY_TIMEOUT)
        # Compared by the server's own database ID: two addresses can reach one database.
        if code.cg.database_identity(source) == code.cg.database_identity(target):
            raise Refused("the target is the local database itself; nothing was changed. [neo4j.enterprise] must "
                          "name another database than [neo4j.local]")
        source_hash = code.cg.graph_hash(source)
        if source_hash != report["determinism_hash_sorted"]:
            raise Refused("the local graph is not the graph the load report verified; nothing was changed on "
                          "Enterprise. Run the local Neo4j load again")
        held = holdings(target, own_labels)
        if held["nodes"] and not held["foreign_nodes"] and local_load.is_current(target, STORE, want, report, code, sep) \
                and local_load.models_status(target, STORE, want["newest"], code)[1] in ("current", "none"):
            return {**result, "status": "current", "nodes": report["nodes"], "relationships": report["relationships"],
                    "graph_hash": source_hash, "held_before": held, "marker": code.ss.read_neo4j(target, STORE)[0]}
        action = decide(held, database, replace, confirm)
        if action == "replace":
            remove_own(target, own_labels)
        copied = code.cg.copy(source, target, BATCH)
        target_hash = code.cg.graph_hash(target)
        if target_hash != source_hash:
            raise Refused(f"the copy's graph hash {target_hash} differs from the local graph's {source_hash}; "
                          "no marker was written. Run the command again with --replace")
        records = write_records(target, out, code)
        modules = check_tags(target, out, cfg_doc, code)
        try:
            models = local_load.load_models(target, STORE, want["newest"], code, log if log is not None else io.StringIO())
        except local_load.LoadError as err:
            raise Refused(str(err)) from None
        extras = [extra(target, STORE) for extra in extra_loads]
        try:
            marker = local_load.mark(target, STORE, want, report, code.ss, local_load.release_label(release_root, code.ss))
        except local_load.LoadError as err:
            raise Refused(str(err)) from None
    return {**result, "status": "copied", "replaced": action == "replace", "held_before": held,
            "nodes": copied["nodes"], "relationships": copied["relationships"], "graph_hash": target_hash,
            "release_records": records, "modules": modules, "logical_models": models, "extra_loads": extras,
            "marker": marker}


def line(result):
    return (f"neo4j (enterprise, database {result['database']}): {result['status']}, {result['nodes']} nodes, "
            f"{result['relationships']} relationships, graph hash {result['graph_hash']} equal to the local graph's")


def ask(text):
    return input(text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kpi_store.copy_enterprise", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--replace", action="store_true",
                    help="replace the KPI Store's nodes the target database already holds; never anyone else's")
    ap.add_argument("--json", action="store_true", help="print the result as JSON instead of one line")
    args = ap.parse_args(argv)
    try:
        local = ls.load(ls.locate(args.stores))
        confirm = ask if sys.stdin is not None and sys.stdin.isatty() else None
        result = copy(local, Path(args.release), replace=args.replace, confirm=confirm)
    except ls.LocalSettingsError as err:
        print(f"neo4j (enterprise): {err}", file=sys.stderr)
        return 2
    except (Refused, ov.ReleaseError) as err:
        print(f"neo4j (enterprise): STOPPED. {err}", file=sys.stderr)
        return 1
    except Exception as err:   # a driver error's text can carry an address, so only its type is printed
        print(f"neo4j (enterprise): FAILED. A server did not answer, or a statement failed ({type(err).__name__}). "
              "The target database may hold a partial copy; run the command again with --replace", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str) if args.json else line(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
