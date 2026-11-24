"""Tests for batch B3, written before the change (validation first, DSBP-DEC-0011).

* On the baseline (renamed to new IDs, nothing else changed) the batch check fails: no intended change has happened.
* On the candidate that build_candidate.py makes, the batch check and the release checks V2 to V7 pass, except the
  known ones: V4's two missing definitions and V5's company terms, which later batches remove.
* The batch check fails on candidates that get exactly one change wrong.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import rdflib
from rdflib import Literal, URIRef
from rdflib.namespace import OWL, SKOS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "validation"))
import build_candidate as bc  # noqa: E402
import check_expected as ce  # noqa: E402
import dsbp_checks as d  # noqa: E402


@pytest.fixture(scope="module")
def baseline():
    return d.load(d.BASELINE_CORE)


@pytest.fixture(scope="module")
def expected():
    return ce.read_expected()


@pytest.fixture(scope="module")
def built(baseline, expected):
    return bc.build(baseline, expected)


def copy(g):
    out = rdflib.Graph()
    for t in g:
        out.add(t)
    return out


def node(rows, old):
    return URIRef(next(r["new_iri"] for r in rows if r["baseline_iri"] == d.OLD_PROC + old))


def test_expected_file_names_only_real_concepts(baseline, expected):
    procs = {d.local_id(str(s)) for s in d.processes(baseline)}
    for r in expected:
        if r["baseline_id"]:
            assert r["baseline_id"] in procs, r
        if r["new_parent"] and not r["new_parent"].startswith("NEW:"):
            assert r["new_parent"] in procs, r
        assert r["decision"].startswith("DSBP-DEC-"), r


def test_the_baseline_fails_the_batch_check(baseline, expected):
    rows = bc.migration_rows(baseline, [])  # new IDs, no other change
    m = {URIRef(r["baseline_iri"]): URIRef(r["new_iri"]) for r in rows}
    renamed = rdflib.Graph()
    for s, p, o in baseline:
        renamed.add((m.get(s, s), p, m.get(o, o)))
    fails = ce.check(baseline, renamed, rows, expected)
    assert any("new concept NEW:it" in f for f in fails)
    assert any("CM-1-1-4 should sit under CM-1-1" in f for f in fails)
    assert any("still carries a notation" in f for f in fails)


def test_the_built_candidate_passes_the_batch_check(baseline, expected, built):
    g, rows = built
    assert ce.check(baseline, g, rows, expected) == []


def test_the_built_candidate_passes_the_release_checks(baseline, expected, built):
    g, rows = built
    approved = ce.approved_ids(baseline, expected)
    assert d.nothing_lost(baseline, rows) == []
    assert d.only_approved_changed(baseline, g, rows, approved, frozenset({SKOS.notation})) == []
    assert d.relationships_kept(baseline, g, rows, approved) == []
    assert sorted(d.structure(g)) == ["V4: DSBP-P-%06d has no definition" % i for i in sorted(
        int(d.local_id(r["new_iri"])[-6:]) for r in rows if d.local_id(r["baseline_iri"]) in
        ("CM-1-1-3-5-3", "CM-1-1-4-6-1"))]


def test_v3_fails_when_an_unlisted_concept_moves(baseline, expected, built):
    g, rows = built
    g = copy(g)
    stray = node(rows, "CM-1-3-1")
    g.set((stray, SKOS.broader, node(rows, "CM-1-2")))
    approved = ce.approved_ids(baseline, expected)
    assert any("CM-1-3-1" in f for f in d.only_approved_changed(baseline, g, rows, approved,
                                                                 frozenset({SKOS.notation})))


@pytest.mark.parametrize("break_it, message", [
    (lambda g, rows: g.set((node(rows, "CM-1-1-4"), SKOS.broader, node(rows, "L1-refining"))), "CM-1-1-4 should sit under"),
    (lambda g, rows: g.set((node(rows, "CM-1-2"), SKOS.prefLabel, Literal("Supply And Trading", lang="en"))), "CM-1-2 should be labelled"),
    (lambda g, rows: g.remove((node(rows, "CM-1-2"), d.CORE.priorPreferredLabel, None)), "old label"),
    (lambda g, rows: g.remove((node(rows, "CM-1-4"), OWL.deprecated, None)), "CM-1-4 should be owl:deprecated"),
    (lambda g, rows: g.add((node(rows, "CM-1-3-10"), SKOS.notation, Literal("CM 1.3.10"))), "still carries a notation"),
    (lambda g, rows: g.set((node(rows, "CM-1-1-4-6-3"), d.CORE.taxonomyLevel, Literal(3))), "should be level 2"),
])
def test_the_batch_check_fails_on_one_wrong_change(baseline, expected, built, break_it, message):
    g, rows = built
    g = copy(g)
    break_it(g, rows)
    assert any(message in f for f in ce.check(baseline, g, rows, expected))


def test_the_batch_check_fails_when_a_new_concept_is_missing(baseline, expected, built):
    g, rows = built
    g = copy(g)
    retail = next(s for s in d.processes(g) if str(g.value(s, SKOS.prefLabel)) == "Retail")
    g.remove((retail, None, None))
    assert any("NEW:retail" in f for f in ce.check(baseline, g, rows, expected))


def test_the_batch_check_fails_when_the_exclusion_is_not_in_the_map(baseline, expected, built):
    g, rows = built
    rows = [dict(r) for r in rows]
    r = next(r for r in rows if r["baseline_iri"].endswith("L1-shared-services"))
    r["note"] = ""
    assert any("L1-shared-services needs a migration-map row" in f for f in ce.check(baseline, g, rows, expected))
