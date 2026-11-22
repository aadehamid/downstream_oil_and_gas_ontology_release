"""Tests of the upgrade command (kpi_store/upgrade.py) on small releases made in temporary Git copies.

Each test makes a copy the way the runbook does (git init, then the commit "KPI Store <version> as shipped"),
changes it the way the commands do, and upgrades it from a newer release folder or zip. The check the merged copy
must pass is a stand-in that passes or fails at once; the real check is bash scripts/check.sh, which the guide's
rehearsal runs.
"""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from kpi_store import cut, upgrade as up

PASS = [sys.executable, "-c", "print('all checks passed')"]
FAIL = [sys.executable, "-c", "import sys; print('1 failed'); sys.exit(1)"]
PATHS = "kpi_store/**\nscripts/**\n**/*.py\n!scripts/pinned-tests.txt\n"
REGISTRY = "MODULES = [\n    'kpi',\n    'organization',\n]\n\n\ndef build():\n    return 1\n"


def git(root, *args):
    env = {k: v for k, v in os.environ.items() if k not in cut.GIT_PLACE}
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def write(root, files):
    for path, text in files.items():
        target = Path(root) / path
        if text is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")


def release(root, version, changes=None):
    """A release folder: its name, the tool list, two tools, the module registry, two content files and a pin list."""
    files = {
        "release.json": json.dumps({"release": f"KPI Store {version}"}),
        "kpi_store/upgrade-paths.txt": PATHS,
        "kpi_store/tool.py": "A = 1\n",
        "scripts/check.sh": "echo 'all checks passed'\n",
        "business_architecture/ontology/release/build_module.py": REGISTRY,
        "business_architecture/ontology/kpi/measures.ttl": "# the measures\n",
        "business_architecture/ontology/kpi/measures.csv": "id\nM1\n",
        "scripts/pinned-tests.txt": "test_a\n",
    }
    files.update(changes or {})
    write(root, files)
    return Path(root)


def shipped(tmp_path, version="1.2"):
    """A copy made as the runbook makes it."""
    copy = release(tmp_path / "copy", version)
    git(copy, "init", "-q")
    git(copy, "config", "user.name", "KPI Store operator")
    git(copy, "config", "user.email", "kpi-store-operator@example.invalid")
    git(copy, "add", "-A")
    git(copy, "commit", "-q", "-m", f"KPI Store {version} as shipped")
    return copy


def commit(copy, files, message="A change by a command"):
    write(copy, files)
    git(copy, "add", "-A")
    git(copy, "commit", "-q", "-m", message)


def read(copy, path):
    return (Path(copy) / path).read_text(encoding="utf-8")


def state(copy):
    return git(copy, "rev-parse", "HEAD"), git(copy, "tag"), git(copy, "status", "--porcelain"), git(copy, "worktree", "list")


def test_an_upgrade_takes_new_tools_keeps_content_and_tags(tmp_path):
    copy = shipped(tmp_path)
    commit(copy, {"business_architecture/ontology/kpi/measures.csv": "id\nM1\nM2\n"})
    new = release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n", "business_architecture/ontology/kpi/measures.csv": "id\nM1\nM9\n", "business_architecture/ontology/kpi/measures.ttl": "# the measures, as the release team has them\n", "business_architecture/ontology/kpi/units.csv": "unit\nbbl\n", "kpi_store/new.py": "B = 1\n", "scripts/pinned-tests.txt": "test_a\ntest_b\n"})
    said = []
    plan = up.upgrade(copy, new, say=said.append, check=PASS)
    assert read(copy, "kpi_store/tool.py") == "A = 2\n"
    assert read(copy, "kpi_store/new.py") == "B = 1\n"
    # Content stays the copy's, whether the copy changed it or not; a new content file is added.
    assert read(copy, "business_architecture/ontology/kpi/measures.csv") == "id\nM1\nM2\n"
    assert read(copy, "business_architecture/ontology/kpi/measures.ttl") == "# the measures\n"
    assert read(copy, "business_architecture/ontology/kpi/units.csv") == "unit\nbbl\n"
    # A pattern with ! keeps the copy's pin list.
    assert read(copy, "scripts/pinned-tests.txt") == "test_a\n"
    assert sorted(plan.kept) == ["business_architecture/ontology/kpi/measures.csv",
                                 "business_architecture/ontology/kpi/measures.ttl", "release.json",
                                 "scripts/pinned-tests.txt"]
    assert plan.updated == ["kpi_store/tool.py"]
    assert git(copy, "tag") == "kpi-store-1.3-tools"
    assert git(copy, "log", "-1", "--format=%s") == "Upgrade the tools to KPI Store 1.3"
    assert git(copy, "status", "--porcelain") == ""
    assert len(git(copy, "worktree", "list").splitlines()) == 1
    assert said[-1].startswith("Upgraded to the tools of KPI Store 1.3.")


