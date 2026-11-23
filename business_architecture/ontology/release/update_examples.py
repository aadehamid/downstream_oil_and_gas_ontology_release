#!/usr/bin/env python3
"""Makes the hand edits of five worked examples of HOW-TO-UPDATE.md, so that each can be followed and tested from
start to end in a copy of the release.

    python3 update_examples.py <example> --plan     # list every file the example changes; change nothing
    python3 update_examples.py <example> --write    # make the changes

    deprecate-role   "Deprecate a term": the role Black Oil Manager is deprecated into Asphalt Manager
    system-kind      "Change the kind of a term": a fourth system kind, data platform, and Databricks takes it
    move-entry       "Move catalog entries to another class": the catalog entry HR becomes a data portfolio
    raci             "Change the RACI": two made-up roles and a made-up RACI for one process
    domain-list      "Add a controlled list to a module": a made-up list of data domains in the kpi module

Every example is made up. None is the organization's answer: the successor of a role, the kind of a system, the
class of a catalog entry, a RACI and a domain all come from the business. Run an example only in a copy of the
release. Run each example in a copy of its own, because two examples may change the same module.

`--write` changes sources only: tables, vocabularies, shapes, builders, the figures that the module's tests pin, a
proposal and the approval. It builds and releases nothing: the guide's next commands do that. Read each function
below as the pattern for a change of your own: one function per file.

The examples are made for KPI Store 1.2 as shipped: each looks for the exact text it changes. Every change is
worked out before the first file is written. So on a release that has moved on, where a file no longer holds that
text, `--plan` and `--write` both stop, name the file and change nothing. The command also refuses a copy that
holds the example already, a file that is a link, and a path that leaves the copy. Exit 0 when done, 1 when refused.
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from onboard_example import Refused, Tree  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ONT = "business_architecture/ontology"
PROCESS = "business_architecture/business_process"


def swap(tree, path, old, new):
    """Replaces the one place of a file that holds `old`. No place, or two, stops the run with nothing changed."""
    text = tree.read(path)
    if text.count(old) != 1:
        raise Refused(f"{path} does not hold the text this example changes, or holds it more than once. The example is made "
                      f"for KPI Store 1.2 as shipped, and this file has changed since. Nothing was changed. The text, which "
                      f"the file holds {text.count(old)} times, is: {old.strip()[:160]!r}")
    tree.texts[path] = text.replace(old, new)
    return path


def append(tree, path, added):
    """Adds text at the end of a file, after one blank line."""
    tree.texts[path] = tree.read(path).rstrip("\n") + "\n\n" + added
    return path


def approval(name, version, words):
    """The function that writes an example's approval file. Every release names the file that holds its approval."""
    def approval_file(tree, date):
        path = f"{ONT}/approvals/example-{name}.md"
        tree.new(path, f"# Approval of {version}\n\n{date}. The ontology owner: \"{words}\"\n\n"
                 f"A made-up approval, written by release/update_examples.py for the worked example `{name}`.\n")
        return path
    return approval_file


def cut_tests(tree, date):
    """One line in scripts/pinned-tests.txt. A release of organization gives integration a new version and leaves
    data-product as it is. The tests of the cut tool then skip, and one test fails to say so, until this line says
    that the copy has moved on from the release as shipped."""
    path = "scripts/pinned-tests.txt"
    line = "kpi_store/tests/test_cut.py::test_the_baseline_is_this_trees_or_data_product_has_moved_on"
    text = tree.read(path)
    if line in text:   # an earlier release of another module has added the line: it is said once
        return path
    tree.texts[path] = text.rstrip("\n") + f"\n# This copy has released a module that data-product does not depend on, so the cut tests' versions are not its own.\n{line}\n"
    return path


# ---- deprecate-role: Black Oil Manager is deprecated into Asphalt Manager ------------------------------------

def role_row(tree, date):
    """The role's row in roles.csv names its successor, and how the successor keeps its name: as an alternative
    label (`alt`), or as a hidden label (`hidden`) for a misspelling. The note says why and who decided."""
    return swap(tree, f"{ONT}/organization/roles.csv",
                "black-oil-manager,Black Oil Manager,,position,,,,,\n",
                'black-oil-manager,Black Oil Manager,,position,asphalt-manager,alt,,"Deprecated: a made-up answer for '
                "the worked example of HOW-TO-UPDATE.md says the Asphalt Manager does this role's work "
                f'(approvals/example-deprecate-role.md, {date}).",\n')


def role_pins(tree, date):
    """The figures the module's tests pin: one more deprecated role, one fewer live role, and the new merge."""
    path = f"{ONT}/organization/test_roles.py"
    swap(tree, path, '(f["deprecated roles"], f["live roles"]), (3, 57))', '(f["deprecated roles"], f["live roles"]), (4, 56))')
    return swap(tree, path, "        self.assertEqual(replaced, {\n",
                '        self.assertEqual(replaced, {\n            "black-oil-manager": "asphalt-manager",\n')


