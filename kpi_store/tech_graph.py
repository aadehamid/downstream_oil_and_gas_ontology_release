"""Builds the technical graph of one environment from what the workspace reports, and loads it into the stores.

The technical graph records what is built on the data platform, in the terms of the technical-graph module
(business_architecture/ontology/technical-graph/): each table and view with its name and layer, the tables it
reads from, the job or pipeline that builds it, the Genie spaces bound to it, the design it builds in the
ontology, the measures a metric view computes, and the table on the earlier platform that it replaces. It is
data, never part of a release package: build() makes it from one discovery reading, and write() saves it in the
run's folder.

    graph = build(discovery, ontology_view, settings)     # no connection, no clock, standard library only
    files = write(graph, run_folder)                       # tech-graph.nq and tech-graph-summary.json
    load_delta(gate, settings, files)                      # Databricks: a triple table in the tech_graph schema
    load_jena(files, query_url)                            # Fuseki: one named graph per environment
    load_neo4j(session, files)                             # Neo4j: a subgraph labelled Tech, beside the ontology

Every load is checked against the file it was given, and each store keeps a marker, so the sync check can say
whether a store's technical graph is current or behind (status_neo4j, status_jena, status_delta). Each status
function proves content, never only a count: it reads the store's copy back and compares a hash of it with the
files'.

The same discovery reading always gives the same bytes: the lines are sorted, every IRI comes from a name, and
the only times in the file are the ones the platform reported.

Where it sits in the run. This module has no command of its own; other steps call it:
  the notebook             after the release is loaded into Databricks, it calls build_from_files(), write() and
                           load_delta(), and leaves tech-graph.nq beside its report in the volume
  the runner's report step fetches that file into <run folder>/tech-graph/ and checks its digest
  fuseki, neo4j, enterprise  each loads the fetched file after the ontology (load_jena, load_neo4j)
  sync                     asks each store's status function

What the loads write: in Databricks, two tables in <write_catalog>.<tech_graph_schema>, and a staging table there
for the length of the load; in Fuseki, the graph file's named graphs; in Neo4j, the nodes labelled Tech, their
relationships and one TechGraphMarker node. A relationship may end at one of the ontology's Resource nodes (a
design or a measure). The loads create, change and delete no Resource node, no relationship between two Resource
nodes, none of the ontology's triples or graphs, and no file of a release package.

build() and write() need nothing but Python. The loads need rdflib; load_delta and load_jena also need
pyoxigraph, and load_neo4j needs the neo4j driver.
"""
import datetime as dt
import hashlib
import importlib.util
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

TG = "https://w3id.org/mpc/ontology/modules/technical-graph/"         # the module's classes and properties
LAYER = "https://w3id.org/mpc/ontology/modules/data-product/layer/"   # the layer code list, kept in data-product
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
XSD = "http://www.w3.org/2001/XMLSchema#"
# Every IRI this module makes for a thing on the platform, and for the graph itself, starts here:
# urn:kpi-store:tech:<environment>:<kind>/<name>. The urn: scheme keeps these IRIs apart from the ontology's
# https: ones, and the Enterprise copy knows a technical-graph node by it.
BASE = "urn:kpi-store:tech:"
GRAPH_FILE = "tech-graph.nq"
SUMMARY_FILE = "tech-graph-summary.json"

# The naming rule for layers: the first word of the schema name. A schema that starts with another word has no
# layer, such as a schema of the earlier platform.
SCHEMA_LAYERS = {"replica": "replica", "silver": "silver", "gold": "gold", "semantic": "metric-view"}
# Links whose value is one entry of a code list. In Neo4j each becomes a property that holds the entry's code.
CODE_LINKS = (TG + "layer", TG + "result")

# The Neo4j subgraph: every node carries LABEL, never Resource, which is the ontology's.
LABEL = "Tech"
MARKER_LABEL = "TechGraphMarker"
KIND = "tech"   # the name subgraph.replace_subgraph gives the edges between two nodes of this subgraph
# The Databricks tables, in <write_catalog>.<tech_graph_schema>.
TRIPLES_TABLE = "tech_graph_triples"
MARKERS_TABLE = "tech_graph_markers"
DELTA_STORE = "databricks"   # the value of the marker row's store column

