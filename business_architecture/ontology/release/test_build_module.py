"""Tests for the module release builder (Step 10; the decision of 2026-10-13): each written package equals a
fresh build, a release candidate carries no issued date, dependencies name versions that exist, and
the DCAT record and manifest describe the files.

Run: python3 -m pytest test_build_module.py (needs rdflib, pyshacl).
"""
import hashlib
import re
import json
import os
import unittest
from unittest import mock

from rdflib import Graph, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF

import build_module as bm

DCAT = bm.DCAT
# The sentence that approved each issued release (the decision of 2026-10-13).
SESSION2 = "(the review comments of a subject matter expert reviewing the documents)"
RECORDED = "(the review comments of a subject matter expert reviewing the documents)"
RELEASES = "(the review comments of a subject matter expert reviewing the documents)"
REF_MPC_1_2 = "(the review comments of a subject matter expert reviewing the documents)"
APPROVALS = {"organization": (RECORDED, "Yes, approve 2.0.0 (Recommended)"),
             "ref-mpc": (REF_MPC_1_2, "Approve ref-mpc 1.2.0 (Recommended)"),  # 1.2.0, the decision of 2026-10-22
             "kpi": ("(the review comments of a subject matter expert reviewing the documents)",
                     "You have my approval to keep going and release things as needed. while I am out"),
             "party": ("(the review comments of a subject matter expert reviewing the documents)",
                       "You have my permission to release the stable version when you are done.")}
# The Step 7 modules' first releases, approved with the release plan (the decision of 2026-10-22).
PLAN = ("(the review comments of a subject matter expert reviewing the documents)", "release plan approved")
STEP7 = ("data-product", "value-stream", "system", "lane", "market-data")
APPROVALS.update({name: PLAN for name in STEP7})
APPROVALS["integration"] = PLAN  # the decision of 2026-10-22
APPROVALS["kpi"] = PLAN  # kpi 1.1.0, the decision of 2026-10-22
# The close-out releases, approved together (the decision of 2026-10-23).
CLOSEOUT = ("(the review comments of a subject matter expert reviewing the documents)", "Approve all six (Recommended)")
APPROVALS["value-stream"] = CLOSEOUT  # value-stream 1.1.0, the decision of 2026-10-23
APPROVALS["data-product"] = CLOSEOUT  # data-product 1.1.0, the decision of 2026-10-23
APPROVALS["party"] = CLOSEOUT  # party 1.1.0, the decision of 2026-10-23
APPROVALS["kpi"] = CLOSEOUT  # kpi 1.1.1, the decision of 2026-10-23
APPROVALS["integration"] = (CLOSEOUT[0], "Major: integration 2.0.0 (Recommended)")  # the decision of 2026-10-23
# Item G's releases, approved together (the decision of 2026-10-25).
ITEM_G = ("(the review comments of a subject matter expert reviewing the documents)", "Approve all three (Recommended)")
APPROVALS.update({name: ITEM_G for name in ("system", "party", "integration")})  # system 1.1.0, party 1.2.0, integration 2.1.0
# Item F's releases, approved as one plan (the decision of 2026-10-25).
ITEM_F = ("(the review comments of a subject matter expert reviewing the documents)", "Approve the plan (Recommended)")
APPROVALS.update({name: ITEM_F for name in ("kpi", "market-data", "data-product", "system", "integration")})
# The internal systems' descriptions, approved by a subject matter expert (the decision of 2026-10-12, 2026-10-25, evening; 0103).
DELEGATED = ("(the review comments of a subject matter expert reviewing the documents)", "Approved as described")
APPROVALS.update({name: DELEGATED for name in ("system", "party", "integration")})  # system 1.3.0, party 1.3.0, integration 2.3.0
# The deferred qSKOS fixes, approved under the same delegation (the decision of 2026-10-26).
APPROVALS.update({name: DELEGATED for name in ("lane", "organization", "value-stream")})  # lane 1.1.0, organization 2.1.0 and 2.2.0, value-stream 1.2.0
# MPC-P11's releases, approved by a subject matter expert and the decision owner's brief (the decision of 2026-10-26).
BRIEF = ("(the review comments of a subject matter expert reviewing the documents)", "Approve (Recommended)")
APPROVALS.update({name: BRIEF for name in ("system", "party")})  # system 1.4.0, party 1.4.0
# The customer inputs' releases: party 2.0.0, a major the subject matter expert approved by aligning with the plan; system 1.5.0
# and integration 2.4.0, minors a subject matter expert approved with that alignment (the decision of 2026-10-27).
CUSTOMER_INPUTS = ("(the review comments of a subject matter expert reviewing the documents)",
                   "I am aligned with all your recommendation in the input plan.")
