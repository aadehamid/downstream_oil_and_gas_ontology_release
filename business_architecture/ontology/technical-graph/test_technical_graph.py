"""Tests for the technical-graph module (the decision of 2026-11-02): the vocabulary, its shapes and the example graph.

Run: python3 -m pytest test_technical_graph.py
"""
import os
import sys
import unittest

from pyshacl import validate
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, SKOS

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "release"))
import newest  # noqa: E402

TG = Namespace("https://w3id.org/mpc/ontology/modules/technical-graph/")
SH = Namespace("http://www.w3.org/ns/shacl#")
VOCAB = Graph().parse(os.path.join(HERE, "vocabulary.ttl"))
SHAPES = Graph().parse(os.path.join(HERE, "shapes.ttl"))
EXAMPLE = Graph().parse(os.path.join(HERE, "example", "example-graph.ttl"))
ONTOLOGY = os.path.join(HERE, "..")
# The releases the module links to by IRI; a graph that uses the vocabulary is checked with them loaded.
LINKED = Graph()
for module in ("data-product", "kpi", "system"):
    LINKED.parse(os.path.join(ONTOLOGY, "releases", module, newest.newest_version(module, ONTOLOGY), f"{module}.ttl"))


def conforms(data):
    ok, _, text = validate(VOCAB + LINKED + data, shacl_graph=SHAPES, inference="none")
    return ok, text


class Vocabulary(unittest.TestCase):
    def test_every_term_has_a_label_a_definition_and_a_citation(self):
        terms = [s for s in set(VOCAB.subjects(RDF.type, None)) if str(s).startswith(str(TG))
                 and not str(s).startswith(str(TG) + "check-result/")]
        self.assertGreater(len(terms), 30)
        for term in terms:
            self.assertEqual(len(list(VOCAB.objects(term, SKOS.definition))), 1, term)
            self.assertTrue(list(VOCAB.objects(term, DCTERMS.bibliographicCitation)), term)

    def test_the_layer_list_is_data_products_not_a_new_one(self):
        # new-module.md, step 2: point to another module's terms by IRI; never redefine them.
        self.assertFalse(any("Layer" in str(s) for s in VOCAB.subjects(RDF.type, SKOS.ConceptScheme)))

    def test_no_owner_property(self):
        # the decision of 2026-11-02, item 3: who answers for it is found through the data product, not a property here.
        props = {str(s) for s in VOCAB.subjects(RDF.type, OWL.ObjectProperty)} | {str(s) for s in VOCAB.subjects(RDF.type, OWL.DatatypeProperty)}
        self.assertFalse([p for p in props if "owner" in p.lower() or "accountab" in p.lower()])

    def test_every_check_result_is_a_top_concept_both_ways(self):
        for c in VOCAB.objects(TG.CheckResults, SKOS.hasTopConcept):
            self.assertIn((c, SKOS.topConceptOf, TG.CheckResults), VOCAB)

    def test_no_shape_message_has_an_apostrophe(self):
        # The ontology skill's SHACL rule 19: some stores mangle an apostrophe in a message.
        for msg in SHAPES.objects(None, SH.message):
            self.assertNotIn("'", str(msg))


class Example(unittest.TestCase):
    def test_the_example_holds_its_committed_figures(self):
        # The example is kept as committed. These figures were counted by hand from the file, so a changed file fails here.
        # 1.1.0 added 13 triples to the 409: two earlier tables (2 each), a job and a pipeline (2 each), two
        # replaces links and three builtBy links.
        self.assertEqual(len(EXAMPLE), 422)
        kinds = {cls: len(set(EXAMPLE.subjects(RDF.type, TG[cls]))) for cls in
                 ("Agent", "DefinitionsView", "Host", "Job", "MetricView", "Orchestrator", "Pipeline", "PipelineStep",
                  "QualityCheck", "SourceDatabase", "Table")}
        self.assertEqual(kinds, {"Agent": 2, "DefinitionsView": 3, "Host": 1, "Job": 1, "MetricView": 3, "Orchestrator": 1,
                                 "Pipeline": 1, "PipelineStep": 5, "QualityCheck": 7, "SourceDatabase": 2, "Table": 21})

    def test_the_example_uses_only_the_vocabulary(self):
        defined = set(VOCAB.subjects())
        used = {p for p in EXAMPLE.predicates() if str(p).startswith(str(TG))}
        used |= {o for o in EXAMPLE.objects(None, RDF.type) if str(o).startswith(str(TG))}
        self.assertEqual(used - defined, set())

    def test_the_example_conforms(self):
        ok, text = conforms(EXAMPLE)
        self.assertTrue(ok, text)


