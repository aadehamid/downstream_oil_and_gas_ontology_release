"""The comparison. The first test pins the first report expected on the sandbox, row by row, by hand."""
import datetime as dt

from kpi_store import compare, discovery, ontology_view as ov
from kpi_store.tests import support
from kpi_store.tests.test_ontology_view import RELEASES, package

NOW = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.timezone.utc)
GOLD = "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"
SUMMARY_VIEW = "idp_sbx.semantic_sem_commercial.mips_mpr_executive_summary_fact_vw"
BENCHMARK_VIEW = "idp_sbx.semantic_sem_commercial.mips_mpr_benchmark_prices_fact_vw"


def ontology():
    return ov.read_packages(package("data-product", "1.2.0"), package("kpi", ov.newest_version("kpi", RELEASES)))


def run(change=None, view=None, **settings):
    workspace, genie = support.sandbox()
    if change:
        change(workspace, genie)
    s = support.make_settings(**settings)
    view = view or ontology()
    schemas = {s.environment_name(o.full_name).rsplit(".", 1)[0] for o in view.objects.values()}
    found = discovery.discover(s, workspace.run_sql, genie, schemas)
    return compare.compare(view, found, s, NOW)


def kinds(result):
    return sorted({r["kind"]: 0 for r in result.rows}), [r["kind"] for r in result.rows]


def of(result, kind):
    return [r for r in result.rows if r["kind"] == kind]


def test_the_first_report_on_the_sandbox_shapes_is_the_expected_one():
    result = run()
    assert result.passes == {"object_names": 33, "table_edges": 40, "metric_view_sources": 3}
    assert result.blocked
    counts = {k: len(of(result, k)) for k in {r["kind"] for r in result.rows}}
    assert counts == {"column-renamed": 1, "column-case": 2, "object-extra": 7, "migration-pair": 8, "measure-link": 8,
                      "second-source": 1, "question": 1}
    assert len(result.rows) == 28

    # The one row that stops the load.
    blocking = [r for r in result.rows if r["blocks"]]
    assert len(blocking) == 1
    assert blocking[0] == {
        "kind": "column-renamed", "blocks": True, "object": GOLD, "ontology_value": "ChangeValue", "found_value": "Change_Value_Amount",
        "evidence": f"column lineage holds both names with the same sources; the metric view {SUMMARY_VIEW} reads Change_Value_Amount",
        "proposed_fix": {"action": "rename-column", "module": "data-product", "from": "ChangeValue", "to": "Change_Value_Amount"},
        "recommended": "accept", "decision": "", "decided_by": "", "note": ""}

    # The two names that differ only in case.
    assert [(r["object"], r["ontology_value"], r["found_value"], r["recommended"], r["blocks"]) for r in of(result, "column-case")] == [
        (GOLD, "assessment_amount", "Assessment_Amount", "accept", False),
        (GOLD, "Previous_amount", "Previous_Amount", "accept", False)]
    assert of(result, "column-case")[0]["proposed_fix"] == {"action": "rename-column", "module": "data-product",
                                                           "from": "assessment_amount", "to": "Assessment_Amount"}

    # The objects the ontology does not have: the two views and the unused silver and gold tables. No replica table.
    assert [r["object"] for r in of(result, "object-extra")] == [
        "idp_sbx.gold_commercial_core.sample_margin_fact", "idp_sbx.gold_commercial_core.sample_volume_fact",
        "idp_sbx.semantic_sem_commercial.mpr_mips_crack_spread_price_fact_metricsfromsilver_vw",
        "idp_sbx.semantic_sem_commercial.mpr_mips_crack_spread_price_fact_vw",
        "idp_sbx.silver_mdm_core.sample_location_dim", "idp_sbx.silver_mdm_core.sample_product_dim",
        "idp_sbx.silver_udm_core.sample_trade_fact"]
    assert {r["recommended"] for r in of(result, "object-extra")} == {"reject"}

    # The measure links proposed from Genie, all on the executive summary view.
    links = of(result, "measure-link")
    assert {r["object"] for r in links} == {SUMMARY_VIEW}
    assert [(r["found_value"], r["proposed_fix"]["measure"], r["ontology_value"]) for r in links] == [
        ("Crack spread KPI filter", "crack-spreads", ""),
        ("Gasoline basis KPI filter", "gasoline-prices", "gasoline-prices"),
        ("Gasoline cash KPI filter", "gasoline-prices", "gasoline-prices"),
        ("Distillate basis KPI filter", "distillate-prices", "distillate-prices"),
        ("Distillate cash KPI filter", "distillate-prices", "distillate-prices"),
        ("Crude KPI filter", "crude-prices", "crude-prices"),
        ("Renewable KPI filter", "additional-market-prices", "additional-market-prices"),
        ("NGL KPI filter", "additional-market-prices", "additional-market-prices")]
    assert links[5]["proposed_fix"] == {
        "action": "add-measure-link", "module": "data-product", "view": SUMMARY_VIEW, "measure": "crude-prices",
        "filter_name": "Crude KPI filter", "space": "01aa",
        "filter": "Sample_Sheet_Name IN ('Sample Sheet One', 'Sample Sheet Two')\nAND TRIM(Sample_Display_Name) IN ('Sample Item A', 'Sample Item B')"}

    # The two questions: crack spreads also come from the executive summary view; the benchmark view has no measure filter.
    second = of(result, "second-source")[0]
    assert (second["object"], second["proposed_fix"]) == (SUMMARY_VIEW, {
        "action": "add-serves-measure", "module": "data-product", "view": SUMMARY_VIEW, "measure": "crack-spreads"})
    assert second["ontology_value"] == "crack-spreads is served by idp_sbx.semantic_sem_commercial.mpr_mips_crack_spread_price_fact_metrics_vw"
    assert second["note"] == "Question: does Crack Spreads Pricing also come from this view?"
    question = of(result, "question")[0]
    assert (question["object"], question["ontology_value"], question["note"]) == \
        (BENCHMARK_VIEW, "crude-prices", "Question: does this view have a measure of its own?")

    # The tables that the current tables replace.
    pairs = of(result, "migration-pair")
    assert (pairs[0]["object"], pairs[0]["found_value"]) == (GOLD, "synapse_dev.commercial_core.mips_mpr_executive_summary_fact")
    assert sorted(r["found_value"].split(".")[1] for r in pairs) == ["commercial_core"] + ["mdm_core"] * 5 + ["udm_core"] * 2
    assert not any(r["blocks"] for r in result.rows if r["kind"] != "column-renamed")


