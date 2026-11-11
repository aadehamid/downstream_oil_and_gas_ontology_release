"""The copy to Neo4j Enterprise: one named database, no administration, and a replace that needs a decision and
never deletes anyone else's nodes. The databases are stand-ins."""
import json
from types import SimpleNamespace

import pytest

from kpi_store import copy_enterprise as ce
from kpi_store import load_neo4j as ln
from kpi_store.tests import stores_support, support
from kpi_store.tests.test_load_neo4j import DP, KPI, REPORT, WANT, graph, stub_code

REAL = ln.release_code(support.ROOT)
TARGET = "businessprocessarchitecturegraph"


# ---- the one database ------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["system", "SYSTEM", " System ", "", None])
def test_the_system_database_and_an_empty_name_are_refused(name):
    with pytest.raises(ce.Refused, match="never the system database"):
        ce.checked_name(name)


def test_the_target_is_opened_by_name_and_the_server_must_confirm_it():
    driver = stores_support.FakeDriver({TARGET: stores_support.FakeNeo4j(TARGET)})
    with ce.open_target(driver, TARGET) as session:
        assert session.database == TARGET
    assert driver.opened == [TARGET] and driver.databases[TARGET].closed

    alias = stores_support.FakeDriver({"bpa": stores_support.FakeNeo4j(TARGET)})
    with pytest.raises(ce.Refused, match=f"the server opened the database {TARGET}, not bpa; nothing was read or written"):
        ce.open_target(alias, "bpa")
    assert alias.databases["bpa"].closed and alias.databases["bpa"].statements == ["CALL db.info() YIELD name RETURN name"]

    none = stores_support.FakeDriver({})
    with pytest.raises(ce.Refused):
        ce.open_target(none, "system")
    assert none.opened == []   # refused before any session


@pytest.mark.parametrize("statement", [
    "CREATE DATABASE other", "create database other if not exists", "CREATE OR REPLACE DATABASE other",
    "CREATE COMPOSITE DATABASE both", "DROP DATABASE businessprocessarchitecturegraph", "STOP DATABASE other",
    "ALTER DATABASE other SET ACCESS READ ONLY", "CREATE ALIAS bpa FOR DATABASE other", "DROP ALIAS bpa FOR DATABASE",
    "ALTER USER neo4j SET PASSWORD 'x'", "CREATE ROLE writer", "GRANT ALL ON DATABASE other TO writer",
    "USE otherwork MATCH (n) DETACH DELETE n", "  use otherwork CREATE (:Note)", "DROP CONSTRAINT n10s_unique_uri",
    "DROP INDEX some_index", "TERMINATE TRANSACTIONS 'x'", 12345])
def test_administration_another_database_and_every_drop_are_refused(statement):
    with pytest.raises(ce.Refused, match="was not sent to Enterprise"):
        ce.check_statement(statement)


def test_the_statements_the_copy_sends_pass_the_guard():
    sent = [REAL.cg.NODES, REAL.cg.EDGES, REAL.cg.WRITE_NODES, REAL.cg.WRITE_EDGES,
            "CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE",
            REAL.rr.CLEAR, REAL.rr.WRITE, REAL.rr.READ, REAL.mt.NODES, REAL.mt.EDGES, REAL.mt.CLEAR_MODULES, REAL.mt.MODULES,
            REAL.mt.REQUIRES, REAL.lm.NEO4J_NODES, REAL.lm.NEO4J_EDGES, "CALL db.info() YIELD id RETURN id",
            "MERGE (m:EpmStoreMarker {store: $s}) SET m = $p",
            f"MATCH (n) WHERE {ce.own_predicate()} CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS OF 1000 ROWS"]
    for statement in sent:
        ce.check_statement(statement)
    query = SimpleNamespace(text="MATCH (n:Resource) RETURN count(n) AS n")   # the driver's Query object has .text
    ce.check_statement(query)


