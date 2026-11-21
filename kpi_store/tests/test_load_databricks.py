"""The gate, the staging-table hash check, the marker, and the whole run against a fake Databricks."""
import datetime as dt
import hashlib
import json

import pytest

from kpi_store import load_databricks as ld
from kpi_store import ontology_view as ov
from kpi_store import report
from kpi_store.tests import support

NOW = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.timezone.utc)
RDFSTORE = ld.import_rdfstore(support.ROOT)
TRIPLES, MARKERS = "idp_sbx.kpi_store.epm_triples", "idp_sbx.kpi_store.epm_store_markers"
DP = "https://w3id.org/mpc/ontology/modules/data-product/1.0.0"


def gate(run_sql=None):
    sent = []
    return ld.Gate(support.make_settings(), run_sql or (lambda s: sent.append(s) or [])), sent


# ---- the gate ------------------------------------------------------------------------------------

@pytest.mark.parametrize("statement", [
    "SELECT * FROM system.information_schema.tables",
    "SELECT a FROM system.access.table_lineage JOIN system.lakeflow.jobs USING (id)",
    "SELECT * FROM IDP_SBX.gold_commercial_core.some_fact f JOIN synapse_dev.replica_mpr.pricedetail d ON f.id = d.id",
    "WITH x AS (SELECT * FROM idp_sbx.a.b) SELECT * FROM x",
    "WITH a AS (SELECT * FROM idp_sbx.s.t), b AS (WITH inner_c AS (SELECT * FROM a) SELECT * FROM inner_c) SELECT * FROM b JOIN A USING (id)",
    "WITH t AS (SELECT * FROM idp_sbx.s.t) SELECT * FROM t JOIN idp_sbx.s.t USING (id)",
    "DESCRIBE TABLE EXTENDED `idp_sbx`.`semantic_sem_commercial`.`some_vw` AS JSON",
    "SELECT marker FROM idp_sbx.kpi_store.epm_store_markers WHERE store = 'databricks'",
])
def test_the_gate_passes_reads_inside_the_read_catalogs_and_the_system_schemas(statement):
    g, sent = gate()
    assert g.check(statement)[0] == "read"
    g.run(statement)
    assert sent == [statement]


@pytest.mark.parametrize("statement", [
    "CREATE SCHEMA IF NOT EXISTS idp_sbx.kpi_store",
    "CREATE SCHEMA IF NOT EXISTS idp_sbx.tech_graph",
    "CREATE VOLUME IF NOT EXISTS idp_sbx.kpi_store.releases",
    "CREATE OR REPLACE TABLE idp_sbx.kpi_store.epm_triples AS SELECT * FROM idp_sbx.kpi_store.epm_triples__staging_ab12",
    "CREATE TABLE IF NOT EXISTS idp_sbx.kpi_store.epm_store_markers (store STRING, marker STRING) USING DELTA",
    "INSERT INTO idp_sbx.TECH_GRAPH.nodes (a) SELECT decode(unbase64('YQ=='), 'UTF-8')",
    "DELETE FROM idp_sbx.kpi_store.epm_store_markers WHERE store = 'databricks'",
    "DROP TABLE IF EXISTS idp_sbx.kpi_store.epm_triples__staging_ab12",
    "COMMENT ON TABLE idp_sbx.kpi_store.epm_triples IS 'The release as RDF quads'",
    "ALTER TABLE idp_sbx.tech_graph.tech_graph_triples ALTER COLUMN subject COMMENT 'The quad\\'s subject'",
])
def test_the_gate_passes_writes_inside_the_two_schemas(statement):
    g, sent = gate()
    assert g.check(statement)[0] == "write"
    g.run(statement)
    assert sent == [statement]


