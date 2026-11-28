"""Tests for batch B5, written before the change (validation first, DSBP-DEC-0011).

* On B3's core, check V6 fails on the 8 new concepts and V4 on the 2 missing definitions; on the core this batch
  builds, checks V1 to V4, V6 and V7 pass. V5 (company terms) still fails, on 1.2's namespace and editorial text,
  and waits for its batches.
* A change row that names the wrong concept, an unknown source, or a source without its facts is refused.
* Every scope note this batch writes that names another process has a sentence naming it back, unless the two are
  parent and child (the quality bar, point 4).
* The taxonomy gate (DSBP-DEC-0045) holds: every check_taxonomy.py failure is one taxonomy-known.csv lists.
* The release files are what build_candidate.py writes, byte for byte (DSBP-DEC-0050). This batch's test takes
  that comparison over from B3's.
"""
from __future__ import annotations

import csv
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import rdflib
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "validation"))
import dsbp_checks as d  # noqa: E402

# Loaded by path: B3's folder also has a build_candidate.py, and B5's script puts B3's folder on sys.path.
_spec = importlib.util.spec_from_file_location("b5_build_candidate", HERE / "build_candidate.py")
b5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b5)

IGNORE = frozenset({SKOS.notation})


@pytest.fixture(scope="module")
def baseline():
    return d.load(d.BASELINE_CORE)


@pytest.fixture(scope="module")
def b3():
    return b5.build_b3()


@pytest.fixture(scope="module")
def built():
    return b5.build()


@pytest.fixture(scope="module")
def changes():
    return b5.read_changes()


@pytest.fixture(scope="module")
def sources():
    return b5.read_sources()


def copy(g):
    out = rdflib.Graph()
    for t in g:
        out.add(t)
    return out


def concept(cid: str) -> URIRef:
    return URIRef(d.NEW_PROC + cid)


# Before and after ---------------------------------------------------------------------------------------------------

def test_b3s_core_fails_v4_and_v6(baseline, b3):
    g, rows, _ = b3
    assert len(d.structure(g)) == 2
    assert len(d.evidence(baseline, g, rows)) == 8


def test_the_built_core_passes_the_release_checks(baseline, built):
    g, rows, approved = built
    assert d.baseline_untouched() == []
    assert d.nothing_lost(baseline, rows, g) == []
    assert d.only_approved_changed(baseline, g, rows, approved, IGNORE) == []
    assert d.structure(g) == []
    assert d.evidence(baseline, g, rows) == []
    assert d.relationships_kept(baseline, g, rows) == []


def test_every_changed_concept_has_a_change_note_and_no_internal_source(built, changes):
    g, _, _ = built
    for c in changes:
        if c["change"] == "exclude":
            continue
        s = concept(c["id"])
        assert any(b5.DECISION in str(n) and c["decision"] in str(n) for n in g.objects(s, SKOS.changeNote)), c["id"]
        assert not any(d.INTERNAL_SOURCE.search(str(x)) for x in g.objects(s, DCTERMS.source)), c["id"]


def test_the_excluded_concept_leaves_the_core_and_the_map_says_why(built, changes):
    g, rows, _ = built
    for c in (c for c in changes if c["change"] == "exclude"):
        s = concept(c["id"])
        assert (s, None, None) not in g and (None, None, s) not in g
        row = next(r for r in rows if r["status"] == "excluded" and c["decision"] in r["note"]
                   and c["evidence"] in r["note"])
        assert row["new_iri"] == ""


def test_v3_fails_when_a_concept_the_batch_does_not_list_changes(baseline, built):
    g, rows, approved = built
    g = copy(g)
    g.set((concept("DSBP-P-000003"), SKOS.definition, Literal("Edited.", lang="en")))
    assert any("not on the approved list" in f or "DSBP-P-000003" in f or "approved" in f
               for f in d.only_approved_changed(baseline, g, rows, approved, IGNORE))


def test_v6_fails_when_a_cited_source_loses_its_access_date(baseline, built, sources):
    g, rows, _ = built
    g = copy(g)
    g.remove((URIRef(sources["iso-31000"]["url"]), d.DSBP.accessDate, None))
    assert any("Enterprise" in f or "DSBP-P-000711" in f for f in d.evidence(baseline, g, rows))


# The change list and the source list --------------------------------------------------------------------------------

