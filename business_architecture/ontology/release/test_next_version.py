"""Tests for next_version.py: the entry it sets, the changelog section, and the move of the old package."""
import argparse
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import next_version as nv  # noqa: E402

BUILDER = '''MODULES = {
    "kpi": {
        "title": "KPI",
        "version": "1.3.0", "stage": None, "approver": "the module owner", "issued": "2026-10-28",
        "approval": ("approvals/old.md", "Approved (as described)"),
        "parts": ["kpi/vocabulary.ttl"],
    },
    "lane": {
        "title": "Lane",
        "version": "1.1.0", "stage": None, "issued": "2026-10-26",
        "approval": ("approvals/lane.md", "Approved"),
    },
}
'''
PIPELINE = 'PACKAGES = [("core", "2.4.0"), ("kpi", "1.3.0"), ("lane", "1.1.0")]\n'
CONFIG = '{"packages": {"core": "2.4.0", "kpi": "1.3.0", "lane": "1.1.0"}}\n'


def tree(tmp, versions):
    """A made-up ontology folder: the builder, the two lists of versions, and one kpi package per version."""
    for path, text in (("release/build_module.py", BUILDER), ("projection/pipeline.py", PIPELINE),
                       ("projection/skill-run/epm-config.json", CONFIG), ("releases/kpi/CHANGELOG.md", "# kpi changelog\n\n## 1.3.0 (2026-10-28)\n\nFirst.\n\n### Known gaps\n\n- One gap.\n")):
        os.makedirs(os.path.dirname(os.path.join(tmp, path)), exist_ok=True)
        with open(os.path.join(tmp, path), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    for version in versions:
        os.makedirs(os.path.join(tmp, "releases", "kpi", version))
        with open(os.path.join(tmp, "releases", "kpi", version, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write("{}")


def read(tmp, path):
    with open(os.path.join(tmp, path), encoding="utf-8") as f:
        return f.read()


class Start(unittest.TestCase):
    def test_start_sets_a_correction_version_and_only_that_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree(tmp, ["1.3.0"])
            nv.start(argparse.Namespace(module="kpi", version="1.3.1-correction.1", kind="patch", date="2026-11-11",
                                        why="A correction.", approver="the ontology owner",
                                        where="discovery-runs/run-1.md", words="Typed yes."), ontology=tmp)
            builder = read(tmp, "release/build_module.py")
            self.assertIn('"version": "1.3.1-correction.1", "stage": None,\n'
                          '        "approver": "the ontology owner", "issued": "2026-11-11",\n'
                          '        "approval": ("discovery-runs/run-1.md", "Typed yes."),\n'
                          '        "parts": ["kpi/vocabulary.ttl"],', builder)
            self.assertIn('"version": "1.1.0", "stage": None, "issued": "2026-10-26",\n        "approval": ("approvals/lane.md", "Approved"),', builder)
            self.assertNotIn("approvals/old.md", builder)
            log = read(tmp, "releases/kpi/CHANGELOG.md")
            self.assertTrue(log.startswith("# kpi changelog\n\n## 1.3.1-correction.1 (2026-11-11)\n\nA patch release. A correction.\n\n"
                                           "- [patch] A correction.\n\n### Known gaps\n\n- One gap.\n\n## 1.3.0 (2026-10-28)"), log)

    def test_a_second_start_replaces_what_the_first_one_wrote(self):
        first = nv.set_entry(BUILDER, "kpi", "1.3.1-correction.1", "2026-11-11", 'the "ontology" owner', "runs/1.md", "Typed yes.")
        second = nv.set_entry(first, "kpi", "1.3.1-correction.2", "2026-11-13", "the module owner", "runs/2.md", "Typed yes again.")
        scope = {}
        exec(second, scope)   # the entry is Python: a key written twice would keep its last, older value
        self.assertEqual({k: scope["MODULES"]["kpi"][k] for k in ("version", "approver", "issued", "approval")},
                         {"version": "1.3.1-correction.2", "approver": "the module owner", "issued": "2026-11-13",
                          "approval": ("runs/2.md", "Typed yes again.")})
        for key in ("approver", "issued", "approval", "version"):
            self.assertEqual(second.split('"lane"')[0].count(f'"{key}":'), 1, key)
        self.assertEqual(scope["MODULES"]["lane"]["issued"], "2026-10-26")

    def test_current_reads_a_correction_version(self):
        text = nv.set_entry(BUILDER, "kpi", "1.3.1-correction.2", "2026-11-12", "a role", "w.md", "words")
        self.assertIn('"version": "1.3.1-correction.2"', text)
        self.assertEqual(text.count('"version"'), 2)


class Finish(unittest.TestCase):
    def finish(self, tmp, old):
        nv.finish(argparse.Namespace(module="kpi", old=old), ontology=tmp)

    def test_finish_moves_the_plain_package_and_names_the_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree(tmp, ["1.3.0", "1.3.1-correction.1"])
            self.finish(tmp, "1.3.0")
            self.assertTrue(os.path.isfile(os.path.join(tmp, "releases", "previous", "kpi", "1.3.0", "manifest.json")))
            self.assertEqual(os.listdir(os.path.join(tmp, "releases", "kpi")).count("1.3.0"), 0)
            self.assertEqual(read(tmp, "projection/pipeline.py"), 'PACKAGES = [("core", "2.4.0"), ("kpi", "1.3.1-correction.1"), ("lane", "1.1.0")]\n')
            self.assertEqual(read(tmp, "projection/skill-run/epm-config.json"),
                             '{"packages": {"core": "2.4.0", "kpi": "1.3.1-correction.1", "lane": "1.1.0"}}\n')

    def test_finish_moves_a_correction_when_a_second_one_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree(tmp, ["1.3.1-correction.1", "1.3.1-correction.2"])
            for path in ("projection/pipeline.py", "projection/skill-run/epm-config.json"):
                text = read(tmp, path).replace("1.3.0", "1.3.1-correction.1")
                with open(os.path.join(tmp, path), "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            self.finish(tmp, "1.3.1-correction.1")
            self.assertTrue(os.path.isdir(os.path.join(tmp, "releases", "previous", "kpi", "1.3.1-correction.1")))
            self.assertIn('("kpi", "1.3.1-correction.2")', read(tmp, "projection/pipeline.py"))

    def test_finish_stops_while_the_old_package_is_still_the_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree(tmp, ["1.3.0", "1.3.1-correction.1"])
            with self.assertRaises(SystemExit) as caught:
                self.finish(tmp, "1.3.1-correction.1")
            self.assertIn("still the newest package", str(caught.exception))
            self.assertEqual(read(tmp, "projection/pipeline.py"), PIPELINE)


class Cascade(unittest.TestCase):
    """The made-up tree: kpi is the changed module, and lane stands for a module that depends on it. A whole package
    here is a folder with a manifest and a file named whole; a folder with only a manifest is what a failed build
    leaves."""

    def package(self, tmp, module, version, whole=True):
        os.makedirs(os.path.join(tmp, "releases", module, version), exist_ok=True)
        for name in ["manifest.json"] + (["whole"] if whole else []):
            with open(os.path.join(tmp, "releases", module, version, name), "w", encoding="utf-8") as f:
                f.write("{}")

    def tree(self, tmp, lane=("1.1.0",)):
        tree(tmp, ["1.3.0", "1.4.0"])          # kpi's new package is written
        self.package(tmp, "kpi", "1.4.0")
        for version in lane:
            self.package(tmp, "lane", version)
        self.built = []

    def run_cascade(self, tmp, **more):
        def build(module):
            self.built.append((module, nv.current_version(module, tmp)))
            self.package(tmp, module, nv.current_version(module, tmp))

        def verify(module):
            newest = nv.packages(module, tmp)[-1]
            if not os.path.isfile(os.path.join(tmp, "releases", module, newest, "whole")):
                raise SystemExit(f"{module} {newest} differs from a fresh build")
        nv.cascade(self.args(), ontology=tmp, order=["kpi", "lane"], **{"build": build, "verify": verify, **more})

    def args(self):
        return argparse.Namespace(module="kpi", date="2026-11-12", why="Takes the new version of what it requires.",
                                  approver="the ontology owner", where="approvals/a.md", words="Approved as a minor.")

    def test_the_next_patch_of_a_plain_version_and_of_a_correction(self):
        self.assertEqual(nv.next_patch("1.2.0"), "1.2.1")
        self.assertEqual(nv.next_patch("1.2.1-correction.2"), "1.2.2")
        with self.assertRaises(SystemExit):
            nv.next_patch("1.2")

    def test_each_dependent_gets_the_next_patch_and_every_module_is_finished(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.tree(tmp)
            self.run_cascade(tmp)
            self.assertEqual(self.built, [("lane", "1.1.1")])
            self.assertEqual(nv.packages("kpi", tmp), ["1.4.0"])
            self.assertEqual(nv.packages("lane", tmp), ["1.1.1"])
            self.assertEqual(sorted(os.listdir(os.path.join(tmp, "releases", "previous"))), ["kpi", "lane"])
            self.assertEqual(read(tmp, "projection/pipeline.py"), 'PACKAGES = [("core", "2.4.0"), ("kpi", "1.4.0"), ("lane", "1.1.1")]\n')
            self.assertIn("## 1.1.1 (2026-11-12)\n\nA patch release. Takes the new version of what it requires.", read(tmp, "releases/lane/CHANGELOG.md"))
            self.assertFalse(os.path.exists(os.path.join(tmp, "release", nv.CASCADE_PLAN)))

    def test_it_stops_before_any_change_when_the_changed_modules_package_is_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree(tmp, ["1.3.0"])
            self.package(tmp, "lane", "1.1.0")
            before = read(tmp, "release/build_module.py")
            with self.assertRaises(SystemExit) as stopped:
                nv.cascade(self.args(), ontology=tmp, order=["kpi", "lane"], build=lambda module: self.fail("built"),
                           verify=lambda module: self.fail("verified"))
            self.assertIn("write kpi's new package first", str(stopped.exception))
            self.assertEqual(read(tmp, "release/build_module.py"), before)
            self.assertFalse(os.path.exists(os.path.join(tmp, "release", nv.CASCADE_PLAN)))

    def test_a_finish_that_fails_halfway_is_taken_up_by_the_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.tree(tmp)
            real = lambda module, old: nv.finish(argparse.Namespace(module=module, old=old), tmp)   # noqa: E731

            def fail_at_lane(module, old):
                if module == "lane":
                    raise SystemExit("the disk is full")
                real(module, old)
            with self.assertRaises(SystemExit):
                self.run_cascade(tmp, finish_one=fail_at_lane)
            # kpi is finished and holds one package again; lane is written and not finished.
            self.assertEqual((nv.packages("kpi", tmp), nv.packages("lane", tmp)), (["1.4.0"], ["1.1.0", "1.1.1"]))
            self.built = []
            self.run_cascade(tmp)
            self.assertEqual(self.built, [])      # nothing is built or started a second time
            self.assertEqual((nv.packages("kpi", tmp), nv.packages("lane", tmp)), (["1.4.0"], ["1.1.1"]))
            self.assertEqual(nv.current_version("lane", tmp), "1.1.1")
            self.assertFalse(os.path.exists(os.path.join(tmp, "release", nv.CASCADE_PLAN)))

    def test_a_folder_that_a_failed_build_left_is_not_taken_for_a_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.tree(tmp)
            self.package(tmp, "lane", "1.1.1", whole=False)     # only a manifest
            with open(os.path.join(tmp, "release", nv.CASCADE_PLAN), "w", encoding="utf-8") as f:
                f.write('{"module": "kpi", "versions": {"kpi": ["1.3.0", "1.4.0"], "lane": ["1.1.0", "1.1.1"]}}')
            with self.assertRaises(SystemExit) as stopped:
                self.run_cascade(tmp)
            self.assertIn("releases/lane/1.1.1 is not a whole package", str(stopped.exception))
            self.assertIn("Delete that folder, then run cascade again", str(stopped.exception))
            # Nothing was finished: both modules still hold their old package.
            self.assertEqual((nv.packages("kpi", tmp), nv.packages("lane", tmp)), (["1.3.0", "1.4.0"], ["1.1.0", "1.1.1"]))
            # With the folder deleted, the next run builds the package and ends.
            import shutil
            shutil.rmtree(os.path.join(tmp, "releases", "lane", "1.1.1"))
            self.run_cascade(tmp)
            self.assertEqual(self.built, [("lane", "1.1.1")])
            self.assertEqual((nv.packages("kpi", tmp), nv.packages("lane", tmp)), (["1.4.0"], ["1.1.1"]))


class Exceptions(unittest.TestCase):
    def test_finish_moves_a_packages_stand_alone_exceptions_with_it_and_gives_the_new_package_its_own(self):
        with tempfile.TemporaryDirectory() as top:
            tmp = os.path.join(top, "business_architecture", "ontology")
            tree(tmp, ["1.3.0", "1.3.1"])
            for version, text in (("1.3.0", "Holds the kept text.\n"), ("1.3.1", "A patch.\n\nHolds the kept text.\n")):
                with open(os.path.join(tmp, "releases", "kpi", version, "CHANGELOG.md"), "w", encoding="utf-8") as f:
                    f.write(text)
            os.makedirs(os.path.join(top, "scripts"))
            listed = os.path.join(top, "scripts", "standalone-exceptions.txt")
            kept = "business_architecture/ontology/releases/lane/1.1.0/CHANGELOG.md :: other-release :: kept text :: 1 :: why"
            with open(listed, "w", encoding="utf-8") as f:
                f.write("# why\n" + kept + "\n"
                        "business_architecture/ontology/releases/kpi/1.3.0/CHANGELOG.md :: other-release :: kept text :: 1 :: why\n"
                        "business_architecture/ontology/releases/kpi/1.3.0/kpi.ttl :: other-release :: gone text :: 2 :: why\n")
            nv.finish(argparse.Namespace(module="kpi", old="1.3.0"), ontology=tmp)
            with open(listed, encoding="utf-8") as f:
                self.assertEqual(f.read().splitlines(), [
                    "# why", kept,
                    "business_architecture/ontology/releases/previous/kpi/1.3.0/CHANGELOG.md :: other-release :: kept text :: 1 :: why",
                    "business_architecture/ontology/releases/kpi/1.3.1/CHANGELOG.md :: other-release :: kept text :: 1 :: why",
                    # The new package does not hold this text, so it gets no line of its own.
                    "business_architecture/ontology/releases/previous/kpi/1.3.0/kpi.ttl :: other-release :: gone text :: 2 :: why"])


if __name__ == "__main__":
    unittest.main()
