"""The sync check: each store read through a stand-in, judged current after a load and not current after a change."""
import json
from types import SimpleNamespace

import pytest

from kpi_store import load_databricks as ldb
from kpi_store import load_neo4j as ln
from kpi_store import sync_check as sc
from kpi_store.tests import stores_support, support
from kpi_store.tests.test_load_neo4j import DP, KPI, graph

REAL = ln.release_code(support.ROOT)
TARGET = "businessprocessarchitecturegraph"
GRAPHS = {DP: 3, KPI: 1}
WANT = {"catalog_datasets": 2, "catalog_digest": "digest-1", "input_fingerprint": "fingerprint-1", "newest": [DP, KPI],
        "jena_graphs": GRAPHS, "jena_apart": ()}
MARKER = {"catalog_datasets": 2, "catalog_digest": "digest-1", "input_fingerprint": "fingerprint-1", "count": [4],
          "marked_at": "2026-11-10T08:00:00Z", "commit": "KPI Store 1.1", "store": "databricks"}
TRIPLES, MARKERS = "idp_sbx.kpi_store.epm_triples", "idp_sbx.kpi_store.epm_store_markers"


# ---- the SDK's statement execution -----------------------------------------------------------------

def response(state, rows=None, columns=("graph", "n"), statement_id="st-1", following=None):
    return SimpleNamespace(statement_id=statement_id, status=SimpleNamespace(state=SimpleNamespace(value=state)),
                           manifest=SimpleNamespace(schema=SimpleNamespace(columns=[SimpleNamespace(name=c) for c in columns])),
                           result=SimpleNamespace(data_array=rows, next_chunk_index=following))


class Client:
    def __init__(self, first, later=(), chunks=None):
        self.first, self.later, self.chunks, self.calls = first, list(later), chunks or {}, []
        self.statement_execution = self

    def execute_statement(self, **options):
        self.calls.append(("execute", options))
        return self.first

    def get_statement(self, statement_id):
        self.calls.append(("get", statement_id))
        return self.later.pop(0)

    def get_statement_result_chunk_n(self, statement_id, index):
        self.calls.append(("chunk", statement_id, index))
        return self.chunks[index]


def test_a_statement_runs_on_the_named_warehouse_and_returns_row_dicts():
    client = Client(response("SUCCEEDED", [[DP, "3"], [None, "1"]]))
    rows = sc.statement_runner(client, "wh123")("SELECT 1")
    assert rows == [{"graph": DP, "n": "3"}, {"graph": None, "n": "1"}]
    assert client.calls == [("execute", {"statement": "SELECT 1", "warehouse_id": "wh123", "wait_timeout": "30s"})]


def test_a_slow_statement_is_polled_and_a_long_result_is_read_in_chunks():
    client = Client(response("PENDING"), [response("RUNNING"), response("SUCCEEDED", [["a", "1"]], following=1)],
                    chunks={1: SimpleNamespace(data_array=[["b", "2"]], next_chunk_index=None)})
    rows = sc.statement_runner(client, "wh123", sleep=lambda s: None)("SELECT 1")
    assert rows == [{"graph": "a", "n": "1"}, {"graph": "b", "n": "2"}]
    assert [c[0] for c in client.calls] == ["execute", "get", "get", "chunk"]


def test_a_statement_that_fails_or_never_ends_raises():
    with pytest.raises(RuntimeError, match="the statement ended as FAILED"):
        sc.statement_runner(Client(response("FAILED")), "wh123")("SELECT 1")
    forever = Client(response("PENDING"), [response("RUNNING")] * 5)
    with pytest.raises(RuntimeError, match="did not finish within 4 seconds"):
        sc.statement_runner(forever, "wh123", wait_seconds=4, sleep=lambda s: None)("SELECT 1")


# ---- Databricks --------------------------------------------------------------------------------------

def workspace(marker=MARKER, graphs=GRAPHS, tables=("epm_triples", "epm_store_markers")):
    sent = []
    def run_sql(statement):
        sent.append(" ".join(statement.split()))
        if "system.information_schema.tables" in statement:
            return [{"table_name": t} for t in tables]
        if statement.startswith("SELECT marker"):
            return [{"marker": json.dumps(marker)}] if marker else []
        if statement.startswith("SELECT graph, count(*)"):
            return [{"graph": g, "n": str(n)} for g, n in graphs.items()]   # the API returns counts as text
        raise AssertionError(statement)
    return run_sql, sent