# ---- system-kind: a fourth system kind, and Databricks takes it ----------------------------------------------

def kind_vocabulary(tree, date):
    """The new value of the code list, as a concept in the list's scheme, and the two definitions that named the
    kinds one by one."""
    path = f"{ONT}/system/vocabulary.ttl"
    swap(tree, path, "skos:hasTopConcept kind:application, kind:office-tool, kind:document ;",
         "skos:hasTopConcept kind:application, kind:office-tool, kind:document, kind:data-platform ;")
    swap(tree, path, "\"The three kinds of thing the process map's systems field names.\"@en ;",
         "\"The kinds of system: the three kinds of thing the process map's systems field names, and the data platform.\"@en ;")
    swap(tree, path, '"Whether the system is an application, an office tool or a working document, from the system-kind code list."@en ;',
         '"Whether the system is an application, an office tool, a working document or a data platform, from the system-kind code list."@en ;')
    return swap(tree, path, '    skos:definition "A named document or file that the process works from, not an application."@en .\n',
                '    skos:definition "A named document or file that the process works from, not an application."@en .\n'
                'kind:data-platform a skos:Concept ; skos:inScheme sys:SystemKind ; skos:topConceptOf sys:SystemKind ; '
                'skos:prefLabel "Data platform"@en ; skos:notation "data-platform" ;\n'
                '    skos:definition "A platform that holds data from other systems and serves it to reports, applications and agents. '
                'Made-up wording, for the worked example of HOW-TO-UPDATE.md."@en .\n')


def kind_shape(tree, date):
    """The shape of the property that points at the list: its `sh:in` names every value, so it gains the new one."""
    return swap(tree, f"{ONT}/system/shapes.ttl", "sh:in ( kind:application kind:office-tool kind:document ) ] ;",
                "sh:in ( kind:application kind:office-tool kind:document kind:data-platform ) ] ;")


def kind_builder(tree, date):
    """The builder's own list of the kinds a table may name."""
    return swap(tree, f"{ONT}/system/build_systems.py", 'KINDS = ("application", "office-tool", "document")',
                'KINDS = ("application", "office-tool", "document", "data-platform")')


def kind_row(tree, date):
    """The system's row in its table takes the new kind."""
    return swap(tree, f"{ONT}/system/other-systems.csv", "databricks,Databricks,,application,", "databricks,Databricks,,data-platform,")


def kind_pins(tree, date):
    """The figures the module's tests pin, and a line that names the system and its new kind."""
    path = f"{ONT}/system/test_systems.py"
    swap(tree, path, '"application": 40, "office-tool": 4, "document": 5,',
         '"application": 39, "office-tool": 4, "document": 5, "data-platform": 1,')
    return swap(tree, path, '        self.assertEqual(SYSTEMS.value(SYSTEM["xpims"], SYS.systemKind), KIND["application"])\n',
                '        self.assertEqual(SYSTEMS.value(SYSTEM["xpims"], SYS.systemKind), KIND["application"])\n'
                '        self.assertEqual(SYSTEMS.value(SYSTEM["databricks"], SYS.systemKind), KIND["data-platform"])\n')


# ---- move-entry: the catalog entry HR becomes a data portfolio -----------------------------------------------

ENTRY_PROPOSAL = """# Proposal EXAMPLE-P02: the catalog entry HR is a portfolio, not a data product

| Field | Value |
|---|---|
| Status | Accepted (a made-up decision, {date}). Applied to `data_product_portfolio.json` |
| Date | {date} |
| Decision | `business_architecture/ontology/approvals/example-move-entry.md` |
| Source | `data_product_portfolio.json`: the entry `dp-hr` under the line `dpl-hr` |

This proposal is made up. `release/update_examples.py` wrote it for the worked example of `HOW-TO-UPDATE.md`, "Move
catalog entries to another class".

## The gap

The portfolio file lists HR under the line HR as an entry of its `portfolios` list. The ontology types every entry
of that list as a data product. HR is a functional area whose data products are not named yet.

## The proposal

Give the entry `dp-hr` the field `"kind": "portfolio"`. The entry keeps its id, its name, its status and its line.
Allow the field in the file's schema, `business_architecture/schema/data_product_portfolio.schema.json`.

## How the ontology takes it

The entry keeps its IRI. Its class changes from `dp:DataProduct` to `dp:DataPortfolio`, a class that this release
of `data-product` adds. A list of data products no longer holds the entry, so the release is a major.
"""


