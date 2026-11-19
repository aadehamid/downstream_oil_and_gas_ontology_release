"""Build the pricing platform tables of the data-product module (since 1.2.0; the decision of 2026-10-25, items 7 to 16).

    python3 build_pricing.py            # check the tables and print the figures
    python3 build_pricing.py --write    # also write pricing.ttl
    python3 build_pricing.py --verify   # fail unless pricing.ttl equals a fresh build

pricing/tables.csv names each table and view of the subject matter expert's pricing assets, its layer, the system a
replica copies, and for a data product its kind, the criterion that decided it and why; lineage.csv says which
table each is derived from, at every hop; columns.csv the value columns' lineage only; agents.csv the Genie
agents and the metric views they use; view-systems.csv the systems each view's lineage reaches; sources.csv the
title of each source the module cites, which each table and agent names in its source column. The names are the
idp_sbx sandbox's, marked sandbox. The build fails unless every name resolves, a replica copies a known system and
is no data product, every other table is a data product with a kind, a foundational one is derived only from
replicas, a derived one from at least one data product, and every view's systems are the ones its lineage reaches.
"""
import argparse
import csv
import os
import sys
from collections import Counter

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS, XSD

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, "pricing")
OUTPUT = os.path.join(HERE, "pricing.ttl")
MEASURES = os.path.join(HERE, "..", "kpi", "measures.ttl")
SYSTEMS = os.path.join(HERE, "..", "system", "systems.csv")

DP = Namespace("https://w3id.org/mpc/ontology/modules/data-product/")
TABLE = Namespace("https://w3id.org/mpc/ontology/modules/data-product/table/")
COLUMN = Namespace("https://w3id.org/mpc/ontology/modules/data-product/column/")
AGENT = Namespace("https://w3id.org/mpc/ontology/modules/data-product/agent/")
KIND = Namespace("https://w3id.org/mpc/ontology/modules/data-product/kind/")
LAYER = Namespace("https://w3id.org/mpc/ontology/modules/data-product/layer/")
PRODUCT = Namespace("https://w3id.org/mpc/ontology/modules/data-product/product/")
SYSTEM = Namespace("https://w3id.org/mpc/ontology/modules/system/system/")
MEASURE = Namespace("https://w3id.org/mpc/ontology/modules/kpi/measure/")
SRC = Namespace("https://w3id.org/mpc/ontology/source/")
PROV = Namespace("http://www.w3.org/ns/prov#")
WHOLE = PRODUCT["master-pricing"]  # all pricing sits under Master Pricing (the decision of 2026-10-25, item 13)
LAYERS = ("replica", "silver", "gold", "metric-view")
KINDS = ("foundational", "derived")
TESTS = ("inputs", "logic")
# pricing/sources.csv gives each source its key (the end of its IRI) and its title: the pricing assets, which each
# table and agent names in its source column, and the data
# product kinds' sources, all generic frameworks (tier 5), since no MPC, peer or downstream source defines the kinds
# (the decision of 2026-10-25, item 14; data-product-kinds research of 2026-10-25). A new source is a new row there.


