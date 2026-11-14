"""The notebook: its start-up checks stop before any read or write, and its run is the tested run."""
import contextlib
import functools
import hashlib
import importlib.util
import json
import re
import sys
import zipfile

import pytest

from kpi_store.tests import support

NOTEBOOK = support.ROOT / "kpi_store" / "notebook" / "kpi_store_load.py"
# The small workspace's technical graph, counted by hand: 3 objects with a type, a name, a layer and a design (12),
# 2 reads-from links, 2 built-by links, 2 last-refresh times, and the job with its type and name.
TECH_TRIPLES = 20


@pytest.fixture(autouse=True)
def the_tree_s_own_package_afterwards():
    """The notebook imports kpi_store from the unpacked zip, which holds less than the tree's package. A later
    test in the same process must get the tree's package again, so each test puts the imports back."""
    modules = {name: module for name, module in sys.modules.items() if name == "kpi_store" or name.startswith("kpi_store.")}
    path = list(sys.path)
    yield
    for name in [n for n in sys.modules if n == "kpi_store" or n.startswith("kpi_store.")]:
        del sys.modules[name]
    sys.modules.update(modules)
    sys.path[:] = path


@functools.cache
def notebook():
    spec = importlib.util.spec_from_file_location("kpi_store_load_notebook", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)   # outside Databricks there is no dbutils, so nothing runs on import
    return module


@contextlib.contextmanager
def import_state_kept():
    """The notebook puts the unzipped release first on the import path and drops every loaded kpi_store module, as
    it must in Databricks. In a test process that would leave later tests importing the small release's kpi_store,
    which lacks whole sub-packages. This puts the import path and the modules back as they were."""
    def loaded():
        return {name: module for name, module in sys.modules.items() if name == "kpi_store" or name.startswith("kpi_store.")}
    path, modules = list(sys.path), loaded()
    try:
        yield
    finally:
        sys.path[:] = path
        for name in loaded():
            del sys.modules[name]
        sys.modules.update(modules)


@pytest.fixture(autouse=True)
def the_import_state_is_put_back():
    with import_state_kept():
        yield


def test_a_notebook_run_leaves_the_import_path_and_the_loaded_modules_as_they_were(tmp_path):
    import kpi_store.questions   # a sub-package the zip of these tests does not hold
    before, package = list(sys.path), sys.modules["kpi_store"]
    with import_state_kept():
        run_main(volume(tmp_path), support.small_workspace())
        assert sys.path != before and sys.modules["kpi_store"] is not package   # what the notebook does
        assert "kpi_store.questions" not in sys.modules
    assert sys.path == before and sys.modules["kpi_store"] is package
    assert sys.modules["kpi_store.questions"] is kpi_store.questions


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
    assert summary["status"] == "loaded" and summary["count"] == 32
    # The technical graph follows the load: built from the run's discovery.json, saved beside the report, and loaded
    # into the tech_graph schema. Each of the two loads replaced its table once.
    tech = summary["tech_graph"]
    run_dir = folder / "reports" / summary["run"]
    assert tech["status"] == "loaded" and tech["table"] == "idp_sbx.tech_graph.tech_graph_triples" and workspace.rewrites == 2
    assert tech["file"] == str(run_dir / "tech-graph.nq") and (run_dir / "tech-graph.nq").is_file()
    assert tech["count"] == len(workspace.store["idp_sbx.tech_graph.tech_graph_triples"]) == TECH_TRIPLES
    assert '<urn:kpi-store:tech:idp_sbx+synapse_dev:object/idp_sbx.gold_sample.sample_fact>' in (run_dir / "tech-graph.nq").read_text(encoding="utf-8")
    marker = json.loads(workspace.store["idp_sbx.kpi_store.epm_store_markers"][0]["marker"])
    assert marker["commit"] == "KPI Store 1.1 (zip sha256 " + hashlib.sha256((folder / "kpi-store-1.1.zip").read_bytes()).hexdigest() + ")"
    assert (folder / "discovery-report.json").is_file()
    again, _ = run_main(folder, workspace, stale_after_days="")
    assert again["status"] == "current" and again["tech_graph"]["status"] == "current" and workspace.rewrites == 2