class Questions(unittest.TestCase):
    def test_q47_lists_the_table_that_copies_a_changed_systems_data(self):
        # a change to a system first affects the tables that copy its data.
        with open(os.path.join(ONTOLOGY, "regression", "queries", "q47-affected-by-change.rq"), encoding="utf-8") as f:
            rows = {(str(r.changed), str(r.affected)) for r in (VOCAB + EXAMPLE).query(f.read())}
        copies = {(str(s), str(t)) for t, db in EXAMPLE.subject_objects(TG.copies) for s in EXAMPLE.objects(db, TG.standsFor)}
        self.assertTrue(copies)
        self.assertLessEqual(copies, rows)


DEMO = "urn:kpi-store-example:tech:"
DESIGN = "https://w3id.org/mpc/ontology/modules/data-product/table/"
BATCH, DETAIL = "silver_mdm_core.mips_price_batch_dim", "silver_udm_core.mpr_price_detail_fact"
JOB, PIPELINE = DEMO + "builder/job-nightly-pricing-build", DEMO + "builder/pipeline-price-detail-refresh"


def rows(name, graph):
    with open(os.path.join(ONTOLOGY, "regression", "queries", name), encoding="utf-8") as f:
        return {tuple(None if v is None else str(v) for v in r) for r in graph.query(f.read())}


