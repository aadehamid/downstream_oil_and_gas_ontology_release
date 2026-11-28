"""Batch B5: definitions, scope notes and public sources, applied on top of batch B3, by script, never by hand.

B3's script builds the structure from 1.2 (DSBP-DEC-0045 and 0050); this script takes that result and applies
changes.csv, with the sources in sources.csv. It writes the working core, the migration map and the approved list
(DSBP-DEC-0053), and the tests fail when a committed file differs by one byte from a fresh run.

What a row of changes.csv does, by its `change`:
- rewrite, add: sets the definition (when the row has one) and the scope note, and cites the row's sources;
- scope, reciprocal: changes only the scope note, by `scope_mode` (replace it, or append a sentence);
- sources: changes only the sources, and appends to the scope note when the row has one;
- exclude: the concept leaves the release, with its reason in the migration map.
Every changed concept loses the predecessor's private workbook as a source (check V6 and DSBP-DEC-0002) and gets a
change note naming this batch's decision.
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import rdflib
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "validation"))
import dsbp_checks as d  # noqa: E402

DECISION = "DSBP-DEC-0053"
CHANGES = HERE / "changes.csv"
SOURCES = HERE / "sources.csv"
KINDS = {"rewrite", "add", "scope", "reciprocal", "sources", "exclude"}
MODES = {"replace", "append", "none"}


def _load_b3():
    """B3's script and check module, loaded by path, since both batches name their script build_candidate.py."""
    b3 = HERE.parent / "B3-structure"
    sys.path.insert(0, str(b3))
    spec = importlib.util.spec_from_file_location("b3_build_candidate", b3 / "build_candidate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, mod.ce


B3, CE = _load_b3()


def read_changes(path: Path = CHANGES) -> list[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for r in rows:
        if r["change"] not in KINDS or r["scope_mode"] not in MODES:
            raise ValueError(f"{r['id']}: unknown change {r['change']!r} or scope mode {r['scope_mode']!r}")
    return rows


def read_sources(path: Path = SOURCES) -> dict[str, dict]:
    return {r["key"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}


def source_keys(r: dict) -> list[str]:
    return [k.strip() for k in r["sources"].split(";") if k.strip()]


def issued(text: str) -> Literal:
    """An issue date, typed: a full date as xsd:date, a month (such as ISO 31000's 2018-02) as xsd:gYearMonth."""
    if len(text) == 7:
        return Literal(text, datatype=XSD.gYearMonth)
    return Literal(text, datatype=XSD.date)


def build_b3() -> tuple[rdflib.Graph, list[dict], set[str]]:
    baseline, expected = d.load(d.BASELINE_CORE), CE.read_expected()
    g, rows = B3.build(baseline, expected)
    return g, rows, CE.approved_ids(baseline, expected, g, rows)


def cite(g: rdflib.Graph, s: URIRef, src: dict) -> str:
    """Cites src on s, with the facts check V6 asks of a public source; returns the source's IRI for check V3."""
    iri = URIRef(src["url"])
    g.add((s, DCTERMS.source, iri))
    g.set((iri, RDF.type, DCTERMS.BibliographicResource))
    g.set((iri, DCTERMS.title, Literal(src["title"], lang="en")))
    g.set((iri, DCTERMS.publisher, Literal(src["publisher"], lang="en")))
    g.set((iri, DCTERMS.hasVersion, Literal(src["version"], lang="en")))
    if src["issued"]:
        g.set((iri, DCTERMS.issued, issued(src["issued"])))
    g.set((iri, d.DSBP.accessDate, Literal(src["access_date"], datatype=XSD.date)))
    return str(iri)


def apply(g: rdflib.Graph, rows: list[dict], changes: list[dict], sources: dict[str, dict]) -> set[str]:
    """Applies the changes to g and rows in place; returns the IDs this batch changes, in old local IDs (check V3)."""
    new_to_old = {r["new_iri"]: d.local_id(r["baseline_iri"]) for r in rows if r["new_iri"]}
    approved = set()
    for c in changes:
        s = URIRef(d.NEW_PROC + c["id"])
        if (s, RDF.type, SKOS.Concept) not in g:
            raise ValueError(f"{c['id']} is not a concept of the B3 core")
        if str(g.value(s, SKOS.prefLabel)) != c["label"]:
            raise ValueError(f"{c['id']} is {g.value(s, SKOS.prefLabel)!r} in the B3 core, not {c['label']!r}")
        approved.add(new_to_old.get(str(s), c["id"]))
        if c["change"] == "exclude":
            g.remove((s, None, None))
            g.remove((None, None, s))
            for r in rows:
                if r["new_iri"] == str(s):
                    r.update(new_iri="", status="excluded", note=f"{c['decision']}: {c['evidence']}")
            continue
        if c["definition"]:
            g.set((s, SKOS.definition, Literal(c["definition"], lang="en")))
        if c["scope_mode"] == "replace":
            g.remove((s, SKOS.scopeNote, None))
            g.add((s, SKOS.scopeNote, Literal(c["scope_note"], lang="en")))
        elif c["scope_mode"] == "append" and c["scope_note"]:
            g.add((s, SKOS.scopeNote, Literal(c["scope_note"], lang="en")))
        for src in list(g.objects(s, DCTERMS.source)):
            if d.INTERNAL_SOURCE.search(str(src)):
                g.remove((s, DCTERMS.source, src))
        for key in source_keys(c):
            approved.add(cite(g, s, sources[key]))
        g.add((s, SKOS.changeNote, Literal(f"Revised by batch B5 under {DECISION} ({c['decision']}).", lang="en")))
    return approved


def declare_access_date(g: rdflib.Graph, sources: dict[str, dict]) -> set[str]:
    """Declares dsbp:accessDate, which Dublin Core lacks (validation/README.md), the first time a batch uses it.

    It is an annotation property, as Dublin Core's own terms are when an OWL file uses them: it says something about
    a cited source, not about the domain. That also keeps it out of the reasoner's sight (check V8). HermiT reasons
    only over the OWL 2 datatype map, which has no xsd:date, so a datatype property with that range stops it."""
    p = d.DSBP.accessDate
    g.add((p, RDF.type, OWL.AnnotationProperty))
    g.add((p, RDFS.label, Literal("access date", lang="en")))
    g.add((p, SKOS.definition, Literal("The day on which a cited source was last consulted and found to hold what "
                                       "it is cited for.", lang="en")))
    g.add((p, SKOS.scopeNote, Literal("ISO 690 calls it the date of citation. Dublin Core has no term for it, so "
                                      "this ontology defines one. Its value is an xsd:date, such as 2026-11-28 "
                                      "(check V6).", lang="en")))
    g.add((p, RDFS.isDefinedBy, URIRef(str(d.DSBP).rstrip("/"))))
    return {str(p), cite(g, p, sources["iso-690"])}


def build() -> tuple[rdflib.Graph, list[dict], set[str]]:
    g, rows, approved = build_b3()
    sources = read_sources()
    approved |= apply(g, rows, read_changes(), sources)
    approved |= declare_access_date(g, sources)
    return g, rows, approved


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="where to write the working core (Turtle)")
    ap.add_argument("--map-out", type=Path, required=True, help="where to write the migration map (CSV)")
    ap.add_argument("--approved-out", type=Path, required=True, help="where to write the approved list for check V3")
    a = ap.parse_args()
    g, rows, approved = build()
    g.serialize(a.out, format="turtle")
    with a.map_out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["baseline_iri", "new_iri", "status", "note"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    a.approved_out.write_text("".join(f"{x}\n" for x in sorted(approved)), encoding="utf-8", newline="\n")
