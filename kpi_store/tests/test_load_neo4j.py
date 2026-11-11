"""The local Neo4j load: the skill's steps run with this Python, the login file that lives only for the load, the
marker's two checks, and the second run that changes nothing. The database and the skill's driver are stand-ins."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from kpi_store import load_neo4j as ln
from kpi_store.tests import stores_support, support

REAL = ln.release_code(support.ROOT)
DP, KPI = "https://w3id.org/mpc/ontology/modules/data-product/1.0.0", "https://w3id.org/mpc/ontology/modules/kpi/1.0.0"
WANT = {"catalog_datasets": 2, "catalog_digest": "digest-1", "input_fingerprint": "fingerprint-1", "newest": [DP, KPI]}
REPORT = {"passed": True, "input_fingerprint": "fingerprint-1", "nodes": 5, "relationships": 7,
          "determinism_hash_sorted": "hash-1", "shacl_violations_in_graph": 0, "in_graph_shape_constraints": 3,
          "fail_cases": [{"status": "passed"}, {"status": "no-op"}, {"status": "passed"}], "roundtrip_lost": 0, "roundtrip_added": 0}
SECRET = "pw-Only-In-Settings"


def graph(marked=True, hash_="hash-1"):
    """A database that holds the verified graph: 5 Resource nodes, 7 relationships, the two release records."""
    db = stores_support.FakeNeo4j()
    db.add(["Resource"], 5)
    db.relationships, db.graph_hash = 7, hash_
    db.add(["ModuleRelease"], version_iri=DP)
    db.add(["ModuleRelease"], version_iri=KPI)
    if marked:
        db.add(["EpmStoreMarker"], store="neo4j", catalog_datasets=2, catalog_digest="digest-1",
               input_fingerprint="fingerprint-1", count=[5, 7], graph_hash="hash-1", marked_at="2026-11-10T08:00:00Z")
    return db


def stub_code(calls, fails=None, report=REPORT):
    """The release's code with the skill's driver, the graph hash and the report check replaced by stand-ins."""
    class Driver:
        def __init__(self, cfg, run, log):
            self.cfg = cfg
            calls.append(("config", cfg))

        def run_steps(self, steps):
            env = Path(self.cfg["neo4j_env"])
            calls.append(("steps", steps, env.read_text(encoding="utf-8")))
            if fails:
                raise REAL.rp.Failed(fails)
            Path(self.cfg["out"]).mkdir(parents=True, exist_ok=True)
            (Path(self.cfg["out"]) / "projection-report.json").write_text(json.dumps(report), encoding="utf-8")

    return SimpleNamespace(
        rp=SimpleNamespace(read_config=lambda path: json.loads(Path(path).read_text(encoding="utf-8")), Driver=Driver,
                           Failed=REAL.rp.Failed, PY=REAL.rp.PY, RS=REAL.rp.RS),
        lv=SimpleNamespace(hash_graph=lambda session, sep=None: (session.graph_hash, 0, 0, 0), N10S_SEP="__"),
        build=SimpleNamespace(report_earned=lambda rep: [] if rep.get("passed") else ["report passed is false"]),
        lm=SimpleNamespace(models=lambda newest: []), ss=REAL.ss)


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(ln.ldb, "expected", lambda root, ss=None: dict(WANT))
    return stores_support.local_settings(tmp_path, password=f'password = "{SECRET}"')


def connect_to(db):
    return lambda neo4j: stores_support.FakeDriver({"neo4j": db})


# ---- running the skill's steps with this Python ----------------------------------------------------

def test_a_driver_command_runs_with_this_python_and_the_found_java():
    prefixes = (REAL.rp.PY, REAL.rp.RS)
    assert ln.plain_command(list(REAL.rp.PY) + ["load_verify.py", "--report", "r.json"], prefixes) == [sys.executable, "load_verify.py", "--report", "r.json"]
    assert ln.plain_command(list(REAL.rp.RS) + ["rdfstore.py"], prefixes) == [sys.executable, "rdfstore.py"]
    assert ln.plain_command(["java", "-jar", "robot.jar"], prefixes, "/sample/jdk/bin/java") == ["/sample/jdk/bin/java", "-jar", "robot.jar"]
    assert ln.plain_command(["java", "-jar", "robot.jar"], prefixes) == ["java", "-jar", "robot.jar"]
    assert REAL.rp.PY[0] == "uv" and REAL.rp.PY[-1] == "python"   # what the prefix replaces


def test_each_step_command_writes_to_the_log_and_never_through_a_shell(tmp_path):
    seen = []
    def run(cmd, **options):
        seen.append((cmd, options))
        options["stdout"].write("the step's own words\n") if options["stdout"] is not ln.subprocess.PIPE else None
        return SimpleNamespace(returncode=3, stdout="one\ntwo\n")
    step = ln.step_runner((REAL.rp.PY,), tmp_path / "load.log", run=run)
    assert step(list(REAL.rp.PY) + ["build.py", "merge"], cwd="scripts") == (3, None)
    assert step(list(REAL.rp.PY) + ["inputs.py", "data"], capture=True) == (3, "one\ntwo\n")
    cmd, options = seen[0]
    assert cmd == [sys.executable, "build.py", "merge"] and options["cwd"] == "scripts" and "shell" not in options
    assert options["env"]["PYTHONDONTWRITEBYTECODE"] == "1" and options["stdin"] == ln.subprocess.DEVNULL
    assert "the step's own words" in (tmp_path / "load.log").read_text(encoding="utf-8")


def test_the_run_configuration_names_this_release_and_the_local_store(tmp_path, local):
    cfg = ln.run_config(support.ROOT, local, tmp_path / "x.env")
    skill_run = support.ROOT / "business_architecture" / "ontology" / "projection" / "skill-run"
    assert cfg["projection_config"] == str(skill_run / "epm-config.json") and cfg["inputs_script"] == str(skill_run / "inputs.py")
    assert cfg["out"] == str(tmp_path / "lpg-out") and cfg["robot_jar"] == str(tmp_path / "robot.jar")
    assert cfg["neo4j_env"] == str(tmp_path / "x.env") and "plugins_dir" not in cfg and "target_env" not in cfg
    assert (cfg["mode"], cfg["separator"], cfg["release_graphs"]) == ("releases", "_", ["shapes", "catalog"])
    with_plugins = stores_support.local_settings(tmp_path, plugins_folder='plugins_folder = "plugins"')
    assert ln.run_config(support.ROOT, with_plugins, "x.env")["plugins_dir"] == str(tmp_path / "plugins")
    (tmp_path / "run.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert REAL.rp.read_config(str(tmp_path / "run.json"))["out"] == str(tmp_path / "lpg-out")   # the skill accepts it


def test_the_login_file_holds_the_four_settings_and_is_private(tmp_path, local):
    path = ln.write_env_file(tmp_path / "run" / "neo4j-local.env", local.neo4j_local)
    assert path.read_text(encoding="utf-8") == (f"NEO4J_URI=bolt://127.0.0.1:7687\nNEO4J_USERNAME=neo4j\nNEO4J_PASSWORD={SECRET}\n"
                                               "NEO4J_DATABASE=neo4j\n")
    if ln.os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


# ---- the report and the marker ---------------------------------------------------------------------

def test_a_report_must_exist_pass_and_be_of_this_release(tmp_path):
    code = stub_code([])
    with pytest.raises(ln.LoadError, match="there is no load report"):
        ln.read_report(tmp_path, code, WANT)
    for report, message in (({**REPORT, "passed": False}, r"did not pass 1 check\(s\), e.g. report passed is false"),
                            ({**REPORT, "input_fingerprint": "fingerprint-0"}, "is of other release files")):
        (tmp_path / "projection-report.json").write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(ln.LoadError, match=message):
            ln.read_report(tmp_path, code, WANT)
    (tmp_path / "projection-report.json").write_text(json.dumps(REPORT), encoding="utf-8")
    assert ln.read_report(tmp_path, code, WANT)["nodes"] == 5


def test_the_marker_is_written_only_when_counts_and_release_records_match():
    db = graph(marked=False)
    marker = ln.mark(db, "neo4j", WANT, REPORT, REAL.ss, "KPI Store 1.1")
    assert {k: marker[k] for k in ("catalog_datasets", "catalog_digest", "input_fingerprint", "store", "count", "commit", "graph_hash")} == {
        "catalog_datasets": 2, "catalog_digest": "digest-1", "input_fingerprint": "fingerprint-1", "store": "neo4j",
        "count": [5, 7], "commit": "KPI Store 1.1", "graph_hash": "hash-1"}
    assert db.count("EpmStoreMarker") == 1 and db.count("Resource") == 5   # the marker is never a Resource

    short = graph(marked=False)
    short.nodes.pop(0)
    with pytest.raises(ln.LoadError, match="4 nodes and 7 relationships, not the report's 5 and 7; no marker was written"):
        ln.mark(short, "neo4j", WANT, REPORT, REAL.ss, "KPI Store 1.1")
    assert short.count("EpmStoreMarker") == 0 and short.writes() == []

    unrecorded = graph(marked=False)
    unrecorded.nodes = [n for n in unrecorded.nodes if n[1].get("version_iri") != KPI]
    with pytest.raises(ln.LoadError, match=r"its 1 release record\(s\) are not one for each of the 2 newest releases"):
        ln.mark(unrecorded, "neo4j", WANT, REPORT, REAL.ss, "KPI Store 1.1")
    assert unrecorded.writes() == []


@pytest.mark.parametrize("change, current", [
    (lambda db: None, True),
    (lambda db: setattr(db, "graph_hash", "hash-2"), False),                       # the graph moved
    (lambda db: db.nodes.pop(0), False),                                            # a node is gone
    (lambda db: db.nodes[-1][1].update(input_fingerprint="fingerprint-0"), False),  # marked from other files
    (lambda db: db.nodes[-1][1].update(graph_hash="hash-0"), False),                # marked for another graph
    (lambda db: db.nodes.pop(), False),                                             # no marker
    (lambda db: db.nodes.pop(5), False),                                            # a release record is gone
])
def test_current_needs_the_marker_the_hash_the_counts_and_the_records(change, current):
    db = graph()
    change(db)
    assert ln.is_current(db, "neo4j", WANT, REPORT, stub_code([]), "_") is current


# ---- the load --------------------------------------------------------------------------------------

def test_the_load_runs_the_five_steps_then_marks_and_removes_the_login_file(tmp_path, local):
    calls, db = [], graph(marked=False)
    result = ln.load(local, support.ROOT, tmp_path / "run", code=stub_code(calls), connect=connect_to(db))
    assert calls[1][1] == ["project", "load", "review", "tags", "release-record"]
    assert f"NEO4J_PASSWORD={SECRET}" in calls[1][2]                    # the steps could read the login
    assert not (tmp_path / "run" / "neo4j-local.env").exists()          # and it is gone afterwards
    assert (result["status"], result["nodes"], result["relationships"], result["graph_hash"]) == ("loaded", 5, 7, "hash-1")
    assert (result["fail_cases_passed"], result["fail_cases"], result["logical_models"]) == (3, 3, "none")
    assert result["marker"]["count"] == [5, 7] and db.count("EpmStoreMarker") == 1
    for path in (tmp_path / "run").iterdir():
        assert SECRET not in path.read_text(encoding="utf-8"), path.name
    assert SECRET not in json.dumps(result, default=str)
    assert ln.line(result) == ("neo4j (local, database neo4j): loaded, 5 nodes, 7 relationships, 0 SHACL violations over 3 "
                               "constraints, round trip lost 0 and added 0, graph hash hash-1")


def test_a_second_load_on_the_same_release_changes_nothing(tmp_path, local):
    calls, db = [], graph()
    (tmp_path / "lpg-out").mkdir()
    (tmp_path / "lpg-out" / "projection-report.json").write_text(json.dumps(REPORT), encoding="utf-8")
    result = ln.load(local, support.ROOT, tmp_path / "run", code=stub_code(calls), connect=connect_to(db))
    assert result["status"] == "current" and calls == [] and db.writes() == []
    assert not (tmp_path / "run" / "neo4j-local.env").exists()
    forced = ln.load(local, support.ROOT, tmp_path / "run", force=True, code=stub_code(calls), connect=connect_to(db))
    assert forced["status"] == "loaded" and calls[1][0] == "steps"


def test_a_database_that_moved_is_loaded_again(tmp_path, local):
    calls, db = [], graph(hash_="hash-2")
    (tmp_path / "lpg-out").mkdir()
    (tmp_path / "lpg-out" / "projection-report.json").write_text(json.dumps(REPORT), encoding="utf-8")
    db_after = graph(marked=False)
    drivers = iter([stores_support.FakeDriver({"neo4j": db}), stores_support.FakeDriver({"neo4j": db_after})])
    result = ln.load(local, support.ROOT, tmp_path / "run", code=stub_code(calls), connect=lambda neo4j: next(drivers))
    assert result["status"] == "loaded" and len(calls) == 2


def test_a_failed_step_stops_the_load_and_still_removes_the_login_file(tmp_path, local):
    db = graph(marked=False)
    with pytest.raises(ln.LoadError, match="the local load stopped: load_verify.py exited 1"):
        ln.load(local, support.ROOT, tmp_path / "run", code=stub_code([], fails="load_verify.py exited 1"), connect=connect_to(db))
    assert not (tmp_path / "run" / "neo4j-local.env").exists() and db.writes() == []


def test_an_extra_load_runs_before_the_marker(tmp_path, local):
    db, order = graph(marked=False), []
    def technical_graph(session, store):
        order.append((store, session.count("EpmStoreMarker")))
        return {"nodes": 0}
    result = ln.load(local, support.ROOT, tmp_path / "run", code=stub_code([]), connect=connect_to(db), extra_loads=(technical_graph,))
    assert order == [("neo4j", 0)] and result["extra_loads"] == [{"nodes": 0}]


def test_the_command_refuses_bad_settings_before_anything_else(tmp_path, capsys):
    assert ln.main(["--stores", str(tmp_path / "missing.toml")]) == 2
    assert "cannot read the local settings file" in capsys.readouterr().err
