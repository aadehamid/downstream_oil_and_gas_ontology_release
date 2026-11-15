"""The local settings file: what it must hold, where it may be, and that a password is never shown."""
from pathlib import Path

import pytest

from kpi_store import local_settings as ls
from kpi_store.tests import stores_support, support


def test_the_example_file_gives_every_setting(tmp_path):
    local = stores_support.local_settings(tmp_path)
    assert local.settings == tmp_path / "kpi_store.toml" and local.run_folder == tmp_path / "runs"
    assert (local.databricks.profile, local.databricks.workspace_folder) == ("DEFAULT", "/Workspace/Shared/kpi_store")
    assert local.databricks.timeout_minutes == 60 and local.databricks.cli is None
    assert local.databricks.environment_version == "2"
    f = local.fuseki
    assert (f.url, f.port, f.dataset, f.is_local) == ("http://127.0.0.1:3030/ds", 3030, "/ds", True)
    assert (f.query_url, f.data_url, f.update_url) == ("http://127.0.0.1:3030/ds/query", "http://127.0.0.1:3030/ds/data",
                                                      "http://127.0.0.1:3030/ds/update")
    assert f.ping_url == "http://127.0.0.1:3030/$/ping" and f.java is None
    assert f.jar == tmp_path / "jena-fuseki-server-6.2.0.jar" and f.data_folder == tmp_path / "fuseki-db"
    assert (local.neo4j_local.uri, local.neo4j_local.username, local.neo4j_local.database) == ("bolt://127.0.0.1:7687", "neo4j", "neo4j")
    assert local.neo4j_local.plugins_folder is None
    assert local.neo4j_enterprise.database == "businessprocessarchitecturegraph"
    assert local.robot_jar == tmp_path / "robot.jar" and local.projection_out == tmp_path / "lpg-out" and local.bash is None


def test_a_password_is_never_in_a_text_form(tmp_path):
    local = stores_support.local_settings(tmp_path, password='password = "s3cret-Value"')
    assert local.neo4j_enterprise.password.reveal() == "s3cret-Value"
    for text in (str(local), repr(local), str(local.neo4j_local), f"{local.neo4j_enterprise.password}"):
        assert "s3cret-Value" not in text
    assert "***" in repr(local.neo4j_local)


def test_a_password_may_come_from_the_environment(tmp_path):
    local = stores_support.local_settings(tmp_path, environ={"SAMPLE_PW": "from-env"}, password='password_env = "SAMPLE_PW"')
    assert local.neo4j_local.password.reveal() == "from-env"
    with pytest.raises(ls.LocalSettingsError, match="SAMPLE_PW, which is not set"):
        stores_support.local_settings(tmp_path, environ={}, password='password_env = "SAMPLE_PW"')


@pytest.mark.parametrize("inside", ["stores.toml", "kpi_store/stores.toml", "KPI_STORE/Stores.TOML"])
def test_a_settings_file_inside_the_release_folder_is_refused_whatever_its_case(tmp_path, inside):
    release = tmp_path / "Release"
    (release / "kpi_store").mkdir(parents=True)
    with pytest.raises(ls.LocalSettingsError, match="inside the release folder"):
        ls.parse(b"", release / inside, {}, release)
    with pytest.raises(ls.LocalSettingsError, match="inside the release folder"):
        ls.load(Path(str(release).upper()) / inside, {}, release)
    assert ls.parse(b"", tmp_path / "stores.toml", {}, release).fuseki is None   # beside the release folder is outside it


def test_the_release_folder_is_the_one_given_not_the_one_the_code_is_in(tmp_path):
    other = tmp_path / "other-release"
    stores_support.local_settings(other / "conf")   # accepted against the code's own folder
    with pytest.raises(ls.LocalSettingsError, match="the local settings file is inside the release folder"):
        ls.load(other / "conf" / "stores.toml", {}, release_root=other)
    outside = stores_support.local_settings(tmp_path / "local", run_folder=f'run_folder = "{(other / "runs").as_posix()}"')
    with pytest.raises(ls.LocalSettingsError, match=r"\[release\] run_folder is inside the release folder"):
        ls.check_outside(outside, other)
    assert ls.check_outside(outside, tmp_path / "elsewhere") is outside


