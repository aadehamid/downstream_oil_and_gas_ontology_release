"""Discovery against a made-up workspace with the sandbox's shapes: what is kept and what the rules drop."""
from kpi_store import discovery
from kpi_store.tests import support

SCHEMAS = ("idp_sbx.gold_commercial_core", "idp_sbx.silver_mdm_core", "idp_sbx.silver_udm_core", "idp_sbx.semantic_sem_commercial",
           "synapse_dev.replica_mpr", "synapse_dev.replica_mips", "synapse_dev.replica_kittyhawk")
GOLD = "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"


def discover(**settings):
    workspace, genie = support.sandbox()
    return discovery.discover(support.make_settings(**settings), workspace.run_sql, genie, SCHEMAS), workspace, genie


def test_objects_keep_their_spelling_and_the_skip_rules_and_the_catalog_filter_apply():
    found, _, _ = discover()
    # 33 ontology objects, 7 unused objects, 1 unused replica table and 8 replaced tables; 5 skipped, 1 outside the read catalogs.
    assert len(found.tables) == 49
    for dropped in ("synapse_dev.replica_mpr.pricedetail__ct", "synapse_dev.replica_mips.attrep_apply_exceptions",
                    "idp_sbx.bronze_replica_mpr.pricedetail", "idp_sbx.kpi_store_poc.old_triples", "idp_sbx.information_schema.tables",
                    "other_catalog.gold_commercial_core.elsewhere_fact"):
        assert not found.exists(dropped)
    assert found.exists("IDP_SBX.Gold_Commercial_Core.MIPS_MPR_Executive_Summary_Fact")
    assert found.tables["synapse_dev.replica_mpr.pricedetail"].table_type == "FOREIGN"
    assert found.columns[GOLD] == ["Sample_Sheet_Name", "Sample_Display_Name", "Assessment_Amount", "Previous_Amount", "Change_Value_Amount"]
    assert "other_catalog.gold_commercial_core.elsewhere_fact" not in found.columns
    assert "idp_sbx.bronze_replica_mpr.pricedetail" not in found.columns


def test_metric_views_are_described_and_parsed():
    found, workspace, _ = discover()
    assert sorted(v.rsplit(".", 1)[1] for v in found.metric_views) == [
        "mips_mpr_benchmark_prices_fact_vw", "mips_mpr_executive_summary_fact_vw",
        "mpr_mips_crack_spread_price_fact_metrics_vw", "mpr_mips_crack_spread_price_fact_metricsfromsilver_vw"]
    assert len([s for s in workspace.statements if s.startswith("DESCRIBE")]) == 4   # the plain view is not described
    view = found.metric_views["idp_sbx.semantic_sem_commercial.mips_mpr_benchmark_prices_fact_vw"]
    assert view.tables == ["idp_sbx.silver_mdm_core.mpr_price_master_dim", "idp_sbx.silver_udm_core.mpr_price_detail_fact"]


def test_lineage_keeps_an_edge_only_when_both_ends_exist_and_drops_self_edges():
    found, _, _ = discover()
    # 39 of the 40 ontology edges (one is proved by a view's definition), 8 migration pairs, 1 edge into an unused table.
    assert len(found.table_edges) == 48
    assert ("idp_sbx.silver_mdm_core.mips_price_batch_dim", "idp_sbx.silver_mdm_core.mips_price_batch_dim") not in found.table_edges
    assert not any("dropped" in s or "dropped" in t or "bronze" in s or "other_catalog" in s for s, t in found.table_edges)
    assert len(found.migration_pairs) == 8
    assert ("synapse_dev.commercial_core.mips_mpr_executive_summary_fact", GOLD) in found.migration_pairs
    assert found.upstream(GOLD) == {
        "idp_sbx.silver_udm_core.mips_price_assessment_fact", "idp_sbx.silver_mdm_core.mips_price_assessment_group_dim",
        "idp_sbx.silver_mdm_core.mips_price_batch_dim", "idp_sbx.silver_mdm_core.mips_price_group_dim",
        "idp_sbx.silver_mdm_core.mips_price_sheet_dim", "idp_sbx.silver_mdm_core.mpr_price_master_dim",
        "synapse_dev.commercial_core.mips_mpr_executive_summary_fact"}
    assert found.last_written(GOLD) == "2026-11-02T06:00:00Z"
    # Column lineage keeps the old column names, and drops the self-edge and the edge from a dropped table.
    silver = "idp_sbx.silver_udm_core.mips_price_assessment_fact"
    both = {(silver, "assessment_amount"), (silver, "previous_amount")}
    assert found.column_sources(GOLD, "ChangeValue") == both == found.column_sources(GOLD, "Change_Value_Amount")
    assert len(found.column_edges) == 6   # 8 rows, less two pairs that differ only in case