# Two files of the release that the loads call. Their folders are not packages, so they are loaded by path
# (_module), from the release folder a caller names or else the one this code is in.
RELEASE_ROOT = Path(__file__).resolve().parents[1]
RDFSTORE = Path("skills") / "rdf-store" / "scripts" / "rdfstore.py"
SUBGRAPH = Path("business_architecture") / "ontology" / "projection" / "subgraph.py"


class TechGraphError(Exception):
    """The technical graph could not be built, or a store's copy differs from the file it was loaded from."""


# ---- the graph -----------------------------------------------------------------------------------

@dataclass
class TechGraph:
    graph: str                                    # the named graph's IRI, one per environment
    environment: str                              # the read catalogs, lower case, sorted, joined by +
    triples: set = field(default_factory=set)     # {(subject IRI, predicate IRI, object)}; see _iri and _text
    notes: list = field(default_factory=list)     # what was left out or recorded in a weaker form, in words

    def nquads(self):
        """The graph as sorted N-Quads text: one line per triple, each in the named graph."""
        return "".join(sorted(f"<{s}> <{p}> {o} <{self.graph}> .\n" for s, p, o in self.triples))

    def subjects(self, cls):
        return sorted(s for s, p, o in self.triples if p == RDF_TYPE and o == _iri(TG + cls))

    def links(self, name):
        """[(subject, object IRI)] of one tg: property whose values are IRIs, sorted."""
        return sorted((s, o[1:-1]) for s, p, o in self.triples if p == TG + name and o.startswith("<"))

    def summary(self):
        """Counts for a person to read: nodes per class and links per property."""
        classes, links = {}, {}
        for s, p, o in self.triples:
            if p == RDF_TYPE:
                classes[o[1:-1][len(TG):]] = classes.get(o[1:-1][len(TG):], 0) + 1
            else:
                links[p[len(TG):]] = links.get(p[len(TG):], 0) + 1
        return {"graph": self.graph, "environment": self.environment, "triples": len(self.triples),
                "classes": dict(sorted(classes.items())), "properties": dict(sorted(links.items())), "notes": self.notes}


def _iri(value):
    """An IRI in N-Triples form. An object of a triple is kept in this form, so a leading < tells an IRI from a
    literal."""
    return f"<{value}>"


def _text(value, datatype=None):
    """An N-Triples literal. Control characters are escaped, so one triple is always one line."""
    out = []
    for ch in str(value):
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"' + (f"^^<{datatype}>" if datatype else "")


def _key(name, exact=False):
    """A name as the last part of an IRI. Everything but letters, digits, dot, dash and underscore is escaped.
    A name is lower-cased, because names are compared without case. An ID is kept exactly (exact=True): two IDs
    that differ only in case are two things."""
    return urllib.parse.quote(str(name) if exact else str(name).lower(), safe="._-")


def environment(settings):
    """The environment's name inside every IRI: its read catalogs, lower case, sorted, joined by +."""
    return "+".join(sorted(c.lower() for c in settings.read_catalogs))


def graph_iri(settings):
    """The named graph that holds this environment's technical graph."""
    return f"{BASE}{environment(settings)}:graph"


def schema_layer(schema):
    """The layer the naming rule gives a schema, as a code of the layer code list, or None."""
    # A schema with no underscore is one word, not a layer word followed by a name, so the rule does not apply.
    return SCHEMA_LAYERS.get(schema.lower().split("_", 1)[0]) if "_" in schema else None


def _reading(discovery):
    """The discovery reading as the dict its JSON holds, from a Discovery, its JSON text, or that dict."""
    if hasattr(discovery, "to_json"):
        return json.loads(discovery.to_json())
    if isinstance(discovery, (str, bytes)):
        return json.loads(discovery)
    return discovery


