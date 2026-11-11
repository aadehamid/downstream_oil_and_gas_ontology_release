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
        with open(os.path.join(tmp, path), "w", encoding="utf-8") as f:
            f.write(text)
    for version in versions:
        os.makedirs(os.path.join(tmp, "releases", "kpi", version))
        with open(os.path.join(tmp, "releases", "kpi", version, "manifest.json"), "w", encoding="utf-8") as f:
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
                with open(os.path.join(tmp, path), "w", encoding="utf-8") as f:
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


if __name__ == "__main__":
    unittest.main()
