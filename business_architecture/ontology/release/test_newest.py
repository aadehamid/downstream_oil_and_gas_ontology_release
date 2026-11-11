"""Tests for newest.py: the newest version on disk, and the refusal to overwrite a released package."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import newest  # noqa: E402


def package(ontology, module, version, files=None):
    folder = os.path.join(ontology, "releases", module, version)
    os.makedirs(folder)
    for name, text in {"manifest.json": "{}", **(files or {})}.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return folder


class Newest(unittest.TestCase):
    def test_by_number_not_by_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            package(tmp, "kpi", "1.9.0")
            package(tmp, "kpi", "1.10.0")
            self.assertEqual(newest.newest_version("kpi", tmp), "1.10.0")

    def test_a_folder_without_a_manifest_is_not_a_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            package(tmp, "kpi", "1.0.0")
            os.makedirs(os.path.join(tmp, "releases", "kpi", "2.0.0"))
            self.assertEqual(newest.newest_version("kpi", tmp), "1.0.0")

    def test_no_package_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "releases", "kpi"))
            with self.assertRaises(FileNotFoundError):
                newest.newest_version("kpi", tmp)

    def test_a_correction_version_is_newer_than_what_it_corrects_and_older_than_the_next_patch(self):
        # The order, written by hand. It is not SemVer's, where 1.2.1-correction.1 would sort before 1.2.1.
        order = ["1.2.0", "1.2.1", "1.2.1-correction.1", "1.2.1-correction.2", "1.2.1-correction.10", "1.2.2", "1.10.0", "2.0.0"]
        self.assertEqual(sorted(reversed(order), key=newest.version_key), order)
        self.assertEqual(newest.version_key("1.2.1-correction.1"), (1, 2, 1, 1))
        self.assertEqual(newest.version_key("1.2.1"), (1, 2, 1, 0))
        for name in ("previous", "1.2", "1.2.1-rc.1", "1.2.1-correction", "1.2.1-correction.x", "v1.2.1", "1.2.1-correction.1.bak", "",
                     "1.2.1\n", "1.2.1\r\n", " 1.2.1", "1.2.1-correction.1\n"):
            self.assertIsNone(newest.version_key(name), name)

    def test_two_spellings_never_get_one_place_in_the_order(self):
        # Each of these would tie with a plain version: correction 0 with 1.2.0, a leading zero with the same number
        # without it, and digits of another script with the ASCII ones.
        for name in ("1.2.0-correction.0", "1.2.0-correction.01", "01.2.0", "1.02.0", "1.2.00", "1.2.\u0663", "\u0661.2.0",
                     "1.2.0-correction.\u0661"):
            self.assertIsNone(newest.version_key(name), name)
        for name, key in (("0.1.0", (0, 1, 0, 0)), ("10.20.30", (10, 20, 30, 0)), ("1.0.0-correction.10", (1, 0, 0, 10))):
            self.assertEqual(newest.version_key(name), key)
        with self.assertRaisesRegex(ValueError, "is not a version"):
            newest.correction_version("1.2.0-correction.0")

    def test_the_newest_folder_may_be_a_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("1.2.0", "1.2.1-correction.1", "1.2.1-correction.2"):
                package(tmp, "data-product", version)
            os.makedirs(os.path.join(tmp, "releases", "data-product", "1.2.1-correction.3"))  # no manifest: not a package
            os.makedirs(os.path.join(tmp, "releases", "data-product", "1.9.0-draft"))
            self.assertEqual(newest.newest_version("data-product", tmp), "1.2.1-correction.2")
            package(tmp, "data-product", "1.2.2")
            self.assertEqual(newest.newest_version("data-product", tmp), "1.2.2")

    def test_a_correction_takes_the_next_patch_number_and_a_second_one_counts_up(self):
        self.assertEqual(newest.correction_version("1.2.0"), "1.2.1-correction.1")
        self.assertEqual(newest.correction_version("1.2.1-correction.1"), "1.2.1-correction.2")
        self.assertEqual(newest.correction_version("1.2.1-correction.9"), "1.2.1-correction.10")
        self.assertEqual(newest.correction_version("2.5.9"), "2.5.10-correction.1")
        for text in ("1.2", "1.2.0-rc.1", "latest"):
            with self.assertRaises(ValueError):
                newest.correction_version(text)

    def test_the_pattern_finds_a_version_inside_a_text(self):
        import re
        found = re.findall(rf"^## ({newest.VERSION_PATTERN})", "## 1.2.1-correction.1 (2026-11-11)\n\n## 1.2.0 (2026-10-25)\n", re.M)
        self.assertEqual(found, ["1.2.1-correction.1", "1.2.0"])

    def test_core_file_follows_a_new_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            package(tmp, "core", "2.4.0")
            self.assertTrue(newest.core_file(ontology=tmp).endswith(os.path.join("core", "2.4.0", "core.ttl")))
            package(tmp, "core", "2.5.0")
            self.assertTrue(newest.core_file(ontology=tmp).endswith(os.path.join("core", "2.5.0", "core.ttl")))

    def test_core_builder_is_the_highest_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("build_core.py", "build_core_next.py", "build_core_2_4.py", "build_core_2_10.py", "test_build_core_2_11.py"):
                open(os.path.join(tmp, name), "w", encoding="utf-8", newline="\n").close()
            self.assertEqual(newest.core_builder(tmp), "build_core_2_10")

    def test_a_core_builder_name_with_a_line_end_is_not_a_builder(self):
        # With match and "$", "build_core_9_9.py\n" would pass and give the module name "build_core_9_9.".
        import re
        self.assertIsNone(newest.CORE_BUILDER.fullmatch("build_core_9_9.py\n"))
        self.assertIsNotNone(newest.CORE_BUILDER.fullmatch("build_core_9_9.py"))
        self.assertNotIn("$", newest.CORE_BUILDER.pattern)
        self.assertNotIn("$", newest.VERSION.pattern)
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("build_core_2_4.py", "build_core_9_9.py\n" if os.name != "nt" else "build_core_2_3.py"):
                open(os.path.join(tmp, name), "w", encoding="utf-8", newline="\n").close()
            self.assertEqual(newest.core_builder(tmp), "build_core_2_4")
            self.assertTrue(re.fullmatch(r"build_core_\d+_\d+", newest.core_builder(tmp)))


class RefuseOverwrite(unittest.TestCase):
    def test_a_new_package_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            newest.refuse_overwrite(os.path.join(tmp, "absent"), {"a.ttl": "x"}, "kpi 1.0.0")

    def test_the_same_content_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = package(tmp, "kpi", "1.0.0", {"a.ttl": "x"})
            newest.refuse_overwrite(out, {"a.ttl": "x"}, "kpi 1.0.0")

    def test_a_changed_file_is_refused_and_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = package(tmp, "kpi", "1.0.0", {"a.ttl": "x"})
            with self.assertRaises(SystemExit) as caught:
                newest.refuse_overwrite(out, {"a.ttl": "y"}, "kpi 1.0.0")
            self.assertIn("a.ttl", str(caught.exception))
            self.assertIn("raise the version", str(caught.exception))

    def test_a_new_file_in_a_released_package_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = package(tmp, "kpi", "1.0.0")
            with self.assertRaises(SystemExit):
                newest.refuse_overwrite(out, {"b.ttl": "y"}, "kpi 1.0.0")

    def test_the_rebuild_of_a_whole_set_may_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = package(tmp, "kpi", "1.0.0", {"a.ttl": "x"})
            newest.refuse_overwrite(out, {"a.ttl": "y"}, "kpi 1.0.0", rebuild_released=True)


if __name__ == "__main__":
    unittest.main()