def test_a_refused_statement_never_reaches_the_session_or_a_transaction():
    db = stores_support.FakeNeo4j(TARGET)
    class Tx:
        def __init__(self): self.sent = []
        def run(self, query, *a, **k): self.sent.append(query)
        def commit(self): return "committed"
    tx = Tx()
    db.begin_transaction = lambda *a, **k: tx
    session = ce.TargetSession(db, TARGET)
    assert session.run("MATCH (n) RETURN count(n) AS n").single()["n"] == 0
    with pytest.raises(ce.Refused):
        session.run("CREATE DATABASE other")
    guarded = session.begin_transaction()
    guarded.run("MATCH (n:Resource) RETURN count(n) AS n")
    with pytest.raises(ce.Refused):
        guarded.run("DROP DATABASE other")
    with pytest.raises(ce.Refused):
        session.run(SimpleNamespace(text="USE system SHOW DATABASES"))
    assert db.statements == ["MATCH (n) RETURN count(n) AS n"] and tx.sent == ["MATCH (n:Resource) RETURN count(n) AS n"]
    assert guarded.commit() == "committed"


# ---- what the target holds, and the decision -------------------------------------------------------

BASES = ["https://w3id.org/mpc/ontology/modules/data-product/", "https://w3id.org/mpc/ontology/modules/kpi/"]
PARAMS = {"bases": BASES, "store": "enterprise", "prefixes": ["dp_", "n4sch_", "owl_", "skos_"],
          "tech_base": "urn:kpi-store:tech:", "tech_classes": ["MetricView", "Table"]}
TECH = "urn:kpi-store:tech:idp_sbx+synapse_dev:object/"
KPI_TAG = "https://w3id.org/mpc/ontology/modules/kpi/1.0.0"


def held_target(hash_="hash-1"):
    """The target database as an earlier copy left it: the graph, and this copy's own marker."""
    db = graph(hash_=hash_, store="enterprise")
    db.name, db.ident = TARGET, "db-2"
    return db


def test_the_rules_read_the_module_iris_the_store_name_and_the_projections_label_prefixes():
    assert ce.own_params(BASES, ["skos", "owl", "dp"], ["Table", "MetricView"]) == PARAMS


def test_the_technical_graphs_class_names_come_from_its_newest_package():
    newest = ["https://w3id.org/mpc/ontology/modules/kpi/1.3.0", "https://w3id.org/mpc/ontology/modules/technical-graph/1.1.0"]
    assert ce.tech_class_names(support.ROOT, newest) == [
        "Agent", "Builder", "DataObject", "DefinitionsView", "Host", "Job", "MetricView", "Orchestrator", "Pipeline",
        "PipelineStep", "QualityCheck", "SourceDatabase", "Table", "TechnicalObject", "View"]
    assert ce.tech_class_names(support.ROOT, newest[:1]) == []
    with pytest.raises(ce.Refused, match="technical-graph package .* cannot be read"):
        ce.tech_class_names(support.ROOT, ["https://w3id.org/mpc/ontology/modules/technical-graph/9.9.9"])


def test_holdings_tell_the_kpi_stores_nodes_from_the_others():
    db = held_target()
    db.add(["Resource", "skos_Concept", "n4sch_Class"], uri="urn:sample:concept", graph=KPI_TAG)   # a projected node's labels
    db.add(["LogicalModel", "Entity"], 4, uri="urn:sample:entity", models=["sample-model"])
    db.add(["Tech", "Table"], 3, uri=TECH + "idp_sbx.gold_sample.sample_fact", name="idp_sbx.gold_sample.sample_fact")
    db.add(["TechGraphMarker"], store="enterprise", digest="d1", triples=9)
    assert ce.holdings(db, PARAMS) == {"nodes": 17, "own": {"Resource": 6, "ModuleRelease": 2, "EpmStoreMarker": 1, "LogicalModel": 4,
                                                           "Tech": 3, "TechGraphMarker": 1},
                                      "foreign": {}, "foreign_nodes": 0, "foreign_examples": []}
    db.add(["Invoice"], 2)
    db.add(["Invoice", "Paid"])
    db.add([])
    held = ce.holdings(db, PARAMS)
    assert (held["nodes"], held["foreign_nodes"]) == (21, 4)
    assert held["foreign"] == {"Invoice": 3, "Paid": 1, "(no label)": 1}


