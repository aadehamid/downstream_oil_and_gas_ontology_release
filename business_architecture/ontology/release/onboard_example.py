#!/usr/bin/env python3
"""Onboards one made-up module, `sample-area`, so that HOW-TO-UPDATE.md's "Onboard another module" can be followed
and tested from start to end.

    python3 onboard_example.py --plan     # list every place a new module is registered in; change nothing
    python3 onboard_example.py --write    # write the module's folder and register it in each place

The module is an example and no part of the ontology: three made-up areas, each a concept that covers one process
of the core module. `--write` writes the module's own folder and then adds the module to every place the release
lists its modules. It does not build or release anything: the guide's next commands do that. Read each function
below, and register_module.py's functions, as the pattern for a module of your own: register_module.py has one
function per place, and the new-module form's apply command uses the same functions.

Every change is worked out before the first file is written, so a place that has moved stops the command with
nothing changed. The command refuses a release that holds the module already. Exit 0 when done, 1 when refused.
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import register_module  # noqa: E402
from register_module import Refused, Tree  # noqa: E402,F401  (update_examples.py imports both from here)

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ONT = "business_architecture/ontology"
MODULE = "sample-area"
VERSION = "1.0.0"
NAMESPACE = f"https://w3id.org/mpc/ontology/modules/{MODULE}/"
PREFIX = "sa"
QUESTION = "Which processes does each sample area cover?"
APPROVAL = f"approvals/sample-area-{VERSION}.md"
APPROVAL_WORDS = "Approved as the first release of the made-up sample-area module."


# ---- the module's own folder ------------------------------------------------------------------------

README = f"""# sample-area: a made-up module

The `sample-area` module is an example. `release/onboard_example.py` wrote it to show how a new module joins the
release, and `HOW-TO-UPDATE.md`, "Onboard another module", walks through it. It holds three made-up areas as a SKOS
code list, and the one process of the `core` module that each area covers. Its namespace is `{NAMESPACE}`.

| File | What |
|---|---|
| `vocabulary.ttl`, `shapes.ttl` | The area scheme, the `coversProcess` property, and the shapes: an area has one label, one notation, one definition and at least one process |
| `sample-areas.csv` | The table the areas are built from: one row per area |
| `build_sample_areas.py`, `sample-areas.ttl` | The build. `--verify` fails unless `sample-areas.ttl` equals a fresh build. `scripts/check.sh` runs it |
| `test_sample_areas.py` | Tests: the build is current, the three areas are the table's, and SHACL rejects an area with no process |
"""

VOCABULARY = f"""# The sample-area module's vocabulary: three made-up areas and the process each covers. An example,
# written by release/onboard_example.py. Processes are concepts of the core process scheme, by IRI.
@prefix {PREFIX}: <{NAMESPACE}> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

{PREFIX}:SampleAreas a skos:ConceptScheme ;
    rdfs:label "sample areas"@en ;
    skos:definition "The made-up areas of the onboarding example. They stand for the areas of a new data domain."@en ;
    dcterms:bibliographicCitation "{ONT}/sample-area/sample-areas.csv, a made-up table"@en .

{PREFIX}:SampleArea a owl:Class ;
    rdfs:label "sample area"@en ;
    skos:definition "One made-up area of the onboarding example."@en ;
    dcterms:bibliographicCitation "{ONT}/sample-area/sample-areas.csv, a made-up table"@en .

{PREFIX}:coversProcess a owl:ObjectProperty ;
    rdfs:label "covers process"@en ;
    rdfs:domain skos:Concept ; rdfs:range skos:Concept ;
    skos:definition "A process of the core module that the sample area covers."@en ;
    dcterms:bibliographicCitation "{ONT}/sample-area/sample-areas.csv, column covers_process; competency question 58"@en .
"""

SHAPES = f"""# SHACL shapes for the made-up sample-area module, written by release/onboard_example.py.
@prefix {PREFIX}: <{NAMESPACE}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix shp: <{NAMESPACE}shapes/> .

shp:Area a sh:NodeShape ;
    sh:targetClass {PREFIX}:SampleArea ;
    sh:property [ sh:path skos:inScheme ; sh:minCount 1 ; sh:maxCount 1 ; sh:hasValue {PREFIX}:SampleAreas ;
                  sh:message "A sample area is in the sample areas scheme." ] ;
    sh:property [ sh:path skos:prefLabel ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype rdf:langString ] ;
    sh:property [ sh:path skos:notation ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:string ] ;
    sh:property [ sh:path skos:definition ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype rdf:langString ] ;
    sh:property [ sh:path {PREFIX}:coversProcess ; sh:minCount 1 ; sh:nodeKind sh:IRI ;
                  sh:message "A sample area covers at least one process." ] .
