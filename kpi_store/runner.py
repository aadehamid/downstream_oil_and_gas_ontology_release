"""One command that runs the whole KPI Store chain, from a cleared report to the sync check.

    python -m kpi_store.runner --stores <local settings file>                 # the whole chain
    python -m kpi_store.runner --stores <file> --dry-run                      # print each step's commands; run nothing
    python -m kpi_store.runner --stores <file> --from fuseki                  # go on from one step, in the newest run
    python -m kpi_store.runner --stores <file> --only sync                    # one step
    python -m kpi_store.runner --stores <file> --skip check,enterprise        # leave steps out
    python -m kpi_store.runner --stores <file> --reset                        # empty the stores, to load them again

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
              recommended decisions filled in, and stop. When it loaded: fetch the technical graph's file, which
              the notebook built from the workspace, into <run folder>/tech-graph
  fuseki      load the local Fuseki and compare the hashes; then the technical graph
  neo4j       load the local Neo4j and run every check there; then the technical graph
  enterprise  copy the verified graph to the one database on Neo4j Enterprise; then the technical graph
  sync        the sync check of all four stores, with the technical graph's lines
  summary     one summary of the run

Every Databricks call is the Databricks CLI with the profile of the local settings (OAuth sign-in, no token).
Each step prints one line and writes its result to <run folder>/<run ID>/steps/. The runner's own files all go
to the run folder, which must lie outside the release folder. One step changes the release folder: the cut step
calls the cut tool, which writes the correction version there. Python may also leave __pycache__ folders beside
the code it runs; the zip leaves them out.

What the runner reads: the local settings file (--stores, read by kpi_store.local_settings), this environment's
kpi_store.toml (read by kpi_store.settings), the release folder, and the results of earlier steps in the same run.
What it writes: the run's folder, the schema and the volume in Databricks when they are missing, the two uploaded
files, the imported notebook, and, through the store modules, the three stores.

How this file is laid out: the constants, the run's context, then one block per step in the order of the list
above, then the chain that runs them. Each step is a function step_<name>(ctx). It returns a dict with a "status"
and the "line" to print, raises StepFailed when it fails, and raises Stop when a person must act before the run
can go on.

Clearing a report stays a person's job. When the run stops on a report, open
<run folder>/pending/discovery-report.to-clear.csv. Each row's decision holds the recommended one. Change it where
you disagree, write your role or initials in decided_by on every row you decide, save, and run the same command
again. A row that blocks needs a decision and a decided_by. A row that does not block and has no decided_by stays
undecided. decided_by is a role or initials, such as "the ontology owner"; the cut tool holds the rule
(kpi_store.cut.is_role), and a name with an e-mail address or a long number is refused. The next run hands the
report to the cut tool, which shows its plan and asks you to approve it in the terminal.

A store load does not run when the notebook step of the same run did not load this release: the run then stops,
with exit 3. A run that has no notebook step of its own (--only or --from on a new run ID) is not held back.
--skip, --only, --from and --mode check each leave steps out; the last line and the summary then name the steps
left out, and the run does not say that every step passed. Only a run of the whole chain says that.

--reset runs no step. It empties the stores the steps loaded: the Enterprise database's KPI Store nodes, the local
Neo4j database, the local Fuseki dataset and the four Databricks tables (kpi_store.reset). It first prints what it
will delete in each store and asks for the word reset; --yes leaves the question out, and --dry-run prints and
deletes nothing. With --reset, --only and --skip take store names: enterprise, neo4j, fuseki, databricks. It keeps
the release folder, the run folder and, in Databricks, the schemas, the volume and the notebook. The next plain
run then loads every store again.

Exit 0 when every requested step ran and passed, 1 when a step failed, 2 on bad settings or arguments, 3 when the
run stopped for a person to act (the last line says what to do). A reset ends with 0 when every store of
its selection holds nothing of the KPI Store. It ends with 1 when a store was left alone or failed, when Ctrl+C
stopped it, or when the word was not typed; --skip leaves a store out on purpose.
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
import tomllib
import traceback
import zipfile
from pathlib import Path

from . import cut as cut_tool
from . import local_settings as ls
from . import report as rep
from . import settings as settings_module
from . import setup_check

# The steps in the order they run. A step's place here is also its number in <run>/steps/NN-<name>.json.
ENVIRONMENT_KEY = "kpi_store"   # the name of the notebook run's one serverless environment inside its request
STEPS = ("cut", "check", "zip", "volume", "upload", "notebook", "report", "fuseki", "neo4j", "enterprise", "sync", "summary")
NOTEBOOK = Path("kpi_store") / "notebook" / "kpi_store_load.py"   # inside the release folder
NOTEBOOK_NAME = "kpi_store_load"   # the notebook's name in the workspace folder, and the run's task key
SETTINGS_NAME = "kpi_store.toml"
# A fetched report waits for a person in <run folder>/pending. It lies beside the runs, not inside one, because the
# run that cuts it is a later run than the one that fetched it. TO_CLEAR is the CSV the person edits. CONFIRMED is
# the decisions as the runner read them back, which is the file the cut tool gets.
PENDING, TO_CLEAR, CONFIRMED = "pending", "discovery-report.to-clear.csv", "confirmed.csv"
# The line scripts/check.sh prints at its end, when no check stopped it. The check step accepts no other last line.
CHECK_PASSED = "all checks passed"
# Never in the zip: Git's folder, caches, and anything that could be a settings file with a password.
SKIP_FOLDERS = (".git", "__pycache__", ".pytest_cache", ".venv", ".mypy_cache", ".ruff_cache")
SKIP_FILES = (".DS_Store", "Thumbs.db", SETTINGS_NAME)
# A file of these kinds that is about to be zipped is parsed, and may not give a secret a value (secret_keys).
SECRET_SUFFIXES = (".toml", ".env", ".ini", ".cfg", ".conf", ".properties")
SECRET_WORDS = ("password", "passwd", "pwd", "secret", "token")
KEY_PARTS = re.compile(r"[A-Za-z0-9]+")    # the words of a setting's name: NEO4J_PASSWORD gives NEO4J, PASSWORD
PLACEHOLDER = re.compile(r"^<[^<>]*>$")    # a value such as <password>: how an example file shows where a secret goes
SKIP_SUFFIXES = (".pyc", ".pyo")           # compiled Python: a cache, rebuilt wherever the code runs
# Text files travel with LF line ends, so a checkout that turned them into CRLF still gives the same zip.
TEXT_SUFFIXES = (".py", ".md", ".ttl", ".rq", ".json", ".csv", ".html", ".jsonld", ".yaml", ".yml", ".cypher", ".txt",
                 ".sh", ".nt", ".toml", ".tsv", ".mjs", ".example", ".excalidraw", ".eraser", ".gitattributes", ".gitkeep")
# Every zip entry gets this date, the earliest a zip can hold. The zip's bytes, and so its SHA-256, then do not
# depend on when a file was written or checked out.
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
# The sha256 line of kpi_store.toml. Group 1 is the text before the value, kept as it is when the value is replaced.
SHA_LINE = re.compile(r'(?m)^(\s*sha256\s*=\s*)"[0-9a-fA-F]{64}"')
POLL_SECONDS = 15   # the wait between two looks at the notebook run
DONE_STATES = ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")   # the life-cycle states of a Databricks run that has ended
# The notebook's statuses that mean Databricks holds this release: loaded in this run, already current, or already
# held with only the marker written (kpi_store.load_databricks.load). When this run's notebook step ended with any
# other status, the store loads are stopped (not_loaded_reason).
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
        # Refused here, before any step: the local settings file and the folders the run writes to must lie outside
        # this release folder, which the zip step packs and the upload step sends.
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
        # The hooks let a caller, such as a test, swap the cut for one that answers its own prompts, and add graphs,
        # loads or rules beside the ontology's. The command line sets none of them.
        self.hooks = {"cut": cut_with_tool, "extra_graphs": None, "neo4j_extra_loads": (), "own_rules": None} | (hooks or {})
        self.planned = []   # --dry-run: the commands a step would run
        self.left_out = []  # the steps --skip or --mode check left out, for the summary

    @property
    def volume_path(self):
        """The volume as a file path: /Volumes/<catalog>/<schema>/<volume>. The zip and the settings land here."""
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
            # No input is offered: a command that asked a question would otherwise hang the run.
            done = self.run(cmd, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL, **options)
        except OSError as err:
            raise StepFailed(f"{Path(cmd[0]).name} could not be started ({type(err).__name__})") from None
        return done.returncode, done.stdout or "", done.stderr or ""

    def step_file(self, name):
        """The file that holds a step's result in this run: steps/NN-<name>.json, numbered in step order."""
        return self.run_dir / "steps" / f"{STEPS.index(name) + 1:02d}-{name}.json"

    def earlier(self, name):
        """An earlier step's result in this run, or None."""
        try:
            return json.loads(self.step_file(name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


def write_text(path, text):
    """Writes text as UTF-8 with LF line ends on every platform, and makes the folder when it is missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def last_lines(text, n=3):
    """The last n lines of a command's output as one line, for a step's error message."""
    return " | ".join(line.strip() for line in text.strip().splitlines()[-n:])


# ---- cut ------------------------------------------------------------------------------------------------
# Step 1. A report that a person cleared after an earlier run is turned into a correction version here, before
# anything else, so the check, the zip and every load of this run work on the corrected release.

def cut_command(report_json, release_root, decisions=None):
    """The cut tool's command line: the cleared report, the confirmed decisions as CSV, and the release folder."""
    cmd = [sys.executable, "-m", "kpi_store.cut", "--report", str(report_json)]
    if decisions is not None:
        cmd += ["--decisions", str(decisions)]
    return cmd + ["--release", str(release_root)]


def cut_with_tool(report_json, release_root, run_dir, decisions=None, run=subprocess.run):
    """Calls the cut tool on a cleared report and returns {"status": "cut"} or {"status": "failed", ...}. The
    tool shows its plan and asks the person who runs it to approve, so it gets this terminal: nothing is captured.
    Its exit 0 means cut, recorded or already cut. Its exit 1 means refused or failed. The release folder is then
    unchanged in all but two cases, which the tool's own message names: the cut was committed and Git could not
    tag it, or a write failed and a file could not be put back. This function sees only the exit code, so its
    "why" text points to the tool's message and does not say what state the release is in."""
    if not (Path(release_root) / "kpi_store" / "cut.py").is_file():
        return {"status": "failed", "why": "this release has no cut tool (kpi_store/cut.py)"}
    done = run(cut_command(report_json, release_root, decisions), cwd=str(release_root))
    if done.returncode == 0:
        return {"status": "cut"}
    return {"status": "failed", "why": f"the cut tool exited {done.returncode}: it refused or failed. Its last lines, above, say why and "
                                       "what state the release is in"}


def cleared_report(pending):
    """The pending report with the decisions of the to-clear CSV, or Stop when a row that blocks lacks a decision or
    a decided_by. The CSV must hold exactly the report's rows, each once: a row deleted from it is not a decision. A
    row that does not block and has a decision but no name was not confirmed: its decision is dropped. The result
    is checked again after the CSV is applied, on the report itself. Returns (report, IDs of the rows left undecided)."""
    report = rep.read(pending / rep.JSON_NAME)
    path = pending / TO_CLEAR
    try:
        # utf-8-sig: a spreadsheet may save the CSV with a byte-order mark, which must not become part of "id".
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        raise Stop(f"the report in {pending} has no {TO_CLEAR}; run the report step again") from None
    except UnicodeDecodeError:   # a spreadsheet saved the file in the machine's own encoding
        raise Stop(f"save {path} as UTF-8: in Excel choose File, Save As, and the file type \"CSV UTF-8 (Comma "
                   "delimited)\"; then run the same command again") from None
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
        if name and not cut_tool.is_role(name):   # the cut tool's own rule, asked here so the person corrects it first
            raise Stop(f"correct {path}: decided_by of row {row['id']} is not a role or initials. There, {cut_tool.ROLE_HELP}. "
                       "Then run the same command again")
        if blocks.get(row.get("id")) and not (decision and name):
            open_rows.append(row["id"])
        elif decision and not name:
            row["decision"] = ""
            undecided.append(row["id"])
    if open_rows:
        raise Stop(f"clear the report: in {path} give a decision and write your role or initials in decided_by for the row(s) that block "
                   f"({', '.join(open_rows)}), save, then run the same command again")
    confirmed = pending / CONFIRMED
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
        raise Stop(f"clear the report: in {path} give a decision and write your role or initials in decided_by for the row(s) that block "
                   f"({', '.join(still_open)}), save, then run the same command again")
    return cleared, undecided


def step_cut(ctx):
    """Step 1. Hands the cleared report in <run folder>/pending to the cut tool. With no report there, the step
    does nothing and the run goes on. The cleared report and the confirmed decisions are copied into this run's
    folder first, so the run keeps what was cut."""
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
    decisions = ctx.run_dir / CONFIRMED   # a copy: the pending folder moves when the cut is done
    shutil.copyfile(ctx.pending / CONFIRMED, decisions)
    result = ctx.hooks["cut"](cleared, ctx.release_root, ctx.run_dir, decisions)
    if result.get("status") != "cut":
        raise StepFailed(f"the cut did not finish: {result.get('why', result.get('status'))}. The report stays in {ctx.pending}")
    # A report is cut once: its files leave the pending folder and stay with the run that cut them.
    shutil.move(str(ctx.pending), str(ctx.run_dir / "cut-report"))
    decided = sum(1 for row in report["rows"] if row["decision"])
    return {**result, "report": str(cleared), "decided_rows": decided, "undecided_rows": undecided,
            "line": f"cut the cleared report: {decided} row(s) decided, {len(undecided)} left undecided"}


def cut_with_library(report_json, release_root, run_dir, decisions=None, ask=input, say=print):
    """The same cut through the tool's library call, in this process: for a caller that answers the prompts itself,
    such as a test. Returns the same dict as cut_with_tool, with the outcome's version tag and record."""
    try:
        outcome = cut_tool.cut(report_json, release_root, decisions, ask=ask, say=say)
    except EOFError:
        return {"status": "failed", "why": "no answer was typed; nothing was changed"}
    except (cut_tool.CutRefused, cut_tool.CutFailed, cut_tool.CutIncomplete) as err:
        return {"status": "failed", "why": f"{type(err).__name__}: {err}"}
    return {"status": "cut", "outcome": outcome.status, "tag": outcome.tag, "committed": outcome.committed,
            "record": Path(outcome.record).as_posix() if outcome.record else "", "files": len(outcome.files)}


# ---- check ----------------------------------------------------------------------------------------------
# Step 2. The release's own checks must pass on the folder as it is now, after the cut, before it is zipped.

def step_check(ctx):
    """Step 2. Runs scripts/check.sh in the release folder and keeps its output in <run>/check.log. The step
    passes only when the exit code is 0 and the last line is CHECK_PASSED: a script that ended early for any
    reason did not run every check."""
    if ctx.bash is None and not ctx.dry_run:
        raise StepFailed("bash was not found, and scripts/check.sh is a bash script. Install Git for Windows, or name "
                         "bash.exe in [tools] bash; python -m kpi_store.setup_check --only bash says more")
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
# Step 3. The zip is what Databricks loads. Two aims shape this block. The zip leaves this machine, so the step
# refuses to zip a settings-like file that gives a secret a value. The test is by file suffix and by the words of
# a setting's name (release_files, secret_keys); a secret in any other kind of file, or under another name, is not
# found. And the zip is built to give the same bytes from the same files: sorted entries, one date, one mode, LF
# line ends. Another version of Python's zlib may still compress differently. That changes the checksum but not
# the check, because the settings copy gets the checksum of the zip this step just built.

def is_secret_key(key):
    """True when a setting's name says its value is a secret: one of its words is password, passwd, pwd, secret
    or token. Words are split at anything but letters and digits, so NEO4J_PASSWORD and api-token are secrets and
    tokens_per_page is not. A name whose last word is env names an environment variable, not a secret
    (password_env)."""
    parts = [part.lower() for part in KEY_PARTS.findall(str(key))]
    return bool(parts) and parts[-1] != "env" and any(part in SECRET_WORDS for part in parts)


def is_secret_value(value):
    """True for a value that could be a real secret: text that is not empty and not a <placeholder>."""
    return isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER.match(value.strip())


def _toml_secrets(node, found):
    """Walks a parsed TOML document, through every table and list, and collects the names that hold a secret."""
    if isinstance(node, dict):
        for key, value in node.items():
            if is_secret_key(key) and is_secret_value(value):
                found.append(str(key))
            _toml_secrets(value, found)
    elif isinstance(node, list):
        for item in node:
            _toml_secrets(item, found)
    return found


def secret_keys(path):
    """The names of the settings in a file that give a secret a value. The file is parsed, not searched: a TOML
    file with the TOML parser, through every table; any other file as KEY=VALUE or KEY: VALUE lines, with an
    optional `export`, quotes and spaces. A TOML file that does not parse cannot be cleared, so it counts as
    holding a secret. The values themselves are never returned."""
    data = Path(path).read_bytes()
    if Path(path).suffix.lower() == ".toml":
        try:
            return _toml_secrets(tomllib.loads(data.decode("utf-8")), [])
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            return ["the file is not valid TOML, so it cannot be checked"]
    found = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line[0] in "#;[":   # a blank line, a comment, or an INI section header
            continue
        if line.lower().startswith(("export ", "set ")):
            line = line.split(None, 1)[1]
        key, sep, value = re.split(r"\s*([=:])\s*", line, maxsplit=1) if re.search(r"[=:]", line) else (line, "", "")
        key, value = key.strip().strip("\"'"), value.strip().strip("\"'")
        if sep and is_secret_key(key) and is_secret_value(value):
            found.append(key)
    return found


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
    settings-like file (SECRET_SUFFIXES, or a name that starts with .env) that gives a secret a value stops the
    step (secret_keys): the zip is uploaded, and a password must not travel in it. The example settings file
    passes for the same reason any file would: its password values are placeholders."""
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
        if path.suffix.lower() in SECRET_SUFFIXES or path.name.lower().startswith(".env"):
            keys = secret_keys(path)
            if keys:
                raise StepFailed(f"{name} in the release folder sets a password or another secret ({', '.join(keys[:3])}). "
                                 "The zip is uploaded, so nothing was zipped. Move the file outside the release folder")
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
            # A fixed date, the Unix system code (3) and one file mode (0o644) for every entry. Taken from the
            # machine that builds the zip, any of them would make the checksum differ between machines.
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
    """Step 3. Writes the zip and a copy of kpi_store.toml that names the zip's SHA-256, both into <run>/upload.
    The settings file on this machine is not changed. The copy is the one the upload step sends, and it is the
    notebook's only way to know which zip to accept."""
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
# Steps 4 to 6. Every call is the Databricks CLI as an argument list (Context.cli), signed in through its profile.

def step_volume(ctx):
    """Step 4. Makes sure the schema and the volume exist, so the upload has a place to land. Each is looked up
    first and created only when the lookup fails. When it cannot be created, for example because the person lacks
    the right, the message gives the two SQL statements to run by hand."""
    s = ctx.settings
    schema, volume = f"{s.write_catalog}.{s.write_schema}", f"{s.write_catalog}.{s.write_schema}.{s.volume}"
    by_hand = (f"Run these two statements in a Databricks SQL editor, then run the same command again: "
               f"CREATE SCHEMA IF NOT EXISTS {schema}; CREATE VOLUME IF NOT EXISTS {volume};")
    made = []
    for what, get, create in (("schema", ctx.cli("schemas", "get", schema), ctx.cli("schemas", "create", s.write_schema, s.write_catalog)),
                              ("volume", ctx.cli("volumes", "read", volume),
                               ctx.cli("volumes", "create", s.write_catalog, s.write_schema, s.volume, "MANAGED"))):
        code, _, _ = ctx.call(get)
        if code == 0 and not ctx.dry_run:   # a dry run goes on, so its plan shows the create command too
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
    """Step 5. Copies the zip and then the settings copy into the volume, over what is there. It sends the two
    files the zip step of this run wrote, so after both copies the settings in the volume name the zip in the
    volume. The two copies are separate calls. When the second fails, the volume holds the new zip beside the
    older settings, which name another checksum: the notebook then refuses the zip until the upload is run again."""
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
    """The one-time run: one notebook task and no cluster, which Databricks runs on serverless compute.

    The run names its serverless environment version, [databricks] environment_version, so that the notebook gets
    the Python it was tested on and not whatever the workspace gives a run that names none. Databricks' page
    "Configure the serverless environment" (dated 2026-10-22) says a notebook task uses the notebook's own
    environment unless a job-level environment overrides it; this is that override. An empty setting leaves it out."""
    bricks = ctx.local.need("databricks")
    task = {"task_key": NOTEBOOK_NAME,
            "notebook_task": {"notebook_path": f"{bricks.workspace_folder}/{NOTEBOOK_NAME}", "source": "WORKSPACE",
                              "base_parameters": {"settings_path": f"{ctx.volume_path}/{SETTINGS_NAME}", "mode": ctx.mode}}}
    request = {"run_name": f"KPI Store load {ctx.run_id}", "tasks": [task]}
    if bricks.environment_version:
        task["environment_key"] = ENVIRONMENT_KEY
        request["environments"] = [{"environment_key": ENVIRONMENT_KEY, "spec": {"environment_version": bricks.environment_version}}]
    return request


def _json(text, what):
    """A CLI answer as parsed JSON, or StepFailed naming the call that gave something else."""
    try:
        return json.loads(text)
    except ValueError:
        raise StepFailed(f"the Databricks CLI's answer to {what} is not JSON") from None


def wait_for_run(ctx, run_id):
    """Polls the run until it ends or the wait is over. Returns the run as the CLI describes it."""
    limit = ctx.local.need("databricks").timeout_minutes * 60   # [databricks] timeout_minutes; 60 when not set
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
    """Step 6. Imports the notebook into the workspace folder, submits it as a one-time serverless run, waits for
    it, and reads the JSON summary the notebook ends with.

    A call that follows an unfinished wait does not submit a second run. As soon as Databricks gives a run ID,
    the step's file records it with the status "waiting". A later call that finds that record waits for the same
    run. When the run has ended, the record changes to "ended", and the next call submits a new run.

    This covers one command after another. It does not cover two commands on the same run at the same time, or
    a command that is stopped between the submit and the write of the record: each of those can submit a second
    run, because nothing locks the step and Databricks is given no key that marks a repeat."""
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
    # The notebook's output belongs to the task's own run, which has another ID than the run that was submitted.
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
# Step 7. The notebook either loaded or stopped on a report. This block fetches what the next steps need in
# each case: the technical graph's file for the store loads, or the report for a person to clear.

def prefilled_csv(report):
    """The report's rows as CSV with each empty decision filled with the recommended one. decided_by stays empty:
    the person who confirms a row writes their name there."""
    rows = [{**row, "decision": row["decision"] or row["recommended"]} for row in report["rows"]]
    return rep.to_csv({**report, "rows": rows})


def blocking_lines(report):
    """One line per row that blocks, as the report step prints it."""
    return [f"  {row['id']} {row['kind']} {row['object']}: {row['ontology_value']} -> {row['found_value']}; "
            f"recommended: {row['recommended'] or 'none'}" for row in report["rows"] if row["blocks"]]


def tech_graph_files(ctx):
    """The technical graph's files as the runner last fetched them, for the store loads; None when there are none."""
    from . import sync_check
    path = sync_check.tech_graph_file(ctx.local)
    return [path] if path else None


def fetch_tech_graph(ctx, summary):
    """Fetches the technical graph's file, which the notebook wrote beside its report, into <run folder>/tech-graph,
    and checks it is the file the notebook loaded. Returns the notebook's result for it, or None when the notebook
    built none."""
    tech = summary.get("tech_graph")
    if not tech or not tech.get("file"):
        return None
    from . import sync_check, tech_graph
    target = ctx.run_root / sync_check.TECH_FOLDER / tech_graph.GRAPH_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    code, _, err = ctx.call(ctx.cli("fs", "cp", "dbfs:" + tech["file"], str(target), "--overwrite"))
    if code != 0:
        raise StepFailed(f"the technical graph's file could not be fetched from the volume ({last_lines(err, 1)})")
    if tech_graph.digest([target]) != tech.get("digest"):
        target.unlink()
        raise StepFailed("the technical graph's file in the volume is not the one the notebook loaded; nothing was kept. "
                         "Run the same command with --from notebook")
    return {"status": tech.get("status"), "digest": tech.get("digest"), "count": tech.get("count"), "file": str(target)}


def step_report(ctx):
    """Step 7. Reads the notebook's summary from this run. When the notebook loaded, fetches the technical graph's
    file. When it stopped on a report, fetches the two report files into <run folder>/pending, writes the CSV to
    clear with the recommended decisions filled in, prints the rows that block, and stops the run (exit 3)."""
    if ctx.dry_run:
        for name in (rep.JSON_NAME, rep.CSV_NAME):
            ctx.call(ctx.cli("fs", "cp", f"dbfs:{ctx.volume_path}/reports/<report run>/{name}", str(ctx.pending / name), "--overwrite"))
        ctx.call(ctx.cli("fs", "cp", f"dbfs:{ctx.volume_path}/reports/<report run>/tech-graph.nq",
                         str(ctx.run_root / "tech-graph" / "tech-graph.nq"), "--overwrite"))
        return {"status": "dry-run", "line": "would fetch the report when the notebook stopped on one"}
    notebook = ctx.earlier("notebook")
    if not notebook or "summary" not in notebook:
        raise StepFailed("there is no notebook result in this run; run the notebook step first")
    summary = notebook["summary"]
    if summary.get("status") != "blocked":
        marker = summary.get("marker") or {}
        tech = fetch_tech_graph(ctx, summary)
        return {"status": "no report to clear", "marker": marker, "tech_graph": tech,
                "line": "no row blocks" + (f"; Databricks marker of {marker.get('marked_at')}, {marker.get('count')} rows" if marker else "")
                        + (f"; technical graph {tech['status']} in Databricks, its file fetched" if tech else "; no technical graph in this run")}
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
    # The step's file is written here: run_steps writes none for a step that raises Stop.
    write_text(ctx.step_file("report"), json.dumps({"status": "report to clear", "to_clear": str(to_clear),
                                                    "blocking_rows": [r["id"] for r in report["rows"] if r["blocks"]]}, indent=2) + "\n")
    raise Stop(f"clear the report: edit the decision column of {to_clear} (each holds the recommended decision), write "
               "your role or initials in decided_by on every row you decide, save, then run the same command again")


# ---- the local stores -----------------------------------------------------------------------------------
# Steps 8 to 10. Databricks comes first on purpose: its comparison with the workspace decides whether this
# release may be loaded anywhere. So before each store load run_steps asks not_loaded_reason, which looks at the
# notebook step of this run only; a run without one is let through. The order of the three loads
# matters too: the local Neo4j has the plugins the checks need, and Neo4j Enterprise gets a copy of the graph
# those checks passed.

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
    """Step 8. Loads the release into the local Fuseki, then the technical graph when its file was fetched
    (kpi_store.load_fuseki). The store's dataset hash must equal the hash of the release files, or the step
    fails."""
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would start or reuse Fuseki, load it and compare the hashes"}
    from . import load_fuseki
    extra = ctx.hooks["extra_graphs"](ctx.release_root, ctx.run_dir) if ctx.hooks["extra_graphs"] else None
    try:
        result = load_fuseki.run(ctx.local, ctx.release_root, extra_graphs=extra, tech_graph_files=tech_graph_files(ctx))
    except (load_fuseki.FusekiError, load_fuseki.ldb.ov.ReleaseError) as err:
        raise StepFailed(str(err)) from None
    except OSError as err:
        raise StepFailed(f"Fuseki did not answer ({type(err).__name__})") from None
    if result["status"] == "mismatch":
        raise StepFailed(load_fuseki.line(result))
    # The module's own line starts with the store's name; the runner prints the step's name in its place.
    return {**result, "line": load_fuseki.line(result).split(": ", 1)[1]}


def neo4j_extras(ctx):
    """The loads that follow the ontology in a Neo4j database: the technical graph when its file was fetched, then
    any the hooks add."""
    from . import load_neo4j
    files = tech_graph_files(ctx)
    return ((load_neo4j.tech_graph_loader(files, ctx.release_root),) if files else ()) + tuple(ctx.hooks["neo4j_extra_loads"])


def step_neo4j(ctx):
    """Step 9. Loads the release into the local Neo4j and runs every check there, then the technical graph
    (kpi_store.load_neo4j). The load's configuration and its log go to <run>/neo4j."""
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would load the local Neo4j and run every check there"}
    from . import load_neo4j
    try:
        result = load_neo4j.load(ctx.local, ctx.release_root, run_dir=ctx.run_dir / "neo4j", extra_loads=neo4j_extras(ctx))
    except load_neo4j.LoadError as err:
        raise StepFailed(str(err)) from None
    except Exception as err:   # a driver error's text can carry an address
        raise StepFailed(f"the local Neo4j did not answer ({type(err).__name__})") from None
    return {**result, "line": load_neo4j.line(result).split(": ", 1)[1]}


def step_enterprise(ctx):
    """Step 10. Copies the graph the local Neo4j holds to the one database on Neo4j Enterprise, then the technical
    graph (kpi_store.copy_enterprise). The copy replaces KPI Store nodes the database already holds only with
    --replace-enterprise. The output of the logical models' load goes to <run>/enterprise.log."""
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would copy the verified graph to the Enterprise database"}
    from . import copy_enterprise
    rules = ctx.hooks["own_rules"] or copy_enterprise.OWN_RULES
    ctx.run_dir.mkdir(parents=True, exist_ok=True)   # --only enterprise may be the first step of a run
    try:
        with (ctx.run_dir / "enterprise.log").open("a", encoding="utf-8", newline="\n") as log:
            result = copy_enterprise.copy(ctx.local, ctx.release_root, replace=ctx.replace_enterprise,
                                          extra_loads=neo4j_extras(ctx), own_rules=rules, log=log)
    except copy_enterprise.Refused as err:
        # The copy's own command takes --replace. Here the person runs the runner, whose option has another name.
        raise StepFailed(re.sub(r"Run the command again with --replace\b", "Run the runner again with --from enterprise "
                                "--replace-enterprise", str(err))) from None
    except Exception as err:   # only the error's type is printed: a driver error's text can carry an address
        raise StepFailed(f"a Neo4j server did not answer, or a statement failed ({type(err).__name__})") from None
    return {**result, "line": copy_enterprise.line(result).split(": ", 1)[1]}


# ---- the sync check and the summary ---------------------------------------------------------------------
# Steps 11 and 12. The loads each checked their own store. The sync check reads all four again, side by side,
# and the summary says what this run did.

def step_sync(ctx):
    """Step 11. Reads Databricks, Fuseki, the local Neo4j and Neo4j Enterprise, and judges each as current or not
    (kpi_store.sync_check). One store that is not current fails the step. The rows are written to the step's
    file before the failure, so the summary and a later look can show which store is behind."""
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would read the four stores and judge each"}
    from . import sync_check
    extra = ctx.hooks["extra_graphs"](ctx.release_root, ctx.run_dir) if ctx.hooks["extra_graphs"] else {}
    rows = sync_check.check(ctx.local, ctx.release_root, extra_graphs=tuple(extra or ()), tech_graph_files=tech_graph_files(ctx))
    for text in sync_check.lines(rows):
        ctx.out("  " + text)
    result = {"rows": [{"store": s, "status": status, "why": why} for s, status, why in rows]}
    if not sync_check.all_current(rows):
        behind = [s for s, status, _ in rows if status not in ("current", sync_check.LEFT_OUT)]
        write_text(ctx.step_file("sync"), json.dumps({**result, "status": "not current"}, indent=2) + "\n")
        fix = ""
        if any(status == sync_check.NOT_CHECKED for _, status, _ in rows):
            fix = (". The technical graph was not checked, because its file was never fetched: the report step fetches "
                   "it after a notebook run that loaded, so run the same command with --from notebook")
        raise StepFailed(f"not current: {', '.join(behind)}{fix}")
    return {**result, "status": "current", "line": f"all {len(rows)} lines read current"}


def step_summary(ctx):
    """Step 12. Prints each step's status from this run's step files and writes them to <run>/summary.json. A step
    this command left out is named as left out, even when an earlier command recorded a result for it."""
    if ctx.dry_run:
        return {"status": "dry-run", "line": "would print the run's summary"}
    steps = {name: ctx.earlier(name) for name in STEPS if name != "summary"}
    ctx.out(f"summary of run {ctx.run_id}:")
    for name, result in steps.items():
        if name in ctx.left_out:   # an earlier command's result for this run stays in its file; it is not this command's
            ctx.out(f"  {name:<11} left out of this run" + (f" (recorded earlier: {result.get('status')})" if result else ""))
        elif result:
            ctx.out(f"  {name:<11} {result.get('status')}")
    write_text(ctx.run_dir / "summary.json", json.dumps({"run": ctx.run_id, "left_out": list(ctx.left_out), "steps": steps},
                                                        indent=2, default=str) + "\n")
    return {"status": "written", "summary": str(ctx.run_dir / "summary.json"),
            "line": f"the run's files are in {ctx.run_dir}"}


STEP_FUNCTIONS = {"cut": step_cut, "check": step_check, "zip": step_zip, "volume": step_volume, "upload": step_upload,
                  "notebook": step_notebook, "report": step_report, "fuseki": step_fuseki, "neo4j": step_neo4j,
                  "enterprise": step_enterprise, "sync": step_sync, "summary": step_summary}
# The steps that are stopped when this run's notebook step did not load the release (not_loaded_reason). --mode
# check leaves them out.
LOCAL_LOADS = ("fuseki", "neo4j", "enterprise", "sync")


# ---- the chain ------------------------------------------------------------------------------------------

def selected(only=None, start=None, skip=()):
    """The steps to run, in order."""
    names = list(STEPS)
    if start:
        names = names[names.index(start):]
    if only is not None:   # an empty list selects no step; it never means "every step"
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
        except Exception as err:   # pylint: disable=broad-except
            expected = isinstance(err, StepFailed)
            if expected:
                failure = err
            else:
                # An error no step expected still ends the run with one line and a step file, never a traceback.
                # Only the error's type is printed, because an error's text can name an address or a path on this
                # machine; the whole traceback goes to a file in the run folder for whoever investigates.
                detail, where = ctx.run_dir / f"{name}.error.txt", ""
                if not ctx.dry_run:   # a dry run writes nothing
                    try:
                        ctx.run_dir.mkdir(parents=True, exist_ok=True)
                        write_text(detail, "".join(traceback.format_exception(err)))
                        where = f"; the detail is in {detail}"
                    except OSError:
                        pass
                failure = StepFailed(f"an unexpected error stopped the step ({type(err).__name__}){where}. Fix the "
                                     f"cause, then run the same command with --from {name}")
            err = failure
            if not ctx.dry_run:
                # The sync step wrote its rows before it failed. They are kept, not replaced by a bare "failed".
                # An unexpected error in the sync step wrote no new rows, so an older file is not kept.
                kept = ctx.earlier(name) if (name == "sync" and expected) or name == "notebook" else None
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
    """A new run's ID: the UTC time to the second, such as 20261111T093000Z. It names the run's folder."""
    return (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def newest_run(run_root):
    """The newest run's ID in the run folder, or None. Run IDs are UTC times, so they sort by name."""
    runs = sorted(p.name for p in Path(run_root).glob("[0-9]*T[0-9]*Z") if p.is_dir()) if Path(run_root).is_dir() else []
    return runs[-1] if runs else None


def step_list(text, known=STEPS, what="step", allow_empty=True):
    """Reads the value of --only or --skip: names with commas between them. An unknown name is an error. The names
    are steps, or stores when the command is a reset. --only reads with allow_empty=False: an empty value, such as a
    script's unset variable, is an error rather than a run of every step."""
    names = [n.strip() for n in (text or "").split(",") if n.strip()]   # "zip, upload" and " " read as meant
    if not names and not allow_empty:
        raise argparse.ArgumentTypeError(f"--only names no {what}; give at least one of: {', '.join(known)}")
    unknown = [n for n in names if n not in known]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown {what} {unknown[0]}; the {what}s are {', '.join(known)}")
    return names


def main(argv=None, **context_options):
    """Reads the arguments and the two settings files, picks the run and its steps, and runs them. Returns the
    exit code. Bad settings stop here with exit 2, before any step."""
    ap = argparse.ArgumentParser(prog="kpi_store.runner", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--from", dest="start", choices=STEPS, help="start at this step, in the newest run")
    # --only and --skip are read as text here and checked below: their names are steps, or stores with --reset.
    ap.add_argument("--only", help="run only these steps (comma-separated), in the newest run; with --reset, empty "
                    "only these stores")
    ap.add_argument("--skip", default="", help="leave these steps out (comma-separated); with --reset, these stores")
    ap.add_argument("--run-id", help="the run to go on with (default: a new run, or the newest with --from or --only)")
    ap.add_argument("--mode", choices=("load", "check"), default="load",
                    help="check stops the notebook after its report and loads nothing (default load)")
    ap.add_argument("--replace-enterprise", action="store_true",
                    help="let the copy replace the KPI Store's nodes the Enterprise database already holds")
    ap.add_argument("--dry-run", action="store_true", help="print each step's commands as argument lists and run nothing; "
                    "with --reset, print what would be deleted and delete nothing")
    ap.add_argument("--reset", action="store_true",
                    help="run no step; empty the stores the KPI Store loaded (enterprise, neo4j, fuseki, databricks), so "
                         "the next run loads them again. It prints what it will delete and asks for the word reset first")
    ap.add_argument("--yes", action="store_true", help="with --reset: do not ask before deleting; for a script")
    args = ap.parse_args(argv)
    if args.reset:
        from . import reset
    # The two kinds of command share --only and --skip, so an option that belongs to the other kind is refused:
    # a reset that silently ignored --from, or a load that ignored --yes, would not do what the person asked.
    if args.reset and (args.start or args.run_id or args.replace_enterprise or args.mode != "load"):
        ap.error("--reset takes only --stores, --release, --only, --skip, --yes and --dry-run")
    if args.yes and not args.reset:
        ap.error("--yes belongs to --reset")
    try:
        known, what = (reset.STORES, "store") if args.reset else (STEPS, "step")
        args.only = step_list(args.only, known, what, allow_empty=False) if args.only is not None else None
        args.skip = step_list(args.skip, known, what)
    except argparse.ArgumentTypeError as err:
        ap.error(str(err))
    try:
        local = ls.load(ls.locate(args.stores), release_root=Path(args.release))
        run_root = local.need("run_folder")
        # --from and --only go on in the newest run when there is one, because they need that run's earlier
        # results: the zip, the notebook's summary. A plain command starts a new run.
        run_id = args.run_id or ((args.start or args.only) and newest_run(run_root)) or new_run_id()
        ctx = Context(local, args.release, run_id, mode=args.mode, dry_run=args.dry_run,
                      replace_enterprise=args.replace_enterprise, **context_options)
    except (ls.LocalSettingsError, settings_module.SettingsError) as err:
        print(f"runner: {err}", file=sys.stderr)
        return 2
    if args.reset:
        # A reset is no run: it gets no run folder and writes no step file. It reads the same two settings files.
        stores = [s for s in reset.STORES if (args.only is None or s in args.only) and s not in args.skip]
        if not stores:
            ap.error("--only and --skip leave no store to reset")
        return reset.run(ctx, stores, yes=args.yes, dry_run=args.dry_run)
    names = selected(args.only, args.start, args.skip)
    if args.mode == "check":   # the notebook loads nothing in this mode, so the stores are not loaded either
        names = [n for n in names if n not in LOCAL_LOADS]
    # Whatever narrowed the run (--only, --from, --skip or --mode check), a step that did not run is named.
    ctx.left_out = [n for n in STEPS if n not in names]
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
