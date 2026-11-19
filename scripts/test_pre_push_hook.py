"""Tests for scripts/hooks/pre-push: it runs the release's check before a push that sends commits, passes the
check's exit code through, and runs nothing for a push that only deletes remote branches. Each test builds a
throwaway Git repository whose scripts/check.sh is a stand-in that records that it ran."""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hooks", "pre-push")
ZEROS = "0" * 40
# A pre-push hook may run with GIT_DIR set; a test repository must not inherit it.
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


@pytest.fixture
def repo(tmp_path):
    if shutil.which("git") is None or shutil.which("bash") is None:
        pytest.skip("needs git and bash")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=CLEAN_ENV)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check.sh").write_text('echo ran > "$(dirname "$0")/ran.txt"\nexit "${STAND_IN_EXIT:-0}"\n',
                                                  encoding="utf-8", newline="\n")
    return tmp_path


def push(repo, lines, code=0):
    env = dict(CLEAN_ENV, STAND_IN_EXIT=str(code))
    return subprocess.run(["bash", HOOK, "origin", "https://example.invalid/r.git"], input=lines, text=True,
                          capture_output=True, cwd=repo, env=env)


def test_a_push_with_commits_runs_the_check_and_keeps_its_exit_code(repo):
    line = f"refs/heads/topic {'a' * 40} refs/heads/topic {ZEROS}\n"
    assert push(repo, line).returncode == 0
    assert (repo / "scripts" / "ran.txt").exists()
    (repo / "scripts" / "ran.txt").unlink()
    assert push(repo, line, code=1).returncode == 1
    assert (repo / "scripts" / "ran.txt").exists()


def test_no_lines_runs_the_check_as_git_hook_run_does(repo):
    assert push(repo, "", code=1).returncode == 1
    assert (repo / "scripts" / "ran.txt").exists()


def test_a_push_that_only_deletes_branches_runs_no_check(repo):
    lines = f"(delete) {ZEROS} refs/heads/old-1 {'b' * 40}\n(delete) {ZEROS} refs/heads/old-2 {'c' * 40}\n"
    result = push(repo, lines, code=1)
    assert result.returncode == 0 and "only deletes remote branches" in result.stdout
    assert not (repo / "scripts" / "ran.txt").exists()


def test_a_push_that_deletes_one_branch_and_sends_another_runs_the_check(repo):
    lines = f"(delete) {ZEROS} refs/heads/old {'b' * 40}\nrefs/heads/new {'d' * 40} refs/heads/new {ZEROS}\n"
    assert push(repo, lines, code=1).returncode == 1