def entry_proposal(tree, date):
    """The proposal to the process authority. The portfolio file changes only through an accepted proposal."""
    path = f"{PROCESS}/proposals/EXAMPLE-P02-portfolio-entry.md"
    tree.new(path, ENTRY_PROPOSAL.format(date=date))
    return path


def entry_source(tree, date):
    """The accepted proposal, applied to the portfolio file: the entry says what kind of thing it is."""
    return swap(tree, f"{PROCESS}/data_product_portfolio.json", '{ "id": "dp-hr", "name": "HR", "status": "defined_only" }',
                '{ "id": "dp-hr", "name": "HR", "status": "defined_only", "kind": "portfolio" }')


def entry_schema(tree, date):
    """The portfolio file's schema lists the fields an entry may have, so it gains the new field and its one value."""
    return swap(tree, "business_architecture/schema/data_product_portfolio.schema.json",
                '        "id": { "type": "string", "pattern": "^dp-[a-z0-9-]+$" },\n',
                '        "id": { "type": "string", "pattern": "^dp-[a-z0-9-]+$" },\n'
                '        "kind": { "type": "string", "enum": ["portfolio"] },\n')


def entry_vocabulary(tree, date):
    """The class the entry moves to, with its label, its definition and its source."""
    return swap(tree, f"{ONT}/data-product/vocabulary.ttl", "dp:DataProducts a skos:ConceptScheme ;",
                'dp:DataPortfolio a owl:Class ;\n    rdfs:label "data portfolio"@en ;\n'
                '    skos:definition "A named part of a data product line that groups the data of one functional area and is not itself '
                'a data product. Made-up wording, for the worked example of HOW-TO-UPDATE.md."@en ;\n'
                f'    dcterms:bibliographicCitation "{PROCESS}/proposals/EXAMPLE-P02-portfolio-entry.md, a made-up proposal"@en .\n\n'
                "dp:DataProducts a skos:ConceptScheme ;")


def entry_shapes(tree, date):
    """The shapes: the new class takes what every catalog entry has, sits in one line, and is never also a data
    product."""
    path = f"{ONT}/data-product/shapes.ttl"
    swap(tree, path, "    sh:targetClass dp:PortfolioSegment, dp:DataProductLine, dp:DataProduct ;",
         "    sh:targetClass dp:PortfolioSegment, dp:DataProductLine, dp:DataProduct, dp:DataPortfolio ;")
    swap(tree, path, "    sh:targetClass dp:DataProductLine, dp:DataProduct ;", "    sh:targetClass dp:DataProductLine, dp:DataProduct, dp:DataPortfolio ;")
    return swap(tree, path, "# An active item is one the portfolio describes, so it is defined, not parked.\n",
                "# A data portfolio sits in one line, as a data product does, and is never also a data product: one kind per term.\n"
                "shp:Portfolio a sh:NodeShape ;\n    sh:targetClass dp:DataPortfolio ;\n"
                "    sh:property [ sh:path skos:broader ; sh:minCount 1 ; sh:maxCount 1 ; sh:class dp:DataProductLine ;\n"
                '                  sh:message "A data portfolio sits in exactly one data product line." ] ;\n'
                "    sh:property [ sh:path dp:portfolioStatus ; sh:minCount 1 ; sh:maxCount 1 ;\n"
                "                  sh:in ( status:active status:defined-only status:open-decision ) ] ;\n"
                "    sh:not [ sh:class dp:DataProduct ] ;\n"
                '    sh:message "A data portfolio sits in one line, has one status and is not also a data product." .\n\n'
                "# An active item is one the portfolio describes, so it is defined, not parked.\n")


def entry_builder(tree, date):
    """The builder: it refuses a kind it does not know, types an entry by its kind, keeps the entry's IRI, and
    says in a history note what the entry was before."""
    path = f"{ONT}/data-product/build_data_products.py"
    swap(tree, path, '                if item.get("status") not in STATUSES:\n',
         '                if item.get("kind") not in (None, "portfolio"):\n'
         '                    problems.append(f"{item[\'id\']}: kind {item.get(\'kind\')!r} is not portfolio")\n'
         '                if item.get("status") not in STATUSES:\n')
    swap(tree, path, '                describe(PRODUCT[local("dp-", p["id"])], DP.DataProduct, p, l, "data product")\n',
         '                if p.get("kind") == "portfolio":\n'
         '                    describe(PRODUCT[local("dp-", p["id"])], DP.DataPortfolio, p, l, "data portfolio")\n'
         '                    g.add((PRODUCT[local("dp-", p["id"])], SKOS.historyNote, Literal(\n'
         '                        "data-product 2.0.0: until this release the entry was a data product (dp:DataProduct). The portfolio "\n'
         '                        "file now marks it a portfolio (proposal EXAMPLE-P02, made up).", lang="en")))\n'
         '                else:\n'
         '                    describe(PRODUCT[local("dp-", p["id"])], DP.DataProduct, p, l, "data product")\n')
    swap(tree, path, '    products = [p for l in lines for p in l.get("portfolios", [])]\n',
         '    entries = [p for l in lines for p in l.get("portfolios", [])]\n'
         '    products = [p for p in entries if p.get("kind") != "portfolio"]\n')
    return swap(tree, path, '        "data products": len(products),\n',
                '        "data products": len(products),\n        "data portfolios": len(entries) - len(products),\n')


