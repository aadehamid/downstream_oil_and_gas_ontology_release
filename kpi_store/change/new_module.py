"""A new module of one of the two patterns the new-module form supports (KPI-DEC-0002, Q4, Q10 form 6 and Q11;
KPI-DEC-0004, item 1).

The patterns are release/module_patterns.py's: a vocabulary (terms with definitions, other names and a hierarchy)
and a reference table (items of a class the ontology holds, each with one value of each of a fixed set of
properties the ontology holds). A new class, a new property or a rule of its own needs a specialist, and the form
says so. What each line says:

    module:<key>,pattern,<vocabulary or reference-table>      facts.csv, the module itself
    module:<key>,title,<its name>
    module:<key>,description,<what it covers>
    module:<key>,source,<the documents that describe it>
    module:<key>,property,<a property, as prefix:name>         a reference table: one row per property, in order

    a term of a vocabulary
        create node term:<key> '<its name>'
        add definition '<what it means>' to term:<key>
        create exact synonym '<another name>' for term:<key>              any number
        create edge term:<key> skos:broader term:<the key of its broader term>   none for a top term
    an item of a reference table
        create node item:<key> '<its name>'
        create edge item:<key> rdf:type <the class, as prefix:name>
        add definition '<text>' to item:<key>                            when skos:definition is a property
        create exact synonym '<text>' for item:<key>                     when skos:altLabel is a property
        create edge item:<key> <property> <an item the release holds>    each property whose value is an item
        facts.csv: item:<key>,<property>,<value>                          each other property: a text or a value

`term:` and `item:` name the new module's own namespace, <https://w3id.org/mpc/ontology/modules/<key>/term/> and
<.../item/>; every other prefix is one that the release's packages bind to one namespace only.

What the propose command calls: from_form (the lines and facts of a signed form) and check_changes (the lines and
facts checked against the release: the pattern's table checks, the module built in memory, and every shape of the
release run over it with the packages it requires). What the apply command calls: write (the module's folder,
written into a scratch copy and registered in every place by release/register_module.py), and compare (the round
trip: the built module read back into lines and facts). A module's first release is 1.0.0, a major, and needs the
Ontology Owner's signature beside the Data Owner's and the Architect's.
"""
import ast
import importlib.util
import re
from pathlib import Path

from .. import cut
from . import ChangeRefused, kgcl
from .kgcl import Change

BASE = "https://w3id.org/mpc/ontology/"
MODULES_NS = BASE + "modules/"
SKOS = "http://www.w3.org/2004/02/skos/core#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XSD = "http://www.w3.org/2001/XMLSchema#"
DCTERMS = "http://purl.org/dc/terms/"
SH = "http://www.w3.org/ns/shacl#"
STANDARD_PREFIXES = {"rdf": RDF, "rdfs": RDFS, "owl": OWL, "xsd": XSD, "skos": SKOS, "dcterms": DCTERMS}
VOCABULARY, REFERENCE_TABLE = "vocabulary", "reference-table"
VERSION = "1.0.0"
OWNER_WORDS = "The Ontology Owner"
SUBJECT = "module:"
FACTS = ("pattern", "title", "description", "source", "property")
# The properties any reference table may pick, beside those the ontology defines: (label, kind, datatype, range).
STANDARD = {SKOS + "definition": ("definition", "text", "", ""),
            SKOS + "altLabel": ("other name", "text", "", ""),
            SKOS + "notation": ("code", "typed", XSD + "string", ""),
            DCTERMS + "source": ("source document", "item", "", DCTERMS + "BibliographicResource"),
            DCTERMS + "date": ("date", "typed", XSD + "date", ""),
            SKOS + "inScheme": ("list it is in", "item", "", SKOS + "ConceptScheme")}
GENERAL = {SKOS + "Concept", OWL + "Thing", RDFS + "Resource"}   # a property of these is no property of a class's own
# The modules whose classes a reference table does not offer, and why. Their items come through a form of their own,
# from the process authority, or are records kept outside the ontology.
NOT_OFFERED = {"core": "the process map request adds processes", "kpi": "the KPI intake form adds measures",
               "system": "the reference-item form adds systems", "organization": "the process map request adds roles",
               "data-product": "the data-product catalog comes from the process authority",
               "value-stream": "the value streams come from the process authority",
               "integration": "the integration module holds rules about other modules",
               "technical-graph": "its classes describe records kept outside the ontology",
               "logical-model": "its classes describe logical data models"}
NAME_LIMIT = 40   # the module's key names a folder, a package and a prefix


# ---- the release's own pattern code ------------------------------------------------------------------