@pytest.mark.parametrize("statement, message", [
    ("DROP TABLE idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact", "a write outside"),
    ("CREATE OR REPLACE TABLE idp_sbx.kpi_store_poc.epm_triples AS SELECT 1", "a write outside"),
    ("INSERT INTO synapse_dev.replica_mpr.pricedetail SELECT * FROM idp_sbx.kpi_store.epm_triples", "a write outside"),
    ("DELETE FROM idp_sbx.silver_mdm_core.mpr_price_master_dim", "a write outside"),
    ("CREATE SCHEMA IF NOT EXISTS idp_sbx.elsewhere", "a write outside"),
    ("CREATE SCHEMA IF NOT EXISTS other_catalog.kpi_store", "a write outside"),
    ("CREATE VOLUME IF NOT EXISTS idp_sbx.default.releases", "a volume outside"),
    ("DROP SCHEMA idp_sbx.kpi_store CASCADE", "not a statement the KPI Store runs"),
    ("DROP TABLE idp_sbx.kpi_store.epm_triples, idp_sbx.gold_commercial_core.some_fact", "target is not a table"),
    ("CREATE VIEW idp_sbx.kpi_store.v AS SELECT 1", "not a statement the KPI Store runs"),
    ("UPDATE idp_sbx.kpi_store.epm_triples SET object = 'x'", "not a statement the KPI Store runs"),
    ("MERGE INTO idp_sbx.kpi_store.epm_triples t USING idp_sbx.kpi_store.s s ON t.a = s.a WHEN MATCHED THEN DELETE", "not a statement the KPI Store runs"),
    ("TRUNCATE TABLE idp_sbx.kpi_store.epm_triples", "not a statement the KPI Store runs"),
    ("GRANT SELECT ON TABLE idp_sbx.kpi_store.epm_triples TO `someone`", "not a statement the KPI Store runs|cannot be parsed"),
    ("SELECT * FROM third_catalog.some_schema.some_table", "a read outside"),
    ("SELECT * FROM system.billing.usage", "a read outside"),
    ("SELECT * FROM system.information_schema.tables t JOIN another_catalog.some_schema.x USING (id)", "a read outside"),
    ("SELECT * FROM epm_triples", "a read outside"),
    ("CREATE OR REPLACE TABLE idp_sbx.kpi_store.copy AS SELECT * FROM fourth_catalog.a.b", "a read outside"),
    ("INSERT INTO idp_sbx.kpi_store.epm_triples SELECT * FROM (SELECT * FROM other_catalog.a.b)", "a read outside"),
    # A bare name outside the scope of the WITH clause that defines it is a table of the session's default schema.
    ("SELECT count(*) FROM (WITH x AS (SELECT 1 AS v) SELECT * FROM x) q JOIN x ON q.v = x.id", "a read outside .*: x"),
    ("SELECT * FROM idp_sbx.a.b WHERE id IN (WITH x AS (SELECT 1 AS id) SELECT id FROM x) AND EXISTS (SELECT 1 FROM x)", "a read outside .*: x"),
    ("SELECT * FROM (SELECT 1 UNION ALL (WITH y AS (SELECT 2) SELECT * FROM y) UNION ALL SELECT * FROM y) u", "a read outside .*: y"),
    ("CREATE OR REPLACE TABLE idp_sbx.kpi_store.copy AS SELECT * FROM (WITH x AS (SELECT 1) SELECT * FROM x) q JOIN x ON TRUE", "a read outside .*: x"),
    # A WITH clause that takes a real table's name does not make another catalog's table of that name a CTE.
    ("WITH t AS (SELECT * FROM idp_sbx.s.t) SELECT * FROM t JOIN other_catalog.s.t USING (id)", "a read outside .*: other_catalog.s.t"),
    ("SELECT 1; DROP TABLE idp_sbx.kpi_store.epm_triples", "one statement at a time"),
    # A comment goes only on a table of the KPI Store's own, and an ALTER may only write column comments.
    ("COMMENT ON TABLE idp_sbx.gold_commercial_core.some_fact IS 'x'", "a write outside"),
    ("ALTER TABLE idp_sbx.gold_commercial_core.some_fact ALTER COLUMN Amount COMMENT 'x'", "a write outside"),
    ("COMMENT ON TABLE epm_triples IS 'x'", "a write outside"),
    ("COMMENT ON SCHEMA idp_sbx.kpi_store IS 'x'", "not a statement the KPI Store runs"),
    ("COMMENT ON COLUMN idp_sbx.kpi_store.epm_triples.subject IS 'x'", "not a statement the KPI Store runs"),
    ("ALTER TABLE idp_sbx.kpi_store.epm_triples DROP COLUMN subject", "not a statement the KPI Store runs"),
    ("ALTER TABLE idp_sbx.kpi_store.epm_triples ALTER COLUMN subject TYPE INT", "not a statement the KPI Store runs"),
    ("ALTER TABLE idp_sbx.kpi_store.epm_triples RENAME TO idp_sbx.kpi_store.other", "not a statement the KPI Store runs"),
    ("ALTER TABLE idp_sbx.kpi_store.epm_triples SET TBLPROPERTIES ('a' = 'b')", "not a statement the KPI Store runs"),
    ("ALTER TABLE idp_sbx.kpi_store.epm_triples ALTER COLUMN subject COMMENT 'x', ALTER COLUMN object COMMENT 'y'",
     "not a statement the KPI Store runs|cannot be parsed"),
])
def test_the_gate_refuses_everything_else_and_sends_nothing(statement, message):
    g, sent = gate()
    with pytest.raises(ld.GateRefusal, match=message):
        g.run(statement)
    assert sent == [] and g.statements == 0


