"""The two module patterns of the new-module form, and the files each pattern gives a module (KPI-DEC-0002, Q10 form
6 and Q11).

    vocabulary        terms with a definition, other names and a place in a hierarchy: a SKOS concept scheme of the
                      module's own, one skos:Concept per term, under at most one other term of the same scheme
    reference-table   items of a class the ontology holds already, each with one value of each of a fixed set of
                      properties the ontology holds already

Neither pattern adds a class, a property or a rule of meaning: a module that needs one is drafted by an AI under
five gates (drafted_module.py), or is a specialist's work (HOW-TO-UPDATE.md, "Onboard another module"). The shapes of each pattern are fixed below; the module's settings
only fill them in.

A module made by a pattern has five files of its own, which the apply command writes from a proposal
(kpi_store/change/new_module.py): a README, the table (terms.csv or items.csv), a builder, the shapes and a test
file. The builder is a few lines: its SPEC block holds the module's settings, and main() below does the work, so
every module of one pattern is built by the same code:

    python3 build_<module>.py            # check the table and print the figures
    python3 build_<module>.py --write    # also write the module's Turtle
    python3 build_<module>.py --verify   # fail unless the Turtle equals a fresh build

The build fails, naming the row, unless every row has a cell for each column, a key, a name and what the pattern needs, no key or name is
used twice, every broader term is a term of the table and no term is under itself, and every value fits its
property: a text, a value of the property's datatype, or an item that the newest package of a module the module
requires holds.

Needs rdflib; the test file needs pyshacl too.
"""
import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY = os.path.dirname(HERE)
NAMESPACES = "https://w3id.org/mpc/ontology/modules/"
SKOS = "http://www.w3.org/2004/02/skos/core#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
CITATION = "http://purl.org/dc/terms/bibliographicCitation"
VOCABULARY, REFERENCE_TABLE = "vocabulary", "reference-table"
PATTERNS = (VOCABULARY, REFERENCE_TABLE)
KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TABLE = {VOCABULARY: "terms.csv", REFERENCE_TABLE: "items.csv"}
OUTPUT = {VOCABULARY: "terms.ttl", REFERENCE_TABLE: "items.ttl"}
TERM_COLUMNS = ("term_id", "name", "definition", "other_names", "broader")
KINDS = ("text", "typed", "item")   # a property's value: English text, a literal of a datatype, or an item by IRI


class TableError(Exception):
    """The module's table does not reconcile. The message names each row that does not."""


def namespace(spec):
    return f"{NAMESPACES}{spec['module']}/"


def scheme(spec):
    return namespace(spec) + "scheme"


def item_base(spec):
    return namespace(spec) + ("term/" if spec["pattern"] == VOCABULARY else "item/")


def builder_name(module):
    return f"build_{module.replace('-', '_')}.py"


def test_name(module):
    return f"test_{module.replace('-', '_')}.py"


def expand(spec, curie):
    prefix, _, local = curie.partition(":")
    if prefix not in spec["prefixes"] or not local:
        raise TableError(f"{curie} is not a name of the form prefix:name with a prefix the module's settings hold")
    return spec["prefixes"][prefix] + local


# ---- the table --------------------------------------------------------------------------------------

def columns(spec):
    if spec["pattern"] == VOCABULARY:
        return list(TERM_COLUMNS)
    return ["item_id", "name"] + [p["curie"] for p in spec["properties"]]


