"""Build the next core release: added processes, steps and business areas. The apply command writes a copy of this file
as build_core_<major>_<minor>.py, with the block marked FILL IN filled from a signed process map request
(kpi_store/change/core_release.py). A specialist may copy it and fill the block by hand the same way. It follows
build_core_2_3.py, the builder that added a node. For a change to an existing node's ID or description, read
build_core_2_2.py, which applies those; this file stops on them.

A new node is shaped as 2.3.0's: prefLabel, notation, definition (the first sentence of its description), scope note
(the rest), broader, inScheme, taxonomy level and provenance, and core:businessDomain when the block names its area.
A new business area is a member of the core:BusinessDomain code list, a top concept both ways, as 2.4.0 made every
code-list member. The map fields that core does not read (UNREAD_FIELDS, which other modules build from) may change
between the two copies of the map; any other change stops the build.

    python3 build_core_<major>_<minor>.py --write    # write releases/core/<version>/
    python3 build_core_<major>_<minor>.py --verify   # fail unless the written package equals a fresh build
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

from pyshacl import validate
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, SKOS, XSD

import build_core_2_1 as b21
import build_core_2_2 as maps
import build_core_next as first
import frozen_sources
import newest

HERE = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY = os.path.dirname(HERE)

# --- FILL IN ---------------------------------------------------------------------------------------------------------
VERSION, ISSUED = "X.Y.Z", "YYYY-MM-DD"
BASE_VERSION = "X.Y.Z"  # the core release this one starts from
# The two copies of the process map to compare, each named by the commit that holds it (or any label of 12 or more
# letters and digits in a plain folder). Each has a file in release/frozen/: <first 12 characters>-downstream_process_map.json
EARLIER_COMMIT = "the-commit-you-started-from"
SOURCE_COMMIT = "the-commit-that-changed-the-map"
APPROVAL = ("where the approval is recorded", "the sentence that approved this release")
DECISIONS = ["your decision record"]
# Each added node: its ID -> (its fields in the map beyond the description, its parent's slug, the slug of its business
# area or None).
APPROVED_NODE = {"CM 9.9.9": ({"id": "CM 9.9.9", "level": 3, "name": "The process's name"}, "CM-9-9", "commercial")}
# Each added business area: its slug -> (its name, its definition).
APPROVED_AREAS = {}
# ---------------------------------------------------------------------------------------------------------------------

BASE = frozen_sources.package_dir(ONTOLOGY, "core", BASE_VERSION)
CHANGELOG = os.path.join(ONTOLOGY, "releases", "core", f"CHANGELOG-{VERSION}.md")
RELEASE_DIR = os.path.join(ONTOLOGY, "releases", "core", VERSION)
CORE, PROC, ONTOLOGY_IRI, SCHEME = maps.CORE, maps.PROC, maps.ONTOLOGY_IRI, maps.SCHEME
# What an earlier core release counted of its own changes; this release does not repeat them.
EARLIER_COUNTS = ("renamed concepts", "alternative labels moved", "code-list top concepts", "IDs on stubs",
                  "changed descriptions", "19948 references rejected", "19948 references confirmed", "new business areas")
AREA = first.DOMAIN                   # the namespace of the business areas
AREAS = CORE.BusinessDomain           # their code list
UNREAD_FIELDS = {"raci", "systems"}   # read by organization and system; build_core_2_4.py set the first such list


def map_nodes(commit):
    """The map at a commit, as build_core_2_2.map_nodes gives it, without the fields core does not read."""
    return {slug: ({k: v for k, v in node.items() if k not in UNREAD_FIELDS}, parent)
            for slug, (node, parent) in maps.map_nodes(commit).items()}


def en(text):
    return Literal(text, lang="en")


def build():
    g = Graph()
    g.parse(os.path.join(BASE, "core.ttl"))
    new, ids, descriptions = maps.changes(base=g, earlier=map_nodes(EARLIER_COMMIT), current=map_nodes(SOURCE_COMMIT))
    if ids or descriptions or sorted(node["id"] for _, node, _ in new) != sorted(APPROVED_NODE):
        sys.exit(f"the map changed more than APPROVED_NODE says: new {[n['id'] for _, n, _ in new]}, IDs {ids}, "
                 f"descriptions {[d[0] for d in descriptions]}")
    for slug, (label, definition) in sorted(APPROVED_AREAS.items()):
        a = URIRef(AREA + slug)
        if (a, None, None) in g:
            sys.exit(f"the business area {slug} is in core {BASE_VERSION} already")
        g.add((a, RDF.type, SKOS.Concept))
        g.add((a, SKOS.prefLabel, en(label)))
        g.add((a, SKOS.definition, en(definition)))
        g.add((a, SKOS.inScheme, AREAS))
        g.add((a, SKOS.topConceptOf, AREAS))
        g.add((AREAS, SKOS.hasTopConcept, a))
        g.add((a, DCTERMS.provenance, en(f"Added in core {VERSION} from a process map request; {APPROVAL[0]} holds its approval.")))
    for slug, node, parent in new:
        s = URIRef(PROC + slug)
        fields, approved_parent, area = APPROVED_NODE[node["id"]]
        if {k: v for k, v in node.items() if k != "description"} != fields or parent != approved_parent \
                or not node.get("description"):
            sys.exit(f"{node['id']}: its map fields or parent differ from APPROVED_NODE: {node}, parent {parent}")
        if (URIRef(PROC + parent), RDF.type, SKOS.Concept) not in g:
            sys.exit(f"{slug}: its parent {parent} is not a concept")
        definition, scope = maps.split_description(node["description"])
        g.add((s, RDF.type, SKOS.Concept))
        g.add((s, SKOS.prefLabel, en(node["name"])))
        g.add((s, SKOS.notation, Literal(node["id"])))
        g.add((s, SKOS.definition, en(definition)))
        if scope:
            g.add((s, SKOS.scopeNote, en(scope)))
        g.add((s, SKOS.broader, URIRef(PROC + parent)))
        g.add((s, SKOS.inScheme, SCHEME))
        g.add((s, CORE.taxonomyLevel, Literal(node["level"])))
        if area:
            if (URIRef(AREA + area), SKOS.inScheme, AREAS) not in g:
                sys.exit(f"{slug}: its business area {area} is not in the core:BusinessDomain list")
            g.add((s, CORE.businessDomain, URIRef(AREA + area)))
        g.add((s, DCTERMS.provenance, en(f"Added in core {VERSION} from the process map; definition and scope note from the map's description.")))
    for p in (OWL.versionInfo, OWL.versionIRI, DCTERMS.issued, DCTERMS.modified, OWL.priorVersion):
        g.remove((ONTOLOGY_IRI, p, None))
    g.add((ONTOLOGY_IRI, OWL.versionInfo, Literal(VERSION)))
    g.add((ONTOLOGY_IRI, OWL.versionIRI, URIRef(f"{ONTOLOGY_IRI}/{VERSION}")))
    g.add((ONTOLOGY_IRI, OWL.priorVersion, URIRef(f"{ONTOLOGY_IRI}/{BASE_VERSION}")))
    g.add((ONTOLOGY_IRI, DCTERMS.issued, Literal(ISSUED, datatype=XSD.date)))
    g.add((ONTOLOGY_IRI, DCTERMS.modified, Literal(ISSUED, datatype=XSD.date)))
    with open(os.path.join(BASE, "counts.json"), encoding="utf-8") as f:
        counts = Counter(json.load(f))
    counts["process concepts"] = sum(1 for s in g.subjects(RDF.type, SKOS.Concept) if str(s).startswith(PROC))
    counts["new concepts"] = len(new)
    for key in EARLIER_COUNTS:
        counts.pop(key, None)
    counts["new business areas"] = len(APPROVED_AREAS)
    return g, counts


def catalog():
    base = f"{ONTOLOGY_IRI}/releases/{VERSION}"
    dcat = first.DCAT
    g = Graph()
    g.bind("dcat", dcat)
    g.bind("dcterms", DCTERMS)
    cat, dataset = URIRef(str(ONTOLOGY_IRI).split("/modules/")[0] + "/catalog"), URIRef(f"{ONTOLOGY_IRI}/{VERSION}")
    g.add((cat, RDF.type, dcat.Catalog))
    g.add((cat, dcat.dataset, dataset))
    g.add((dataset, RDF.type, dcat.Dataset))
    g.add((dataset, DCTERMS.title, en(f"Core Process Ontology {VERSION}")))
    g.add((dataset, DCTERMS.isVersionOf, ONTOLOGY_IRI))
    g.add((dataset, OWL.versionInfo, Literal(VERSION)))
    g.add((dataset, DCTERMS.issued, Literal(ISSUED, datatype=XSD.date)))
    g.add((dataset, DCTERMS.rights, en(b21.RIGHTS)))
    for name, media in (("core.ttl", "text/turtle"), ("core.jsonld", "application/ld+json"), ("shapes.ttl", "text/turtle"),
                        ("canonical-facts.csv", "text/csv")):
        dist = URIRef(f"{base}/{name}")
        g.add((dataset, dcat.distribution, dist))
        g.add((dist, RDF.type, dcat.Distribution))
        g.add((dist, dcat.downloadURL, dist))
        g.add((dist, dcat.mediaType, Literal(media)))
    return g.serialize(format="turtle")


def package(g, counts):
    """The earlier release's shapes and canonical-fact mapping unchanged; the graph, catalog, counts and changelog new."""
    with open(os.path.join(BASE, "shapes.ttl"), encoding="utf-8") as f:
        shapes_text = f.read()
    with open(os.path.join(BASE, "canonical-facts.csv"), encoding="utf-8") as f:
        mapping_text = f.read()
    files = {"core.ttl": g.serialize(format="turtle"), "core.jsonld": first.jsonld(g), "shapes.ttl": shapes_text,
             "catalog.ttl": catalog(), "canonical-facts.csv": mapping_text,
             "counts.json": json.dumps(dict(sorted(counts.items())), indent=2) + "\n"}
    with open(CHANGELOG, encoding="utf-8") as f:
        files["CHANGELOG.md"] = f.read()
    with open(os.path.join(BASE, "manifest.json"), encoding="utf-8") as f:
        base_manifest = f.read()
    files["manifest.json"] = json.dumps({
        "module": "core", "version": VERSION, "release_candidate": False,
        "ontology_iri": str(ONTOLOGY_IRI), "version_iri": f"{ONTOLOGY_IRI}/{VERSION}",
        "built_from": {f"core {BASE_VERSION} manifest": hashlib.sha256(base_manifest.encode()).hexdigest(),
                       "process map": f"{maps.SOURCE_PATH} at {SOURCE_COMMIT}"},
        "decisions": DECISIONS,
        "approval": {"file": APPROVAL[0], "words": APPROVAL[1]},
        "files": {n: hashlib.sha256(t.encode()).hexdigest() for n, t in sorted(files.items())}}, indent=2) + "\n"
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--rebuild-released", action="store_true", help="overwrite a released package: a rebuild of the whole set")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    g, counts = build()
    conforms, _, text = validate(g, shacl_graph=Graph().parse(os.path.join(BASE, "shapes.ttl")), advanced=True)
    if not conforms:
        sys.exit(f"core {VERSION} fails its shapes:\n" + text)
    files = package(g, counts)
    print(f"core {VERSION}: {len(g)} triples; shapes conform; process concepts {counts['process concepts']}, "
          f"new concepts {counts['new concepts']}")
    if args.verify:
        stale = [n for n, t in files.items() if not os.path.exists(os.path.join(RELEASE_DIR, n))
                 or open(os.path.join(RELEASE_DIR, n), encoding="utf-8").read() != t]
        if stale:
            sys.exit(f"core {VERSION} package is not current: {stale}")
        print("release package is current")
    if args.write:
        newest.refuse_overwrite(RELEASE_DIR, files, f"core {VERSION}", args.rebuild_released)
        os.makedirs(RELEASE_DIR, exist_ok=True)
        for n, t in files.items():
            with open(os.path.join(RELEASE_DIR, n), "w", encoding="utf-8", newline="\n") as f:
                f.write(t)
        print(f"wrote {RELEASE_DIR}")


if __name__ == "__main__":
    main()