def entry_pins(tree, date):
    """The figures the module's tests pin, a line that names the entry and its new class, and a test of what the
    new shape rejects."""
    path = f"{ONT}/data-product/test_data_products.py"
    swap(tree, path, "        self.assertEqual(len(terms), 16)  # 7, then", "        self.assertEqual(len(terms), 17)  # the data portfolio; 7, then")
    swap(tree, path, "    def test_rejects_rows_on_a_table(self):\n",
         "    def test_rejects_a_portfolio_that_is_also_a_data_product(self):\n"
         '        hr = URIRef("https://w3id.org/mpc/ontology/modules/data-product/product/hr")\n'
         "        self.assertFalse(self.broken(lambda g: g.add((hr, RDF.type, DP.DataProduct))))\n\n"
         "    def test_rejects_rows_on_a_table(self):\n")
    swap(tree, path, '"segments": 3, "lines": 19, "data products": 49, "active products": 16,\n'
         '            "defined_only products": 33, "open_decision products": 0, "parked without a description": 33,',
         '"segments": 3, "lines": 19, "data products": 48, "data portfolios": 1, "active products": 16,\n'
         '            "defined_only products": 32, "open_decision products": 0, "parked without a description": 32,')
    return swap(tree, path, "        self.assertEqual(len(set(PRODUCTS.subjects(RDF.type, DP.DataProduct))), 49)\n",
                "        self.assertEqual(len(set(PRODUCTS.subjects(RDF.type, DP.DataProduct))), 48)\n"
                "        # The worked example of HOW-TO-UPDATE.md: HR keeps its IRI and is a data portfolio, not a data product.\n"
                '        hr = URIRef("https://w3id.org/mpc/ontology/modules/data-product/product/hr")\n'
                "        self.assertEqual(set(PRODUCTS.objects(hr, RDF.type)), {DP.DataPortfolio, SKOS.Concept})\n")


# ---- raci: two made-up roles and a made-up RACI for one process ----------------------------------------------

RACI_PROPOSAL = """# Proposal EXAMPLE-P01: a RACI for CM 1.1.2 Regional Optimization

| Field | Value |
|---|---|
| Status | Accepted (a made-up decision, {date}). Applied to `downstream_process_map.json` |
| Date | {date} |
| Decision | `business_architecture/ontology/approvals/example-raci.md` |
| Source | A made-up RACI chart, as of {date} |

This proposal is made up. `release/update_examples.py` wrote it for the worked example of `HOW-TO-UPDATE.md`, "Change
the RACI".

## The gap

The process map gives CM 1.1.2 Regional Optimization no RACI. The ontology infers none from the processes under it.

## The proposal

Give CM 1.1.2 these four lists. Two of the roles are new to the process map.

| Level | Role |
|---|---|
| Responsible | Sample Data Steward |
| Accountable | Sample Domain Owner |
| Consulted | IT Data Owner |
| Informed | Business Analyst |

## How the ontology takes it

The `organization` module gains two roles and four assignments, one for each entry. It removes nothing, so its
release is a minor.
"""


def raci_proposal(tree, date):
    """The proposal to the process authority. The process map changes only through an accepted proposal."""
    path = f"{PROCESS}/proposals/EXAMPLE-P01-sample-raci.md"
    tree.new(path, RACI_PROPOSAL.format(date=date))
    return path


def raci_source(tree, date):
    """The accepted proposal, applied to the process map: the process's four lists."""
    lists = "".join(f'                  "{level}": [\n                    "{role}"\n                  ]{end}\n' for level, role, end in (
        ("responsible", "Sample Data Steward", ","), ("accountable", "Sample Domain Owner", ","),
        ("consulted", "IT Data Owner", ","), ("informed", "Business Analyst", "")))
    anchor = '                "id": "CM 1.1.2",\n                "level": 3,\n                "name": "Regional Optimization",\n'
    return swap(tree, f"{PROCESS}/downstream_process_map.json", anchor, anchor + '                "raci": {\n' + lists + "                },\n")


