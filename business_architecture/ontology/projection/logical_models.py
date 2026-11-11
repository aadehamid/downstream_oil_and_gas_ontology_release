"""Loads a release's logical models into the ontology stores, when its newest releases hold the logical-model module
(the decision of 2026-11-02, amendment "the stores"). Where the releases hold no such package, every command here finds
nothing to load and changes nothing.

    python3 logical_models.py load [--store neo4j] [--store jena] [--skills <folder>]   # what the newest releases hold
    python3 logical_models.py rows                                                     # the subgraph's nodes and edges, as JSON

What each store gets, beside the module's vocabulary, which the projection loads like every package's:
- Jena and the Delta triple table: every package graph of the newest releases, each as a named graph,
  <version IRI>/<file name without .ttl>. A package graph is a Turtle file the package's manifest.json lists beside
  its content and its release graphs (build_module.py's "graphs"): for logical-model, each model's ER Studio export
  (<slug>.erstudio.ttl) and annotation layer (<slug>.layer.ttl). Jena takes them in one SPARQL Update request
  (load_jena). This file does not connect to Databricks: package_rows returns the graphs, their triple counts and the
  rows of the triple table, in the rdf-store skill's columns, for the load that writes the table.
  sync_stores.py's drift check counts the package graphs with the release graphs (jena_graphs).
- Neo4j: each model in full as its own subgraph, apart from the ontology's Resource nodes (graph_rows has the nodes
  and edges). The load replaces it in one transaction with its marker, a digest of the model graph files, and commits
  only when every edge found its target and the ontology's counts did not move (subgraph.replace_subgraph). The
  projection's counts, hash and round trip read Resource nodes only, so they never read the subgraph. sync_stores.py
  check compares it with the package's graphs on an lm:neo4j line, by marker and content fingerprint.

The labels, node shapes and loader are a build choice delegated to the build's agent, under the subject matter expert's decision of 2026-10-12. The store
addresses and the Neo4j login come from sync_stores.settings; no password is printed.
Needs rdflib; load also needs neo4j for Neo4j and pyoxigraph for Jena, and package_rows needs pyoxigraph (uv run --with ...).

In the KPI Store load only the Neo4j half of this file runs, as a library. The local Neo4j load
(kpi_store/load_neo4j.py) and the copy to Enterprise (kpi_store/copy_enterprise.py) call models, graph_rows, digest,
content, read_marker and drift to see whether the subgraph is current, and load_neo4j to replace it when it is not.
The subgraph is loaded after the ontology and before the store's marker is written. The sync check
(kpi_store/sync_check.py) reads it with the same calls. The KPI Store's Databricks and Fuseki loads put the package
graphs in their own dataset, with the release's other graphs, so they do not call load_jena or package_rows.
The load command above is for a run by hand, with the settings of sync_stores.settings.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys

import subgraph as sg
import sync_stores as ss

MODULE = "logical-model"
LABEL = "LogicalModel"  # every node of the subgraph; never Resource
MARKER_LABEL = "LogicalModelMarker"
KIND = "model"  # an edge between two nodes of the subgraph
NEO4J_NODES = sg.node_query(LABEL)
NEO4J_EDGES = sg.edge_query(LABEL)
RELEASES = os.path.join(ss.REPO, "business_architecture", "ontology", "releases")
BUILDER = os.path.join(ss.REPO, "business_architecture", "ontology", "logical-model")
SKILLS = os.path.join(ss.REPO, "skills")  # the release ships the rdf-store skill here


# ---------- what the newest releases hold ----------

def held(releases=None):
    """True when the newest version folder of some module holds package graphs, read from its manifest.json with the
    standard library only, so a caller can plan the load without rdflib. load reads the catalog itself."""
    releases = releases or RELEASES
    if not os.path.isdir(releases):
        return False
    for module in sorted(os.listdir(releases)):
        folder = os.path.join(releases, module)
        versions = [v for v in os.listdir(folder) if ss.release_newest.version_key(v)] if os.path.isdir(folder) else []
        if not versions:
            continue
        manifest = os.path.join(folder, max(versions, key=ss.release_newest.version_key), "manifest.json")
        if not os.path.isfile(manifest):
            continue
        with open(manifest, encoding="utf-8") as f:
            if ss.extra_graph_files(module, json.load(f)):
                return True
    return False


def newest(ref=None):
    """The newest releases of the catalog in this tree, or at a Git ref (sync_stores.repo_file)."""
    return ss.newest_releases(ss.catalog_datasets(ss.repo_file(ss.CATALOG, ref)))


def package_graphs(releases=None, ref=None):
    """{graph IRI: path under the repository} of every package graph of the newest releases (sync_stores.package_graphs),
    read at ref like the rest of sync_stores.py check."""
    found = {}
    for iri in releases if releases is not None else newest(ref):
        found.update(ss.package_graphs(iri, ref))
    return found


def models(releases=None, ref=None):
    """[(slug, export path, layer path)] of the newest logical-model package, from its manifest at ref; [] when the
    newest releases hold no logical-model module. A model whose export or layer is missing stops the load."""
    iri = next((i for i in (releases if releases is not None else newest(ref)) if i.rsplit("/", 2)[-2] == MODULE), None)
    if iri is None:
        return []
    graphs = sorted(ss.package_graphs(iri, ref).values())
    slugs = sorted({os.path.basename(p).split(".")[0] for p in graphs if p.endswith((".erstudio.ttl", ".layer.ttl"))})
    found = []
    for slug in slugs:
        export, layer = (next((p for p in graphs if os.path.basename(p) == f"{slug}.{k}.ttl"), None) for k in ("erstudio", "layer"))
        if not export or not layer:
            raise SystemExit(f"{MODULE}: model {slug} lacks its {'export' if not export else 'layer'} in the package's manifest")
        found.append((slug, export, layer))
    return found


# ---------- the subgraph ----------

def builder():
    """The module's builder, whose namespaces and entity rule (an owl:Class of the export with a dcterms:identifier) the
    subgraph shares, so both read one definition."""
    if BUILDER not in sys.path:
        sys.path.insert(0, BUILDER)
    import build_logical_model as blm
    return blm


def literals(g, *subjects, names=None):
    """A node's properties from its literals: rdfs:label is name, dcterms:identifier erstudio_id, dcterms:description
    description, and any other literal its predicate's local name. A key with two values holds a sorted list."""
    from rdflib import Literal
    from rdflib.namespace import DCTERMS, RDFS
    names = {RDFS.label: "name", DCTERMS.identifier: "erstudio_id", DCTERMS.description: "description", **(names or {})}
    found = {}
    for s in subjects:
        for p, o in g.predicate_objects(s):
            if isinstance(o, Literal):
                found.setdefault(names.get(p, sg.local_name(p)), set()).add(sg.neo4j_value(o.toPython()))
    return {k: next(iter(v)) if len(v) == 1 else sorted(map(str, v)) for k, v in found.items()}