def test_is_inside_compares_whole_folder_names_without_case(tmp_path):
    assert ls.is_inside(tmp_path / "REL" / "a.toml", tmp_path / "rel")
    assert ls.is_inside(tmp_path / "rel", tmp_path / "rel")
    assert not ls.is_inside(tmp_path / "rel-other" / "a.toml", tmp_path / "rel")
    assert not ls.is_inside(tmp_path, tmp_path / "rel")


@pytest.mark.parametrize("key, line, table", [
    ("run_folder", 'run_folder = "{root}/runs"', r"\[release\] run_folder"),
    ("settings", 'settings = "{root}/kpi_store/kpi_store.toml"', r"\[release\] settings"),
    ("out", 'out = "{root}/lpg-out"', r"\[projection\] out"),
    ("data_folder", 'data_folder = "{root}/fuseki-db"', r"\[fuseki\] data_folder"),
])
def test_a_folder_the_runner_writes_to_may_not_be_inside_the_release(tmp_path, key, line, table):
    with pytest.raises(ls.LocalSettingsError, match=table + " is inside the release folder"):
        stores_support.local_settings(tmp_path, **{key: line.format(root=support.ROOT.as_posix())})


@pytest.mark.parametrize("replace, message", [
    ({"database": 'database = "system"'}, "never the system database"),
    ({"database": 'database = " SYSTEM "'}, "never the system database"),
    ({"database": 'database = ""'}, "must name a database"),
    ({"uri": 'uri = "http://127.0.0.1:7474"'}, "must be a bolt:// or neo4j:// address"),
    ({"uri": 'uri = "bolt://neo4j:pw@127.0.0.1:7687"'}, "must not hold a user name or a password"),
    ({"url": 'url = "http://127.0.0.1:3030"'}, "must be a dataset URL"),
    ({"url": 'url = "http://127.0.0.1:3030/ds/query"'}, "must be a dataset URL"),
    ({"workspace_folder": 'workspace_folder = "Shared/kpi_store"'}, "must start with /"),
    ({"timeout_minutes": "timeout_minutes = 0"}, "must be 1 or more"),
    ({"timeout_minutes": 'timeout_minutes = "60"'}, "must be a whole number"),
    ({"environment_version": "environment_version = 2"}, "must be text"),
    ({"environment_version": 'environment_version = "latest"'}, 'must be a number in quotes, such as "2"'),
    ({"profile": 'profile = " "'}, "must name a Databricks CLI profile"),
    ({"password": 'password = ""'}, "exactly one of password and password_env"),
    ({"password": 'password = "a"\npassword_env = "B"'}, "exactly one of password and password_env"),
    ({"jar": 'jarr = "x.jar"'}, "unknown key 'fuseki.jarr'"),
])
def test_a_wrong_value_is_named(tmp_path, replace, message):
    with pytest.raises(ls.LocalSettingsError, match=message):
        stores_support.local_settings(tmp_path, **replace)


def test_an_unknown_table_and_a_missing_key_are_errors(tmp_path):
    with pytest.raises(ls.LocalSettingsError, match="unknown table 'fusekii'"):
        ls.parse(b'[fusekii]\nurl = "http://127.0.0.1:3030/ds"\n', tmp_path / "s.toml", {}, support.ROOT)
    with pytest.raises(ls.LocalSettingsError, match=r"\[fuseki\] lacks 'jar'"):
        ls.parse(b'[fuseki]\nurl = "http://127.0.0.1:3030/ds"\n', tmp_path / "s.toml", {}, support.ROOT)


def test_broken_toml_is_reported_without_quoting_the_file(tmp_path):
    with pytest.raises(ls.LocalSettingsError) as err:
        ls.parse(b'[neo4j.local]\npassword = "hunter2\n', tmp_path / "s.toml", {}, support.ROOT)
    assert "not valid TOML" in str(err.value) and "hunter2" not in str(err.value)


