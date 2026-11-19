"""The new-KPI path: a KPI intake form, its proposal of KGCL lines and facts, and its apply (KPI-DEC-0004, item 1;
KPI-DEC-0002, Q4 to Q7, Q10 form 1 and Q13).

The propose tests read this tree's own KPI intake pack and kpi tables, and write proposals into a temporary folder
only. The form is the shipped example Crack Spreads Pricing with a name, a definition and an other name of its own,
as the update guide's example does, under names the guide's example does not use, so the tests also hold on a
release where the guide's example was applied. The KGCL lines, the facts, the routes and the table rows they expect are
written by hand. The apply tests run on a temporary copy of the release; the tree itself is never written.
"""
import csv
import json
import shutil
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS, XSD

from kpi_store import apply as apply_cmd, cut, propose as propose_cmd
from kpi_store.change import ChangeRefused, approval, kgcl, kpi_tables, new_measures as nm, proposal
from kpi_store.intake import picklists
from kpi_store.tests import support
from kpi_store.tests.test_propose_apply import NOW, _versions, digest, git, no_global_git, quiet, scratch_release  # noqa: F401

ROOT = support.ROOT
EXAMPLE = ROOT / "kpi-intake" / "examples" / "crack-spreads-pricing.json"
SIGNED = {"data-owner": {"name": "A Data Owner", "date": "2026-11-19"},
          "domain-confirmation": {"name": "A Domain Owner", "date": "2026-11-19"},
          "architect": {"name": "An Architect", "date": "2026-11-19"}}
M = "measure:test-spread-margin"
DEFINITION = "A made-up market margin for tests: a product's price less the price of the crude it is made from."
LINES = [f"create node {M} 'Test Spread Margin'",
         f"add definition 'A made-up market margin for tests: a product’s price less the price of the crude it is made from.' to {M}",
         f"create exact synonym 'test spread' for {M}",
         f"create edge {M} kpi:measureKind kind:market-indicator",
         f"create edge {M} dcterms:source src:planner-measure-list-2026-10-18",
         f"create edge {M} kpi:usedBy persona:distribution-planner",
         f"create edge {M} kpi:usedBy persona:prompt-planner",
         f"create edge {M} kpi:usedBy persona:short-term-planner",
         f"create edge {M} kpi:informsProcess proc:CM-1-1-4-7-4",
         f"create edge {M} kpi:notToBeConfusedWith measure:margin-capture",
         f"create edge {M} kpi:notToBeConfusedWith measure:rm-margin-indicator",
         f"create edge {M} kpi:notToBeConfusedWith measure:rm-margin-per-barrel"]
REASON = ("MPC files crack spreads under market indicators and calls margins dependent on factors beyond its control. "
          "The list's cracks (NYMEX 3-2-1, USGC 3-2-1 MEH ex-RIN, Chicago WTI 3-2-1 ex-RIN) are benchmarks, not performance.")
NOT_NOTE = ("Not realized refinery margin, not margin capture, and not MPC's R&M Margin Indicator. A 3-2-1 built from "
            "separate product and crude legs is not the published series.")


def next_opm(root=ROOT):
    """The OPM- number after the highest that the tree's identifier table holds."""
    rows = csv.DictReader((root / kpi_tables.KPI_FOLDER / "measure-identifiers.csv").open(encoding="utf-8"))
    return 1 + max(int(r["identifier"][4:]) for r in rows if r["identifier"].startswith("OPM-"))


FACTS = [(M, "kpi:kpiCandidate", "false"), (M, "kpi:classificationTest", "3"), (M, "kpi:classificationReason", REASON),
         (M, "kpi:comparedAgainst", "30-day trend; 5-year history"),
         (M, "kpi:publicCounterpart", "MPC 10 (Gulf Coast, Mid-Continent, West Coast and blended 3-2-1 cracks)"),
         (M, "dcterms:bibliographicCitation", "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28"),
         (M, "kpi:grain", "daily, by market hub"),
         (M, "kpi:basis", "products price - crude price, for a stated crude:product ratio (for example 3-2-1); "
                          "unit: Illustration: US dollars per barrel"),
         (M, "skos:scopeNote", NOT_NOTE)]
# A sentence back in the scope note of each measure that 5.2 names (test_new_kpi_modules.py tests the other modules).
RETURN = "Not Test Spread Margin: the scope note of Test Spread Margin says how the two differ."
RETURNS = [(f"measure:{m}", "skos:scopeNote", RETURN) for m in ("margin-capture", "rm-margin-indicator", "rm-margin-per-barrel")]
# The answers of the example that feed the modules beside kpi, which the tests of this file leave out.
OTHERS = ("2.3", "2.4", "6.3", "6.4", "6.5", "6.6", "7.8")