@pytest.mark.parametrize("labels, props", [
    (["Resource", "Customer"], {"uri": "https://other.example/x"}),                    # a generic label, another graph's IRI
    (["Resource"], {"uri": "https://other.example/y", "graph": "https://other.example/graph/1.0.0"}),   # tagged, by another release
    (["Resource"], {"graph": "https://w3id.org/mpc/ontology/modules/kpi/1.0.0"}),          # no uri
    (["Resource"], {"uri": "https://other.example/z", "graph": ["a", "list"]}),
    (["ModuleRelease"], {"version_iri": "https://other.example/module/1.0.0"}),
    (["Module"], {"uri": "https://other.example/module/1.0.0"}),
    (["EpmStoreMarker"], {"store": "enterprise"}),
    (["LogicalModel"], {"name": "someone else's model"}),
    (["LogicalModelMarker"], {"store": "enterprise"}),
    # A marker of another store, although it has a marker's fields.
    (["EpmStoreMarker"], {"store": "neo4j", "catalog_digest": "abc"}),
    (["LogicalModelMarker"], {"store": "neo4j", "digest": "abc"}),
    # The release's own tag and a uri, on a node with a label the projection never gives.
    (["Resource", "Customer"], {"uri": "urn:external:item", "graph": KPI_TAG}),
    (["Resource", "skos_Concept", "Customer"], {"uri": "urn:external:item", "graph": KPI_TAG}),
    # The technical graph's label on a node that is not of its shape.
    (["Tech", "Table"], {"uri": "https://other.example/table"}),          # not in the technical graph's urn: scheme
    (["Tech", "Customer"], {"uri": TECH + "x"}),                          # a label that is no class of the module
    (["Tech"], {"name": "no uri"}),
    (["TechGraphMarker"], {"store": "neo4j", "digest": "abc"}),            # another store's marker
])
def test_a_node_that_only_shares_a_label_with_the_kpi_store_is_foreign_and_survives_a_replace(labels, props):
    db = held_target()
    db.add(labels, **props)
    db.add(["Account"], id=7)   # the foreign node's neighbour
    held = ce.holdings(db, PARAMS)
    assert held["foreign_nodes"] == 2 and held["own"] == {"Resource": 5, "ModuleRelease": 2, "EpmStoreMarker": 1}
    assert held["foreign_examples"][0].startswith(":".join(labels))
    with pytest.raises(ce.Refused, match=r"holds 2 node\(s\) that are not the KPI Store's"):
        ce.decide(held, TARGET, replace=True)
    ce.remove_own(db, PARAMS)   # even a delete that did run takes the KPI Store's nodes only
    assert db.nodes == [(labels, props), (["Account"], {"id": 7})]


def test_the_limit_of_the_rule_is_pinned():
    # A node with the release's tag, a uri and only projection labels is treated as the KPI Store's, whoever wrote
    # it: the module's text and the refusal say so, and the target database must be the KPI Store's alone.
    db = held_target()
    db.add(["Resource", "skos_Concept"], uri="urn:external:item", graph=KPI_TAG)
    assert ce.holdings(db, PARAMS)["foreign_nodes"] == 0
    assert "the target database is dedicated" in " ".join(ce.__doc__.split())
    with pytest.raises(ce.Refused, match="so the database must be the KPI Store's alone"):
        ce.decide(ce.holdings(db, PARAMS), TARGET)