def table_text(spec, rows):
    """The table's text: a header and one row per term or item, with LF line ends."""
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=columns(spec), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def read_table(folder, spec):
    with open(os.path.join(folder, TABLE[spec["pattern"]]), encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != columns(spec):
            raise TableError(f"{TABLE[spec['pattern']]} must have the columns {', '.join(columns(spec))}")
        rows = list(reader)
    for number, row in enumerate(rows, start=2):   # row 1 is the header
        if None in row or None in row.values():
            raise TableError(f"{TABLE[spec['pattern']]}, row {number}: the row must have {len(columns(spec))} cells, "
                             f"one for each column: {', '.join(columns(spec))}")
    return rows


def held_items(spec):
    """Every subject of the newest package of each module the module requires."""
    from rdflib import Graph
    sys.path.insert(0, HERE)
    import newest
    held = set()
    for module in spec.get("depends_on", []):
        version = newest.newest_version(module, ONTOLOGY)
        g = Graph().parse(os.path.join(ONTOLOGY, "releases", module, version, f"{module}.ttl"))
        held |= {str(s) for s in g.subjects()}
    return held


def problems(spec, rows, held=None):
    """Each row that does not reconcile, as a sentence; empty when the table is sound."""
    from rdflib import Literal, URIRef
    key = "term_id" if spec["pattern"] == VOCABULARY else "item_id"
    out = []
    if not rows:
        out.append("the table has no row")
    ids = [r[key] for r in rows]
    names = [r["name"].casefold() for r in rows]
    for r in rows:
        who = r[key] or "(a row with no key)"
        if not KEY.fullmatch(r[key]):
            out.append(f"{who}: the key must be lower-case letters and digits, with hyphens between them")
        if ids.count(r[key]) > 1:
            out.append(f"{who}: the key is used twice")
        if not r["name"].strip() or r["name"] != r["name"].strip():
            out.append(f"{who}: no name, or a name that starts or ends with a space")
        elif names.count(r["name"].casefold()) > 1:
            out.append(f"{who}: the name {r['name']!r} is used twice")
        if spec["pattern"] == VOCABULARY:
            if not r["definition"].strip():
                out.append(f"{who}: no definition")
            others = [o.strip() for o in r["other_names"].split(";")] if r["other_names"] else []
            if any(not o for o in others) or len({o.casefold() for o in others}) != len(others) \
                    or r["name"].casefold() in {o.casefold() for o in others}:
                out.append(f"{who}: an other name is empty, named twice or the term's own name")
            if r["broader"] and r["broader"] not in ids:
                out.append(f"{who}: the broader term {r['broader']} is not a term of the table")
            if r["broader"] == r[key]:
                out.append(f"{who}: the term is under itself")
            continue
        for p in spec["properties"]:
            value = r[p["curie"]]
            if not value or value != value.strip():
                out.append(f"{who}: no value of {p['curie']}, or a value that starts or ends with a space")
            elif p["kind"] == "typed" and Literal(value, datatype=URIRef(p["datatype"])).ill_typed:
                out.append(f"{who}: {value!r} is not a value of the datatype {p['datatype']} that {p['curie']} takes")
            elif p["kind"] == "item":
                try:
                    iri = expand(spec, value)
                except TableError as err:
                    out.append(f"{who}: {err}")
                    continue
                if held is not None and iri not in held:
                    out.append(f"{who}: {value} is not an item of the newest package of "
                               f"{' or '.join(spec['depends_on'])}")
    if spec["pattern"] == VOCABULARY:   # a chain of broader terms must end at a top term
        up = {r[key]: r["broader"] for r in rows}
        for start in up:
            seen, at = set(), start
            while at and at not in seen:
                seen.add(at)
                at = up.get(at, "")
            if at:
                out.append(f"{start}: the chain of broader terms comes back to {at}")
                break
    return out


def load(folder, spec):
    rows = read_table(folder, spec)
    found = problems(spec, rows, held_items(spec) if spec["pattern"] == REFERENCE_TABLE else None)
    if found:
        raise TableError(f"the {spec['module']} table does not reconcile:\n  " + "\n  ".join(found))
    return rows


# ---- the build --------------------------------------------------------------------------------------

def build(spec, rows):
    """The module's graph from its settings and its table."""
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import DCTERMS, RDF, SKOS as S, XSD
    g = Graph()
    base = Namespace(item_base(spec))
    g.bind(spec["prefix"], Namespace(namespace(spec)))
    g.bind("term" if spec["pattern"] == VOCABULARY else "item", base)
    for prefix, ns in sorted(spec.get("prefixes", {}).items()):
        g.bind(prefix, Namespace(ns))
    g.bind("skos", S)
    g.bind("dcterms", DCTERMS)
    cite = Literal(spec["citation"], lang="en")
    if spec["pattern"] == VOCABULARY:
        s = URIRef(scheme(spec))
        g.add((s, RDF.type, S.ConceptScheme))
        g.add((s, S.prefLabel, Literal(spec["title"], lang="en")))
        g.add((s, S.definition, Literal(spec["description"], lang="en")))
        g.add((s, DCTERMS.bibliographicCitation, cite))
        for r in rows:
            t = base[r["term_id"]]
            g.add((t, RDF.type, S.Concept))
            g.add((t, S.inScheme, s))
            g.add((t, S.prefLabel, Literal(r["name"], lang="en")))
            g.add((t, S.notation, Literal(r["term_id"], datatype=XSD.string)))
            g.add((t, S.definition, Literal(r["definition"], lang="en")))
            g.add((t, DCTERMS.bibliographicCitation, cite))
            for other in (o.strip() for o in r["other_names"].split(";") if o.strip()):
                g.add((t, S.altLabel, Literal(other, lang="en")))
            if r["broader"]:
                g.add((t, S.broader, base[r["broader"]]))
                g.add((base[r["broader"]], S.narrower, t))
            else:
                g.add((t, S.topConceptOf, s))
                g.add((s, S.hasTopConcept, t))
        return g
    for r in rows:
        i = base[r["item_id"]]
        g.add((i, RDF.type, URIRef(spec["class"])))
        g.add((i, URIRef(spec["name_property"]), Literal(r["name"], lang="en")))
        for p in spec["properties"]:
            value = r[p["curie"]]
            if p["kind"] == "text":
                o = Literal(value, lang="en")
            elif p["kind"] == "typed":
                o = Literal(value, datatype=URIRef(p["datatype"]))
            else:
                o = URIRef(expand(spec, value))
            g.add((i, URIRef(p["iri"]), o))
    return g


def turtle(spec, rows):
    what = "terms" if spec["pattern"] == VOCABULARY else "items"
    return (f"# The {what} of the {spec['title']} module.\n"
            f"# Built by {builder_name(spec['module'])} from {TABLE[spec['pattern']]}. Do not edit by hand.\n"
            + build(spec, rows).serialize(format="turtle"))


def figures(spec, rows):
    if spec["pattern"] == VOCABULARY:
        return f"terms {len(rows)}; top terms {sum(1 for r in rows if not r['broader'])}"
    return f"items {len(rows)}; properties {len(spec['properties'])}"


def main(folder, spec, argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)
    try:
        rows = load(folder, spec)
    except (TableError, OSError) as err:
        sys.exit(str(err))
    text = turtle(spec, rows)
    output = OUTPUT[spec["pattern"]]
    print(figures(spec, rows))
    if args.verify:
        path = os.path.join(folder, output)
        if not (os.path.exists(path) and open(path, encoding="utf-8").read() == text):
            sys.exit(f"{output} is not current: run {builder_name(spec['module'])} --write")
        print(f"{output} is current")
    if args.write:
        with open(os.path.join(folder, output), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {output}")


# ---- the shapes -------------------------------------------------------------------------------------

def shapes_text(spec):
    """The pattern's shapes, filled in with the module's settings. Each targets only the module's own terms or
    items, so they say nothing of the class's items in other modules."""
    head = (f"# SHACL shapes of the {spec['title']} module: the {spec['pattern']} pattern of release/module_patterns.py,\n"
            "# written by the apply command from the new-module form. Do not edit by hand.\n"
            "@prefix sh: <http://www.w3.org/ns/shacl#> .\n@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
            "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
            f"@prefix shp: <{namespace(spec)}shapes/> .\n\n")
    if spec["pattern"] == VOCABULARY:
        s = scheme(spec)
        return head + (
            "shp:Term a sh:NodeShape ;\n"
            f'    sh:target [ a sh:SPARQLTarget ; sh:select "SELECT ?this WHERE {{ ?this <{SKOS}inScheme> <{s}> }}" ] ;\n'
            "    sh:property [ sh:path skos:prefLabel ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype rdf:langString ;\n"
            '                  sh:languageIn ( "en" ) ; sh:message "A term has one English name." ] ;\n'
            "    sh:property [ sh:path skos:definition ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype rdf:langString ;\n"
            '                  sh:languageIn ( "en" ) ; sh:message "A term has one English definition." ] ;\n'
            "    sh:property [ sh:path skos:notation ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:string ] ;\n"
            "    sh:property [ sh:path skos:altLabel ; sh:datatype rdf:langString ] ;\n"
            "    sh:property [ sh:path skos:broader ; sh:maxCount 1 ; sh:node shp:InScheme ;\n"
            '                  sh:message "A term is under at most one term, of the same vocabulary." ] ;\n'
            "    sh:or ( [ sh:property [ sh:path skos:broader ; sh:minCount 1 ] ]\n"
            f"            [ sh:property [ sh:path skos:topConceptOf ; sh:hasValue <{s}> ] ] ) ;\n"
            '    sh:message "A term is under another term, or a top term of the vocabulary." .\n\n'
            "shp:InScheme a sh:NodeShape ;\n"
            f"    sh:property [ sh:path skos:inScheme ; sh:hasValue <{s}> ] .\n")
    lines = ["shp:Item a sh:NodeShape ;",
             f'    sh:target [ a sh:SPARQLTarget ; sh:select "SELECT ?this WHERE {{ ?this a <{spec["class"]}> . '
             f'FILTER(STRSTARTS(STR(?this), \\"{item_base(spec)}\\")) }}" ] ;',
             f'    sh:property [ sh:path <{spec["name_property"]}> ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype rdf:langString ;',
             '                  sh:languageIn ( "en" ) ; sh:message "An item has one English name." ]']
    for p in spec["properties"]:
        if p["kind"] == "text":
            rule = 'sh:datatype rdf:langString ; sh:languageIn ( "en" )'
        elif p["kind"] == "typed":
            rule = f"sh:datatype <{p['datatype']}>"
        else:
            rule = "sh:nodeKind sh:IRI"
        message = re.sub(r"[^\w ,.-]", "", p["label"].split(" (")[0])   # the label without its prefix:name
        lines[-1] += " ;"
        lines.append(f'    sh:property [ sh:path <{p["iri"]}> ; sh:minCount 1 ; sh:maxCount 1 ; {rule} ;')
        lines.append(f'                  sh:message "An item has one value of {message}." ]')
    return head + "\n".join(lines) + " .\n"


# ---- the module's other files -----------------------------------------------------------------------

def _in_docstring(text):
    """A text as it can stand in a Python docstring of three double quotes."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def builder_text(spec, change):
    name = builder_name(spec["module"])
    output = OUTPUT[spec["pattern"]]
    return f'''"""Build the {_in_docstring(spec['title'])} module, of the {spec['pattern']} pattern (written by the apply command).

    python3 {name}            # check the table and print the figures
    python3 {name} --write    # also write {output}
    python3 {name} --verify   # fail unless {output} equals a fresh build

The {'terms' if spec['pattern'] == VOCABULARY else 'items'} come from {TABLE[spec['pattern']]}, one row each. release/module_patterns.py holds the pattern: the checks of the
table and the build. SPEC below holds this module's own settings, which the apply command wrote from the proposal
{change} (business_architecture/ontology/approvals/{change}.kgcl). Do not edit by hand.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "release"))
import module_patterns  # noqa: E402

