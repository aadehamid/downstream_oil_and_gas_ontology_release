"""Batch B3: build the candidate from the baseline and expected-changes.csv, by script, never by hand.

This only builds a graph in memory or a file you name. Nothing in the release is written until the decision owner
approves expected-changes.csv; until then the tests use it to show that check_expected.py passes a correct
candidate and fails a wrong one.

ID rule (DSBP-DEC-0031): every baseline process that lives on gets DSBP-P-<n>, numbered 1 to 707 in the sorted
order of its 1.2 IRI (an excluded concept keeps its number unused, so the numbers have gaps); each new concept
gets the next number after 707, in the file's order. Old codes (the IRI's local part
and skos:notation) go to the migration map only.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import rdflib
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, SKOS

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validation"))
import check_expected as ce  # noqa: E402
import dsbp_checks as d  # noqa: E402


def migration_rows(baseline: rdflib.Graph, expected: list[dict]) -> list[dict]:
    change = {r["baseline_id"]: r for r in expected if r["baseline_id"]}
    # Descendants change only when the moved concept's level changes; a move at the same level leaves them as they were.
    shifted = {d.OLD_PROC + x for r in expected if r["change"] == "move"
               and int(r["expected_level"]) != d.level(baseline, URIRef(d.OLD_PROC + r["baseline_id"]))
               for x in ce.descendants(baseline, r["baseline_id"])}
    rows = []
    for i, s in enumerate(sorted(d.processes(baseline), key=str), start=1):
        old = d.local_id(str(s))
        r = change.get(old, {})
        kind = r.get("change", "")
        if kind == "exclude":
            why = f"{r['decision']}: {r['draft_definition'] or r['evidence']}"
            rows.append({"baseline_iri": str(s), "new_iri": "", "status": "excluded", "note": why})
            continue
        status = {"rename": "relabeled", "deprecate": "deprecated", "move": "modified"}.get(kind, "retained")
        if str(s) in shifted and status == "retained":
            status = "modified"  # its level changes because an ancestor moves
        if (s, OWL.deprecated, Literal(True)) in baseline:
            status = "deprecated"
        note = f"notation {baseline.value(s, SKOS.notation)}" if baseline.value(s, SKOS.notation) else ""
        rows.append({"baseline_iri": str(s), "new_iri": f"{d.NEW_PROC}DSBP-P-{i:06d}", "status": status, "note": note})
    return rows


def build(baseline: rdflib.Graph, expected: list[dict]) -> tuple[rdflib.Graph, list[dict]]:
    rows = migration_rows(baseline, expected)
    m = {URIRef(r["baseline_iri"]): URIRef(r["new_iri"]) for r in rows if r["new_iri"]}
    gone = {URIRef(r["baseline_iri"]) for r in rows if not r["new_iri"]}
    g = rdflib.Graph()
    for s, p, o in baseline:
        if s in gone or o in gone or (s in m and p == SKOS.notation):
            continue
        g.add((m.get(s, s), p, m.get(o, o)))
    nxt = len(rows) + 1
    new_nodes = {}
    new_rows = []
    for r in expected:
        if r["change"] == "new":
            n = URIRef(f"{d.NEW_PROC}DSBP-P-{nxt:06d}")
            nxt += 1
            new_nodes[r["key"]] = n
            g.add((n, RDF.type, SKOS.Concept))
            g.add((n, SKOS.prefLabel, Literal(r["new_label"], lang="en")))
            g.add((n, SKOS.definition, Literal(r["draft_definition"], lang="en")))
            g.add((n, d.CORE.taxonomyLevel, Literal(int(r["expected_level"]))))
            new_rows.append((n, r))
    resolve = lambda ref: ce._resolve(ref, {str(k): str(v) for k, v in m.items()}, new_nodes)  # noqa: E731
    # A map note names a replacement by its new ID and label, not by the file's working key (NEW:it).
    labels = {r["key"]: r["new_label"] for r in expected if r["change"] == "new"}
    for row in rows:
        row["note"] = re.sub(r"NEW:[\w-]+", lambda k: f"{d.local_id(str(new_nodes[k.group(0)]))} ({labels[k.group(0)]})",
                             row["note"])
    for r in expected:
        node = new_nodes.get(r["key"]) if r["change"] == "new" else resolve(r["baseline_id"])
        if r["change"] in ("new", "move") or (r["change"] == "rename" and r["new_parent"]):
            g.set((node, SKOS.broader, resolve(r["new_parent"])))
        if r["change"] == "rename":
            old_label = g.value(node, SKOS.prefLabel)
            g.add((node, d.CORE.priorPreferredLabel, old_label))
            g.set((node, SKOS.prefLabel, Literal(r["new_label"], lang="en")))
        if r["change"] == "deprecate":
            g.set((node, OWL.deprecated, Literal(True)))
            for key in re.findall(r"NEW:[\w-]+", r["draft_definition"]):
                g.add((node, DCTERMS.isReplacedBy, new_nodes[key]))
    # A new concept joins the scheme its parent is in, as every baseline concept is in one.
    for n, r in new_rows:
        parent = resolve(r["new_parent"])
        while parent is not None and g.value(parent, SKOS.inScheme) is None and parent in new_nodes.values():
            parent = g.value(parent, SKOS.broader)
        for scheme in (g.objects(parent, SKOS.inScheme) if parent is not None else []):
            g.add((n, SKOS.inScheme, scheme))
    # Levels follow the parents: recompute from the roots down.
    procs = d.processes(g)
    roots = [s for s in procs if g.value(s, SKOS.broader) is None]
    todo = [(r, 0) for r in roots]
    while todo:
        s, lv = todo.pop()
        g.set((s, d.CORE.taxonomyLevel, Literal(lv)))
        todo += [(c, lv + 1) for c in g.subjects(SKOS.broader, s) if c in procs]
    # The notation is the neutral ID, never the old code (DSBP-DEC-0031 and 0048; the ontology skill's
    # identity-taxonomy.md, Step 2, rule 2, for a build that generalizes a release).
    for s in procs:
        g.set((s, SKOS.notation, Literal(d.local_id(str(s)))))
    return g, rows


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="where to write the candidate (Turtle)")
    ap.add_argument("--map-out", type=Path, required=True, help="where to write the migration map (CSV)")
    a = ap.parse_args()
    g, rows = build(d.load(d.BASELINE_CORE), ce.read_expected())
    g.serialize(a.out, format="turtle")
    with a.map_out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["baseline_iri", "new_iri", "status", "note"])
        w.writeheader()
        w.writerows(rows)
