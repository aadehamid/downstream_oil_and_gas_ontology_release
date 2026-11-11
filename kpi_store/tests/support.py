"""Made-up workspaces and releases for the tests: a fake Databricks that answers the statements the KPI Store
sends, a workspace with the sandbox's shapes, a small workspace, and a small release folder.

Every name of a column value, a job, a Genie filter or an unused table is invented. The 33 object names are the
ones the ontology already holds; they are written here by hand, never read from the ontology.
"""
import base64
import json
import re
from pathlib import Path
from types import SimpleNamespace

from kpi_store import settings as settings_module

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
SETTINGS_TEXT = (ROOT / "kpi_store" / "kpi_store.example.toml").read_text(encoding="utf-8")


def make_settings(folder=Path("."), **replace):
    """Settings from the example file, with whole lines replaced: make_settings(spaces='spaces = ["abc"]')."""
    text = SETTINGS_TEXT
    for key, line in replace.items():
        text, n = re.subn(rf"(?m)^{key} = .*$", line, text)
        assert n == 1, key
    return settings_module.parse(text.encode("utf-8"), folder)


def describe_json(full_name, yaml_text, measures=()):
    """The JSON that DESCRIBE TABLE EXTENDED <view> AS JSON returns for a metric view, in its real shape."""
    catalog, schema, table = full_name.split(".")
    return json.dumps({
        "table_name": table, "catalog_name": catalog, "namespace": [schema], "schema_name": schema,
        "type": "METRIC_VIEW", "view_text": yaml_text,
        "columns": [{"name": m, "type": {"name": "decimal", "precision": 38, "scale": 6}, "is_measure": True} for m in measures]
                   + [{"name": "Sample_Dimension", "type": {"name": "string"}}],
        "table_properties": {"metric_view.from.name": full_name, "metric_view.from.type": "ASSET"},
        "view_creation_spark_configuration": {"spark.sql.ansi.enabled": "true"},
    })


class FakeGenie:
    """The part of databricks-sdk's Genie API the discovery calls. Lists one space per page, so paging is used."""

    def __init__(self, spaces):
        self.spaces = spaces   # {space ID: (title, serialized space text or an Exception to raise)}
        self.calls = []

    def list_spaces(self, page_token=None):
        ids = sorted(self.spaces)
        at = ids.index(page_token) if page_token else 0
        self.calls.append(("list", page_token))
        return SimpleNamespace(spaces=[SimpleNamespace(space_id=ids[at], title=self.spaces[ids[at]][0])] if ids else [],
                               next_page_token=ids[at + 1] if at + 1 < len(ids) else None)

    def get_space(self, space_id, include_serialized_space=None):
        self.calls.append(("get", space_id, include_serialized_space))
        title, serialized = self.spaces[space_id]
        if isinstance(serialized, Exception):
            raise serialized
        return SimpleNamespace(space_id=space_id, title=title, serialized_space=serialized)