def test_a_missing_object_blocks_and_a_wrong_catalog_name_reads_as_an_environment_setting():
    def drop(workspace, genie):
        workspace.objects.remove(("synapse_dev", "replica_mpr", "pricedetail", "FOREIGN"))
    result = run(drop)
    missing = of(result, "object-missing")
    assert [(r["object"], r["blocks"], r["recommended"]) for r in missing] == [("synapse_dev.replica_mpr.pricedetail", True, "")]
    assert result.passes == {"object_names": 32, "table_edges": 39, "metric_view_sources": 3}
    assert not of(result, "edge-missing")   # the object's own row covers its edge

    result = run(read_catalogs='read_catalogs = ["idp_sbx", "sources"]', synapse_dev='synapse_dev = "sources"')
    missing = of(result, "object-missing")
    assert len(missing) == 21 and {r["recommended"] for r in missing} == {"environment setting"}
    assert missing[0]["object"].startswith("sources.replica_") and missing[0]["proposed_fix"]["ontology_catalog"] == "synapse_dev"
    assert result.passes["object_names"] == 12


def test_a_renamed_object_is_found_by_its_lineage():
    def rename(workspace, genie):
        old, new = "idp_sbx.silver_udm_core.mpr_price_detail_fact", "idp_sbx.silver_udm_core.mpr_price_detail_v2_fact"
        workspace.objects = [(c, s, "mpr_price_detail_v2_fact" if f"{c}.{s}.{t}" == old else t, k) for c, s, t, k in workspace.objects]
        workspace.table_lineage = [(a, new if b == old else b, e, t) for a, b, e, t in workspace.table_lineage if a != old]
    result = run(rename)
    renamed = of(result, "object-renamed")
    assert [(r["ontology_value"], r["found_value"], r["blocks"], r["recommended"]) for r in renamed] == [
        ("idp_sbx.silver_udm_core.mpr_price_detail_fact", "idp_sbx.silver_udm_core.mpr_price_detail_v2_fact", True, "accept")]
    assert renamed[0]["evidence"] == "table lineage gives it every source the ontology's edges name"
    assert "idp_sbx.silver_udm_core.mpr_price_detail_v2_fact" not in [r["object"] for r in of(result, "object-extra")]