def build(discovery, view, settings, every_object=False):
    """The technical graph of one environment.

    discovery is a discovery.Discovery, or the JSON it writes. view is the ontology_view.OntologyView of the
    release. Every name is compared without case; an ID (a job, a pipeline, a Genie space) is kept exactly. Raises
    settings.SettingsError when two designs of the ontology get one name in this environment.

    Which objects are in the graph: the objects in a schema that holds a designed object, the objects a Genie
    space is bound to, both ends of every migration pair, and everything those are built from or that is built
    from them, by the platform's lineage and the metric views' own definitions. every_object=True takes every
    object the discovery read instead.
    """
    from . import discovery as disc
    found = _reading(discovery)
    env = environment(settings)
    g = TechGraph(graph=f"{BASE}{env}:graph", environment=env)
    tables = found.get("tables") or {}
    metric_views = found.get("metric_views") or {}

    # What each object reads: the lineage the platform observed, and the tables a metric view's definition names.
    # reads {object: its sources}; written {object: its newest write}; unread {object: a write time that is no
    # date}; writers {object: the IDs of what wrote it}.
    reads, written, unread, writers = {}, {}, {}, {}
    for edge in found.get("table_edges") or []:
        source, target = edge["source"].lower(), edge["target"].lower()
        # Lineage keeps history, so an edge can name an object that is gone. Only an edge whose two ends exist
        # today is kept, and an object that reads itself says nothing.
        if source == target or source not in tables or target not in tables:
            continue
        reads.setdefault(target, set()).add(source)
        if edge.get("last_event"):
            # Times are compared as full instants, whatever form the reading holds them in. Only the value
            # written below, tg:lastRefresh, is cut to the second.
            when = disc.instant(edge["last_event"])
            if when is None:
                unread[target] = str(edge["last_event"])
            elif target not in written or when > written[target]:
                written[target] = when
        writers.setdefault(target, set()).update(str(e) for e in edge.get("entities") or [])
    for name, definition in metric_views.items():
        for source in definition.get("tables") or []:
            if name.lower() in tables and source.lower() in tables and source.lower() != name.lower():
                reads.setdefault(name.lower(), set()).add(source.lower())
    pairs = sorted({(s.lower(), t.lower()) for s, t in found.get("migration_pairs") or []
                    if s.lower() in tables and t.lower() in tables and s.lower() != t.lower()})

    # designs {this environment's name: the ontology object it builds}. The settings' [names] table turns the
    # ontology's catalog names into this environment's.
    by_name = {o.full_name: o for o in view.objects.values()}
    designs = {name: by_name[full_name] for name, full_name in settings.one_name_each(by_name).items() if name in tables}
    spaces = sorted(found.get("genie_spaces") or [], key=lambda s: str(s.get("space_id")))

    if every_object:
        scope = set(tables)
    else:
        schemas = {name.rsplit(".", 1)[0] for name in designs}
        seeds = {name for name in tables if name.rsplit(".", 1)[0] in schemas}
        seeds |= {t.lower() for space in spaces for t in space.get("tables") or [] if t.lower() in tables}
        seeds |= {name for pair in pairs for name in pair}
        # From the seeds the scope follows lineage both ways: down to every source of a seed, and up to everything
        # built from a seed. So the graph holds the seeds' whole chains and leaves out the workspace's other objects.
        read_by = {}
        for target, sources in reads.items():
            for source in sources:
                read_by.setdefault(source, set()).add(target)
        scope = _reach(seeds, reads) | _reach(seeds, read_by)

    def node(kind, key, prefix=""):
        """An object's IRI from its name, or a builder's or a space's from its ID, which follows the prefix."""
        return f"{BASE}{env}:{kind}/{prefix}{_key(key, exact=bool(prefix))}"

    def add(subject, name, value):
        """One triple. name is a tg: property's local name, or "a" for the type."""
        g.triples.add((subject, RDF_TYPE if name == "a" else TG + name, value))

    # The objects. A metric view counts as one only when the ontology names a measure it computes; any other
    # view, metric or not, is a View, and everything else is a Table.
    for name in sorted(scope):
        info, subject, design = tables[name], node("object", name), designs.get(name)
        kind = str(info.get("table_type") or "").upper()
        measures = [view.measures[m].iri for m in (design.measures if design else ()) if m in view.measures]
        if kind == "METRIC_VIEW" and measures:
            add(subject, "a", _iri(TG + "MetricView"))
            for measure in measures:
                add(subject, "implements", _iri(measure))
        elif kind in ("VIEW", "METRIC_VIEW"):
            add(subject, "a", _iri(TG + "View"))
            if kind == "METRIC_VIEW":
                g.notes.append(f"{info['full_name']} is a metric view the ontology names no measure for; it is recorded as a view")
        else:
            add(subject, "a", _iri(TG + "Table"))
            if name in written:
                add(subject, "lastRefresh", _text(disc.utc_text(written[name]), XSD + "dateTime"))
            elif name in unread:
                g.notes.append(f"{info['full_name']}: its last write, {unread[name]!r}, is not a date and time; it is left out")
        add(subject, "name", _text(info["full_name"]))
        layer = schema_layer(str(info.get("schema") or name.split(".")[1]))
        if layer:
            add(subject, "layer", _iri(LAYER + layer))
        if design:
            add(subject, "designedAs", _iri(design.iri))
        for source in sorted(reads.get(name, ())):
            if source in scope:
                add(subject, "readsFrom", _iri(node("object", source)))

    # The jobs and pipelines that build the objects, each joined to what it wrote.
    builders = {str(i): b for i, b in (found.get("builders") or {}).items()}
    for name in sorted(scope):
        for entity in sorted(writers.get(name, ())):
            if entity not in builders:
                continue   # a notebook or a query wrote it: the platform keeps no name for those
            builder = builders[entity]
            kind = "Pipeline" if str(builder.get("kind")).lower() == "pipeline" else "Job"
            subject = node("builder", entity, prefix=f"{kind.lower()}-")
            add(subject, "a", _iri(TG + kind))
            add(subject, "name", _text(builder.get("name") or entity))
            add(node("object", name), "builtBy", _iri(subject))

    # The Genie spaces, each bound to its tables.
    for space in spaces:
        subject = node("agent", space["space_id"], prefix="genie-")
        add(subject, "a", _iri(TG + "Agent"))
        add(subject, "name", _text(space.get("title") or f"Genie space {space['space_id']}"))
        for table in sorted({t.lower() for t in space.get("tables") or []}):
            if table in scope:
                add(subject, "binds", _iri(node("object", table)))
            else:
                g.notes.append(f"Genie space {space['space_id']} is bound to {table}, which the discovery did not read")

    # The migration pairs: the new table replaces the earlier platform's.
    for source, target in pairs:
        if source in scope and target in scope:
            add(node("object", target), "replaces", _iri(node("object", source)))
    g.notes = sorted(set(g.notes))   # sorted and without repeats, so the summary is the same on every run
    return g


