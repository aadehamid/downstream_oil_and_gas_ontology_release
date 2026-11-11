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
    ("pull-request", "Tracked in issue 3524 of the tracker.", "issue 3524", "Recheck rdflib issue 3524 every three months."),
    ("pull-request", "See PR 361, https://github.com/some-owner/x/pull/361.", "PR 361",
     "Issue 237, https://github.com/neo4j-labs/neosemantics/issues/237, and PR 361, https://github.com/neo4j-labs/neosemantics/pull/361"),
    ("pull-request", "It broke after issue 237.", "issue 237", "MAP mode breaks in-graph SHACL (neosemantics issue 237, open)."),
    ("pull-request", "Issue 45, https://github.com/apache/jena/issues/7 is another one.", "Issue 45",
     "Issue 45, https://github.com/apache/jena/issues/45, is open."),
    ("pull-request", "PR 36, https://github.com/neo4j-labs/neosemantics/pull/361", "PR 36",
     "PR 361, https://github.com/neo4j-labs/neosemantics/pull/361"),
    ("decision-record", "Recorded as EPM-DEC-001-0028.", "EPM-DEC-", "The decision of 2026-10-31 records it; see EPM-GLOS-001."),
    ("session", "The plan is in ~/.claude/handoffs.", "~/.claude", "The claim is in the file claude.md."),
    ("session", "Read handoffs/epm/notes.md first.", "handoffs/", "The shift handoff is at 06:00."),
    ("session", "It stays in the handoff folder.", "handoff folder", "The handoff between shifts is logged."),
    ("session", "Settings live in .claude/settings.json.", ".claude/", "The file notes.claude is not read."),
    ("removed-demo", "Run demos/downstream-pricing/tests.", "demos/", "The memos/ folder holds the notes."),
    ("removed-demo", "The pricing demo uses it.", "pricing demo", "Pricing demonstrates the margin."),
    ("removed-demo", "<urn:pricing-demo:tech:check/x> a tg:QualityCheck .", "pricing-demo", "The pricing-demonstration page."),
    ("removed-demo", "python -m pricing_demo.tech_graph load", "pricing_demo", "repricing_demos = 2"),
    ("removed-aura", "Copy the graph to AuraDB.", "AuraDB", "Laura reviewed the aural test."),
    ("removed-aura", "Neo4j and Aura hold it.", "Aura", "The restaurant brand is not a store."),
    ("removed-docker", "Start the store with docker compose up.", "docker", "The dock worker loads the barge."),
    ("removed-docker", "See the Dockerfile.", "Docker", "Truck docks are numbered."),
    ("removed-token", "Set DATABRICKS_TOKEN first.", "DATABRICKS_TOKEN", "DATABRICKS_HOST names the workspace."),
    ("removed-token", "Paste a personal access token.", "access token", "Access to tokens of appreciation is open."),
    ("github-link", "See https://github.com/some-owner/private-repo.", "github.com/some-owner", "See https://github.com/apache/jena."),
    ("github-link", "See https://www.github.com/some-owner/private-repo.", "www.github.com/some-owner",
     "See https://www.github.com/apache/jena."),
    ("github-link", "git clone git@github.com:some-owner/private-repo.git", "github.com:some-owner",
     "git clone git@github.com:apache/jena.git"),
    ("github-link", "git remote add up ssh://git@github.com/some-owner/private-repo.git", "github.com/some-owner",
     "git remote add up ssh://git@github.com/neo4j/apoc.git"),
    ("github-link", "See https://gist.github.com/some-owner/0123abcd.", "gist.github.com/some-owner",
     "See https://gist.github.com/jbarrasa/0123abcd."),
    ("github-link", "curl https://api.github.com/repos/some-owner/private-repo/contents/x", "api.github.com/repos/some-owner",
     "curl https://api.github.com/repos/ontodev/robot/releases and https://api.github.com/rate_limit"),
    ("github-link", "curl -L https://codeload.github.com/some-owner/private-repo/zip/refs/heads/x", "codeload.github.com/some-owner",
     "curl -L https://codeload.github.com/ontodev/robot/zip/refs/tags/v1.9.10"),
    ("github-link", "git clone ssh://git@altssh.github.com:443/some-owner/private-repo.git", "altssh.github.com:443/some-owner",
     "git clone ssh://git@altssh.github.com:443/apache/jena.git"),
    ("github-link", "See https://objects.githubusercontent.com/some-owner/x.", "objects.githubusercontent.com/some-owner",
     "See https://docs.github.com/en/actions/some-owner and https://notgithub.com/some-owner/x."),
    ("user-path", "The file is //Users/somebody/work/notes.md.", "/Users/somebody", "See https://users/somebody/ and https://example.org//x."),
    ("user-path", "Open C:\\users\\somebody in Explorer.", "C:\\users\\somebody", "Open C:\\users\\<name> in Explorer."),
    ("user-path", "Open c:/Users/somebody/kpi-store.", "c:/Users/somebody", "The ratio c:/users is not a path; nor is c:/Users/<name>."),
    ("user-path", "cd /HOME/somebody/kpi-store", "/HOME/somebody", "The page /homepage/somebody and the word home/somebody."),
    ("home-path", "cd %HOMEDRIVE%%HOMEPATH%\\kpi-store", "%HOMEDRIVE%", "HOMEDRIVE and HOMEPATH are Windows variables; 50%HOME is not."),
    ("home-path", "cd %HOMEPATH%\\kpi-store", "%HOMEPATH%", "Set %KPI_STORE_HOME% to the folder."),
    ("home-path", "cd $env:USERPROFILE\\kpi-store", "$env:USERPROFILE\\kpi-store", "$env:EPM_STORES_ENV names the settings file."),
    ("home-path", "export OUT=${HOME}/lpg-out", "${HOME}/lpg-out", "${HOMEBREW_PREFIX}/bin is not the home folder."),
    ("home-path", "Read ~somebody/notes.md first.", "~somebody/notes.md", "About ~5/10 of the rows, or ~somebody without a path."),
    ("removed-demo", "The pricing demos were removed.", "pricing demos", "Pricing demonstrations are public."),
    ("removed-demo", "import pricing_demos", "pricing_demos", "repricing_demos = 2 and pricing_demosaic = 3"),
    ("removed-demo", "the pricingdemo catalog", "pricingdemo", "the pricingdemography table"),
    ("user-path", "The file is /Users/somebody/work/notes.md.", "/Users/somebody", "See https://example.org/Users/somebody/ and /Users/<name>/."),
    ("user-path", "cd /home/somebody/kpi-store", "/home/somebody", "https://www.aspentech.com/-/media/aspentech/home/resources/x.pdf"),
    ("user-path", "Open C:\\Users\\somebody\\kpi-store in Explorer.", "C:\\Users\\somebody", "Open C:\\Users\\<name>\\kpi-store or C:\\kpi-store."),
    ("home-path", "Read ~/private-repository/README.md first.", "~/private-repository/README.md", "https://www.api.org/~/media/files/x.pdf"),
    ("home-path", "The output goes to ~/lpg-out/epm.", "~/lpg-out/epm", "Write it to <your output folder>, about ~40 MB."),
    ("home-path", "export OUT=$HOME/lpg-out", "$HOME/lpg-out", "The variable HOME names the home folder; $HOMEPAGE does not."),
    ("home-path", "cd %USERPROFILE%\\kpi-store", "%USERPROFILE%", "Usage is 40% of the USERPROFILE quota."),
    ("github-link", "curl https://raw.githubusercontent.com/someone/x/y.txt", "raw.githubusercontent.com/someone",
     "See https://docs.github.com/en/actions and https://github.com/neo4j-labs/neosemantics."),
]


