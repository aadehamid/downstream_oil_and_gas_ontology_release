"""The reset: what it says it will delete, the word it waits for, and what each store keeps. The stores are
stand-ins, and every name and count is made up and written out by hand."""
import json
import re
from types import SimpleNamespace

import pytest

from kpi_store import reset, runner
from kpi_store.tests import stores_support, support
from kpi_store.tests.test_load_neo4j import graph

TARGET = "businessprocessarchitecturegraph"
BASES = ["https://w3id.org/mpc/ontology/modules/data-product/", "https://w3id.org/mpc/ontology/modules/kpi/"]
PARAMS = {"bases": BASES, "prefixes": ["dp_", "n4sch_", "owl_", "skos_"], "tech_base": "urn:kpi-store:tech:",
          "tech_classes": ["MetricView", "Table"], "lm_slugs": [], "lm_bases": [], "lm_labels": []}
TRIPLES, MARKERS = "idp_sbx.kpi_store.epm_triples", "idp_sbx.kpi_store.epm_store_markers"
TECH_TRIPLES, TECH_MARKERS = "idp_sbx.tech_graph.tech_graph_triples", "idp_sbx.tech_graph.tech_graph_markers"
THE_FOUR_DROPS = ["DROP TABLE IF EXISTS idp_sbx.kpi_store.epm_triples", "DROP TABLE IF EXISTS idp_sbx.kpi_store.epm_store_markers",
                  "DROP TABLE IF EXISTS idp_sbx.tech_graph.tech_graph_triples", "DROP TABLE IF EXISTS idp_sbx.tech_graph.tech_graph_markers"]
KEPT = ("kept: the release folder, the run folder with every run's files and reports, and in Databricks the two "
        "schemas, the volume with the zip and the reports, and the notebook")


class Workspace(support.FakeWorkspace):
    """The fake Databricks, which also counts a table's rows. The statement API gives a count as text."""

    def run_sql(self, statement):
        counted = re.match(r"SELECT count\(\*\) AS n FROM ([\w.]+)$", " ".join(statement.split()))
        if counted:
            self.statements.append(statement)
            return [{"n": str(len(self.store[counted.group(1).lower()]))}]
        return super().run_sql(statement)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Four loaded stores, each with something beside the KPI Store's own data, and a run folder with a run in it."""
    root = tmp_path / "release"
    (root / "kpi_store").mkdir(parents=True)
    (root / "release.json").write_text('{"release": "KPI Store 1.1"}\n', encoding="utf-8", newline="\n")
    folder = tmp_path / "local"
    folder.mkdir()
    (folder / "kpi_store.toml").write_text(support.SETTINGS_TEXT.replace('warehouse_id = ""', 'warehouse_id = "wh123"'),
                                           encoding="utf-8", newline="\n")
    local = stores_support.local_settings(folder, release_root=root)
    step_file = folder / "runs" / "20261111T120000Z" / "steps" / "08-fuseki.json"
    step_file.parent.mkdir(parents=True)
    step_file.write_text('{"status": "loaded"}\n', encoding="utf-8", newline="\n")

    enterprise = graph(store="enterprise")           # 5 Resource, 2 ModuleRelease, 1 EpmStoreMarker
    enterprise.name = TARGET
    enterprise.add(["Invoice"], 2, number="made up")  # someone else's nodes: no mark of the KPI Store
    neo4j = graph(store="neo4j")
    neo4j.add(["_GraphConfig"])
    neo4j.add(["_NsPrefDef"], 3)
    neo4j.constraints = ["n10s_unique_uri"]

    data = local.fuseki.data_folder
    (data / "Data-0001").mkdir(parents=True)
    (data / "Data-0001" / "nodes.dat").write_bytes(b"made up")
    (data / "tdb.lock").write_text("4242", encoding="utf-8")
    (folder / "runs" / "fuseki").mkdir()
    (folder / "runs" / "fuseki" / "fuseki.pid").write_text('{"pid": 4242, "token": "t0"}\n', encoding="utf-8")
    fuseki = SimpleNamespace(up=True, events=[])

    def stop(state):
        fuseki.events.append("stop")
        (state / "fuseki.pid").unlink()
        fuseki.up = False
        return "stopped", 4242
    monkeypatch.setattr(reset.load_fuseki, "answers", lambda f: fuseki.up)
    monkeypatch.setattr(reset.load_fuseki, "stop", stop)
    monkeypatch.setattr(reset.load_fuseki, "command_line", lambda pid: None)
    monkeypatch.setattr(reset.ldb, "import_sync_stores", lambda release: SimpleNamespace(read_jena=lambda url: {"urn:sample:g1": 3, "urn:sample:g2": 4}))

    workspace = Workspace()
    workspace.store = {TRIPLES: [{"subject": "s"}] * 4, MARKERS: [{"store": "databricks", "marker": "{}"}],
                       TECH_TRIPLES: [{"subject": "s"}] * 2,
                       # never the reset's to drop: other work in the same schemas, and a staging table left behind
                       "idp_sbx.kpi_store.other_work": [{"x": 1}], "idp_sbx.kpi_store.epm_triples__staging": [],
                       "idp_sbx.tech_graph.notes": [{"x": 1}]}
    monkeypatch.setattr(reset.sync_check, "statement_runner", lambda client, warehouse: workspace.run_sql)
    monkeypatch.setattr(reset, "marks", lambda ctx, code, store: PARAMS | {"store": store})
    wiped = []   # the load's own wipe drops every constraint, so the reset must never call it
    code = SimpleNamespace(cg=SimpleNamespace(CONFIG_LABELS=("_GraphConfig", "_NsPrefDef", "_n10sValidatorConfig")),
                           lv=SimpleNamespace(wipe=lambda session: wiped.append(session.name)))
    lines = []
    ctx = runner.Context(local, root, "20261111T130000Z", sleep=lambda s: None, databricks="/sample/databricks",
                         bash="/sample/bash", out=lines.append)
    asked = []

    def go(typed=reset.WORD, **options):
        def ask(text):
            asked.append(text)
            if isinstance(typed, BaseException):
                raise typed
            return typed() if callable(typed) else typed
        return reset.run(ctx, options.pop("stores", reset.STORES), ask=ask, code=code, client_for=lambda profile: None,
                         connect=lambda cfg: stores_support.FakeDriver({"neo4j": neo4j, TARGET: enterprise}), **options)
    return SimpleNamespace(go=go, lines=lines, asked=asked, enterprise=enterprise, neo4j=neo4j, data=data, fuseki=fuseki,
                           workspace=workspace, wiped=wiped, ctx=ctx, local=local, root=root, step_file=step_file, folder=folder)


