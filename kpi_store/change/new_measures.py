"""Adds new measures to the kpi module's tables from their KGCL lines and their facts, rebuilds the module, and turns
the difference between two built kpi graphs back into lines and facts (KPI-DEC-0004, item 1; KPI-DEC-0002, Q10
form 1).

A new measure is two files of its proposal (proposal.py). change.kgcl holds everything KGCL can say:

    create node measure:<key> '<name>'                                  measure-classification.csv, name
    add definition '<text>' to measure:<key>                            measure-details.csv, definition
    create exact synonym '<text>' for measure:<key>                     measure-details.csv, aliases   any number
    create edge measure:<key> kpi:measureKind kind:<kind>               measure-classification.csv, class
    create edge measure:<key> dcterms:source src:<slug>                 measure-classification.csv, source (its key)
    create edge measure:<key> kpi:usedBy persona:<slug>                 measure-classification.csv, personas   any number
    create edge measure:<key> kpi:informsProcess proc:<id>              measure-details.csv, informs_process   any number
    create edge measure:<key> kpi:notToBeConfusedWith measure:<other>   measure-details.csv, not_to_be_confused_with

facts.csv holds the facts KGCL cannot write, one row each (measure, property, value). On kgcl-schema 0.7.0 a quoted
text object of `create edge` renders without its quotes, and `change annotation` does not parse, so these values
have no KGCL line (KPI-DEC-0004):

    kpi:kpiCandidate                true or false          measure-classification.csv, kpi_candidate     required
    kpi:classificationTest          1 to 5                 measure-classification.csv, rule_test         required
    kpi:classificationReason        text                   measure-classification.csv, reason            required
    kpi:comparedAgainst             text                   measure-classification.csv, compared_against
    kpi:publicCounterpart           text                   measure-classification.csv, mpc_counterpart
    dcterms:bibliographicCitation   text                   measure-classification.csv, evidence
    kpi:grain                       text                   measure-details.csv, grain
    kpi:basis                       text                   measure-details.csv, basis
    skos:scopeNote                  text                   measure-details.csv, not_note
    skos:note                       text                   identifier-notes.csv

A fact that a KGCL line can carry (a name, a definition, an other name or a link) is refused in facts.csv.

The builder writes the rest by rule, and compare expects it: the measure's types, its scheme both ways, its short
key, the classification evidence as a second source, and its identifier. The apply gives each new measure of a kind
that takes one the next KPI- or OPM- number after the module's highest, in the order of the proposals, as the
builder's run rule needs (build_measures.py). The table's topic column stays empty: the form keeps the topic (4.9)
in its own file.

apply_changes works on the release folder it is given, which must be a scratch copy, as kpi_tables.py does.
"""
import re
from pathlib import Path

from .. import cut
from . import ChangeRefused, kpi_tables
from .kgcl import Change, write_line

BASE = "https://w3id.org/mpc/ontology/"
KPI_NS = kpi_tables.PREFIXES["kpi"]
# The namespaces of build_measures.py; a test checks that they are the builder's.
PREFIXES = {**kpi_tables.PREFIXES, "kind": KPI_NS + "measure-kind/", "persona": KPI_NS + "persona/",
            "src": BASE + "source/", "dcterms": "http://purl.org/dc/terms/",
            "skos": "http://www.w3.org/2004/02/skos/core#"}
FOLDER = kpi_tables.KPI_FOLDER
CLASSIFICATION, DETAILS = kpi_tables.CLASSIFICATION, kpi_tables.DETAILS
IDENTIFIERS, NOTES, PERSONAS, SOURCES = "measure-identifiers", "identifier-notes", "personas", "measure-sources"
TABLES = (CLASSIFICATION, DETAILS, IDENTIFIERS, NOTES)
# build_measures.py's kinds, its identifier prefix for each kind, the one exception to the run, and the source every
# measure cites; a test checks that they are the builder's.
KINDS = ("kpi", "operational-metric", "plan-variance-diagnostic", "market-indicator", "decision-support-indicator",
         "tracker-or-report", "alert", "not-a-measure")
PREFIX = {"kpi": "KPI", "operational-metric": "OPM", "market-indicator": "OPM", "plan-variance-diagnostic": "OPM",
          "decision-support-indicator": "OPM", "alert": "OPM"}
EXCEPTIONS = {"crack-spreads": "KPI-0001"}
CLASSIFIED_BY = "kpi-classification-evidence"
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
LANGUAGE = "en"

# predicate -> (the prefix of its target, True when a measure takes exactly one)
EDGES = {"kpi:measureKind": ("kind", True), "dcterms:source": ("src", True), "kpi:usedBy": ("persona", False),
         "kpi:informsProcess": ("proc", False), "kpi:notToBeConfusedWith": ("measure", False)}
