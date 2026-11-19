"""Tests for scripts/doc_snippets.py, which tests every code block in the Markdown documents and in the HTML
pages written by hand.

Each test writes a small document by hand into a temporary folder and checks what the tool says about it. The
last tests read this tree: its registry, its documents and their tags. scripts/check.sh runs the blocks of the
tree itself with `doc_snippets.py check`, which prints the count.

Run: uv run --no-project --with pytest --with rdflib --with pyyaml --with sqlglot python -m pytest -q scripts/test_doc_snippets.py
"""
import hashlib
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc_snippets as d  # noqa: E402

REGISTRY = """
temporary_reasons = ["awaits-the-rewrite"]

[reasons]
needs-client-server = "x"
illustration = "x"
awaits-the-rewrite = "x"

[contexts.scratch]
base = "empty"

[contexts.other]
base = "empty"

[contexts.copy]
base = "release-copy"

[contexts.repo]
base = "release-copy"
git = true

[contexts.gated]
base = "empty"
needs_env = ["DOC_TEST_GATE"]
[contexts.gated.placeholders]
"your name" = "env:DOC_TEST_NAME"
"a word" = "plain"

[contexts.quick]
base = "empty"
timeout = 1

[contexts.signed-in]
base = "empty"
home = "real"

[contexts.settings]
base = "empty"
needs_env = ["DOC_TEST_SETTINGS_FILE"]
[contexts.settings.set_env]
DOC_TEST_LOCAL = "env:DOC_TEST_SETTINGS_FILE"
DOC_TEST_FIXED = "fixed text"
"""


@pytest.fixture(autouse=True)
def not_started_by_a_block(monkeypatch):
    """scripts/check.sh may itself be started by a block of a document, and then the environment says so. These
    tests check the tool as a person starts it, so each one begins without those two variables."""
    monkeypatch.delenv(d.NESTED, raising=False)
    monkeypatch.delenv(d.NESTED_FILE, raising=False)


def fence(info, *body):
    return "\n".join(["```" + info, *body, "```", ""])


def check(tmp_path, text, *, files=None, environ=None, registry=REGISTRY, doc="guide.md", **options):
    """Check one hand-written document, guide.md, in a temporary tree."""
    root = tmp_path / "tree"
    root.mkdir(exist_ok=True)
    (root / doc).write_text(text, encoding="utf-8", newline="\n")
    for name, content in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content, encoding="utf-8", newline="\n")
    (tmp_path / "registry.toml").write_text(registry, encoding="utf-8", newline="\n")
    env = {k: v for k, v in os.environ.items() if k not in (d.NESTED, d.NESTED_FILE)}
    env.update(environ or {})
    checker = d.Checker(root, d.load_registry(tmp_path / "registry.toml"), environ=env, **options)
    return checker.check([doc])


def page(*lines):
    """A hand-written page, guide.html, whose body is these lines. The first of them is line 4 of the page."""
    return "\n".join(["<!DOCTYPE html>", "<html><head><title>Guide</title></head>", "<body>", *lines,
                      "</body></html>", ""])


def check_page(tmp_path, *lines, **options):
    return check(tmp_path, page(*lines), doc="guide.html", **options)


def snapshot(root: Path):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


# -- every block is tagged


def test_a_block_with_no_tag_fails_with_its_document_and_line(tmp_path):
    result = check(tmp_path, "# Guide\n\n" + fence("", "echo hello") + "\n" + fence("bash", "echo hello"))
    assert result.failures == ["guide.md:3: the block has no language and no tag",
                               "guide.md:7: the block has no tag after its language `bash`"]
    assert result.summary() == "2 blocks: 0 run (0 status-only), 0 checked, 0 skipped, 2 failed"


def test_an_unknown_tag_fails(tmp_path):
    result = check(tmp_path, fence("bash runs", "echo hello"))
    assert result.failures == ["guide.md:1: unknown tag `runs`: use one of run, expect, skip, file, excerpt, "
                               "usage, parse, nested"]


def test_a_block_in_a_list_a_tilde_fence_and_an_open_fence_are_all_seen(tmp_path):
    text = "1. Step.\n\n   ```text\n   indented\n   ```\n\n~~~\ntilde\n~~~\n\n> ```sh\n> quoted\n> ```\n\n```text\nnever closed\n"
    result = check(tmp_path, text)
    assert result.failures == [
        "guide.md:3: the block has no tag after its language `text`",
        "guide.md:7: the block has no language and no tag",
        "guide.md:11: a code block inside a block quote cannot be tested; move it out of the quote",
        "guide.md:15: the code block is never closed"]


def test_inline_code_that_starts_a_line_with_three_backticks_is_not_a_block(tmp_path):
    result = check(tmp_path, "```bash run``` is how a tag looks.\n\n" + fence("json parse", "{}"))
    assert result.failures == [] and result.summary() == "1 blocks: 0 run (0 status-only), 1 checked, 0 skipped"


def test_an_attribute_a_tag_does_not_take_fails(tmp_path):
    result = check(tmp_path, fence("json parse exit=2", "{}") + fence("python run=scratch quickly", "pass"))
    assert result.failures == ["guide.md:1: `exit` is not something a `parse` block takes",
                               "guide.md:4: `quickly` is not something a `run` block takes"]


# -- run


def test_a_run_block_runs_and_is_counted(tmp_path):
    result = check(tmp_path, fence("python run=scratch status-only", "print(6 * 7)"))
    assert result.failures == [] and result.summary() == "1 blocks: 1 run (1 status-only), 0 checked, 0 skipped"


def test_a_run_block_needs_an_expect_block_or_the_word_status_only(tmp_path):
    """Without this rule a block that prints the wrong thing passes on its exit status alone."""
    bare = check(tmp_path, fence("python run=scratch", "print('unexpected')"))
    assert bare.failures == ["guide.md:1: nothing checks what this block prints. Put an `expect` block right after "
                             "it, or add `status-only` to say that only its exit status counts"]
    assert bare.summary() == "1 blocks: 0 run (0 status-only), 0 checked, 0 skipped, 1 failed"
    both = check(tmp_path, fence("python run=scratch status-only", "print(1)") + fence("text expect", "1"))
    assert both.failures[0] == "guide.md:1: the block says `status-only`, but an expect block follows it. Keep one"
    apart = check(tmp_path, fence("python run=scratch", "print(1)") + fence("json parse", "{}")
                  + fence("text expect", "1"))
    assert apart.failures[0].startswith("guide.md:1: nothing checks what this block prints")
    mixed = check(tmp_path, fence("python run=scratch", "print(1)") + fence("text expect", "1")
                  + fence("python run=scratch status-only", "print(2)"))
    assert mixed.failures == [] and mixed.summary() == "3 blocks: 2 run (1 status-only), 1 checked, 0 skipped"


def test_a_failing_run_block_fails_with_its_document_line_and_output(tmp_path):
    text = "# Guide\n\n" + fence("python run=scratch status-only", "print('before the error')", "raise SystemExit(3)")
    result = check(tmp_path, text)
    assert result.failures == ["guide.md:3: the block ended with exit status 3, not 0 (context scratch)\n"
                               "    | before the error"]
    assert result.summary() == "1 blocks: 0 run (0 status-only), 0 checked, 0 skipped, 1 failed"


def test_a_bash_block_stops_at_its_first_failing_command(tmp_path):
    result = check(tmp_path, fence("bash run=scratch status-only", "echo one", "false", "echo two"))
    assert result.failures == ["guide.md:1: the block ended with exit status 1, not 0 (context scratch)\n    | one"]


def test_a_run_block_may_expect_another_exit_status(tmp_path):
    good = check(tmp_path, fence("python run=scratch exit=2 status-only", "raise SystemExit(2)"))
    assert good.failures == []
    bad = check(tmp_path, fence("python run=scratch exit=2 status-only", "pass"))
    assert bad.failures == ["guide.md:1: the block ended with exit status 0, not 2 (context scratch)\n    | (no output)"]


def test_a_run_block_may_say_what_the_reader_types_at_its_prompts(tmp_path):
    ask = ['name = input("Type the new name to confirm: ")', 'answer = input("Type yes to cut: ")', "print()",
           "print('typed', name, 'and', answer)"]
    shown = fence("text expect", "Type the new name to confirm: Type yes to cut:", "typed Change_Value_Amount and yes")
    text = (fence('python run=scratch types="Change_Value_Amount,yes"', *ask) + shown
            + fence('powershell run=copy types="Change_Value_Amount,yes"', "python -c \"print('first line')\"", "python ask.py")
            + fence("text expect", "first line", "Type the new name to confirm: Type yes to cut:",
                    "typed Change_Value_Amount and yes"))
    result = check(tmp_path, text, files={"ask.py": "\n".join(ask) + "\n"})
    assert result.failures == [] and result.summary() == "4 blocks: 2 run (0 status-only), 2 checked, 0 skipped"
    # With no types= a prompt gets no answer, as before: the block fails where it asks.
    silent = check(tmp_path, fence("python run=scratch status-only", *ask))
    assert len(silent.failures) == 1 and "EOFError" in silent.failures[0]
    empty = check(tmp_path, fence('python run=scratch status-only types="yes,,no"', "pass"))
    assert empty.failures == ["guide.md:1: types= holds what the reader types at each prompt, with commas between the answers"]


def test_a_run_block_needs_a_known_context_and_a_language_that_runs(tmp_path):
    text = (fence("python run status-only", "pass") + fence("python run=nowhere status-only", "pass")
            + fence("json run=scratch status-only", "{}"))
    result = check(tmp_path, text)
    assert result.failures == [
        "guide.md:1: a run block names its context: `run=<context>` (one of copy, gated, other, quick, repo, scratch, settings, signed-in)",
        "guide.md:4: no context named `nowhere` in doc_snippets.toml: use one of copy, gated, other, quick, repo, "
        "scratch, settings, signed-in",
        "guide.md:7: a `json` block cannot run in the context `scratch`: `run` takes bash, sh, python, powershell, cmd, "
        "and a language the context names a program for"]


def test_a_block_that_runs_too_long_is_stopped(tmp_path):
    result = check(tmp_path, fence("python run=quick status-only", "import time", "time.sleep(30)"))
    assert result.failures == ["guide.md:1: the block ran past its time limit of 1 seconds (context quick)\n"
                               "    | (no output)"]


# -- contexts


def test_blocks_of_one_context_run_in_order_in_one_folder(tmp_path):
    text = (fence("bash run=scratch status-only", "echo first > made.txt")
            + fence("python run=scratch", "print(open('made.txt').read().strip(), 'then second')")
            + fence("text expect", "first then second"))
    result = check(tmp_path, text)
    assert result.failures == [] and result.summary() == "3 blocks: 2 run (1 status-only), 1 checked, 0 skipped"


def test_two_contexts_do_not_share_a_folder(tmp_path):
    text = (fence("bash run=scratch status-only", "echo first > made.txt")
            + fence("python run=other", "import os", "print(sorted(os.listdir('.')), 'is all')")
            + fence("text expect", "[] is all"))
    assert check(tmp_path, text).failures == []


def test_a_later_bash_block_starts_in_the_folder_the_earlier_one_left(tmp_path):
    text = (fence("bash run=scratch status-only", "mkdir inner", "cd inner") + fence("bash run=scratch", "basename \"$PWD\"")
            + fence("text expect", "inner"))
    assert check(tmp_path, text).failures == []


def test_only_a_define_block_gives_later_blocks_its_variables_and_functions(tmp_path):
    kept = (fence("bash run=scratch define status-only", "NAME=store", "greet() { echo \"hello $1\"; }")
            + fence("bash run=scratch", "greet \"$NAME\"") + fence("text expect", "hello store"))
    assert check(tmp_path, kept).failures == []
    lost = fence("bash run=scratch status-only", "NAME=store") + fence("bash run=scratch status-only", "echo \"$NAME\"")
    failures = check(tmp_path, lost).failures
    assert len(failures) == 1 and failures[0].startswith("guide.md:4: the block ended with exit status 1, not 0")
    assert "NAME: unbound variable" in failures[0]


def test_a_define_block_may_name_several_contexts(tmp_path):
    text = (fence("bash run=scratch,other define status-only", "WORD=shared") + fence("bash run=scratch", "echo \"$WORD\" one")
            + fence("text expect", "shared one") + fence("bash run=other", "echo \"$WORD\" two")
            + fence("text expect", "shared two"))
    assert check(tmp_path, text).failures == []
    result = check(tmp_path, fence("bash run=scratch,other status-only", "echo no"))
    assert result.failures == ["guide.md:1: only a `define` block may name more than one context"]


def test_after_a_failure_the_later_blocks_of_that_context_fail_without_running(tmp_path):
    text = (fence("python run=scratch status-only", "raise SystemExit(1)")
            + fence("python run=scratch status-only", "open('ran.txt', 'w').close()")
            + fence("python run=other status-only", "print('another context still runs')"))
    result = check(tmp_path, text)
    assert result.failures[1] == "guide.md:4: not run: the block at line 1 of the same context failed"
    assert result.summary() == "3 blocks: 1 run (1 status-only), 0 checked, 0 skipped, 2 failed"


def test_a_release_copy_holds_the_tree_and_a_git_copy_holds_one_commit(tmp_path):
    text = (fence("python run=copy", "print(open('data/a.txt').read())") + fence("text expect", "from the tree")
            + fence("bash run=repo", "git log --format=%s", "git status --short") + fence("text expect", "The release as received"))
    assert check(tmp_path, text, files={"data/a.txt": "from the tree\n"}).failures == []


def test_a_context_that_is_off_is_counted_and_all_contexts_makes_it_a_failure(tmp_path):
    text = fence("python run=gated", "print('<a word>')") + fence("text expect", "plain")
    off = check(tmp_path, text)
    assert off.failures == []
    assert off.summary() == "2 blocks: 0 run (0 status-only), 0 checked, 2 skipped (context gated is off (set DOC_TEST_GATE) 2)"
    on = check(tmp_path, text, environ={"DOC_TEST_GATE": "1"})
    assert on.failures == [] and on.summary() == "2 blocks: 1 run (0 status-only), 1 checked, 0 skipped"
    required = check(tmp_path, text, all_contexts=True)
    assert required.failures[0] == "guide.md:1: the context `gated` cannot run: set DOC_TEST_GATE"