def raci_register(tree, date):
    """A row in the role register for each new role string of the process map, with the role it names."""
    path = f"{ONT}/organization/role-register.csv"
    tree.texts[path] = tree.read(path).rstrip("\n") + ("\nSample Data Steward,sample-data-steward,exact,\n"
                                                        "Sample Domain Owner,sample-domain-owner,exact,\n")
    return path


def raci_roles(tree, date):
    """A row in roles.csv for each new role: its name as the source spells it, its kind, its definition and a note
    that names the source and its date."""
    path = f"{ONT}/organization/roles.csv"
    note = f"A made-up role of the worked example of HOW-TO-UPDATE.md (proposal EXAMPLE-P01, as of {date})."
    tree.texts[path] = tree.read(path).rstrip("\n") + (
        f'\nsample-data-steward,Sample Data Steward,,position,,,"A made-up role that looks after the meaning and the quality of one body of data.","{note}",\n'
        f'sample-domain-owner,Sample Domain Owner,,position,,,"A made-up role that answers for one body of data.","{note}",\n')
    return path


def raci_pins(tree, date):
    """The figures the module's tests pin: one more process with a RACI, four more entries, two more role strings
    and two more roles."""
    path = f"{ONT}/organization/test_roles.py"
    swap(tree, path, "(153, 913, 91, 60, 54, 6, 11, 940))", "(154, 917, 93, 62, 56, 6, 11, 944))")
    return swap(tree, path, '(f["deprecated roles"], f["live roles"]), (3, 57))', '(f["deprecated roles"], f["live roles"]), (3, 59))')


# ---- domain-list: a made-up list of data domains in the kpi module -------------------------------------------

DOMAIN_NS = "https://w3id.org/mpc/ontology/modules/kpi/"
DOMAIN_QUESTION = "Which data domains does the ontology hold, and what data does each cover?"


def next_question(tree):
    """The number after the last competency question of the copy: 58 on the release as shipped."""
    rows = [line.split(",", 1)[0] for line in tree.read(f"{ONT}/regression/expected.csv").splitlines()[1:] if line.strip()]
    if not rows or not all(row.isdigit() for row in rows):
        raise Refused(f"{ONT}/regression/expected.csv does not start each row with a question's number. Nothing was changed")
    return max(int(row) for row in rows) + 1

DOMAIN_TABLE = """domain_id,name,definition
yard-stock,Yard Stock,"The made-up yard stock domain, which stands for one data domain of your organization."
dock-schedule,Dock Schedule,"The made-up dock schedule domain, which stands for a second data domain of your organization."
"""

DOMAIN_VOCABULARY = f"""# A made-up list of data domains, added by release/update_examples.py for the worked example of HOW-TO-UPDATE.md.
kpi:DataDomains a skos:ConceptScheme ;
    rdfs:label "data domains"@en ;
    skos:definition "The data domains a measure can belong to. A made-up list, for the worked example of HOW-TO-UPDATE.md."@en ;
    dcterms:bibliographicCitation "{ONT}/kpi/data-domains.csv, a made-up table"@en .

kpi:DataDomain a owl:Class ;
    rdfs:label "data domain"@en ;
    skos:definition "A body of data with one owner, as the list of data domains names it."@en ;
    dcterms:bibliographicCitation "{ONT}/kpi/data-domains.csv, a made-up table"@en .

kpi:dataDomain a owl:ObjectProperty ;
    rdfs:label "data domain"@en ;
    rdfs:domain kpi:MeasureDefinition ; rdfs:range skos:Concept ;
    skos:definition "The data domain the measure belongs to, from the list of data domains."@en ;
    dcterms:bibliographicCitation "{ONT}/kpi/data-domains.csv, a made-up table; competency question QUESTION_NUMBER"@en .
"""

DOMAIN_SHAPES = """# A made-up list of data domains (the worked example of HOW-TO-UPDATE.md). A domain is a value of its own list, and a
# measure's domain is a value of that list and of no other.
shp:DataDomain a sh:NodeShape ;
    sh:targetClass kpi:DataDomain ;
    sh:property [ sh:path skos:inScheme ; sh:minCount 1 ; sh:maxCount 1 ; sh:hasValue kpi:DataDomains ;
                  sh:message "A data domain is in the list of data domains." ] ;
    sh:property [ sh:path skos:prefLabel ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype rdf:langString ] ;
    sh:property [ sh:path skos:notation ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:string ] ;
    sh:property [ sh:path skos:definition ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype rdf:langString ] ;
    sh:property [ sh:path dcterms:bibliographicCitation ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype rdf:langString ;
                  sh:message "A data domain cites its source." ] .

shp:MeasureDomainIsOnTheList a sh:NodeShape ;
    sh:targetObjectsOf kpi:dataDomain ;
    sh:property [ sh:path skos:inScheme ; sh:minCount 1 ; sh:hasValue kpi:DataDomains ] ;
    sh:message "A measure names a data domain from the list of data domains." .
"""

