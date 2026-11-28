"""Tests for dsbp_checks.py.

Two kinds of test, following the validation-first rule (decision DSBP-DEC-0011):

* On the untouched baseline, used as an "identity" candidate, the checks that guard what must not change pass,
  and the neutrality check V5 fails, because the baseline still names company systems.
* Each check is shown failing on a deliberately broken copy, so we know it can catch the mistake it is for.

Run from the repository root:

    uv run --with rdflib --with pyshacl --with owlready2 --with pytest python -m pytest ds_business_process/validation
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import rdflib
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsbp_checks as d  # noqa: E402


@pytest.fixture(scope="session")
def baseline() -> rdflib.Graph:
    return d.load(d.BASELINE_CORE)


@pytest.fixture(scope="session")
def rows(baseline) -> list[dict]:
    """Every baseline process under a new neutral ID (DSBP-DEC-0031): retained, or deprecated where the baseline
    already deprecates it."""
    return [{"baseline_iri": str(s), "new_iri": f"{d.NEW_PROC}DSBP-P-{i:06d}",
             "status": "deprecated" if (s, OWL.deprecated, Literal(True)) in baseline else "retained", "note": ""}
            for i, s in enumerate(sorted(d.processes(baseline), key=str), start=1)]


@pytest.fixture(scope="session")
def candidate(baseline, rows) -> rdflib.Graph:
    """The baseline with every process IRI replaced by its new one, and nothing else changed."""
    m = {URIRef(r["baseline_iri"]): URIRef(r["new_iri"]) for r in rows}
    out = rdflib.Graph()
    for s, p, o in baseline:
        out.add((m.get(s, s), p, m.get(o, o)))
    return out


def copy(g: rdflib.Graph) -> rdflib.Graph:
    out = rdflib.Graph()
    for t in g:
        out.add(t)
    out.namespace_manager = g.namespace_manager
    return out


def java_works() -> bool:
    """A real Java, not a stub that only sits on the PATH (as macOS ships one)."""
    if shutil.which("java") is None:
        return False
    try:
        return subprocess.run(["java", "-version"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def some_process(g: rdflib.Graph, at_level: int) -> URIRef:
    return sorted(s for s in d.processes(g) if d.level(g, s) == at_level)[0]


# The baseline as an identity candidate ---------------------------------------------------------------------------
def test_baseline_has_the_recorded_shape(baseline):
    procs = d.processes(baseline)
    assert len(procs) == 707
    counts = {}
    for s in procs:
        counts[d.level(baseline, s)] = counts.get(d.level(baseline, s), 0) + 1
    assert counts == {0: 2, 1: 10, 2: 13, 3: 48, 4: 137, 5: 474, 6: 23}


def test_v1_passes_on_the_real_releases():
    # Pinned (scripts/pinned-tests.txt): it asks whether 1.2's releases are still as shipped, so it fails, as it should,
    # in a tree where the runner has cut a correction release. The V1 tests below build their own releases and still run.
    assert d.baseline_untouched() == []


def test_identity_passes_v2_v3_v7(baseline, rows, candidate):
    assert d.nothing_lost(baseline, rows, candidate) == []
    assert d.only_approved_changed(baseline, candidate, rows, set()) == []
    assert d.relationships_kept(baseline, candidate, rows) == []


def test_identity_v4_finds_only_the_two_known_missing_definitions(baseline):
    # CM-1-1-4-6 also lacks a definition, but it is retired (owl:deprecated), so V4 does not require one.
    fails = d.structure(baseline)
    assert sorted(fails) == sorted(f"V4: {x} has no definition" for x in ("CM-1-1-3-5-3", "CM-1-1-4-6-1"))


def test_identity_passes_v6_because_no_definition_changed(baseline, rows, candidate):
    assert d.evidence(baseline, candidate, rows) == []


def test_v5_is_red_on_the_baseline(baseline):
    fails = d.company_neutral(baseline)
    assert any("'XPIMS'" in f for f in fails)
    assert any("'DPO'" in f for f in fails)


# Each check fails on a deliberately broken copy -------------------------------------------------------------------
def test_v1_fails_when_one_byte_changes(tmp_path):
    rel = tmp_path / "releases"
    shutil.copytree(d.RELEASES / "core" / "2.4.0", rel / "core" / "2.4.0")
    f = rel / "core" / "2.4.0" / "core.ttl"
    data = bytearray(f.read_bytes())
    data[-2] = ord(" ") if data[-2] != ord(" ") else ord("\t")
    f.write_bytes(bytes(data))
    core_only = {k: v for k, v in d.read_manifest_list().items() if k.startswith("core/2.4.0/")}
    assert d.baseline_untouched(rel, core_only) == ["V1: core/2.4.0/core.ttl differs from its manifest hash"]


def test_v2_fails_when_a_row_is_dropped(baseline, rows):
    fails = d.nothing_lost(baseline, rows[1:])
    assert fails == [f"V2: {rows[0]['baseline_iri']} has 0 rows in the migration map; it needs exactly one"]


def test_v2_fails_on_a_duplicate_a_bad_status_and_an_unexplained_exclusion(baseline, rows):
    broken = [dict(r) for r in rows] + [dict(rows[0])]
    broken[1]["status"] = "kept"
    broken[2]["status"], broken[2]["note"] = "excluded", ""
    fails = d.nothing_lost(baseline, broken)
    assert any("has 2 rows" in f for f in fails)
    assert any("unknown status 'kept'" in f for f in fails)
    assert any("excluded with no reason" in f for f in fails)


def test_v2_fails_when_a_kept_concept_keeps_its_old_code_or_shares_a_new_id(baseline, rows):
    broken = [dict(r) for r in rows]
    broken[0]["new_iri"] = broken[0]["baseline_iri"]          # the old, place-shaped code carried over
    broken[2]["new_iri"] = broken[1]["new_iri"]               # two concepts under one new ID
    fails = d.nothing_lost(baseline, broken)
    assert any("is not a neutral ID" in f for f in fails)
    assert any("is given to 2 baseline processes" in f for f in fails)


def test_v3_fails_when_a_concept_outside_the_list_changes(baseline, rows, candidate):
    g = copy(candidate)
    s = some_process(g, 5)
    g.set((s, SKOS.prefLabel, Literal("Changed without approval", lang="en")))
    fails = d.only_approved_changed(baseline, g, rows, set())
    old = next(r["baseline_iri"] for r in rows if r["new_iri"] == str(s))
    assert len(fails) == 1 and fails[0].startswith(f"V3: {d.local_id(old)} (now {d.local_id(str(s))}) changed")
    assert d.only_approved_changed(baseline, g, rows, {d.local_id(str(s))}) == []   # approved by new ID
    assert d.only_approved_changed(baseline, g, rows, {d.local_id(old)}) == []      # or by old code


def test_v4_fails_on_a_cycle(baseline):
    g = copy(baseline)
    child = some_process(g, 2)
    parent = g.value(child, SKOS.broader)
    g.add((parent, SKOS.broader, child))
    assert any("cycle" in f for f in d.structure(g))


def test_v4_fails_on_a_deleted_definition_a_second_parent_and_a_duplicate_label(baseline):
    g = copy(baseline)
    a, b = sorted(s for s in d.processes(g) if d.level(g, s) == 4)[:2]
    g.remove((a, SKOS.definition, None))
    other = next(x for x in sorted(d.processes(g), key=str)
                 if d.level(g, x) == 3 and x != g.value(a, SKOS.broader))
    g.add((a, SKOS.broader, other))
    g.set((b, SKOS.prefLabel, g.value(some_process(g, 5), SKOS.prefLabel)))
    fails = d.structure(g)
    assert f"V4: {d.local_id(str(a))} has no definition" in fails
    assert any(f.startswith(f"V4: {d.local_id(str(a))} at level 4 has 2 parents") for f in fails)
    assert any("is shared by" in f for f in fails)


def test_v4_fails_on_a_level_jump(baseline):
    g = copy(baseline)
    s = some_process(g, 5)
    g.set((s, d.CORE.taxonomyLevel, Literal(6)))
    assert any(f"{d.local_id(str(s))} is level 6 under a level-4 parent" in f for f in d.structure(g))


def test_v5_fails_when_xpims_is_put_back_into_one_label(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,yes,system,test\n", encoding="utf-8")
    g = rdflib.Graph()
    s = URIRef(d.DSBP + "process/X-1")
    g.add((s, d.DSBP.taxonomyLevel, Literal(0)))
    g.add((s, SKOS.prefLabel, Literal("Run the refinery planning model", lang="en")))
    g.add((s, SKOS.example, Literal("for example in a commercial planning model", lang="en")))
    assert d.company_neutral(g, terms) == []          # skos:example may name a product the register does not list
    g.set((s, SKOS.prefLabel, Literal("Run XPIMS", lang="en")))
    assert len(d.company_neutral(g, terms)) == 1
    g.set((s, SKOS.prefLabel, Literal("Run XPIMS-based model", lang="en")))  # a hyphen does not hide the term
    assert len(d.company_neutral(g, terms)) == 1


def test_v5_reads_examples_other_subjects_and_the_new_namespace(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,yes,system,test\nMPC,yes,company,test\n", encoding="utf-8")
    s = URIRef(d.DSBP + "process/X-1")
    for prop, subject, text in [
            (SKOS.example, s, "Runs in XPIMS"),                                 # a company-built system as example
            (d.DSBP.primaryPurpose, s, "Uses an MPC-owned tool"),               # a module property, new namespace
            (RDFS.comment, URIRef(d.DSBP + "SomeClass"), "Uses an MPC-owned tool"),  # not a process
            (SKOS.definition, URIRef(d.DSBP + "system/X"), "Uses an MPC-owned tool")]:
        g = rdflib.Graph()
        g.add((s, d.DSBP.taxonomyLevel, Literal(0)))
        g.add((subject, prop, Literal(text, lang="en")))
        assert len(d.company_neutral(g, terms)) == 1, prop
    g = rdflib.Graph()
    g.add((s, SKOS.example, Literal("MPC calls this a planning cycle", lang="en")))  # a company name may stand here
    assert d.company_neutral(g, terms) == []


def test_v6_fails_when_a_changed_definition_has_no_complete_public_source(baseline, rows, candidate):
    g = copy(candidate)
    s = some_process(g, 5)
    g.set((s, SKOS.definition, Literal("A new public definition.", lang="en")))
    g.remove((s, DCTERMS.source, None))
    src = URIRef("https://example.org/standard")
    g.add((s, DCTERMS.source, src))
    for p, o in [(DCTERMS.title, "A standard"), (DCTERMS.publisher, "A body"),
                 (DCTERMS.hasVersion, "1.0"), (d.DSBP.accessDate, "2026-11-24")]:
        g.add((src, p, Literal(o)))
    assert d.evidence(baseline, g, rows) == []
    g.remove((src, d.DSBP.accessDate, None))
    fails = d.evidence(baseline, g, rows)
    assert len(fails) == 1 and "access date" in fails[0]


def test_v6_refuses_the_internal_workbook_as_evidence(baseline, rows, candidate):
    g = copy(candidate)
    s = some_process(g, 5)
    g.set((s, SKOS.definition, Literal("A new definition.", lang="en")))
    g.remove((s, DCTERMS.source, None))
    g.add((s, DCTERMS.source, URIRef("urn:step3c-definition-workbook")))
    assert any("internal" in f for f in d.evidence(baseline, g, rows))


def test_v7_fails_when_one_fact_is_deleted(baseline, rows, candidate):
    procs = d.processes(baseline)
    facts = [(s, p, o) for s, p, o in baseline
             if s in procs and o in procs and str(p).startswith(str(d.CORE))]
    assert facts, "the baseline should hold process-to-process statements in the core namespace"
    m = {URIRef(r["baseline_iri"]): URIRef(r["new_iri"]) for r in rows}
    s, p, o = sorted(facts)[0]
    g = copy(candidate)
    g.remove((m[s], p, m[o]))
    assert len(d.relationships_kept(baseline, g, rows, set())) == 1

def test_v8_passes_a_consistent_graph_and_fails_a_contradiction():
    pytest.importorskip("owlready2")
    if not java_works():
        pytest.skip("HermiT needs Java")
    ex = rdflib.Namespace("https://example.org/t#")
    g = rdflib.Graph()
    g.add((URIRef("https://example.org/t"), RDF.type, OWL.Ontology))
    for c in (ex.A, ex.B):
        g.add((c, RDF.type, OWL.Class))
    g.add((ex.A, OWL.disjointWith, ex.B))
    g.add((ex.x, RDF.type, OWL.NamedIndividual))
    g.add((ex.x, RDF.type, ex.A))
    assert d.logic(g) == []
    g.add((ex.x, RDF.type, ex.B))
    assert d.logic(g) == ["V8: the reasoner found the candidate inconsistent"]


def test_v8_runs_on_the_baseline(baseline):
    pytest.importorskip("owlready2")
    if not java_works():
        pytest.skip("HermiT needs Java")
    assert d.logic(baseline) == []


def test_v8_finds_an_unsatisfiable_class():
    pytest.importorskip("owlready2")
    if not java_works():
        pytest.skip("HermiT needs Java")
    ex = rdflib.Namespace("https://example.org/u#")
    g = rdflib.Graph()
    g.add((URIRef("https://example.org/u"), RDF.type, OWL.Ontology))
    for c in (ex.A, ex.B):
        g.add((c, RDF.type, OWL.Class))
    g.add((ex.A, OWL.disjointWith, ex.B))
    g.add((ex.C, RDF.type, OWL.Class))
    g.add((ex.C, RDFS.subClassOf, ex.A))
    assert d.logic(g) == []
    g.add((ex.C, RDFS.subClassOf, ex.B))   # C is both A and B, which cannot be: no individual can be a C
    assert [f for f in d.logic(g) if "unsatisfiable" in f and "C" in f]


def test_v8_reports_a_java_that_does_not_work(monkeypatch):
    owlready2 = pytest.importorskip("owlready2")

    def broken(*args, **kwargs):
        raise owlready2.OwlReadyJavaError("java: command not found")
    monkeypatch.setattr(owlready2, "sync_reasoner_hermit", broken)
    g = rdflib.Graph()
    g.add((URIRef("https://example.org/j"), RDF.type, OWL.Ontology))
    assert d.logic(g) == ["V8: the reasoner could not run (OwlReadyJavaError); HermiT needs a working Java"]


def test_cli_exits_non_zero_on_the_identity_candidate_because_of_v5(rows, candidate, tmp_path, capsys):
    m = tmp_path / "map.csv"
    with m.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["baseline_iri", "new_iri", "status", "note"])
        w.writeheader()
        w.writerows(rows)
    c = tmp_path / "candidate.ttl"
    candidate.serialize(c, format="turtle")
    # V1 reads this tree's releases, not the candidate, and a cut tree fails it (see the pinned test above), so it is
    # skipped here: this test is about the candidate's checks.
    assert d.main(["--candidate", str(c), "--map", str(m), "--skip", "V1", "V8", "V9"]) == 1
    out = capsys.readouterr().out
    assert "V5: FAIL" in out and "V2: pass" in out and "V3: pass" in out and "V7: pass" in out
    # V5 alone makes it fail: with V4 skipped too it still fails, and with V5 skipped as well it passes.
    assert d.main(["--candidate", str(c), "--map", str(m), "--skip", "V1", "V4", "V8", "V9"]) == 1
    out = capsys.readouterr().out
    assert [line.split(":")[0] for line in out.splitlines() if ": FAIL" in line] == ["V5"]
    assert d.main(["--candidate", str(c), "--map", str(m), "--skip", "V1", "V4", "V5", "V8", "V9"]) == 0
    capsys.readouterr()
    # V9 is not built, so it fails unless it is skipped: an unbuilt check never reads as a pass.
    assert d.main(["--candidate", str(c), "--map", str(m), "--skip", "V1", "V4", "V5", "V8"]) == 1
    assert "V9: FAIL" in capsys.readouterr().out
    capsys.readouterr()
    with pytest.raises(FileNotFoundError):
        d.main(["--candidate", str(c), "--map", str(m), "--approved", str(tmp_path / "typo.txt")])


def test_cli_reports_v1_and_fails_on_it(rows, candidate, tmp_path, capsys, monkeypatch):
    # The CLI tests above skip V1, which reads this tree's releases. This one stands in a result for it, so the CLI's
    # handling of V1 is tested on a shipped tree and a cut tree alike.
    m = tmp_path / "map.csv"
    with m.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["baseline_iri", "new_iri", "status", "note"])
        w.writeheader()
        w.writerows(rows)
    c = tmp_path / "candidate.ttl"
    candidate.serialize(c, format="turtle")
    others = ["--skip", "V4", "V5", "V8", "V9"]
    monkeypatch.setattr(d, "baseline_untouched", lambda: [])
    assert d.main(["--candidate", str(c), "--map", str(m)] + others) == 0
    assert "V1: pass" in capsys.readouterr().out
    monkeypatch.setattr(d, "baseline_untouched", lambda: ["V1: manifest x/1.0.0/manifest.json is in the recorded list and missing"])
    assert d.main(["--candidate", str(c), "--map", str(m)] + others) == 1
    out = capsys.readouterr().out
    assert [line.split(":")[0] for line in out.splitlines() if ": FAIL" in line] == ["V1"]
    assert "x/1.0.0/manifest.json" in out
    assert d.main(["--candidate", str(c), "--map", str(m), "--skip", "V1", "V4", "V5", "V8", "V9"]) == 0
    capsys.readouterr()


# Fixes from the independent review, rounds 1 and 2, each shown failing on a broken copy ---------------------------------
def test_v2_fails_when_a_kept_concept_is_missing_from_the_candidate(baseline, rows, candidate):
    g = copy(candidate)
    gone = URIRef(rows[5]["new_iri"])
    g.remove((gone, None, None))
    assert d.nothing_lost(baseline, rows, g) == [
        f"V2: {rows[5]['baseline_iri']} is retained but its new IRI {d.local_id(str(gone))} "
        f"is not a process in the candidate"]
    g = copy(candidate)
    g.remove((gone, d.CORE.taxonomyLevel, None))      # still has a label, but no level: no longer a process
    assert len(d.nothing_lost(baseline, rows, g)) == 1


@pytest.mark.parametrize("bad", ["DSBP-P-000001/", "x/DSBP-P-000001", "DSBP-P-1"])
def test_v2_fails_on_a_new_iri_with_extra_path_or_a_short_number(baseline, rows, bad):
    broken = [dict(r) for r in rows]
    broken[0]["new_iri"] = d.NEW_PROC + bad
    assert any("is not a neutral ID" in f for f in d.nothing_lost(baseline, broken))


def test_v2_fails_when_an_excluded_concept_keeps_a_new_iri_or_stays_in_the_candidate(baseline, rows):
    broken = [dict(r) for r in rows]
    broken[0]["status"], broken[0]["note"] = "excluded", "DSBP-DEC-0018: test"
    g = rdflib.Graph()
    g.add((URIRef(broken[0]["baseline_iri"]), SKOS.prefLabel, Literal("still here")))
    fails = d.nothing_lost(baseline, broken, g)
    assert any("is excluded but still has a new IRI" in f for f in fails)
    assert any("is excluded but is still in the candidate" in f for f in fails)
    g = rdflib.Graph()
    g.add((URIRef(d.NEW_PROC + "DSBP-P-000002"), SKOS.narrower, URIRef(broken[0]["baseline_iri"])))  # as object
    assert any("is excluded but is still in the candidate" in f for f in d.nothing_lost(baseline, broken, g))


def test_v3_sees_through_the_move_to_the_new_namespace(baseline, rows, candidate):
    """A candidate that moves every module property to the new namespace and changes nothing else passes V3."""
    g = rdflib.Graph()
    for s, p, o in candidate:
        g.add((s, URIRef(str(p).replace(str(d.CORE), str(d.DSBP))), o))
    assert d.only_approved_changed(baseline, g, rows, set()) == []
    assert d.relationships_kept(baseline, g, rows) == []
    s = some_process(g, 5)
    g.set((s, d.DSBP.primaryPurpose, Literal("Changed without approval", lang="en")))
    assert len(d.only_approved_changed(baseline, g, rows, set())) == 1


def test_v3_fails_on_an_unapproved_exclusion_or_new_concept(baseline, rows, candidate):
    # A concept nothing points at, so excluding it changes no other concept's statements.
    i = next(i for i, r in enumerate(rows) if not list(baseline.subject_predicates(URIRef(r["baseline_iri"]))))
    broken = [dict(r) for r in rows]
    broken[i].update(status="excluded", new_iri="", note="test")
    g = copy(candidate)
    g.remove((URIRef(rows[i]["new_iri"]), None, None))
    new = URIRef(d.NEW_PROC + "DSBP-P-000900")
    g.add((new, d.CORE.taxonomyLevel, Literal(1)))
    fails = d.only_approved_changed(baseline, g, broken, set())
    old = d.local_id(rows[i]["baseline_iri"])
    assert f"V3: {old} is excluded but is not on the approved list" in fails
    assert "V3: DSBP-P-000900 is a new concept but is not on the approved list" in fails
    assert d.only_approved_changed(baseline, g, broken, {old, "DSBP-P-000900"}) == []


def test_v4_fails_on_a_dangling_parent_a_negative_or_double_level_and_blank_or_double_definitions(baseline):
    g = copy(baseline)
    a, b, c, e = sorted(s for s in d.processes(g) if d.level(g, s) == 5)[:4]
    g.set((a, SKOS.broader, URIRef(d.OLD_PROC + "NOT-THERE")))
    g.add((b, d.CORE.taxonomyLevel, Literal(7)))
    g.set((c, SKOS.definition, Literal("   ", lang="en")))
    g.add((e, SKOS.definition, Literal("A second definition.", lang="en")))
    top = some_process(g, 0)
    g.set((top, d.CORE.taxonomyLevel, Literal(-1)))
    fails = d.structure(g)
    assert f"V4: {d.local_id(str(a))} sits under NOT-THERE, which is not a process in the candidate" in fails
    assert f"V4: {d.local_id(str(b))} has 2 different levels; it needs one" in fails
    assert f"V4: {d.local_id(str(c))} has no definition" in fails
    assert f"V4: {d.local_id(str(e))} has 2 definitions; it needs one" in fails
    assert f"V4: {d.local_id(str(top))} has a negative level -1" in fails


def test_v4_runs_the_shacl_shapes(baseline, tmp_path):
    shapes = tmp_path / "shapes.ttl"
    shapes.write_text("""@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