def untouched(world):
    """True when no store lost anything: the checks of a reset that must not have deleted."""
    drops = [s for s in world.workspace.statements if "DROP" in s.upper()]
    return (len(world.enterprise.nodes) == 10 and len(world.neo4j.nodes) == 12 and not world.enterprise.writes()
            and not world.neo4j.writes() and world.neo4j.constraints == ["n10s_unique_uri"] and not world.wiped
            and (world.data / "Data-0001" / "nodes.dat").is_file() and world.fuseki.events == [] and not drops
            and len(world.workspace.store) == 6)


# ---- the plan and the question ---------------------------------------------------------------------

def test_the_plan_says_for_each_store_what_will_be_deleted_and_what_stays(world):
    assert world.go(dry_run=True) == 0
    assert world.lines == [
        "reset (dry run): what would be deleted in enterprise, neo4j, fuseki and databricks. Nothing is deleted yet",
        "enterprise: in the database businessprocessarchitecturegraph, delete 8 node(s) that carry the KPI Store's marks, "
        "with their relationships (1 EpmStoreMarker, 2 ModuleRelease, 5 Resource)",
        "  2 node(s) without those marks stay (2 Invoice). The next copy stops while the database holds them",
        "  the uniqueness constraint that the copy made stays; the next copy uses it",
        "neo4j: in the local database neo4j, delete 12 node(s) that the load wrote, with their relationships "
        "(1 EpmStoreMarker, 2 ModuleRelease, 5 Resource, 1 _GraphConfig, 3 _NsPrefDef), then drop the constraint that the "
        "load made (n10s_unique_uri)",
        f"fuseki: stop the Fuseki that the load started, then delete the dataset folder {world.data} (2 graph(s), 7 triples)",
        "databricks: drop 3 table(s): idp_sbx.kpi_store.epm_triples (4 row(s)), idp_sbx.kpi_store.epm_store_markers (1 row(s)), "
        "idp_sbx.tech_graph.tech_graph_triples (2 row(s))",
        "  not there, so not dropped: idp_sbx.tech_graph.tech_graph_markers",
        KEPT,
        "dry run: nothing was deleted"]