def test_a_technical_graph_table_that_differs_fails_the_run(tmp_path):
    folder, workspace = volume(tmp_path), support.small_workspace()
    real = workspace.run_sql
    def lossy(statement):   # a store that drops the technical graph's rows as they are written
        if statement.lstrip().startswith("INSERT INTO idp_sbx.tech_graph.tech_graph_triples__staging"):
            workspace.statements.append(statement)
            return []
        return real(statement)
    workspace.run_sql = lossy
    with pytest.raises(RuntimeError, match="the technical graph's load stopped: staging-mismatch"):
        run_main(folder, workspace)
    assert "idp_sbx.tech_graph.tech_graph_triples" not in workspace.store
    assert len(workspace.store["idp_sbx.kpi_store.epm_triples"]) == 32   # the ontology's own load stands


def test_a_run_that_stops_on_a_report_builds_no_technical_graph(tmp_path):
    folder, workspace = volume(tmp_path), support.small_workspace()
    workspace.columns["idp_sbx.gold_sample.sample_fact"] = ["Amount_Renamed"]
    summary, _ = run_main(folder, workspace)
    assert summary["status"] == "blocked" and "tech_graph" not in summary
    assert not any(name.startswith("idp_sbx.tech_graph.") for name in workspace.store)


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
    assert text.startswith("# Databricks notebook source\n") and len(cells) == 6
    assert cells[1].strip() == ("# MAGIC %pip install databricks-sdk==0.164.0 pyoxigraph==0.5.13 rdflib==7.6.0 sqlglot==30.31.0 "
                                "pyyaml==6.0.3 tomli==2.2.1")
    assert "dbutils.library.restartPython()" in cells[2] and "import" not in cells[2]
    # The third cell says which Python runs, before the cell that needs it. It must be readable by a Python older
    # than the lowest one supported, or that Python could not say the sentence.
    assert "PYTHON_MINIMUM = (3, 10)" in cells[3] and "print(" in cells[3] and "needs Python 3.10 or later" in cells[3]
    assert "f\"" not in cells[3] and "match " not in cells[3] and ":=" not in cells[3]
    assert "token" not in text.lower().replace("no token", "").replace("it needs no token", "")


def test_a_zip_with_the_wrong_checksum_is_never_opened(tmp_path):
    folder = volume(tmp_path, sha256="0" * 64)
    with pytest.raises(notebook().Stop, match="the release zip's SHA-256 is"):
        notebook().bootstrap(folder / "kpi_store.toml", work_dir=tmp_path / "work")
    assert not (tmp_path / "work").exists()   # its code was not unpacked, so it could not run


def test_the_unpacked_files_are_the_bytes_that_were_hashed(tmp_path, monkeypatch):
    """A zip replaced in the volume between the checksum and the unpack must not be the one unpacked."""
    folder, nb = volume(tmp_path), notebook()
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as z:
        z.writestr("kpi_store/__init__.py", "")
        z.writestr("swapped.txt", "not the release")

    class SwapAfterHash:
        """hashlib, except that the zip in the volume is replaced as soon as its checksum is asked for."""
        @staticmethod
        def sha256(*args):
            real = hashlib.sha256(*args)

            class Digest:
                update = real.update

                @staticmethod
                def hexdigest():
                    (folder / "kpi-store-1.1.zip").write_bytes(other.read_bytes())
                    return real.hexdigest()
            return Digest()

    monkeypatch.setattr(nb, "hashlib", SwapAfterHash)
    with import_state_kept(), pytest.raises(nb.Stop, match="the release zip's SHA-256 is"):
        nb.bootstrap(folder / "kpi_store.toml", work_dir=tmp_path / "work")   # the release's own second check sees the swap
    assert not (tmp_path / "work" / "swapped.txt").exists()
    assert (tmp_path / "work" / "release.json").is_file()   # the hashed zip's own file


