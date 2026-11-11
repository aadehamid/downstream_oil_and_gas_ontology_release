"""Pin the figures epm-facts reports, so a change that moves one fails here first.

Run: uv run --with pytest python -m pytest -q scripts/test_epm_facts.py

When a figure changes on purpose (a Phase 1 batch merges, a release lands),
update the pinned value in the same change and say why in its body.
"""
import csv
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import epm_facts  # noqa: E402


def run(*args):
    out = subprocess.check_output([sys.executable, os.path.join(HERE, "epm_facts.py"), "--json", *args], text=True)
    return json.loads(out)


def test_find_catches_text_split_across_lines(tmp_path):
    # A fixture repository: the live text this test first searched (the playbook's "the decision of 2026-10-05,
    # decided") moved to the worklog on one line when the playbook's evidence moved there (2026-10-23).
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    (tmp_path / "doc.md").write_text("In this repository this is the decision of 2026-10-05,\n  decided 2026-10-06.\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, env=env)
    hits = epm_facts.find_hits("the decision of 2026-10-05, decided", str(tmp_path))
    assert [(name, line, kind) for name, line, kind, _ in hits] == [("doc.md", 1, "split")]


def test_find_skips_only_a_fresh_generated_copy(tmp_path, monkeypatch):
    # A page the builder makes is a copy of its Markdown, so a search counts the Markdown only. A page that
    # carries the generator's mark but is hand-written, stale, or no longer built is searched like any file.
    import build_docs_html
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    head = f"<html><head>{build_docs_html.MARK}</head>\n"
    fresh = head + "<p>The crack spread is a margin.</p></html>\n"
    (tmp_path / "README.md").write_text("The crack spread is a margin.\n", encoding="utf-8", newline="\n")
    (tmp_path / "README.html").write_text(fresh, encoding="utf-8", newline="\n")
    (tmp_path / "stale.html").write_text(head + "<p>The crack spread was edited by hand.</p></html>\n", encoding="utf-8", newline="\n")
    (tmp_path / "orphan.html").write_text(head + "<p>A crack spread page no source builds.</p></html>\n", encoding="utf-8", newline="\n")
    (tmp_path / "ontology-stores-runbook.html").write_text("<html><head></head>\n<p>The crack spread is a margin.</p></html>\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, env=env)
    monkeypatch.setattr(epm_facts, "built_pages", lambda root: {"README.html": fresh, "stale.html": fresh})
    hits = epm_facts.find_hits("crack spread", str(tmp_path))
    assert sorted(name for name, _, _, _ in hits) == ["README.md", "ontology-stores-runbook.html", "orphan.html", "stale.html"]


def test_sweep_takes_the_changed_words_with_their_context():
    diff = ("@@ -1 +1 @@\n-The regression stands at 34 answerable and 9 waiting.\n"
            "+The regression stands at 42 answerable and 1 waiting.\n")
    assert epm_facts.changed_phrases(diff) == ["at 34 answerable", "and 9 waiting"]


def test_sweep_takes_context_from_an_unchanged_neighbouring_line():
    # "At 686" changes, "answerable." on the next line does not.
    diff = "@@ -1,2 +1,2 @@\n-At 686\n+At 409\n answerable.\n"
    assert epm_facts.changed_phrases(diff) == ["At 686 answerable"]


def test_sweep_does_not_take_context_from_another_change():
    # two nearby changes in one -U1 hunk keep their own context.
    diff = "@@ -1,2 +1,2 @@\n-the ledger holds 34\n+the ledger holds 42\n-9 waiting\n+1 waiting\n"
    assert epm_facts.changed_phrases(diff) == ["holds 34", "9 waiting"]


def test_sweep_does_not_take_context_across_a_blank_line():
    diff = "@@ -1,3 +1,3 @@\n-the ledger holds 34\n+the ledger holds 42\n \n-9 waiting\n+1 waiting\n"
    assert epm_facts.changed_phrases(diff) == ["holds 34", "9 waiting"]


def test_sweep_counts_a_word_moved_to_another_line_as_changed():
    # two lines swap their values; each line's old value is still searched.
    diff = "@@ -1,2 +1,2 @@\n-the ledger holds 34\n-9 waiting\n+the ledger holds 9\n+34 waiting\n"
    assert epm_facts.changed_phrases(diff) == ["holds 34", "9 waiting"]


def test_sweep_finds_a_phrase_whose_context_is_on_an_unchanged_line(tmp_path, monkeypatch):
    # End to end, so the diff's context flag is tested too: with -U0 the sweep returns nothing here.
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)

    def git(*a):
        subprocess.check_call(["git", "-C", str(tmp_path), *a], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "source.md").write_text("At 686\nanswerable.\n", encoding="utf-8", newline="\n")
    (tmp_path / "stale.md").write_text("At 686 answerable.\n", encoding="utf-8", newline="\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    (tmp_path / "source.md").write_text("At 409\nanswerable.\n", encoding="utf-8", newline="\n")
    git("commit", "-q", "-am", "change")
    report = dict(epm_facts.sweep("HEAD~1", root=str(tmp_path)))
    assert [(name, i) for name, i, _, _ in report["At 686 answerable"]] == [("stale.md", 1)]


def test_sweep_finds_both_old_values_of_two_swapped_lines(tmp_path, monkeypatch):
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)

    def git(*a):
        subprocess.check_call(["git", "-C", str(tmp_path), *a], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "source.md").write_text("the ledger holds 34\n9 waiting\n", encoding="utf-8", newline="\n")
    (tmp_path / "stale-one.md").write_text("the ledger holds 34\n", encoding="utf-8", newline="\n")
    (tmp_path / "stale-two.md").write_text("9 waiting\n", encoding="utf-8", newline="\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    (tmp_path / "source.md").write_text("the ledger holds 9\n34 waiting\n", encoding="utf-8", newline="\n")
    git("commit", "-q", "-am", "swap")
    report = dict(epm_facts.sweep("HEAD~1", root=str(tmp_path)))
    assert [name for name, *_ in report["holds 34"]] == ["stale-one.md"]
    assert [name for name, *_ in report["9 waiting"]] == ["stale-two.md"]


def test_sweep_reads_a_deleted_line_that_starts_with_dashes():
    diff = ("diff --git a/x.md b/x.md\n--- a/x.md\n+++ b/x.md\n@@ -1 +1 @@\n"
            "--- the ledger holds 686 rows\n+-- the ledger holds 409 rows\n")
    assert epm_facts.changed_phrases(diff) == ["holds 686 rows"]


def test_sweep_finds_the_old_wording_left_elsewhere(tmp_path, monkeypatch):
    # A clean environment, for this test's git calls and the sweep's: in a pre-push hook git sets GIT_DIR,
    # and an inherited GIT_DIR would point every call at the real repository instead of tmp_path.
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)

    def git(*a):
        subprocess.check_call(["git", "-C", str(tmp_path), *a], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "a.md").write_text("Three systems are matched.\n", encoding="utf-8", newline="\n")
    (tmp_path / "b.md").write_text("Here three\nsystems are matched, split across lines.\n", encoding="utf-8", newline="\n")
    (tmp_path / "c.md").write_text("Three systems are matched *2026-10-21:* four.\n", encoding="utf-8", newline="\n")
    (tmp_path / "d.sql").write_text("-- Three systems feed this view (Superseded 2026-10-22: four).\n", encoding="utf-8", newline="\n")
    (tmp_path / "e.page").write_text("Three systems, as the page says.\n", encoding="utf-8", newline="\n")
    (tmp_path / "f — guide.md").write_text("Three systems, in a file whose name git quotes.\n", encoding="utf-8", newline="\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    (tmp_path / "a.md").write_text("Four systems are matched.\n", encoding="utf-8", newline="\n")
    git("commit", "-q", "-am", "change")
    report = dict(epm_facts.sweep("HEAD~1", root=str(tmp_path)))
    states = {(name, state) for name, _, state, _ in report["Three systems"]}
    assert states == {("b.md", "live"), ("c.md", "dated"), ("d.sql", "dated"), ("e.page", "live"), ("f — guide.md", "live")}


def _backlog():
    with open(epm_facts.BACKLOG, encoding="utf-8") as f:
        return f.read()


def test_gate_figures_survive_a_failing_gate(tmp_path):
    fake = tmp_path / "evidence-gate.py"
    fake.write_text("import sys\npromoted = 1066\nheld_ctx = 237\nprint('GATE FAILED: 1 check(s)')\nsys.exit(1)\n", encoding="utf-8", newline="\n")
    ns, ok, out = epm_facts.run_keeping_globals(str(fake))
    assert ok is False and "GATE FAILED" in out
    assert (ns["promoted"], ns["held_ctx"]) == (1066, 237)


def _decisions_copy(tmp_path):
    import shutil
    folder = tmp_path / "decisions"
    shutil.copytree(epm_facts.DECISIONS, folder)
    return folder


# ---------- quotes ----------

def _quote_fixture(tmp_path, reason="", owner_words=None, block=None):
    """A copy of the batch 1 review file and the backlog, with one field changed."""
    reviews = tmp_path / "reviews"
    reviews.mkdir(parents=True)
    src = os.path.join(epm_facts.REVIEWS, "precedes-follows-batch1-review.csv")
    with open(src, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if reason:
        rows[7]["semantic_reason"] = reason
    if owner_words:
        rows[0]["owner_words"] = owner_words
    with open(reviews / "batch.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    backlog = tmp_path / "backlog.md"
    with open(epm_facts.BACKLOG, encoding="utf-8") as f:
        text = f.read()
    if block:
        text += f"\n\n> {block}\n"
    backlog.write_text(text, encoding="utf-8", newline="\n")
    return epm_facts.quote_problems(str(reviews), str(backlog), epm_facts.ANSWERS)


def test_quotes_report_when_nothing_was_checked(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    backlog = tmp_path / "backlog.md"
    backlog.write_text("no quotes\n", encoding="utf-8", newline="\n")
    problems = epm_facts.quote_problems(str(empty), str(backlog), str(empty))
    assert any("no saved answer text" in p for p in problems)
    assert any("no review file" in p for p in problems)


def test_quotes_reject_empty_answers_and_blank_rows(tmp_path):
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / "empty.md").write_text("<!-- source header only -->\n", encoding="utf-8", newline="\n")
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    (reviews / "batch.csv").write_text("row_id,owner_words,scope_note_sentence,semantic_reason,owner_decision\nREL-00193,,,,\n", encoding="utf-8", newline="\n")
    backlog = tmp_path / "backlog.md"
    backlog.write_text("", encoding="utf-8", newline="\n")
    problems = epm_facts.quote_problems(str(reviews), str(backlog), str(answers))
    assert any("no saved answer text" in p for p in problems)
    assert any("owner_words is blank" in p for p in problems)


def _decision_fixture(tmp_path, number, words, status="Decided"):
    """A decisions folder holding one record with the given 'the words of a subject matter expert reviewing the documents' section."""
    folder = tmp_path / "decisions"
    folder.mkdir(parents=True)
    (folder / f"DEC-{number:04d}-test.md").write_text(
        f"# DEC-{number:04d}: test\n\n| Field | Value |\n|---|---|\n| Status | {status} |\n\n"
        f"## Decision\n\nThe definition \"The source completes before the target begins\" stays.\n\n"
        f"## the words of a subject matter expert reviewing the documents\n\n{words}\n\n## Evidence\n\nNone.\n", encoding="utf-8", newline="\n")
    reviews = os.path.dirname(epm_facts.REVIEWS + "/")
    return epm_facts.quote_problems(reviews, epm_facts.BACKLOG, epm_facts.ANSWERS, str(folder))


SAVED = '"Approved: Q1–Q18 as recommended in the comment above"'


def _answers(tmp_path, text):
    folder = tmp_path / "answers"
    folder.mkdir(parents=True)
    (folder / "a.md").write_text("<!-- header -->\n\n" + text, encoding="utf-8", newline="\n")
    return str(folder)


def test_rendered_answers_keep_block_boundaries(tmp_path):
    for name, text in {"paragraphs": "yes to all\n\nseven\n", "heading": "yes to all\n\n## seven\n",
                       "list": "- yes to all\n- seven\n", "html": "yes to all\n\n<div>not</div>\n\nseven\n"}.items():
        corpus = epm_facts.rendered_answer_corpus(_answers(tmp_path / name, text))
        assert "yes to all seven" not in corpus, name
    # Line breaks inside one paragraph still read as spaces.
    assert "yes to all seven" in epm_facts.rendered_answer_corpus(_answers(tmp_path / "soft", "yes to all\nseven\n"))


def test_rendered_answers_keep_comment_syntax_in_code(tmp_path):
    corpus = epm_facts.rendered_answer_corpus(_answers(tmp_path / "a", "```text\nApprove <!-- do not --> every risky change\n```\n"))
    assert "Approve every risky change" not in corpus
    assert "Approve <!-- do not --> every risky change" in corpus
    corpus = epm_facts.rendered_answer_corpus(_answers(tmp_path / "b", "Say `a <!-- b --> c` now\n"))
    assert "a <!-- b --> c" in corpus
    assert "header" not in corpus


def _decision_with_answers(tmp_path, answer_text, words):
    answers = _answers(tmp_path, answer_text)
    folder = tmp_path / "decisions"
    folder.mkdir()
    (folder / "the decision of 2026-10-12-test.md").write_text(
        f"# t\n\n| Field | Value |\n|---|---|\n| Status | Decided |\n\n## the words of a subject matter expert reviewing the documents\n\n{words}\n", encoding="utf-8", newline="\n")
    return [p for p in epm_facts.quote_problems(epm_facts.REVIEWS, epm_facts.BACKLOG, answers, str(folder))
            if "the decision of 2026-10-12" in p]


def test_word_match_treats_dashes_as_part_of_a_word():
    match = epm_facts.in_corpus_as_words
    assert not match("author responses to Batch", "source-author responses to Batch 2")
    assert not match("Q18 as recommended in the comment above", "Approved: Q1–Q18 as recommended in the comment above")
    assert not match("not payment completion or the end", "validation—not payment completion or the end")
    assert not match("approve every risky", "approve every risky-change rule")
    assert match("approve every risky change", "Yes, approve every risky change.")


def test_word_match_is_strict_at_punctuation_edges():
    # Strict on purpose: these can be quoted whole instead ("Q1(approve unusual widgets)").
    match = epm_facts.in_corpus_as_words
    assert not match("(approve unusual widgets)", "Q1(approve unusual widgets)")
    assert not match("version 1.", "version 1.2 ships")
    assert match("(approve unusual widgets)", "Say (approve unusual widgets) now")


def test_word_match_treats_apostrophes_marks_and_soft_hyphens_as_part_of_a_word():
    match = epm_facts.in_corpus_as_words
    assert not match("Settlement follows the agreement", "Settlement follows the agreement’s billing schedule")
    assert not match("follows the agreement", "follows the agreement's billing")
    assert not match("Neil wrote the plan", "O’Neil wrote the plan")
    assert not match("approve the cafe", "approve the café order")
    assert not match("approve the auto", "approve the auto­mation")
    assert match("follows the agreement’s billing", "Settlement follows the agreement’s billing schedule")
    assert match("approve every risky change", "(approve every risky change)")


def test_word_match_rejects_a_quote_that_drops_a_possessive():
    match = epm_facts.in_corpus_as_words
    assert not match("We approve workers", "We approve workers’ wages")
    assert not match("Please approve James", "Please approve James' proposal.")
    # Known strict case: a quote inside curly single quotes must include the closing mark.
    assert not match("approve every risky change", "They wrote ‘approve every risky change’ today")
    assert match("approve every risky change’", "They wrote ‘approve every risky change’ today")


def test_no_tracked_file_names_the_decision_owner():
    assert epm_facts.name_problems() == []


def test_names_check_finds_the_owner_in_any_case_path_and_office_file(tmp_path):
    import zipfile
    first, user = "Ha" + "mid", "aade" + "ha" + "mid"
    # A clean environment, so an inherited GIT_DIR or GIT_INDEX_FILE cannot point git elsewhere.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    (tmp_path / "clean.md").write_text("the subject matter expert approved it.\n", encoding="utf-8", newline="\n")
    (tmp_path / "prose.md").write_text(f"line one\n{first.upper()} approved it.\n", encoding="utf-8", newline="\n")
    (tmp_path / "link.md").write_text(f"https://github.com/{user}/repo\n", encoding="utf-8", newline="\n")
    (tmp_path / f"{first.lower()}-notes.txt").write_text("no name inside\n", encoding="utf-8", newline="\n")
    os.symlink("clean.md", tmp_path / f"{first}-link.md")
    with zipfile.ZipFile(tmp_path / "book.xlsx", "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", f"<t>{first}'s verdict</t>")
    # Office shows these cells as the name: a character reference, and two rich-text runs.
    with zipfile.ZipFile(tmp_path / "PROBE.XLSX", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/sharedStrings.xml",
                   '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   "<si><t>H&#97;mid</t></si>\n  <si>\n    <r><t>Ha</t></r>\n    <r><t>mid</t></r>\n  </si></sst>")
        # A sheet tab and an author property, each written with a character reference.
        z.writestr("xl/workbook.xml", '<workbook><sheets><sheet name="H&#97;mid" sheetId="1"/></sheets></workbook>')
        z.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="urn:cp" xmlns:dc="urn:dc">'
                   "<dc:creator>H&#97;mid</dc:creator></cp:coreProperties>")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, env=env)
    assert sorted(epm_facts.name_problems(str(tmp_path))) == sorted([
        "PROBE.XLSX!xl/sharedStrings.xml (displayed text):1: names the decision owner",
        "PROBE.XLSX!xl/sharedStrings.xml (displayed text):2: names the decision owner",
        "PROBE.XLSX!xl/sharedStrings.xml (decoded values):1: names the decision owner",
        "PROBE.XLSX!xl/workbook.xml (decoded values):1: names the decision owner",
        "PROBE.XLSX!docProps/core.xml (decoded values):1: names the decision owner",
        "book.xlsx!xl/worksheets/sheet1.xml:1: names the decision owner",
        "book.xlsx!xl/worksheets/sheet1.xml (decoded values):1: names the decision owner",
        f"{first}-link.md: the path names the decision owner",
        f"{first.lower()}-notes.txt: the path names the decision owner",
        "link.md:1: names the decision owner",
        "link.md (displayed text):1: names the decision owner",
        "prose.md:2: names the decision owner",
        "prose.md (displayed text):2: names the decision owner",
    ])


def test_names_check_reads_every_file_where_there_is_no_git(tmp_path):
    # A tree without .git: every file under the root is read, not only the tracked ones.
    first = "Ha" + "mid"
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "prose.md").write_text(f"line one\n{first} approved it.\n", encoding="utf-8", newline="\n")
    (tmp_path / "clean.md").write_text("the subject matter expert approved it.\n", encoding="utf-8", newline="\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_text(first, encoding="utf-8", newline="\n")
    assert set(epm_facts.name_problems(str(tmp_path))) == {
        "deep/prose.md:2: names the decision owner", "deep/prose.md (displayed text):2: names the decision owner"}


def test_names_check_finds_a_name_split_by_markdown_or_html_formatting(tmp_path):
    # A browser shows these as the name in one piece; a scan of the raw lines does not see it.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    (tmp_path / "emphasis.md").write_text("Approved by H**a**" + "mid on 2026-10-26.\n", encoding="utf-8", newline="\n")
    (tmp_path / "page.html").write_text("<p>Approved by h<strong>a</strong>" + "mid.</p>\n", encoding="utf-8", newline="\n")
    (tmp_path / "plain.html").write_text("<p>Approved by the decision owner.</p>\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, env=env)
    assert sorted(epm_facts.name_problems(str(tmp_path))) == [
        "emphasis.md (displayed text):1: names the decision owner",
        "page.html (displayed text):1: names the decision owner",
    ]


# The module map and coverage (item C of the store-tests handoff).

BUILDER_STUB = 'MODULES = {"lane": {"parts": ["lane/vocabulary.ttl", "lane/lanes.ttl"]}}\n'


def plant_release(releases, module, version, manifest, ttl=""):
    folder = releases / module / version
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"module": module, "version": version, **manifest}), encoding="utf-8", newline="\n")
    (folder / (module + ".ttl")).write_text(ttl, encoding="utf-8", newline="\n")


def test_module_map_follows_a_new_release_and_a_changed_requirement(tmp_path):
    releases, builder = tmp_path / "releases", tmp_path / "build_module.py"
    builder.write_text(BUILDER_STUB, encoding="utf-8", newline="\n")
    plant_release(releases, "core", "1.0.0", {"triples": 5, "built_from": {"process map": "map.json at abc"}})
    plant_release(releases, "lane", "1.0.0", {"triples": 3, "depends_on": {"core": "1.0.0"}})
    before = {m["module"]: m for m in epm_facts.module_releases(str(releases), str(builder))}
    assert before["lane"]["newest"] == "1.0.0" and before["lane"]["requires"] == {"core": "1.0.0"}
    assert (before["lane"]["built_from"], before["lane"]["builder_sources"]) == ([], ["lane/"])
    assert (before["core"]["built_from"], before["core"]["builder_sources"]) == (["map.json at abc"], [])
    plant_release(releases, "core", "2.0.0", {"triples": 6, "built_from": {"core 1.0.0 manifest": "f" * 64}})
    plant_release(releases, "lane", "1.10.0", {"triples": 4, "depends_on": {"core": "2.0.0"}})
    after = {m["module"]: m for m in epm_facts.module_releases(str(releases), str(builder))}
    # 1.10.0 sorts after 1.0.0 as a version, not as text.
    assert (after["lane"]["newest"], after["lane"]["earlier"], after["lane"]["requires"], after["lane"]["triples"]) == \
        ("1.10.0", ["1.0.0"], {"core": "2.0.0"}, 4)
    assert after["core"]["built_from"] == ["core 1.0.0 manifest"]


def test_module_map_follows_the_manifest_and_labels_the_builders_folders(tmp_path, capsys, monkeypatch):
    # The builder today packages lane/ and extra/, but the newer lane release's manifest says it was
    # built from something else: the manifest wins, and a release without one shows the builder's
    # folders under their own label, never as the release's.
    releases, builder = tmp_path / "releases", tmp_path / "build_module.py"
    builder.write_text('MODULES = {"lane": {"parts": ["lane/lanes.ttl", "extra/more.ttl"]},'
                       ' "system": {"parts": ["system/systems.ttl"]}}\n', encoding="utf-8", newline="\n")
    plant_release(releases, "lane", "1.0.0", {"triples": 3})
    plant_release(releases, "lane", "2.0.0", {"triples": 3, "built_from": {"lane table": "lane/old.csv at 123"}})
    plant_release(releases, "system", "1.0.0", {"triples": 2})
    mods = {m["module"]: m for m in epm_facts.module_releases(str(releases), str(builder))}
    assert (mods["lane"]["built_from"], mods["lane"]["builder_sources"]) == (["lane/old.csv at 123"], [])
    assert (mods["system"]["built_from"], mods["system"]["builder_sources"]) == ([], ["system/"])
    monkeypatch.setattr(epm_facts, "RELEASES", str(releases))
    monkeypatch.setattr(epm_facts, "MODULE_BUILDER", str(builder))
    epm_facts.main(["modules"])
    out = capsys.readouterr().out
    assert "lane 2.0.0 (earlier: 1.0.0); requires nothing; 3 triples; built from (release manifest): lane/old.csv at 123" in out
    assert "system 1.0.0 (earlier: none); requires nothing; 2 triples; sources (builder today): system/" in out


def test_module_map_lists_the_released_modules():
    names = [m["module"] for m in epm_facts.module_releases()]
    assert names == ["core", "data-product", "integration", "kpi", "lane", "logical-model", "market-data", "organization", "party", "ref-mpc", "system", "technical-graph", "value-stream"]


M = "https://w3id.org/mpc/ontology/modules/"
P = "https://w3id.org/mpc/ontology/process/"
TYPE = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
COVERAGE_TTL = {
    "core": """@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix proc: <https://w3id.org/mpc/ontology/process/> .
proc:A a skos:Concept ; skos:notation "X 1" ; skos:prefLabel "Linked" .
proc:B a skos:Concept ; skos:notation "X 2" ; skos:prefLabel "Bare" .
""",
    # Each module links A the right way, with the other end typed as its module says. B appears in
    # each module too, but on the wrong end or with a wrongly typed other end, so it must not count.
    "organization": f"""<urn:asg> <{M}organization/forProcess> <{P}A> .
<urn:asg> {TYPE} <{M}organization/ResponsibilityAssignment> .
<{P}B> <{M}organization/forProcess> <urn:asg> .
<urn:untyped> <{M}organization/forProcess> <{P}B> .
""",
    "system": f"""<urn:sys> <{M}system/supports> <{P}A> .
<urn:sys> {TYPE} <{M}system/System> .
<{P}B> <{M}system/supports> <urn:sys> .
""",
    "kpi": f"""<urn:m> <{M}kpi/informsProcess> <{P}A> .
<urn:m> {TYPE} <{M}kpi/MeasureDefinition> .
<{P}B> <{M}kpi/informsProcess> <urn:m> .
""",
    "lane": f"""<{P}A> <{M}lane/officeLane> <urn:front> .
<urn:front> {TYPE} <{M}lane/OfficeLane> .
<urn:front> <{M}lane/officeLane> <{P}B> .
<{P}B> <{M}lane/officeLane> <urn:not-a-lane> .
""",
    "value-stream": f"""<urn:step> <{M}value-stream/realizes> <{P}A> .
<urn:step> {TYPE} <{M}value-stream/ValueStreamProcess> .
<{P}B> <{M}value-stream/realizes> <urn:step> .
""",
    "data-product": f"""<urn:dp> <{M}data-product/producedBy> <{P}A> .
<urn:dp> {TYPE} <{M}data-product/DataProduct> .
<urn:segment> <{M}data-product/anchoredIn> <{P}B> .
<urn:segment> {TYPE} <{M}data-product/PortfolioSegment> .
<urn:segment> <{M}data-product/producedBy> <{P}B> .
<{P}B> <{M}data-product/consumedBy> <urn:dp> .
""",
    "party": f"<urn:stage/Onboarding> <{M}party/stageProcess> <{P}B> .\n",
}


def test_coverage_counts_each_link_and_lists_the_process_with_none(tmp_path):
    releases = tmp_path / "releases"
    for module, ttl in COVERAGE_TTL.items():
        plant_release(releases, module, "1.0.0", {"triples": 1}, ttl)
    c = epm_facts.coverage("core", str(releases))
    assert c["processes"] == 2
    assert {k: v["with"] for k, v in c["links"].items()} == \
        {"raci": 1, "system": 1, "kpi": 1, "lane": 1, "value_stream": 1, "data_product": 1}
    assert all(v["without"] == ["X 2 Bare"] for v in c["links"].values())
    assert c["with_none"] == ["X 2 Bare"]
    stage = epm_facts.coverage("stage:onboarding", str(releases))
    assert (stage["processes"], stage["with_none"]) == (1, ["X 2 Bare"])
    # module:<name> takes the same typed links: B sits in the lane module only on wrong ends.
    assert epm_facts.coverage("module:lane", str(releases))["processes"] == 1
    assert epm_facts.coverage("module:party", str(releases))["processes"] == 1


def test_coverage_reads_each_link_from_its_newest_release(tmp_path):
    releases = tmp_path / "releases"
    for module, ttl in COVERAGE_TTL.items():
        plant_release(releases, module, "1.0.0", {"triples": 1}, ttl)
    # A newer system release drops the link, so A no longer counts as having one.
    plant_release(releases, "system", "1.1.0", {"triples": 0}, "")
    assert epm_facts.coverage("core", str(releases))["links"]["system"]["with"] == 0


# ---- citations: words other documents attribute to the decision owner (Plan 3, 2026-10-30) ----

NAMED_MISS = "not in the answers file, record or comment it names"  # a quote its named source lacks


def _citation_fixture(tmp_path, doc):
    answers, decisions = tmp_path / "answers", tmp_path / "decisions"
    answers.mkdir(parents=True, exist_ok=True); decisions.mkdir(exist_ok=True)
    (answers / "answers-y.md").write_text("<!-- verbatim from urn:epm:comment:7000001 -->\nship the ledger as it stands today\n", encoding="utf-8", newline="\n")
    (answers / "answers-x.md").write_text("<!-- context -->\nkeep the old figures as they were recorded\n", encoding="utf-8", newline="\n")
    (tmp_path / "doc.md").write_text(doc, encoding="utf-8", newline="\n")
    return epm_facts.citation_problems(root=str(tmp_path), answers=str(answers), decisions=str(decisions), files=["doc.md"])


def test_citations_walk_every_markdown_file_where_there_is_no_git(tmp_path):
    # files=None in a tree without .git: every .md under the root is read, nothing is tracked.
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "doc.md").write_text("a document\n", encoding="utf-8", newline="\n")
    (tmp_path / "top.md").write_text("another\n", encoding="utf-8", newline="\n")
    (tmp_path / "other.txt").write_text("not Markdown\n", encoding="utf-8", newline="\n")
    assert epm_facts.markdown_files(str(tmp_path)) == ["deep/doc.md", "top.md"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    subprocess.run(["git", "-C", str(tmp_path), "add", "top.md"], check=True, env=env)
    assert epm_facts.markdown_files(str(tmp_path)) == ["top.md"]  # with Git, the tracked files only


def test_counts_without_the_gate_gives_the_taxonomy_figures_alone(tmp_path, monkeypatch, capsys):
    # Without mapping_v2.py the command answers with the taxonomy figures and never starts the Step 4 pipeline.
    import types

    def pipeline():
        raise AssertionError("the Step 4 pipeline was started without its gate")
    monkeypatch.setattr(epm_facts, "STEP4", str(tmp_path))  # no mapping_v2.py here
    monkeypatch.setattr(epm_facts, "run_pipeline", pipeline)
    monkeypatch.setattr(epm_facts, "taxonomy", lambda: {"concepts": 1})
    monkeypatch.setattr(epm_facts, "commit", lambda: "c")
    args = types.SimpleNamespace(json=True)
    assert epm_facts.cmd_counts(args) == 0
    assert json.loads(capsys.readouterr().out)["step4_gate"] == "not in this tree"