APPROVALS.update({name: CUSTOMER_INPUTS for name in ("party", "system", "integration")})
# ref-mpc 1.3.0, a minor release a subject matter expert approved on the subject matter expert's answer about the brands
# (the decision of 2026-10-27, amendment of 2026-10-27).
BRANDS = (CUSTOMER_INPUTS[0], "yes those can be brand values. Others I cannot answer.")
APPROVALS["ref-mpc"] = BRANDS
APPROVALS["party"] = DELEGATED  # party 2.1.0, the decision of 2026-10-25, amendment of 2026-10-28
APPROVALS["integration"] = DELEGATED  # integration 2.5.0, the decision of 2026-10-25, amendment of 2026-10-28
APPROVALS["kpi"] = DELEGATED  # kpi 1.3.0, the KPI and OPM identifiers, the decision of 2026-10-28
# technical-graph 1.0.0, the follow-up release's new module, a major the subject matter expert approved (the decision of 2026-11-02,
# amendment of 2026-11-02, later).
# technical-graph 1.1.0 is a minor release made under the delegation recorded in KPI-DEC-0001, which the release names.
APPROVALS["technical-graph"] = ("../domain/kpi-store-decisions/KPI-DEC-0001.md",
                                "Decide anything inside the plan yourself and log it.")
APPROVALS["logical-model"] = ("(the review comments of a subject matter expert reviewing the documents)", "I approve logical-model 1.0.0,")


def approval_holds(name, m):
    """The release names the sentence a subject matter expert reviewing the documents wrote for it, and that sentence is in the body of the
    saved file. Another sentence of the same file, an answer to another question, is not an approval."""
    path, words = m["approval"]
    if (path, words) != APPROVALS[name]:
        return False
    if not os.path.exists(os.path.join(bm.ONTOLOGY, path)):
        # The builders name the review comments of a subject matter expert, a sentence and not a file, and the
        # words travel with the package (the decision of 2026-10-31).
        return "subject matter expert" in path
    with open(os.path.join(bm.ONTOLOGY, path)) as f:
        # the words of a subject matter expert reviewing the documents sit in the body; the context sits in HTML comments.
        body = re.sub(r"<!--.*?-->", "", f.read(), flags=re.S)
    return words in body


def shipped(tc, name, version):
    """The package's folder, in releases/ or the history folder (build_module.package_folder). The tree holds each
    module's newest and previous packages, so a missing one fails."""
    folder = bm.package_folder(name, version)
    tc.assertIsNotNone(folder, f"{name} {version} is not on disk under releases/")
    return folder


