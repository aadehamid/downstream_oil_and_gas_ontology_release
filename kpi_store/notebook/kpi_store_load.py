# Databricks notebook source
# MAGIC %md
# MAGIC # KPI Store load
# MAGIC
# MAGIC This notebook loads the KPI Store release into the Delta table `epm_triples`. Run it on serverless compute.
# MAGIC It needs no token: it uses the notebook's own session.
# MAGIC
# MAGIC 1. It reads `kpi_store.toml` from the volume and checks the release zip beside it against the SHA-256 the
# MAGIC    settings name. A missing or wrong settings file, or a zip that differs, stops the run before anything else.
# MAGIC 2. It compares the ontology with the workspace and writes `discovery-report.json` and `discovery-report.csv`
# MAGIC    to the volume.
# MAGIC 3. If a row of the report blocks, it stops there. Otherwise it loads `epm_triples` through a staging table
# MAGIC    whose hash must equal the hash of the release files, and writes the marker row in `epm_store_markers`.
# MAGIC 4. After a load it builds the technical graph from what step 2 read, saves it beside the report as
# MAGIC    `tech-graph.nq`, and loads it into the `tech_graph` schema the same way. The summary holds its result
# MAGIC    under `tech_graph`.
# MAGIC
# MAGIC Parameters:
# MAGIC
# MAGIC | Name | Default | Meaning |
# MAGIC |---|---|---|
# MAGIC | `settings_path` | `/Volumes/idp_sbx/kpi_store/releases/kpi_store.toml` | The settings file. The zip sits in the same folder. |
# MAGIC | `mode` | `load` | `load` loads when no row blocks. `check` stops after the report. |
# MAGIC | `stale_after_days` | `35` | A table with no write for this many days gets a freshness row. Empty leaves freshness out. |
# MAGIC
# MAGIC The notebook ends with a JSON summary. Its `status` is `blocked`, `checked`, `current`, `marked` or `loaded`.
# MAGIC A hash that differs fails the run.
# MAGIC
# MAGIC | Status | Meaning |
# MAGIC |---|---|
# MAGIC | `blocked` | A row of the report blocks. Nothing was loaded. Clear the report, cut, and run again. |
# MAGIC | `checked` | `mode` was `check` and no row blocks. Nothing was loaded. |
# MAGIC | `current` | `epm_triples` and its marker already hold this release. Nothing was written. |
# MAGIC | `marked` | `epm_triples` already held this release. Only the marker row was written. |
# MAGIC | `loaded` | `epm_triples` was replaced through the staging table, read back, and marked. |
# MAGIC
# MAGIC What the notebook may touch: it writes only to the two KPI Store schemas the settings name, and to the
# MAGIC volume. It reads only the read catalogs the settings name and three system schemas. The release's code
# MAGIC checks every SQL statement against this rule before it runs.
# MAGIC
# MAGIC The cells, in order:
# MAGIC
# MAGIC 1. Install the packages at the versions the release was tested with. A pinned version gives the same
# MAGIC    result on every run.
# MAGIC 2. Restart Python, so the cells after it use the packages that were just installed.
# MAGIC 3. Define the two functions that do the work: `bootstrap` checks the zip and unpacks it, and `main` runs
# MAGIC    the comparison and the load. This cell runs nothing.
# MAGIC 4. Run `main` and hand its summary to the caller. The runner on the Windows machine reads this summary.
# MAGIC
# MAGIC The notebook holds little code of its own. The comparison and the load live in the release zip, in the
# MAGIC `kpi_store` package, so the code that runs is the code whose checksum the settings name.

# COMMAND ----------

# MAGIC %pip install databricks-sdk==0.164.0 pyoxigraph==0.5.13 rdflib==7.6.0 sqlglot==30.31.0 pyyaml==6.0.3

# COMMAND ----------

# Restart Python so the packages installed above replace any older versions the session already loaded.
# Outside Databricks there is no dbutils, and this cell does nothing: the tests load this file as a module.
if "dbutils" in globals():
    dbutils.library.restartPython()  # noqa: F821  the notebook supplies dbutils

# COMMAND ----------

# The two functions of the load. bootstrap runs before any of the release's code can: it is what decides whether
# that code is the right code. main then hands the work to the release's kpi_store package.

import hashlib
import json
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path


class Stop(Exception):
    """The run stopped before any read or write of the workspace."""