def _load(root, name):
    """A script of the release's release/ folder, loaded from that release: the patterns and the places are the
    release's own, so a scratch copy registers the module with the copy's code."""
    path = Path(root) / cut.ONTOLOGY / "release" / f"{name}.py"
    if not path.is_file():
        raise ChangeRefused(f"{path.relative_to(root).as_posix()} is missing: this release cannot make a new module")
    spec = importlib.util.spec_from_file_location(f"_kpi_store_{name}_{abs(hash(str(path)))}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def patterns(root):
    return _load(root, "module_patterns")


def places(root):
    return _load(root, "register_module")


# ---- what the release holds ---------------------------------------------------------------------------

class Release:
    """The newest package of every module, parsed once, with the names a new module may use. Needs rdflib."""

    def __init__(self, root, graphs=None):
        from rdflib import Graph
        from kpi_store import ontology_view as ov
        self.root = Path(root)
        if graphs is None:
            versions = ov.newest_versions(self.root / ov.RELEASES)
            graphs = {m: Graph().parse(str(self.root / ov.RELEASES / m / v / f"{m}.ttl"), format="turtle")
                      for m, v in versions.items()}
        self.graphs = graphs
        self.union = Graph()
        for g in graphs.values():
            self.union += g
        bound = {}
        for g in graphs.values():
            for prefix, ns in g.namespaces():
                bound.setdefault(prefix, set()).add(str(ns))
        self.prefixes = dict(STANDARD_PREFIXES)
        for prefix, held in bound.items():
            if len(held) == 1 and prefix not in self.prefixes and prefix not in ("term", "item") \
                    and next(iter(held)).startswith(BASE):
                self.prefixes[prefix] = next(iter(held))

    def curie(self, iri):
        """An IRI as prefix:name, or None when no prefix of the release writes it."""
        fits = [(len(ns), p) for p, ns in self.prefixes.items()
                if str(iri).startswith(ns) and re.fullmatch(r"[A-Za-z0-9_.-]+", str(iri)[len(ns):])]
        if not fits:
            return None
        n, prefix = max(fits)
        return f"{prefix}:{str(iri)[n:]}"

    def expand(self, curie):
        prefix, _, local = curie.partition(":")
        if prefix not in self.prefixes or not local:
            raise ChangeRefused(f"{curie} is not a name the release's prefixes write")
        return self.prefixes[prefix] + local

    def label(self, iri):
        from rdflib import URIRef
        for p in (SKOS + "prefLabel", RDFS + "label", DCTERMS + "title"):
            values = sorted(str(o) for o in self.union.objects(URIRef(iri), URIRef(p)))
            if values:
                return values[0]
        return str(iri).rstrip("/").rsplit("/", 1)[-1]

    def defined_in(self, iri):
        """The modules whose newest package gives the IRI a type."""
        from rdflib import URIRef
        return sorted(m for m, g in self.graphs.items() if (URIRef(iri), URIRef(RDF + "type"), None) in g)

    def deprecated(self, iri):
        from rdflib import Literal, URIRef
        return (URIRef(iri), URIRef(OWL + "deprecated"), Literal(True)) in self.union

    def supers(self, cls):
        """The class and every class above it."""
        from rdflib import URIRef
        out, todo = set(), [URIRef(cls)]
        while todo:
            c = todo.pop()
            if str(c) not in out:
                out.add(str(c))
                todo += list(self.union.objects(c, URIRef(RDFS + "subClassOf")))
        return out


def offered_classes(release):
    """The classes a reference table may hold items of: a class with a name and a definition, of a module that
    NOT_OFFERED does not leave out, that a package other than ref-mpc gives items already. ref-mpc is left out
    because company-specific instances live there only (MODULES.md, "Three kinds of content"). Each item names its
    module."""
    from rdflib import URIRef
    out = []
    for module, g in sorted(release.graphs.items()):
        if module in NOT_OFFERED:
            continue
        for c in sorted(set(g.subjects(URIRef(RDF + "type"), URIRef(OWL + "Class")))):
            if not isinstance(c, URIRef) or release.deprecated(c) or not (c, URIRef(SKOS + "definition"), None) in g:
                continue
            if not any((None, URIRef(RDF + "type"), c) in held for m, held in release.graphs.items() if m != "ref-mpc"):
                continue
            curie = release.curie(c)
            if curie:
                out.append({"id": str(c), "label": f"{release.label(c)} ({curie})", "module": module})
    return out


def offered_properties(release, classes=None):
    """The properties a reference table may pick: the standard few, and each property of the release with a name,
    one domain that is an offered class or a class above one, and a range a value can be written for."""
    from rdflib import URIRef
    classes = offered_classes(release) if classes is None else classes
    above = set()
    for c in classes:
        above |= release.supers(c["id"]) - GENERAL
    out = [{"id": iri, "label": f"{label} ({release.curie(iri)})", "kind": kind, "datatype": datatype, "range": rng,
            "domain": ""} for iri, (label, kind, datatype, rng) in STANDARD.items()]
    for kind_class, kind in ((OWL + "ObjectProperty", "item"), (OWL + "DatatypeProperty", "typed")):
        for p in sorted(set(release.union.subjects(URIRef(RDF + "type"), URIRef(kind_class)))):
            domains = sorted(str(d) for d in release.union.objects(p, URIRef(RDFS + "domain")))
            ranges = sorted(str(r) for r in release.union.objects(p, URIRef(RDFS + "range")))
            curie = release.curie(p)
            if not curie or release.deprecated(p) or len(domains) != 1 or domains[0] not in above or len(ranges) > 1 \
                    or not (p, URIRef(RDFS + "label"), None) in release.union:
                continue
            rng = ranges[0] if ranges else ""
            if kind == "typed":
                k, datatype = ("text", "") if rng in ("", RDF + "langString") else ("typed", rng)
                if k == "typed" and not rng.startswith(XSD):
                    continue
                out.append({"id": str(p), "label": f"{release.label(p)} ({curie})", "kind": k, "datatype": datatype,
                            "range": "", "domain": domains[0]})
            else:
                out.append({"id": str(p), "label": f"{release.label(p)} ({curie})", "kind": "item", "datatype": "",
                            "range": rng, "domain": domains[0]})
    return out


# ---- from the form ------------------------------------------------------------------------------------

def slug(text):
    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))