"""

TABLE = """area_id,name,definition,covers_process
north-yard,North yard,"The made-up north yard, which stands for the first area of a new data domain.",CM-1-2-1
south-yard,South yard,"The made-up south yard, which stands for the second area of a new data domain.",CM-1-2-2
river-dock,River dock,"The made-up river dock, which stands for the third area of a new data domain.",CM-1-2-3
"""

BUILDER = f'''"""Build the made-up sample-area module (written by release/onboard_example.py).

    python3 build_sample_areas.py            # check the table and print the figures
    python3 build_sample_areas.py --write    # also write sample-areas.ttl
    python3 build_sample_areas.py --verify   # fail unless sample-areas.ttl equals a fresh build

The areas come from sample-areas.csv, one row each. The build fails unless every area has a name and a definition,
no area is named twice, and every process a row names is in the newest core.
"""
import argparse
import csv
import os
import sys

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import DCTERMS, RDF, SKOS, XSD

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "release"))
import newest  # noqa: E402
CORE = newest.core_file()
TABLE = os.path.join(HERE, "sample-areas.csv")
OUTPUT = os.path.join(HERE, "sample-areas.ttl")

SA = Namespace("{NAMESPACE}")
AREA = Namespace("{NAMESPACE}area/")
PROC = Namespace("https://w3id.org/mpc/ontology/process/")


def load():
    with open(TABLE, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    core = Graph().parse(CORE)
    processes = {{str(s) for s in core.subjects(RDF.type, SKOS.Concept)}}
    problems = [f"{{r['area_id']}}: no name or no definition" for r in rows if not (r["name"] and r["definition"])]
    problems += [f"{{r['area_id']}}: process {{r['covers_process']}} is not in the newest core" for r in rows
                 if str(PROC[r["covers_process"]]) not in processes]
    if len({{r["area_id"] for r in rows}}) != len(rows):
        problems.append("an area is named twice")
    if problems:
        sys.exit("the sample-area table does not reconcile:\\n  " + "\\n  ".join(problems))
    return rows


def build(rows):
    g = Graph()
    for prefix, ns in (("{PREFIX}", SA), ("area", AREA), ("proc", PROC), ("skos", SKOS), ("dcterms", DCTERMS)):
        g.bind(prefix, ns)
    for row in rows:
        iri = AREA[row["area_id"]]
        g.add((iri, RDF.type, SKOS.Concept))
        g.add((iri, RDF.type, SA.SampleArea))
        g.add((iri, SKOS.inScheme, SA.SampleAreas))
        g.add((iri, SKOS.topConceptOf, SA.SampleAreas))
        g.add((SA.SampleAreas, SKOS.hasTopConcept, iri))
        g.add((iri, SKOS.prefLabel, Literal(row["name"], lang="en")))
        g.add((iri, SKOS.notation, Literal(row["area_id"], datatype=XSD.string)))
        g.add((iri, SKOS.definition, Literal(row["definition"], lang="en")))
        # The source is a citation in words. A dcterms:source would need an evidence tier in the integration module.
        g.add((iri, DCTERMS.bibliographicCitation, Literal("{ONT}/sample-area/sample-areas.csv, a made-up table", lang="en")))
        g.add((iri, SA.coversProcess, PROC[row["covers_process"]]))
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    rows = load()
    text = ("# The areas of the made-up sample-area module.\\n"
            "# Built by build_sample_areas.py from sample-areas.csv. Do not edit by hand.\\n"
            + build(rows).serialize(format="turtle"))
    print(f"areas {{len(rows)}}; covered processes {{len({{r['covers_process'] for r in rows}})}}")
    if args.verify:
        if not (os.path.exists(OUTPUT) and open(OUTPUT, encoding="utf-8").read() == text):
            sys.exit("sample-areas.ttl is not current: run build_sample_areas.py --write")
        print("sample-areas.ttl is current")
    if args.write:
        with open(OUTPUT, "w", encoding="utf-8", newline="\\n") as f:
            f.write(text)
        print("wrote sample-areas.ttl")


if __name__ == "__main__":
    main()
'''

TEST = '''"""Tests for the made-up sample-area module: the build is current, the areas are the table's three, and SHACL
accepts the module and rejects an area with no process.

