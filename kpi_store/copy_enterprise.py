"""Copies the verified graph from the local Neo4j to one named database on Neo4j Enterprise, and checks the copy.

    py -m kpi_store.copy_enterprise --stores <local settings file> [--replace]

The Enterprise server has no plugin, so the copy is plain Cypher over the driver (the ontology-to-lpg skill's
copy_graph.py). Run the local load first (kpi_store.load_neo4j): the copy takes only the graph whose hash equals
the load report's.

Where it sits in the run: this is the runner's enterprise step (kpi_store.runner). It runs after the local Neo4j
load and before the sync check. It reads the local database, the load's output folder ([projection] out) and the
release folder. It writes to the one Enterprise database, and to nothing else: no file, and never the local
database.

What this command may touch on Enterprise, enforced in code:
- It writes to ONE database: the one [neo4j.enterprise] database names (businessprocessarchitecturegraph). Every
  session is opened on that name, and the server must answer that this is the database it opened. The system
  database is refused.
- It never creates, drops, starts, stops or alters a database, an alias, a user or a role, and it drops nothing:
  every statement passes one guard that refuses such a statement before it is sent.
- A database that already holds nodes is replaced only on an explicit decision: --replace, or the database's name
  typed at the prompt, which first shows what the database holds. When it holds any node that is not the KPI
  Store's, the command stops and changes nothing, whatever was decided.
- A node is the KPI Store's by what only its own loads write, never by a label alone (OWN_RULES). A Resource
  node, for example, must carry the release tag of one of this release's modules; a node that is merely
  labelled Resource is someone else's. The check of what the database holds and the delete of a replace use
  the same rule, so the replace cannot delete a node the check did not count as the KPI Store's.
- The rule has a limit. A node that carries a release tag of one of this release's modules, a uri, and no label
  but Resource and the projection's own prefixed labels is treated as the KPI Store's, whoever wrote it. So is
  a node that has the shape of a release record, a module or a logical-model node. The copy cannot tell such a
  node from its own, and a replace deletes it. This is acceptable only because the target database is dedicated
  to the KPI Store; do not point [neo4j.enterprise] database at a database other work also writes to.

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
from . import load_fuseki
from . import load_neo4j as local_load
from . import local_settings as ls
from . import ontology_view as ov

STORE = "enterprise"   # the name the target database's marker carries
# What makes a node the KPI Store's: its label AND what only the KPI Store's own load writes on it. The conditions
# read three parameters (own_params): $bases, the IRI every version of each module of the release starts with;
# $store, the store name this copy writes on its markers; $prefixes, what every label of a projected node starts
# with (each prefix of the projection configuration, and the ontology import's own, followed by an underscore).
#   Resource            module_tags.py tags every projected node with its release's version IRI, in `graph`; and the
#                       projection gives a node no label but Resource and prefixed ones (skos_Concept, owl_Class)
#   ModuleRelease       release_record.py writes the release's version IRI
#   Module              module_tags.py's module graph: the node's uri is a version IRI
#   EpmStoreMarker      this copy's own marker: its store name, and the catalog digest
#   LogicalModel        logical_models.py: a uri, and the model's slug or the models the node belongs to
#   LogicalModelMarker  this copy's own marker: its store name, and the digest of the model files
#   Tech                tech_graph.py writes no mark of its own on a node, so the rule is its shape: a uri in the
#                       technical graph's own urn: scheme, and no label but Tech and the names of the
#                       technical-graph module's classes ($tech_classes)
#   TechGraphMarker     this copy's own marker: its store name, and the digest of the graph files
OWN_RULES = {
    "Resource": ("n.uri IS NOT NULL AND any(b IN $bases WHERE toStringOrNull(n.graph) STARTS WITH b) "
                 "AND all(l IN labels(n) WHERE l = 'Resource' OR any(p IN $prefixes WHERE l STARTS WITH p))"),
    "ModuleRelease": "any(b IN $bases WHERE toStringOrNull(n.version_iri) STARTS WITH b)",
    "Module": "any(b IN $bases WHERE toStringOrNull(n.uri) STARTS WITH b)",
    "EpmStoreMarker": "n.store = $store AND n.catalog_digest IS NOT NULL",
    "LogicalModel": "n.uri IS NOT NULL AND (n.models IS NOT NULL OR n.slug IS NOT NULL)",
    "LogicalModelMarker": "n.store = $store AND n.digest IS NOT NULL",
    "Tech": ("toStringOrNull(n.uri) STARTS WITH $tech_base "
             "AND all(l IN labels(n) WHERE l = 'Tech' OR l IN $tech_classes)"),
    "TechGraphMarker": "n.store = $store AND n.digest IS NOT NULL",
}
SCHEMA_PREFIX = "n4sch"   # the ontology import's own labels: n4sch_Class and the like
OWN_LABELS = tuple(OWN_RULES)
# Nodes and relationships per request of the copy, and nodes per transaction of a replace's delete. A batch keeps
# each request and each transaction small enough for the server's memory, whatever the graph's size.
BATCH = 1000
# Seconds the server gives one statement before it ends it with an error. The graph hash reads the whole graph
# and is the slowest statement; without a limit a stuck query would hang the run.
QUERY_TIMEOUT = 600
# Administration of the server, a change of database inside a statement, and any DROP. The first two lines match
# an administration verb followed, in the same statement, by the kind of thing it administers, so CREATE DATABASE
# and ALTER USER are refused while CREATE CONSTRAINT and CREATE (n) pass. The match is on words, so it also
# refuses a harmless statement that holds both, such as a CREATE with the text 'user' in it: the guard errs
# towards refusing. USE is matched only as a statement's first word, where it would send the statement to
# another database. DROP and TERMINATE are refused wherever they stand.
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
        # Parameters go on as the caller gave them, as a dict or as keywords: the driver takes both forms.
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
        # A transaction has its own run(), which would bypass the session's guard, so it is wrapped too.
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
        # db.info() is the server's own answer to "which database is this session on".
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

def own_predicate(rules=OWN_RULES):
    """The Cypher condition that is true for a node `n` of the KPI Store. holdings and remove_own both use it.
    coalesce(..., false) matters: a condition on a missing property gives null, and NOT null is null, so without
    it a node that fails every rule by a missing property would count as neither own nor foreign."""
    return "coalesce(" + " OR ".join(f"(n:{label} AND {condition})" for label, condition in rules.items()) + ", false)"


def own_params(bases, label_prefixes, tech_classes=(), store=STORE):
    """The parameters the conditions of OWN_RULES read. label_prefixes are the projection's prefixes, without the
    underscore: a projected node's labels are Resource and <prefix>_<name>. tech_classes are the names of the
    technical-graph module's classes: a technical-graph node's labels are Tech and such names."""
    from . import tech_graph
    return {"bases": list(bases), "store": store, "prefixes": sorted({f"{p}_" for p in (*label_prefixes, SCHEMA_PREFIX)}),
            "tech_base": tech_graph.BASE, "tech_classes": sorted(tech_classes)}


def tech_class_names(release_root, newest):
    """The local names of the classes the newest technical-graph release declares; none when the release holds no
    such module. They are read from the package file, so a new version's classes are known without a code change."""
    from rdflib import Graph
    from rdflib.namespace import OWL, RDF
    from . import tech_graph
    iri = next((i for i in newest if i.rsplit("/", 2)[-2] == "technical-graph"), None)
    if iri is None:
        return []
    version = iri.rsplit("/", 1)[-1]
    path = Path(release_root) / ov.RELEASES / "technical-graph" / version / "technical-graph.ttl"
    try:
        graph = Graph().parse(str(path), format="turtle")
    except (OSError, ValueError) as err:
        raise Refused(f"the technical-graph package {path} cannot be read ({type(err).__name__})") from None
    return sorted(str(c)[len(tech_graph.TG):] for c in graph.subjects(RDF.type, OWL.Class) if str(c).startswith(tech_graph.TG))


