"""Adds new reference items to their module's source tables, rebuilds the module, and turns the difference between
two built graphs back into KGCL lines (KPI-DEC-0002, Q10 form 5, and Q7 items 3 and 5).

Two kinds of item are rows of tables that a builder reads, and this file adds both:

    system   a system that a document names: a row of system/other-systems.csv and one of system/definitions.csv
             create node system:<slug> '<its name>'
             add definition '<what it does>' to system:<slug>
             create exact synonym '<another name>' for system:<slug>               any number
             create edge system:<slug> sys:systemKind kind:<application, office-tool or document>
             create edge system:<slug> sys:namedBy src:<the key of the document that names it>
             create edge system:<slug> dcterms:source src:<key>                    the naming document, and any others
    table    a Databricks table that copies a table of a system (a replica): a row of data-product/pricing/tables.csv
             create node table:<slug> '<catalog.schema.table>'
             create edge table:<slug> dp:layer layer:replica
             create edge table:<slug> dp:copiesSystem system:<slug>
             create edge table:<slug> dcterms:source src:<the key of the document that records it>

Each item needs only its name, a definition (a system) and links to things the module already holds. A system cites
only documents in system/sources.csv, and a table only documents in data-product/pricing/sources.csv, because a
new document needs its evidence tier in the integration module too. The other kinds the form names (a table built
from other tables, a source document, a role and a data product) need a specialist; the form says why.

apply_changes works on the release folder it is given, which must be a scratch copy: the apply command copies the
release first and writes the real sources only after every check has passed. It reads and writes the tables with
cut.Tables and runs the module's builder with cut._run. No table is written when any change is refused.

compare is the round trip. Besides the lines above, a builder writes triples that every item of its kind has: its
types, its scheme both ways and its short key; a table also its full name and its sandbox mark; and a system that
cites a document no other system's definition cites gives that document its type and its title. compare checks
those against what the item's lines say, and refuses any other difference.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import cut
from . import ChangeRefused
from .kgcl import Change, write_line

BASE = "https://w3id.org/mpc/ontology/"
SKOS = "http://www.w3.org/2004/02/skos/core#"
# rdflib is read only where a graph is: the intake check calls slug_of, and needs no rdflib.
# The namespaces of build_systems.py and build_pricing.py; a test checks that they are the builders'.
PREFIXES = {"system": BASE + "modules/system/system/", "kind": BASE + "modules/system/kind/",
            "sys": BASE + "modules/system/", "table": BASE + "modules/data-product/table/",
            "layer": BASE + "modules/data-product/layer/", "dp": BASE + "modules/data-product/",
            "src": BASE + "source/", "dcterms": "http://purl.org/dc/terms/"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SANDBOX = ("idp_sbx.", "synapse_dev.")     # build_pricing.py marks these names sandbox, and the module holds no other
LANGUAGE = "en"


@dataclass(frozen=True)
class Kind:
    """One kind of reference item: where its rows go, what builds it, and which lines it takes."""
    name: str          # the form's answer to R2
    what: str          # how a sentence names one
    module: str        # the release module that holds it
    folder: Path       # the module's folder, from the release's top folder
    builder: str
    output: str        # the built file the round trip compares, in the folder
    tests: str         # the module's tests, as a unittest module of the folder
    prefix: str        # the prefix of the item's id
    types: tuple
    scheme: str
    edges: dict        # predicate -> (the prefix of its target, True when the item takes exactly one)
    definition: bool   # the item takes a definition and other names


ONTOLOGY = cut.ONTOLOGY
KINDS = {
    "system": Kind("system", "a system", "system", ONTOLOGY / "system", "build_systems.py", "systems.ttl", "test_systems",
                   "system", (PREFIXES["sys"] + "System", SKOS + "Concept"), PREFIXES["sys"] + "Systems",
                   {"sys:systemKind": ("kind", True), "sys:namedBy": ("src", True), "dcterms:source": ("src", False)},
                   definition=True),
    "table": Kind("table", "a table", "data-product", ONTOLOGY / "data-product", "build_pricing.py", "pricing.ttl",
                  "test_data_products", "table", (PREFIXES["dp"] + "PlatformTable", SKOS + "Concept"),
                  PREFIXES["dp"] + "PlatformTables",
                  {"dp:layer": ("layer", True), "dp:copiesSystem": ("system", True), "dcterms:source": ("src", True)},
                  definition=False),
}
BY_PREFIX = {k.prefix: k for k in KINDS.values()}
SYSTEM_FOLDER, PRICING = ONTOLOGY / "system", cut.PRICING


def slug(text):
    """A short key from a name: its letters and digits in lower case, joined by hyphens."""
    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))


def slug_of(kind, name, system=""):
    """The short key of a new item: a system's from its name; a table's from the system it copies and the last part
    of its full name, as the module's replicas have it (synapse_dev.replica_mips.mips_currency is replica-mips-currency)."""
    if kind == "system":
        return slug(name)
    tail = slug(name.rsplit(".", 1)[-1])
    if tail.startswith(system + "-"):
        tail = tail[len(system) + 1:]
    return f"replica-{system}-{tail}" if tail and system else ""