# ---- what a current store holds ----------------------------------------------------------------

def test_the_graphs_of_a_release_and_the_marker_fields(tmp_path):
    root = support.small_release(tmp_path)
    graphs = ld.release_graphs(root)
    assert sorted(graphs) == [DP, DP + "/catalog", DP + "/sample-model", DP + "/shapes",
                              "https://w3id.org/mpc/ontology/modules/kpi/1.0.0", "https://w3id.org/mpc/ontology/modules/kpi/1.0.0/catalog",
                              "https://w3id.org/mpc/ontology/modules/kpi/1.0.0/shapes"]
    assert graphs[DP + "/sample-model"].name == "sample-model.ttl" and graphs[DP].name == "data-product.ttl"
    want = ld.expected(root)
    assert want["catalog_datasets"] == 2 and want["input_fingerprint"] == "sample-fingerprint"
    assert want["catalog_digest"] == hashlib.sha256(
        b"https://w3id.org/mpc/ontology/modules/data-product/1.0.0\nhttps://w3id.org/mpc/ontology/modules/kpi/1.0.0").hexdigest()
    # Counted by hand from support.py: data-product 22, its shapes, catalog and model 1 each; kpi 5, its shapes and catalog 1 each.
    assert len(ld.build_dataset(root, RDFSTORE)) == 32


def test_a_correction_version_is_loaded_when_the_catalog_lists_it_and_refused_when_it_does_not(tmp_path):
    listed = support.small_release(tmp_path / "listed", versions=("1.0.0", "1.0.1-correction.1"))
    newest = "https://w3id.org/mpc/ontology/modules/data-product/1.0.1-correction.1"
    assert ld.expected(listed)["newest"] == [newest, "https://w3id.org/mpc/ontology/modules/kpi/1.0.0"]
    assert newest in ld.release_graphs(listed) and DP not in ld.release_graphs(listed)
    unlisted = support.small_release(tmp_path / "unlisted", versions=("1.0.0", "1.0.1-correction.1"), catalog_versions=("1.0.0",))
    with pytest.raises(ov.ReleaseError, match="the catalog's newest data-product is 1.0.0, and the newest package folder is 1.0.1-correction.1"):
        ld.release_graphs(unlisted)


# ---- the load --------------------------------------------------------------------------------------

def load(workspace, root, commit="KPI Store 1.1 (zip sha256 made-up)"):
    return ld.load(ld.Gate(support.make_settings(), workspace.run_sql), support.make_settings(), root, commit, NOW, RDFSTORE, batch=10)


def test_a_load_goes_through_staging_and_marks_the_table(tmp_path):
    root, workspace = support.small_release(tmp_path), support.FakeWorkspace()
    result = load(workspace, root)
    assert result["status"] == "loaded" and result["count"] == 32 and result["table"] == TRIPLES
    assert len(workspace.store[TRIPLES]) == 32 and workspace.rewrites == 1
    assert not [t for t in workspace.store if "__staging_" in t]
    assert len([s for s in workspace.statements if s.startswith("INSERT INTO idp_sbx.kpi_store.epm_triples__staging_")]) == 4   # batches of 10
    assert RDFSTORE.dataset_hash(RDFSTORE.from_rows(tuple(r.values()) for r in workspace.store[TRIPLES])) == result["dataset_hash"]
    marker = json.loads(workspace.store[MARKERS][0]["marker"])
    assert workspace.store[MARKERS][0]["store"] == "databricks" and len(workspace.store[MARKERS]) == 1
    assert marker == {"catalog_datasets": 2, "catalog_digest": ld.expected(root)["catalog_digest"], "input_fingerprint": "sample-fingerprint",
                      "marked_at": "2026-11-11T12:00:00Z", "commit": "KPI Store 1.1 (zip sha256 made-up)", "store": "databricks",
                      "count": [32], "dataset_hash": result["dataset_hash"]}
    graphs = {r["graph"] for r in workspace.store[TRIPLES]}
    assert DP in graphs and DP + "/shapes" in graphs and None not in graphs
    assert any(r["object_kind"] == "literal" and r["subject"].startswith("_:") for r in workspace.store[TRIPLES])