def bootstrap(settings_path, work_dir=None):
    """(release root, settings). Checks the zip's SHA-256 against the settings, unzips the release to a local
    folder, puts it on the import path, and validates the settings in full with the release's own code.

    This function uses the standard library only, because the release's code is inside the zip it checks."""
    path = Path(settings_path)
    # Read only the two values needed to find and check the zip. The full validation comes after the unzip, with
    # the release's own settings code.
    try:
        doc = tomllib.loads(path.read_bytes().decode("utf-8"))
        zip_name, want = doc["release"]["zip"], doc["release"]["sha256"]
    except OSError as err:
        raise Stop(f"cannot read the settings file {path}: {type(err).__name__}") from None
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as err:
        raise Stop(f"the settings file {path} is wrong: {type(err).__name__}: {err}") from None
    # A bare file name only: a name with a folder in it could point at a zip outside the settings file's folder.
    if not isinstance(zip_name, str) or Path(zip_name).name != zip_name or not zip_name.endswith(".zip"):
        raise Stop("[release] zip must be a file name ending in .zip, with no folder")
    zip_path = path.parent / zip_name
    if not zip_path.is_file():
        raise Stop(f"the release zip {zip_name} is not beside the settings file")
    # The checksum comes first, and the zip is opened only when it matches: a zip that differs is never
    # unpacked, so none of its code can run. It is read in 1 MB pieces to keep a large zip out of memory.
    digest = hashlib.sha256()
    with zip_path.open("rb") as f:
        for piece in iter(lambda: f.read(1 << 20), b""):
            digest.update(piece)
    if digest.hexdigest() != want:
        raise Stop(f"the release zip's SHA-256 is {digest.hexdigest()}, not the {want} the settings name")
    target = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="kpi_store_"))
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(target)
    except (zipfile.BadZipFile, OSError) as err:
        raise Stop(f"the release zip cannot be opened: {type(err).__name__}") from None
    # The zip holds the release's files at its top, or inside one folder.
    roots = [p for p in [target, *sorted(d for d in target.iterdir() if d.is_dir())] if (p / "kpi_store" / "__init__.py").is_file()]
    if not roots:
        raise Stop("the release zip holds no kpi_store package")
    root = roots[0]
    # A notebook session can run this twice. Drop the kpi_store modules and the import paths of an earlier
    # unzip, so this run uses this zip's code and no other.
    for name in [m for m in sys.modules if m == "kpi_store" or m.startswith("kpi_store.")]:
        del sys.modules[name]   # a second run in one session must import the new zip's code
    sys.path[:] = [p for p in sys.path if not p.startswith(str(target.parent / "kpi_store_"))]
    sys.path.insert(0, str(root))
    # From here on the release's own code runs. It validates the whole settings file and checks the zip again.
    from kpi_store import settings as settings_module
    try:
        settings = settings_module.load(path)
        settings_module.check_zip(settings)
    except settings_module.SettingsError as err:
        raise Stop(str(err)) from None
    return root, settings


def main(spark, dbutils, genie=None):
    """Runs the load with the notebook's own Spark session and returns the summary."""
    # The three parameters. The runner sets settings_path and mode when it submits the run; a person who runs the
    # notebook by hand sets them in the widgets at the top.
    dbutils.widgets.text("settings_path", "/Volumes/idp_sbx/kpi_store/releases/kpi_store.toml")
    dbutils.widgets.text("mode", "load")
    dbutils.widgets.text("stale_after_days", "35")
    days = dbutils.widgets.get("stale_after_days").strip()
    root, settings = bootstrap(dbutils.widgets.get("settings_path").strip())
    from kpi_store import load_databricks
    if genie is None:
        from databricks.sdk import WorkspaceClient
        genie = WorkspaceClient().genie   # the notebook's own sign-in; no token is read or stored
    # The comparison, the report and the load of epm_triples. The release's code gets one function that runs a SQL
    # statement and returns its rows, and it checks each statement before it calls that function.
    summary = load_databricks.run(settings, root, lambda statement: spark.sql(statement).collect(), genie,
                                  mode=dbutils.widgets.get("mode").strip() or "load",
                                  stale_after_days=int(days) if days else None)
    # The technical graph is built only when Databricks holds this release: after a report that blocks, or in
    # mode check, there is nothing for it to describe yet.
    if summary["status"] in ("current", "marked", "loaded"):
        from kpi_store import tech_graph
        run_dir = Path(summary["report_json"]).parent   # the run's folder in the volume; discovery.json is there
        graph_files = tech_graph.write(tech_graph.build_from_files(run_dir / "discovery.json", root, settings), run_dir)
        gate = load_databricks.Gate(settings, lambda statement: spark.sql(statement).collect())
        summary["tech_graph"] = tech_graph.load_delta(gate, settings, graph_files, root) | {"file": str(graph_files[0])}
    print(json.dumps(summary, indent=2))
    # A hash that differs must fail the run, not end it quietly: the summary is printed first so the person can
    # read the comparison, and then the run fails.
    for name, status in (("the load", summary["status"]), ("the technical graph's load", summary.get("tech_graph", {}).get("status"))):
        if status in ("staging-mismatch", "main-mismatch"):
            raise RuntimeError(f"{name} stopped: {status}. The hashes differ; see the summary above.")
    return summary

# COMMAND ----------

# Run the load and end the notebook with the summary as its result. A caller that submitted the run, such as the
# runner, reads the summary from the run's output. Outside Databricks this cell does nothing.
if "dbutils" in globals():
    dbutils.notebook.exit(json.dumps(main(spark, dbutils)))  # noqa: F821  the notebook supplies spark and dbutils
