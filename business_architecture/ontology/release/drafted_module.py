"""The drafted pattern: a module whose classes, properties and shapes an AI drafted (KPI-DEC-0002, Q17(a) and Q19).

The two patterns of module_patterns.py add no class, no property and no rule of meaning. A module that needs one
can be drafted by an AI from a new-module form (kpi_store/ai/draft.py), and goes into the release only after the
five gates of Q19 have passed and the Ontology Owner has signed. This file holds the checks of a draft and the
files of a drafted module, so that the module's own builder and test file run the same checks as the commands, with
no kpi_store code.

A draft is five files in one folder:

    model.ttl        the module's classes, properties and named individuals, every one in the module's namespace
    shapes.ttl       its SHACL shapes, every one in <namespace>shapes/
    questions.json   the competency questions as SPARQL: [{"id", "question", "sparql", "expected"}], where expected
                     is true for an ASK query, or the rows of a SELECT query as lists of texts
    examples.json    {"pass": "<Turtle>", "fail": [{"id", "breaks", "shape", "add", "remove"}]}: example data that
                     must pass, and changes to it that must each break the node shape they name
    summary.json     [{"term", "meaning", "example"}]: the plain-words summary for the signers

What problems() refuses, before any gate: the ontology skill's Step 3 gate (skills/ontology/SKILL.md) as code. Every
class and property has one English label, one English definition and a citation; every property has one domain, one
range and a shape that gives its cardinality; every term is in the module's namespace, so a draft changes nothing the
release holds; every other name it uses is a standard one or a term of a module it requires; every shape targets a
term of the module only; example data names only things of its own; and no query can reach a network.
model.ttl and shapes.ttl each take an allowlist: MODEL_PREDICATES and no blank node, and SHACL_CORE.

The gates that code runs (gates()):

    gate 1   every competency question gives its expected answer over the model, the passing examples and the
             modules the module requires; the passing examples meet the draft's shapes and the required modules'
             shapes; each failing example breaks the node shape it names; and every node shape is broken by one
    gate 2   the OWL 2 RL reasoner of owlrl finds the model, the passing examples and the required modules
             consistent: it reports no contradiction, such as one thing in two disjoint classes; and its closure of them holds no
             triple about a term of the release that its closure of the required modules alone does not hold
    gate 4   the summary gives each class, property and node shape a meaning and an example, in words

Gate 3 (a second model, of another family, reviews the draft) and gate 5 (the Ontology Owner signs, and the release
is 1.0.0) are the work of a model and of people; kpi_store records them in the proposal and the approval record.

A drafted module's folder holds the five files, a README, a builder and a test file. The builder:

    python3 build_<module>.py            # check the draft and run gates 1, 2 and 4
    python3 build_<module>.py --write    # also write model.ttl and shapes.ttl in their canonical form
    python3 build_<module>.py --verify   # fail unless both files are canonical and every gate passes

Needs rdflib, pyshacl and owlrl (owlrl comes with pyshacl).
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY = os.path.dirname(HERE)
NAMESPACES = "https://w3id.org/mpc/ontology/modules/"
DRAFTED = "drafted"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XSD = "http://www.w3.org/2001/XMLSchema#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
DCTERMS = "http://purl.org/dc/terms/"
SH = "http://www.w3.org/ns/shacl#"
STANDARD = {"rdf": RDF, "rdfs": RDFS, "owl": OWL, "xsd": XSD, "skos": SKOS, "dcterms": DCTERMS, "sh": SH}
MODEL, SHAPES, QUESTIONS, EXAMPLES, SUMMARY = "model.ttl", "shapes.ttl", "questions.json", "examples.json", "summary.json"
FILES = (MODEL, SHAPES, QUESTIONS, EXAMPLES, SUMMARY)
LOCAL = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}")
ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,19}")
# The terms of SHACL Core a drafted shape may use (SHACL, W3C Recommendation of 2017-07-20, sections 2 to 4). Nothing
# of SHACL-AF or SHACL-SPARQL, such as sh:rule or sh:sparql, which run code; and no sh:deactivated, which would hide a
# shape from gate 1.
SHACL_CORE = {SH + t for t in (
    "NodeShape", "PropertyShape", "targetClass", "targetNode", "targetSubjectsOf", "targetObjectsOf", "property", "path",
    "inversePath", "alternativePath", "zeroOrMorePath", "oneOrMorePath", "zeroOrOnePath", "class", "datatype", "nodeKind",
    "IRI", "Literal", "BlankNode", "BlankNodeOrIRI", "BlankNodeOrLiteral", "IRIOrLiteral", "minCount", "maxCount",
    "minExclusive", "minInclusive", "maxExclusive", "maxInclusive", "minLength", "maxLength", "pattern", "flags",
    "languageIn", "uniqueLang", "equals", "disjoint", "lessThan", "lessThanOrEquals", "not", "and", "or", "xone", "node",
    "qualifiedValueShape", "qualifiedMinCount", "qualifiedMaxCount", "qualifiedValueShapesDisjoint", "closed",
    "ignoredProperties", "hasValue", "in", "message", "severity", "Violation", "Warning", "Info", "name",
    "description", "order")}
SHAPE_PREDICATES = {RDF + "type", RDF + "first", RDF + "rest", RDFS + "label", RDFS + "comment"}
# The predicates a drafted model may use, and nothing else: names, definitions and notes, the citation, domains,
# ranges, the class and property hierarchy, and disjointness. The module's own properties may also be used, on its own
# individuals. A drafted model holds no blank node: every thing has a name, and its cardinalities live in the shapes.
# Each schema predicate: the kind of module term its subject is, the kind of term its object is (of the module or of a
# module it requires, never a standard term), and the rule in words. A datatype property's range is the one exception:
# an XSD datatype or rdf:langString.
SCHEMA = {RDFS + "subClassOf": ("class", "class", "A module class may be under a class of the module or of a module it requires."),
          OWL + "disjointWith": ("class", "class", "A module class may be disjoint with a class of the module or of a module it requires."),
          RDFS + "subPropertyOf": ("property", "property", "A module property may be under a property of the module or of a module it requires."),
          RDFS + "domain": ("property", "class", "A module property's domain is a class of the module or of a module it requires."),
          RDFS + "range": ("property", "class", "A module property's range is a class of the module or of a module it requires, "
                                                 "or for a datatype property an XSD datatype or rdf:langString.")}
MODEL_PREDICATES = {RDF + "type", RDFS + "label", RDFS + "comment", SKOS + "definition", SKOS + "altLabel",
                    SKOS + "scopeNote", SKOS + "example", DCTERMS + "bibliographicCitation", DCTERMS + "source",
                    RDFS + "domain", RDFS + "range", RDFS + "subClassOf", RDFS + "subPropertyOf", OWL + "disjointWith"}
KINDS = {OWL + "Class": "class", OWL + "ObjectProperty": "property", OWL + "DatatypeProperty": "property",
         OWL + "NamedIndividual": "individual"}
TARGETS = ("targetClass", "targetNode", "targetSubjectsOf", "targetObjectsOf")
LITERAL_RANGES = {RDF + "langString", RDFS + "Literal", RDF + "PlainLiteral"}


class DraftError(Exception):
    """A draft's file cannot be read, or the draft does not have the form the pattern needs. Nothing was written."""