def test_a_missing_column_blocks_when_nothing_took_its_place():
    def drop(workspace, genie):
        workspace.columns[GOLD].remove("Change_Value_Amount")
    result = run(drop)
    assert [(r["ontology_value"], r["blocks"]) for r in of(result, "column-missing")] == [("ChangeValue", True)]
    assert not of(result, "column-renamed")


def test_a_rename_without_lineage_is_found_by_the_name():
    def no_lineage(workspace, genie):
        workspace.column_lineage = []
        workspace.columns[GOLD] = ["Assessment_Amount", "Previous_Amount", "Change_Value"]
    renamed = of(run(no_lineage), "column-renamed")
    assert [(r["found_value"], r["evidence"]) for r in renamed] == [("Change_Value", "the names differ only in punctuation or by a suffix")]


def test_a_missing_edge_blocks_and_an_object_with_no_lineage_at_all_does_not():
    edge = ("synapse_dev.replica_mips.mips_currency", "idp_sbx.silver_mdm_core.mips_price_sheet_dim")

    def drop_one(workspace, genie):
        workspace.table_lineage = [r for r in workspace.table_lineage if (r[0], r[1]) != edge]
    result = run(drop_one)
    assert [(r["object"], r["ontology_value"], r["blocks"]) for r in of(result, "edge-missing")] == [(edge[1], edge[0], True)]
    assert result.passes["table_edges"] == 39

    def drop_all(workspace, genie):
        workspace.table_lineage = [r for r in workspace.table_lineage if r[1] != "idp_sbx.silver_mdm_core.mips_price_batch_dim"]
    result = run(drop_all)
    assert [(r["object"], r["blocks"]) for r in of(result, "no-lineage")] == [("idp_sbx.silver_mdm_core.mips_price_batch_dim", False)]
    assert result.passes["table_edges"] == 39 and not of(result, "edge-missing")


def test_a_metric_view_that_reads_another_table_fails_its_source_check():
    def other_source(workspace, genie):
        text = (support.FIXTURES / "metric_view_table_source.yaml").read_text(encoding="utf-8").replace(
            "mips_mpr_executive_summary_fact", "sample_margin_fact")
        workspace.describe[SUMMARY_VIEW] = support.describe_json(SUMMARY_VIEW, text)
        workspace.table_lineage = [r for r in workspace.table_lineage if r[1] != SUMMARY_VIEW]
    result = run(other_source)
    assert result.passes == {"object_names": 33, "table_edges": 39, "metric_view_sources": 2}
    assert [(r["object"], r["ontology_value"]) for r in of(result, "edge-missing")] == [(SUMMARY_VIEW, GOLD)]
    questions = [r for r in of(result, "question") if r["proposed_fix"]["action"] == "add-edge"]
    assert [(r["object"], r["found_value"]) for r in questions] == [(SUMMARY_VIEW, "idp_sbx.gold_commercial_core.sample_margin_fact")]


def test_lineage_into_an_object_from_a_table_the_ontology_does_not_name_is_a_question():
    def feed(workspace, genie):
        workspace.table_lineage.append(("idp_sbx.silver_udm_core.sample_trade_fact", GOLD, "9001", "2026-11-02T06:00:00"))
    questions = [r for r in of(run(feed), "question") if r["object"] == GOLD]
    assert [(r["found_value"], r["blocks"]) for r in questions] == [("idp_sbx.silver_udm_core.sample_trade_fact", False)]


def test_stale_data_is_a_row_that_does_not_block_and_freshness_can_be_left_out():
    def old(workspace, genie):
        workspace.table_lineage = [(a, b, e, "2026-09-08T06:00:00" if b == GOLD else t) for a, b, e, t in workspace.table_lineage]
    result = run(old)
    assert [(r["object"], r["found_value"], r["blocks"]) for r in of(result, "stale-data")] == [(GOLD, "2026-09-08T06:00:00Z", False)]
    assert "35 days" in of(result, "stale-data")[0]["evidence"]
    workspace, genie = support.sandbox()
    old(workspace, genie)
    s = support.make_settings()
    found = discovery.discover(s, workspace.run_sql, genie, {"idp_sbx.gold_commercial_core"})
    assert not of(compare.compare(ontology(), found, s, NOW, stale_after_days=None), "stale-data")