class FakeWorkspace:
    """A fake Databricks. run_sql answers each statement shape the KPI Store sends and fails on any other. The
    system tables return every row they hold, whatever the WHERE clause says, so the code's own filters are tested."""

    def __init__(self):
        self.objects = []        # (catalog, schema, table, table type)
        self.columns = {}        # {"catalog.schema.table": [column names]}
        self.describe = {}       # {"catalog.schema.table", lower case: DESCRIBE JSON text}
        self.table_lineage = []  # (source, target, entity ID or None, event time)
        self.column_lineage = [] # (source table, source column, target table, target column)
        self.jobs = []           # (job ID, name, change time)
        self.pipelines = []      # (pipeline ID, name, change time)
        self.store = {}          # {table, lower case: [row dicts]}: what the load created
        self.statements = []
        self.rewrites = 0        # how often a CREATE OR REPLACE ... AS SELECT ran
        self.corrupt_staging = False
        self.corrupt_promote = False   # alter a row as the staging table replaces the main table

    def writes(self):
        return [s for s in self.statements if not s.lstrip().upper().startswith(("SELECT", "DESCRIBE"))]

    def run_sql(self, statement):
        self.statements.append(statement)
        s = " ".join(statement.split())
        if s.startswith("SELECT table_catalog, table_schema, table_name, table_type"):
            return [{"table_catalog": c, "table_schema": sc, "table_name": t, "table_type": k, "last_altered": "2026-11-02T06:00:00"}
                    for c, sc, t, k in self.objects]
        if s.startswith("SELECT table_name FROM system.information_schema.tables"):
            catalog, schema = re.search(r"table_catalog\) = '(\w+)' AND lower\(table_schema\) = '(\w+)'", s).groups()
            return [{"table_name": name.split(".")[2]} for name in self.store if name.startswith(f"{catalog}.{schema}.")]
        if s.startswith("SELECT table_catalog, table_schema, table_name, column_name"):
            return [{"table_catalog": n.split(".")[0], "table_schema": n.split(".")[1], "table_name": n.split(".")[2],
                     "column_name": c, "ordinal_position": i} for n, cols in self.columns.items() for i, c in enumerate(cols, 1)]
        m = re.match(r"DESCRIBE TABLE EXTENDED `(\w+)`\.`(\w+)`\.`(\w+)` AS JSON$", s)
        if m:
            return [{"json_metadata": self.describe[".".join(m.groups()).lower()]}]
        if "FROM system.access.table_lineage" in s:
            return [{"source_table_full_name": a, "target_table_full_name": b, "entity_id": e, "last_event": t}
                    for a, b, e, t in self.table_lineage]
        if "FROM system.access.column_lineage" in s:
            return [{"source_table_full_name": a, "source_column_name": b, "target_table_full_name": c, "target_column_name": d}
                    for a, b, c, d in self.column_lineage]
        if "FROM system.lakeflow.jobs" in s:
            return [{"job_id": i, "name": n, "change_time": t} for i, n, t in self.jobs]
        if "FROM system.lakeflow.pipelines" in s:
            return [{"pipeline_id": i, "name": n, "change_time": t} for i, n, t in self.pipelines]
        if re.match(r"CREATE (SCHEMA|VOLUME) IF NOT EXISTS [\w.]+$", s):
            return []
        m = re.match(r"CREATE OR REPLACE TABLE ([\w.]+) AS SELECT \* FROM ([\w.]+)$", s)
        if m:
            self.store[m.group(1).lower()] = [dict(r) for r in self.store[m.group(2).lower()]]
            if self.corrupt_promote:
                self.store[m.group(1).lower()][0]["object"] += " altered"
                self.corrupt_promote = False
            self.rewrites += 1
            return []
        m = re.match(r"CREATE OR REPLACE TABLE ([\w.]+) \(subject STRING NOT NULL", s)
        if m:
            self.store[m.group(1).lower()] = []
            return []
        m = re.match(r"CREATE TABLE IF NOT EXISTS ([\w.]+) \(store STRING, marker STRING\)", s)
        if m:
            self.store.setdefault(m.group(1).lower(), [])
            return []
        m = re.match(r"DROP TABLE IF EXISTS ([\w.]+)$", s)
        if m:
            self.store.pop(m.group(1).lower(), None)
            return []
        m = re.match(r"DELETE FROM ([\w.]+) WHERE store = '(\w+)'$", s)
        if m:
            self.store[m.group(1).lower()] = [r for r in self.store[m.group(1).lower()] if r["store"] != m.group(2)]
            return []
        m = re.match(r"INSERT INTO ([\w.]+) \(store, marker\) SELECT '(\w+)', decode\(unbase64\('([A-Za-z0-9+/=]+)'\), 'UTF-8'\)$", s)
        if m:
            self.store[m.group(1).lower()].append({"store": m.group(2), "marker": base64.b64decode(m.group(3)).decode("utf-8")})
            return []
        m = re.match(r"INSERT INTO ([\w.]+) \(subject, predicate, object, object_kind, datatype, lang, graph\) SELECT ", s)
        if m:
            names = ("subject", "predicate", "object", "object_kind", "datatype", "lang", "graph")
            rows = []
            for line in statement.split("FROM VALUES\n", 1)[1].split("\nAS v(")[0].split("\n"):
                cells = line.rstrip(",").strip()[1:-1].split(", ")
                assert len(cells) == 7, line
                rows.append({n: None if c == "NULL" else base64.b64decode(c.strip("'")).decode("utf-8") for n, c in zip(names, cells)})
            if self.corrupt_staging and rows:
                rows[0]["object"] += " altered"
                self.corrupt_staging = False
            self.store[m.group(1).lower()] += rows
            return []
        m = re.match(r"SELECT subject, predicate, object, object_kind, datatype, lang, graph FROM ([\w.]+)$", s)
        if m:
            return [dict(r) for r in self.store[m.group(1).lower()]]
        m = re.match(r"SELECT marker FROM ([\w.]+) WHERE store = '(\w+)'$", s)
        if m:
            return [{"marker": r["marker"]} for r in self.store[m.group(1).lower()] if r["store"] == m.group(2)]
        raise AssertionError(f"the fake workspace does not know this statement: {s[:200]}")