def namespace(spec):
    return f"{NAMESPACES}{spec['module']}/"


def shapes_namespace(spec):
    return namespace(spec) + "shapes/"


def examples_namespace(spec):
    return f"http://example.org/{spec['module']}/"


def prefixes(spec):
    """The prefixes a draft's Turtle and queries may use without declaring them: the standard ones, the module's own,
    shp: for its shapes, ex: for its examples, and those of the release that the module's settings hold."""
    return {**STANDARD, **spec.get("prefixes", {}), spec["prefix"]: namespace(spec), "shp": shapes_namespace(spec),
            "ex": examples_namespace(spec)}


def header(spec):
    return "".join(f"@prefix {p}: <{ns}> .\n" for p, ns in sorted(prefixes(spec).items()))


def builder_name(module):
    return f"build_{module.replace('-', '_')}.py"


def test_name(module):
    return f"test_{module.replace('-', '_')}.py"


# ---- reading a draft --------------------------------------------------------------------------------

class Draft:
    """The five parts of a draft, parsed. `texts` keeps each file's text as read."""

    def __init__(self, spec, texts):
        from rdflib import Graph
        self.spec, self.texts = spec, dict(texts)
        missing = [name for name in FILES if name not in texts]
        if missing:
            raise DraftError(f"the draft has no {', no '.join(missing)}")
        self.model = turtle(spec, texts[MODEL], MODEL)
        self.shapes = turtle(spec, texts[SHAPES], SHAPES)
        self.questions = _json(texts[QUESTIONS], QUESTIONS)
        self.examples = _json(texts[EXAMPLES], EXAMPLES)
        self.summary = _json(texts[SUMMARY], SUMMARY)
        if not isinstance(self.questions, list) or not isinstance(self.summary, list):
            raise DraftError(f"{QUESTIONS} and {SUMMARY} must each hold a JSON list")
        if not isinstance(self.examples, dict) or set(self.examples) != {"pass", "fail"} or \
                not isinstance(self.examples["pass"], str) or not isinstance(self.examples["fail"], list):
            raise DraftError(f'{EXAMPLES} must hold {{"pass": "<Turtle>", "fail": [...]}}')
        self.passing = turtle(spec, self.examples["pass"], f"{EXAMPLES}, pass")
        self.failing = []
        for n, f in enumerate(self.examples["fail"], 1):
            if not isinstance(f, dict) or set(f) != {"id", "breaks", "shape", "add", "remove"} or \
                    not all(isinstance(f[k], str) for k in f):
                raise DraftError(f"{EXAMPLES}, failing example {n}: it must hold exactly id, breaks, shape, add and "
                                 "remove, each a text")
            self.failing.append((f, turtle(spec, f["add"], f"{EXAMPLES}, {f['id']}, add") if f["add"].strip() else Graph(),
                                 turtle(spec, f["remove"], f"{EXAMPLES}, {f['id']}, remove") if f["remove"].strip() else Graph()))

    def named(self):
        """The module's own terms: the IRIs the model gives a triple."""
        from rdflib import URIRef
        return sorted({s for s in self.model.subjects() if isinstance(s, URIRef)})

    def of_kind(self, kind):
        from rdflib import URIRef
        return sorted({s for k, name in KINDS.items() if name == kind
                       for s in self.model.subjects(URIRef(RDF + "type"), URIRef(k)) if isinstance(s, URIRef)})

    def node_shapes(self):
        from rdflib import URIRef
        return sorted({s for s in self.shapes.subjects(URIRef(RDF + "type"), URIRef(SH + "NodeShape"))
                       if isinstance(s, URIRef)})

    def label(self, term):
        from rdflib import URIRef
        for p in (RDFS + "label", SKOS + "prefLabel"):
            for o in sorted(self.model.objects(URIRef(term), URIRef(p)), key=str):
                return str(o)
        return curie(self.spec, term)


def turtle(spec, text, what):
    """A graph from a draft's Turtle, with the prefixes of prefixes() declared first. Raises DraftError."""
    from rdflib import Graph
    try:
        return Graph().parse(data=header(spec) + text, format="turtle")
    except Exception as err:   # rdflib raises several kinds; the message names the line
        raise DraftError(f"{what} is not Turtle that can be read ({type(err).__name__}: {str(err)[:200]})") from None


def _json(text, what):
    try:
        return json.loads(text)
    except ValueError as err:
        raise DraftError(f"{what} is not JSON ({err})") from None


def read(folder, spec):
    """The Draft in a folder that holds the five files."""
    texts = {}
    for name in FILES:
        try:
            with open(os.path.join(folder, name), encoding="utf-8", newline="") as f:
                texts[name] = f.read()
        except (OSError, UnicodeDecodeError) as err:
            raise DraftError(f"{name} cannot be read ({type(err).__name__})") from None
    return Draft(spec, texts)