def test_a_load_comments_each_table_and_each_column(tmp_path):
    root, workspace = support.small_release(tmp_path), support.FakeWorkspace()
    assert load(workspace, root)["status"] == "loaded"
    assert workspace.comments == {TRIPLES: {"": ld.TRIPLES_COMMENT, **ld.TRIPLE_COLUMNS},
                                  MARKERS: {"": ld.MARKERS_COMMENT, **ld.MARKER_COLUMNS}}
    assert tuple(ld.TRIPLE_COLUMNS) == RDFSTORE.COLUMNS   # every column of the rdf-store skill's row format, in order
    # A lost marker is written again, and the comments with it.
    workspace.store[MARKERS], workspace.comments = [], {}
    assert load(workspace, root)["status"] == "marked" and workspace.comments[TRIPLES][""] == ld.TRIPLES_COMMENT


@pytest.mark.parametrize("text, read", [
    ("The quad's subject", "The quad's subject"),
    ("A path such as C:\\temp\\x and a \\' pair", "A path such as C:\\temp\\x and a \\' pair"),
    ("Two\nlines\tand  spaces", "Two lines and spaces"),
    ("It ends with a backslash \\", "It ends with a backslash \\"),
])
def test_a_comment_reads_back_as_its_text_whatever_quotes_or_backslashes_it_holds(text, read):
    import sqlglot
    for statement in ld.comment_statements("idp_sbx.kpi_store.epm_triples", text, {"subject": text}):
        g, sent = gate()
        g.run(statement)   # the Gate passes it
        tree = sqlglot.parse_one(statement, read="databricks")
        literal = tree.expression if isinstance(tree, sqlglot.exp.Comment) else tree.args["actions"][0].args["comment"]
        assert literal.this == read and sent == [statement]


def test_a_second_load_changes_nothing(tmp_path):
    root, workspace = support.small_release(tmp_path), support.FakeWorkspace()
    first = load(workspace, root)
    before = json.dumps(workspace.store, sort_keys=True)
    sent = len(workspace.statements)
    second = ld.load(ld.Gate(support.make_settings(), workspace.run_sql), support.make_settings(), root, "another commit",
                     NOW + dt.timedelta(hours=1), RDFSTORE)
    assert second["status"] == "current" and second["dataset_hash"] == first["dataset_hash"]
    assert second["marker"]["marked_at"] == "2026-11-11T12:00:00Z"
    assert json.dumps(workspace.store, sort_keys=True) == before and workspace.rewrites == 1
    assert [s for s in workspace.statements[sent:] if not s.startswith("SELECT")] == []


def test_an_altered_staging_row_stops_the_load_and_leaves_the_main_table_untouched(tmp_path):
    root, workspace = support.small_release(tmp_path), support.FakeWorkspace()
    load(workspace, root)
    held = json.dumps(workspace.store, sort_keys=True)
    changed = support.small_release(tmp_path / "next", column="Other_Amount")
    workspace.corrupt_staging = True
    result = load(workspace, changed)
    assert result["status"] == "staging-mismatch"
    assert result["comparison"]["hashes_equal"] is False and (result["comparison"]["missing"], result["comparison"]["extra"]) == (1, 1)
    assert json.dumps(workspace.store, sort_keys=True) == held and workspace.rewrites == 1   # table and marker as they were
    assert not [t for t in workspace.store if "__staging_" in t]                          # the staging table is dropped all the same
    assert load(workspace, changed)["status"] == "loaded" and workspace.rewrites == 2


def test_a_main_table_that_differs_after_the_replace_is_not_marked(tmp_path):
    root, workspace = support.small_release(tmp_path), support.FakeWorkspace()
    workspace.corrupt_promote = True
    result = load(workspace, root)
    assert result["status"] == "main-mismatch" and result["comparison"]["published"] is True
    assert result["comparison"]["staging"] == {"hashes_equal": True} and result["comparison"]["hashes_equal"] is False
    assert MARKERS not in workspace.store and not [t for t in workspace.store if "__staging_" in t]
    assert load(workspace, root)["status"] == "loaded" and len(workspace.store[MARKERS]) == 1