def kpi_form(folder, changes=None, sign_offs=SIGNED, number="", drop=("3.6", *OTHERS), name="sample"):
    """The shipped example as a new measure, written to the folder, with these answers changed. Returns its path. By
    default it leaves out the answers that feed the modules beside kpi, and names no view in 7.1."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    answers = data["answers"]
    if set(OTHERS) <= set(drop):
        answers["7.1"] = "@no-data-yet"
    # The pack rebuilds the example from the ontology, so a sentence another form returned to the scope note of Crack
    # Spreads Pricing would reach 5.3: the tests set it.
    answers.update({"2.1": "Test Spread Margin", "2.2": DEFINITION, "5.1": ["test spread"], "5.3": NOT_NOTE, **(changes or {})})
    for key in drop:
        answers.pop(key, None)
    data.update(kpi_name=answers["2.1"], example_of="", comment="", sign_offs=sign_offs,
                request={"number": number} if number else {})
    path = Path(folder) / f"{name}.kpi-intake.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


# ---------- the lines and the facts ----------

def test_the_prefixes_kinds_and_identifier_rules_are_the_builders():
    import importlib.util
    path = ROOT / kpi_tables.KPI_FOLDER / "build_measures.py"
    spec = importlib.util.spec_from_file_location("build_measures_for_test", path)
    bm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bm)
    assert (nm.PREFIXES["measure"], nm.PREFIXES["kpi"], nm.PREFIXES["kind"], nm.PREFIXES["persona"], nm.PREFIXES["proc"],
            nm.PREFIXES["src"]) == (str(bm.MEASURE), str(bm.KPI), str(bm.KIND), str(bm.PERSONA), str(bm.PROC), str(bm.SRC))
    assert (nm.KINDS, nm.PREFIX, nm.EXCEPTIONS) == (bm.KINDS, bm.PREFIX, bm.PREFIX_EXCEPTIONS)
    sources = {r["key"]: r["slug"] for r in csv.DictReader((ROOT / kpi_tables.KPI_FOLDER / "measure-sources.csv").open(encoding="utf-8"))}
    assert sources[bm.CLASSIFIED_BY] == nm.CLASSIFIED_BY == "kpi-classification-evidence"


def test_every_line_reads_and_writes_as_the_official_grammar_does():
    from kgcl_schema.grammar.parser import parse_statement
    from kgcl_schema.grammar.render_operations import render
    for line in LINES:
        assert kgcl.write_line(kgcl.read_line(line)) == line
        assert render(parse_statement(line)) == line
    # The straight apostrophe of the definition is a ’ in the line, and the reader turns it back (KPI-DEC-0004, item 3).
    assert kgcl.read_line(LINES[1]).text == DEFINITION


@pytest.mark.parametrize("facts,message", [
    ([*FACTS, (M, "skos:definition", "Another definition.")], "skos:definition is said by a KGCL line of change.kgcl, not by facts.csv"),
    ([*FACTS, (M, "kpi:usedBy", "persona:mid-term-planner")], "kpi:usedBy is said by a KGCL line of change.kgcl"),
    ([*FACTS, (M, "kpi:planType", "monthly")], "kpi:planType is not a fact of a new measure"),
    ([f for f in FACTS if f[1] != "kpi:classificationReason"], "needs the fact kpi:classificationReason in facts.csv"),
    ([*FACTS, ("measure:unit-utilization", "kpi:grain", "hourly")], "a fact of facts.csv is about a new measure that a 'create node' line makes"),
    ([*FACTS, (M, "kpi:grain", "weekly")], "the measure has this fact already"),
    ([(M, "kpi:kpiCandidate", "true"), *FACTS[1:]], "only an operational metric can be a KPI candidate, and this measure is market-indicator"),
    ([(M, "kpi:kpiCandidate", "yes"), *FACTS[1:]], "the value is true or false"),
    ([f for f in FACTS if f[1] != "skos:scopeNote"], "a measure it is mistaken for needs a skos:scopeNote fact"),
    ([*FACTS[:2], (M, "kpi:classificationReason", "Two\nlines.")], "the value holds a line break"),
])
def test_facts_are_refused_unless_they_are_facts_kgcl_cannot_carry(facts, message):
    with pytest.raises(ChangeRefused, match=message):
        nm.measures(kgcl.read_lines("\n".join(LINES)), facts)


@pytest.mark.parametrize("lines,message", [
    (LINES[1:], "this line is about a measure that no 'create node' line before it makes"),
    ([LINES[0], *LINES[2:]], "measure:test-spread-margin has no definition"),
    ([*LINES[:3], *LINES[4:]], "needs exactly one kpi:measureKind link, and has 0"),
    ([*LINES, f"create edge {M} dcterms:source src:mpc-s01"], "needs exactly one dcterms:source link, and has 2"),
    ([*LINES, f"rename {M} from 'Test Spread Margin' to 'Other'"], "a new KPI takes a name, a definition, other names and links"),
    ([*LINES, "create exact synonym 'x' for system:mips"], r"a new KPI is a measure \(measure:<id>\)"),
    ([*LINES, f"create exact synonym 'Test spread margin' for {M}"], "the measure has this name already"),
])
def test_the_lines_of_a_new_measure_are_refused_unless_complete(lines, message):
    with pytest.raises(ChangeRefused, match=message):
        nm.measures(kgcl.read_lines("\n".join(lines)), FACTS)


@pytest.mark.parametrize("old,new,message", [
    ("src:planner-measure-list-2026-10-18", "src:a-made-up-document",
     "src:a-made-up-document is neither a document of kpi/measure-sources.csv nor a source with a title and an evidence "
     "tier in the release. A new source document needs a specialist"),
    ("persona:prompt-planner", "persona:asphalt-manager", "persona:asphalt-manager is not a planning persona of kpi/personas.csv"),
    ("kind:market-indicator", "kind:target", "kind:target is not a kind of measure"),
    ("proc:CM-1-1-4-7-4", "proc:CM-9-9", "proc:CM-9-9 is not a process of the newest core"),
    ("measure:margin-capture", "measure:a-made-up-measure", "measure:a-made-up-measure is not another measure of the kpi module"),
    ("'test spread'", "'crack spread'", "the measure crack-spreads has the name 'crack spread' already. A change to it goes through the term-change form"),
])
def test_a_new_measure_that_does_not_fit_the_tables_is_refused(old, new, message):
    changes = kgcl.read_lines("\n".join(line.replace(old, new) for line in LINES))
    with pytest.raises(ChangeRefused, match=message):
        nm.check_changes(changes, FACTS, ROOT)


# ---------- propose ----------

def test_propose_writes_the_lines_the_facts_the_route_and_the_signers_of_a_new_kpi(tmp_path):
    said = []
    form = kpi_form(tmp_path, {"7.7": "The margin column, for the gasoline series"}, number="NK-TEST-1")
    [folder] = propose_cmd.propose([form], tmp_path / "out", ROOT, now=NOW, say=said.append)
    assert folder == tmp_path / "out" / "NK-TEST-1"
    assert (folder / "change.kgcl").read_text(encoding="utf-8") == "".join(line + "\n" for line in LINES)
    with (folder / "facts.csv").open(encoding="utf-8", newline="") as f:
        assert [tuple(r) for r in csv.reader(f)] == [("measure", "property", "value"), *FACTS, *RETURNS]
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert record["route"] == "minor" and record["new_module"] is False
    assert [(s["role"], s["name"]) for s in record["signatures"]] == [
        ("Data Owner", "A Data Owner"), ("Domain Owner", "A Domain Owner"), ("Architect", "An Architect")]
    assert record["signatures"][1]["words"] == "This KPI belongs to my domain."
    assert said[0] == f"wrote the proposal {folder.as_posix()}: 12 changes and 12 facts, route minor"
    read = proposal.read(folder)
    assert (read.lines, read.facts, read.route) == (LINES, FACTS + RETURNS, "minor")
    summary = (folder / "summary.txt").read_text(encoding="utf-8").splitlines()
    for line in ('The new measure: "Test Spread Margin" (measure:test-spread-margin), in the kpi module',
                 "  - Its kind: market indicator.", "  - A role that uses it: Prompt Planner.",
                 "  - A process it informs: CM 1.1.4.7.4 Capture Product/Crude/Feedstock Price.",
                 '  - How often it is stated, and its breakdowns: "daily, by market hub"',
                 "Its identifier: the apply gives it the next free OPM- number.",
                 "The changes reach these modules: kpi (minor).",
                 "For the Architect: 7.7 stays in the form's file: the ontology has no property for the measure or column "
                 "of a view yet.",
                 "The route: minor. This is a minor: the changes add content, and the old meaning still holds."):
        assert line in summary, line


def test_a_kpi_and_a_note_on_its_identifier_give_their_own_facts(tmp_path):
    changes = {"4.3": "no", "4.4": "no", "4.5": "no", "4.6": "yes", "4.6.detail": "A made-up scorecard of 2026",
               "3.6": "PLAN-7 in the planning dashboard"}
    [folder] = propose_cmd.propose([kpi_form(tmp_path, changes, drop=("6.7",))], tmp_path / "out", ROOT, now=NOW, say=quiet)
    read = proposal.read(folder)
    assert f"create edge {M} kpi:measureKind kind:kpi" in read.lines
    assert (M, "kpi:classificationTest", "5") in read.facts and (M, "kpi:kpiCandidate", "false") in read.facts
    assert (M, "skos:note", "PLAN-7 in the planning dashboard") in read.facts
    assert (M, "dcterms:bibliographicCitation", "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28; A made-up scorecard of 2026") in read.facts
    assert "Its identifier: the apply gives it the next free KPI- number." in (folder / "summary.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("changes,sign_offs,message", [
    ({"2.2": ""}, SIGNED, "is not complete and signed. .*2.2 is missing"),
    ({}, {k: v for k, v in SIGNED.items() if k != "architect"}, "is not complete and signed. .*the Architect has not signed"),
    ({"6.1": ["https://w3id.org/mpc/ontology/modules/organization/role/asphalt-manager"]}, SIGNED,
     '6.1 names "Asphalt Manager", which is not one of the planning personas'),
    ({"3.5": ["https://w3id.org/mpc/ontology/source/src-cftc-p180-001"]}, SIGNED,
     "3.5 names a document that the form does not offer. The kpi module takes a document of its own sources or one "
     "that 3.5 offers"),
    ({"3.5": ["https://w3id.org/mpc/ontology/source/mpc-s01", "https://w3id.org/mpc/ontology/source/planner-measure-list-2026-10-18"]},
     SIGNED, "3.5 names 2 documents, and the kpi module records one source for each measure"),
    ({"5.1": ["the crack"]}, SIGNED, "the measure crack-spreads has the name 'the crack' already"),
])
def test_propose_refuses_a_kpi_form_it_cannot_carry_and_writes_nothing(tmp_path, changes, sign_offs, message):
    with pytest.raises(propose_cmd.ProposeRefused, match=message):
        propose_cmd.propose([kpi_form(tmp_path, changes, sign_offs)], tmp_path / "out", ROOT, now=NOW, say=quiet)
    assert not (tmp_path / "out").exists()


def test_propose_refuses_a_shipped_example_because_its_measure_exists_already(tmp_path):
    with pytest.raises(propose_cmd.ProposeRefused,
                       match="crack-spreads-pricing.json asks for a change the kpi module cannot take: the measure crack-spreads "
                             "has the name 'Crack Spreads Pricing' already. A change to it goes through the term-change form"):
        propose_cmd.propose([EXAMPLE], tmp_path / "out", ROOT, now=NOW, say=quiet)
    assert not (tmp_path / "out").exists()


def test_a_proposal_with_a_broken_facts_file_is_refused(tmp_path):
    [folder] = propose_cmd.propose([kpi_form(tmp_path)], tmp_path / "out", ROOT, now=NOW, say=quiet)
    (folder / "facts.csv").write_text("measure,value\n", encoding="utf-8")
    with pytest.raises(ChangeRefused, match="facts.csv must start with the header measure,property,value"):
        proposal.read(folder)


# ---------- apply ----------

def _write(folder, lines, facts=(), change=None):
    folder.mkdir(parents=True)
    (folder / "change.kgcl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    if facts:
        (folder / "facts.csv").write_text(proposal.facts_text(facts), encoding="utf-8")
    record = {"change": change or folder.name, "route": "minor", "new_module": False, "signatures": [
        {"role": "Data Owner", "name": "A Data Owner", "date": "2026-11-19", "words": "Right."},
        {"role": "Architect", "name": "An Architect", "date": "2026-11-19", "words": "Approved."}]}
    (folder / "approval.json").write_text(json.dumps(record), encoding="utf-8")
    return folder


def test_apply_refuses_a_new_kpi_with_a_reference_item_as_two_modules(tmp_path):
    from kpi_store.tests.test_reference_item import SYSTEM_LINES
    kpi, item = _write(tmp_path / "kpi", LINES, FACTS), _write(tmp_path / "item", SYSTEM_LINES)
    for folders in ([kpi, item], [item, kpi]):
        with pytest.raises(ChangeRefused, match="these proposals change two modules: the kpi module and the module of a new "
                                                "reference item. Apply them one module at a time"):
            apply_cmd.apply(folders, ROOT, say=quiet)


def test_a_facts_file_that_is_not_csv_is_refused_in_plain_words(tmp_path, capsys):
    # A field longer than the csv module's limit (131,072 characters); Python 3.11 and later read a NUL byte.
    folder = _write(tmp_path / "long-field", LINES, FACTS)
    (folder / "facts.csv").write_text(f"measure,property,value\nmeasure:x,kpi:grain,{'a' * 200_000}\n", encoding="utf-8")
    with pytest.raises(ChangeRefused, match="the proposal long-field: facts.csv cannot be read"):
        proposal.read(folder)
    assert apply_cmd.main([str(folder), "--release", str(ROOT)]) == 1
    assert capsys.readouterr().err.startswith("Not applied: the proposal long-field: facts.csv cannot be read")


def test_apply_refuses_a_new_kpi_with_a_term_change_stray_facts_and_the_same_kpi_twice(tmp_path):
    one, two = _write(tmp_path / "one", LINES, FACTS), _write(tmp_path / "two", LINES, FACTS)
    term = _write(tmp_path / "term", ["create exact synonym 'a made-up other name' for measure:unit-utilization"])
    stray = _write(tmp_path / "stray", ["create exact synonym 'a made-up other name' for measure:unit-utilization"], FACTS)
    for folders, message in (([one, term], "these proposals are term changes and new KPIs"),
                             ([stray], "the proposal stray holds facts.csv, which only a new KPI has"),
                             ([one, two], "the proposals one and two both add measure:test-spread-margin")):
        with pytest.raises(ChangeRefused, match=message):
            apply_cmd.apply(folders, ROOT, say=quiet)


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_new_kpi_goes_from_the_form_to_a_committed_minor_release(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    opm = next_opm(root)
    measures = root / kpi_tables.MEASURES
    kept = tmp_path / "measures-before.ttl"
    shutil.copy2(measures, kept)
    held = _versions(root)
    [folder] = propose_cmd.propose([kpi_form(tmp_path, number="NK-1")], tmp_path / "proposals", root, now=NOW, say=quiet)
    said = []
    files = apply_cmd.apply([folder], root, say=said.append, now=NOW)
    major, minor, _ = held["kpi"].split(".")
    new = f"{major}.{int(minor) + 1}.0"
    assert said[:3] == ["1 proposal to apply:", "  NK-1: minor, signed by Data Owner, Domain Owner, Architect", "    " + LINES[0]]
    assert f"    fact {','.join(FACTS[0])}" in said and f"  kpi {held['kpi']} -> {new}" in said
    assert said[-2].startswith(f"Done. kpi is now {new} (minor)")
    assert _versions(root)["kpi"] == new and git(root, "status", "--porcelain") == ""
    assert git(root, "log", "-1", "--format=%s").strip() == f"Apply the new KPI NK-1: kpi {new}"
    body = git(root, "log", "-1", "--format=%b")
    assert "The facts (measure, property, value):\nmeasure:test-spread-margin,kpi:kpiCandidate,false\n" in body
    assert set(git(root, "show", "--name-only", "--no-renames", "--format=", "HEAD").split()) == set(files)
    # The rows the form added, written by hand.
    rows = lambda name: list(csv.DictReader((root / kpi_tables.KPI_FOLDER / f"{name}.csv").open(encoding="utf-8")))
    assert rows("measure-classification")[-1] == {
        "measure_id": "test-spread-margin", "name": "Test Spread Margin", "source": "planner-list", "topic": "",
        "personas": "Distribution Planner; Prompt Planner; Short-Term Planner", "class": "market-indicator",
        "kpi_candidate": "no", "rule_test": "3", "compared_against": "30-day trend; 5-year history",
        "mpc_counterpart": "MPC 10 (Gulf Coast, Mid-Continent, West Coast and blended 3-2-1 cracks)", "reason": REASON,
        "evidence": "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28"}
    assert rows("measure-details")[-1] == {
        "measure_id": "test-spread-margin", "definition": DEFINITION, "grain": "daily, by market hub",
        "basis": "products price - crude price, for a stated crude:product ratio (for example 3-2-1); unit: Illustration: US dollars per barrel",
        "aliases": "test spread", "not_to_be_confused_with": "margin-capture;rm-margin-indicator;rm-margin-per-barrel",
        "not_note": NOT_NOTE, "informs_process": "CM 1.1.4.7.4"}
    assert rows("measure-identifiers")[-1] == {"measure_id": "test-spread-margin", "identifier": f"OPM-{opm:04d}"}
    # The round trip, and the record, the change file and the facts the release keeps.
    lines, facts = nm.compare(kept, measures)
    assert (sorted(lines), facts) == (sorted(LINES), sorted(FACTS + RETURNS))
    record = approval.record_path(root, "NK-1")
    assert approval.read_record(record)["route"] == "minor"
    assert record.with_suffix(".kgcl").read_text(encoding="utf-8").splitlines() == LINES
    assert proposal.read_facts(record.with_suffix(".facts.csv").read_text(encoding="utf-8"), "NK-1") == FACTS + RETURNS
    lists = picklists.load(root / "kpi-intake")
    assert "Test Spread Margin" in {m["label"] for m in lists["lists"]["measures"]} and picklists.stale_modules(lists, root) == {}
    # The ontology records roles and never a person's name (KPI-DEC-0004, item 2).
    for path in (root / cut.ONTOLOGY).rglob("*"):
        if path.suffix in (".ttl", ".jsonld", ".nt", ".trig"):
            text = path.read_text(encoding="utf-8")
            assert not any(s["name"] in text for s in SIGNED.values()), path


def test_a_failing_step_and_a_builder_error_roll_everything_back(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    [folder] = propose_cmd.propose([kpi_form(tmp_path)], tmp_path / "proposals", root, now=NOW, say=quiet)
    before = digest(root)

    def fail_at_the_tests(name):
        if name == "run the kpi module's tests":
            raise RuntimeError("made-up failure")
    with pytest.raises(cut.CutFailed, match="the step 'run the kpi module's tests' failed: RuntimeError: made-up failure. The release is as it was."):
        apply_cmd.apply([folder], root, say=quiet, now=NOW, before_step=fail_at_the_tests)
    assert digest(root) == before

    (root / kpi_tables.KPI_FOLDER / "build_measures.py").write_text('import sys\nsys.exit("made-up builder failure")\n', encoding="utf-8")
    before = digest(root)
    with pytest.raises(cut.CutFailed, match="(?s)the kpi builder refused the changed tables.*made-up builder failure"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)
    assert digest(root) == before
    assert not approval.record_path(root, folder.name).exists()


def test_the_round_trip_refuses_a_difference_that_neither_file_states(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    before = Graph().parse(root / kpi_tables.MEASURES)
    opm = next_opm(root)
    nm.apply_changes(kgcl.read_lines("\n".join(LINES)), FACTS, root)
    after = Graph().parse(root / kpi_tables.MEASURES)
    lines, facts = nm.compare(before, after)
    assert (sorted(lines), facts) == (sorted(LINES), sorted(FACTS))
    s = URIRef(nm.iri(M))
    kpi = nm.PREFIXES["kpi"]
    for change, message in (
            # a text fact facts.csv does not hold: a plan type, which a measure does not take
            (lambda g: g.add((s, URIRef(kpi + "planType"), Literal("monthly", datatype=XSD.string))), "1 ways"),
            # a fact of the right property with the wrong form: the candidate as text
            (lambda g: (g.remove((s, URIRef(kpi + "kpiCandidate"), None)),
                        g.add((s, URIRef(kpi + "kpiCandidate"), Literal("false", lang="en")))), "1 ways"),
            # another measure changed beside the new one
            (lambda g: g.add((URIRef(nm.iri("measure:unit-utilization")), SKOS.altLabel, Literal("x", lang="en"))), "1 ways"),
            # an identifier off the run
            (lambda g: (g.remove((s, DCTERMS.identifier, None)), g.add((s, DCTERMS.identifier, Literal("OPM-0040", datatype=XSD.string)))),
             rf"the new OPM identifiers are \[40\], and the run needs \[{opm}\]"),
            # a second identifier beside the right one (round 1, finding 3)
            (lambda g: g.add((s, DCTERMS.identifier, Literal("OPM-9999", datatype=XSD.string))), "dc/terms/identifier"),
            # a link written as a text that holds the target's IRI (finding 4)
            (lambda g: (g.remove((s, URIRef(kpi + "usedBy"), URIRef(nm.iri("persona:prompt-planner")))),
                        g.add((s, URIRef(kpi + "usedBy"), Literal(nm.iri("persona:prompt-planner"))))), "1 ways"),
            # a candidate flag that is not a boolean (finding 5)
            (lambda g: (g.remove((s, URIRef(kpi + "kpiCandidate"), None)),
                        g.add((s, URIRef(kpi + "kpiCandidate"), Literal("not-a-bool", datatype=XSD.boolean)))), "1 ways"),
            # no identifier at all
            (lambda g: g.remove((s, DCTERMS.identifier, None)), "needs a OPM-nnnn identifier, not None"),
            # the classification evidence, which every measure cites
            (lambda g: g.remove((s, DCTERMS.source, URIRef(nm.PREFIXES["src"] + nm.CLASSIFIED_BY))), "which every measure has")):
        changed = Graph() + after
        change(changed)
        with pytest.raises(ChangeRefused, match=message):
            nm.compare(before, changed)
    # A fact the graph holds with another value is a difference of the facts, which apply's round trip reports.
    changed = Graph() + after
    changed.remove((s, URIRef(kpi + "grain"), None))
    changed.add((s, URIRef(kpi + "grain"), Literal("weekly", datatype=XSD.string)))
    lines, facts = nm.compare(before, changed)
    assert sorted(lines) == sorted(LINES) and (M, "kpi:grain", "weekly") in facts and (M, "kpi:grain", "daily, by market hub") not in facts
    assert nm.compare(before, Graph() + before) == ([], [])


def test_apply_stops_when_the_rebuilt_module_holds_what_neither_file_states(tmp_path, monkeypatch):
    root = scratch_release(tmp_path, git_copy=False)
    [folder] = propose_cmd.propose([kpi_form(tmp_path)], tmp_path / "proposals", root, now=NOW, say=quiet)
    before = digest(root)

    from kpi_store.change import other_modules
    real = other_modules.apply_changes

    def and_one_more_triple(changes, facts, staging):
        built = real(changes, facts, staging)
        with built.open("a", encoding="utf-8") as f:
            f.write('\n<https://w3id.org/mpc/ontology/modules/kpi/measure/test-spread-margin> '
                    '<https://w3id.org/mpc/ontology/modules/kpi/grain> "weekly"^^<http://www.w3.org/2001/XMLSchema#string> .\n')
        return built
    monkeypatch.setattr(other_modules, "apply_changes", and_one_more_triple)
    # The extra value is a fact of the right form, so the module's compare returns it, and the apply's round trip finds
    # that facts.csv does not hold it.
    with pytest.raises(cut.CutFailed, match=r"the kpi module does not hold exactly the proposals' changes: missing none, "
                                            r"more \['measure:test-spread-margin,kpi:grain,weekly'\]"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)
    assert digest(root) == before


RM = ROOT / "kpi-intake" / "examples" / "rm-margin-per-barrel.json"


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_the_rm_margin_example_cites_a_source_the_form_offers_and_apply_adds_its_row(tmp_path, no_global_git):
    # The shipped R&M Margin example cites the MPC Form 10-K (3.5), which the form offers and the ontology records with a
    # title and an evidence tier, and which kpi/measure-sources.csv does not hold yet. The apply adds its row.
    root = scratch_release(tmp_path, git_copy=True)
    data = json.loads(RM.read_text(encoding="utf-8"))
    data["answers"].update({"2.1": "Test Margin per Barrel", "2.2": "A made-up margin per barrel for tests.", "5.1": []})
    for key in OTHERS:   # this test is about the kpi module; test_new_kpi_modules.py tests the others
        data["answers"].pop(key, None)
    data.update(kpi_name="Test Margin per Barrel", example_of="", comment="", request={"number": "NK-RM-1"},
                sign_offs=SIGNED)
    form = tmp_path / "rm.kpi-intake.json"
    form.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    [folder] = propose_cmd.propose([form], tmp_path / "proposals", root, now=NOW, say=quiet)
    read = proposal.read(folder)
    assert "create edge measure:test-margin-per-barrel dcterms:source src:mpc-s01" in read.lines
    assert "create edge measure:test-margin-per-barrel kpi:measureKind kind:operational-metric" in read.lines
    assert ("measure:test-margin-per-barrel", "kpi:kpiCandidate", "true") in read.facts
    kept = tmp_path / "measures-before.ttl"
    shutil.copy2(root / kpi_tables.MEASURES, kept)
    apply_cmd.apply([folder], root, say=quiet, now=NOW)
    assert git(root, "status", "--porcelain") == ""
    sources = list(csv.DictReader((root / kpi_tables.KPI_FOLDER / "measure-sources.csv").open(encoding="utf-8")))
    assert sources[-1] == {"key": "mpc-s01", "slug": "mpc-s01",
                           "title": "Marathon Petroleum Corporation, Form 10-K for the fiscal year ended 2025-12-31",
                           "short_name": ""}
    row = list(csv.DictReader((root / kpi_tables.KPI_FOLDER / "measure-classification.csv").open(encoding="utf-8")))[-1]
    assert (row["measure_id"], row["source"], row["class"], row["kpi_candidate"]) == (
        "test-margin-per-barrel", "mpc-s01", "operational-metric", "yes")
    lines, facts = nm.compare(kept, root / kpi_tables.MEASURES)
    assert sorted(lines) == sorted(read.lines) and facts == sorted(read.facts)
    # A second KPI that cites the same document takes the row the first one added.
    data["answers"].update({"2.1": "Test Margin per Barrel Two", "2.2": "Another made-up margin per barrel for tests."})
    data.update(kpi_name="Test Margin per Barrel Two", request={"number": "NK-RM-2"})
    form.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    [folder] = propose_cmd.propose([form], tmp_path / "proposals", root, now=NOW, say=quiet)
    apply_cmd.apply([folder], root, say=quiet, now=NOW)
    sources = list(csv.DictReader((root / kpi_tables.KPI_FOLDER / "measure-sources.csv").open(encoding="utf-8")))
    assert [r["slug"] for r in sources].count("mpc-s01") == 1


# ---------- a source that the kpi module gains (round 2 of the review) ----------

MPC = "https://w3id.org/mpc/ontology/source/mpc-s01"
MPC_TITLE = "Marathon Petroleum Corporation, Form 10-K for the fiscal year ended 2025-12-31"
# The documents 3.5 offers that the ontology records and kpi/measure-sources.csv may not hold yet, with their titles.
OFFERED = {"mpc-s01": MPC_TITLE, "mplx-s01": "MPLX LP, Form 10-K for the fiscal year ended 2025-12-31"}


def fresh_source(root):
    """A document of OFFERED that the release's measure-sources.csv does not hold yet: after the guide's examples a
    release holds some of them."""
    held = {r["slug"] for r in csv.DictReader((root / kpi_tables.KPI_FOLDER / "measure-sources.csv").open(encoding="utf-8"))}
    slug = next((s for s in OFFERED if s not in held), None)
    if slug is None:
        pytest.skip("the release holds a row for every document these tests may cite")
    return slug


def test_the_round_trip_requires_a_new_source_to_gain_one_type_and_one_title(tmp_path):
    from rdflib.namespace import RDF
    root = scratch_release(tmp_path, git_copy=False)
    slug = fresh_source(root)
    before = Graph().parse(root / kpi_tables.MEASURES)
    lines = [line.replace("src:planner-measure-list-2026-10-18", f"src:{slug}") for line in LINES]
    nm.apply_changes(kgcl.read_lines("\n".join(lines)), FACTS, root)
    after = Graph().parse(root / kpi_tables.MEASURES)
    src, title = URIRef(nm.PREFIXES["src"] + slug), DCTERMS.title
    assert (src, title, Literal(OFFERED[slug], lang="en")) in after and nm.compare(before, after)[1] == sorted(FACTS)
    stray = URIRef(nm.PREFIXES["kind"] + "a-made-up-kind")
    for change, message in (
            (lambda g: g.remove((src, RDF.type, DCTERMS.BibliographicResource)), "lacks .*BibliographicResource"),
            (lambda g: g.remove((src, title, None)), "lacks http://purl.org/dc/terms/title"),
            (lambda g: g.add((src, title, Literal("A second title", lang="en"))), "differ in 1 ways"),
            (lambda g: (g.remove((src, title, None)), g.add((src, title, Literal("   ", lang="en")))), "differ in 2 ways"),
            # a source link to a node outside src: does not make that node a source with a type and a title
            (lambda g: (g.add((URIRef(nm.iri(M)), DCTERMS.source, stray)), g.add((stray, RDF.type, DCTERMS.BibliographicResource)),
                        g.add((stray, title, Literal("x", lang="en")))), "differ in 3 ways")):
        changed = Graph() + after
        change(changed)
        with pytest.raises(ChangeRefused, match=message):
            nm.compare(before, changed)


def test_a_new_source_whose_slug_is_another_rows_key_is_refused_by_name(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    slug = fresh_source(root)
    path = root / kpi_tables.KPI_FOLDER / "measure-sources.csv"
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(f'{slug},{slug}-2024,"A made-up row whose key is the slug of a document 3.5 offers",\n')
    lines = [line.replace("src:planner-measure-list-2026-10-18", f"src:{slug}") for line in LINES]
    with pytest.raises(ChangeRefused, match=f"src:{slug} needs a row of kpi/measure-sources.csv under the key {slug}, "
                                            f"and the row of src:{slug}-2024 holds that key"):
        nm.check_changes(kgcl.read_lines("\n".join(lines)), FACTS, root)


def test_a_source_takes_one_non_blank_english_or_untagged_title(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    package = next((root / cut.ONTOLOGY / "releases" / "ref-mpc").glob("*/ref-mpc.ttl"))
    with package.open("a", encoding="utf-8") as f:
        f.write(f'\n<{MPC}> <http://purl.org/dc/terms/title> ""@en, "   "@en, "A Form 10-K (in French)"@fr .\n')
    assert nm.source_records(root)[MPC] == MPC_TITLE
    # Three made-up sources with an evidence tier: one with only unusable titles, one with only an untagged title,
    # one with an English title and an untagged title that sorts before it.
    src = "https://w3id.org/mpc/ontology/source/"
    tier = "<https://w3id.org/mpc/ontology/modules/authority/evidenceTier>"
    for integration in (root / cut.ONTOLOGY / "releases" / "integration").glob("*/integration.ttl"):
        with integration.open("a", encoding="utf-8") as f:
            for name in ("test-unusable", "test-untagged", "test-both"):
                f.write(f'\n<{src}{name}> {tier} "made-up tier" .\n')
    with package.open("a", encoding="utf-8") as f:
        title = "<http://purl.org/dc/terms/title>"
        f.write(f'\n<{src}test-unusable> {title} "   "@en, "Un titre"@fr, "2025-12-31"^^<http://www.w3.org/2001/XMLSchema#date> .\n'
                f'<{src}test-untagged> {title} "An untagged title" .\n'
                f'<{src}test-both> {title} "A untagged title, first in text order", "The English title"@en .\n')
    records = nm.source_records(root)
    assert src + "test-unusable" not in records
    assert records[src + "test-untagged"] == "An untagged title"
    assert records[src + "test-both"] == "The English title"
