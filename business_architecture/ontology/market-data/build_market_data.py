"""Build the market-data module (Step 7; the decision of 2026-10-19, the decision of 2026-10-20).

    python3 build_market_data.py            # check the tables and print the figures
    python3 build_market_data.py --write    # also write market-data.ttl
    python3 build_market_data.py --verify   # fail unless market-data.ttl equals a fresh build

regions.csv gives MPC's refining regions and MPC Economics' product market regions;
benchmarks.csv the crude markers, product benchmarks and the RVO cost; series.csv the
published series of the crack-spreads measure, each with its legs, the series it blends, or a
mark that its source does not list its legs. The build fails unless every region, benchmark
and blended series a row names exists, each leg-built series has one crude leg, at least one
product leg and at most one compliance-cost leg, a blended series has no legs, a series with
neither legs nor a blend is marked legs_unstated, and every source is in sources.csv, which gives each
source its title. Every region, benchmark, series, new price and enumeration names its source in a source column,
and series.csv's note column holds a series' scope note, such as its blend weights. A new source or note is a new
row or cell, with no code change.

Since 1.1.0 (the decision of 2026-10-25, items 4 and 5): market-prices.csv names the prices the decision owner's pricing
views report for the other pricing measures, each linked to its measure, reusing a benchmark of the same name;
enumerations.csv names, for each measure, the view and columns that list all of its series, since the module
names only examples. Every scheme states its top concepts both ways (the decision of 2026-10-25, item 5).
"""
import argparse
import csv
import os
import sys

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import DCTERMS, RDF, SKOS, XSD

HERE = os.path.dirname(os.path.abspath(__file__))
MEASURES = os.path.join(HERE, "..", "kpi", "measures.ttl")
OUTPUT = os.path.join(HERE, "market-data.ttl")

MKT = Namespace("https://w3id.org/mpc/ontology/modules/market-data/")
BKIND = Namespace("https://w3id.org/mpc/ontology/modules/market-data/benchmark-kind/")
REGION = Namespace("https://w3id.org/mpc/ontology/modules/market-data/region/")
BENCH = Namespace("https://w3id.org/mpc/ontology/modules/market-data/benchmark/")
SERIES = Namespace("https://w3id.org/mpc/ontology/modules/market-data/series/")
LEG = Namespace("https://w3id.org/mpc/ontology/modules/market-data/leg/")
MEASURE = Namespace("https://w3id.org/mpc/ontology/modules/kpi/measure/")
SRC = Namespace("https://w3id.org/mpc/ontology/source/")
MEASURE_ID = "crack-spreads"
# sources.csv gives each cited source its key (the tables' source column), the end of its IRI and its title. A source
# the kpi module also declares keeps the title build_measures.py gives it (kpi/measure-sources.csv).
SOURCE_TABLE = "sources.csv"
SCHEMES = {"refining": MKT.RefiningRegions, "market": MKT.MarketRegions}
PRICE = Namespace("https://w3id.org/mpc/ontology/modules/market-data/price/")
ENUM = Namespace("https://w3id.org/mpc/ontology/modules/market-data/enumeration/")
REPORTED_AS = ("basis", "cash", "differential", "settlement", "assessment")
TEMPLATE_NOTE = ("The definition is built from the Executive Summary or benchmark agent's filters, which name this price and its group; the subject matter expert's files give no definition of their own (the decision of 2026-10-25, Known gaps).")
KINDS = ("crude-marker", "product-benchmark", "compliance-cost")