def test_a_block_does_not_see_the_variables_of_another_context(tmp_path):
    text = fence("python run=scratch", "import os", "print('gate:', os.environ.get('DOC_TEST_GATE'))") \
        + fence("text expect", "gate: None")
    assert check(tmp_path, text, environ={"DOC_TEST_GATE": "secret"}).failures == []


def test_a_context_sets_variables_for_its_blocks_and_no_other_context_gets_them(tmp_path):
    show = "import os; print(os.environ.get('DOC_TEST_LOCAL'), os.environ.get('DOC_TEST_FIXED'))"
    text = (fence("python run=settings", show) + fence("text expect", "prepared.toml fixed text")
            + fence("python run=scratch", show) + fence("text expect", "None None"))
    # The reader's own value of the variable must not reach a block of another context.
    result = check(tmp_path, text, environ={"DOC_TEST_SETTINGS_FILE": "prepared.toml", "DOC_TEST_LOCAL": "the-readers-own.toml"})
    assert result.failures == [] and result.ran == 2 and result.checked == 2


def test_a_check_started_by_a_block_runs_no_block_and_says_so(tmp_path):
    """The running check hands its blocks a random value and a file that holds it. Here a block starts the check
    again on the same tree: the second check must run nothing, or it would start a third."""
    tool = str(d.ROOT / "scripts" / "doc_snippets.py")
    text = (fence("python run=scratch", "import os, subprocess, sys",
                  f"r = subprocess.run([sys.executable, {tool!r}, '--root', {str(tmp_path / 'tree')!r}, 'check'],",
                  "                   capture_output=True, text=True)", "print(r.stdout + 'exit ' + str(r.returncode))")
            + fence("text expect", "3 blocks: 0 run (0 status-only), 1 checked, 2 skipped (not run: a check started by a "
                                   "block runs no block 2)",
                    "this check was started by a block of another check, so it ran no block", "exit 0")
            + fence("json parse", "{}"))
    result = check(tmp_path, text)
    assert result.failures == [] and result.summary() == "3 blocks: 1 run (0 status-only), 2 checked, 0 skipped"
    assert not result.nested


def test_the_nested_variable_alone_never_turns_the_check_off(tmp_path):
    """Set by hand, or left over from a check that has ended, the variable once made the check run nothing and
    exit 0. Now it is an error, with every option."""
    text = fence("python run=scratch status-only", "raise SystemExit(1)")
    message = ["the variable DOC_SNIPPETS_NESTED is set, but no running check started this one. Unset it and run "
               "the check again: it runs nothing only when a block of another check starts it"]
    gone = tmp_path / "gone" / "nested-token"
    for environ in ({d.NESTED: "1"}, {d.NESTED: "abc", d.NESTED_FILE: str(gone)}):
        for options in ({}, {"all_contexts": True}, {"static": True}):
            result = check(tmp_path, text, environ=environ, **options)
            assert result.failures == message, (environ, options)
            assert result.summary() == "0 blocks: 0 run (0 status-only), 0 checked, 0 skipped"
    wrong = tmp_path / "nested-token"
    wrong.write_text("another value", encoding="utf-8", newline="\n")
    assert check(tmp_path, text, environ={d.NESTED: "abc", d.NESTED_FILE: str(wrong)}).failures == message
    wrong.write_text("abc", encoding="utf-8", newline="\n")
    proved = check(tmp_path, text, environ={d.NESTED: "abc", d.NESTED_FILE: str(wrong)})
    assert proved.failures == [] and proved.nested
    assert proved.skipped == {"not run: a check started by a block runs no block": 1}


# -- the release the examples describe

CATALOG = "releases/catalog.ttl"


def describing(catalog_text):
    """The test registry, saying that the examples describe the release whose catalog holds this text."""
    return REGISTRY + f'\n[describes]\nfile = "{CATALOG}"\nsha256 = "{hashlib.sha256(catalog_text.encode()).hexdigest()}"\n'


# A block that fails when it runs, and the output it would have to print. On the release the documents describe
# both count as failed. On any other release neither is run or compared.
WOULD_FAIL = fence("python run=scratch", "raise SystemExit('the example shows another version')") + fence("text expect", "version 1.2.0")


def test_on_the_release_the_examples_describe_the_check_runs_every_block(tmp_path):
    text = fence("python run=scratch", "print('version 1.2.0')") + fence("text expect", "version 1.2.0")
    for catalog in ("one release\n", "one release\r\n"):   # a checkout on Windows gives the same digest
        (tmp_path / "tree" / "releases").mkdir(parents=True, exist_ok=True)
        (tmp_path / "tree" / CATALOG).write_bytes(catalog.encode())
        result = check(tmp_path, text, registry=describing("one release\n"))
        assert result.failures == [] and (result.ran, result.checked) == (1, 1) and not result.release_changed
    assert len(check(tmp_path, WOULD_FAIL, registry=describing("one release\n")).failures) == 2
    # A folder with no catalog holds no release to compare, so the check runs as it always did.
    (tmp_path / "tree" / CATALOG).unlink()
    assert len(check(tmp_path, WOULD_FAIL, registry=describing("one release\n")).failures) == 2


def test_on_a_changed_release_the_check_runs_no_block_and_still_parses(tmp_path):
    """After a correction or a new version the catalog differs. An example may then rightly show something else,
    so the default check parses and compares files, runs nothing and says so."""
    text = WOULD_FAIL + fence("json parse", "{}") + fence("json parse", "{not json")
    result = check(tmp_path, text, files={CATALOG: "a correction version\n"}, registry=describing("one release\n"))
    assert result.release_changed and not result.nested
    assert result.failures[0].startswith("guide.md:10: the block is not valid json") and len(result.failures) == 1
    assert (result.ran, result.checked, result.failed_blocks) == (0, 1, 1)
    assert result.skipped == {"not run: the release changed since the documents were written": 2}


def test_on_a_changed_release_the_strict_check_fails_and_still_runs_the_blocks(tmp_path):
    then, now = hashlib.sha256(b"one release\n").hexdigest(), hashlib.sha256(b"a correction version\n").hexdigest()
    result = check(tmp_path, WOULD_FAIL, files={CATALOG: "a correction version\n"}, registry=describing("one release\n"), strict=True)
    assert result.failures[0] == (f"the documents' examples describe another release than this one: the registry holds {then} and "
                                  f"{CATALOG} gives {now}. Bring the examples up to date with this release, then run: "
                                  "python scripts/doc_snippets.py describe-release --write")
    assert len(result.failures) == 3 and not result.release_changed   # the builder also sees each example to change


def test_the_command_says_that_the_release_changed_and_exits_0(tmp_path, capsys):
    (tmp_path / "releases").mkdir()
    (tmp_path / CATALOG).write_text("a correction version\n", encoding="utf-8", newline="\n")
    (tmp_path / "guide.md").write_text(WOULD_FAIL, encoding="utf-8", newline="\n")
    registry = tmp_path / "registry.toml"
    registry.write_text(describing("one release\n"), encoding="utf-8", newline="\n")
    assert d.main(["--root", str(tmp_path), "check", "guide.md"], registry_path=registry) == 0
    assert capsys.readouterr().out == (
        "2 blocks: 0 run (0 status-only), 0 checked, 2 skipped (not run: the release changed since the documents were written 2)\n"
        "note: the release changed since the documents were written, so this check ran no block. An example may show a version "
        "or a count of the release as it was then. scripts/DOC-SNIPPETS.md says how to bring the examples up to date "
        "(\"The release the examples describe\").\n")
    assert d.main(["--root", str(tmp_path), "check", "--strict", "guide.md"], registry_path=registry) == 1


def test_describe_release_says_whether_the_digest_is_this_releases_and_writes_it_on_request(tmp_path, capsys):
    (tmp_path / "releases").mkdir()
    (tmp_path / CATALOG).write_text("a correction version\n", encoding="utf-8", newline="\n")
    registry = tmp_path / "registry.toml"
    registry.write_text(describing("one release\n"), encoding="utf-8", newline="\n")
    now = hashlib.sha256(b"a correction version\n").hexdigest()
    args = ["--root", str(tmp_path), "describe-release"]
    for flags in ([], ["--check"]):
        assert d.main(args + flags, registry_path=registry) == 1
        assert capsys.readouterr().out.startswith("FAIL the documents' examples describe another release: registry.toml holds ")
    assert registry.read_text(encoding="utf-8") == describing("one release\n")   # nothing was written
    assert d.main(args + ["--write"], registry_path=registry) == 0
    assert capsys.readouterr().out == f"wrote {now} to registry.toml: the documents' examples now describe this release\n"
    # Only the digest changed, and the file keeps LF line ends.
    assert registry.read_bytes() == describing("a correction version\n").encode()
    for flags in ([], ["--check"], ["--write"]):
        assert d.main(args + flags, registry_path=registry) == 0
        assert capsys.readouterr().out == f"the documents' examples describe this release ({CATALOG}, SHA-256 {now})\n"
    # A folder with no catalog, and a registry that names no release, are both said plainly.
    (tmp_path / CATALOG).unlink()
    assert d.main(args, registry_path=registry) == 1
    assert capsys.readouterr().out == f"FAIL the file {CATALOG} does not exist, so this folder holds no release to describe\n"
    registry.write_text(REGISTRY, encoding="utf-8", newline="\n")
    assert d.main(args + ["--write"], registry_path=registry) == 1
    assert capsys.readouterr().out == "FAIL registry.toml has no [describes] table, so it names no release\n"


def test_a_describes_table_needs_a_relative_file_and_a_digest(tmp_path):
    path = tmp_path / "r.toml"
    for table, why in (('file = "catalog.ttl"\n', "needs file"), ('file = "/catalog.ttl"\nsha256 = "' + "0" * 64 + '"\n', "needs file"),
                       ('file = "C:/catalog.ttl"\nsha256 = "' + "0" * 64 + '"\n', "needs file"),
                       ('file = "../catalog.ttl"\nsha256 = "' + "0" * 64 + '"\n', "needs file"),
                       ('file = "catalog.ttl"\nsha256 = "ABC"\n', "sha256 must be 64 hexadecimal digits"),
                       ('file = "catalog.ttl"\nsha256 = "' + "0" * 64 + '"\nmore = 1\n', "needs file")):
        path.write_text("[describes]\n" + table, encoding="utf-8", newline="\n")
        with pytest.raises(d.RegistryError, match=why):
            d.load_registry(path)


def test_the_registry_describes_the_release_as_shipped():
    """Pinned (scripts/pinned-tests.txt): the digest in the registry is this release's, so the check of the release
    as shipped runs every block. After a correction or a new version it differs, and scripts/check.sh then runs no
    block. A release cannot be built with a stale digest, because scripts/check-pinned.sh runs this test."""
    registry = d.load_registry()
    assert registry.describes == "business_architecture/ontology/releases/catalog.ttl"
    assert d.release_digest(d.ROOT, registry) == registry.sha256, (
        "the documents' examples describe another release. Bring them up to date, then run: "
        "python scripts/doc_snippets.py describe-release --write")


def test_the_static_check_runs_nothing_but_still_reads_the_tags(tmp_path):
    text = fence("python run=scratch status-only", "raise SystemExit(1)") + fence("python run=nowhere status-only", "pass")
    result = check(tmp_path, text, static=True)
    assert len(result.failures) == 1 and result.failures[0].startswith("guide.md:4: no context named `nowhere`")
    assert result.skipped == {"not run: static check": 1}


# -- nothing is written to the tree or to the home folder


def test_in_a_context_with_a_temporary_home_a_block_writes_to_its_copy_and_that_home(tmp_path):
    marker = f".doc-snippets-test-{uuid.uuid4().hex}"
    in_home = "~" + "/" + marker        # written in two parts: the stand-alone check refuses a home path in a file
    text = (fence("bash run=copy", "echo changed > data/a.txt", "echo new > data/b.txt", f"echo home > {in_home}",
                  "cat data/a.txt")
            + fence("text expect", "changed")
            + fence("python run=copy", "import pathlib", f"print((pathlib.Path.home() / '{marker}').read_text())")
            + fence("text expect", "home"))
    root = tmp_path / "tree"
    root.mkdir()
    (root / "data").mkdir()
    (root / "data" / "a.txt").write_text("from the tree\n", encoding="utf-8", newline="\n")
    (root / "guide.md").write_text(text, encoding="utf-8", newline="\n")
    before = snapshot(root)
    result = check(tmp_path, text)
    assert result.failures == [] and result.ran == 2
    assert snapshot(root) == before
    assert (root / "data" / "a.txt").read_text(encoding="utf-8") == "from the tree\n"
    assert not (Path.home() / marker).exists()


