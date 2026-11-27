"""Release checks for DS_Business_Process, the company-agnostic successor of KPI Store 1.2's process ontology.

Each check takes the baseline (KPI Store 1.2, frozen) and a candidate (the new release) and returns a list of
failure messages; an empty list means the check passed. ``main`` runs them all and exits non-zero on any failure.

The checks and what each proves:

V1  baseline_untouched      every KPI Store 1.2 release manifest in the recorded list is present and unchanged, and
                            every file it lists still has its recorded SHA-256
V2  nothing_lost            every baseline process IRI has exactly one row in the migration map, with a known status;
                            each living concept has its own neutral new ID (DSBP-P-000123) and is in the candidate,
                            and its old IRI is gone; a deprecated row is owl:deprecated in the candidate and no other
                            row is; an excluded concept has no new IRI and is gone from the candidate
V3  only_approved_changed   a concept that differs from the baseline, is excluded, or is new, is on the approved list;
                            so is any other subject (a class, a property, the ontology header) whose statements differ;
                            a blank node is compared by its content and count, so a change inside one counts, and
                            blank nodes that nothing points at are compared together
V4  structure               no cycles; one parent below the top, and that parent is a process; one level, an integer,
                            not negative, = parent level + 1; skos:narrower, where given, is the inverse of
                            skos:broader; on every concept one preferred label per language, none blank, and no other
                            concept with the same label; one non-blank definition on every concept that is not
                            deprecated; optional SHACL shapes conform
V5  company_neutral         no term from the company-terms register in any literal of the candidate, on any subject
                            and any property, nor in any IRI, in any letter case and split at marks and case changes;
                            skos:example may name a company, never a company-built system; a phrase in the
                            allowed-terms register (a generic meaning of the same letters) is not a hit; a cited
                            source's own IRI, URL, title, description and publisher may name a company; no literal
                            carries the predecessor's parked-tree-change codes (PTC-001), and none outside a cited
                            source's record or an example carries a working file name (notes.md, plan.xlsx)
V6  evidence                every new or changed definition, on any subject, cites a public source with title,
                            publisher, URL, version or issue date, and access date, none of them blank, and cites no
                            internal source beside it. The access date is dsbp:accessDate, written as a date
                            (2026-11-27): Dublin Core has no term for the day a source was read (README.md, "How a
                            source is recorded")
V7  relationships_kept      the baseline's process-to-process statements (core properties, skos:related) still hold,
                            unless one end is excluded or the batch lists the statement as an approved removal
V8  logic                   the candidate, without its owl:imports, is consistent under the HermiT reasoner (needs Java
                            and owlready2)
V9  competency questions    not built yet; see README.md. It counts as a failure until it is built, unless skipped.

Usage, from the repository root:

    uv run --with rdflib --with pyshacl --with owlready2 python ds_business_process/validation/dsbp_checks.py \\
        --candidate <candidate.ttl> --map <migration-map.csv> --approved <approved.txt> [--shapes <shapes.ttl>] \\
        [--removals <removals.txt>] [--ignore skos:notation ...]
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

import rdflib
from rdflib import RDF, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDFS, SKOS, XSD

ROOT = Path(__file__).resolve().parents[2]
RELEASES = ROOT / "business_architecture" / "ontology" / "releases"
BASELINE_CORE = RELEASES / "core" / "2.4.0" / "core.ttl"
TERMS = Path(__file__).resolve().parents[1] / "registers" / "company-terms.csv"
ALLOWED = Path(__file__).resolve().parents[1] / "registers" / "company-terms-allowed.csv"
MANIFESTS = Path(__file__).resolve().parents[1] / "registers" / "baseline-manifests.csv"

OLD_PROC = "https://w3id.org/mpc/ontology/process/"
CORE = rdflib.Namespace("https://w3id.org/mpc/ontology/modules/core/")
DSBP = rdflib.Namespace("https://w3id.org/ds-bp/ontology/")
STATUSES = {"retained", "relabeled", "modified", "deprecated", "excluded"}
KEEPS_IRI = {"retained", "relabeled", "modified", "deprecated"}  # statuses whose concept lives on under a new IRI
NEW_PROC = str(DSBP) + "process/"
NEW_ID = re.compile(r"DSBP-P-\d{6}")  # neutral IDs that say nothing about place (DSBP-DEC-0031)
# Sources that are evidence of the predecessor only, never public evidence (V6). A `urn:` source IRI is one this
# project or its predecessor named without a place to find it; an identifier may still be a URN, such as an ISBN.
INTERNAL_SOURCE = re.compile(r"step3c-definition-workbook", re.IGNORECASE)
INTERNAL_IRI = re.compile(r"^urn:", re.IGNORECASE)
# IRIs this project or its predecessor minted: they name a source, but they are not where a reader can find it (V6).
MINTED = ("https://w3id.org/ds-bp/", "https://w3id.org/mpc/")
NEW_IRI = re.compile(re.escape(NEW_PROC) + r"DSBP-P-\d{6}")
# The predecessor's working trace, which a reader outside it cannot follow (V5): its parked-tree-change codes, which
# are never public, and the names of its working files. A public document's file name may stand on its source record
# and in an example; a web address is not read as a file name, so a site in .md or .py is not a hit.
TRACE_CODE = re.compile(r"(?<![A-Za-z0-9])PTC-\d+(?:-[A-Z]+)?(?![A-Za-z0-9])", re.IGNORECASE)
TRACE_FILE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]+\.(?:md|xlsx|xlsm|csv|json|py|ipynb|docx|pptx)(?![A-Za-z0-9])",
                        re.IGNORECASE)
WEB_ADDRESS = re.compile(r"\b(?:https?|ftp)://\S+", re.IGNORECASE)
INTEGER_TYPES = {XSD.integer, XSD.int, XSD.long, XSD.short, XSD.nonNegativeInteger, XSD.positiveInteger,
                 XSD.unsignedInt, XSD.unsignedLong, XSD.unsignedShort}
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def load(path: Path) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(path)
    return g


def local_id(iri: str) -> str:
    """The last segment of an IRI, after its last `/` or `#`: `CM-1-1`, `related`."""
    return re.split(r"[/#]", iri.rstrip("/"))[-1]


def processes(g: rdflib.Graph) -> set[URIRef]:
    """Concepts with a taxonomy level: the process hierarchy, under any namespace."""
    return {s for s in g.subjects(CORE.taxonomyLevel, None)} | {s for s in g.subjects(DSBP.taxonomyLevel, None)}


def _levels(g: rdflib.Graph, s) -> set:
    return set(g.objects(s, CORE.taxonomyLevel)) | set(g.objects(s, DSBP.taxonomyLevel))


def level(g: rdflib.Graph, s: URIRef) -> int | None:
    """The concept's one level, or None when it has none, more than one, or one that is not a whole number (V4
    reports the last two), so no check reads an arbitrary one of several."""
    values = _levels(g, s)
    whole = {_whole(v) for v in values}
    return whole.pop() if len(whole) == 1 and None not in whole else None


def _whole(v) -> int | None:
    """A level as a whole number: an integer-typed literal whose text is digits, such as 3 in Turtle. Anything else
    (a string "3", a boolean, "3_0", a blank node) is not one."""
    if not isinstance(v, Literal) or v.datatype not in INTEGER_TYPES or not re.fullmatch(r"[+-]?\d+", str(v)):
        return None
    return int(str(v))


def read_map(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def old_to_new(rows: list[dict]) -> dict[str, str]:
    return {r["baseline_iri"]: r["new_iri"] for r in rows if r.get("new_iri")}


def read_approved(path: Path | None) -> set[str]:
    """No path means nothing is approved. A path that does not exist is an error, not an empty list: a mistyped
    name must not turn the check into one that passes everything or nothing by surprise."""
    if path is None:
        return set()
    if not path.exists():
        raise FileNotFoundError(f"approved list {path} does not exist")
    return {local_id(x.strip()) for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")}


# V1 ---------------------------------------------------------------------------------------------------------------
def read_manifest_list(path: Path = MANIFESTS) -> dict[str, str]:
    """The baseline's manifests, by path under the releases folder, with each manifest's own SHA-256."""
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["manifest"]: r["sha256"] for r in csv.DictReader(fh)}


def baseline_untouched(releases: Path = RELEASES, listed: dict[str, str] | None = None) -> list[str]:
    """``listed`` is the recorded set of manifests; a manifest deleted or edited fails, not only a file one lists."""
    fails = []
    listed = read_manifest_list() if listed is None else listed
    manifests = sorted(releases.rglob("manifest.json"))
    if not manifests:
        return [f"V1: no release manifest found under {releases}"]
    for name, want in sorted(listed.items()):
        m = releases / name
        if not m.exists():
            fails.append(f"V1: manifest {name} is in the recorded list and missing")
        elif hashlib.sha256(m.read_bytes()).hexdigest() != want:
            fails.append(f"V1: manifest {name} differs from its recorded hash")
    for m in manifests:
        try:
            files = json.loads(m.read_text(encoding="utf-8")).get("files", {})
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
            fails.append(f"V1: {m.relative_to(releases).as_posix()} is not a readable manifest ({type(e).__name__})")
            continue
        if not isinstance(files, dict):
            fails.append(f"V1: {m.relative_to(releases).as_posix()} is not a readable manifest (files is not a map)")
            continue
        for name, want in files.items():
            f = m.parent / name
            if not f.exists():
                fails.append(f"V1: {f.relative_to(releases).as_posix()} is listed in its manifest and missing")
            elif hashlib.sha256(f.read_bytes()).hexdigest() != want:
                fails.append(f"V1: {f.relative_to(releases).as_posix()} differs from its manifest hash")
    return fails


# V2 ---------------------------------------------------------------------------------------------------------------
def nothing_lost(baseline: rdflib.Graph, rows: list[dict], candidate: rdflib.Graph | None = None) -> list[str]:
    """With a candidate, also checks that each living concept is a process in it (it has a level), and that an
    excluded one appears nowhere in it, as subject or as object."""
    fails = []
    procs_c = processes(candidate) if candidate is not None else set()
    seen: dict[str, int] = {}
    news: dict[str, int] = {}
    for r in rows:
        seen[r["baseline_iri"]] = seen.get(r["baseline_iri"], 0) + 1
        if r["status"] not in STATUSES:
            fails.append(f"V2: {r['baseline_iri']} has unknown status {r['status']!r}")
        if r["status"] in KEEPS_IRI:
            new = r.get("new_iri", "")
            if not NEW_IRI.fullmatch(new):
                fails.append(f"V2: {r['baseline_iri']} is {r['status']} but its new IRI {new!r} is not a "
                             f"neutral ID of the form {NEW_PROC}DSBP-P-000123 (DSBP-DEC-0031)")
            news[new] = news.get(new, 0) + 1
            if candidate is not None and URIRef(new) not in procs_c:
                fails.append(f"V2: {r['baseline_iri']} is {r['status']} but its new IRI {local_id(new)} "
                             f"is not a process in the candidate")
            old = URIRef(r["baseline_iri"])
            if candidate is not None and ((old, None, None) in candidate or (None, None, old) in candidate):
                fails.append(f"V2: {r['baseline_iri']} has the new IRI {local_id(new)} but the old IRI is "
                             f"still in the candidate")
            if candidate is not None and URIRef(new) in procs_c:
                dep = (URIRef(new), OWL.deprecated, Literal(True)) in candidate
                if dep != (r["status"] == "deprecated"):
                    fails.append(f"V2: {local_id(new)} is {r['status']} in the map but "
                                 f"{'is' if dep else 'is not'} owl:deprecated in the candidate")
        if r["status"] == "excluded":
            if not r.get("note", "").strip():
                fails.append(f"V2: {r['baseline_iri']} is excluded with no reason in the note column")
            if r.get("new_iri", "").strip():
                fails.append(f"V2: {r['baseline_iri']} is excluded but still has a new IRI")
            old = URIRef(r["baseline_iri"])
            if candidate is not None and ((old, None, None) in candidate or (None, None, old) in candidate):
                fails.append(f"V2: {r['baseline_iri']} is excluded but is still in the candidate")
    for p in sorted(map(str, processes(baseline))):
        n = seen.get(p, 0)
        if n != 1:
            fails.append(f"V2: {p} has {n} rows in the migration map; it needs exactly one")
    fails += [f"V2: new IRI {x} is given to {n} baseline processes; each needs its own"
              for x, n in sorted(news.items()) if n > 1]
    extra = set(seen) - set(map(str, processes(baseline)))
    fails += [f"V2: map row {x} is not a baseline process" for x in sorted(extra)]
    return fails


# V3 ---------------------------------------------------------------------------------------------------------------
def _same_predicate(p: URIRef) -> URIRef:
    """A module property moved from the old namespace to the new one is the same property for V3 and V7."""
    return URIRef(str(p).replace(str(CORE), str(DSBP), 1)) if str(p).startswith(str(CORE)) else p


def _statements(g: rdflib.Graph, s, mapping: dict[str, str], ignore: frozenset = frozenset(),
                _path: tuple = ()) -> set[tuple]:
    """A subject's statements, comparable across two graphs: module IRIs move to the new namespace, mapped IRIs to
    their new ones, and a blank-node object becomes its own statements, since its label differs between graphs.
    Two blank nodes with the same content on one property count twice (each statement carries its count), and a
    loop back to a blank node on the path is written as how many steps back it goes."""
    counts: dict[tuple, int] = {}
    ignore = frozenset(map(_same_predicate, ignore))
    path = _path + (s,)
    for p, o in g.predicate_objects(s):
        p = _same_predicate(p)
        if p in ignore:
            continue
        if isinstance(o, URIRef):
            o = _same_predicate(URIRef(mapping.get(str(o), str(o))))
        elif isinstance(o, rdflib.BNode):
            o = (("_:cycle", len(path) - path.index(o)) if o in path
                 else ("_:", frozenset(_statements(g, o, mapping, ignore, path))))
        counts[(p, o)] = counts.get((p, o), 0) + 1
    return {(p, o) if n == 1 else (p, o, n) for (p, o), n in counts.items()}


UNREFERENCED = URIRef("urn:dsbp:v3:blank-nodes-no-named-subject-points-at")


def _others(g: rdflib.Graph, mapping: dict[str, str], ignore: frozenset) -> dict[URIRef, set]:
    """The statements of every named subject that is not a process, with module IRIs moved to the new namespace.
    A blank node is compared through the subject that points at it. Blank nodes that nothing points at, such as an
    owl:AllDisjointClasses axiom, are compared together, by content and count, under one placeholder subject."""
    procs = processes(g)
    out: dict[URIRef, set] = {}
    for s in set(g.subjects()):
        if not isinstance(s, URIRef) or s in procs or str(s) in mapping:
            continue
        stmts = _statements(g, s, mapping, ignore)
        if stmts:
            out[_same_predicate(s)] = stmts
    # Blank nodes no named subject reaches: those nothing points at, and one node of each detached loop.
    reached, todo = set(), [o for s in g.subjects() if isinstance(s, URIRef) for o in g.objects(s, None)
                            if isinstance(o, rdflib.BNode)]
    while todo:
        b = todo.pop()
        if b not in reached:
            reached.add(b)
            todo += [o for o in g.objects(b, None) if isinstance(o, rdflib.BNode)]
    loose = sorted({x for x in g.subjects() if isinstance(x, rdflib.BNode)} - reached, key=str)
    roots = [b for b in loose if (None, None, b) not in g]
    covered = set(roots)
    for b in roots:
        todo = [b]
        while todo:
            x = todo.pop()
            for o in g.objects(x, None):
                if isinstance(o, rdflib.BNode) and o not in covered:
                    covered.add(o)
                    todo.append(o)
    counts: dict = {}
    for b in roots:
        key = frozenset(_statements(g, b, mapping, ignore))
        if key:
            counts[key] = counts.get(key, 0) + 1
    for b in loose:  # a detached loop has no first node: it is read from each of its nodes, as one group
        if b in covered:
            continue
        group, todo = set(), [b]
        while todo:
            x = todo.pop()
            if x not in group:
                group.add(x)
                todo += [o for o in g.objects(x, None) if isinstance(o, rdflib.BNode)]
        covered |= group
        key = ("_:loop", frozenset(frozenset(_statements(g, x, mapping, ignore)) for x in group))
        counts[key] = counts.get(key, 0) + 1
    if counts:
        out[UNREFERENCED] = {(k, n) for k, n in counts.items()}
    return out


def only_approved_changed(baseline: rdflib.Graph, candidate: rdflib.Graph, rows: list[dict],
                          approved: set[str], ignore: frozenset = frozenset()) -> list[str]:
    """``ignore`` names predicates that a batch changes on every concept by an approved rule, such as
    skos:notation, which the ID batch moves to the migration map (DSBP-DEC-0031)."""
    mapping = old_to_new(rows)
    fails = []
    for r in rows:
        if r["status"] == "excluded" and local_id(r["baseline_iri"]) not in approved:
            fails.append(f"V3: {local_id(r['baseline_iri'])} is excluded but is not on the approved list")
        if r["status"] not in KEEPS_IRI:
            continue
        old, new = URIRef(r["baseline_iri"]), URIRef(r["new_iri"])
        before = _statements(baseline, old, mapping, ignore)
        after = _statements(candidate, new, {}, ignore)
        if before != after and not {local_id(str(old)), local_id(str(new))} & approved:
            fails.append(f"V3: {local_id(str(old))} (now {local_id(str(new))}) changed but is not on the approved list "
                         f"({len(before - after)} statements removed, {len(after - before)} added)")
    known = {r["new_iri"] for r in rows if r.get("new_iri")}
    for s in sorted(processes(candidate), key=str):
        if str(s) in known:
            continue
        if not NEW_IRI.fullmatch(str(s)):
            fails.append(f"V3: {s} is in the candidate but is neither a mapped concept nor a new neutral ID")
        elif local_id(str(s)) not in approved:
            fails.append(f"V3: {local_id(str(s))} is a new concept but is not on the approved list")
    before, after = _others(baseline, mapping, ignore), _others(candidate, {}, ignore)
    for s in sorted(set(before) | set(after), key=str):
        if before.get(s, set()) != after.get(s, set()) and local_id(str(s)) not in approved and str(s) not in approved:
            fails.append(f"V3: {s} is not a process, changed, and is not on the approved list "
                         f"({len(before.get(s, set()) - after.get(s, set()))} statements removed, "
                         f"{len(after.get(s, set()) - before.get(s, set()))} added)")
    # A property in both namespaces at once is a half-done move, which the comparison above cannot see.
    for s, p, _ in sorted(candidate):
        if str(p).startswith(str(CORE)) and (s, _same_predicate(p), None) in candidate:
            fails.append(f"V3: {local_id(str(s))} carries {local_id(str(p))} in both the old and the new namespace")
    return sorted(set(fails), key=fails.index)


# V4 ---------------------------------------------------------------------------------------------------------------
def structure(candidate: rdflib.Graph, shapes: Path | None = None) -> list[str]:
    fails = []
    procs = processes(candidate)
    parents: dict[URIRef, list] = {s: list(candidate.objects(s, SKOS.broader)) for s in procs}
    for s, ps in parents.items():
        levels = _levels(candidate, s)
        bad = sorted(str(x) for x in levels if _whole(x) is None)
        if bad:
            fails.append(f"V4: {local_id(str(s))} has a level that is not a whole number ({', '.join(bad)})")
        whole = {_whole(x) for x in levels} - {None}
        if len(whole) > 1:
            fails.append(f"V4: {local_id(str(s))} has {len(whole)} different levels; it needs one")
        lv = level(candidate, s)
        if lv is not None and lv < 0:
            fails.append(f"V4: {local_id(str(s))} has a negative level {lv}")
        if lv is not None and lv > 0 and len(ps) != 1:
            fails.append(f"V4: {local_id(str(s))} at level {lv} has {len(ps)} parents; it needs one")
        for p in ps:
            if p not in procs:
                fails.append(f"V4: {local_id(str(s))} sits under {local_id(str(p))}, which is not a process "
                             f"in the candidate")
                continue
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
    # skos:narrower is optional, but where it is given it must be the exact inverse of skos:broader.
    for s, n in sorted(candidate.subject_objects(SKOS.narrower)):
        if (n, SKOS.broader, s) not in candidate:
            fails.append(f"V4: {local_id(str(s))} has narrower {local_id(str(n))}, which does not have it as broader")
    if any(True for _ in candidate.triples((None, SKOS.narrower, None))):
        for s, b in sorted(candidate.subject_objects(SKOS.broader)):
            if (b, SKOS.narrower, s) not in candidate:
                fails.append(f"V4: {local_id(str(s))} has broader {local_id(str(b))}, which does not list it as "
                             f"narrower")
    labels: dict[str, list] = {}
    for s in procs:
        prefs = list(candidate.objects(s, SKOS.prefLabel))
        if not [x for x in prefs if str(x).strip()]:
            fails.append(f"V4: {local_id(str(s))} has no preferred label")
        elif any(not str(x).strip() for x in prefs):
            fails.append(f"V4: {local_id(str(s))} has a blank preferred label")
        per_language: dict = {}
        for x in prefs:
            per_language[getattr(x, "language", None)] = per_language.get(getattr(x, "language", None), 0) + 1
        for lang, n in sorted(per_language.items(), key=lambda kv: str(kv[0])):
            if n > 1:
                fails.append(f"V4: {local_id(str(s))} has {n} preferred labels in {lang or 'no language'}; "
                             f"it needs one")
        # One concept's label in two languages, or the same label twice, is not a clash with another concept.
        for lab in {str(x).strip().casefold() for x in prefs if str(x).strip()}:
            labels.setdefault(lab, []).append(local_id(str(s)))
        deprecated = (s, OWL.deprecated, Literal(True)) in candidate
        defs = [x for x in candidate.objects(s, SKOS.definition) if str(x).strip()]
        if not deprecated and not defs:
            fails.append(f"V4: {local_id(str(s))} has no definition")
        if len(set(candidate.objects(s, SKOS.definition))) > 1:
            fails.append(f"V4: {local_id(str(s))} has {len(set(candidate.objects(s, SKOS.definition)))} "
                         f"definitions; it needs one")
    fails += [f"V4: preferred label {k!r} is shared by {', '.join(sorted(v))}"
              for k, v in labels.items() if len(v) > 1]
    if shapes is not None:
        import pyshacl
        ok, _, text = pyshacl.validate(candidate, shacl_graph=load(shapes), inference="none")
        if not ok:
            fails.append("V4: SHACL shapes do not conform:\n" + text[:2000])
    return fails


# V5 ---------------------------------------------------------------------------------------------------------------
def read_terms(path: Path = TERMS) -> list[tuple[str, re.Pattern, str]]:
    """Each term as a whole word, with its kind. Only a letter or a digit joins words here, so "XPIMS-based",
    "MPC-owned" and "XPIMS_run" match."""
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        flags = 0 if r["case_sensitive"].strip().lower() == "yes" else re.IGNORECASE
        out.append((r["term"], re.compile(r"(?<![A-Za-z0-9])" + re.escape(r["term"]) + r"(?![A-Za-z0-9])", flags),
                    r.get("kind", "").strip()))
    return out


def read_allowed(path: Path = ALLOWED) -> list[re.Pattern]:
    """Phrases in which a register term has a generic meaning, such as "days payable outstanding (DPO)". A
    missing file allows nothing."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [re.compile(re.escape(r["phrase"]), re.IGNORECASE) for r in csv.DictReader(fh) if r["phrase"].strip()]