def module_key(title):
    return slug(title)


def _one(answers, key):
    from kpi_store.intake import rules
    return "".join(rules.values(answers, key)[:1])


def from_form(answers, root):
    """The short key of the new module, and the KGCL changes, the facts and the notes for the Architect of a signed
    new-module form. Raises ChangeRefused, in plain words, for an answer the patterns cannot take."""
    from kpi_store.intake import rules
    straight = lambda text: text.replace(kgcl.TYPOGRAPHIC, "'").strip()
    title, pattern = straight(_one(answers, "N1")), _one(answers, "N3")
    key = module_key(title)
    if not key:
        raise ChangeRefused(f'N1: "{title}" has no letter or digit to make the module\'s short key from')
    if pattern not in (VOCABULARY, REFERENCE_TABLE):
        raise ChangeRefused("N3: a module that is not a vocabulary or a reference table needs a specialist")
    m = SUBJECT + key
    sources = [straight(s) for s in rules.values(answers, "N12")]
    facts = [(m, "pattern", pattern), (m, "title", title), (m, "description", straight(_one(answers, "N2"))),
             (m, "source", "; ".join(sources))]
    changes = []
    if pattern == VOCABULARY:
        names = [straight(n) for n in rules.positions(answers, "N4")]
        definitions, others, broader = (rules.positions(answers, q) for q in ("N5", "N6", "N7"))
        at = lambda values, i: straight(values[i]) if i < len(values) else ""
        keys = {}
        for i, name in enumerate(names):
            if not name:
                continue
            k = slug(name)
            if not k:
                raise ChangeRefused(f'N4: "{name}" has no letter or digit to make the term\'s short key from')
            if k in keys.values():
                raise ChangeRefused(f'N4: "{name}" has the short key {k}, as another term has. Give each term a name of its own')
            keys[name.casefold()] = k
        for i, name in enumerate(names):
            if not name:
                continue
            s = f"term:{keys[name.casefold()]}"
            changes += [Change("create node", s, text=name), Change("add definition", s, text=at(definitions, i))]
            changes += [Change("create synonym", s, text=o.strip()) for o in at(others, i).split(";") if o.strip()]
            up = at(broader, i)
            if up:
                if up.casefold() not in keys:
                    raise ChangeRefused(f'N7: "{name}" is under "{up}", which is not a term of N4. Name a term of this list')
                changes.append(Change("create edge", s, predicate="skos:broader", target=f"term:{keys[up.casefold()]}"))
        if not changes:
            raise ChangeRefused("N4 names no term")
        return key, changes, facts, []
    release = Release(root)
    cls = _one(answers, "N8")
    cls_curie = release.curie(cls)
    if not cls_curie:
        raise ChangeRefused(f"N8 names {cls}, which no prefix of the release writes; it needs a specialist")
    props = rules.real_values(answers, "N9")
    for p in props:
        curie = release.curie(p)
        if not curie:
            raise ChangeRefused(f"N9 names {p}, which no prefix of the release writes; it needs a specialist")
        facts.append((m, "property", curie))
    offered = {o["id"]: o for o in offered_properties(release)}
    names = [straight(n) for n in rules.positions(answers, "N10")]
    values = rules.positions(answers, "N11")
    used = {}
    for i, name in enumerate(names):
        if not name:
            continue
        k = slug(name)
        if not k or k in used:
            raise ChangeRefused(f'N10: "{name}" has no letter or digit, or the same short key as "{used.get(k, "")}"'
                                ". Give each item a name of its own")
        used[k] = name
        s = f"item:{k}"
        cells = [straight(c) for c in values[i].split("|")] if i < len(values) and values[i].strip() else []
        if len(cells) != len(props):
            raise ChangeRefused(f'N11: "{name}" has {len(cells)} value{"s" if len(cells) != 1 else ""}, and N9 picks '
                                f'{len(props)} propert{"ies" if len(props) != 1 else "y"}. Write one value for each, in the '
                                'order of N9, with a vertical bar (|) between them')
        changes += [Change("create node", s, text=name), Change("create edge", s, predicate="rdf:type", target=cls_curie)]
        for p, cell in zip(props, cells):
            info = offered.get(p)
            if info is None:
                raise ChangeRefused(f"N9 names {release.label(p)}, which the form does not offer for a reference table")
            curie = release.curie(p)
            if p == SKOS + "definition":
                changes.append(Change("add definition", s, text=cell))
            elif p == SKOS + "altLabel":
                changes.append(Change("create synonym", s, text=cell))
            elif info["kind"] == "item":
                changes.append(Change("create edge", s, predicate=curie, target=_item_named(release, info, cell, name)))
            else:
                facts.append((s, curie, cell))
    if not used:
        raise ChangeRefused("N10 names no item")
    return key, changes, facts, []


