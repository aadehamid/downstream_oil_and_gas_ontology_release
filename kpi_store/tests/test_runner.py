"""The runner: each step against stand-ins, every Databricks CLI call as a recorded argument list, the zip built
the same way twice, and the stop for a report that a person must clear."""
import csv
import datetime as dt
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from kpi_store import report as rep
from kpi_store import runner
from kpi_store.tests import stores_support, support

RUN = "20261111T120000Z"
CLI = "/sample/databricks"
PROFILE = ["--profile", "DEFAULT"]
VOLUME = "dbfs:/Volumes/idp_sbx/kpi_store/releases"
GOLD = "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"


class Recorder:
    """Stands in for subprocess.run: records each argument list and answers from a function of it."""

    def __init__(self, answer=None):
        self.calls, self.options, self.answer = [], [], answer or (lambda cmd: None)

    def __call__(self, cmd, **options):
        self.calls.append(cmd)
        self.options.append(options)
        found = self.answer(cmd) or (0, "", "")
        return SimpleNamespace(returncode=found[0], stdout=found[1], stderr=found[2])


def release_folder(root):
    files = {"README.md": "# Sample\r\nrelease\r\n", "release.json": '{"release": "KPI Store 1.1"}\n',
             "kpi_store/__init__.py": "", "kpi_store/notebook/kpi_store_load.py": "# Databricks notebook source\n",
             "kpi_store/kpi_store.example.toml": support.SETTINGS_TEXT, "data/sample.ttl": "<urn:a> a <urn:B> .\r\n",
             "scripts/check.sh": "echo all checks passed\n",
             # never in the zip:
             "kpi_store/__pycache__/x.cpython-312.pyc": "x", "kpi_store.toml": "[release]\n", "data/.DS_Store": "x",
             ".venv/pyvenv.cfg": "home = /sample\n"}
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    (root / "data" / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "data" / "empty-folder").mkdir()
    return root


@pytest.fixture
def setup(tmp_path):
    root = release_folder(tmp_path / "release")
    local = stores_support.local_settings(tmp_path / "local", release_root=root)
    lines = []
    def make(run=None, **options):
        return runner.Context(local, root, RUN, run=run or Recorder(), sleep=lambda s: None, databricks=CLI,
                              bash="/sample/bash", out=lines.append, **options)
    return SimpleNamespace(root=root, local=local, lines=lines, make=make, run_dir=tmp_path / "local" / "runs" / RUN,
                           pending=tmp_path / "local" / "runs" / "pending", tmp=tmp_path)


# ---- the steps' order and selection ----------------------------------------------------------------

def test_the_steps_run_in_this_order():
    assert runner.STEPS == ("cut", "check", "zip", "volume", "upload", "notebook", "report", "fuseki", "neo4j",
                            "enterprise", "sync", "summary")
    assert runner.selected() == list(runner.STEPS)
    assert runner.selected(start="fuseki") == ["fuseki", "neo4j", "enterprise", "sync", "summary"]
    assert runner.selected(only=["sync", "zip"]) == ["zip", "sync"]
    assert runner.selected(start="neo4j", skip=["enterprise", "summary"]) == ["neo4j", "sync"]
    assert runner.step_list("zip,upload") == ["zip", "upload"]
    with pytest.raises(Exception, match="unknown step zipp"):
        runner.step_list("zipp")


def test_run_ids_are_utc_times_and_the_newest_is_found(tmp_path):
    assert runner.new_run_id(dt.datetime(2026, 11, 11, 12, 0, 0, tzinfo=dt.timezone.utc)) == RUN
    assert runner.newest_run(tmp_path / "none") is None
    for name in ("20261110T090000Z", RUN, "pending"):
        (tmp_path / name).mkdir()
    assert runner.newest_run(tmp_path) == RUN


# ---- zip -------------------------------------------------------------------------------------------