def curie(iri):
    """prefix:name for an IRI of one of PREFIXES' namespaces, the longest that fits, else None."""
    if not isinstance(iri, str):
        return None
    fits = [(len(ns), p) for p, ns in PREFIXES.items() if iri.startswith(ns) and len(iri) > len(ns)]
    if not fits:
        return None
    n, prefix = max(fits)
    return f"{prefix}:{iri[n:]}"


def iri(text):
    """The IRI of prefix:name, as text."""
    prefix, name = text.split(":", 1)
    return PREFIXES[prefix] + name


def tail(text):
    return text.split(":", 1)[1]


@dataclass
class Item:
    kind: Kind
    subject: str                # system:<slug> or table:<slug>
    label: str = ""
    definition: str = ""
    synonyms: list = field(default_factory=list)
    edges: list = field(default_factory=list)      # (predicate, target), in the lines' order

    @property
    def slug(self):
        return tail(self.subject)

    def targets(self, predicate):
        return [t for p, t in self.edges if p == predicate]


def items(changes):
    """The new items the changes make, in order. Refuses a change that is not about a new item, and an item that
    lacks a line it needs or has one it may not."""
    changes = list(changes)
    if not changes:
        raise ChangeRefused("there are no changes to apply")
    found = {}
    for change in changes:
        line = write_line(change)   # also refuses a change that has no KGCL form
        prefix = change.subject.split(":", 1)[0]
        kind = BY_PREFIX.get(prefix)
        if kind is None:
            raise ChangeRefused(f"a reference item is a system (system:<id>) or a table (table:<id>): {line}")
        if change.kind == "create node":
            if change.subject in found:
                raise ChangeRefused(f"the item is made twice: {line}")
            if not SLUG.fullmatch(tail(change.subject)):
                raise ChangeRefused(f"the short key of a new item is lower-case letters and digits joined by hyphens: {line}")
            found[change.subject] = Item(kind, change.subject, label=change.text)
            continue
        item = found.get(change.subject)
        if item is None:
            raise ChangeRefused(f"a reference item adds new items only, and this line is about an item that no "
                                f"'create node' line before it makes: {line}")
        if change.kind == "add definition" and kind.definition:
            if item.definition:
                raise ChangeRefused(f"the item has a definition already: {line}")
            item.definition = change.text
        elif change.kind == "create synonym" and kind.definition:
            if ";" in change.text:
                raise ChangeRefused(f"an other name may not hold a semicolon, which separates them in the table: {line}")
            if change.text.casefold() in {n.casefold() for n in (item.label, *item.synonyms)}:
                raise ChangeRefused(f"the item has this name already: {line}")
            item.synonyms.append(change.text)
        elif change.kind == "create edge" and change.predicate in kind.edges:
            want, _ = kind.edges[change.predicate]
            if change.target.split(":", 1)[0] != want:
                raise ChangeRefused(f"{change.predicate} of {kind.what} points at {want}:<id>: {line}")
            if (change.predicate, change.target) in item.edges:
                raise ChangeRefused(f"the item has this link already: {line}")
            item.edges.append((change.predicate, change.target))
        else:
            takes = "a name, a definition, other names and links" if kind.definition else "a name and links"
            raise ChangeRefused(f"{kind.what} of the reference-item form takes {takes} ({', '.join(kind.edges)}) only: {line}")
    for item in found.values():
        _complete(item)
    return list(found.values())