def curie(spec, iri):
    fits = [(len(ns), p) for p, ns in prefixes(spec).items() if str(iri).startswith(ns) and str(iri) != ns]
    if not fits:
        return str(iri)
    n, p = max(fits)
    return f"{p}:{str(iri)[n:]}"


def expand(spec, text):
    """An IRI from prefix:name with a prefix of prefixes(), or the text as it is."""
    prefix, colon, local = text.partition(":")
    known = prefixes(spec)
    return known[prefix] + local if colon and prefix in known and not local.startswith("//") else text


# ---- the modules a draft rests on --------------------------------------------------------------------

def closure(depends_on, ontology=ONTOLOGY):
    """The modules the module requires, and the modules they require, from each newest package's manifest."""
    sys.path.insert(0, os.path.join(ontology, "release"))
    import newest
    out, todo = set(), list(depends_on)
    while todo:
        m = todo.pop()
        if m in out:
            continue
        out.add(m)
        if not isinstance(m, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", m):
            raise DraftError(f"depends_on names {m!r}, which is not a module's name")
        try:
            manifest = os.path.join(ontology, "releases", m, newest.newest_version(m, ontology), "manifest.json")
            with open(manifest, encoding="utf-8") as f:
                todo += list(json.load(f).get("depends_on") or {})
        except (OSError, ValueError) as err:
            raise DraftError(f"depends_on names {m}, which the release holds no package of ({type(err).__name__})") from None
    return sorted(out)


def context(spec, ontology=ONTOLOGY):
    """(the newest packages of the modules the module requires, joined, and their shapes, joined)."""
    from rdflib import Graph
    sys.path.insert(0, os.path.join(ontology, "release"))
    import newest
    data, shapes = Graph(), Graph()
    for m in closure(spec.get("depends_on", []), ontology):
        folder = os.path.join(ontology, "releases", m, newest.newest_version(m, ontology))
        data.parse(os.path.join(folder, f"{m}.ttl"), format="turtle")
        if os.path.isfile(os.path.join(folder, "shapes.ttl")):
            shapes.parse(os.path.join(folder, "shapes.ttl"), format="turtle")
    return data, shapes


# ---- the form of the draft: the ontology skill's Step 3 gate --------------------------------------------

def parsed_query(spec, text):
    """The query translated by rdflib's parser, which reads \\u escapes first, or DraftError. Refuses any form but SELECT
    and ASK, a dataset clause (FROM, FROM NAMED) and SERVICE anywhere, so a question asks only the graph it is given."""
    from rdflib.plugins.sparql.algebra import translateQuery
    from rdflib.plugins.sparql.parser import parseQuery
    try:
        tree = parseQuery(text)
        query = translateQuery(tree, initNs=prefixes(spec))
    except Exception as err:   # pyparsing and rdflib raise several kinds
        raise DraftError(f"the query cannot be read ({type(err).__name__}: {str(err)[:120]})") from None
    if query.algebra.name not in ("SelectQuery", "AskQuery"):
        raise DraftError("the query must be a SELECT or ASK query")
    names = {c.name for c in _walk(tree)}
    if "ServiceGraphPattern" in names or "DatasetClause" in names:
        raise DraftError("the query uses SERVICE, FROM or FROM NAMED. A competency question asks the graph it is given, "
                         "and nothing else")
    return query


def _walk(x):
    from rdflib.plugins.sparql.parserutils import CompValue
    if isinstance(x, CompValue):
        yield x
    if isinstance(x, dict):
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, (list, tuple, set)) or type(x).__name__ == "ParseResults":
        for v in x:
            yield from _walk(v)


def _iris(x):
    from rdflib import URIRef
    from rdflib.plugins.sparql.parserutils import CompValue
    from rdflib.paths import AlternativePath, InvPath, MulPath, NegatedPath, SequencePath
    if isinstance(x, URIRef):
        yield x
    elif isinstance(x, InvPath):          # ^p
        yield from _iris(x.arg)
    elif isinstance(x, MulPath):          # p+, p*, p?
        yield from _iris(x.path)
    elif isinstance(x, (SequencePath, AlternativePath, NegatedPath)):   # p/q, p|q, !p
        yield from _iris(x.args)
    elif isinstance(x, (CompValue, dict)):
        for v in x.values():
            yield from _iris(v)
    elif isinstance(x, (list, tuple, set)) or type(x).__name__ == "ParseResults":
        for v in x:
            yield from _iris(v)


def _standard(iri):
    return any(str(iri).startswith(ns) for ns in STANDARD.values())


