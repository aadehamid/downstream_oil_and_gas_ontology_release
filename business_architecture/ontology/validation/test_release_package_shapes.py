"""Step 9 (the decision of 2026-10-22): every release package on disk conforms to its own shapes.ttl, run over
the package with the released packages it requires loaded (its closure, read from the manifests). The
whole-graph gate (test_all_module_shapes.py) runs the source files; this test runs what was shipped.

Run: python3 -m pytest test_release_package_shapes.py (needs rdflib, pyshacl).
"""
import glob
import importlib
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from pyshacl import validate
from rdflib import Graph, Namespace
from rdflib.namespace import SKOS

HERE = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ONTOLOGY, "release"))
import build_module  # noqa: E402
import newest  # noqa: E402
core = importlib.import_module(newest.core_builder())  # the newest core builder: its version and the version it builds from

# Pinned by hand: each module's newest package and the one before it (the decision of 2026-10-31). A new release
# must join this list, so its package is checked here. logical-model has one release.
PACKAGES = [
    ("core", "2.3.0"), ("core", "2.4.0"),
    ("data-product", "1.1.0"), ("data-product", "1.2.0"), ("integration", "2.4.0"), ("integration", "2.5.0"),
    ("kpi", "1.2.0"), ("kpi", "1.3.0"), ("lane", "1.0.0"), ("lane", "1.1.0"),
    ("logical-model", "1.0.0"), ("market-data", "1.0.0"), ("market-data", "1.1.0"),
    ("organization", "2.1.0"), ("organization", "2.2.0"), ("party", "2.0.0"), ("party", "2.1.0"),
    ("ref-mpc", "1.2.0"), ("ref-mpc", "1.3.0"), ("system", "1.4.0"), ("system", "1.5.0"),
    ("technical-graph", "1.0.0"), ("technical-graph", "1.1.0"), ("value-stream", "1.1.0"), ("value-stream", "1.2.0"),
]


def package_file(name, version, fname):
    folder = build_module.package_folder(name, version)  # releases/<name>/<version>/, or the history folder
    return os.path.join(folder or os.path.join(ONTOLOGY, "releases", name, version), fname)


def packages_on_disk(ontology=ONTOLOGY):
    """(module, version) for every package folder, the history folder releases/previous/ included."""
    found = set()
    for pattern in (os.path.join(ontology, "releases", "*", "*", ""), os.path.join(ontology, "releases", "previous", "*", "*", "")):
        for p in glob.glob(pattern):
            name, version = p.rstrip(os.sep).split(os.sep)[-2:]
            if name != "previous" and version[0].isdigit():
                found.add((name, version))
    return found


def previous_version(name, newest, ontology=ONTOLOGY):
    """The version before `newest`, read from the newest package's own CHANGELOG.md (its second heading), not from
    the folders on disk; None when the changelog names no earlier version."""
    with open(os.path.join(ontology, "releases", name, newest, "CHANGELOG.md")) as f:
        versions = re.findall(rf"^## ({newest.VERSION_PATTERN})", f.read(), re.M)
    return versions[1] if versions[:1] == [newest] and len(versions) > 1 else None


def expected_release_packages(ontology=ONTOLOGY):
    """The packages the tree must hold (the decision of 2026-10-31): each module's newest version, from the builders'
    own tables, and the one before it, from each newest package's changelog (core's from its builder's base). Nothing
    here is read from the list of folders, so a missing package is missed by the disk, not by this."""
    newest = {(m, build_module.label(build_module.MODULES[m])) for m in build_module.MODULES} | {("core", core.VERSION)}
    previous = {("core", os.path.basename(core.BASE))}
    for name, version in newest - {("core", core.VERSION)}:
        before = previous_version(name, version, ontology)
        if before:
            previous.add((name, before))
    return newest | previous


def package_graph(name, version):
    return Graph().parse(package_file(name, version, f"{name}.ttl"))


def with_closure(name, version, g, tc=None):
    data = Graph()
    data += g
    try:
        closure = build_module.closure(build_module.released_requires(name, version))
    except FileNotFoundError as e:
        # Only a package of the history folder may lack its closure: its manifest may name versions the tree does
        # not hold (the decision of 2026-10-31). A newest package's closure must be on disk.
        previous = os.path.isdir(os.path.join(ONTOLOGY, "releases", "previous", name, version))
        if tc is None or not previous:
            raise
        tc.skipTest(f"{e}: {name} {version} is history only (releases/previous/), and the tree does not hold its closure")
    for dep, dep_version in sorted(closure.items()):
        data.parse(package_file(dep, dep_version, f"{dep}.ttl"))
    return data


def conforms(name, version, data):
    ok, _, text = validate(data, shacl_graph=Graph().parse(package_file(name, version, "shapes.ttl")), advanced=True)
    return ok, text


