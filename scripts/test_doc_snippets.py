"""Tests for scripts/doc_snippets.py, which tests every code block in the Markdown documents.

Each test writes a small document by hand into a temporary folder and checks what the tool says about it. The
last tests read this tree: its registry, its documents and their tags. scripts/check.sh runs the blocks of the
tree itself with `doc_snippets.py check`, which prints the count.

Run: uv run --no-project --with pytest --with rdflib --with pyyaml --with sqlglot python -m pytest -q scripts/test_doc_snippets.py
"""
import hashlib
import os
import sys
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
"""


def fence(info, *body):
    return "\n".join(["```" + info, *body, "```", ""])


def check(tmp_path, text, *, files=None, environ=None, registry=REGISTRY, **options):
    """Check one hand-written document, guide.md, in a temporary tree."""
    root = tmp_path / "tree"
    root.mkdir(exist_ok=True)
    (root / "guide.md").write_text(text, encoding="utf-8", newline="\n")
    for name, content in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content, encoding="utf-8", newline="\n")
    (tmp_path / "registry.toml").write_text(registry, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in (d.NESTED, d.NESTED_FILE)}
    env.update(environ or {})
    checker = d.Checker(root, d.load_registry(tmp_path / "registry.toml"), environ=env, **options)
    return checker.check(["guide.md"])


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
                               "parse, nested"]


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


def test_a_run_block_needs_a_known_context_and_a_language_that_runs(tmp_path):
    text = (fence("python run status-only", "pass") + fence("python run=nowhere status-only", "pass")
            + fence("json run=scratch status-only", "{}"))
    result = check(tmp_path, text)
    assert result.failures == [
        "guide.md:1: a run block names its context: `run=<context>` (one of copy, gated, other, quick, repo, scratch, signed-in)",
        "guide.md:4: no context named `nowhere` in doc_snippets.toml: use one of copy, gated, other, quick, repo, "
        "scratch, signed-in",
        "guide.md:7: a `json` block cannot run: `run` takes bash, sh, python, powershell, cmd"]


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
    wrong.write_text("another value", encoding="utf-8")
    assert check(tmp_path, text, environ={d.NESTED: "abc", d.NESTED_FILE: str(wrong)}).failures == message
    wrong.write_text("abc", encoding="utf-8")
    proved = check(tmp_path, text, environ={d.NESTED: "abc", d.NESTED_FILE: str(wrong)})
    assert proved.failures == [] and proved.nested
    assert proved.skipped == {"not run: a check started by a block runs no block": 1}


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
    (root / "data" / "a.txt").write_text("from the tree\n", encoding="utf-8")
    (root / "guide.md").write_text(text, encoding="utf-8")
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
    (tree / "guide.md").write_text(fence("cypher parse", "MATCH (n) RETURN n"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONDONTWRITEBYTECODE", d.NESTED, d.NESTED_FILE)}
    r = subprocess.run([sys.executable, str(tree / "scripts" / "doc_snippets.py"), "check"], cwd=tree, env=env,
                       capture_output=True, text=True)
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


needs_links = pytest.mark.skipif(os.name == "nt", reason="making a link needs a privilege on Windows")


@needs_links
def test_a_link_inside_the_tree_is_copied_as_what_it_points_to(tmp_path):
    """Copied as a link, it pointed back into the tree, and a block that wrote through it changed the tree."""
    root = tmp_path / "tree"
    (root / "data").mkdir(parents=True)
    (root / "data" / "a.txt").write_text("from the tree\n", encoding="utf-8")
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
    outside.write_text("not part of the release\n", encoding="utf-8")
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


def test_a_command_cannot_be_parsed_instead_of_run(tmp_path):
    result = check(tmp_path, fence("bash parse", "echo hello"))
    assert result.failures == ["guide.md:1: `bash` cannot be parsed: `parse` reads json, toml, yaml, turtle, sparql, "
                               "sql, cypher. A command is tagged `run` or `skip`"]


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
    ("py -m kpi_store.runner --settings kpi_store.toml", ["py", "-m", "kpi_store.runner", "--settings", "kpi_store.toml"]),
    ('py tool.py --why "Two words" --empty ""', ["py", "tool.py", "--why", "Two words", "--empty", ""]),
    (r"py -m tool C:\kpi-store\report.json 'single quoted'", ["py", "-m", "tool", r"C:\kpi-store\report.json", "single quoted"]),
    ("  java   -jar  fuseki.jar ", ["java", "-jar", "fuseki.jar"]),
])
def test_a_plain_command_line_splits_into_its_arguments(line, args):
    assert d.split_command(line) == args


@pytest.mark.parametrize("line", ["py a.py | more", "py a.py > out.txt", "$env:X = 1", "py a.py; py b.py",
                                  'py a.py "$NAME"', "py a.py %NAME%", "py a.py && py b.py", 'py "open'])
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
    text = (fence("powershell run=copy", "# A comment line.", "cd tools", 'py show.py "two words" `', "    last")
            + fence("text expect", "['two words', 'last']")
            + fence("cmd run=copy status-only", "REM back in the top folder", "cd ..", "py tools/show.py one"))
    result = check(tmp_path, text, files={"tools/show.py": "import sys\nprint(sys.argv[1:])\n"})
    assert result.failures == [] and result.summary() == "3 blocks: 2 run (1 status-only), 1 checked, 0 skipped"


def test_a_powershell_block_with_shell_syntax_fails_unless_it_says_windows(tmp_path):
    result = check(tmp_path, "# Guide\n\n" + fence("powershell run=scratch status-only", "py -c \"print(1)\"", "$env:A = 1"),
                   static=True)
    assert result.failures == ["guide.md:3: line 5 is not a plain command line (`$`). Write it without shell syntax, "
                               "or add os=windows so that it runs in a real shell on Windows only"]


@pytest.mark.skipif(os.name == "nt", reason="on Windows the block runs")
def test_a_block_for_windows_only_is_counted_elsewhere(tmp_path):
    result = check(tmp_path, fence("powershell run=scratch os=windows status-only", "$env:A = 1; py -c \"print($env:A)\""))
    assert result.failures == [] and result.summary() == "1 blocks: 0 run (0 status-only), 0 checked, 1 skipped (windows-only 1)"


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


# -- the command


def test_the_command_prints_each_failure_and_the_count_and_exits_1(tmp_path, capsys):
    (tmp_path / "guide.md").write_text(fence("json parse", "{}") + fence("text", "no tag"), encoding="utf-8")
    assert d.main(["--root", str(tmp_path), "check"]) == 1
    assert capsys.readouterr().out == ("FAIL guide.md:4: the block has no tag after its language `text`\n"
                                       "2 blocks: 0 run (0 status-only), 1 checked, 0 skipped, 1 failed\n")
    (tmp_path / "guide.md").write_text(fence("json parse", "{}"), encoding="utf-8")
    assert d.main(["--root", str(tmp_path), "check", "guide.md"]) == 0
    assert capsys.readouterr().out == "1 blocks: 0 run (0 status-only), 1 checked, 0 skipped\n"
    assert d.main(["--root", str(tmp_path), "list"]) == 0
    assert capsys.readouterr().out == "   1  guide.md: parse 1\n   1  total: parse 1\n"


def test_the_html_command_counts_only_pages_with_no_markdown_source(tmp_path, capsys):
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "a.html").write_text("<pre>from a.md</pre>", encoding="utf-8")
    (tmp_path / "built.html").write_text('<meta name="generator" content="x"><pre>built</pre>', encoding="utf-8")
    (tmp_path / "hand.html").write_text("<pre><code>one</code></pre><p><code>two</code> <code>three</code></p>"
                                        "<pre class='x'>four</pre>", encoding="utf-8")
    assert d.html_pages(tmp_path) == [("hand.html", 2, 2)]


def test_a_registry_with_an_unknown_key_or_base_is_refused(tmp_path):
    path = tmp_path / "r.toml"
    path.write_text('[contexts.a]\nbase = "empty"\nshell = true\n', encoding="utf-8")
    with pytest.raises(d.RegistryError, match="context a has unknown key"):
        d.load_registry(path)
    path.write_text('[contexts.a]\nbase = "the tree itself"\n', encoding="utf-8")
    with pytest.raises(d.RegistryError, match="context a needs base"):
        d.load_registry(path)
    path.write_text('[reasons]\nillustration = "x"\ntemporary_reasons = ["illustration"]\n', encoding="utf-8")
    with pytest.raises(d.RegistryError, match="the reason temporary_reasons needs a sentence"):
        d.load_registry(path)
    path.write_text('temporary_reasons = ["later"]\n', encoding="utf-8")
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
        "stores": ("KPI_STORE_TEST_FUSEKI_URL", "KPI_STORE_TEST_NEO4J_URI"),
        "databricks-free": ("KPI_STORE_TEST_DATABRICKS_PROFILE",)}
    assert [name for name, c in contexts.items() if c.home == "real"] == ["databricks-free"]


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


def test_a_markdown_file_git_ignores_is_outside_the_scan(tmp_path):
    """The rule of the scan: what Git tracks or would add. An ignored file does not ship. A folder with no Git
    is read whole."""
    import subprocess
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for folder in ("repository", "plain"):
        (tmp_path / folder).mkdir()
        for name, content in (("tracked.md", "# T\n"), ("new.md", "# N\n"), ("notes.md", "# I\n"),
                              (".gitignore", "notes.md\n")):
            (tmp_path / folder / name).write_text(content, encoding="utf-8")
    for args in (["init", "-q"], ["add", "tracked.md", ".gitignore"]):
        subprocess.run(["git", *args], cwd=tmp_path / "repository", env=env, check=True, capture_output=True)
    assert d.documents(tmp_path / "repository") == ["new.md", "tracked.md"]
    assert d.documents(tmp_path / "plain") == ["new.md", "notes.md", "tracked.md"]


def test_no_part_of_the_tool_is_a_long_file():
    parts = sorted((d.ROOT / "scripts" / "doc_snippets_parts").glob("*.py")) + [d.ROOT / "scripts" / "doc_snippets.py"]
    assert [p.name for p in parts] == ["__init__.py", "check.py", "extract.py", "match.py", "parsers.py",
                                       "registry.py", "report.py", "run.py", "doc_snippets.py"]
    for part in parts:
        assert len(part.read_text(encoding="utf-8").split("\n")) < 500, part.name


def test_every_block_of_the_tree_has_a_valid_tag():
    """The static half of the check, so that this file alone finds a block with no tag. scripts/check.sh then runs
    the blocks with `doc_snippets.py check`."""
    result = d.Checker(static=True).check()
    assert result.failures == []
    assert result.total > 80