DOMAIN_BUILDER = f'''"""Build the made-up list of data domains (written by release/update_examples.py).

    python3 build_data_domains.py            # check the table and print the figures
    python3 build_data_domains.py --write    # also write data-domains.ttl
    python3 build_data_domains.py --verify   # fail unless data-domains.ttl equals a fresh build

The domains come from data-domains.csv, one row each. The build fails unless every domain has a name and a
definition, and no domain is named twice.
"""
import argparse
import csv
import os
import sys

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import DCTERMS, RDF, SKOS, XSD

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "data-domains.csv")
OUTPUT = os.path.join(HERE, "data-domains.ttl")

KPI = Namespace("{DOMAIN_NS}")
DOMAIN = Namespace("{DOMAIN_NS}data-domain/")
CITATION = "{ONT}/kpi/data-domains.csv, a made-up table"


def load():
    with open(TABLE, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    problems = [f"{{r['domain_id']}}: no name or no definition" for r in rows if not (r["name"] and r["definition"])]
    for column in ("domain_id", "name"):
        if len({{r[column] for r in rows}}) != len(rows):
            problems.append(f"two domains share a {{column}}")
    if problems:
        sys.exit("the data domain table does not reconcile:\\n  " + "\\n  ".join(problems))
    return rows


def build(rows):
    g = Graph()
    for prefix, ns in (("kpi", KPI), ("domain", DOMAIN), ("skos", SKOS), ("dcterms", DCTERMS)):
        g.bind(prefix, ns)
    for row in rows:
        iri = DOMAIN[row["domain_id"]]
        g.add((iri, RDF.type, SKOS.Concept))
        g.add((iri, RDF.type, KPI.DataDomain))
        g.add((iri, SKOS.inScheme, KPI.DataDomains))
        g.add((iri, SKOS.topConceptOf, KPI.DataDomains))
        g.add((KPI.DataDomains, SKOS.hasTopConcept, iri))
        g.add((iri, SKOS.prefLabel, Literal(row["name"], lang="en")))
        g.add((iri, SKOS.notation, Literal(row["domain_id"], datatype=XSD.string)))
        g.add((iri, SKOS.definition, Literal(row["definition"], lang="en")))
        g.add((iri, DCTERMS.bibliographicCitation, Literal(CITATION, lang="en")))
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    rows = load()
    text = ("# The made-up list of data domains of the kpi module.\\n"
            "# Built by build_data_domains.py from data-domains.csv. Do not edit by hand.\\n"
            + build(rows).serialize(format="turtle"))
    print(f"data domains {{len(rows)}}")
    if args.verify:
        if not (os.path.exists(OUTPUT) and open(OUTPUT, encoding="utf-8").read() == text):
            sys.exit("data-domains.ttl is not current: run build_data_domains.py --write")
        print("data-domains.ttl is current")
    if args.write:
        with open(OUTPUT, "w", encoding="utf-8", newline="\\n") as f:
            f.write(text)
        print("wrote data-domains.ttl")


if __name__ == "__main__":
    main()
'''

DOMAIN_TEST = '''"""Tests for the made-up list of data domains: the build is current, the domains are the table's two, and SHACL
accepts the list, accepts a measure that names a domain of it, and rejects a measure that names a value of another
list.

Run: python3 -m pytest test_data_domains.py (needs rdflib, pyshacl).
"""
import os
import subprocess
import sys
import unittest

from pyshacl import validate
from rdflib import Graph, Namespace
from rdflib.namespace import SKOS

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_data_domains as bd  # noqa: E402

VOCAB = Graph().parse(os.path.join(HERE, "vocabulary.ttl"))
SHAPES = Graph().parse(os.path.join(HERE, "shapes.ttl"))
MEASURES = Graph().parse(os.path.join(HERE, "measures.ttl"))
MEASURE = Namespace("https://w3id.org/mpc/ontology/modules/kpi/measure/")
KIND = Namespace("https://w3id.org/mpc/ontology/modules/kpi/measure-kind/")


def conforms(data):
    return validate(data + VOCAB, shacl_graph=SHAPES, advanced=True)[0]


class Build(unittest.TestCase):
    def test_build_is_current(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_data_domains.py"), "--verify"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_two_domains(self):
        # Pinned by hand from data-domains.csv.
        domains = bd.build(bd.load())
        self.assertEqual({str(s)[len(str(bd.DOMAIN)):] for s in domains.subjects(SKOS.inScheme, bd.KPI.DataDomains)},
                         {"yard-stock", "dock-schedule"})


class Shapes(unittest.TestCase):
    """The measure in these tests is an illustration. No measure of the release names a domain."""

    def setUp(self):
        self.data = bd.build(bd.load()) + MEASURES
        self.measure = MEASURE["unit-utilization"]
        self.assertIn((self.measure, SKOS.inScheme, bd.KPI.Measures), self.data)

    def test_the_list_conforms(self):
        self.assertTrue(conforms(self.data))

    def test_a_measure_may_name_a_domain_of_the_list(self):
        self.data.add((self.measure, bd.KPI.dataDomain, bd.DOMAIN["yard-stock"]))
        self.assertTrue(conforms(self.data))

    def test_a_value_of_another_list_is_rejected(self):
        self.data.add((self.measure, bd.KPI.dataDomain, KIND["alert"]))
        self.assertFalse(conforms(self.data))

    def test_two_domains_on_one_measure_are_rejected(self):
        self.data.add((self.measure, bd.KPI.dataDomain, bd.DOMAIN["yard-stock"]))
        self.data.add((self.measure, bd.KPI.dataDomain, bd.DOMAIN["dock-schedule"]))
        self.assertFalse(conforms(self.data))


if __name__ == "__main__":
    unittest.main()
'''

