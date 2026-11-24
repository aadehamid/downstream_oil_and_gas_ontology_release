"""Release checks for DS_Business_Process, the company-agnostic successor of KPI Store 1.2's process ontology.

Each check takes the baseline (KPI Store 1.2, frozen) and a candidate (the new release) and returns a list of
failure messages; an empty list means the check passed. ``main`` runs them all and exits non-zero on any failure.

The checks and what each proves:

V1  baseline_untouched      every file listed in a KPI Store 1.2 release manifest still has its recorded SHA-256
V2  nothing_lost            every baseline process IRI has exactly one row in the migration map, with a known status
V3  only_approved_changed   a concept whose statements differ from the baseline is on the batch's approved list
V4  structure               no cycles; one parent below the top; level = parent level + 1; unique preferred labels;
                            a definition on every concept that is not deprecated; optional SHACL shapes conform
V5  company_neutral         no term from the company-terms register in a label, definition or note of the
                            reference layer, except in skos:example values
V6  evidence                every new or changed definition cites a public source with title, publisher, URL,
                            version or issue date, and access date
V7  relationships_kept      the baseline's process-to-process statements still hold, unless their subject is approved
V8  logic                   the candidate is consistent under the HermiT reasoner (needs Java and owlready2)

V9 (competency questions) is not built yet; see README.md.

Usage, from the repository root:

    uv run --with rdflib --with pyshacl --with owlready2 python ds_business_process/validation/dsbp_checks.py \\
        --candidate <candidate.ttl> --map <migration-map.csv> --approved <approved.txt> [--shapes <shapes.ttl>]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

import rdflib
from rdflib import RDF, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, SKOS

ROOT = Path(__file__).resolve().parents[2]
RELEASES = ROOT / "business_architecture" / "ontology" / "releases"
BASELINE_CORE = RELEASES / "core" / "2.4.0" / "core.ttl"
TERMS = Path(__file__).resolve().parents[1] / "registers" / "company-terms.csv"

OLD_PROC = "https://w3id.org/mpc/ontology/process/"
CORE = rdflib.Namespace("https://w3id.org/mpc/ontology/modules/core/")
DSBP = rdflib.Namespace("https://w3id.org/ds-bp/ontology/")
STATUSES = {"retained", "relabeled", "modified", "deprecated", "excluded"}
KEEPS_IRI = {"retained", "relabeled", "modified", "deprecated"}
# Literal-valued properties that carry reference-layer text a reader sees (V5).
TEXT_PROPS = [SKOS.prefLabel, SKOS.altLabel, SKOS.definition, SKOS.scopeNote, SKOS.note,
              SKOS.editorialNote, SKOS.changeNote, DCTERMS.provenance, CORE.primaryPurpose,
              CORE.keyInputFlow, CORE.primaryOutputFlow, CORE.plannedInput, CORE.plannedOutput]
# Sources that are evidence of the predecessor only, never public evidence (V6).
INTERNAL_SOURCE = re.compile(r"(step3c-definition-workbook|^urn:)")


def load(path: Path) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(path)
    return g


def local_id(iri: str) -> str:
    return iri.rstrip("/").rsplit("/", 1)[-1]


def processes(g: rdflib.Graph) -> set[URIRef]:
    """Concepts with a taxonomy level: the process hierarchy, under any namespace."""
    return {s for s in g.subjects(CORE.taxonomyLevel, None)} | {s for s in g.subjects(DSBP.taxonomyLevel, None)}


def level(g: rdflib.Graph, s: URIRef) -> int | None:
    v = g.value(s, CORE.taxonomyLevel)
    if v is None:  # not `or`: a level-0 Literal is falsy
        v = g.value(s, DSBP.taxonomyLevel)
    return int(v) if v is not None else None


def read_map(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def old_to_new(rows: list[dict]) -> dict[str, str]:
    return {r["baseline_iri"]: r["new_iri"] for r in rows if r.get("new_iri")}


def read_approved(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    return {local_id(x.strip()) for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.startswith("#")}


# V1 ---------------------------------------------------------------------------------------------------------------
def baseline_untouched(releases: Path = RELEASES) -> list[str]:
    fails = []
    manifests = sorted(releases.rglob("manifest.json"))
    if not manifests:
        return [f"V1: no release manifest found under {releases}"]
    for m in manifests:
        files = json.loads(m.read_text(encoding="utf-8")).get("files", {})
        for name, want in files.items():
            f = m.parent / name
            if not f.exists():
                fails.append(f"V1: {f.relative_to(releases)} is listed in its manifest and missing")
            elif hashlib.sha256(f.read_bytes()).hexdigest() != want:
                fails.append(f"V1: {f.relative_to(releases)} differs from its manifest hash")
    return fails


# V2 ---------------------------------------------------------------------------------------------------------------
def nothing_lost(baseline: rdflib.Graph, rows: list[dict]) -> list[str]:
    fails = []
    seen: dict[str, int] = {}
    for r in rows:
        seen[r["baseline_iri"]] = seen.get(r["baseline_iri"], 0) + 1
        if r["status"] not in STATUSES:
            fails.append(f"V2: {r['baseline_iri']} has unknown status {r['status']!r}")
        if r["status"] in KEEPS_IRI and local_id(r.get("new_iri", "")) != local_id(r["baseline_iri"]):
            fails.append(f"V2: {r['baseline_iri']} is {r['status']} but its new IRI changes the local ID")
        if r["status"] == "excluded" and not r.get("note", "").strip():
            fails.append(f"V2: {r['baseline_iri']} is excluded with no reason in the note column")
    for p in sorted(map(str, processes(baseline))):
        n = seen.get(p, 0)
        if n != 1:
            fails.append(f"V2: {p} has {n} rows in the migration map; it needs exactly one")
    extra = set(seen) - set(map(str, processes(baseline)))
    fails += [f"V2: map row {x} is not a baseline process" for x in sorted(extra)]
    return fails


# V3 ---------------------------------------------------------------------------------------------------------------
def _statements(g: rdflib.Graph, s: URIRef, mapping: dict[str, str]) -> set[tuple]:
    out = set()
    for p, o in g.predicate_objects(s):
        if isinstance(o, URIRef):
            o = URIRef(mapping.get(str(o), str(o)))
        out.add((p, o))
    return out


def only_approved_changed(baseline: rdflib.Graph, candidate: rdflib.Graph, rows: list[dict],
                          approved: set[str]) -> list[str]:
    mapping = old_to_new(rows)
    fails = []
    for r in rows:
        if r["status"] not in KEEPS_IRI:
            continue
        old, new = URIRef(r["baseline_iri"]), URIRef(r["new_iri"])
        before = _statements(baseline, old, mapping)
        after = _statements(candidate, new, {})
        if before != after and local_id(str(old)) not in approved:
            fails.append(f"V3: {local_id(str(old))} changed but is not on the approved list "
                         f"({len(before - after)} statements removed, {len(after - before)} added)")
    return fails


# V4 ---------------------------------------------------------------------------------------------------------------
def structure(candidate: rdflib.Graph, shapes: Path | None = None) -> list[str]:
    fails = []
    procs = processes(candidate)
    parents: dict[URIRef, list] = {s: list(candidate.objects(s, SKOS.broader)) for s in procs}
    for s, ps in parents.items():
        lv = level(candidate, s)
        if lv is not None and lv > 0 and len(ps) != 1:
            fails.append(f"V4: {local_id(str(s))} at level {lv} has {len(ps)} parents; it needs one")
        for p in ps:
            plv = level(candidate, p)
            if lv is not None and plv is not None and lv != plv + 1:
                fails.append(f"V4: {local_id(str(s))} is level {lv} under a level-{plv} parent")
    # Depth-first search over every parent link, not only the first, so a cycle hides behind no second parent.
    state: dict = {}  # absent: not visited; 1: on the current path; 2: done
    cyclic: set = set()
    for root in sorted(procs, key=str):
        if root in state:
            continue
        stack = [(root, iter(parents.get(root, [])))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
            elif state.get(nxt) == 1:
                cyclic.add(nxt)
            elif nxt not in state:
                state[nxt] = 1
                stack.append((nxt, iter(parents.get(nxt, []))))
    fails += [f"V4: the hierarchy has a cycle through {local_id(str(s))}" for s in sorted(cyclic, key=str)]
    labels: dict[str, list] = {}
    for s in procs:
        for lab in candidate.objects(s, SKOS.prefLabel):
            labels.setdefault(str(lab).casefold(), []).append(local_id(str(s)))
        deprecated = (s, OWL.deprecated, Literal(True)) in candidate
        if not deprecated and candidate.value(s, SKOS.definition) is None:
            fails.append(f"V4: {local_id(str(s))} has no definition")
    fails += [f"V4: preferred label {k!r} is shared by {', '.join(sorted(v))}"
              for k, v in labels.items() if len(v) > 1]
    if shapes is not None:
        import pyshacl
        ok, _, text = pyshacl.validate(candidate, shacl_graph=load(shapes), inference="none")
        if not ok:
            fails.append("V4: SHACL shapes do not conform:\n" + text[:2000])
    return fails


# V5 ---------------------------------------------------------------------------------------------------------------
def read_terms(path: Path = TERMS) -> list[tuple[str, re.Pattern]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        flags = 0 if r["case_sensitive"].strip().lower() == "yes" else re.IGNORECASE
        out.append((r["term"], re.compile(r"(?<![\w-])" + re.escape(r["term"]) + r"(?![\w-])", flags)))
    return out


def company_neutral(candidate: rdflib.Graph, terms_path: Path = TERMS) -> list[str]:
    terms = read_terms(terms_path)
    fails = []
    for s in sorted(processes(candidate), key=str):
        for prop in TEXT_PROPS:
            for o in candidate.objects(s, prop):
                for term, rx in terms:
                    if rx.search(str(o)):
                        fails.append(f"V5: {local_id(str(s))} {prop.n3(candidate.namespace_manager)} "
                                     f"contains {term!r}")
    return fails


# V6 ---------------------------------------------------------------------------------------------------------------
def _public(g: rdflib.Graph, src: URIRef) -> list[str]:
    missing = []
    url = g.value(src, DCTERMS.identifier) or (src if str(src).startswith("http") else None)
    if INTERNAL_SOURCE.search(str(src)):
        return ["a public source (this one is internal)"]
    if g.value(src, DCTERMS.title) is None:
        missing.append("title")
    if g.value(src, DCTERMS.publisher) is None:
        missing.append("publisher")
    if url is None or not str(url).startswith(("http://", "https://")):
        missing.append("URL")
    if g.value(src, DCTERMS.hasVersion) is None and g.value(src, DCTERMS.issued) is None:
        missing.append("version or issue date")
    if g.value(src, DSBP.accessDate) is None:
        missing.append("access date")
    return missing


def evidence(baseline: rdflib.Graph, candidate: rdflib.Graph, rows: list[dict]) -> list[str]:
    back = {r["new_iri"]: r["baseline_iri"] for r in rows if r.get("new_iri")}
    fails = []
    for s in sorted(processes(candidate), key=str):
        new_def = candidate.value(s, SKOS.definition)
        if new_def is None:
            continue
        old = back.get(str(s))
        if old is not None and baseline.value(URIRef(old), SKOS.definition) == new_def:
            continue  # definition unchanged: the predecessor's provenance stands
        problems = [(src, _public(candidate, src)) for src in candidate.objects(s, DCTERMS.source)]
        if not any(not miss for _, miss in problems):
            detail = "; ".join(f"{local_id(str(src))} lacks {', '.join(m)}" for src, m in problems) or "no source"
            fails.append(f"V6: {local_id(str(s))} has a new or changed definition without a complete public "
                         f"source ({detail})")
    return fails


# V7 ---------------------------------------------------------------------------------------------------------------
def relationships_kept(baseline: rdflib.Graph, candidate: rdflib.Graph, rows: list[dict],
                       approved: set[str]) -> list[str]:
    mapping = old_to_new(rows)
    procs = processes(baseline)
    fails = []
    for s, p, o in baseline:
        if s in procs and o in procs and str(p).startswith(str(CORE)):
            if local_id(str(s)) in approved:
                continue
            ns, no = URIRef(mapping.get(str(s), "")), URIRef(mapping.get(str(o), ""))
            np_ = URIRef(str(p).replace(str(CORE), str(DSBP))) if (ns, p, no) not in candidate else p
            if (ns, p, no) not in candidate and (ns, np_, no) not in candidate:
                fails.append(f"V7: {local_id(str(s))} {local_id(str(p))} {local_id(str(o))} is gone")
    return fails


# V8 ---------------------------------------------------------------------------------------------------------------
def logic(candidate: rdflib.Graph) -> list[str]:
    try:
        import owlready2
    except ImportError:
        return ["V8: owlready2 is not installed, so the reasoner did not run"]
    with tempfile.TemporaryDirectory() as tmp:
        nt = Path(tmp) / "candidate.nt"
        candidate.serialize(nt, format="nt", encoding="utf-8")
        world = owlready2.World()
        onto = world.get_ontology(nt.as_uri()).load()
        try:
            with onto:
                owlready2.sync_reasoner_hermit(world, infer_property_values=False, debug=0)
        except owlready2.OwlReadyInconsistentOntologyError:
            return ["V8: the reasoner found the candidate inconsistent"]
        bad = list(world.inconsistent_classes())
        return [f"V8: class {c} is unsatisfiable" for c in bad]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--approved", type=Path)
    ap.add_argument("--shapes", type=Path)
    ap.add_argument("--baseline", type=Path, default=BASELINE_CORE)
    ap.add_argument("--skip", nargs="*", default=[], help="check IDs to skip, such as V8")
    a = ap.parse_args(argv)
    baseline, candidate, rows = load(a.baseline), load(a.candidate), read_map(a.map)
    approved = read_approved(a.approved)
    checks = {
        "V1": lambda: baseline_untouched(),
        "V2": lambda: nothing_lost(baseline, rows),
        "V3": lambda: only_approved_changed(baseline, candidate, rows, approved),
        "V4": lambda: structure(candidate, a.shapes),
        "V5": lambda: company_neutral(candidate),
        "V6": lambda: evidence(baseline, candidate, rows),
        "V7": lambda: relationships_kept(baseline, candidate, rows, approved),
        "V8": lambda: logic(candidate),
    }
    failed = 0
    for cid, fn in checks.items():
        if cid in a.skip:
            print(f"{cid}: skipped")
            continue
        fails = fn()
        print(f"{cid}: {'pass' if not fails else f'FAIL ({len(fails)})'}")
        for f in fails[:50]:
            print("   ", f)
        if len(fails) > 50:
            print(f"    ... and {len(fails) - 50} more")
        failed += bool(fails)
    print("V9: not built yet (competency questions)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