def test_a_dry_run_asks_nothing_and_deletes_nothing(world):
    assert world.go(dry_run=True) == 0
    assert world.asked == [] and untouched(world)
    assert world.go(dry_run=True, yes=True) == 0   # --yes does not turn a dry run into a reset
    assert untouched(world)


@pytest.mark.parametrize("typed", ["", "yes", "y", "Reset", "reset now", "businessprocessarchitecturegraph", EOFError()])
def test_without_the_word_reset_nothing_is_deleted(world, typed):
    assert world.go(typed) == 1
    assert world.asked == ["Type reset to delete this, or press Enter to stop: "]
    assert world.lines[-1] == "reset: STOPPED. The word reset was not typed; nothing was deleted"
    assert untouched(world)


def test_yes_leaves_the_question_out(world):
    assert world.go(typed=AssertionError("asked"), yes=True) == 0
    assert world.asked == [] and world.enterprise.count("Resource") == 0


# ---- what each store loses and keeps ---------------------------------------------------------------

def test_the_word_empties_the_stores_in_order_and_a_node_without_the_marks_survives(world):
    assert world.go(" reset ") == 0
    assert world.lines[-5:] == [
        "enterprise: emptied. 8 node(s) deleted from the database businessprocessarchitecturegraph; 2 node(s) without the "
        "KPI Store's marks left as they were",
        "neo4j: emptied. 12 node(s) deleted from the local database neo4j, and the constraint n10s_unique_uri dropped",
        f"fuseki: emptied. process 4242 stopped; {world.data} deleted",
        "databricks: emptied. 3 table(s) dropped: idp_sbx.kpi_store.epm_triples, idp_sbx.kpi_store.epm_store_markers, "
        "idp_sbx.tech_graph.tech_graph_triples",
        "reset done: enterprise, neo4j, fuseki and databricks hold nothing of the KPI Store. To load again, run: py -m kpi_store.runner"]
    # Enterprise: the two Invoice nodes are all that is left, and no statement dropped anything there.
    assert world.enterprise.nodes == [(["Invoice"], {"number": "made up"})] * 2
    assert not any("DROP" in s for s in world.enterprise.statements)
    # The local database: nothing is left. The one constraint went by its name, not through the load's wipe.
    assert world.neo4j.nodes == [] and world.wiped == [] and world.neo4j.constraints == []
    assert [s for s in world.neo4j.statements if "DROP" in s] == ["DROP CONSTRAINT `n10s_unique_uri` IF EXISTS"]
    assert not world.data.exists() and world.fuseki.events == ["stop"]
    # What the reset never touches: the run's files, the release folder, the local folder's other files.
    assert world.step_file.read_text(encoding="utf-8") == '{"status": "loaded"}\n'
    assert (world.root / "release.json").is_file() and (world.folder / "stores.toml").is_file()
    assert sorted(p.name for p in world.folder.iterdir()) == ["kpi_store.toml", "runs", "stores.toml"]


def test_a_second_reset_finds_nothing_to_delete_and_asks_nothing(world):
    assert world.go() == 0
    world.asked.clear(), world.lines.clear()
    assert world.go(typed=AssertionError("asked")) == 0
    assert world.asked == []
    assert world.lines[1:-1] == [
        "enterprise: the database businessprocessarchitecturegraph holds no node with the KPI Store's marks; nothing to delete",
        "  2 node(s) without those marks stay (2 Invoice). The next copy stops while the database holds them",
        "neo4j: the local database neo4j holds no node that the load wrote and no constraint that it made; nothing to delete",
        "fuseki: no Fuseki runs that the load started, and there is no dataset folder; nothing to delete",
        "databricks: none of the four tables exists (idp_sbx.kpi_store.epm_triples, idp_sbx.kpi_store.epm_store_markers, "
        "idp_sbx.tech_graph.tech_graph_triples, idp_sbx.tech_graph.tech_graph_markers); nothing to delete",
        KEPT]