class Packages(unittest.TestCase):
    def test_each_written_package_equals_a_fresh_build(self):
        for name in bm.MODULES:
            with self.subTest(module=name):
                g = bm.build(name)
                self.assertTrue(bm.check(name, g)[0])
                for fname, text in bm.package(name, g).items():
                    with open(os.path.join(bm.release_dir(name), fname)) as f:
                        self.assertEqual(f.read(), text, fname)

    def test_an_issued_release_carries_the_owners_recorded_approval_and_a_candidate_no_date(self):
        # A module's first release is a major, which needs the subject matter expert's approval (module policy).
        for name, m in bm.MODULES.items():
            with self.subTest(module=name):
                g = bm.build(name)
                manifest = json.loads(bm.package(name, g)["manifest.json"])
                issued = (URIRef(bm.MODULES_NS + name), DCTERMS.issued, None) in g
                if m["stage"] is None:
                    path, _ = m["approval"]
                    self.assertTrue(approval_holds(name, m))
                    self.assertTrue(issued)
                    iri = URIRef(bm.MODULES_NS + name)
                    self.assertEqual(g.value(iri, DCTERMS.modified), g.value(iri, DCTERMS.issued))
                    self.assertFalse(manifest["release_candidate"])
                    # A manifest names no file the tree does not hold: the field comes out (bm.recorded_where).
                    self.assertEqual(manifest["approved_by"].get("recorded_in"), bm.recorded_where(path))
                else:
                    self.assertFalse(issued)
                    self.assertTrue(manifest["release_candidate"])

    def test_another_sentence_of_the_answers_file_is_not_an_approval(self):
        wrong = dict(bm.MODULES["organization"], approval=(RECORDED, "Yes, cut 2.1.0 (Recommended)"))
        self.assertFalse(approval_holds("organization", wrong))
        self.assertTrue(approval_holds("organization", bm.MODULES["organization"]))

    def test_a_manifest_names_where_an_approval_is_recorded_only_as_a_path(self):
        # The sources name a subject matter expert's review comments, a sentence, and the manifest then leaves the
        # field out. A file in the tree is named.
        sentence = "(the review comments of a subject matter expert reviewing the documents)"
        self.assertIsNone(bm.recorded_where(sentence))
        self.assertEqual(bm.recorded_where("README.md"), "README.md")
        name = "organization"
        m = dict(bm.MODULES[name], approval=(sentence, "Approved as described"))
        g = bm.build(name)
        with mock.patch.dict(bm.MODULES, {name: m}):
            approved = json.loads(bm.package(name, g)["manifest.json"])["approved_by"]
        self.assertNotIn("recorded_in", approved)
        self.assertEqual(approved["words"], "Approved as described")

    def test_dependencies_name_versions_that_exist(self):
        for name in bm.MODULES:
            for dep, version in bm.dependencies(name).items():
                with self.subTest(module=name, dep=dep):
                    # The dependency's package must be on disk, not only in the builder's own table.
                    package = os.path.join(shipped(self, dep, version))
                    self.assertTrue(os.path.isfile(os.path.join(package, "manifest.json")), f"{name} names {dep} {version}")
                    with open(os.path.join(package, "manifest.json")) as f:
                        self.assertEqual(json.load(f)["version"], version)
                    self.assertIn((URIRef(bm.MODULES_NS + name), DCTERMS.requires,
                                   URIRef(f"{bm.MODULES_NS}{dep}/{version}")), bm.build(name))

    def test_ref_mpc_is_validated_with_the_control_relationship_shape(self):
        # ref-mpc's control relationship is checked by the organization module's shapes.
        shapes = bm.parse(bm.MODULES["ref-mpc"]["shapes"])
        sh = "http://www.w3.org/ns/shacl#"
        self.assertIn((None, URIRef(sh + "targetClass"), URIRef(bm.MODULES_NS + "organization/ControlRelationship")), shapes)

    def test_the_header_names_the_version(self):
        for name in bm.MODULES:
            g, iri = bm.build(name), URIRef(bm.MODULES_NS + name)
            self.assertIn((iri, RDF.type, OWL.Ontology), g)
            self.assertEqual(str(g.value(iri, OWL.versionIRI)), f"{iri}/{bm.label(bm.MODULES[name])}")

    def test_the_catalog_lists_the_three_distributions(self):
        for name in bm.MODULES:
            cat = Graph().parse(data=bm.catalog(name), format="turtle")
            dataset = next(cat.subjects(RDF.type, DCAT.Dataset))
            names = {str(d).rsplit("/", 1)[1] for d in cat.objects(dataset, DCAT.distribution)}
            # and a graph the package carries as it is (build_module's "graphs"; only logical-model has any)
            graphs = {os.path.basename(p) for p in bm.MODULES[name].get("graphs", [])}
            self.assertEqual(names, {f"{name}.ttl", f"{name}.jsonld", "shapes.ttl"} | graphs)

    def test_the_manifest_hashes_every_other_file(self):
        for name in bm.MODULES:
            files = bm.package(name, bm.build(name))
            manifest = json.loads(files["manifest.json"])
            self.assertEqual(set(manifest["files"]), set(files) - {"manifest.json"})
            for fname, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256(files[fname].encode()).hexdigest(), digest)