# ---- the workspace with the sandbox's shapes -------------------------------------------------------

SILVER_MDM = ("mips_price_assessment_group_dim", "mips_price_batch_dim", "mips_price_group_dim", "mips_price_sheet_dim",
              "mpr_price_master_dim")
SILVER_UDM = ("mips_price_assessment_fact", "mpr_price_detail_fact")
GOLD = ("mips_mpr_executive_summary_fact", "mpr_mips_crack_spread_price_fact")
METRIC_VIEWS = ("mips_mpr_benchmark_prices_fact_vw", "mips_mpr_executive_summary_fact_vw",
                "mpr_mips_crack_spread_price_fact_metrics_vw")
REPLICA = {
    "replica_kittyhawk": ("deliveryperiodcategory", "holidaycalendar", "priceservice"),
    "replica_mips": ("mips_currency", "mips_priceassessment", "mips_priceassessmentgroup", "mips_pricebatch",
                     "mips_pricegroup", "mips_pricesheet", "mips_unitofmeasure"),
    "replica_mpr": ("areastate", "attribute", "attributeref", "category", "city", "country", "facility", "frequency",
                    "pricedetail", "pricemaster", "pricetype"),
}
# The 40 table edges, target first, written by hand.
EDGES = {
    "idp_sbx.silver_mdm_core.mips_price_assessment_group_dim": ("replica_mips.mips_currency", "replica_mips.mips_priceassessmentgroup", "replica_mips.mips_unitofmeasure"),
    "idp_sbx.silver_mdm_core.mips_price_batch_dim": ("replica_mips.mips_pricebatch",),
    "idp_sbx.silver_mdm_core.mips_price_group_dim": ("replica_mips.mips_pricegroup",),
    "idp_sbx.silver_mdm_core.mips_price_sheet_dim": ("replica_mips.mips_currency", "replica_mips.mips_pricesheet", "replica_mips.mips_unitofmeasure"),
    "idp_sbx.silver_mdm_core.mpr_price_master_dim": (
        "replica_kittyhawk.deliveryperiodcategory", "replica_kittyhawk.holidaycalendar", "replica_kittyhawk.priceservice",
        "replica_mpr.areastate", "replica_mpr.attribute", "replica_mpr.attributeref", "replica_mpr.category", "replica_mpr.city",
        "replica_mpr.country", "replica_mpr.facility", "replica_mpr.frequency", "replica_mpr.pricemaster", "replica_mpr.pricetype"),
    "idp_sbx.silver_udm_core.mips_price_assessment_fact": ("replica_mips.mips_priceassessment",),
    "idp_sbx.silver_udm_core.mpr_price_detail_fact": ("replica_mpr.pricedetail",),
    "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact": (
        "silver_udm_core.mips_price_assessment_fact", "silver_mdm_core.mips_price_assessment_group_dim",
        "silver_mdm_core.mips_price_batch_dim", "silver_mdm_core.mips_price_group_dim", "silver_mdm_core.mips_price_sheet_dim",
        "silver_mdm_core.mpr_price_master_dim"),
    "idp_sbx.gold_commercial_core.mpr_mips_crack_spread_price_fact": (
        "silver_udm_core.mips_price_assessment_fact", "silver_mdm_core.mips_price_assessment_group_dim",
        "silver_mdm_core.mips_price_batch_dim", "silver_mdm_core.mips_price_group_dim", "silver_mdm_core.mips_price_sheet_dim",
        "silver_udm_core.mpr_price_detail_fact", "silver_mdm_core.mpr_price_master_dim"),
    "idp_sbx.semantic_sem_commercial.mips_mpr_benchmark_prices_fact_vw": ("silver_udm_core.mpr_price_detail_fact", "silver_mdm_core.mpr_price_master_dim"),
    "idp_sbx.semantic_sem_commercial.mips_mpr_executive_summary_fact_vw": ("gold_commercial_core.mips_mpr_executive_summary_fact",),
    "idp_sbx.semantic_sem_commercial.mpr_mips_crack_spread_price_fact_metrics_vw": ("gold_commercial_core.mpr_mips_crack_spread_price_fact",),
}
EXTRAS = (("gold_commercial_core", "sample_margin_fact", "MANAGED"), ("gold_commercial_core", "sample_volume_fact", "MANAGED"),
          ("silver_mdm_core", "sample_location_dim", "MANAGED"), ("silver_mdm_core", "sample_product_dim", "STREAMING_TABLE"),
          ("silver_udm_core", "sample_trade_fact", "MANAGED"),
          ("semantic_sem_commercial", "mpr_mips_crack_spread_price_fact_metricsfromsilver_vw", "METRIC_VIEW"),
          ("semantic_sem_commercial", "mpr_mips_crack_spread_price_fact_vw", "VIEW"))