def problems(draft, known, data):
    """Each way the draft does not have the form the pattern needs, as a sentence; empty when it has. `known` is the
    set of IRIs that the modules the module requires hold as subjects, and `data` their packages, joined."""
    from rdflib import BNode, Literal, URIRef
    spec, model, shapes = draft.spec, draft.model, draft.shapes
    ns, shp, ex = namespace(spec), shapes_namespace(spec), examples_namespace(spec)
    out = []
    named = set(draft.named())
    shape_terms = {s for s in shapes.subjects() if isinstance(s, URIRef)}
    if not draft.of_kind("class"):
        out.append(f"{MODEL} defines no class")
    for t in sorted(named):
        local = str(t)[len(ns):] if str(t).startswith(ns) else ""
        if not str(t).startswith(ns) or str(t).startswith(shp):
            out.append(f"{MODEL}: {t} is not a term of the module's namespace {ns}. A draft adds terms of its own, and "
                       "changes no term of the release")
        elif not LOCAL.fullmatch(local):
            out.append(f"{MODEL}: {curie(spec, t)} must have a name of letters, digits, hyphens and underscores, "
                       "starting with a letter")
        kinds = {str(k) for k in model.objects(t, URIRef(RDF + "type"))} & set(KINDS)
        if not kinds:
            out.append(f"{MODEL}: {curie(spec, t)} is not typed as a class, an object property, a datatype property or "
                       "a named individual")
        elif len(kinds) > 1:
            out.append(f"{MODEL}: {curie(spec, t)} is typed as more than one kind of term. Each term is of one kind only")
    for t in sorted(shape_terms):
        if not str(t).startswith(shp):
            out.append(f"{SHAPES}: {t} is not a shape of the module's shapes namespace {shp}")
        elif (t, URIRef(RDF + "type"), URIRef(SH + "NodeShape")) not in shapes:
            out.append(f"{SHAPES}: {curie(spec, t)} must be a node shape: a URI of shp: typed sh:NodeShape. A property "
                       "shape is a blank node reached from a node shape by sh:property")
    for g, name, roots in ((model, MODEL, named), (shapes, SHAPES, shape_terms)):
        reached, todo = set(), list(roots)
        while todo:
            s = todo.pop()
            for o in g.objects(s, None):
                if isinstance(o, BNode) and o not in reached:
                    reached.add(o)
                    todo.append(o)
        if any(isinstance(s, BNode) and s not in reached for s in g.subjects()):
            out.append(f"{name} holds a blank node that no term of the module reaches")
    for t in draft.of_kind("class") + draft.of_kind("property") + draft.of_kind("individual"):
        c = curie(spec, t)
        for p, what in ((RDFS + "label", "label"), (SKOS + "definition", "definition")):
            values = list(model.objects(t, URIRef(p)))
            if len(values) != 1 or not isinstance(values[0], Literal) or values[0].language != "en" or not str(values[0]).strip():
                out.append(f"{MODEL}: {c} must have exactly one English {what} (rdfs:label or skos:definition with @en)")
        if t in draft.of_kind("individual"):
            continue
        if not list(model.objects(t, URIRef(DCTERMS + "bibliographicCitation"))):
            out.append(f"{MODEL}: {c} cites no source (dcterms:bibliographicCitation)")
    individuals = set(draft.of_kind("individual"))
    classes, properties = set(draft.of_kind("class")), set(draft.of_kind("property"))
    required_classes = {c for k in (OWL + "Class", RDFS + "Class") for c in data.subjects(URIRef(RDF + "type"), URIRef(k))
                        if isinstance(c, URIRef) and not _standard(c)}
    required_properties = {c for k in (OWL + "ObjectProperty", OWL + "DatatypeProperty", RDF + "Property")
                           for c in data.subjects(URIRef(RDF + "type"), URIRef(k)) if isinstance(c, URIRef) and not _standard(c)}
    for s_, p_, o_ in model:
        if isinstance(s_, BNode) or isinstance(o_, BNode):
            out.append(f"{MODEL} holds a blank node. A drafted model names every thing it states, and its cardinalities "
                       "live in the shapes; other OWL constructs need a specialist")
        elif str(p_).startswith(ns) and p_ not in named:
            pass   # a name the draft does not define: the check of the names below says so
        elif str(p_).startswith(ns) and p_ not in properties:
            out.append(f"{MODEL} uses {curie(spec, p_)} as a predicate, and it is not a property of the draft")
        elif str(p_).startswith(ns):
            if s_ not in individuals:
                out.append(f"{MODEL} uses the property {curie(spec, p_)} on {curie(spec, s_)}: a draft uses its own "
                           "properties only on the module's own individuals")
        elif str(p_) not in MODEL_PREDICATES:
            out.append(f"{MODEL} uses {curie(spec, p_)}, which a drafted model does not take. It takes names, definitions, "
                       "citations, domains, ranges, rdfs:subClassOf, rdfs:subPropertyOf and owl:disjointWith; other "
                       "modelling needs a specialist")
        elif str(p_) == RDF + "type":
            if not isinstance(o_, URIRef):
                fits = False
            elif s_ in individuals:
                fits = str(o_) == OWL + "NamedIndividual" or o_ in classes or o_ in required_classes
            else:
                fits = str(o_) in KINDS
            if not fits:
                out.append(f"{MODEL} types {curie(spec, s_)} as {curie(spec, o_)}, which a drafted model does not take. "
                           "A class or a property takes only its kind; an individual takes owl:NamedIndividual and a "
                           "class of the module or of a module it requires")
        elif str(p_) in SCHEMA:
            subjects, objects, what = SCHEMA[str(p_)]
            ok_subject = s_ in (classes if subjects == "class" else properties)
            if str(p_) == RDFS + "range" and (s_, URIRef(RDF + "type"), URIRef(OWL + "DatatypeProperty")) in model:
                ok_object = isinstance(o_, URIRef) and (str(o_).startswith(XSD) or str(o_) == RDF + "langString")
            elif objects == "class":
                ok_object = o_ in classes or o_ in required_classes
            else:
                ok_object = o_ in properties or o_ in required_properties
            if not ok_subject or not ok_object:
                out.append(f"{MODEL}: {curie(spec, s_)} {curie(spec, p_)} {curie(spec, o_)} is not taken. {what}")
    for p in draft.of_kind("property"):
        c = curie(spec, p)
        domains, ranges = list(model.objects(p, URIRef(RDFS + "domain"))), list(model.objects(p, URIRef(RDFS + "range")))
        if len(domains) != 1 or len(ranges) != 1 or not all(isinstance(v, URIRef) for v in domains + ranges):
            out.append(f"{MODEL}: {c} must have exactly one rdfs:domain and exactly one rdfs:range, each a named class "
                       "or datatype")
        elif (p, URIRef(RDF + "type"), URIRef(OWL + "ObjectProperty")) in model and \
                (str(ranges[0]).startswith(XSD) or str(ranges[0]) in LITERAL_RANGES):
            out.append(f"{MODEL}: {c} is an object property, so its range is a class, not the datatype "
                       f"{curie(spec, ranges[0])}")
        elif (p, URIRef(RDF + "type"), URIRef(OWL + "DatatypeProperty")) in model and \
                not (str(ranges[0]).startswith(XSD) or str(ranges[0]) in LITERAL_RANGES):
            out.append(f"{MODEL}: {c} is a datatype property, so its range is a datatype, not {curie(spec, ranges[0])}")
        attached = {ps for ns_ in draft.node_shapes() for ps in shapes.objects(ns_, URIRef(SH + "property"))}
        counted = any((ps, URIRef(SH + k), None) in shapes for ps in shapes.subjects(URIRef(SH + "path"), p)
                      if ps in attached for k in ("minCount", "maxCount"))
        if not counted:
            out.append(f"{SHAPES}: no shape gives the cardinality of {c} (a property shape with sh:path {c} and "
                       "sh:minCount or sh:maxCount)")
    if not draft.node_shapes():
        out.append(f"{SHAPES} holds no node shape")
    for g, name in ((model, MODEL), (shapes, SHAPES)):
        for s, p, o in g:
            for term in (p, o):
                if not isinstance(term, URIRef):
                    continue
                if str(term).startswith(ns):
                    if term not in named and term not in shape_terms:
                        out.append(f"{name} names {curie(spec, term)}, which the draft does not define")
                elif str(term).startswith(ex):
                    out.append(f"{name} names the example {curie(spec, term)}: the model and the shapes hold no "
                               "example data")
                elif not _standard(term) and str(term) not in known:
                    out.append(f"{name} names {curie(spec, term)}, which neither the draft nor a module it requires "
                               "defines")
    nodes = set(draft.node_shapes())
    for s, p, o in shapes:
        for term in (p, o):
            if str(term).startswith(SH) and str(term) not in SHACL_CORE:
                out.append(f"{SHAPES} uses {curie(spec, term)}, which is not a term of SHACL Core that the drafted "
                           "pattern takes. A drafted shape uses only SHACL Core constraints, with no rule, no SPARQL "
                           "and no sh:deactivated")
        if not str(p).startswith(SH) and str(p) not in SHAPE_PREDICATES:
            out.append(f"{SHAPES} uses {curie(spec, p)}, which a shape does not take")
        if str(p) in (SH + t for t in TARGETS) and s not in nodes:
            out.append(f"{SHAPES}: {curie(spec, s)} has a target, so it must be a URI of shp: typed sh:NodeShape")
        if str(p) == SH + "property" and s not in nodes:
            out.append(f"{SHAPES}: a property shape is nested under {curie(spec, s)}. Only a node shape of shp: holds "
                       "property shapes, so each rule belongs to one node shape")
        if str(p) == SH + "property" and (not isinstance(o, BNode) or len(set(shapes.subjects(p, o))) > 1):
            out.append(f"{SHAPES}: the property shape {curie(spec, o)} of {curie(spec, s)} must be a blank node that one "
                       "node shape holds")
        if str(p) in (SH + t for t in TARGETS) and not str(o).startswith(ns):
            out.append(f"{SHAPES}: {curie(spec, s)} targets {curie(spec, o)}, which is not a term of the module. A "
                       "drafted shape says nothing of the release's own terms")
    for g, name in [(draft.passing, "the passing examples")] + \
            [(add, f"the failing example {f['id']}") for f, add, _ in draft.failing]:
        if any(isinstance(s, BNode) for s in g.subjects()):
            out.append(f"{EXAMPLES}: {name} give a triple to a blank node. Example data names each thing with a name of "
                       f"the examples namespace {ex} (ex:)")
        for s in set(g.subjects()):
            if isinstance(s, URIRef) and not str(s).startswith(ex):
                out.append(f"{EXAMPLES}: {name} give a triple to {curie(spec, s)}. Example data uses names of the "
                           f"examples namespace {ex} only (ex:), so that it changes nothing the release holds")
    ids = [q.get("id") if isinstance(q, dict) else None for q in draft.questions]
    if not draft.questions:
        out.append(f"{QUESTIONS} holds no competency question")
    for n, q in enumerate(draft.questions, 1):
        if not isinstance(q, dict) or set(q) != {"id", "question", "sparql", "expected"}:
            out.append(f"{QUESTIONS}, question {n}: it must hold exactly id, question, sparql and expected")
            continue
        if not isinstance(q["id"], str) or not ID.fullmatch(q["id"]) or ids.count(q["id"]) > 1:
            out.append(f"{QUESTIONS}, question {n}: the id must be a short name of letters and digits, used once")
        if not isinstance(q["question"], str) or not q["question"].strip() or not isinstance(q["sparql"], str):
            out.append(f"{QUESTIONS}, {q['id']}: the question must be words, and sparql a query")
            continue
        try:
            query = parsed_query(spec, q["sparql"])
        except DraftError as err:
            out.append(f"{QUESTIONS}, {q['id']}: {err}")
            continue
        if not any(str(i).startswith(ns) for i in _iris(query.algebra)):
            out.append(f"{QUESTIONS}, {q['id']}: the query names no term of the module")
        expected = q["expected"]
        if not (expected is True or (isinstance(expected, list) and expected and all(
                isinstance(r, list) and r and all(isinstance(v, str) for v in r) for r in expected))):
            out.append(f"{QUESTIONS}, {q['id']}: expected must be true for an ASK query, or at least one row of texts "
                       "for a SELECT query")
    fail_ids = [f["id"] for f, _, _ in draft.failing]
    node_shapes = set(draft.node_shapes())
    if not draft.failing:
        out.append(f"{EXAMPLES} holds no failing example")
    for f, add, remove in draft.failing:
        if not ID.fullmatch(f["id"]) or fail_ids.count(f["id"]) > 1:
            out.append(f"{EXAMPLES}: the failing example {f['id']!r} needs a short id of its own")
        if not f["breaks"].strip():
            out.append(f"{EXAMPLES}, {f['id']}: breaks must say in words which rule the example breaks")
        if URIRef(expand(spec, f["shape"])) not in node_shapes:
            out.append(f"{EXAMPLES}, {f['id']}: {f['shape']} is not a node shape of {SHAPES}")
        if not len(add) and not len(remove):
            out.append(f"{EXAMPLES}, {f['id']}: the example adds and removes nothing")
        for t in remove:
            if any(isinstance(x, BNode) for x in t) or t not in draft.passing:
                out.append(f"{EXAMPLES}, {f['id']}: it removes a triple that the passing examples do not hold, or one "
                           "with a blank node")
                break
    return sorted(set(out))


