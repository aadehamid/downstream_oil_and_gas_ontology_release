"""The runner: each step against stand-ins, every Databricks CLI call as a recorded argument list, the zip built
the same way twice, and the stop for a report that a person must clear."""
import csv
import datetime as dt
import hashlib
import json
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
             ".git/config": "[core]\n", "kpi_store/__pycache__/x.cpython-312.pyc": "x", "kpi_store.toml": "secret = 1\n",
             "sub/stores.toml": 'password = "x"\n', "data/.DS_Store": "x"}
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


def test_a_changed_file_changes_the_checksum(setup):
    before, _ = runner.build_zip(setup.root, setup.tmp / "a.zip")
    (setup.root / "data" / "sample.ttl").write_text("<urn:a> a <urn:C> .\n", encoding="utf-8")
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

LOADED = {"status": "loaded", "count": 58250, "table": "idp_sbx.kpi_store.epm_triples", "dataset_hash": "ab12",
          "marker": {"marked_at": "2026-11-11T12:05:00Z", "count": [58250]}}
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
                               "your name in decided_by on every row you decide, save, then run the same command again")
    with to_clear.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [(r["id"], r["decision"], r["decided_by"]) for r in rows] == [("R001", "accept", ""), ("R002", "accept", ""), ("R003", "", "")]
    assert setup.lines == ["the notebook stopped: 1 row(s) block the load, of 3 in the report",
                           f"  R001 column-renamed {GOLD}: ChangeValue -> Change_Value_Amount; recommended: accept"]


def test_a_run_that_did_not_block_has_no_report_to_clear(setup):
    with pytest.raises(runner.StepFailed, match="run the notebook step first"):
        runner.step_report(setup.make())
    run = Recorder()
    result = runner.step_report(with_notebook(setup, LOADED, run))
    assert run.calls == [] and result["status"] == "no report to clear"
    assert result["line"] == "no row blocks; Databricks marker of 2026-11-11T12:05:00Z, [58250] rows"


# ---- cut -------------------------------------------------------------------------------------------

def pending_report(setup, edit=None):
    """A pending report as the report step leaves it, with the to-clear CSV edited as a person would."""
    setup.pending.mkdir(parents=True)
    report = sample_report()
    (setup.pending / "discovery-report.json").write_text(rep.to_json(report), encoding="utf-8")
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
    with pytest.raises(runner.Stop, match=r"give a decision and your name in decided_by for the row\(s\) that block \(R001\)"):
        runner.step_cut(setup.make(hooks={"cut": lambda *a: called.append(a)}))
    assert called == [] and setup.pending.is_dir()


def test_a_cleared_report_is_cut_once_and_unconfirmed_rows_stay_undecided(setup):
    pending_report(setup, {"R001": {"decided_by": "the owner"}})
    seen = []
    def cut(report_json, release_root, run_dir):
        seen.append((json.loads(Path(report_json).read_text(encoding="utf-8")), release_root, run_dir))
        return {"status": "cut", "version": "1.2.1-correction.1"}
    result = runner.step_cut(setup.make(hooks={"cut": cut}))
    report, root, run_dir = seen[0]
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
    assert runner.cut_with_tool("cleared.json", setup.root, setup.run_dir, run) == {"status": "failed", "why": "this release has no cut tool (kpi_store/cut.py)"}
    (setup.root / "kpi_store" / "cut.py").write_text("", encoding="utf-8")
    assert runner.cut_with_tool("cleared.json", setup.root, setup.run_dir, run) == {"status": "cut"}
    assert run.calls == [[sys.executable, "-m", "kpi_store.cut", "--report", "cleared.json", "--release", str(setup.root)]]
    assert "capture_output" not in run.options[0]   # the tool asks for approval in this terminal
    assert runner.cut_with_tool("cleared.json", setup.root, setup.run_dir, Recorder(lambda cmd: (1, "", "")))["why"] == "the cut tool exited 1"


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
        ["fs", "cp"], ["fs", "cp"]]
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


def test_the_local_loads_are_skipped_when_databricks_did_not_load(setup, monkeypatch):
    for name in runner.LOCAL_LOADS:
        monkeypatch.setitem(runner.STEP_FUNCTIONS, name, lambda ctx: pytest.fail("a local load ran"))
    ctx = with_notebook(setup, {"status": "checked"})
    assert runner.run_steps(ctx, list(runner.LOCAL_LOADS)) == 0
    assert setup.lines == [f"{name}: skipped, because Databricks did not load this release in this run" for name in runner.LOCAL_LOADS]


def test_the_local_steps_pass_the_hooks_on_and_the_summary_lists_the_run(setup, monkeypatch):
    from kpi_store import copy_enterprise, load_fuseki, load_neo4j, sync_check
    seen = {}
    extra = {"urn:sample:tech-graph": "objects.ttl"}
    monkeypatch.setattr(load_fuseki, "run", lambda local, root, extra_graphs=None: seen.update(fuseki=extra_graphs) or {
        "status": "loaded", "graphs": 8, "triples": 33, "dataset_hash": "ab12", "store_hash": "ab12", "server": "reused", "persistent": True})
    monkeypatch.setattr(load_neo4j, "load", lambda local, root, run_dir=None, extra_loads=(): seen.update(neo4j=extra_loads) or {
        "status": "loaded", "database": "neo4j", "nodes": 5, "relationships": 7, "shacl_violations_in_graph": 0,
        "in_graph_constraints": 3, "roundtrip_lost": 0, "roundtrip_added": 0, "graph_hash": "hash-1"})
    monkeypatch.setattr(copy_enterprise, "copy", lambda local, root, **options: seen.update(enterprise=options) or {
        "status": "copied", "database": "businessprocessarchitecturegraph", "nodes": 5, "relationships": 7, "graph_hash": "hash-1"})
    monkeypatch.setattr(sync_check, "check", lambda local, root, extra_graphs=(): seen.update(sync=extra_graphs) or [
        ("jena", "current", "8 graphs"), ("neo4j", "current", "marked")])
    loader = lambda session, store: {}   # noqa: E731
    ctx = setup.make(replace_enterprise=True, hooks={"extra_graphs": lambda root, run_dir: extra, "neo4j_extra_loads": (loader,),
                                                     "own_labels": ("Resource", "TechObject")})
    assert runner.run_steps(ctx, ["fuseki", "neo4j", "enterprise", "sync", "summary"]) == 0
    assert seen["fuseki"] == extra and seen["neo4j"] == (loader,) and seen["sync"] == ("urn:sample:tech-graph",)
    assert seen["enterprise"]["replace"] is True and seen["enterprise"]["own_labels"] == ("Resource", "TechObject")
    assert setup.lines[0].startswith("fuseki: loaded, 8 graphs, 33 triples") and "sync: all 2 lines read current" in setup.lines
    summary = json.loads((setup.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert {k: v["status"] for k, v in summary["steps"].items() if v} == {"fuseki": "loaded", "neo4j": "loaded", "enterprise": "copied", "sync": "current"}
    monkeypatch.setattr(sync_check, "check", lambda local, root, extra_graphs=(): [("jena", "behind", "1 graph missing")])
    assert runner.run_steps(ctx, ["sync"]) == 1 and setup.lines[-1] == "sync: FAILED. not current: jena"
    assert json.loads((setup.run_dir / "steps" / "11-sync.json").read_text(encoding="utf-8"))["rows"][0]["status"] == "behind"


def test_the_command_refuses_bad_settings_before_anything_else(tmp_path, capsys):
    assert runner.main(["--stores", str(tmp_path / "missing.toml")]) == 2
    assert "cannot read the local settings file" in capsys.readouterr().err