DOMAIN_QUERY = f"""# QQUESTION_NUMBER {DOMAIN_QUESTION}
PREFIX kpi: <{DOMAIN_NS}>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?domain ?name ?covers WHERE {{
  ?domain skos:inScheme kpi:DataDomains ; skos:prefLabel ?name ; skos:definition ?covers .
}}
"""


def domain_files(tree, date):
    """The list's table, a builder that writes it as Turtle, and a test file."""
    for name, text in (("data-domains.csv", DOMAIN_TABLE), ("build_data_domains.py", DOMAIN_BUILDER), ("test_data_domains.py", DOMAIN_TEST)):
        tree.new(f"{ONT}/kpi/{name}", text)
    return f"{ONT}/kpi/data-domains.csv, build_data_domains.py and test_data_domains.py"


def domain_vocabulary(tree, date):
    """The list's scheme, the class of its values, and the property that points at the list."""
    return append(tree, f"{ONT}/kpi/vocabulary.ttl", DOMAIN_VOCABULARY.replace("QUESTION_NUMBER", str(next_question(tree))))


def domain_shapes(tree, date):
    """The shapes: the property's cardinality on the measure's shape, the property in the closed shape's list, and
    two new shapes, one for a value of the list and one that keeps the property on its own list."""
    path = f"{ONT}/kpi/shapes.ttl"
    swap(tree, path, "    sh:property [ sh:path pop:populationEvidence ; sh:minCount 0 ; sh:maxCount 1 ; sh:datatype xsd:string ] .\n",
         "    sh:property [ sh:path pop:populationEvidence ; sh:minCount 0 ; sh:maxCount 1 ; sh:datatype xsd:string ] ;\n"
         "    sh:property [ sh:path kpi:dataDomain ; sh:minCount 0 ; sh:maxCount 1 ; sh:nodeKind sh:IRI ;\n"
         '                  sh:message "A measure belongs to at most one data domain." ] .\n')
    swap(tree, path, "pop:includes pop:excludes pop:populationEvidence ) ;", "pop:includes pop:excludes pop:populationEvidence kpi:dataDomain ) ;")
    return append(tree, path, DOMAIN_SHAPES)


def domain_package(tree, date):
    """The new Turtle file in the list of files the module's package is built from, and in the test that names
    those files by hand."""
    swap(tree, f"{ONT}/release/test_build_module.py", 'for part in ("kpi/vocabulary.ttl", "kpi/measures.ttl", "population/vocabulary.ttl",',
         'for part in ("kpi/vocabulary.ttl", "kpi/measures.ttl", "kpi/data-domains.ttl", "population/vocabulary.ttl",')
    swap(tree, f"{ONT}/release/build_module.py", '"parts": ["kpi/vocabulary.ttl", "kpi/measures.ttl",',
         '"parts": ["kpi/vocabulary.ttl", "kpi/measures.ttl", "kpi/data-domains.ttl",')
    return f"{ONT}/release/build_module.py and test_build_module.py"


def domain_check(tree, date):
    """Two lines in the check: the new builder's --verify, and the new test file in the test list."""
    path = "scripts/check.sh"
    swap(tree, path, "(cd $ONT/kpi && run with_deps python build_measures.py --verify)\n",
         "(cd $ONT/kpi && run with_deps python build_measures.py --verify)\n(cd $ONT/kpi && run with_deps python build_data_domains.py --verify)\n")
    return swap(tree, path, "  business_architecture/ontology/kpi/test_measures.py \\\n",
                "  business_architecture/ontology/kpi/test_data_domains.py \\\n  business_architecture/ontology/kpi/test_measures.py \\\n")