# property -> (table, column, the literal's form: "boolean", "integer", "string" for xsd:string, "text" for @en)
FACTS = {"kpi:kpiCandidate": (CLASSIFICATION, "kpi_candidate", "boolean"),
         "kpi:classificationTest": (CLASSIFICATION, "rule_test", "integer"),
         "kpi:classificationReason": (CLASSIFICATION, "reason", "string"),
         "kpi:comparedAgainst": (CLASSIFICATION, "compared_against", "string"),
         "kpi:publicCounterpart": (CLASSIFICATION, "mpc_counterpart", "string"),
         "dcterms:bibliographicCitation": (CLASSIFICATION, "evidence", "string"),
         "kpi:grain": (DETAILS, "grain", "string"),
         "kpi:basis": (DETAILS, "basis", "string"),
         "skos:scopeNote": (DETAILS, "not_note", "text"),
         "skos:note": (NOTES, "note", "text")}
REQUIRED = ("kpi:kpiCandidate", "kpi:classificationTest", "kpi:classificationReason")
CARRIED = ("skos:prefLabel", "skos:definition", "skos:altLabel", *EDGES)   # what KGCL lines say


def curie(iri):
    """prefix:name for an IRI of one of PREFIXES' namespaces, the longest that fits, else None."""
    fits = [(len(ns), p) for p, ns in PREFIXES.items() if str(iri).startswith(ns) and len(str(iri)) > len(ns)]
    if not isinstance(iri, str) or not fits:
        return None
    n, prefix = max(fits)
    return f"{prefix}:{iri[n:]}"


def iri(text):
    prefix, name = text.split(":", 1)
    return PREFIXES[prefix] + name


def tail(text):
    return text.split(":", 1)[1]


class Measure:
    """One new measure, as its lines and facts state it."""

    def __init__(self, subject, label):
        self.subject, self.label = subject, label
        self.definition, self.synonyms, self.edges, self.facts = "", [], [], {}

    @property
    def key(self):
        return tail(self.subject)

    def targets(self, predicate):
        return [t for p, t in self.edges if p == predicate]


def _fact_problem(prop, value):
    """Why a fact's value cannot go into its table, or None."""
    if prop in CARRIED:
        return f"{prop} is said by a KGCL line of change.kgcl, not by facts.csv"
    if prop not in FACTS:
        return f"{prop} is not a fact of a new measure ({', '.join(FACTS)})"
    if not value or value != value.strip():
        return "the value is empty or starts or ends with a space"
    if any(ord(c) < 32 or c in "  " for c in value):
        return "the value holds a line break or another control character"
    form = FACTS[prop][2]
    if form == "boolean" and value not in ("true", "false"):
        return "the value is true or false"
    if form == "integer" and value not in ("1", "2", "3", "4", "5"):
        return "the value is a test from 1 to 5"
    return None


def measures(changes, facts=()):
    """The new measures the changes and the facts make, in order. Refuses a line that is not about a new measure, a
    fact that is not about one, and a measure that lacks a line or a fact it needs or has one it may not."""
    changes = list(changes)
    if not changes:
        raise ChangeRefused("there are no changes to apply")
    found = {}
    for change in changes:
        line = write_line(change)
        if not change.subject.startswith("measure:"):
            raise ChangeRefused(f"a new KPI is a measure (measure:<id>): {line}")
        if change.kind == "create node":
            if change.subject in found:
                raise ChangeRefused(f"the measure is made twice: {line}")
            if not SLUG.fullmatch(change.subject[len("measure:"):]):
                raise ChangeRefused(f"the short key of a new measure is lower-case letters and digits joined by hyphens: {line}")
            found[change.subject] = Measure(change.subject, change.text)
            continue
        m = found.get(change.subject)
        if m is None:
            raise ChangeRefused(f"a new KPI adds new measures only, and this line is about a measure that no 'create node' "
                                f"line before it makes: {line}")
        if change.kind == "add definition":
            if m.definition:
                raise ChangeRefused(f"the measure has a definition already: {line}")
            m.definition = change.text
        elif change.kind == "create synonym":
            if ";" in change.text:
                raise ChangeRefused(f"an other name may not hold a semicolon, which separates them in the table: {line}")
            if change.text.casefold() in {n.casefold() for n in (m.label, *m.synonyms)}:
                raise ChangeRefused(f"the measure has this name already: {line}")
            m.synonyms.append(change.text)
        elif change.kind == "create edge" and change.predicate in EDGES:
            want = EDGES[change.predicate][0]
            if change.target.split(":", 1)[0] != want:
                raise ChangeRefused(f"{change.predicate} of a measure points at {want}:<id>: {line}")
            if (change.predicate, change.target) in m.edges:
                raise ChangeRefused(f"the measure has this link already: {line}")
            m.edges.append((change.predicate, change.target))
        else:
            raise ChangeRefused(f"a new KPI takes a name, a definition, other names and links ({', '.join(EDGES)}) "
                                f"only: {line}")
    for subject, prop, value in facts:
        row = f"{subject},{prop},{value}"
        m = found.get(subject)
        if m is None:
            raise ChangeRefused(f"a fact of facts.csv is about a new measure that a 'create node' line makes: {row}")
        problem = _fact_problem(prop, value)
        if problem:
            raise ChangeRefused(f"{problem}: {row}")
        if prop in m.facts:
            raise ChangeRefused(f"the measure has this fact already: {row}")
        m.facts[prop] = value
    for m in found.values():
        _complete(m)
    return list(found.values())


