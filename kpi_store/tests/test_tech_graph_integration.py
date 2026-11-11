"""The technical graph loaded into a real Neo4j and a real Fuseki.

Each test needs a test server and skips without one. Name the servers in the environment:

    KPI_STORE_TEST_TECH_NEO4J_URI=bolt://127.0.0.1:17831
    KPI_STORE_TEST_TECH_NEO4J_PASSWORD=<the test server's password>
    KPI_STORE_TEST_TECH_NEO4J_USER=neo4j            (optional)
    KPI_STORE_TEST_TECH_NEO4J_DATABASE=neo4j        (optional)
    KPI_STORE_TEST_TECH_FUSEKI_QUERY=http://127.0.0.1:17833/tech/query

The Neo4j test replaces the technical graph and its own made-up ontology nodes, and it refuses a database that
holds any other node. The Fuseki test writes only the technical graph's named graph and one made-up graph. The
Neo4j server needs no plugin: every statement is plain Cypher.

Every expected figure is written by hand from support.sandbox(), as in test_tech_graph.py.
"""
import importlib.util
import os
import urllib.parse
import urllib.request

import pytest

from kpi_store import discovery as disc
from kpi_store import ontology_view as ov
from kpi_store import tech_graph as tg
from kpi_store.questions import roles as R
from kpi_store.tests import support

ENV = "urn:kpi-store:tech:idp_sbx+synapse_dev:"
OBJECT = ENV + "object/"
GRAPH = ENV + "graph"
LAYER = "https://w3id.org/mpc/ontology/modules/data-product/layer/"
OTHER_GRAPH = "urn:made-up:another-load"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """(graph files, OntologyView, the built graph) from the sandbox-shaped workspace."""
    workspace, genie = support.sandbox()
    settings = support.make_settings()
    view = ov.read(support.ROOT)
    schemas = {settings.environment_name(o.full_name).rsplit(".", 1)[0] for o in view.objects.values()}
    graph = tg.build(disc.discover(settings, workspace.run_sql, genie, schemas), view, settings)
    return tg.write(graph, tmp_path_factory.mktemp("run")), view, graph


# ---- Neo4j ---------------------------------------------------------------------------------------------

@pytest.fixture()
def session():
    uri, password = os.environ.get("KPI_STORE_TEST_TECH_NEO4J_URI"), os.environ.get("KPI_STORE_TEST_TECH_NEO4J_PASSWORD")
    if not uri or not password:
        pytest.skip("no test Neo4j: set KPI_STORE_TEST_TECH_NEO4J_URI and KPI_STORE_TEST_TECH_NEO4J_PASSWORD")
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(uri, auth=(os.environ.get("KPI_STORE_TEST_TECH_NEO4J_USER", "neo4j"), password))
    with driver, driver.session(database=os.environ.get("KPI_STORE_TEST_TECH_NEO4J_DATABASE")) as s:
        strangers = s.run("MATCH (n) WHERE NOT n:Tech AND NOT n:TechGraphMarker AND coalesce(n.madeUp, false) <> true "
                          "RETURN count(n) AS n").single()["n"]
        if strangers:
            pytest.skip(f"the test Neo4j holds {strangers} node(s) this test did not make; it is not touched")
        s.run("MATCH (n) DETACH DELETE n").consume()
        yield s
        s.run("MATCH (n) DETACH DELETE n").consume()


def made_up_ontology(session, view):
    """The ontology nodes the technical graph links to, as the projection names them: the 33 platform tables, each
    with its layer, and the 5 measures."""
    session.run("UNWIND $codes AS code CREATE (:Resource:skos_Concept {uri: $base + code, skos_notation: code, madeUp: true})",
                codes=["replica", "silver", "gold", "metric-view"], base=LAYER).consume()
    session.run("UNWIND $rows AS row MATCH (l:skos_Concept {uri: $base + row.layer}) "
                "CREATE (:Resource:dp_PlatformTable {uri: row.uri, dp_fullName: row.name, madeUp: true})-[:dp_layer]->(l)",
                rows=[{"uri": o.iri, "name": o.full_name, "layer": o.layer} for o in view.objects.values()], base=LAYER).consume()
    session.run("UNWIND $uris AS uri CREATE (:Resource:kpi_MeasureDefinition {uri: uri, madeUp: true})",
                uris=sorted(m.iri for m in view.measures.values())).consume()


def count(session, query, **params):
    return session.run(query, **params).single()["n"]


