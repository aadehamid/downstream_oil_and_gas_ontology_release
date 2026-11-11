"""The four questions on a real Neo4j Enterprise composite database, with the made-up graphs.

The test needs a test server and skips without one. Name the server in the environment:

    KPI_STORE_TEST_NEO4J_URI=bolt://127.0.0.1:17811
    KPI_STORE_TEST_NEO4J_PASSWORD=<the test server's password>
    KPI_STORE_TEST_NEO4J_USER=neo4j            (optional)

It replaces what the two fixture databases hold, so it never runs against a server it was not pointed at.
It is one test, because its steps share the server and must not run side by side.
Every expected row is written by hand from fixtures/questions/governance.cypher and bpa.cypher.
"""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path

import pytest

from kpi_store.questions import connection as C
from kpi_store.questions import discover as D
from kpi_store.questions import mapping as M
from kpi_store.questions import run

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "questions"

VIEW = "idp_sbx.semantic_sem_commercial.mips_mpr_executive_summary_fact_vw"
GOLD = "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"
CHECK = {"object": GOLD, "check": "gold table has rows", "result": "pass", "checked_at": "2026-11-01T06:00:00Z"}

Q6 = [
    {"kpi_code": "crude-prices", "kpi": "Crude Market Pricing", "metric_view": VIEW, "gold": [GOLD],
     "silver": ["idp_sbx.silver_udm_core.mips_price_assessment_fact"],
     "replica": "synapse_dev.replica_mips.mips_priceassessment", "system_code": "mips", "system": "MIPS",
     "quality": [CHECK], "governance_system": "MIPS", "governance_tables": 3,
     "governance_table_sample": ["MIPS.Currency", "MIPS.PriceAssessment"],
     "governance_table": ["MIPS.PriceAssessment"]},
    {"kpi_code": "crude-prices", "kpi": "Crude Market Pricing", "metric_view": VIEW, "gold": [GOLD],
     "silver": ["idp_sbx.silver_mdm_core.mpr_price_master_dim"],
     "replica": "synapse_dev.replica_mpr.pricemaster", "system_code": "mpr", "system": "MPR",
     "quality": [CHECK], "governance_system": "MPR", "governance_tables": 2,
     "governance_table_sample": ["MPR.PriceDetail", "MPR.PriceMaster"],
     "governance_table": ["MPR.PriceMaster"]},
]

Q4 = [
    ("kpi store", "replica table", "synapse_dev.replica_mips.mips_priceassessment", None, "replica"),
    ("kpi store", "silver table", "idp_sbx.silver_udm_core.mips_price_assessment_fact", None, "silver"),
    ("kpi store", "gold table", GOLD, None, "gold"),
    ("kpi store", "metric view", VIEW, None, "metric-view"),
    ("kpi store", "data product", "dp-master-pricing", "Master Pricing", None),
    ("kpi store", "kpi", "crude-prices", "Crude Market Pricing", None),
    ("governance", "table", "MIPS.Currency", None, "Operational"),
    ("governance", "table", "MIPS.PriceAssessment", None, "Operational"),
    ("governance", "table", "MIPS.PriceBatch", None, "Operational"),
    ("governance", "derived table", "RPT.PriceSummary", None, "Reporting"),
]

# system, in_kpi_store, tables, replica, silver, gold, by_link
Q1_WITH_LINKS = [("DW_REPORTING", False, 1, 0, 0, 0, 0), ("MIPS", True, 3, 1, 2, 1, 1),
                 ("MPR", True, 2, 1, 1, 1, 0), ("ZEPHYR", False, 2, 0, 0, 0, 0)]
Q1_BY_NAME = [("DW_REPORTING", False, 1, 0, 0, 0, 0), ("MIPS", True, 3, 1, 1, 1, 0),
              ("MPR", True, 2, 1, 1, 1, 0), ("ZEPHYR", False, 2, 0, 0, 0, 0)]

