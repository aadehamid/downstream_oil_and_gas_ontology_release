"""One command that runs the whole KPI Store chain, from a cleared report to the sync check.

    py -m kpi_store.runner --stores <local settings file>                 # the whole chain
    py -m kpi_store.runner --stores <file> --dry-run                      # print each step's commands; run nothing
    py -m kpi_store.runner --stores <file> --from fuseki                  # go on from one step, in the newest run
    py -m kpi_store.runner --stores <file> --only sync                    # one step
    py -m kpi_store.runner --stores <file> --skip check,enterprise        # leave steps out

The steps, in order:
  cut         when a cleared report waits in <run folder>/pending, turn it into a correction version (the cut tool)
  check       scripts/check.sh, with bash (Git Bash on Windows)
  zip         the release folder as one zip: files only, sorted, fixed dates, LF line ends; then a copy of
              kpi_store.toml that holds the zip's SHA-256. In a Git checkout the zip holds the files Git tracks
              and no other. In a plain folder it holds every file but caches. Either way the step stops when
              a settings-like file to be zipped holds a password
  volume      create the schema and the volume in Databricks when they are missing
  upload      copy the zip and the settings to the volume
  notebook    import the notebook, submit it as a serverless run, wait, and read its result
  report      when the notebook stopped on a report: fetch it, print the rows that block, write a copy with the
              recommended decisions filled in, and stop
  fuseki      load the local Fuseki and compare the hashes
  neo4j       load the local Neo4j and run every check there
  enterprise  copy the verified graph to the one database on Neo4j Enterprise
  sync        the sync check of all four stores
  summary     one summary of the run

Every Databricks call is the Databricks CLI with the profile of the local settings (OAuth sign-in, no token).
Each step prints one line and writes its result to <run folder>/<run ID>/steps/. Nothing is written into the
release folder.

Clearing a report stays a person's job. When the run stops on a report, open
<run folder>/pending/discovery-report.to-clear.csv. Each row's decision holds the recommended one. Change it where
you disagree, write your name in decided_by on every row you decide, save, and run the same command again. A
row that blocks needs a decision and a name. A row that does not block and has no name stays undecided.

A store load never runs after a notebook run that did not load this release: the run then stops, with exit 3.
--skip leaves a step out on purpose; the last line and the summary then name the steps left out, and the run
does not say that every step passed.

Exit 0 when every requested step ran and passed, 1 when a step failed, 2 on bad settings or arguments, 3 when the
run stopped for a person to act (the last line says what to do).
"""
import argparse
import csv
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from . import local_settings as ls
from . import report as rep
from . import settings as settings_module
from . import setup_check

STEPS = ("cut", "check", "zip", "volume", "upload", "notebook", "report", "fuseki", "neo4j", "enterprise", "sync", "summary")
NOTEBOOK = Path("kpi_store") / "notebook" / "kpi_store_load.py"
NOTEBOOK_NAME = "kpi_store_load"
SETTINGS_NAME = "kpi_store.toml"
PENDING, TO_CLEAR = "pending", "discovery-report.to-clear.csv"
CHECK_PASSED = "all checks passed"
# Never in the zip: Git's folder, caches, and anything that could be a settings file with a password.
SKIP_FOLDERS = (".git", "__pycache__", ".pytest_cache", ".venv", ".mypy_cache", ".ruff_cache")
SKIP_FILES = (".DS_Store", "Thumbs.db", SETTINGS_NAME)
# A file of these kinds that is about to be zipped may not set a password. The one example file may: it holds none.
SECRET_SUFFIXES = (".toml", ".env", ".ini", ".cfg", ".conf", ".properties")
SECRET_LINE = re.compile(rb"(?im)^\s*[\w.\-]*(password|passwd|secret)[\w.\-]*\s*[=:]\s*\S")
SECRET_EXAMPLES = ("kpi_store/stores.example.toml",)
SKIP_SUFFIXES = (".pyc", ".pyo")
# Text files travel with LF line ends, so a checkout that turned them into CRLF still gives the same zip.
TEXT_SUFFIXES = (".py", ".md", ".ttl", ".rq", ".json", ".csv", ".html", ".jsonld", ".yaml", ".yml", ".cypher", ".txt",
                 ".sh", ".nt", ".toml", ".tsv", ".mjs", ".example", ".excalidraw", ".eraser", ".gitattributes", ".gitkeep")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
SHA_LINE = re.compile(r'(?m)^(\s*sha256\s*=\s*)"[0-9a-fA-F]{64}"')
POLL_SECONDS = 15
DONE_STATES = ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")
LOADED = ("loaded", "current", "marked")


class StepFailed(Exception):
    """A step failed. The message says why."""


