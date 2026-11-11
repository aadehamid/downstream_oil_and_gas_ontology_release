"""Tests for scripts/check_standalone.py: each deny rule with a line it must find and a near miss it must pass, the
pending list, and --strict. Every line and count here is written by hand."""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_standalone as cs  # noqa: E402

# (rule, a line the rule must find, the text it reports, a near miss no rule may find)
CASES = [
    ("other-branch", "The package is rebuilt on the main branch.", "main branch", "The main branches of the process tree."),
    ("other-branch", "On main every package is on disk.", "On main", "Planned maintenance is on maintenance orders."),
    ("other-branch", "The export is cut from main each night.", "from main", "The value comes from mainframe extracts."),
    ("other-branch", "No module in main has any.", "in main", "The work is done in main() of the script."),
    ("other-branch", "A zip of main holds it.", "of main", "for (const jump of main.querySelectorAll('a')) {}"),
    ("other-branch", "Compared against the map on `main` at 1b3105e.", "on `main`", "Call `main` with no arguments."),
    ("other-branch", "git diff origin/main", "origin/main", "The origin of maintenance cost is the work order."),
    ("other-branch", "It lives in the main repository.", "main repository", "The main report of the repository."),
    ("other-release", "In the share release the pins move.", "share release", "Shareholders release the dividend."),
    ("other-release", "import scripts.share_release.augment", "share_release", "The market share released in the filing."),
    ("other-release", "if EPM_SHARE_RELEASE: skip()", "SHARE_RELEASE", "SHARED_RELEASES = 3"),
    ("reference-number", "Fixed in #231 after review.", "#231", "A zero-width space is &#8203; in HTML."),
    ("reference-number", "the post-#31 workbook headers", "#31", "See guide.html#31 for the section."),
    ("reference-number", "(see #7, an earlier change)", "#7", "  color: #333333;"),
    ("reference-number", "merged by #12 and reverted", "#12", '<rect fill="#000" stroke="#111111"/>'),
    ("reference-number", "Reviewed under #488.", "#488", "border-bottom: 2px solid #131416;"),
    ("reference-number", "Tracked as #9.", "#9", "ultra-low-sulfur diesel #2 and #6 fuel oil"),
    ("reference-number", "See #45", "#45", "## 4 Headings and # 5 comments"),
    ("pull-request", "The fix came with PR 123.", "PR 123", "The PR team has 123 members."),
    ("pull-request", "Rounds on PRs #479 and #480.", "PRs #479", "PRIDE 123 is a product code."),
    ("pull-request", "Opened as pull request 17.", "pull request 17", "Pull requests are reviewed in 2 rounds."),
    ("pull-request", "This closes issue 45.", "issue 45", "OEO has no fuel oil class (OEO issue 1958)."),
    ("decision-record", "Recorded as EPM-DEC-001-0028.", "EPM-DEC-", "The decision of 2026-10-31 records it; see EPM-GLOS-001."),
    ("session", "The plan is in ~/.claude/handoffs.", "~/.claude", "The claim is in the file claude.md."),
    ("session", "Read handoffs/epm/notes.md first.", "handoffs/", "The shift handoff is at 06:00."),
    ("session", "It stays in the handoff folder.", "handoff folder", "The handoff between shifts is logged."),
    ("session", "Settings live in .claude/settings.json.", ".claude/", "The file notes.claude is not read."),
    ("removed-demo", "Run demos/downstream-pricing/tests.", "demos/", "The memos/ folder holds the notes."),
    ("removed-demo", "The pricing demo uses it.", "pricing demo", "Pricing demonstrates the margin."),
    ("removed-aura", "Copy the graph to AuraDB.", "AuraDB", "Laura reviewed the aural test."),
    ("removed-aura", "Neo4j and Aura hold it.", "Aura", "The restaurant brand is not a store."),
    ("removed-docker", "Start the store with docker compose up.", "docker", "The dock worker loads the barge."),
    ("removed-docker", "See the Dockerfile.", "Docker", "Truck docks are numbered."),
    ("removed-token", "Set DATABRICKS_TOKEN first.", "DATABRICKS_TOKEN", "DATABRICKS_HOST names the workspace."),
    ("removed-token", "Paste a personal access token.", "access token", "Access to tokens of appreciation is open."),
    ("github-link", "See https://github.com/some-owner/private-repo.", "github.com/some-owner", "See https://github.com/apache/jena."),
    ("github-link", "curl https://raw.githubusercontent.com/someone/x/y.txt", "raw.githubusercontent.com/someone",
     "See https://docs.github.com/en/actions and https://github.com/neo4j-labs/neosemantics."),
]


@pytest.mark.parametrize("rule,bad,reported,near_miss", CASES)
def test_each_rule_finds_its_line_and_passes_its_near_miss(rule, bad, reported, near_miss):
    assert (1, rule, reported) in cs.findings_in(bad)
    assert cs.findings_in(near_miss) == []


def test_every_rule_has_a_case():
    assert {rule for rule, _, _ in cs.RULES} == {rule for rule, _, _, _ in CASES}
    assert len(cs.RULES) == 11