def graph_rows(model_files, ref=None):
    """Nodes ({"labels", "props"}) and edges ({"s", "t", "o", "ontology", "p"}) of the subgraph, from each model's export
    and layer. Every node is labelled LogicalModel and one of:
      Model      the model's lm:LogicalModel individual: uri, slug, name (its title), created
      Entity     an owl:Class of the export with a dcterms:identifier: uri, models, name, erstudio_id, description and
                 its other literals
      Attribute  a datatype property of the export whose domain is an entity, with the literals of its ER Studio
                 attribute (:sourceAttribute) and its own: uri, models, name, datatype (its range's local name),
                 description, erstudio_id, business_term (the IRI of its glossary term, when it has one)
      Key        a key shape of the export (:keyType): uri, models, name (the shape's local name), key_type, message
    and the edges are
      (Entity)-[:IN_MODEL]->(Model), (Entity)-[:HAS_ATTRIBUTE]->(Attribute), (Entity)-[:HAS_KEY]->(Key),
      (Key)-[:ON_ATTRIBUTE]->(Attribute), (Entity)-[:RELATES_TO {uri, name}]->(Entity) for each object property between
      two entities (the inverse twin that ER Studio adds, an owl:inverseOf of another such property, is left out), and
      (Entity)-[:SOURCE_SYSTEM|DESCRIBES|IMPLEMENTED_BY]->(:Resource) for each link of its layer.
    A node two models share (a reused attribute, which the builder allows only when both describe it the same way) is
    one node, with both slugs in models."""
    from rdflib import Graph, URIRef
    from rdflib.namespace import DCTERMS, OWL, RDF, RDFS
    blm = builder()
    sh = "http://www.w3.org/ns/shacl#"
    nodes, edges = {}, set()

    def node(uri, kind, props, slug=None):
        n = nodes.setdefault(str(uri), {"labels": [LABEL, kind], "props": {"uri": str(uri)}})
        n["props"].update(props)
        if slug:
            n["props"]["models"] = sorted({*n["props"].get("models", []), slug})

    for slug, export_path, layer_path in model_files:
        export = Graph().parse(data=ss.repo_file(export_path, ref), format="turtle")
        layer = Graph().parse(data=ss.repo_file(layer_path, ref), format="turtle")
        entities = set(blm.entities(export, []).values())
        for m in layer.subjects(RDF.type, blm.LM.LogicalModel):
            node(m, "Model", {"slug": slug, **literals(layer, m, names={DCTERMS.identifier: "slug"})})
        for e in entities:
            node(e, "Entity", literals(export, e), slug)
        attributes = set()
        for prop in sorted(export.subjects(RDF.type, OWL.DatatypeProperty)):
            owners = [d for d in export.objects(prop, RDFS.domain) if d in entities]
            if not owners:
                continue
            sources = list(export.objects(prop, blm.ER.sourceAttribute))
            props = literals(export, *sources, prop)
            ranges = sorted(sg.local_name(r) for r in export.objects(prop, RDFS.range))
            if ranges:
                props["datatype"] = ranges[0] if len(ranges) == 1 else ranges
            terms = sorted(str(t) for s in sources for t in export.objects(s, blm.ER.businessTerm))
            if terms:
                props["business_term"] = terms[0] if len(terms) == 1 else terms
            node(prop, "Attribute", props, slug)
            attributes.add(prop)
            for d in owners:
                edges.add((str(d), "HAS_ATTRIBUTE", str(prop), False, ()))
        for key in sorted(export.subjects(blm.ER.keyType, None)):
            props = {"name": sg.local_name(key), **{k: v for k, v in literals(export, key).items() if k != "name"}}
            types = sorted(sg.local_name(t) for t in export.objects(key, blm.ER.keyType))
            props["key_type"] = types[0] if len(types) == 1 else types
            node(key, "Key", props, slug)
            for target in export.objects(key, URIRef(sh + "targetClass")):
                if target in entities:
                    edges.add((str(target), "HAS_KEY", str(key), False, ()))
            for shape in export.objects(key, URIRef(sh + "property")):
                for path in export.objects(shape, URIRef(sh + "path")):
                    if path in attributes:
                        edges.add((str(key), "ON_ATTRIBUTE", str(path), False, ()))
        between = {r for r in export.subjects(RDF.type, OWL.ObjectProperty)
                   if set(export.objects(r, RDFS.domain)) & entities and set(export.objects(r, RDFS.range)) & entities}
        for r in sorted(between):
            if set(export.objects(r, OWL.inverseOf)) & between:
                continue  # ER Studio's inverse twin of a relationship already drawn
            label = sorted(str(n) for n in export.objects(r, RDFS.label))
            p = (("uri", str(r)),) + ((("name", label[0]),) if label else ())
            for d in export.objects(r, RDFS.domain):
                for e in export.objects(r, RDFS.range):
                    if d in entities and e in entities:
                        edges.add((str(d), "RELATES_TO", str(e), False, p))
        for e, m in layer.subject_objects(blm.LM.inModel):
            edges.add((str(e), sg.edge_type(blm.LM.inModel), str(m), False, ()))
        for link in (blm.LM.sourceSystem, blm.LM.describes, blm.LM.implementedBy):
            for e, target in layer.subject_objects(link):
                edges.add((str(e), sg.edge_type(link), str(target), True, ()))
    return ([nodes[u] for u in sorted(nodes)],
            [{"s": s, "t": t, "o": o, "ontology": ont, "p": dict(p)} for s, t, o, ont, p in sorted(edges)])