def test_databricks_is_read_through_the_gate_with_three_statements():
    run_sql, sent = workspace()
    marker, total, held = sc.read_databricks(support.make_settings(), run_sql, REAL.ss)
    assert (marker["count"], total, held) == ([4], [4], {DP: 3, KPI: 1})
    assert sent[1:] == [f"SELECT marker FROM {MARKERS} WHERE store = 'databricks'",
                        f"SELECT graph, count(*) AS n FROM {TRIPLES} GROUP BY graph"]
    assert "lower(table_schema) = 'kpi_store'" in sent[0]


def test_a_workspace_with_no_marker_table_reads_as_unmarked():
    run_sql, sent = workspace(tables=())
    assert sc.read_databricks(support.make_settings(), run_sql, REAL.ss) == (None, [0], {})
    assert len(sent) == 1   # nothing is read from a table that is not there


def test_a_statement_outside_the_kpi_stores_schemas_is_refused():
    with pytest.raises(ldb.GateRefusal):
        ldb.Gate(support.make_settings(), lambda s: pytest.fail("not sent")).run("SELECT * FROM other_catalog.s.t")


# ---- what a current store holds --------------------------------------------------------------------

def test_expected_reads_the_folder_and_orders_a_correction_version(tmp_path):
    root = support.small_release(tmp_path / "release", versions=("1.0.0", "1.0.1-correction.1"))
    ss = ldb.import_sync_stores(root)
    want = sc.expected(root, ss, "worktree", ("urn:sample:tech-graph",))
    correction = DP[:-len("1.0.0")] + "1.0.1-correction.1"
    assert (want["catalog_datasets"], want["newest"], want["input_fingerprint"]) == (3, [correction, KPI], "sample-fingerprint")
    assert want["jena_graphs"] == {correction: 22, correction + "/shapes": 1, correction + "/catalog": 1, correction + "/sample-model": 1,
                                   KPI: 5, KPI + "/shapes": 1, KPI + "/catalog": 1}
    assert want["jena_apart"] == ("urn:sample:tech-graph",)


# ---- reading and judging the four stores -----------------------------------------------------------

def stores(tmp_path, monkeypatch, jena=GRAPHS, databricks=None, local=None, enterprise=None, warehouse="wh123", connect=None,
           quick=False):
    """check()'s rows with every store a stand-in. Each argument is what that store holds."""
    monkeypatch.setattr(sc, "expected", lambda root, ss, ref="worktree", extra=(): dict(WANT))
    local_settings = stores_support.local_settings(tmp_path)
    (tmp_path / "kpi_store.toml").write_text(support.SETTINGS_TEXT.replace('warehouse_id = ""', f'warehouse_id = "{warehouse}"'), encoding="utf-8")
    ss = SimpleNamespace(**{k: getattr(REAL.ss, k) for k in dir(REAL.ss) if not k.startswith("__")})
    def read_jena(url):
        assert url == "http://127.0.0.1:3030/ds/query"
        if isinstance(jena, Exception):
            raise jena
        return dict(jena)
    ss.read_jena = read_jena
    code = SimpleNamespace(ss=ss, lm=SimpleNamespace(models=lambda newest: []),
                           lv=SimpleNamespace(hash_graph=lambda session: (session.graph_hash, 0, 0, 0)))
    run_sql, sent = databricks or workspace()
    monkeypatch.setattr(sc, "statement_runner", lambda client, warehouse_id: run_sql if (client, warehouse_id) == ("client of DEFAULT", "wh123") else None)
    target = enterprise or marked_target()
    drivers = {"bolt://127.0.0.1:7687": stores_support.FakeDriver({"neo4j": local or graph()}),
               local_settings.neo4j_enterprise.uri: stores_support.FakeDriver({TARGET: target})}
    rows = sc.check(local_settings, support.ROOT, code=code, connect=connect or (lambda neo4j: drivers[neo4j.uri]),
                    client_for=lambda profile: f"client of {profile}", quick=quick)
    return {store: (status, why) for store, status, why in rows}, drivers


def marked_target():
    db = graph(marked=False)
    db.name = TARGET
    db.add(["EpmStoreMarker"], store="enterprise", catalog_datasets=2, catalog_digest="digest-1",
           input_fingerprint="fingerprint-1", count=[5, 7], marked_at="2026-11-10T09:00:00Z", commit="KPI Store 1.1",
           graph_hash="hash-1")
    return db


def test_after_a_load_every_store_reads_current(tmp_path, monkeypatch):
    rows, drivers = stores(tmp_path, monkeypatch)
    assert {store: status for store, (status, _) in rows.items()} == {
        "databricks": "current", "jena": "current", "neo4j": "current", "enterprise": "current"}
    assert rows["jena"][1] == "2 graphs, 4 triples, each equal to the release files"
    assert rows["databricks"][1] == "marked 2026-11-10T08:00:00Z at commit KPI Store 1.1"
    assert list(drivers.values())[1].opened == [TARGET]   # Enterprise is read in the named database
    for driver in drivers.values():
        for db in driver.databases.values():
            assert db.writes() == []   # the check only reads
    assert sc.all_current([(s, *row) for s, row in rows.items()])