def test_a_finding_names_its_line():
    assert cs.findings_in("clean\n\nFixed in #231.\n") == [(3, "reference-number", "#231")]


def test_the_allowed_owners_are_public_projects_the_tree_cites():
    assert {"apache", "neo4j", "neo4j-labs", "rdflib", "ontodev"} <= cs.GITHUB_OWNERS
    assert "aadehamid" not in cs.GITHUB_OWNERS
    assert all(owner == owner.lower() for owner in cs.GITHUB_OWNERS)


def tree(tmp_path, files, pending=None):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
    if pending is not None:
        (tmp_path / "scripts").mkdir(exist_ok=True)
        (tmp_path / "scripts" / "standalone-pending.txt").write_text(pending, encoding="utf-8")
    return str(tmp_path)


def test_a_clean_tree_passes(tmp_path, capsys):
    root = tree(tmp_path, {"a.md": "Nothing to see.\n", "deep/b.py": "x = 1\n"})
    assert cs.check(root) == ([], [], [])
    assert cs.main(["--root", root]) == 0
    assert capsys.readouterr().out == "stand-alone\n"


def test_a_finding_names_the_file_the_line_and_the_rule(tmp_path, capsys):
    root = tree(tmp_path, {"docs/a.md": "fine\nMerged in PR 12.\n"})
    assert cs.check(root)[0] == ["docs/a.md:2: [pull-request] PR 12"]
    assert cs.main(["--root", root]) == 1
    assert "docs/a.md:2: [pull-request] PR 12" in capsys.readouterr().out


def test_a_file_that_is_not_text_is_skipped(tmp_path):
    root = tree(tmp_path, {"image.png": b"\x89PNG\0#231 PR 12", "latin.bin": b"caf\xe9 PR 12"})
    assert cs.check(root) == ([], [], [])


def test_the_checks_own_files_are_not_read(tmp_path):
    root = tree(tmp_path, {"scripts/check_standalone.py": "PR 12\n", "scripts/test_check_standalone.py": "PR 12\n",
                           "scripts/other.py": "PR 12\n"})
    assert cs.check(root)[0] == ["scripts/other.py:1: [pull-request] PR 12"]


def test_a_pending_path_is_skipped_and_counted(tmp_path, capsys):
    root = tree(tmp_path, {"skills/x/a.md": "PR 12 and PR 13\n", "skills/x/clean.md": "fine\n", "b.md": "fine\n"},
                pending="# why\nskills/** :: being cleaned\n")
    findings, stale, summary = cs.check(root)
    assert (findings, stale) == ([], [])
    assert summary == ["pending `skills/**`: 2 findings in 1 files (being cleaned)"]
    assert cs.main(["--root", root]) == 0
    assert capsys.readouterr().out.endswith("stand-alone, except the 1 pending paths above\n")


def test_strict_ignores_the_pending_list(tmp_path):
    root = tree(tmp_path, {"skills/x/a.md": "PR 12\n"}, pending="skills/** :: being cleaned\n")
    assert cs.check(root, strict=True) == (["skills/x/a.md:1: [pull-request] PR 12"], [], [])
    assert cs.main(["--root", root, "--strict"]) == 1


def test_a_pending_line_that_matches_no_file_fails(tmp_path):
    root = tree(tmp_path, {"a.md": "fine\n"}, pending="gone/** :: was removed\n")
    assert cs.check(root)[1] == ["scripts/standalone-pending.txt: `gone/**` matches no file; remove the line"]
    assert cs.main(["--root", root]) == 1


def test_a_pending_line_whose_files_are_all_clean_fails(tmp_path):
    root = tree(tmp_path, {"docs/a.md": "fine\n"}, pending="docs/** :: awaits its rewrite\n")
    assert cs.check(root)[1] == ["scripts/standalone-pending.txt: every file under `docs/**` is clean; remove the line"]
    assert cs.main(["--root", root]) == 1


def test_a_finding_outside_the_pending_paths_still_fails(tmp_path):
    root = tree(tmp_path, {"skills/a.md": "PR 12\n", "docs/b.md": "PR 13\n"}, pending="skills/** :: being cleaned\n")
    assert cs.check(root)[0] == ["docs/b.md:1: [pull-request] PR 13"]


def test_a_pending_line_without_a_reason_is_refused(tmp_path, capsys):
    root = tree(tmp_path, {"skills/a.md": "PR 12\n"}, pending="skills/**\n")
    with pytest.raises(ValueError, match="standalone-pending.txt:1: write `<glob> :: <reason>`"):
        cs.check(root)
    assert cs.main(["--root", root]) == 1


def test_with_git_only_tracked_files_are_read(tmp_path):
    root = tree(tmp_path, {"tracked.md": "PR 12\n", "untracked.md": "PR 13\n"})
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", root], check=True, env=env)
    subprocess.run(["git", "-C", root, "add", "tracked.md"], check=True, env=env)
    assert cs.check(root)[0] == ["tracked.md:1: [pull-request] PR 12"]


def test_this_trees_checked_paths_are_clean_and_its_pending_list_is_live():
    findings, stale, _ = cs.check()
    assert findings == []
    assert stale == []