@pytest.mark.parametrize("rule,bad,reported,near_miss", CASES)
def test_each_rule_finds_its_line_and_passes_its_near_miss(rule, bad, reported, near_miss):
    assert (1, rule, reported) in cs.findings_in(bad)
    assert cs.findings_in(near_miss) == []


def test_every_rule_has_a_case():
    assert {rule for rule, _, _ in cs.RULES} == {rule for rule, _, _, _ in CASES}
    assert len(cs.RULES) == 13


def test_a_finding_names_its_line():
    assert cs.findings_in("clean\n\nFixed in #231.\n") == [(3, "reference-number", "#231")]


def test_the_allowed_owners_are_public_projects_the_tree_cites():
    assert {"apache", "neo4j", "neo4j-labs", "rdflib", "ontodev"} <= cs.GITHUB_OWNERS
    assert "some-owner" not in cs.GITHUB_OWNERS
    assert all(owner == owner.lower() for owner in cs.GITHUB_OWNERS)


def tree(tmp_path, files, pending=None, exceptions=None):
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
    if exceptions is not None:
        (tmp_path / "scripts").mkdir(exist_ok=True)
        (tmp_path / "scripts" / "standalone-exceptions.txt").write_text(exceptions, encoding="utf-8")
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
                           "scripts/standalone-exceptions.txt": "# quotes PR 12\n", "scripts/other.py": "PR 12\n"})
    assert cs.check(root)[0] == ["scripts/other.py:1: [pull-request] PR 12"]


