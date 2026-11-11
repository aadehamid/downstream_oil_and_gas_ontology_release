"""The technical graph built from the made-up workspace with the sandbox's shapes.

Every expected figure is written by hand from support.sandbox(): its objects, lineage rows, jobs and Genie
spaces. Nothing here is read back from the code under test.
"""
import json
import random
from pathlib import Path

import pytest

from kpi_store import discovery as disc
from kpi_store import load_databricks as lb
from kpi_store import ontology_view as ov
from kpi_store import tech_graph as tg
from kpi_store.tests import support

ENV = "urn:kpi-store:tech:idp_sbx+synapse_dev:"
OBJECT = ENV + "object/"
DESIGN = "https://w3id.org/mpc/ontology/modules/data-product/table/"
MEASURE = "https://w3id.org/mpc/ontology/modules/kpi/measure/"
SEMANTIC = "idp_sbx.semantic_sem_commercial."
GOLD_SUMMARY = "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"
JOB, PIPELINE = ENV + "builder/job-9001", ENV + "builder/pipeline-pipe-0001"
# The eight tables of the earlier platform, each replaced by the table of the same name one layer schema over.
REPLACED = {
    "idp_sbx.silver_mdm_core.mips_price_assessment_group_dim": "synapse_dev.mdm_core.mips_price_assessment_group_dim",
    "idp_sbx.silver_mdm_core.mips_price_batch_dim": "synapse_dev.mdm_core.mips_price_batch_dim",
    "idp_sbx.silver_mdm_core.mips_price_group_dim": "synapse_dev.mdm_core.mips_price_group_dim",
    "idp_sbx.silver_mdm_core.mips_price_sheet_dim": "synapse_dev.mdm_core.mips_price_sheet_dim",
    "idp_sbx.silver_mdm_core.mpr_price_master_dim": "synapse_dev.mdm_core.mpr_price_master_dim",
    "idp_sbx.silver_udm_core.mips_price_assessment_fact": "synapse_dev.udm_core.mips_price_assessment_fact",
    "idp_sbx.silver_udm_core.mpr_price_detail_fact": "synapse_dev.udm_core.mpr_price_detail_fact",
    GOLD_SUMMARY: "synapse_dev.commercial_core.mips_mpr_executive_summary_fact",
}
# The objects the workspace holds and the ontology does not: no design to point to.
EXTRAS = (
    "idp_sbx.gold_commercial_core.sample_margin_fact", "idp_sbx.gold_commercial_core.sample_volume_fact",
    "idp_sbx.silver_mdm_core.sample_location_dim", "idp_sbx.silver_mdm_core.sample_product_dim",
    "idp_sbx.silver_udm_core.sample_trade_fact", SEMANTIC + "mpr_mips_crack_spread_price_fact_metricsfromsilver_vw",
    SEMANTIC + "mpr_mips_crack_spread_price_fact_vw", "synapse_dev.replica_mpr.sample_unused_source",
)


@pytest.fixture(scope="module")
def reading():
    """(Discovery, OntologyView, Settings): the sandbox-shaped workspace read against the release's own packages."""
    workspace, genie = support.sandbox()
    settings = support.make_settings()
    view = ov.read(support.ROOT)
    schemas = {settings.environment_name(o.full_name).rsplit(".", 1)[0] for o in view.objects.values()}
    return disc.discover(settings, workspace.run_sql, genie, schemas), view, settings


@pytest.fixture(scope="module")
def graph(reading):
    return tg.build(*reading)


def values(graph, subject, name):
    return sorted(o for s, p, o in graph.triples if s == subject and p == tg.TG + name)


# ---- what the graph holds ---------------------------------------------------------------------------

def test_the_nodes_of_each_class(graph):
    # 44 tables: 21 replica, 7 silver, 2 gold, 5 unused silver and gold, 1 unused replica, 8 of the earlier platform.
    # 3 metric views the ontology names. 2 views: the plain view, and the metric view the ontology names no measure for.
    assert graph.summary()["classes"] == {"Agent": 2, "Job": 1, "MetricView": 3, "Pipeline": 1, "Table": 44, "View": 2}