def test_in_the_local_database_a_node_and_a_constraint_that_the_load_did_not_make_stay(world):
    world.neo4j.add(["Note"], text="made up")
    world.neo4j.constraints = ["note_text_unique", "n10s_unique_uri", "other_work_key"]
    assert world.go(stores=["neo4j"]) == 0
    assert world.lines[1:4] == [
        "neo4j: in the local database neo4j, delete 12 node(s) that the load wrote, with their relationships "
        "(1 EpmStoreMarker, 2 ModuleRelease, 5 Resource, 1 _GraphConfig, 3 _NsPrefDef), then drop the constraint that the "
        "load made (n10s_unique_uri)",
        "  1 node(s) that the load did not write stay (1 Note)",
        "  2 constraint(s) that the load did not make stay (note_text_unique, other_work_key)"]
    assert world.lines[-2] == ("neo4j: emptied. 12 node(s) deleted from the local database neo4j, and the constraint "
                               "n10s_unique_uri dropped; 1 node(s) that the load did not write and 2 constraint(s) that it "
                               "did not make left as they were")
    assert world.neo4j.nodes == [(["Note"], {"text": "made up"})]
    assert world.wiped == [] and world.neo4j.constraints == ["note_text_unique", "other_work_key"]
    assert len(world.enterprise.nodes) == 10   # a store that was not named is not touched


def test_a_constraint_of_the_load_is_dropped_also_when_no_node_is_left_to_delete(world):
    world.neo4j.nodes, world.neo4j.constraints = [], ["n10s_unique_uri", "other_work_key"]
    assert world.go(stores=["neo4j"]) == 0
    assert world.lines[1:3] == ["neo4j: in the local database neo4j, drop the constraint that the load made (n10s_unique_uri)",
                                "  1 constraint(s) that the load did not make stay (other_work_key)"]
    assert world.neo4j.constraints == ["other_work_key"] and world.wiped == []


def test_a_local_database_with_no_constraint_does_not_speak_of_constraints(world):
    world.neo4j.nodes, world.neo4j.constraints = [(["Note"], {"text": "made up"})], []
    assert world.go(stores=["neo4j"], typed=AssertionError("asked")) == 0
    assert world.lines[1:3] == [
        "neo4j: the local database neo4j holds no node that the load wrote and no constraint that it made; nothing to delete",
        "  1 node(s) that the load did not write stay (1 Note)"]
    assert world.lines[-1] == "reset done: neo4j holds nothing of the KPI Store. To load again, run: py -m kpi_store.runner"
    assert world.neo4j.nodes == [(["Note"], {"text": "made up"})] and world.asked == []


def test_only_the_named_stores_are_emptied(world):
    assert world.go(stores=["fuseki", "enterprise"]) == 0
    assert world.lines[0] == "reset: what will be deleted in enterprise and fuseki. Nothing is deleted yet"
    assert world.enterprise.count("Resource") == 0 and not world.data.exists()
    assert len(world.neo4j.nodes) == 12 and world.workspace.statements == []


# ---- a relationship that another writer attached ---------------------------------------------------

@pytest.mark.parametrize("store, said", [
    ("enterprise", "enterprise: cannot be emptied: in the database businessprocessarchitecturegraph, 3 relationship(s) join a "
                   "KPI Store node to a node without its marks (at the far end: 3 Invoice, 1 Paid). The delete would remove "
                   "them with the node, and they are another writer's. Nothing was deleted. Ask their owner to remove them, "
                   "then run the reset again"),
    ("neo4j", "neo4j: cannot be emptied: in the local database neo4j, 3 relationship(s) join a KPI Store node to a node "
              "without its marks (at the far end: 3 Invoice, 1 Paid). The delete would remove them with the node, and they "
              "are another writer's. Nothing was deleted. Ask their owner to remove them, then run the reset again")])
def test_a_relationship_from_another_writers_node_to_a_kpi_store_node_leaves_the_store_alone(world, store, said):
    db = getattr(world, store)
    db.add(["Invoice", "Paid"], number="made up")
    db.links = [(["Invoice", "Paid"], 1), (["Invoice"], 2)]
    before = list(db.nodes)
    assert world.go() == 1
    assert said in world.lines
    assert db.nodes == before and not db.writes() and db.constraints == (["n10s_unique_uri"] if store == "neo4j" else [])
    other = world.neo4j if store == "enterprise" else world.enterprise
    assert other.count("Resource") == 0   # the other stores are emptied
    assert world.lines[-1].startswith(f"reset: NOT DONE. Not emptied: {store}; its line above says why.")


@pytest.mark.parametrize("store", ["enterprise", "neo4j"])
def test_a_relationship_attached_after_the_question_stops_the_delete(world, store):
    db = getattr(world, store)
    before = list(db.nodes)
    def typed():
        db.links = [(["Invoice"], 1)]   # another writer attaches it while the question waits
        return "reset"
    assert world.go(typed, stores=[store]) == 1
    assert world.lines[-2].startswith(f"{store}: FAILED. in the ") and "1 relationship(s) join a KPI Store node" in world.lines[-2]
    assert db.nodes == before and not db.writes()