def _complete(m):
    name = m.subject
    if not m.definition:
        raise ChangeRefused(f"{name} has no definition: add a line 'add definition '<text>' to {name}'")
    for predicate, (_, one) in EDGES.items():
        n = len(m.targets(predicate))
        if one and n != 1:
            raise ChangeRefused(f"{name} needs exactly one {predicate} link, and has {n}")
    missing = [p for p in REQUIRED if p not in m.facts]
    if missing:
        raise ChangeRefused(f"{name} needs the fact{'s' if len(missing) > 1 else ''} {', '.join(missing)} in facts.csv")
    kind = tail(m.targets("kpi:measureKind")[0])
    if m.facts["kpi:kpiCandidate"] == "true" and kind != "operational-metric":
        raise ChangeRefused(f"{name}: only an operational metric can be a KPI candidate, and this measure is {kind}")
    if m.targets("kpi:notToBeConfusedWith") and "skos:scopeNote" not in m.facts:
        raise ChangeRefused(f"{name}: a measure it is mistaken for needs a skos:scopeNote fact that says how they differ")
    if tail(m.targets("dcterms:source")[0]) == CLASSIFIED_BY:
        raise ChangeRefused(f"{name}: every measure cites src:{CLASSIFIED_BY} already. Name the document the measure "
                            "comes from")


def _read(root, names):
    try:
        return cut.Tables(root, FOLDER, names)
    except cut.CutRefused:
        raise ChangeRefused(f"{root} holds no kpi tables: it is not a KPI Store release") from None


def next_numbers(rows):
    """{prefix: the next number of its run} from the identifier rows, leaving out the exception to the run."""
    out = {}
    for prefix in set(PREFIX.values()):
        held = [int(r["identifier"][len(prefix) + 1:]) for r in rows
                if r["identifier"].startswith(prefix + "-") and r["measure_id"] not in EXCEPTIONS]
        start = 1 + sum(1 for v in EXCEPTIONS.values() if v.startswith(prefix + "-"))
        out[prefix] = max(held, default=start - 1) + 1
    return out