class Release_1_1_0(unittest.TestCase):
    """What 1.1.0 adds, pinned by hand from its changelog, and what it keeps of 1.0.0."""

    ADDED = {"Builder", "Job", "Pipeline", "builtBy", "replaces"}

    def previous(self):
        # 1.0.0 is the newest package until 1.1.0 is written, and the one before it afterwards.
        for folder in (("releases", "previous"), ("releases",)):
            path = os.path.join(ONTOLOGY, *folder, "technical-graph", "1.0.0", "technical-graph.ttl")
            if os.path.exists(path):
                return Graph().parse(path)
        self.fail("technical-graph 1.0.0 is not on disk")

    def declared(self, g):
        return {s for s in g.subjects(RDF.type, None) if str(s).startswith(str(TG))}

    def test_the_counts_of_each_kind_of_term(self):
        self.assertEqual(len(set(VOCAB.subjects(RDF.type, OWL.Class))), 15)
        self.assertEqual(len(set(VOCAB.subjects(RDF.type, OWL.ObjectProperty))), 15)
        self.assertEqual(len(set(VOCAB.subjects(RDF.type, OWL.DatatypeProperty))), 9)
        self.assertEqual(len(set(VOCAB.subjects(RDF.type, SKOS.Concept))), 3)

    def test_it_declares_every_term_of_1_0_0_and_exactly_five_more(self):
        before, now = self.declared(self.previous()), self.declared(VOCAB)
        self.assertEqual(len(before), 38)   # 12 classes, 22 properties, the code list and its 3 values
        self.assertEqual(before - now, set())
        self.assertEqual({str(s)[len(str(TG)):] for s in now - before}, self.ADDED)

    def test_nothing_is_deprecated(self):
        self.assertEqual(list(VOCAB.subject_objects(OWL.deprecated)), [])

    def test_every_statement_of_1_0_0_is_kept_but_one_definition(self):
        module = URIRef(str(TG).rstrip("/"))
        lost = {t for t in self.previous() if t[0] != module and t not in VOCAB}
        # The one changed statement: the definition of a technical object now lists a builder among its examples.
        self.assertEqual({(s, p) for s, p, _ in lost}, {(TG.TechnicalObject, SKOS.definition)})
        self.assertIn("a pipeline step, a builder, a quality check", str(VOCAB.value(TG.TechnicalObject, SKOS.definition)))

    def test_each_new_property_has_one_domain_one_range_and_a_cardinality(self):
        from rdflib.namespace import RDFS
        for name, domain, rng in (("replaces", TG.DataObject, TG.DataObject), ("builtBy", TG.DataObject, TG.Builder)):
            self.assertEqual(list(VOCAB.objects(TG[name], RDF.type)), [OWL.ObjectProperty])
            self.assertEqual(list(VOCAB.objects(TG[name], RDFS.domain)), [domain])
            self.assertEqual(list(VOCAB.objects(TG[name], RDFS.range)), [rng])
            shapes = [s for s in SHAPES.subjects(SH.path, TG[name]) if (None, SH.property, s) in SHAPES]
            self.assertEqual(len(shapes), 1, name)
            self.assertEqual(SHAPES.value(shapes[0], SH.minCount).toPython(), 0)
            self.assertIsNone(SHAPES.value(shapes[0], SH.maxCount))
            self.assertIn((next(SHAPES.subjects(SH.property, shapes[0])), SH.targetClass, TG.DataObject), SHAPES)

    def test_a_job_and_a_pipeline_are_builders_and_a_builder_is_a_technical_object(self):
        from rdflib.namespace import RDFS
        self.assertEqual(list(VOCAB.objects(TG.Job, RDFS.subClassOf)), [TG.Builder])
        self.assertEqual(list(VOCAB.objects(TG.Pipeline, RDFS.subClassOf)), [TG.Builder])
        self.assertEqual(list(VOCAB.objects(TG.Builder, RDFS.subClassOf)), [TG.TechnicalObject])

    def test_q56_names_what_each_table_replaces(self):
        # Written by hand from the example graph's two made-up links.
        self.assertEqual(rows("q56-replaces.rq", VOCAB + EXAMPLE), {
            (DEMO + "object/" + BATCH, BATCH, DEMO + "earlier/mdm_core.mips_price_batch_dim",
             "earlier_warehouse.mdm_core.mips_price_batch_dim", DESIGN + "silver-mips-price-batch-dim"),
            (DEMO + "object/" + DETAIL, DETAIL, DEMO + "earlier/udm_core.mpr_price_detail_fact",
             "earlier_warehouse.udm_core.mpr_price_detail_fact", DESIGN + "silver-mpr-price-detail-fact")})

    def test_q56_finds_nothing_without_the_links(self):
        g = Graph()
        g += EXAMPLE
        g.remove((None, TG.replaces, None))
        self.assertEqual(rows("q56-replaces.rq", VOCAB + g), set())

    def test_q56b_is_empty_and_fires_on_a_table_that_replaces_itself_or_its_replacement(self):
        self.assertEqual(rows("q56b-replaces-itself.rq", VOCAB + EXAMPLE), set())
        new, old = URIRef(DEMO + "object/" + BATCH), URIRef(DEMO + "earlier/mdm_core.mips_price_batch_dim")
        own = Graph()
        own += EXAMPLE
        own.add((new, TG.replaces, new))
        self.assertEqual(rows("q56b-replaces-itself.rq", own), {(str(new), str(new))})
        back = Graph()
        back += EXAMPLE
        back.add((old, TG.replaces, new))
        self.assertEqual(rows("q56b-replaces-itself.rq", back), {(str(new), str(old)), (str(old), str(new))})

    def test_q57_names_each_tables_builders(self):
        self.assertEqual(rows("q57-built-by.rq", VOCAB + EXAMPLE), {
            (DEMO + "object/" + BATCH, JOB, str(TG.Job), "Nightly pricing build (made up)"),
            (DEMO + "object/" + DETAIL, JOB, str(TG.Job), "Nightly pricing build (made up)"),
            (DEMO + "object/" + DETAIL, PIPELINE, str(TG.Pipeline), "Price detail refresh (made up)")})

    def test_q57_finds_nothing_without_the_links(self):
        g = Graph()
        g += EXAMPLE
        g.remove((None, TG.builtBy, None))
        self.assertEqual(rows("q57-built-by.rq", VOCAB + g), set())