def _items_of(release, cls):
    from rdflib import URIRef
    if not cls:
        return set(release.union.subjects())
    return set(release.union.subjects(URIRef(RDF + "type"), URIRef(cls)))


def _item_named(release, info, text, name):
    """The item of the property's range that a value names: by its IRI, the last part of its IRI, or its name."""
    folded = text.casefold()
    hits = sorted({str(i) for i in _items_of(release, info["range"])
                   if folded in (str(i).casefold(), str(i).rstrip("/").rsplit("/", 1)[-1].casefold(),
                                 release.label(i).casefold())})
    if len(hits) != 1:
        what = release.label(info["range"]) if info["range"] else "item"
        raise ChangeRefused(f'N11: "{name}" gives {info["label"]} the value "{text}", which names '
                            f'{"no" if not hits else len(hits)} {what}{"s" if len(hits) > 1 else ""} of the ontology. '
                            "Write its name as the ontology holds it, or the last part of its IRI")
    curie = release.curie(hits[0])
    if not curie:
        raise ChangeRefused(f"N11: {hits[0]} is a name no prefix of the release writes; it needs a specialist")
    return curie


# ---- the lines and facts, read back into the pattern's settings and table --------------------------------

def is_new_module(facts):
    return any(s.startswith(SUBJECT) for s, _, _ in facts)


def _modules_table(root):
    return cut._modules(Path(root) / cut.ONTOLOGY / "release" / "build_module.py")


def _taken_prefixes(root):
    path = Path(root) / cut.ONTOLOGY / "projection" / "pipeline.py"
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "PREFIXES":
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise ChangeRefused(f"{path} holds no PREFIXES: it is not a KPI Store release")


def split(changes, facts, root, release=None):
    """The pattern's settings (SPEC) and the table's rows that the lines and facts state, checked against the
    release. Raises ChangeRefused for a line or a fact the pattern does not take."""
    module_facts = [f for f in facts if f[0].startswith(SUBJECT)]
    keys = {s for s, _, _ in module_facts}
    if len(keys) != 1:
        raise ChangeRefused("a new module's facts name one module")
    key = next(iter(keys))[len(SUBJECT):]
    said = {}
    for _, prop, value in module_facts:
        if prop not in FACTS or (prop != "property" and prop in said):
            raise ChangeRefused(f"a new module's facts are one pattern, title, description and source, and the "
                                f"properties of a reference table: {SUBJECT}{key},{prop},{value}")
        said.setdefault(prop, []).append(value)
    missing = [p for p in FACTS[:4] if p not in said or not said[p][0]]
    if missing:
        raise ChangeRefused(f"the new module {key} has no {', no '.join(missing)}")
    pattern = said["pattern"][0]
    if pattern not in (VOCABULARY, REFERENCE_TABLE):
        raise ChangeRefused(f"{pattern!r} is not a pattern of the new-module form; it needs a specialist")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", key) or len(key) > NAME_LIMIT:
        raise ChangeRefused(f"the module's short key {key!r} must be lower-case letters and digits with hyphens, at most "
                            f"{NAME_LIMIT} characters: give the module a shorter name")
    if key != module_key(said["title"][0]):
        raise ChangeRefused(f"the module's short key {key} is not the one its title {said['title'][0]!r} gives")
    root = Path(root)
    if key in _modules_table(root) or (root / cut.ONTOLOGY / key).exists() or \
            (root / cut.ONTOLOGY / "releases" / key).exists():
        raise ChangeRefused(f"the release holds a module or a folder named {key} already. Give the module another name")
    prefix = key.replace("-", "_")
    spec = {"module": key, "pattern": pattern, "prefix": prefix, "title": said["title"][0],
            "description": said["description"][0], "citation": said["source"][0]}
    for text in spec["title"], spec["description"], spec["citation"]:
        problem = kgcl.text_problem(text)
        if problem:
            raise ChangeRefused(f"{problem}: {text!r}")
    if pattern == VOCABULARY:
        if "property" in said or len(facts) != len(module_facts):
            raise ChangeRefused("a vocabulary takes no property and no fact of a term: a term's facts are its lines")
        return spec, _terms(changes)
    release = release or Release(root)
    if prefix in _taken_prefixes(root) or prefix in release.prefixes:
        raise ChangeRefused(f"the prefix {prefix} that the module's name gives is taken. Give the module another name")
    return _reference_table(spec, changes, facts, said.get("property", []), release)