def _reach(seeds, steps):
    """The seeds and everything reached from them by following steps, {name: {next names}}."""
    seen, todo = set(seeds), list(seeds)
    while todo:
        for nxt in steps.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def build_from_files(discovery_json, release_root, settings, every_object=False):
    """build() from a run's discovery.json and the release's packages."""
    from . import ontology_view as ov
    text = Path(discovery_json).read_text(encoding="utf-8")
    return build(text, ov.read(release_root), settings, every_object)


def write(graph, folder):
    """Writes the graph and its summary into the run's folder. Returns the graph files, which every load takes."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in ((GRAPH_FILE, graph.nquads()), (SUMMARY_FILE, json.dumps(graph.summary(), indent=2, sort_keys=True) + "\n")):
        with (folder / name).open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return [folder / GRAPH_FILE]


# ---- what the files hold ----------------------------------------------------------------------------

def digest(graph_files):
    """The SHA-256 of the graph files, each file's name and bytes in name order. The Neo4j and Databricks markers
    record it; Jena keeps no marker. The zero byte after each name and each file keeps two different sets of files
    from giving the same input."""
    h = hashlib.sha256()
    for path in sorted(Path(p) for p in graph_files):
        h.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def _quads(graph_files):
    """The graph files parsed into one rdflib dataset."""
    from rdflib import Dataset
    data = Dataset()
    for path in sorted(Path(p) for p in graph_files):
        data.parse(data=path.read_text(encoding="utf-8"), format="nquads")
    return data


def graph_counts(graph_files):
    """{graph IRI: triple count} of the graph files: what Jena and the triple table hold when current."""
    counts = {}
    for _, _, _, graph in _quads(graph_files).quads((None, None, None, None)):
        counts[str(graph)] = counts.get(str(graph), 0) + 1
    return counts


def jena_apart(graph_files):
    """The graph names a Jena dataset holds for the technical graph. They are no part of a release, so the
    ontology's own check leaves them out (sync_stores.judge_jena's apart)."""
    return sorted(graph_counts(graph_files))


def _module(release_root, relative, name):
    """A module of the release, loaded by its path: those folders are not packages."""
    path = Path(release_root or RELEASE_ROOT) / relative
    spec = importlib.util.spec_from_file_location(name, path) if path.is_file() else None
    if spec is None:
        raise TechGraphError(f"{path} is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows(graph_files, release_root=None):
    """(nodes, edges) of the Neo4j subgraph, in the form subgraph.replace_subgraph takes.

    A node is every subject with a type: its labels are Tech and the local name of each type, and its properties
    are uri and one per literal, named by the property's local name (name, lastRefresh, checkedAt); a time is text
    in UTC, as in the file. A value from
    a code list becomes a property that holds the value's code (layer: "gold", result: "pass"). Every other link
    becomes a relationship named in capitals (READS_FROM, DESIGNED_AS, BUILT_BY, BINDS, REPLACES, IMPLEMENTS,
    CHECKS). A link to a node of this graph is a tech edge; a link to anything else ends at an ontology node."""
    from rdflib import Literal, URIRef
    from . import discovery as disc
    sg = _module(release_root, SUBGRAPH, "kpi_store_subgraph")
    data = _quads(graph_files)
    triples = {(s, p, o) for s, p, o, _ in data.quads((None, None, None, None))}
    typed = {s for s, p, o in triples if p == URIRef(RDF_TYPE)}
    nodes = {str(s): {"labels": {LABEL}, "props": {"uri": str(s)}, "values": {}} for s in typed}
    edges = set()
    for s, p, o in triples:
        if s not in typed:
            raise TechGraphError(f"{s} has no type, so it has no label")
        n = nodes[str(s)]
        if p == URIRef(RDF_TYPE):
            n["labels"].add(sg.local_name(o))
        elif isinstance(o, Literal):
            # A time keeps the one UTC form the file gives it; rdflib would rewrite its Z as an offset.
            when = disc.utc_text(str(o)) if str(o.datatype) == XSD + "dateTime" else ""
            n["values"].setdefault(sg.local_name(p), set()).add(when or str(o))
        elif str(p) in CODE_LINKS:
            n["values"].setdefault(sg.local_name(p), set()).add(sg.local_name(o))
        else:
            edges.add((str(s), sg.edge_type(p), str(o), o not in typed))
    for n in nodes.values():
        for key, values in n.pop("values").items():
            n["props"][key] = next(iter(values)) if len(values) == 1 else sorted(values)
        n["labels"] = sorted(n["labels"])
    return ([nodes[u] for u in sorted(nodes)],
            [{"s": s, "t": t, "o": o, "ontology": ontology} for s, t, o, ontology in sorted(edges)])


def content(nodes, edges, release_root=None):
    """The subgraph as one SHA-256, the same from rows() and from what a store returns."""
    return _module(release_root, SUBGRAPH, "kpi_store_subgraph").fingerprint(nodes, edges)


def _now(now=None):
    """The time a marker carries, in UTC to the second. A test passes its own time."""
    return (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def marker(graph_files, store, now=None):
    """A store's marker for the technical graph: which files it was loaded from, and how much they hold."""
    counts = graph_counts(graph_files)
    return {"store": store, "digest": digest(graph_files), "graphs": json.dumps(counts, sort_keys=True),
            "triples": sum(counts.values()), "marked_at": _now(now)}


