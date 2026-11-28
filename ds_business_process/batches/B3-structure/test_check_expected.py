"""Tests for batch B3, written before the change (validation first, DSBP-DEC-0011).

* On the baseline (renamed to new IDs, nothing else changed) the batch check fails: no intended change has happened.
* On the candidate that build_candidate.py makes, the batch check and the release checks V2, V3, V4 and V7 pass,
  except V4's two known missing definitions. V5 (company terms) and V6 (public sources on the 8 new definitions)
  are not run here: both still fail, and batches B4 and B5 fix them.
* The batch check fails on candidates that get exactly one change wrong.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

import pytest
import rdflib
import rdflib.compare
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, SKOS

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
    assert any("its one notation is its neutral ID" in f for f in fails)


def test_the_built_candidate_passes_the_batch_check(baseline, expected, built):
    g, rows = built
    assert ce.check(baseline, g, rows, expected) == []


def test_the_built_candidate_passes_the_release_checks(baseline, expected, built):
    g, rows = built
    approved = ce.approved_ids(baseline, expected, g, rows)
    assert d.nothing_lost(baseline, rows, g) == []
    assert d.only_approved_changed(baseline, g, rows, approved, frozenset({SKOS.notation})) == []
    assert d.relationships_kept(baseline, g, rows) == []
    assert sorted(d.structure(g)) == ["V4: DSBP-P-%06d has no definition" % i for i in sorted(
        int(d.local_id(r["new_iri"])[-6:]) for r in rows if d.local_id(r["baseline_iri"]) in
        ("CM-1-1-3-5-3", "CM-1-1-4-6-1"))]


def test_v3_fails_when_an_unlisted_concept_moves(baseline, expected, built):
    g, rows = built
    g = copy(g)
    stray = node(rows, "CM-1-3-1")
    g.set((stray, SKOS.broader, node(rows, "CM-1-2")))
    approved = ce.approved_ids(baseline, expected, g, rows)
    assert any("CM-1-3-1" in f for f in d.only_approved_changed(baseline, g, rows, approved,
                                                                 frozenset({SKOS.notation})))


@pytest.mark.parametrize("break_it, message", [
    (lambda g, rows: g.set((node(rows, "CM-1-1-4"), SKOS.broader, node(rows, "L1-refining"))), "CM-1-1-4 should sit under"),
    (lambda g, rows: g.set((node(rows, "CM-1-2"), SKOS.prefLabel, Literal("Supply And Trading", lang="en"))), "CM-1-2 should be labelled"),
    (lambda g, rows: g.remove((node(rows, "CM-1-2"), d.CORE.priorPreferredLabel, None)), "old label"),
    (lambda g, rows: g.add((URIRef(d.OLD_PROC + "CM-1-4"), SKOS.prefLabel, Literal("IT Services", lang="en"))),
     "CM-1-4 should be excluded"),
    (lambda g, rows: g.add((URIRef(d.OLD_PROC + "CM-1-1-4-6"), SKOS.prefLabel, Literal("Commercial Development", lang="en"))),
     "CM-1-1-4-6 should be excluded"),
    (lambda g, rows: g.add((node(rows, "CM-1-3-10"), SKOS.notation, Literal("CM 1.3.10"))), "its one notation is its neutral ID"),
    (lambda g, rows: g.remove((node(rows, "CM-1-3-10"), SKOS.notation, None)), "its one notation is its neutral ID"),
    (lambda g, rows: g.add((node(rows, "CM-1-3-10"), SKOS.notation, Literal(d.local_id(str(node(rows, "CM-1-3-10"))), lang="en"))),
     "its one notation is its neutral ID"),
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


def test_v3_fails_when_a_new_concept_the_file_does_not_name_appears(baseline, expected, built):
    g, rows = built
    g = copy(g)
    stray = URIRef(d.NEW_PROC + "DSBP-P-000999")
    g.add((stray, d.CORE.taxonomyLevel, Literal(1)))
    g.add((stray, SKOS.prefLabel, Literal("Unplanned area", lang="en")))
    approved = ce.approved_ids(baseline, expected, g, rows)
    fails = d.only_approved_changed(baseline, g, rows, approved, frozenset({SKOS.notation}))
    assert fails == ["V3: DSBP-P-000999 is a new concept but is not on the approved list"]


def test_a_baseline_concept_renamed_to_a_new_label_does_not_approve_itself(baseline, expected, built):
    g, rows = built
    g = copy(g)
    retail = next(s for s in d.processes(g) if str(g.value(s, SKOS.prefLabel)) == "Retail")
    g.remove((retail, None, None))
    g.remove((None, None, retail))
    stray = node(rows, "CM-1-3-1")
    g.set((stray, SKOS.prefLabel, Literal("Retail", lang="en")))
    approved = ce.approved_ids(baseline, expected, g, rows)
    assert d.local_id(str(stray)) not in approved
    assert any("CM-1-3-1" in f for f in d.only_approved_changed(baseline, g, rows, approved,
                                                                 frozenset({SKOS.notation})))


def test_one_new_row_approves_one_node_and_rows_are_required(baseline, expected, built):
    g, rows = built
    g = copy(g)
    twin = URIRef(d.NEW_PROC + "DSBP-P-000998")
    g.add((twin, d.CORE.taxonomyLevel, Literal(3)))
    g.add((twin, SKOS.prefLabel, Literal("Retail")))
    approved = ce.approved_ids(baseline, expected, g, rows)
    assert "DSBP-P-000998" not in approved
    assert sum("is a new concept but is not on the approved list" in f
               for f in d.only_approved_changed(baseline, g, rows, approved, frozenset({SKOS.notation}))) == 2
    with pytest.raises(ValueError):
        ce.approved_ids(baseline, expected, g)


def test_a_relabelled_baseline_concept_cannot_stand_in_for_a_new_one(baseline, expected, built):
    g, rows = built
    g = copy(g)
    it = next(s for s in d.processes(g) if str(g.value(s, SKOS.prefLabel)) == "Information Technology")
    g.remove((it, None, None))
    g.set((node(rows, "CM-1-3-1"), SKOS.prefLabel, Literal("Information Technology", lang="en")))
    assert any("new concept NEW:it" in f for f in ce.check(baseline, g, rows, expected))


# The file has no "unchanged" row now; this one, for a concept the batch does not touch, tests that kind of row.
UNCHANGED = {"key": "", "baseline_id": "CM-1-1-3", "change": "unchanged", "new_label": "", "new_parent": "CM-1-1",
             "expected_level": "3", "decision": "DSBP-DEC-0031", "evidence": "", "draft_definition": ""}


def test_an_unchanged_row_is_not_approved_for_v3(baseline, expected, built):
    g, rows = built
    assert "CM-1-1-3" not in ce.approved_ids(baseline, expected + [UNCHANGED], g, rows)
    assert ce.check(baseline, g, rows, expected + [UNCHANGED]) == []


@pytest.mark.parametrize("break_it, message", [
    (lambda g, rows: g.set((node(rows, "CM-1-1-3"), SKOS.prefLabel, Literal("Renamed", lang="en"))), "its label changed"),
    (lambda g, rows: g.set((node(rows, "CM-1-1-3"), SKOS.broader, node(rows, "CM-1-2"))), "its parent changed"),
    (lambda g, rows: g.add((node(rows, "CM-1-1-3"), OWL.deprecated, Literal(True))), "its deprecation changed"),
])
def test_the_batch_check_fails_when_an_unchanged_row_changes(baseline, expected, built, break_it, message):
    g, rows = built
    g = copy(g)
    break_it(g, rows)
    assert any(f"CM-1-1-3 is listed as unchanged but {message}" in f
               for f in ce.check(baseline, g, rows, expected + [UNCHANGED]))


def test_map_notes_name_replacements_by_new_id_not_by_working_key(built):
    g, rows = built
    notes = {d.local_id(r["baseline_iri"]): r["note"] for r in rows}
    assert not any("NEW:" in n for n in notes.values())
    it = next(s for s in d.processes(g) if str(g.value(s, SKOS.prefLabel)) == "Information Technology")
    assert f"{d.local_id(str(it))} (Information Technology)" in notes["L1-process-excellence-it"]
    assert "(Strategy & Business Development)" in notes["CM-1-1-4-6"]


def test_the_batch_check_fails_on_a_map_note_that_keeps_a_working_key(baseline, expected, built):
    g, rows = built
    rows = [dict(r) for r in rows]
    next(r for r in rows if r["baseline_iri"].endswith("L1-shared-services"))["note"] += " See NEW:risk-mgmt."
    assert any("still names the working key NEW:risk-mgmt" in f for f in ce.check(baseline, g, rows, expected))


def test_the_retired_commercial_development_is_excluded_not_deprecated(baseline, built):
    g, rows = built
    status = {d.local_id(r["baseline_iri"]): r for r in rows}
    assert status["CM-1-1-4-6"]["status"] == "excluded" and status["CM-1-1-4-6"]["new_iri"] == ""
    old = URIRef(d.OLD_PROC + "CM-1-1-4-6")
    assert (old, None, None) not in g and (None, None, old) not in g


def test_moved_concepts_and_their_descendants_are_modified_in_the_map(baseline, expected, built):
    _, rows = built
    status = {d.local_id(r["baseline_iri"]): r["status"] for r in rows}
    assert status["CM-1-1-4"] == "modified"
    assert all(status[x] in ("modified", "deprecated") for x in ce.descendants(baseline, "CM-1-1-4"))
    assert status["L1-process-excellence-it"] == "excluded"
    # A move at the same level (CM-1-3-10 stays L3) leaves its children as they were.
    kids = ce.descendants(baseline, "CM-1-3-10")
    assert kids and all(status[x] in ("retained", "deprecated") for x in kids)


def test_new_concepts_join_their_parents_scheme(baseline, expected, built):
    g, _ = built
    for s in d.processes(g):
        assert g.value(s, SKOS.inScheme) is not None, s


@pytest.mark.parametrize("parent", ["CM-1", "CM-1-3", "L0-downstream-operations", "L0-enabling-functions",
                                    "L1-refining", "MS-1-2"])
def test_v3_fails_when_an_unchanged_parent_is_edited(baseline, expected, built, parent):
    g, rows = built
    g = copy(g)
    g.set((node(rows, parent), SKOS.prefLabel, Literal("Edited", lang="en")))
    approved = ce.approved_ids(baseline, expected, g, rows)
    assert parent not in approved
    assert any(parent in f for f in d.only_approved_changed(baseline, g, rows, approved, frozenset({SKOS.notation})))


def test_same_level_move_descendants_are_not_approved(baseline, expected, built):
    g, rows = built
    kids = ce.descendants(baseline, "CM-1-3-10")
    assert kids and not (kids & ce.approved_ids(baseline, expected, g, rows))


# Step 3's gate (DSBP-DEC-0045): check_taxonomy.py runs on the candidate, and every failure it reports is one
# that taxonomy-known.csv lists, with the batch that fixes it, at exactly the count listed. A new failure, or
# a known one fixed without updating the file, fails this test.
TAXONOMY = HERE.parents[2] / "skills" / "ontology" / "scripts" / "check_taxonomy.py"
KNOWN = HERE / "taxonomy-known.csv"
CODE_PROPERTIES = (str(d.CORE.evidenceRow), str(d.CORE.sourceRow), str(DCTERMS.identifier))


def taxonomy_failures(graph: rdflib.Graph, tmp_path) -> list[str]:
    path = tmp_path / "candidate.ttl"
    graph.serialize(path, format="turtle")
    out = subprocess.run([sys.executable, str(TAXONOMY), *(f"--code-property={c}" for c in CODE_PROPERTIES), str(path)],
                         capture_output=True, text=True)
    fails = [line[len("FAIL "):] for line in out.stdout.splitlines() if line.startswith("FAIL ")]
    # A crash, or anything but the summary line on stderr, must not pass as a short list of failures.
    assert out.returncode == (1 if fails else 0), out.stderr
    assert out.stderr.strip() == (f"{len(fails)} check(s) failed" if fails else ""), out.stderr
    return fails


def unlisted_taxonomy_failures(failures: list[str]) -> tuple[list[str], dict[str, int]]:
    """The gate: each failure must match exactly one row of taxonomy-known.csv, and each row's count must hold."""
    known = list(csv.DictReader(KNOWN.open(encoding="utf-8")))
    counts = {row["id"]: 0 for row in known}
    unlisted = []
    for failure in failures:
        hits = [row["id"] for row in known if re.fullmatch(row["pattern"], failure)]
        if len(hits) == 1:
            counts[hits[0]] += 1
        else:
            unlisted.append(failure)
    wrong_counts = {row["id"]: counts[row["id"]] for row in known if counts[row["id"]] != int(row["count"])}
    return unlisted, wrong_counts


