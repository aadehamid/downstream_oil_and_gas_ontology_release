"""Check that figures stated in governed documents match epm-facts.

Each test reads a sentence or table from a document and compares it with what
`scripts/epm_facts.py` computes from the source files. A failure means the
document has drifted: update the document (or, if the source changed on
purpose, both the document and the pinned values in test_epm_facts.py).

Run: uv run --with pytest --with rdflib python -m pytest -q scripts/test_published_figures.py

Checked: every total and summary figure these documents state about Step 4
data, and that step4/README.md states no live ledger or gate figures at all. The ontology guide's module
versions, triple counts, total and module count are checked against the newest releases. Deliberately not checked, because they are not data totals this tool
computes:
- step4/README.md's "16/16 sections": signed-off sections of the mapping document.
- The backlog's "All 96 Section B rows": the historic Section B population,
  explained by the index note "Section B is 96 rows plus 6".
- Subgroup breakdowns inside backlog section intros (for example "5 rows of the
  REL-00445 pattern"): they split rows whose section totals are checked here.
"""
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import epm_facts  # noqa: E402

STEP4_README = os.path.join(ROOT, "business_architecture", "ontology", "step4", "README.md")
ONTOLOGY_README = os.path.join(ROOT, "business_architecture", "ontology", "README.md")
DEC_0025 = os.path.join(ROOT, "business_architecture", "domain", "decisions", "the decision of 2026-10-06-phase1-scope.md")
GUIDE = os.path.join(ROOT, "business_architecture", "ontology", "epm-ontology-guide.html")


@pytest.fixture(scope="module")
def facts():
    out = subprocess.check_output([sys.executable, os.path.join(HERE, "epm_facts.py"), "--json", "counts"], text=True)
    return json.loads(out)


@pytest.fixture(scope="module")
def facts_0025(tmp_path_factory):
    """Counts on the commit the decision of 2026-10-06 cites, not today's.

    A decision record states its figures as of the commit it names ("run on
    commit `1179405`"), so its figures are history and stay as recorded while
    later batches move the live counts. Today's epm_facts.py runs on that
    commit's tree, so the counting logic is the same one checked everywhere else.
    """
    sha = re.search(r"run on commit `([0-9a-f]+)`", flat(DEC_0025)).group(1)
    tree = tmp_path_factory.mktemp("dec0025")
    archive = subprocess.run(["git", "-C", ROOT, "archive", sha], capture_output=True)
    assert archive.returncode == 0, (
        f"commit {sha} is not in this clone; a shallow clone needs `git fetch --unshallow` "
        f"(CI checks out full history): {archive.stderr.decode().strip()}")
    archive = archive.stdout
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
    os.makedirs(tree / "scripts", exist_ok=True)
    shutil.copy(os.path.join(HERE, "epm_facts.py"), tree / "scripts" / "epm_facts.py")
    out = subprocess.check_output([sys.executable, str(tree / "scripts" / "epm_facts.py"), "--json", "counts"],
                                  text=True, stderr=subprocess.DEVNULL)
    result = json.loads(out)
    result["backlog"] = str(tree / os.path.relpath(epm_facts.BACKLOG, ROOT))
    return result


def flat(path):
    """The document's text with all whitespace runs collapsed, so wrapped sentences match."""
    with open(path, encoding="utf-8") as f:
        return re.sub(r"\s+", " ", f.read())


def num(s):
    return int(s.replace(",", ""))


def pairs_table(backlog=None):
    """(G1b row, reverse row) pairs from the backlog's "G1b pairs held on both sides" table."""
    with open(backlog or epm_facts.BACKLOG, encoding="utf-8") as f:
        text = f.read()
    section = text.split("## G1b pairs held on both sides", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\|\s*(REL-\d{5})\s*\|\s*(REL-\d{5})\s*\|", section, re.M)


# Numbers step4/README.md may state because they are not live figures. Anything
# else numeric is a figure, however it is worded or emphasised.
README_NON_FIGURES = [
    # Fixed figures, each matched only in its own sentence; removed before the file-name rule splits them.
    r"All 10 boxes in release-checklist\.md are complete",
    r"document, 16/16 sections\)",
    r"in one flag-day release",
    r"\d{4}-\d{2}-\d{2}",                           # dates
    r"(?<![&\w])#\d+\b",                               # change and issue numbers
    r"\b\d+\.\d+\.\d+\b",                           # release versions
    r"\b(?:REL-\d{5}|EPM-[A-Z]+-\d{3}(?:-\d{4})?|CM(?:-\d+)+|MPC-S\d+)\b",  # the project's ID namespaces
    r"[\w./-]+\.(?:md|py|csv|ttl|json|jsonl|sh|txt|html)\b",  # file names
    r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b",          # commit SHAs
    r"\bstep\d\b|\bStep \d+\b|\bQ\d+\b|\bpython3\b",   # step names, decision numbers, the command
]


# Any number word is a figure too: the README states counts nowhere, so it needs none
# beyond the allowlisted phrases. Matching words near nouns missed "FAIL count is one".
NUMBER_WORD = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"(?:thir|four|fif|six|seven|eigh|nine)teen|(?:twen|thir|for|fif|six|seven|eigh|nine)ty|"
    r"hundred|thousand|million|dozen|single|none)\b"
    r"|\bno\s+(?:[\w-]+\s+){0,2}?(?:emitting|held|deferred|facts?|rows?|mentions?|PASS|FAIL|failures?|checks?)\b",
    re.I)


