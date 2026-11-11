"""Tests for scripts/check.sh itself: it clears inherited GIT_* variables before any check runs, so a test
that builds a temporary repository cannot reach this one from the pre-push hook (the earlier change incident)."""
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check.sh")
# The bash on PATH. On Windows a program started by the bare name "bash" is looked for in the system folder first,
# and the bash.exe there starts the Linux subsystem, not Git Bash.
BASH = shutil.which("bash") or "bash"


def _lines():
    with open(CHECK, encoding="utf-8") as f:
        return f.read().split("\n")


def _guard():
    return next(line for line in _lines() if "compgen -e" in line and "GIT_" in line)


def test_the_guard_clears_every_git_variable():
    env = dict(os.environ, GIT_DIR="/nonexistent", GIT_WORK_TREE="/nonexistent", GIT_INDEX_FILE="/nonexistent/i",
               GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.bare", GIT_CONFIG_VALUE_0="true")
    script = "set -euo pipefail\n" + _guard() + "\nenv | grep -c '^GIT_' || true\n"
    out = subprocess.run([BASH, "-c", script], env=env, capture_output=True, text=True, check=True, encoding="utf-8").stdout
    assert out.strip() == "0"


def test_the_guard_runs_before_the_first_check():
    lines = _lines()
    guard = lines.index(_guard())
    first = next(i for i, line in enumerate(lines) if line.startswith('before="$(snapshot)"'))
    assert guard < first


# Plan 2 (codebase architecture, 2026-10-30): check.sh lists its module verifies and test files by hand, and
# nothing stopped a new module or test file from being left out. These tests make the lists complete.

def _modules():
    """The module names build_module.py's MODULES table declares, read without importing it."""
    import ast
    path = os.path.join(HERE, "..", "business_architecture", "ontology", "release", "build_module.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    table = next(n.value for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "MODULES" for t in n.targets))
    return [k.value for k in table.keys]


def _commands():
    """check.sh's executable text: every comment dropped, whole-line or after a command (a # that starts a word, as
    after a space or a control operator such as ;, &, | or a bracket; no command in check.sh quotes one), and $step4
    written out, so every path reads in full."""
    import re
    code = [re.sub(r"(^|[\s;&|()<>])#.*$", r"\1", line) for line in _lines()]
    return "\n".join(code).replace("$step4", "business_architecture/ontology/step4")


def test_every_module_release_is_verified():
    text = _commands()
    missing = [m for m in _modules() if f"build_module.py {m} --verify" not in text]
    assert _modules() and not missing, missing


def test_every_tracked_test_file_is_run():
    root = os.path.join(HERE, "..")
    if os.path.exists(os.path.join(root, ".git")):  # a folder, or a file in a worktree
        files = subprocess.run(["git", "ls-files", "*test_*.py"], cwd=root, capture_output=True, text=True,
                               check=True, encoding="utf-8").stdout.split()
    else:  # a tree without Git: every test file in it
        files = sorted(os.path.relpath(os.path.join(r, f), root).replace(os.sep, "/") for r, ds, fs in os.walk(root) for f in fs
                       if f.startswith("test_") and f.endswith(".py") and "__pycache__" not in r and ".venv" not in r)
    # The skills' tests (skills/<name>/scripts/) run by module name in the script's own section, not by path.
    files = [f for f in files if not f.startswith("skills/")]
    text = _commands()
    missing = [f for f in files if f not in text]  # by its full path, in a command, not in a comment
    assert files and not missing, missing


def _run_tests_function():
    """check.sh's run_tests function, as text."""
    lines = _lines()
    start = next(i for i, line in enumerate(lines) if line.startswith("run_tests() {"))
    return "\n".join(lines[start:lines.index("}", start) + 1])


def _call_run_tests(command):
    script = "set -euo pipefail\n" + _run_tests_function() + f"\n(run_tests bash -c '{command}')\necho after\n"
    return subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8")


def test_a_failed_test_command_prints_its_output_and_stops_the_script():
    """The output was lost: the script ended at the failed command, before the line that prints it."""
    done = _call_run_tests("echo Ran 3 tests in 1s; echo the reason; exit 4")
    assert done.returncode == 1 and "the reason" in done.stdout and "after" not in done.stdout


def test_a_test_command_that_ran_no_test_fails_and_one_that_ran_some_passes():
    assert _call_run_tests("echo Ran 0 tests in 0s").returncode == 1
    done = _call_run_tests("echo Ran 3 tests in 1s")
    assert done.returncode == 0 and done.stdout.endswith("after\n")


def _find_python(tmp_path, exits):
    """Runs check.sh's search for a Python with stand-ins first on PATH: {name: the exit status of that stand-in}."""
    lines = _lines()
    start = lines.index('PYTHON=""')
    end = next(i for i, line in enumerate(lines) if line.startswith('[ -n "$PYTHON" ]'))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, status in exits.items():
        stand_in = bin_dir / name
        stand_in.write_text(f"#!/bin/sh\nexit {status}\n", encoding="utf-8", newline="\n")
        stand_in.chmod(0o755)
    # cd and pwd give the folder as bash names it; under Git Bash that is /c/..., which PATH needs.
    script = 'PATH="$(cd "$1" && pwd):$PATH"\n' + "\n".join(lines[start:end + 1]) + '\necho "$PYTHON"\n'
    return subprocess.run([BASH, "-c", script, "find-python", str(bin_dir)], capture_output=True, text=True, encoding="utf-8")


def test_the_script_takes_the_first_python_that_runs(tmp_path):
    """Windows may hold a python3.exe that only opens the Store. A name counts only when it runs."""
    done = _find_python(tmp_path, {"python3": 9, "python": 0, "py": 0})
    assert (done.returncode, done.stdout) == (0, "python\n")


def test_the_script_stops_when_no_python_runs(tmp_path):
    done = _find_python(tmp_path, {"python3": 9, "python": 1, "py": 1})
    assert done.returncode == 1 and done.stdout == ""
    assert done.stderr == "no Python 3.11 or later was found: tried python3, python and py\n"
