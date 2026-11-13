"""Tests for update_examples.py: the files each worked example changes, what it writes there, and its refusals.

The lists of files below are written by hand. HOW-TO-UPDATE.md follows each example to its end, the full check,
in the document test's slow context.
"""
import glob
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import update_examples as ue  # noqa: E402

ONT = "business_architecture/ontology"
PROCESS = "business_architecture/business_process"
# For each example: the files of this release it changes, and the files it adds. Written by hand.
CHANGED = {
    "deprecate-role": [f"{ONT}/organization/roles.csv", f"{ONT}/organization/test_roles.py", "scripts/pinned-tests.txt"],
    "system-kind": [f"{ONT}/system/vocabulary.ttl", f"{ONT}/system/shapes.ttl", f"{ONT}/system/build_systems.py",
                    f"{ONT}/system/other-systems.csv", f"{ONT}/system/test_systems.py"],
    "move-entry": [f"{PROCESS}/data_product_portfolio.json", "business_architecture/schema/data_product_portfolio.schema.json",
                   f"{ONT}/data-product/vocabulary.ttl", f"{ONT}/data-product/shapes.ttl",
                   f"{ONT}/data-product/build_data_products.py", f"{ONT}/data-product/test_data_products.py"],
    "raci": [f"{PROCESS}/downstream_process_map.json", f"{ONT}/organization/role-register.csv", f"{ONT}/organization/roles.csv",
             f"{ONT}/organization/test_roles.py", "scripts/pinned-tests.txt", "kpi-intake/README.md"],
    "domain-list": [f"{ONT}/kpi/vocabulary.ttl", f"{ONT}/kpi/shapes.ttl", f"{ONT}/release/build_module.py",
                    f"{ONT}/release/test_build_module.py", "scripts/check.sh",
                    f"{ONT}/regression/expected.csv", f"{ONT}/regression/run.py", f"{ONT}/competency-questions.md", f"{ONT}/MODULES.md"],
}
ADDED = {
    "deprecate-role": [],
    "system-kind": [],
    "move-entry": [f"{PROCESS}/proposals/EXAMPLE-P02-portfolio-entry.md"],
    "raci": [f"{PROCESS}/proposals/EXAMPLE-P01-sample-raci.md"],
    "domain-list": [f"{ONT}/kpi/data-domains.csv", f"{ONT}/kpi/build_data_domains.py", f"{ONT}/kpi/test_data_domains.py",
                    f"{ONT}/regression/queries/q58-data-domains.rq"],
}
FOLLOWED = glob.glob(os.path.join(ue.ROOT, ONT, "approvals", "example-*.md"))


def copy_of(name, tmp):
    for path in CHANGED[name]:
        os.makedirs(os.path.dirname(os.path.join(tmp, path)), exist_ok=True)
        shutil.copyfile(os.path.join(ue.ROOT, path), os.path.join(tmp, path))


def files(tmp):
    found = {}
    for folder, _, names in os.walk(tmp):
        for name in names:
            with open(os.path.join(folder, name), "rb") as f:
                found[os.path.relpath(os.path.join(folder, name), tmp).replace(os.sep, "/")] = f.read()
    return found


def written(name):
    """The files of a temporary copy after the example was written there, as text, and the lines it said."""
    with tempfile.TemporaryDirectory() as tmp:
        copy_of(name, tmp)
        before, said = files(tmp), []
        ue.apply(name, root=tmp, date="2026-11-12", write=True, say=said.append)
        after = files(tmp)
    return before, {path: data.decode("utf-8") for path, data in after.items()}, said