def test_the_links_of_each_kind(graph):
    assert graph.summary()["properties"] == {
        "name": 53,          # every node has one
        "designedAs": 33,    # the 33 objects of the ontology
        "layer": 41,         # every object but the 8 of the earlier platform, whose schemas name no layer
        "implements": 6,     # benchmark 1, executive summary 4, crack spread 1
        "readsFrom": 52,     # the 40 designed edges, 3 of the unnamed metric view, 8 migrations, 1 into an unused table
        "builtBy": 10,       # the job writes 7 silver and 2 gold tables; the pipeline writes 1 unused table
        "lastRefresh": 10,   # the same 10 tables
        "binds": 3,          # one space to two metric views, the other to one
        "replaces": 8,
    }
    assert graph.summary()["triples"] == 269   # the 216 above and one type for each of the 53 nodes


def test_all_33_ontology_objects_are_found_and_point_to_their_designs(graph, reading):
    _, view, _ = reading
    links = graph.links("designedAs")
    assert len(links) == 33 and len({o for _, o in links}) == 33
    assert {o for _, o in links} == {o.iri for o in view.objects.values()}
    assert (OBJECT + GOLD_SUMMARY, DESIGN + "gold-mips-mpr-executive-summary-fact") in links
    assert (OBJECT + "synapse_dev.replica_mpr.pricedetail", DESIGN + "replica-mpr-pricedetail") in links


def test_a_name_is_matched_without_case_and_through_the_names_map(reading):
    found, view, _ = reading
    doc = json.loads(found.to_json())
    renamed = {}
    for key, info in doc["tables"].items():
        if info["catalog"] == "idp_sbx":
            info = {**info, "catalog": "IDP_PRD", "full_name": "IDP_PRD." + info["full_name"].split(".", 1)[1].upper()}
            key = "idp_prd." + key.split(".", 1)[1]
        renamed[key] = info
    doc["tables"] = renamed
    doc["table_edges"], doc["migration_pairs"], doc["metric_views"], doc["genie_spaces"] = [], [], {}, []
    settings = support.make_settings(read_catalogs='read_catalogs = ["idp_prd", "synapse_dev"]', write_catalog='write_catalog = "idp_prd"',
                                     idp_sbx='idp_sbx = "idp_prd"')
    built = tg.build(doc, view, settings)
    assert len(built.links("designedAs")) == 33
    subject = "urn:kpi-store:tech:idp_prd+synapse_dev:object/idp_prd.gold_commercial_core.mips_mpr_executive_summary_fact"
    assert (subject, DESIGN + "gold-mips-mpr-executive-summary-fact") in built.links("designedAs")
    assert values(built, subject, "name") == ['"IDP_PRD.GOLD_COMMERCIAL_CORE.MIPS_MPR_EXECUTIVE_SUMMARY_FACT"']


def test_the_eight_replaces_links(graph):
    assert graph.links("replaces") == sorted((OBJECT + new, OBJECT + old) for new, old in REPLACED.items())


def test_a_replaced_table_is_a_table_with_its_name_and_no_layer_or_design(graph):
    old = OBJECT + "synapse_dev.mdm_core.mips_price_batch_dim"
    assert old in graph.subjects("Table")
    assert values(graph, old, "name") == ['"synapse_dev.mdm_core.mips_price_batch_dim"']
    assert values(graph, old, "layer") == [] and values(graph, old, "designedAs") == []


def test_the_extras_are_objects_with_no_design(graph):
    designed = {s for s, _ in graph.links("designedAs")}
    objects = set(graph.subjects("Table")) | set(graph.subjects("View")) | set(graph.subjects("MetricView"))
    for name in EXTRAS:
        assert OBJECT + name in objects, name
        assert OBJECT + name not in designed, name
    assert len(objects - designed) == 16   # the 8 extras and the 8 tables of the earlier platform


