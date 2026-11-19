"""Tests for the market-data module (Step 7; the decision of 2026-10-19, the decision of 2026-10-20): the build is
current, each series' recipe matches MPC Economics', MPC's and CME's wording, a series with a different region, legs or RIN
treatment is a different series, and SHACL accepts the module and rejects broken series.

Run: python3 -m pytest test_market_data.py (needs rdflib, pyshacl).
"""
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from pyshacl import validate
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SKOS

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_market_data as bm  # noqa: E402

MKT, SERIES, BENCH, REGION, LEG, MEASURE = bm.MKT, bm.SERIES, bm.BENCH, bm.REGION, bm.LEG, bm.MEASURE
VOCAB = Graph().parse(os.path.join(HERE, "vocabulary.ttl"))
SHAPES = Graph().parse(os.path.join(HERE, "shapes.ttl"))
DATA = Graph().parse(os.path.join(HERE, "market-data.ttl"))
CONTEXT = Graph().parse(bm.MEASURES).parse(os.path.join(HERE, "..", "kpi", "vocabulary.ttl"))


def recipe(series):
    return {(str(DATA.value(l, MKT.benchmark))[len(str(BENCH)):], int(DATA.value(l, MKT.barrels)))
            for l in DATA.objects(SERIES[series], MKT.leg)}


def conforms(g):
    return validate(g + VOCAB + CONTEXT, shacl_graph=SHAPES, advanced=True)[0]