GOLD_SUMMARY = "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"
SILVER_ASSESSMENT = "idp_sbx.silver_udm_core.mips_price_assessment_fact"
SEMANTIC = "idp_sbx.semantic_sem_commercial."


def sandbox():
    """(FakeWorkspace, FakeGenie) with the sandbox's shapes: the 33 objects, the renamed column, the two columns
    that differ in case, the unused objects, the 40 edges, the migration pairs, and rows the rules must drop."""
    w = FakeWorkspace()
    for schema, tables in REPLICA.items():
        w.objects += [("synapse_dev", schema, t, "FOREIGN") for t in tables]
    w.objects += [("idp_sbx", "silver_mdm_core", t, "MANAGED") for t in SILVER_MDM]
    w.objects += [("idp_sbx", "silver_udm_core", t, "MANAGED") for t in SILVER_UDM]
    w.objects += [("idp_sbx", "gold_commercial_core", t, "MANAGED") for t in GOLD]
    w.objects += [("idp_sbx", "semantic_sem_commercial", t, "METRIC_VIEW") for t in METRIC_VIEWS]
    w.objects += [("idp_sbx", schema, t, kind) for schema, t, kind in EXTRAS]
    # Rows the skip rules cover, a replica table no data product reads, and a catalog outside the read catalogs.
    w.objects += [("synapse_dev", "replica_mpr", "pricedetail__ct", "FOREIGN"), ("synapse_dev", "replica_mips", "attrep_apply_exceptions", "FOREIGN"),
                  ("idp_sbx", "bronze_replica_mpr", "pricedetail", "MANAGED"), ("idp_sbx", "kpi_store_poc", "old_triples", "MANAGED"),
                  ("idp_sbx", "information_schema", "tables", "VIEW"), ("synapse_dev", "replica_mpr", "sample_unused_source", "FOREIGN"),
                  ("other_catalog", "gold_commercial_core", "elsewhere_fact", "MANAGED")]
    # The tables each current table replaces: the same name, in the schema the layer rule gives.
    old = [("mdm_core", t) for t in SILVER_MDM] + [("udm_core", t) for t in SILVER_UDM] + [("commercial_core", GOLD[0])]
    w.objects += [("synapse_dev", schema, t, "FOREIGN") for schema, t in old]

    w.columns = {
        GOLD_SUMMARY: ["Sample_Sheet_Name", "Sample_Display_Name", "Assessment_Amount", "Previous_Amount", "Change_Value_Amount"],
        "idp_sbx.gold_commercial_core.mpr_mips_crack_spread_price_fact": ["Sample_Date", "Crack_Spread_Price_Amount", "Sample_Active_Flag"],
        SILVER_ASSESSMENT: ["Sample_Batch_ID", "Sample_Group_ID", "Assessment_Amount", "Previous_Amount"],
        "idp_sbx.silver_udm_core.mpr_price_detail_fact": ["Sample_Master_ID", "Sample_Effective_Date", "Settle_Price_Amount"],
        SEMANTIC + "mips_mpr_benchmark_prices_fact_vw": ["Sample_Label", "Settle_Price_Amount", "Avg_Sample_Price", "Row_Count"],
        SEMANTIC + "mips_mpr_executive_summary_fact_vw": ["Sample_Sheet_Name", "Sample_Display_Name", "Assessment_Amount", "Previous_Amount", "Change_Value_Amount"],
        SEMANTIC + "mpr_mips_crack_spread_price_fact_metrics_vw": ["Sample_Date", "Avg_Spread", "Max_Spread", "Min_Spread", "Sample_Range", "Row_Count"],
        "idp_sbx.bronze_replica_mpr.pricedetail": ["Id"],
        "other_catalog.gold_commercial_core.elsewhere_fact": ["ChangeValue"],
    }
    for view, fixture, measures in (
            ("mips_mpr_benchmark_prices_fact_vw", "metric_view_join_filter.yaml", ("Avg_Sample_Price", "Row_Count")),
            ("mips_mpr_executive_summary_fact_vw", "metric_view_table_source.yaml", ("Assessment_Amount", "Previous_Amount", "Change_Value_Amount")),
            ("mpr_mips_crack_spread_price_fact_metrics_vw", "metric_view_measure_refs.yaml", ("Avg_Spread", "Max_Spread", "Min_Spread", "Sample_Range", "Row_Count")),
            ("mpr_mips_crack_spread_price_fact_metricsfromsilver_vw", "metric_view_sql_source.yaml", ("Avg_Spread",))):
        w.describe[SEMANTIC + view] = describe_json(SEMANTIC + view, (FIXTURES / fixture).read_text(encoding="utf-8"), measures)

    when = "2026-11-02T06:00:00"
    for target, sources in EDGES.items():
        for source in sources:
            catalog = "synapse_dev" if source.startswith("replica_") else "idp_sbx"
            # The benchmark view's join is left out of lineage, so the view's own definition must prove that edge.
            if target.endswith("benchmark_prices_fact_vw") and source.endswith("mpr_price_master_dim"):
                continue
            entity = None if target.startswith(SEMANTIC) else "9001"
            w.table_lineage.append((f"{catalog}.{source}", target, entity, when))
    w.table_lineage += [(f"synapse_dev.{schema}.{t}", f"idp_sbx.{'gold' if schema == 'commercial_core' else 'silver'}_{schema}.{t}", None, "2026-08-14T10:00:00")
                        for schema, t in old]
    w.table_lineage += [
        ("idp_sbx.silver_mdm_core.mips_price_batch_dim", "idp_sbx.silver_mdm_core.mips_price_batch_dim", "9001", when),       # a self-edge
        ("idp_sbx.staging.dropped_stage_table", "idp_sbx.silver_mdm_core.mips_price_group_dim", "9001", "2026-07-20T06:00:00"),  # its source is gone
        (GOLD_SUMMARY, "idp_sbx.gold_commercial_core.dropped_variant_fact", "9001", "2026-07-20T06:00:00"),                  # its target is gone
        ("idp_sbx.bronze_replica_mpr.pricedetail", "idp_sbx.silver_udm_core.mpr_price_detail_fact", None, "2026-09-02T06:00:00"),  # a skipped schema
        ("other_catalog.gold_commercial_core.elsewhere_fact", GOLD_SUMMARY, None, when),                                    # outside the read catalogs
        ("synapse_dev.replica_mpr.pricemaster", "idp_sbx.silver_mdm_core.sample_location_dim", "pipe-0001", "2026-10-01T06:00:00"),
        (None, GOLD_SUMMARY, "9001", when),
    ]
    w.column_lineage = [
        (SILVER_ASSESSMENT, "Assessment_Amount", GOLD_SUMMARY, "assessment_amount"),
        (SILVER_ASSESSMENT, "Assessment_Amount", GOLD_SUMMARY, "Assessment_Amount"),
        (SILVER_ASSESSMENT, "Previous_Amount", GOLD_SUMMARY, "Previous_amount"),
        (SILVER_ASSESSMENT, "Previous_Amount", GOLD_SUMMARY, "Previous_Amount"),
        (SILVER_ASSESSMENT, "Assessment_Amount", GOLD_SUMMARY, "ChangeValue"),
        (SILVER_ASSESSMENT, "Previous_Amount", GOLD_SUMMARY, "ChangeValue"),
        (SILVER_ASSESSMENT, "Assessment_Amount", GOLD_SUMMARY, "Change_Value_Amount"),
        (SILVER_ASSESSMENT, "Previous_Amount", GOLD_SUMMARY, "Change_Value_Amount"),
        (GOLD_SUMMARY, "Change_Value_Amount", GOLD_SUMMARY, "Change_Value_Amount"),                       # a self-edge
        ("idp_sbx.staging.dropped_stage_table", "Amount", GOLD_SUMMARY, "Change_Value_Amount"),           # its source is gone
    ]
    w.jobs = [("9001", "Sample_Old_Pipeline_Name", "2026-07-10T00:00:00"), ("9001", "Sample_Master_Pipeline", "2026-10-20T00:00:00"),
              ("7777", "Sample_Unrelated_Job", "2026-10-21T00:00:00")]
    w.pipelines = [("pipe-0001", "Sample_Bronze_To_Silver", "2026-09-30T00:00:00")]
    crack_space = json.dumps({"version": 2, "data_sources": {"tables": [{"identifier": SEMANTIC + "mpr_mips_crack_spread_price_fact_metrics_vw"}]},
                              "instructions": {"example_question_sqls": [{"id": "e1", "question": ["Show the sample spread"],
                                                                         "sql": ["SELECT MEASURE(Avg_Spread) FROM " + SEMANTIC + "mpr_mips_crack_spread_price_fact_metrics_vw"]}]}})
    genie = FakeGenie({"01aa": ("Sample Pricing Space", (FIXTURES / "genie_space.json").read_text(encoding="utf-8")),
                       "01bb": ("Sample Spread Space", crack_space)})
    return w, genie