def test_the_check_and_the_delete_use_one_rule():
    rule = ce.own_predicate()
    assert rule.startswith("coalesce((n:Resource AND n.uri IS NOT NULL AND any(b IN $bases WHERE toStringOrNull(n.graph) STARTS WITH b) "
                           "AND all(l IN labels(n) WHERE l = 'Resource' OR any(p IN $prefixes WHERE l STARTS WITH p)))")
    assert "(n:EpmStoreMarker AND n.store = $store AND n.catalog_digest IS NOT NULL)" in rule
    assert "(n:LogicalModelMarker AND n.store = $store AND n.digest IS NOT NULL)" in rule
    db = held_target()
    ce.holdings(db, PARAMS)
    ce.remove_own(db, PARAMS)
    assert all(rule in statement for statement in db.statements) and len(db.statements) == 2
    assert "MATCH (n) WHERE " + rule + " CALL (n) { DETACH DELETE n }" in db.statements[1]
    assert not any(statement.startswith("MATCH (n) CALL") or "MATCH (n) DETACH" in statement for statement in db.statements)


def test_the_replace_needs_a_decision_and_foreign_nodes_always_stop_it():
    empty = {"nodes": 0, "own": {}, "foreign": {}, "foreign_nodes": 0, "foreign_examples": []}
    own = {"nodes": 7, "own": {"Resource": 5, "ModuleRelease": 2}, "foreign": {}, "foreign_nodes": 0, "foreign_examples": []}
    mixed = {"nodes": 9, "own": {"Resource": 5}, "foreign": {"Invoice": 3, "Note": 1}, "foreign_nodes": 4,
             "foreign_examples": ["Invoice", "Note"]}
    assert ce.decide(empty, TARGET) == "empty"
    with pytest.raises(ce.Refused, match=r"holds 7 node\(s\) that carry the KPI Store's own marks \(its release tags, release records, "
                                         r"logical models and markers\), by label: 2 ModuleRelease, 5 Resource. Nothing was changed"):
        ce.decide(own, TARGET)
    assert ce.decide(own, TARGET, replace=True) == "replace"
    asked = []
    assert ce.decide(own, TARGET, confirm=lambda text: asked.append(text) or TARGET + "\n") == "replace"
    assert "2 ModuleRelease, 5 Resource" in asked[0]
    with pytest.raises(ce.Refused, match="Nothing was changed"):
        ce.decide(own, TARGET, confirm=lambda text: "yes")
    for options in ({}, {"replace": True}, {"confirm": lambda text: TARGET}):
        with pytest.raises(ce.Refused, match=r"holds 4 node\(s\) that are not the KPI Store's, by label: 3 Invoice, 1 Note; for example Invoice, Note. Nothing was changed"):
            ce.decide(mixed, TARGET, **options)


def test_the_replace_deletes_the_kpi_stores_nodes_and_leaves_other_nodes():
    db = held_target()
    db.add(["Invoice"], 3)
    ce.remove_own(db, PARAMS)
    assert db.nodes == [(["Invoice"], {})] * 3 and len(db.statements) == 1


# ---- the checks after the copy ---------------------------------------------------------------------

def test_release_records_that_do_not_write_or_read_back_stop_the_copy(tmp_path):
    (tmp_path / "release-records.json").write_text(json.dumps({"graph_hash": "hash-1", "records": [{}, {}]}), encoding="utf-8")
    good = SimpleNamespace(rr=SimpleNamespace(write=lambda s, c: ([], 2), check=lambda s, c: []))
    assert ce.write_records(None, tmp_path, good) == 2
    for rr, message in ((SimpleNamespace(write=lambda s, c: (["1 of 2 records found their owl:Ontology node"], 1), check=lambda s, c: []), "1 of 2 records"),
                        (SimpleNamespace(write=lambda s, c: ([], 2), check=lambda s, c: ["no record of kpi"]), "no record of kpi")):
        with pytest.raises(ce.Refused, match=message):
            ce.write_records(None, tmp_path, SimpleNamespace(rr=rr))
    with pytest.raises(ce.Refused, match="there is no release-records.json"):
        ce.write_records(None, tmp_path / "empty", good)