def holdings(session, params, rules=OWN_RULES):
    """What the database holds: {"nodes", "own": {own label: nodes}, "foreign": {label or "(no label)": nodes},
    "foreign_nodes", "foreign_examples"}. A node is foreign unless own_predicate holds for it, whatever its
    labels are. foreign_examples names up to five foreign nodes by their labels and uri."""
    held = {"nodes": 0, "own": {}, "foreign": {}, "foreign_nodes": 0, "foreign_examples": []}
    rows = session.run(f"MATCH (n) WITH labels(n) AS labels, {own_predicate(rules)} AS own "
                       "RETURN own, labels, count(*) AS n", **params).data()
    for row in rows:
        labels, n = row["labels"], row["n"]
        held["nodes"] += n
        if row["own"]:
            # An own node is counted once, under the first of the rules' labels it carries.
            first = next(label for label in rules if label in labels)
            held["own"][first] = held["own"].get(first, 0) + n
        else:
            held["foreign_nodes"] += n
            for label in labels or ["(no label)"]:
                held["foreign"][label] = held["foreign"].get(label, 0) + n
    if held["foreign_nodes"]:
        found = session.run(f"MATCH (n) WHERE NOT {own_predicate(rules)} "
                            "RETURN labels(n) AS labels, n.uri AS uri ORDER BY toStringOrNull(n.uri) LIMIT 5", **params).data()
        held["foreign_examples"] = [":".join(r["labels"]) + (f" {r['uri']}" if r["uri"] else "") for r in found]
    return held