def _complete(item):
    kind, name = item.kind, item.subject
    if kind.definition and not item.definition:
        raise ChangeRefused(f"{name} has no definition: add a line 'add definition '<text>' to {name}'")
    for predicate, (_, one) in kind.edges.items():
        n = len(item.targets(predicate))
        if n == 0 or (one and n > 1):
            raise ChangeRefused(f"{name} needs {'exactly one' if one else 'at least one'} {predicate} link, and has {n}")
    if kind.name == "system" and item.targets("sys:namedBy")[0] not in item.targets("dcterms:source"):
        raise ChangeRefused(f"{name}: the document that names a system is also one of its sources (dcterms:source), "
                            "as the system module's builder writes it")
    if kind.name == "table":
        if item.targets("dp:layer") != ["layer:replica"]:
            raise ChangeRefused(f"{name}: the form adds a replica only (dp:layer layer:replica). A table built from "
                                "other tables is a data product, and needs a specialist")
        if not cut.FULL_NAME.fullmatch(item.label):
            raise ChangeRefused(f"{name}: the name {item.label!r} is not a full name of the form catalog.schema.table")
        if not item.label.startswith(SANDBOX):
            raise ChangeRefused(f"{name}: the module holds the sandbox's tables only, whose names start with "
                                f"{' or '.join(SANDBOX)}, and {item.label!r} does not")


def _read(root, folder, names):
    try:
        return cut.Tables(root, folder, names)
    except cut.CutRefused:
        raise ChangeRefused(f"{root} holds no {folder.as_posix()} tables: it is not a KPI Store release") from None


def _names(rows):
    """Every name of the systems of some rows: label and other names, in lower case."""
    out = {}
    for r in rows:
        for n in [r["label"], *(a for a in r.get("alt_labels", "").split(";") if a.strip())]:
            out.setdefault(n.strip().casefold(), r["slug"])
    return out


def _system_kinds(root):
    from rdflib import Graph, URIRef
    from rdflib.namespace import SKOS
    g = Graph().parse(Path(root) / SYSTEM_FOLDER / "vocabulary.ttl", format="turtle")
    return {curie(str(s)) for s in g.subjects(SKOS.inScheme, URIRef(PREFIXES["sys"] + "SystemKind"))}