def read_csv(name):
    with open(os.path.join(HERE, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def source_problems(rows, table, has_slug=True):
    """What is wrong with a sources table: a key or slug that is empty, holds a space or is used twice, or an empty
    title. The same check is in kpi/build_measures.py and data-product/build_pricing.py."""
    problems = []
    for column in ("key", "slug") if has_slug else ("key",):
        values = [r[column] for r in rows]
        problems += [f"{table}: the {column} {v!r} must not be empty or hold a space" for v in values
                     if not v.strip() or any(c.isspace() for c in v)]
        problems += [f"{table} lists the {column} {v!r} {values.count(v)} times" for v in sorted(set(values)) if values.count(v) > 1]
    problems += [f"{table}: {r['key']!r} has no title" for r in rows if not r["title"].strip()]
    return problems


def read_sources():
    """Key -> (IRI, title), from sources.csv, and the problems the table has."""
    rows = read_csv(SOURCE_TABLE)
    return {r["key"]: (SRC[r["slug"]], r["title"]) for r in rows}, source_problems(rows, "sources.csv")


def legs(text):
    return [(b, int(n)) for b, n in (part.split(":") for part in text.split(";") if part)]


def load():
    regions, benchmarks, series = read_csv("regions.csv"), read_csv("benchmarks.csv"), read_csv("series.csv")
    prices, enums = read_csv("market-prices.csv"), read_csv("enumerations.csv")
    region_ids = {r["slug"] for r in regions}
    bench = {b["slug"]: b for b in benchmarks}
    series_ids = {s["slug"] for s in series}
    measures = {str(n) for n in Graph().parse(MEASURES).objects(None, SKOS.notation)}
    sources, problems = read_sources()
    problems += [] if MEASURE_ID in measures else [f"{MEASURE_ID} is not a measure of the kpi module"]
    problems += [f"region {r['slug']}: unknown scheme {r['scheme']!r}" for r in regions if r["scheme"] not in SCHEMES]
    problems += [f"region {r['slug']}: unknown source {r['source']!r}, which is not in sources.csv" for r in regions
                 if r["source"] not in sources]
    problems += [f"enumeration {e['slug']}: unknown source {e['source']!r}, which is not in sources.csv" for e in enums
                 if e["source"] not in sources]
    problems += [f"series {s['slug']}: its note is blank" for s in series if s["note"] and not s["note"].strip()]
    for b in benchmarks:
        if b["region"] and b["region"] not in region_ids:
            problems.append(f"benchmark {b['slug']}: unknown region {b['region']!r}")
        if b["kind"] not in KINDS:
            problems.append(f"benchmark {b['slug']}: unknown kind {b['kind']!r}")
        if b["source"] not in sources:
            problems.append(f"benchmark {b['slug']}: unknown source {b['source']!r}, which is not in sources.csv")
    for s in series:
        if s["region"] and s["region"] not in region_ids:
            problems.append(f"series {s['slug']}: unknown region {s['region']!r}")
        if s["source"] not in sources:
            problems.append(f"series {s['slug']}: unknown source {s['source']!r}, which is not in sources.csv")
        blend = [x for x in s["blend_of"].split(";") if x]
        problems += [f"series {s['slug']}: blends unknown series {x!r}" for x in blend if x not in series_ids]
        if blend and s["legs"]:
            problems.append(f"series {s['slug']}: a blended series has no legs of its own")
        if s["legs_unstated"] and (blend or s["legs"]):
            problems.append(f"series {s['slug']}: legs_unstated is only for a series with neither legs nor a blend")
        if not blend and not s["legs"] and not s["legs_unstated"]:
            problems.append(f"series {s['slug']}: has neither legs nor a blend, and is not marked legs_unstated")
        if not blend and s["legs"]:
            kinds = [bench[b]["kind"] for b, _ in legs(s["legs"]) if b in bench]
            problems += [f"series {s['slug']}: unknown benchmark {b!r}" for b, _ in legs(s["legs"]) if b not in bench]
            if kinds.count("crude-marker") != 1 or "product-benchmark" not in kinds or kinds.count("compliance-cost") > 1:
                problems.append(f"series {s['slug']}: needs one crude leg, at least one product leg and at most one compliance-cost leg")
            if ("compliance-cost" in kinds) != (s["excludes_rin_cost"] == "false"):
                problems.append(f"series {s['slug']}: a series deducts the RVO cost (an RVO leg) exactly when excludes_rin_cost is false")
    labels = {b["label"] for b in benchmarks} | {s["label"] for s in series}
    for p in prices:
        problems += [f"price {p['slug']}: measure {p['measure']!r} is not a measure of the kpi module"] if p["measure"] not in measures else []
        problems += [f"price {p['slug']}: reported as {x!r}" for x in p["reported_as"].split(";") if x not in REPORTED_AS]
        if p["reuses"]:
            if p["reuses"] not in bench:
                problems.append(f"price {p['slug']}: reuses unknown benchmark {p['reuses']!r}")
            elif p["mpr"] and bench[p["reuses"]]["mpr"] != p["mpr"]:
                problems.append(f"price {p['slug']}: its Price Master ID differs from the benchmark it reuses")
        elif p["source"] not in sources:
            problems.append(f"price {p['slug']}: a new price needs a source in sources.csv, not {p['source']!r}")
        elif not p["definition"]:
            problems.append(f"price {p['slug']}: a new price needs a definition")
        elif p["label"] in labels:
            problems.append(f"price {p['slug']}: label {p['label']!r} is another series' or benchmark's; reuse it instead")
    problems += [f"enumeration {e['slug']}: measure {e['measure']!r} is not a measure" for e in enums if e["measure"] not in measures]
    if problems:
        sys.exit("market-data tables do not reconcile:\n  " + "\n  ".join(problems))
    return regions, benchmarks, series, prices, enums


def build(regions, benchmarks, series, prices=(), enums=()):
    sources = read_sources()[0]
    g = Graph()
    for prefix, ns in (("mkt", MKT), ("bkind", BKIND), ("region", REGION), ("benchmark", BENCH), ("series", SERIES),
                       ("leg", LEG), ("measure", MEASURE), ("src", SRC), ("skos", SKOS), ("dcterms", DCTERMS),
                       ("price", PRICE), ("enumeration", ENUM)):
        g.bind(prefix, ns)
    for iri, title in sources.values():
        g.add((iri, RDF.type, DCTERMS.BibliographicResource))
        g.add((iri, DCTERMS.title, Literal(title, lang="en")))

    def concept(iri, scheme, row, source):
        g.add((iri, RDF.type, SKOS.Concept))
        g.add((iri, SKOS.inScheme, scheme))
        g.add((iri, SKOS.topConceptOf, scheme))  # flat schemes, stated both ways (the decision of 2026-10-25, item 5)
        g.add((scheme, SKOS.hasTopConcept, iri))
        g.add((iri, SKOS.prefLabel, Literal(row["label"], lang="en")))
        g.add((iri, SKOS.notation, Literal(row["slug"], datatype=XSD.string)))
        g.add((iri, SKOS.definition, Literal(row["definition"], lang="en")))
        g.add((iri, DCTERMS.source, sources[source][0]))

    for r in regions:
        concept(REGION[r["slug"]], SCHEMES[r["scheme"]], r, r["source"])
    for b in benchmarks:
        iri = BENCH[b["slug"]]
        concept(iri, MKT.Series, b, b["source"])
        g.add((iri, RDF.type, MKT.Benchmark))
        g.add((iri, MKT.benchmarkKind, BKIND[b["kind"]]))
        if b["region"]:
            g.add((iri, MKT.region, REGION[b["region"]]))
        if b["mpr"]:
            g.add((iri, MKT.priceMasterId, Literal(b["mpr"], datatype=XSD.string)))
    for s in series:
        iri = SERIES[s["slug"]]
        concept(iri, MKT.Series, s, s["source"])
        g.add((iri, RDF.type, MKT.BenchmarkSeries))
        g.add((iri, MKT.seriesOf, MEASURE[MEASURE_ID]))
        for alias in (a for a in s["aliases"].split(";") if a):
            g.add((iri, SKOS.altLabel, Literal(alias, lang="en")))
        if s["region"]:
            g.add((iri, MKT.region, REGION[s["region"]]))
        if s["excludes_rin_cost"]:
            g.add((iri, MKT.excludesRINCost, Literal(s["excludes_rin_cost"] == "true")))
        for b, n in legs(s["legs"]):
            leg = LEG[f"{s['slug']}--{b}"]
            g.add((iri, MKT.leg, leg))
            g.add((leg, RDF.type, MKT.Leg))
            g.add((leg, MKT.benchmark, BENCH[b]))
            g.add((leg, MKT.barrels, Literal(n)))
        for x in (x for x in s["blend_of"].split(";") if x):
            g.add((iri, MKT.blendOf, SERIES[x]))
        if s["mpr"]:
            g.add((iri, MKT.priceMasterId, Literal(s["mpr"], datatype=XSD.string)))
        if s["legs_unstated"]:
            g.add((iri, MKT.legsUnstated, Literal(True)))
        if s["note"]:
            g.add((iri, SKOS.scopeNote, Literal(s["note"], lang="en")))
    for p in prices:
        if p["reuses"]:
            iri = BENCH[p["reuses"]]
        else:
            iri = PRICE[p["slug"].removeprefix("price-")]
            concept(iri, MKT.Series, p, p["source"])
            g.add((iri, RDF.type, MKT.MarketPrice))
            g.add((iri, SKOS.editorialNote, Literal(TEMPLATE_NOTE, lang="en")))
            if p["mpr"]:
                g.add((iri, MKT.priceMasterId, Literal(p["mpr"], datatype=XSD.string)))
        g.add((iri, MKT.priceOf, MEASURE[p["measure"]]))
        for x in p["reported_as"].split(";"):
            g.add((iri, MKT.reportedAs, Literal(x, datatype=XSD.string)))
    for e in enums:
        iri = ENUM[e["slug"]]
        g.add((iri, RDF.type, MKT.SeriesEnumeration))
        g.add((iri, MKT.enumerates, MEASURE[e["measure"]]))
        g.add((iri, MKT.sourceView, Literal(e["view"], datatype=XSD.string)))
        g.add((iri, MKT.idColumn, Literal(e["id_column"], datatype=XSD.string)))
        g.add((iri, MKT.nameColumn, Literal(e["name_column"], datatype=XSD.string)))
        if e["group_column"]:
            g.add((iri, MKT.groupColumn, Literal(e["group_column"], datatype=XSD.string)))
        if e["filter"]:
            g.add((iri, MKT.rowFilter, Literal(e["filter"], lang="en")))
        if e["count"]:
            g.add((iri, SKOS.note, Literal(e["count"], lang="en")))
        g.add((iri, DCTERMS.source, sources[e["source"]][0]))
    return g


def figures(regions, benchmarks, series, prices=(), enums=()):
    return {
        "regions": len(regions),
        "market regions": sum(r["scheme"] == "market" for r in regions),
        "benchmarks": len(benchmarks),
        "crude markers": sum(b["kind"] == "crude-marker" for b in benchmarks),
        "price master ids": sum(bool(b["mpr"]) for b in benchmarks) + sum(bool(s["mpr"]) for s in series),
        "series": len(series),
        "legs": sum(len(legs(s["legs"])) for s in series),
        "market prices": sum(not p["reuses"] for p in prices),
        "benchmarks that are also market prices": sum(bool(p["reuses"]) for p in prices),
        "enumerations": len(enums),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    regions, benchmarks, series, prices, enums = load()
    text = ("# Benchmark series of the market-data module (Step 7; the decision of 2026-10-19, the decision of 2026-10-20).\n"
            "# Built by build_market_data.py from regions.csv, benchmarks.csv, series.csv, market-prices.csv and\n"
            "# enumerations.csv. Do not edit by hand.\n"
            + build(regions, benchmarks, series, prices, enums).serialize(format="turtle"))
    print("; ".join(f"{k} {v}" for k, v in figures(regions, benchmarks, series, prices, enums).items()))
    if args.verify:
        if not (os.path.exists(OUTPUT) and open(OUTPUT, encoding="utf-8").read() == text):
            sys.exit("market-data.ttl is not current: run build_market_data.py --write")
        print("market-data.ttl is current")
    if args.write:
        with open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