def test_the_candidate_fails_check_taxonomy_only_where_listed(built, tmp_path):
    assert unlisted_taxonomy_failures(taxonomy_failures(built[0], tmp_path)) == ([], {})


def test_every_known_taxonomy_failure_names_the_batch_that_fixes_it():
    for row in csv.DictReader(KNOWN.open(encoding="utf-8")):
        assert row["reason"] and row["fixed_by"], row["id"]


def test_the_taxonomy_gate_catches_a_new_failure(built, tmp_path):
    g = rdflib.Graph()
    for triple in built[0]:
        g.add(triple)
    some = next(s for s in sorted(d.processes(g)) if (s, SKOS.definition, None) in g)
    g.remove((some, SKOS.definition, None))
    unlisted, wrong_counts = unlisted_taxonomy_failures(taxonomy_failures(g, tmp_path))
    assert any(f.startswith("definition:") and d.local_id(str(some)) in f for f in unlisted), unlisted
    assert wrong_counts == {}


def test_the_taxonomy_gate_catches_a_changed_count(built, tmp_path):
    # Fixing a listed failure without updating taxonomy-known.csv changes its count, and the gate says so.
    g = rdflib.Graph()
    for triple in built[0]:
        g.add(triple)
    g.add((URIRef(d.NEW_PROC + "DSBP-P-000103"), SKOS.definition, rdflib.Literal("A placeholder definition.", lang="en")))
    unlisted, wrong_counts = unlisted_taxonomy_failures(taxonomy_failures(g, tmp_path))
    assert unlisted == [] and wrong_counts == {"TX-2": 1}