# ---- a small release and a small workspace -------------------------------------------------------

PREFIXES = """@prefix dp: <https://w3id.org/mpc/ontology/modules/data-product/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix dcat: <http://www.w3.org/ns/dcat#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix t: <https://w3id.org/mpc/ontology/modules/data-product/table/> .
@prefix c: <https://w3id.org/mpc/ontology/modules/data-product/column/> .
@prefix layer: <https://w3id.org/mpc/ontology/modules/data-product/layer/> .
@prefix m: <https://w3id.org/mpc/ontology/modules/kpi/measure/> .
"""
MODULES = "https://w3id.org/mpc/ontology/modules/"


def small_data_product(version="1.0.0", fact="sample_fact", column="Amount"):
    return PREFIXES + f"""
<{MODULES}data-product> a owl:Ontology ; owl:versionIRI <{MODULES}data-product/{version}> .
t:source a dp:PlatformTable ; dp:fullName "synapse_dev.replica_sample.source_table" ; dp:layer layer:replica .
t:middle a dp:PlatformTable ; dp:fullName "idp_sbx.silver_sample.middle_dim" ; dp:layer layer:silver ;
    prov:wasDerivedFrom t:source .
t:fact a dp:PlatformTable ; dp:fullName "idp_sbx.gold_sample.{fact}" ; dp:layer layer:gold ;
    prov:wasDerivedFrom t:middle ; dp:servesMeasure m:sample-prices .
c:middle--amount a dp:PlatformColumn ; dp:columnName "Amount" ; dp:columnOf t:middle .
c:fact--amount a dp:PlatformColumn ; dp:columnName "{column}" ; dp:columnOf t:fact ; prov:wasDerivedFrom c:middle--amount .
_:note skos:note "A blank node, so the hash is tested on one." .
"""