def _edit(changes, root):
    """The tables of the release with the new items' rows added in memory: {kind name: cut.Tables to write}. Raises
    ChangeRefused when any item does not fit them."""
    found = items(changes)
    systems = _read(root, SYSTEM_FOLDER, ("systems",))
    others = _read(root, SYSTEM_FOLDER, ("other-systems", "definitions"))
    every = systems.rows["systems"] + others.rows["other-systems"]
    out = {}
    for item in found:
        if item.kind.name == "system":
            out["system"] = others
            sources = {r["key"] for r in _read(root, SYSTEM_FOLDER, ("sources",)).rows["sources"]}
            taken, names = {r["slug"] for r in every}, _names(every)
            if item.slug in taken:
                raise ChangeRefused(f"the system module has a system with the short key {item.slug} already")
            for name in [item.label, *item.synonyms]:
                if name.casefold() in names:
                    raise ChangeRefused(f"the system {names[name.casefold()]} has the name {name!r} already")
            [kind] = item.targets("sys:systemKind")
            if kind not in _system_kinds(root):
                raise ChangeRefused(f"{kind} is not a kind of system the system module holds")
            for key in item.targets("dcterms:source"):
                if tail(key) not in sources:
                    raise ChangeRefused(f"{key} is not a document of system/sources.csv. A new source document needs a "
                                        "specialist, because its evidence tier is in the integration module")
            row = {"slug": item.slug, "label": item.label, "alt_labels": ";".join(item.synonyms),
                   "kind": tail(kind), "named_by": tail(item.targets("sys:namedBy")[0])}
            others.rows["other-systems"].append(row)
            others.rows["definitions"].append({"slug": item.slug, "definition": item.definition,
                                               "sources": ";".join(tail(k) for k in item.targets("dcterms:source")), "note": ""})
            every.append(row)
        else:
            tables = out.setdefault("table", _read(root, PRICING, ("tables",)))
            sources = {r["key"] for r in _read(root, PRICING, ("sources",)).rows["sources"]}
            if item.slug in {t["slug"] for t in tables.rows["tables"]}:
                raise ChangeRefused(f"the data-product module has a table with the short key {item.slug} already")
            if tables.matches(item.label):
                raise ChangeRefused(f"the data-product module holds the table {item.label} already")
            [system] = item.targets("dp:copiesSystem")
            if tail(system) not in {r["slug"] for r in every}:
                raise ChangeRefused(f"{system} is not a system of the system module")
            [key] = item.targets("dcterms:source")
            if tail(key) not in sources:
                raise ChangeRefused(f"{key} is not a document of data-product/pricing/sources.csv. A new source document "
                                    "needs a specialist, because its evidence tier is in the integration module")
            tables.rows["tables"].append({"slug": item.slug, "name": item.label, "layer": "replica",
                                          "copies_system": tail(system), "kind": "", "classification_test": "",
                                          "classification_reason": "", "serves_measures": "", "source": tail(key)})
    return found, out


def kind_of(changes):
    """The one Kind of the new items, or ChangeRefused when they are of two kinds or are not new items."""
    kinds = {item.kind.name for item in items(changes)}
    if len(kinds) != 1:
        raise ChangeRefused("one apply adds items of one kind, and these are systems and tables. Apply them one "
                            "kind at a time")
    return KINDS[kinds.pop()]


def check_changes(changes, release_root):
    """Raises ChangeRefused when any change does not fit the tables of the release. Writes nothing and runs no
    builder: the propose command calls it on the real release."""
    _edit(changes, Path(release_root).resolve())


def apply_changes(changes, release_root):
    """Writes the new items into the tables of a scratch copy of the release and rebuilds the module with its
    builder. Returns the path of the rebuilt file. Raises ChangeRefused, and writes nothing, when any change does not
    fit the tables. When the builder refuses the changed tables, they stay written in the scratch copy, and
    ChangeRefused carries the builder's message."""
    root = Path(release_root).resolve()
    kind = kind_of(changes)
    _, tables = _edit(changes, root)
    tables[kind.name].write(root)
    try:
        cut._run(f"rebuild the {kind.module} module", [kind.builder, "--write"], root / kind.folder)
    except cut.CutFailed as err:
        raise ChangeRefused(f"the {kind.module} builder refused the changed tables: {err}") from None
    return root / kind.folder / kind.output


def _text(o):
    from rdflib import Literal
    return isinstance(o, Literal) and o.language == LANGUAGE and o.datatype is None