def test_the_neo4j_load(session, built):
    files, view, graph = built
    made_up_ontology(session, view)
    assert count(session, "MATCH (n:Resource) RETURN count(n) AS n") == 42          # 33 tables, 4 layers, 5 measures
    assert tg.status_neo4j(session, files)[0] == "unmarked"

    loaded = tg.load_neo4j(session, files, now=None)
    assert loaded["status"] == "loaded"
    assert (loaded["nodes"], loaded["tech_edges"], loaded["ontology_edges"]) == (53, 73, 39)
    assert (loaded["ontology_nodes"], loaded["ontology_relationships"]) == (42, 33)   # the ontology did not move
    assert count(session, "MATCH (n:Tech) RETURN count(n) AS n") == 53
    assert count(session, "MATCH (n:Tech:Resource) RETURN count(n) AS n") == 0
    assert count(session, "MATCH (n:Resource) RETURN count(n) AS n") == 42
    labels = {r["label"]: r["n"] for r in session.run(
        "MATCH (n:Tech) UNWIND labels(n) AS label WITH label, count(*) AS n WHERE label <> 'Tech' RETURN label, n")}
    assert labels == {"Table": 44, "MetricView": 3, "View": 2, "Job": 1, "Pipeline": 1, "Agent": 2}
    kinds = {r["t"]: r["n"] for r in session.run("MATCH (:Tech)-[r]->() RETURN type(r) AS t, count(*) AS n")}
    assert kinds == {"READS_FROM": 52, "BUILT_BY": 10, "BINDS": 3, "REPLACES": 8, "DESIGNED_AS": 33, "IMPLEMENTS": 6}
    marker = session.run("MATCH (m:TechGraphMarker) RETURN properties(m) AS p").single()["p"]
    assert marker["digest"] == tg.digest(files) and marker["triples"] == 269 and marker["nodes"] == 53
    assert tg.status_neo4j(session, files)[0] == "current"

    # The questions' default names find the graph: a Databricks table, the Synapse table it replaces, and the
    # layer of its design.
    tech, name = R.role("tech.object").candidates[0], R.role("tech.name").candidates[0]
    replaces, designed = R.role("replaces").candidates[0], R.role("tech.designed_as").candidates[0]
    table, in_layer = R.role("platform_table.node").candidates[0], R.role("platform_table.in_layer").candidates[0]
    layer, code = R.role("layer.node").candidates[0], R.role("layer.code").candidates[0]
    assert (tech, name, replaces, designed) == ("Tech", "name", "REPLACES", "DESIGNED_AS")
    links = sorted((r["key"], r["layer"]) for r in session.run(
        f"MATCH (new:{tech})-[:{replaces}]->(old:{tech}), (new)-[:{designed}]->(:{table})-[:{in_layer}]->(l:{layer}) "
        f"WITH split(toLower(old.{name}), '.') AS parts, l.{code} AS layer "
        "RETURN parts[-2] + '.' + parts[-1] AS key, layer"))
    assert links == [("commercial_core.mips_mpr_executive_summary_fact", "gold"),
                     ("mdm_core.mips_price_assessment_group_dim", "silver"), ("mdm_core.mips_price_batch_dim", "silver"),
                     ("mdm_core.mips_price_group_dim", "silver"), ("mdm_core.mips_price_sheet_dim", "silver"),
                     ("mdm_core.mpr_price_master_dim", "silver"), ("udm_core.mips_price_assessment_fact", "silver"),
                     ("udm_core.mpr_price_detail_fact", "silver")]

    # A second load of the same files writes nothing: the marker keeps its time.
    again = tg.load_neo4j(session, files)
    assert again["status"] == "current"
    assert session.run("MATCH (m:TechGraphMarker) RETURN m.marked_at AS t").single()["t"] == marker["marked_at"]

    # A hand edit reads as changed, and a load repairs it.
    session.run("MATCH (:Tech {uri: $s})-[r:REPLACES]->() DELETE r", s=OBJECT + "idp_sbx.silver_mdm_core.mips_price_batch_dim").consume()
    assert tg.status_neo4j(session, files)[0] == "changed"
    assert tg.load_neo4j(session, files)["status"] == "loaded"
    assert tg.status_neo4j(session, files)[0] == "current"

    # An edit that moves no count reads as changed too: one name, then every node gone with the marker left.
    session.run("MATCH (j:Tech:Job) SET j.name = 'Sample_Tampered_Pipeline'").consume()
    assert count(session, "MATCH (n:Tech) RETURN count(n) AS n") == 53
    assert tg.status_neo4j(session, files)[0] == "changed"
    assert tg.load_neo4j(session, files)["status"] == "loaded" and tg.status_neo4j(session, files)[0] == "current"
    session.run("MATCH (n:Tech) DETACH DELETE n").consume()
    assert tg.read_neo4j(session)["digest"] == tg.digest(files)
    assert tg.status_neo4j(session, files)[0] == "changed"
    assert tg.load_neo4j(session, files)["status"] == "loaded" and tg.status_neo4j(session, files)[0] == "current"

    # Other graph files read as behind until they are loaded.
    newer = files[0].parent / "newer" / "tech-graph.nq"
    newer.parent.mkdir()
    newer.write_text(graph.nquads().replace("Sample_Master_Pipeline", "Sample_Renamed_Pipeline"), encoding="utf-8", newline="\n")
    assert tg.status_neo4j(session, [newer])[0] == "behind"
    assert tg.load_neo4j(session, [newer])["status"] == "loaded"
    assert session.run("MATCH (j:Tech:Job) RETURN j.name AS name").single()["name"] == "Sample_Renamed_Pipeline"
    assert tg.status_neo4j(session, [newer])[0] == "current" and tg.status_neo4j(session, files)[0] == "behind"

    # A link whose design the ontology does not hold stops the load, and the database keeps what it had.
    session.run("MATCH (t:dp_PlatformTable {dp_fullName: 'idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact'}) DETACH DELETE t").consume()
    with pytest.raises(SystemExit, match="1 ontology edges found no target"):
        tg.load_neo4j(session, files)
    assert session.run("MATCH (j:Tech:Job) RETURN j.name AS name").single()["name"] == "Sample_Renamed_Pipeline"
    assert count(session, "MATCH (n:Tech) RETURN count(n) AS n") == 53