Q7 = [
    {"kpi_code": "crude-prices", "kpi": "Crude Market Pricing", "metric_view": VIEW, "system_code": "mips",
     "governance_system": "MIPS",
     "reasons": ["policy Confidential pricing data on table MIPS.PriceAssessment",
                 "policy SOX financial reporting on the system"]},
    {"kpi_code": "crude-prices", "kpi": "Crude Market Pricing", "metric_view": VIEW, "system_code": "mpr",
     "governance_system": "MPR", "reasons": ["class Confidential on table MPR.PriceMaster"]},
]


def builder():
    spec = importlib.util.spec_from_file_location("questions_build_graph", FIXTURES / "build_graph.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def server():
    uri, password = os.environ.get("KPI_STORE_TEST_NEO4J_URI"), os.environ.get("KPI_STORE_TEST_NEO4J_PASSWORD")
    if not uri or not password:
        pytest.skip("no test server named: set KPI_STORE_TEST_NEO4J_URI and KPI_STORE_TEST_NEO4J_PASSWORD")
    neo4j = pytest.importorskip("neo4j", reason="the neo4j driver is not installed")
    build = builder()
    connection = C.Connection(uri=uri, user=os.environ.get("KPI_STORE_TEST_NEO4J_USER", "neo4j"), password=password,
                              composite=build.COMPOSITE, governance_alias="governance", bpa_alias="bpa")
    driver = neo4j.GraphDatabase.driver(uri, auth=(connection.user, password), notifications_min_severity="OFF",
                                        connection_timeout=5, max_transaction_retry_time=5)
    try:
        driver.verify_connectivity()
    except Exception as error:
        driver.close()
        pytest.skip(f"no test server reachable at {uri}: {type(error).__name__}")
    return connection, driver, build


def tuples(answer):
    return [tuple(row[c] for c in answer["columns"]) for row in answer["rows"]]


def set_value(mapping, role, value):
    changed = copy.deepcopy(mapping)
    changed["roles"][role]["value"] = value
    changed["digest"] = M.digest(changed)
    return changed


def test_the_four_questions_on_a_composite_database(tmp_path, monkeypatch):
    connection, driver, build = server()
    reader = run.Reader(connection)
    try:
        build.build(driver)

        # Discovery, without a plugin, proposes the mapping the fixture holds.
        schemas = run.read_schemas(reader, connection.graphs)
        proposal = D.propose(schemas)
        with (FIXTURES / "mapping.json").open(encoding="utf-8") as f:
            expected = json.load(f)
        assert {n: e["value"] for n, e in proposal["roles"].items()} == {
            n: e["value"] for n, e in expected["roles"].items()}
        assert proposal["roles"]["system_to_table"]["value"] == {"types": ["CONTAINS"], "max_hops": 2}
        mapping = M.confirm(proposal, schemas)

        def ask(question, mapping=mapping, **params):
            return run.ask(reader, question, mapping, connection.graphs, params)

        assert ask("q6", kpi="crude-prices", sample=2)["rows"] == Q6
        assert ask("q6", kpi="Crude Market PRICING", sample=2)["rows"] == Q6        # by name, any case
        assert ask("q6", kpi="no-such-kpi")["rows"] == []
        no_checks = ask("q6", mapping=set_value(mapping, "tech.checks", None), kpi="crude-prices", sample=2)["rows"]
        assert no_checks == [dict(row, quality=[]) for row in Q6]

        answer = ask("q4", system="MIPS")
        assert answer["columns"] == ["graph", "kind", "name", "label", "layer"] and tuples(answer) == Q4
        empty = ask("q4", system="no-such-system")
        assert empty["rows"] == [] and empty["columns"] == ["graph", "kind", "name", "label", "layer"]
        no_lineage = ask("q4", mapping=set_value(mapping, "table.derived_from", None), system="mips")
        assert tuples(no_lineage) == Q4[:-1]

        answer = ask("q1")
        assert answer["columns"] == ["system", "in_kpi_store", "tables", "replica", "silver", "gold", "by_link"]
        assert tuples(answer) == Q1_WITH_LINKS
        assert tuples(ask("q1", mapping=set_value(mapping, "replaces", None))) == Q1_BY_NAME
        assert tuples(ask("q1", system="mpr")) == [("MPR", True, 2, 1, 1, 1, 0)]

        assert ask("q7")["rows"] == Q7
        assert ask("q7", terms=["sox"])["rows"] == [dict(Q7[0], reasons=["policy SOX financial reporting on the system"])]
        assert ask("q7", terms=["retention"])["rows"] == []        # the policy is on a system no KPI rests on
        assert ask("q7", mapping=set_value(mapping, "policy.applies_to", None))["rows"] == [Q7[1]]

        # A value stays a value: text that would end a string in a formatted query finds nothing and harms nothing.
        assert ask("q4", system="mips' OR 1=1 //")["rows"] == []

        # The server refuses a write in the read transaction every query runs in.
        before = reader.read("USE graph.byName($graph) MATCH (n) RETURN count(n) AS nodes",
                             {"graph": connection.graphs["governance"]})
        with pytest.raises(Exception, match="(?i)read access mode|not allowed"):
            reader.read("CALL () { USE graph.byName($graph) CREATE (n:Written {madeUp: true}) RETURN 1 AS one } "
                        "RETURN one", {"graph": connection.graphs["governance"]})
        assert before == [{"nodes": 25}]      # 1 server, 4 systems, 4 schemas, 8 tables, 2 columns, 1 report, 3 policies, 1 person, 1 role
        assert reader.read("USE graph.byName($graph) MATCH (n) RETURN count(n) AS nodes",
                           {"graph": connection.graphs["governance"]}) == before

        # The command line, end to end, with its files outside the release.
        for key in C.KEYS:
            monkeypatch.delenv("KPI_STORE_NEO4J_" + key.upper(), raising=False)
        settings = tmp_path / "questions.toml"
        settings.write_text(
            f'[neo4j]\nuri = "{connection.uri}"\nuser = "{connection.user}"\npassword = "{connection.password}"\n'
            f'composite = "{connection.composite}"\ngovernance_alias = "governance"\nbpa_alias = "bpa"\n',
            encoding="utf-8", newline="\n")
        shown = io.StringIO()

        def command(*argv):
            return run.main([*argv, "--settings", str(settings), "--mapping", str(tmp_path / "mapping.json")],
                            out=shown)

        assert command("discover") == 0
        assert command("confirm", "--yes") == 0
        assert command("check") == 0
        assert command("ask", "q7", "--param", 'terms=["sox"]', "--out", str(tmp_path / "answers")) == 0
        with (tmp_path / "answers" / "q7.json").open(encoding="utf-8") as f:
            assert json.load(f)["rows"] == [dict(Q7[0], reasons=["policy SOX financial reporting on the system"])]
        assert (tmp_path / "answers" / "q7.csv").read_text(encoding="utf-8").splitlines()[1] == (
            f'crude-prices,Crude Market Pricing,{VIEW},mips,MIPS,"[""policy SOX financial reporting on the system""]"')

        # Drift: the governance graph loses a property a role names, and the next run stops and names the role.
        with driver.session(database=build.MEMBERS["governance"][0]) as session:
            session.run("MATCH (t:Table) REMOVE t.classification").consume()
        with pytest.raises(M.MappingError, match="role table.classification: property classification is no longer "
                                                 "on label Table in the governance graph"):
            ask("q7")
        assert command("check") == 1 and command("ask", "q1", "--out", str(tmp_path / "answers")) == 1
        assert "role table.classification: property classification is no longer on label Table" in shown.getvalue()
        assert not (tmp_path / "answers" / "q1.json").exists()
        assert connection.password not in shown.getvalue()
    finally:
        try:
            build.build(driver)          # leave the fixture as built, for the next run
        finally:
            reader.close()
            driver.close()
