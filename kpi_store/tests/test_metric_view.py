"""Metric view definitions: the YAML variants and the table names inside SQL."""
import pytest

from kpi_store import metric_view as mv
from kpi_store.tests import support

VIEW = "idp_sbx.semantic_sem_commercial.sample_vw"


def fixture(name):
    return (support.FIXTURES / name).read_text(encoding="utf-8")


def test_a_table_source_with_display_names_synonyms_and_format():
    view = mv.parse_describe_json(support.describe_json(VIEW, fixture("metric_view_table_source.yaml"), ("Assessment_Amount",)))
    assert view.name == VIEW and not view.source_is_sql
    assert view.tables == ["idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"]
    assert [m["name"] for m in view.measures] == ["Assessment_Amount", "Previous_Amount", "Change_Value_Amount"]
    assert view.measures[0]["display_name"] == "Assessment amount" and view.measures[0]["synonyms"] == ["assessment", "current value"]
    assert view.measures[0]["format"] == {"type": "number"}
    assert view.measure_columns == ["Assessment_Amount"] and view.from_name == VIEW
    assert view.reads_column("change_value_amount") and view.reads_column("Sample_Display_Name")
    assert not view.reads_column("ChangeValue") and not view.reads_column("Amount")


def test_joins_and_a_filter():
    view = mv.parse_yaml(fixture("metric_view_join_filter.yaml"), VIEW, "idp_sbx", "semantic_sem_commercial")
    assert view.tables == ["idp_sbx.silver_mdm_core.mpr_price_master_dim", "idp_sbx.silver_udm_core.mpr_price_detail_fact"]
    assert view.filter.startswith("source.Sample_Master_ID IN (901, 902, 903)")
    assert [d["name"] for d in view.dimensions] == ["Sample_Label", "Settle_Price_Amount"]
    assert view.reads_column("Settle_Price_Amount") and view.reads_column("sample_master_id")


def test_measure_references_and_a_source_in_mixed_case():
    view = mv.parse_yaml(fixture("metric_view_measure_refs.yaml"), VIEW)
    assert view.tables == ["idp_sbx.gold_commercial_core.mpr_mips_crack_spread_price_fact"]
    by_name = {m["name"]: m for m in view.measures}
    assert by_name["Sample_Range"]["measure_refs"] == ["Max_Spread", "Min_Spread"]
    assert by_name["Avg_Spread"]["measure_refs"] == []
    assert view.filter == "Sample_Active_Flag = 'Y'"


def test_a_sql_source_with_ctes_names_its_tables_and_not_its_ctes():
    view = mv.parse_yaml(fixture("metric_view_sql_source.yaml"), VIEW, "idp_sbx", "semantic_sem_commercial")
    assert view.source_is_sql
    assert view.tables == ["idp_sbx.silver_mdm_core.mips_price_group_dim", "idp_sbx.silver_udm_core.mips_price_assessment_fact",
                           "idp_sbx.silver_udm_core.mpr_price_detail_fact"]   # the two-part name takes the view's catalog


def test_nested_joins_backticks_and_short_names():
    text = """
version: 1.1
source: "`Gold_Sample`.`Fact`"
joins:
  - name: a
    source: dim_a
    using: [id]
    joins:
      - name: b
        source: SELECT * FROM other_cat.s.dim_b WHERE flag = 'Y'
measures:
  - name: n
    expr: COUNT(1)
"""
    view = mv.parse_yaml(text, VIEW, "idp_sbx", "semantic_sem_commercial")
    assert view.tables == ["idp_sbx.gold_sample.fact", "idp_sbx.semantic_sem_commercial.dim_a", "other_cat.s.dim_b"]


def test_tables_and_columns_in_sql():
    sql = "WITH x AS (SELECT * FROM a.b.c) SELECT * FROM x JOIN `d`.`e`.`F` USING (id) LEFT JOIN g.h ON TRUE"
    assert mv.tables_in_sql(sql, "cat", "sch") == ["a.b.c", "cat.g.h", "d.e.f"]
    with pytest.raises(mv.MetricViewError, match="cannot give"):
        mv.tables_in_sql("SELECT * FROM lonely")
    assert mv.columns_in_sql("v.Sample_Sheet_Name IN ('a', 'b') AND TRIM(Sample_Label) = 'c'") == [("", "sample_label"), ("v", "sample_sheet_name")]
    assert mv.columns_in_sql("not ( sql") == []


def test_a_definition_that_cannot_be_read_is_refused():
    with pytest.raises(mv.MetricViewError, match="not JSON"):
        mv.parse_describe_json("not json")
    with pytest.raises(mv.MetricViewError, match="holds no view_text"):
        mv.parse_describe_json('{"table_name": "v", "catalog_name": "c", "schema_name": "s"}')
    with pytest.raises(mv.MetricViewError, match="names no source"):
        mv.parse_yaml("version: 1.1\nmeasures: []\n", VIEW)
    with pytest.raises(mv.MetricViewError, match="not valid YAML"):
        mv.parse_yaml("source: [unclosed", VIEW)
    with pytest.raises(mv.MetricViewError, match="cannot parse the SQL"):
        mv.parse_yaml("source: SELECT FROM WHERE (", VIEW, "c", "s")