<https://example.org/s#NeedsNotation> a sh:NodeShape ; sh:targetClass skos:Concept ;
    sh:property [ sh:path skos:prefLabel ; sh:minCount 1 ] .
""", encoding="utf-8")
    g = rdflib.Graph()
    s = URIRef(d.NEW_PROC + "DSBP-P-000001")
    g.add((s, RDF.type, SKOS.Concept))
    g.add((s, d.DSBP.taxonomyLevel, Literal(0)))
    g.add((s, SKOS.definition, Literal("A test concept.", lang="en")))
    assert any("SHACL shapes do not conform" in f for f in d.structure(g, shapes))
    g.add((s, SKOS.prefLabel, Literal("Test", lang="en")))
    assert d.structure(g, shapes) == []


def _sourced(candidate, src, facts):
    g = copy(candidate)
    s = some_process(g, 5)
    g.set((s, SKOS.definition, Literal("A new public definition.", lang="en")))
    g.remove((s, DCTERMS.source, None))
    g.add((s, DCTERMS.source, src))
    for p, o in facts:
        g.add((src, p, o if not isinstance(o, str) else Literal(o)))
    return g


FULL = [(DCTERMS.title, "A standard"), (DCTERMS.publisher, "A body"), (DCTERMS.hasVersion, "1.0"),
        (d.DSBP.accessDate, "2026-11-24")]


def test_v6_takes_the_url_from_the_iri_when_the_identifier_is_not_a_url(baseline, rows, candidate):
    g = _sourced(candidate, URIRef("https://example.org/standard"), FULL + [(DCTERMS.identifier, "ISO 22400-2")])
    assert d.evidence(baseline, g, rows) == []


def test_v6_refuses_a_minted_iri_a_blank_value_and_an_internal_identifier(baseline, rows, candidate):
    minted = _sourced(candidate, URIRef(d.DSBP + "source/my-standard"), FULL)
    assert any("URL" in f for f in d.evidence(baseline, minted, rows))
    blank = _sourced(candidate, URIRef("https://example.org/standard"),
                     [(p, "  " if p == DCTERMS.publisher else o) for p, o in FULL])
    assert any("publisher" in f for f in d.evidence(baseline, blank, rows))
    internal = _sourced(candidate, URIRef("https://example.org/standard"),
                        FULL + [(DCTERMS.identifier, "Step3C-Definition-Workbook row 12")])
    assert any("internal" in f for f in d.evidence(baseline, internal, rows))


def test_v6_sees_a_second_definition_added_beside_the_old_one(baseline, rows, candidate):
    g = copy(candidate)
    s = next(x for x in sorted(d.processes(g), key=str) if g.value(x, SKOS.definition) is not None)
    g.remove((s, DCTERMS.source, None))
    g.add((s, SKOS.definition, Literal("An added definition.", lang="fr")))
    assert len(d.evidence(baseline, g, rows)) == 1


def test_v7_checks_approved_concepts_too_and_allows_listed_removals(baseline, rows, candidate):
    procs = d.processes(baseline)
    s, p, o = sorted((s, p, o) for s, p, o in baseline
                     if s in procs and o in procs and str(p).startswith(str(d.CORE)))[0]
    m = {URIRef(r["baseline_iri"]): URIRef(r["new_iri"]) for r in rows}
    g = copy(candidate)
    g.remove((m[s], p, m[o]))
    assert len(d.relationships_kept(baseline, g, rows)) == 1      # being approved in V3 does not excuse it
    fact = f"{d.local_id(str(s))} {d.local_id(str(p))} {d.local_id(str(o))}"
    assert d.relationships_kept(baseline, g, rows, {fact}) == []


def test_v7_skips_statements_whose_end_is_excluded(baseline, rows, candidate):
    procs = d.processes(baseline)
    s, p, o = sorted((s, p, o) for s, p, o in baseline
                     if s in procs and o in procs and str(p).startswith(str(d.CORE)))[0]
    broken = [dict(r) for r in rows]
    r = next(r for r in broken if r["baseline_iri"] == str(o))
    r.update(status="excluded", new_iri="", note="test")
    g = copy(candidate)
    g.remove((URIRef(next(x["new_iri"] for x in rows if x["baseline_iri"] == str(o))), None, None))
    assert not [f for f in d.relationships_kept(baseline, g, broken) if d.local_id(str(o)) in f]


def test_read_approved_refuses_a_missing_file(tmp_path):
    assert d.read_approved(None) == set()
    with pytest.raises(FileNotFoundError):
        d.read_approved(tmp_path / "missing.txt")


def test_cli_passes_removals_and_shapes_through(baseline, rows, candidate, tmp_path, capsys):
    procs = d.processes(baseline)
    s, p, o = sorted((s, p, o) for s, p, o in baseline
                     if s in procs and o in procs and str(p).startswith(str(d.CORE)))[0]
    m = {URIRef(r["baseline_iri"]): URIRef(r["new_iri"]) for r in rows}
    g = copy(candidate)
    g.remove((m[s], p, m[o]))
    mp, c = tmp_path / "map.csv", tmp_path / "candidate.ttl"
    with mp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["baseline_iri", "new_iri", "status", "note"])
        w.writeheader()
        w.writerows(rows)
    g.serialize(c, format="turtle")
    only7 = ["--skip", "V1", "V2", "V3", "V4", "V5", "V6", "V8", "V9"]
    assert d.main(["--candidate", str(c), "--map", str(mp)] + only7) == 1
    rm = tmp_path / "removals.txt"
    rm.write_text(f"{d.local_id(str(s))} {d.local_id(str(p))} {d.local_id(str(o))}\n", encoding="utf-8")
    assert d.main(["--candidate", str(c), "--map", str(mp), "--removals", str(rm)] + only7) == 0
    shapes = tmp_path / "shapes.ttl"
    shapes.write_text("""@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