def test_a_pending_path_is_skipped_and_counted(tmp_path, capsys):
    root = tree(tmp_path, {"HOW-TO-UPDATE.md": "PR 12 and PR 13\n", "b.md": "fine\n"},
                pending="# why\nHOW-TO-UPDATE.md :: awaits its rewrite\n")
    findings, stale, summary = cs.check(root)
    assert (findings, stale) == ([], [])
    assert summary == ["pending `HOW-TO-UPDATE.md`: 2 findings in 1 files (awaits its rewrite)"]
    assert cs.main(["--root", root]) == 0
    assert capsys.readouterr().out.endswith("stand-alone, except the 1 pending paths above\n")


def test_strict_ignores_the_pending_list(tmp_path):
    root = tree(tmp_path, {"README.md": "PR 12\n"}, pending="README.md :: awaits its rewrite\n")
    assert cs.check(root, strict=True) == (["README.md:1: [pull-request] PR 12"], [], [])
    assert cs.main(["--root", root, "--strict"]) == 1


def test_a_pending_file_hides_no_file_with_a_longer_name(tmp_path):
    # The pending line names one file. A new file beside it, with a name that starts the same way, is checked.
    root = tree(tmp_path, {"HOW-TO-UPDATE.md": "PR 12\n", "HOW-TO-UPDATE.evasion.md": "PR 13\n"},
                pending="HOW-TO-UPDATE.md :: awaits its rewrite\n")
    assert cs.check(root)[0] == ["HOW-TO-UPDATE.evasion.md:1: [pull-request] PR 13"]
    assert cs.main(["--root", root]) == 1


def test_a_pending_line_that_matches_no_file_fails(tmp_path):
    root = tree(tmp_path, {"a.md": "fine\n"}, pending="README.md :: awaits its rewrite\n")
    assert cs.check(root)[1] == ["scripts/standalone-pending.txt: `README.md` is not a file in this tree; remove the line"]
    assert cs.main(["--root", root]) == 1


def test_a_pending_line_whose_files_are_all_clean_fails(tmp_path):
    root = tree(tmp_path, {"HOW-TO-UPDATE.md": "fine\n"}, pending="HOW-TO-UPDATE.md :: awaits its rewrite\n")
    assert cs.check(root)[1] == ["scripts/standalone-pending.txt: `HOW-TO-UPDATE.md` is clean; remove the line"]
    assert cs.main(["--root", root]) == 1


def test_a_finding_outside_the_pending_paths_still_fails(tmp_path):
    root = tree(tmp_path, {"README.md": "PR 12\n", "docs/b.md": "PR 13\n"}, pending="README.md :: awaits its rewrite\n")
    assert cs.check(root)[0] == ["docs/b.md:1: [pull-request] PR 13"]


def test_a_pending_line_without_a_reason_is_refused(tmp_path, capsys):
    root = tree(tmp_path, {"README.md": "PR 12\n"}, pending="README.md\n")
    with pytest.raises(ValueError, match="standalone-pending.txt:1: write `<path> :: <reason>`"):
        cs.check(root)
    assert cs.main(["--root", root]) == 1


@pytest.mark.parametrize("line", [
    "docs/** :: awaits rewrite",                 # a new folder
    "* :: everything",                           # the whole tree
    "README.* :: awaits the documents rewrite",  # an allowed path, widened
    "HOW-TO-UPDATE.* :: awaits the documents rewrite",  # two allowed files as one wildcard
    "docs/new.md :: awaits rewrite",             # a new file
])
def test_the_pending_list_cannot_grow(tmp_path, capsys, line):
    root = tree(tmp_path, {"docs/new.md": "PR 12\n", "README.md": "PR 13\n", "README.html": "PR 14\n"}, pending=line + "\n")
    with pytest.raises(ValueError, match="standalone-pending.txt:1: .* is not a file the list may hold"):
        cs.check(root)
    assert cs.main(["--root", root]) == 1
    assert cs.check(root, strict=True)[0] == ["README.html:1: [pull-request] PR 14", "README.md:1: [pull-request] PR 13",
                                              "docs/new.md:1: [pull-request] PR 12"]


def test_the_allowed_pending_lines_are_these_eight_files_and_this_trees_list_holds_no_other():
    # Written by hand. A later change may delete a line here and in the list; it may never add or widen one.
    assert cs.ALLOWED_PENDING == (
        "README.md",
        "KNOWN-OPEN-ITEMS.md",
        "HOW-TO-UPDATE.md",
        "HOW-TO-UPDATE.html",
        "business_architecture/ontology/epm-walkthrough.html",
        "business_architecture/ontology/epm-ontology-guide.html",
        "viewer/index.html",
        "horoi_viewer/index.html",
    )
    assert not any(c in path for path in cs.ALLOWED_PENDING for c in "*?[")
    assert [path for path, _ in cs.read_pending()] == list(cs.ALLOWED_PENDING)