def test_after_a_deliberate_change_each_store_reads_not_current(tmp_path, monkeypatch):
    fewer = marked_target()
    fewer.nodes.pop(0)                                    # one node deleted in the target
    rows, _ = stores(tmp_path, monkeypatch, jena={DP: 3},  # one graph dropped in Fuseki
                     databricks=workspace(graphs={DP: 2, KPI: 1}), enterprise=fewer)
    assert rows["jena"] == ("behind", "1 graph(s) of the newest releases missing and 0 other(s) held")
    assert rows["enterprise"] == ("changed", "marked with [5, 7], now holds [4, 7]")
    assert rows["databricks"][0] == "changed" and f"e.g. {DP}: 2, not 3" in rows["databricks"][1]
    assert rows["neo4j"][0] == "current"
    assert not sc.all_current([(s, *row) for s, row in rows.items()])


def test_a_store_loaded_from_another_release_reads_behind_and_one_never_marked_unmarked(tmp_path, monkeypatch):
    old = graph()
    old.nodes[-1][1]["catalog_digest"] = "digest-0"
    rows, _ = stores(tmp_path, monkeypatch, local=old, enterprise=graph(marked=False) and renamed(graph(marked=False)),
                     databricks=workspace(marker={**MARKER, "input_fingerprint": "fingerprint-0"}), jena={})
    assert rows["neo4j"] == ("behind", "marked 2026-11-10T08:00:00Z from another release set (catalog_digest)")
    assert rows["enterprise"] == ("unmarked", "no marker: mark it after a checked load")
    assert rows["databricks"] == ("behind", "marked 2026-11-10T08:00:00Z from another release set (input_fingerprint)")
    assert rows["jena"][0] == "empty"


def test_an_edit_that_keeps_the_counts_reads_changed_by_the_graph_hash(tmp_path, monkeypatch):
    edited_local, edited_target = graph(), marked_target()
    edited_local.graph_hash = edited_target.graph_hash = "hash-after-one-property-changed"   # same nodes, same relationships
    rows, _ = stores(tmp_path, monkeypatch, local=edited_local, enterprise=edited_target)
    for store in ("neo4j", "enterprise"):
        assert rows[store] == ("changed", "its content differs from the graph it was marked with, although the counts are equal")
    untouched, _ = stores(tmp_path, monkeypatch)
    assert untouched["enterprise"] == ("current", "marked 2026-11-10T09:00:00Z at commit KPI Store 1.1; graph hash hash-1 equal to the marker's")


def test_quick_compares_counts_only_and_says_so(tmp_path, monkeypatch):
    edited = marked_target()
    edited.graph_hash = "hash-after-one-property-changed"
    rows, _ = stores(tmp_path, monkeypatch, enterprise=edited, quick=True)
    assert rows["enterprise"] == ("current", "marked 2026-11-10T09:00:00Z at commit KPI Store 1.1 (counts only: --quick left the graph hash out)")
    assert rows["neo4j"][1].endswith("(counts only: --quick left the graph hash out)")
    assert "counts only" not in rows["jena"][1] and "counts only" not in rows["databricks"][1]


def test_a_marker_without_a_graph_hash_cannot_read_current(tmp_path, monkeypatch):
    old = marked_target()
    del old.nodes[-1][1]["graph_hash"]
    rows, _ = stores(tmp_path, monkeypatch, enterprise=old)
    assert rows["enterprise"] == ("changed", "its marker holds no graph hash, so its content cannot be compared; load it again")