def digest(model_files, ref=None):
    """The SHA-256 of the model graph files (in this tree, or at ref), each file's name and bytes in name order:
    what a Neo4j store's LogicalModelMarker records. It says which files a store was loaded from. content says
    what the store holds now. The drift check needs both: a hand edit in the database leaves the digest as it was."""
    h = hashlib.sha256()
    for path in sorted(p for _, *paths in model_files for p in paths):
        h.update(os.path.basename(path).encode() + b"\0" + ss.repo_bytes(path, ref) + b"\0")
    return h.hexdigest()


def content(nodes, edges):
    """The subgraph reduced to one SHA-256 (subgraph.fingerprint), from graph_rows or from a store's rows."""
    return sg.fingerprint(nodes, edges)


# ---------- the drift check ----------

def read_marker(session):
    """A Neo4j database's LogicalModelMarker with its live content fingerprint as "content"; None when it has none."""
    rec = session.run(f"MATCH (m:{MARKER_LABEL}) RETURN properties(m) AS p").single()
    if not rec:
        return None
    found = dict(rec["p"])
    found["content"] = content(list(session.run(NEO4J_NODES)), list(session.run(NEO4J_EDGES)))
    return found


def drift(markers, want_digest, want_content):
    """Each Neo4j database's status for the subgraph, from {store: its marker (read_marker), None, or a string that
    says why it could not be read}. current only when its marker names the package's model files and its content
    equals them; behind (other model files), changed (the content differs while the marker matches: a hand edit,
    say), unmarked (no marker: a reload wiped it, or it was never loaded) or unreachable."""
    rows = []
    for store, m in markers.items():
        if isinstance(m, str):
            rows.append((store, "unreachable", m))
        elif not m:
            rows.append((store, "unmarked", "no logical-model marker: run logical_models.py load --store neo4j"))
        elif m.get("digest") != want_digest:
            rows.append((store, "behind", f"marked {m.get('marked_at')} from other model files ({str(m.get('digest'))[:12]}, "
                                          f"not {want_digest[:12]})"))
        elif m.get("content") != want_content:
            rows.append((store, "changed", "its logical models differ from the package's graphs although its marker matches; "
                                           "run logical_models.py load --store neo4j"))
        else:
            rows.append((store, "current", f"marked {m.get('marked_at')} with the model files' digest {want_digest[:12]}"))
    return rows


