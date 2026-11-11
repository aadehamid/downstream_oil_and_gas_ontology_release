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

# COMMAND ----------

# MAGIC %pip install databricks-sdk==0.164.0 pyoxigraph==0.5.13 rdflib==7.6.0 sqlglot==30.31.0 pyyaml==6.0.3

# COMMAND ----------

if "dbutils" in globals():
    dbutils.library.restartPython()  # noqa: F821  the notebook supplies dbutils

# COMMAND ----------

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
    try:
        doc = tomllib.loads(path.read_bytes().decode("utf-8"))
        zip_name, want = doc["release"]["zip"], doc["release"]["sha256"]
    except OSError as err:
        raise Stop(f"cannot read the settings file {path}: {type(err).__name__}") from None
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as err:
        raise Stop(f"the settings file {path} is wrong: {type(err).__name__}: {err}") from None
    if not isinstance(zip_name, str) or Path(zip_name).name != zip_name or not zip_name.endswith(".zip"):
        raise Stop("[release] zip must be a file name ending in .zip, with no folder")
    zip_path = path.parent / zip_name
    if not zip_path.is_file():
        raise Stop(f"the release zip {zip_name} is not beside the settings file")
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
    for name in [m for m in sys.modules if m == "kpi_store" or m.startswith("kpi_store.")]:
        del sys.modules[name]   # a second run in one session must import the new zip's code
    sys.path[:] = [p for p in sys.path if not p.startswith(str(target.parent / "kpi_store_"))]
    sys.path.insert(0, str(root))
    from kpi_store import settings as settings_module
    try:
        settings = settings_module.load(path)
        settings_module.check_zip(settings)
    except settings_module.SettingsError as err:
        raise Stop(str(err)) from None
    return root, settings


def main(spark, dbutils, genie=None):
    """Runs the load with the notebook's own Spark session and returns the summary."""
    dbutils.widgets.text("settings_path", "/Volumes/idp_sbx/kpi_store/releases/kpi_store.toml")
    dbutils.widgets.text("mode", "load")
    dbutils.widgets.text("stale_after_days", "35")
    days = dbutils.widgets.get("stale_after_days").strip()
    root, settings = bootstrap(dbutils.widgets.get("settings_path").strip())
    from kpi_store import load_databricks
    if genie is None:
        from databricks.sdk import WorkspaceClient
        genie = WorkspaceClient().genie   # the notebook's own sign-in; no token is read or stored
    summary = load_databricks.run(settings, root, lambda statement: spark.sql(statement).collect(), genie,
                                  mode=dbutils.widgets.get("mode").strip() or "load",
                                  stale_after_days=int(days) if days else None)
    print(json.dumps(summary, indent=2))
    if summary["status"] in ("staging-mismatch", "main-mismatch"):
        raise RuntimeError(f"the load stopped: {summary['status']}. The hashes differ; see the summary above.")
    return summary

# COMMAND ----------

if "dbutils" in globals():
    dbutils.notebook.exit(json.dumps(main(spark, dbutils)))  # noqa: F821  the notebook supplies spark and dbutils