def _terms(changes):
    rows, order = {}, []
    for c in changes:
        prefix, _, k = c.subject.partition(":")
        if prefix != "term":
            raise ChangeRefused(f"a vocabulary's lines are about its terms, term:<key>: {kgcl.write_line(c)}")
        row = rows.setdefault(k, {"term_id": k, "name": "", "definition": "", "other_names": [], "broader": ""})
        if k not in order:
            order.append(k)
        if c.kind == "create node" and not row["name"]:
            row["name"] = c.text
        elif c.kind == "add definition" and not row["definition"]:
            row["definition"] = c.text
        elif c.kind == "create synonym" and ";" not in c.text:
            row["other_names"].append(c.text)
        elif c.kind == "create edge" and c.predicate == "skos:broader" and c.target.startswith("term:") and not row["broader"]:
            row["broader"] = c.target[len("term:"):]
        else:
            raise ChangeRefused("a term takes create node, add definition, other names without a semicolon and at most "
                                f"one skos:broader to a term: {kgcl.write_line(c)}")
    out = []
    for k in order:
        row = rows[k]
        if not row["name"] or not row["definition"]:
            raise ChangeRefused(f"the term term:{k} needs a create node line and an add definition line")
        out.append(dict(row, other_names="; ".join(row["other_names"])))
    return out


def _name_property(release, cls, root):
    """rdfs:label when a shape of the release names the class's items by it, else skos:prefLabel."""
    from rdflib import Graph, URIRef
    from kpi_store import ontology_view as ov
    shapes = Graph()
    for m, v in ov.newest_versions(Path(root) / ov.RELEASES).items():
        shapes.parse(str(Path(root) / ov.RELEASES / m / v / "shapes.ttl"), format="turtle")
    classes = {URIRef(c) for c in release.supers(cls)}
    for shape in {s for c in classes for s in shapes.subjects(URIRef(SH + "targetClass"), c)}:
        for prop in shapes.objects(shape, URIRef(SH + "property")):
            if (prop, URIRef(SH + "path"), URIRef(RDFS + "label")) in shapes:
                return RDFS + "label"
    return SKOS + "prefLabel"


def _owner(release, iri, rng=""):
    """The module that owns an IRI: the integration module for a source document, which gives each its evidence
    tier; else the module whose namespace holds it; else every module that gives it a type."""
    found = release.defined_in(iri)
    if rng == DCTERMS + "BibliographicResource" and "integration" in found:
        return ["integration"]
    own = [m for m in found if str(iri).startswith(f"{MODULES_NS}{m}/")]
    return own or found


def _reference_table(spec, changes, facts, props, release):
    offered = {o["id"]: o for o in offered_properties(release)}
    properties = []
    for curie in props:
        iri = release.expand(curie)
        info = offered.get(iri)
        if info is None or curie in [p["curie"] for p in properties]:
            raise ChangeRefused(f"{curie} is not a property a reference table may pick, or it is picked twice")
        properties.append({"iri": iri, "curie": curie, "label": info["label"], "kind": info["kind"],
                           "datatype": info["datatype"], "range": info["range"], "domain": info["domain"]})
    by_iri = {p["iri"]: p for p in properties}
    rows, order, classes = {}, [], set()
    for c in changes:
        prefix, _, k = c.subject.partition(":")
        if prefix != "item":
            raise ChangeRefused(f"a reference table's lines are about its items, item:<key>: {kgcl.write_line(c)}")
        row = rows.setdefault(k, {"item_id": k, "name": ""})
        if k not in order:
            order.append(k)
        prop = {"add definition": SKOS + "definition", "create synonym": SKOS + "altLabel"}.get(c.kind)
        if c.kind == "create node" and not row["name"]:
            row["name"] = c.text
        elif c.kind == "create edge" and c.predicate == "rdf:type" and "@class" not in row:
            row["@class"] = c.target
            classes.add(c.target)
        elif prop and prop in by_iri and by_iri[prop]["curie"] not in row:
            row[by_iri[prop]["curie"]] = c.text
        elif c.kind == "create edge" and c.predicate in [p["curie"] for p in properties if p["kind"] == "item"] \
                and c.predicate not in row:
            row[c.predicate] = c.target
        else:
            raise ChangeRefused("an item takes create node, one rdf:type, and one value of each picked property: "
                                f"{kgcl.write_line(c)}")
    for subject, curie, value in facts:
        if subject.startswith(SUBJECT):
            continue
        k = subject[len("item:"):] if subject.startswith("item:") else None
        kinds = {p["curie"]: p["kind"] for p in properties}
        if k not in rows or kinds.get(curie) not in ("text", "typed") or curie in rows[k] or \
                release.expand(curie) in (SKOS + "definition", SKOS + "altLabel"):
            raise ChangeRefused(f"a fact of an item gives one text or value of a picked property: {subject},{curie},{value}")
        rows[k][curie] = value
    if len(classes) != 1:
        raise ChangeRefused("every item of a reference table is of one class, named by its rdf:type line")
    cls_curie = classes.pop()
    cls = release.expand(cls_curie)
    offered_classes_ = {c["id"]: c for c in offered_classes(release)}
    if cls not in offered_classes_:
        why = next((w for m, w in NOT_OFFERED.items() if m in release.defined_in(cls)), "")
        raise ChangeRefused(f"{cls_curie} is not a class a reference table may hold items of"
                            + (f": {why}" if why else ". A new class needs a specialist"))
    above = release.supers(cls) - GENERAL
    out = []
    for k in order:
        row = rows[k]
        missing = [p["curie"] for p in properties if p["curie"] not in row]
        if not row["name"] or "@class" not in row or missing:
            raise ChangeRefused(f"the item item:{k} needs a name, its class and a value of {', '.join(missing) or 'each property'}")
        row.pop("@class")
        out.append(row)
    for p in properties:
        if p["domain"] and p["domain"] not in above:
            raise ChangeRefused(f"{p['label']} is a property of {release.label(p['domain'])}, and the items are of "
                                f"{release.label(cls)}")
    depends = set(_owner(release, cls))
    used = {cls_curie.partition(":")[0]} | {p["curie"].partition(":")[0] for p in properties}
    for p in properties:
        depends |= set(_owner(release, p["iri"])) if not p["iri"] in STANDARD else set()
        for row in out:
            if p["kind"] == "item":
                used.add(row[p["curie"]].partition(":")[0])
                depends |= set(_owner(release, release.expand(row[p["curie"]]), p["range"]))
    owner = offered_classes_[cls]["module"]
    spec.update({"class": cls, "class_curie": cls_curie, "class_module": owner,
                 "name_property": _name_property(release, cls, release.root),
                 "properties": [{k: p[k] for k in ("iri", "curie", "label", "kind", "datatype")} for p in properties],
                 "prefixes": {u: release.prefixes[u] for u in sorted(used)},
                 "depends_on": sorted(depends)})
    return spec, out