Run: python3 -m pytest test_sample_areas.py (needs rdflib, pyshacl).
"""
import os
import subprocess
import sys
import unittest

from pyshacl import validate
from rdflib import Graph, Literal
from rdflib.namespace import RDF, SKOS, XSD

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_sample_areas as bs  # noqa: E402

VOCAB = Graph().parse(os.path.join(HERE, "vocabulary.ttl"))
SHAPES = Graph().parse(os.path.join(HERE, "shapes.ttl"))


def conforms(data):
    return validate(data + VOCAB, shacl_graph=SHAPES, advanced=True)[0]


class Build(unittest.TestCase):
    def test_build_is_current(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_sample_areas.py"), "--verify"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_three_areas_and_their_processes(self):
        # Pinned by hand from sample-areas.csv.
        areas = bs.build(bs.load())
        self.assertEqual({(str(s)[len(str(bs.AREA)):], str(o)[len(str(bs.PROC)):]) for s, o in areas.subject_objects(bs.SA.coversProcess)},
                         {("north-yard", "CM-1-2-1"), ("south-yard", "CM-1-2-2"), ("river-dock", "CM-1-2-3")})
        self.assertEqual(len(set(areas.subjects(SKOS.inScheme, bs.SA.SampleAreas))), 3)


class Shapes(unittest.TestCase):
    def test_the_module_conforms(self):
        self.assertTrue(conforms(bs.build(bs.load())))

    def test_an_area_with_no_process_is_rejected(self):
        data = bs.build(bs.load())
        extra = bs.AREA["no-process"]
        for p, o in ((RDF.type, bs.SA.SampleArea), (SKOS.inScheme, bs.SA.SampleAreas), (SKOS.prefLabel, Literal("No process", lang="en")),
                     (SKOS.notation, Literal("no-process", datatype=XSD.string)), (SKOS.definition, Literal("An area that covers nothing.", lang="en"))):
            data.add((extra, p, o))
        self.assertFalse(conforms(data))


if __name__ == "__main__":
    unittest.main()
'''

QUERY = f"""PREFIX {PREFIX}: <{NAMESPACE}>
SELECT ?area ?process WHERE {{
  ?area {PREFIX}:coversProcess ?process .
}}
"""


# ---- the module, as the places need it ------------------------------------------------------------

def module(date):
    """The made-up module as release/register_module.py registers it: one function per place there."""
    return register_module.Module(
        name=MODULE, version=VERSION, prefix=PREFIX, title="Sample Area Module",
        description="Three made-up areas as a code list, and the process each covers. An example of onboarding a module.",
        approver="the ontology owner", approval=(APPROVAL, APPROVAL_WORDS),
        parts=[f"{MODULE}/vocabulary.ttl", f"{MODULE}/sample-areas.ttl"], shapes=[f"{MODULE}/shapes.ttl"],
        depends_on=["core"], decisions=[APPROVAL],
        files={"README.md": README, "vocabulary.ttl": VOCABULARY, "shapes.ttl": SHAPES, "sample-areas.csv": TABLE,
               "build_sample_areas.py": BUILDER, "test_sample_areas.py": TEST},
        builder="build_sample_areas.py", test="test_sample_areas.py",
        changelog=(f"# {MODULE} changelog\n\n## {VERSION} ({date})\n\nThe module's first release, a major. Approved by the "
                   f"ontology owner ({APPROVAL}). It holds three made-up areas as a code list and the process each covers. "
                   "It requires the newest core.\n\n### Known gaps\n\nNone.\n"),
        question=QUESTION, question_heading="The made-up sample areas",
        question_intro=f"The question of the made-up `{MODULE}` module, which `release/onboard_example.py` adds as an example.",
        query_name="sample-area-processes", query=QUERY,
        regression_files=["vocabulary.ttl", "sample-areas.ttl"], purpose="A made-up example of a new module",
        modules_section=(f"### {MODULE}: a made-up example of a new module\n\nThree made-up areas are a code list, and each "
                         "covers one process. `release/onboard_example.py` adds the module as an example of onboarding. Here "
                         "the area is the subject: `coversProcess` points from the area to core.\n\n"
                         f"<!-- module: {MODULE} -->\n```turtle parse\n"
                         f"@prefix proc: <https://w3id.org/mpc/ontology/process/> .\n@prefix {PREFIX}: <{NAMESPACE}> .\n"
                         f"@prefix area: <{NAMESPACE}area/> .\n\narea:north-yard {PREFIX}:coversProcess proc:CM-1-2-1 .\n"
                         f"area:south-yard {PREFIX}:coversProcess proc:CM-1-2-2 .\n```\n\n"),
        approval_text=(f"# Approval of {MODULE} {VERSION}\n\n{date}. The ontology owner: \"{APPROVAL_WORDS}\"\n\n"
                       "The ontology owner owns the module until they name a module owner.\n"))


def onboard(root=ROOT, date=None, write=False, say=print):
    """Registers the module in every place, or lists the places. Raises Refused with nothing changed."""
    date = date or datetime.date.today().isoformat()
    done = register_module.register(module(date), root, date, write=write)
    for path in done:
        say(f"{'registered in' if write else 'would register in'} {path}")
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--plan", action="store_true", help="list the places and change nothing")
    how.add_argument("--write", action="store_true", help="write the module's folder and register it in each place")
    ap.add_argument("--date", help="the release's date, YYYY-MM-DD (default: today)")
    a = ap.parse_args(argv)
    try:
        onboard(date=a.date, write=a.write)
    except Refused as err:
        print(f"refused: {err}", file=sys.stderr)
        return 1
    if a.write:
        print(f"Now build: cd ../{MODULE}, then build_sample_areas.py --write. HOW-TO-UPDATE.md has the steps after it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