# ---- the gates --------------------------------------------------------------------------------------

def _joined(*graphs):
    from rdflib import Graph
    g = Graph()
    for one in graphs:
        g += one
    return g


def _value(term):
    return "" if term is None else str(term)


def answers(draft, data):
    """{question id: (the answer it gave, the answer it expects)}, each as JSON-ready values."""
    out = {}
    for q in draft.questions:
        try:
            result = data.query(parsed_query(draft.spec, q["sparql"]))
        except Exception as err:   # a query rdflib cannot parse or run
            out[q["id"]] = (f"the query fails ({type(err).__name__}: {str(err)[:120]})", q["expected"])
            continue
        if result.type == "ASK":
            got = bool(result.askAnswer)
        else:
            got = sorted([_value(v) for v in row] for row in result)
        expected = q["expected"] if q["expected"] is True else \
            sorted([expand(draft.spec, v) for v in row] for row in q["expected"])
        out[q["id"]] = (got, expected)
    return out


def _report_shapes(report, shapes):
    """{the node shape each violation comes from} and [focus node, message] of each violation of a SHACL report."""
    from rdflib import URIRef
    owner = {ps: ns for ns, ps in shapes.subject_objects(URIRef(SH + "property"))}
    sources, results = set(), []
    for r in report.subjects(URIRef(RDF + "type"), URIRef(SH + "ValidationResult")):
        if report.value(r, URIRef(SH + "resultSeverity")) not in (None, URIRef(SH + "Violation")):
            continue
        source = report.value(r, URIRef(SH + "sourceShape"))
        sources.add(owner.get(source, source))
        results.append((report.value(r, URIRef(SH + "focusNode")), report.value(r, URIRef(SH + "resultMessage"))))
    return sources, results