def compare(before, after, kind):
    """The KGCL lines that take the built graph `before` to `after` (files or rdflib Graphs) by adding new items of
    one kind, in the order apply_changes reads them. Raises ChangeRefused when the graphs differ in a way that no
    such line states, naming those differences."""
    from rdflib import Graph, URIRef
    from rdflib.namespace import DCTERMS, RDF, SKOS
    kind = KINDS[kind] if isinstance(kind, str) else kind
    before, after = (g if isinstance(g, Graph) else Graph().parse(str(g), format="turtle") for g in (before, after))
    removed, added = set(before) - set(after), set(after) - set(before)
    unsupported = [f"- {s} {p} {o}" for s, p, o in removed]
    ns = PREFIXES[kind.prefix]
    held = set(before.subjects())
    new = {s for s, p, o in added if p == SKOS.prefLabel and s not in held and str(s).startswith(ns) and len(str(s)) > len(ns)}
    scheme = URIRef(kind.scheme)
    edges = {URIRef(iri(p)): p for p in kind.edges}
    changes, cited, seen = {s: [] for s in new}, set(), set()
    label = {s: str(o) for s, p, o in added if s in new and p == SKOS.prefLabel}
    for s, p, o in added:
        if s == scheme and p == SKOS.hasTopConcept and o in new:
            seen.add((s, p, o))
        elif s in new and (s, p, o) in _expected(kind, s, label[s]):
            seen.add((s, p, o))
        elif s in new and p == SKOS.prefLabel and _text(o):
            changes[s].append(Change("create node", curie(str(s)), text=str(o)))
        elif s in new and p == SKOS.definition and _text(o) and kind.definition:
            changes[s].append(Change("add definition", curie(str(s)), text=str(o)))
        elif s in new and p == SKOS.altLabel and _text(o) and kind.definition:
            changes[s].append(Change("create synonym", curie(str(s)), text=str(o)))
        elif s in new and p in edges and (curie(str(o)) or ":").split(":", 1)[0] == kind.edges[edges[p]][0]:
            changes[s].append(Change("create edge", curie(str(s)), predicate=edges[p], target=curie(str(o))))
            if p == DCTERMS.source:
                cited.add(o)
        elif s not in new:
            continue   # read below, once every new item's documents are known
        else:
            unsupported.append(f"+ {s} {p} {o!r}")
    for s, p, o in added:
        if s in new or (s == scheme and p == SKOS.hasTopConcept and o in new):
            continue
        # A document that no definition cited before gains its type and its title in the system module.
        if kind.name == "system" and s in cited and (p == RDF.type and o == DCTERMS.BibliographicResource
                                                     or p == DCTERMS.title and _text(o)):
            continue
        unsupported.append(f"+ {s} {p} {o!r}")
    for s in sorted(new):
        unsupported += [f"{s} lacks {p} {o!r}, which every {kind.name} has" for _, p, o in
                        sorted(_expected(kind, s, label[s]) - seen)]
    if unsupported:
        shown = sorted(unsupported)[:10]
        raise ChangeRefused(f"the graphs differ in {len(unsupported)} ways that no line of a new {kind.name} states: "
                            + "; ".join(shown))
    order = {"create node": 0, "add definition": 1, "create synonym": 2, "create edge": 3}
    return [write_line(c) for s in sorted(new) for c in sorted(changes[s], key=lambda c: (order[c.kind], write_line(c)))]


def _expected(kind, s, label):
    """The triples the builder writes for every item of the kind, whatever its lines say."""
    from rdflib import Literal, URIRef
    from rdflib.namespace import RDF, SKOS, XSD
    scheme = URIRef(kind.scheme)
    out = {(s, RDF.type, URIRef(t)) for t in kind.types}
    out |= {(s, SKOS.inScheme, scheme), (s, SKOS.topConceptOf, scheme), (scheme, SKOS.hasTopConcept, s),
            (s, SKOS.notation, Literal(tail(curie(str(s))), datatype=XSD.string))}
    if kind.name == "table":
        out |= {(s, URIRef(PREFIXES["dp"] + "fullName"), Literal(label, datatype=XSD.string)),
                (s, URIRef(PREFIXES["dp"] + "sandbox"), Literal(label.startswith(SANDBOX)))}
    return out
