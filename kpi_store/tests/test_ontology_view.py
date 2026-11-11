"""The ontology side: version order, the newest package, and the facts the data-product package holds."""
import pytest

from kpi_store import ontology_view as ov
from kpi_store.tests import support

RELEASES = support.ROOT / ov.RELEASES


def package(module, version):
    """A released package's folder, whether it is still the newest or has moved to releases/previous/."""
    for folder in (RELEASES / module / version, RELEASES / "previous" / module / version):
        if folder.is_dir():
            return folder
    raise AssertionError(f"{module} {version} is not in this release")


def test_a_correction_version_is_newer_than_its_plain_version_and_older_than_the_next_patch():
    order = ["1.2.0", "1.2.1", "1.2.1-correction.1", "1.2.1-correction.2", "1.2.1-correction.10", "1.2.2", "1.10.0", "2.0.0"]
    assert sorted(reversed(order), key=ov.version_key) == order
    assert ov.version_key("1.2.1-correction.1") == (1, 2, 1, 1) and ov.version_key("1.2.1") == (1, 2, 1, 0)
    for name in ("previous", "1.2", "1.2.1-rc.1", "1.2.1-correction", "v1.2.1", "1.2.1-correction.1.bak"):
        assert ov.version_key(name) is None


def test_the_newest_version_reads_a_correction_and_needs_a_manifest(tmp_path):
    for version, released in (("1.2.0", True), ("1.2.1-correction.1", True), ("1.2.1-correction.2", False), ("1.10.0-draft", True)):
        (tmp_path / "data-product" / version).mkdir(parents=True)
        if released:
            (tmp_path / "data-product" / version / "manifest.json").write_text("{}", encoding="utf-8")
    assert ov.newest_version("data-product", tmp_path) == "1.2.1-correction.1"
    (tmp_path / "previous" / "data-product" / "9.9.9").mkdir(parents=True)
    (tmp_path / "empty").mkdir()
    assert ov.newest_versions(tmp_path) == {"data-product": "1.2.1-correction.1"}
    with pytest.raises(ov.ReleaseError, match="holds no released package"):
        ov.newest_version("empty", tmp_path)


def test_data_product_1_2_0_holds_33_objects_40_table_edges_and_8_columns():
    view = ov.read_packages(package("data-product", "1.2.0"), package("kpi", ov.newest_version("kpi", RELEASES)))
    assert len(view.objects) == 33
    layers = [o.layer for o in view.objects.values()]
    assert {layer: layers.count(layer) for layer in set(layers)} == {"replica": 21, "silver": 7, "gold": 2, "metric-view": 3}
    assert len(view.edges) == 40   # column edges use the same predicate and are not counted
    assert len(view.columns) == 8
    gold = "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"
    assert sorted(c.name for c in view.columns if c.table == gold) == ["ChangeValue", "Previous_amount", "assessment_amount"]
    change = next(c for c in view.columns if c.name == "ChangeValue")
    assert change.derived_from == (("idp_sbx.silver_udm_core.mips_price_assessment_fact", "Assessment_Amount"),
                                   ("idp_sbx.silver_udm_core.mips_price_assessment_fact", "Previous_Amount"))
    assert view.upstream("IDP_SBX.semantic_sem_commercial.mips_mpr_executive_summary_fact_vw") == {gold}
    summary_view = view.objects["idp_sbx.semantic_sem_commercial.mips_mpr_executive_summary_fact_vw"]
    assert summary_view.measures == ("additional-market-prices", "crude-prices", "distillate-prices", "gasoline-prices")
    assert sorted(view.measures) == ["additional-market-prices", "crack-spreads", "crude-prices", "distillate-prices", "gasoline-prices"]
    assert view.measures["crack-spreads"].label == "Crack Spreads Pricing"
    assert {o.full_name.split(".")[0] for o in view.objects.values()} == {"idp_sbx", "synapse_dev"}


def test_read_takes_the_newest_package_of_each_module(tmp_path):
    support.small_release(tmp_path, versions=("1.0.0", "1.0.1-correction.1"), fact="renamed_fact")
    view = ov.read(tmp_path)
    assert view.versions == {"data-product": "1.0.1-correction.1", "kpi": "1.0.0"}
    assert sorted(view.objects) == ["idp_sbx.gold_sample.renamed_fact", "idp_sbx.silver_sample.middle_dim", "synapse_dev.replica_sample.source_table"]
    assert view.edges == {("idp_sbx.gold_sample.renamed_fact", "idp_sbx.silver_sample.middle_dim"),
                          ("idp_sbx.silver_sample.middle_dim", "synapse_dev.replica_sample.source_table")}
    assert view.measures["sample-prices"].label == "Sample Market Pricing"
    assert ov.release_name(tmp_path) == "KPI Store 1.1"


def test_a_release_without_its_packages_or_its_name_is_refused(tmp_path):
    with pytest.raises(ov.ReleaseError, match="is missing"):
        ov.read(tmp_path)
    with pytest.raises(ov.ReleaseError, match="names no release"):
        ov.release_name(tmp_path)


def test_a_table_derived_from_something_that_is_not_a_platform_table_gives_no_edge(tmp_path):
    support.small_release(tmp_path)
    package_file = tmp_path / ov.RELEASES / "data-product" / "1.0.0" / "data-product.ttl"
    with package_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write("t:fact prov:wasDerivedFrom <urn:sample:a-report> .\n")
    assert len(ov.read(tmp_path).edges) == 2