def check(markers, ref=None):
    """The lm:<store> rows of sync_stores.py check, from each database's marker (drift), judged against the package at
    the same ref as the rest of the check (worktree, or None, reads this tree): none when that ref's newest releases
    hold no logical-model module."""
    files = models(ref=ref)
    if not files:
        return []
    nodes, edges = graph_rows(files, ref)
    return drift(markers, digest(files, ref), content(nodes, edges))


# ---------- loading ----------

def rdfstore(skills=None):
    """The rdf-store skill's rdfstore.py, whose dataset and row functions every load of the triple table uses."""
    path = os.path.join(os.path.expanduser(skills or SKILLS), "rdf-store", "scripts", "rdfstore.py")
    spec = importlib.util.spec_from_file_location("rdfstore", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(os.path.dirname(path))
    return module


def dataset(rs, graphs):
    """The package graphs as one rdfstore dataset, each file under its graph IRI."""
    paths = [os.path.join(ss.REPO, p) for p in graphs.values()]
    return rs.pack(paths, {os.path.realpath(os.path.join(ss.REPO, p)): iri for iri, p in graphs.items()})


def package_rows(rs=None, releases=None):
    """What a load of the triple table adds for the logical models, with no connection made:
    {"graphs": {graph IRI: path under the repository}, "counts": {graph IRI: triple count of its file},
     "rows": the graphs' rows in rdfstore.COLUMNS order (rdfstore.to_rows)}.
    The loader replaces the rows whose graph is one of "graphs" with "rows", then compares the table's rows per graph
    with "counts". Every value is empty when the newest releases hold no package graph. rs is the rdf-store skill's
    rdfstore module (default: the one under this release's skills folder)."""
    from rdflib import Graph
    graphs = package_graphs(releases)
    if not graphs:
        return {"graphs": {}, "counts": {}, "rows": []}
    rs = rs or rdfstore()
    return {"graphs": graphs,
            "counts": {iri: len(Graph().parse(os.path.join(ss.REPO, p), format="turtle")) for iri, p in graphs.items()},
            "rows": rs.to_rows(dataset(rs, graphs))}


def load_jena(rs, graphs, query_url):
    """Replaces each package graph in Jena in one SPARQL Update request (rdfstore's FusekiStore.publish). query_url is
    the dataset's SPARQL query URL; its data and update URLs sit beside it."""
    base = query_url.rsplit("/", 1)[0]
    rs.FusekiStore(base + "/data", query_url, base + "/update").publish(dataset(rs, graphs))
    print(f"jena: {len(graphs)} package graph(s) loaded")


def load_neo4j(session, files, store="neo4j"):
    """Replaces the subgraph and its marker in the database the session is on, in one transaction.

    The commit comes only after subgraph.replace_subgraph returns, which it does only when every edge found its
    target and the ontology's counts did not move. On any error the transaction is rolled back, so the database
    keeps the subgraph and the marker it had."""
    nodes, edges = graph_rows(files)
    marker = {"store": store, "digest": digest(files), "models": [slug for slug, _, _ in files], "nodes": len(nodes),
              "edges": len(edges), "marked_at": ss.now()}
    tx = session.begin_transaction()
    try:
        made, after = sg.replace_subgraph(tx, store, LABEL, MARKER_LABEL, nodes, edges, marker, KIND, edge_props=True)
        tx.commit()
    finally:
        if not tx.closed():
            tx.rollback()
    print(f"{store}: {len(files)} logical model(s), {len(nodes)} {LABEL} nodes, {made[KIND]} edges between them, "
          f"{made['ontology']} to ontology nodes; ontology unchanged at {after[0]} nodes and {after[1]} relationships; "
          f"marked {marker['digest'][:12]}")


def load(stores, values, skills=None):
    """Loads what the newest releases hold into each named store (neo4j, jena), at the addresses in values
    (sync_stores.settings); nothing, with a line that says so, when they hold no package graph."""
    releases = newest()
    graphs, files = package_graphs(releases), models(releases)
    if not graphs:
        print("the newest releases hold no package graph, so no logical model: nothing to load")
        return
    if "jena" in stores:
        load_jena(rdfstore(skills), graphs, ss.need(values, "EPM_JENA_QUERY"))
    if "neo4j" in stores and files:
        driver, session = ss.neo4j_session_from(values)
        with driver, session:
            load_neo4j(session, files)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=("load", "rows"))
    ap.add_argument("--store", action="append", choices=ss.READ_HERE, help="load: these stores (default: both)")
    ap.add_argument("--skills", default=os.environ.get("EPM_SKILLS"),
                    help="load: the folder holding the rdf-store skill (default $EPM_SKILLS, else this release's skills folder)")
    args = ap.parse_args(argv)
    if args.command == "rows":
        nodes, edges = graph_rows(models())
        print(json.dumps({"nodes": nodes, "edges": edges}, indent=1, default=str))
    else:
        load(tuple(args.store or ss.READ_HERE), ss.settings(), args.skills)


if __name__ == "__main__":
    main()