def test_the_copys_own_delete_is_unchanged():
    from kpi_store import copy_enterprise as ce
    assert ce.own_predicate().startswith("coalesce((n:Resource AND ")
    db = stores_support.FakeNeo4j()
    ce.remove_own(db, PARAMS | {"store": "enterprise"})
    assert len(db.statements) == 1 and db.statements[0].endswith("CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 1000 ROWS")


# ---- Ctrl+C ----------------------------------------------------------------------------------------

def test_ctrl_c_during_a_store_names_it_and_the_stores_not_reached(world, monkeypatch):
    def stopped(session, params, rules):
        if session.name == "neo4j":
            raise KeyboardInterrupt
        world.enterprise.nodes = [n for n in world.enterprise.nodes if n[0] == ["Invoice"]]
    monkeypatch.setattr(reset.copy_enterprise, "remove_own", stopped)
    assert world.go() == 1
    assert world.lines[-2:] == [
        "neo4j: STOPPED by Ctrl+C while it was being emptied. It may be partly emptied",
        "reset: STOPPED at neo4j. Not reached, so not changed: fuseki and databricks. Run the same command again"]
    assert world.data.exists() and len(world.workspace.store) == 6 and world.fuseki.events == []


def test_ctrl_c_at_the_question_deletes_nothing(world):
    assert world.go(KeyboardInterrupt()) == 1
    assert world.lines[-1] == "reset: STOPPED. The word reset was not typed; nothing was deleted"
    assert untouched(world)


# ---- Databricks: the four tables and no other ------------------------------------------------------

def test_a_table_outside_the_four_is_never_named(world):
    assert reset.drop_statements(world.ctx.settings) == THE_FOUR_DROPS
    assert world.go(stores=["databricks"]) == 0
    assert [s for s in world.workspace.statements if not s.startswith("SELECT")] == THE_FOUR_DROPS
    assert sorted(world.workspace.store) == ["idp_sbx.kpi_store.epm_triples__staging", "idp_sbx.kpi_store.other_work", "idp_sbx.tech_graph.notes"]
    named = " ".join(world.workspace.statements)
    assert "other_work" not in named and "__staging" not in named and "tech_graph.notes" not in named
    assert "VOLUME" not in named.upper() and "DROP SCHEMA" not in named.upper()


def test_every_statement_goes_through_the_gate(world, monkeypatch):
    checked = []
    real = reset.ldb.Gate.check
    monkeypatch.setattr(reset.ldb.Gate, "check", lambda self, statement: (checked.append(statement), real(self, statement))[1])
    assert world.go(stores=["databricks"]) == 0
    assert checked == world.workspace.statements and len(checked) == 13
    # The Gate is what refuses a table of another schema: the reset has no check of its own to pass instead.
    monkeypatch.setattr(reset, "databricks_tables", lambda settings: ("idp_sbx.gold_commercial_core.sample_fact",))
    world.workspace.store["idp_sbx.gold_commercial_core.sample_fact"] = [{"x": 1}]
    assert world.go(stores=["databricks"]) == 0   # that table is in no KPI Store schema, so it is never seen as there
    assert "idp_sbx.gold_commercial_core.sample_fact" in world.workspace.store
    with pytest.raises(reset.ldb.GateRefusal, match="a write outside the KPI Store's schemas"):
        reset.ldb.Gate(world.ctx.settings, world.workspace.run_sql).run("DROP TABLE IF EXISTS idp_sbx.gold_commercial_core.sample_fact")


