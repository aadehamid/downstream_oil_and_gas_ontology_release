"""Says what a current ontology store holds, and judges a store against it.

Three stores hold the release: a Neo4j database, a Jena dataset and the Delta triple table in Databricks.
- Neo4j and Databricks each hold a marker that says which release set they were loaded from: the catalog's datasets
  (their count and a digest of their IRIs, from releases/catalog.ttl) and the projection's input fingerprint
  (projection-manifest.json). In Neo4j the marker is a node labelled EpmStoreMarker, never Resource, so the
  projection's counts, hash and round trip do not read it. In Databricks it is a row of epm_store_markers, beside
  epm_triples.
- Jena holds no marker. Its named graphs are version IRIs, so its graph names and each graph's triple count are
  compared with the newest release files.
- When the newest releases hold the logical-model module, Jena and the triple table also hold each package graph its
  manifest lists (package_graphs). A Neo4j database holds the models as a subgraph apart from the projection, which
  check reports on an lm:neo4j line (logical_models.py).

    python3 sync_stores.py expected [--ref <git ref>]             # what a current store holds
    python3 sync_stores.py check [--store neo4j] [--store jena]   # judge the stores the settings name
    python3 sync_stores.py mark                                   # check the Neo4j database, then write its marker

This file reads Neo4j over Bolt and Jena over its SPARQL query URL. It does not connect to Databricks: the load that
writes the triple table also writes its marker (marker), and a caller that has read the table and the marker passes
them to drift. Every expectation comes from this tree's files. --ref reads them at a Git ref instead.

In the KPI Store load this file is a library, not a step of the runner. Each store load under kpi_store/ (Databricks,
Fuseki, the local Neo4j, the copy to Enterprise) and the sync check import it from the release folder and ask it the
same things: what a current store holds (expected, jena_graphs), what a marker looks like (marker) and how a store
compares (drift). So the loads and the sync check cannot disagree on what "current" means. Those callers bring their
own settings and connections. The three commands above, with the settings below, are for a run by hand.
The only writes here are mark's: one marker node in Neo4j. Nothing here writes a file, Jena or Databricks.

The settings come from one place (settings): the file EPM_STORES_ENV names, kept outside the repository, and the
process environment, which wins. No password is printed.
Needs rdflib; check and mark also need neo4j (uv run --with ...).
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "release"))
import newest as release_newest  # noqa: E402  (the one version order; standard library only)
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
CATALOG = "business_architecture/ontology/releases/catalog.ttl"
MANIFEST = "business_architecture/ontology/projection/projection-manifest.json"
REPORT = os.path.join(HERE, "projection-report.json")
TRIPLES_TABLE = "epm_triples"
MARKER_TABLE = "epm_store_markers"
MARKER_LABEL = "EpmStoreMarker"
RELEASE_GRAPHS = ("shapes", "catalog")  # skill-run/epm-run.json's "release_graphs"
STORES = ("neo4j", "jena", "databricks")
READ_HERE = ("neo4j", "jena")  # the stores check and mark connect to
MARKER_FIELDS = ("catalog_datasets", "catalog_digest", "input_fingerprint")
WORKTREE = "worktree"  # the ref that means this tree's files
DEFAULT_GRAPH = "(the default graph)"  # triples outside any named graph: no release graph has this name, so they read as a stray
SETTINGS = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE", "EPM_JENA_QUERY")


# ---------- the settings ----------

class Unset(LookupError):
    """A setting a command needs has no value. The message is the setting's name, never a value."""


