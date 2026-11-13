"""Tests for update_examples.py: the files each worked example changes, what it writes there, and its refusals.

The lists of files below are written by hand. HOW-TO-UPDATE.md follows each example to its end, the full check,
in the document test's slow context.

Each example changes the exact text of KPI Store 1.1 as shipped, so its tests need the module it changes at the
version of that release (BASELINE). On a tree where that module has another version, the example's tests are
skipped, and the skip names both versions. That is right after a release of the module, and after the example was
followed. test_each_example_fits_this_release_or_its_module_has_moved_on says when a skip or a pass would hide a
problem: a module still at its shipped version whose example no longer fits the tree. The tests of the refusals
build their own small trees and run on every release.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import next_version  # noqa: E402
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
# The module each example changes, at the version KPI Store 1.1 shipped. Written by hand.
BASELINE = {"deprecate-role": ("organization", "2.2.0"), "system-kind": ("system", "1.5.0"), "move-entry": ("data-product", "1.2.0"),
            "raci": ("organization", "2.2.0"), "domain-list": ("kpi", "1.3.0")}


# One file of each example whose text the example replaces. Written by hand.
MOVED = {"deprecate-role": f"{ONT}/organization/roles.csv", "system-kind": f"{ONT}/system/vocabulary.ttl",
         "move-entry": f"{PROCESS}/data_product_portfolio.json", "raci": f"{PROCESS}/downstream_process_map.json",
         "domain-list": f"{ONT}/kpi/shapes.ttl"}


def moved_on(name, held):
    """Why an example's tests do not apply to a tree, or "" when they do. `held` gives each module's version."""
    module, shipped = BASELINE[name]
    return "" if held[module] == shipped else (f"this tree holds {module} {held[module]}, and the example {name} changes "
                                                f"{module} {shipped}, the version of KPI Store 1.1 as shipped")


HELD = {module: next_version.current_version(module) for module, _ in BASELINE.values()}
SKIP = {name: moved_on(name, HELD) for name in BASELINE}


def as_shipped(name):
    return unittest.skipIf(SKIP[name], SKIP[name])


def question_number():
    """The number the domain-list example gives its question on this tree: one after the last question."""
    with open(os.path.join(ue.ROOT, ONT, "regression", "expected.csv"), encoding="utf-8") as f:
        return max(int(line.split(",", 1)[0]) for line in f.read().splitlines()[1:] if line.strip()) + 1


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


class Rules(unittest.TestCase):
    """What decides whether an example's tests run, tested with made-up versions, and the guard on that rule."""

    def test_the_five_examples(self):
        self.assertEqual(sorted(ue.EXAMPLES), ["deprecate-role", "domain-list", "move-entry", "raci", "system-kind"])
        self.assertEqual(sorted(CHANGED), sorted(ue.EXAMPLES))
        self.assertEqual(sorted(BASELINE), sorted(ue.EXAMPLES))

    def test_an_example_is_skipped_only_when_its_own_module_has_moved_on(self):
        shipped = {"organization": "2.2.0", "system": "1.5.0", "data-product": "1.2.0", "kpi": "1.3.0"}
        self.assertEqual({name: moved_on(name, shipped) for name in BASELINE}, dict.fromkeys(BASELINE, ""))
        after = dict(shipped, organization="3.0.0")
        self.assertEqual(sorted(name for name in BASELINE if moved_on(name, after)), ["deprecate-role", "raci"])
        self.assertEqual(moved_on("raci", after), "this tree holds organization 3.0.0, and the example raci changes organization "
                                                  "2.2.0, the version of KPI Store 1.1 as shipped")
        self.assertEqual(moved_on("system-kind", after), "")

    def test_each_example_fits_this_release_or_its_module_has_moved_on(self):
        """A skipped example is right when its module has a new version. An example whose module is still at the
        shipped version must fit the tree: if a file it changes has moved, its tests would fail or, worse, the
        guide's example would stop for a reader. This test says which."""
        for name in ue.EXAMPLES:
            if SKIP[name]:
                continue
            with self.subTest(name):
                try:
                    ue.apply(name, date="2026-11-12", say=lambda line: None)   # a plan: it writes nothing
                except ue.Refused as err:
                    module, shipped = BASELINE[name]
                    self.fail(f"{module} is still at {shipped}, and the example {name} does not fit this tree: {err}. Bring "
                              "update_examples.py and the guide's example up to date. In a copy that has moved on from the "
                              "release for good, add this test and the tests of that example to scripts/pinned-tests.txt.")