def test_the_zip_holds_the_release_files_only_and_is_the_same_twice(setup):
    first, count = runner.build_zip(setup.root, setup.tmp / "a.zip")
    second, _ = runner.build_zip(setup.root, setup.tmp / "b.zip")
    assert first == second == hashlib.sha256((setup.tmp / "a.zip").read_bytes()).hexdigest() and count == 8
    with zipfile.ZipFile(setup.tmp / "a.zip") as z:
        assert z.namelist() == ["README.md", "data/image.png", "data/sample.ttl", "kpi_store/__init__.py",
                                "kpi_store/kpi_store.example.toml", "kpi_store/notebook/kpi_store_load.py", "release.json",
                                "scripts/check.sh"]
        assert {info.date_time for info in z.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        assert z.read("README.md") == b"# Sample\nrelease\n" and z.read("data/sample.ttl") == b"<urn:a> a <urn:B> .\n"
        assert z.read("data/image.png") == b"\x89PNG\r\n\x1a\n"   # a binary file keeps its bytes


PASSWORD_FILE = '[neo4j.enterprise]\npassword = "pw-That-Must-Not-Travel"\n'


@pytest.mark.parametrize("name", ["machine-stores.toml", "conf/local.env", ".env.production", "conf/db.ini"])
def test_a_plain_folder_with_a_password_file_of_any_name_is_not_zipped(setup, name):
    (setup.root / name).parent.mkdir(parents=True, exist_ok=True)
    (setup.root / name).write_text(PASSWORD_FILE if name.endswith(".toml") else "NEO4J_PASSWORD=pw-That-Must-Not-Travel\n", encoding="utf-8", newline="\n")
    with pytest.raises(runner.StepFailed, match=f"{name} in the release folder sets a password or another secret") as err:
        runner.build_zip(setup.root, setup.tmp / "a.zip")
    assert "pw-That-Must-Not-Travel" not in str(err.value) and not (setup.tmp / "a.zip").exists()
    with pytest.raises(runner.StepFailed):
        runner.step_zip(setup.make(runner.subprocess.run))
    assert not (setup.run_dir / "upload").exists()


@pytest.mark.parametrize("name, text, keys", [
    ("credentials.toml", '"password" = "secret"\n', "password"),                                   # a quoted key
    ("conf/local.env", "export NEO4J_PASSWORD=secret\n", "NEO4J_PASSWORD"),                       # an exported variable
    ("deep.toml", '[stores]\n[[stores.neo4j]]\nname = "a"\n[stores.neo4j.login]\nPassWord = "secret"\n', "PassWord"),
    ("inline.toml", 'login = { user = "a", "api-token" = "secret" }\n', "api-token"),
    ("conf/db.ini", "[db]\npassword : 'secret'\n", "password"),
    ("conf/app.properties", '  client.secret = "secret"\n', "client.secret"),
    (".env", "set DB_PWD=secret\n", "DB_PWD"),
    ("broken.toml", 'password = "secret\n', "the file is not valid TOML, so it cannot be checked"),
    ("kpi_store/stores.example.toml", '[neo4j.local]\npassword = "a-real-one"\n', "password"),     # no file is exempt by its name
])
def test_a_secret_is_found_by_parsing_the_file_not_by_its_spelling(setup, name, text, keys):
    (setup.root / name).parent.mkdir(parents=True, exist_ok=True)
    (setup.root / name).write_text(text, encoding="utf-8", newline="\n")
    assert runner.secret_keys(setup.root / name) == [keys]
    with pytest.raises(runner.StepFailed, match="sets a password or another secret") as err:
        runner.build_zip(setup.root, setup.tmp / "a.zip")
    assert '"secret' not in str(err.value) and "a-real-one" not in str(err.value) and not (setup.tmp / "a.zip").exists()


@pytest.mark.parametrize("name, text", [
    ("a.toml", 'password_env = "KPI_STORE_PW"\n'),              # names an environment variable; the real files use it
    ("b.toml", 'password = "<the Enterprise password>"\n'),     # a placeholder
    ("c.toml", 'password = ""\ntoken = "  "\n'),
    ("d.toml", 'tokens_per_page = "40"\nsecretary = "a name"\npasswords = "many"\n'),
    ("e.toml", "password = 12\n"),                             # not text
    ("f.env", "# NEO4J_PASSWORD=secret\nNEO4J_URI=bolt://127.0.0.1:7687\nNEO4J_PASSWORD=\n"),
    ("g.ini", "; password = secret\n[section]\nuser = neo4j\n"),
])
def test_a_near_miss_is_not_a_secret(setup, name, text):
    (setup.root / name).write_text(text, encoding="utf-8", newline="\n")
    assert runner.secret_keys(setup.root / name) == []


@pytest.mark.parametrize("key, secret", [
    ("password", True), ("NEO4J_PASSWORD", True), ("api-token", True), ("client.secret", True), ("db_pwd", True), ("Passwd", True),
    ("password_env", False), ("tokens_per_page", False), ("secretary", False), ("passwords", False), ("path", False), ("", False)])
def test_which_names_say_secret(key, secret):
    assert runner.is_secret_key(key) is secret


def test_the_example_settings_file_and_a_commented_password_line_may_travel(setup):
    (setup.root / "kpi_store" / "stores.example.toml").write_text(stores_support.STORES_TEXT, encoding="utf-8", newline="\n")
    (setup.root / "environment.example").write_text("# NEO4J_PASSWORD=\n", encoding="utf-8", newline="\n")
    (setup.root / "notes.toml").write_text('# password = "an example in a comment"\ntitle = "the password rule"\n', encoding="utf-8", newline="\n")
    _, count = runner.build_zip(setup.root, setup.tmp / "a.zip")
    assert count == 11


def git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    runner.subprocess.run(["git", "-C", str(root), "-c", "user.name=sample", "-c", "user.email=sample@example.org", *args],
                          check=True, capture_output=True, stdin=runner.subprocess.DEVNULL, env=env)


def test_in_a_git_checkout_the_zip_holds_only_the_files_git_tracks(setup):
    git(setup.root, "init", "-q")
    git(setup.root, "add", "README.md", "release.json", "kpi_store/__init__.py", "data/sample.ttl")
    (setup.root / "machine-stores.toml").write_text(PASSWORD_FILE, encoding="utf-8", newline="\n")   # left in the folder, never added
    (setup.root / "draft-notes.md").write_text("not part of the release\n", encoding="utf-8", newline="\n")
    runner.build_zip(setup.root, setup.tmp / "a.zip")
    with zipfile.ZipFile(setup.tmp / "a.zip") as z:
        assert z.namelist() == ["README.md", "data/sample.ttl", "kpi_store/__init__.py", "release.json"]
        assert not any(b"pw-That-Must-Not-Travel" in z.read(name) for name in z.namelist())
    git(setup.root, "add", "machine-stores.toml")   # a tracked password file is refused, not zipped
    with pytest.raises(runner.StepFailed, match="machine-stores.toml in the release folder sets a password or another secret"):
        runner.build_zip(setup.root, setup.tmp / "b.zip")
    def no_git(cmd, **options):
        raise OSError("git is not installed")
    with pytest.raises(runner.StepFailed, match="git ls-files did not run"):
        runner.build_zip(setup.root, setup.tmp / "c.zip", no_git)


def test_a_settings_file_inside_the_release_given_is_refused_whatever_its_name(setup, capsys):
    stores_support.local_settings(setup.root / "conf")   # inside the release the command is given, outside the code's own
    inside = runner.ls.load(setup.root / "conf" / "stores.toml", {}, release_root=setup.tmp / "elsewhere")
    with pytest.raises(runner.ls.LocalSettingsError, match="the local settings file is inside the release folder"):
        runner.Context(inside, setup.root, RUN)
    assert runner.main(["--stores", str(setup.root / "conf" / "stores.toml"), "--release", str(setup.root), "--only", "zip"]) == 2
    assert "inside the release folder" in capsys.readouterr().err and not (setup.root / "conf" / "runs").exists()


def test_a_changed_file_changes_the_checksum(setup):
    before, _ = runner.build_zip(setup.root, setup.tmp / "a.zip")
    (setup.root / "data" / "sample.ttl").write_text("<urn:a> a <urn:C> .\n", encoding="utf-8", newline="\n")
    assert runner.build_zip(setup.root, setup.tmp / "a.zip")[0] != before


def test_the_settings_copy_gets_the_zips_checksum_and_nothing_else_changes():
    text = support.SETTINGS_TEXT
    new = runner.settings_with_checksum(text, "ab" * 32)
    assert f'sha256 = "{"ab" * 32}"  # the zip' in new and new.replace("ab" * 32, "0" * 64) == text
    for wrong in (text.replace("sha256", "sha"), text + '\nsha256 = "' + "0" * 64 + '"\n'):
        with pytest.raises(runner.StepFailed, match="exactly one sha256 line"):
            runner.settings_with_checksum(wrong, "ab" * 32)


def test_the_zip_step_writes_outside_the_release_and_leaves_the_settings_file_alone(setup):
    ctx = setup.make()
    result = runner.step_zip(ctx)
    built = setup.run_dir / "upload" / "kpi-store-1.1.zip"
    assert result["sha256"] == hashlib.sha256(built.read_bytes()).hexdigest() and result["files"] == 8
    assert f'sha256 = "{result["sha256"]}"' in (setup.run_dir / "upload" / "kpi_store.toml").read_text(encoding="utf-8")
    assert (setup.tmp / "local" / "kpi_store.toml").read_text(encoding="utf-8") == support.SETTINGS_TEXT
    assert result["line"] == f"kpi-store-1.1.zip: 8 files, SHA-256 {result['sha256']}"


# ---- check -----------------------------------------------------------------------------------------

def test_the_check_step_runs_the_script_with_bash_and_needs_its_last_line(setup):
    run = Recorder(lambda cmd: (0, "--- a check\nall checks passed\n", ""))
    assert runner.step_check(setup.make(run))["status"] == "passed"
    assert run.calls == [["/sample/bash", "scripts/check.sh"]] and run.options[0]["cwd"] == str(setup.root.resolve())
    assert "shell" not in run.options[0]
    for answer in ((1, "a check failed\n", "boom"), (0, "all checks passed\nbut then something else\n", "")):
        with pytest.raises(runner.StepFailed, match="scripts/check.sh did not pass"):
            runner.step_check(setup.make(Recorder(lambda cmd: answer)))
    assert (setup.run_dir / "check.log").read_text(encoding="utf-8") == "all checks passed\nbut then something else\n"
    no_bash = setup.make()
    no_bash.bash = None
    with pytest.raises(runner.StepFailed, match="bash was not found, and scripts/check.sh is a bash script"):
        runner.step_check(no_bash)


# ---- the volume and the upload ---------------------------------------------------------------------

def test_a_schema_and_volume_that_exist_are_only_read(setup):
    run = Recorder()
    result = runner.step_volume(setup.make(run))
    assert run.calls == [[CLI, "schemas", "get", "idp_sbx.kpi_store", *PROFILE],
                         [CLI, "volumes", "read", "idp_sbx.kpi_store.releases", *PROFILE]]
    assert result["created"] == [] and result["line"] == "idp_sbx.kpi_store.releases is there"


def test_a_missing_schema_and_volume_are_created(setup):
    run = Recorder(lambda cmd: (1, "", "Error: does not exist") if cmd[2] in ("get", "read") else None)
    result = runner.step_volume(setup.make(run))
    assert run.calls == [[CLI, "schemas", "get", "idp_sbx.kpi_store", *PROFILE],
                         [CLI, "schemas", "create", "kpi_store", "idp_sbx", *PROFILE],
                         [CLI, "volumes", "read", "idp_sbx.kpi_store.releases", *PROFILE],
                         [CLI, "volumes", "create", "idp_sbx", "kpi_store", "releases", "MANAGED", *PROFILE]]
    assert result["created"] == ["schema", "volume"]


def test_when_the_volume_cannot_be_created_the_person_gets_the_two_statements(setup):
    run = Recorder(lambda cmd: (1, "", "Error: PERMISSION_DENIED\n"))
    with pytest.raises(runner.StepFailed) as err:
        runner.step_volume(setup.make(run))
    assert "the schema could not be created (Error: PERMISSION_DENIED)" in str(err.value)
    assert "CREATE SCHEMA IF NOT EXISTS idp_sbx.kpi_store; CREATE VOLUME IF NOT EXISTS idp_sbx.kpi_store.releases;" in str(err.value)


def test_the_upload_copies_the_zip_then_the_settings(setup):
    with pytest.raises(runner.StepFailed, match="run the zip step first"):
        runner.step_upload(setup.make())
    ctx = setup.make()
    runner.write_text(ctx.step_file("zip"), json.dumps(runner.step_zip(ctx)))
    run = Recorder()
    result = runner.step_upload(setup.make(run))
    upload = setup.run_dir / "upload"
    assert run.calls == [[CLI, "fs", "cp", str(upload / "kpi-store-1.1.zip"), f"{VOLUME}/kpi-store-1.1.zip", "--overwrite", *PROFILE],
                         [CLI, "fs", "cp", str(upload / "kpi_store.toml"), f"{VOLUME}/kpi_store.toml", "--overwrite", *PROFILE]]
    assert result["volume"] == "/Volumes/idp_sbx/kpi_store/releases"
    with pytest.raises(runner.StepFailed, match=r"kpi-store-1.1.zip could not be uploaded \(Error: no such volume\)"):
        runner.step_upload(setup.make(Recorder(lambda cmd: (1, "", "Error: no such volume"))))


# ---- the notebook ----------------------------------------------------------------------------------

TECH_NQ = b"<urn:kpi-store:tech:sample:object/a> <urn:sample:p> <urn:sample:o> <urn:kpi-store:tech:sample:graph> .\n"
REPORTS = "/Volumes/idp_sbx/kpi_store/releases/reports/20261111T120300Z-0a1b2c3d"
LOADED = {"status": "loaded", "count": 58250, "table": "idp_sbx.kpi_store.epm_triples", "dataset_hash": "ab12",
          "marker": {"marked_at": "2026-11-11T12:05:00Z", "count": [58250]},
          # The digest is the technical graph's rule, written out: the file's name, a zero byte, its bytes, a zero byte.
          "tech_graph": {"status": "loaded", "count": 1, "file": REPORTS + "/tech-graph.nq",
                         "digest": hashlib.sha256(b"tech-graph.nq\0" + TECH_NQ + b"\0").hexdigest()}}
BLOCKED = {"status": "blocked", "blocking_rows": ["R001"], "report_json": "/Volumes/idp_sbx/kpi_store/releases/reports/20261111T120300Z-0a1b2c3d/discovery-report.json",
           "report_csv": "/Volumes/idp_sbx/kpi_store/releases/reports/20261111T120300Z-0a1b2c3d/discovery-report.csv"}


def databricks(summary, states=("RUNNING", "TERMINATED"), result_state="SUCCESS", error=None):
    polls = iter(states)
    def answer(cmd):
        if cmd[1:3] == ["jobs", "submit"]:
            return 0, '{"run_id": 7001}', ""
        if cmd[1:3] == ["jobs", "get-run"]:
            state = next(polls)
            return 0, json.dumps({"state": {"life_cycle_state": state, "result_state": result_state if state == "TERMINATED" else None},
                                  "tasks": [{"run_id": 7002}]}), ""
        if cmd[1:3] == ["jobs", "get-run-output"]:
            return 0, json.dumps({"notebook_output": {"result": json.dumps(summary)} if summary else {}, "error": error}), ""
    return Recorder(answer)


def test_the_notebook_is_imported_submitted_serverless_and_its_result_read(setup):
    run = databricks(LOADED)
    result = runner.step_notebook(setup.make(run))
    request_file = setup.run_dir / "submit.json"
    assert run.calls == [
        [CLI, "workspace", "mkdirs", "/Workspace/Shared/kpi_store", *PROFILE],
        [CLI, "workspace", "import", "/Workspace/Shared/kpi_store/kpi_store_load", "--file",
         str(setup.root.resolve() / "kpi_store" / "notebook" / "kpi_store_load.py"), "--format", "SOURCE", "--language", "PYTHON",
         "--overwrite", *PROFILE],
        [CLI, "jobs", "submit", "--no-wait", "--json", f"@{request_file}", "--output", "json", *PROFILE],
        [CLI, "jobs", "get-run", "7001", "--output", "json", *PROFILE],
        [CLI, "jobs", "get-run", "7001", "--output", "json", *PROFILE],
        [CLI, "jobs", "get-run-output", "7002", "--output", "json", *PROFILE]]
    assert json.loads(request_file.read_text(encoding="utf-8")) == {
        "run_name": f"KPI Store load {RUN}",
        "tasks": [{"task_key": "kpi_store_load",
                   "notebook_task": {"notebook_path": "/Workspace/Shared/kpi_store/kpi_store_load", "source": "WORKSPACE",
                                     "base_parameters": {"settings_path": "/Volumes/idp_sbx/kpi_store/releases/kpi_store.toml",
                                                         "mode": "load"}}}]}   # no cluster: the run is serverless
    assert (result["status"], result["databricks_run_id"]) == ("loaded", 7001)
    assert result["line"] == "notebook run 7001 loaded: 58250 triples in idp_sbx.kpi_store.epm_triples, hash ab12"
    assert all("shell" not in o and o["stdin"] == runner.subprocess.DEVNULL for o in run.options)
    assert not any("token" in part.lower() for cmd in run.calls for part in cmd)


def test_a_notebook_run_that_fails_says_why(setup):
    run = databricks(None, result_state="FAILED", error="Stop: the release zip's SHA-256 is 11, not the 22 the settings name\n  at line 4")
    with pytest.raises(runner.StepFailed, match="the notebook run 7001 did not succeed: Stop: the release zip's SHA-256 is 11, not the 22"):
        runner.step_notebook(setup.make(run))
    with pytest.raises(runner.StepFailed, match="ended without its JSON summary"):
        runner.step_notebook(setup.make(databricks(None)))
    with pytest.raises(runner.StepFailed, match="ended with status main-mismatch"):
        runner.step_notebook(setup.make(databricks({"status": "main-mismatch"})))
    with pytest.raises(runner.StepFailed, match=r"could not be submitted \(Error: not signed in\)"):
        runner.step_notebook(setup.make(Recorder(lambda cmd: (1, "", "Error: not signed in") if cmd[2] == "submit" else None)))


def test_a_run_that_outlasts_the_wait_is_waited_for_again_and_not_submitted_twice(setup):
    slow = databricks(LOADED, states=["RUNNING"] * 1000)
    with pytest.raises(runner.StepFailed, match="the notebook run 7001 still runs after 60 minutes"):
        runner.step_notebook(setup.make(slow))
    assert sum(1 for c in slow.calls if c[2] == "get-run") == 60 * 60 // runner.POLL_SECONDS + 1
    assert json.loads((setup.run_dir / "steps" / "06-notebook.json").read_text(encoding="utf-8")) == {"status": "waiting", "databricks_run_id": 7001}
    again = databricks(LOADED, states=["TERMINATED"])
    assert runner.step_notebook(setup.make(again))["status"] == "loaded"
    assert [c[2] for c in again.calls] == ["get-run", "get-run-output"]


# ---- the report ------------------------------------------------------------------------------------

def sample_report(decision="", decided_by=""):
    rows = [{"kind": "column-renamed", "blocks": True, "object": GOLD, "ontology_value": "ChangeValue", "found_value": "Change_Value_Amount",
             "evidence": "column lineage holds both names",
             "proposed_fix": {"action": "rename-column", "module": "data-product", "from": "ChangeValue", "to": "Change_Value_Amount"},
             "recommended": "accept", "decision": decision, "decided_by": decided_by, "note": ""},
            {"kind": "column-case", "blocks": False, "object": GOLD, "ontology_value": "assessment_amount", "found_value": "Assessment_Amount",
             "evidence": "the names differ only in case", "proposed_fix": {"action": "respell-column"}, "recommended": "accept",
             "decision": "", "decided_by": "", "note": ""},
            {"kind": "question", "blocks": False, "object": GOLD, "ontology_value": "", "found_value": "", "evidence": "a question",
             "proposed_fix": {"action": "none"}, "recommended": "", "decision": "", "decided_by": "", "note": ""}]
    return rep.build("KPI Store 1.1", {"data-product": "1.2.0"},
                     {"id": "20261111T120300Z-0a1b2c3d", "at": "2026-11-11T12:03:00Z", "settings_sha256": "s", "zip_sha256": "z"},
                     rows, {"object_names": 33, "table_edges": 40, "metric_view_sources": 3})


def fetching(report):
    """A CLI stand-in whose fs cp writes the report files where the runner asked."""
    def answer(cmd):
        if cmd[1:3] == ["fs", "cp"]:
            Path(cmd[4]).write_text(rep.to_json(report) if cmd[4].endswith(".json") else rep.to_csv(report), encoding="utf-8", newline="\n")
    return Recorder(answer)


def with_notebook(setup, summary, run=None):
    ctx = setup.make(run)
    runner.write_text(ctx.step_file("notebook"), json.dumps({"status": summary["status"], "summary": summary}))
    return ctx


def test_a_blocked_run_fetches_the_report_prefills_a_copy_and_stops(setup):
    run = fetching(sample_report())
    with pytest.raises(runner.Stop) as stop:
        runner.step_report(with_notebook(setup, BLOCKED, run))
    assert run.calls == [[CLI, "fs", "cp", "dbfs:" + BLOCKED["report_json"], str(setup.pending / "discovery-report.json"), "--overwrite", *PROFILE],
                         [CLI, "fs", "cp", "dbfs:" + BLOCKED["report_csv"], str(setup.pending / "discovery-report.csv"), "--overwrite", *PROFILE]]
    to_clear = setup.pending / "discovery-report.to-clear.csv"
    assert str(stop.value) == (f"clear the report: edit the decision column of {to_clear} (each holds the recommended decision), write "
                               "your role or initials in decided_by on every row you decide, save, then run the same command again")
    with to_clear.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [(r["id"], r["decision"], r["decided_by"]) for r in rows] == [("R001", "accept", ""), ("R002", "accept", ""), ("R003", "", "")]
    assert setup.lines == ["the notebook stopped: 1 row(s) block the load, of 3 in the report",
                           f"  R001 column-renamed {GOLD}: ChangeValue -> Change_Value_Amount; recommended: accept"]


def test_a_run_that_did_not_block_has_no_report_to_clear(setup):
    with pytest.raises(runner.StepFailed, match="run the notebook step first"):
        runner.step_report(setup.make())
    def fetch(cmd):
        Path(cmd[4]).write_bytes(TECH_NQ)
    run = Recorder(fetch)
    result = runner.step_report(with_notebook(setup, LOADED, run))
    kept = setup.tmp / "local" / "runs" / "tech-graph" / "tech-graph.nq"
    assert run.calls == [[CLI, "fs", "cp", "dbfs:" + REPORTS + "/tech-graph.nq", str(kept), "--overwrite", *PROFILE]]
    assert result["status"] == "no report to clear" and kept.read_bytes() == TECH_NQ
    assert result["tech_graph"] == {"status": "loaded", "digest": LOADED["tech_graph"]["digest"], "count": 1, "file": str(kept)}
    assert result["line"] == ("no row blocks; Databricks marker of 2026-11-11T12:05:00Z, [58250] rows; technical graph loaded in "
                              "Databricks, its file fetched")
    assert runner.tech_graph_files(setup.make()) == [kept]


def test_a_technical_graph_file_that_is_not_the_one_loaded_is_not_kept(setup):
    def other(cmd):
        Path(cmd[4]).write_bytes(TECH_NQ + b"<urn:a> <urn:b> <urn:c> <urn:g> .\n")
    with pytest.raises(runner.StepFailed, match="is not the one the notebook loaded; nothing was kept"):
        runner.step_report(with_notebook(setup, LOADED, Recorder(other)))
    assert runner.tech_graph_files(setup.make()) is None
    with pytest.raises(runner.StepFailed, match=r"could not be fetched from the volume \(Error: not found\)"):
        runner.step_report(with_notebook(setup, LOADED, Recorder(lambda cmd: (1, "", "Error: not found"))))
    older = {k: v for k, v in LOADED.items() if k != "tech_graph"}   # a notebook that built no technical graph
    result = runner.step_report(with_notebook(setup, older, Recorder()))
    assert result["tech_graph"] is None and result["line"].endswith("; no technical graph in this run")


# ---- cut -------------------------------------------------------------------------------------------

def pending_report(setup, edit=None):
    """A pending report as the report step leaves it, with the to-clear CSV edited as a person would."""
    setup.pending.mkdir(parents=True)
    report = sample_report()
    (setup.pending / "discovery-report.json").write_text(rep.to_json(report), encoding="utf-8", newline="\n")
    rows = list(csv.DictReader(runner.prefilled_csv(report).splitlines()))
    for row in rows:
        row.update((edit or {}).get(row["id"], {}))
    with (setup.pending / runner.TO_CLEAR).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rep.ROW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_with_no_pending_report_there_is_nothing_to_cut(setup):
    assert runner.step_cut(setup.make())["status"] == "nothing to cut"


def test_a_report_that_is_not_cleared_stops_the_run_before_the_cut(setup):
    pending_report(setup)   # the recommended decisions, and no name
    called = []
    with pytest.raises(runner.Stop) as stop:
        runner.step_cut(setup.make(hooks={"cut": lambda *a: called.append(a)}))
    assert str(stop.value) == (f"clear the report: in {setup.pending / runner.TO_CLEAR} give a decision and write your role or initials "
                               "in decided_by for the row(s) that block (R001), save, then run the same command again")
    assert called == [] and setup.pending.is_dir()


def test_a_csv_that_a_spreadsheet_saved_in_another_encoding_stops_with_how_to_save_it(setup):
    pending_report(setup, {"R001": {"decided_by": "the owner"}})
    path = setup.pending / runner.TO_CLEAR
    path.write_bytes(path.read_bytes().replace(b"the owner", "the owner".encode() + b" \x96 pricing"))   # a cp1252 dash
    called = []
    with pytest.raises(runner.Stop) as stop:
        runner.step_cut(setup.make(hooks={"cut": lambda *a: called.append(a)}))
    assert str(stop.value) == (f"save {path} as UTF-8: in Excel choose File, Save As, and the file type \"CSV UTF-8 (Comma "
                               "delimited)\"; then run the same command again")
    assert called == [] and setup.pending.is_dir()


def test_a_refused_copy_names_the_runners_own_option_for_the_replace(setup, monkeypatch):
    from kpi_store import copy_enterprise

    def refuse(local, root, **options):
        raise copy_enterprise.Refused("the database holds 12 node(s) that carry the KPI Store's own marks. Nothing was changed. "
                                      "Run the command again with --replace to replace them.")
    monkeypatch.setattr(copy_enterprise, "copy", refuse)
    assert runner.run_steps(setup.make(), ["enterprise"]) == 1
    assert setup.lines[-1] == ("enterprise: FAILED. the database holds 12 node(s) that carry the KPI Store's own marks. Nothing was "
                               "changed. Run the runner again with --from enterprise --replace-enterprise to replace them.")


@pytest.mark.parametrize("name", ["a.person@example.org", "x" * 61, "the owner; drop", "name/with/slash"])
def test_decided_by_must_be_a_role_or_initials_as_the_cut_tool_requires(setup, name):
    pending_report(setup, {"R001": {"decided_by": name}})
    with pytest.raises(runner.Stop, match="decided_by of row R001 is not a role or initials. There, write a role or initials, such as"):
        runner.step_cut(setup.make(hooks={"cut": lambda *a: pytest.fail("the cut ran")}))


def test_who_may_decide_is_the_cut_tools_rule_and_no_other(setup, monkeypatch):
    asked = []
    monkeypatch.setattr(runner.cut_tool, "is_role", lambda text: asked.append(text) or text == "only this passes")
    pending_report(setup, {"R001": {"decided_by": "the owner"}})
    with pytest.raises(runner.Stop, match="decided_by of row R001 is not a role or initials"):
        runner.step_cut(setup.make(hooks={"cut": lambda *a: pytest.fail("the cut ran")}))
    assert asked == ["the owner"]
    runner.shutil.rmtree(setup.pending)
    pending_report(setup, {"R001": {"decided_by": "only this passes"}})
    assert runner.step_cut(setup.make(hooks={"cut": lambda *a: {"status": "cut"}}))["status"] == "cut"


def test_the_library_cut_maps_the_tools_outcome_and_its_refusals(monkeypatch):
    cut = runner.cut_tool   # the module object the runner holds
    seen = []
    def made(report, release_root, decisions, ask, say):
        seen.append((report, release_root, decisions, ask("Type yes: ")))
        return cut.Outcome("cut", None, Path("business_architecture/ontology/discovery-runs/run-1.md"), ["a", "b"], True, "data-product-1.2.1-correction.1")
    monkeypatch.setattr(cut, "cut", made)
    result = runner.cut_with_library("cleared.json", "release", "run", "confirmed.csv", ask=lambda prompt: "yes", say=lambda line: None)
    assert result == {"status": "cut", "outcome": "cut", "tag": "data-product-1.2.1-correction.1", "committed": True,
                      "record": "business_architecture/ontology/discovery-runs/run-1.md", "files": 2}
    assert seen == [("cleared.json", "release", "confirmed.csv", "yes")]
    for error, why in ((cut.CutRefused("row R001 was not confirmed; nothing was changed"), "CutRefused: row R001 was not confirmed; nothing was changed"),
                       (cut.CutFailed("the build failed"), "CutFailed: the build failed"), (EOFError(), "no answer was typed; nothing was changed")):
        def refuse(*a, **k):
            raise error
        monkeypatch.setattr(cut, "cut", refuse)
        assert runner.cut_with_library("cleared.json", "release", "run") == {"status": "failed", "why": why}


@pytest.mark.parametrize("name", ["the owner", "H.A.", "data-platform lead", "O'Neil 2"])
def test_a_role_or_initials_passes(setup, name):
    pending_report(setup, {"R001": {"decided_by": name}})
    assert runner.step_cut(setup.make(hooks={"cut": lambda *a: {"status": "cut"}}))["status"] == "cut"


def edit_csv(setup, change):
    path = setup.pending / runner.TO_CLEAR
    with path.open(encoding="utf-8", newline="") as f:
        rows = change(list(csv.DictReader(f)))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rep.ROW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("change, said", [
    (lambda rows: rows[1:], "missing: R001"),                                                   # the row that blocks was deleted
    (lambda rows: rows[:2], "missing: R003"),
    (lambda rows: rows + [{**rows[0], "id": "R009"}], "not in the report: R009"),
    (lambda rows: rows + [rows[1]], "a row ID occurs twice"),
])
def test_a_csv_that_does_not_hold_exactly_the_reports_rows_never_reaches_the_cut(setup, change, said):
    pending_report(setup, {"R001": {"decided_by": "the owner"}})
    edit_csv(setup, change)
    called = []
    with pytest.raises(runner.Stop) as stop:
        runner.step_cut(setup.make(hooks={"cut": lambda *a: called.append(a) or {"status": "cut"}}))
    assert "it must hold exactly the report's 3 rows, each once" in str(stop.value) and said in str(stop.value)
    assert called == [] and (setup.pending / "discovery-report.json").is_file()


def test_the_report_itself_is_checked_after_the_csv_is_applied(setup, monkeypatch):
    pending_report(setup, {"R001": {"decided_by": "the owner"}})
    # Whatever the CSV step lets through, a blocking row without a decision and a name stops the cut.
    monkeypatch.setattr(rep, "apply_csv_decisions", lambda report, path: report)
    with pytest.raises(runner.Stop, match=r"give a decision and write your role or initials in decided_by for the row\(s\) that block \(R001\)"):
        runner.step_cut(setup.make(hooks={"cut": lambda *a: pytest.fail("the cut ran")}))


def test_a_cleared_report_is_cut_once_and_unconfirmed_rows_stay_undecided(setup):
    pending_report(setup, {"R001": {"decided_by": "the owner"}})
    seen = []
    def cut(report_json, release_root, run_dir, decisions):
        with Path(decisions).open(encoding="utf-8", newline="") as f:
            handed = [(r["id"], r["decision"], r["decided_by"]) for r in csv.DictReader(f)]
        seen.append((json.loads(Path(report_json).read_text(encoding="utf-8")), release_root, run_dir, decisions, handed))
        return {"status": "cut", "version": "1.2.1-correction.1"}
    result = runner.step_cut(setup.make(hooks={"cut": cut}))
    report, root, run_dir, decisions, handed = seen[0]
    # The cut gets the cleared report and the confirmed decisions as CSV, both in the run's folder.
    assert decisions == setup.run_dir / "confirmed.csv" and decisions.is_file()
    assert handed == [("R001", "accept", "the owner"), ("R002", "", ""), ("R003", "", "")]
    assert [(r["id"], r["decision"], r["decided_by"]) for r in report["rows"]] == [
        ("R001", "accept", "the owner"), ("R002", "", ""), ("R003", "", "")]
    assert (root, run_dir) == (setup.root.resolve(), setup.run_dir)
    assert (result["status"], result["version"], result["decided_rows"], result["undecided_rows"]) == ("cut", "1.2.1-correction.1", 1, ["R002"])
    assert not setup.pending.exists() and (setup.run_dir / "cut-report" / "discovery-report.json").is_file()
    assert runner.step_cut(setup.make(hooks={"cut": cut}))["status"] == "nothing to cut" and len(seen) == 1


def test_a_wrong_decision_or_a_failed_cut_keeps_the_report_pending(setup):
    pending_report(setup, {"R001": {"decision": "maybe", "decided_by": "the owner"}})
    with pytest.raises(runner.Stop, match="decision must be empty or one of accept, reject, environment setting"):
        runner.step_cut(setup.make())
    runner.shutil.rmtree(setup.pending)
    pending_report(setup, {"R001": {"decision": "reject", "decided_by": "the owner"}})
    with pytest.raises(runner.StepFailed, match="the cut did not finish: the cut tool exited 1"):
        runner.step_cut(setup.make(hooks={"cut": lambda *a: {"status": "failed", "why": "the cut tool exited 1"}}))
    assert (setup.pending / "discovery-report.json").is_file()


def test_the_cut_tool_is_called_as_a_module_with_the_report_and_the_release(setup):
    run = Recorder()
    assert runner.cut_with_tool("cleared.json", setup.root, setup.run_dir, "confirmed.csv", run) == {
        "status": "failed", "why": "this release has no cut tool (kpi_store/cut.py)"}
    (setup.root / "kpi_store" / "cut.py").write_text("", encoding="utf-8", newline="\n")
    assert runner.cut_with_tool("cleared.json", setup.root, setup.run_dir, "confirmed.csv", run) == {"status": "cut"}
    assert run.calls == [[sys.executable, "-m", "kpi_store.cut", "--report", "cleared.json", "--decisions", "confirmed.csv",
                          "--release", str(setup.root)]]
    assert run.options[0] == {"cwd": str(setup.root)}   # nothing captured or redirected: the tool asks in this terminal
    refused = runner.cut_with_tool("cleared.json", setup.root, setup.run_dir, "confirmed.csv", Recorder(lambda cmd: (1, "", "")))
    assert refused == {"status": "failed", "why": "the cut tool exited 1: it refused or failed, and changed nothing"}
    assert runner.cut_command("cleared.json", "release") == [sys.executable, "-m", "kpi_store.cut", "--report", "cleared.json", "--release", "release"]


def test_the_zip_after_a_cut_is_built_from_the_tree_the_cut_left(setup):
    pending_report(setup, {"R001": {"decided_by": "the owner"}})
    before, _ = runner.build_zip(setup.root, setup.tmp / "before.zip")
    def cut(report_json, release_root, run_dir, decisions):   # the cut writes a correction version into the release
        package = Path(release_root) / "releases" / "data-product" / "1.2.1-correction.1" / "data-product.ttl"
        package.parent.mkdir(parents=True)
        package.write_text("<urn:a> a <urn:Corrected> .\n", encoding="utf-8", newline="\n")
        return {"status": "cut"}
    ctx = setup.make(hooks={"cut": cut})
    assert runner.run_steps(ctx, ["cut", "zip"]) == 0
    built = json.loads(ctx.step_file("zip").read_text(encoding="utf-8"))
    assert built["sha256"] != before and built["files"] == 9
    with zipfile.ZipFile(built["zip"]) as z:
        assert z.read("releases/data-product/1.2.1-correction.1/data-product.ttl") == b"<urn:a> a <urn:Corrected> .\n"
    assert f'sha256 = "{built["sha256"]}"' in Path(built["settings"]).read_text(encoding="utf-8")


# ---- the chain -------------------------------------------------------------------------------------

def test_a_dry_run_prints_every_command_and_runs_and_writes_nothing(setup):
    run = Recorder()
    ctx = setup.make(run, dry_run=True)
    assert runner.run_steps(ctx, runner.selected()) == 0
    assert run.calls == [] and not setup.run_dir.exists() and not setup.pending.exists()
    printed = [json.loads(line) for line in setup.lines if line.startswith("  [")]
    assert [c[1:3] for c in printed if c[0] == CLI] == [
        ["schemas", "get"], ["schemas", "create"], ["volumes", "read"], ["volumes", "create"], ["fs", "cp"], ["fs", "cp"],
        ["workspace", "mkdirs"], ["workspace", "import"], ["jobs", "submit"], ["jobs", "get-run"], ["jobs", "get-run-output"],
        ["fs", "cp"], ["fs", "cp"], ["fs", "cp"]]
    assert printed[-1][3:5] == ["dbfs:/Volumes/idp_sbx/kpi_store/releases/reports/<report run>/tech-graph.nq",
                                str(setup.tmp / "local" / "runs" / "tech-graph" / "tech-graph.nq")]
    assert ["/sample/bash", "scripts/check.sh"] in printed
    assert all(c[-2:] == PROFILE for c in printed if c[0] == CLI)


def test_a_stop_for_a_person_ends_the_chain_with_code_3(setup):
    ctx = with_notebook(setup, BLOCKED, fetching(sample_report()))
    ran = []
    stubbed = dict(runner.STEP_FUNCTIONS, fuseki=lambda c: ran.append("fuseki") or {"status": "x", "line": "x"})
    try:
        runner.STEP_FUNCTIONS.update(stubbed)
        assert runner.run_steps(ctx, ["report", "fuseki"]) == 3
    finally:
        runner.STEP_FUNCTIONS["fuseki"] = runner.step_fuseki
    assert ran == [] and setup.lines[-1].startswith("report: STOPPED. Next step: clear the report: edit the decision column of ")
    assert json.loads((setup.run_dir / "steps" / "07-report.json").read_text(encoding="utf-8"))["blocking_rows"] == ["R001"]


def test_a_failed_step_ends_the_chain_with_code_1_and_is_recorded(setup):
    ctx = setup.make(Recorder(lambda cmd: (1, "", "Error: PERMISSION_DENIED")))
    assert runner.run_steps(ctx, ["volume", "upload"]) == 1
    assert setup.lines[-1].startswith("volume: FAILED. the schema could not be created")
    assert json.loads((setup.run_dir / "steps" / "04-volume.json").read_text(encoding="utf-8"))["status"] == "failed"
    assert not (setup.run_dir / "steps" / "05-upload.json").exists()


@pytest.mark.parametrize("record, said", [
    ({"status": "blocked", "summary": BLOCKED}, "the notebook stopped on a report, so Databricks does not hold this release"),
    ({"status": "failed", "why": "the notebook run 7001 did not succeed"}, "the notebook step ended as failed"),
    ({"status": "waiting", "databricks_run_id": 7001}, "the notebook run has not ended"),
    ({"status": "checked", "summary": {"status": "checked"}}, "the notebook step ended as checked"),
])
def test_a_store_load_after_a_notebook_that_did_not_load_is_a_stop_never_a_pass(setup, monkeypatch, record, said):
    for name in runner.LOCAL_LOADS:
        monkeypatch.setitem(runner.STEP_FUNCTIONS, name, lambda ctx: pytest.fail("a local load ran"))
    ctx = setup.make()
    runner.write_text(ctx.step_file("notebook"), json.dumps(record))
    assert runner.run_steps(ctx, ["fuseki", "neo4j", "enterprise", "sync", "summary"]) == 3   # as --from fuseki --skip report runs
    assert setup.lines == [f"fuseki: STOPPED. Next step: {runner.not_loaded_reason(ctx)}"] and said in setup.lines[0]
    assert not (setup.run_dir / "summary.json").exists()


def test_the_last_line_says_every_step_passed_only_when_none_was_left_out():
    assert runner.closing_line([]) == "every step passed"
    assert runner.closing_line(["check", "report"]) == "the steps that ran passed; left out: check, report (not run, so not checked)"


def test_a_skipped_check_is_named_in_the_last_line_and_the_summary(setup):
    code = runner.main(["--stores", str(setup.local.path), "--release", str(setup.root), "--skip", "check", "--only", "check,summary",
                        "--run-id", RUN], out=setup.lines.append)
    # Only the summary ran: every other step is named, in the chain's order, on the screen and in summary.json.
    assert code == 0 and setup.lines[-1] == ("the steps that ran passed; left out: cut, check, zip, volume, upload, notebook, report, fuseki, neo4j, enterprise, sync (not run, so not checked)")
    assert [line for line in setup.lines if line.endswith("left out of this run")] == [
        f"  {name:<11} left out of this run" for name in ("cut", "check", "zip", "volume", "upload", "notebook", "report", "fuseki",
                                                           "neo4j", "enterprise", "sync")]
    assert "every step passed" not in setup.lines
    assert json.loads((setup.run_dir / "summary.json").read_text(encoding="utf-8"))["left_out"] == [
        "cut", "check", "zip", "volume", "upload", "notebook", "report", "fuseki", "neo4j", "enterprise", "sync"]


def test_a_run_narrowed_by_only_or_from_never_says_every_step_passed(setup):
    args = ["--stores", str(setup.local.path), "--release", str(setup.root), "--run-id", RUN]
    options = dict(out=setup.lines.append, run=Recorder(), databricks=CLI, bash="/sample/bash")
    assert runner.main([*args, "--only", "zip,volume"], **options) == 0
    assert setup.lines[-1] == ("the steps that ran passed; left out: cut, check, upload, notebook, report, fuseki, neo4j, enterprise, "
                               "sync, summary (not run, so not checked)")
    first = len(setup.lines)
    assert runner.main([*args, "--from", "summary"], **options) == 0
    assert setup.lines[-1] == "the steps that ran passed; left out: cut, check, zip, volume, upload, notebook, report, fuseki, neo4j, enterprise, sync (not run, so not checked)"
    # The summary names each step this command left out, and what an earlier command of the same run recorded for it.
    assert setup.lines[first + 1:-2] == [
        f"summary of run {RUN}:", "  cut         left out of this run", "  check       left out of this run",
        "  zip         left out of this run (recorded earlier: built)", "  volume      left out of this run (recorded earlier: ready)",
        "  upload      left out of this run", "  notebook    left out of this run", "  report      left out of this run",
        "  fuseki      left out of this run", "  neo4j       left out of this run", "  enterprise  left out of this run",
        "  sync        left out of this run"]
    assert json.loads((setup.run_dir / "summary.json").read_text(encoding="utf-8"))["left_out"] == [
        "cut", "check", "zip", "volume", "upload", "notebook", "report", "fuseki", "neo4j", "enterprise", "sync"]
    assert "every step passed" not in setup.lines


def test_only_a_run_of_the_whole_chain_says_every_step_passed(setup, monkeypatch):
    for name in runner.STEPS:
        monkeypatch.setitem(runner.STEP_FUNCTIONS, name, lambda ctx: {"status": "loaded", "line": "done"})
    args = ["--stores", str(setup.local.path), "--release", str(setup.root), "--run-id", RUN]
    assert runner.main(args, out=setup.lines.append) == 0 and setup.lines[-1] == "every step passed"
    assert runner.main([*args, "--only", ",".join(runner.STEPS[:-1])], out=setup.lines.append) == 0
    assert setup.lines[-1] == "the steps that ran passed; left out: summary (not run, so not checked)"


def test_mode_check_leaves_the_store_loads_out_and_says_so(setup):
    runner.main(["--stores", str(setup.local.path), "--release", str(setup.root), "--mode", "check", "--dry-run", "--run-id", RUN],
                out=setup.lines.append, run=Recorder(), databricks=CLI, bash="/sample/bash")
    assert setup.lines[0] == f"run {RUN} (dry run): cut, check, zip, volume, upload, notebook, report, summary"


def test_a_notebook_wait_that_times_out_keeps_the_run_id_and_the_next_run_polls_the_same_run(setup):
    slow = databricks(LOADED, states=["RUNNING"] * 1000)
    assert runner.run_steps(setup.make(slow), ["notebook", "report"]) == 1
    record = setup.run_dir / "steps" / "06-notebook.json"
    assert json.loads(record.read_text(encoding="utf-8")) == {"status": "waiting", "databricks_run_id": 7001}
    unreadable = Recorder(lambda cmd: (1, "", "Error: connection reset"))   # a poll that fails keeps it too
    assert runner.run_steps(setup.make(unreadable), ["notebook"]) == 1
    assert json.loads(record.read_text(encoding="utf-8")) == {"status": "waiting", "databricks_run_id": 7001}
    again = databricks(LOADED, states=["RUNNING", "TERMINATED"])
    assert runner.run_steps(setup.make(again), ["notebook"]) == 0
    assert [c[2] for c in again.calls] == ["get-run", "get-run", "get-run-output"]   # no second submit
    assert sum(1 for run in (slow, unreadable, again) for c in run.calls if c[2] == "submit") == 1
    assert json.loads(record.read_text(encoding="utf-8"))["status"] == "loaded"
    failed = databricks(None, result_state="FAILED", error="Stop: the settings file is wrong")
    assert runner.run_steps(setup.make(failed), ["notebook"]) == 1   # a run that ended and failed is not waited for again
    assert json.loads(record.read_text(encoding="utf-8"))["status"] == "failed"


def test_the_local_steps_pass_the_hooks_on_and_the_summary_lists_the_run(setup, monkeypatch):
    from kpi_store import copy_enterprise, load_fuseki, load_neo4j, sync_check
    seen = {}
    extra = {"urn:sample:tech-graph": "objects.ttl"}
    tech_file = setup.tmp / "local" / "runs" / "tech-graph" / "tech-graph.nq"   # as the report step fetched it
    tech_file.parent.mkdir(parents=True)
    tech_file.write_bytes(TECH_NQ)
    monkeypatch.setattr(load_neo4j, "tech_graph_loader", lambda files, root: ("the technical graph's loader", files, root))
    monkeypatch.setattr(load_fuseki, "run", lambda local, root, extra_graphs=None, tech_graph_files=None: seen.update(fuseki=extra_graphs, fuseki_tech=tech_graph_files) or {
        "status": "loaded", "graphs": 8, "triples": 33, "dataset_hash": "ab12", "store_hash": "ab12", "server": "reused", "persistent": True})
    monkeypatch.setattr(load_neo4j, "load", lambda local, root, run_dir=None, extra_loads=(): seen.update(neo4j=extra_loads) or {
        "status": "loaded", "database": "neo4j", "nodes": 5, "relationships": 7, "shacl_violations_in_graph": 0,
        "in_graph_constraints": 3, "roundtrip_lost": 0, "roundtrip_added": 0, "graph_hash": "hash-1"})
    monkeypatch.setattr(copy_enterprise, "copy", lambda local, root, **options: seen.update(enterprise=options) or {
        "status": "copied", "database": "businessprocessarchitecturegraph", "nodes": 5, "relationships": 7, "graph_hash": "hash-1"})
    monkeypatch.setattr(sync_check, "check", lambda local, root, extra_graphs=(), tech_graph_files=None: seen.update(sync=extra_graphs, sync_tech=tech_graph_files) or [
        ("jena", "current", "8 graphs"), ("neo4j", "current", "marked")])
    loader = lambda session, store: {}   # noqa: E731
    rules = {"Resource": "n.uri IS NOT NULL", "TechObject": "n.tech_graph IS NOT NULL"}
    ctx = setup.make(replace_enterprise=True, hooks={"extra_graphs": lambda root, run_dir: extra, "neo4j_extra_loads": (loader,),
                                                     "own_rules": rules})
    assert runner.run_steps(ctx, ["fuseki", "neo4j", "enterprise", "sync", "summary"]) == 0
    tech_loader = ("the technical graph's loader", [tech_file], setup.root.resolve())
    assert seen["fuseki"] == extra and seen["sync"] == ("urn:sample:tech-graph",)
    assert seen["fuseki_tech"] == seen["sync_tech"] == [tech_file]
    # In both Neo4j databases the technical graph follows the ontology, before any load a hook adds.
    assert seen["neo4j"] == (tech_loader, loader) and seen["enterprise"]["extra_loads"] == (tech_loader, loader)
    assert seen["enterprise"]["replace"] is True and seen["enterprise"]["own_rules"] == rules
    assert setup.lines[0].startswith("fuseki: loaded, 8 graphs, 33 triples") and "sync: all 2 lines read current" in setup.lines
    summary = json.loads((setup.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert {k: v["status"] for k, v in summary["steps"].items() if v} == {"fuseki": "loaded", "neo4j": "loaded", "enterprise": "copied", "sync": "current"}
    monkeypatch.setattr(sync_check, "check", lambda local, root, extra_graphs=(), tech_graph_files=None: [("jena", "behind", "1 graph missing")])
    assert runner.run_steps(ctx, ["sync"]) == 1 and setup.lines[-1] == "sync: FAILED. not current: jena"
    assert json.loads((setup.run_dir / "steps" / "11-sync.json").read_text(encoding="utf-8"))["rows"][0]["status"] == "behind"


def test_the_sync_step_fails_on_a_technical_graph_that_was_not_checked_and_names_the_fix(setup, monkeypatch):
    from kpi_store import sync_check
    seen = {}
    def check(local, root, extra_graphs=(), tech_graph_files=None):
        seen["files"] = tech_graph_files
        return [("jena", "current", "8 graphs"), ("tech:jena", "not checked", sync_check.NO_FILE)]
    monkeypatch.setattr(sync_check, "check", check)
    assert runner.run_steps(setup.make(), ["sync"]) == 1 and seen["files"] is None   # no file was ever fetched
    assert setup.lines[-1] == ("sync: FAILED. not current: tech:jena. The technical graph was not checked, because its file was "
                               "never fetched: the report step fetches it after a notebook run that loaded, so run the same "
                               "command with --from notebook")
    assert json.loads((setup.run_dir / "steps" / "11-sync.json").read_text(encoding="utf-8"))["status"] == "not current"


def test_the_command_refuses_bad_settings_before_anything_else(tmp_path, capsys):
    assert runner.main(["--stores", str(tmp_path / "missing.toml")]) == 2
    assert "cannot read the local settings file" in capsys.readouterr().err
