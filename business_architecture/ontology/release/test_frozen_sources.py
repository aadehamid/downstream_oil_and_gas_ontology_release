"""Frozen sources: the core builders read the process map from frozen files, and a released package is found in
releases/ or in the history folder releases/previous/."""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_module as bm  # noqa: E402
import frozen_sources as fs  # noqa: E402


class Frozen(unittest.TestCase):
    def test_the_frozen_file_is_read(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fs, "FROZEN", tmp):
            self.assertFalse(fs.is_frozen("abc123def456", "x/map.json"))
            with open(fs.frozen_path("abc123def456", "x/map.json"), "wb") as f:
                f.write(b'{"frozen": true}')
            self.assertTrue(fs.is_frozen("abc123def456", "x/map.json"))
            self.assertEqual(fs.read("abc123def456", "x/map.json"), b'{"frozen": true}')

    def test_without_a_frozen_file_the_read_fails_and_names_the_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fs, "FROZEN", tmp):
            with self.assertRaises(FileNotFoundError) as raised:
                fs.read("abc123def4567890", "x/map.json")
            self.assertIn("abc123def456-map.json", str(raised.exception))

    def test_a_package_is_found_in_the_history_folder_when_releases_lacks_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = os.path.join(tmp, "releases", "core", "2.3.0")
            previous = os.path.join(tmp, "releases", "previous", "core", "2.3.0")
            with mock.patch.object(bm, "ONTOLOGY", tmp):
                self.assertEqual(fs.package_dir(tmp, "core", "2.3.0"), plain)  # neither folder: the plain path
                self.assertIsNone(bm.package_folder("core", "2.3.0"))
                with self.assertRaises(FileNotFoundError):
                    bm.released_requires("core", "2.3.0")
                os.makedirs(previous)
                with open(os.path.join(previous, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
                    f.write("{}\n")
                self.assertEqual(fs.package_dir(tmp, "core", "2.3.0"), previous)
                self.assertEqual(bm.package_folder("core", "2.3.0"), previous)
                self.assertEqual(bm.released_requires("core", "2.3.0"), {})
                os.makedirs(plain)
                with open(os.path.join(plain, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
                    f.write('{"depends_on": {"x": "1.0.0"}}\n')
                self.assertEqual(fs.package_dir(tmp, "core", "2.3.0"), plain)  # releases/ wins when both hold it
                self.assertEqual(bm.package_folder("core", "2.3.0"), plain)

    def test_the_frozen_maps_are_the_four_the_core_builders_name(self):
        pins = fs.pinned()
        self.assertEqual([c[:8] for c, _ in pins], ["b75fd991", "82593547", "c351ef0e", "4906666a"])
        self.assertTrue(all(p == "business_architecture/business_process/downstream_process_map.json" for _, p in pins))
        for commit, path in pins:
            self.assertTrue(fs.is_frozen(commit, path), commit)
            self.assertTrue(fs.read(commit, path).lstrip().startswith(b"["))


class NewestSet(unittest.TestCase):
    def test_every_module_is_built_against_the_newest_set(self):
        self.assertEqual(bm.newest_on_disk("core"), "2.4.0")
        self.assertEqual(bm.dependencies("kpi")["core"], "2.4.0")
        self.assertEqual(bm.dependencies("ref-mpc"), {"organization": "2.2.0", "party": "2.1.0"})
        self.assertEqual(bm.dependencies("technical-graph"), {"data-product": "1.2.0", "kpi": "1.3.0", "system": "1.5.0"})

    def test_a_shape_path_names_the_modules_newest_package(self):
        self.assertEqual(bm.resolve("releases/organization/2.1.0/shapes.ttl"), "releases/organization/2.2.0/shapes.ttl")
        self.assertEqual(bm.resolve("ref-mpc/shapes.ttl"), "ref-mpc/shapes.ttl")


if __name__ == "__main__":
    unittest.main()
