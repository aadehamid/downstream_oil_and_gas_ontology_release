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
import shutil
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
    """Every baseline process retained under a new neutral ID (DSBP-DEC-0031)."""
    return [{"baseline_iri": str(s), "new_iri": f"{d.NEW_PROC}DSBP-P-{i:06d}", "status": "retained", "note": ""}
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
    assert d.baseline_untouched() == []


def test_identity_passes_v2_v3_v7(baseline, rows, candidate):
    assert d.nothing_lost(baseline, rows) == []
    assert d.only_approved_changed(baseline, candidate, rows, set()) == []
    assert d.relationships_kept(baseline, candidate, rows, set()) == []


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
    assert d.baseline_untouched(rel) == ["V1: core/2.4.0/core.ttl differs from its manifest hash"]


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
    g.add((s, SKOS.example, Literal("for example in XPIMS", lang="en")))
    assert d.company_neutral(g, terms) == []          # skos:example is allowed to name a product
    g.set((s, SKOS.prefLabel, Literal("Run XPIMS", lang="en")))
    assert len(d.company_neutral(g, terms)) == 1
    g.set((s, SKOS.prefLabel, Literal("Run XPIMS-based model", lang="en")))  # hyphen joins: not a whole word
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
    if shutil.which("java") is None:
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
    if shutil.which("java") is None:
        pytest.skip("HermiT needs Java")
    assert d.logic(baseline) == []


def test_cli_exits_non_zero_on_the_identity_candidate_because_of_v5(rows, candidate, tmp_path, capsys):
    m = tmp_path / "map.csv"
    with m.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["baseline_iri", "new_iri", "status", "note"])
        w.writeheader()
        w.writerows(rows)
    c = tmp_path / "candidate.ttl"
    candidate.serialize(c, format="turtle")
    assert d.main(["--candidate", str(c), "--map", str(m), "--skip", "V8"]) == 1
    out = capsys.readouterr().out
    assert "V5: FAIL" in out and "V2: pass" in out and "V3: pass" in out and "V7: pass" in out