SPEC = {json.dumps(spec, indent=4, ensure_ascii=False, sort_keys=True)}

if __name__ == "__main__":
    module_patterns.main(HERE, SPEC)
'''


def test_text(spec, rows):
    key = "term_id" if spec["pattern"] == VOCABULARY else "item_id"
    return f'''"""Tests for the {_in_docstring(spec['title'])} module (written by the apply command): the build is current, the module holds the
table's {len(rows)} {'terms' if spec['pattern'] == VOCABULARY else 'items'}, its shapes accept it, and they reject a {'term' if spec['pattern'] == VOCABULARY else 'item'} that has lost {'its definition' if spec['pattern'] == VOCABULARY else 'a value'}.

Run: python3 -m pytest {test_name(spec['module'])} (needs rdflib, pyshacl).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "release"))
sys.path.insert(0, HERE)
import module_patterns  # noqa: E402
import {builder_name(spec['module'])[:-3]} as built  # noqa: E402


class Module(module_patterns.Checks, unittest.TestCase):
    FOLDER = HERE
    SPEC = built.SPEC
    # Pinned from the proposal: the number of rows and the first row's key and name.
    ROWS = {len(rows)}
    FIRST = ({json.dumps(rows[0][key], ensure_ascii=False)}, {json.dumps(rows[0]["name"], ensure_ascii=False)})


if __name__ == "__main__":
    unittest.main()
'''


def readme_text(spec, rows, change):
    what = "terms" if spec["pattern"] == VOCABULARY else "items"
    if spec["pattern"] == VOCABULARY:
        about = (f"It holds {len(rows)} terms as a SKOS concept scheme, `{spec['prefix']}:scheme`: each term has a name, "
                 "a definition, its other names and at most one broader term of the same scheme.")
    else:
        names = ", ".join(f"`{p['curie']}`" for p in spec["properties"]) or "no other property"
        about = (f"It holds {len(rows)} items of the class `{spec['class_curie']}`, which the `{spec['class_module']}` "
                 f"module defines. Each item has a name and one value of each of these properties: {names}.")
    return (f"# {spec['module']}: {spec['title']}\n\n{spec['description']}\n\n{about} The module follows the "
            f"{spec['pattern']} pattern of the new-module form, and the apply command wrote it from the proposal "
            f"{change}. Its namespace is `{namespace(spec)}`. The documents it rests on: {spec['citation']}.\n\n"
            "| File | What |\n|---|---|\n"
            f"| `{TABLE[spec['pattern']]}` | The table the {what} are built from: one row each |\n"
            f"| `{builder_name(spec['module'])}`, `{OUTPUT[spec['pattern']]}` | The build. `--verify` fails unless "
            f"`{OUTPUT[spec['pattern']]}` equals a fresh build. `scripts/check.sh` runs it |\n"
            "| `shapes.ttl` | The pattern's shapes, filled in for this module |\n"
            f"| `{test_name(spec['module'])}` | Tests: the build is current, the {what} are the table's, and the shapes "
            "reject a broken one |\n\n"
            "Change the module with a release of its own, through HOW-TO-UPDATE.md. Do not edit these files by hand.\n")


def question(spec):
    if spec["pattern"] == VOCABULARY:
        return f"Which terms does the {spec['title']} module hold, and which term is each one under?"
    return f"Which items does the {spec['title']} module list?"


def query(spec):
    if spec["pattern"] == VOCABULARY:
        return (f"PREFIX skos: <{SKOS}>\nSELECT ?term ?name ?broader WHERE {{\n"
                f"  ?term skos:inScheme <{scheme(spec)}> ; skos:prefLabel ?name .\n"
                "  OPTIONAL { ?term skos:broader ?broader }\n}\n")
    return (f"SELECT ?item ?name WHERE {{\n  ?item a <{spec['class']}> ; <{spec['name_property']}> ?name .\n"
            f"  FILTER(STRSTARTS(STR(?item), \"{item_base(spec)}\"))\n}}\n")


def example(spec, rows):
    """Turtle that the module's package holds: the first row's name, and its place in the scheme or its class."""
    first = rows[0]
    literal = json.dumps(first["name"], ensure_ascii=False)
    if spec["pattern"] == VOCABULARY:
        return (f"@prefix skos: <{SKOS}> .\n@prefix {spec['prefix']}: <{namespace(spec)}> .\n"
                f"@prefix term: <{item_base(spec)}> .\n\n"
                f"term:{first['term_id']} skos:inScheme {spec['prefix']}:scheme ;\n    skos:prefLabel {literal}@en .\n")
    return (f"@prefix item: <{item_base(spec)}> .\n\n"
            f"item:{first['item_id']} a <{spec['class']}> ;\n    <{spec['name_property']}> {literal}@en .\n")


# ---- the test file's checks -------------------------------------------------------------------------

class Checks:
    """The tests of a module made by a pattern. A module's test file sets FOLDER, SPEC, ROWS and FIRST."""
    FOLDER = SPEC = ROWS = FIRST = None

    def graphs(self):
        from rdflib import Graph
        data = build(self.SPEC, load(self.FOLDER, self.SPEC))
        return data, Graph().parse(os.path.join(self.FOLDER, "shapes.ttl"))

    def conforms(self, data, shapes):
        from pyshacl import validate
        return validate(data, shacl_graph=shapes, advanced=True)[0]

    def test_build_is_current(self):
        done = subprocess.run([sys.executable, os.path.join(self.FOLDER, builder_name(self.SPEC["module"])), "--verify"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_module_holds_the_table(self):
        rows = load(self.FOLDER, self.SPEC)
        key = "term_id" if self.SPEC["pattern"] == VOCABULARY else "item_id"
        self.assertEqual((len(rows), (rows[0][key], rows[0]["name"])), (self.ROWS, tuple(self.FIRST)))

    def test_the_shapes_accept_the_module(self):
        self.assertTrue(self.conforms(*self.graphs()))

    def test_the_shapes_reject_a_broken_entry(self):
        from rdflib import URIRef
        data, shapes = self.graphs()
        first = URIRef(item_base(self.SPEC) + self.FIRST[0])
        path = URIRef(SKOS + "definition") if self.SPEC["pattern"] == VOCABULARY else \
            URIRef((self.SPEC["properties"] or [{"iri": self.SPEC["name_property"]}])[0]["iri"])
        data.remove((first, path, None))
        self.assertFalse(self.conforms(data, shapes))