def test_the_tool_leaves_no_python_cache_in_the_tree(tmp_path):
    """The Cypher check imports the tokenizer from the tree. Run as a command, with nothing set to stop it, Python
    would write a cache folder beside that module."""
    import shutil
    import subprocess
    tree = tmp_path / "tree"
    shutil.copytree(d.ROOT / "kpi_store" / "questions", tree / "kpi_store" / "questions",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(d.ROOT / "kpi_store" / "__init__.py", tree / "kpi_store" / "__init__.py")
    (tree / "scripts").mkdir()
    for name in ("doc_snippets.py", "doc_snippets.toml"):
        shutil.copy(d.ROOT / "scripts" / name, tree / "scripts" / name)
    shutil.copytree(d.ROOT / "scripts" / "doc_snippets_parts", tree / "scripts" / "doc_snippets_parts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (tree / "guide.md").write_text(fence("cypher parse", "MATCH (n) RETURN n"), encoding="utf-8", newline="\n")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONDONTWRITEBYTECODE", d.NESTED, d.NESTED_FILE)}
    r = subprocess.run([sys.executable, str(tree / "scripts" / "doc_snippets.py"), "check"], cwd=tree, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.stdout == "1 blocks: 0 run (0 status-only), 1 checked, 0 skipped\n", r.stdout + r.stderr
    assert [p.as_posix() for p in tree.rglob("__pycache__")] == []


def test_a_context_that_keeps_the_real_home_gives_it_to_its_blocks(tmp_path):
    """The stated exception: a context with home = "real" does not protect the home folder."""
    home = tmp_path / "the-real-home"
    home.mkdir()
    text = (fence("python run=signed-in", "import pathlib", "print('home is', pathlib.Path.home().name)")
            + fence("text expect", "home is the-real-home")
            + fence("python run=scratch", "import pathlib", "print('home is', pathlib.Path.home().name)")
            + fence("text expect", "home is home"))
    result = check(tmp_path, text, environ={"HOME": str(home), "USERPROFILE": str(home)})
    assert result.failures == []


def test_a_block_cannot_find_the_tree_through_a_variable(tmp_path):
    """The check is started in the tree, so PWD named it, and a block that wrote to $PWD wrote into the tree."""
    root = tmp_path / "tree"
    text = (fence("python run=scratch", "import os, pathlib",
                  "pathlib.Path(os.environ['PWD'], 'escape-marker').write_text('x')",
                  "print('same folder:', os.path.samefile(os.environ['PWD'], os.getcwd()))",
                  "print('old folder:', os.environ.get('OLDPWD'))",
                  "print('tool home:', os.environ.get('SOME_TOOL_HOME'))",
                  "print('path kept:', 'PATH' in os.environ)")
            + fence("text expect", "same folder: True", "old folder: None", "tool home: None", "path kept: True"))
    environ = {"PWD": str(root), "OLDPWD": str(root), "SOME_TOOL_HOME": str(root / "tools")}
    result = check(tmp_path, text, environ=environ)
    assert result.failures == []
    assert sorted(p.name for p in root.iterdir()) == ["guide.md"]


def _can_link():
    """True when this account may make a symbolic link. On Windows that takes administrator rights or Developer Mode."""
    with tempfile.TemporaryDirectory() as folder:
        try:
            os.symlink("target", os.path.join(folder, "link"))
        except (OSError, NotImplementedError):
            return False
    return True


# Without the right to make a link, how the copy treats a link in the tree is not proven on this machine.
needs_links = pytest.mark.skipif(not _can_link(), reason="this account cannot make a symbolic link")


@needs_links
def test_a_link_inside_the_tree_is_copied_as_what_it_points_to(tmp_path):
    """Copied as a link, it pointed back into the tree, and a block that wrote through it changed the tree."""
    root = tmp_path / "tree"
    (root / "data").mkdir(parents=True)
    (root / "data" / "a.txt").write_text("from the tree\n", encoding="utf-8", newline="\n")
    os.symlink(root / "data" / "a.txt", root / "link.txt")
    os.symlink("data", root / "linked-folder")
    text = (fence("bash run=copy", "cat link.txt", "echo changed > link.txt", "echo changed > linked-folder/a.txt",
                  "cat data/a.txt")
            + fence("text expect", "from the tree", "from the tree"))
    result = check(tmp_path, text)
    assert result.failures == []
    assert (root / "data" / "a.txt").read_text(encoding="utf-8") == "from the tree\n"


@needs_links
def test_a_link_that_leads_outside_the_tree_is_refused(tmp_path):
    root = tmp_path / "tree"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not part of the release\n", encoding="utf-8", newline="\n")
    os.symlink(outside, root / "out.txt")
    result = check(tmp_path, fence("bash run=copy status-only", "echo changed > out.txt"))
    assert result.failures == ["guide.md:1: the link out.txt leads outside the release, so the release cannot be "
                               "copied"]
    assert outside.read_text(encoding="utf-8") == "not part of the release\n"


def test_a_block_does_not_get_the_checks_own_encoding_settings(tmp_path):
    """A reader on Windows has neither variable. A block that needs one must set it where the reader sees it."""
    text = (fence("python run=scratch", "import os",
                  "print('settings:', os.environ.get('PYTHONUTF8'), os.environ.get('PYTHONIOENCODING'))")
            + fence("text expect", "settings: None None"))
    assert check(tmp_path, text).failures == []
    assert check(tmp_path, text, environ={"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}).failures == []


@pytest.mark.skipif(os.name == "nt", reason="the POSIX half; on Windows taskkill stops the tree")
def test_a_stopped_block_does_not_keep_the_check_waiting_for_a_process_that_got_away(tmp_path, monkeypatch):
    """The block starts a process in its own session, which outlives the stop and holds the output pipe open.
    Reading the output with no limit waited for it."""
    import time
    from doc_snippets_parts import run
    monkeypatch.setattr(run, "DRAIN_SECONDS", 1)
    text = fence("python run=quick status-only", "import subprocess, sys, time",
                 "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(12)'], start_new_session=True)",
                 "time.sleep(30)")
    started = time.monotonic()
    result = check(tmp_path, text)
    assert time.monotonic() - started < 8
    assert result.failures == ["guide.md:1: the block ran past its time limit of 1 seconds (context quick)\n"
                               "    | (no output)"]


# -- code that is not in a fence


def test_a_code_block_indented_by_four_spaces_fails(tmp_path):
    text = "\n".join(["# Guide", "", "Run this:", "", "    python3 obsolete.py", "    python3 second-line.py", "",
                      "Then this, under a heading:", "", "## Next", "    python3 after-a-heading.py", "",
                      "- A step.", "", "      python3 inside-a-list-item.py", ""])
    result = check(tmp_path, text)
    assert result.failures == [
        "guide.md:5: a code block indented by four spaces cannot be tested; use a fenced block",
        "guide.md:11: a code block indented by four spaces cannot be tested; use a fenced block",
        "guide.md:15: a code block indented by four spaces cannot be tested; use a fenced block"]
    assert result.summary() == "3 blocks: 0 run (0 status-only), 0 checked, 0 skipped, 3 failed"


def test_indented_text_that_is_not_code_passes(tmp_path):
    text = "\n".join([
        "# Guide", "",
        "A paragraph whose second line", "    is indented by four spaces is still the paragraph.", "",
        "1. A step.", "", "   More text of the step.", "", "   - A point inside the step.", "",
        "     More text of the point, five spaces in.", "", "       Seven spaces in is still text of the point.", "",
        "10. A step with a wide number.", "", "    Its text starts four spaces in.", "",
        "- A point", "    whose wrapped line is indented.", "", "    - A point four spaces in is a nested point.", "",
        "| a | b |", "|---|---|", "", "<!--", "    a comment may hold anything", "-->", "",
        "   ```json parse", "   {}", "   ```", ""])
    result = check(tmp_path, text)
    assert result.failures == [] and result.summary() == "1 blocks: 0 run (0 status-only), 1 checked, 0 skipped"


def test_a_raw_html_code_block_fails(tmp_path):
    text = "\n".join(["# Guide", "", "<pre><code>python3 obsolete.py</code></pre>", "", "<code>", "python3 x.py",
                      "</code>", "", "A table cell may hold <pre>one</pre> too.", "",
                      "The words `<pre>` and `<code>` in code spans, and a <code>span</code> in a sentence, are text.",
                      ""])
    result = check(tmp_path, text)
    assert result.failures == ["guide.md:3: a raw HTML code block cannot be tested; use a fenced block",
                               "guide.md:5: a raw HTML code block cannot be tested; use a fenced block",
                               "guide.md:9: a raw HTML code block cannot be tested; use a fenced block"]


# -- expect


@pytest.mark.parametrize("expected,actual", [
    ("hello", "hello\n"),
    ("hello", "\n\nhello   \r\n\r\n"),                              # line ends, spaces at the end, blank edges
    ("hello", "\x1b[32mhello\x1b[0m"),                              # colour codes
    ("run <run id> took <time> s", "run 20261111-ab12cd34 took 0.42 s"),
    ("first\n...\nlast", "first\nlast"),                            # ... is any number of lines, also none
    ("first\n...\nlast", "first\na\nb\nc\nlast"),
    ("...\nall checks passed", "--- one\n--- two\nall checks passed"),
    ("a\n...\nb\n...\nc", "a\nx\nb\nb\nc"),
    ("wrote <path>\n...", "wrote /tmp/x/report.json"),
    # uv reports its own work on a machine that has not run the command before
    ("hello", "Resolved 3 packages in 12ms\nPrepared 2 packages in 1.04s\nInstalled 2 packages in 3ms\nhello"),
    ("hello", "Installed 1 package in 1ms\nhello"),
])
def test_output_that_matches(expected, actual):
    assert d.output_matches(expected, actual)


@pytest.mark.parametrize("expected,actual", [
    ("hello", "hullo"),
    ("hello", "hello\nand more"),
    ("hello\nworld", "hello"),
    ("  indented", "indented"),                                     # spaces at the start of a line count
    ("run <run id> done", "run  done"),                             # a placeholder is never empty
    ("run <run id>", "run 1\nrun 2"),                               # and never crosses a line
    ("first\n...\nlast", "first\nlast\nafter"),
    ("a.c", "abc"),                                                 # the text is literal, not a pattern
    ("hello", "Installed 2 parts in 3ms\nhello"),                   # only uv's own lines are left out
    ("hello", "note: Installed 2 packages in 3ms\nhello"),
    ("Installed 2 packages in 3ms\nhello", "Installed 2 packages in 3ms\nhello"),  # and never asked for
])
def test_output_that_differs(expected, actual):
    assert not d.output_matches(expected, actual)


@pytest.mark.parametrize("expected", ["", "\n\n", "...", "...\n...", "<output>", "<first line>\n...\n<last line>",
                                      "  <a>  <b>  "])
def test_an_expectation_with_no_text_of_its_own_matches_nothing(expected):
    """Each of these matched any output, so a block was counted as checked with nothing checked."""
    assert not d.has_fixed_text(expected)
    for actual in ("", "something else", "a\nb\nc"):
        assert not d.output_matches(expected, actual)


@pytest.mark.parametrize("body", [[], ["..."], ["<any output>"], ["...", "<the last line>"]])
def test_an_expect_block_with_no_text_of_its_own_fails(tmp_path, body):
    result = check(tmp_path, fence("python run=scratch", "print('anything')") + fence("text expect", *body))
    assert result.failures == ["guide.md:4: the expect block holds no text of its own, so it would match any output. "
                               "Give it at least one line with words that the output must hold"]
    assert result.summary() == "2 blocks: 1 run (0 status-only), 0 checked, 0 skipped, 1 failed"


def test_an_expect_block_that_differs_fails_with_both_texts(tmp_path):
    text = fence("python run=scratch", "print('loaded 12 triples')") + fence("text expect", "loaded 13 triples")
    result = check(tmp_path, text)
    assert result.failures == ["guide.md:4: the output of the block at line 1 is not what this block shows\n"
                               "    | --- expected\n    | +++ output\n    | @@ -1 +1 @@\n"
                               "    | -loaded 13 triples\n    | +loaded 12 triples"]
    assert result.summary() == "2 blocks: 1 run (0 status-only), 0 checked, 0 skipped, 1 failed"


def test_an_expect_block_must_follow_a_run_or_skip_block(tmp_path):
    text = fence("text expect", "alone") + fence("json parse", "{}") + fence("text expect", "after a parse")
    result = check(tmp_path, text)
    assert result.failures == [
        "guide.md:1: an expect block must come right after the `run` or `skip` block whose output it shows",
        "guide.md:7: an expect block must come right after the `run` or `skip` block whose output it shows"]


def test_an_expect_block_after_a_skipped_block_is_skipped_for_the_same_reason(tmp_path):
    text = fence('bash skip reason="needs-client-server: reads the client\'s workspace"', "databricks current-user me") \
        + fence("text expect", "someone")
    result = check(tmp_path, text)
    assert result.failures == [] and result.summary() == "2 blocks: 0 run (0 status-only), 0 checked, 2 skipped (needs-client-server 2)"


# -- skip


def test_a_skip_needs_an_allowed_reason_and_a_detail(tmp_path):
    text = (fence("bash skip", "a") + fence('bash skip reason="too slow: takes an hour"', "b")
            + fence('bash skip reason="illustration"', "c") + fence('bash skip reason="illustration: x"', "d")
            + fence('bash skip=illustration reason="illustration: a sketch of the flow"', "e")
            + fence('text skip reason="illustration: a sketch of the flow"', "f"))
    result = check(tmp_path, text)
    assert result.failures == [
        'guide.md:1: a skipped block needs reason="<reason>: <detail>"',
        "guide.md:4: `too slow` is not an allowed reason: use one of awaits-the-rewrite, illustration, "
        "needs-client-server",
        "guide.md:7: the reason `illustration` needs a detail after a colon, in a few words",
        "guide.md:10: the reason `illustration` needs a detail after a colon, in a few words",
        'guide.md:13: a skip is written `skip reason="<reason>: <detail>"`']
    assert result.skipped == {"illustration": 1}


def test_strict_refuses_a_temporary_reason(tmp_path):
    text = fence('bash skip reason="awaits-the-rewrite: the guide is rewritten next"', "old-command") \
        + fence('text skip reason="illustration: a sketch of the flow"', "a -> b")
    relaxed = check(tmp_path, text)
    assert relaxed.failures == [] and relaxed.skipped == {"awaits-the-rewrite": 1, "illustration": 1}
    strict = check(tmp_path, text, strict=True)
    assert strict.failures == ["guide.md:1: the reason `awaits-the-rewrite` is temporary and must be gone at the cut"]


# -- file, excerpt, parse


def test_a_file_block_must_equal_the_file(tmp_path):
    files = {"settings/example.toml": "[release]\nzip = \"a.zip\"\n"}
    same = check(tmp_path, fence("toml file=settings/example.toml", "[release]", 'zip = "a.zip"'), files=files)
    assert same.failures == [] and same.checked == 1
    drift = check(tmp_path, fence("toml file=settings/example.toml", "[release]", 'zip = "b.zip"'), files=files)
    assert drift.failures == ["guide.md:1: the block differs from settings/example.toml\n"
                              "    | --- settings/example.toml\n    | +++ the block\n    | @@ -1,2 +1,2 @@\n"
                              "    |  [release]\n    | -zip = \"a.zip\"\n    | +zip = \"b.zip\""]
    missing = check(tmp_path, fence("toml file=settings/none.toml", "x = 1"), files=files)
    assert missing.failures == ["guide.md:1: the file settings/none.toml does not exist"]
    outside = check(tmp_path, fence("toml file=../registry.toml", "x = 1"), files=files)
    assert outside.failures == ["guide.md:1: `../registry.toml` must be a path inside the release"]


def test_an_excerpt_block_must_be_lines_of_the_file_next_to_each_other(tmp_path):
    files = {"code.py": "def one():\n    return 1\n\n\ndef two():\n    return 2\n"}
    assert check(tmp_path, fence("python excerpt=code.py", "def two():", "    return 2"), files=files).failures == []
    result = check(tmp_path, fence("python excerpt=code.py", "def one():", "    return 2"), files=files)
    assert result.failures == ["guide.md:1: the lines are not in code.py, in this order and next to each other\n"
                               "    | the block starts: def one():\n    | the closest line: def one():"]


@pytest.mark.parametrize("lang,good,bad", [
    ("json", '{"format": 1}', '"format": 1'),
    ("toml", '[release]\nzip = "a.zip"', "[release\nzip"),
    ("yaml", "version: 1.1\nsource: a.b.c", "version: [1.1"),
    ("turtle", "@prefix ex: <https://example.org/> .\nex:a ex:b ex:c .", "ex:a ex:b ."),
    ("turtle", "kpi:a skos:prefLabel \"Margin\"@en .", "kpi:a skos:prefLabel"),     # prefixes may go undeclared
    ("sparql", "SELECT ?s WHERE { ?s ?p ?o }", "SELECT ?s WHERE { ?s ?p }"),
    ("sparql", "INSERT DATA { <urn:a> <urn:b> <urn:c> }", "INSERT { <urn:a> }"),
    ("sql", "SELECT a FROM b.c.d WHERE e = 1", "SELECT FROM WHERE (("),
    ("cypher", "MATCH (n:Resource {uri: $uri}) RETURN n.`a b` AS x // (", "MATCH (n:Resource RETURN n"),
    ("cypher", "RETURN 'it''s' AS x", "RETURN 'never closed"),
    ("ini", "[profile]\nhost = <your workspace URL>", "[profile]\nno value or sign"),
    ("ini", "dbms.security.procedures.unrestricted=apoc.*,n10s.*", "one = 1\none = 2"),   # a section's lines may stand alone
])
def test_a_parse_block_must_be_valid(tmp_path, lang, good, bad):
    assert check(tmp_path, fence(f"{lang} parse", good)).failures == []
    failures = check(tmp_path, fence(f"{lang} parse", bad)).failures
    assert len(failures) == 1 and failures[0].startswith(f"guide.md:1: the block is not valid {lang}\n")


def test_the_cypher_check_is_a_token_check_and_not_a_grammar_check(tmp_path):
    """The stated limit: clauses in the wrong order pass. What it finds is in the test above."""
    assert check(tmp_path, fence("cypher parse", "MATCH RETURN")).failures == []
    assert check(tmp_path, fence("cypher parse", "// only a comment")).failures == [
        "guide.md:1: the block is not valid cypher\n    | ValueError: no statement"]


def test_the_cypher_check_reads_this_trees_tokenizer_when_another_copy_is_loaded(tmp_path, monkeypatch):
    # A test that unpacks the release zip leaves a package named kpi_store behind, loaded from a folder that is gone.
    import types
    gone = types.ModuleType("kpi_store")
    gone.__file__, gone.__path__ = str(tmp_path / "gone" / "kpi_store" / "__init__.py"), [str(tmp_path / "gone" / "kpi_store")]
    monkeypatch.setitem(sys.modules, "kpi_store", gone)
    for name in [n for n in sys.modules if n.startswith("kpi_store.")]:
        monkeypatch.delitem(sys.modules, name)
    result = check(tmp_path, fence("cypher parse", "MATCH (n:Resource) RETURN count(n)"))
    assert result.failures == [] and result.checked == 1
    assert sys.modules["kpi_store"] is gone


def test_a_command_cannot_be_parsed_instead_of_run(tmp_path):
    result = check(tmp_path, fence("bash parse", "echo hello"))
    assert result.failures == ["guide.md:1: `bash` cannot be parsed: `parse` reads json, toml, yaml, ini, turtle, sparql, "
                               "sql, cypher. A command is tagged `run` or `skip`"]


def test_rdf_1_2_syntax_is_parsed_when_the_block_says_so(tmp_path):
    reifier = "<urn:w> lib:createdBy <urn:p> ~ <urn:a> {| lib:position 2 |} ."
    query = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o FILTER(!isTRIPLE(?o)) }"
    assert check(tmp_path, fence("turtle parse rdf=1.2", reifier) + fence("sparql parse rdf=1.2", query)).failures == []
    old = check(tmp_path, fence("turtle parse", reifier) + fence("sparql parse", query)).failures
    assert [f.split("\n")[0] for f in old] == ["guide.md:1: the block is not valid turtle", "guide.md:4: the block is not valid sparql"]
    bad = check(tmp_path, fence("turtle parse rdf=1.2", "<urn:w> lib:createdBy .") + fence("sparql parse rdf=1.2", "SELECT * WHERE { ?s ?p }")
                + fence("turtle parse rdf=2", reifier) + fence("json parse rdf=1.2", "{}")).failures
    assert [f.split("\n")[0] for f in bad] == [
        "guide.md:1: the block is not valid turtle", "guide.md:4: the block is not valid sparql",
        "guide.md:7: the block is not valid turtle", "guide.md:10: `rdf` is not something a `parse` block takes"]


def test_a_skipped_block_in_a_language_the_check_parses_is_still_parsed(tmp_path):
    reason = 'skip reason="needs-client-server: runs on the client\'s server"'
    text = (fence(f"sql {reason}", "DROP TABLE IF EXISTS a.b.c;") + fence(f"python {reason}", "store = rs.SparkStore(spark, '<table>')")
            + fence(f"bash {reason}", "databricks auth login ((") + fence("text expect", "signed in"))
    result = check(tmp_path, text)
    assert result.failures == []
    assert result.summary() == ("4 blocks: 0 run (0 status-only), 2 checked, 2 skipped (needs-client-server 2), "
                                "2 of the checked parsed but not run (needs-client-server 2)")
    broken = check(tmp_path, fence(f"sql {reason}", "DROP TABLE IF EXISTS ((") + fence(f"python {reason}", "store = ("))
    assert [f.split("\n")[0] for f in broken.failures] == [
        "guide.md:1: the skipped block is not valid sql. A skipped block in a language the check can parse is still parsed",
        "guide.md:4: the skipped block is not valid python. A skipped block in a language the check can parse is still parsed"]


PARSER = ("import argparse\nap = argparse.ArgumentParser()\nap.add_argument('--config')\n"
          "ap.add_argument(\"--plan\", action='store_true')\nap.add_argument('data', nargs='*')\nap.parse_args()\n")
SUBCOMMANDS = ("import argparse\nap = argparse.ArgumentParser()\nsub = ap.add_subparsers(dest='command', required=True)\n"
               "one = sub.add_parser('records')\none.add_argument('--report')\ntwo = sub.add_parser('write')\n"
               "two.add_argument('--uri')\nap.parse_args()\n")


def test_a_usage_block_names_scripts_that_exist_and_options_their_parsers_take(tmp_path):
    files = {"tools/load.py": PARSER, "tools/record.py": SUBCOMMANDS}
    good = (fence("bash usage=tools/load.py", "uv run --no-project --with rdflib python load.py --config <file> \\", "  [--plan]")
            + fence("text usage=tools", "load.py --config <config> <data>...", "# then", "scripts/record.py records --report r.json",
                    "record.py write --uri bolt://127.0.0.1:<port>"))
    result = check(tmp_path, good, files=files)
    assert result.failures == [] and result.checked == 2
    bad = (fence("bash usage=tools/load.py", "python load.py --config x --replace --batch 5") + fence("bash usage=tools", "gone.py --a")
           + fence("bash usage=tools/load.py", "python record.py --report r") + fence("bash usage=tools", "echo no script here")
           + fence("bash usage=../outside.py", "python outside.py") + fence("bash usage=tools", "# only a comment")
           + fence("bash usage=tools", "record.py write --report r.json"))
    assert check(tmp_path, bad, files=files).failures == [
        "guide.md:1: load.py has no option --replace, --batch",
        "guide.md:4: the script tools/gone.py does not exist",
        "guide.md:7: the line names record.py, and the tag names tools/load.py",
        "guide.md:10: the line `echo no script here` names no script",
        "guide.md:13: `../outside.py` must be a script or a folder inside the release",
        "guide.md:16: the block names no script",
        "guide.md:19: record.py has no option --report"]     # --report belongs to the other subcommand


def test_an_option_that_a_script_only_mentions_is_not_one_it_takes(tmp_path):
    """The option must be the parser's. A comment, a docstring or any other string that holds its text is not
    enough, whether the script can print its help here or not."""
    mentions = '"""Takes --report."""\n# --report\nx = "--report"\n' + PARSER
    cannot_run = "import a_package_that_is_not_installed\n" + mentions
    for source in (mentions, cannot_run):
        result = check(tmp_path, fence("bash usage=tools/check.py", "python check.py --config c --report r.json"),
                       files={"tools/check.py": source})
        assert result.failures == ["guide.md:1: check.py has no option --report"]
    # Read from the text when the script cannot run: the declared options still pass.
    assert check(tmp_path, fence("bash usage=tools/check.py", "python check.py --config c [--plan]"),
                 files={"tools/check.py": cannot_run}).failures == []
    assert d.declared_options(cannot_run) == {"--config", "--plan"}
    # A script that parses its arguments by hand is not started. The options its code compares, looks up or lists
    # count; a docstring, a comment, a longer string and a name that is only given the text do not.
    by_hand = ('"""Takes --doc."""\nimport sys\n# --comment\nx = "--plain"\nknown = {"--uri", "--env"}\nopts = dict.fromkeys(sys.argv)\n'
               'if "--report" in opts:\n    print(opts.get("--output"), "give --longer or nothing")\nraise SystemExit("this script was started")\n')
    assert d.handled_options(by_hand) == {"--uri", "--env", "--report", "--output"}
    # A text counts only where the code reads its arguments. An argument of another call, such as an error's text,
    # and a list, which is a command for another program, do not make an option.
    elsewhere = ('import subprocess, sys\nraise SystemExit("--fake")\nprint("--printed")\nsubprocess.run(["tool", "--passed-on"])\n'
                 'def f(): return "--returned"\n')
    assert d.handled_options(elsewhere) == set()
    reads = ('import sys\nargv = sys.argv[1:]\nif argv[0] == "--equal": pass\nif "--member" in argv: pass\nat = argv.index("--index")\n'
             'opts = {"--key": 1}\nvalue = opts["--subscript"]\nfor flag in ("--tuple",): pass\nif argv[0].startswith("--prefix"): pass\n'
             'match argv[0]:\n    case "--case" | "--other-case": pass\n')
    assert d.handled_options(reads) == {"--equal", "--member", "--index", "--key", "--subscript", "--tuple", "--prefix",
                                        "--case", "--other-case"}
    assert check(tmp_path, fence("bash usage=tools", "elsewhere.py --fake"), files={"tools/elsewhere.py": elsewhere}).failures == [
        "guide.md:1: elsewhere.py has no option --fake"]
    files = {"tools/by_hand.py": by_hand}
    assert check(tmp_path, fence("bash usage=tools", "by_hand.py --uri <uri> [--env <file>] --report r --output o"), files=files).failures == []
    assert check(tmp_path, fence("bash usage=tools", "by_hand.py --doc --comment --plain --longer"), files=files).failures == [
        "guide.md:1: by_hand.py has no option --doc, --comment, --plain, --longer"]


# -- placeholders


def test_a_placeholder_takes_its_value_from_the_context(tmp_path):
    text = fence("python run=gated", "print('<your name>', '<a word>')") + fence("text expect", "Rehearsal-1 plain")
    result = check(tmp_path, text, environ={"DOC_TEST_GATE": "1", "DOC_TEST_NAME": "Rehearsal-1"})
    assert result.failures == []


def test_a_placeholder_with_no_value_or_an_unsafe_value_fails(tmp_path):
    none = check(tmp_path, fence("python run=scratch status-only", "print('<your name>')"))
    assert none.failures == ["guide.md:1: the placeholder <your name> has no value in the context `scratch`. "
                             "Give it one in doc_snippets.toml, or tag the block `skip`"]
    unset = check(tmp_path, fence("python run=gated status-only", "print('<your name>')"), environ={"DOC_TEST_GATE": "1"})
    assert unset.failures == ["guide.md:1: the placeholder <your name> reads the variable DOC_TEST_NAME, "
                              "which is not set"]
    unsafe = check(tmp_path, fence("bash run=gated status-only", "echo <your name>"),
                   environ={"DOC_TEST_GATE": "1", "DOC_TEST_NAME": "x; touch injected"})
    assert unsafe.failures == ["guide.md:1: the value of the placeholder <your name> holds a character that is "
                               "not allowed"]


# -- Windows command lines


@pytest.mark.parametrize("line,args", [
    ("python -m kpi_store.runner --settings kpi_store.toml", ["python", "-m", "kpi_store.runner", "--settings", "kpi_store.toml"]),
    ('python tool.py --why "Two words" --empty ""', ["python", "tool.py", "--why", "Two words", "--empty", ""]),
    (r"python -m tool C:\kpi-store\report.json 'single quoted'", ["python", "-m", "tool", r"C:\kpi-store\report.json", "single quoted"]),
    ("  java   -jar  fuseki.jar ", ["java", "-jar", "fuseki.jar"]),
])
def test_a_plain_command_line_splits_into_its_arguments(line, args):
    assert d.split_command(line) == args


@pytest.mark.parametrize("line", ["python a.py | more", "python a.py > out.txt", "$env:X = 1", "python a.py; python b.py",
                                  'python a.py "$NAME"', "python a.py %NAME%", "python a.py && python b.py", 'py "open'])
def test_a_line_that_needs_a_shell_is_not_a_plain_command_line(line):
    with pytest.raises(d.NotSimple):
        d.split_command(line)


def test_py_and_python_are_this_interpreter():
    assert d.resolve_program(["py", "-3", "-m", "x"], None) == [sys.executable, "-B", "-m", "x"]
    assert d.resolve_program(["py", "-3.12", "a.py"], None) == [sys.executable, "-B", "a.py"]
    assert d.resolve_program(["python", "a.py"], None) == [sys.executable, "-B", "a.py"]
    with pytest.raises(FileNotFoundError):
        d.resolve_program(["no-such-program-here"], None)


def test_a_powershell_block_of_plain_lines_runs_without_a_shell(tmp_path):
    text = (fence("powershell run=copy", "# A comment line.", "cd tools", 'python show.py "two words" `', "    last")
            + fence("text expect", "['two words', 'last']")
            + fence("cmd run=copy status-only", "REM back in the top folder", "cd ..", "python tools/show.py one"))
    result = check(tmp_path, text, files={"tools/show.py": "import sys\nprint(sys.argv[1:])\n"})
    assert result.failures == [] and result.summary() == "3 blocks: 2 run (1 status-only), 1 checked, 0 skipped"


def test_a_powershell_block_with_shell_syntax_fails_unless_it_says_windows(tmp_path):
    result = check(tmp_path, "# Guide\n\n" + fence("powershell run=scratch status-only", "python -c \"print(1)\"", "$env:A = 1"),
                   static=True)
    assert result.failures == ["guide.md:3: line 5 is not a plain command line (`$`). Write it without shell syntax, "
                               "or add os=windows so that it runs in a real shell on Windows only"]


@pytest.mark.skipif(os.name == "nt", reason="on Windows the block runs")
def test_a_block_for_windows_only_is_counted_elsewhere(tmp_path):
    result = check(tmp_path, fence("powershell run=scratch os=windows status-only", "$env:A = 1; python -c \"print($env:A)\""))
    assert result.failures == [] and result.summary() == "1 blocks: 0 run (0 status-only), 0 checked, 1 skipped (windows-only 1)"


@pytest.mark.skipif(os.name != "nt", reason="elsewhere the block is counted and not run")
def test_a_block_for_windows_only_runs_in_a_real_shell_on_windows(tmp_path):
    # `python`, not `py`: the test runs wherever the check script runs, and a Python from a virtual environment or
    # from uv has no launcher. The Python that runs this test is on PATH under the name python.
    text = (fence("powershell run=scratch os=windows", "$env:A = 'seen'; python -c \"import os; print(os.environ['A'])\"")
            + fence("text expect", "seen")
            + fence("cmd run=scratch os=windows", "set B=also&& python -c \"import os; print(os.environ['B'])\"")
            + fence("text expect", "also"))
    result = check(tmp_path, text)
    assert result.failures == [] and result.summary() == "4 blocks: 2 run (0 status-only), 2 checked, 0 skipped"


def test_a_block_that_starts_python_with_py_fails_on_every_machine(tmp_path):
    """The first real run was on a Python from a virtual environment, where `py` is not there. The documents start
    Python with `python`, and the check holds every run block to that."""
    launcher = "p" + "y"   # spelled in two parts, so that a search of the tree for the launcher's commands finds none here
    for body in (f"{launcher} -m pip install rdflib", f"$env:A = 1; {launcher} -c \"print(1)\"", f"set B=also&& {launcher} -c \"print(1)\"",
                 f"cd C:\\kpi-store-1.1\n{launcher}.exe -m kpi_store.setup_check", f"if ($true) {{ {launcher} -V }}",
                 f"{launcher.capitalize()} -V", f"{launcher.upper()}.EXE -V", f"call {launcher} -V", f"@{launcher} -V", f"& {launcher} -V",
                 f"echo on && CALL {launcher} -V", f"start {launcher} tool.{launcher}",
                 f'start "" {launcher} -V', f"start /wait {launcher} -V", f'START "KPI Store" /wait /b {launcher}.exe -V'):
        assert d.starts_launcher(body), body
    # The word inside another word, a path or an argument is not the launcher.
    for body in ("python -m pip install rdflib", "setx PY_PYTHON 3.12", "uv run tool.py", f"echo {launcher}", f"C:\\tools\\{launcher} -V",
                 "copy.exe a b", "happy -V", f"call tool.{launcher}", "set PY=3", f"python -m {launcher}_compile x",
                 f'start "{launcher}" python -V', "start /wait python -V", f"start notepad {launcher}",
                 f'start "" "python" {launcher} -V'):   # after the title, the quoted word is the program and the launcher's name its argument
        assert not d.starts_launcher(body), body
    said = ("the block starts Python with `py`. Write `python`: a Python from a virtual environment has no `py` "
            "launcher, so the command would not start there")
    for tag, body in (("powershell run=scratch status-only", f"{launcher} -c \"print(1)\""),
                      ("powershell run=scratch os=windows status-only", f"$env:A = 1; {launcher} -c \"print(1)\""),
                      ("cmd run=scratch os=windows status-only", f"set B=also&& {launcher} -c \"print(1)\""),
                      ("bash run=scratch status-only", f"{launcher} -c 'print(1)'")):
        assert check(tmp_path, fence(tag, body)).failures == [f"guide.md:1: {said}"], tag
    assert check(tmp_path, fence("powershell run=scratch status-only", "python -c \"print(1)\"")).failures == []


def test_a_missing_program_fails_the_line(tmp_path):
    result = check(tmp_path, fence("powershell run=scratch status-only", "no-such-program-here --version"))
    assert result.failures == ["guide.md:1: the program `no-such-program-here` is not installed, so the line cannot "
                               "run\n    | (no output)"]


# -- nested documents


def test_a_nested_block_is_a_small_document_whose_blocks_are_tested(tmp_path):
    text = "\n".join(["# Guide", "", "````markdown nested", "Write it like this:", "",
                      "```python run=scratch", "print('inside')", "open('made.txt', 'w').close()", "```", "",
                      "```text expect", "outside", "```", "````", "",
                      "```python run=scratch", "import os", "print(os.path.exists('made.txt'))", "```", "",
                      "```text expect", "False", "```", ""])
    result = check(tmp_path, text)
    assert result.failures == ["guide.md:11: the output of the block at line 6 is not what this block shows\n"
                               "    | --- expected\n    | +++ output\n    | @@ -1 +1 @@\n    | -outside\n    | +inside"]
    assert result.summary() == "4 blocks: 2 run (0 status-only), 1 checked, 0 skipped, 1 failed"


def test_a_nested_block_must_hold_a_block(tmp_path):
    result = check(tmp_path, "````markdown nested\nonly words\n````\n")
    assert result.failures == ["guide.md:1: the nested block holds no code block"]


# -- a page written by hand


def test_a_pre_block_with_no_attribute_fails_with_its_page_and_line(tmp_path):
    result = check_page(tmp_path, "<h1>Guide</h1>", "<pre>echo hello</pre>", "<p>Text with <code>inline code</code>.</p>",
                        '<pre class="cmd" data-snippet="bash">echo hello</pre>', '<pre data-snippet="">x</pre>')
    assert result.failures == [
        'guide.html:5: the <pre> block has no data-snippet attribute. Write data-snippet="<language> <tag>", as on a '
        "Markdown fence",
        "guide.html:7: the block has no tag after its language `bash`",
        "guide.html:8: the block has no language and no tag"]
    assert result.summary() == "3 blocks: 0 run (0 status-only), 0 checked, 0 skipped, 3 failed"


def test_a_page_block_runs_as_the_text_its_reader_sees(tmp_path):
    # Character references are decoded and the tags that colour the text are dropped. The line break after
    # <pre> is not part of the block.
    result = check_page(tmp_path,
                        '<pre data-snippet="bash run=scratch">',
                        '<span class="c"># a comment</span>',
                        "test 1 -lt 2 &amp;&amp; echo &quot;5 &lt; 7 &amp; more&quot;</pre>",
                        '<pre data-snippet="text expect">5 &lt; 7 &amp; more</pre>')
    assert result.failures == []
    assert result.summary() == "2 blocks: 1 run (0 status-only), 1 checked, 0 skipped"


def test_a_page_block_whose_output_differs_fails(tmp_path):
    result = check_page(tmp_path, '<pre data-snippet="python run=scratch">print("loaded 13 graphs")</pre>',
                        '<pre data-snippet="text expect">loaded 12 graphs</pre>')
    assert len(result.failures) == 1
    assert result.failures[0].startswith("guide.html:5: the output of the block at line 4 is not what this block shows")
    assert "-loaded 12 graphs" in result.failures[0] and "+loaded 13 graphs" in result.failures[0]


def test_a_failing_page_block_fails_and_a_run_block_needs_its_expect_or_status_only(tmp_path):
    result = check_page(tmp_path, '<pre data-snippet="bash run=scratch status-only">exit 3</pre>',
                        '<pre data-snippet="bash run=other">echo unchecked</pre>')
    assert result.failures[0].startswith("guide.html:4: the block ended with exit status 3, not 0 (context scratch)")
    assert result.failures[1].startswith("guide.html:5: nothing checks what this block prints.")
    assert result.summary() == "2 blocks: 0 run (0 status-only), 0 checked, 0 skipped, 2 failed"


def test_a_page_skip_needs_an_allowed_reason_and_strict_refuses_a_temporary_one(tmp_path):
    lines = ['<pre data-snippet="bash skip reason=&quot;needs-client-server: reads the client workspace&quot;">x</pre>',
             '<pre data-snippet="text expect">any output</pre>',
             '<pre data-snippet="bash skip reason=&quot;too slow: takes an hour&quot;">x</pre>',
             "<pre data-snippet='bash skip reason=\"awaits-the-rewrite: goes with the old section\"'>x</pre>"]
    result = check_page(tmp_path, *lines)
    assert result.failures == ["guide.html:6: `too slow` is not an allowed reason: use one of awaits-the-rewrite, "
                               "illustration, needs-client-server"]
    assert result.skipped == {"needs-client-server": 2, "awaits-the-rewrite": 1}
    strict = check_page(tmp_path, *lines, strict=True)
    assert strict.failures[1] == "guide.html:7: the reason `awaits-the-rewrite` is temporary and must be gone at the cut"


def test_a_page_file_excerpt_and_parse_block_are_checked(tmp_path):
    files = {"settings.toml": '[release]\nzip = "kpi-store-1.1.zip"\nsha256 = "abc"\n'}
    good = ['<pre data-snippet="toml file=settings.toml">[release]', 'zip = &quot;kpi-store-1.1.zip&quot;',
            'sha256 = "abc"</pre>',
            '<pre data-snippet="toml excerpt=settings.toml">zip = "kpi-store-1.1.zip"</pre>',
            '<pre data-snippet="json parse">{"format": 1}</pre>']
    result = check_page(tmp_path, *good, files=files)
    assert result.failures == [] and result.summary() == "3 blocks: 0 run (0 status-only), 3 checked, 0 skipped"
    bad = ['<pre data-snippet="toml file=settings.toml">[release]</pre>',
           '<pre data-snippet="toml excerpt=settings.toml">zip = "kpi-store-1.0.zip"</pre>',
           '<pre data-snippet="json parse">{"format": 1,}</pre>']
    result = check_page(tmp_path, *bad, files=files)
    assert [f.split("\n")[0] for f in result.failures] == [
        "guide.html:4: the block differs from settings.toml",
        "guide.html:5: the lines are not in settings.toml, in this order and next to each other",
        "guide.html:6: the block is not valid json"]


def test_an_unknown_tag_a_nested_block_and_an_open_block_fail_in_a_page(tmp_path):
    result = check_page(tmp_path, '<pre data-snippet="bash test">x</pre>',
                        '<pre data-snippet="markdown nested">x</pre>', '<pre data-snippet="json parse">{}')
    assert result.failures == [
        "guide.html:4: unknown tag `test`: use one of run, expect, skip, file, excerpt, usage, parse, nested",
        "guide.html:5: a nested block is for a Markdown document, not for a page",
        "guide.html:6: the <pre> code block is never closed"]


def test_only_a_pre_or_a_tagged_element_is_a_block_of_a_page(tmp_path):
    # Text in a script or a style is not a block. An element other than <pre> is one only when it carries the tag.
    result = check_page(tmp_path, "<script>var t = '<pre>not a block</pre>';</script>",
                        "<style>pre { color: red } /* <pre>no</pre> */</style>",
                        "<p>A <code>span</code> in a sentence is text.</p>",
                        '<div class="code"><code data-snippet="json parse">{"a": [1, 2]}</code></div>',
                        '<img data-snippet="json parse" src="x.png">',
                        '<pre data-snippet="json parse">{"b": <b>3</b>}</pre>')
    assert result.failures == ["guide.html:8: a <img> element holds no text, so it cannot be a code block"]
    assert result.summary() == "3 blocks: 0 run (0 status-only), 2 checked, 0 skipped, 1 failed"


def test_a_page_is_left_out_only_when_one_of_the_two_builders_made_it(tmp_path):
    # Text that looks like a generator line, another tool's line, and a Markdown file of the same name do not take
    # a hand-written page out of the check.
    (tmp_path / "comment.html").write_text('<!-- <meta name="generator" content="scripts/build_docs_html.py"> --><pre>x</pre>',
                                           encoding="utf-8")
    (tmp_path / "script.html").write_text("<script>var m = '<meta name=\"generator\" content=\"scripts/build_docs_html.py\">';</script>"
                                          "<pre>x</pre>", encoding="utf-8")
    (tmp_path / "other-tool.html").write_text('<meta name="generator" content="some other tool"><pre>x</pre>', encoding="utf-8")
    (tmp_path / "twin.md").write_text("# Twin\n", encoding="utf-8")
    (tmp_path / "twin.html").write_text("<pre>written by hand beside twin.md</pre>", encoding="utf-8")
    (tmp_path / "built.html").write_text("<meta content='scripts/build_docs_html.py' name='GENERATOR'><pre>x</pre>", encoding="utf-8")
    assert d.html_documents(tmp_path) == ["comment.html", "other-tool.html", "script.html", "twin.html"]


def test_the_pages_in_scope_are_those_no_markdown_file_is_the_source_of(tmp_path, capsys):
    (tmp_path / "a.md").write_text("# A\n\n" + fence("json parse", "{}"), encoding="utf-8")
    (tmp_path / "a.html").write_text('<META NAME=generator CONTENT=\'scripts/build_docs_html.py\'><pre>built from a.md</pre>',
                                     encoding="utf-8")
    (tmp_path / "built.html").write_text('<meta name="generator" content="scripts/build_playbook_html.py"><pre>built</pre>',
                                         encoding="utf-8")
    (tmp_path / "hand.html").write_text(page("<pre>no tag</pre>", '<pre data-snippet="json parse">{}</pre>'),
                                        encoding="utf-8")
    (tmp_path / "plain.html").write_text(page("<p>No block.</p>"), encoding="utf-8")
    assert d.html_documents(tmp_path) == ["hand.html", "plain.html"]
    assert d.main(["--root", str(tmp_path), "check"]) == 1
    assert capsys.readouterr().out == (
        'FAIL hand.html:4: the <pre> block has no data-snippet attribute. Write data-snippet="<language> <tag>", as '
        "on a Markdown fence\n"
        "3 blocks: 0 run (0 status-only), 2 checked, 0 skipped, 1 failed\n")
    assert d.main(["--root", str(tmp_path), "list"]) == 0
    assert capsys.readouterr().out == ("   1  a.md: parse 1\n   2  hand.html: (untagged or unreadable) 1, parse 1\n"
                                       "   3  total: (untagged or unreadable) 1, parse 2\n")


# -- the command


def test_the_command_prints_each_failure_and_the_count_and_exits_1(tmp_path, capsys, monkeypatch):
    # The command reads the real environment. When a block of a running check started these tests, as the full
    # check in a guide does, that environment says so, and the command would run no block.
    monkeypatch.delenv(d.NESTED, raising=False)
    monkeypatch.delenv(d.NESTED_FILE, raising=False)
    (tmp_path / "guide.md").write_text(fence("json parse", "{}") + fence("text", "no tag"), encoding="utf-8", newline="\n")
    assert d.main(["--root", str(tmp_path), "check"]) == 1
    assert capsys.readouterr().out == ("FAIL guide.md:4: the block has no tag after its language `text`\n"
                                       "2 blocks: 0 run (0 status-only), 1 checked, 0 skipped, 1 failed\n")
    (tmp_path / "guide.md").write_text(fence("json parse", "{}"), encoding="utf-8", newline="\n")
    assert d.main(["--root", str(tmp_path), "check", "guide.md"]) == 0
    assert capsys.readouterr().out == "1 blocks: 0 run (0 status-only), 1 checked, 0 skipped\n"
    assert d.main(["--root", str(tmp_path), "list"]) == 0
    assert capsys.readouterr().out == "   1  guide.md: parse 1\n   1  total: parse 1\n"


def test_the_html_command_counts_only_pages_with_no_markdown_source(tmp_path, capsys):
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8", newline="\n")
    (tmp_path / "a.html").write_text('<meta name="generator" content="scripts/build_docs_html.py"><pre>from a.md</pre>',
                                     encoding="utf-8", newline="\n")
    (tmp_path / "built.html").write_text('<meta name="generator" content="scripts/build_playbook_html.py"><pre>built</pre>',
                                         encoding="utf-8", newline="\n")
    (tmp_path / "hand.html").write_text("<pre><code>one</code></pre><p><code>two</code> <code>three</code></p>"
                                        "<pre class='x'>four</pre>", encoding="utf-8", newline="\n")
    assert d.html_pages(tmp_path) == [("hand.html", 2, 2)]


CHAIN = REGISTRY + """
[contexts.chain]
base = "empty"
owner = "m-owner.md"
"""


def check_tree(tmp_path, files, docs, registry=REGISTRY, environ=None, **options):
    """Check several documents of a temporary tree, in the order given."""
    root = tmp_path / "tree"
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content, encoding="utf-8", newline="\n")
    (tmp_path / "registry.toml").write_text(registry, encoding="utf-8", newline="\n")
    env = {k: v for k, v in os.environ.items() if k not in (d.NESTED, d.NESTED_FILE)}
    env.update(environ or {})
    return d.Checker(root, d.load_registry(tmp_path / "registry.toml"), environ=env, **options).check(docs)


def test_a_context_with_an_owner_is_one_chain_that_other_documents_go_on_from(tmp_path):
    files = {"a-early.md": fence("bash run=chain", "cat made.txt") + fence("text expect", "by the owner"),
             "m-owner.md": fence("bash run=chain status-only", "echo by the owner > made.txt"),
             "z-late.md": fence("bash run=chain status-only", "test -f made.txt") + fence("bash run=scratch status-only", "test ! -f made.txt")}
    result = check_tree(tmp_path, files, ["a-early.md", "m-owner.md", "z-late.md"], registry=CHAIN)
    assert result.failures == [] and result.ran == 4
    assert list(result.by_document) == ["m-owner.md", "a-early.md", "z-late.md"]     # the owner is read first


def test_without_its_owner_a_chain_s_block_is_counted_and_all_contexts_makes_it_a_failure(tmp_path):
    files = {"a-early.md": fence("bash run=chain status-only", "test -f made.txt"), "m-owner.md": "# Owner\n"}
    alone = check_tree(tmp_path, files, ["a-early.md"], registry=CHAIN)
    assert alone.failures == [] and alone.skipped == {"context chain goes on from m-owner.md, which this check did not read": 1}
    strict = check_tree(tmp_path, files, ["a-early.md"], registry=CHAIN, all_contexts=True)
    assert strict.failures == ["a-early.md:1: the context `chain` goes on from m-owner.md: check that document in the same run"]


def test_the_owner_of_a_chain_is_read_before_the_documents_that_use_it(tmp_path):
    for name, text in (("a.md", "```bash run=other,chain define status-only\n```\n"), ("b.md", "run=chains\n"),
                       ("c.md", "```bash run=chain\n```\n"), ("m-owner.md", ""), ("z.md", "```bash run=chain\n```\n")):
        (tmp_path / name).write_text(text, encoding="utf-8", newline="\n")
    (tmp_path / "registry.toml").write_text(CHAIN, encoding="utf-8", newline="\n")
    registry = d.load_registry(tmp_path / "registry.toml")
    assert d.chain_order(tmp_path, registry, ["a.md", "b.md", "c.md", "m-owner.md", "z.md"]) == ["b.md", "m-owner.md", "a.md", "c.md", "z.md"]
    assert d.chain_order(tmp_path, registry, ["a.md", "z.md"]) == ["a.md", "z.md"]


FIXTURE = REGISTRY + """
[contexts.store]
base = "release-copy"
pass_env = ["DOC_TEST_LOG", "DOC_TEST_FAIL"]
fixture = "python tools/fixture.py"
[contexts.store.runs]
sql = "python tools/run_sql.py"
[contexts.store.placeholders]
"the table" = "fixture"
"no value" = "fixture"
"""
FIXTURE_FILES = {
    "tools/fixture.py": "import json, os, sys\nfrom pathlib import Path\n"
                        "folder = Path(os.environ['DOC_SNIPPETS_FIXTURE_DIR'])\n"
                        "with open(os.environ['DOC_TEST_LOG'], 'a') as log:\n    log.write(sys.argv[1] + '\\n')\n"
                        "if sys.argv[1] in os.environ.get('DOC_TEST_FAIL', '').split():\n"
                        "    sys.exit('the store did not answer' if sys.argv[1] == 'up' else 'left behind: the made-up store')\n"
                        "if sys.argv[1] == 'up':\n"
                        "    (folder / 'values.json').write_text(json.dumps({'placeholders': {'the table': 'made_up.rows'},\n"
                        "                                                    'env': {'DOC_TEST_GIVEN': 'by the fixture'}}))\n",
    "tools/run_sql.py": "import os, sys\nfrom pathlib import Path\n"
                        "assert (Path(os.environ['DOC_SNIPPETS_FIXTURE_DIR']) / 'values.json').is_file()\n"
                        "assert os.environ['DOC_TEST_GIVEN'] == 'by the fixture'\n"
                        "print('ran:', Path(sys.argv[1]).read_text().strip())\n",
}


def test_a_context_s_fixture_is_made_once_gives_values_and_is_removed_at_the_end(tmp_path):
    log = tmp_path / "log.txt"
    text = (fence("sql run=store", "DROP TABLE <the table>;") + fence("text expect", "ran: DROP TABLE made_up.rows;")
            + fence("sql run=store status-only", "SELECT 1"))
    result = check(tmp_path, text, files=FIXTURE_FILES, registry=FIXTURE, environ={"DOC_TEST_LOG": str(log)})
    assert result.failures == [] and (result.ran, result.checked) == (2, 1)
    assert log.read_text().split() == ["up", "down"]
    # The static check makes no fixture and still knows the placeholder.
    static = check(tmp_path, text, files=FIXTURE_FILES, registry=FIXTURE, environ={"DOC_TEST_LOG": str(log)}, static=True)
    assert static.failures == [] and log.read_text().split() == ["up", "down"]


def test_a_fixture_that_cannot_be_made_or_removed_fails_the_check(tmp_path):
    log = tmp_path / "log.txt"
    text = fence("sql run=store status-only", "SELECT 1") + fence("sql run=store status-only", "SELECT 2")
    made = check(tmp_path, text, files=FIXTURE_FILES, registry=FIXTURE, environ={"DOC_TEST_LOG": str(log), "DOC_TEST_FAIL": "up"})
    assert [f.split("\n")[0] for f in made.failures] == [
        "guide.md:1: the fixture of the context `store` could not be made",
        "guide.md:4: not run: the block at line 1 of the same context failed"]
    # After a failed `up` the check still runs `down`, so that a store made halfway does not stay.
    assert "the store did not answer" in made.failures[0] and log.read_text().split() == ["up", "down"]
    log.unlink()
    # When that `down` fails too, the check says so on a line of its own: something may be left on a server.
    both = check(tmp_path, text, files=FIXTURE_FILES, registry=FIXTURE, environ={"DOC_TEST_LOG": str(log), "DOC_TEST_FAIL": "up down"})
    assert log.read_text().split() == ["up", "down"] and len(both.failures) == 3
    assert both.failures[2].startswith("the fixture of the context `store` could not be removed after its start had failed. "
                                       "What it made may still be there; its output below says what is left and how to "
                                       "remove it by hand (the fixture is `python tools/fixture.py`)\n")
    assert "left behind: the made-up store" in both.failures[2]
    log.unlink()
    removed = check(tmp_path, text, files=FIXTURE_FILES, registry=FIXTURE, environ={"DOC_TEST_LOG": str(log), "DOC_TEST_FAIL": "down"})
    assert removed.ran == 2 and len(removed.failures) == 1
    assert removed.failures[0].startswith("the fixture of the context `store` could not be removed. What it made may still be there")
    missing = check(tmp_path, fence("sql run=store status-only", "SELECT <no value>"), files=FIXTURE_FILES, registry=FIXTURE,
                    environ={"DOC_TEST_LOG": str(log)})
    assert missing.failures == ["guide.md:1: the fixture of the context `store` gave the placeholder <no value> no value, "
                                "or one with a character that is not allowed"]


def test_the_registry_holds_nothing_the_runner_reads_as_a_secret():
    """The runner refuses to zip a release in which a settings file has a key that names a password or a token.
    The registry is such a file, so a context gets a password from its fixture, never from a key here."""
    sys.path.insert(0, str(d.ROOT))
    try:
        from kpi_store import runner
    finally:
        sys.path.remove(str(d.ROOT))
    assert runner.secret_keys(d.REGISTRY) == []


def test_a_fixture_or_a_runs_table_needs_a_copy_of_the_release_and_an_owner_a_path_inside_it(tmp_path):
    path = tmp_path / "r.toml"
    path.write_text('[contexts.a]\nbase = "empty"\nfixture = "python tools/fixture.py"\n', encoding="utf-8", newline="\n")
    with pytest.raises(d.RegistryError, match="context a has a fixture or runs, so it needs base"):
        d.load_registry(path)
    path.write_text('[contexts.a]\nbase = "empty"\nowner = "../guide.md"\n', encoding="utf-8", newline="\n")
    with pytest.raises(d.RegistryError, match="context a needs owner as a document's path"):
        d.load_registry(path)


def test_a_registry_with_an_unknown_key_or_base_is_refused(tmp_path):
    path = tmp_path / "r.toml"
    path.write_text('[contexts.a]\nbase = "empty"\nshell = true\n', encoding="utf-8", newline="\n")
    with pytest.raises(d.RegistryError, match="context a has unknown key"):
        d.load_registry(path)
    path.write_text('[contexts.a]\nbase = "the tree itself"\n', encoding="utf-8", newline="\n")
    with pytest.raises(d.RegistryError, match="context a needs base"):
        d.load_registry(path)
    path.write_text('[reasons]\nillustration = "x"\ntemporary_reasons = ["illustration"]\n', encoding="utf-8", newline="\n")
    with pytest.raises(d.RegistryError, match="the reason temporary_reasons needs a sentence"):
        d.load_registry(path)
    path.write_text('temporary_reasons = ["later"]\n', encoding="utf-8", newline="\n")
    with pytest.raises(d.RegistryError, match="temporary reason later is not a reason"):
        d.load_registry(path)


# -- this tree


def test_the_reasons_are_the_six_agreed_ones_and_one_is_temporary():
    registry = d.load_registry()
    assert sorted(registry.reasons) == ["awaits-the-rewrite", "destructive", "illustration", "needs-browser-sign-in",
                                        "needs-client-server", "windows-only"]
    assert registry.temporary == ("awaits-the-rewrite",)


def test_the_contexts_that_run_everywhere_need_no_variable_and_the_others_name_theirs():
    contexts = d.load_registry().contexts
    assert {name: c.needs_env for name, c in contexts.items()} == {
        "scratch": (), "release-copy": (), "release-git": (),
        "slow": ("DOC_SNIPPETS_SLOW",),
        "correction": ("DOC_SNIPPETS_SLOW",),
        "new-module": ("DOC_SNIPPETS_SLOW",),
        "term-change": ("DOC_SNIPPETS_SLOW",),
        "reference-item": ("DOC_SNIPPETS_SLOW",),
        "new-kpi": ("DOC_SNIPPETS_SLOW",),
        "stores": ("KPI_STORE_TEST_FUSEKI_URL", "KPI_STORE_TEST_NEO4J_URI"),
        "databricks-free": ("KPI_STORE_TEST_DATABRICKS_PROFILE",),
        "reasoner": ("KPI_STORE_TEST_ROBOT_JAR",),
        "empty-fuseki": ("KPI_STORE_TEST_EMPTY_FUSEKI_URL",),
        "first-run": ("KPI_STORE_TEST_LOCAL_SETTINGS", "KPI_STORE_TEST_LPG_OUT"),
        "questions": ("KPI_STORE_TEST_NEO4J_URI", "KPI_STORE_TEST_NEO4J_PASSWORD"),
        "enterprise-database": ("KPI_STORE_TEST_NEO4J_URI", "KPI_STORE_TEST_NEO4J_PASSWORD"),
        "scratch-database": ("KPI_STORE_TEST_NEO4J_URI", "KPI_STORE_TEST_NEO4J_PASSWORD"),
        "scratch-schemas": ("KPI_STORE_TEST_LOCAL_SETTINGS",),
        "windows-account": ("DOC_SNIPPETS_WINDOWS_ACCOUNT",),
        "shared-drive": ("DOC_SNIPPETS_SHARED_DRIVE",)}
    assert [name for name, c in contexts.items() if c.home == "real"] == ["databricks-free", "first-run", "scratch-schemas",
                                                                          "windows-account"]
    # The runbook's commands read KPI_STORE_LOCAL. Only its own context may give that variable to a block. The
    # questions' commands read KPI_STORE_NEO4J_*; their fixture gives those, so the registry names no password.
    assert {name: sorted(c.set_env) for name, c in contexts.items() if c.set_env} == {"first-run": ["KPI_STORE_LOCAL"]}
    assert contexts["first-run"].set_env == {"KPI_STORE_LOCAL": "env:KPI_STORE_TEST_LOCAL_SETTINGS"}
    # One chain goes on from one document into others: the runbook's. A fixture is always the tree's own file.
    assert {name: c.owner for name, c in contexts.items() if c.owner} == {
        "first-run": "business_architecture/ontology/projection/ontology-stores-runbook.md"}
    for c in contexts.values():
        for command in [c.fixture, *c.runs.values()]:
            assert not command or command.startswith("python scripts/doc_snippets_fixtures.py "), c.name


def test_every_markdown_document_of_the_tree_is_in_scope():
    docs = d.documents(d.ROOT)
    for known in ("README.md", "HOW-TO-UPDATE.md", "KNOWN-OPEN-ITEMS.md", "scripts/DOC-SNIPPETS.md",
                  "business_architecture/ontology/projection/README.md", "skills/ontology/SKILL.md",
                  "skills/ontology-to-lpg/references/pipeline.md"):
        assert known in docs, known
    on_disk = {p.relative_to(d.ROOT).as_posix() for p in d.ROOT.rglob("*.md")
               if not set(p.relative_to(d.ROOT).parts) & d.SKIP_DIRS}
    tracked_or_new = set(d.tree_files(d.ROOT))
    assert set(docs) == {p for p in on_disk if p in tracked_or_new}


def test_the_hand_written_pages_of_the_tree_are_in_scope_and_the_generated_ones_are_not():
    pages = d.html_documents(d.ROOT)
    for known in ("business_architecture/ontology/epm-walkthrough.html",
                  "business_architecture/ontology/epm-ontology-guide.html",
                  "viewer/index.html"):
        assert known in pages, known
    for built in ("HOW-TO-UPDATE.html", "business_architecture/ontology/MODULES.html",
                  "skills/ontology/references/ontology-build-playbook.html"):
        assert built not in pages, built


def test_a_markdown_file_git_ignores_is_outside_the_scan(tmp_path):
    """The rule of the scan: what Git tracks or would add. An ignored file does not ship. A folder with no Git
    is read whole."""
    import subprocess
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for folder in ("repository", "plain"):
        (tmp_path / folder).mkdir()
        for name, content in (("tracked.md", "# T\n"), ("new.md", "# N\n"), ("notes.md", "# I\n"),
                              (".gitignore", "notes.md\n")):
            (tmp_path / folder / name).write_text(content, encoding="utf-8", newline="\n")
    for args in (["init", "-q"], ["add", "tracked.md", ".gitignore"]):
        subprocess.run(["git", *args], cwd=tmp_path / "repository", env=env, check=True, capture_output=True)
    assert d.documents(tmp_path / "repository") == ["new.md", "tracked.md"]
    assert d.documents(tmp_path / "plain") == ["new.md", "notes.md", "tracked.md"]


def test_no_part_of_the_tool_is_a_long_file():
    parts = sorted((d.ROOT / "scripts" / "doc_snippets_parts").glob("*.py")) + [d.ROOT / "scripts" / "doc_snippets.py"]
    assert [p.name for p in parts] == ["__init__.py", "check.py", "extract.py", "links.py", "match.py", "pages.py", "parsers.py",
                                       "registry.py", "report.py", "run.py", "static.py", "doc_snippets.py"]
    for part in parts:
        assert len(part.read_text(encoding="utf-8").split("\n")) < 500, part.name


def test_every_block_of_the_tree_has_a_valid_tag():
    """The static half of the check, so that this file alone finds a block with no tag. scripts/check.sh then runs
    the blocks with `doc_snippets.py check`."""
    result = d.Checker(static=True).check()
    assert result.failures == []
    assert result.total > 80


# ---- the blocks that no test runs ----

NOT_RUN_HEADING = "## Blocks the test does not run"


def test_the_blocks_that_are_not_run_are_named_by_document_heading_and_first_line(tmp_path):
    (tmp_path / "guide.md").write_text("\n".join([
        "# Guide", "", "## Sign in", "",
        '```powershell skip reason="needs-browser-sign-in: opens the sign-in page"', "", "  databricks   auth login --host <url>", "```",
        "", "````markdown nested", "# not a heading of the guide", '```text skip reason="illustration: a sketch of the loads"',
        "a | b", "```", "````", "", "```bash run=scratch status-only", "true", "```", ""]), encoding="utf-8", newline="\n")
    (tmp_path / "page.html").write_text(page(
        "<h2 id='x'>Make the <em>shared</em> folders</h2>",
        "<pre data-snippet='text skip reason=\"illustration: the name of one file\"'>crack-spreads.json</pre>"),
        encoding="utf-8", newline="\n")
    assert d.not_run(tmp_path) == [
        ("guide.md", "Sign in", "databricks auth login --host <url>", "needs-browser-sign-in"),
        ("guide.md", "Sign in", "a | b", "illustration"),
        ("page.html", "Make the shared folders", "crack-spreads.json", "illustration")]
    assert d.block_key("\n" + "x" * 80 + "\nsecond") == "x" * 60


def test_the_rows_of_a_table_under_a_heading_are_read_with_their_code_spans_and_bars():
    text = "\n".join(["## Other", "| a |", "|---|", "| no |", "", NOT_RUN_HEADING, "", "Some words.", "",
                      "| Document | Block |", "|---|---|", "| `guide.md` | `a \\| b` |", "| `page.html` | `` a `b` `` |", "",
                      "| later | table |", "|---|---|", "| not | read |"])
    assert d.table_rows(text, NOT_RUN_HEADING) == [["guide.md", "a | b"], ["page.html", "a `b`"]]
    assert d.table_rows(text, "## Absent") == []


def test_every_block_that_no_test_runs_is_in_the_table_and_the_table_names_no_other():
    """Nobody adds a skipped block in silence: scripts/DOC-SNIPPETS.md lists each one, with what was done instead
    and who can run it. `python scripts/doc_snippets.py not-run` prints the first four cells of every row."""
    text = (d.ROOT / "scripts" / "DOC-SNIPPETS.md").read_text(encoding="utf-8")
    rows = d.table_rows(text, NOT_RUN_HEADING)
    assert rows, f"scripts/DOC-SNIPPETS.md has no table under {NOT_RUN_HEADING}"
    assert all(len(row) == 6 and all(row) for row in rows), "each row has six cells, and none is empty"
    listed = [tuple(row[:4]) for row in rows]
    blocks = d.not_run(d.ROOT)
    assert len(set(blocks)) == len(blocks), "two skipped blocks of one document start with the same line under one heading"
    missing = [block for block in blocks if block not in listed]
    gone = [row for row in listed if row not in blocks]
    assert not missing, f"skipped blocks that the table does not list: {missing}"
    assert not gone, f"rows of the table that name no skipped block: {gone}"
    assert len(listed) == len(set(listed))


# ---- the stand-in stores of scripts/doc_snippets_fixtures.py ----

def fixtures_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("doc_snippets_fixtures", d.ROOT / "scripts" / "doc_snippets_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_block_s_statements_are_split_at_the_semicolons_that_end_a_line():
    f = fixtures_module()
    assert f.statements("// a comment\nMATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS;\n"
                        "DROP CONSTRAINT n10s_unique_uri IF EXISTS;\n") == [
        "MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS", "DROP CONSTRAINT n10s_unique_uri IF EXISTS"]
    assert f.statements("-- a comment\nSELECT ';' AS x;  \nSELECT 2") == ["SELECT ';' AS x", "SELECT 2"]
    assert f.table_text(["name", "n"], [{"name": "a", "n": 1}, {"name": None, "n": 2}]) == "name, n\na, 1\nnull, 2"


def test_a_statement_reaches_only_the_throwaway_schemas():
    f = fixtures_module()
    names = {"idp_sbx.kpi_store": "rehearsal.doc_snippets_1", "idp_sbx.tech_graph": "rehearsal.doc_snippets_1_tech"}
    assert f.to_scratch("DROP TABLE IF EXISTS idp_sbx.kpi_store.epm_triples", names) == ("TABLE", "rehearsal.doc_snippets_1.epm_triples")
    assert f.to_scratch("drop volume if exists IDP_SBX.kpi_store.releases", names) == ("VOLUME", "rehearsal.doc_snippets_1.releases")
    assert f.to_scratch("DROP SCHEMA IF EXISTS IDP_SBX.tech_graph", names) == ("SCHEMA", "rehearsal.doc_snippets_1_tech")
    for statement in ("DROP TABLE IF EXISTS idp_sbx.kpi_store_other.epm_triples", "DROP SCHEMA IF EXISTS idp_sbx.gold_commercial_core",
                      "DROP TABLE IF EXISTS workspace.default.b", "DROP SCHEMA IF EXISTS idp_sbx.kpi_store.epm_triples",
                      "DROP TABLE IF EXISTS idp_sbx.kpi_store", "DROP TABLE IF EXISTS rehearsal.doc_snippets_1.epm_triples"):
        with pytest.raises(f.Refused, match="only the throwaway schemas may be changed"):
            f.to_scratch(statement, names)
    # Any other statement, a second name, a quoted name, CASCADE or a name with no schema is never sent.
    for statement in ("DROP TABLE idp_sbx.kpi_store.a", "DROP TABLE IF EXISTS idp_sbx.kpi_store.a, workspace.default.b",
                      "DROP TABLE IF EXISTS epm_triples", "DROP CATALOG idp_sbx", "DROP SCHEMA IF EXISTS idp_sbx.kpi_store CASCADE",
                      "DROP TABLE IF EXISTS `workspace`.`default`.`b`", "USE CATALOG workspace", "DELETE FROM idp_sbx.kpi_store.a",
                      "DROP TABLE IF EXISTS idp_sbx.kpi_store.a; DROP TABLE x"):
        with pytest.raises(f.Refused, match="only one DROP TABLE, DROP VOLUME or DROP SCHEMA"):
            f.to_scratch(statement, names)
    schema = "rehearsal.doc_snippets_1"
    assert f.only_inside(f"INSERT INTO {schema}.t__staging_1 (a) SELECT decode(unbase64(c0), 'x.y') FROM VALUES ('a.b') AS v(c0)", schema)
    for statement in (f"CREATE TABLE {schema}.t AS SELECT * FROM workspace.default.b", "SELECT 1", f"SELECT * FROM `{schema}`.t",
                      "CREATE TABLE rehearsal.doc_snippets_10.t (a STRING)"):
        with pytest.raises(f.Refused, match="only tables of rehearsal.doc_snippets_1 may be used"):
            f.only_inside(statement, schema)


def test_a_cypher_statement_cannot_name_another_database():
    f = fixtures_module()
    for statement in ("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS", "DROP CONSTRAINT n10s_unique_uri IF EXISTS",
                      "MATCH (n) RETURN count(n) AS nodes_left", "SHOW CONSTRAINTS YIELD name RETURN count(name) AS constraints_left",
                      "MATCH (n {note: 'USE the DATABASE'}) RETURN n"):
        assert f.check_cypher(statement, "scratch") == statement
    assert f.check_cypher("CALL db.info() YIELD name RETURN name", "read")
    refused = {
        "USE businessprocessarchitecturegraph MATCH (n) DETACH DELETE n": "starts with MATCH",
        "MATCH (n) CALL { USE businessprocessarchitecturegraph MATCH (m) DETACH DELETE m } RETURN n": "holds USE",
        "MATCH (n) CALL (n) { use graph.byName('neo4j') MATCH (m) DETACH DELETE m } RETURN n": "holds USE",
        "DROP DATABASE businessprocessarchitecturegraph": "starts with MATCH",
        "CREATE DATABASE other": "starts with MATCH", "DROP ALIAS a FOR DATABASE": "starts with MATCH",
        "STOP DATABASE neo4j": "starts with MATCH", "ALTER DATABASE neo4j SET ACCESS READ ONLY": "starts with MATCH",
        "SHOW DATABASES": "starts with MATCH", "CREATE (n:Written)": "starts with MATCH",
        "MATCH (n) CALL apoc.cypher.runWrite('MATCH (m) DETACH DELETE m', {}) YIELD value RETURN n": "calls the procedure apoc.cypher.runWrite",
        "MATCH (n) CALL dbms.listConfig() YIELD name RETURN name": "calls the procedure dbms.listConfig",
        "CALL db.info() YIELD name RETURN name": "starts with MATCH",        # the throwaway database only empties and counts
    }
    for statement, why in refused.items():
        with pytest.raises(f.Refused, match=why):
            f.check_cypher(statement, "scratch")
    # A comment between CALL and the name, or backticks around the name, hide no procedure: the server reads the
    # statement without its comments, and a name in backticks as the name.
    hidden = {
        "MATCH (n) CALL /* x */ apoc.bolt.execute('bolt://other', 'CREATE (m)', {}) YIELD value RETURN value": "calls the procedure apoc.bolt.execute",
        "MATCH (n) CALL/**/apoc.bolt.execute('bolt://other', 'CREATE (m)', {}) YIELD value RETURN value": "calls the procedure apoc.bolt.execute",
        "MATCH (n) CALL // x\n apoc.bolt.execute('bolt://other', 'CREATE (m)', {}) YIELD value RETURN value": "calls the procedure apoc.bolt.execute",
        "MATCH (n) CALL `apoc`.`bolt`.`execute`('bolt://other', 'CREATE (m)', {}) YIELD value RETURN value": "calls the procedure apoc.bolt.execute",
        "MATCH (n) CALL apoc . bolt . execute('bolt://other', 'CREATE (m)', {}) YIELD value RETURN value": "calls the procedure apoc.bolt.execute",
        "MATCH (n) CALL db.`info`.`x y`() YIELD name RETURN name": "a CALL whose procedure name cannot be read",
        "MATCH (n) CALL `a``b`() YIELD name RETURN name": "a CALL whose procedure name cannot be read",
        "MATCH (n) CALL $name() YIELD name RETURN name": "a CALL whose procedure name cannot be read",
        "MATCH (n) /* a note */ CALL { U/* x */SE neo4j MATCH (m) RETURN m } RETURN n": "",   # checked below: not USE
        "MATCH (n) CALL { /* ' */ USE neo4j MATCH (m) RETURN m /* ' */ } RETURN n": "holds USE",
    }
    for statement, why in hidden.items():
        if not why:
            assert f.check_cypher(statement, "scratch") == statement      # U SE is no keyword; the server refuses it
            continue
        with pytest.raises(f.Refused, match=why):
            f.check_cypher(statement, "scratch")
    # A comment mark inside a string is text, a quote inside a comment is comment, and a subquery after a comment stays.
    for statement in ("MATCH (n {note: '// CALL apoc.x() /* '}) RETURN n", "MATCH (n) // it's a note\nRETURN n",
                      "MATCH (n) CALL /* each node */ (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS",
                      "MATCH (n:`CALL apoc.x`) RETURN n"):
        assert f.check_cypher(statement, "scratch") == statement
    assert f.check_cypher("CALL /* which */ db.info() YIELD name RETURN name", "read")
    for statement in ("MATCH (n) DETACH DELETE n", "MATCH (n) RETURN n"):       # a read session refuses a write itself
        assert f.check_cypher(statement, "read")
    with pytest.raises(f.Refused, match="holds USE"):
        f.check_cypher("MATCH (n) CALL { USE neo4j MATCH (m) RETURN m } RETURN n", "read")
    with pytest.raises(f.Refused, match="starts with MATCH"):
        f.check_cypher("DROP CONSTRAINT n10s_unique_uri IF EXISTS", "read")


class FakeNeo4j:
    """A stand-in for the driver: it records every statement with its database, and holds the names a server has."""

    def __init__(self, databases=(), aliases=(), fail_on=None):
        self.databases, self.aliases, self.fail_on, self.sent = list(databases), list(aliases), fail_on, []

    def session(self, database=None, **options):
        return self._Session(self, database)

    class _Session:
        def __init__(self, server, database):
            self.server, self.database = server, database

        def __enter__(self):
            return self

        def __exit__(self, *error):
            return False

        def run(self, statement):
            server = self.server
            if server.fail_on and server.fail_on in statement:
                raise RuntimeError("the server refused")
            server.sent.append((self.database, statement))
            names = server.databases if statement.startswith("SHOW DATABASES") else server.aliases if statement.startswith("SHOW ALIASES") else []
            created = re.match(r"CREATE (?:COMPOSITE )?DATABASE (\w+)", statement)
            if created:
                server.databases.append(created.group(1))

            class Result:
                def value(self):
                    return list(names)

                def consume(self):
                    return None
            return Result()


def test_a_neo4j_fixture_makes_its_own_databases_and_removes_only_those(tmp_path):
    f = fixtures_module()
    assert f.new_name("scratch") != f.new_name("scratch") and re.fullmatch(r"docsnippetsscratch[0-9a-f]{8}", f.new_name("scratch"))
    server = FakeNeo4j(databases=["neo4j", "system", "businessprocessarchitecturegraph"])
    name = f.scratch_up(server, tmp_path, "docsnippetsscratch00000001")
    assert f.created(tmp_path) == [["database", name]]
    assert ("system", f"CREATE DATABASE {name} WAIT") in server.sent
    assert all(database in ("system", name) for database, _ in server.sent)        # nothing is sent to another database
    assert not any(statement.startswith("DROP") or "DELETE" in statement for _, statement in server.sent)
    server.sent.clear()
    assert f.remove_created(server, tmp_path) == 0
    assert server.sent == [("system", f"DROP DATABASE {name} IF EXISTS WAIT")] and f.created(tmp_path) == []
    # The questions' fixture: two databases, the composite, two aliases. Removed newest first, and nothing else.
    names = {"composite": "docsnippetscomposite1", "governance": "docsnippetsgovernance1", "bpa": "docsnippetsbpa1"}
    server.sent.clear()
    f.questions_up(server, tmp_path, names)
    assert f.created(tmp_path) == [["database", "docsnippetsgovernance1"], ["database", "docsnippetsbpa1"], ["composite", "docsnippetscomposite1"],
                                   ["alias", "docsnippetscomposite1.governance"], ["alias", "docsnippetscomposite1.bpa"]]
    loaded = {database for database, statement in server.sent if database != "system"}
    assert loaded == {"docsnippetsgovernance1", "docsnippetsbpa1"}
    assert not any("DELETE" in statement or statement.startswith("DROP") or "IF NOT EXISTS" in statement for _, statement in server.sent)
    server.sent.clear()
    assert f.remove_created(server, tmp_path) == 0
    assert [statement for _, statement in server.sent] == [
        "DROP ALIAS docsnippetscomposite1.bpa IF EXISTS FOR DATABASE", "DROP ALIAS docsnippetscomposite1.governance IF EXISTS FOR DATABASE",
        "DROP COMPOSITE DATABASE docsnippetscomposite1 IF EXISTS WAIT", "DROP DATABASE docsnippetsbpa1 IF EXISTS WAIT",
        "DROP DATABASE docsnippetsgovernance1 IF EXISTS WAIT"]


def test_a_neo4j_fixture_never_empties_or_drops_a_database_that_was_there(tmp_path, capsys):
    f = fixtures_module()
    # A name the fixture wants is taken: it stops before it makes, empties or drops anything, and so does its `down`.
    for held in ({"databases": ["docsnippetsbpa1"]}, {"aliases": ["docsnippetscomposite1"]}, {"databases": ["DocSnippetsGovernance1"]}):
        server, folder = FakeNeo4j(**held), tmp_path / str(len(list(tmp_path.iterdir())))
        folder.mkdir()
        with pytest.raises(f.Refused, match="the server already holds"):
            f.questions_up(server, folder, {"composite": "docsnippetscomposite1", "governance": "docsnippetsgovernance1", "bpa": "docsnippetsbpa1"})
        assert all(statement.startswith("SHOW ") for _, statement in server.sent) and f.created(folder) == []
        assert f.remove_created(server, folder) == 0
        assert all(statement.startswith("SHOW ") for _, statement in server.sent)
    server, folder = FakeNeo4j(databases=["docsnippetsscratch1"]), tmp_path / "scratch"
    folder.mkdir()
    with pytest.raises(f.Refused, match="the server already holds docsnippetsscratch1"):
        f.scratch_up(server, folder, "docsnippetsscratch1")
    assert f.remove_created(server, folder) == 0 and all(statement.startswith("SHOW ") for _, statement in server.sent)
    # A set-up that stops halfway removes what it had made, and only that.
    server, folder = FakeNeo4j(databases=["neo4j"], fail_on="CREATE COMPOSITE"), tmp_path / "half"
    folder.mkdir()
    with pytest.raises(RuntimeError):
        f.questions_up(server, folder, {"composite": "docsnippetscomposite2", "governance": "docsnippetsgovernance2", "bpa": "docsnippetsbpa2"})
    assert f.created(folder) == [["database", "docsnippetsgovernance2"], ["database", "docsnippetsbpa2"]]
    server.sent.clear()
    assert f.remove_created(server, folder) == 0
    assert [statement for _, statement in server.sent] == ["DROP DATABASE docsnippetsbpa2 IF EXISTS WAIT",
                                                           "DROP DATABASE docsnippetsgovernance2 IF EXISTS WAIT"]
    # A drop that fails is named with the statement that removes the thing by hand, and stays on record.
    server, folder = FakeNeo4j(fail_on="DROP DATABASE docsnippetsscratch3"), tmp_path / "left"
    folder.mkdir()
    f.record(folder, "database", "docsnippetsscratch3")
    assert f.remove_created(server, folder) == 1 and f.created(folder) == [["database", "docsnippetsscratch3"]]
    assert "left behind: the database docsnippetsscratch3 (RuntimeError). Remove it by hand, in the system database: " \
           "DROP DATABASE docsnippetsscratch3 IF EXISTS WAIT" in capsys.readouterr().out
    f.record(folder, "database", "neo4j")
    with pytest.raises(f.Refused, match="neo4j is not a name this fixture makes"):
        f.remove_created(FakeNeo4j(), folder)


# ---- the links of the documents ----

def tree(tmp_path, files):
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8", newline="\n")
    return tmp_path


def test_a_markdown_link_to_a_missing_file_fails_with_its_document_and_line(tmp_path):
    root = tree(tmp_path, {"guide.md": "# Guide\n\nRead [the runbook](docs/runbook.md) and [the notes](docs/notes.md).\n",
                           "docs/runbook.md": "Back to [the guide](../guide.md#top).\n"})
    assert d.broken_links(root) == ["guide.md:3: the link docs/notes.md is not a file or a folder of the tree"]


def test_a_link_whose_target_stands_on_the_next_line_is_read():
    # A target may start on the line after "](". The link belongs to the line that opens it.
    assert d.markdown_links("see [the guide](\n  not-there.md) and\n[two](a.md) [three](\nb.md \"title\")\n") == [
        (1, "not-there.md"), (3, "a.md"), (3, "b.md")]
    # A code line after "](" is not a target.
    assert d.markdown_links("an open [bracket](\n\n    indented.md)\n") == []


def test_links_with_a_scheme_and_anchors_are_not_checked_and_the_path_before_an_anchor_is(tmp_path):
    root = tree(tmp_path, {"a.md": "[site](https://example.org/x.md) [mail](mailto:someone@example.org) [part](#part)\n"
                                   "[other](b.md#part) [gone](c.md#part) [query](b.md?x=1)\n", "b.md": ""})
    assert d.broken_links(root) == ["a.md:2: the link c.md#part is not a file or a folder of the tree"]


def test_a_link_inside_code_is_not_a_link_and_an_image_and_a_reference_definition_are(tmp_path):
    text = "\n".join(["Write `[text](missing-1.md)` for a link.", "", "```text skip reason=\"x\"", "[text](missing-2.md)", "```", "",
                      "![a picture](missing-3.png)", "", "[name]: missing-4.md", ""])
    root = tree(tmp_path, {"a.md": text})
    assert d.broken_links(root) == ["a.md:7: the link missing-3.png is not a file or a folder of the tree",
                                    "a.md:9: the link missing-4.md is not a file or a folder of the tree"]


def test_a_link_may_name_a_folder_a_title_and_a_name_with_a_space_or_brackets(tmp_path):
    root = tree(tmp_path, {"a.md": "[folder](docs/) [same](docs) [title](docs/b.md \"The title\") [space](docs/my%20file.md)\n"
                                   "[angle](<docs/my file.md>) [round](docs/c_(1).md) [up](../outside.md)\n",
                           "docs/b.md": "", "docs/my file.md": "", "docs/c_(1).md": ""})
    assert d.broken_links(root) == ["a.md:2: the link ../outside.md points outside the tree"]


def test_a_link_that_differs_from_the_file_name_only_in_case_fails(tmp_path):
    root = tree(tmp_path, {"a.md": "[readme](docs/readme.md)\n", "docs/README.md": ""})
    assert d.broken_links(root) == ["a.md:1: the link docs/readme.md is not a file or a folder of the tree"]


def test_an_html_page_s_href_and_src_are_checked_and_its_script_text_is_not(tmp_path):
    page_text = "\n".join(['<html><head><link rel="stylesheet" href="style.css"><script src="app.js"></script></head><body>',
                           '<a href="guide.md">guide</a> <a href="gone.html#x">gone</a> <a href="https://example.org/">site</a>',
                           '<img src="pictures/missing.png">',
                           '<script>var data = {"href": "not-a-file.json"}; var s = \'<a href="also-not.html">\';</script>',
                           '</body></html>'])
    root = tree(tmp_path, {"page.html": page_text, "guide.md": "", "style.css": "", "app.js": ""})
    assert d.broken_links(root) == ["page.html:2: the link gone.html#x is not a file or a folder of the tree",
                                    "page.html:3: the link pictures/missing.png is not a file or a folder of the tree"]


def test_the_links_command_exits_1_on_a_broken_link_and_0_on_none(tmp_path, capsys):
    root = tree(tmp_path, {"a.md": "[b](b.md)\n"})
    assert d.main(["--root", str(root), "links"]) == 1
    assert capsys.readouterr().out == "FAIL a.md:1: the link b.md is not a file or a folder of the tree\n1 broken link(s)\n"
    (root / "b.md").write_text("", encoding="utf-8", newline="\n")
    assert d.main(["--root", str(root), "links"]) == 0
    assert capsys.readouterr().out == "every relative link points at a file or a folder of the tree\n"


def test_this_tree_s_documents_hold_no_broken_link():
    assert d.broken_links(d.ROOT) == []


def test_the_formulas_quoted_as_text_in_the_crack_spread_definition_hold():
    """The three formula blocks of the KPI definition are text, so no tool runs them. This reads them from the
    document and works them out: the two forms of the Ex-RVO formula give the same number, Ex-RVO is Inc-RVO less
    the RVO of a barrel, and each set of regional weights adds up to 1."""
    doc = d.ROOT / "business_architecture/reference/internal/crack-spread-kpi-definition.md"
    blocks = re.findall(r'```text skip reason="illustration: a formula[^"]*"\n(.*?)```', doc.read_text(encoding="utf-8"), re.S)
    assert len(blocks) == 3

    def worked(block, **values):
        """Each line of the block that holds a multiplication, worked out with the given values."""
        results = []
        for line in block.splitlines():
            if "×" not in line:
                continue
            text = line.split(":")[-1].strip().lstrip("=")
            results.append(eval(text.replace("×", "*").replace("−", "-"), {"__builtins__": {}}, values))
        return results

    for prices in ({"CBOB": 2.31, "ULSD": 2.67, "Crude": 78.4, "RVO": 0.13}, {"CBOB": 1.0, "ULSD": 3.5, "Crude": 60.0, "RVO": 0.0},
                   {"CBOB": 3.02, "ULSD": 2.2, "Crude": 101.25, "RVO": 0.41}):
        ex_rvo, equivalent = worked(blocks[0], **prices)
        (inc_rvo,) = worked(blocks[1], **prices)
        assert ex_rvo == pytest.approx(equivalent)
        assert ex_rvo == pytest.approx(inc_rvo - prices["RVO"] * 42)
    assert worked(blocks[2], USGC=1, Chicago=1, LA=1) == [pytest.approx(1.0), pytest.approx(1.0)]
