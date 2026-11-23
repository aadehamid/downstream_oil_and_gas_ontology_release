"""Tests of the upgrade command (kpi_store/upgrade.py) on small releases made in temporary Git copies.

Each test makes a copy the way the runbook does (git init, then the commit "KPI Store <version> as shipped"),
changes it the way the commands do, and upgrades it from a newer release folder or zip. The check the merged copy
must pass is a stand-in that passes or fails at once; the real check is bash scripts/check.sh, which the guide's
rehearsal runs.
"""
import json
import os
import shutil
import subprocess
import sys
import warnings
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
    # Content the copy changed stays the copy's; content it left as shipped takes the new version; a new content
    # file is added.
    assert read(copy, "business_architecture/ontology/kpi/measures.csv") == "id\nM1\nM2\n"
    assert read(copy, "business_architecture/ontology/kpi/measures.ttl") == "# the measures, as the release team has them\n"
    assert read(copy, "business_architecture/ontology/kpi/units.csv") == "unit\nbbl\n"
    # A pattern with ! keeps the copy's pin list.
    assert read(copy, "scripts/pinned-tests.txt") == "test_a\n"
    assert sorted(plan.kept) == ["business_architecture/ontology/kpi/measures.csv", "release.json",
                                 "scripts/pinned-tests.txt"]
    assert plan.renewed == ["business_architecture/ontology/kpi/measures.ttl"]
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
    shutil.rmtree(log.parent)
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


# On Windows, zipfile reads a backslash in an entry's name as a folder separator, so "a\\b.py" lands inside.
BACKSLASH = pytest.param("a\\b.py", marks=pytest.mark.skipif(os.sep == "\\", reason="zipfile on Windows reads \\ as /"))


@pytest.mark.parametrize("name", ["../outside.py", "/abs.py", BACKSLASH, "c:x.py"])
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


def test_a_first_commit_that_names_no_release_is_refused(tmp_path):
    copy = release(tmp_path / "copy", "1.2", {"release.json": "{}"})
    git(copy, "init", "-q")
    git(copy, "config", "user.name", "x")
    git(copy, "config", "user.email", "x@example.invalid")
    git(copy, "add", "-A")
    git(copy, "commit", "-q", "-m", "The release as received")
    with pytest.raises(up.UpgradeRefused, match="the release.json of this copy's first commit does not name a release"):
        up.upgrade(copy, release(tmp_path / "new", "1.3"), say=lambda *_: None, check=PASS)


def test_two_first_commits_are_refused(tmp_path):
    copy = shipped(tmp_path)
    first = git(copy, "rev-parse", "--abbrev-ref", "HEAD")
    git(copy, "checkout", "-q", "--orphan", "other")
    commit(copy, {"kpi_store/other.py": "x = 1\n"}, "Another start")
    git(copy, "checkout", "-q", first)
    git(copy, "merge", "-q", "--allow-unrelated-histories", "-m", "join", "other")
    with pytest.raises(up.UpgradeRefused, match="more than one first commit"):
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
                 "business_architecture/ontology/projection/pipeline.py", "HOW-TO-UPDATE.md", "HANDOUT.md", "skills/ontology/SKILL.md",
                 "scripts/check.sh", "conftest.py"):
        assert up.is_tool(path, patterns), path
    for path in ("release.json", "business_architecture/ontology/kpi/measures.ttl", "kpi-intake/catalogue.toml",
                 "business_architecture/ontology/kpi/measure-details.csv", "scripts/pinned-tests.txt",
                 "scripts/standalone-exceptions.txt", "business_architecture/ontology/releases/catalog.ttl"):
        assert not up.is_tool(path, patterns), path


# ---------- the findings of the first review ----------

def objects(copy):
    return git(copy, "count-objects", "-v")


def test_a_content_file_the_copy_made_at_a_path_the_new_release_adds_keeps_the_copys(tmp_path):
    copy = shipped(tmp_path)
    commit(copy, {"business_architecture/ontology/kpi/units.csv": "unit\nmine\n"})
    new = release(tmp_path / "new", "1.3", {"business_architecture/ontology/kpi/units.csv": "unit\ntheirs\n",
                                            "kpi_store/tool.py": "A = 2\n"})
    plan = up.upgrade(copy, new, say=lambda *_: None, check=PASS)
    assert read(copy, "business_architecture/ontology/kpi/units.csv") == "unit\nmine\n"
    assert "business_architecture/ontology/kpi/units.csv" in plan.kept and plan.added == []