def test_a_tool_file_the_commands_changed_gets_both_changes(tmp_path):
    copy = shipped(tmp_path)
    commit(copy, {"business_architecture/ontology/release/build_module.py": REGISTRY.replace(
        "    'organization',\n", "    'organization',\n    'sampletankinspections',\n")})
    new = release(tmp_path / "new", "1.3",
                  {"business_architecture/ontology/release/build_module.py": REGISTRY.replace("return 1", "return 2")})
    plan = up.upgrade(copy, new, say=lambda *_: None, check=PASS)
    text = read(copy, "business_architecture/ontology/release/build_module.py")
    assert "'sampletankinspections'" in text and "return 2" in text
    assert plan.merged == ["business_architecture/ontology/release/build_module.py"]


def test_the_same_lines_changed_on_both_sides_is_refused_and_nothing_changes(tmp_path):
    copy = shipped(tmp_path)
    commit(copy, {"kpi_store/tool.py": "A = 'mine'\n"})
    new = release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 'theirs'\n"})
    before = state(copy)
    with pytest.raises(up.UpgradeRefused, match=r"changed the same lines of kpi_store/tool\.py"):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)
    assert state(copy) == before
    assert read(copy, "kpi_store/tool.py") == "A = 'mine'\n"


def test_a_failed_check_is_refused_and_nothing_changes(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"})
    before = state(copy)
    with pytest.raises(up.UpgradeRefused, match=r"the full check failed on the merged copy \(exit 1\); its output is in (.+)") as err:
        up.upgrade(copy, new, say=lambda *_: None, check=FAIL)
    log = Path(str(err.value).split("its output is in ")[1].split(". Send")[0])
    assert log.read_text(encoding="utf-8").startswith("1 failed")
    assert state(copy) == before
    assert read(copy, "kpi_store/tool.py") == "A = 1\n"


def test_the_check_runs_on_the_merged_copy(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"})
    look = [sys.executable, "-c", "import pathlib, sys; t = pathlib.Path('kpi_store/tool.py').read_text(); "
                                  "print('all checks passed' if t == 'A = 2\\n' else t); sys.exit(t != 'A = 2\\n')"]
    up.upgrade(copy, new, say=lambda *_: None, check=look)
    assert read(copy, "kpi_store/tool.py") == "A = 2\n"


def test_a_second_upgrade_starts_from_the_tag(tmp_path):
    copy = shipped(tmp_path)
    up.upgrade(copy, release(tmp_path / "v13", "1.3", {"kpi_store/tool.py": "A = 2\n"}), say=lambda *_: None, check=PASS)
    commit(copy, {"kpi_store/tool.py": "A = 2\nMINE = 1\n"})
    plan = up.upgrade(copy, release(tmp_path / "v14", "1.4", {"kpi_store/tool.py": "Z = 0\nA = 2\n"}),
                      say=lambda *_: None, check=PASS)
    assert plan.base_release == "KPI Store 1.3" and plan.base_from == "the tag kpi-store-1.3-tools"
    assert read(copy, "kpi_store/tool.py") == "Z = 0\nA = 2\nMINE = 1\n"
    assert git(copy, "tag").split() == ["kpi-store-1.3-tools", "kpi-store-1.4-tools"]


def test_tools_of_the_same_release_change_nothing(tmp_path):
    copy = shipped(tmp_path)
    before = state(copy)
    said = []
    up.upgrade(copy, release(tmp_path / "new", "1.2", {"kpi_store/tool.py": "A = 2\n"}), say=said.append, check=FAIL)
    assert said[-1] == "This copy has the tools of KPI Store 1.2 already. Nothing was changed."
    assert state(copy) == before


def test_the_plan_says_what_would_change_and_changes_nothing(tmp_path):
    copy = shipped(tmp_path)
    before = state(copy)
    said = []
    plan = up.upgrade(copy, release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"}), plan_only=True, say=said.append, check=FAIL)
    assert plan.updated == ["kpi_store/tool.py"]
    lines = said[0].splitlines()
    assert lines[0] == "From KPI Store 1.2 (at the first commit) to the tools of KPI Store 1.3."
    assert lines[1] == "  1 tool files that take the new version: kpi_store/tool.py"
    assert lines[-1] == "  1 content files the new release changes, which keep your version: release.json"
    assert said[-1] == "This was the plan only. Nothing was changed."
    assert state(copy) == before


def test_a_tool_file_the_new_release_removes_is_removed(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3")
    (new / "kpi_store" / "tool.py").unlink()
    plan = up.upgrade(copy, new, say=lambda *_: None, check=PASS)
    assert plan.removed == ["kpi_store/tool.py"]
    assert not (copy / "kpi_store" / "tool.py").exists()


def test_a_zip_works_and_its_sha_256_is_said(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"})
    archive = tmp_path / "kpi-store-1.3.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for path in sorted(new.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(new).as_posix())
    said = []
    up.upgrade(copy, archive, say=said.append, check=PASS)
    assert said[0].startswith("The zip's SHA-256 is ") and len(said[0].split()[-1]) == 65
    assert read(copy, "kpi_store/tool.py") == "A = 2\n"


@pytest.mark.parametrize("name", ["../outside.py", "/abs.py", "a\\b.py", "c:x.py"])
def test_a_zip_entry_outside_the_folder_is_refused(tmp_path, name):
    copy = shipped(tmp_path)
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "x")
    with pytest.raises(up.UpgradeRefused, match="would land outside the release folder"):
        up.upgrade(copy, archive, say=lambda *_: None, check=PASS)
    assert not (tmp_path / "outside.py").exists()


def test_a_plain_folder_is_refused(tmp_path):
    copy = release(tmp_path / "copy", "1.2")
    with pytest.raises(up.UpgradeRefused, match="is not a Git copy"):
        up.upgrade(copy, release(tmp_path / "new", "1.3"), say=lambda *_: None, check=PASS)


def test_uncommitted_changes_are_refused(tmp_path):
    copy = shipped(tmp_path)
    write(copy, {"kpi_store/tool.py": "A = 'not committed'\n"})
    with pytest.raises(cut.CutRefused, match="changes that are not committed: kpi_store/tool.py"):
        up.upgrade(copy, release(tmp_path / "new", "1.3"), say=lambda *_: None, check=PASS)


def test_a_first_commit_that_is_not_as_shipped_is_refused(tmp_path):
    copy = release(tmp_path / "copy", "1.2")
    git(copy, "init", "-q")
    git(copy, "config", "user.name", "x")
    git(copy, "config", "user.email", "x@example.invalid")
    git(copy, "add", "-A")
    git(copy, "commit", "-q", "-m", "first")
    with pytest.raises(up.UpgradeRefused, match='first commit is "first", not "KPI Store <version> as shipped"'):
        up.upgrade(copy, release(tmp_path / "new", "1.3"), say=lambda *_: None, check=PASS)


def test_a_release_without_the_tool_list_is_refused(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3")
    (new / "kpi_store" / "upgrade-paths.txt").unlink()
    with pytest.raises(up.UpgradeRefused, match="has no kpi_store/upgrade-paths.txt"):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)


@pytest.mark.parametrize("text", ["{}", '{"release": "1.3"}', "not json", '["KPI Store 1.3"]'])
def test_a_release_that_names_no_release_is_refused(tmp_path, text):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3", {"release.json": text})
    with pytest.raises(up.UpgradeRefused, match="does not name a release"):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)


def test_a_tag_on_head_is_the_base(tmp_path):
    copy = shipped(tmp_path)
    git(copy, "tag", "kpi-store-1.3-tools", "HEAD")
    said = []
    up.upgrade(copy, release(tmp_path / "new", "1.3"), say=said.append, check=PASS)
    assert said[-1] == "This copy has the tools of KPI Store 1.3 already. Nothing was changed."


def test_a_tag_the_upgrade_would_make_is_refused(tmp_path):
    copy = shipped(tmp_path)
    git(copy, "checkout", "-q", "-b", "elsewhere")
    commit(copy, {"kpi_store/other.py": "x = 1\n"})
    git(copy, "tag", "kpi-store-1.3-tools", "HEAD")
    git(copy, "checkout", "-q", "-")
    before = state(copy)
    with pytest.raises(up.UpgradeRefused, match="already has the tag kpi-store-1.3-tools"):
        up.upgrade(copy, release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"}), say=lambda *_: None, check=PASS)
    assert state(copy) == before


@pytest.mark.parametrize("path, tool", [
    ("conftest.py", True), ("a/b/c.py", True), ("kpi_store/x/y.json", True), ("scripts/pinned-tests.txt", False),
    ("business_architecture/ontology/kpi/measures.ttl", False), ("README.md", False), ("kpi_store", False)])
def test_the_patterns(path, tool):
    assert up.is_tool(path, up.read_patterns(PATHS)) is tool


def test_this_releases_tool_list():
    """The release's own list: code and the guides are tools; the ontology's tables, Turtle and records are content."""
    root = Path(__file__).resolve().parents[2]
    patterns = up.read_patterns((root / up.PATHS_FILE).read_text(encoding="utf-8"))
    for path in ("kpi_store/upgrade.py", "business_architecture/ontology/release/build_module.py",
                 "business_architecture/ontology/projection/pipeline.py", "HOW-TO-UPDATE.md", "skills/ontology/SKILL.md",
                 "scripts/check.sh", "conftest.py"):
        assert up.is_tool(path, patterns), path
    for path in ("release.json", "business_architecture/ontology/kpi/measures.ttl", "kpi-intake/catalogue.toml",
                 "business_architecture/ontology/kpi/measure-details.csv", "scripts/pinned-tests.txt",
                 "scripts/standalone-exceptions.txt", "business_architecture/ontology/releases/catalog.ttl"):
        assert not up.is_tool(path, patterns), path