def test_skipped_and_out_of_scope_objects_are_left_out(graph):
    subjects = {s for s, _, _ in graph.triples}
    for name in ("synapse_dev.replica_mpr.pricedetail__ct", "synapse_dev.replica_mips.attrep_apply_exceptions",
                 "idp_sbx.bronze_replica_mpr.pricedetail", "idp_sbx.kpi_store_poc.old_triples",
                 "other_catalog.gold_commercial_core.elsewhere_fact", "idp_sbx.staging.dropped_stage_table"):
        assert OBJECT + name not in subjects, name


def test_the_layer_comes_from_the_schema_name(graph):
    layer = "<https://w3id.org/mpc/ontology/modules/data-product/layer/%s>"
    assert values(graph, OBJECT + "synapse_dev.replica_mips.mips_currency", "layer") == [layer % "replica"]
    assert values(graph, OBJECT + "idp_sbx.silver_mdm_core.sample_location_dim", "layer") == [layer % "silver"]
    assert values(graph, OBJECT + GOLD_SUMMARY, "layer") == [layer % "gold"]
    assert values(graph, OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw", "layer") == [layer % "metric-view"]
    assert tg.schema_layer("Silver_MDM_Core") == "silver"
    assert tg.schema_layer("mdm_core") is None and tg.schema_layer("silver") is None


def test_reads_from_is_the_live_lineage_and_the_metric_views_own_definitions(graph):
    reads = graph.links("readsFrom")
    assert (OBJECT + GOLD_SUMMARY, OBJECT + "idp_sbx.silver_udm_core.mips_price_assessment_fact") in reads
    # The lineage rows leave this edge out; the benchmark view's definition names the joined table.
    assert (OBJECT + SEMANTIC + "mips_mpr_benchmark_prices_fact_vw", OBJECT + "idp_sbx.silver_mdm_core.mpr_price_master_dim") in reads
    # The migration is lineage too: the new table was loaded from the old one.
    assert (OBJECT + "idp_sbx.silver_mdm_core.mips_price_batch_dim", OBJECT + "synapse_dev.mdm_core.mips_price_batch_dim") in reads
    # The metric view the ontology does not name reads the three tables its SQL names.
    unnamed = OBJECT + SEMANTIC + "mpr_mips_crack_spread_price_fact_metricsfromsilver_vw"
    assert [o for s, o in reads if s == unnamed] == [OBJECT + "idp_sbx.silver_mdm_core.mips_price_group_dim",
                                                    OBJECT + "idp_sbx.silver_udm_core.mips_price_assessment_fact",
                                                    OBJECT + "idp_sbx.silver_udm_core.mpr_price_detail_fact"]
    # No table reads itself, though the lineage rows hold such a row.
    assert all(s != o for s, o in reads)


def test_reads_from_does_not_come_from_the_ontology(reading):
    found, view, settings = reading
    doc = json.loads(found.to_json())
    doc["table_edges"], doc["metric_views"], doc["migration_pairs"] = [], {}, []
    built = tg.build(doc, view, settings)
    assert len(view.edges) == 40 and built.links("readsFrom") == []
    assert len(built.links("designedAs")) == 33


def test_the_builders(graph):
    assert graph.subjects("Job") == [JOB] and graph.subjects("Pipeline") == [PIPELINE]
    # The job's newest name, not the one it had before; the job no lineage row names is left out.
    assert values(graph, JOB, "name") == ['"Sample_Master_Pipeline"']
    assert values(graph, PIPELINE, "name") == ['"Sample_Bronze_To_Silver"']
    built = graph.links("builtBy")
    assert (OBJECT + GOLD_SUMMARY, JOB) in built
    assert [s for s, o in built if o == PIPELINE] == [OBJECT + "idp_sbx.silver_mdm_core.sample_location_dim"]
    assert len([s for s, o in built if o == JOB]) == 9
    # A metric view has no builder: no job wrote it.
    assert all(SEMANTIC not in s for s, _ in built)


def test_a_writer_the_platform_keeps_no_name_for_is_no_builder(reading, graph):
    found, view, settings = reading
    doc = json.loads(found.to_json())
    for edge in doc["table_edges"]:
        if edge["target"] == GOLD_SUMMARY:
            edge["entities"] = edge["entities"] + ["sample-notebook-77"]
    assert tg.build(doc, view, settings).nquads() == graph.nquads()


def test_the_genie_spaces_and_what_they_bind(graph):
    pricing, spread = ENV + "agent/genie-01aa", ENV + "agent/genie-01bb"
    assert graph.subjects("Agent") == [pricing, spread]
    assert values(graph, pricing, "name") == ['"Sample Pricing Space"']
    assert graph.links("binds") == [
        (pricing, OBJECT + SEMANTIC + "mips_mpr_benchmark_prices_fact_vw"),
        (pricing, OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw"),
        (spread, OBJECT + SEMANTIC + "mpr_mips_crack_spread_price_fact_metrics_vw")]


def test_no_genie_filter_or_example_text_is_in_the_graph(graph):
    text = graph.nquads()
    for word in ("Sample Sheet", "KPI filter", "price_change_pct", "Show the sample"):
        assert word not in text


def test_the_metric_views_and_the_measures_they_implement(graph):
    assert graph.links("implements") == sorted([
        (OBJECT + SEMANTIC + "mips_mpr_benchmark_prices_fact_vw", MEASURE + "crude-prices"),
        (OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw", MEASURE + "additional-market-prices"),
        (OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw", MEASURE + "crude-prices"),
        (OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw", MEASURE + "distillate-prices"),
        (OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw", MEASURE + "gasoline-prices"),
        (OBJECT + SEMANTIC + "mpr_mips_crack_spread_price_fact_metrics_vw", MEASURE + "crack-spreads")])


def test_a_metric_view_with_no_named_measure_is_a_view_and_a_note_says_so(graph):
    unnamed = OBJECT + SEMANTIC + "mpr_mips_crack_spread_price_fact_metricsfromsilver_vw"
    assert unnamed in graph.subjects("View") and unnamed not in graph.subjects("MetricView")
    assert graph.notes == ["idp_sbx.semantic_sem_commercial.mpr_mips_crack_spread_price_fact_metricsfromsilver_vw is a metric view "
                           "the ontology names no measure for; it is recorded as a view"]


def test_freshness_is_the_newest_write_the_lineage_records(graph):
    stamp = '"%s"^^<http://www.w3.org/2001/XMLSchema#dateTime>'
    # The migration wrote this table in August; the job wrote it again in November.
    assert values(graph, OBJECT + "idp_sbx.silver_mdm_core.mips_price_batch_dim", "lastRefresh") == [stamp % "2026-11-02T06:00:00"]
    assert values(graph, OBJECT + "idp_sbx.silver_mdm_core.sample_location_dim", "lastRefresh") == [stamp % "2026-10-01T06:00:00"]
    assert values(graph, OBJECT + "synapse_dev.replica_mpr.pricedetail", "lastRefresh") == []
    assert values(graph, OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw", "lastRefresh") == []


def test_a_write_time_that_is_no_date_is_left_out_with_a_note(reading):
    found, view, settings = reading
    doc = json.loads(found.to_json())
    for edge in doc["table_edges"]:
        if edge["target"] == GOLD_SUMMARY:
            edge["last_event"] = "last Tuesday"
    built = tg.build(doc, view, settings)
    assert values(built, OBJECT + GOLD_SUMMARY, "lastRefresh") == []
    assert any("'last Tuesday'" in note and GOLD_SUMMARY in note for note in built.notes)
    assert tg._date_time("2026-11-02 06:00:00+00:00") == "2026-11-02T06:00:00+00:00"


def test_every_object_takes_what_the_default_scope_leaves_out(reading):
    found, view, settings = reading
    doc = json.loads(found.to_json())
    doc["tables"]["synapse_dev.other_core.sample_far_table"] = {
        "full_name": "synapse_dev.other_core.sample_far_table", "catalog": "synapse_dev", "schema": "other_core",
        "name": "sample_far_table", "table_type": "FOREIGN", "last_altered": ""}
    far = OBJECT + "synapse_dev.other_core.sample_far_table"
    assert far not in tg.build(doc, view, settings).subjects("Table")
    assert far in tg.build(doc, view, settings, every_object=True).subjects("Table")
    # A table that feeds a designed one is in scope, whatever its schema.
    doc["table_edges"].append({"source": "synapse_dev.other_core.sample_far_table", "target": GOLD_SUMMARY, "entities": [], "last_event": ""})
    assert far in tg.build(doc, view, settings).subjects("Table")


def test_a_name_with_odd_characters_still_gives_one_line_and_a_safe_iri(reading):
    found, view, settings = reading
    doc = json.loads(found.to_json())
    doc["tables"]['idp_sbx.gold_commercial_core.odd "name"\n<x>'] = {
        "full_name": 'idp_sbx.gold_commercial_core.Odd "Name"\n<x>', "catalog": "idp_sbx", "schema": "gold_commercial_core",
        "name": 'Odd "Name"\n<x>', "table_type": "MANAGED", "last_altered": ""}
    built = tg.build(doc, view, settings)
    subject = OBJECT + "idp_sbx.gold_commercial_core.odd%20%22name%22%0A%3Cx%3E"
    assert values(built, subject, "name") == ['"idp_sbx.gold_commercial_core.Odd \\"Name\\"\\n<x>"']
    assert all(line.endswith(" .") for line in built.nquads().splitlines())
    assert len(built.nquads().splitlines()) == 269 + 3


# ---- the same reading gives the same bytes -----------------------------------------------------------

def test_two_builds_are_byte_equal_and_shuffled_input_changes_nothing(reading, graph):
    found, view, settings = reading
    first = graph.nquads()
    assert tg.build(found, view, settings).nquads() == first
    doc = json.loads(found.to_json())
    rng = random.Random(7)

    def shuffled(value):
        if isinstance(value, dict):
            keys = list(value)
            rng.shuffle(keys)
            return {k: shuffled(value[k]) for k in keys}
        if isinstance(value, list):
            items = [shuffled(v) for v in value]
            rng.shuffle(items)
            return items
        return value

    mixed = {key: (value if key == "migration_pairs" else shuffled(value)) for key, value in doc.items()}
    mixed["migration_pairs"] = list(reversed(doc["migration_pairs"]))
    assert list(mixed["tables"]) != list(doc["tables"])
    assert tg.build(mixed, view, settings).nquads() == first
    assert first == "".join(sorted(first.splitlines(keepends=True)))


def test_the_file_holds_no_time_but_the_platforms(graph, tmp_path):
    files = tg.write(graph, tmp_path)
    assert [p.name for p in files] == ["tech-graph.nq"]
    text = files[0].read_bytes()
    assert b"\r" not in text and text.count(b"\n") == 269
    stamps = {line.split(b'"')[1] for line in text.splitlines() if b"lastRefresh" in line}
    assert stamps == {b"2026-11-02T06:00:00", b"2026-10-01T06:00:00"}
    assert b"2026-" not in b"".join(line for line in text.splitlines() if b"lastRefresh" not in line)
    summary = json.loads((tmp_path / "tech-graph-summary.json").read_text(encoding="utf-8"))
    assert summary["graph"] == ENV + "graph" and summary["environment"] == "idp_sbx+synapse_dev" and summary["triples"] == 269
    again = tg.write(graph, tmp_path / "again")
    assert again[0].read_bytes() == text and tg.digest(again) == tg.digest(files)


def test_build_from_files_reads_the_runs_discovery_json(reading, graph, tmp_path):
    found, _, settings = reading
    (tmp_path / "discovery.json").write_text(found.to_json(), encoding="utf-8", newline="\n")
    assert tg.build_from_files(tmp_path / "discovery.json", support.ROOT, settings).nquads() == graph.nquads()


# ---- the module's shapes ------------------------------------------------------------------------------

RELEASES = support.ROOT / "business_architecture" / "ontology" / "releases"


@pytest.fixture(scope="module")
def shapes():
    """(the module's released shapes, the releases a technical graph is checked with)."""
    from rdflib import Graph
    package = RELEASES / "technical-graph" / "1.1.0"
    linked = Graph().parse(package / "technical-graph.ttl")
    for module in ("data-product", "kpi", "system"):
        linked.parse(RELEASES / module / ov.newest_version(module, RELEASES) / f"{module}.ttl")
    return Graph().parse(package / "shapes.ttl"), linked


def report(shapes, nquads):
    """{(focus node, path, message)} of the SHACL report on a technical graph."""
    from pyshacl import validate
    from rdflib import Dataset, Graph, Namespace
    from rdflib.namespace import RDF
    sh = Namespace("http://www.w3.org/ns/shacl#")
    data = Graph()
    for s, p, o, _ in Dataset().parse(data=nquads, format="nquads").quads((None, None, None, None)):
        data.add((s, p, o))
    _, results, _ = validate(data + shapes[1], shacl_graph=shapes[0], inference="none")
    return {(str(results.value(r, sh.focusNode)), str(results.value(r, sh.resultPath)), str(results.value(r, sh.resultMessage)))
            for r in results.subjects(RDF.type, sh.ValidationResult)}


def test_the_built_graph_meets_the_modules_shapes(graph, shapes):
    assert report(shapes, graph.nquads()) == set()


def test_a_wrong_graph_fails_the_shapes_on_the_wrong_statement(graph, shapes):
    good = graph.nquads()
    table, graph_iri = OBJECT + GOLD_SUMMARY, ENV + "graph"

    def with_line(subject, name, value):
        return good + f"<{subject}> <{tg.TG}{name}> {value} <{graph_iri}> .\n"

    # A table that replaces a job.
    assert report(shapes, with_line(table, "replaces", f"<{JOB}>")) == {
        (table, tg.TG + "replaces", "A data object replaces only other data objects.")}
    # A table built by another table.
    other = OBJECT + "idp_sbx.silver_udm_core.mips_price_assessment_fact"
    assert report(shapes, with_line(table, "builtBy", f"<{other}>")) == {
        (table, tg.TG + "builtBy", "A data object is built only by builders: jobs and pipelines.")}
    # A second layer, from outside the layer code list.
    assert report(shapes, with_line(table, "layer", "<urn:made-up:bronze>")) == {
        (table, tg.TG + "layer", "A data object is in at most one layer, from the data-product layer code list."),
        ("urn:made-up:bronze", "http://www.w3.org/2004/02/skos/core#inScheme", "A layer is a value of the data-product layer code list.")}
    # A table with no name.
    nameless = "".join(line for line in good.splitlines(keepends=True) if not line.startswith(f"<{table}> <{tg.TG}name>"))
    assert report(shapes, nameless) == {(table, tg.TG + "name", "A technical object has one name.")}
    # A design that is nothing in the ontology.
    assert report(shapes, with_line(OBJECT + EXTRAS[0], "designedAs", "<urn:made-up:no-design>")) == {
        (OBJECT + EXTRAS[0], tg.TG + "designedAs",
         "A technical object builds at most one design: a platform table, a data product or an agent of data-product.")}


# ---- the rows Neo4j gets --------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def files(graph, tmp_path_factory):
    return tg.write(graph, tmp_path_factory.mktemp("run"))


def test_the_neo4j_rows(files):
    nodes, edges = tg.rows(files)
    assert len(nodes) == 53
    assert all("Tech" in n["labels"] and "Resource" not in n["labels"] for n in nodes)
    by_uri = {n["props"]["uri"]: n for n in nodes}
    assert by_uri[OBJECT + GOLD_SUMMARY] == {"labels": ["Table", "Tech"], "props": {
        "uri": OBJECT + GOLD_SUMMARY, "name": GOLD_SUMMARY, "layer": "gold", "lastRefresh": "2026-11-02T06:00:00"}}
    assert by_uri[OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw"]["labels"] == ["MetricView", "Tech"]
    assert by_uri[OBJECT + SEMANTIC + "mips_mpr_executive_summary_fact_vw"]["props"]["layer"] == "metric-view"
    assert by_uri[JOB] == {"labels": ["Job", "Tech"], "props": {"uri": JOB, "name": "Sample_Master_Pipeline"}}
    assert by_uri[ENV + "agent/genie-01bb"]["labels"] == ["Agent", "Tech"]
    kinds = {}
    for e in edges:
        kinds[(e["t"], e["ontology"])] = kinds.get((e["t"], e["ontology"]), 0) + 1
    # Links inside the graph are tech edges. Links to a design or a measure end at an ontology node.
    assert kinds == {("READS_FROM", False): 52, ("BUILT_BY", False): 10, ("BINDS", False): 3, ("REPLACES", False): 8,
                     ("DESIGNED_AS", True): 33, ("IMPLEMENTS", True): 6}
    assert {"s": OBJECT + "idp_sbx.silver_mdm_core.mips_price_batch_dim", "t": "REPLACES",
            "o": OBJECT + "synapse_dev.mdm_core.mips_price_batch_dim", "ontology": False} in edges


def test_the_digest_and_the_marker_follow_the_files(files, graph, tmp_path):
    marker = tg.marker(files, "neo4j", now=None)
    assert marker["store"] == "neo4j" and marker["triples"] == 269 and marker["digest"] == tg.digest(files)
    assert json.loads(marker["graphs"]) == {ENV + "graph": 269}
    assert tg.jena_apart(files) == [ENV + "graph"]
    changed = tmp_path / "tech-graph.nq"
    changed.write_text(graph.nquads().replace("Sample_Master_Pipeline", "Sample_Renamed_Pipeline"), encoding="utf-8", newline="\n")
    assert tg.digest([changed]) != tg.digest(files)


def test_the_statuses(files, graph, tmp_path):
    held = tg.marker(files, "neo4j")
    assert tg._judge(held, files)[0] == "current"
    assert tg._judge(None, files)[0] == "unmarked"
    assert tg._judge({**held, "digest": "0" * 64}, files)[0] == "behind"
    assert tg._judge(held, files, "its content differs")[0] == "changed"
    graph_iri = ENV + "graph"
    assert tg.status_jena({graph_iri: 269, "urn:another:graph": 5}, files)[0] == "current"
    assert tg.status_jena({"urn:another:graph": 5}, files) == ("behind", f"1 technical-graph graph(s) missing, e.g. {graph_iri}")
    assert tg.status_jena({graph_iri: 268}, files)[0] == "changed"
    assert tg.status_delta(held, files, {graph_iri: 269})[0] == "current"
    assert tg.status_delta(held, files, {graph_iri: 100})[0] == "changed"
    assert tg.status_delta(None, files)[0] == "unmarked"


# ---- Databricks, on the fake workspace -------------------------------------------------------------------

def test_the_delta_load_writes_the_triple_table_and_its_marker_in_the_tech_graph_schema(files):
    workspace, _ = support.sandbox()
    settings = support.make_settings()
    gate = lb.Gate(settings, workspace.run_sql)
    result = tg.load_delta(gate, settings, files, support.ROOT, batch=100)
    assert result["status"] == "loaded" and result["table"] == "idp_sbx.tech_graph.tech_graph_triples" and result["count"] == 269
    held = workspace.store["idp_sbx.tech_graph.tech_graph_triples"]
    assert len(held) == 269 and {r["graph"] for r in held} == {ENV + "graph"}
    assert {"subject": OBJECT + "idp_sbx.silver_mdm_core.mips_price_batch_dim", "predicate": tg.TG + "replaces",
            "object": OBJECT + "synapse_dev.mdm_core.mips_price_batch_dim", "object_kind": "iri", "datatype": None, "lang": None,
            "graph": ENV + "graph"} in held
    marker = json.loads(workspace.store["idp_sbx.tech_graph.tech_graph_markers"][0]["marker"])
    assert marker["digest"] == tg.digest(files) and marker["triples"] == 269 and marker["store"] == "databricks"
    assert tg.status_delta(tg.read_delta(gate, settings), files, {ENV + "graph": len(held)})[0] == "current"
    # Every write went to the tech_graph schema, and no staging table is left.
    written = [s for s in workspace.writes() if not s.startswith("CREATE SCHEMA")]
    assert written and all("idp_sbx.tech_graph." in s for s in written)
    assert sorted(workspace.store) == ["idp_sbx.tech_graph.tech_graph_markers", "idp_sbx.tech_graph.tech_graph_triples"]

    # A second run on the same files writes nothing.
    before = len(workspace.writes())
    again = tg.load_delta(gate, settings, files, support.ROOT)
    assert again["status"] == "current"
    assert [s for s in workspace.writes()[before:] if not s.startswith("CREATE SCHEMA")] == []


def test_a_staging_table_that_differs_leaves_the_triple_table_alone(files):
    workspace, _ = support.sandbox()
    settings = support.make_settings()
    altered = []

    def run_sql(statement):
        rows = workspace.run_sql(statement)
        staging = [name for name in workspace.store if "__staging_" in name]
        if statement.startswith("INSERT INTO") and staging and not altered:
            # One name is changed as it lands in the staging table.
            row = next(r for r in workspace.store[staging[0]] if r["object"] == "Sample_Master_Pipeline")
            row["object"] = "Sample_Altered_Pipeline"
            altered.append(row)
        return rows

    gate = lb.Gate(settings, run_sql)
    result = tg.load_delta(gate, settings, files, support.ROOT)
    assert altered and result["status"] == "staging-mismatch"
    assert workspace.store == {} and tg.read_delta(gate, settings) is None


def test_the_delta_load_cannot_write_outside_the_two_schemas(files):
    workspace, _ = support.sandbox()
    elsewhere = support.make_settings(tech_graph_schema='tech_graph_schema = "tech_graph"')
    gate = lb.Gate(elsewhere, workspace.run_sql)

    class Other:   # settings that name a schema the Gate's settings do not
        write_catalog, tech_graph_schema = "idp_sbx", "gold_commercial_core"

    with pytest.raises(lb.GateRefusal):
        tg.load_delta(gate, Other, files, support.ROOT)
    assert workspace.writes() == []


def test_the_notebooks_lines(tmp_path):
    """The lines the notebook runs after its own load: the run's discovery.json becomes the graph files, and the
    graph files load through the same Gate."""
    workspace, genie = support.sandbox()
    settings = support.make_settings(tmp_path)
    root = support.ROOT
    summary = lb.run(settings, root, workspace.run_sql, genie, mode="check", out_dir=tmp_path)

    run_dir = Path(summary["report_json"]).parent
    graph_files = tg.write(tg.build_from_files(run_dir / "discovery.json", root, settings), run_dir)
    summary["tech_graph"] = tg.load_delta(lb.Gate(settings, workspace.run_sql), settings, graph_files, root)

    assert (run_dir / "tech-graph.nq").is_file() and (run_dir / "tech-graph-summary.json").is_file()
    assert summary["tech_graph"]["status"] == "loaded" and summary["tech_graph"]["count"] == 269
    assert len(workspace.store["idp_sbx.tech_graph.tech_graph_triples"]) == 269