def test_with_no_warehouse_the_reset_prints_the_statements_and_ends_with_exit_1(world, tmp_path):
    (world.folder / "kpi_store.toml").write_text(support.SETTINGS_TEXT, encoding="utf-8", newline="\n")   # warehouse_id = ""
    world.ctx.settings = reset.settings_module.load(world.folder / "kpi_store.toml")
    assert world.go() == 1   # a store of the selection that was left alone is a failure, also when nobody named it
    said = world.lines[world.lines.index(KEPT) - 5:world.lines.index(KEPT)]
    assert said == [
        "databricks: cannot be emptied from this machine: kpi_store.toml names no SQL warehouse, and outside the notebook this "
        "code runs SQL only through one. Set [databricks] warehouse_id and run the reset again. Or run these four statements "
        "in a Databricks SQL editor, and leave Databricks out of the reset with --skip databricks:",
        "  DROP TABLE IF EXISTS idp_sbx.kpi_store.epm_triples;", "  DROP TABLE IF EXISTS idp_sbx.kpi_store.epm_store_markers;",
        "  DROP TABLE IF EXISTS idp_sbx.tech_graph.tech_graph_triples;", "  DROP TABLE IF EXISTS idp_sbx.tech_graph.tech_graph_markers;"]
    assert world.lines[-1] == ("reset: NOT DONE. Not emptied: databricks; its line above says why. enterprise, neo4j and fuseki hold "
                               "nothing of the KPI Store. Run the same command again, or leave a store out on purpose with --skip "
                               "databricks")
    assert world.workspace.statements == [] and len(world.workspace.store) == 6
    world.lines.clear()
    assert world.go(stores=["databricks"]) == 1
    assert world.lines[-1] == ("reset: NOT DONE. Nothing was deleted. Not emptied: databricks; its line above says why. Run the "
                               "same command again, or leave a store out on purpose with --skip databricks")
    world.lines.clear()
    assert world.go(stores=["databricks"], dry_run=True) == 1
    assert world.lines[-1] == ("dry run: nothing was deleted. The reset would leave databricks alone and end with exit code 1; "
                               "leave a store out on purpose with --skip databricks")
    assert world.go(stores=["enterprise", "neo4j", "fuseki"]) == 0   # left out on purpose: no failure
    world.lines.clear()
    world.enterprise.name = "another"   # a second store that is left alone
    assert world.go(stores=["enterprise", "databricks"]) == 1
    assert world.lines[-1] == ("reset: NOT DONE. Nothing was deleted. Not emptied: enterprise and databricks; their lines above "
                               "say why. Run the same command again, or leave a store out on purpose with --skip "
                               "enterprise,databricks")


# ---- Fuseki: its own process and its own folder ----------------------------------------------------

def test_a_folder_that_is_not_the_configured_one_is_refused(world, tmp_path):
    other = tmp_path / "other-db"
    (other / "Data-0001").mkdir(parents=True)
    with pytest.raises(reset.ResetFailed, match=r"other-db is not the folder that \[fuseki\] data_folder names; nothing was deleted"):
        reset.check_dataset_folder(other, world.local, world.root)
    with pytest.raises(reset.ResetFailed, match="is not the folder"):
        reset.check_dataset_folder(world.data.parent, world.local, world.root)   # the folder above it
    with pytest.raises(reset.ResetFailed, match="is not the folder"):
        reset.check_dataset_folder(world.data / "Data-0001", world.local, world.root)   # a folder inside it
    assert reset.check_dataset_folder(world.data, world.local, world.root) == world.data
    assert (other / "Data-0001").is_dir() and (world.data / "Data-0001" / "nodes.dat").is_file()


def test_a_data_folder_reached_through_a_link_is_refused_and_the_folder_checked_is_the_folder_deleted(world, tmp_path, monkeypatch):
    real = tmp_path / "elsewhere"
    (real / "fuseki-db" / "Data-0001").mkdir(parents=True)
    (real / "fuseki-db" / "Data-0001" / "nodes.dat").write_bytes(b"someone else's")
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)
    through = stores_support.local_settings(world.folder, release_root=world.root,
                                            data_folder=f'data_folder = "{(link / "fuseki-db").as_posix()}"')
    with pytest.raises(reset.ResetFailed, match=r"linked is a link, so \[fuseki\] data_folder does not say which folder would "
                                                "be deleted; nothing was deleted"):
        reset.check_dataset_folder(link / "fuseki-db", through, world.root)
    world.ctx.local = through
    assert world.go(stores=["fuseki"]) == 1
    assert world.fuseki.events == [] and (real / "fuseki-db" / "Data-0001" / "nodes.dat").is_file()
    # The last part as a link is refused too.
    last = tmp_path / "db-link"
    last.symlink_to(real / "fuseki-db", target_is_directory=True)
    direct = stores_support.local_settings(world.folder, release_root=world.root, data_folder=f'data_folder = "{last.as_posix()}"')
    with pytest.raises(reset.ResetFailed, match="db-link is a link"):
        reset.check_dataset_folder(last, direct, world.root)
    # With no link, the path that was checked is the one that is deleted, in its resolved form.
    roundabout = world.folder / "runs" / ".." / "fuseki-db"   # the same folder, written another way in the settings
    world.ctx.local = stores_support.local_settings(world.folder, release_root=world.root,
                                                    data_folder=f'data_folder = "{roundabout.as_posix()}"')
    assert world.ctx.local.fuseki.data_folder == roundabout and ".." in roundabout.parts
    deleted = []
    monkeypatch.setattr(reset, "delete_folder", lambda folder, sleep: deleted.append(folder))
    checked = reset.check_dataset_folder(roundabout, world.ctx.local, world.root)
    assert checked == world.data.resolve() and ".." not in checked.parts
    assert world.go(stores=["fuseki"]) == 0 and deleted == [world.data.resolve()]
    assert world.lines[-2] == f"fuseki: emptied. process 4242 stopped; {world.data.resolve()} deleted"


