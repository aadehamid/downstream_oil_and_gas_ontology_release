"""Tests for the Neo4j Ontology Graph Specification document (neo4j_spec.py) and its place in pipeline.py build. They
need no Neo4j and no network: the specification's 1.1.0 JSON Schema is the copy kept in this folder.

Run: python3 -m pytest test_neo4j_spec.py (needs rdflib, pyshacl, jsonschema).
"""
import copy
import hashlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from rdflib import Graph

import neo4j_spec as ns
import pipeline as pl

# A small module in the release's own namespaces: a class with a definition and two other names, a literal
# property that every node must have, and a link to another class.
DATA = """
@prefix kpi: <https://w3id.org/mpc/ontology/modules/kpi/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
kpi:MeasureDefinition skos:definition "What a measure is, before anyone computes it."@en ;
    skos:altLabel "KPI"@en, "measure"@en .
kpi:measureCode skos:definition "The measure's short code."@en .
kpi:informs rdfs:comment "The process a measure informs." .
kpi:m1 a kpi:MeasureDefinition ; kpi:measureCode "M1" ; kpi:informs kpi:p1 .
kpi:p1 a kpi:Process .
"""
SHAPES = """
@prefix kpi: <https://w3id.org/mpc/ontology/modules/kpi/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
kpi:MeasureShape a sh:NodeShape ; sh:targetClass kpi:MeasureDefinition ;
    sh:property [ sh:path kpi:measureCode ; sh:datatype xsd:string ; sh:minCount 1 ; sh:maxCount 1 ] ;
    sh:property [ sh:path kpi:informs ; sh:class kpi:Process ] .
"""
# The SHA-256 of the schema file as fetched on 2026-11-21; README.md records the same value.
SCHEMA_SHA256 = "c8fc0021c86b944a3090e7c5e084409970274fdabea79c8b715976fc09da78eb"


def small():
    return ns.document(Graph().parse(data=DATA, format="turtle"), Graph().parse(data=SHAPES, format="turtle"))


class Document(unittest.TestCase):
    def test_a_small_module_gives_a_document_that_conforms(self):
        self.assertEqual(ns.schema_problems(small()), [])

    def test_a_class_takes_its_definition_its_other_names_and_its_iri(self):
        node = small()["nodes"]["kpi_MeasureDefinition"]
        self.assertEqual(node["description"], "What a measure is, before anyone computes it.")
        self.assertEqual(node["aliases"], ["KPI", "measure"])
        self.assertEqual(node["reference"], "https://w3id.org/mpc/ontology/modules/kpi/MeasureDefinition")
        self.assertEqual(node["labels"], {"identifier": "kpi_MeasureDefinition", "implied": ["Resource"]})

    def test_a_property_is_typed_and_required_from_its_shape(self):
        prop = small()["nodes"]["kpi_MeasureDefinition"]["properties"]["kpi_measureCode"]
        self.assertEqual(prop, {"type": "STRING", "must_exist": True, "description": "The measure's short code.",
                                "reference": "https://w3id.org/mpc/ontology/modules/kpi/measureCode"})

    def test_a_link_to_a_class_is_a_relationship_and_its_end_is_a_node(self):
        doc = small()
        rel = doc["relationships"]["kpi_MeasureDefinition-kpi_informs-kpi_Process"]
        self.assertEqual((rel["type"], rel["from"]["label"], rel["to"]["label"]),
                         ("kpi_informs", "kpi_MeasureDefinition", "kpi_Process"))
        self.assertEqual(rel["description"], "The process a measure informs.")   # rdfs:comment when there is no definition
        self.assertIn("kpi_Process", doc["nodes"])
        self.assertNotIn("description", doc["nodes"]["kpi_Process"])            # no definition, no description

    def test_a_property_shape_with_no_type_is_listed_as_left_out(self):
        shapes = SHAPES.replace("sh:datatype xsd:string ;", "")
        doc = ns.document(Graph().parse(data=DATA, format="turtle"), Graph().parse(data=shapes, format="turtle"))
        self.assertIn("kpi_MeasureDefinition.kpi_measureCode: no sh:datatype or sh:class to map",
                      doc["extensions"]["custom"]["left_out"])
        self.assertNotIn("kpi_measureCode", doc["nodes"]["kpi_MeasureDefinition"]["properties"])

    def test_the_schema_check_finds_a_broken_document(self):
        for change, expected in ((lambda d: d.pop("id"), "'id' is a required property"),
                                 (lambda d: d["nodes"]["kpi_MeasureDefinition"]["properties"]["kpi_measureCode"]
                                  .update(type="TEXT"), "'TEXT' is not one of"),
                                 (lambda d: d.update(owner="someone"), "Additional properties are not allowed")):
            doc = copy.deepcopy(small())
            change(doc)
            problems = ns.schema_problems(doc)
            self.assertTrue(any(expected in p for p in problems), problems)


class ThisRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ns.SPEC, encoding="utf-8") as f:
            cls.doc = json.load(f)

    def test_the_kept_schema_is_the_published_1_1_0(self):
        with open(ns.SCHEMA, "rb") as f:
            raw = f.read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SCHEMA_SHA256)
        self.assertEqual(json.loads(raw)["$id"], ns.SCHEMA_URL)
        self.assertEqual(self.doc["schema"], ns.SCHEMA_URL)

    def test_every_label_and_type_is_the_name_the_load_gives_the_term(self):
        named = [(n["labels"]["identifier"], n["reference"]) for k, n in self.doc["nodes"].items() if k != ns.RESOURCE]
        named += [(r["type"], r["reference"]) for r in self.doc["relationships"].values()]
        named += [(key, p["reference"]) for n in self.doc["nodes"].values() for key, p in n["properties"].items()
                  if "reference" in p]
        self.assertGreater(len(named), 100)
        self.assertEqual([(name, iri) for name, iri in named if pl.lpg_name(iri) != name], [])

    def test_the_document_names_the_packages_it_describes(self):
        self.assertEqual(self.doc["version"], ", ".join(f"{m} {v}" for m, v in pl.PACKAGES))


class Build(unittest.TestCase):
    """pipeline.py build writes the document, and build --verify fails on a stale or a broken one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manifest = os.path.join(self.tmp.name, "projection-manifest.json")
        self.spec = os.path.join(self.tmp.name, "neo4j-spec.json")
        for patch in (mock.patch.object(pl, "build", lambda: ("a\n", "", "{}\n")),
                      mock.patch.object(pl, "MANIFEST", self.manifest), mock.patch.object(ns, "SPEC", self.spec),
                      mock.patch.object(ns, "text", lambda: json.dumps(small(), indent=2) + "\n")):
            patch.start()
            self.addCleanup(patch.stop)

    def main(self, *args):
        out = io.StringIO()
        with mock.patch("sys.argv", ["pipeline.py", "build", *args]), mock.patch("sys.stdout", out):
            pl.main()
        return out.getvalue()

    def test_build_writes_the_document_and_verify_passes(self):
        self.assertIn("wrote neo4j-spec.json", self.main())
        with open(self.spec, encoding="utf-8") as f:
            self.assertEqual(f.read(), ns.text())
        self.assertIn("neo4j-spec.json is current and conforms", self.main("--verify"))

    def test_verify_fails_on_a_stale_document(self):
        self.main()
        with open(self.spec, "a", encoding="utf-8") as f:
            f.write(" ")
        with self.assertRaisesRegex(SystemExit, "neo4j-spec.json is not current"):
            self.main("--verify")

    def test_verify_fails_on_a_document_that_breaks_the_schema(self):
        broken = small()
        broken["nodes"]["kpi_MeasureDefinition"]["properties"]["kpi_measureCode"]["type"] = "TEXT"
        with mock.patch.object(ns, "text", lambda: json.dumps(broken, indent=2) + "\n"):
            self.main()
            with self.assertRaisesRegex(SystemExit, "breaks the specification's 1.1.0 schema"):
                self.main("--verify")


if __name__ == "__main__":
    unittest.main()