def _judge(held, graph_files, differs=None):
    """(status, why) from a store's marker and whether its content differs from the files."""
    want = digest(graph_files)
    # The order is from the weakest evidence to the strongest: no marker, a marker of other files, a marker of
    # these files over other content. Only a store that passes all three reads current.
    if not held:
        return "unmarked", "no technical-graph marker: load the technical graph"
    if held.get("digest") != want:
        return "behind", f"marked {held.get('marked_at')} from other graph files ({str(held.get('digest'))[:12]}, not {want[:12]})"
    if differs:
        return "changed", f"{differs} although its marker matches: load the technical graph again"
    return "current", f"marked {held.get('marked_at')} with the graph files' digest {want[:12]}"


# ---- Neo4j -----------------------------------------------------------------------------------------

def read_neo4j(session, release_root=None):
    """The database's technical-graph marker with its live content fingerprint as "content"; None with no marker."""
    sg = _module(release_root, SUBGRAPH, "kpi_store_subgraph")
    record = session.run(f"MATCH (m:{MARKER_LABEL}) RETURN properties(m) AS p").single()
    if not record:
        return None
    held = dict(record["p"])
    held["content"] = sg.fingerprint(list(session.run(sg.node_query(LABEL))), list(session.run(sg.edge_query(LABEL))))
    return held