def _validate(data, shapes, focus=None, advanced=False):
    """(conforms, report) of the shapes over the data, for the focus nodes only when `focus` names them. The draft's
    shapes run without SHACL's advanced features; only the release's own shapes, which a person reviewed, use them."""
    from pyshacl import validate
    # pyshacl adds triples of its own to the shapes graph it is given, so it gets a copy.
    more = {"focus_nodes": focus} if focus is not None else {}
    conforms, report, _ = validate(data, shacl_graph=_joined(shapes), advanced=advanced, allow_warnings=True, **more)
    return conforms, report


def gate_1(draft, data, release_shapes):
    """(passed, the lines that say what each check found)."""
    spec = draft.spec
    lines, ok = [], True
    base = _joined(data, draft.model, draft.passing)
    for qid, (got, expected) in answers(draft, base).items():
        if got == expected:
            lines.append(f"{qid}: gives the answer it expects")
        else:
            ok = False
            lines.append(f"{qid}: expects {json.dumps(expected, ensure_ascii=False)[:300]}, and gives "
                         f"{json.dumps(got, ensure_ascii=False)[:300]}")
    conforms, report = _validate(base, draft.shapes)
    if conforms:
        lines.append("the passing examples meet the draft's shapes")
    else:
        ok = False
        _, results = _report_shapes(report, draft.shapes)
        lines.append("the passing examples break the draft's shapes: " + "; ".join(
            f"{curie(spec, f)}: {m}" for f, m in sorted(results, key=str)[:5]))
    if len(release_shapes):
        # Only the model's terms and the examples are judged: the required modules alone are not the whole graph,
        # so a shape about the links between other modules may fail on them. The apply runs the whole-graph gate.
        own = (namespace(spec), examples_namespace(spec))
        focus = sorted({s for g in (draft.model, draft.passing) for s in g.subjects() if str(s).startswith(own)})
        _, report = _validate(base, release_shapes, focus, advanced=True)
        _, results = _report_shapes(report, release_shapes)
        mine = [(f, m) for f, m in results if str(f).startswith(own)]
        if mine:
            ok = False
            lines.append("the model or the passing examples break a shape of a module the module requires: " + "; ".join(
                f"{curie(spec, f)}: {m}" for f, m in sorted(mine, key=str)[:5]))
        else:
            lines.append("the model and the passing examples meet the shapes of the modules the module requires")
    broken = set()
    for f, add, remove in draft.failing:
        g = _joined(base)
        for t in remove:
            g.remove(t)
        g += add
        conforms, report = _validate(g, draft.shapes)
        sources, _ = _report_shapes(report, draft.shapes)
        shape = expand(spec, f["shape"])
        if not conforms and any(str(s) == shape for s in sources):
            broken.add(shape)
            lines.append(f"{f['id']}: breaks {curie(spec, shape)}, as it should ({f['breaks']})")
        else:
            ok = False
            lines.append(f"{f['id']}: should break {curie(spec, shape)} ({f['breaks']}), and does not")
    for s in draft.node_shapes():
        if str(s) not in broken:
            ok = False
            lines.append(f"no failing example breaks {curie(spec, s)}, so nothing shows that its rules hold")
    return ok, lines


def _closure(graph):
    import owlrl
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(graph)
    return graph


def _link_back(triple, own):
    """True for a link from a release term back into the draft through a property of the release, such as the
    inverse of a property an example uses, or a symmetric one: the release's own axioms make it, and it says nothing
    new of the release term itself. Never rdf:type, owl:sameAs or another standard term, and never a module property."""
    from rdflib import URIRef
    _, p, o = triple
    return isinstance(p, URIRef) and not _standard(p) and not str(p).startswith(own) and \
        isinstance(o, URIRef) and str(o).startswith(own)


