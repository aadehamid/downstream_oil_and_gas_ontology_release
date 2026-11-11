"""The setup check: each check passes on a machine that is set up, and fails with one fix line on one that is not."""
import hashlib
import importlib.metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from kpi_store import setup_check as sc
from kpi_store.tests import stores_support, support

TARGET = "businessprocessarchitecturegraph"


def context(tmp_path, run=None, which=None, connect=None, version=(3, 12, 4), installed=None, write=True, **replace):
    if write:
        stores_support.local_settings(tmp_path, **replace)
    return sc.Context(str(tmp_path / "stores.toml"), environ={}, run=run or (lambda cmd, **k: SimpleNamespace(returncode=0, stdout="", stderr="")),
                      which=which or (lambda name: None), connect=connect, version=version,
                      installed=installed or (lambda name: sc.PACKAGES[name]))


def test_the_checks_have_these_names_in_this_order():
    assert list(sc.CHECKS) == ["python", "packages", "local-settings", "kpi-store-settings", "java", "fuseki-jar", "robot-jar",
                               "bash", "check-script-tools", "databricks-cli", "databricks-auth", "neo4j-local",
                               "neo4j-plugins", "neo4j-enterprise"]


def test_python_older_than_3_11_fails(tmp_path):
    assert sc.python(context(tmp_path, version=(3, 12, 4))) == (True, "Python 3.12.4", "")
    ok, detail, fix = sc.python(context(tmp_path, version=(3, 10, 9)))
    assert (ok, detail) == (False, "Python 3.10.9") and "Install Python 3.11 or later" in fix


def test_a_missing_or_other_package_version_gets_the_exact_install_line(tmp_path):
    assert sc.PACKAGES == {"rdflib": "7.6.0", "pyshacl": "0.40.2", "pyoxigraph": "0.5.13", "neo4j": "6.4.1",
                           "databricks-sdk": "0.164.0", "sqlglot": "30.31.0", "pyyaml": "6.0.3"}
    assert sc.packages(context(tmp_path))[0] is True
    def installed(name):
        if name == "neo4j":
            raise importlib.metadata.PackageNotFoundError(name)
        return "0.163.0" if name == "databricks-sdk" else sc.PACKAGES[name]
    ok, detail, fix = sc.packages(context(tmp_path, installed=installed))
    assert ok is False and detail == "neo4j missing (need 6.4.1), databricks-sdk 0.163.0 (need 0.164.0)"
    assert fix == "py -m pip install neo4j==6.4.1 databricks-sdk==0.164.0"


def test_the_local_settings_must_exist_outside_the_release(tmp_path):
    assert sc.local_settings(context(tmp_path)) == (True, f"{tmp_path / 'stores.toml'}, outside the release folder", "")
    ok, detail, fix = sc.local_settings(context(tmp_path / "none", write=False))
    assert ok is False and "cannot read the local settings file" in detail and "Copy kpi_store/stores.example.toml" in fix
    inside = sc.Context(str(support.ROOT / "kpi_store" / "stores.example.toml"), environ={})
    assert sc.local_settings(inside)[0] is False and "inside the release folder" in sc.local_settings(inside)[1]
    # A check that needs the settings fails with the settings' fix, not with an error.
    assert sc.java(inside) == (False, f"needs the local settings file: {inside.local_error}", sc.SETTINGS_FIX)


def test_the_kpi_store_settings_file_must_be_valid(tmp_path):
    ok, detail, fix = sc.kpi_store_settings(context(tmp_path))   # the example names no SQL warehouse
    assert not ok and "names no SQL warehouse, so the sync check cannot read Databricks" in detail
    assert fix == f"In {tmp_path / 'kpi_store.toml'} set [databricks] warehouse_id to the ID of a SQL warehouse you may use"
    (tmp_path / "kpi_store.toml").write_text(support.SETTINGS_TEXT.replace('warehouse_id = ""', 'warehouse_id = "0a1b2c3d4e5f"'), encoding="utf-8")
    ok, detail, _ = sc.kpi_store_settings(context(tmp_path))
    assert ok and detail == f"{tmp_path / 'kpi_store.toml'}: writes to idp_sbx.kpi_store, volume releases, SQL warehouse 0a1b2c3d4e5f"
    (tmp_path / "kpi_store.toml").write_text("[release]\n", encoding="utf-8")
    ok, detail, fix = sc.kpi_store_settings(context(tmp_path))
    assert not ok and fix == f"Copy kpi_store/kpi_store.example.toml to {tmp_path / 'kpi_store.toml'} and fill it in"


def test_java_must_be_found_and_be_21_or_later(tmp_path):
    which = lambda name: "/sample/java" if name == "java" else None   # noqa: E731
    version = lambda text: (lambda cmd, **k: SimpleNamespace(returncode=0, stdout="", stderr=text))   # noqa: E731
    assert sc.java(context(tmp_path, which=which, run=version('openjdk version "21.0.2"'))) == (True, "Java 21 at /sample/java", "")
    ok, detail, fix = sc.java(context(tmp_path, which=which, run=version('java version "1.8.0_292"')))
    assert not ok and detail == "/sample/java is Java 8; Fuseki 6.2.0 needs 21 or later" and "Install a Java 21 runtime" in fix
    assert sc.java(context(tmp_path))[1] == "Java was not found"