def test_a_tag_that_differs_stops_the_copy_before_the_module_graph(tmp_path, local_and_out):
    local, out = local_and_out
    (out / "run-manifest.json").write_text(json.dumps({"data": [{"path": "a.ttl"}]}), encoding="utf-8")
    (out / "inferred.nt").write_text("", encoding="utf-8")
    sent = []
    target = SimpleNamespace(run=lambda statement, params: sent.append(statement) or SimpleNamespace(data=lambda: []))
    def code(problems):
        mt = SimpleNamespace(read_packages=lambda paths: ["package"] if paths == ["a.ttl"] else pytest.fail("the manifest's files"),
                             expected_tags=lambda packages, inferred: ({}, {}), check=lambda run, nodes, edges, prefixes, sep: (0, 0, problems),
                             module_rows=lambda packages: ([{"uri": DP}, {"uri": KPI}], []),
                             CLEAR_MODULES="clear", MODULES="modules", REQUIRES="requires")
        return SimpleNamespace(mt=mt, build=REAL.build)
    cfg = ln.run_config(support.ROOT, local, "")
    with pytest.raises(ce.Refused, match=r"release tags differ from the packages' \(untagged nodes\); no marker was written"):
        ce.check_tags(target, out, cfg, code({"untagged nodes": ["urn:sample:n"], "wrong tags": []}))
    assert sent == []
    assert ce.check_tags(target, out, cfg, code({"untagged nodes": []})) == 2 and sent == ["clear", "modules", "requires"]


# ---- the copy --------------------------------------------------------------------------------------

@pytest.fixture
def local_and_out(tmp_path, monkeypatch):
    monkeypatch.setattr(ce.ldb, "expected", lambda root, ss=None: dict(WANT))
    out = tmp_path / "lpg-out"
    out.mkdir()
    (out / "projection-report.json").write_text(json.dumps(REPORT), encoding="utf-8")
    return stores_support.local_settings(tmp_path), out


def copy_code(order):
    code = stub_code([])
    def copy(source, target, size):
        order.append("copy")
        inner = getattr(target, "_inner", target)
        inner.nodes += [n for n in source.nodes if "Resource" in n[0]]
        inner.relationships, inner.graph_hash = source.relationships, source.graph_hash
        return {"nodes": 5, "relationships": 7}
    code.lv.Timed = lambda session, seconds: session
    code.cg = SimpleNamespace(database_identity=lambda s: s.run("CALL db.info() YIELD id RETURN id").single()["id"],
                              graph_hash=lambda s: s.graph_hash, copy=copy)
    return code


def run_copy(local, source, target, monkeypatch, order=None, **options):
    order = [] if order is None else order
    def records(session, out, code):
        order.append("records")
        getattr(session, "_inner", session).nodes += [(["ModuleRelease"], {"version_iri": v}) for v in (DP, KPI)]
        return 2
    monkeypatch.setattr(ce, "write_records", records)
    monkeypatch.setattr(ce, "check_tags", lambda *a: order.append("tags") or 2)
    drivers = {"bolt://127.0.0.1:7687": stores_support.FakeDriver({"neo4j": source}),
               local.neo4j_enterprise.uri: stores_support.FakeDriver({TARGET: target, "otherwork": stores_support.FakeNeo4j("otherwork")})}
    result = ce.copy(local, support.ROOT, code=copy_code(order), connect=lambda neo4j: drivers[neo4j.uri], **options)
    return result, drivers[local.neo4j_enterprise.uri], order


def empty_target():
    db = stores_support.FakeNeo4j(TARGET, ident="db-2")
    db.graph_hash = "hash-of-nothing"
    return db