def test_a_configured_folder_that_holds_more_than_a_dataset_is_refused_before_the_question(world):
    (world.data / "notes.txt").write_text("made up", encoding="utf-8")
    assert world.go(stores=["fuseki"]) == 1
    assert world.lines[1] == (f"fuseki: cannot be emptied: {world.data} holds notes.txt, which is no part of a Fuseki dataset; "
                              "nothing was deleted. Correct [fuseki] data_folder, or move that file away")
    assert world.asked == [] and world.fuseki.events == [] and (world.data / "notes.txt").is_file()


def test_a_data_folder_that_holds_the_run_folder_or_the_settings_is_refused(world):
    wide = stores_support.local_settings(world.folder, release_root=world.root,
                                         data_folder=f'data_folder = "{world.folder.as_posix()}"')
    with pytest.raises(reset.ResetFailed, match="holds the local settings file, so it is not only a Fuseki dataset folder"):
        reset.check_dataset_folder(world.folder, wide, world.root)
    assert (world.folder / "stores.toml").is_file()


def test_a_fuseki_that_the_load_did_not_start_is_not_stopped_and_its_folder_stays(world):
    (world.folder / "runs" / "fuseki" / "fuseki.pid").unlink()
    assert world.go(stores=["fuseki"]) == 1
    assert world.lines[1].startswith("fuseki: cannot be emptied: a Fuseki answers at http://127.0.0.1:3030/ds, and the load "
                                     "did not start it, so this command does not stop it.")
    assert world.fuseki.events == [] and (world.data / "Data-0001" / "nodes.dat").is_file() and world.asked == []


def test_a_saved_process_id_that_is_stale_stops_nothing_and_deletes_nothing(world, monkeypatch):
    monkeypatch.setattr(reset.load_fuseki, "stop", lambda state: ("stale", 4242))   # the ID belongs to another program now
    assert world.go(stores=["fuseki"]) == 1
    assert world.lines[-2].startswith("fuseki: FAILED. a Fuseki answers at http://127.0.0.1:3030/ds, and the load did not start it")
    assert world.lines[-1] == "reset: STOPPED at fuseki. Run the same command again"
    assert (world.data / "Data-0001" / "nodes.dat").is_file()


def test_the_folder_is_deleted_only_after_the_server_has_ended(world, monkeypatch):
    seen = []
    still = iter(["java -jar fuseki", "java -jar fuseki", None])
    def command_line(pid):
        seen.append((pid, world.data.exists()))
        return next(still)
    monkeypatch.setattr(reset.load_fuseki, "command_line", command_line)
    waits = []
    world.ctx.sleep = waits.append
    assert world.go(stores=["fuseki"]) == 0
    assert seen == [(4242, True)] * 3 and waits == [1, 1] and not world.data.exists()
    # A process that never ends: the reset gives up and leaves the folder.
    (world.data / "Data-0001").mkdir(parents=True)
    (world.folder / "runs" / "fuseki" / "fuseki.pid").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reset.load_fuseki, "command_line", lambda pid: "java -jar fuseki")
    assert world.go(stores=["fuseki"]) == 1
    assert "did not end within 30 seconds; nothing of the dataset was deleted" in world.lines[-2] and world.data.exists()


def test_a_fuseki_on_another_machine_is_left_alone(world):
    world.ctx.local = stores_support.local_settings(world.folder, release_root=world.root, url='url = "http://fuseki.example.org:3030/ds"')
    assert world.go(stores=["fuseki"]) == 1
    assert world.lines[1] == ("fuseki: cannot be emptied: http://fuseki.example.org:3030/ds is not on this machine, and this "
                              "command stops and empties only a Fuseki that the load started here")
    assert world.fuseki.events == [] and world.data.exists()