def small_release(root, versions=("1.0.0",), catalog_versions=None, **data_product):
    """Writes a small release folder under root and returns root. The data-product module gets one package per
    version; the catalog lists catalog_versions, by default the same ones."""
    releases = root / "business_architecture" / "ontology" / "releases"

    def package(module, version, content, extra=()):
        folder = releases / module / version
        folder.mkdir(parents=True, exist_ok=True)
        files = {f"{module}.ttl": content,
                 "shapes.ttl": f"<{MODULES}{module}/{version}/shapes#S> a <http://www.w3.org/ns/shacl#NodeShape> .\n",
                 "catalog.ttl": f"<{MODULES}{module}/{version}> a <http://www.w3.org/ns/dcat#Dataset> .\n", **dict(extra)}
        for name, text in files.items():
            (folder / name).write_text(text, encoding="utf-8", newline="\n")
        (folder / "manifest.json").write_text(json.dumps({"module": module, "version": version, "files": {n: "" for n in files}}),
                                              encoding="utf-8", newline="\n")

    for version in versions:
        package("data-product", version, small_data_product(version, **data_product),
                extra=[("sample-model.ttl", "<urn:sample:model> a <urn:sample:Model> .\n")])
    package("kpi", "1.0.0", PREFIXES + f"""
<{MODULES}kpi> a owl:Ontology ; owl:versionIRI <{MODULES}kpi/1.0.0> .
m:sample-prices a skos:Concept ; skos:prefLabel "Sample Market Pricing"@en ; skos:notation "sample-prices" .
""")
    listed = [f"<{MODULES}data-product/{v}>" for v in (catalog_versions or versions)] + [f"<{MODULES}kpi/1.0.0>"]
    (releases / "catalog.ttl").write_text(
        "@prefix dcat: <http://www.w3.org/ns/dcat#> .\n<urn:sample:catalog> a dcat:Catalog ; dcat:dataset " + ", ".join(listed) + " .\n",
        encoding="utf-8", newline="\n")
    projection = root / "business_architecture" / "ontology" / "projection"
    projection.mkdir(parents=True, exist_ok=True)
    # The release's own description of what a current store holds, which the load imports from the release it loads.
    (projection / "sync_stores.py").write_text((ROOT / "business_architecture" / "ontology" / "projection" / "sync_stores.py").read_text(encoding="utf-8"),
                                               encoding="utf-8", newline="\n")
    # The one version order of the tree, which sync_stores and kpi_store read from the release scripts.
    release = root / "business_architecture" / "ontology" / "release"
    release.mkdir(parents=True, exist_ok=True)
    (release / "newest.py").write_text((ROOT / "business_architecture" / "ontology" / "release" / "newest.py").read_text(encoding="utf-8"),
                                       encoding="utf-8", newline="\n")
    (projection / "projection-manifest.json").write_text('{"input_fingerprint": "sample-fingerprint"}\n', encoding="utf-8", newline="\n")
    (root / "release.json").write_text('{"release": "KPI Store 1.1"}\n', encoding="utf-8", newline="\n")
    return root


def small_workspace():
    """A FakeWorkspace that agrees with small_release: three objects, their columns and their two edges."""
    w = FakeWorkspace()
    w.objects = [("synapse_dev", "replica_sample", "source_table", "FOREIGN"), ("idp_sbx", "silver_sample", "middle_dim", "MANAGED"),
                 ("idp_sbx", "gold_sample", "sample_fact", "MANAGED")]
    w.columns = {"idp_sbx.silver_sample.middle_dim": ["Amount"], "idp_sbx.gold_sample.sample_fact": ["Amount"]}
    w.table_lineage = [("synapse_dev.replica_sample.source_table", "idp_sbx.silver_sample.middle_dim", "9001", "2026-11-02T06:00:00"),
                       ("idp_sbx.silver_sample.middle_dim", "idp_sbx.gold_sample.sample_fact", "9001", "2026-11-02T06:00:00")]
    w.jobs = [("9001", "Sample_Master_Pipeline", "2026-10-20T00:00:00")]
    return w