<https://example.org/s#Never> a sh:NodeShape ; sh:targetClass skos:Concept ;
    sh:property [ sh:path skos:prefLabel ; sh:maxCount 0 ] .
""", encoding="utf-8")
    capsys.readouterr()
    d.main(["--candidate", str(c), "--map", str(mp), "--shapes", str(shapes),
            "--skip", "V1", "V2", "V3", "V5", "V6", "V7", "V8"])
    assert "SHACL shapes do not conform" in capsys.readouterr().out


def test_v3_refuses_a_stray_old_iri_even_when_its_code_is_approved(baseline, rows, candidate):
    g = copy(candidate)
    old = URIRef(rows[3]["baseline_iri"])
    g.add((old, d.CORE.taxonomyLevel, Literal(4)))
    g.add((URIRef(d.NEW_PROC + d.local_id(str(old))), d.CORE.taxonomyLevel, Literal(4)))   # new namespace, old code
    fails = d.only_approved_changed(baseline, g, rows, {d.local_id(str(old))})
    assert sum("neither a mapped concept nor a new neutral ID" in f for f in fails) == 2


def test_v3_sees_a_property_left_in_both_namespaces(baseline, rows, candidate):
    g = copy(candidate)
    s = some_process(g, 5)
    for o in list(g.objects(s, d.CORE.primaryPurpose)) or [Literal("x")]:
        g.add((s, d.CORE.primaryPurpose, o))
        g.add((s, d.DSBP.primaryPurpose, o))
    assert any("in both the old and the new namespace" in f for f in d.only_approved_changed(baseline, g, rows, set()))


def test_v5_lets_a_cited_filing_name_its_company_but_not_a_system(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,yes,system,test\nMPC,yes,company,test\n", encoding="utf-8")
    s, src = URIRef(d.NEW_PROC + "DSBP-P-000001"), URIRef("https://www.sec.gov/example-10-k")
    g = rdflib.Graph()
    g.add((s, d.DSBP.taxonomyLevel, Literal(0)))
    g.add((s, DCTERMS.source, src))
    g.add((src, DCTERMS.title, Literal("MPC 2025 Form 10-K")))
    assert d.company_neutral(g, terms) == []
    g.add((src, DCTERMS.description, Literal("Describes XPIMS")))
    assert len(d.company_neutral(g, terms)) == 1
    g = rdflib.Graph()
    g.add((URIRef(d.DSBP + "SomeClass"), DCTERMS.title, Literal("MPC terms")))   # not a cited source
    assert len(d.company_neutral(g, terms)) == 1


@pytest.mark.parametrize("iri", ["http://w3id.org/ds-bp/source/ref-1", "https://W3ID.ORG/ds-bp/source/ref-1"])
def test_v6_refuses_minted_iris_in_any_scheme_or_case(baseline, rows, candidate, iri):
    g = _sourced(candidate, URIRef(iri), FULL)
    assert any("URL" in f for f in d.evidence(baseline, g, rows))


# Fixes from the first independent review of the generalization pull request, each shown failing on a broken copy ------------------------------------
def test_v1_fails_when_a_whole_manifest_is_deleted(tmp_path):
    rel = tmp_path / "releases"
    shutil.copytree(d.RELEASES / "core" / "2.4.0", rel / "core" / "2.4.0")
    listed = {k: v for k, v in d.read_manifest_list().items() if k.startswith(("core/2.4.0/", "data-product/"))}
    assert d.baseline_untouched(rel, listed) == [
        "V1: manifest data-product/1.2.0/manifest.json is in the recorded list and missing"]


def test_v1_fails_when_a_manifest_is_edited(tmp_path):
    rel = tmp_path / "releases"
    shutil.copytree(d.RELEASES / "core" / "2.4.0", rel / "core" / "2.4.0")
    m = rel / "core" / "2.4.0" / "manifest.json"
    m.write_text(m.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    core_only = {k: v for k, v in d.read_manifest_list().items() if k.startswith("core/2.4.0/")}
    assert d.baseline_untouched(rel, core_only) == ["V1: manifest core/2.4.0/manifest.json differs from its recorded hash"]


def test_v2_fails_when_an_old_iri_stays_beside_the_new_one(baseline, rows, candidate):
    g = copy(candidate)
    g.add((URIRef(rows[3]["baseline_iri"]), SKOS.prefLabel, Literal("left behind", lang="en")))
    fails = d.nothing_lost(baseline, rows, g)
    assert len(fails) == 1 and "old IRI is still in the candidate" in fails[0]


def test_v2_fails_when_the_map_and_owl_deprecated_disagree(baseline, rows, candidate):
    g = copy(candidate)
    live = next(r for r in rows if r["status"] == "retained")
    g.add((URIRef(live["new_iri"]), OWL.deprecated, Literal(True)))
    fails = d.nothing_lost(baseline, rows, g)
    assert len(fails) == 1 and "is owl:deprecated" in fails[0]
    marked = [dict(r, status="deprecated") if r is live else r for r in rows]
    assert d.nothing_lost(baseline, marked, g) == []
    assert any("is not owl:deprecated" in f for f in d.nothing_lost(baseline, marked, candidate))


def test_v3_sees_a_change_to_a_class_or_the_ontology_header(baseline, rows, candidate):
    s = sorted(x for x in set(baseline.subjects(RDF.type, OWL.Class)) if isinstance(x, URIRef))[0]
    g = copy(candidate)
    g.add((s, RDFS.comment, Literal("A new comment.", lang="en")))
    fails = d.only_approved_changed(baseline, g, rows, set())
    assert len(fails) == 1 and "is not a process" in fails[0]
    assert d.only_approved_changed(baseline, g, rows, {d.local_id(str(s))}) == []


def test_v3_treats_a_class_moved_to_the_new_namespace_as_unchanged(baseline, rows, candidate):
    def move(x):
        return URIRef(str(x).replace(str(d.CORE), str(d.DSBP), 1)) if isinstance(x, URIRef) else x
    g = rdflib.Graph()
    for s, p, o in candidate:
        g.add((move(s), move(p), move(o)))
    assert d.only_approved_changed(baseline, g, rows, set()) == []


def test_cli_ignore_leaves_notation_out_of_v3(baseline, rows, candidate, tmp_path, capsys):
    g = copy(candidate)
    g.remove((None, SKOS.notation, None))
    if len(g) == len(candidate):
        pytest.skip("the baseline has no skos:notation")
    mp, c = tmp_path / "map.csv", tmp_path / "candidate.ttl"
    with mp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["baseline_iri", "new_iri", "status", "note"])
        w.writeheader()
        w.writerows(rows)
    g.serialize(c, format="turtle")
    only3 = ["--skip", "V1", "V2", "V4", "V5", "V6", "V7", "V8", "V9"]
    assert d.main(["--candidate", str(c), "--map", str(mp)] + only3) == 1
    assert d.main(["--candidate", str(c), "--map", str(mp), "--ignore", "skos:notation"] + only3) == 0
    with pytest.raises(ValueError):
        d.expand("notation")


def test_v4_fails_on_a_narrower_link_that_does_not_match_broader(baseline, candidate):
    g = copy(candidate)
    child = some_process(g, 2)
    parent = g.value(child, SKOS.broader)
    g.add((parent, SKOS.narrower, child))
    fails = d.structure(g)
    assert any("does not list it as narrower" in f for f in fails)          # the other links have no inverse
    g = copy(candidate)
    g.add((parent, SKOS.narrower, some_process(g, 3)))
    assert any("which does not have it as broader" in f for f in d.structure(g))


def test_v4_fails_on_a_missing_or_doubled_preferred_label(candidate):
    base = len(d.structure(candidate))
    g = copy(candidate)
    s = some_process(g, 3)
    g.remove((s, SKOS.prefLabel, None))
    assert any("has no preferred label" in f for f in d.structure(g))
    g = copy(candidate)
    g.add((s, SKOS.prefLabel, Literal("A second English label", lang="en")))
    assert len(d.structure(g)) == base + 1


def test_v5_reads_any_property_and_the_ontology_header(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,yes,system,test\n", encoding="utf-8")
    onto = URIRef(d.DSBP)
    for prop in (DCTERMS.creator, URIRef("https://example.org/anyProperty"), OWL.versionInfo):
        g = rdflib.Graph()
        g.add((onto, prop, Literal("Built from XPIMS")))
        assert len(d.company_neutral(g, terms, tmp_path / "none.csv")) == 1, prop


def test_v5_treats_an_underscore_as_a_boundary(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,yes,system,test\n", encoding="utf-8")
    g = rdflib.Graph()
    g.add((URIRef(d.DSBP + "x"), RDFS.label, Literal("XPIMS_run_2")))
    assert len(d.company_neutral(g, terms, tmp_path / "none.csv")) == 1
    g.set((URIRef(d.DSBP + "x"), RDFS.label, Literal("XPIMSX")))      # a letter joins words: a different word
    assert d.company_neutral(g, terms, tmp_path / "none.csv") == []


def test_v5_allows_a_registered_generic_meaning_only(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nDPO,yes,system,test\n", encoding="utf-8")
    allowed = tmp_path / "allowed.csv"
    allowed.write_text("term,phrase,why\nDPO,days payable outstanding (DPO),finance measure\n", encoding="utf-8")
    g = rdflib.Graph()
    s = URIRef(d.DSBP + "measure/x")
    g.add((s, SKOS.definition, Literal("Days payable outstanding (DPO) is a working-capital measure.", lang="en")))
    assert d.company_neutral(g, terms, allowed) == []
    g.add((s, SKOS.scopeNote, Literal("Planned in DPO.", lang="en")))
    assert len(d.company_neutral(g, terms, allowed)) == 1


def test_v5_lets_a_cited_source_name_its_publisher(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nMPC,yes,company,test\n", encoding="utf-8")
    g = rdflib.Graph()
    s, src = URIRef(d.NEW_PROC + "DSBP-P-000001"), URIRef("https://example.org/10-k")
    g.add((s, DCTERMS.source, src))
    g.add((src, DCTERMS.publisher, Literal("MPC")))
    assert d.company_neutral(g, terms, tmp_path / "none.csv") == []


def test_v6_fails_when_an_internal_source_stays_beside_a_public_one(baseline, rows, candidate):
    g = _sourced(candidate, URIRef("https://example.org/standard"), FULL)
    s = some_process(g, 5)
    g.add((s, DCTERMS.source, URIRef("urn:step3c-definition-workbook")))
    fails = d.evidence(baseline, g, rows)
    assert len(fails) == 1 and "still cites an internal source" in fails[0]


def test_v6_accepts_a_urn_identifier_on_a_public_source(baseline, rows, candidate):
    g = _sourced(candidate, URIRef("https://example.org/book"), FULL + [(DCTERMS.identifier, "urn:isbn:9780000000000")])
    assert d.evidence(baseline, g, rows) == []


def test_v6_reads_definitions_of_subjects_that_are_not_processes(baseline, rows, candidate):
    g = copy(candidate)
    cls = URIRef(d.DSBP + "measure/SomeNewClass")
    g.add((cls, SKOS.definition, Literal("A new class.", lang="en")))
    assert len(d.evidence(baseline, g, rows)) == 1
    s = sorted(x for x in set(baseline.subjects(SKOS.definition, None))
               if isinstance(x, URIRef) and x not in d.processes(baseline))
    if s:  # an unchanged definition of a baseline class needs no new source
        assert d.evidence(baseline, candidate, rows) == []


def test_v7_reads_skos_related(baseline):
    procs = sorted(d.processes(baseline), key=str)
    a, b = procs[0], procs[1]
    g = copy(baseline)
    g.add((a, SKOS.related, b))
    rows = [{"baseline_iri": str(s), "new_iri": str(s), "status": "retained", "note": ""} for s in procs]
    assert d.relationships_kept(g, baseline, rows) == [
        f"V7: {d.local_id(str(a))} related {d.local_id(str(b))} is gone"]


def test_v8_ignores_owl_imports():
    pytest.importorskip("owlready2")
    if not java_works():
        pytest.skip("HermiT needs Java")
    g = rdflib.Graph()
    o = URIRef("https://example.org/i")
    g.add((o, RDF.type, OWL.Ontology))
    g.add((o, OWL.imports, URIRef("https://example.invalid/never-there.ttl")))
    assert d.logic(g) == []


def test_v8_reports_a_load_failure_instead_of_crashing(monkeypatch):
    owlready2 = pytest.importorskip("owlready2")

    class Broken:
        def load(self):
            raise ValueError("cannot parse")

    monkeypatch.setattr(owlready2.World, "get_ontology", lambda self, iri: Broken())
    g = rdflib.Graph()
    g.add((URIRef("https://example.org/j"), RDF.type, OWL.Ontology))
    fails = d.logic(g)
    assert len(fails) == 1 and "could not be loaded" in fails[0]


def test_v5_catches_a_company_system_name_in_any_letter_case():
    g = rdflib.Graph()
    g.add((URIRef(d.DSBP + "x"), RDFS.label, Literal("runs in xpims")))
    assert len(d.company_neutral(g)) == 1


@pytest.mark.parametrize("text, why", [
    ("{ not json", "JSONDecodeError"),
    ("[]", "AttributeError"),
    ('{"files": null}', "files is not a map"),
    ('{"files": []}', "files is not a map"),
])
def test_v1_reports_an_unreadable_manifest_and_checks_the_rest(tmp_path, text, why):
    rel = tmp_path / "releases"
    for name in ("core", "organization"):
        src = next(p.parent for p in sorted((d.RELEASES / name).glob("*/manifest.json")))
        shutil.copytree(src, rel / name / src.name)
    bad = next((rel / "core").glob("*/manifest.json"))
    bad.write_bytes(text.encode("utf-8"))
    other = next((rel / "organization").glob("*/manifest.json")).parent
    victim = other / next(iter(json.loads((other / "manifest.json").read_text(encoding="utf-8"))["files"]))
    victim.write_bytes(victim.read_bytes() + b" ")
    fails = d.baseline_untouched(rel, {})
    assert f"V1: {bad.relative_to(rel).as_posix()} is not a readable manifest ({why})" in fails
    assert f"V1: {victim.relative_to(rel).as_posix()} differs from its manifest hash" in fails


def test_v1_reports_a_manifest_that_is_not_utf8(tmp_path):
    rel = tmp_path / "releases"
    src = next(p.parent for p in sorted((d.RELEASES / "core").glob("*/manifest.json")))
    shutil.copytree(src, rel / "core" / src.name)
    (rel / "core" / src.name / "manifest.json").write_bytes(b"\xff\xfe{")
    assert any("is not a readable manifest (UnicodeDecodeError)" in f for f in d.baseline_untouched(rel, {}))


# Follow-ups from the reviews of the first release checks --------------------------------------------------------------


def test_v3_sees_a_change_inside_a_blank_node_and_not_a_new_blank_label(baseline, rows, candidate):
    s, old = URIRef(rows[0]["new_iri"]), URIRef(rows[0]["baseline_iri"])
    note = URIRef("https://example.org/qualifiedNote")
    b1, b2 = rdflib.BNode(), rdflib.BNode()
    base, cand = copy(baseline), copy(candidate)
    base.add((old, note, b1))
    base.add((b1, RDFS.comment, Literal("same")))
    cand.add((s, note, b2))                       # another label, the same content: no change
    cand.add((b2, RDFS.comment, Literal("same")))
    assert d.only_approved_changed(base, cand, rows, set()) == []
    cand.set((b2, RDFS.comment, Literal("edited")))
    assert any(d.local_id(str(old)) in f for f in d.only_approved_changed(base, cand, rows, set()))


def test_v4_lets_one_concept_carry_one_label_in_two_languages(candidate):
    base = d.structure(candidate)
    g = copy(candidate)
    s = some_process(g, 3)
    g.add((s, SKOS.prefLabel, Literal(str(g.value(s, SKOS.prefLabel)), lang="fr")))
    assert len(d.structure(g)) == len(base)


@pytest.mark.parametrize("blank", [Literal("  "), Literal("", lang="fr"), Literal(" ", lang="en")])
def test_v4_fails_on_a_blank_label_beside_a_real_one(candidate, blank):
    g = copy(candidate)
    s = some_process(g, 3)
    g.add((s, SKOS.prefLabel, blank))
    fails = d.structure(g)
    assert any(f"{d.local_id(str(s))} has a blank preferred label" in f for f in fails)
    assert not any("is shared by" in f for f in fails)


def test_v4_counts_labels_per_language(candidate):
    g = copy(candidate)
    s = some_process(g, 3)
    g.add((s, SKOS.prefLabel, Literal("Second", lang="en")))
    g.add((s, SKOS.prefLabel, Literal("Premier", lang="fr")))
    fails = [f for f in d.structure(g) if d.local_id(str(s)) in f and "preferred labels" in f]
    assert fails == [f"V4: {d.local_id(str(s))} has 2 preferred labels in en; it needs one"]


def test_v4_reports_a_level_that_is_not_a_whole_number(candidate):
    g = copy(candidate)
    s = some_process(g, 3)
    g.set((s, d.CORE.taxonomyLevel, Literal("three")))
    fails = d.structure(g)
    assert any(f"{d.local_id(str(s))} has a level that is not a whole number (three)" in f for f in fails)


def test_indented_comment_lines_are_skipped(tmp_path):
    approved = tmp_path / "approved.txt"
    approved.write_text("CM-1-1\n   # CM-1-2 is not approved\n", encoding="utf-8")
    assert d.read_approved(approved) == {"CM-1-1"}
    removals = tmp_path / "removals.txt"
    removals.write_text("  # CM-1 related CM-2\nCM-1-1  related   CM-1-2\n", encoding="utf-8")
    assert d.read_removals(removals) == {"CM-1-1 related CM-1-2"}


def test_v5_reads_iris_but_lets_a_cited_source_keep_its_own(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nMarathon,no,company,test\nXPIMS,no,system,test\n",
                     encoding="utf-8")
    none = tmp_path / "none.csv"
    s = URIRef(d.NEW_PROC + "DSBP-P-000001")
    g = rdflib.Graph()
    g.add((s, d.DSBP.taxonomyLevel, Literal(0)))
    g.add((s, URIRef(d.DSBP + "feedsSystem"), URIRef(d.DSBP + "system/xpims-run")))
    assert any("IRI" in f and "XPIMS" in f for f in d.company_neutral(g, terms, none))
    src = URIRef("https://www.marathonpetroleum.com/Investors/")
    g = rdflib.Graph()
    g.add((s, RDFS.seeAlso, src))                                 # not a cited source: a hit
    assert any("the IRI" in f and "Marathon" in f for f in d.company_neutral(g, terms, none))
    g = rdflib.Graph()
    g.add((s, DCTERMS.source, src))
    g.add((src, DCTERMS.identifier, Literal("https://www.marathon.example/10-k.htm")))
    g.add((src, DCTERMS.identifier, URIRef("https://www.marathon.example/10-k.htm")))
    assert d.company_neutral(g, terms, none) == []
    g.add((src, DCTERMS.identifier, URIRef("https://vendor.example/xpims-guide")))  # a system, even on a source
    assert any("xpims-guide" in f for f in d.company_neutral(g, terms, none))


@pytest.mark.parametrize("iri", ["https://w3id.org/mpc/ontology/modules/core/taxonomyLevel",
                                 "https://example.org/hasXpimsId", "https://example.org/MPCProcess",
                                 "https://example.org/mpc_process"])
def test_v5_reads_an_iri_in_any_letter_case_and_word_split(tmp_path, iri):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nMPC,yes,company,test\nXPIMS,no,system,test\n", encoding="utf-8")
    g = rdflib.Graph()
    g.add((URIRef(d.NEW_PROC + "DSBP-P-000001"), URIRef(iri), Literal(1)))
    assert any("the IRI" in f for f in d.company_neutral(g, terms, tmp_path / "none.csv"))


def test_v5_does_not_read_a_short_term_inside_a_longer_word(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nMPC,yes,company,test\n", encoding="utf-8")
    g = rdflib.Graph()
    g.add((URIRef(d.NEW_PROC + "DSBP-P-000001"), URIRef("https://example.org/rmpcx"), Literal(1)))
    assert d.company_neutral(g, terms, tmp_path / "none.csv") == []


@pytest.mark.parametrize("text", ["Retired per PTC-001.", "See step3c-parked-tree-changes.md.",
                                  "From the plan.xlsx sheet", "ptc-001", "PTC-001-AB", "See PLAN.XLSX", "Notes.MD"])
def test_v5_refuses_the_predecessors_working_trace(tmp_path, text):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,no,system,test\n", encoding="utf-8")
    g = rdflib.Graph()
    g.add((URIRef(d.NEW_PROC + "DSBP-P-000001"), DCTERMS.provenance, Literal(text, lang="en")))
    fails = d.company_neutral(g, terms, tmp_path / "none.csv")
    assert len(fails) == 1 and "working trace" in fails[0]


def test_v5_lets_a_cited_source_name_its_own_file(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,no,system,test\n", encoding="utf-8")
    s, src = URIRef(d.NEW_PROC + "DSBP-P-000001"), URIRef("https://www.eia.gov/petroleum/")
    g = rdflib.Graph()
    g.add((s, DCTERMS.source, src))
    g.add((src, DCTERMS.title, Literal("Refinery capacity data, refcap.xlsx")))
    assert d.company_neutral(g, terms, tmp_path / "none.csv") == []


def test_v5_reads_web_addresses_and_examples_as_no_working_file(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,no,system,test\n", encoding="utf-8")
    s = URIRef(d.NEW_PROC + "DSBP-P-000001")
    g = rdflib.Graph()
    g.add((s, SKOS.scopeNote, Literal("Published at https://gov.md/energy and https://data.example/refcap.xlsx")))
    g.add((s, SKOS.example, Literal("A shipper files the nomination as nominations.csv.")))
    assert d.company_neutral(g, terms, tmp_path / "none.csv") == []
    g.add((s, SKOS.example, Literal("Parked under PTC-002.")))              # a code is never public
    assert len(d.company_neutral(g, terms, tmp_path / "none.csv")) == 1


def test_v5_refuses_a_trace_code_on_a_cited_source(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nXPIMS,no,system,test\n", encoding="utf-8")
    s, src = URIRef(d.NEW_PROC + "DSBP-P-000001"), URIRef("https://www.eia.gov/petroleum/")
    g = rdflib.Graph()
    g.add((s, DCTERMS.source, src))
    g.add((src, DCTERMS.description, Literal("Chosen under PTC-001")))
    assert len(d.company_neutral(g, terms, tmp_path / "none.csv")) == 1


def test_v3_counts_two_equal_blank_nodes_and_compares_unreferenced_ones(baseline, rows, candidate):
    s, old = URIRef(rows[0]["new_iri"]), URIRef(rows[0]["baseline_iri"])
    note = URIRef("https://example.org/qualifiedNote")
    base, cand = copy(baseline), copy(candidate)
    for g, subj in ((base, old), (cand, s)):
        b = rdflib.BNode()
        g.add((subj, note, b))
        g.add((b, RDFS.comment, Literal("same")))
    assert d.only_approved_changed(base, cand, rows, set()) == []
    b = rdflib.BNode()
    cand.add((s, note, b))                               # a second blank node with the same content
    cand.add((b, RDFS.comment, Literal("same")))
    assert any(d.local_id(str(old)) in f for f in d.only_approved_changed(base, cand, rows, set()))
    cand = copy(candidate)
    axiom = rdflib.BNode()                               # an axiom that no named subject points at
    cand.add((axiom, RDF.type, OWL.AllDisjointClasses))
    assert any("blank-nodes" in f for f in d.only_approved_changed(baseline, cand, rows, set()))


def test_v3_tells_loops_to_different_blank_nodes_apart(baseline, rows):
    def chain(back_to):
        g = rdflib.Graph()
        s = URIRef("https://example.org/thing")
        b = [rdflib.BNode() for _ in range(3)]
        g.add((s, RDFS.seeAlso, b[0]))
        g.add((b[0], RDFS.seeAlso, b[1]))
        g.add((b[1], RDFS.seeAlso, b[2]))
        g.add((b[2], RDFS.seeAlso, b[back_to]))
        return d._statements(g, s, {})
    assert chain(0) != chain(1)
    g = rdflib.Graph()
    b = rdflib.BNode()
    g.add((URIRef("https://example.org/x"), RDFS.seeAlso, b))
    g.add((b, RDFS.seeAlso, b))
    assert d._statements(g, URIRef("https://example.org/x"), {}) == {
        (RDFS.seeAlso, ("_:", frozenset({(RDFS.seeAlso, ("_:cycle", 1))})))}


@pytest.mark.parametrize("value", [Literal("3.0", datatype=rdflib.XSD.decimal), Literal("1", datatype=rdflib.XSD.boolean),
                                   Literal("3"), rdflib.BNode("123")])
def test_a_level_must_be_an_integer_literal(value):
    assert d._whole(value) is None
    assert d._whole(Literal(3)) == 3


def test_v4_takes_no_level_from_a_concept_with_a_good_and_a_bad_one(candidate):
    g = copy(candidate)
    s = some_process(g, 3)
    g.add((s, d.DSBP.taxonomyLevel, Literal("three")))
    assert d.level(g, s) is None
    assert any("not a whole number" in f for f in d.structure(g) if d.local_id(str(s)) in f)


def test_v6_needs_the_access_date_written_as_a_date(baseline, rows, candidate):
    facts = [(p, "last week" if p == d.DSBP.accessDate else o) for p, o in FULL]
    g = _sourced(candidate, URIRef("https://example.org/standard"), facts)
    assert any("access date" in f for f in d.evidence(baseline, g, rows))
    g = _sourced(candidate, URIRef("https://example.org/standard"),
                 [(p, o) for p, o in FULL if p != d.DSBP.accessDate] +
                 [(d.DSBP.accessDate, Literal("2026-11-27", datatype=rdflib.XSD.date))])
    assert d.evidence(baseline, g, rows) == []


def test_v5_exempts_a_cited_iri_only_where_it_is_cited(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nMarathon,no,company,test\nMPC,yes,company,test\n", encoding="utf-8")
    none = tmp_path / "none.csv"
    s, src = URIRef(d.NEW_PROC + "DSBP-P-000001"), URIRef("https://www.marathonpetroleum.com/Investors/")
    g = rdflib.Graph()
    g.add((s, DCTERMS.source, src))
    g.add((src, DCTERMS.title, Literal("Investors")))
    g.add((src, RDF.type, URIRef("http://purl.org/dc/dcmitype/Text")))  # any statement about the source keeps it cited
    g.add((src, RDFS.comment, Literal("The investor page")))
    assert d.company_neutral(g, terms, none) == []
    g.add((s, RDFS.seeAlso, src))                                 # the same IRI, used outside the citation
    assert any("the IRI" in f for f in d.company_neutral(g, terms, none))
    g = rdflib.Graph()
    minted = URIRef("https://w3id.org/mpc/ontology/source/a-filing")
    g.add((s, DCTERMS.source, minted))                            # the predecessor's own name for a source
    assert any("w3id.org/mpc" in f for f in d.company_neutral(g, terms, none))


@pytest.mark.parametrize("model", [
    lambda g, x: g.add((x, RDF.type, SKOS.Concept)),
    lambda g, x: g.add((x, RDF.type, OWL.Class)),
    lambda g, x: g.add((x, RDF.type, OWL.Ontology)),
    lambda g, x: g.add((x, RDF.type, OWL.ObjectProperty)),
    lambda g, x: g.add((x, RDF.type, RDF.Property)),
    lambda g, x: g.add((x, SKOS.prefLabel, Literal("Investors", lang="en"))),
    lambda g, x: g.add((x, RDFS.subClassOf, OWL.Thing)),
])
def test_v5_does_not_exempt_an_iri_the_ontology_models_even_when_it_is_cited(tmp_path, model):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nMarathon,no,company,test\n", encoding="utf-8")
    none = tmp_path / "none.csv"
    s, x = URIRef(d.NEW_PROC + "DSBP-P-000001"), URIRef("https://example.org/marathon-investors")
    g = rdflib.Graph()
    g.add((s, DCTERMS.source, x))
    model(g, x)
    assert any("the IRI" in f for f in d.company_neutral(g, terms, none))


def test_v5_does_not_count_a_self_citation_as_a_source(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nMarathon,no,company,test\n", encoding="utf-8")
    none = tmp_path / "none.csv"
    x = URIRef("https://example.org/marathon-unit")
    g = rdflib.Graph()
    g.add((x, DCTERMS.source, x))
    g.add((x, DCTERMS.title, Literal("Marathon unit")))
    fails = d.company_neutral(g, terms, none)
    assert any("the IRI" in f for f in fails) and any("dcterms:title" in f for f in fails)


@pytest.mark.parametrize("iri", ["https://w3id.org/mpc", "https://w3id.org/mpc#marathon", "HTTP://W3ID.ORG/mpc?a=1",
                                 "ftp://w3id.org/ds-bp/x"])
def test_v5_and_v6_read_a_minted_iri_with_or_without_a_path(iri):
    assert d.MINTED.match(iri) and not d._is_url(iri)
    assert not d.MINTED.match("https://w3id.org/mpcx/") and d._is_url("https://example.org/mpc")


def test_v6_refuses_an_access_date_that_is_not_on_the_calendar(baseline, rows, candidate):
    facts = [(p, "2026-02-31" if p == d.DSBP.accessDate else o) for p, o in FULL]
    g = _sourced(candidate, URIRef("https://example.org/standard"), facts)
    assert any("access date" in f for f in d.evidence(baseline, g, rows))


def test_v3_compares_detached_blank_node_loops_and_skips_empty_ones(baseline, rows, candidate):
    def loop(g, text):
        a, b = rdflib.BNode(), rdflib.BNode()
        g.add((a, RDFS.seeAlso, b))
        g.add((b, RDFS.seeAlso, a))
        g.add((a, RDFS.comment, Literal(text)))
    base, cand = copy(baseline), copy(candidate)
    loop(base, "same")
    loop(cand, "same")
    assert d.only_approved_changed(base, cand, rows, set()) == []
    cand = copy(candidate)
    loop(cand, "edited")
    assert any("blank-nodes" in f for f in d.only_approved_changed(base, cand, rows, set()))
    cand = copy(candidate)
    note = URIRef("https://example.org/ignoredOnly")
    cand.add((rdflib.BNode(), note, Literal("x")))
    assert d.only_approved_changed(baseline, cand, rows, set(), frozenset({note})) == []


@pytest.mark.parametrize("labels", [("a", "b", "c"), ("z", "y", "a")])
def test_v3_reads_a_detached_loop_with_a_tail_as_one_group_whatever_its_labels(baseline, rows, candidate, labels):
    def loop_with_tail(g, names):
        a, b, c = (rdflib.BNode(n) for n in names)
        g.add((a, RDFS.seeAlso, b))
        g.add((b, RDFS.seeAlso, a))
        g.add((a, RDFS.seeAlso, c))
        g.add((c, RDFS.comment, Literal("x")))
    base, cand = copy(baseline), copy(candidate)
    loop_with_tail(base, ("m1", "m2", "m3"))
    loop_with_tail(cand, labels)
    assert d.only_approved_changed(base, cand, rows, set()) == []


def test_v3_skips_a_detached_loop_of_ignored_statements(baseline, rows, candidate):
    cand = copy(candidate)
    note = URIRef("https://example.org/ignoredOnly")
    a, b = rdflib.BNode(), rdflib.BNode()
    cand.add((a, note, b))
    cand.add((b, note, a))
    assert d.only_approved_changed(baseline, cand, rows, set(), frozenset({note})) == []


def test_v5_treats_a_minted_iri_in_any_scheme_as_minted(tmp_path):
    terms = tmp_path / "terms.csv"
    terms.write_text("term,case_sensitive,kind,why\nMPC,yes,company,test\n", encoding="utf-8")
    g = rdflib.Graph()
    g.add((URIRef(d.NEW_PROC + "DSBP-P-000001"), DCTERMS.source, URIRef("ftp://w3id.org/mpc/source/x")))
    assert any("w3id.org/mpc" in f for f in d.company_neutral(g, terms, tmp_path / "none.csv"))