def describe(counts):
    """The counts as text for a message: "12 ModuleRelease, 4810 Resource"."""
    return ", ".join(f"{n} {label}" for label, n in sorted(counts.items())) or "nothing"


def decide(held, database, replace=False, confirm=None):
    """"empty" or "replace". Raises Refused when the database holds foreign nodes, whatever was decided, and when it
    holds the KPI Store's nodes and nobody decided to replace them. confirm(text) asks a person and returns
    what they typed."""
    if not held["nodes"]:
        return "empty"
    # Foreign nodes are checked before the decision is read, so --replace cannot get past them.
    if held["foreign_nodes"]:
        raise Refused(f"the database {database} holds {held['foreign_nodes']} node(s) that are not the KPI Store's, "
                      f"by label: {describe(held['foreign'])}; for example {', '.join(held.get('foreign_examples') or ['(none read)'])}. "
                      "Nothing was changed, and this command will not delete them. Check [neo4j.enterprise] database, "
                      "or ask the owner of those nodes")
    what = (f"the database {database} holds {held['nodes']} node(s) that carry the KPI Store's own marks (its release "
            f"tags, release records, logical models and markers), by label: {describe(held['own'])}")
    if replace:
        return "replace"
    if confirm is not None and confirm(f"{what}.\nType the database's name to replace them, or press Enter to stop: ").strip() == database:
        return "replace"
    raise Refused(f"{what}. Nothing was changed. Run the command again with --replace to replace them. The replace "
                  "deletes every node that carries those marks, so the database must be the KPI Store's alone")