def test_builders_take_the_newest_name_of_each_id():
    found, _, _ = discover()
    assert found.builders == {"9001": {"kind": "job", "name": "Sample_Master_Pipeline"},
                              "pipe-0001": {"kind": "pipeline", "name": "Sample_Bronze_To_Silver"}}
    assert found.table_edges[("idp_sbx.silver_udm_core.mips_price_assessment_fact", GOLD)]["entities"] == ["9001"]


def test_genie_spaces_are_listed_page_by_page_and_read_with_their_serialized_form():
    found, _, genie = discover()
    assert genie.calls == [("list", None), ("list", "01bb"), ("get", "01aa", True), ("get", "01bb", True)]
    summary, crack = found.genie_spaces
    assert (summary.space_id, summary.title, len(summary.tables), len(summary.filters), len(summary.expressions), len(summary.example_sqls)) == \
        ("01aa", "Sample Pricing Space", 2, 10, 1, 1)
    assert summary.filters[5] == {"title": "Crude KPI filter", "sql": "Sample_Sheet_Name IN ('Sample Sheet One', 'Sample Sheet Two')\n"
                                  "AND TRIM(Sample_Display_Name) IN ('Sample Item A', 'Sample Item B')"}
    assert summary.expressions == [{"title": "Price change percent", "sql": "MEASURE(Change_Value_Amount) / NULLIF(MEASURE(Previous_Amount), 0)"}]
    assert summary.example_sqls[0]["sql"].startswith("SELECT Sample_Display_Name, MEASURE(Assessment_Amount)\nFROM idp_sbx.")
    assert crack.tables == ["idp_sbx.semantic_sem_commercial.mpr_mips_crack_spread_price_fact_metrics_vw"] and crack.filters == []
    assert found.notes == []


def test_named_spaces_are_read_without_listing_and_a_closed_space_is_a_note():
    workspace, genie = support.sandbox()
    genie.spaces["01bb"] = ("Closed", PermissionError("no access"))
    found = discovery.discover(support.make_settings(spaces='spaces = ["01bb", "01aa"]'), workspace.run_sql, genie, SCHEMAS)
    assert genie.calls == [("get", "01bb", True), ("get", "01aa", True)]
    assert [s.space_id for s in found.genie_spaces] == ["01aa"]
    assert found.notes == ["Genie space 01bb could not be read (PermissionError)"]
    without = discovery.discover(support.make_settings(), workspace.run_sql, None, SCHEMAS)
    assert without.genie_spaces == [] and without.notes == ["Genie spaces were not read: no Genie client was given"]


def test_rows_may_be_spark_rows_and_the_reading_serializes():
    class Row(dict):
        def asDict(self):
            return {k.upper(): v for k, v in self.items()}
    workspace, genie = support.sandbox()
    found = discovery.discover(support.make_settings(), lambda q: [Row(r) for r in workspace.run_sql(q)], genie, SCHEMAS)
    assert len(found.tables) == 49 and len(found.table_edges) == 48
    text = found.to_json()
    assert '"migration_pairs"' in text and '"Sample_Master_Pipeline"' in text and text.endswith("\n")


def test_the_migration_naming_rule():
    assert discovery.migration_pair("synapse_dev.mdm_core.Some_Dim", "idp_sbx.silver_mdm_core.some_dim")
    assert not discovery.migration_pair("idp_sbx.mdm_core.some_dim", "idp_sbx.silver_mdm_core.some_dim")      # one catalog
    assert not discovery.migration_pair("synapse_dev.mdm_core.some_dim", "idp_sbx.silver_mdm_core.other_dim")  # another table
    assert not discovery.migration_pair("synapse_dev.mdm_core.some_dim", "idp_sbx.mdm_core.some_dim")          # no layer prefix
    assert not discovery.migration_pair("synapse_dev.replica_mpr.pricedetail", "idp_sbx.silver_udm_core.pricedetail")