def test_each_jar_is_checked_by_checksum(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    ok, detail, fix = sc.fuseki_jar(ctx)
    assert not ok and detail.endswith("jena-fuseki-server-6.2.0.jar is missing")
    assert fix == ("Download jena-fuseki-server-6.2.0.jar from https://repo1.maven.org/maven2/org/apache/jena/jena-fuseki-server/6.2.0/ "
                   f"and save it as {tmp_path / 'jena-fuseki-server-6.2.0.jar'}")
    (tmp_path / "robot.jar").write_bytes(b"not robot")
    ok, detail, fix = sc.robot_jar(ctx)
    assert not ok and hashlib.sha256(b"not robot").hexdigest() in detail and "robot.jar (ROBOT 1.9.10) again" in fix
    assert sc.ROBOT_SHA256 == "16a73c074f3df359a7338a84b4e0788785fe06117f931bb9796e9619ea776105"
    monkeypatch.setattr(sc, "ROBOT_SHA256", hashlib.sha256(b"not robot").hexdigest())
    assert sc.robot_jar(ctx) == (True, f"{tmp_path / 'robot.jar'} has the pinned SHA-256", "")


def test_bash_on_windows_is_git_bash_and_never_the_linux_subsystems(tmp_path):
    git = tmp_path / "Git"
    (git / "bin").mkdir(parents=True)
    (git / "cmd").mkdir()
    (git / "bin" / "bash.exe").write_text("", encoding="utf-8")
    (tmp_path / "System32").mkdir()
    (tmp_path / "System32" / "bash.exe").write_text("", encoding="utf-8")
    wsl = str(tmp_path / "System32" / "bash.exe")
    beside_git = lambda name: str(git / "cmd" / "git.exe") if name == "git" else wsl   # noqa: E731
    assert sc.find_bash(None, {}, beside_git, windows=True) == git / "bin" / "bash.exe"
    only_wsl = lambda name: wsl if name == "bash" else None   # noqa: E731
    assert sc.find_bash(None, {}, only_wsl, windows=True) is None
    assert sc.find_bash(None, {"ProgramFiles": str(tmp_path)}, only_wsl, windows=True) == tmp_path / "Git" / "bin" / "bash.exe"
    assert sc.find_bash(git / "bin" / "bash.exe", {}, lambda name: None, windows=True) == git / "bin" / "bash.exe"
    assert sc.find_bash(tmp_path / "gone.exe", {}, beside_git, windows=True) is None
    assert sc.find_bash(None, {}, lambda name: "/usr/bin/bash", windows=False) == Path("/usr/bin/bash")
    ok, detail, fix = sc.bash(context(tmp_path / "s"))
    assert not ok and "scripts/check.sh is a bash script" in detail and "Install Git for Windows" in fix


def test_the_check_script_needs_python3_and_uv_inside_bash(tmp_path):
    bash = tmp_path / "bash"
    bash.write_text("", encoding="utf-8")
    calls = []
    def run(cmd, **k):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="3 12\nuv 0.9.2\n", stderr="")
    ctx = context(tmp_path / "s", run=run, bash=f'bash = "{bash.as_posix()}"')
    assert sc.check_script_tools(ctx) == (True, "inside bash: python3 3.12 and uv 0.9.2", "")
    assert calls == [[str(bash), "-c", "python3 -c 'import sys; print(sys.version_info[0], sys.version_info[1])' && uv --version"]]
    ctx.run = lambda cmd, **k: SimpleNamespace(returncode=127, stdout="", stderr="uv: command not found")
    ok, detail, fix = sc.check_script_tools(ctx)
    assert not ok and "python3 or uv was not found" in detail and fix.startswith("Run py -m pip install uv")


def test_the_databricks_cli_must_run_and_the_profile_must_be_signed_in(tmp_path):
    calls = []
    def run(cmd, **k):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="Databricks CLI v1.25.0\n", stderr="")
    which = lambda name: "/sample/databricks" if name == "databricks" else None   # noqa: E731
    ctx = context(tmp_path, run=run, which=which)
    assert sc.databricks_cli(ctx) == (True, "Databricks CLI v1.25.0 at /sample/databricks", "")
    assert sc.databricks_auth(ctx) == (True, "signed in through the profile DEFAULT", "")
    assert calls == [["/sample/databricks", "--version"],
                     ["/sample/databricks", "current-user", "me", "--profile", "DEFAULT", "--output", "json"]]
    ctx.run = lambda cmd, **k: SimpleNamespace(returncode=1, stdout="", stderr="cannot configure default credentials")
    assert sc.databricks_auth(ctx) == (False, "the profile DEFAULT is not signed in",
                                       "databricks auth login --host <your workspace> --profile DEFAULT")
    ok, detail, fix = sc.databricks_cli(context(tmp_path))
    assert not ok and detail == "the Databricks CLI was not found" and "winget install Databricks.DatabricksCLI" in fix
    assert sc.find_databricks(stores_support.local_settings(tmp_path, cli='cli = "gone.exe"'), which) is None