class Stop(Exception):
    """The run stops for a person to act. The message is the next step."""


# ---- the run's context ------------------------------------------------------------------------------

class Context:
    """One run: the settings, the run's folder, and how commands are run. The tests replace run, sleep, the tools'
    paths and the hooks."""

    def __init__(self, local, release_root, run_id, mode="load", dry_run=False, replace_enterprise=False,
                 run=subprocess.run, sleep=time.sleep, databricks=None, bash=None, hooks=None, out=print):
        self.local, self.release_root = ls.check_outside(local, release_root), Path(release_root).resolve()
        self.settings_path = local.need("settings")
        self.settings = settings_module.load(self.settings_path)
        self.run_root = local.need("run_folder")
        self.run_id, self.run_dir = run_id, self.run_root / run_id
        self.pending = self.run_root / PENDING
        self.mode, self.dry_run, self.replace_enterprise = mode, dry_run, replace_enterprise
        self.run, self.sleep, self.out = run, sleep, out
        self.databricks = databricks or setup_check.find_databricks(local)
        self.bash = bash or setup_check.find_bash(local.bash)
        self.hooks = {"cut": cut_with_tool, "extra_graphs": None, "neo4j_extra_loads": (), "own_rules": None} | (hooks or {})
        self.planned = []   # --dry-run: the commands a step would run
        self.left_out = []  # the steps --skip or --mode check left out, for the summary

    @property
    def volume_path(self):
        s = self.settings
        return f"/Volumes/{s.write_catalog}/{s.write_schema}/{s.volume}"

    def cli(self, *args):
        """A Databricks CLI command as an argument list, with the profile of the local settings."""
        return [str(self.databricks or "databricks"), *args, "--profile", self.local.need("databricks").profile]

    def call(self, cmd, **options):
        """Runs one command with no shell and returns (exit code, stdout, stderr). --dry-run records it instead."""
        cmd = [str(c) for c in cmd]
        if self.dry_run:
            self.planned.append(cmd)
            return 0, "", ""
        try:
            done = self.run(cmd, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL, **options)
        except OSError as err:
            raise StepFailed(f"{Path(cmd[0]).name} could not be started ({type(err).__name__})") from None
        return done.returncode, done.stdout or "", done.stderr or ""

    def step_file(self, name):
        return self.run_dir / "steps" / f"{STEPS.index(name) + 1:02d}-{name}.json"

    def earlier(self, name):
        """An earlier step's result in this run, or None."""
        try:
            return json.loads(self.step_file(name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def last_lines(text, n=3):
    return " | ".join(line.strip() for line in text.strip().splitlines()[-n:])


# ---- cut ------------------------------------------------------------------------------------------------

def cut_with_tool(report_json, release_root, run_dir, run=subprocess.run):
    """Calls the cut tool on a cleared report and returns {"status": "cut"} or {"status": "failed", ...}. The
    tool asks the person who runs it to approve, so it gets this terminal."""
    if not (Path(release_root) / "kpi_store" / "cut.py").is_file():
        return {"status": "failed", "why": "this release has no cut tool (kpi_store/cut.py)"}
    done = run([sys.executable, "-m", "kpi_store.cut", "--report", str(report_json), "--release", str(release_root)],
               cwd=str(release_root))
    return {"status": "cut"} if done.returncode == 0 else {"status": "failed", "why": f"the cut tool exited {done.returncode}"}


def cleared_report(pending):
    """The pending report with the decisions of the to-clear CSV, or Stop when a row that blocks lacks a decision or
    a name. The CSV must hold exactly the report's rows, each once: a row deleted from it is not a decision. A
    row that does not block and has a decision but no name was not confirmed: its decision is dropped. The result
    is checked again after the CSV is applied, on the report itself. Returns (report, IDs of the rows left undecided)."""
    report = rep.read(pending / rep.JSON_NAME)
    path = pending / TO_CLEAR
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        raise Stop(f"the report in {pending} has no {TO_CLEAR}; run the report step again") from None
    blocks = {row["id"]: row["blocks"] for row in report["rows"]}
    found = [row.get("id") or "" for row in rows]
    missing, unknown = sorted(set(blocks) - set(found)), sorted(set(found) - set(blocks))
    if missing or unknown or len(found) != len(set(found)):
        said = "; ".join(text for text in (f"missing: {', '.join(missing)}" if missing else "",
                                           f"not in the report: {', '.join(unknown)}" if unknown else "",
                                           "a row ID occurs twice" if len(found) != len(set(found)) else "") if text)
        raise Stop(f"correct {path}: it must hold exactly the report's {len(blocks)} rows, each once ({said}). Restore the "
                   "rows, decide them, save, then run the same command again")
    open_rows, undecided = [], []
    for row in rows:
        decision, name = (row.get("decision") or "").strip(), (row.get("decided_by") or "").strip()
        if blocks.get(row.get("id")) and not (decision and name):
            open_rows.append(row["id"])
        elif decision and not name:
            row["decision"] = ""
            undecided.append(row["id"])
    if open_rows:
        raise Stop(f"clear the report: in {path} give a decision and your name in decided_by for the row(s) that block "
                   f"({', '.join(open_rows)}), save, then run the same command again")
    confirmed = pending / "confirmed.csv"
    with confirmed.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rep.ROW_FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    try:
        cleared = rep.apply_csv_decisions(report, confirmed)
    except rep.ReportError as err:
        raise Stop(f"correct {path}: {err}. Then run the same command again") from None
    # The last word is the report that goes to the cut, not the CSV it was built from.
    still_open = [row["id"] for row in cleared["rows"] if row["blocks"] and not (row["decision"] and row["decided_by"])]
    if still_open:
        raise Stop(f"clear the report: in {path} give a decision and your name in decided_by for the row(s) that block "
                   f"({', '.join(still_open)}), save, then run the same command again")
    return cleared, undecided


def step_cut(ctx):
    if not (ctx.pending / rep.JSON_NAME).is_file():
        return {"status": "nothing to cut", "line": "no report waits to be cut"}
    if ctx.dry_run:
        return {"status": "dry-run", "line": f"would cut the cleared report in {ctx.pending}"}
    try:
        report, undecided = cleared_report(ctx.pending)
    except rep.ReportError as err:
        raise StepFailed(f"the pending report cannot be read: {err}") from None
    cleared = ctx.run_dir / "cleared-report.json"
    write_text(cleared, rep.to_json(report))
    result = ctx.hooks["cut"](cleared, ctx.release_root, ctx.run_dir)
    if result.get("status") != "cut":
        raise StepFailed(f"the cut did not finish: {result.get('why', result.get('status'))}. The report stays in {ctx.pending}")
    # A report is cut once: its files leave the pending folder and stay with the run that cut them.
    shutil.move(str(ctx.pending), str(ctx.run_dir / "cut-report"))
    decided = sum(1 for row in report["rows"] if row["decision"])
    return {**result, "report": str(cleared), "decided_rows": decided, "undecided_rows": undecided,
            "line": f"cut the cleared report: {decided} row(s) decided, {len(undecided)} left undecided"}


# ---- check ----------------------------------------------------------------------------------------------

def step_check(ctx):
    if ctx.bash is None and not ctx.dry_run:
        raise StepFailed("bash was not found, and scripts/check.sh is a bash script. Install Git for Windows, or name "
                         "bash.exe in [tools] bash; py -m kpi_store.setup_check --only bash says more")
    cmd = [str(ctx.bash or "bash"), "scripts/check.sh"]
    code, out, err = ctx.call(cmd, cwd=str(ctx.release_root))
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would run the check script"}
    write_text(ctx.run_dir / "check.log", out + err)
    lines = [line for line in out.strip().splitlines() if line.strip()]
    if code != 0 or not lines or lines[-1].strip() != CHECK_PASSED:
        raise StepFailed(f"scripts/check.sh did not pass (exit {code}); read {ctx.run_dir / 'check.log'}")
    return {"status": "passed", "log": str(ctx.run_dir / "check.log"), "line": CHECK_PASSED}


# ---- zip ------------------------------------------------------------------------------------------------

def tracked_files(root, run=subprocess.run):
    """The files Git tracks in a checkout, as paths relative to it. Raises StepFailed when Git cannot say."""
    try:
        done = run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, stdin=subprocess.DEVNULL)
    except OSError:
        done = None
    if done is None or done.returncode != 0:
        raise StepFailed("the release folder is a Git checkout, but git ls-files did not run. The zip holds only the "
                         "files Git tracks there, so Git must be on PATH")
    return [Path(name) for name in done.stdout.decode("utf-8").split("\0") if name]


def release_files(root, run=subprocess.run):
    """The release's files as sorted (path inside the zip, file) pairs. Folders are not entries.

    In a Git checkout these are the files Git tracks, and no other: a file someone left in the folder is not in
    the zip. A plain folder has no such list, so there every file counts except caches. In both cases a
    settings-like file (SECRET_SUFFIXES, or a name that starts with .env) that sets a password stops the step:
    the zip is uploaded, and a password must not travel in it."""
    root = Path(root)
    if (root / ".git").exists():
        candidates = tracked_files(root, run)
    else:
        candidates = [path.relative_to(root) for path in root.rglob("*")]
    found = []
    for relative in candidates:
        path = root / relative
        if any(part in SKIP_FOLDERS for part in relative.parts[:-1]) or not path.is_file() or path.is_symlink():
            continue
        if path.name in SKIP_FILES or path.suffix in SKIP_SUFFIXES or relative.parts[0] in SKIP_FOLDERS:
            continue
        name = relative.as_posix()
        if (path.suffix.lower() in SECRET_SUFFIXES or path.name.lower().startswith(".env")) and name not in SECRET_EXAMPLES \
                and SECRET_LINE.search(path.read_bytes()):
            raise StepFailed(f"{name} in the release folder sets a password. The zip is uploaded, so nothing was zipped. "
                             "Move the file outside the release folder")
        found.append((name, path))
    return sorted(found)


def build_zip(root, target, run=subprocess.run):
    """Writes the release zip and returns (SHA-256, number of files). The same files give the same bytes: entries
    are sorted, every entry has one fixed date and mode, and text files get LF line ends."""
    target = Path(target)
    files = release_files(root, run)   # read in full first: a refused file must leave nothing written
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, path in files:
            data = path.read_bytes()
            if path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_SUFFIXES:
                data = data.replace(b"\r\n", b"\n")
            info = zipfile.ZipInfo(name, ZIP_DATE)
            info.compress_type, info.create_system, info.external_attr = zipfile.ZIP_DEFLATED, 3, 0o644 << 16
            z.writestr(info, data, compresslevel=9)
    return settings_module.file_sha256(target), len(files)


def settings_with_checksum(text, sha256):
    """The settings file's text with [release] sha256 set to the zip's checksum. The file must hold exactly one
    sha256 line."""
    new, count = SHA_LINE.subn(lambda m: f'{m.group(1)}"{sha256}"', text)
    if count != 1:
        raise StepFailed(f"{SETTINGS_NAME} must hold exactly one sha256 line of 64 hexadecimal digits in [release]")
    return new


def step_zip(ctx):
    target = ctx.run_dir / "upload" / ctx.settings.zip_name
    if ctx.dry_run:
        return {"status": "dry-run", "line": f"would write {target} and a {SETTINGS_NAME} with its SHA-256"}
    if ls.is_inside(ctx.run_dir, ctx.release_root):
        raise StepFailed("the run folder is inside the release folder; the zip would hold itself")
    sha256, count = build_zip(ctx.release_root, target, ctx.run)
    text = settings_with_checksum(ctx.settings_path.read_text(encoding="utf-8"), sha256)
    write_text(target.parent / SETTINGS_NAME, text)
    try:   # the copy is read back as the notebook will read it
        settings_module.check_zip(settings_module.load(target.parent / SETTINGS_NAME))
    except settings_module.SettingsError as err:
        raise StepFailed(f"the settings copy for the upload is wrong: {err}") from None
    return {"status": "built", "zip": str(target), "sha256": sha256, "files": count,
            "settings": str(target.parent / SETTINGS_NAME), "bytes": target.stat().st_size,
            "line": f"{ctx.settings.zip_name}: {count} files, SHA-256 {sha256}"}


# ---- Databricks: the volume, the upload, the notebook ---------------------------------------------------

def step_volume(ctx):
    s = ctx.settings
    schema, volume = f"{s.write_catalog}.{s.write_schema}", f"{s.write_catalog}.{s.write_schema}.{s.volume}"
    by_hand = (f"Run these two statements in a Databricks SQL editor, then run the same command again: "
               f"CREATE SCHEMA IF NOT EXISTS {schema}; CREATE VOLUME IF NOT EXISTS {volume};")
    made = []
    for what, get, create in (("schema", ctx.cli("schemas", "get", schema), ctx.cli("schemas", "create", s.write_schema, s.write_catalog)),
                              ("volume", ctx.cli("volumes", "read", volume),
                               ctx.cli("volumes", "create", s.write_catalog, s.write_schema, s.volume, "MANAGED"))):
        code, _, _ = ctx.call(get)
        if code == 0 and not ctx.dry_run:
            continue
        code, _, err = ctx.call(create)
        if code != 0:
            raise StepFailed(f"the {what} could not be created ({last_lines(err, 1)}). {by_hand}")
        made.append(what)
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would create the schema and the volume when missing"}
    return {"status": "ready", "created": made,
            "line": f"{volume} is there" + (f" (created: {', '.join(made)})" if made else "")}


def step_upload(ctx):
    built = ctx.earlier("zip")
    if not ctx.dry_run and (not built or not Path(built["zip"]).is_file()):
        raise StepFailed("there is no zip in this run; run the zip step first")
    files = [built["zip"], built["settings"]] if built else [f"<run>/upload/{ctx.settings.zip_name}", f"<run>/upload/{SETTINGS_NAME}"]
    for path in files:   # the zip first: the settings must never name a zip that is not there yet
        code, _, err = ctx.call(ctx.cli("fs", "cp", path, f"dbfs:{ctx.volume_path}/{Path(path).name}", "--overwrite"))
        if code != 0:
            raise StepFailed(f"{Path(path).name} could not be uploaded ({last_lines(err, 1)})")
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would upload the zip and the settings"}
    return {"status": "uploaded", "volume": ctx.volume_path, "sha256": built["sha256"],
            "line": f"{ctx.settings.zip_name} and {SETTINGS_NAME} are in {ctx.volume_path}"}


def submit_request(ctx):
    """The one-time run: one notebook task and no cluster, which Databricks runs on serverless compute."""
    folder = ctx.local.need("databricks").workspace_folder
    return {"run_name": f"KPI Store load {ctx.run_id}",
            "tasks": [{"task_key": NOTEBOOK_NAME,
                       "notebook_task": {"notebook_path": f"{folder}/{NOTEBOOK_NAME}", "source": "WORKSPACE",
                                         "base_parameters": {"settings_path": f"{ctx.volume_path}/{SETTINGS_NAME}",
                                                             "mode": ctx.mode}}}]}


def _json(text, what):
    try:
        return json.loads(text)
    except ValueError:
        raise StepFailed(f"the Databricks CLI's answer to {what} is not JSON") from None


def wait_for_run(ctx, run_id):
    """Polls the run until it ends or the wait is over. Returns the run as the CLI describes it."""
    limit = ctx.local.need("databricks").timeout_minutes * 60
    waited = 0
    while True:
        code, out, err = ctx.call(ctx.cli("jobs", "get-run", str(run_id), "--output", "json"))
        if code != 0:
            raise StepFailed(f"the run {run_id} could not be read ({last_lines(err, 1)})")
        described = _json(out, "jobs get-run")
        if (described.get("state") or {}).get("life_cycle_state") in DONE_STATES:
            return described
        if waited >= limit:
            raise StepFailed(f"the notebook run {run_id} still runs after {limit // 60} minutes. It goes on in Databricks; "
                             "run the same command with --from notebook to wait for it again")
        ctx.sleep(POLL_SECONDS)
        waited += POLL_SECONDS


def step_notebook(ctx):
    folder = ctx.local.need("databricks").workspace_folder
    request_file = ctx.run_dir / "submit.json"
    waiting = (ctx.earlier("notebook") or {}) if not ctx.dry_run else {}
    run_id = waiting.get("databricks_run_id") if waiting.get("status") == "waiting" else None
    if run_id is None:
        for cmd, what in ((ctx.cli("workspace", "mkdirs", folder), "the workspace folder could not be made"),
                          (ctx.cli("workspace", "import", f"{folder}/{NOTEBOOK_NAME}", "--file", str(ctx.release_root / NOTEBOOK),
                                   "--format", "SOURCE", "--language", "PYTHON", "--overwrite"), "the notebook could not be imported")):
            code, _, err = ctx.call(cmd)
            if code != 0:
                raise StepFailed(f"{what} ({last_lines(err, 1)})")
        if not ctx.dry_run:
            write_text(request_file, json.dumps(submit_request(ctx), indent=2) + "\n")
        # The request goes by file: quotes inside an argument do not survive every Windows command line.
        code, out, err = ctx.call(ctx.cli("jobs", "submit", "--no-wait", "--json", f"@{request_file}", "--output", "json"))
        if code != 0:
            raise StepFailed(f"the notebook run could not be submitted ({last_lines(err, 1)})")
        if ctx.dry_run:
            ctx.planned.append(["(the request)", json.dumps(submit_request(ctx))])
            ctx.call(ctx.cli("jobs", "get-run", "<run ID>", "--output", "json"))
            ctx.call(ctx.cli("jobs", "get-run-output", "<task run ID>", "--output", "json"))
            return {"status": "dry-run", "line": "would import the notebook, submit it, wait and read its result"}
        run_id = _json(out, "jobs submit").get("run_id")
        if not run_id:
            raise StepFailed("the Databricks CLI gave no run ID for the submitted run")
        write_text(ctx.step_file("notebook"), json.dumps({"status": "waiting", "databricks_run_id": run_id}, indent=2) + "\n")
    described = wait_for_run(ctx, run_id)
    # The run ended, so a later call must submit a new one, whatever this one's result is.
    write_text(ctx.step_file("notebook"), json.dumps({"status": "ended", "databricks_run_id": run_id}, indent=2) + "\n")
    tasks = described.get("tasks") or [{}]
    task_run = tasks[0].get("run_id") or run_id
    code, out, err = ctx.call(ctx.cli("jobs", "get-run-output", str(task_run), "--output", "json"))
    if code != 0:
        raise StepFailed(f"the run's output could not be read ({last_lines(err, 1)})")
    output = _json(out, "jobs get-run-output")
    state = described.get("state") or {}
    if state.get("result_state") != "SUCCESS":
        why = output.get("error") or state.get("state_message") or state.get("result_state") or "no reason given"
        raise StepFailed(f"the notebook run {run_id} did not succeed: {str(why).strip().splitlines()[0][:300]}")
    try:
        summary = json.loads((output.get("notebook_output") or {}).get("result") or "")
    except ValueError:
        raise StepFailed(f"the notebook run {run_id} ended without its JSON summary") from None
    write_text(ctx.run_dir / "notebook-result.json", json.dumps(summary, indent=2) + "\n")
    status = summary.get("status")
    said = {"blocked": f"stopped on a report: {len(summary.get('blocking_rows', []))} row(s) block",
            "checked": "checked: no row blocks; nothing was loaded (mode check)"}.get(
        status, f"{status}: {summary.get('count')} triples in {summary.get('table')}, hash {summary.get('dataset_hash')}")
    if status not in ("blocked", "checked") + LOADED:
        raise StepFailed(f"the notebook ended with status {status}")
    return {"status": status, "databricks_run_id": run_id, "summary": summary, "line": f"notebook run {run_id} {said}"}


# ---- the report -----------------------------------------------------------------------------------------

def prefilled_csv(report):
    """The report's rows as CSV with each empty decision filled with the recommended one. decided_by stays empty:
    the person who confirms a row writes their name there."""
    rows = [{**row, "decision": row["decision"] or row["recommended"]} for row in report["rows"]]
    return rep.to_csv({**report, "rows": rows})


def blocking_lines(report):
    return [f"  {row['id']} {row['kind']} {row['object']}: {row['ontology_value']} -> {row['found_value']}; "
            f"recommended: {row['recommended'] or 'none'}" for row in report["rows"] if row["blocks"]]


def step_report(ctx):
    if ctx.dry_run:
        for name in (rep.JSON_NAME, rep.CSV_NAME):
            ctx.call(ctx.cli("fs", "cp", f"dbfs:{ctx.volume_path}/reports/<report run>/{name}", str(ctx.pending / name), "--overwrite"))
        return {"status": "dry-run", "line": "would fetch the report when the notebook stopped on one"}
    notebook = ctx.earlier("notebook")
    if not notebook or "summary" not in notebook:
        raise StepFailed("there is no notebook result in this run; run the notebook step first")
    summary = notebook["summary"]
    if summary.get("status") != "blocked":
        marker = summary.get("marker") or {}
        return {"status": "no report to clear", "marker": marker,
                "line": "no row blocks" + (f"; Databricks marker of {marker.get('marked_at')}, {marker.get('count')} rows" if marker else "")}
    ctx.pending.mkdir(parents=True, exist_ok=True)
    for key, name in (("report_json", rep.JSON_NAME), ("report_csv", rep.CSV_NAME)):
        code, _, err = ctx.call(ctx.cli("fs", "cp", "dbfs:" + summary[key], str(ctx.pending / name), "--overwrite"))
        if code != 0:
            raise StepFailed(f"{name} could not be fetched from the volume ({last_lines(err, 1)})")
    try:
        report = rep.read(ctx.pending / rep.JSON_NAME)
    except rep.ReportError as err:
        raise StepFailed(str(err)) from None
    to_clear = ctx.pending / TO_CLEAR
    write_text(to_clear, prefilled_csv(report))
    shown = blocking_lines(report)
    ctx.out(f"the notebook stopped: {len(shown)} row(s) block the load, of {len(report['rows'])} in the report")
    for text in shown:
        ctx.out(text)
    write_text(ctx.step_file("report"), json.dumps({"status": "report to clear", "to_clear": str(to_clear),
                                                    "blocking_rows": [r["id"] for r in report["rows"] if r["blocks"]]}, indent=2) + "\n")
    raise Stop(f"clear the report: edit the decision column of {to_clear} (each holds the recommended decision), write "
               "your name in decided_by on every row you decide, save, then run the same command again")


# ---- the local stores -----------------------------------------------------------------------------------

def not_loaded_reason(ctx):
    """Why a store load may not run: this run's notebook step did not load the release. None when it did, or when
    this run has no notebook step (--only and --from may run the loads on their own)."""
    notebook = ctx.earlier("notebook")
    if notebook is None or notebook.get("status") in LOADED:
        return None
    status = notebook.get("status")
    if status == "blocked":
        return ("the notebook stopped on a report, so Databricks does not hold this release. Clear the report, then "
                "run the same command again without --skip report")
    if status == "waiting":
        return ("the notebook run has not ended, so Databricks may not hold this release yet. Run the same command "
                "with --from notebook to wait for it")
    return (f"the notebook step ended as {status}, so Databricks does not hold this release. Run the same command "
            "with --from notebook")


def step_fuseki(ctx):
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would start or reuse Fuseki, load it and compare the hashes"}
    from . import load_fuseki
    extra = ctx.hooks["extra_graphs"](ctx.release_root, ctx.run_dir) if ctx.hooks["extra_graphs"] else None
    try:
        result = load_fuseki.run(ctx.local, ctx.release_root, extra_graphs=extra)
    except (load_fuseki.FusekiError, OSError) as err:
        raise StepFailed(str(err) if isinstance(err, load_fuseki.FusekiError) else f"Fuseki did not answer ({type(err).__name__})") from None
    if result["status"] == "mismatch":
        raise StepFailed(load_fuseki.line(result))
    return {**result, "line": load_fuseki.line(result).split(": ", 1)[1]}


def step_neo4j(ctx):
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would load the local Neo4j and run every check there"}
    from . import load_neo4j
    try:
        result = load_neo4j.load(ctx.local, ctx.release_root, run_dir=ctx.run_dir / "neo4j",
                                 extra_loads=ctx.hooks["neo4j_extra_loads"])
    except load_neo4j.LoadError as err:
        raise StepFailed(str(err)) from None
    except Exception as err:   # a driver error's text can carry an address
        raise StepFailed(f"the local Neo4j did not answer ({type(err).__name__})") from None
    return {**result, "line": load_neo4j.line(result).split(": ", 1)[1]}


def step_enterprise(ctx):
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would copy the verified graph to the Enterprise database"}
    from . import copy_enterprise
    rules = ctx.hooks["own_rules"] or copy_enterprise.OWN_RULES
    try:
        with (ctx.run_dir / "enterprise.log").open("a", encoding="utf-8", newline="\n") as log:
            result = copy_enterprise.copy(ctx.local, ctx.release_root, replace=ctx.replace_enterprise,
                                          extra_loads=ctx.hooks["neo4j_extra_loads"], own_rules=rules, log=log)
    except copy_enterprise.Refused as err:
        raise StepFailed(str(err)) from None
    except Exception as err:
        raise StepFailed(f"a Neo4j server did not answer, or a statement failed ({type(err).__name__})") from None
    return {**result, "line": copy_enterprise.line(result).split(": ", 1)[1]}


def step_sync(ctx):
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would read the four stores and judge each"}
    from . import sync_check
    extra = ctx.hooks["extra_graphs"](ctx.release_root, ctx.run_dir) if ctx.hooks["extra_graphs"] else {}
    rows = sync_check.check(ctx.local, ctx.release_root, extra_graphs=tuple(extra or ()))
    for text in sync_check.lines(rows):
        ctx.out("  " + text)
    result = {"rows": [{"store": s, "status": status, "why": why} for s, status, why in rows]}
    if not sync_check.all_current(rows):
        behind = [s for s, status, _ in rows if status != "current"]
        write_text(ctx.step_file("sync"), json.dumps({**result, "status": "not current"}, indent=2) + "\n")
        raise StepFailed(f"not current: {', '.join(behind)}")
    return {**result, "status": "current", "line": f"all {len(rows)} lines read current"}


def step_summary(ctx):
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would print the run's summary"}
    steps = {name: ctx.earlier(name) for name in STEPS if name != "summary"}
    ctx.out(f"summary of run {ctx.run_id}:")
    for name, result in steps.items():
        if name in ctx.left_out:
            ctx.out(f"  {name:<11} left out of this run")
        elif result:
            ctx.out(f"  {name:<11} {result.get('status')}")
    write_text(ctx.run_dir / "summary.json", json.dumps({"run": ctx.run_id, "left_out": list(ctx.left_out), "steps": steps},
                                                        indent=2, default=str) + "\n")
    return {"status": "written", "summary": str(ctx.run_dir / "summary.json"),
            "line": f"the run's files are in {ctx.run_dir}"}


STEP_FUNCTIONS = {"cut": step_cut, "check": step_check, "zip": step_zip, "volume": step_volume, "upload": step_upload,
                  "notebook": step_notebook, "report": step_report, "fuseki": step_fuseki, "neo4j": step_neo4j,
                  "enterprise": step_enterprise, "sync": step_sync, "summary": step_summary}
LOCAL_LOADS = ("fuseki", "neo4j", "enterprise", "sync")


# ---- the chain ------------------------------------------------------------------------------------------

def selected(only=None, start=None, skip=()):
    """The steps to run, in order."""
    names = list(STEPS)
    if start:
        names = names[names.index(start):]
    if only:
        names = [n for n in names if n in only]
    return [n for n in names if n not in skip]


def run_steps(ctx, names):
    """Runs the steps in order. Returns the exit code: 0, 1 (a step failed) or 3 (stopped for a person)."""
    for name in names:
        ctx.planned = []
        reason = not_loaded_reason(ctx) if name in LOCAL_LOADS and not ctx.dry_run else None
        if reason:   # a load that did not run is never a pass
            ctx.out(f"{name}: STOPPED. Next step: {reason}")
            return 3
        try:
            result = STEP_FUNCTIONS[name](ctx)
        except Stop as stop:
            ctx.out(f"{name}: STOPPED. Next step: {stop}")
            return 3
        except StepFailed as err:
            if not ctx.dry_run:
                kept = ctx.earlier(name) if name in ("sync", "notebook") else None
                # A notebook run that is still waited for keeps its record: the record holds the Databricks run ID,
                # and without it the next run would submit a second job.
                if name == "notebook" and (kept or {}).get("status") != "waiting":
                    kept = None
                write_text(ctx.step_file(name), json.dumps(kept or {"status": "failed", "why": str(err)}, indent=2) + "\n")
            ctx.out(f"{name}: FAILED. {err}")
            return 1
        if ctx.dry_run:
            ctx.out(f"{name}: {result['line']}")
            for cmd in ctx.planned:
                ctx.out("  " + json.dumps(cmd))
            continue
        write_text(ctx.step_file(name), json.dumps(result, indent=2, default=str) + "\n")
        ctx.out(f"{name}: {result['line']}")
    return 0


def new_run_id(now=None):
    return (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def newest_run(run_root):
    """The newest run's ID in the run folder, or None. Run IDs are UTC times, so they sort by name."""
    runs = sorted(p.name for p in Path(run_root).glob("[0-9]*T[0-9]*Z") if p.is_dir()) if Path(run_root).is_dir() else []
    return runs[-1] if runs else None


def step_list(text):
    names = [n for n in (text or "").split(",") if n]
    unknown = [n for n in names if n not in STEPS]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown step {unknown[0]}; the steps are {', '.join(STEPS)}")
    return names


def main(argv=None, **context_options):
    ap = argparse.ArgumentParser(prog="kpi_store.runner", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--from", dest="start", choices=STEPS, help="start at this step, in the newest run")
    ap.add_argument("--only", type=step_list, help="run only these steps (comma-separated), in the newest run")
    ap.add_argument("--skip", type=step_list, default=[], help="leave these steps out (comma-separated)")
    ap.add_argument("--run-id", help="the run to go on with (default: a new run, or the newest with --from or --only)")
    ap.add_argument("--mode", choices=("load", "check"), default="load",
                    help="check stops the notebook after its report and loads nothing (default load)")
    ap.add_argument("--replace-enterprise", action="store_true",
                    help="let the copy replace the KPI Store's nodes the Enterprise database already holds")
    ap.add_argument("--dry-run", action="store_true", help="print each step's commands as argument lists and run nothing")
    args = ap.parse_args(argv)
    try:
        local = ls.load(ls.locate(args.stores), release_root=Path(args.release))
        run_root = local.need("run_folder")
        run_id = args.run_id or ((args.start or args.only) and newest_run(run_root)) or new_run_id()
        ctx = Context(local, args.release, run_id, mode=args.mode, dry_run=args.dry_run,
                      replace_enterprise=args.replace_enterprise, **context_options)
    except (ls.LocalSettingsError, settings_module.SettingsError) as err:
        print(f"runner: {err}", file=sys.stderr)
        return 2
    names = selected(args.only, args.start, args.skip)
    ctx.left_out = [n for n in args.skip if n in selected(args.only, args.start)]
    if args.mode == "check":   # the notebook loads nothing in this mode, so the stores are not loaded either
        ctx.left_out += [n for n in names if n in LOCAL_LOADS]
        names = [n for n in names if n not in LOCAL_LOADS]
    ctx.out(f"run {run_id}{' (dry run)' if args.dry_run else ''}: {', '.join(names)}")
    code = run_steps(ctx, names)
    if code == 0 and not args.dry_run:
        ctx.out(closing_line(ctx.left_out))
    return code


def closing_line(left_out):
    """The last line of a run whose steps all passed. It says so only when no step was left out."""
    if not left_out:
        return "every step passed"
    return f"the steps that ran passed; left out: {', '.join(left_out)} (not run, so not checked)"


if __name__ == "__main__":
    sys.exit(main())