# ---- a store that fails or cannot be read ----------------------------------------------------------

def test_a_store_that_cannot_be_read_is_left_alone_and_the_others_are_emptied(world):
    world.enterprise.name = "another"   # the server opens another database than the one named: the copy's own refusal
    assert world.go() == 1
    assert world.lines[1] == (f"enterprise: cannot be emptied: the server opened the database another, not {TARGET}; nothing "
                              "was read or written. Name the database itself in [neo4j.enterprise] database, not an alias")
    assert world.lines[-1] == ("reset: NOT DONE. Not emptied: enterprise; its line above says why. neo4j, fuseki and databricks hold "
                               "nothing of the KPI Store. Run the same command again, or leave a store out on purpose with --skip "
                               "enterprise")
    assert len(world.enterprise.nodes) == 10 and world.neo4j.nodes == []


def test_a_failure_stops_the_reset_and_names_the_stores_it_did_not_reach(world, monkeypatch):
    def fails(session, params, rules):
        if session.name == "neo4j":
            raise ConnectionError("bolt://made-up-host:7687 refused")
        world.enterprise.nodes = [n for n in world.enterprise.nodes if n[0] == ["Invoice"]]
    monkeypatch.setattr(reset.copy_enterprise, "remove_own", fails)
    assert world.go() == 1
    assert world.lines[-3].startswith("enterprise: emptied. 8 node(s) deleted")
    assert world.lines[-2:] == [
        "neo4j: FAILED. The store did not answer, or a statement failed (ConnectionError). It may be part emptied; run the reset again",
        "reset: STOPPED at neo4j. Not reached, so not changed: fuseki and databricks. Run the same command again"]
    assert "made-up-host" not in " ".join(world.lines)   # an error's own text can carry an address
    assert world.data.exists() and len(world.workspace.store) == 6 and world.fuseki.events == []


# ---- the runner's command line ---------------------------------------------------------------------

@pytest.fixture
def command(tmp_path, monkeypatch):
    stores_support.local_settings(tmp_path / "local", release_root=tmp_path / "release")
    (tmp_path / "release").mkdir()
    calls = []
    monkeypatch.setattr(reset, "run", lambda ctx, stores, **options: calls.append((stores, options)) or 0)
    steps = []
    monkeypatch.setattr(runner, "run_steps", lambda ctx, names: steps.append(names) or 0)
    def main(*argv):
        return runner.main(["--stores", str(tmp_path / "local" / "stores.toml"), "--release", str(tmp_path / "release"), *argv],
                           databricks="/sample/databricks", bash="/sample/bash", out=lambda text: None)
    return SimpleNamespace(main=main, calls=calls, steps=steps)


def test_reset_runs_no_step_and_names_all_four_stores(command):
    assert command.main("--reset") == 0
    assert command.calls == [(["enterprise", "neo4j", "fuseki", "databricks"], {"yes": False, "dry_run": False})]
    assert command.steps == []


def test_only_and_skip_take_store_names_with_reset_and_step_names_without(command, capsys):
    assert command.main("--reset", "--only", "databricks,enterprise", "--yes") == 0
    assert command.main("--reset", "--skip", "databricks", "--dry-run") == 0
    assert command.calls == [(["enterprise", "databricks"], {"yes": True, "dry_run": False}),
                             (["enterprise", "neo4j", "fuseki"], {"yes": False, "dry_run": True})]
    for argv, said in ((("--reset", "--only", "zip"), "unknown store zip; the stores are enterprise, neo4j, fuseki, databricks"),
                       (("--only", "databricks"), "unknown step databricks; the steps are cut, check, zip"),
                       (("--reset", "--skip", "enterprise,neo4j,fuseki,databricks"), "--only and --skip leave no store to reset"),
                       (("--reset", "--from", "fuseki"), "--reset takes only --stores, --release, --only, --skip, --yes and --dry-run"),
                       (("--reset", "--replace-enterprise"), "--reset takes only"), (("--reset", "--mode", "check"), "--reset takes only"),
                       (("--yes",), "--yes belongs to --reset")):
        with pytest.raises(SystemExit) as stop:
            command.main(*argv)
        assert stop.value.code == 2 and said in capsys.readouterr().err
    assert len(command.calls) == 2 and command.steps == []
    assert command.main("--only", "sync") == 0 and command.steps == [["sync"]]   # a plain run still takes step names