def test_the_stale_threshold_compares_instants_across_offsets():
    # NOW is 2026-11-11 12:00 UTC, so the 35-day limit is 2026-10-07 12:00 UTC.
    def written(text):
        def change(workspace, genie):
            workspace.table_lineage = [(a, b, e, text if b == GOLD else t) for a, b, e, t in workspace.table_lineage]
        return [(r["object"], r["found_value"]) for r in of(run(change), "stale-data")]

    assert written("2026-10-07T10:00:00-05:00") == []                                   # 15:00 UTC: inside the limit
    assert written("2026-10-07 13:00:00+02:00") == [(GOLD, "2026-10-07T11:00:00Z")]     # 11:00 UTC: outside it
    assert written("2026-10-07 12:30:00") == []                                         # no zone is UTC
    assert written("2026-10-07T11:59:59Z") == [(GOLD, "2026-10-07T11:59:59Z")]
    # A reading that still holds the platform's own text is judged the same way.
    workspace, genie = support.sandbox()
    s = support.make_settings()
    found = discovery.discover(s, workspace.run_sql, genie, {"idp_sbx.gold_commercial_core"})
    for (source, target), edge in found.table_edges.items():
        if target == GOLD.lower():
            edge["last_event"] = "2026-10-07T10:00:00-05:00"
    assert not [r for r in of(compare.compare(ontology(), found, s, NOW), "stale-data") if r["object"] == GOLD]
    naive_now = dt.datetime(2026, 11, 11, 12, 0)
    assert not [r for r in of(compare.compare(ontology(), found, s, naive_now), "stale-data") if r["object"] == GOLD]


def test_two_ontology_objects_with_one_name_here_stop_the_comparison():
    import pytest
    from kpi_store import settings as settings_module
    view = ontology()
    twin = next(o for o in view.objects.values() if o.full_name.startswith("idp_sbx.gold_commercial_core."))
    other = "idp." + twin.full_name.split(".", 1)[1]
    view.objects[other.lower()] = ov.PlatformObject("urn:made-up:design/twin", other, "gold", ())
    s = settings_module.parse(support.SETTINGS_TEXT.replace('idp_sbx = "idp_sbx"\n', 'idp = "idp_sbx"\n').encode("utf-8"))
    workspace, genie = support.sandbox()
    found = discovery.discover(s, workspace.run_sql, genie, ())
    with pytest.raises(settings_module.SettingsError) as err:
        compare.compare(view, found, s, NOW)
    assert other in str(err.value) and twin.full_name in str(err.value)
    assert "idp = 'idp_sbx'" in str(err.value) and "idp_sbx (no entry)" in str(err.value)


def test_a_filter_whose_table_is_not_clear_is_a_question_and_the_telling_words_are_singular():
    def unclear(workspace, genie):
        title, text = genie.spaces["01aa"]
        genie.spaces["01aa"] = (title, text.replace('"Sample_Sheet_Name IN (\'Sample Sheet One\', \'Sample Sheet Two\')\\n"', '"Unknown_Column = 1\\n"')
                                .replace('"AND TRIM(Sample_Display_Name) IN (\'Sample Item A\', \'Sample Item B\')"', '""'))
    result = run(unclear)
    assert len(of(result, "measure-link")) == 7
    unclear_rows = [r for r in of(result, "question") if r["object"] == "Genie space Sample Pricing Space"]
    assert [(r["ontology_value"], r["found_value"]) for r in unclear_rows] == [("crude-prices", "Crude KPI filter")]
    assert compare.words("Crack spreads KPI filter") == {"crack", "spread"}
    assert compare.words("Additional Market Prices (Renewables, NGLs)") == {"renewable", "ngl"}
    assert compare.words("Default sample group") == {"sample", "group"}


def test_a_filter_that_names_two_measures_is_not_a_measure_link():
    def two(workspace, genie):
        title, text = genie.spaces["01aa"]
        genie.spaces["01aa"] = (title, text.replace("Gasoline basis KPI filter", "Gasoline and distillate KPI filter"))
    links = of(run(two), "measure-link")
    assert len(links) == 7 and "Gasoline and distillate KPI filter" not in [r["found_value"] for r in links]
