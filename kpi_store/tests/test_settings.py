"""The settings file: what it must hold, and that a wrong file stops with a SettingsError."""
import hashlib

import pytest

from kpi_store import settings
from kpi_store.tests import support


def test_the_example_file_parses_to_the_values_it_shows():
    s = support.make_settings()
    assert (s.zip_name, s.write_catalog, s.write_schema, s.tech_graph_schema, s.volume) == \
        ("kpi-store-1.1.zip", "idp_sbx", "kpi_store", "tech_graph", "releases")
    assert s.read_catalogs == ("idp_sbx", "synapse_dev")
    assert s.triples_table == "idp_sbx.kpi_store.epm_triples"
    assert s.markers_table == "idp_sbx.kpi_store.epm_store_markers"
    assert s.write_schemas == ("idp_sbx.kpi_store", "idp_sbx.tech_graph")
    assert s.skip_schemas == ("information_schema", "bronze_replica_*", "kpi_store_poc")
    assert s.skip_tables == ("*__ct", "attrep_*")
    assert s.genie_spaces == () and s.warehouse_id == ""
    assert s.sha256 == hashlib.sha256(support.SETTINGS_TEXT.encode("utf-8")).hexdigest()


def test_names_translate_the_catalog_and_ignore_case():
    s = support.make_settings(read_catalogs='read_catalogs = ["workspace", "sources"]', idp_sbx='idp_sbx = "workspace"',
                              synapse_dev='synapse_dev = "sources"')
    assert s.environment_name("IDP_SBX.gold_commercial_core.Some_Table") == "workspace.gold_commercial_core.Some_Table"
    assert s.environment_name("synapse_dev.replica_mpr.pricedetail") == "sources.replica_mpr.pricedetail"
    assert s.environment_name("unmapped.a.b") == "unmapped.a.b"


def test_skip_rules_ignore_case_and_cover_schemas_and_tables():
    s = support.make_settings()
    assert s.skipped("Bronze_Replica_MPR") and s.skipped("information_schema") and s.skipped("kpi_store_poc")
    assert not s.skipped("replica_mpr") and not s.skipped("kpi_store")
    assert s.skipped("replica_mpr", "PriceDetail__CT") and s.skipped("replica_mips", "attrep_status")
    assert not s.skipped("replica_mpr", "pricedetail")


@pytest.mark.parametrize("change, message", [
    ({"sha256": 'sha256 = "abc"'}, "64 lower-case hexadecimal"),
    ({"zip": 'zip = "../kpi-store-1.1.zip"'}, "file name ending in .zip"),
    ({"write_catalog": 'write_catalog = "idp sbx; DROP"'}, "letters, digits and _"),
    ({"tech_graph_schema": 'tech_graph_schema = "kpi_store"'}, "must differ"),
    ({"read_catalogs": "read_catalogs = []"}, "at least one"),
    ({"read_catalogs": 'read_catalogs = ["idp_sbx", "synapse_dev", "system"]'}, "must not name system"),
    ({"read_catalogs": 'read_catalogs = "idp_sbx"'}, "must be a list"),
    ({"synapse_dev": 'synapse_dev = "other_sources"'}, "read_catalogs does not name"),
    ({"tables": 'tables = ["*__ct", "x\'; --"]'}, "which is not a name or a"),
    ({"spaces": "spaces = [7]"}, "list of strings"),
    ({"volume": 'volumes = "releases"'}, "unknown key 'volumes'"),
    ({"write_schema": "# write_schema left out"}, "lacks 'write_schema'"),
])
def test_a_wrong_value_is_refused(change, message):
    with pytest.raises(settings.SettingsError, match=message):
        support.make_settings(**change)


def test_a_missing_table_an_unknown_table_and_bad_toml_are_refused():
    text = support.SETTINGS_TEXT
    with pytest.raises(settings.SettingsError, match=r"table \[genie\] is missing"):
        settings.parse(text.split("[genie]")[0].encode())
    with pytest.raises(settings.SettingsError, match=r"unknown table \[token\]"):
        settings.parse((text + '\n[token]\nvalue = "x"\n').encode())
    with pytest.raises(settings.SettingsError, match="not valid TOML"):
        settings.parse(b"[release\nzip = ")


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(settings.SettingsError, match="cannot read the settings file"):
        settings.load(tmp_path / "kpi_store.toml")


def test_the_zip_must_be_beside_the_settings_and_have_the_named_checksum(tmp_path):
    data = b"made-up zip bytes"
    good = hashlib.sha256(data).hexdigest()
    s = support.make_settings(tmp_path, sha256=f'sha256 = "{good}"')
    with pytest.raises(settings.SettingsError, match="is not beside the settings file"):
        settings.check_zip(s)
    (tmp_path / "kpi-store-1.1.zip").write_bytes(data)
    assert settings.check_zip(s) == good
    (tmp_path / "kpi-store-1.1.zip").write_bytes(data + b"!")
    with pytest.raises(settings.SettingsError, match="SHA-256 is .*, not the"):
        settings.check_zip(s)