# ---- the check ----------------------------------------------------------------------------------------

def check_changes(changes, facts, root):
    """Raises ChangeRefused when the new module does not fit the release: a line or a fact the pattern does not
    take, a row the pattern's table checks refuse, or a shape of the release or of the pattern that the module, built
    in memory with the packages it requires, does not meet. Writes nothing. Returns (spec, rows)."""
    from pyshacl import validate
    from rdflib import Graph
    from kpi_store import ontology_view as ov
    root = Path(root).resolve()
    release = Release(root)
    spec, rows = split(changes, facts, root, release)
    mp = patterns(root)
    found = mp.problems(spec, rows, {str(s) for s in release.union.subjects()} if spec["pattern"] == REFERENCE_TABLE else None)
    if found:
        raise ChangeRefused("the module's table does not reconcile: " + "; ".join(found))
    data = mp.build(spec, rows)
    versions = ov.newest_versions(root / ov.RELEASES)
    shapes = Graph().parse(data=mp.shapes_text(spec), format="turtle")
    for m, v in versions.items():
        shapes.parse(str(root / ov.RELEASES / m / v / "shapes.ttl"), format="turtle")
    for m in _closure(spec.get("depends_on", []), root):
        data += release.graphs[m]
    # Only the module's own terms and items are judged here: the packages loaded beside them are not the whole graph,
    # so a shape about the links between other modules may fail on them. The apply command runs the whole-graph gate.
    _, report, _ = validate(data, shacl_graph=shapes, advanced=True)
    found = _violations(report, release, mp.namespace(spec))
    if found:
        raise ChangeRefused("the module does not meet the release's shapes: " + "; ".join(found))
    return spec, rows


def _closure(depends_on, root):
    """The modules the dependencies require, and theirs, from each newest package's manifest."""
    import json
    from kpi_store import ontology_view as ov
    versions = ov.newest_versions(Path(root) / ov.RELEASES)
    out, todo = set(), list(depends_on)
    while todo:
        m = todo.pop()
        if m in out:
            continue
        out.add(m)
        manifest = Path(root) / ov.RELEASES / m / versions[m] / "manifest.json"
        if manifest.is_file():
            todo += list(json.loads(manifest.read_text(encoding="utf-8")).get("depends_on") or {})
    return sorted(out)


def _violations(report, release, own):
    """At most five violations of a SHACL report whose focus is a term or an item of the namespace `own`, each as
    "<the item>: <the shape's message>"."""
    from rdflib import URIRef
    out = []
    for result in report.subjects(URIRef(RDF + "type"), URIRef(SH + "ValidationResult")):
        focus = report.value(result, URIRef(SH + "focusNode"))
        if not str(focus).startswith(own):
            continue
        message = report.value(result, URIRef(SH + "resultMessage"))
        path = report.value(result, URIRef(SH + "resultPath"))
        text = str(message) if message else f"a value of {release.curie(path) or path} is missing or wrong"
        out.append(f"{str(focus)[len(own):].replace('/', ':', 1)}: {text}")
    out = sorted(set(out))
    return out[:5] + ([f"and {len(out) - 5} more"] if len(out) > 5 else [])