def _edit(changes, facts, root):
    """The kpi tables of the release with the new measures' rows added in memory. Raises ChangeRefused when any
    measure does not fit them."""
    found = measures(changes, facts)
    tables = _read(root, TABLES)
    personas = {r["slug"]: r["label"] for r in _read(root, (PERSONAS,)).rows[PERSONAS]}
    sources = {r["slug"]: r["key"] for r in _read(root, (SOURCES,)).rows[SOURCES]}
    ids = {r["measure_id"] for r in tables.rows[CLASSIFICATION]}
    details = {r["measure_id"]: r for r in tables.rows[DETAILS]}
    names = {}
    for r in tables.rows[CLASSIFICATION]:
        for n in [r["name"], *kpi_tables._split(details.get(r["measure_id"], {}).get("aliases", ""))]:
            names.setdefault(n.casefold(), r["measure_id"])
    numbers = next_numbers(tables.rows[IDENTIFIERS])
    processes = None
    for m in found:
        if m.key in ids:
            raise ChangeRefused(f"the kpi module has a measure with the short key {m.key} already. A change to it goes "
                                "through the term-change form")
        for n in [m.label, *m.synonyms]:
            if n.casefold() in names:
                raise ChangeRefused(f"the measure {names[n.casefold()]} has the name {n!r} already. A change to it goes "
                                    "through the term-change form")
        kind = tail(m.targets("kpi:measureKind")[0])
        if kind not in KINDS:
            raise ChangeRefused(f"kind:{kind} is not a kind of measure ({', '.join(KINDS)})")
        [source] = m.targets("dcterms:source")
        if tail(source) not in sources:
            raise ChangeRefused(f"{source} is not a document of kpi/measure-sources.csv. A new source document needs a "
                                "specialist, because its evidence tier is in the integration module")
        for p in m.targets("kpi:usedBy"):
            if tail(p) not in personas:
                raise ChangeRefused(f"{p} is not a planning persona of kpi/personas.csv, and the kpi builder writes only "
                                    "those")
        for o in m.targets("kpi:notToBeConfusedWith"):
            if tail(o) not in ids or o == m.subject:
                raise ChangeRefused(f"{o} is not another measure of the kpi module")
        informs = []
        for p in m.targets("kpi:informsProcess"):
            if processes is None:
                processes = kpi_tables._process_index(root)
            index, notation = processes
            target = iri(p)
            if target not in index.values():
                raise ChangeRefused(f"{p} is not a process of the newest core")
            informs.append(notation.get(target, tail(p)))
        f = m.facts
        tables.rows[CLASSIFICATION].append({
            "measure_id": m.key, "name": m.label, "source": sources[tail(source)], "topic": "",
            "personas": "; ".join(personas[tail(p)] for p in m.targets("kpi:usedBy")), "class": kind,
            "kpi_candidate": "yes" if f["kpi:kpiCandidate"] == "true" else "no",
            "rule_test": f["kpi:classificationTest"], "compared_against": f.get("kpi:comparedAgainst", ""),
            "mpc_counterpart": f.get("kpi:publicCounterpart", ""), "reason": f["kpi:classificationReason"],
            "evidence": f.get("dcterms:bibliographicCitation", "")})
        tables.rows[DETAILS].append({
            "measure_id": m.key, "definition": m.definition, "grain": f.get("kpi:grain", ""),
            "basis": f.get("kpi:basis", ""), "aliases": ";".join(m.synonyms),
            "not_to_be_confused_with": ";".join(tail(o) for o in m.targets("kpi:notToBeConfusedWith")),
            "not_note": f.get("skos:scopeNote", ""), "informs_process": ";".join(informs)})
        if kind in PREFIX:
            prefix = PREFIX[kind]
            tables.rows[IDENTIFIERS].append({"measure_id": m.key, "identifier": f"{prefix}-{numbers[prefix]:04d}"})
            numbers[prefix] += 1
        if "skos:note" in f:
            tables.rows[NOTES].append({"measure_id": m.key, "note": f["skos:note"]})
        ids.add(m.key)
        for n in [m.label, *m.synonyms]:
            names[n.casefold()] = m.key
    return found, tables


def check_changes(changes, facts, release_root):
    """Raises ChangeRefused when any new measure does not fit the kpi tables of the release. Writes nothing and runs
    no builder: the propose command calls it on the real release."""
    _edit(changes, facts, Path(release_root).resolve())


def apply_changes(changes, facts, release_root):
    """Writes the new measures into the kpi tables of a scratch copy of the release and rebuilds measures.ttl.
    Returns its path. Raises ChangeRefused, and writes nothing, when any measure does not fit the tables. When the
    builder refuses the changed tables, they stay written in the scratch copy, and ChangeRefused carries its message."""
    root = Path(release_root).resolve()
    _, tables = _edit(changes, facts, root)
    tables.write(root)
    try:
        cut._run("rebuild the kpi module", [kpi_tables.BUILDER, "--write"], root / FOLDER)
    except cut.CutFailed as err:
        raise ChangeRefused(f"the kpi builder refused the changed tables: {err}") from None
    return root / kpi_tables.MEASURES


def _value(o, form):
    """The fact's value of a literal of this form, or None when the literal does not have the form."""
    from rdflib import Literal
    from rdflib.namespace import XSD
    if not isinstance(o, Literal):
        return None
    if form == "text":
        return str(o) if o.language == LANGUAGE and o.datatype is None else None
    datatype = {"boolean": XSD.boolean, "integer": XSD.integer, "string": XSD.string}[form]
    if o.datatype != datatype:
        return None
    return str(o.toPython()).lower() if form == "boolean" else str(o)