class ReleasePackages(unittest.TestCase):
    def test_every_package_is_listed(self):
        # Keyed on folders, not manifests, so a package written without its manifest is not missed.
        on_disk = packages_on_disk()
        self.assertEqual(set(PACKAGES), expected_release_packages())  # the list by hand agrees with the builders and changelogs
        # The tree keeps every earlier package under releases/previous/, however many later changes retire;
        # outside it, a module's folder holds only its newest package.
        self.assertEqual(set(PACKAGES) - on_disk, set())
        for name, version in on_disk - set(PACKAGES):
            self.assertTrue(os.path.isdir(os.path.join(ONTOLOGY, "releases", "previous", name, version)),
                            f"{name} {version} is neither the newest nor in releases/previous/")

    def test_a_broken_package_fails(self):
        # An office lane without its notation breaks the lane package's own shapes.
        lane = Namespace("https://w3id.org/mpc/ontology/modules/lane/lane/")
        version = "1.1.0"  # the newest lane package
        g = package_graph("lane", version)
        g.remove((lane["front-office"], SKOS.notation, None))
        ok, text = conforms("lane", version, with_closure("lane", version, g, self))
        self.assertFalse(ok)
        self.assertIn("front-office", text)


class ReleaseInventory(unittest.TestCase):
    """The expected package list comes from the builders and the changelogs, never from the folders it is
    checked against, so a missing package fails test_every_package_is_listed instead of vanishing."""

    def test_the_previous_version_comes_from_the_newest_packages_changelog(self):
        self.assertEqual(previous_version("kpi", "1.3.0"), "1.2.0")
        self.assertEqual(previous_version("lane", "1.1.0"), "1.0.0")
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "releases", "x", "1.0.0")
            os.makedirs(folder)
            with open(os.path.join(folder, "CHANGELOG.md"), "w") as f:
                f.write("# x\n\n## 1.0.0 (2026-10-01)\n\nFirst.\n")
            self.assertIsNone(previous_version("x", "1.0.0", tmp))

    def test_the_expected_set_is_each_newest_package_and_the_one_before(self):
        expected = expected_release_packages()
        newest = {(m, build_module.label(build_module.MODULES[m])) for m in build_module.MODULES} | {("core", core.VERSION)}
        self.assertTrue(newest <= expected)
        self.assertIn(("core", "2.3.0"), expected)
        self.assertIn(("kpi", "1.2.0"), expected)
        # every module has a version before its newest, except logical-model, whose 1.0.0 is its only release (the decision of 2026-11-02)
        self.assertEqual(len(expected), 2 * len(newest) - 1)
        self.assertTrue(expected <= packages_on_disk())

    def test_a_tree_missing_a_previous_package_is_found_out(self):
        # The negative fixture: every newest package's changelog, and no history folder. The expectation still
        # names each previous version, so the disk fails to match it.
        newest = {(m, build_module.label(build_module.MODULES[m])) for m in build_module.MODULES} | {("core", core.VERSION)}
        with tempfile.TemporaryDirectory() as tmp:
            for name, version in newest:  # the previous versions are left out of the fixture on purpose
                folder = os.path.join(tmp, "releases", name, version)
                os.makedirs(folder)
                shutil.copy(os.path.join(ONTOLOGY, "releases", name, version, "CHANGELOG.md"), folder)
            self.assertEqual(packages_on_disk(tmp) - expected_release_packages(tmp), set())
            missing = expected_release_packages(tmp) - packages_on_disk(tmp)
            self.assertIn(("kpi", "1.2.0"), missing)
            self.assertIn(("core", "2.3.0"), missing)

    def test_a_newest_package_without_its_closure_fails_and_only_history_skips(self):
        # with_closure turns a missing closure into a skip only for a package of releases/previous/.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "releases", "previous", "kpi", "0.9.0"))
            os.makedirs(os.path.join(tmp, "releases", "kpi", "1.0.0"))

            def gone(name, version):
                raise FileNotFoundError(f"{name} {version} is not on disk")
            with mock.patch.object(build_module, "released_requires", gone), \
                    mock.patch.object(sys.modules[__name__], "ONTOLOGY", tmp):
                with self.assertRaises(FileNotFoundError):
                    with_closure("kpi", "1.0.0", Graph(), self)  # a newest package
                with self.assertRaises(FileNotFoundError):
                    with_closure("kpi", "0.9.0", Graph())  # no test case to skip
                with self.assertRaises(unittest.SkipTest):
                    with_closure("kpi", "0.9.0", Graph(), self)  # history


def _package_test(name, version):
    def test(self):
        ok, text = conforms(name, version, with_closure(name, version, package_graph(name, version), self))
        self.assertTrue(ok, text[:3000])
    return test


for _name, _version in PACKAGES:
    setattr(ReleasePackages, f"test_{_name.replace('-', '_')}_{_version.replace('.', '_')}_conforms",
            _package_test(_name, _version))


if __name__ == "__main__":
    unittest.main()
