#!/usr/bin/env python3
"""Builds and removes the two practice catalogs that the test job's stores part reads.

    python scripts/rehearsal_workspace.py create [--profile NAME]   make both catalogs and their 63 made-up objects
    python scripts/rehearsal_workspace.py drop [--profile NAME]     drop both catalogs, with everything in them

The test job (.github/workflows/check.yml, the stores job) maps the client's catalogs to these two:
kpi_reh_idp_sbx plays idp_sbx (silver, gold and the metric views) and kpi_reh_synapse_dev plays synapse_dev (the
replica tables and the tables the current ones replace). Nothing here is client data. The object names are the
ones the ontology holds, plus made-up ones. Each downstream table is made FROM its sources (CREATE TABLE AS SELECT,
then INSERT ... SELECT), so Databricks records table and column lineage for each edge. Lineage appears in
system.access.table_lineage some time after the statements run, so wait before the first test run.

The executive summary fact table is made first with a column ChangeValue and then replaced with
Change_Value_Amount. Column lineage then holds both spellings, and the first run stops on the report on that one
difference, as the test job expects.

Every statement names one of the two catalogs, and nothing else in the workspace is read or changed. create stops
when a catalog already exists: run drop first. drop names only the two catalogs. The profile is a Databricks CLI
profile (default DEFAULT), signed in with `databricks auth login`. The statements run on the workspace's first SQL
warehouse by name. Needs databricks-sdk.
"""
import argparse
import sys
from pathlib import Path

MAIN, SOURCE = "kpi_reh_idp_sbx", "kpi_reh_synapse_dev"
CATALOGS = (MAIN, SOURCE)
COMMENT = "KPI Store rehearsal: made-up objects for the test job; safe to drop"

REPLICA = {
    "replica_kittyhawk": ("deliveryperiodcategory", "holidaycalendar", "priceservice"),
    "replica_mips": ("mips_currency", "mips_priceassessment", "mips_priceassessmentgroup", "mips_pricebatch",
                     "mips_pricegroup", "mips_pricesheet", "mips_unitofmeasure"),
    "replica_mpr": ("areastate", "attribute", "attributeref", "category", "city", "country", "facility", "frequency",
                    "pricedetail", "pricemaster", "pricetype"),
}
# Objects the skip rules must drop, and one replica table no data product reads.
REPLICA_NOISE = (("replica_mpr", "pricedetail__ct"), ("replica_mips", "attrep_apply_exceptions"), ("replica_mpr", "sample_unused_source"))

# Silver table -> (the columns it selects from its first source, its replica sources). The first source is the base.
SILVER = {
    "silver_mdm_core.mips_price_assessment_group_dim": ("replica_mips.mips_priceassessmentgroup", "replica_mips.mips_currency", "replica_mips.mips_unitofmeasure"),
    "silver_mdm_core.mips_price_batch_dim": ("replica_mips.mips_pricebatch",),
    "silver_mdm_core.mips_price_group_dim": ("replica_mips.mips_pricegroup",),
    "silver_mdm_core.mips_price_sheet_dim": ("replica_mips.mips_pricesheet", "replica_mips.mips_currency", "replica_mips.mips_unitofmeasure"),
    "silver_mdm_core.mpr_price_master_dim": (
        "replica_mpr.pricemaster", "replica_kittyhawk.deliveryperiodcategory", "replica_kittyhawk.holidaycalendar",
        "replica_kittyhawk.priceservice", "replica_mpr.areastate", "replica_mpr.attribute", "replica_mpr.attributeref",
        "replica_mpr.category", "replica_mpr.city", "replica_mpr.country", "replica_mpr.facility", "replica_mpr.frequency",
        "replica_mpr.pricetype"),
    "silver_udm_core.mips_price_assessment_fact": ("replica_mips.mips_priceassessment",),
    "silver_udm_core.mpr_price_detail_fact": ("replica_mpr.pricedetail",),
}
# The table each current table replaces: same name, schema without the layer prefix, in the source catalog.
REPLACED = [("mdm_core", t.split(".")[1]) for t in SILVER if t.startswith("silver_mdm_core.")] + \
           [("udm_core", t.split(".")[1]) for t in SILVER if t.startswith("silver_udm_core.")] + \
           [("commercial_core", "mips_mpr_executive_summary_fact")]
EXTRA_TABLES = ("gold_commercial_core.sample_margin_fact", "gold_commercial_core.sample_volume_fact",
                "silver_mdm_core.sample_location_dim", "silver_mdm_core.sample_product_dim", "silver_udm_core.sample_trade_fact")