def test_the_copy_writes_to_the_named_database_only_and_marks_it_last(local_and_out, monkeypatch):
    local, _ = local_and_out
    target = empty_target()
    result, driver, order = run_copy(local, graph(), target, monkeypatch)
    assert driver.opened == [TARGET] and driver.databases["otherwork"].statements == []
    assert order == ["copy", "records", "tags"] and target.statements[-1] == "MERGE (m:EpmStoreMarker {store: $s}) SET m = $p"
    assert (result["status"], result["replaced"], result["nodes"], result["relationships"]) == ("copied", False, 5, 7)
    assert result["graph_hash"] == "hash-1" and result["marker"]["store"] == "enterprise" and result["marker"]["count"] == [5, 7]
    assert ce.line(result) == (f"neo4j (enterprise, database {TARGET}): copied, 5 nodes, 7 relationships, graph hash hash-1 "
                               "equal to the local graph's")
    again, _, order = run_copy(local, graph(), target, monkeypatch)
    assert again["status"] == "current" and order == []   # the second run copies nothing


def test_the_copy_is_refused_before_any_write(local_and_out, monkeypatch):
    local, out = local_and_out
    same = empty_target()
    same.ident = "db-1"
    with pytest.raises(ce.Refused, match="the target is the local database itself"):
        run_copy(local, graph(), same, monkeypatch)
    moved, target = graph(hash_="hash-2"), empty_target()
    with pytest.raises(ce.Refused, match="the local graph is not the graph the load report verified"):
        run_copy(local, moved, target, monkeypatch)
    foreign = empty_target()
    foreign.add(["Invoice"], 3)
    with pytest.raises(ce.Refused, match=r"3 node\(s\) that are not the KPI Store's, by label: 3 Invoice"):
        run_copy(local, graph(), foreign, monkeypatch, replace=True)
    shared = held_target("hash-0")   # the KPI Store's old graph, and one node of someone else's that is also labelled Resource
    shared.add(["Resource", "Customer"], uri="https://other.example/x")
    with pytest.raises(ce.Refused, match=r"1 node\(s\) that are not the KPI Store's, by label: 1 Customer, 1 Resource; "
                                         r"for example Resource:Customer https://other.example/x"):
        run_copy(local, graph(), shared, monkeypatch, replace=True)
    assert shared.count("Resource") == 6 and shared.writes() == []
    held = held_target("hash-0")
    with pytest.raises(ce.Refused, match="Run the command again with --replace"):
        run_copy(local, graph(), held, monkeypatch)
    for db in (same, target, foreign, held):
        assert db.writes() == []
    (out / "projection-report.json").write_text(json.dumps({**REPORT, "input_fingerprint": "fingerprint-0"}), encoding="utf-8")
    with pytest.raises(ce.Refused, match="is of other release files"):
        run_copy(local, graph(), empty_target(), monkeypatch)


def test_a_decided_replace_removes_the_old_graph_first(local_and_out, monkeypatch):
    local, _ = local_and_out
    held = held_target("hash-0")
    result, _, order = run_copy(local, graph(), held, monkeypatch, replace=True)
    assert result["status"] == "copied" and result["replaced"] is True and result["held_before"]["own"]["Resource"] == 5
    assert held.count("Resource") == 5 and held.count("EpmStoreMarker") == 1
    first_write = held.writes()[0]
    assert first_write.startswith("MATCH (n) WHERE coalesce((n:Resource AND ") and "DETACH DELETE n" in first_write


def test_a_copy_whose_hash_differs_writes_no_marker(local_and_out, monkeypatch):
    local, _ = local_and_out
    target = empty_target()
    code = copy_code([])
    code.cg.copy = lambda source, target, size: {"nodes": 5, "relationships": 7}   # copies nothing
    drivers = {"bolt://127.0.0.1:7687": stores_support.FakeDriver({"neo4j": graph()}),
               local.neo4j_enterprise.uri: stores_support.FakeDriver({TARGET: target})}
    with pytest.raises(ce.Refused, match="the copy's graph hash hash-of-nothing differs from the local graph's hash-1; no marker was written"):
        ce.copy(local, support.ROOT, code=code, connect=lambda neo4j: drivers[neo4j.uri])
    assert target.count("EpmStoreMarker") == 0


def test_the_command_refuses_bad_settings_before_anything_else(tmp_path, capsys):
    assert ce.main(["--stores", str(tmp_path / "missing.toml")]) == 2
    assert "cannot read the local settings file" in capsys.readouterr().err