# ---------- Python 3.10: the notebook's side runs there too ----------

def test_the_notebook_side_reads_toml_without_tomllib(tmp_path, monkeypatch):
    """The first real run was on serverless compute with Python 3.10, which has no tomllib. The notebook's own
    bootstrap and the release's settings module each take the first reader that is there."""
    from kpi_store import toml_reader
    assert toml_reader.READERS == ("tomllib", "tomli", "pip._vendor.tomli")
    made_up = type(sys)("made_up_reader")
    seen = []

    def load(name):
        seen.append(name)
        if name != "pip._vendor.tomli":
            raise ImportError(name)
        return made_up
    assert toml_reader.reader(load=load) is made_up and seen == list(toml_reader.READERS)
    with pytest.raises(ImportError, match=r"^Python \d+\.\d+\.\d+ has no TOML reader\. Python 3\.11 and later bring one "
                                          r"\(tomllib\); on an older Python install the package tomli$"):
        toml_reader.reader(names=("no_such_reader_a", "no_such_reader_b"))
    assert toml_reader.loads('a = "b"') == {"a": "b"}
    with pytest.raises(toml_reader.TOMLDecodeError):
        toml_reader.loads("a = ")
    # The notebook's own copy of the same choice, for the code that runs before the zip is unpacked.
    nb = notebook()
    assert nb.toml_reader().loads('a = "b"') == {"a": "b"}
    import importlib
    real = importlib.import_module
    monkeypatch.setattr(importlib, "import_module", lambda name, *a: (_ for _ in ()).throw(ImportError(name))
                        if name in toml_reader.READERS else real(name, *a))
    with pytest.raises(nb.Stop, match=r"has no TOML reader, so the settings file cannot be read\. Run the first cell"):
        nb.toml_reader()


def test_the_modules_the_notebook_reaches_import_no_tomllib_of_their_own():
    """A module that runs in the notebook must read TOML through kpi_store/toml_reader.py. This walks the imports from
    the modules that the notebook names and fails on a direct import of tomllib, which Python 3.10 does not have."""
    import ast
    package = support.ROOT / "kpi_store"
    seen, todo = {}, ["settings", "load_databricks", "tech_graph"]
    while todo:
        name = todo.pop()
        if name in seen or not (package / f"{name}.py").is_file():
            continue
        tree = ast.parse((package / f"{name}.py").read_text(encoding="utf-8"))
        seen[name] = sorted({alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
                            | {node.module.split(".")[0] for node in ast.walk(tree)
                               if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module})
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                todo += [node.module] if node.module else [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").startswith("kpi_store"):
                todo += [alias.name for alias in node.names] + node.module.split(".")[1:]
    assert sorted(seen) == ["compare", "discovery", "load_databricks", "metric_view", "ontology_view", "report", "settings",
                            "tech_graph", "toml_reader"]
    assert [name for name, imports in seen.items() if "tomllib" in imports] == []
    assert "import tomllib" not in NOTEBOOK.read_text(encoding="utf-8")


def test_every_file_that_runs_in_the_notebook_is_python_3_10_syntax():
    """The notebook, the modules it reaches, and the four files of the release that those load by their path."""
    import ast
    files = ["kpi_store/notebook/kpi_store_load.py", "kpi_store/__init__.py", "kpi_store/toml_reader.py", "kpi_store/settings.py",
             "kpi_store/load_databricks.py", "kpi_store/discovery.py", "kpi_store/compare.py", "kpi_store/report.py",
             "kpi_store/tech_graph.py", "kpi_store/metric_view.py", "kpi_store/ontology_view.py",
             "business_architecture/ontology/projection/sync_stores.py", "business_architecture/ontology/projection/subgraph.py",
             "business_architecture/ontology/release/newest.py", "skills/rdf-store/scripts/rdfstore.py"]
    for name in files:
        ast.parse((support.ROOT / name).read_text(encoding="utf-8"), name, feature_version=(3, 10))
