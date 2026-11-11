"""The notebook: its start-up checks stop before any read or write, and its run is the tested run."""
import functools
import hashlib
import importlib.util
import json
import re
import zipfile

import pytest

from kpi_store.tests import support

NOTEBOOK = support.ROOT / "kpi_store" / "notebook" / "kpi_store_load.py"


@functools.cache
def notebook():
    spec = importlib.util.spec_from_file_location("kpi_store_load_notebook", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)   # outside Databricks there is no dbutils, so nothing runs on import
    return module


def volume(tmp_path, zip_bytes=None, sha256=None, settings=True, top_folder=""):
    """A made-up volume folder: a release zip of the small release plus the real kpi_store package, and settings."""
    folder = tmp_path / "volume"
    folder.mkdir()
    if zip_bytes is None:
        release = support.small_release(tmp_path / "release")
        with zipfile.ZipFile(folder / "kpi-store-1.1.zip", "w") as z:
            for path in sorted(release.rglob("*")):
                if path.is_file():
                    z.write(path, top_folder + path.relative_to(release).as_posix())
            for path in sorted((support.ROOT / "kpi_store").glob("*.py")):
                z.write(path, top_folder + "kpi_store/" + path.name)
            rdfstore = support.ROOT / "skills" / "rdf-store" / "scripts" / "rdfstore.py"
            z.write(rdfstore, top_folder + "skills/rdf-store/scripts/rdfstore.py")
    else:
        (folder / "kpi-store-1.1.zip").write_bytes(zip_bytes)
    digest = sha256 or hashlib.sha256((folder / "kpi-store-1.1.zip").read_bytes()).hexdigest()
    if settings:
        text = re.sub(r'(?m)^sha256 = "[0-9a-f]+"', f'sha256 = "{digest}"', support.SETTINGS_TEXT)
        (folder / "kpi_store.toml").write_text(text, encoding="utf-8", newline="\n")
    return folder


class Widgets:
    def __init__(self, values):
        self.values, self.defaults = values, {}

    def text(self, name, default):
        self.defaults[name] = default

    def get(self, name):
        return self.values.get(name, self.defaults[name])


class Spark:
    def __init__(self, workspace):
        self.workspace = workspace

    def sql(self, statement):
        rows = self.workspace.run_sql(statement)
        return type("Frame", (), {"collect": lambda self: rows})()


def run_main(folder, workspace, **widgets):
    from types import SimpleNamespace
    dbutils = SimpleNamespace(widgets=Widgets({"settings_path": str(folder / "kpi_store.toml"), **widgets}))
    return notebook().main(Spark(workspace), dbutils, genie=support.FakeGenie({})), dbutils


@pytest.mark.parametrize("top_folder", ["", "kpi-store-1.1/"])
def test_the_notebook_loads_from_a_zip_in_the_volume_and_a_second_run_changes_nothing(tmp_path, top_folder):
    folder, workspace = volume(tmp_path, top_folder=top_folder), support.small_workspace()
    summary, dbutils = run_main(folder, workspace)
    assert dbutils.widgets.defaults == {"settings_path": "/Volumes/idp_sbx/kpi_store/releases/kpi_store.toml", "mode": "load", "stale_after_days": "35"}
    assert summary["status"] == "loaded" and summary["count"] == 32 and workspace.rewrites == 1
    marker = json.loads(workspace.store["idp_sbx.kpi_store.epm_store_markers"][0]["marker"])
    assert marker["commit"] == "KPI Store 1.1 (zip sha256 " + hashlib.sha256((folder / "kpi-store-1.1.zip").read_bytes()).hexdigest() + ")"
    assert (folder / "discovery-report.json").is_file()
    again, _ = run_main(folder, workspace, stale_after_days="")
    assert again["status"] == "current" and workspace.rewrites == 1


def test_check_mode_is_a_notebook_parameter(tmp_path):
    folder, workspace = volume(tmp_path), support.small_workspace()
    summary, _ = run_main(folder, workspace, mode="check")
    assert summary["status"] == "checked" and "idp_sbx.kpi_store.epm_triples" not in workspace.store


@pytest.mark.parametrize("make, message", [
    (lambda t: volume(t, settings=False), "cannot read the settings file"),
    (lambda t: volume(t, sha256="0" * 64), "the release zip's SHA-256 is"),
    (lambda t: volume(t, zip_bytes=b"PK\x03\x04 this is not a whole zip"), "the release zip cannot be opened"),
    (lambda t: volume(t, zip_bytes=None).joinpath("kpi-store-1.1.zip").unlink() or t / "volume", "is not beside the settings file"),
])
def test_a_missing_settings_file_or_a_wrong_or_corrupt_zip_stops_before_any_read_or_write(tmp_path, make, message):
    folder, workspace = make(tmp_path), support.small_workspace()
    with pytest.raises(notebook().Stop, match=message):
        run_main(folder, workspace)
    assert workspace.statements == []


def test_a_zip_changed_after_the_settings_were_written_is_refused(tmp_path):
    folder, workspace = volume(tmp_path), support.small_workspace()
    with (folder / "kpi-store-1.1.zip").open("ab") as f:
        f.write(b"one more byte")
    with pytest.raises(notebook().Stop, match="the release zip's SHA-256 is"):
        run_main(folder, workspace)
    assert workspace.statements == []


@pytest.mark.parametrize("old, new, message", [
    ('write_schema = "kpi_store"', 'write_schema = "kpi store"', "letters, digits and _"),
    ('[genie]', '[genie]\ntoken = "x"', "unknown key 'token'"),
    ('zip = "kpi-store-1.1.zip"', 'zip = 7', "must be a file name ending in .zip"),
    ('[release]', '[release', "the settings file .* is wrong"),
])
def test_a_wrong_settings_file_stops_before_any_read_or_write(tmp_path, old, new, message):
    folder, workspace = volume(tmp_path), support.small_workspace()
    path = folder / "kpi_store.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    with pytest.raises(notebook().Stop, match=message):
        run_main(folder, workspace)
    assert workspace.statements == []


def test_the_notebook_pins_its_packages_and_restarts_python_before_any_code():
    text = NOTEBOOK.read_text(encoding="utf-8")
    cells = text.split("# COMMAND ----------")
    assert text.startswith("# Databricks notebook source\n") and len(cells) == 5
    assert cells[1].strip() == "# MAGIC %pip install databricks-sdk==0.164.0 pyoxigraph==0.5.13 rdflib==7.6.0 sqlglot==30.31.0 pyyaml==6.0.3"
    assert "dbutils.library.restartPython()" in cells[2] and "import" not in cells[2]
    assert "token" not in text.lower().replace("no token", "").replace("it needs no token", "")


def test_a_zip_with_the_wrong_checksum_is_never_opened(tmp_path):
    folder = volume(tmp_path, sha256="0" * 64)
    with pytest.raises(notebook().Stop, match="the release zip's SHA-256 is"):
        notebook().bootstrap(folder / "kpi_store.toml", work_dir=tmp_path / "work")
    assert not (tmp_path / "work").exists()   # its code was not unpacked, so it could not run