def compare(before, after):
    """The KGCL lines and the facts that take the built kpi graph `before` to `after` (files or rdflib Graphs) by
    adding new measures: (lines, [(measure, property, value)]), in a fixed order. Raises ChangeRefused when the
    graphs differ in a way that no line and no fact of a new measure states, naming those differences."""
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import DCTERMS, RDF, SKOS, XSD
    before, after = (g if isinstance(g, Graph) else Graph().parse(str(g), format="turtle") for g in (before, after))
    removed, added = set(before) - set(after), set(after) - set(before)
    unsupported = [f"- {s} {p} {o}" for s, p, o in removed]
    ns, held = PREFIXES["measure"], set(before.subjects())
    new = {s for s, p, o in added if p == SKOS.prefLabel and s not in held and str(s).startswith(ns) and len(str(s)) > len(ns)}
    scheme = URIRef(KPI_NS + "Measures")
    edges = {URIRef(iri(p)): p for p in EDGES}
    facts = {URIRef(iri(p)): p for p in FACTS}
    lines, rows, idents = {s: [] for s in new}, [], {}
    for s, p, o in added:
        if s == scheme and p == SKOS.hasTopConcept and o in new:
            continue
        if s not in new:
            unsupported.append(f"+ {s} {p} {o!r}")
        elif (s, p, o) in _expected(s, scheme):
            continue
        elif p == DCTERMS.identifier and isinstance(o, Literal) and o.datatype == XSD.string:
            idents[s] = str(o)
        elif p in (SKOS.prefLabel, SKOS.definition, SKOS.altLabel) and _value(o, "text") is not None:
            kind = {SKOS.prefLabel: "create node", SKOS.definition: "add definition", SKOS.altLabel: "create synonym"}[p]
            lines[s].append(Change(kind, curie(str(s)), text=str(o)))
        elif p in edges and (curie(str(o)) or ":").split(":", 1)[0] == EDGES[edges[p]][0]:
            lines[s].append(Change("create edge", curie(str(s)), predicate=edges[p], target=curie(str(o))))
        elif p in facts and _value(o, FACTS[facts[p]][2]) is not None:
            rows.append((curie(str(s)), facts[p], _value(o, FACTS[facts[p]][2])))
        else:
            unsupported.append(f"+ {s} {p} {o!r}")
    for s in sorted(new):
        unsupported += [f"{s} lacks {p} {o!r}, which every measure has" for _, p, o in sorted(_expected(s, scheme) - added)]
    unsupported += _identifier_problems(before, after, new, idents)
    if unsupported:
        shown = sorted(unsupported)[:10]
        raise ChangeRefused(f"the graphs differ in {len(unsupported)} ways that no line and no fact of a new measure states: "
                            + "; ".join(shown))
    order = {"create node": 0, "add definition": 1, "create synonym": 2, "create edge": 3}
    out = [write_line(c) for s in sorted(new) for c in sorted(lines[s], key=lambda c: (order[c.kind], write_line(c)))]
    return out, sorted(rows)


def _expected(s, scheme):
    """The triples the builder writes for every measure, whatever its lines and facts say."""
    from rdflib import Literal, URIRef
    from rdflib.namespace import DCTERMS, RDF, SKOS, XSD
    return {(s, RDF.type, URIRef(KPI_NS + "MeasureDefinition")), (s, RDF.type, SKOS.Concept),
            (s, SKOS.inScheme, scheme), (s, SKOS.topConceptOf, scheme), (scheme, SKOS.hasTopConcept, s),
            (s, SKOS.notation, Literal(tail(curie(str(s))), datatype=XSD.string)),
            (s, DCTERMS.source, URIRef(PREFIXES["src"] + CLASSIFIED_BY))}


def _identifier_problems(before, after, new, idents):
    """Each new measure has the identifier its kind takes, and the new identifiers of each prefix are the next
    numbers of its run after the highest one `before` holds."""
    from rdflib import URIRef
    from rdflib.namespace import DCTERMS
    kind_of = URIRef(KPI_NS + "measureKind")
    held = [{"measure_id": tail(curie(str(s)) or ":"), "identifier": str(o)} for s, o in before.subject_objects(DCTERMS.identifier)]
    numbers = next_numbers(held)
    problems, given = [], {}
    for s in sorted(new):
        kind = tail(curie(str(after.value(s, kind_of))) or ":")
        prefix, value = PREFIX.get(kind), idents.get(s)
        if prefix is None and value is not None:
            problems.append(f"{s} is a {kind} and has the identifier {value!r}, which a {kind} does not take")
        elif prefix is not None and not re.fullmatch(prefix + r"-\d{4}", value or ""):
            problems.append(f"{s} is a {kind} and needs a {prefix}-nnnn identifier, not {value!r}")
        elif prefix is not None:
            given.setdefault(prefix, []).append(int(value[len(prefix) + 1:]))
    for prefix, got in given.items():
        want = list(range(numbers[prefix], numbers[prefix] + len(got)))
        if sorted(got) != want:
            problems.append(f"the new {prefix} identifiers are {sorted(got)}, and the run needs {want}")
    return problems