def status_neo4j(session, graph_files, release_root=None):
    """(status, why) of a Neo4j database's technical graph: current, behind (loaded from other files), changed
    (its content differs although its marker matches) or unmarked."""
    held = read_neo4j(session, release_root)
    differs = None
    if held and held.get("content") != content(*rows(graph_files, release_root), release_root):
        differs = "its technical graph differs from the graph files"
    return _judge(held, graph_files, differs)


def load_neo4j(session, graph_files, store="neo4j", release_root=None, now=None):
    """Replaces the technical graph and its marker in the database the session is on, in one transaction, by plain
    Cypher: no plugin is called, so the same call loads a local server and an Enterprise database.

    The ontology must already be loaded, because the graph's links to designs and measures end at its nodes. The
    transaction commits only when every link found its target and the ontology's node and relationship counts did
    not move. A database that already holds these files is left alone. Returns a dict whose "status" is "current"
    or "loaded"."""
    sg = _module(release_root, SUBGRAPH, "kpi_store_subgraph")
    nodes, edges = rows(graph_files, release_root)
    result = {"store": store, "digest": digest(graph_files), "nodes": len(nodes), "edges": len(edges)}
    held = read_neo4j(session, release_root)
    if held and held.get("digest") == result["digest"] and held.get("content") == sg.fingerprint(nodes, edges):
        return {**result, "status": "current", "marker": {k: v for k, v in held.items() if k != "content"}}
    written = marker(graph_files, store, now) | {"nodes": len(nodes), "edges": len(edges)}
    # One transaction holds the delete, the new nodes and edges and the marker. replace_subgraph raises before
    # the commit when a check fails, and the rollback below then leaves the earlier technical graph in place.
    tx = session.begin_transaction()
    try:
        made, after = sg.replace_subgraph(tx, store, LABEL, MARKER_LABEL, nodes, edges, written, KIND)
        tx.commit()
    finally:
        if not tx.closed():
            tx.rollback()
    return {**result, "status": "loaded", "marker": written, "tech_edges": made[KIND], "ontology_edges": made["ontology"],
            "ontology_nodes": after[0], "ontology_relationships": after[1]}


# ---- Jena ------------------------------------------------------------------------------------------

def _rdfstore(release_root=None, rdfstore=None):
    """The rdf-store skill's module: the caller's when it already imported one, else loaded from the release."""
    return rdfstore or _module(release_root, RDFSTORE, "kpi_store_rdfstore")


def _dataset(rs, graph_files):
    """The graph files as one pyoxigraph dataset, for the hash and the load."""
    return rs.pack([str(p) for p in sorted(Path(p) for p in graph_files)])


def _jena_urls(query_url):
    """(data URL, update URL) of the dataset whose query URL this is: Fuseki serves the three side by side."""
    base = query_url.rsplit("/", 1)[0]
    return base + "/data", base + "/update"