@unittest.skipIf(FOLLOWED, "this copy holds a worked example already: an example was followed here")
class Examples(unittest.TestCase):
    def test_the_five_examples(self):
        self.assertEqual(sorted(ue.EXAMPLES), ["deprecate-role", "domain-list", "move-entry", "raci", "system-kind"])
        self.assertEqual(sorted(CHANGED), sorted(ue.EXAMPLES))

    def test_a_plan_names_each_file_and_changes_nothing(self):
        for name in ue.EXAMPLES:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                copy_of(name, tmp)
                before, said = files(tmp), []
                done = ue.apply(name, root=tmp, date="2026-11-12", say=said.append)
                self.assertEqual(said, [f"would change {place}" for place in done])
                self.assertEqual(len(done), len(ue.EXAMPLES[name]["places"]))
                self.assertEqual(files(tmp), before)

    def test_write_changes_these_files_and_adds_these(self):
        for name in ue.EXAMPLES:
            with self.subTest(name):
                before, after, said = written(name)
                self.assertEqual(sorted(set(after) - set(before)), sorted(ADDED[name] + [f"{ONT}/approvals/example-{name}.md"]))
                self.assertEqual(sorted(p for p in before if before[p].decode("utf-8") != after[p]), sorted(CHANGED[name]))
                self.assertTrue(all(line.startswith("changed ") for line in said))

    def test_a_second_run_is_refused_and_changes_nothing(self):
        for name in ue.EXAMPLES:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                copy_of(name, tmp)
                ue.apply(name, root=tmp, date="2026-11-12", write=True, say=lambda line: None)
                before = files(tmp)
                with self.assertRaisesRegex(ue.Refused, f"holds the example {name} already"):
                    ue.apply(name, root=tmp, date="2026-11-12", write=True, say=lambda line: None)
                self.assertEqual(files(tmp), before)

    def test_a_file_that_is_not_as_expected_stops_the_run_with_nothing_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_of("system-kind", tmp)
            table = os.path.join(tmp, ONT, "system", "other-systems.csv")
            with open(table, encoding="utf-8", newline="") as f:
                text = f.read()
            with open(table, "w", encoding="utf-8", newline="") as f:
                f.write(text.replace("databricks,Databricks,,application,", "databricks,Databricks,,office-tool,"))
            before = files(tmp)
            with self.assertRaisesRegex(ue.Refused, "other-systems.csv: expected one place"):
                ue.apply("system-kind", root=tmp, date="2026-11-12", write=True, say=lambda line: None)
            self.assertEqual(files(tmp), before)

    def test_a_missing_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:   # an empty folder holds none of the files
            with self.assertRaises(ue.Refused):
                ue.apply("deprecate-role", root=tmp, date="2026-11-12", say=lambda line: None)

    def test_the_role_is_deprecated_into_its_successor(self):
        _, after, _ = written("deprecate-role")
        row = next(line for line in after[f"{ONT}/organization/roles.csv"].splitlines() if line.startswith("black-oil-manager,"))
        self.assertTrue(row.startswith('black-oil-manager,Black Oil Manager,,position,asphalt-manager,alt,,"Deprecated: a made-up answer'))
        self.assertIn('"black-oil-manager": "asphalt-manager",', after[f"{ONT}/organization/test_roles.py"])
        self.assertIn("(4, 56))", after[f"{ONT}/organization/test_roles.py"])
        self.assertTrue(after["scripts/pinned-tests.txt"].endswith(
            "kpi_store/tests/test_cut.py::test_the_baseline_is_this_trees_or_data_product_has_moved_on\n"))

    def test_the_system_takes_a_fourth_kind(self):
        _, after, _ = written("system-kind")
        self.assertIn("databricks,Databricks,,data-platform,", after[f"{ONT}/system/other-systems.csv"])
        self.assertIn('kind:data-platform a skos:Concept ; skos:inScheme sys:SystemKind ;', after[f"{ONT}/system/vocabulary.ttl"])
        self.assertIn("kind:document, kind:data-platform ;", after[f"{ONT}/system/vocabulary.ttl"])
        self.assertIn("sh:in ( kind:application kind:office-tool kind:document kind:data-platform ) ]", after[f"{ONT}/system/shapes.ttl"])
        self.assertIn('KINDS = ("application", "office-tool", "document", "data-platform")', after[f"{ONT}/system/build_systems.py"])

    def test_the_entry_moves_to_a_new_class_and_keeps_its_id(self):
        _, after, _ = written("move-entry")
        self.assertIn('{ "id": "dp-hr", "name": "HR", "status": "defined_only", "kind": "portfolio" }', after[f"{PROCESS}/data_product_portfolio.json"])
        self.assertIn("dp:DataPortfolio a owl:Class ;", after[f"{ONT}/data-product/vocabulary.ttl"])
        import json
        schema = json.loads(after["business_architecture/schema/data_product_portfolio.schema.json"])
        self.assertEqual(schema["$defs"]["portfolio"]["properties"]["kind"], {"type": "string", "enum": ["portfolio"]})
        self.assertIn("    sh:not [ sh:class dp:DataProduct ] ;", after[f"{ONT}/data-product/shapes.ttl"])
        self.assertIn('describe(PRODUCT[local("dp-", p["id"])], DP.DataPortfolio, p, l, "data portfolio")', after[f"{ONT}/data-product/build_data_products.py"])
        self.assertIn("Status | Accepted (a made-up decision, 2026-11-12)", after[f"{PROCESS}/proposals/EXAMPLE-P02-portfolio-entry.md"])

    def test_the_raci_names_two_new_roles_for_one_process(self):
        _, after, _ = written("raci")
        source = after[f"{PROCESS}/downstream_process_map.json"]
        self.assertIn('"name": "Regional Optimization",\n                "raci": {\n                  "responsible": [\n'
                      '                    "Sample Data Steward"\n                  ],\n', source)
        import json
        json.loads(source)   # the map is still JSON
        self.assertTrue(after[f"{ONT}/organization/role-register.csv"].endswith(
            "Sample Data Steward,sample-data-steward,exact,\nSample Domain Owner,sample-domain-owner,exact,\n"))
        self.assertEqual(after[f"{ONT}/organization/roles.csv"].count("\nsample-"), 2)
        self.assertIn("(154, 917, 93, 62, 56, 6, 11, 944))", after[f"{ONT}/organization/test_roles.py"])
        self.assertIn("| `roles` | 6.1 and P5 | 66 of 67 | 1 | Value Chain Optimization Director |", after["kpi-intake/README.md"])

    def test_the_list_gets_its_table_its_shapes_and_its_question(self):
        _, after, _ = written("domain-list")
        self.assertEqual(after[f"{ONT}/kpi/data-domains.csv"].splitlines()[0], "domain_id,name,definition")
        self.assertIn("kpi:DataDomains a skos:ConceptScheme ;", after[f"{ONT}/kpi/vocabulary.ttl"])
        shapes = after[f"{ONT}/kpi/shapes.ttl"]
        self.assertIn("pop:populationEvidence kpi:dataDomain ) ;", shapes)
        self.assertIn("    sh:targetObjectsOf kpi:dataDomain ;\n    sh:property [ sh:path skos:inScheme ; sh:minCount 1 ; sh:hasValue kpi:DataDomains ] ;", shapes)
        self.assertIn('"kpi/measures.ttl", "kpi/data-domains.ttl",', after[f"{ONT}/release/build_module.py"])
        self.assertIn('"kpi/measures.ttl", "kpi/data-domains.ttl", "population/vocabulary.ttl",', after[f"{ONT}/release/test_build_module.py"])
        self.assertEqual(after["scripts/check.sh"].count("data_domains"), 2)
        self.assertTrue(after[f"{ONT}/regression/expected.csv"].endswith("58,answerable,q58-data-domains.rq,\n"))
        self.assertIn("58. Which data domains does the ontology hold, and what data does each cover?\n", after[f"{ONT}/competency-questions.md"])
        compile(after[f"{ONT}/kpi/build_data_domains.py"], "build_data_domains.py", "exec")
        compile(after[f"{ONT}/kpi/test_data_domains.py"], "test_data_domains.py", "exec")


class Refusal(unittest.TestCase):
    def test_a_copy_that_holds_an_example_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ONT, "approvals"))
            with open(os.path.join(tmp, ONT, "approvals", "example-raci.md"), "w", encoding="utf-8") as f:
                f.write("# Approval\n")
            with self.assertRaisesRegex(ue.Refused, "holds the example raci already; nothing was changed"):
                ue.apply("raci", root=tmp, write=True, say=lambda line: None)


if __name__ == "__main__":
    unittest.main()