def gate_2(draft, data):
    """(passed, the lines). The OWL 2 RL closure of the model, the passing examples and the required modules must be
    consistent, and must hold no triple about a term of the release that the closure of the required modules alone
    does not hold: a draft adds terms of its own, and changes what no term of the release means, by any route."""
    from owlrl.Namespaces import ERRNS
    from rdflib import URIRef
    g = _closure(_joined(data, draft.model, draft.passing))
    errors = sorted(str(o) for o in g.objects(None, ERRNS.error))
    lines = [f"the OWL 2 RL reasoner (owlrl) finds a contradiction: {e}" for e in errors[:5]]
    before = _closure(_joined(data))
    own = (namespace(draft.spec), examples_namespace(draft.spec))
    changed = sorted((t for t in g if isinstance(t[0], URIRef) and not str(t[0]).startswith(own)
                      and not _standard(t[0]) and t[1] != ERRNS.error and t not in before
                      and not _link_back(t, own) and not (str(t[1]) == OWL + "sameAs" and t[0] == t[2])), key=str)
    for s, p, o in changed[:5]:
        lines.append(f"the draft would change the release term {curie(draft.spec, s)}: the reasoner then finds "
                     f"{curie(draft.spec, s)} {curie(draft.spec, p)} {curie(draft.spec, o)}, which the release alone does "
                     "not say")
    if lines:
        return False, lines
    return True, ["the OWL 2 RL reasoner (owlrl) finds the model, the passing examples and the modules the module "
                  "requires consistent, and the draft changes no term of the release"]


def gate_4(draft):
    """(passed, the lines): the summary gives each class, property and node shape a meaning and an example."""
    spec = draft.spec
    wanted = {str(t) for t in draft.of_kind("class") + draft.of_kind("property") + draft.node_shapes()}
    seen, lines, ok = {}, [], True
    for n, e in enumerate(draft.summary, 1):
        if not isinstance(e, dict) or set(e) != {"term", "meaning", "example"} or \
                not all(isinstance(e[k], str) and e[k].strip() for k in e):
            ok = False
            lines.append(f"entry {n} must hold exactly term, meaning and example, each in words")
            continue
        iri = expand(spec, e["term"])
        if iri not in wanted:
            ok = False
            lines.append(f"entry {n} is about {e['term']}, which is no class, property or node shape of the draft")
        elif iri in seen:
            ok = False
            lines.append(f"{e['term']} has two entries")
        seen[iri] = e
    for t in sorted(wanted - set(seen)):
        ok = False
        lines.append(f"{curie(spec, t)} has no entry that says in words what it means, with an example")
    if ok:
        lines.append(f"the summary says what each of the {len(wanted)} new classes, properties and shapes means, "
                     "with an example")
    return ok, lines


GATE_NAMES = {1: "competency questions and examples", 2: "the reasoner finds the model consistent",
              3: "a second model of another family reviewed the draft",
              4: "a plain-words summary for the signers", 5: "the Ontology Owner signs, and the release is 1.0.0"}


def gates(draft, ontology=ONTOLOGY):
    """[{gate, name, passed, results}] of gates 1, 2 and 4, run against the newest packages of the required modules.
    Raises DraftError when the draft does not have the form the pattern needs."""
    data, release_shapes = context(draft.spec, ontology)
    found = problems(draft, {str(s) for s in data.subjects()} | {str(s) for s in release_shapes.subjects()}, data)
    if found:
        raise DraftError("the draft does not have the form the pattern needs:\n  " + "\n  ".join(found))
    out = []
    for n, (passed, lines) in ((1, gate_1(draft, data, release_shapes)), (2, gate_2(draft, data)), (4, gate_4(draft))):
        out.append({"gate": n, "name": GATE_NAMES[n], "passed": passed, "results": lines})
    return out


# ---- the module's files -----------------------------------------------------------------------------

def model_text(spec, graph):
    return (f"# The classes and properties of the {spec['title']} module, drafted by an AI and released after the five\n"
            "# gates of KPI-DEC-0002, Q19. Written by the apply command. Do not edit by hand.\n"
            + _serialized(spec, graph))


def shapes_text(spec, graph):
    return (f"# SHACL shapes of the {spec['title']} module, drafted by an AI and released after the five gates of\n"
            "# KPI-DEC-0002, Q19. Written by the apply command. Do not edit by hand.\n" + _serialized(spec, graph))


def _serialized(spec, graph):
    from rdflib import Graph, Namespace
    g = Graph(bind_namespaces="none")
    g += graph
    used = {str(t) for triple in graph for t in triple}
    for p, ns in sorted(prefixes(spec).items()):
        if any(u.startswith(ns) for u in used):
            g.bind(p, Namespace(ns))
    return g.serialize(format="turtle")


def canonical(draft):
    """{file name: text} of the draft in its canonical form: the Turtle as the builder writes it, the JSON sorted."""
    spec = draft.spec
    dump = lambda value: json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return {MODEL: model_text(spec, draft.model), SHAPES: shapes_text(spec, draft.shapes),
            QUESTIONS: dump(draft.questions), EXAMPLES: dump(draft.examples), SUMMARY: dump(draft.summary)}


def figures(draft):
    return (f"classes {len(draft.of_kind('class'))}; properties {len(draft.of_kind('property'))}; "
            f"node shapes {len(draft.node_shapes())}; questions {len(draft.questions)}; "
            f"failing examples {len(draft.failing)}")


def summary_lines(draft):
    """The plain-words summary, for summary.txt and the README: each new thing, what it means, and an example."""
    spec = draft.spec
    out = []
    kinds = {**{str(t): "class" for t in draft.of_kind("class")}, **{str(t): "property" for t in draft.of_kind("property")},
             **{str(t): "rule" for t in draft.node_shapes()}}
    for e in draft.summary:
        iri = expand(spec, e["term"])
        name = draft.label(iri) if kinds.get(iri) != "rule" else curie(spec, iri)
        out.append(f'  - The {kinds.get(iri, "term")} "{name}" ({curie(spec, iri)}): {e["meaning"]}')
        out.append(f"    For example: {e['example']}")
    return out