def test_a_row_with_the_wrong_label_is_refused(b3, changes, sources):
    g, rows, _ = b3
    bad = dict(changes[0], label="Not its label")
    with pytest.raises(ValueError, match="not 'Not its label'"):
        b5.apply(copy(g), [dict(r) for r in rows], [bad], sources)


def test_a_row_for_a_concept_b3_lacks_is_refused(b3, changes, sources):
    g, rows, _ = b3
    with pytest.raises(ValueError, match="not a concept"):
        b5.apply(copy(g), [dict(r) for r in rows], [dict(changes[0], id="DSBP-P-000999")], sources)


def test_an_unknown_change_kind_is_refused(tmp_path):
    path = tmp_path / "changes.csv"
    text = b5.CHANGES.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([text[0], text[1].replace(",rewrite,", ",retitle,", 1)]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown change"):
        b5.read_changes(path)


def test_every_source_key_is_listed_and_every_listed_source_is_cited(changes, sources):
    cited = {k for c in changes for k in b5.source_keys(c)} | {"iso-690"}  # iso-690: dsbp:accessDate's source
    assert cited == set(sources)


def test_every_source_has_the_facts_v6_asks_for(sources):
    for key, s in sources.items():
        assert s["url"].startswith("https://") and s["title"] and s["publisher"] and s["version"], key
        assert d._is_date(s["access_date"]), key
        assert not s["issued"] or re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", s["issued"]), key


def test_every_rewrite_or_add_has_a_definition_and_a_public_source(changes):
    for c in changes:
        if c["change"] in ("rewrite", "add"):
            assert c["definition"] and b5.source_keys(c), c["id"]
            assert c["decision"].startswith("DSBP-DEC-"), c["id"]


def test_the_access_date_property_is_an_annotation_property_with_no_range(built):
    # A datatype property with the range xsd:date stops the reasoner (check V8): xsd:date is not in the OWL 2
    # datatype map, and HermiT reasons over that map only.
    g, _, _ = built
    p = d.DSBP.accessDate
    assert (p, rdflib.RDF.type, rdflib.OWL.AnnotationProperty) in g
    assert (p, rdflib.RDFS.range, None) not in g and (p, rdflib.RDFS.domain, None) not in g
    assert g.value(p, SKOS.definition) is not None


def java_works() -> bool:
    if shutil.which("java") is None:
        return False
    try:
        return subprocess.run(["java", "-version"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def test_the_built_core_passes_v8(built):
    pytest.importorskip("owlready2")
    if not java_works():
        pytest.skip("HermiT needs Java")
    assert d.logic(built[0]) == []


# Reciprocal scope notes (quality bar, point 4) ----------------------------------------------------------------------

def named_processes(g: rdflib.Graph, text: str, own: URIRef) -> set[URIRef]:
    """The processes whose label the text names. A longer label wins over a shorter one inside it."""
    found = set()
    for label, s in sorted(((str(g.value(s, SKOS.prefLabel)), s) for s in d.processes(g)), key=lambda x: -len(x[0])):
        pattern = r"(?<![\w&])" + re.escape(label) + r"(?![\w]| &)"
        if re.search(pattern, text):
            text = re.sub(pattern, " ", text)
            if s != own:
                found.add(s)
    return found


def unreciprocated(g: rdflib.Graph, changes: list[dict]) -> list[str]:
    missing = []
    for c in changes:
        if c["change"] == "exclude" or not c["scope_note"]:
            continue
        s = concept(c["id"])
        for o in named_processes(g, c["scope_note"], s):
            if (s, SKOS.broader, o) in g or (o, SKOS.broader, s) in g:
                continue
            back = " ".join(str(x) for x in g.objects(o, SKOS.scopeNote))
            if c["label"] not in back:
                missing.append(f"{c['id']} names {d.local_id(str(o))}, whose scope note does not name it back")
    return missing


def test_every_scope_note_that_names_a_process_is_named_back(built, changes):
    assert unreciprocated(built[0], changes) == []


def test_the_reciprocal_check_catches_a_missing_sentence(built, changes):
    g = copy(built[0])
    refining = concept("DSBP-P-000684")
    for n in list(g.objects(refining, SKOS.scopeNote)):
        if "Lubricants & Specialties" in str(n):
            g.remove((refining, SKOS.scopeNote, n))
    assert len(unreciprocated(g, changes)) == 2


# The taxonomy gate (DSBP-DEC-0045) ----------------------------------------------------------------------------------

TAXONOMY = HERE.parents[2] / "skills" / "ontology" / "scripts" / "check_taxonomy.py"
KNOWN = HERE / "taxonomy-known.csv"
CODE_PROPERTIES = (str(d.CORE.evidenceRow), str(d.CORE.sourceRow), str(DCTERMS.identifier))


def taxonomy_failures(graph: rdflib.Graph, tmp_path) -> list[str]:
    path = tmp_path / "candidate.ttl"
    graph.serialize(path, format="turtle")
    out = subprocess.run([sys.executable, str(TAXONOMY), *(f"--code-property={c}" for c in CODE_PROPERTIES), str(path)],
                         capture_output=True, text=True)
    fails = [line[len("FAIL "):] for line in out.stdout.splitlines() if line.startswith("FAIL ")]
    assert out.returncode == (1 if fails else 0), out.stderr
    assert out.stderr.strip() == (f"{len(fails)} check(s) failed" if fails else ""), out.stderr
    return fails


def unlisted_taxonomy_failures(failures: list[str]) -> tuple[list[str], dict[str, int]]:
    known = list(csv.DictReader(KNOWN.open(encoding="utf-8")))
    counts = {row["id"]: 0 for row in known}
    unlisted = []
    for failure in failures:
        hits = [row["id"] for row in known if re.fullmatch(row["pattern"], failure)]
        if len(hits) == 1:
            counts[hits[0]] += 1
        else:
            unlisted.append(failure)
    return unlisted, {row["id"]: counts[row["id"]] for row in known if counts[row["id"]] != int(row["count"])}


def test_the_core_fails_check_taxonomy_only_where_listed(built, tmp_path):
    assert unlisted_taxonomy_failures(taxonomy_failures(built[0], tmp_path)) == ([], {})


def test_the_taxonomy_gate_catches_an_untagged_source_fact(built, sources, tmp_path):
    g = copy(built[0])
    iri = URIRef(sources["nist-csf-2"]["url"])
    g.set((iri, DCTERMS.publisher, Literal("National Institute of Standards and Technology")))
    unlisted, _ = unlisted_taxonomy_failures(taxonomy_failures(g, tmp_path))
    assert any(f.startswith("untagged:") and "csrc.nist.gov" in f for f in unlisted), unlisted


def test_every_known_taxonomy_failure_names_the_batch_that_fixes_it():
    for row in csv.DictReader(KNOWN.open(encoding="utf-8")):
        assert row["reason"] and row["fixed_by"], row["id"]


# The definition review ----------------------------------------------------------------------------------------------

def test_the_definition_review_covers_every_row(changes):
    review = (HERE / "definition-review.md").read_text(encoding="utf-8")
    reviewed = set(re.findall(r"^\| `(DSBP-P-\d{6})`", review, re.M))
    assert reviewed == {c["id"] for c in changes}


# The applied batch: the release files are what build_candidate.py writes, byte for byte (DSBP-DEC-0050) -----------

RELEASE = HERE.parents[1]
RELEASE_FILES = {"--out": RELEASE / "ontology" / "core" / "core.ttl",
                 "--map-out": RELEASE / "migration" / "core-process-map.csv",
                 "--approved-out": RELEASE / "migration" / "core-approved.txt"}


@pytest.fixture(scope="module")
def fresh_build(tmp_path_factory):
    out = tmp_path_factory.mktemp("fresh")
    paths = {flag: out / path.name for flag, path in RELEASE_FILES.items()}
    subprocess.run([sys.executable, str(HERE / "build_candidate.py"),
                    *[x for flag, path in paths.items() for x in (flag, str(path))]], check=True, cwd=HERE)
    return paths


@pytest.mark.parametrize("flag", sorted(RELEASE_FILES))
def test_the_release_file_is_what_the_script_writes(fresh_build, flag):
    assert RELEASE_FILES[flag].read_bytes() == fresh_build[flag].read_bytes()


def test_the_release_map_has_its_columns_and_unix_line_ends():
    data = RELEASE_FILES["--map-out"].read_bytes()
    assert data.splitlines()[0] == b"baseline_iri,new_iri,status,note"
    assert b"\r" not in data


def test_the_release_approved_list_is_the_batch_list(built):
    assert d.read_approved(RELEASE_FILES["--approved-out"]) == built[2]


def test_b3s_approved_list_is_gone():
    assert not (RELEASE / "migration" / "core-b3-approved.txt").exists()