class EarlierReleases(unittest.TestCase):
    def test_party_holds_its_four_source_files_and_nothing_else(self):
        # the decision of 2026-10-22, item 2: the vocabulary, code lists, systems and lifecycle, read here from the
        # source files rather than from the builder's list; the reference parties and examples stay out.
        released = Graph().parse(os.path.join(bm.release_dir("party"), "party.ttl"))
        header = URIRef(bm.MODULES_NS + "party")
        released.remove((header, None, None))
        sources = Graph()
        for name in ("vocabulary.ttl", "code-lists.ttl", "systems.ttl", "lifecycle.ttl"):
            sources.parse(os.path.join(bm.ONTOLOGY, "party", name))
        sources.remove((header, None, None))
        self.assertEqual(set(released), set(sources))
        for path in ("ref-mpc/reference-parties.ttl", "party/examples.ttl"):
            outside = Graph().parse(os.path.join(bm.ONTOLOGY, path))
            self.assertFalse(set(outside) & set(released), path)

    def test_the_new_releases_require_the_current_ones(self):
        # Every newest package is built against the newest versions (the decision of 2026-10-31).
        self.assertEqual(bm.dependencies("ref-mpc"), {"organization": "2.2.0", "party": "2.1.0"})
        self.assertEqual(bm.dependencies("organization"), {"core": "2.4.0"})
        self.assertEqual(bm.dependencies("kpi"), {"core": "2.4.0"})
        self.assertEqual(bm.dependencies("party"), {"core": "2.4.0", "system": "1.5.0"})
        self.assertEqual(bm.dependencies("data-product"), {"core": "2.4.0", "kpi": "1.3.0", "system": "1.5.0"})
        self.assertEqual(bm.dependencies("value-stream"), {"core": "2.4.0", "data-product": "1.2.0", "kpi": "1.3.0"})
        self.assertEqual(bm.dependencies("system"), {"core": "2.4.0"})
        self.assertEqual(bm.dependencies("lane"), {"core": "2.4.0"})
        self.assertEqual(bm.dependencies("market-data"), {"kpi": "1.3.0"})
        self.assertEqual(bm.dependencies("integration"), {
            "core": "2.4.0", "organization": "2.2.0", "kpi": "1.3.0", "data-product": "1.2.0",
            "value-stream": "1.2.0", "system": "1.5.0", "lane": "1.1.0", "market-data": "1.1.0", "party": "2.1.0"})
        self.assertEqual(bm.dependencies("logical-model"), {"party": "2.1.0", "system": "1.5.0", "data-product": "1.2.0"})

    def test_the_closure_reads_the_builders_table_and_no_manifest(self):
        # The newest packages are rebuilt in some order, so a manifest not yet rebuilt may still name a version the
        # tree does not hold: a module's closure never opens one (the decision of 2026-10-31).
        def manifest_opened(dep, version):
            raise AssertionError(f"released_requires({dep}, {version}) was read")
        with mock.patch.object(bm, "released_requires", manifest_opened), \
                mock.patch.object(bm, "newest_on_disk", lambda module: "9.9.9"):
            def reach(name):
                # Every module reachable through the builders' raw depends_on lists (core reaches nothing).
                seen, todo = set(), list(bm.MODULES[name]["depends_on"])
                while todo:
                    d = todo.pop()
                    if d not in seen:
                        seen.add(d)
                        todo += bm.MODULES[d]["depends_on"] if d in bm.MODULES else []
                return seen
            newest = lambda d: "9.9.9" if d == "core" else bm.label(bm.MODULES[d])
            self.assertEqual(reach("value-stream"), {"core", "data-product", "kpi", "system"})
            for name in bm.MODULES:
                self.assertEqual(bm.released_closure(name), {d: newest(d) for d in reach(name)}, name)

    def test_a_release_that_loses_to_a_higher_one_adds_no_requirements(self):
        # catalog 1.0.0 needs types 1.0.0; catalog 1.1.0 needs nothing. reviews needs catalog 1.1.0, so
        # 1.1.0 wins and types must not load, whichever requirement is met first (the ontology skill's
        # check_packages test, a change to the skills folder). The old closure loaded types.
        table = {("catalog", "1.0.0"): {"types": "1.0.0"}, ("catalog", "1.1.0"): {},
                 ("reviews", "1.0.0"): {"catalog": "1.1.0"}, ("types", "1.0.0"): {}}
        real = bm.released_requires
        bm.released_requires = lambda dep, version: dict(table[(dep, version)])
        try:
            for order in ({"catalog": "1.0.0", "reviews": "1.0.0"}, {"reviews": "1.0.0", "catalog": "1.0.0"}):
                with self.subTest(order=list(order)):
                    self.assertEqual(bm.closure(order), {"catalog": "1.1.0", "reviews": "1.0.0"})
        finally:
            bm.released_requires = real

    def test_a_correction_version_wins_over_the_version_it_corrects(self):
        # reviews needs catalog 1.0.0 and prices needs catalog 1.0.1-correction.1: the correction is the higher one.
        table = {("catalog", "1.0.0"): {}, ("catalog", "1.0.1-correction.1"): {}, ("catalog", "1.0.1-correction.2"): {},
                 ("reviews", "1.0.0"): {"catalog": "1.0.0"}, ("prices", "1.0.0"): {"catalog": "1.0.1-correction.1"},
                 ("offers", "1.0.0"): {"catalog": "1.0.1-correction.2"}}
        requires = lambda dep, version: dict(table[(dep, version)])
        self.assertEqual(bm.closure({"reviews": "1.0.0", "prices": "1.0.0"}, requires),
                         {"reviews": "1.0.0", "prices": "1.0.0", "catalog": "1.0.1-correction.1"})
        self.assertEqual(bm.closure({"offers": "1.0.0", "prices": "1.0.0"}, requires),
                         {"offers": "1.0.0", "prices": "1.0.0", "catalog": "1.0.1-correction.2"})

    def test_a_shape_path_with_a_correction_version_names_the_newest_package(self):
        current = bm.label(bm.MODULES["party"])
        self.assertEqual(bm.resolve("releases/party/1.0.1-correction.3/shapes.ttl"), f"releases/party/{current}/shapes.ttl")
        self.assertEqual(bm.resolve("releases/party/1.0.0/shapes.ttl"), f"releases/party/{current}/shapes.ttl")
        self.assertEqual(bm.resolve("party/shapes.ttl"), "party/shapes.ttl")

    def test_a_choice_justified_only_by_a_losing_release_does_not_settle(self):
        # root needs a 1.0.0, which needs b 1.0.0, which needs a 2.0.0,
        # which needs b 2.0.0. a 2.0.0 is reached only through b 1.0.0, which loses to b 2.0.0, which is
        # reached only through a 2.0.0. A losing release adds nothing, so no set of choices justifies itself:
        # the closure fails loudly instead of returning a wrong set.
        table = {("a", "1.0.0"): {"b": "1.0.0"}, ("b", "1.0.0"): {"a": "2.0.0"},
                 ("a", "2.0.0"): {"b": "2.0.0"}, ("b", "2.0.0"): {}}
        real = bm.released_requires
        bm.released_requires = lambda dep, version: dict(table[(dep, version)])
        try:
            with self.assertRaisesRegex(ValueError, "does not settle"):
                bm.closure({"a": "1.0.0"})
        finally:
            bm.released_requires = real

    def test_a_closure_that_never_settles_fails(self):
        # a 1.0.0 needs b 1.0.0, which needs a 2.0.0; a 2.0.0 needs nothing, so b drops and a 1.0.0 returns.
        table = {("a", "1.0.0"): {"b": "1.0.0"}, ("b", "1.0.0"): {"a": "2.0.0"}, ("a", "2.0.0"): {}}
        real = bm.released_requires
        bm.released_requires = lambda dep, version: dict(table[(dep, version)])
        try:
            with self.assertRaisesRegex(ValueError, "does not settle"):
                bm.closure({"a": "1.0.0"})
        finally:
            bm.released_requires = real

    def test_each_step7_package_holds_its_two_source_files(self):
        # the decision of 2026-10-22: each package is its module's vocabulary and instance file, nothing else. The newest
        # release of each is compared with the sources (value-stream 1.1.0 since the decision of 2026-10-23).
        # data-product 1.2.0 adds pricing.ttl, its third source file (the decision of 2026-10-25).
        files = {"data-product": ("data-products.ttl", "pricing.ttl"), "value-stream": ("value-streams.ttl",),
                 "system": ("systems.ttl",), "lane": ("lanes.ttl",), "market-data": ("market-data.ttl",)}
        for name, instances in files.items():
            with self.subTest(module=name):
                released = Graph().parse(os.path.join(bm.release_dir(name), f"{name}.ttl"))
                header = URIRef(bm.MODULES_NS + name)
                released.remove((header, None, None))
                sources = Graph()
                for part in ("vocabulary.ttl",) + instances:
                    sources.parse(os.path.join(bm.ONTOLOGY, name, part))
                sources.remove((header, None, None))
                self.assertEqual(set(released), set(sources))

    def test_ref_mpc_1_2_0_is_untouched(self):
        # ref-mpc 1.3.0 is built now; the released 1.2.0 package must still match its own manifest.
        out = os.path.join(shipped(self, "ref-mpc", "1.2.0"))
        with open(os.path.join(out, "manifest.json")) as f:
            manifest = json.load(f)
        self.assertEqual(manifest["version"], "1.2.0")
        for fname, digest in manifest["files"].items():
            with self.subTest(file=fname), open(os.path.join(out, fname), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest)

    def test_ref_mpc_1_3_0_holds_the_companies_the_parties_and_the_brands(self):
        # the decision of 2026-10-27, amendment of 2026-10-27: the brands join the two parts of 1.2.0.
        released = Graph().parse(os.path.join(shipped(self, "ref-mpc", "1.3.0"), "ref-mpc.ttl"))
        header = URIRef(bm.MODULES_NS + "ref-mpc")
        released.remove((header, None, None))
        sources = Graph()
        for part in ("ref-mpc/ref-mpc.ttl", "ref-mpc/reference-parties.ttl", "ref-mpc/reference-brands.ttl"):
            sources.parse(os.path.join(bm.ONTOLOGY, part))
        sources.remove((header, None, None))
        self.assertEqual(set(released), set(sources))
        for slug in ("marathon", "arco", "tesoro"):
            self.assertIn((URIRef(bm.MODULES_NS + "ref-mpc/brand/" + slug), None, None), released)
        with open(os.path.join(shipped(self, "ref-mpc", "1.3.0"), "manifest.json")) as f:
            manifest = json.load(f)
        self.assertEqual(manifest["approved_by"].get("recorded_in"), bm.recorded_where(BRANDS[0]))

    def test_the_brands_release_carries_the_answer(self):
        m = bm.MODULES["ref-mpc"]
        self.assertEqual(m["approval"], BRANDS)
        self.assertEqual((m["version"], m["stage"], m["issued"]), ("1.3.0", None, "2026-10-27"))
        self.assertIn("the decision of 2026-10-27", m["decisions"])
        self.assertTrue(m["approver"].startswith("a subject matter expert reviewing the documents"))

    def test_ref_mpc_1_2_0_holds_the_companies_and_the_parties(self):
        # the decision of 2026-10-22: ref-mpc.ttl and the reference parties moved from party/ (the decision of 2026-10-22).
        released = Graph().parse(os.path.join(shipped(self, "ref-mpc", "1.2.0"), "ref-mpc.ttl"))
        header = URIRef(bm.MODULES_NS + "ref-mpc")
        released.remove((header, None, None))
        sources = Graph()
        for part in ("ref-mpc/ref-mpc.ttl", "ref-mpc/reference-parties.ttl"):
            sources.parse(os.path.join(bm.ONTOLOGY, part))
        sources.remove((header, None, None))
        self.assertEqual(set(released), set(sources))
        self.assertIn((URIRef(bm.MODULES_NS + "ref-mpc/party/mpc-payer"), None, None), released)

    def test_kpi_holds_the_measures_and_the_populations(self):
        # the decision of 2026-10-22: the kpi vocabulary and measures, and the population vocabulary and statements, in the newest
        # release (1.1.1 since the decision of 2026-10-23, which adds pop:populationEvidence's range).
        released = Graph().parse(os.path.join(bm.release_dir("kpi"), "kpi.ttl"))
        header = URIRef(bm.MODULES_NS + "kpi")
        released.remove((header, None, None))
        sources = Graph()
        for part in ("kpi/vocabulary.ttl", "kpi/measures.ttl", "population/vocabulary.ttl", "population/population.ttl"):
            sources.parse(os.path.join(bm.ONTOLOGY, part))
        sources.remove((header, None, None))
        self.assertEqual(set(released), set(sources))
        pop = URIRef(bm.MODULES_NS + "population/includes")
        self.assertEqual(len(list(released.subject_objects(pop))), 8)
        xsd_string = URIRef("http://www.w3.org/2001/XMLSchema#string")
        rng = URIRef("http://www.w3.org/2000/01/rdf-schema#range")
        self.assertEqual(set(released.objects(URIRef(bm.MODULES_NS + "population/populationEvidence"), rng)), {xsd_string})

    def test_integration_holds_three_vocabularies_and_neither_population_nor_apqc(self):
        # the decision of 2026-10-22: placement, authority (vocabulary and source tiers) and consumer, read from the
        # source files; the population statements ship in kpi 1.1.0 and the APQC list stays a reference file.
        released = Graph().parse(os.path.join(bm.release_dir("integration"), "integration.ttl"))
        header = URIRef(bm.MODULES_NS + "integration")
        released.remove((header, None, None))
        sources = Graph()
        for part in ("placement/vocabulary.ttl", "authority/vocabulary.ttl", "authority/source-tiers.ttl",
                     "consumer/vocabulary.ttl"):
            sources.parse(os.path.join(bm.ONTOLOGY, part))
        self.assertEqual(set(released), set(sources))
        for part in ("population/vocabulary.ttl", "population/population.ttl", "apqc/apqc-elements.ttl"):
            outside = Graph().parse(os.path.join(bm.ONTOLOGY, part))
            self.assertFalse(set(outside) & set(released), part)
        # Each vocabulary keeps its own namespace: no term is minted under the package IRI.
        self.assertFalse([s for s in released.subjects() if str(s).startswith(bm.MODULES_NS + "integration")])

    def test_integration_ships_its_own_shapes(self):
        # the package's shapes are the module's own, not whatever the builder names. Since 2.0.0 they
        # are the consumer, placement and authority shapes together (the decision of 2026-10-23); 1.0.0 shipped consumer's only.
        packaged = Graph().parse(os.path.join(bm.release_dir("integration"), "shapes.ttl"))
        source = Graph()
        for part in ("consumer/shapes.ttl", "placement/shapes.ttl", "authority/shapes.ttl"):
            source.parse(os.path.join(bm.ONTOLOGY, part))
        from rdflib.compare import isomorphic
        self.assertTrue(isomorphic(packaged, source))
        self.assertFalse(isomorphic(packaged, Graph().parse(os.path.join(bm.ONTOLOGY, "data-product", "shapes.ttl"))))

    def test_every_term_a_consumer_rule_relies_on_is_defined_in_the_released_closure(self):
        # integration's published dependencies define each term its rules rely on (party:roleType
        # needed party 1.0.0). The population terms ship in kpi 1.1.0, after this package (the decision of 2026-10-22, item 5).
        con = "https://w3id.org/mpc/ontology/modules/consumer/"
        pop = "https://w3id.org/mpc/ontology/modules/population/"
        data = bm.validation_graph("integration", bm.build("integration"))
        relies = set(data.objects(None, URIRef(con + "reliesOn")))
        local = {t for t in relies if str(t).startswith("https://w3id.org/mpc/")}
        self.assertIn(URIRef(bm.MODULES_NS + "party/roleType"), local)
        # Declared, not merely mentioned: placement annotates other modules' properties, which makes them
        # subjects here without defining them.
        undefined = {str(t) for t in local if not str(t).startswith(pop) and (t, RDF.type, None) not in data}
        self.assertEqual(undefined, set())

    def test_the_step7_releases_carry_the_release_plan_approval(self):
        for name in tuple(n for n in STEP7 if n not in ("value-stream", "data-product", "system", "market-data", "lane")):
            self.assertEqual(bm.MODULES[name]["approval"], PLAN)
            self.assertEqual((bm.MODULES[name]["version"], bm.MODULES[name]["stage"], bm.MODULES[name]["issued"]),
                             ("1.0.0", None, "2026-10-22"))


    def test_the_delegated_releases_carry_the_delegation(self):
        # the decision of 2026-10-26: a subject matter expert approved the three minor releases.
        # the decision of 2026-10-26: and the three that carry the deferred qSKOS fixes.
        # system 1.3.0 and party 1.3.0 carried it too, until system 1.4.0 and party 1.4.0 (the decision of 2026-10-26), and
        # integration 2.3.0 until integration 2.4.0 (the decision of 2026-10-27).
        # organization 2.1.0 carried it until organization 2.2.0, which carries it too (the decision of 2026-10-18, amendment
        # of 2026-10-28).
        for name, version in (("lane", "1.1.0"), ("value-stream", "1.2.0")):
            self.assertEqual(bm.MODULES[name]["approval"], DELEGATED)
            self.assertEqual((bm.MODULES[name]["version"], bm.MODULES[name]["stage"], bm.MODULES[name]["issued"]),
                             (version, None, "2026-10-26"))
        m = bm.MODULES["organization"]
        self.assertEqual(m["approval"], DELEGATED)
        self.assertEqual((m["version"], m["stage"], m["issued"]), ("2.2.0", None, "2026-10-28"))
        self.assertTrue(m["approver"].startswith("a subject matter expert reviewing the documents"))

    def test_the_customer_inputs_releases_carry_the_alignment(self):
        # the decision of 2026-10-27: party 2.0.0, a major the subject matter expert approved by aligning with the plan that names it;
        # system 1.5.0 and integration 2.4.0, minors a subject matter expert approved with that alignment.
        # party 2.0.0 and integration 2.4.0 carried it until party 2.1.0 and integration 2.5.0 (the decision of 2026-10-25,
        # amendment of 2026-10-28).
        m = bm.MODULES["system"]
        self.assertEqual(m["approval"], CUSTOMER_INPUTS)
        self.assertEqual((m["version"], m["stage"], m["issued"]), ("1.5.0", None, "2026-10-27"))
        self.assertIn("the decision of 2026-10-27", m["decisions"])
        for name, version in (("party", "2.1.0"), ("integration", "2.5.0")):
            m = bm.MODULES[name]
            self.assertEqual(m["approval"], DELEGATED)
            self.assertEqual((m["version"], m["stage"], m["issued"]), (version, None, "2026-10-28"))
            self.assertTrue(m["approver"].startswith("a subject matter expert reviewing the documents"))
        for name in ("system", "integration"):
            self.assertTrue(bm.MODULES[name]["approver"].startswith("a subject matter expert reviewing the documents"))

    def test_the_item_f_releases_carry_their_approval(self):
        # the decision of 2026-10-25: the subject matter expert approved the plan of the five.
        for name, version in (("market-data", "1.1.0"), ("data-product", "1.2.0")):
            self.assertEqual(bm.MODULES[name]["approval"], ITEM_F)
            self.assertEqual((bm.MODULES[name]["version"], bm.MODULES[name]["stage"], bm.MODULES[name]["issued"]),
                             (version, None, "2026-10-25"))

class BuilderGate(unittest.TestCase):
    def test_the_builder_runs_sparql_targets(self):
        # integration's tier shape uses a SPARQL target, so the builder's own
        # check must run SHACL-AF; a tier without its rank fails there.
        g = bm.build("integration")
        self.assertTrue(bm.check("integration", g)[0])
        mpc = URIRef(bm.MODULES_NS + "authority/tier/mpc")
        g.remove((mpc, URIRef(bm.MODULES_NS + "authority/rank"), None))
        ok, text = bm.check("integration", g)
        self.assertFalse(ok)
        self.assertIn("MinCountConstraintComponent", text)


if __name__ == "__main__":
    unittest.main()