class Versions:
    """A Neo4j session that answers the two version questions."""

    def __init__(self, kernel="2025.06.2", n10s="2025.06.1", apoc="2025.06.2"):
        self.kernel, self.n10s, self.apoc = kernel, n10s, apoc

    def run(self, query, **k):
        if "dbms.components" in query:
            return stores_support.Result([{"v": self.kernel}])
        if self.n10s is None:
            raise RuntimeError("Unknown function 'n10s.version'")
        assert query == "RETURN n10s.version() AS n10s, apoc.version() AS apoc"
        return stores_support.Result([{"n10s": self.n10s, "apoc": self.apoc}])

    def __enter__(self): return self
    def __exit__(self, *exc): return None


def test_the_local_neo4j_needs_the_pinned_versions_of_itself_and_both_plugins(tmp_path):
    def connect(session):
        return lambda neo4j: stores_support.FakeDriver({"neo4j": session})
    assert sc.neo4j_local(context(tmp_path, connect=connect(Versions()))) == (
        True, "Neo4j 2025.06.2, n10s 2025.06.1, APOC 2025.06.2, database neo4j", "")
    ok, detail, fix = sc.neo4j_local(context(tmp_path, connect=connect(Versions(n10s=None))))
    assert not ok and detail == "Neo4j 2025.06.2 answers, but n10s or APOC does not" and "install the plugins n10s 2025.06.1 and APOC 2025.06.2" in fix
    ok, detail, _ = sc.neo4j_local(context(tmp_path, connect=connect(Versions(apoc="2025.05.0"))))
    assert not ok and detail == "Neo4j 2025.06.2, n10s 2025.06.1, APOC 2025.05.0"
    def down(neo4j):
        raise ConnectionError(f"{neo4j.uri} refused")
    ok, detail, fix = sc.neo4j_local(context(tmp_path, connect=down))
    assert (ok, detail) == (False, "the local Neo4j did not answer (ConnectionError)") and fix.startswith("Start the DBMS in Neo4j Desktop")


def test_the_plugin_jars_are_checked_only_when_a_folder_is_named(tmp_path):
    assert sc.neo4j_plugins(context(tmp_path))[1].startswith("skipped")
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "apoc.jar").write_bytes(b"some other jar")
    ok, detail, fix = sc.neo4j_plugins(context(tmp_path, plugins_folder='plugins_folder = "plugins"'))
    assert not ok and detail == f"{tmp_path / 'plugins'} lacks n10s 2025.06.1, APOC Core 2025.06.2"
    assert fix == f"Put neosemantics-2025.06.1.jar and apoc-2025.06.2-core.jar in {tmp_path / 'plugins'} and restart the DBMS"


def test_the_enterprise_database_must_be_reachable_and_be_the_named_one(tmp_path):
    db = stores_support.FakeNeo4j(TARGET)
    db.add(["Resource"], 3)
    there = lambda neo4j: stores_support.FakeDriver({TARGET: db})   # noqa: E731
    assert sc.neo4j_enterprise(context(tmp_path, connect=there)) == (True, f"database {TARGET} is there and holds 3 node(s)", "")
    assert db.writes() == []
    other = lambda neo4j: stores_support.FakeDriver({TARGET: stores_support.FakeNeo4j("neo4j")})   # noqa: E731
    ok, detail, fix = sc.neo4j_enterprise(context(tmp_path, connect=other))
    assert not ok and "the server opened the database neo4j" in detail and fix.startswith(f"Ask the server's administrator for the database {TARGET}")
    gone = lambda neo4j: stores_support.FakeDriver({})   # noqa: E731
    ok, detail, fix = sc.neo4j_enterprise(context(tmp_path, connect=gone))
    assert (ok, detail) == (False, "the Enterprise server did not answer (LookupError)") and "[neo4j.enterprise]" in fix


def test_the_command_prints_one_fix_per_failure_and_exits_1(tmp_path, capsys):
    make = lambda stores: context(tmp_path, version=(3, 10, 0))   # noqa: E731
    assert sc.main(["--only", "python", "--only", "local-settings"], context=make) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("FAIL python") and out[1].startswith("     fix: Install Python 3.11 or later")
    assert out[2].startswith("ok   local-settings") and out[3] == "1 of 2 checks passed; fix the 1 above and run this again"
    assert sc.main(["--only", "local-settings"], context=make) == 0
    assert sc.main(["--list"]) == 0 and capsys.readouterr().out.splitlines()[-14:] == list(sc.CHECKS)
    with pytest.raises(SystemExit):
        sc.main(["--only", "no-such-check"])