# ---- Fuseki --------------------------------------------------------------------------------------------

@pytest.fixture()
def query_url():
    url = os.environ.get("KPI_STORE_TEST_TECH_FUSEKI_QUERY")
    if not url:
        pytest.skip("no test Fuseki: set KPI_STORE_TEST_TECH_FUSEKI_QUERY")
    update(url, f"DROP SILENT GRAPH <{GRAPH}> ; DROP SILENT GRAPH <{OTHER_GRAPH}>")
    yield url
    update(url, f"DROP SILENT GRAPH <{GRAPH}> ; DROP SILENT GRAPH <{OTHER_GRAPH}>")


def update(query_url, text):
    request = urllib.request.Request(query_url.rsplit("/", 1)[0] + "/update", data=text.encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/sparql-update"})
    urllib.request.urlopen(request, timeout=60).close()


def sync_stores():
    path = support.ROOT / "business_architecture" / "ontology" / "projection" / "sync_stores.py"
    spec = importlib.util.spec_from_file_location("tech_graph_test_sync_stores", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_jena_load(query_url, built):
    files, _, _ = built
    ss = sync_stores()
    update(query_url, f"INSERT DATA {{ GRAPH <{OTHER_GRAPH}> {{ <urn:made-up:s> <urn:made-up:p> <urn:made-up:o> }} }}")
    assert tg.status_jena(query_url, files) == ("behind", f"1 technical-graph graph(s) missing, e.g. {GRAPH}")

    loaded = tg.load_jena(files, query_url)
    assert loaded["status"] == "loaded" and loaded["graphs"] == {GRAPH: 269}
    held = ss.read_jena(query_url)
    assert held == {GRAPH: 269, OTHER_GRAPH: 1}                 # the other load's graph is untouched
    assert tg.status_jena(query_url, files) == ("current", "1 graph(s), 269 triples, equal to the graph files by hash")
    # The ontology's own check leaves the technical graph out when it is told the graph's name.
    assert ss.judge_jena(held, {OTHER_GRAPH: 1}, apart=tg.jena_apart(files))[0] == "current"
    assert ss.judge_jena(held, {OTHER_GRAPH: 1})[0] == "behind"

    assert tg.load_jena(files, query_url)["status"] == "current"

    # A triple removed by hand reads as changed, and a load repairs it.
    old = OBJECT + "synapse_dev.mdm_core.mips_price_batch_dim"
    update(query_url, f"DELETE WHERE {{ GRAPH <{GRAPH}> {{ ?new <{tg.TG}replaces> <{old}> }} }}")
    assert tg.status_jena(query_url, files)[0] == "changed"
    assert tg.load_jena(files, query_url)["status"] == "loaded"

    # One object edited by hand: the graph still holds 269 triples, and it reads as changed.
    job = ENV + "builder/job-9001"
    update(query_url, f'DELETE DATA {{ GRAPH <{GRAPH}> {{ <{job}> <{tg.TG}name> "Sample_Master_Pipeline" }} }} ; '
                      f'INSERT DATA {{ GRAPH <{GRAPH}> {{ <{job}> <{tg.TG}name> "Sample_Tampered_Pipeline" }} }}')
    assert ss.read_jena(query_url)[GRAPH] == 269
    assert tg.status_jena(query_url, files) == (
        "changed", "its technical graph holds 269 triples that are not the graph files' 269: load it again")
    assert tg.load_jena(files, query_url)["status"] == "loaded" and tg.status_jena(query_url, files)[0] == "current"

    # The graph dropped: behind, with nothing held.
    update(query_url, f"DROP GRAPH <{GRAPH}>")
    assert tg.status_jena(query_url, files)[0] == "behind"
    assert tg.load_jena(files, query_url)["status"] == "loaded"
    assert ss.read_jena(query_url) == {GRAPH: 269, OTHER_GRAPH: 1}

    # The questions the module adds run on the loaded graph: what each table replaces.
    query = (support.ROOT / "business_architecture" / "ontology" / "regression" / "queries" / "q56-replaces.rq").read_text(encoding="utf-8")
    scoped = query.replace("WHERE {", f"WHERE {{ GRAPH <{GRAPH}> {{", 1).rstrip().rstrip("}") + "} }"
    found = ss.jena_select(query_url, scoped)
    assert len(found) == 8
    assert {"idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact": "synapse_dev.commercial_core.mips_mpr_executive_summary_fact"}.items() \
        <= {r["name"]["value"]: r["replacedName"]["value"] for r in found}.items()