def test_the_technical_graph_gets_a_line_per_store_judged_by_its_own_module(tmp_path, monkeypatch):
    from kpi_store import tech_graph
    files, seen = ["tech-graph.nq"], {}
    monkeypatch.setattr(tech_graph, "jena_apart", lambda graph_files: ["urn:kpi-store:tech:sample:graph"] if graph_files == files else [])
    monkeypatch.setattr(tech_graph, "status_jena", lambda url, graph_files, root: seen.update(jena=(url, graph_files)) or ("current", "1 graph(s), 269 triples"))
    monkeypatch.setattr(tech_graph, "status_delta", lambda gate, settings, graph_files, root: seen.update(delta=settings.tech_graph_schema) or ("behind", "marked from other graph files"))
    def status_neo4j(session, graph_files, root):
        seen.setdefault("neo4j", []).append(getattr(session, "database", session.name))
        if session.name == TARGET:
            return "changed", "its technical graph differs from the graph files although its marker matches"
        raise ConnectionError("bolt://127.0.0.1:7687 refused")
    monkeypatch.setattr(tech_graph, "status_neo4j", status_neo4j)
    wanted = {}
    monkeypatch.setattr(sc, "expected", lambda root, ss, ref="worktree", extra=(): wanted.update(apart=extra) or dict(WANT))
    local = stores_support.local_settings(tmp_path)
    (tmp_path / "kpi_store.toml").write_text(support.SETTINGS_TEXT.replace('warehouse_id = ""', 'warehouse_id = "wh123"'), encoding="utf-8")
    ss = SimpleNamespace(**{k: getattr(REAL.ss, k) for k in dir(REAL.ss) if not k.startswith("__")})
    ss.read_jena = lambda url: dict(GRAPHS)
    code = SimpleNamespace(ss=ss, lm=SimpleNamespace(models=lambda newest: []), lv=SimpleNamespace(hash_graph=lambda s: (s.graph_hash, 0, 0, 0)))
    monkeypatch.setattr(sc, "statement_runner", lambda client, warehouse_id: workspace()[0])
    drivers = {"bolt://127.0.0.1:7687": stores_support.FakeDriver({"neo4j": graph()}),
               local.neo4j_enterprise.uri: stores_support.FakeDriver({TARGET: marked_target()})}
    rows = sc.check(local, support.ROOT, code=code, connect=lambda neo4j: drivers[neo4j.uri], client_for=lambda profile: "client",
                    tech_graph_files=files)
    assert wanted["apart"] == ("urn:kpi-store:tech:sample:graph",)   # the ontology's own check leaves its graphs out
    assert rows[-4:] == [("tech:databricks", "behind", "marked from other graph files"),
                         ("tech:jena", "current", "1 graph(s), 269 triples"),
                         ("tech:neo4j", "unreachable", "unreachable (ConnectionError)"),
                         ("tech:enterprise", "changed", "its technical graph differs from the graph files although its marker matches")]
    assert seen["jena"] == ("http://127.0.0.1:3030/ds/query", files) and seen["delta"] == "tech_graph"
    assert seen["neo4j"] == ["neo4j", TARGET] and not sc.all_current(rows)
    without = sc.check(local, support.ROOT, code=code, connect=lambda neo4j: drivers[neo4j.uri], client_for=lambda profile: "client")
    assert not any(store.startswith("tech:") for store, _, _ in without)


def test_the_technical_graphs_file_is_the_one_named_or_the_one_the_runner_fetched(tmp_path):
    local = stores_support.local_settings(tmp_path)
    assert sc.tech_graph_file(local) is None
    fetched = tmp_path / "runs" / "tech-graph" / "tech-graph.nq"
    fetched.parent.mkdir(parents=True)
    fetched.write_text("", encoding="utf-8")
    assert sc.tech_graph_file(local) == fetched
    (tmp_path / "other.nq").write_text("", encoding="utf-8")
    assert sc.tech_graph_file(local, str(tmp_path / "other.nq")) == tmp_path / "other.nq"
    with pytest.raises(sc.ls.LocalSettingsError, match="the technical graph file .* is missing"):
        sc.tech_graph_file(local, str(tmp_path / "gone.nq"))


def renamed(db):
    db.name = TARGET
    return db


def test_a_store_that_cannot_be_read_says_why_without_an_address(tmp_path, monkeypatch):
    def connect(neo4j):
        raise ConnectionError(f"cannot reach {neo4j.uri} as {neo4j.username}")
    rows, _ = stores(tmp_path, monkeypatch, jena=TimeoutError("http://127.0.0.1:3030"), warehouse="", connect=connect)
    assert rows["neo4j"] == ("unreachable", "unreachable (ConnectionError)")
    assert rows["enterprise"] == ("unreachable", "unreachable (ConnectionError)")
    assert rows["jena"] == ("unreachable", "unreachable (TimeoutError)")
    assert rows["databricks"] == ("unreachable", "set [databricks] warehouse_id in kpi_store.toml to read the triple table")


def test_the_lines_and_the_exit_code(tmp_path, capsys):
    rows = [("jena", "current", "2 graphs"), ("lm:enterprise", "behind", "other files")]
    assert sc.lines(rows) == ["jena            current     2 graphs", "lm:enterprise   behind      other files"]
    assert sc.all_current(rows[:1]) and not sc.all_current(rows)
    assert sc.main(["--stores", str(tmp_path / "missing.toml")]) == 2
    assert "cannot read the local settings file" in capsys.readouterr().err