def readme_figures(text):
    """Figures left in the text once markup, character references and the allowed non-figures are removed."""
    text = re.sub(r"[*_`]", "", html.unescape(text))
    for pattern in README_NON_FIGURES:
        text = re.sub(pattern, " ", text)
    return re.findall(r"\d[\d,]*", text) + NUMBER_WORD.findall(text)


def test_ontology_readme_taxonomy(facts):
    tax = facts["taxonomy"]
    if "triples" not in tax:
        pytest.skip("rdflib not installed")
    m = re.search(r"([\d,]+) triples, ([\d,]+) `skos:Concept`, ([\d,]+) `skos:broader` links, "
                  r"([\d,]+) concepts with `skos:definition`", flat(ONTOLOGY_README))
    assert m, "taxonomy sentence not found in ontology/README.md"
    assert tuple(num(g) for g in m.groups()) == (
        tax["triples"], tax["concepts"], tax["broader_links"], tax["concepts_with_definition"])


# Backlog index row label -> (issue, heading prefix of the section it counts).
INDEX_SECTIONS = {
    "G3 Section B": ("an earlier change", "G3 Section B"),
    "G1b rows held for a verb correction": ("an earlier change", "G1b rows held for a verb correction"),
    "Supply & Trading": ("an earlier change", "Supply & Trading recommend/advise rows"),
    "Triggers": ("an earlier change", "Triggers pass"),
    "Precedes/follows": ("an earlier change", "Precedes/follows holds"),
    "Governed-by": ("an earlier change", None),
    "G3 Section A": ("an earlier change", "G3 Section A"),
    "Other verb-review holds": ("an earlier change", "Other verb-review holds"),
}


def batch_rows(n):
    """Rows in the batch n review file."""
    path = os.path.join(epm_facts.REVIEWS, f"precedes-follows-batch{n}-review.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for r in csv.DictReader(f) if r["row_id"].startswith("REL-"))


def section_count(prefix):
    return sum(1 for _, (_, s) in epm_facts.phase1_rows().items() if s.startswith(prefix))


def guide_text():
    """The ontology guide's displayed text: tags dropped, character references decoded, whitespace collapsed."""
    with open(GUIDE, encoding="utf-8") as f:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", f.read())))


def test_guide_module_figures_match_the_newest_releases():
    """The guide's snapshot of each module, its total and its module count, against the releases in the tree.

    A release that is not reflected in the guide fails here, so the guide moves with the release. The total is the size of the newest releases (twelve since technical-graph 1.0.0, 2026-11-02) loaded into one graph, which is smaller than the
    sum of the modules' counts because the modules share some triples. Not checked: the figures inside each
    module card (processes, measures, systems, roles), the requires column, and the dated query output, which
    states the graph of 2026-10-27 on purpose.
    """
    import rdflib
    newest = {r["module"]: (r["newest"], r["triples"]) for r in epm_facts.module_releases()}
    text = guide_text()
    cards = re.findall(r"\b(" + "|".join(map(re.escape, newest)) + r") (\d+\.\d+\.\d+) ([\d,]+) triples", text)
    assert sorted(m for m, _, _ in cards) == sorted(newest), "the guide needs one card per released module"
    whole = rdflib.Graph()
    for module, version, triples in cards:
        assert (version, num(triples)) == newest[module], module
        whole += epm_facts.newest_graph(module)
    totals = [re.search(p, text) for p in (r"Triples ([\d,]+) in the \w+ newest releases together",
                                           r"loaded together, ([\d,]+) triples since",
                                           r"for the whole ontology \(([\d,]+) triples\)")]
    assert all(totals), "a statement of the total moved; update this test with it"
    assert {num(t.group(1)) for t in totals} == {len(whole)}
    assert num(re.search(r"Modules (\d+) each released", text).group(1)) == len(newest)