def _words(text: str) -> list[str]:
    """An IRI's words, in lower case: split at every mark and at a change of case, so `hasXpimsId`, `xpims-run`
    and `MPCProcess` all hold the word for the term."""
    return [w.casefold() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", text)]


def _iri_names(iri: str, term: str) -> bool:
    """Whether an IRI names a register term, in any letter case: the term's words appear in a row among the IRI's
    words, or, for a term of five letters or more, inside one of its runs of letters, as `marathon` does in
    `marathonpetroleum.com`. A shorter term, such as MPC, must stand as a word of its own, so `rmpcx` is not a hit."""
    want = _words(term)
    if not want:
        return False
    have = _words(iri)
    if any(have[i:i + len(want)] == want for i in range(len(have) - len(want) + 1)):
        return True
    flat = "".join(want)
    return len(flat) >= 5 and any(flat in run.casefold() for run in re.findall(r"[A-Za-z0-9]+", iri))


def company_neutral(candidate: rdflib.Graph, terms_path: Path = TERMS, allowed_path: Path = ALLOWED) -> list[str]:
    """Every literal of every subject on every property, the ontology header and module properties included.
    skos:example is read for company-built systems, which leave the reference ontology even as examples
    (DSBP-DEC-0006); a company name may stand in an example (GOAL.md, done line 4), and in the title,
    description, publisher, URL or IRI of a cited source, such as a peer's filing. A commercial product is not in the
    register at all."""
    terms = read_terms(terms_path)
    allowed = read_allowed(allowed_path)
    sources = set(candidate.objects(None, DCTERMS.source))
    fails = []
    # IRIs, in every position. A cited source's own IRI, and an IRI given as its identifier, may name the company that
    # published it, such as a peer's filing, but never a company-built system.
    # The exemption holds only in those places: the object of dcterms:source, the subject of the source's own record,
    # and a URIRef given as its identifier; never for an IRI this project or its predecessor minted.
    record = (DCTERMS.title, DCTERMS.description, DCTERMS.publisher, DCTERMS.identifier, DCTERMS.hasVersion,
              DCTERMS.issued, DSBP.accessDate)
    seen = set()
    for s, p, o in sorted(candidate, key=lambda x: (str(x[0]), str(x[1]), str(x[2]))):
        for iri, cited in ((s, s in sources and p in record), (p, False),
                           (o, p == DCTERMS.source or (s in sources and p == DCTERMS.identifier))):
            if not isinstance(iri, URIRef):
                continue
            cited = cited and not str(iri).lower().replace("http://", "https://", 1).startswith(MINTED)
            for term, _, kind in terms:
                if (kind == "company" and cited) or (iri, term) in seen or not _iri_names(str(iri), term):
                    continue
                seen.add((iri, term))
                fails.append(f"V5: the IRI {iri} contains {term!r}")
    for s, prop, o in sorted(candidate, key=lambda x: (str(x[0]), str(x[1]), str(x[2]))):
        if not isinstance(o, Literal):
            continue
        text = str(o)
        citation = s in sources and prop in (DCTERMS.title, DCTERMS.description, DCTERMS.publisher, DCTERMS.identifier)
        hit = TRACE_CODE.search(text)
        if hit is None and not citation and prop != SKOS.example:
            hit = TRACE_FILE.search(WEB_ADDRESS.sub(" ", text))
        if hit:
            fails.append(f"V5: {local_id(str(s))} {prop.n3(candidate.namespace_manager)} carries the working "
                         f"trace {hit.group(0)!r}, which a reader outside the predecessor cannot follow")
        for rx in allowed:
            text = rx.sub(" ", text)
        # A cited source's own words and address (citation, above): a peer's filing may name the peer (DSBP-DEC-0002).
        for term, rx, kind in terms:
            if kind == "company" and (prop == SKOS.example or citation):
                continue
            if rx.search(text):
                fails.append(f"V5: {local_id(str(s))} {prop.n3(candidate.namespace_manager)} "
                             f"contains {term!r}")
    return fails


# V6 ---------------------------------------------------------------------------------------------------------------
def _filled(g: rdflib.Graph, s: URIRef, p: URIRef) -> bool:
    return any(str(o).strip() for o in g.objects(s, p))


def _is_url(x) -> bool:
    low = str(x).lower()
    return low.startswith(("http://", "https://")) and not low.replace("http://", "https://", 1).startswith(MINTED)


def _is_date(text: str) -> bool:
    """A real calendar date written YYYY-MM-DD: 2026-02-31 is not one."""
    if not ISO_DATE.fullmatch(text):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _public(g: rdflib.Graph, src: URIRef) -> list[str]:
    """What a source lacks to count as public evidence. The URL is a dcterms:identifier that is a web address, or
    else the source's own IRI; an IRI this project or its predecessor minted is not a place a reader can go."""
    ids = [str(x) for x in g.objects(src, DCTERMS.identifier)]
    if INTERNAL_IRI.search(str(src)) or any(INTERNAL_SOURCE.search(x) for x in [str(src)] + ids):
        return ["a public source (this one is internal)"]
    missing = []
    if not _filled(g, src, DCTERMS.title):
        missing.append("title")
    if not _filled(g, src, DCTERMS.publisher):
        missing.append("publisher")
    if not any(_is_url(x) for x in ids) and not _is_url(src):
        missing.append("URL")
    if not _filled(g, src, DCTERMS.hasVersion) and not _filled(g, src, DCTERMS.issued):
        missing.append("version or issue date")
    if not any(_is_date(str(o).strip()) for o in g.objects(src, DSBP.accessDate)):
        missing.append("access date (as a date, such as 2026-11-27)")
    return missing


def evidence(baseline: rdflib.Graph, candidate: rdflib.Graph, rows: list[dict]) -> list[str]:
    back = {r["new_iri"]: r["baseline_iri"] for r in rows if r.get("new_iri")}
    fails = []
    for s in sorted(set(candidate.subjects(SKOS.definition, None)), key=str):
        new_defs = set(candidate.objects(s, SKOS.definition))
        # The same concept in the baseline: by the map, under the same IRI, or moved from the old module namespace.
        olds = [back.get(str(s)), str(s), str(s).replace(str(DSBP), str(CORE), 1)]
        if any(o and set(baseline.objects(URIRef(o), SKOS.definition)) == new_defs for o in olds):
            continue  # definition unchanged: the predecessor's provenance stands
        problems = [(src, _public(candidate, src)) for src in candidate.objects(s, DCTERMS.source)]
        internal = [src for src, miss in problems if miss == ["a public source (this one is internal)"]]
        if internal:
            fails.append(f"V6: {local_id(str(s))} has a new or changed definition that still cites an internal "
                         f"source ({', '.join(local_id(str(x)) for x in internal)})")
        elif not any(not miss for _, miss in problems):
            detail = "; ".join(f"{local_id(str(src))} lacks {', '.join(m)}" for src, m in problems) or "no source"
            fails.append(f"V6: {local_id(str(s))} has a new or changed definition without a complete public "
                         f"source ({detail})")
    return fails


# V7 ---------------------------------------------------------------------------------------------------------------
def read_removals(path: Path | None) -> set[str]:
    """Approved removals, one per line as `<subject> <property> <object>` in old local IDs."""
    if path is None:
        return set()
    return {" ".join(x.split()) for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")}


def relationships_kept(baseline: rdflib.Graph, candidate: rdflib.Graph, rows: list[dict],
                       removals: set[str] = frozenset()) -> list[str]:
    """Every statement is checked, an approved concept's too: a rename or a move does not license losing a
    dependency. A statement may go only when one end is excluded, or when ``removals`` names it."""
    mapping = old_to_new(rows)
    excluded = {r["baseline_iri"] for r in rows if r["status"] == "excluded"}
    procs = processes(baseline)
    fails = []
    for s, p, o in sorted(baseline):
        if s in procs and o in procs and (str(p).startswith(str(CORE)) or p == SKOS.related):
            if str(s) in excluded or str(o) in excluded:
                continue
            if f"{local_id(str(s))} {local_id(str(p))} {local_id(str(o))}" in removals:
                continue
            ns, no = URIRef(mapping.get(str(s), "")), URIRef(mapping.get(str(o), ""))
            if (ns, p, no) not in candidate and (ns, _same_predicate(p), no) not in candidate:
                fails.append(f"V7: {local_id(str(s))} {local_id(str(p))} {local_id(str(o))} is gone")
    return fails


# V8 ---------------------------------------------------------------------------------------------------------------
def logic(candidate: rdflib.Graph) -> list[str]:
    try:
        import owlready2
    except ImportError:
        return ["V8: owlready2 is not installed, so the reasoner did not run"]
    g = rdflib.Graph()
    for t in candidate.triples((None, None, None)):
        if t[1] != OWL.imports:  # the reasoner reads this file alone; an import would fetch from the web or fail
            g.add(t)
    with tempfile.TemporaryDirectory() as tmp:
        nt = Path(tmp) / "candidate.nt"
        g.serialize(nt, format="nt", encoding="utf-8")
        world = owlready2.World()
        try:
            # Load from an open file: owlready2 cannot open a file: URI with a drive letter on Windows.
            with open(nt, "rb") as f:
                onto = world.get_ontology("https://w3id.org/ds-bp/v8-candidate/").load(fileobj=f, format="ntriples")
        except Exception as e:  # noqa: BLE001 - a file the loader cannot read is a failure, not a crash
            return [f"V8: the candidate could not be loaded for the reasoner ({type(e).__name__}: {e})"]
        try:
            with onto:
                owlready2.sync_reasoner_hermit(world, infer_property_values=False, debug=0)
        except owlready2.OwlReadyInconsistentOntologyError:
            return ["V8: the reasoner found the candidate inconsistent"]
        except (owlready2.OwlReadyJavaError, FileNotFoundError, OSError) as e:
            return [f"V8: the reasoner could not run ({type(e).__name__}); HermiT needs a working Java"]
        except Exception as e:  # noqa: BLE001 - a file the loader cannot read is a failure, not a crash
            return [f"V8: the candidate could not be loaded for the reasoner ({type(e).__name__}: {e})"]
        bad = list(world.inconsistent_classes())
        return [f"V8: class {c} is unsatisfiable" for c in bad]


_PREFIXES = {"skos": str(SKOS), "dcterms": str(DCTERMS), "rdfs": str(RDFS), "owl": str(OWL), "rdf": str(RDF),
             "core": str(CORE), "dsbp": str(DSBP)}


def expand(name: str) -> URIRef:
    """A predicate given on the command line, as a full IRI or as prefix:name with a known prefix."""
    if name.startswith(("http://", "https://")):
        return URIRef(name)
    prefix, sep, rest = name.partition(":")
    if not sep or prefix not in _PREFIXES:
        raise ValueError(f"--ignore {name!r}: give a full IRI or one of {', '.join(sorted(_PREFIXES))}:<name>")
    return URIRef(_PREFIXES[prefix] + rest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--approved", type=Path)
    ap.add_argument("--shapes", type=Path)
    ap.add_argument("--removals", type=Path, help="approved removals of statements, one `S P O` per line (V7)")
    ap.add_argument("--baseline", type=Path, default=BASELINE_CORE)
    ap.add_argument("--ignore", nargs="*", default=[],
                    help="predicates V3 leaves out, as full IRIs or skos:/dcterms:/rdfs:/owl: names, such as "
                         "skos:notation, which the ID batch moves to the migration map (DSBP-DEC-0031)")
    ap.add_argument("--skip", nargs="*", default=[], help="check IDs to skip, such as V8")
    a = ap.parse_args(argv)
    baseline, candidate, rows = load(a.baseline), load(a.candidate), read_map(a.map)
    approved = read_approved(a.approved)
    removals = read_removals(a.removals)
    ignore = frozenset(expand(x) for x in a.ignore)
    checks = {
        "V1": lambda: baseline_untouched(),
        "V2": lambda: nothing_lost(baseline, rows, candidate),
        "V3": lambda: only_approved_changed(baseline, candidate, rows, approved, ignore),
        "V4": lambda: structure(candidate, a.shapes),
        "V5": lambda: company_neutral(candidate),
        "V6": lambda: evidence(baseline, candidate, rows),
        "V7": lambda: relationships_kept(baseline, candidate, rows, removals),
        "V8": lambda: logic(candidate),
        "V9": lambda: ["V9: the competency-question check is not built yet"],
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
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