def test_the_staging_steps_are_the_rdf_store_skills_and_every_statement_passes_the_gate(tmp_path):
    root, workspace = support.small_release(tmp_path), support.FakeWorkspace()
    g = ld.Gate(support.make_settings(), workspace.run_sql)
    assert ld.load(g, support.make_settings(), root, "made-up", NOW, RDFSTORE)["status"] == "loaded"
    assert g.statements == len(workspace.statements) > 6   # nothing reached the workspace beside the gate
    # The same store, pointed at a table outside the KPI Store's schemas, is refused at its first statement.
    for table in ("idp_sbx.gold_commercial_core.epm_triples", "synapse_dev.kpi_store.epm_triples", "epm_triples"):
        sent = len(workspace.statements)
        outside = RDFSTORE.SparkStore(ld.GatedSpark(g), table)
        with pytest.raises(ld.GateRefusal, match="a write outside"):
            RDFSTORE.roundtrip(outside, ld.build_dataset(root, RDFSTORE))
        with pytest.raises(ld.GateRefusal, match="a read outside") if table == "epm_triples" else pytest.raises(KeyError):
            outside.export()   # a read of another catalog's table passes the gate only when read_catalogs names it
        assert len(workspace.statements) - sent == (0 if table == "epm_triples" else 1)
        assert [s for s in workspace.statements[sent:] if not s.startswith("SELECT")] == []


def test_the_graph_set_is_the_one_sync_stores_expects_for_this_release():
    ss = ld.import_sync_stores(support.ROOT)
    graphs = ld.release_graphs(support.ROOT)
    assert set(graphs) == set(ss.expected_for(None, ["databricks"])["jena_graphs"])
    assert len(graphs) == 41   # 13 releases, each with its content, shapes and catalog, and the two logical model graphs
    assert (ss.TRIPLES_TABLE, ss.MARKER_TABLE) == ("epm_triples", "epm_store_markers")
    assert (support.make_settings().triples_table, support.make_settings().markers_table) == (TRIPLES, MARKERS)


def test_a_changed_release_reloads_and_a_lost_marker_is_written_again(tmp_path):
    root, workspace = support.small_release(tmp_path), support.FakeWorkspace()
    first = load(workspace, root)
    workspace.store[MARKERS] = []
    assert load(workspace, root)["status"] == "marked" and workspace.rewrites == 1 and len(workspace.store[MARKERS]) == 1
    workspace.store[TRIPLES][0]["object"] += " edited by hand"
    assert load(workspace, root)["status"] == "loaded" and workspace.rewrites == 2
    changed = load(workspace, support.small_release(tmp_path / "next", column="Other_Amount"))
    assert changed["status"] == "loaded" and changed["dataset_hash"] != first["dataset_hash"] and workspace.rewrites == 3


def test_this_release_loads_and_reads_back_with_the_same_hash():
    workspace = support.FakeWorkspace()
    result = ld.load(ld.Gate(support.make_settings(), workspace.run_sql), support.make_settings(), support.ROOT, "made-up", NOW, RDFSTORE)
    assert result["status"] == "loaded" and result["count"] == len(workspace.store[TRIPLES]) > 17000
    graphs = {r["graph"] for r in workspace.store[TRIPLES]}
    assert graphs == set(ld.release_graphs(support.ROOT))
    again = ld.load(ld.Gate(support.make_settings(), workspace.run_sql), support.make_settings(), support.ROOT, "made-up", NOW, RDFSTORE)
    assert again["status"] == "current" and workspace.rewrites == 1


# ---- the whole run ----------------------------------------------------------------------------------

def run(workspace, root, out, **more):
    return ld.run(support.make_settings(out), root, workspace.run_sql, None, zip_sha256="c" * 64, now=NOW, rdfstore=RDFSTORE, **more)


