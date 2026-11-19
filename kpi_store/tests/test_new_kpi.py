"""The new-KPI path: a KPI intake form, its proposal of KGCL lines and facts, and its apply (KPI-DEC-0004, item 1;
KPI-DEC-0002, Q4 to Q7, Q10 form 1 and Q13).

The propose tests read this tree's own KPI intake pack and kpi tables, and write proposals into a temporary folder
only. The form is the shipped example Crack Spreads Pricing with a name, a definition and an other name of its own,
as the update guide's example has it. The KGCL lines, the facts, the routes and the table rows they expect are
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
M = "measure:sample-spread-margin"
DEFINITION = "A made-up market margin for tests: a product's price less the price of the crude it is made from."
LINES = [f"create node {M} 'Sample Spread Margin'",
         f"add definition 'A made-up market margin for tests: a product’s price less the price of the crude it is made from.' to {M}",
         f"create exact synonym 'sample spread' for {M}",
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
FACTS = [(M, "kpi:kpiCandidate", "false"), (M, "kpi:classificationTest", "3"), (M, "kpi:classificationReason", REASON),
         (M, "kpi:comparedAgainst", "30-day trend; 5-year history"),
         (M, "kpi:publicCounterpart", "MPC 10 (Gulf Coast, Mid-Continent, West Coast and blended 3-2-1 cracks)"),
         (M, "dcterms:bibliographicCitation", "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28"),
         (M, "kpi:grain", "daily, by market hub"),
         (M, "kpi:basis", "products price - crude price, for a stated crude:product ratio (for example 3-2-1); "
                          "unit: Illustration: US dollars per barrel"),
         (M, "skos:scopeNote", NOT_NOTE)]


def kpi_form(folder, changes=None, sign_offs=SIGNED, number="", drop=("3.6",), name="sample"):
    """The shipped example as a new measure, written to the folder, with these answers changed. Returns its path."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    answers = data["answers"]
    answers.update({"2.1": "Sample Spread Margin", "2.2": DEFINITION, "5.1": ["sample spread"], **(changes or {})})
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
    ([LINES[0], *LINES[2:]], "measure:sample-spread-margin has no definition"),
    ([*LINES[:3], *LINES[4:]], "needs exactly one kpi:measureKind link, and has 0"),
    ([*LINES, f"create edge {M} dcterms:source src:mpc-s01"], "needs exactly one dcterms:source link, and has 2"),
    ([*LINES, f"rename {M} from 'Sample Spread Margin' to 'Other'"], "a new KPI takes a name, a definition, other names and links"),
    ([*LINES, "create exact synonym 'x' for system:mips"], r"a new KPI is a measure \(measure:<id>\)"),
    ([*LINES, f"create exact synonym 'Sample spread margin' for {M}"], "the measure has this name already"),
])
def test_the_lines_of_a_new_measure_are_refused_unless_complete(lines, message):
    with pytest.raises(ChangeRefused, match=message):
        nm.measures(kgcl.read_lines("\n".join(lines)), FACTS)


@pytest.mark.parametrize("old,new,message", [
    ("src:planner-measure-list-2026-10-18", "src:mpc-s01", "src:mpc-s01 is not a document of kpi/measure-sources.csv. A new source document needs a specialist"),
    ("persona:prompt-planner", "persona:asphalt-manager", "persona:asphalt-manager is not a planning persona of kpi/personas.csv"),
    ("kind:market-indicator", "kind:target", "kind:target is not a kind of measure"),
    ("proc:CM-1-1-4-7-4", "proc:CM-9-9", "proc:CM-9-9 is not a process of the newest core"),
    ("measure:margin-capture", "measure:a-made-up-measure", "measure:a-made-up-measure is not another measure of the kpi module"),
    ("'sample spread'", "'crack spread'", "the measure crack-spreads has the name 'crack spread' already. A change to it goes through the term-change form"),
])
def test_a_new_measure_that_does_not_fit_the_tables_is_refused(old, new, message):
    changes = kgcl.read_lines("\n".join(line.replace(old, new) for line in LINES))
    with pytest.raises(ChangeRefused, match=message):
        nm.check_changes(changes, FACTS, ROOT)