# ---- the apply ----------------------------------------------------------------------------------------

def summary_lines(spec, rows):
    """The new module in plain words, for summary.txt."""
    if spec["pattern"] == VOCABULARY:
        text = [f'  - A vocabulary of {len(rows)} term{"s" if len(rows) != 1 else ""}, as a SKOS concept scheme.']
        names = {r["term_id"]: r["name"] for r in rows}
        for r in rows:
            where = f'under "{names[r["broader"]]}"' if r["broader"] else "a top term"
            text.append(f'  - The term "{r["name"]}" ({where}): "{r["definition"]}"')
            if r["other_names"]:
                text.append(f'    Its other names: {r["other_names"]}.')
        return text
    labels = ", ".join(p["label"] for p in spec["properties"]) or "no other property"
    text = [f'  - A reference table of {len(rows)} item{"s" if len(rows) != 1 else ""} of the class {spec["class_curie"]}, '
            f'which the {spec["class_module"]} module defines. Each item has a name and one value of: {labels}.']
    for r in rows:
        cells = "; ".join(f'{p["label"]}: {r[p["curie"]]}' for p in spec["properties"])
        text.append(f'  - The item "{r["name"]}"' + (f" ({cells})." if cells else "."))
    text.append(f'  - It requires the newest {", ".join(spec["depends_on"])}.' if spec["depends_on"] else "")
    return [t for t in text if t]


def changelog(spec, rows, change, date):
    what = (f"{len(rows)} terms as a SKOS concept scheme, each with a definition, its other names and at most one "
            "broader term" if spec["pattern"] == VOCABULARY else
            f"{len(rows)} items of the class `{spec['class_curie']}`, each with a name and one value of each of "
            f"{len(spec['properties'])} properties")
    requires = (f" It requires the newest {', '.join(spec['depends_on'])}." if spec.get("depends_on") else
                " It requires no other module.")
    return (f"# {spec['module']} changelog\n\n## {VERSION} ({date})\n\nThe module's first release, a major. It carries the "
            f"new-module form's proposal {change}, which the Data Owner, the Ontology Owner and the Architect signed "
            f"(approvals/{change}.json). The apply command wrote the module from the form's {spec['pattern']} pattern. "
            f"It holds {what}.{requires} The Ontology Owner owns the module until they name a module owner.\n\n"
            "### Known gaps\n\nNone.\n")


def module_of(spec, rows, change, words, date, root):
    """The release/register_module.py Module of the new module."""
    mp, rm = patterns(root), places(root)
    key, output = spec["module"], mp.OUTPUT[spec["pattern"]]
    files = {"README.md": mp.readme_text(spec, rows, change), mp.TABLE[spec["pattern"]]: mp.table_text(spec, rows),
             mp.builder_name(key): mp.builder_text(spec, change), "shapes.ttl": mp.shapes_text(spec),
             mp.test_name(key): mp.test_text(spec, rows)}
    kind = "vocabulary" if spec["pattern"] == VOCABULARY else "reference table"
    section = (f"### {key}: {spec['title']}\n\n{spec['description']} The module is a {kind} that the new-module form "
               f"made (proposal {change}).\n\n<!-- module: {key} -->\n```turtle parse\n{mp.example(spec, rows)}```\n\n")
    return rm.Module(
        name=key, version=VERSION, prefix=spec["prefix"], title=spec["title"], description=spec["description"],
        approver=OWNER_WORDS, approval=(f"approvals/{change}.json", words), parts=[f"{key}/{output}"],
        shapes=[f"{key}/shapes.ttl"], depends_on=list(spec.get("depends_on", [])), decisions=[f"approvals/{change}.json"],
        files=files, builder=mp.builder_name(key), test=mp.test_name(key), changelog=changelog(spec, rows, change, date),
        question=mp.question(spec), question_heading=spec["title"],
        question_intro=f"The question of the `{key}` module, which the new-module form added (proposal {change}).",
        query_name=f"{key}-content", query=mp.query(spec), regression_files=[output],
        purpose=f"A {kind} made by the new-module form", modules_section=section,
        entry_comment=[f"1.0.0 is the module's first release, which the new-module form's proposal {change} made."])


def write(changes, facts, root, change, words, date):
    """Writes the module's folder into a scratch copy of the release and registers it in every place. Returns the
    module's key. Raises ChangeRefused, and writes nothing, when a part does not fit."""
    root = Path(root).resolve()
    spec, rows = check_changes(changes, facts, root)
    module = module_of(spec, rows, change, words, date, root)
    try:
        places(root).register(module, str(root), date, write=True)
    except Exception as err:   # register_module.Refused: a place is not where the code expects it
        raise ChangeRefused(f"the module cannot be registered: {err}") from None
    return spec["module"]