def test_a_run_that_finds_no_difference_loads_and_writes_its_report(tmp_path):
    root, workspace, out = support.small_release(tmp_path / "release"), support.small_workspace(), tmp_path / "volume"
    summary = run(workspace, root, out)
    assert summary["status"] == "loaded" and summary["blocked"] is False and summary["blocking_rows"] == []
    assert summary["passes"] == {"object_names": 3, "table_edges": 2, "metric_view_sources": 0}
    assert workspace.statements[:3] == ["CREATE SCHEMA IF NOT EXISTS idp_sbx.kpi_store", "CREATE SCHEMA IF NOT EXISTS idp_sbx.tech_graph",
                                        "CREATE VOLUME IF NOT EXISTS idp_sbx.kpi_store.releases"]
    written = report.read(out / "discovery-report.json")
    assert written == report.read(out / "reports" / summary["run"] / "discovery-report.json")
    assert (written["release"], written["ontology"], written["rows"]) == ("KPI Store 1.1", {"data-product": "1.0.0", "kpi": "1.0.0"}, [])
    assert written["run"]["zip_sha256"] == "c" * 64 and written["run"]["settings_sha256"] == support.make_settings().sha256
    assert (out / "discovery-report.csv").is_file() and (out / "reports" / summary["run"] / "discovery.json").is_file()
    assert json.loads(workspace.store[MARKERS][0]["marker"])["commit"] == "KPI Store 1.1 (zip sha256 " + "c" * 64 + ")"
    assert summary["notes"] == ["Genie spaces were not read: no Genie client was given"]


def test_a_second_run_changes_nothing_in_the_store(tmp_path):
    root, workspace, out = support.small_release(tmp_path / "release"), support.small_workspace(), tmp_path / "volume"
    first = run(workspace, root, out)
    held, sent = json.dumps(workspace.store, sort_keys=True), len(workspace.statements)
    second = ld.run(support.make_settings(out), root, workspace.run_sql, None, zip_sha256="c" * 64, now=NOW + dt.timedelta(days=1), rdfstore=RDFSTORE)
    assert second["status"] == "current" and second["dataset_hash"] == first["dataset_hash"]
    assert json.dumps(workspace.store, sort_keys=True) == held and workspace.rewrites == 1
    later = [s for s in workspace.statements[sent:] if not s.startswith(("SELECT", "DESCRIBE"))]
    assert later == workspace.statements[:3]   # only the three CREATE ... IF NOT EXISTS, which change nothing


def test_a_wrong_name_in_the_ontology_stops_the_load_with_a_report(tmp_path):
    root, workspace, out = support.small_release(tmp_path / "release", fact="wrong_name_fact"), support.small_workspace(), tmp_path / "volume"
    summary = run(workspace, root, out)
    assert summary["status"] == "blocked" and summary["blocked"] is True and summary["blocking_rows"] == ["R001"]
    assert TRIPLES not in workspace.store and MARKERS not in workspace.store and workspace.rewrites == 0
    assert workspace.writes() == workspace.statements[:3]
    written = report.read(out / "discovery-report.json")
    assert [(r["kind"], r["object"], r["found_value"], r["blocks"]) for r in written["rows"]] == [
        ("object-renamed", "idp_sbx.gold_sample.wrong_name_fact", "idp_sbx.gold_sample.sample_fact", True)]
    assert written["passes"] == {"object_names": 2, "table_edges": 1, "metric_view_sources": 0}


def test_check_mode_writes_the_report_and_loads_nothing(tmp_path):
    root, workspace, out = support.small_release(tmp_path / "release"), support.small_workspace(), tmp_path / "volume"
    summary = run(workspace, root, out, mode="check")
    assert summary["status"] == "checked" and TRIPLES not in workspace.store and (out / "discovery-report.json").is_file()
    with pytest.raises(ValueError, match="mode must be load or check"):
        run(workspace, root, out, mode="force")


def test_a_release_whose_catalog_is_behind_its_folders_stops_before_databricks_is_touched(tmp_path):
    root = support.small_release(tmp_path / "release", versions=("1.0.0", "1.0.1-correction.1"), catalog_versions=("1.0.0",))
    workspace = support.small_workspace()
    with pytest.raises(ov.ReleaseError, match="the catalog's newest data-product"):
        run(workspace, root, tmp_path / "volume")
    assert workspace.statements == []


def test_a_staging_table_that_could_not_be_dropped_is_named_in_the_result(tmp_path):
    root, workspace = support.small_release(tmp_path), support.FakeWorkspace()
    run_sql = workspace.run_sql

    def no_drop(statement):
        if statement.startswith("DROP TABLE"):
            raise RuntimeError("the warehouse stopped")
        return run_sql(statement)

    result = ld.load(ld.Gate(support.make_settings(), no_drop), support.make_settings(), root, "made-up", NOW, RDFSTORE, batch=10)
    left = [t for t in workspace.store if "__staging_" in t]
    assert result["status"] == "loaded" and len(left) == 1 and result["staging_not_dropped"] == left[0]
    assert "staging_not_dropped" not in load(support.FakeWorkspace(), root)   # a clean load says nothing of it