def read(name):
    with open(os.path.join(TABLES, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def source_problems(rows, table, has_slug=True):
    """What is wrong with a sources table: a key or slug that is empty, holds a space or is used twice, or an empty
    title. The same check is in kpi/build_measures.py and market-data/build_market_data.py."""
    problems = []
    for column in ("key", "slug") if has_slug else ("key",):
        values = [r[column] for r in rows]
        problems += [f"{table}: the {column} {v!r} must not be empty or hold a space" for v in values
                     if not v.strip() or any(c.isspace() for c in v)]
        problems += [f"{table} lists the {column} {v!r} {values.count(v)} times" for v in sorted(set(values)) if values.count(v) > 1]
    problems += [f"{table}: {r['key']!r} has no title" for r in rows if not r["title"].strip()]
    return problems


def split(text):
    return [t for t in text.split(";") if t]


def load():
    tables, lineage, columns = read("tables.csv"), read("lineage.csv"), read("columns.csv")
    source_rows = read("sources.csv")
    agents, view_systems = read("agents.csv"), read("view-systems.csv")
    systems = set()
    for path in (SYSTEMS, os.path.join(os.path.dirname(SYSTEMS), "other-systems.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            systems |= {r["slug"] for r in csv.DictReader(f)}
    measures = {str(n) for n in Graph().parse(MEASURES).objects(None, SKOS.notation)}
    by = {t["slug"]: t for t in tables}
    problems = [f"tables.csv lists {s} {n} times" for s, n in Counter(t["slug"] for t in tables).items() if n > 1]
    problems += source_problems(source_rows, "sources.csv", has_slug=False)
    keys = {r["key"] for r in source_rows}
    problems += [f"{name} {r['slug']}: unknown source {r['source']!r}, which is not in sources.csv"
                 for name, rows in (("table", tables), ("agent", agents)) for r in rows if r["source"] not in keys]
    for t in tables:
        s = t["slug"]
        if t["layer"] not in LAYERS:
            problems.append(f"{s}: layer {t['layer']!r} is not one of {LAYERS}")
        if t["layer"] == "replica":
            if t["copies_system"] not in systems:
                problems.append(f"{s}: a replica copies a system of the system module, not {t['copies_system']!r}")
            if t["kind"]:
                problems.append(f"{s}: a replica is not a data product, so it has no kind")
        else:
            if t["kind"] not in KINDS or t["classification_test"] not in TESTS or not t["classification_reason"]:
                problems.append(f"{s}: a data product needs a kind, a test ({TESTS}) and a reason")
        problems += [f"{s}: serves {m!r}, not a measure" for m in split(t["serves_measures"]) if m not in measures]
        if t["serves_measures"] and t["layer"] != "metric-view":
            problems.append(f"{s}: only a metric view serves a measure")
    sources = {}
    for row in lineage:
        problems += [f"lineage: {x!r} is not a table" for x in (row["table"], row["derived_from"]) if x not in by]
        sources.setdefault(row["table"], set()).add(row["derived_from"])
    problems += [f"lineage lists {k} {n} times" for k, n in Counter((r["table"], r["derived_from"]) for r in lineage).items() if n > 1]
    for s, t in by.items():
        layers = {by[x]["layer"] for x in sources.get(s, ()) if x in by}
        if t["layer"] == "replica" and s in sources:
            problems.append(f"{s}: a replica has no recorded source (Unity Catalog records none above it)")
        if t["kind"] == "foundational" and (not layers or layers != {"replica"}):
            problems.append(f"{s}: a foundational data product is derived only from replicas")
        if t["kind"] == "derived" and not layers - {"replica"}:
            problems.append(f"{s}: a derived data product is derived from at least one data product")
    for c in columns:
        problems += [f"columns: {x!r} is not a table" for x in (c["table"], c["from_table"]) if x not in by]
        if c["table"] in by and c["from_table"] not in sources.get(c["table"], ()):
            problems.append(f"columns: {c['table']}.{c['column']} comes from {c['from_table']}, which the table's lineage lacks")
    for a in agents:
        problems += [f"agent {a['slug']}: uses {v!r}, not a metric view" for v in split(a["uses"])
                     if by.get(v, {}).get("layer") != "metric-view"]

    def reach(s, seen=None):
        seen = set() if seen is None else seen
        for x in sources.get(s, ()):
            if x not in seen:
                seen.add(x)
                reach(x, seen)
        return {by[x]["copies_system"] for x in seen if x in by and by[x]["layer"] == "replica"}
    stated = {v["view"]: set(split(v["systems"])) for v in view_systems}
    for s, t in by.items():
        if t["layer"] == "metric-view" and stated.get(s) != reach(s):
            problems.append(f"{s}: its lineage reaches {sorted(reach(s))}, but view-systems.csv says {sorted(stated.get(s, ()))}")
    if problems:
        sys.exit("pricing tables do not reconcile:\n  " + "\n  ".join(problems))
    return tables, lineage, columns, agents, view_systems, source_rows


def build(tables, lineage, columns, agents, view_systems, sources):
    g = Graph()
    for prefix, ns in (("dp", DP), ("table", TABLE), ("column", COLUMN), ("agent", AGENT), ("kind", KIND), ("layer", LAYER),
                       ("product", PRODUCT), ("system", SYSTEM), ("measure", MEASURE), ("src", SRC), ("prov", PROV),
                       ("skos", SKOS), ("dcterms", DCTERMS)):
        g.bind(prefix, ns)
    for r in sources:
        g.add((SRC[r["key"]], RDF.type, DCTERMS.BibliographicResource))
        g.add((SRC[r["key"]], DCTERMS.title, Literal(r["title"], lang="en")))
    for t in tables:
        iri = TABLE[t["slug"]]
        g.add((iri, RDF.type, DP.PlatformTable))
        g.add((iri, RDF.type, SKOS.Concept))
        g.add((iri, SKOS.inScheme, DP.PlatformTables))
        g.add((iri, SKOS.topConceptOf, DP.PlatformTables))
        g.add((DP.PlatformTables, SKOS.hasTopConcept, iri))
        g.add((iri, SKOS.prefLabel, Literal(t["name"], lang="en")))
        g.add((iri, SKOS.notation, Literal(t["slug"], datatype=XSD.string)))
        g.add((iri, DP.fullName, Literal(t["name"], datatype=XSD.string)))
        g.add((iri, DP.sandbox, Literal(t["name"].startswith("idp_sbx.") or t["name"].startswith("synapse_dev."))))
        g.add((iri, DP.layer, LAYER[t["layer"]]))
        g.add((iri, DCTERMS.source, SRC[t["source"]]))
        if t["layer"] == "replica":
            g.add((iri, DP.copiesSystem, SYSTEM[t["copies_system"]]))
        else:
            g.add((iri, RDF.type, DP.PlatformDataProduct))
            g.add((iri, DCTERMS.isPartOf, WHOLE))
            g.add((iri, DP.dataProductKind, KIND[t["kind"]]))
            g.add((iri, DP.classificationTest, Literal(t["classification_test"], datatype=XSD.string)))
            g.add((iri, DP.classificationReason, Literal(t["classification_reason"], datatype=XSD.string)))
        for m in split(t["serves_measures"]):
            g.add((iri, DP.servesMeasure, MEASURE[m]))
    for row in lineage:
        g.add((TABLE[row["table"]], PROV.wasDerivedFrom, TABLE[row["derived_from"]]))
    for c in columns:
        a = COLUMN[f"{c['table']}--{c['column'].lower()}"]
        b = COLUMN[f"{c['from_table']}--{c['from_column'].lower()}"]
        for iri, table, name in ((a, c["table"], c["column"]), (b, c["from_table"], c["from_column"])):
            g.add((iri, RDF.type, DP.PlatformColumn))
            g.add((iri, DP.columnOf, TABLE[table]))
            g.add((iri, DP.columnName, Literal(name, datatype=XSD.string)))
        g.add((a, PROV.wasDerivedFrom, b))
    for v in view_systems:
        for s in split(v["systems"]):
            g.add((TABLE[v["view"]], DP.dependsOnSystem, SYSTEM[s]))
    for a in agents:
        iri = AGENT[a["slug"]]
        g.add((iri, RDF.type, PROV.SoftwareAgent))
        g.add((iri, RDFS.label, Literal(a["label"], lang="en")))
        g.add((iri, DCTERMS.source, SRC[a["source"]]))
        for v in split(a["uses"]):
            g.add((iri, PROV.used, TABLE[v]))
    return g


def figures(tables, lineage, columns, agents, view_systems, sources=()):
    layers = Counter(t["layer"] for t in tables)
    kinds = Counter(t["kind"] for t in tables if t["kind"])
    return {"tables": len(tables), **{l: layers[l] for l in LAYERS}, **{k: kinds[k] for k in KINDS},
            "lineage links": len(lineage), "value-column links": len(columns), "agents": len(agents)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    loaded = load()
    text = ("# Pricing platform tables of the data-product module (since 1.2.0; the decision of 2026-10-25).\n"
            "# Built by build_pricing.py from the tables in pricing/. Do not edit by hand.\n"
            + build(*loaded).serialize(format="turtle"))
    print("; ".join(f"{k} {v}" for k, v in figures(*loaded).items()))
    if args.verify:
        if not (os.path.exists(OUTPUT) and open(OUTPUT, encoding="utf-8").read() == text):
            sys.exit("pricing.ttl is not current: run build_pricing.py --write")
        print("pricing.ttl is current")
    if args.write:
        with open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