def spec_of(root, key):
    """The SPEC that a module's builder holds, read without running the builder."""
    mp = patterns(root)
    path = Path(root) / cut.ONTOLOGY / key / mp.builder_name(key)
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "SPEC":
            return ast.literal_eval(node.value)
    raise ChangeRefused(f"{path} holds no SPEC")


def compare(root, key):
    """The KGCL lines and facts that the built module states: its Turtle, read back with the builder's settings.
    Raises ChangeRefused for a triple that no line and no fact of the pattern states."""
    from rdflib import Graph
    root = Path(root)
    mp = patterns(root)
    spec = spec_of(root, key)
    return compare_graph(Graph().parse(str(root / cut.ONTOLOGY / key / mp.OUTPUT[spec["pattern"]]), format="turtle"),
                         spec, mp)


def compare_graph(g, spec, mp):
    """compare for a module's graph and its builder's settings."""
    from rdflib import Literal, URIRef
    key = spec["module"]
    m = SUBJECT + key
    facts = [(m, "pattern", spec["pattern"]), (m, "title", spec["title"]), (m, "description", spec["description"]),
             (m, "source", spec["citation"])] + [(m, "property", p["curie"]) for p in spec.get("properties", [])]
    base, cite = mp.item_base(spec), Literal(spec["citation"], lang="en")
    prefix = "term" if spec["pattern"] == VOCABULARY else "item"
    inverse = {ns: p for p, ns in spec.get("prefixes", {}).items()}

    def curie(iri):
        fits = [ns for ns in inverse if str(iri).startswith(ns)]
        if not fits:
            raise ChangeRefused(f"{iri} is not a name the module's prefixes write")
        ns = max(fits, key=len)
        return f"{inverse[ns]}:{str(iri)[len(ns):]}"
    lines, odd = [], []
    en = lambda o: isinstance(o, Literal) and o.language == "en"
    sch = URIRef(mp.scheme(spec))
    for s, p, o in g:
        s_, p_ = str(s), str(p)
        local = s_[len(base):] if s_.startswith(base) else None
        subject = f"{prefix}:{local}"
        if spec["pattern"] == VOCABULARY and s == sch:
            ok = (p_, o) in ((RDF + "type", URIRef(SKOS + "ConceptScheme")), (SKOS + "prefLabel", Literal(spec["title"], lang="en")),
                             (SKOS + "definition", Literal(spec["description"], lang="en")), (DCTERMS + "bibliographicCitation", cite)) \
                or (p_ == SKOS + "hasTopConcept" and (o, URIRef(SKOS + "topConceptOf"), sch) in g)
        elif local is None:
            ok = False
        elif p_ == DCTERMS + "bibliographicCitation" and spec["pattern"] == VOCABULARY:
            ok = o == cite
        elif spec["pattern"] == VOCABULARY:
            ok = True
            if p_ == SKOS + "prefLabel" and en(o):
                lines.append(Change("create node", subject, text=str(o)))
            elif p_ == SKOS + "definition" and en(o):
                lines.append(Change("add definition", subject, text=str(o)))
            elif p_ == SKOS + "altLabel" and en(o):
                lines.append(Change("create synonym", subject, text=str(o)))
            elif p_ == SKOS + "broader" and str(o).startswith(base):
                lines.append(Change("create edge", subject, predicate="skos:broader", target=f"term:{str(o)[len(base):]}"))
            else:
                ok = (p_, o) in ((RDF + "type", URIRef(SKOS + "Concept")), (SKOS + "inScheme", sch), (SKOS + "topConceptOf", sch)) \
                    or (p_ == SKOS + "notation" and str(o) == local) \
                    or (p_ == SKOS + "narrower" and (o, URIRef(SKOS + "broader"), s) in g)
        else:
            ok = True
            by = {q["iri"]: q for q in spec["properties"]}
            if p_ == spec["name_property"] and en(o):
                lines.append(Change("create node", subject, text=str(o)))
            elif p_ == RDF + "type" and str(o) == spec["class"]:
                lines.append(Change("create edge", subject, predicate="rdf:type", target=spec["class_curie"]))
            elif p_ == SKOS + "definition" and p_ in by and en(o):
                lines.append(Change("add definition", subject, text=str(o)))
            elif p_ == SKOS + "altLabel" and p_ in by and en(o):
                lines.append(Change("create synonym", subject, text=str(o)))
            elif p_ in by and by[p_]["kind"] == "item" and isinstance(o, URIRef):
                lines.append(Change("create edge", subject, predicate=by[p_]["curie"], target=curie(o)))
            elif p_ in by and by[p_]["kind"] in ("text", "typed") and isinstance(o, Literal):
                facts.append((subject, by[p_]["curie"], str(o)))
            else:
                ok = False
        if not ok:
            odd.append(f"{s} {p} {o!r}")
    if odd:
        raise ChangeRefused(f"the {key} module holds {len(odd)} triples that no line and no fact of the new-module "
                            "form states: " + "; ".join(sorted(odd)[:5]))
    return sorted(kgcl.write_line(c) for c in lines), facts