CHANGELOG = "releases/kpi/1.3.0/CHANGELOG.md"
EXCEPTION = CHANGELOG + " :: other-release :: Share release :: 1 :: a released package never changes\n"


def test_an_exception_covers_its_exact_text_in_its_file(tmp_path, capsys):
    root = tree(tmp_path, {CHANGELOG: "# kpi\n*Share release, 2026-11-04:* built against core 2.4.0.\n"}, exceptions="# why\n" + EXCEPTION)
    assert cs.check(root) == ([], [], [])
    assert cs.check(root, strict=True) == ([], [], [])  # an exception stays in force for the final cut
    assert cs.main(["--root", root, "--strict"]) == 0


def test_an_exception_does_not_cover_a_new_occurrence(tmp_path):
    text = "*Share release, 2026-11-04:* one.\nAnother note on the Share release.\n"
    root = tree(tmp_path, {CHANGELOG: text}, exceptions=EXCEPTION)
    findings, stale, _ = cs.check(root)
    assert findings == [CHANGELOG + ":1: [other-release] Share release", CHANGELOG + ":2: [other-release] Share release"]
    assert stale == ["scripts/standalone-exceptions.txt:1: " + CHANGELOG
                     + " holds [other-release] `Share release` 2 times, not 1; the exception no longer covers it"]


def test_an_exception_does_not_cover_other_text_another_rule_or_another_file(tmp_path):
    root = tree(tmp_path, {CHANGELOG: "*Share release:* one. Fixed in PR 12. The share release again.\n",
                           "docs/a.md": "Share release\n"}, exceptions=EXCEPTION)
    assert cs.check(root)[0] == ["docs/a.md:1: [other-release] Share release",
                                 CHANGELOG + ":1: [other-release] share release", CHANGELOG + ":1: [pull-request] PR 12"]


def test_an_exception_whose_text_is_gone_fails(tmp_path):
    root = tree(tmp_path, {CHANGELOG: "# kpi\nNothing here.\n"}, exceptions=EXCEPTION)
    assert cs.check(root)[1] == ["scripts/standalone-exceptions.txt:1: " + CHANGELOG
                                 + " holds [other-release] `Share release` 0 times, not 1; remove the line"]
    assert cs.main(["--root", root]) == 1


@pytest.mark.parametrize("line", [
    "a.md :: other-release :: Share release :: 1",                    # no reason
    "a.md :: no-such-rule :: Share release :: 1 :: reason",           # a rule the check does not have
    "a.md :: other-release :: Share release :: many :: reason",       # the count is not a number
    "a.md :: other-release :: Share release :: 0 :: reason",          # an exception for nothing
])
def test_a_malformed_exception_is_refused(tmp_path, line):
    root = tree(tmp_path, {"a.md": "Share release\n"}, exceptions=line + "\n")
    with pytest.raises(ValueError, match="standalone-exceptions.txt:1: write"):
        cs.check(root)
    assert cs.main(["--root", root]) == 1


def test_two_exceptions_for_one_text_are_refused(tmp_path):
    root = tree(tmp_path, {CHANGELOG: "Share release\n"}, exceptions=EXCEPTION + EXCEPTION)
    with pytest.raises(ValueError, match="standalone-exceptions.txt:2: a second line"):
        cs.check(root)


def test_this_trees_exceptions_are_only_for_fixed_content():
    # Written by hand: an exception is for a released package and its changelog, the two taxonomy files, the
    # decision records, a test that names a word to prove it is gone, and two run configurations. Nothing else.
    allowed = ("business_architecture/ontology/releases/", "business_architecture/domain/kpi-store-decisions/",
               "business_architecture/ontology/build/output/step3-taxonomy.ttl",
               "business_architecture/ontology/step4/baseline/step3-taxonomy.ttl", "skills/ontology-to-lpg/scripts/test_",
               "skills/rdf-store/scripts/test_",
               # the two run configurations, whose default paths under the home folder a test pins
               "business_architecture/ontology/projection/skill-run/epm-run.json",
               "skills/ontology-to-lpg/templates/run-config.json",
               "business_architecture/ontology/projection/skill-run/test_skill_run.py")
    entries = cs.read_exceptions()
    assert len(entries) == 38
    assert [path for path, _, _ in entries if not path.startswith(allowed)] == []


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