MAIN_SCHEMAS = ("silver_mdm_core", "silver_udm_core", "gold_commercial_core", "semantic_sem_commercial", "bronze_replica_mpr")
SOURCE_SCHEMAS = (*REPLICA, "mdm_core", "udm_core", "commercial_core")

ROWS = "(1, 'Sample A', 10.5000, TIMESTAMP'2026-11-01 06:00:00'), (2, 'Sample B', 20.2500, TIMESTAMP'2026-11-02 06:00:00'), (3, 'Sample C', 30.0000, TIMESTAMP'2026-11-03 06:00:00')"
BASE_COLUMNS = "id INT, name STRING, amount DECIMAL(18,4), updated_at TIMESTAMP"


def silver_select(main, source, table, sources):
    """The SELECT that builds a silver table from every one of its replica sources, so each is a lineage edge."""
    joins = "".join(f" LEFT JOIN {source}.{s} s{i} ON s0.id = s{i}.id" for i, s in enumerate(sources[1:], 1))
    extra = "".join(f", s{i}.name AS Source_{i}_Name" for i in range(1, len(sources)))
    special = {
        "mips_price_assessment_fact": "s0.id AS Price_Batch_ID, s0.id AS Price_Group_ID, s0.id AS Price_Sheet_ID, s0.amount AS Assessment_Amount, s0.amount - 1 AS Previous_Amount",
        "mpr_price_detail_fact": "s0.id AS Price_Master_ID, CAST(s0.updated_at AS DATE) AS Effective_Date, s0.amount AS Settle_Price_Amount",
        "mips_price_sheet_dim": "s0.id AS Price_Sheet_ID, s0.name AS Price_Sheet_Name",
        "mips_price_group_dim": "s0.id AS Price_Group_ID, s0.name AS Price_Group_Name",
        "mips_price_batch_dim": "s0.id AS Price_Batch_ID, s0.updated_at AS Batch_Datetime",
        "mips_price_assessment_group_dim": "s0.id AS Price_Assessment_Group_ID, s0.name AS MIPS_Display_Name",
        "mpr_price_master_dim": "s0.id AS Price_Master_ID, s0.name AS Price_Master_Name",
    }[table.split(".")[1]]
    return f"SELECT {special}{extra} FROM {source}.{sources[0]} s0{joins}"


def gold_summary_select(main, change_column, assessment="Assessment_Amount", previous="Previous_Amount"):
    s = f"{main}.silver_mdm_core"
    return (f"SELECT sh.Price_Sheet_Name, ag.MIPS_Display_Name, pg.Price_Group_Name, b.Batch_Datetime, pm.Price_Master_Name, "
            f"f.Assessment_Amount AS {assessment}, f.Previous_Amount AS {previous}, "
            f"f.Assessment_Amount - f.Previous_Amount AS {change_column} "
            f"FROM {main}.silver_udm_core.mips_price_assessment_fact f "
            f"LEFT JOIN {s}.mips_price_sheet_dim sh ON f.Price_Sheet_ID = sh.Price_Sheet_ID "
            f"LEFT JOIN {s}.mips_price_assessment_group_dim ag ON f.Price_Group_ID = ag.Price_Assessment_Group_ID "
            f"LEFT JOIN {s}.mips_price_group_dim pg ON f.Price_Group_ID = pg.Price_Group_ID "
            f"LEFT JOIN {s}.mips_price_batch_dim b ON f.Price_Batch_ID = b.Price_Batch_ID "
            f"LEFT JOIN {s}.mpr_price_master_dim pm ON f.Price_Batch_ID = pm.Price_Master_ID")


def gold_crack_select(main):
    s = f"{main}.silver_mdm_core"
    return (f"SELECT 'SAMPLE KPI' AS KPI_ID, d.Effective_Date AS Price_Date, d.Settle_Price_Amount - f.Assessment_Amount AS Crack_Spread_Price_Amount, "
            f"'Y' AS Record_Active_Indicator, sh.Price_Sheet_Name, ag.MIPS_Display_Name, pg.Price_Group_Name, b.Batch_Datetime, pm.Price_Master_Name "
            f"FROM {main}.silver_udm_core.mips_price_assessment_fact f "
            f"JOIN {main}.silver_udm_core.mpr_price_detail_fact d ON f.Price_Batch_ID = d.Price_Master_ID "
            f"LEFT JOIN {s}.mips_price_sheet_dim sh ON f.Price_Sheet_ID = sh.Price_Sheet_ID "
            f"LEFT JOIN {s}.mips_price_assessment_group_dim ag ON f.Price_Group_ID = ag.Price_Assessment_Group_ID "
            f"LEFT JOIN {s}.mips_price_group_dim pg ON f.Price_Group_ID = pg.Price_Group_ID "
            f"LEFT JOIN {s}.mips_price_batch_dim b ON f.Price_Batch_ID = b.Price_Batch_ID "
            f"LEFT JOIN {s}.mpr_price_master_dim pm ON d.Price_Master_ID = pm.Price_Master_ID")