class Example:
    """The tests every example passes. One class below per example, skipped with its reason when its module has
    moved on."""
    name = None

    def test_a_plan_names_each_file_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_of(self.name, tmp)
            before, said = files(tmp), []
            done = ue.apply(self.name, root=tmp, date="2026-11-12", say=said.append)
            self.assertEqual(said, [f"would change {place}" for place in done])
            self.assertEqual(len(done), len(ue.EXAMPLES[self.name]["places"]))
            self.assertEqual(files(tmp), before)

    def test_write_changes_these_files_and_adds_these(self):
        before, after, said = written(self.name)
        added = [path.replace("q58-", f"q{question_number()}-") for path in ADDED[self.name]]
        self.assertEqual(sorted(set(after) - set(before)), sorted(added + [f"{ONT}/approvals/example-{self.name}.md"]))
        self.assertEqual(sorted(p for p in before if before[p].decode("utf-8") != after[p]), sorted(CHANGED[self.name]))
        self.assertTrue(all(line.startswith("changed ") for line in said))

    def test_a_second_run_is_refused_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_of(self.name, tmp)
            ue.apply(self.name, root=tmp, date="2026-11-12", write=True, say=lambda line: None)
            before = files(tmp)
            with self.assertRaisesRegex(ue.Refused, f"holds the example {self.name} already"):
                ue.apply(self.name, root=tmp, date="2026-11-12", write=True, say=lambda line: None)
            self.assertEqual(files(tmp), before)

    def test_a_file_that_has_moved_on_stops_plan_and_write_with_nothing_changed(self):
        # A file the example changes loses the text the example looks for, as after a real update.
        first = MOVED[self.name]
        for write in (False, True):
            with self.subTest(write=write), tempfile.TemporaryDirectory() as tmp:
                copy_of(self.name, tmp)
                with open(os.path.join(tmp, first), "w", encoding="utf-8", newline="") as f:
                    f.write("this file has moved on\n")
                before = files(tmp)
                with self.assertRaisesRegex(ue.Refused, "does not hold the text this example changes.*KPI Store 1.1 as shipped.*Nothing was changed"):
                    ue.apply(self.name, root=tmp, date="2026-11-12", write=write, say=lambda line: None)
                self.assertEqual(files(tmp), before)


@as_shipped("deprecate-role")
class DeprecateRole(Example, unittest.TestCase):
    name = "deprecate-role"

    def test_the_role_is_deprecated_into_its_successor(self):
        _, after, _ = written("deprecate-role")
        row = next(line for line in after[f"{ONT}/organization/roles.csv"].splitlines() if line.startswith("black-oil-manager,"))
        self.assertTrue(row.startswith('black-oil-manager,Black Oil Manager,,position,asphalt-manager,alt,,"Deprecated: a made-up answer'))
        self.assertIn('"black-oil-manager": "asphalt-manager",', after[f"{ONT}/organization/test_roles.py"])
        self.assertIn("(4, 56))", after[f"{ONT}/organization/test_roles.py"])
        self.assertTrue(after["scripts/pinned-tests.txt"].endswith(
            "kpi_store/tests/test_cut.py::test_the_baseline_is_this_trees_or_data_product_has_moved_on\n"))


@as_shipped("system-kind")
class SystemKind(Example, unittest.TestCase):
    name = "system-kind"

    def test_the_system_takes_a_fourth_kind(self):
        _, after, _ = written("system-kind")
        self.assertIn("databricks,Databricks,,data-platform,", after[f"{ONT}/system/other-systems.csv"])
        self.assertIn('kind:data-platform a skos:Concept ; skos:inScheme sys:SystemKind ;', after[f"{ONT}/system/vocabulary.ttl"])
        self.assertIn("kind:document, kind:data-platform ;", after[f"{ONT}/system/vocabulary.ttl"])
        self.assertIn("sh:in ( kind:application kind:office-tool kind:document kind:data-platform ) ]", after[f"{ONT}/system/shapes.ttl"])
        self.assertIn('KINDS = ("application", "office-tool", "document", "data-platform")', after[f"{ONT}/system/build_systems.py"])


@as_shipped("move-entry")
class MoveEntry(Example, unittest.TestCase):
    name = "move-entry"

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


@as_shipped("raci")
class Raci(Example, unittest.TestCase):
    name = "raci"

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


@as_shipped("domain-list")
class DomainList(Example, unittest.TestCase):
    name = "domain-list"

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
        number = question_number()
        self.assertTrue(after[f"{ONT}/regression/expected.csv"].endswith(f"{number},answerable,q{number}-data-domains.rq,\n"))
        self.assertIn(f"{number}. Which data domains does the ontology hold, and what data does each cover?\n", after[f"{ONT}/competency-questions.md"])
        self.assertIn(f"competency question {number}\"@en", after[f"{ONT}/kpi/vocabulary.ttl"])
        self.assertTrue(after[f"{ONT}/regression/queries/q{number}-data-domains.rq"].startswith(f"# Q{number} Which data domains"))
        compile(after[f"{ONT}/kpi/build_data_domains.py"], "build_data_domains.py", "exec")
        compile(after[f"{ONT}/kpi/test_data_domains.py"], "test_data_domains.py", "exec")


