"""The Neo4j Ontology Graph Specification document of this release: neo4j-spec.json.

The document describes the graph the local Neo4j load builds from the release: its node labels, relationship types
and property keys, each with the term's skos:definition as its description, its skos:altLabel values as its aliases
and its IRI as its reference. It follows version 1.1.0 of Neo4j's specification
(https://neo4j.com/docs/ontology-graph-spec/1.1.0/), whose JSON Schema is kept beside this file as
neo4j-spec-schema-1.1.0.json, so the check runs offline. README.md, "The Neo4j specification", says what the
document cannot carry.

Where it sits: pipeline.py build writes it beside projection-manifest.json, and pipeline.py build --verify fails
unless it equals a fresh build and conforms to the schema. So the cut and the apply command, which run
pipeline.py build after they write a package, keep it current, and scripts/check.sh checks it.

The element types are the ontology-to-lpg skill's (build.py element_types, the mapping behind its graph-type and
data-model commands): one node per class a shape targets, one property per key a shape types, and one relationship
per key whose shape names a class, from the shape's class to that class. Names are the kept graph's, read from the
run configuration's separator: the prefix, one underscore, the local name, as pipeline.lpg_name gives them. What
the shapes give no typed form is listed under extensions.custom.left_out.

It reads the packages' Turtle and the shape files that pipeline.py lists, and writes nothing itself: pipeline.py
writes the file. Writing needs rdflib only; the schema check needs jsonschema, which scripts/check.sh provides.
"""
import importlib.util
import json
import os
import re
import sys

from rdflib import URIRef
from rdflib.namespace import RDFS, SKOS

import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "neo4j-spec.json")
SCHEMA = os.path.join(HERE, "neo4j-spec-schema-1.1.0.json")
SCHEMA_URL = "https://neo4j.com/docs/ontology-graph-spec/1.1.0/schema.json"
SKILL_SCRIPTS = os.path.join(HERE, "..", "..", "..", "skills", "ontology-to-lpg", "scripts")
RUN_CONFIG = os.path.join(HERE, "skill-run", "epm-run.json")
# rdflib names a blank node afresh on every parse, so a left-out line that names a blank-node shape drops the name.
BLANK_NODE = re.compile(r" \(n[0-9a-f]{32}b[0-9]+\)")
RESOURCE = "Resource"   # the label n10s gives every node it loads, with the one constraint it creates (n10s_unique_uri)


def _skill_build():
    """The skill's build.py, loaded by its path under a name of its own. It imports its neighbours by plain name, so
    their folder goes on the import path."""
    folder = os.path.abspath(SKILL_SCRIPTS)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location("kpi_store_lpg_build", os.path.join(folder, "build.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text(data, term, predicate):
    """The term's one value for the predicate, preferring English and then no language tag, or None."""
    values = sorted((o for o in data.objects(term, predicate)),
                    key=lambda o: (getattr(o, "language", None) not in ("en", None), getattr(o, "language", None) or "", str(o)))
    return " ".join(str(values[0]).split()) if values else None


def _about(data, iri):
    """description, aliases and reference of a term, from the release's own triples. A term from a standard
    vocabulary, such as SKOS or PROV, has no definition in the release, so it gets no description."""
    term = URIRef(iri)
    out = {}
    description = _text(data, term, SKOS.definition) or _text(data, term, RDFS.comment)
    if description:
        out["description"] = description
    aliases = sorted({" ".join(str(a).split()) for a in data.objects(term, SKOS.altLabel)})
    if aliases:
        out["aliases"] = aliases
    out["reference"] = iri
    return out


def _graph_key():
    return {"type": "STRING", "description": "The version IRI of the release the element was loaded from "
                                             "(the module tag the load writes)."}


def document(data, shapes):
    """The specification document, as a dict, for the release's data and shapes."""
    build = _skill_build()
    cfg = build.load_config(os.path.join(HERE, "skill-run", "epm-config.json"))
    with open(RUN_CONFIG, encoding="utf-8") as f:
        sep = json.load(f)["separator"]
    nodes, rels, left_out = build.element_types(cfg, shapes, data, sep)
    for ends in rels.values():   # a relationship may reach a class no shape targets; it is a node all the same
        for source, target in ends:
            nodes.setdefault(source, {})
            nodes.setdefault(target, {})

    def iri(name):
        prefix, _, local = name.partition(sep)
        return cfg.prefixes[prefix] + local

    def prop(key, typed):
        out = {"type": f"LIST<{typed.base}>" if typed.listed else typed.base}
        if typed.required:
            out["must_exist"] = True
        return out | _about(data, iri(key))

    spec_nodes = {RESOURCE: {
        "labels": {"identifier": RESOURCE},
        "description": "Every node n10s loads from the release. Its uri is unique (the constraint n10s_unique_uri).",
        "properties": {"uri": {"type": "STRING", "unique": True, "description": "The term's IRI."},
                       "graph": _graph_key()},
    }}
    for label in sorted(nodes):
        properties = {"uri": {"type": "STRING", "description": "The term's IRI."},
                      "graph": _graph_key()}
        properties |= {key: prop(key, nodes[label][key]) for key in sorted(nodes[label])}
        spec_nodes[label] = {"labels": {"identifier": label, "implied": [RESOURCE]}, **_about(data, iri(label)),
                             "properties": properties}
    spec_rels = {}
    for key in sorted(rels):
        for source, target in sorted(rels[key]):
            spec_rels[f"{source}-{key}-{target}"] = {
                "type": key, "from": {"node": source, "label": source}, "to": {"node": target, "label": target},
                **_about(data, iri(key)), "properties": {"graph": _graph_key()}}
    return {
        "schema": SCHEMA_URL,
        "version": ", ".join(f"{module} {version}" for module, version in pipeline.PACKAGES),
        "id": "kpi-store",
        "name": "KPI Store",
        "description": "The graph the KPI Store's local Neo4j load builds from the release's Turtle with n10s. The "
                       "Turtle is the master copy; this document is written from it and never edited by hand.",
        "nodes": spec_nodes,
        "relationships": spec_rels,
        "extensions": {"custom": {
            "generated_by": "business_architecture/ontology/projection/neo4j_spec.py",
            "left_out": sorted({BLANK_NODE.sub("", line) for line in left_out}),
        }},
    }


def text():
    """neo4j-spec.json as it must read for the packages pipeline.py lists."""
    data, shapes = pipeline.graph(pipeline.INPUTS), pipeline.graph(pipeline.SHAPES)
    return json.dumps(document(data, shapes), indent=2, ensure_ascii=False) + "\n"


def schema_problems(doc):
    """Every way the document breaks the specification's 1.1.0 JSON Schema, one line each; empty when it conforms."""
    import jsonschema
    with open(SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(top)'}: {e.message}"
            for e in sorted(validator.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))]
