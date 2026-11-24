"""Batch B3 (structure and IDs): does a candidate make exactly the changes in expected-changes.csv?

Written before the change, under the validation-first rule (DSBP-DEC-0011). On the untouched baseline every
"intended change" test fails, because nothing has changed yet; ``test_check_expected.py`` shows that, and shows
each test failing on a candidate that gets one change wrong.

What it checks, for each row of expected-changes.csv:

rename      the concept's preferred label is the new label, and the old label is kept as a prior preferred label
move        the concept's parent is the new parent, and its level is the expected level
deprecate   the concept is owl:deprecated and dcterms:isReplacedBy names each replacement in the row's note
exclude     the concept is not in the candidate, and its migration-map row says excluded, with a reason
new         a concept with the new label exists under the new parent at the expected level, with a definition
unchanged   nothing to check here; the release checks cover it

And for the whole candidate (DSBP-DEC-0031): no process concept carries a skos:notation, every concept that lives
on has an ID of the form DSBP-P-000123, and the old codes appear only in the migration map.

The release checks V1 to V8 still run as well. ``approved_ids`` gives V3 the concepts this batch may change.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import rdflib
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, SKOS

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validation"))
import dsbp_checks as d  # noqa: E402

EXPECTED = Path(__file__).resolve().parent / "expected-changes.csv"
PRIOR = [d.CORE.priorPreferredLabel, d.DSBP.priorPreferredLabel]


def read_expected(path: Path = EXPECTED) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _by_label(g: rdflib.Graph) -> dict[str, URIRef]:
    return {str(o): s for s in d.processes(g) for o in g.objects(s, SKOS.prefLabel)}


def _resolve(ref: str, mapping: dict[str, str], new_nodes: dict[str, URIRef]) -> URIRef | None:
    if not ref:
        return None
    if ref.startswith("NEW:"):
        return new_nodes.get(ref)
    return URIRef(mapping.get(d.OLD_PROC + ref, d.OLD_PROC + ref))


def descendants(baseline: rdflib.Graph, local: str) -> set[str]:
    out, todo = set(), [URIRef(d.OLD_PROC + local)]
    while todo:
        x = todo.pop()
        for c in baseline.subjects(SKOS.broader, x):
            out.add(d.local_id(str(c)))
            todo.append(c)
    return out


def approved_ids(baseline: rdflib.Graph, expected: list[dict], candidate: rdflib.Graph | None = None) -> set[str]:
    """The baseline concepts this batch may change: each named row, the descendants of each move (their level
    changes), and each concept whose parent or child is named (its skos:broader or narrower link changes).
    With a candidate, also the new concepts the file names, found by their new label, so V3 lets them in and
    no other new concept."""
    ids = {r["baseline_id"] for r in expected if r["baseline_id"]}
    if candidate is not None:
        labels = _by_label(candidate)
        ids |= {d.local_id(str(labels[r["new_label"]])) for r in expected
                if r["change"] == "new" and r["new_label"] in labels}
    for r in expected:
        if r["change"] == "move":
            ids |= descendants(baseline, r["baseline_id"])
        if r["new_parent"] and not r["new_parent"].startswith("NEW:"):
            ids.add(r["new_parent"])
    for r in expected:
        old_parent = baseline.value(URIRef(d.OLD_PROC + r["baseline_id"]), SKOS.broader) if r["baseline_id"] else None
        if old_parent is not None:
            ids.add(d.local_id(str(old_parent)))
    return ids


def check(baseline: rdflib.Graph, candidate: rdflib.Graph, rows: list[dict],
          expected: list[dict] | None = None) -> list[str]:
    expected = read_expected() if expected is None else expected
    mapping = d.old_to_new(rows)
    status = {d.local_id(r["baseline_iri"]): r for r in rows}
    labels = _by_label(candidate)
    fails: list[str] = []

    new_nodes = {}
    for r in expected:
        if r["change"] == "new":
            node = labels.get(r["new_label"])
            if node is None:
                fails.append(f"B3: new concept {r['key']} {r['new_label']!r} is missing")
            else:
                new_nodes[r["key"]] = node

    for r in expected:
        what, old = r["change"], r["baseline_id"]
        name = old or r["key"]
        node = new_nodes.get(r["key"]) if what == "new" else _resolve(old, mapping, new_nodes)
        if what == "exclude":
            if node is not None and (node, None, None) in candidate:
                fails.append(f"B3: {old} should be excluded but is still in the candidate")
            row = status.get(old)
            if row is None or row["status"] != "excluded" or not row.get("note", "").strip():
                fails.append(f"B3: {old} needs a migration-map row with status excluded and a reason")
            continue
        if node is None or (node, None, None) not in candidate:
            if what != "new":
                fails.append(f"B3: {name} is missing from the candidate")
            continue
        if what in ("rename", "new") and str(candidate.value(node, SKOS.prefLabel)) != r["new_label"]:
            fails.append(f"B3: {name} should be labelled {r['new_label']!r}, "
                         f"not {str(candidate.value(node, SKOS.prefLabel))!r}")
        if what == "rename":
            before = baseline.value(URIRef(d.OLD_PROC + old), SKOS.prefLabel)
            if not any((node, p, before) in candidate for p in PRIOR):
                fails.append(f"B3: {old}'s old label {str(before)!r} is not kept as a prior preferred label")
        if what in ("move", "new", "rename") and r["new_parent"]:
            want = _resolve(r["new_parent"], mapping, new_nodes)
            got = candidate.value(node, SKOS.broader)
            if got != want:
                fails.append(f"B3: {name} should sit under {r['new_parent']}, not under "
                             f"{d.local_id(str(got)) if got else 'nothing'}")
        if what in ("move", "new", "rename") and r["expected_level"]:
            if d.level(candidate, node) != int(r["expected_level"]):
                fails.append(f"B3: {name} should be level {r['expected_level']}, not {d.level(candidate, node)}")
        if what == "new" and candidate.value(node, SKOS.definition) is None:
            fails.append(f"B3: new concept {name} has no definition")
        if what == "deprecate":
            if (node, OWL.deprecated, Literal(True)) not in candidate:
                fails.append(f"B3: {old} should be owl:deprecated")
            for key in re.findall(r"NEW:\w+", r["draft_definition"]):
                if (node, DCTERMS.isReplacedBy, new_nodes.get(key)) not in candidate:
                    fails.append(f"B3: {old} should be replaced by {key}")

    for s in d.processes(candidate):
        if candidate.value(s, SKOS.notation) is not None:
            fails.append(f"B3: {d.local_id(str(s))} still carries a notation; old codes live only in the map")
        if str(s).startswith(d.OLD_PROC):
            fails.append(f"B3: {d.local_id(str(s))} still has its 1.2 IRI")
    return fails


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, default=d.BASELINE_CORE)
    a = ap.parse_args()
    found = check(d.load(a.baseline), d.load(a.candidate), d.read_map(a.map))
    for f in found:
        print(f)
    print(f"B3: {'pass' if not found else f'FAIL ({len(found)})'}")
    sys.exit(1 if found else 0)