def test_a_new_file_that_differs_only_in_case_is_refused(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3")
    # Removed first: on a file system that ignores case, writing Measures.csv would only rewrite measures.csv.
    (new / "business_architecture/ontology/kpi/measures.csv").unlink()
    (new / "business_architecture/ontology/kpi/Measures.csv").write_text("id\nM9\n", encoding="utf-8", newline="\n")
    before = state(copy)
    with pytest.raises(up.UpgradeRefused, match="differs only in the case of its letters"):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)
    assert state(copy) == before


def test_an_older_release_is_refused(tmp_path):
    copy = shipped(tmp_path)
    up.upgrade(copy, release(tmp_path / "v13", "1.3", {"kpi_store/tool.py": "A = 2\n"}), say=lambda *_: None, check=PASS)
    before = state(copy)
    with pytest.raises(up.UpgradeRefused, match="the new release is KPI Store 1.2, older than the tools of KPI Store 1.3"):
        up.upgrade(copy, release(tmp_path / "v12", "1.2"), say=lambda *_: None, check=PASS)
    assert state(copy) == before


def test_versions_compare_as_numbers():
    assert up.version("KPI Store 1.10") > up.version("KPI Store 1.9")


def test_a_folder_that_moved_while_the_check_ran_is_refused(tmp_path):
    copy = shipped(tmp_path)
    move = [sys.executable, "-c", "import subprocess, sys; subprocess.run(['git', '-C', sys.argv[1], 'commit', '-q', "
                                  "'--allow-empty', '-m', 'meanwhile'], check=True); print('all checks passed')", str(copy)]
    with pytest.raises(up.UpgradeRefused, match="the folder changed while the check ran"):
        up.upgrade(copy, release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"}), say=lambda *_: None, check=move)
    assert git(copy, "log", "-1", "--format=%s") == "meanwhile"
    assert git(copy, "tag") == "" and read(copy, "kpi_store/tool.py") == "A = 1\n"


def test_a_tag_that_cannot_be_made_changes_nothing(tmp_path):
    copy = shipped(tmp_path)
    git(copy, "tag", "kpi-store-1.3-tools/note")
    before = state(copy)
    with pytest.raises(up.UpgradeRefused, match="git tag failed"):
        up.upgrade(copy, release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"}), say=lambda *_: None, check=PASS)
    assert state(copy) == before and read(copy, "kpi_store/tool.py") == "A = 1\n"


def test_a_relative_release_folder_and_source_work_from_elsewhere(tmp_path, monkeypatch):
    shipped(tmp_path)
    release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"})
    monkeypatch.chdir(tmp_path)
    up.upgrade("copy", "new", say=lambda *_: None, check=PASS)
    assert read(tmp_path / "copy", "kpi_store/tool.py") == "A = 2\n"


def test_the_base_is_the_tag_of_the_highest_version(tmp_path):
    copy = shipped(tmp_path)
    first = git(copy, "rev-parse", "--abbrev-ref", "HEAD")
    up.upgrade(copy, release(tmp_path / "v15", "1.5", {"kpi_store/tool.py": "A = 5\n"}), say=lambda *_: None, check=PASS)
    git(copy, "checkout", "-q", "-b", "other", "HEAD~1")
    up.upgrade(copy, release(tmp_path / "v13", "1.3", {"kpi_store/b.py": "B = 3\n"}), say=lambda *_: None, check=PASS)
    up.upgrade(copy, release(tmp_path / "v14", "1.4", {"kpi_store/b.py": "B = 4\n"}), say=lambda *_: None, check=PASS)
    git(copy, "checkout", "-q", first)
    git(copy, "merge", "-q", "-m", "join", "other")
    git(copy, "tag", "kpi-store-backup-tools")
    plan = up.upgrade(copy, release(tmp_path / "v15b", "1.5"), plan_only=True, say=lambda *_: None, check=FAIL)
    assert plan.base_from == "the tag kpi-store-1.5-tools"


def test_the_plan_and_an_early_refusal_write_no_git_object(tmp_path):
    copy = shipped(tmp_path)
    before = objects(copy)
    up.upgrade(copy, release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"}), plan_only=True,
               say=lambda *_: None, check=FAIL)
    assert objects(copy) == before


def test_the_bash_of_the_local_settings_is_used(tmp_path, monkeypatch):
    copy = shipped(tmp_path)
    seen = {}
    monkeypatch.setattr(up.local_settings, "load", lambda path, environ, release_root: type("S", (), {"bash": "/my/bash"})())
    monkeypatch.setattr(up.setup_check, "find_bash", lambda setting=None: seen.setdefault("setting", setting) and None)
    with pytest.raises(up.UpgradeRefused, match="bash was not found"):
        up.upgrade(copy, release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"}), say=lambda *_: None,
                   environ={"KPI_STORE_LOCAL": str(tmp_path / "stores.toml")})
    assert seen["setting"] == "/my/bash"


def test_windows_line_ends_in_the_new_release_are_refused(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3")
    (new / "kpi_store" / "tool.py").write_bytes(b"A = 2\r\n")
    with pytest.raises(up.UpgradeRefused, match=r"Windows line ends \(CRLF\): kpi_store/tool.py"):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)


def zip_of(path, entries, **kw):
    with zipfile.ZipFile(path, "w", **kw) as z:
        for name, text in entries:
            z.writestr(name, text)


def damaged(path):
    zip_of(path, [("kpi_store/tool.py", "A = 2\n" * 50)], compression=zipfile.ZIP_DEFLATED)
    data = bytearray(path.read_bytes())
    data[30 + len("kpi_store/tool.py")] = 0x06   # the first byte of the stream: a block type DEFLATE reserves
    path.write_bytes(bytes(data))


def damaged_lzma(path):
    zip_of(path, [("kpi_store/tool.py", "A = 2\n" * 50)], compression=zipfile.ZIP_LZMA)
    data = bytearray(path.read_bytes())
    data[30 + len("kpi_store/tool.py") + 4] = 0xFF   # inside the LZMA properties after zipfile's 4-byte header
    path.write_bytes(bytes(data))


@pytest.mark.parametrize("make, says", [
    (lambda path: path.write_bytes(b"not a zip"), "cannot be read as a zip"),
    (lambda path: zip_of(path, []), "holds no file"),
    (lambda path: zip_of(path, [(".", "x")]), "names no file"),
    (damaged, r"cannot be read as a zip \(error"),
    (lambda path: damaged_lzma(path), r"cannot be read as a zip \(LZMAError"),
    (lambda path: zip_of(path, [("kpi_store/a.py", "x = 1\n"), ("kpi_store/A.py", "x = 2\n")]),
     "differ only in the case of their letters: kpi_store/A.py, kpi_store/a.py"),
    (lambda path: zip_of(path, [("kpi_store/a.py", "x = 1\n"), ("./kpi_store//A.py", "x = 2\n")]),
     "differ only in the case of their letters: kpi_store/A.py, kpi_store/a.py"),
    (lambda path: zip_of(path, [("kpi_store/a.py", "x = 1\n"), ("KPI_STORE/b.py", "x = 2\n")]),
     "differ only in the case of their letters: KPI_STORE, kpi_store"),
])
def test_a_zip_that_is_not_a_release_is_refused_plainly(tmp_path, make, says):
    copy = shipped(tmp_path)
    archive = tmp_path / "bad.zip"
    make(archive)
    with pytest.raises(up.UpgradeRefused, match=says):
        up.upgrade(copy, archive, say=lambda *_: None, check=PASS)


def test_a_finder_zip_with_one_top_folder_works(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"})
    archive = tmp_path / "finder.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for path in sorted(new.rglob("*")):
            if path.is_file():
                z.write(path, "kpi-store-1.3/" + path.relative_to(new).as_posix())
        z.writestr("__MACOSX/kpi-store-1.3/._release.json", "x")
    up.upgrade(copy, archive, say=lambda *_: None, check=PASS)
    assert read(copy, "kpi_store/tool.py") == "A = 2\n" and not (copy / FINDER_DIR).exists()


FINDER_DIR = "__MACOSX"


def test_a_conflict_names_a_file_with_a_space_whole(tmp_path):
    copy = shipped(tmp_path)
    commit(copy, {"kpi_store/my tool.py": "A = 'mine'\n"})
    new = release(tmp_path / "new", "1.3", {"kpi_store/my tool.py": "A = 'theirs'\n"})
    with pytest.raises(up.UpgradeRefused, match=r"same lines of kpi_store/my tool\.py\."):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)


def test_a_copy_without_an_author_is_told_how_to_set_one(tmp_path):
    copy = shipped(tmp_path)
    git(copy, "config", "--unset", "user.name")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path), GIT_CONFIG_NOSYSTEM="1")
    old = dict(os.environ)
    os.environ.clear(); os.environ.update(env)
    try:
        with pytest.raises(up.UpgradeRefused) as err:
            up.upgrade(copy, release(tmp_path / "new", "1.3"), say=lambda *_: None, check=PASS)
    finally:
        os.environ.clear(); os.environ.update(old)
    assert "git config user.name" in str(err.value) and "plain folder" not in str(err.value)