def domain_question(tree, date):
    """The competency question the list answers: its row in expected.csv, its query, the new file in run.py, and
    the question in competency-questions.md, numbered after the last."""
    number = next_question(tree)
    tree.new(f"{ONT}/regression/queries/q{number}-data-domains.rq", DOMAIN_QUERY.replace("QUESTION_NUMBER", str(number)))
    expected = tree.read(f"{ONT}/regression/expected.csv")
    end = "\r\n" if expected.endswith("\r\n") else "\n"
    tree.texts[f"{ONT}/regression/expected.csv"] = expected + f"{number},answerable,q{number}-data-domains.rq,{end}"
    swap(tree, f"{ONT}/regression/run.py", '"kpi", n) for n in ("vocabulary.ttl", "measures.ttl")]',
         '"kpi", n) for n in ("vocabulary.ttl", "measures.ttl", "data-domains.ttl")]')
    path = f"{ONT}/competency-questions.md"
    text = tree.read(path)
    numeral = "XV" if "\n## XIV." in text else "XIV"
    tree.texts[path] = text.rstrip("\n") + (
        f"\n\n## {numeral}. The made-up data domains (added {date})\nThe question of the made-up list of data domains, which "
        f"`release/update_examples.py` adds to `kpi` as an example.\n{number}. {DOMAIN_QUESTION}\n")
    return f"{ONT}/regression/ and {ONT}/competency-questions.md"


def domain_guide(tree, date):
    """The new file in the modules guide's table of what each package is built from."""
    return swap(tree, f"{ONT}/MODULES.md", "| `kpi/vocabulary.ttl`, `kpi/measures.ttl`, ", "| `kpi/vocabulary.ttl`, `kpi/measures.ttl`, `kpi/data-domains.ttl`, ")


# ---- the examples ---------------------------------------------------------------------------------------------

EXAMPLES = {
    "deprecate-role": {
        "places": (role_row, role_pins, cut_tests, approval("deprecate-role", "organization 3.0.0", "Approved as a major: Black Oil Manager is deprecated into Asphalt Manager.")),
        "next": "Now build: cd ../organization, then build_roles.py --write and build_assignments.py --write.",
    },
    "system-kind": {
        "places": (kind_vocabulary, kind_shape, kind_builder, kind_row, kind_pins,
                   approval("system-kind", "system 2.0.0", "Approved as a major: the system kind data platform, and Databricks as a data platform.")),
        "next": "Now build: cd ../system, then build_systems.py --write.",
    },
    "move-entry": {
        "places": (entry_proposal, entry_source, entry_schema, entry_vocabulary, entry_shapes, entry_builder, entry_pins,
                   approval("move-entry", "data-product 2.0.0", "Approved as a major: the catalog entry HR is a data portfolio.")),
        "next": "Now build: cd ../data-product, then build_data_products.py --write.",
    },
    "raci": {
        "places": (raci_proposal, raci_source, raci_register, raci_roles, raci_pins, cut_tests,
                   approval("raci", "organization 2.3.0", "Approved as a minor: two roles and the RACI of CM 1.1.2.")),
        "next": "Now build: cd ../organization, then build_roles.py --write and build_assignments.py --write.",
    },
    "domain-list": {
        "places": (domain_files, domain_vocabulary, domain_shapes, domain_package, domain_check, domain_question, domain_guide,
                   approval("domain-list", "kpi 1.4.0", "Approved as a minor: a list of data domains and the property that points at it.")),
        "next": "Now build: cd ../kpi, then build_data_domains.py --write.",
    },
}


def apply(name, root=ROOT, date=None, write=False, say=print):
    """Makes one example's changes, or lists the files. Raises Refused with nothing changed."""
    date = date or datetime.date.today().isoformat()
    if os.path.exists(os.path.join(root, ONT, "approvals", f"example-{name}.md")):
        raise Refused(f"this copy holds the example {name} already; nothing was changed")
    tree = Tree(root)
    done = [place(tree, date) for place in EXAMPLES[name]["places"]]
    if write:
        tree.save()
    for path in done:
        say(f"{'changed' if write else 'would change'} {path}")
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("example", choices=sorted(EXAMPLES))
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--plan", action="store_true", help="list the files and change nothing")
    how.add_argument("--write", action="store_true", help="make the changes")
    ap.add_argument("--date", help="the date of the change, YYYY-MM-DD (default: today)")
    a = ap.parse_args(argv)
    try:
        apply(a.example, date=a.date, write=a.write)
    except Refused as err:
        print(f"refused: {err}", file=sys.stderr)
        return 1
    if a.write:
        print(f"{EXAMPLES[a.example]['next']} HOW-TO-UPDATE.md has the steps after it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