def read_jena(rs, query_url, graphs):
    """The named graphs as Jena holds them, as one dataset. A graph Jena does not hold comes back empty."""
    data_url, _ = _jena_urls(query_url)
    held = rs.ox.Dataset()
    for graph in graphs:
        request = urllib.request.Request(data_url + "?" + urllib.parse.urlencode({"graph": graph}),
                                         headers={"Accept": "application/n-triples"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read()
        except urllib.error.HTTPError as err:
            if err.code == 404:   # Fuseki's answer for a graph it does not hold
                continue
            raise
        for t in rs.ox.parse(body, format=rs.ox.RdfFormat.N_TRIPLES):
            held.add(rs.ox.Quad(t.subject, t.predicate, t.object, rs.ox.NamedNode(graph)))
    return held


def load_jena(graph_files, query_url, release_root=None, rdfstore=None):
    """Replaces the technical graph's named graphs in a Fuseki dataset, then reads them back and compares the
    RDFC-1.0 hash with the files'. query_url is the dataset's SPARQL query URL; its data and update URLs sit beside
    it. Other graphs are not touched. A dataset that already holds these files is left alone. Returns a dict whose
    "status" is "current" or "loaded"; raises TechGraphError when the copy differs."""
    rs = _rdfstore(release_root, rdfstore)
    dataset = _dataset(rs, graph_files)
    graphs = jena_apart(graph_files)
    result = {"store": "jena", "digest": digest(graph_files), "graphs": graph_counts(graph_files),
              "dataset_hash": rs.dataset_hash(dataset)}
    if rs.dataset_hash(read_jena(rs, query_url, graphs)) == result["dataset_hash"]:
        return {**result, "status": "current"}
    data_url, update_url = _jena_urls(query_url)
    rs.FusekiStore(data_url, query_url, update_url).publish(dataset)
    if rs.dataset_hash(read_jena(rs, query_url, graphs)) != result["dataset_hash"]:
        raise TechGraphError("jena: the technical graph it holds differs from the graph files after the load")
    return {**result, "status": "loaded"}


def status_jena(query_url, graph_files, release_root=None, rdfstore=None):
    """(status, why) of a Fuseki dataset's technical graph. Jena keeps no marker, so its content is the proof: the
    named graphs are read back and their RDFC-1.0 hash is compared with the files'. current; behind (a graph of the
    files is missing); or changed (the graphs are there and hold other triples, even when the count is the same)."""
    rs = _rdfstore(release_root, rdfstore)
    want = graph_counts(graph_files)
    held = read_jena(rs, query_url, sorted(want))
    there = {g for g in want if any(True for _ in held.quads_for_graph_name(rs.ox.NamedNode(g)))}
    missing = sorted(set(want) - there)
    if missing:
        return "behind", f"{len(missing)} technical-graph graph(s) missing, e.g. {missing[0]}"
    if rs.dataset_hash(held) != rs.dataset_hash(_dataset(rs, graph_files)):
        return "changed", f"its technical graph holds {len(held)} triples that are not the graph files' {sum(want.values())}: load it again"
    return "current", f"{len(want)} graph(s), {sum(want.values())} triples, equal to the graph files by hash"


# ---- Databricks ------------------------------------------------------------------------------------

def delta_tables(settings):
    """(triple table, marker table) of the technical graph, in the tech_graph schema."""
    schema = f"{settings.write_catalog}.{settings.tech_graph_schema}"
    return f"{schema}.{TRIPLES_TABLE}", f"{schema}.{MARKERS_TABLE}"


def _own_tables(gate, settings):
    """The lower-case names of the tables in the tech_graph schema. A caller asks this before it reads a table,
    because a SELECT on a missing table is an error, not an empty answer."""
    found = gate.run("SELECT table_name FROM system.information_schema.tables "
                     f"WHERE lower(table_catalog) = '{settings.write_catalog.lower()}' "
                     f"AND lower(table_schema) = '{settings.tech_graph_schema.lower()}'")
    return {str(r["table_name"]).lower() for r in found}


def read_delta(gate, settings):
    """The triple table's marker as a dict, or None when the marker table or its row is missing or unreadable."""
    if MARKERS_TABLE not in _own_tables(gate, settings):
        return None
    found = gate.run(f"SELECT marker FROM {delta_tables(settings)[1]} WHERE store = '{DELTA_STORE}'")
    try:
        return json.loads(found[0]["marker"]) if found else None
    except (TypeError, ValueError):
        return None


def status_delta(gate, settings, graph_files, release_root=None, rdfstore=None):
    """(status, why) of the technical graph in Databricks, proved by content: the triple table is read back through
    the Gate and its RDFC-1.0 hash is compared with the files'.

    unmarked  no marker row
    behind    the marker names other graph files
    changed   the marker names these files, and the triple table is missing or holds other triples, even when
              its row count is the same
    current   the marker names these files and the table holds exactly their triples"""
    from . import load_databricks as lb
    held = read_delta(gate, settings)
    differs = None
    if held and held.get("digest") == digest(graph_files):
        rs = _rdfstore(release_root, rdfstore)
        if TRIPLES_TABLE not in _own_tables(gate, settings):
            differs = f"{TRIPLES_TABLE} is missing"
        elif rs.dataset_hash(rs.SparkStore(lb.GatedSpark(gate), delta_tables(settings)[0]).export()) \
                != rs.dataset_hash(_dataset(rs, graph_files)):
            differs = f"{TRIPLES_TABLE} holds other triples than the graph files"
    return _judge(held, graph_files, differs)


def load_delta(gate, settings, graph_files, release_root=None, now=None, rdfstore=None, batch=None):
    """Loads the graph files into <write_catalog>.<tech_graph_schema>.tech_graph_triples, in the columns of
    epm_triples, and writes the marker row in tech_graph_markers beside it.

    Every statement passes the Gate. The load is the rdf-store skill's round trip: a staging table is written, read
    back and compared by RDFC-1.0 hash with the files; only an equal staging table replaces the triple table, which
    is read back and compared again before the marker is written. A table that already holds these files is left
    alone. Returns a dict whose "status" is "current", "marked", "loaded", "staging-mismatch" or "main-mismatch"."""
    from . import load_databricks as lb
    rs = _rdfstore(release_root, rdfstore)
    dataset = _dataset(rs, graph_files)
    table, markers = delta_tables(settings)
    want = marker(graph_files, DELTA_STORE, now) | {"dataset_hash": rs.dataset_hash(dataset)}
    stable = {k: v for k, v in want.items() if k != "marked_at"}   # marked_at differs on every run; the rest must not
    result = {"table": table, "digest": want["digest"], "dataset_hash": want["dataset_hash"], "count": len(dataset)}
    gate.run(f"CREATE SCHEMA IF NOT EXISTS {settings.write_catalog}.{settings.tech_graph_schema}")
    store = rs.SparkStore(lb.GatedSpark(gate), table)
    if batch:
        store.BATCH = batch

    def mark():
        """Replaces the marker row. The JSON travels as base64, so no character of it can end the SQL string."""
        text = "decode(unbase64('" + _b64(json.dumps(want, sort_keys=True)) + "'), 'UTF-8')"
        gate.run(f"CREATE TABLE IF NOT EXISTS {markers} (store STRING, marker STRING) USING DELTA "
                 "COMMENT 'Which graph files the technical graph table was loaded from'")
        gate.run(f"DELETE FROM {markers} WHERE store = '{DELTA_STORE}'")
        gate.run(f"INSERT INTO {markers} (store, marker) SELECT '{DELTA_STORE}', {text}")

    # The table already holds exactly these triples: write nothing to it. Only the marker is written, and only
    # when it is missing or differs from this load's in a field other than its time.
    if TRIPLES_TABLE in _own_tables(gate, settings) and rs.dataset_hash(store.export()) == want["dataset_hash"]:
        held = read_delta(gate, settings) or {}
        if all(held.get(k) == v for k, v in stable.items()):
            return {**result, "status": "current", "marker": held}
        mark()
        return {**result, "status": "marked", "marker": want}
    passed, comparison = rs.roundtrip(store, dataset)
    if not passed:
        return {**result, "status": "main-mismatch" if comparison.get("published") else "staging-mismatch", "comparison": comparison}
    mark()
    return {**result, "status": "loaded", "marker": want}


def _b64(text):
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("ascii")