class Build(unittest.TestCase):
    def test_build_is_current(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_market_data.py"), "--verify"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_figures(self):
        # Counted by hand from the tables. 1.1.0 adds two NYMEX crack series, 44 prices (40 new, 4 that reuse a
        # benchmark: LA CARBOB, USGC CBOB, USGC ULSD and NYMEX WTI 747) and 6 enumerations (the decision of 2026-10-25).
        self.assertEqual(bm.figures(*bm.load()), {"regions": 9, "market regions": 6, "benchmarks": 24, "crude markers": 7,
                                                  "price master ids": 23, "series": 15, "legs": 28, "market prices": 40,
                                                  "benchmarks that are also market prices": 4, "enumerations": 6})

    def test_each_pricing_measure_has_its_prices_and_its_enumeration(self):
        # the decision of 2026-10-25, items 4 and 5, counted by hand from the agents' filters.
        measure = "https://w3id.org/mpc/ontology/modules/kpi/measure/"
        count = lambda m: len(set(DATA.subjects(MKT.priceOf, URIRef(measure + m))))
        self.assertEqual([count(m) for m in ("gasoline-prices", "distillate-prices", "crude-prices", "additional-market-prices")],
                         [8, 9, 15, 12])
        enumerated = {str(o).rsplit("/", 1)[1] for o in DATA.objects(None, MKT.enumerates)}
        self.assertEqual(enumerated, {"crack-spreads", "gasoline-prices", "distillate-prices", "crude-prices",
                                      "additional-market-prices"})
        crack = URIRef("https://w3id.org/mpc/ontology/modules/market-data/enumeration/crack-spreads")
        self.assertEqual((str(DATA.value(crack, MKT.idColumn)), str(DATA.value(crack, MKT.nameColumn)),
                          str(DATA.value(crack, MKT.groupColumn))), ("Price_Master_ID", "Price_Master_Name", "MIPS_Groups_Text"))

    def test_the_benchmark_views_five_instruments_serve_crude_prices(self):
        ids = {str(DATA.value(s, MKT.priceMasterId)) for s in
               DATA.subjects(MKT.priceOf, URIRef("https://w3id.org/mpc/ontology/modules/kpi/measure/crude-prices"))}
        self.assertTrue({"572", "747", "750", "752", "9471"} <= ids)

    def test_every_scheme_states_its_top_concepts_both_ways(self):
        for g, scheme in ((DATA, MKT.Series), (DATA, MKT.RefiningRegions), (DATA, MKT.MarketRegions), (VOCAB, MKT.BenchmarkKind)):
            members = set(g.subjects(SKOS.inScheme, scheme))
            self.assertTrue(members)
            self.assertEqual(set(g.objects(scheme, SKOS.hasTopConcept)), members, scheme)
            self.assertEqual(set(g.subjects(SKOS.topConceptOf, scheme)), members, scheme)

    def test_recipes(self):
        # MPC FY2025 Form 10-K, Item 7: "three barrels of MEH crude producing two barrels of USGC CBOB gasoline
        # and one barrel of USGC ULSD", and the same pattern for the other regions; CME for the NYMEX spread.
        self.assertEqual(recipe("crack-gulf-coast-3-2-1"), {("meh", 3), ("usgc-cbob", 2), ("usgc-ulsd", 1)})
        self.assertEqual(recipe("crack-mid-continent-3-2-1"), {("wti", 3), ("chicago-cbob", 2), ("chicago-ulsd", 1)})
        self.assertEqual(recipe("crack-west-coast-3-2-1"), {("ans", 3), ("la-carbob", 2), ("la-carb-diesel", 1)})
        self.assertEqual(recipe("crack-nymex-3-2-1"), {("nymex-wti", 3), ("nymex-rbob", 2), ("nymex-ny-harbor-ulsd", 1)})
        # MPC Economics' definition, sections 4.1 and 4.2: each ex-RIN crack deducts the RVO (MPR 13056) from every product barrel.
        self.assertEqual(recipe("crack-mpr-43870"), {("mpr-14133", 3), ("mpr-11926", 2), ("mpr-12838", 1), ("mpr-13056", 3)})
        self.assertEqual(recipe("crack-mpr-37438"), {("mpr-747", 3), ("mpr-16475", 2), ("mpr-16477", 1), ("mpr-13056", 3)})
        self.assertEqual(recipe("crack-mpr-37439"), {("mpr-747", 3), ("mpr-13076", 2), ("mpr-9408", 1), ("mpr-13056", 3)})
        self.assertEqual(recipe("crack-mpr-36855"), {("mpr-4055", 3), ("mpr-9660", 2), ("mpr-9657", 1), ("mpr-13056", 3)})

    def test_legs_unstated(self):
        # The definition names the PNW and SLC series but does not list their input legs (section 4.2, note).
        for series in ("crack-mpr-37443", "crack-mpr-37471"):
            self.assertEqual(DATA.value(SERIES[series], MKT.legsUnstated), Literal(True))
            self.assertEqual(recipe(series), set())

    def test_price_master_ids_and_regions(self):
        # MPC Economics' definition, sections 4.1, 4.3 and 4.4: each series with its own ID and market region.
        expected = {"crack-mpr-43870": ("43870", "usgc"), "crack-mpr-37438": ("37438", "chicago"),
                    "crack-mpr-37439": ("37439", "group-3"), "crack-mpr-36855": ("36855", "la"),
                    "crack-mpr-37443": ("37443", "pnw"), "crack-mpr-37471": ("37471", "slc"),
                    "crack-mpr-37464": ("37464", None), "crack-mpr-42023": ("42023", None),
                    "crack-nymex-3-2-1": ("39998", None)}
        for series, (mpr, region) in expected.items():
            self.assertEqual(str(DATA.value(SERIES[series], MKT.priceMasterId)), mpr, series)
            self.assertEqual(DATA.value(SERIES[series], MKT.region), REGION[region] if region else None, series)

    def test_economics_blend(self):
        for blend in ("crack-mpr-37464", "crack-mpr-42023"):
            self.assertEqual(set(DATA.objects(SERIES[blend], MKT.blendOf)),
                             {SERIES["crack-mpr-43870"], SERIES["crack-mpr-37438"], SERIES["crack-mpr-36855"]})
            self.assertIn("USGC 0.40, Chicago 0.40 and LA 0.20 before 5 May 2024, and USGC 0.42, Chicago 0.40 and LA 0.18 after",
                          str(DATA.value(SERIES[blend], SKOS.scopeNote)))

    def test_blend(self):
        self.assertEqual(set(DATA.objects(SERIES["crack-blended-3-2-1"], MKT.blendOf)),
                         {SERIES["crack-gulf-coast-3-2-1"], SERIES["crack-mid-continent-3-2-1"], SERIES["crack-west-coast-3-2-1"]})
        self.assertFalse(list(DATA.objects(SERIES["crack-blended-3-2-1"], MKT.leg)))

    def test_same_measure_different_series(self):
        series = set(DATA.subjects(MKT.seriesOf, MEASURE["crack-spreads"]))
        self.assertEqual(len(series), 15)  # 13, then the two NYMEX cracks of 1.1.0 (the decision of 2026-10-25, item 5)
        # MPC's 10-K cracks do not reflect RIN costs; MPC Economics' ex-RIN cracks deduct them (the decision of 2026-10-20);
        # the exchange spread states nothing about RINs.
        self.assertEqual(DATA.value(SERIES["crack-gulf-coast-3-2-1"], MKT.excludesRINCost), Literal(True))
        for s in ("crack-mpr-43870", "crack-mpr-37438", "crack-mpr-37439", "crack-mpr-36855", "crack-mpr-37443", "crack-mpr-37471",
                  "crack-mpr-37464", "crack-mpr-42023"):
            self.assertEqual(DATA.value(SERIES[s], MKT.excludesRINCost), Literal(False), s)
        for s in ("crack-mid-continent-3-2-1", "crack-west-coast-3-2-1", "crack-blended-3-2-1"):
            self.assertEqual(DATA.value(SERIES[s], MKT.excludesRINCost), Literal(True), s)
        self.assertIsNone(DATA.value(SERIES["crack-nymex-3-2-1"], MKT.excludesRINCost))
        # Same crude and product markets, opposite RIN treatment: two series.
        self.assertNotEqual(SERIES["crack-gulf-coast-3-2-1"], SERIES["crack-mpr-43870"])

    def test_planner_names_resolve(self):
        # The planner list's crack names (kpi measure crack-spreads, classification reason) are MPC Economics'
        # published ex-RIN series, not MPC's 10-K cracks (the decision of 2026-10-20).
        self.assertEqual(set(DATA.subjects(SKOS.altLabel, Literal("USGC 3-2-1 MEH ex-RIN", lang="en"))), {SERIES["crack-mpr-43870"]})
        self.assertEqual(set(DATA.subjects(SKOS.altLabel, Literal("Chicago WTI 3-2-1 ex-RIN", lang="en"))), {SERIES["crack-mpr-37438"]})
        self.assertEqual(set(DATA.subjects(SKOS.altLabel, Literal("NYMEX 3-2-1", lang="en"))), {SERIES["crack-nymex-3-2-1"]})


class Tables(unittest.TestCase):
    """A new source is a row in sources.csv, with no change to build_market_data.py (KPI-DEC-0002, Q12)."""

    def build_with(self, edit):
        """Build from a temporary copy of the module's tables after edit(folder) changes them."""
        with tempfile.TemporaryDirectory() as d:
            for name in os.listdir(HERE):
                if name.endswith(".csv"):
                    shutil.copy(os.path.join(HERE, name), d)
            edit(d)
            with mock.patch.object(bm, "HERE", d):
                return bm.build(*bm.load())

    @staticmethod
    def append(folder, name, row):
        with open(os.path.join(folder, name), newline="", encoding="utf-8") as f:
            fields = csv.DictReader(f).fieldnames
        with open(os.path.join(folder, name), "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields, lineterminator="\n").writerow(row)

    def test_a_new_source_is_one_row(self):
        def edit(d):
            self.append(d, "sources.csv", {"key": "ARGUS", "slug": "argus-crack-spreads-2026", "title": "Argus, a test title"})
            self.append(d, "benchmarks.csv", {"slug": "test-crude", "label": "Test crude", "kind": "crude-marker",
                                              "region": "", "definition": "A test crude marker.", "source": "ARGUS", "mpr": ""})
        g = self.build_with(edit)
        src = URIRef("https://w3id.org/mpc/ontology/source/argus-crack-spreads-2026")
        dcterms = "http://purl.org/dc/terms/"
        self.assertEqual(g.value(src, URIRef(dcterms + "title")), Literal("Argus, a test title", lang="en"))
        self.assertEqual(g.value(BENCH["test-crude"], URIRef(dcterms + "source")), src)

    def test_a_row_naming_an_unknown_source_fails(self):
        def edit(d):
            self.append(d, "benchmarks.csv", {"slug": "test-crude", "label": "Test crude", "kind": "crude-marker",
                                              "region": "", "definition": "A test crude marker.", "source": "ARGUS", "mpr": ""})
        with self.assertRaises(SystemExit) as caught:
            self.build_with(edit)
        self.assertIn("benchmark test-crude: unknown source 'ARGUS', which is not in sources.csv", str(caught.exception))

    def test_a_new_region_and_enumeration_cite_the_source_their_rows_name(self):
        def edit(d):
            self.append(d, "sources.csv", {"key": "ARGUS", "slug": "argus-crack-spreads-2026", "title": "Argus, a test title"})
            self.append(d, "regions.csv", {"slug": "test-region", "label": "Test region", "definition": "A test region.",
                                           "scheme": "market", "source": "ARGUS"})
            self.append(d, "enumerations.csv", {"slug": "test-enum", "measure": "crack-spreads", "view": "v", "id_column": "i",
                                                "name_column": "n", "group_column": "", "filter": "", "count": "",
                                                "source": "ARGUS"})
        g = self.build_with(edit)
        src = URIRef("https://w3id.org/mpc/ontology/source/argus-crack-spreads-2026")
        dcterms = URIRef("http://purl.org/dc/terms/source")
        self.assertEqual(g.value(REGION["test-region"], dcterms), src)
        self.assertEqual(g.value(URIRef(str(bm.ENUM) + "test-enum"), dcterms), src)

    def test_a_series_note_is_its_note_cell(self):
        def edit(d):
            path = os.path.join(d, "series.csv")
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fields, rows = reader.fieldnames, list(reader)
            for r in rows:
                if r["slug"] == "crack-blended-3-2-1":
                    r["note"] = "From the third quarter of 2026, a test weighting."
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
        g = self.build_with(edit)
        self.assertEqual(set(g.objects(SERIES["crack-blended-3-2-1"], SKOS.scopeNote)),
                         {Literal("From the third quarter of 2026, a test weighting.", lang="en")})

    def test_a_bad_sources_row_fails(self):
        cases = (({"key": "MPC-S01", "slug": "x", "title": "x"}, "sources.csv lists the key 'MPC-S01' 2 times"),
                 ({"key": "A RGUS", "slug": "x", "title": "x"}, "sources.csv: the key 'A RGUS' must not be empty or hold a space"),
                 ({"key": "ARGUS", "slug": "mpc-performance-measures-evidence", "title": "x"},
                  "sources.csv lists the slug 'mpc-performance-measures-evidence' 2 times"),
                 ({"key": "ARGUS", "slug": "x", "title": " "}, "sources.csv: 'ARGUS' has no title"))
        for row, message in cases:
            with self.assertRaises(SystemExit) as caught:
                self.build_with(lambda d: self.append(d, "sources.csv", row))
            self.assertIn(message, str(caught.exception))


class Shapes(unittest.TestCase):
    def test_module_conforms(self):
        self.assertTrue(conforms(DATA))

    def broken(self, edit):
        g = Graph()
        for t in DATA:
            g.add(t)
        edit(g)
        return conforms(g)

    def test_rejects_legs_and_blend(self):
        self.assertFalse(self.broken(lambda g: g.add((SERIES["crack-blended-3-2-1"], MKT.leg, LEG["crack-gulf-coast-3-2-1--meh"]))))

    def test_rejects_a_market_price_with_no_measure(self):
        p = URIRef("https://w3id.org/mpc/ontology/modules/market-data/price/nyh-cbob")
        self.assertFalse(self.broken(lambda g: g.remove((p, MKT.priceOf, None))))

    def test_rejects_a_value_on_an_enumeration(self):
        e = URIRef("https://w3id.org/mpc/ontology/modules/market-data/enumeration/crack-spreads")
        self.assertFalse(self.broken(lambda g: g.add((e, RDF.value, Literal(127)))))

    def test_rejects_a_price_on_a_market_price(self):
        p = URIRef("https://w3id.org/mpc/ontology/modules/market-data/price/nyh-cbob")
        self.assertFalse(self.broken(lambda g: g.add((p, RDF.value, Literal(2.31)))))

    def test_rejects_a_price(self):
        self.assertFalse(self.broken(lambda g: g.add((BENCH["wti"], MKT.price, Literal(65.5)))))

    def test_rejects_a_price_on_a_leg(self):
        self.assertFalse(self.broken(lambda g: g.add((LEG["crack-gulf-coast-3-2-1--meh"], MKT.price, Literal(65.5)))))

    def test_shared_source_keeps_one_title(self):
        # src:mpc-performance-measures-evidence is also declared by the kpi module.
        kpi = Graph().parse(bm.MEASURES)
        src = bm.read_sources()[0]["MPC-S01"][0]
        both = set(DATA.objects(src, URIRef("http://purl.org/dc/terms/title"))) | set(kpi.objects(src, URIRef("http://purl.org/dc/terms/title")))
        self.assertEqual(len(both), 1, both)

    def test_rejects_a_value_on_a_region(self):
        self.assertFalse(self.broken(lambda g: g.add((REGION["gulf-coast"], MKT.price, Literal(65.5)))))

    def test_rejects_a_series_of_no_measure(self):
        self.assertFalse(self.broken(lambda g: g.remove((SERIES["crack-west-coast-3-2-1"], MKT.seriesOf, None))))

    def test_rejects_unstated_legs_beside_legs(self):
        self.assertFalse(self.broken(lambda g: g.add((SERIES["crack-mpr-43870"], MKT.legsUnstated, Literal(True)))))

    def test_rejects_a_value_on_a_market_region(self):
        self.assertFalse(self.broken(lambda g: g.add((REGION["pnw"], MKT.price, Literal(65.5)))))

    def test_rejects_a_region_off_the_list(self):
        self.assertFalse(self.broken(lambda g: g.add((SERIES["crack-nymex-3-2-1"], MKT.region, BENCH["wti"]))))


if __name__ == "__main__":
    unittest.main()