class Shapes(unittest.TestCase):
    """Each shape rejects what it forbids (the ontology skill's negative tests)."""

    def violations(self, change):
        """{(focus node, path, message)} of the report on the example after one change."""
        g = Graph()
        g += EXAMPLE
        change(g)
        _, report, _ = validate(VOCAB + LINKED + g, shacl_graph=SHAPES, inference="none")
        return {(str(report.value(r, SH.focusNode)), str(report.value(r, SH.resultPath)), str(report.value(r, SH.resultMessage)),
                 str(report.value(r, SH.resultSeverity))) for r in report.subjects(RDF.type, SH.ValidationResult)}

    def test_replacing_something_that_is_not_a_data_object_fails_on_that_link(self):
        table, step = URIRef(DEMO + "object/" + BATCH), self.first(TG.PipelineStep)
        self.assertEqual(self.violations(lambda g: g.add((table, TG.replaces, step))),
                         {(str(table), str(TG.replaces), "A data object replaces only other data objects.", str(SH.Violation))})

    def test_a_builder_that_is_not_a_job_or_a_pipeline_fails_on_that_link(self):
        table, step = URIRef(DEMO + "object/" + BATCH), self.first(TG.PipelineStep)
        self.assertEqual(self.violations(lambda g: g.add((table, TG.builtBy, step))),
                         {(str(table), str(TG.builtBy), "A data object is built only by builders: jobs and pipelines.", str(SH.Violation))})

    def test_a_builder_with_no_name_fails(self):
        job = URIRef(JOB)
        self.assertEqual(self.violations(lambda g: g.remove((job, TG.name, None))),
                         {(JOB, str(TG.name), "A technical object has one name.", str(SH.Violation))})

    def test_a_check_with_two_details_fails(self):
        check = self.first(TG.QualityCheck)
        self.assertEqual(self.violations(lambda g: g.add((check, TG.detail, Literal("a second detail")))),
                         {(str(check), str(TG.detail), "A quality check reports at most one detail, as text.", str(SH.Violation))})

    def test_a_database_with_two_table_counts_or_two_row_counts_fails(self):
        from decimal import Decimal
        db = self.first(TG.SourceDatabase)
        self.assertEqual(self.violations(lambda g: g.add((db, TG.tables, Literal(Decimal("99"))))),
                         {(str(db), str(TG.tables), "A source database has at most one count of tables, a decimal.", str(SH.Violation))})
        self.assertEqual(self.violations(lambda g: g.add((db, TG.rows, Literal(Decimal("99"))))),
                         {(str(db), str(TG.rows), "A technical object has at most one row count, a decimal.", str(SH.Violation))})

    def test_a_table_with_two_row_counts_still_fails(self):
        from decimal import Decimal
        table = URIRef(DEMO + "object/" + BATCH)
        self.assertEqual(self.violations(lambda g: g.add((table, TG.rows, Literal(Decimal("99"))))),
                         {(str(table), str(TG.rows), "A technical object has at most one row count, a decimal.", str(SH.Violation))})

    def test_every_property_states_a_cardinality(self):
        stated = {SHAPES.value(s, SH.path) for s in SHAPES.subjects(SH.path, None)
                  if (s, SH.minCount, None) in SHAPES or (s, SH.maxCount, None) in SHAPES}
        props = set(VOCAB.subjects(RDF.type, OWL.ObjectProperty)) | set(VOCAB.subjects(RDF.type, OWL.DatatypeProperty))
        self.assertEqual(len(props), 24)
        self.assertEqual(props - stated, set())

    def test_a_table_may_replace_two_tables_and_have_two_builders(self):
        table = URIRef(DEMO + "object/" + BATCH)
        self.assertEqual(self.violations(lambda g: (
            g.add((table, TG.replaces, URIRef(DEMO + "earlier/udm_core.mpr_price_detail_fact"))),
            g.add((table, TG.builtBy, URIRef(PIPELINE))))), set())

    def broken(self, change):
        g = Graph()
        g += EXAMPLE
        change(g)
        return conforms(g)[0]

    def first(self, cls):
        return sorted(EXAMPLE.subjects(RDF.type, cls))[0]

    def test_a_result_off_the_list_fails(self):
        check = self.first(TG.QualityCheck)
        self.assertFalse(self.broken(lambda g: (g.remove((check, TG.result, None)),
                                                g.add((check, TG.result, URIRef("urn:example:unknown"))))))

    def test_a_metric_view_computing_no_measure_fails(self):
        view = self.first(TG.MetricView)
        self.assertFalse(self.broken(lambda g: g.remove((view, TG.implements, None))))

    def test_a_layer_outside_data_products_list_fails(self):
        table = self.first(TG.Table)
        self.assertFalse(self.broken(lambda g: (g.remove((table, TG.layer, None)),
                                                g.add((table, TG.layer, URIRef("urn:example:bronze"))))))

    def test_two_layers_fail(self):
        table = next(t for t in sorted(EXAMPLE.subjects(RDF.type, TG.Table)) if (t, TG.layer, None) in EXAMPLE)
        layer = URIRef("https://w3id.org/mpc/ontology/modules/data-product/layer/gold")
        other = URIRef("https://w3id.org/mpc/ontology/modules/data-product/layer/silver")
        self.assertFalse(self.broken(lambda g: (g.add((table, TG.layer, layer)), g.add((table, TG.layer, other)))))

    def test_reading_from_something_not_a_data_object_fails(self):
        view = self.first(TG.MetricView)
        self.assertFalse(self.broken(lambda g: g.add((view, TG.readsFrom, self.first(TG.PipelineStep)))))

    def test_a_check_with_no_time_fails(self):
        check = self.first(TG.QualityCheck)
        self.assertFalse(self.broken(lambda g: g.remove((check, TG.checkedAt, None))))

    def test_a_step_with_no_order_fails(self):
        step = self.first(TG.PipelineStep)
        self.assertFalse(self.broken(lambda g: g.remove((step, TG.order, None))))

    def test_a_database_standing_for_a_non_system_fails(self):
        db = self.first(TG.SourceDatabase)
        self.assertFalse(self.broken(lambda g: (g.remove((db, TG.standsFor, None)),
                                                g.add((db, TG.standsFor, URIRef("urn:example:not-a-system"))))))

    def test_an_orchestrator_routing_nowhere_fails(self):
        orchestrator = self.first(TG.Orchestrator)
        self.assertFalse(self.broken(lambda g: g.remove((orchestrator, TG.routesTo, None))))

    def test_a_check_result_with_two_labels_fails(self):
        result = URIRef("https://w3id.org/mpc/ontology/modules/technical-graph/check-result/pass")
        self.assertFalse(self.broken(lambda g: g.add((result, SKOS.prefLabel, Literal("Passed", lang="en")))))

    def test_a_table_copying_two_databases_fails(self):
        table = next(t for t in sorted(EXAMPLE.subjects(TG.copies, None)))
        other = next(d for d in sorted(EXAMPLE.subjects(RDF.type, TG.SourceDatabase)) if (table, TG.copies, d) not in EXAMPLE)
        self.assertFalse(self.broken(lambda g: g.add((table, TG.copies, other))))

    def test_an_agent_bound_to_a_non_data_object_fails(self):
        agent = self.first(TG.Agent)
        self.assertFalse(self.broken(lambda g: g.add((agent, TG.binds, self.first(TG.PipelineStep)))))

    def test_two_producing_steps_fail(self):
        table = next(t for t in sorted(EXAMPLE.subjects(TG.producedBy, None)) if (t, RDF.type, TG.Table) in EXAMPLE)
        other = next(s for s in sorted(EXAMPLE.subjects(RDF.type, TG.PipelineStep)) if (table, TG.producedBy, s) not in EXAMPLE)
        self.assertFalse(self.broken(lambda g: g.add((table, TG.producedBy, other))))

    def test_a_design_that_is_neither_a_concept_nor_an_agent_fails(self):
        table = self.first(TG.Table)
        self.assertFalse(self.broken(lambda g: (g.remove((table, TG.designedAs, None)),
                                                g.add((table, TG.designedAs, URIRef("urn:example:not-a-design"))))))

    def test_a_check_testing_nothing_fails(self):
        check = self.first(TG.QualityCheck)
        self.assertFalse(self.broken(lambda g: g.remove((check, TG.checks, None))))

    def test_a_refresh_that_is_not_a_time_fails(self):
        table = next(t for t in sorted(EXAMPLE.subjects(TG.lastRefresh, None)))
        self.assertFalse(self.broken(lambda g: (g.remove((table, TG.lastRefresh, None)),
                                                g.add((table, TG.lastRefresh, Literal("yesterday"))))))

    def test_a_database_on_two_hosts_fails(self):
        db = next(d for d in sorted(EXAMPLE.subjects(TG.hostedOn, None)))
        self.assertFalse(self.broken(lambda g: g.add((db, TG.hostedOn, URIRef("urn:example:another-host")))))

    def test_a_name_in_two_forms_fails(self):
        table = self.first(TG.Table)
        self.assertFalse(self.broken(lambda g: g.add((table, TG.name, Literal("another name")))))


if __name__ == "__main__":
    unittest.main()