def remove_own(session, params, rules=OWN_RULES, batch=BATCH):
    """Deletes the KPI Store's nodes, in batches: exactly the nodes own_predicate holds for, never every node."""
    session.run(f"MATCH (n) WHERE {own_predicate(rules)} CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS OF {int(batch)} ROWS",
                **params).consume()


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
    # The module graph is written only after the tags passed: it is built from the same packages.
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
         own_rules=OWN_RULES, log=None):
    """The whole step. Returns a dict whose "status" is "current" (nothing was changed) or "copied". Raises
    Refused when the copy is refused or a check fails.

    extra_loads are functions (session, store name) -> dict that load a subgraph of their own after the logical
    models and before the marker; own_rules must then also hold that subgraph's labels, each with the condition
    that only its loader's nodes meet. The technical graph joins here."""
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
    # Everything up to decide() only reads. The order of the refusals matters: each one below leaves the target
    # as it was found.
    with connect(source_cfg) as source_driver, connect(target_cfg) as target_driver, \
            source_driver.session(database=source_cfg.database) as raw_source, \
            open_target(target_driver, database) as guarded:
        source, target = code.lv.Timed(raw_source, QUERY_TIMEOUT), code.lv.Timed(guarded, QUERY_TIMEOUT)
        # Compared by the server's own database ID: two addresses can reach one database.
        if code.cg.database_identity(source) == code.cg.database_identity(target):
            raise Refused("the target is the local database itself; nothing was changed. [neo4j.enterprise] must "
                          "name another database than [neo4j.local]")
        # The local graph is hashed again now. It may have changed since the load report was written, and only
        # the graph the report verified may be copied.
        source_hash = code.cg.graph_hash(source)
        if source_hash != report["determinism_hash_sorted"]:
            raise Refused("the local graph is not the graph the load report verified; nothing was changed on "
                          "Enterprise. Run the local Neo4j load again")
        prefixes = code.build.load_config(cfg_doc["projection_config"]).prefixes
        params = own_params(load_fuseki.module_bases(code.ss), prefixes, tech_class_names(release_root, want["newest"]))
        held = holdings(target, params, own_rules)
        if held["nodes"] and not held["foreign_nodes"] and local_load.is_current(target, STORE, want, report, code, sep) \
                and local_load.models_status(target, STORE, want["newest"], code)[1] in ("current", "none"):
            # The ontology's copy is current. A subgraph beside it may still be behind, so its load runs; it
            # leaves a current subgraph alone.
            try:
                extras = [extra(target, STORE) for extra in extra_loads]
            except local_load.LoadError as err:
                raise Refused(str(err)) from None
            return {**result, "status": "current", "nodes": report["nodes"], "relationships": report["relationships"],
                    "graph_hash": source_hash, "held_before": held, "extra_loads": extras,
                    "marker": code.ss.read_neo4j(target, STORE)[0]}
        action = decide(held, database, replace, confirm)
        # From here the target changes. The marker is written last, after every check passed, so a copy that
        # stops part-way leaves a database with no current marker, and the sync check reads it as not current.
        if action == "replace":
            remove_own(target, params, own_rules)
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
        try:
            extras = [extra(target, STORE) for extra in extra_loads]
            marker = local_load.mark(target, STORE, want, report, code.ss, local_load.release_label(release_root, code.ss))
        except local_load.LoadError as err:
            raise Refused(str(err)) from None
    return {**result, "status": "copied", "replaced": action == "replace", "held_before": held,
            "nodes": copied["nodes"], "relationships": copied["relationships"], "graph_hash": target_hash,
            "release_records": records, "modules": modules, "logical_models": models, "extra_loads": extras,
            "marker": marker}


def line(result):
    """The one line a person reads."""
    return (f"neo4j (enterprise, database {result['database']}): {result['status']}, {result['nodes']} nodes, "
            f"{result['relationships']} relationships, graph hash {result['graph_hash']} equal to the local graph's"
            + local_load.extras_text(result))


def ask(text):
    """The prompt of the replace decision. main() uses it only when a person is at the terminal."""
    return input(text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kpi_store.copy_enterprise", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--tech-graph", help="the technical graph's file, tech-graph.nq, to load beside the ontology")
    ap.add_argument("--replace", action="store_true",
                    help="replace the KPI Store's nodes the target database already holds; never anyone else's")
    ap.add_argument("--json", action="store_true", help="print the result as JSON instead of one line")
    args = ap.parse_args(argv)
    try:
        local = ls.load(ls.locate(args.stores), release_root=Path(args.release))
        # With no terminal, as under the runner or a scheduler, nobody can type the name: only --replace decides.
        confirm = ask if sys.stdin is not None and sys.stdin.isatty() else None
        extras = (local_load.tech_graph_loader([Path(args.tech_graph)], Path(args.release)),) if args.tech_graph else ()
        result = copy(local, Path(args.release), replace=args.replace, confirm=confirm, extra_loads=extras)
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