def test_a_platform_time_is_read_once_into_utc_and_compared_as_an_instant():
    import datetime as dt
    utc = dt.timezone.utc
    assert discovery.utc_text("2026-11-02 09:00:00") == "2026-11-02T09:00:00Z"            # a space, no zone: UTC
    assert discovery.utc_text("2026-11-02T06:00:00+00:00") == "2026-11-02T06:00:00Z"
    assert discovery.utc_text("2026-11-02T06:00:00Z") == "2026-11-02T06:00:00Z"
    assert discovery.utc_text("2026-11-02T01:00:00-05:00") == "2026-11-02T06:00:00Z"      # an offset names an instant
    assert discovery.utc_text(dt.datetime(2026, 11, 2, 6, 0, 0)) == "2026-11-02T06:00:00Z"
    assert discovery.utc_text(dt.datetime(2026, 11, 2, 8, 0, 0, 250000, tzinfo=dt.timezone(dt.timedelta(hours=2)))) == "2026-11-02T06:00:00Z"
    assert discovery.utc_text(None) == "" and discovery.utc_text("") == "" and discovery.utc_text("last Tuesday") == ""
    assert discovery.instant("2026-11-02 09:00:00") == dt.datetime(2026, 11, 2, 9, tzinfo=utc)
    # As text the first sorts below the second; as instants 09:00 is the newer.
    assert "2026-11-02 09:00:00" < "2026-11-02T06:00:00+00:00"
    assert discovery.newest(["2026-11-02 09:00:00", "2026-11-02T06:00:00+00:00"]) == "2026-11-02T09:00:00Z"
    # Two offsets that name one instant are one time; the later instant wins whatever its offset.
    assert discovery.newest(["2026-11-02T10:00:00+04:00", "2026-11-02T01:00:00-05:00"]) == "2026-11-02T06:00:00Z"
    assert discovery.newest(["2026-11-02T23:30:00-05:00", "2026-11-03T03:00:00+00:00"]) == "2026-11-03T04:30:00Z"
    assert discovery.newest(["", None, "not a time"]) == ""


def test_the_newest_write_is_chosen_by_instant_across_formats():
    workspace = support.small_workspace()
    target = "idp_sbx.silver_sample.middle_dim"
    workspace.table_lineage = [("synapse_dev.replica_sample.source_table", target, "9001", "2026-11-02T06:00:00+00:00"),
                               ("synapse_dev.replica_sample.source_table", target, "9002", "2026-11-02 09:00:00"),
                               ("idp_sbx.gold_sample.sample_fact", target, None, "2026-11-02T03:00:00-05:00")]
    for rows in (workspace.table_lineage, list(reversed(workspace.table_lineage))):
        workspace.table_lineage = rows
        found = discovery.discover(support.make_settings(), workspace.run_sql, None, ())
        assert found.table_edges[("synapse_dev.replica_sample.source_table", target)]["last_event"] == "2026-11-02T09:00:00Z"
        assert found.last_written(target) == "2026-11-02T09:00:00Z"
        assert found.tables[target].last_altered == "2026-11-02T06:00:00Z"


def test_a_builders_current_name_is_its_newest_by_instant_and_ids_keep_their_case():
    workspace = support.small_workspace()
    target = "idp_sbx.silver_sample.middle_dim"
    workspace.table_lineage = [("synapse_dev.replica_sample.source_table", target, "ABC-1", "2026-11-02T06:00:00"),
                               ("idp_sbx.gold_sample.sample_fact", target, "abc-1", "2026-11-02T06:00:00")]
    jobs = [("ABC-1", "Alpha_Old", "2026-10-20T06:00:00+00:00"), ("ABC-1", "Alpha", "2026-10-20 09:00:00"),
            ("abc-1", "Beta", "2026-10-01T00:00:00"), ("abc-1", "Beta_Tie", "2026-10-01T02:00:00+02:00"),
            ("Abc-1", "No lineage row names this ID", "2026-10-25T00:00:00")]
    for rows in (jobs, list(reversed(jobs))):
        workspace.jobs = rows
        found = discovery.discover(support.make_settings(), workspace.run_sql, None, ())
        # Two IDs that differ only in case are two builders. The newer name wins by instant; a tie goes to the name.
        assert found.builders == {"ABC-1": {"kind": "job", "name": "Alpha"}, "abc-1": {"kind": "job", "name": "Beta_Tie"}}