# ---------- propose ----------

def test_propose_writes_the_lines_the_facts_the_route_and_the_signers_of_a_new_kpi(tmp_path):
    said = []
    [folder] = propose_cmd.propose([kpi_form(tmp_path, number="NK-TEST-1")], tmp_path / "out", ROOT, now=NOW, say=said.append)
    assert folder == tmp_path / "out" / "NK-TEST-1"
    assert (folder / "change.kgcl").read_text(encoding="utf-8") == "".join(line + "\n" for line in LINES)
    with (folder / "facts.csv").open(encoding="utf-8", newline="") as f:
        assert [tuple(r) for r in csv.reader(f)] == [("measure", "property", "value"), *FACTS]
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert record["route"] == "minor" and record["new_module"] is False
    assert [(s["role"], s["name"]) for s in record["signatures"]] == [
        ("Data Owner", "A Data Owner"), ("Domain Owner", "A Domain Owner"), ("Architect", "An Architect")]
    assert record["signatures"][1]["words"] == "This KPI belongs to my domain."
    assert said[0] == f"wrote the proposal {folder.as_posix()}: 12 changes and 9 facts, route minor"
    read = proposal.read(folder)
    assert (read.lines, read.facts, read.route) == (LINES, FACTS, "minor")
    summary = (folder / "summary.txt").read_text(encoding="utf-8").splitlines()
    for line in ('The new measure: "Sample Spread Margin" (measure:sample-spread-margin), in the kpi module',
                 "  - Its kind: market indicator.", "  - A role that uses it: Prompt Planner.",
                 "  - A process it informs: CM 1.1.4.7.4 Capture Product/Crude/Feedstock Price.",
                 '  - How often it is stated, and its breakdowns: "daily, by market hub"',
                 "Its identifier: the apply gives it the next free OPM- number.",
                 "  - 2.3, 2.4: the population module", "  - 6.3, 6.4, 6.5: the value-stream module",
                 "  - 6.6, 7.1, 7.8: the data-product module", "  - 6.7: the market-data module",
                 "The route: minor. This is a minor: the changes add content, and the old meaning still holds."):
        assert line in summary, line