def read_env(path):
    """The KEY=value lines of a file. Blank lines and lines that start with # are skipped."""
    values = {}
    with open(os.path.expanduser(path), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def settings(environ=None):
    """The store endpoints and the Neo4j login, read from one place.

    NEO4J_URI (Bolt), NEO4J_USERNAME (default neo4j), NEO4J_PASSWORD, NEO4J_DATABASE (default: the server's own
    default database) and EPM_JENA_QUERY (the dataset's SPARQL query URL). The file EPM_STORES_ENV names gives them;
    a value in the process environment wins. Nothing has a default address: a command that needs a missing setting
    stops and names it (need)."""
    environ = os.environ if environ is None else environ
    found = read_env(environ["EPM_STORES_ENV"]) if environ.get("EPM_STORES_ENV") else {}
    found.update({k: environ[k] for k in SETTINGS if environ.get(k)})
    return {k: found[k] for k in SETTINGS if found.get(k)}


def need(values, key):
    if not values.get(key):
        raise Unset(key)
    return values[key]


def reason(err):
    """Why a store could not be read: the error's name, never its message, which can carry an address. An unset
    setting adds its name."""
    return f"unreachable ({type(err).__name__}{': ' + str(err) if isinstance(err, Unset) else ''})"


# ---------- what a current store holds ----------

def repo_file(path, ref=None):
    """A file's text in this tree, or at a Git ref. The ref `worktree`, like None, reads the tree itself, so a tree
    without Git works."""
    if ref is None or ref == WORKTREE:
        with open(os.path.join(REPO, path), encoding="utf-8") as f:
            return f.read()
    return subprocess.run(["git", "-C", REPO, "show", f"{ref}:{path}"], check=True, capture_output=True,
                          encoding="utf-8").stdout


def repo_bytes(path, ref=None):
    """A file's bytes in this tree, or at a Git ref, as repo_file reads its text."""
    if ref is None or ref == WORKTREE:
        with open(os.path.join(REPO, path), "rb") as f:
            return f.read()
    return subprocess.run(["git", "-C", REPO, "show", f"{ref}:{path}"], check=True, capture_output=True).stdout


def catalog_datasets(text):
    """The dataset IRIs a catalog lists, sorted."""
    from rdflib import Graph, Namespace
    DCAT = Namespace("http://www.w3.org/ns/dcat#")
    return sorted(str(d) for d in Graph().parse(data=text, format="turtle").objects(None, DCAT.dataset))


def newest_releases(datasets):
    """Each module's newest release IRI, .../modules/<module>/<version>, by the release scripts' version_key, so a
    correction version is read as newer than the version it corrects. A version it cannot order is a ValueError."""
    newest = {}
    for iri in datasets:
        module, version = iri.rsplit("/", 2)[-2:]
        key = release_newest.version_key(version)
        if key is None:
            raise ValueError(f"the catalog lists {iri}, whose version this code cannot order")
        if module not in newest or key > newest[module][0]:
            newest[module] = (key, iri)
    return sorted(iri for _, iri in newest.values())


def expected(ref=None):
    """What a current store's marker holds (MARKER_FIELDS), and the newest release IRIs.

    The two kinds of field catch two kinds of change. The catalog's count and digest move when a release is added to
    or taken out of the catalog. The input fingerprint moves when the triples the projection loads change. A store is
    current only when its marker equals all three."""
    datasets = catalog_datasets(repo_file(CATALOG, ref))
    return {"catalog_datasets": len(datasets),
            "catalog_digest": hashlib.sha256("\n".join(datasets).encode()).hexdigest(),
            "input_fingerprint": json.loads(repo_file(MANIFEST, ref))["input_fingerprint"],
            "newest": newest_releases(datasets)}


def extra_graph_files(module, manifest):
    """The Turtle files a package's manifest lists beside its content and its release graphs: the graphs it carries as
    they are (build_module.py's "graphs"), such as a logical model's ER Studio export and annotation layer. The logical-model package
    has them (the decision of 2026-11-02, amendment "the stores")."""
    own = {f"{module}.ttl", *(f"{n}.ttl" for n in RELEASE_GRAPHS)}
    return sorted(n for n in manifest.get("files", {}) if n.endswith(".ttl") and n not in own)


def package_graphs(iri, ref=None):
    """{graph IRI: path under the repository} of a release's package graphs (extra_graph_files), each named
    <version IRI>/<file name without .ttl>, as the release graphs are named <version IRI>/<name>."""
    module, version = iri.rsplit("/", 2)[-2:]
    folder = f"business_architecture/ontology/releases/{module}/{version}"
    try:
        manifest = json.loads(repo_file(f"{folder}/manifest.json", ref))
    except (OSError, subprocess.CalledProcessError):  # a package with no manifest carries no graph of its own
        return {}
    return {f"{iri}/{n[:-len('.ttl')]}": f"{folder}/{n}" for n in extra_graph_files(module, manifest)}


def jena_graphs(newest, ref=None):
    """{graph IRI: triple count} that a current Jena holds, and the triple table too: for each newest release, its
    content under the version IRI, each release graph under <version IRI>/<name>, and each package graph
    (package_graphs), counted from the release's files."""
    from rdflib import Graph
    graphs = {}
    for iri in newest:
        module, version = iri.rsplit("/", 2)[-2:]
        folder = f"business_architecture/ontology/releases/{module}/{version}"
        for name, graph in ((module, iri), *((n, f"{iri}/{n}") for n in RELEASE_GRAPHS)):
            graphs[graph] = len(Graph().parse(data=repo_file(f"{folder}/{name}.ttl", ref), format="turtle"))
        for graph, path in package_graphs(iri, ref).items():
            graphs[graph] = len(Graph().parse(data=repo_file(path, ref), format="turtle"))
    return graphs


def expected_for(ref, stores):
    """What the named stores should hold. The graph counts are read from the release files only when Jena or
    Databricks is named, since both are judged per graph."""
    want = expected(ref)
    return want | {"jena_graphs": jena_graphs(want["newest"], ref)} if {"jena", "databricks"} & set(stores) else want


# ---------- judging ----------

def graphs_differ(held, graphs):
    """Why a store's {graph: triple or row count} is not the expected one (jena_graphs), naming a graph; None when
    they are equal. checked_rows refuses the triple table on it, and drift reads it as changed."""
    missing, stray = sorted(set(graphs) - set(held)), sorted(set(held) - set(graphs))
    if missing or stray:
        return (f"lacks {len(missing)} graph(s) of the newest releases, e.g. {missing[:3]}, "
                f"and holds {len(stray)} other(s), e.g. {stray[:3]}")
    moved = sorted(g for g in graphs if held[g] != graphs[g])
    if moved:
        return (f"has {len(moved)} graph(s) with another row count than the release files' triples, "
                f"e.g. {moved[0]}: {held[moved[0]]}, not {graphs[moved[0]]}")
    return None


def judge_jena(held, want, apart=()):
    """Jena's status from the graphs it holds and those the release files say it should: its graph names are its
    marker. `apart` names graphs that are not part of the release (another load's, judged by its own check); they
    stay out of the comparison."""
    held = {g: n for g, n in held.items() if g not in set(apart)}
    if not held:
        return "empty", "it holds no graph of the releases; load it again"
    missing, stray = sorted(set(want) - set(held)), sorted(set(held) - set(want))
    if missing or stray:
        return "behind", f"{len(missing)} graph(s) of the newest releases missing and {len(stray)} other(s) held"
    moved = [g for g in want if held[g] != want[g]]
    if moved:
        return "changed", f"{len(moved)} graph(s) hold another triple count than the release files, e.g. {moved[0]}"
    return "current", f"{len(held)} graphs, {sum(held.values())} triples, each equal to the release files"


def drift(markers, live, want, stores=STORES):
    """Each store's status from its marker, its live count and the expected values (expected_for).

    current; behind (marked from another release set); changed (its count moved since it was marked); unmarked; or
    unreachable (live[store] is a string that says why). Jena has no marker: judge_jena reads it as current, behind,
    changed or empty, leaving out the graphs want["jena_apart"] names. Databricks is also judged per graph
    (live["databricks_graphs"], {graph: rows}): a graph missing, extra or holding another row count than the release
    files' triples reads changed, with the graph named, even when the total holds. A store with any other name is a
    Neo4j database, so a caller can judge two of them.

    The order of the tests is the order of what to fix first: a store that cannot be read, then one never marked,
    then one marked from another release set, and only then a count that moved since the mark."""
    rows = []
    for store in stores:
        m = markers.get(store)
        if isinstance(live.get(store), str):
            rows.append((store, "unreachable", live[store]))
        elif store == "jena":
            rows.append((store, *judge_jena(live.get(store) or {}, want["jena_graphs"], want.get("jena_apart", ()))))
        elif not m:
            rows.append((store, "unmarked", "no marker: mark it after a checked load"))
        elif any(m.get(k) != want[k] for k in MARKER_FIELDS):
            moved = [k for k in MARKER_FIELDS if m.get(k) != want[k]]
            rows.append((store, "behind", f"marked {m.get('marked_at')} from another release set ({', '.join(moved)})"))
        elif store == "databricks" and "jena_graphs" in want and isinstance(live.get("databricks_graphs"), dict) \
                and (problem := graphs_differ(live["databricks_graphs"], want["jena_graphs"])):
            rows.append((store, "changed", f"{TRIPLES_TABLE} {problem}"))
        elif live.get(store) != m.get("count"):
            rows.append((store, "changed", f"marked with {m.get('count')}, now holds {live.get(store)}"))
        else:
            rows.append((store, "current", f"marked {m.get('marked_at')} at commit {m.get('commit')}"))
    return rows


# ---------- markers ----------

def commit():
    """The checkout's commit, for a marker. A tree without Git says so; a caller that knows better (the release's
    name and its zip's checksum, for example) passes its own text to marker."""
    if not os.path.exists(os.path.join(REPO, ".git")):
        return "unknown (not a Git checkout)"
    return subprocess.run(["git", "-C", REPO, "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True).stdout.strip()


def now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def marker(want, store, count, commit_text=None, marked_at=None):
    """A store's marker: MARKER_FIELDS from want (expected), marked_at, commit, store and count. Every store's marker
    has this shape. Databricks holds it as JSON text in the marker column of epm_store_markers."""
    return {k: want[k] for k in MARKER_FIELDS} | {"marked_at": marked_at or now(), "commit": commit_text or commit(),
                                                  "store": store, "count": count}


def rows_per_graph(rows):
    """{graph: row count} from the triple table's (graph, count) rows, one per graph. A row whose graph is NULL is a
    stray, so it gets a name no release graph has."""
    return {DEFAULT_GRAPH if graph is None else graph: n for graph, n in rows}


def checked_rows(held, want):
    """The triple table's count for its marker, [total rows], from its {graph: rows} (rows_per_graph). Refused unless
    the table holds exactly the graphs a current Jena holds, each with the release files' triple count: a load that
    stopped part way, or one from other files, is not marked."""
    problem = graphs_differ(held, want.get("jena_graphs") or jena_graphs(want["newest"]))
    if problem:
        raise SystemExit(f"databricks: {TRIPLES_TABLE} {problem}")
    return [sum(held.values())]


# ---------- Neo4j ----------

def neo4j_session(uri, user, password, database=None):
    """(driver, session) on one database; None is the server's default database. Close both: `with driver, session:`."""
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(uri, auth=(user, password))
    return driver, driver.session(database=database)


def neo4j_session_from(values):
    """neo4j_session from settings; a missing address or password raises Unset before anything connects."""
    return neo4j_session(need(values, "NEO4J_URI"), values.get("NEO4J_USERNAME", "neo4j"), need(values, "NEO4J_PASSWORD"),
                         values.get("NEO4J_DATABASE"))


def resource_counts(session):
    """What the projection counts: Resource nodes and the relationships between them."""
    nodes = session.run("MATCH (n:Resource) RETURN count(n) AS n").single()["n"]
    edges = session.run("MATCH (:Resource)-[r]->(:Resource) RETURN count(r) AS n").single()["n"]
    return nodes, edges


def read_neo4j(session, store="neo4j"):
    """(marker or None, [Resource nodes, relationships between them]) of the database the session is on."""
    rec = session.run("MATCH (m:EpmStoreMarker {store: $s}) RETURN properties(m) AS p", s=store).single()
    return (dict(rec["p"]) if rec else None), list(resource_counts(session))


def neo4j_checked(store, session, want):
    """A Neo4j database's measured counts, refused unless they match the committed report of the last load, and unless
    it holds one release record for each newest release."""
    with open(REPORT, encoding="utf-8") as f:
        report = json.load(f)
    nodes, edges = resource_counts(session)
    if (nodes, edges) != (report["nodes"], report["relationships"]):
        raise SystemExit(f"{store}: {nodes} nodes and {edges} relationships, not the last load's {report['nodes']} "
                         f"nodes and {report['relationships']} relationships")
    records = session.run("MATCH (r:ModuleRelease) RETURN r.version_iri AS iri").value()
    if sorted(records) != want["newest"]:
        raise SystemExit(f"{store}: its {len(records)} release record(s) are not one for each of the "
                         f"{len(want['newest'])} newest releases")
    return [nodes, edges]


def mark_neo4j(session, store="neo4j", want=None):
    """Checks the database against this tree (neo4j_checked), then writes its marker. Returns the marker.

    The check runs first and stops the command, so a database that does not hold this tree's load is never marked
    current. MERGE on the store's name means a second mark replaces the first and leaves one marker per name."""
    want = want or expected()
    written = marker(want, store, neo4j_checked(store, session, want))
    session.run("MERGE (m:EpmStoreMarker {store: $s}) SET m = $p", s=store, p=written).consume()
    return written


# ---------- Jena ----------

def jena_select(query_url, query):
    """A SELECT's bindings from the dataset's SPARQL query URL."""
    request = urllib.request.Request(query_url + "?" + urllib.parse.urlencode({"query": query}),
                                     headers={"Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)["results"]["bindings"]


def read_jena(query_url):
    """{graph IRI: triple count} of what Jena holds. Triples in the default graph, where nothing should be, count as
    a graph of their own so the check reports them."""
    held = {r["g"]["value"]: int(r["n"]["value"])
            for r in jena_select(query_url, "SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g")}
    in_default = int(jena_select(query_url, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")[0]["n"]["value"])
    if in_default:
        held[DEFAULT_GRAPH] = in_default
    return held


# ---------- the commands ----------

def read_stores(stores, values, name="neo4j"):
    """(markers, live, logical-model markers) of the named stores, for drift and logical_models.drift. A store not
    named is not read. A store that cannot be read, or whose setting is missing, reads as unreachable with the reason.
    Every error is caught per store, so one store that is down still leaves a line for the other."""
    import logical_models as lm  # it imports this module
    markers, live, models = {}, {}, {}
    if "neo4j" in stores:
        try:
            driver, session = neo4j_session_from(values)
            with driver, session:
                markers["neo4j"], live["neo4j"] = read_neo4j(session, name)
                models["neo4j"] = lm.read_marker(session)
        except Exception as err:
            markers["neo4j"], live["neo4j"], models["neo4j"] = None, reason(err), reason(err)
    if "jena" in stores:
        try:
            markers["jena"], live["jena"] = None, read_jena(need(values, "EPM_JENA_QUERY"))
        except Exception as err:
            markers["jena"], live["jena"] = None, reason(err)
    return markers, live, models


def check(stores, ref, values, name="neo4j", out=None):
    """Prints one line per store, and an lm: line for a Neo4j database when the releases hold logical models. Returns
    True when every line reads current."""
    import logical_models as lm
    markers, live, models = read_stores(stores, values, name)
    rows = drift(markers, live, expected_for(ref, stores), stores)
    model_rows = lm.check(models, ref)  # none when the ref's newest releases hold no logical-model module
    for store, status, why in rows:
        print(f"{store:<11} {status:<11} {why}", file=out)
    for store, status, why in model_rows:
        print(f"{'lm:' + store:<11} {status:<11} {why}", file=out)
    return all(status == "current" for _, status, _ in rows + model_rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=("expected", "check", "mark"))
    ap.add_argument("--ref", default=WORKTREE, help="expected, check: a Git ref whose files say what is current "
                    "(default worktree: this tree's files, which needs no Git)")
    ap.add_argument("--store", action="append", choices=READ_HERE, help="check: read and judge only these stores (default: both)")
    ap.add_argument("--name", default="neo4j", help="check, mark: the name the Neo4j marker carries (default neo4j)")
    args = ap.parse_args(argv)
    if args.command == "expected":
        print(json.dumps(expected(args.ref), indent=2))
        return 0
    values = settings()
    if args.command == "check":
        return 0 if check(tuple(args.store) if args.store else READ_HERE, args.ref, values, args.name) else 1
    driver, session = neo4j_session_from(values)  # a marker records what this tree's catalog says the store was loaded from
    with driver, session:
        written = mark_neo4j(session, args.name)
    print(f"{args.name}: marked, holding {written['count']}, from {written['catalog_datasets']} catalog datasets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