def test_a_step_names_the_table_it_lacks(tmp_path):
    local = ls.parse(b'[fuseki]\njar = "f.jar"\nurl = "http://127.0.0.1:3030/ds"\n', tmp_path / "s.toml", {}, support.ROOT)
    assert local.need("fuseki").jar == tmp_path / "f.jar" and local.fuseki.data_folder is None
    with pytest.raises(ls.LocalSettingsError, match=r"lacks \[neo4j.enterprise\]"):
        local.need("neo4j_enterprise")
    with pytest.raises(ls.LocalSettingsError, match=r"lacks \[release\]"):
        local.need("run_folder")


def test_the_file_is_named_by_the_argument_or_the_environment(tmp_path):
    assert ls.locate("a.toml", {"KPI_STORE_LOCAL": "b.toml"}) == Path("a.toml")
    assert ls.locate(None, {"KPI_STORE_LOCAL": "b.toml"}) == Path("b.toml")
    with pytest.raises(ls.LocalSettingsError, match="--stores <file>, or set KPI_STORE_LOCAL"):
        ls.locate(None, {})
    with pytest.raises(ls.LocalSettingsError, match="cannot read the local settings file"):
        ls.load(tmp_path / "missing.toml", {}, support.ROOT)


def test_the_example_s_paths_start_at_the_file_s_folder_and_a_tilde_is_the_user_folder(tmp_path, monkeypatch):
    """The example file names no drive and no user, so it holds wherever a person keeps the local folder. The
    release is unpacked into the user folder, whose path differs for every user."""
    assert ":/" not in stores_support.STORES_TEXT.replace("://", "") and "kpi-store-local" not in stores_support.STORES_TEXT
    local = stores_support.local_settings(tmp_path / "any folder")
    here = tmp_path / "any folder"
    assert (local.settings, local.run_folder) == (here / "kpi_store.toml", here / "runs")
    assert (local.fuseki.jar, local.fuseki.data_folder) == (here / "jena-fuseki-server-6.2.0.jar", here / "fuseki-db")
    assert (local.robot_jar, local.projection_out) == (here / "robot.jar", here / "lpg-out")
    # The three programs of a machine without administrator rights, as the runbook writes them.
    local = stores_support.local_settings(here, cli='cli = "databricks-cli/databricks.exe"', java='java = "jdk-21/bin/java.exe"',
                                          bash='bash = "PortableGit/bin/bash.exe"')
    assert (local.databricks.cli, local.fuseki.java, local.bash) == (
        here / "databricks-cli" / "databricks.exe", here / "jdk-21" / "bin" / "java.exe", here / "PortableGit" / "bin" / "bash.exe")
    # ~ is the user folder on every system; a full path stays as written.
    home = tmp_path / "home of Jo Smith"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    full = (tmp_path / "elsewhere" / "robot.jar").as_posix()
    tilde = "~"   # apart from the slash, so that the stand-alone check does not read this line as a path of this machine
    local = stores_support.local_settings(here, run_folder=f'run_folder = "{tilde}/kpi-store-runs"', robot_jar=f'robot_jar = "{full}"')
    assert local.run_folder == home / "kpi-store-runs" and local.robot_jar == Path(full)


def test_the_environment_version_is_2_when_not_set_and_may_be_left_to_the_workspace(tmp_path):
    """Version 2 has Python 3.11, which the rehearsal runs got. A settings file written before the setting
    existed gets it too. An empty value sends no environment, and the workspace chooses."""
    assert ls.ENVIRONMENT_VERSION == "2"
    text = (tmp_path / "stores.toml")
    stores_support.local_settings(tmp_path)
    lines = [line for line in text.read_text(encoding="utf-8").split("\n") if not line.startswith("environment_version")]
    text.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    assert ls.load(text, {}, support.ROOT).databricks.environment_version == "2"
    assert stores_support.local_settings(tmp_path, environment_version='environment_version = ""').databricks.environment_version == ""
    assert stores_support.local_settings(tmp_path, environment_version='environment_version = " 4 "').databricks.environment_version == "4"