def made_up_tree(tmp):
    """A small tree that holds the two files of the deprecate-role example's first steps, with the text they change."""
    texts = {f"{ONT}/organization/roles.csv": "slug,label\nblack-oil-manager,Black Oil Manager,,position,,,,,\n",
             f"{ONT}/organization/test_roles.py": '(f["deprecated roles"], f["live roles"]), (3, 57))\n        self.assertEqual(replaced, {\n',
             "scripts/pinned-tests.txt": "# pinned\n"}
    for path, text in texts.items():
        os.makedirs(os.path.dirname(os.path.join(tmp, path)), exist_ok=True)
        with open(os.path.join(tmp, path), "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return texts


def link(target, at, directory=False):
    try:
        os.symlink(target, at, target_is_directory=directory)
    except (OSError, NotImplementedError):
        raise unittest.SkipTest("this system does not let the test make a link")


class Refusals(unittest.TestCase):
    """These build their own trees, so they run on every release."""

    def test_the_made_up_tree_takes_the_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            made_up_tree(tmp)
            ue.apply("deprecate-role", root=tmp, date="2026-11-12", write=True, say=lambda line: None)
            self.assertIn("asphalt-manager,alt", files(tmp)[f"{ONT}/organization/roles.csv"].decode("utf-8"))

    def test_a_copy_that_holds_an_example_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ONT, "approvals"))
            with open(os.path.join(tmp, ONT, "approvals", "example-raci.md"), "w", encoding="utf-8") as f:
                f.write("# Approval\n")
            with self.assertRaisesRegex(ue.Refused, "holds the example raci already; nothing was changed"):
                ue.apply("raci", root=tmp, write=True, say=lambda line: None)

    def test_a_missing_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:   # an empty folder holds none of the files
            with self.assertRaisesRegex(ue.Refused, "roles.csv is missing"):
                ue.apply("deprecate-role", root=tmp, date="2026-11-12", say=lambda line: None)

    def test_a_file_whose_text_has_moved_on_is_refused_in_plain_words(self):
        for write in (False, True):
            with self.subTest(write=write), tempfile.TemporaryDirectory() as tmp:
                made_up_tree(tmp)
                with open(os.path.join(tmp, ONT, "organization", "test_roles.py"), "w", encoding="utf-8") as f:
                    f.write("(4, 56)\n")
                before = files(tmp)
                with self.assertRaises(ue.Refused) as refused:
                    ue.apply("deprecate-role", root=tmp, date="2026-11-12", write=write, say=lambda line: None)
                self.assertTrue(str(refused.exception).startswith(
                    f"{ONT}/organization/test_roles.py does not hold the text this example changes, or holds it more than once. "
                    "The example is made for KPI Store 1.1 as shipped, and this file has changed since. Nothing was changed."))
                self.assertEqual(files(tmp), before)

    def test_the_line_for_the_cut_tests_is_written_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            made_up_tree(tmp)
            line = "kpi_store/tests/test_cut.py::test_the_baseline_is_this_trees_or_data_product_has_moved_on\n"
            with open(os.path.join(tmp, "scripts", "pinned-tests.txt"), "a", encoding="utf-8") as f:
                f.write(line)
            ue.apply("deprecate-role", root=tmp, date="2026-11-12", write=True, say=lambda line: None)
            self.assertEqual(files(tmp)["scripts/pinned-tests.txt"].decode("utf-8").count(line), 1)

    def test_a_file_that_is_a_link_is_refused_and_its_target_is_unchanged(self):
        for write in (False, True):
            with self.subTest(write=write), tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
                texts = made_up_tree(tmp)
                target = os.path.join(outside, "roles.csv")
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(texts[f"{ONT}/organization/roles.csv"])
                inside = os.path.join(tmp, ONT, "organization", "roles.csv")
                os.remove(inside)
                link(target, inside)
                with self.assertRaisesRegex(ue.Refused, "organization/roles.csv is a link"):
                    ue.apply("deprecate-role", root=tmp, date="2026-11-12", write=write, say=lambda line: None)
                with open(target, encoding="utf-8", newline="") as f:
                    self.assertEqual(f.read(), texts[f"{ONT}/organization/roles.csv"])
                self.assertFalse(os.path.exists(os.path.join(tmp, ONT, "approvals")))

    def test_a_folder_that_is_a_link_is_refused_and_nothing_is_written_through_it(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            made_up_tree(tmp)
            folder = os.path.join(tmp, ONT, "organization")
            shutil.copytree(folder, os.path.join(outside, "organization"))
            shutil.rmtree(folder)
            link(os.path.join(outside, "organization"), folder, directory=True)
            before = files(outside)
            with self.assertRaisesRegex(ue.Refused, f"{ONT}/organization is a link"):
                ue.apply("deprecate-role", root=tmp, date="2026-11-12", write=True, say=lambda line: None)
            self.assertEqual(files(outside), before)

    def test_a_new_file_is_not_written_through_a_linked_folder(self):
        # The approval is a new file. Its folder is a link to a place outside the copy.
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            made_up_tree(tmp)
            link(outside, os.path.join(tmp, ONT, "approvals"), directory=True)
            before = files(tmp)
            with self.assertRaisesRegex(ue.Refused, f"{ONT}/approvals is a link"):
                ue.apply("deprecate-role", root=tmp, date="2026-11-12", write=True, say=lambda line: None)
            self.assertEqual(os.listdir(outside), [])
            self.assertEqual({p: d for p, d in files(tmp).items() if "approvals" not in p}, {p: d for p, d in before.items() if "approvals" not in p})


if __name__ == "__main__":
    unittest.main()