def main(folder, spec, argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)
    try:
        draft = read(folder, spec)
        results = gates(draft)
    except (DraftError, OSError) as err:
        sys.exit(str(err))
    print(figures(draft))
    for g in results:
        print(f"gate {g['gate']}, {g['name']}: {'passed' if g['passed'] else 'FAILED'}")
    failed = [g for g in results if not g["passed"]]
    if failed:
        sys.exit("\n".join(line for g in failed for line in g["results"]))
    texts = canonical(draft)
    if args.verify:
        stale = [name for name in (MODEL, SHAPES) if texts[name] != draft.texts[name]]
        if stale:
            sys.exit(f"{' and '.join(stale)} {'is' if len(stale) == 1 else 'are'} not in canonical form: run "
                     f"{builder_name(spec['module'])} --write")
        print(f"{MODEL} and {SHAPES} are current")
    if args.write:
        for name in (MODEL, SHAPES):
            with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(texts[name])
        print(f"wrote {MODEL} and {SHAPES}")


def _in_docstring(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def builder_text(spec, change):
    name = builder_name(spec["module"])
    return f'''"""Build the {_in_docstring(spec['title'])} module, of the drafted pattern (written by the apply command).

    python3 {name}            # check the draft and run gates 1, 2 and 4
    python3 {name} --write    # also write {MODEL} and {SHAPES} in their canonical form
    python3 {name} --verify   # fail unless both are canonical and every gate passes

An AI drafted the module's classes, properties and shapes, and the proposal {change} carried them through the five
gates of KPI-DEC-0002, Q19 (business_architecture/ontology/approvals/{change}.json). release/drafted_module.py holds
the checks and the gates. SPEC below holds this module's own settings. Do not edit by hand.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "release"))
import drafted_module  # noqa: E402

SPEC = {json.dumps(spec, indent=4, ensure_ascii=False, sort_keys=True)}

if __name__ == "__main__":
    drafted_module.main(HERE, SPEC)
'''


def test_text(spec):
    return f'''"""Tests for the {_in_docstring(spec['title'])} module (written by the apply command): the build is current, the draft has the
form the pattern needs, its competency questions answer, its examples pass and fail as they should, the reasoner finds
it consistent, and the reasoner does find a contradiction when one is added.

Run: python3 -m pytest {test_name(spec['module'])} (needs rdflib, pyshacl, owlrl).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "release"))
sys.path.insert(0, HERE)
import drafted_module  # noqa: E402
import {builder_name(spec['module'])[:-3]} as built  # noqa: E402


class Module(drafted_module.Checks, unittest.TestCase):
    FOLDER = HERE
    SPEC = built.SPEC


if __name__ == "__main__":
    unittest.main()
'''


def readme_text(spec, draft, change):
    classes = ", ".join(f"`{curie(spec, t)}`" for t in draft.of_kind("class"))
    props = ", ".join(f"`{curie(spec, t)}`" for t in draft.of_kind("property")) or "none"
    return (f"# {spec['module']}: {spec['title']}\n\n{spec['description']}\n\n"
            f"An AI drafted this module's classes ({classes}), properties ({props}) and shapes, and the proposal {change} "
            "carried the draft through the five gates of KPI-DEC-0002, Q19: its competency questions and examples, the "
            "reasoner, a review by a second model of another family, a plain-words summary, and the Ontology Owner's "
            f"signature. Its namespace is `{namespace(spec)}`. The documents it rests on: {spec['citation']}.\n\n"
            "## What the new things mean\n\n" + "\n".join(summary_lines(draft)) + "\n\n"
            "| File | What |\n|---|---|\n"
            f"| `{MODEL}` | The classes and properties |\n| `{SHAPES}` | The shapes, the rules the data must meet |\n"
            f"| `{QUESTIONS}` | The competency questions, as SPARQL with the answers they expect |\n"
            f"| `{EXAMPLES}` | Example data that must pass, and changes to it that must break a shape |\n"
            f"| `{SUMMARY}` | The plain-words summary the signers read |\n"
            f"| `{builder_name(spec['module'])}` | The build. `--verify` runs gates 1, 2 and 4 again. `scripts/check.sh` runs it |\n"
            f"| `{test_name(spec['module'])}` | Tests: the build is current, every gate passes, and the reasoner finds an "
            "added contradiction |\n\n"
            "Change the module with a release of its own, through HOW-TO-UPDATE.md. Do not edit these files by hand.\n")


def question(spec):
    return f"Which classes and properties does the {spec['title']} module define?"


def query(spec):
    return (f"PREFIX rdfs: <{RDFS}>\nSELECT ?term ?label WHERE {{\n  ?term rdfs:label ?label .\n"
            f"  FILTER(STRSTARTS(STR(?term), \"{namespace(spec)}\"))\n}}\n")


def example(spec, draft):
    """Turtle that the module's package holds: the first class and its label."""
    first = draft.of_kind("class")[0]
    label = json.dumps(draft.label(first), ensure_ascii=False)
    return (f"@prefix rdfs: <{RDFS}> .\n@prefix {spec['prefix']}: <{namespace(spec)}> .\n\n"
            f"{curie(spec, first)} rdfs:label {label}@en .\n")


# ---- the test file's checks -------------------------------------------------------------------------

class Checks:
    """The tests of a drafted module. A module's test file sets FOLDER and SPEC."""
    FOLDER = SPEC = None

    def draft(self):
        return read(self.FOLDER, self.SPEC)

    def test_build_is_current(self):
        done = subprocess.run([sys.executable, os.path.join(self.FOLDER, builder_name(self.SPEC["module"])), "--verify"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_every_gate_passes(self):
        failed = [line for g in gates(self.draft()) if not g["passed"] for line in g["results"]]
        self.assertEqual(failed, [])

    def test_the_reasoner_finds_an_added_contradiction(self):
        from rdflib import URIRef
        draft = self.draft()
        draft.passing.add((URIRef(examples_namespace(self.SPEC) + "nothing"), URIRef(RDF + "type"), URIRef(OWL + "Nothing")))
        data, _ = context(self.SPEC)
        self.assertFalse(gate_2(draft, data)[0])