# Step 3's other gate (DSBP-DEC-0045): the definition review has one row for every concept B3 renames,
# moves or adds, named by its new ID.
REVIEW = HERE / "definition-review.md"


def test_the_definition_review_covers_every_changed_concept(built, expected):
    candidate, rows = built
    review = REVIEW.read_text(encoding="utf-8")
    reviewed = set(re.findall(r"^\| `(DSBP-P-\d{6})`", review, re.M))
    new_iri = {d.local_id(r["baseline_iri"]): r["new_iri"] for r in rows}
    labels = {str(o): s for s, o in candidate.subject_objects(SKOS.prefLabel)}
    changed = set()
    for r in expected:
        if r["change"] in ("rename", "move"):
            changed.add(d.local_id(new_iri[r["baseline_id"]]))
        elif r["change"] == "new":
            changed.add(d.local_id(str(labels[r["new_label"]])))
    assert changed and reviewed == changed



# The applied batch: the release files are what build_candidate.py makes, so they carry every check above -------

RELEASE = HERE.parents[1]
RELEASE_CORE = RELEASE / "ontology" / "core" / "core.ttl"
RELEASE_MAP = RELEASE / "migration" / "core-process-map.csv"
RELEASE_APPROVED = RELEASE / "migration" / "core-b3-approved.txt"


def test_the_release_core_is_the_built_candidate(built):
    g, _ = built
    assert rdflib.compare.isomorphic(d.load(RELEASE_CORE), g)


def test_the_release_map_is_the_built_map(built):
    _, rows = built
    with RELEASE_MAP.open(newline="", encoding="utf-8") as fh:
        assert list(csv.DictReader(fh)) == [{k: str(v) for k, v in r.items()} for r in rows]


def test_the_release_approved_list_is_the_batch_list(baseline, expected, built):
    g, rows = built
    assert d.read_approved(RELEASE_APPROVED) == ce.approved_ids(baseline, expected, g, rows)