def test_a_zip_that_cannot_be_read_is_refused(tmp_path):
    copy = shipped(tmp_path)
    archive = tmp_path / "locked.zip"
    zip_of(archive, [("x", "x")])
    archive.chmod(0)
    try:
        if os.access(archive, os.R_OK):
            pytest.skip("this user can read a file with no permissions")
        with pytest.raises(up.UpgradeRefused, match="cannot be read"):
            up.upgrade(copy, archive, say=lambda *_: None, check=PASS)
    finally:
        archive.chmod(0o644)


def test_two_new_files_that_differ_only_in_case_are_refused(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3")
    (new / "kpi_store" / "a.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    if (new / "kpi_store" / "A.py").exists():
        pytest.skip("this file system holds one file for both names")
    (new / "kpi_store" / "A.py").write_text("x = 2\n", encoding="utf-8", newline="\n")
    with pytest.raises(up.UpgradeRefused, match="differs only in the case of its letters"):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)


def test_the_same_version_written_another_way_changes_nothing(tmp_path):
    copy = shipped(tmp_path, "1.3")
    said = []
    up.upgrade(copy, release(tmp_path / "new", "1.03", {"kpi_store/tool.py": "A = 2\n"}), say=said.append, check=FAIL)
    assert said[-1] == "This copy has the tools of KPI Store 1.03 already. Nothing was changed."


@pytest.mark.parametrize("step", ["worktree add", "worktree remove"])
def test_the_worktree_is_gone_whatever_fails(tmp_path, monkeypatch, step):
    copy = shipped(tmp_path)
    real = up._git

    def failing(root, *args, **kw):
        if " ".join(args[:2]) == step:
            if step == "worktree add":   # Git registers the worktree, then the add fails
                real(root, *args, **kw)
            return subprocess.CompletedProcess(args, 1, "", f"{step} failed on purpose")
        return real(root, *args, **kw)
    monkeypatch.setattr(up, "_git", failing)
    with pytest.raises(up.UpgradeRefused):
        up.upgrade(copy, release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"}), say=lambda *_: None, check=FAIL)
    assert len(git(copy, "worktree", "list").splitlines()) == 1


def test_a_zip_in_a_folder_that_cannot_be_read_is_refused(tmp_path):
    copy = shipped(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    zip_of(locked / "release.zip", [("x", "x")])
    locked.chmod(0)
    try:
        if os.access(locked, os.R_OK | os.X_OK):
            pytest.skip("this user can read a folder with no permissions")
        with pytest.raises(up.UpgradeRefused, match="cannot be read"):
            up.upgrade(copy, locked / "release.zip", say=lambda *_: None, check=PASS)
    finally:
        locked.chmod(0o755)


def test_an_output_error_is_not_reported_as_an_unreadable_zip(tmp_path):
    copy = shipped(tmp_path)
    archive = tmp_path / "release.zip"
    zip_of(archive, [("x", "x")])

    def broken(_):
        raise BrokenPipeError
    with pytest.raises(BrokenPipeError):
        up.upgrade(copy, archive, say=broken, check=PASS)


def test_an_entry_listed_twice_is_not_a_case_twin(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3", {"kpi_store/tool.py": "A = 2\n"})
    archive = tmp_path / "twice.zip"
    with zipfile.ZipFile(archive, "w") as z, warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)   # zipfile warns of the name it is asked to write twice
        z.writestr("kpi_store/", "")
        z.writestr("kpi_store/", "")
        for path in sorted(new.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(new).as_posix())
    up.upgrade(copy, archive, say=lambda *_: None, check=PASS)
    assert read(copy, "kpi_store/tool.py") == "A = 2\n"


def test_a_new_file_in_a_folder_that_differs_only_in_case_is_refused(tmp_path):
    # The new release's ontology folder is Business_architecture; the copy's is business_architecture. The new
    # release holds one spelling only, so the test runs on a file system that ignores case too.
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3")
    (new / "business_architecture").rename(new / "tmp-move")
    (new / "tmp-move").rename(new / "Business_architecture")
    with pytest.raises(up.UpgradeRefused, match=r"Business_architecture/\S+ differs only in the case of its letters "
                                                r"from business_architecture, and"):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)


def test_case_twins_read_paths_as_zipfile_unpacks_them():
    assert up.case_twins(["kpi_store/a.py", "./kpi_store//A.py", "kpi_store/a.py"]) == {
        "kpi_store/a.py": ("kpi_store/A.py", "kpi_store/a.py"), "kpi_store/A.py": ("kpi_store/A.py", "kpi_store/a.py")}
    assert up.case_twins(["a/x", "A/y"])["A"] == ("A", "a")
    assert up.case_twins(["kpi_store/", "kpi_store/"]) == {}


def test_content_left_as_shipped_takes_the_new_version_and_the_copys_own_files_stay(tmp_path):
    # A 1.1 copy that never touched the kpi tables, upgraded to a release that adds a column to them: the copy
    # takes the new table, so the new builders read the format they expect.
    copy = shipped(tmp_path)
    commit(copy, {"kpi_store/tool.py": "A = 1\n# the copy's own line\n"}, "A change to a tool")
    new = release(tmp_path / "new", "1.3", {"business_architecture/ontology/kpi/measures.csv": "id,source\nM1,s\n",
                                            "scripts/pinned-tests.txt": "test_a\ntest_b\n"})
    plan = up.upgrade(copy, new, say=lambda *_: None, check=PASS)
    assert read(copy, "business_architecture/ontology/kpi/measures.csv") == "id,source\nM1,s\n"
    assert plan.renewed == ["business_architecture/ontology/kpi/measures.csv"]
    # release.json and a `!` path stay the copy's, though the copy never changed them.
    assert json.loads(read(copy, "release.json"))["release"] == "KPI Store 1.2"
    assert read(copy, "scripts/pinned-tests.txt") == "test_a\n"
    assert "release.json" in plan.kept and "scripts/pinned-tests.txt" in plan.kept


def test_a_table_both_changed_whose_columns_the_new_release_changes_is_refused_and_nothing_changes(tmp_path):
    copy = shipped(tmp_path)
    commit(copy, {"business_architecture/ontology/kpi/measures.csv": "id\nM1\nM2\n"}, "A correction")
    before = state(copy)
    new = release(tmp_path / "new", "1.3", {"business_architecture/ontology/kpi/measures.csv": "id,source\nM1,s\n"})
    with pytest.raises(up.UpgradeRefused, match=r"changes the columns of business_architecture/ontology/kpi/measures\.csv"):
        up.upgrade(copy, new, say=lambda *_: None, check=PASS)
    assert state(copy) == before
    with pytest.raises(up.UpgradeRefused, match="Replace the release with a newer zip"):
        up.plan(copy, new)


def test_a_table_both_changed_with_the_same_columns_keeps_the_copys(tmp_path):
    copy = shipped(tmp_path)
    commit(copy, {"business_architecture/ontology/kpi/measures.csv": "id\nM1\nM2\n"}, "A correction")
    new = release(tmp_path / "new", "1.3", {"business_architecture/ontology/kpi/measures.csv": "id\nM1\nM9\n"})
    plan = up.upgrade(copy, new, say=lambda *_: None, check=PASS)
    assert read(copy, "business_architecture/ontology/kpi/measures.csv") == "id\nM1\nM2\n"
    assert "business_architecture/ontology/kpi/measures.csv" in plan.kept


def test_the_plan_names_the_content_that_takes_the_new_version(tmp_path):
    copy = shipped(tmp_path)
    new = release(tmp_path / "new", "1.3", {"business_architecture/ontology/kpi/measures.ttl": "# newer\n"})
    said = []
    up.upgrade(copy, new, plan_only=True, say=said.append)
    assert any("1 content files you left as shipped, which take the new version: "
               "business_architecture/ontology/kpi/measures.ttl" in line for line in said)
    assert read(copy, "business_architecture/ontology/kpi/measures.ttl") == "# the measures\n"