def metric_view(name, yaml_text):
    return f"CREATE VIEW {name} WITH METRICS LANGUAGE YAML AS $$\n{yaml_text.strip()}\n$$"


def statements(main, source):
    """[(kind, full name, SQL)] in the order to run. kind is schema, table or view; INSERTs carry kind "insert" and
    create nothing. Schemas are created without IF NOT EXISTS, so an existing schema stops the run instead of being
    adopted and later dropped."""
    out = [("schema", f"{source}.{s}", f"CREATE SCHEMA {source}.{s}") for s in SOURCE_SCHEMAS]
    out += [("schema", f"{main}.{s}", f"CREATE SCHEMA {main}.{s}") for s in MAIN_SCHEMAS]
    plain = [(schema, t) for schema, tables in REPLICA.items() for t in tables] + list(REPLICA_NOISE)
    for schema, table in plain:
        name = f"{source}.{schema}.{table}"
        out.append(("table", name, f"CREATE TABLE {name} ({BASE_COLUMNS})"))
        out.append(("insert", name, f"INSERT INTO {name} VALUES {ROWS}"))
    out.append(("table", f"{main}.bronze_replica_mpr.pricedetail", f"CREATE TABLE {main}.bronze_replica_mpr.pricedetail ({BASE_COLUMNS})"))
    for table, sources in SILVER.items():
        out.append(("table", f"{main}.{table}", f"CREATE TABLE {main}.{table} AS {silver_select(main, source, table, sources)}"))
    summary, crack = f"{main}.gold_commercial_core.mips_mpr_executive_summary_fact", f"{main}.gold_commercial_core.mpr_mips_crack_spread_price_fact"
    # First with the old column names, then replaced with the current ones: column lineage then holds both spellings,
    # as it does in the sandbox, and the table holds only the current ones.
    out.append(("table", summary, f"CREATE TABLE {summary} AS {gold_summary_select(main, 'ChangeValue', 'assessment_amount', 'Previous_amount')}"))
    out.append(("insert", summary, f"CREATE OR REPLACE TABLE {summary} AS {gold_summary_select(main, 'Change_Value_Amount')}"))
    out.append(("table", crack, f"CREATE TABLE {crack} AS {gold_crack_select(main)}"))
    # The replaced tables, each a copy of the current table; the INSERT back is the lineage edge of the migration pair.
    for schema, table in REPLACED:
        layer = "gold" if schema == "commercial_core" else "silver"
        old, new = f"{source}.{schema}.{table}", f"{main}.{layer}_{schema}.{table}"
        out.append(("table", old, f"CREATE TABLE {old} AS SELECT * FROM {new} LIMIT 0"))
        out.append(("insert", new, f"INSERT INTO {new} SELECT * FROM {old}"))
    for table in EXTRA_TABLES:
        out.append(("table", f"{main}.{table}", f"CREATE TABLE {main}.{table} ({BASE_COLUMNS})"))
    sem = f"{main}.semantic_sem_commercial"
    out.append(("view", f"{sem}.mips_mpr_executive_summary_fact_vw", metric_view(f"{sem}.mips_mpr_executive_summary_fact_vw", f"""
version: 1.1
source: {summary}
dimensions:
  - name: Price_Sheet_Name
    expr: Price_Sheet_Name
  - name: MIPS_Display_Name
    expr: TRIM(MIPS_Display_Name)
measures:
  - name: Assessment_Amount
    expr: SUM(Assessment_Amount)
  - name: Previous_Amount
    expr: SUM(Previous_Amount)
  - name: Change_Value_Amount
    expr: SUM(Change_Value_Amount)
""")))
    out.append(("view", f"{sem}.mips_mpr_benchmark_prices_fact_vw", metric_view(f"{sem}.mips_mpr_benchmark_prices_fact_vw", f"""
version: 1.1
source: {main}.silver_udm_core.mpr_price_detail_fact
joins:
  - name: master
    source: {main}.silver_mdm_core.mpr_price_master_dim
    on: source.Price_Master_ID = master.Price_Master_ID
filter: source.Price_Master_ID IN (1, 2, 3)
dimensions:
  - name: Display_Name
    expr: master.Price_Master_Name
  - name: Settle_Price_Amount
    expr: source.Settle_Price_Amount
measures:
  - name: Avg_Settle_Price
    expr: AVG(source.Settle_Price_Amount * 100)
  - name: Record_Count
    expr: COUNT(1)
""")))
    out.append(("view", f"{sem}.mpr_mips_crack_spread_price_fact_metrics_vw", metric_view(f"{sem}.mpr_mips_crack_spread_price_fact_metrics_vw", f"""
version: 1.1
source: {main}.gold_commercial_core.MPR_MIPS_Crack_Spread_Price_Fact
filter: Record_Active_Indicator = 'Y'
dimensions:
  - name: Price_Date
    expr: Price_Date
measures:
  - name: Avg_Crack_Spread
    expr: AVG(Crack_Spread_Price_Amount)
  - name: Max_Crack_Spread
    expr: MAX(Crack_Spread_Price_Amount)
  - name: Min_Crack_Spread
    expr: MIN(Crack_Spread_Price_Amount)
  - name: Spread_Range
    expr: MEASURE(Max_Crack_Spread) - MEASURE(Min_Crack_Spread)
  - name: Record_Count
    expr: COUNT(1)
""")))
    out.append(("view", f"{sem}.mpr_mips_crack_spread_price_fact_metricsfromsilver_vw", metric_view(f"{sem}.mpr_mips_crack_spread_price_fact_metricsfromsilver_vw", f"""
version: 1.1
source: |-
  WITH assessments AS (
    SELECT a.Price_Batch_ID, a.Assessment_Amount FROM {main}.silver_udm_core.mips_price_assessment_fact a
  ),
  settles AS (
    SELECT d.Price_Master_ID, d.Settle_Price_Amount FROM {main}.silver_udm_core.mpr_price_detail_fact d
  )
  SELECT 'SAMPLE KPI' AS KPI_ID, settles.Settle_Price_Amount - assessments.Assessment_Amount AS Crack_Spread
  FROM assessments JOIN settles ON assessments.Price_Batch_ID = settles.Price_Master_ID
dimensions:
  - name: KPI_ID
    expr: KPI_ID
measures:
  - name: Avg_Crack_Spread
    expr: AVG(Crack_Spread)
""")))
    out.append(("view", f"{sem}.mpr_mips_crack_spread_price_fact_vw",
                f"CREATE VIEW {sem}.mpr_mips_crack_spread_price_fact_vw AS SELECT * FROM {crack} WHERE Record_Active_Indicator = 'Y'"))
    return out

