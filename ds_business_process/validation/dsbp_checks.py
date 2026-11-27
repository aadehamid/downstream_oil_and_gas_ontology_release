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
                            a blank-node object is compared by its content, so a change inside one counts
V4  structure               no cycles; one parent below the top, and that parent is a process; one level, not negative,
                            = parent level + 1; skos:narrower, where given, is the inverse of skos:broader; one
                            preferred label on every concept, unique; one non-blank definition on every concept that
                            is not deprecated; optional SHACL shapes conform
V5  company_neutral         no term from the company-terms register in any literal or IRI of the candidate, on any
                            subject and any property; skos:example may name a company, never a company-built system; a
                            phrase in the allowed-terms register (a generic meaning of the same letters) is not a hit;
                            a cited source's own IRI, URL, title, description and publisher may name a company; and no
                            literal carries the predecessor's working trace (a decision code such as PTC-001, or a
                            working file name such as notes.md or plan.xlsx)
V6  evidence                every new or changed definition, on any subject, cites a public source with title,
                            publisher, URL, version or issue date, and access date, none of them blank, and cites no
                            internal source beside it. The access date is dsbp:accessDate, an xsd:date: Dublin Core
                            has no term for the day a source was read (see README.md, "How a source is recorded")
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
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

import rdflib
from rdflib import RDF, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDFS, SKOS

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
# The predecessor's working trace, which a reader outside it cannot follow (V5): its parked-tree-change codes and the
# names of its working files. A public document's file name lives on its source record, which V5 leaves out.
TRACE = re.compile(r"(?<![A-Za-z0-9])(?:PTC-\d+(?:-[A-Z])?|[A-Za-z0-9_-]+\.(?:md|xlsx|xlsm|csv|json|py|ipynb|docx|pptx))"
                   r"(?![A-Za-z0-9])")


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


def level(g: rdflib.Graph, s: URIRef) -> int | None:
    v = g.value(s, CORE.taxonomyLevel)
    if v is None:  # not `or`: a level-0 Literal is falsy
        v = g.value(s, DSBP.taxonomyLevel)
    return _whole(v)


def _whole(v) -> int | None:
    """A level as a whole number, or None when it is missing or is not one (V4 reports the second)."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


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
    their new ones, and a blank-node object becomes its own statements, since its label differs between graphs."""
    out = set()
    ignore = frozenset(map(_same_predicate, ignore))
    for p, o in g.predicate_objects(s):
        p = _same_predicate(p)
        if p in ignore:
            continue
        if isinstance(o, URIRef):
            o = _same_predicate(URIRef(mapping.get(str(o), str(o))))
        elif isinstance(o, rdflib.BNode):
            o = ("_:", frozenset(_statements(g, o, mapping, ignore, _path + (s,)))) if o not in _path else ("_:cycle",)
        out.add((p, o))
    return out


def _others(g: rdflib.Graph, mapping: dict[str, str], ignore: frozenset) -> dict[URIRef, set]:
    """The statements of every named subject that is not a process, with module IRIs moved to the new namespace.
    A blank-node subject is compared through the named subject that points at it."""
    procs = processes(g)
    out: dict[URIRef, set] = {}
    for s in set(g.subjects()):
        if not isinstance(s, URIRef) or s in procs or str(s) in mapping:
            continue
        stmts = _statements(g, s, mapping, ignore)
        if stmts:
            out[_same_predicate(s)] = stmts
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
        levels = set(candidate.objects(s, CORE.taxonomyLevel)) | set(candidate.objects(s, DSBP.taxonomyLevel))
        bad = sorted(str(x) for x in levels if _whole(x) is None)
        if bad:
            fails.append(f"V4: {local_id(str(s))} has a level that is not a whole number ({', '.join(bad)})")
        if len({_whole(x) for x in levels if _whole(x) is not None}) > 1:
            fails.append(f"V4: {local_id(str(s))} has {len(levels)} different levels; it needs one")
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
        elif len({getattr(x, "language", None) for x in prefs}) < len(prefs):
            fails.append(f"V4: {local_id(str(s))} has {len(prefs)} preferred labels in one language; it needs one")
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


def company_neutral(candidate: rdflib.Graph, terms_path: Path = TERMS, allowed_path: Path = ALLOWED) -> list[str]:
    """Every literal of every subject on every property, the ontology header and module properties included.
    skos:example is read for company-built systems, which leave the reference ontology even as examples
    (DSBP-DEC-0006); a company name may stand in an example (GOAL.md, done line 4), and in the title,
    description, publisher, URL or IRI of a cited source, such as a peer's filing. A commercial product is not in the
    register at all."""
    terms = read_terms(terms_path)
    allowed = read_allowed(allowed_path)
    sources = set(candidate.objects(None, DCTERMS.source))
    # A cited source's own IRI and URLs may name the company that published it, such as a peer's filing.
    cited = {str(x) for x in sources} | {str(o) for s in sources for o in candidate.objects(s, DCTERMS.identifier)}
    fails = []
    iris = {x for t in candidate for x in t if isinstance(x, URIRef) and str(x) not in cited}
    for iri in sorted(iris, key=str):
        for term, rx, _ in terms:
            if rx.search(str(iri)):
                fails.append(f"V5: the IRI {iri} contains {term!r}")
    for s, prop, o in sorted(candidate, key=lambda x: (str(x[0]), str(x[1]), str(x[2]))):
        if not isinstance(o, Literal):
            continue
        text = str(o)
        if not (s in sources and prop in (DCTERMS.title, DCTERMS.description, DCTERMS.publisher, DCTERMS.identifier)):
            hit = TRACE.search(text)
            if hit:
                fails.append(f"V5: {local_id(str(s))} {prop.n3(candidate.namespace_manager)} carries the working "
                             f"trace {hit.group(0)!r}, which a reader outside the predecessor cannot follow")
        for rx in allowed:
            text = rx.sub(" ", text)
        # A cited source's own words and address: a peer's filing may name the peer (DSBP-DEC-0002).
        citation = s in sources and prop in (DCTERMS.title, DCTERMS.description, DCTERMS.publisher, DCTERMS.identifier)
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
    if not _filled(g, src, DSBP.accessDate):
        missing.append("access date")
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
