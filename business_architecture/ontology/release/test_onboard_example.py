"""Tests for onboard_example.py: the places it registers the made-up module in, and its refusals.

The list of places below is written by hand. HOW-TO-UPDATE.md, "Onboard another module", walks through the whole
example and ends with the full check, in the document test's slow context.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import onboard_example as oe  # noqa: E402

ONT = "business_architecture/ontology"
PLACES = [f"{ONT}/sample-area/", f"{ONT}/approvals/sample-area-1.0.0.md", f"{ONT}/release/build_module.py",
          f"{ONT}/releases/sample-area/CHANGELOG.md", "scripts/check.sh", f"{ONT}/projection/pipeline.py",
          f"{ONT}/projection/skill-run/epm-config.json", f"{ONT}/regression/", f"{ONT}/validation/test_all_module_shapes.py",
          f"{ONT}/competency-questions.md", f"{ONT}/MODULES.md", "scripts/build_docs_html.py"]
# The files of this release that the example changes. A copy of them is all the tests below need.
CHANGED = [f"{ONT}/release/build_module.py", "scripts/check.sh", f"{ONT}/projection/pipeline.py",
           f"{ONT}/projection/skill-run/epm-config.json", f"{ONT}/regression/expected.csv", f"{ONT}/regression/run.py",
           f"{ONT}/validation/test_all_module_shapes.py", f"{ONT}/competency-questions.md", f"{ONT}/MODULES.md",
           "scripts/build_docs_html.py"]
HAS_MODULE = os.path.exists(os.path.join(oe.ROOT, ONT, "sample-area"))
# The number the example's question takes: one after the highest, which is 58 in the release as shipped and higher
# after the new-module form has added a module.
with open(os.path.join(oe.ROOT, ONT, "regression", "expected.csv"), encoding="utf-8") as _f:
    N = max(int(line.split(",", 1)[0]) for line in _f.read().splitlines()[1:] if line) + 1


def copy_of_the_places(tmp):
    for path in CHANGED:
        os.makedirs(os.path.dirname(os.path.join(tmp, path)), exist_ok=True)
        shutil.copyfile(os.path.join(oe.ROOT, path), os.path.join(tmp, path))


def files(tmp):
    found = {}
    for folder, _, names in os.walk(tmp):
        for name in names:
            with open(os.path.join(folder, name), "rb") as f:
                found[os.path.relpath(os.path.join(folder, name), tmp).replace(os.sep, "/")] = f.read()
    return found


@unittest.skipIf(HAS_MODULE, "this copy holds the sample-area module already: the example was followed here")
class Onboard(unittest.TestCase):
    def test_the_plan_lists_every_place_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_of_the_places(tmp)
            before, said = files(tmp), []
            self.assertEqual(oe.onboard(root=tmp, date="2026-11-12", say=said.append), PLACES)
            self.assertEqual(said, [f"would register in {place}" for place in PLACES])
            self.assertEqual(files(tmp), before)

    def test_write_adds_the_module_to_each_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_of_the_places(tmp)
            before = files(tmp)
            oe.onboard(root=tmp, date="2026-11-12", write=True, say=lambda line: None)
            after = files(tmp)
            self.assertEqual(sorted(set(after) - set(before)), sorted(
                [f"{ONT}/sample-area/{name}" for name in ("README.md", "vocabulary.ttl", "shapes.ttl", "sample-areas.csv",
                                                           "build_sample_areas.py", "test_sample_areas.py")]
                + [f"{ONT}/approvals/sample-area-1.0.0.md", f"{ONT}/releases/sample-area/CHANGELOG.md",
                   f"{ONT}/regression/queries/q{N}-sample-area-processes.rq"]))
            self.assertEqual(sorted(p for p in before if before[p] != after[p]), sorted(CHANGED))
            text = {p: after[p].decode("utf-8") for p in CHANGED}
            self.assertRegex(text[f"{ONT}/projection/pipeline.py"], r'\("lane", "[^"]+"\), \("sample-area", "1\.0\.0"\),')
            self.assertIn('"system", "lane", "sample-area", "market-data"', text[f"{ONT}/projection/pipeline.py"])
            self.assertIn('    "sa": "https://w3id.org/mpc/ontology/modules/sample-area/",\n', text[f"{ONT}/projection/pipeline.py"])
            self.assertEqual(text[f"{ONT}/projection/skill-run/epm-config.json"].count("sample-area"), 3)
            self.assertIn('        "version": "1.0.0", "stage": None, "approver": "the ontology owner", "issued": "2026-11-12",\n',
                          text[f"{ONT}/release/build_module.py"])
            self.assertEqual(text["scripts/check.sh"].count("sample-area"), 3)
            self.assertTrue(text[f"{ONT}/regression/expected.csv"].endswith(f"{N},answerable,q{N}-sample-area-processes.rq,\n"))
            self.assertIn(f"{N}. Which processes does each sample area cover?\n", text[f"{ONT}/competency-questions.md"])
            self.assertIn('MODULE_READMES = ["kpi", "lane", "sample-area",', text["scripts/build_docs_html.py"])
            self.assertIn("<!-- module: sample-area -->", text[f"{ONT}/MODULES.md"])

    def test_a_release_that_holds_the_module_is_refused_and_nothing_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_of_the_places(tmp)
            os.makedirs(os.path.join(tmp, ONT, "sample-area"))
            before = files(tmp)
            with self.assertRaises(oe.Refused) as refused:
                oe.onboard(root=tmp, write=True, say=lambda line: None)
            self.assertIn("holds the module sample-area already", str(refused.exception))
            self.assertEqual(files(tmp), before)

    def test_a_place_that_is_not_as_expected_stops_the_run_before_any_file_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_of_the_places(tmp)
            path = os.path.join(tmp, "scripts", "build_docs_html.py")   # the last place the run reaches
            with open(path, encoding="utf-8") as f:
                moved = f.read().replace('MODULE_READMES = ["kpi", "lane",', 'MODULE_READMES = ["lane", "kpi",')
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(moved)
            before = files(tmp)
            with self.assertRaises(oe.Refused):
                oe.onboard(root=tmp, write=True, say=lambda line: None)
            self.assertEqual(files(tmp), before)


class Links(unittest.TestCase):
    """The helper changes only real files inside the copy. These build their own trees and run on every release."""

    def link(self, target, at, directory=False):
        try:
            os.symlink(target, at, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("this system does not let the test make a link")

    def test_a_file_that_is_a_link_is_not_read_and_not_written(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            target = os.path.join(outside, "check.sh")
            with open(target, "w", encoding="utf-8") as f:
                f.write("outside\n")
            os.makedirs(os.path.join(tmp, "scripts"))
            self.link(target, os.path.join(tmp, "scripts", "check.sh"))
            tree = oe.Tree(tmp)
            with self.assertRaisesRegex(oe.Refused, "scripts/check.sh is a link"):
                tree.read("scripts/check.sh")
            tree.texts["scripts/check.sh"] = "changed\n"    # as if the link was put there after the read
            with self.assertRaisesRegex(oe.Refused, "scripts/check.sh is a link"):
                tree.save()
            with open(target, encoding="utf-8") as f:
                self.assertEqual(f.read(), "outside\n")

    def test_a_file_with_a_second_name_outside_the_copy_is_not_written(self):
        # A hard link is no symbolic link and resolves inside the copy, yet a write through it changes the other name.
        with tempfile.TemporaryDirectory() as tmp:
            root, outside = os.path.join(tmp, "copy"), os.path.join(tmp, "outside.txt")
            os.makedirs(root)
            with open(outside, "w", encoding="utf-8") as f:
                f.write("kept")
            try:
                os.link(outside, os.path.join(root, "a.txt"))
            except OSError:
                self.skipTest("this file system makes no hard links")
            tree = oe.Tree(root)
            with self.assertRaises(oe.Refused) as refused:
                tree.read("a.txt")
            self.assertIn("hard link", str(refused.exception))
            with open(outside, encoding="utf-8") as f:
                self.assertEqual(f.read(), "kept")

    def test_a_folder_that_is_a_link_is_not_written_through(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            self.link(outside, os.path.join(tmp, "scripts"), directory=True)
            tree = oe.Tree(tmp)
            with self.assertRaisesRegex(oe.Refused, "scripts is a link"):
                tree.new("scripts/new.txt", "text\n")
            tree.texts["scripts/new.txt"] = "text\n"
            tree.texts["real.txt"] = "text\n"
            with self.assertRaisesRegex(oe.Refused, "scripts is a link"):
                tree.save()
            self.assertEqual(os.listdir(outside), [])
            self.assertFalse(os.path.exists(os.path.join(tmp, "real.txt")))   # checked before the first write

    def test_a_path_that_leaves_the_copy_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "copy"))
            with open(os.path.join(tmp, "beside.txt"), "w", encoding="utf-8") as f:
                f.write("beside\n")
            with self.assertRaisesRegex(oe.Refused, "is not inside the copy"):
                oe.Tree(os.path.join(tmp, "copy")).read("../beside.txt")

    def test_a_copy_reached_through_a_link_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "real"))
            self.link(os.path.join(tmp, "real"), os.path.join(tmp, "by-link"), directory=True)
            tree = oe.Tree(os.path.join(tmp, "by-link"))
            tree.new("a/b.txt", "text\n")
            tree.save()
            with open(os.path.join(tmp, "real", "a", "b.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "text\n")


class Command(unittest.TestCase):
    @unittest.skipUnless(HAS_MODULE, "only a copy that holds the module can show the command's refusal")
    def test_the_command_exits_1_on_a_copy_that_holds_the_module(self):
        self.assertEqual(oe.main(["--write"]), 1)

    def test_the_command_needs_plan_or_write(self):
        with self.assertRaises(SystemExit):
            oe.main([])


if __name__ == "__main__":
    unittest.main()