def create_statements():
    """[(kind, name, SQL)]: the two catalogs, then every object in the order to run."""
    return [("catalog", c, f"CREATE CATALOG {c} COMMENT '{COMMENT}'") for c in (SOURCE, MAIN)] + statements(MAIN, SOURCE)


def drop_statement(catalog):
    """The DROP for one practice catalog. Any other name is refused."""
    if catalog not in CATALOGS:
        raise SystemExit(f"refused: {catalog!r} is not one of the practice catalogs {', '.join(CATALOGS)}")
    return f"DROP CATALOG IF EXISTS {catalog} CASCADE"


def runner(profile):
    """run_sql(statement) on the workspace's first SQL warehouse by name, signed in through the CLI profile."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from kpi_store import sync_check
    client = sync_check.workspace_client(profile)
    found = sorted(client.warehouses.list(), key=lambda x: x.name or "")
    if not found:
        raise SystemExit("the workspace has no SQL warehouse")
    return sync_check.statement_runner(client, found[0].id)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("create", "drop"))
    parser.add_argument("--profile", default="DEFAULT", help="the Databricks CLI profile (default DEFAULT)")
    args = parser.parse_args(argv)
    run_sql = runner(args.profile)
    if args.command == "drop":
        for catalog in CATALOGS:
            run_sql(drop_statement(catalog))
            print("dropped", catalog)
        return 0
    plan = create_statements()
    for kind, name, statement in plan:
        try:
            run_sql(statement)
        except RuntimeError as err:
            raise SystemExit(f"{kind} {name}: {err}\n{statement[:300]}")
        print(f"{kind:8} {name}")
    made = sum(kind not in ("catalog", "insert") for kind, _, _ in plan)
    print(f"created 2 catalogs and {made} objects; lineage appears in system.access.table_lineage some time later")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