def test_a_kpi_and_a_note_on_its_identifier_give_their_own_facts(tmp_path):
    changes = {"4.3": "no", "4.4": "no", "4.5": "no", "4.6": "yes", "4.6.detail": "A made-up scorecard of 2026",
               "3.6": "PLAN-7 in the planning dashboard"}
    [folder] = propose_cmd.propose([kpi_form(tmp_path, changes, drop=("6.7",))], tmp_path / "out", ROOT, now=NOW, say=quiet)
    read = proposal.read(folder)
    assert f"create edge {M} kpi:measureKind kind:kpi" in read.lines
    assert (M, "kpi:classificationTest", "5") in read.facts and (M, "kpi:kpiCandidate", "false") in read.facts
    assert read.facts[-1] == (M, "skos:note", "PLAN-7 in the planning dashboard")
    assert (M, "dcterms:bibliographicCitation", "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28; A made-up scorecard of 2026") in read.facts
    assert "Its identifier: the apply gives it the next free KPI- number." in (folder / "summary.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("changes,sign_offs,message", [
    ({"2.2": ""}, SIGNED, "is not complete and signed. .*2.2 is missing"),
    ({}, {k: v for k, v in SIGNED.items() if k != "architect"}, "is not complete and signed. .*the Architect has not signed"),
    ({"6.1": ["https://w3id.org/mpc/ontology/modules/organization/role/asphalt-manager"]}, SIGNED,
     '6.1 names "Asphalt Manager", which is not one of the planning personas'),
    ({"3.5": ["https://w3id.org/mpc/ontology/source/mpc-s01"]}, SIGNED,
     "src:mpc-s01 is not a document of kpi/measure-sources.csv"),
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


def test_apply_refuses_a_new_kpi_with_a_term_change_stray_facts_and_the_same_kpi_twice(tmp_path):
    one, two = _write(tmp_path / "one", LINES, FACTS), _write(tmp_path / "two", LINES, FACTS)
    term = _write(tmp_path / "term", ["create exact synonym 'a made-up other name' for measure:unit-utilization"])
    stray = _write(tmp_path / "stray", ["create exact synonym 'a made-up other name' for measure:unit-utilization"], FACTS)
    for folders, message in (([one, term], "these proposals are term changes and new KPIs"),
                             ([stray], "the proposal stray holds facts.csv, which only a new KPI has"),
                             ([one, two], "the proposals one and two both add measure:sample-spread-margin")):
        with pytest.raises(ChangeRefused, match=message):
            apply_cmd.apply(folders, ROOT, say=quiet)


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_new_kpi_goes_from_the_form_to_a_committed_minor_release(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
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
    assert "The facts (measure, property, value):\nmeasure:sample-spread-margin,kpi:kpiCandidate,false\n" in body
    assert set(git(root, "show", "--name-only", "--no-renames", "--format=", "HEAD").split()) == set(files)
    # The rows the form added, written by hand.
    rows = lambda name: list(csv.DictReader((root / kpi_tables.KPI_FOLDER / f"{name}.csv").open(encoding="utf-8")))
    assert rows("measure-classification")[-1] == {
        "measure_id": "sample-spread-margin", "name": "Sample Spread Margin", "source": "planner-list", "topic": "",
        "personas": "Distribution Planner; Prompt Planner; Short-Term Planner", "class": "market-indicator",
        "kpi_candidate": "no", "rule_test": "3", "compared_against": "30-day trend; 5-year history",
        "mpc_counterpart": "MPC 10 (Gulf Coast, Mid-Continent, West Coast and blended 3-2-1 cracks)", "reason": REASON,
        "evidence": "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28"}
    assert rows("measure-details")[-1] == {
        "measure_id": "sample-spread-margin", "definition": DEFINITION, "grain": "daily, by market hub",
        "basis": "products price - crude price, for a stated crude:product ratio (for example 3-2-1); unit: Illustration: US dollars per barrel",
        "aliases": "sample spread", "not_to_be_confused_with": "margin-capture;rm-margin-indicator;rm-margin-per-barrel",
        "not_note": NOT_NOTE, "informs_process": "CM 1.1.4.7.4"}
    assert rows("measure-identifiers")[-1] == {"measure_id": "sample-spread-margin", "identifier": "OPM-0031"}
    # The round trip, and the record, the change file and the facts the release keeps.
    lines, facts = nm.compare(kept, measures)
    assert (sorted(lines), facts) == (sorted(LINES), sorted(FACTS))
    record = approval.record_path(root, "NK-1")
    assert approval.read_record(record)["route"] == "minor"
    assert record.with_suffix(".kgcl").read_text(encoding="utf-8").splitlines() == LINES
    assert proposal.read_facts(record.with_suffix(".facts.csv").read_text(encoding="utf-8"), "NK-1") == FACTS
    lists = picklists.load(root / "kpi-intake")
    assert "Sample Spread Margin" in {m["label"] for m in lists["lists"]["measures"]} and picklists.stale_modules(lists, root) == {}
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
             r"the new OPM identifiers are \[40\], and the run needs \[31\]"),
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

    def and_one_more_triple(changes, facts, staging):
        built = nm.apply_changes(changes, facts, staging)
        with built.open("a", encoding="utf-8") as f:
            f.write('\n<https://w3id.org/mpc/ontology/modules/kpi/measure/sample-spread-margin> '
                    '<https://w3id.org/mpc/ontology/modules/kpi/grain> "weekly" .\n')
        return built
    monkeypatch.setattr(apply_cmd, "NEW_KPI", apply_cmd.NEW_KPI.__class__(
        **{**apply_cmd.NEW_KPI.__dict__, "apply_changes": and_one_more_triple}))
    with pytest.raises(cut.CutFailed, match="the step 'compare the kpi module before and after' failed"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)
    assert digest(root) == before
