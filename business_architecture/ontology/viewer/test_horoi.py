"""The reference page (horoi_viewer/index.html): its data, its build record and whether the committed page is current."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location("horoi_builder", HERE / "build_horoi.py")
horoi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(horoi)

TTL = """@prefix x: <https://example.test/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
<https://example.test/modules/MODULE> a owl:Ontology ;
    dcterms:title "The MODULE module"@en ;
    dcterms:description "What MODULE holds."@en REQUIRES .
x:MODULE-Thing a owl:Class ; rdfs:label "A MODULE term"@en ; rdfs:subClassOf [ a owl:Restriction ] .
"""


def package(root, module, version="1.0.0", requires=(), ttl=TTL):
    folder = root / "business_architecture/ontology/releases" / module / version
    folder.mkdir(parents=True)
    text = ttl.replace("MODULE", module).replace("REQUIRES", "".join(f" ;\n    dcterms:requires <{r}>" for r in requires))
    with (folder / (module + ".ttl")).open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    manifest = {
        "module": module,
        "version": version,
        "release_candidate": False,
        "ontology_iri": "https://example.test/modules/" + module,
        "files": {module + ".ttl": hashlib.sha256(text.encode("utf-8")).hexdigest()},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def embedded(page):
    return json.loads(page.split('<script id="ontology-data" type="application/json">')[1].split("</script>")[0])


def two_modules(root):
    package(root, "zeta", requires=["https://example.test/modules/alpha/2.0.0", "https://example.test/modules/Other/1.0.0"])
    package(root, "alpha", version="2.0.0")


def test_the_data_lists_each_module_from_its_own_ontology_statement(tmp_path):
    two_modules(tmp_path)
    data = horoi.build_data(tmp_path)
    assert data["release"] == "KPI Store 1.1"
    assert "sourceCommit" not in data
    assert data["horoiVersion"] == "0.2.0"
    assert data["horoiCommit"] == "e0660af0f795ebfeb6f1354a69b3b0c47ebafba6"
    assert data["referenceModules"] == ["alpha", "zeta"]
    assert data["moduleInfo"] == [
        {
            "name": "alpha",
            "version": "2.0.0",
            "id": "https://example.test/modules/alpha",
            "label": "The alpha module",
            "description": "What alpha holds.",
            "requires": [],
        },
        {
            "name": "zeta",
            "version": "1.0.0",
            "id": "https://example.test/modules/zeta",
            "label": "The zeta module",
            "description": "What zeta holds.",
            "requires": ["https://example.test/modules/Other/1.0.0", "https://example.test/modules/alpha/2.0.0"],
        },
    ]
    # The two classes are terms. The two ontology statements and the two anonymous restrictions are not.
    assert data["referenceTerms"] == ["https://example.test/alpha-Thing", "https://example.test/zeta-Thing"]


def test_a_module_without_its_ontology_statement_or_title_cannot_be_built(tmp_path):
    package(tmp_path, "alpha", ttl="@prefix x: <https://example.test/> .\nx:MODULE-Thing a <http://www.w3.org/2002/07/owl#Class> .\n")
    with pytest.raises(ValueError, match="No package states the ontology"):
        horoi.build_data(tmp_path)
    other = tmp_path / "other"
    package(other, "alpha", ttl=TTL.replace('    dcterms:title "The MODULE module"@en ;\n', ""))
    with pytest.raises(ValueError, match="exactly one title"):
        horoi.build_data(other)


def test_the_build_writes_the_page_and_a_record_that_agree(tmp_path):
    two_modules(tmp_path)
    out = tmp_path / "horoi_viewer"
    horoi.build(tmp_path, out)
    raw = (out / "index.html").read_bytes()
    assert b"\r" not in raw and b"/* EMBEDDED_DATA */" not in raw
    record = json.loads((out / "build.json").read_text(encoding="utf-8"))
    assert list(record) == ["release", "horoi_version", "horoi_commit", "modules", "inputs", "reference_terms", "triples_available", "index_sha256"]
    assert record["release"] == "KPI Store 1.1"
    assert record["modules"] == [{"name": "alpha", "version": "2.0.0"}, {"name": "zeta", "version": "1.0.0"}]
    assert [i["path"] for i in record["inputs"]] == [
        "business_architecture/ontology/releases/alpha/2.0.0/alpha.ttl",
        "business_architecture/ontology/releases/zeta/1.0.0/zeta.ttl",
    ]
    assert record["reference_terms"] == 2
    # alpha states 7 triples: 3 on its ontology, 3 on its class, 1 on the restriction. zeta adds its 2 requirements.
    assert record["triples_available"] == 16
    assert record["index_sha256"] == hashlib.sha256(raw).hexdigest()
    assert embedded(raw.decode("utf-8"))["referenceModules"] == ["alpha", "zeta"]


def test_two_builds_write_the_same_bytes(tmp_path):
    two_modules(tmp_path)
    horoi.build(tmp_path, tmp_path / "one")
    horoi.build(tmp_path, tmp_path / "two")
    for name in ("index.html", "build.json"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_the_check_names_each_stale_file_and_writes_nothing(tmp_path, capsys):
    two_modules(tmp_path)
    out = tmp_path / "horoi_viewer"
    assert horoi.stale(tmp_path, out) == ["index.html", "build.json"]  # nothing built yet
    horoi.build(tmp_path, out)
    assert horoi.stale(tmp_path, out) == []
    assert horoi.main(["--source", str(tmp_path), "--out", str(out), "--check"]) == 0
    # A hand edit of the record alone is caught.
    record = out / "build.json"
    record.write_text(record.read_text(encoding="utf-8").replace("KPI Store 1.1", "Another name"), encoding="utf-8")
    assert horoi.stale(tmp_path, out) == ["build.json"]
    horoi.build(tmp_path, out)
    # A newer package makes both files stale.
    package(tmp_path, "alpha", version="2.1.0")
    before = (out / "index.html").read_bytes(), record.read_bytes()
    assert horoi.stale(tmp_path, out) == ["index.html", "build.json"]
    assert horoi.main(["--source", str(tmp_path), "--out", str(out), "--check"]) == 1
    assert "index.html and build.json differ from a fresh build" in capsys.readouterr().err
    assert ((out / "index.html").read_bytes(), record.read_bytes()) == before


def test_the_committed_page_and_record_equal_a_fresh_build():
    assert horoi.stale(ROOT, ROOT / "horoi_viewer") == [], "run build_horoi.py --source . --out horoi_viewer"


def test_the_committed_page_holds_this_tree_and_names_no_outside_commit():
    # Written by hand from the release folders and the notice file.
    text = (ROOT / "horoi_viewer/index.html").read_text(encoding="utf-8")
    data = embedded(text)
    assert data["release"] == "KPI Store 1.1"
    assert "sourceCommit" not in data and "sourceCommit" not in text
    assert "EPM" not in text.split('<script id="ontology-data"')[0]
    assert {m["name"]: m["version"] for m in data["moduleInfo"]} == {
        "core": "2.4.0",
        "data-product": "1.2.0",
        "integration": "2.5.0",
        "kpi": "1.3.0",
        "lane": "1.1.0",
        "logical-model": "1.0.0",
        "market-data": "1.1.0",
        "organization": "2.2.0",
        "party": "2.1.0",
        "ref-mpc": "1.3.0",
        "system": "1.5.0",
        "technical-graph": "1.1.0",
        "value-stream": "1.2.0",
    }
    record = json.loads((ROOT / "horoi_viewer/build.json").read_text(encoding="utf-8"))
    assert "source_commit" not in record
    assert record["release"] == "KPI Store 1.1"
    # Horoi 0.2.0 is the public release of 2026-11-09, and this is the commit its tag v0.2.0 names.
    assert data["horoiVersion"] == record["horoi_version"] == "0.2.0"
    assert data["horoiCommit"] == record["horoi_commit"] == "e0660af0f795ebfeb6f1354a69b3b0c47ebafba6"
    notice = (ROOT / "horoi_viewer/NOTICE.txt").read_text(encoding="utf-8")
    assert "version 0.2.0 (commit e0660af0f795ebfeb6f1354a69b3b0c47ebafba6, released 2026-11-09)" in notice
    assert "Adapted from Horoi 0.2.0 styles at e0660af0f795ebfeb6f1354a69b3b0c47ebafba6." in text
    assert "33caa8cc916e7efb767a5c2831216ff1cb11c509" not in text


def test_the_page_shows_the_release_name_and_links_only_inside_the_release():
    template = (HERE / "horoi_page.html").read_text(encoding="utf-8")
    assert template.count("/* EMBEDDED_DATA */") == 1
    assert '<div id="release-scope">' in template and "${data.release} · All ontology modules" in template
    # The footer names the Horoi version from the data, so the page cannot show one version and record another.
    assert '<a href="NOTICE.txt" id="credits">Adapted from Horoi · Credits</a>' in template
    assert "`Adapted from Horoi ${data.horoiVersion} · Credits`" in template
    # A group of one measure reads "1 entry", not "1 entries".
    assert '${groups.get(kind).length===1?"entry":"entries"}' in template and "} entries</summary>" not in template
    for link in ("../viewer/index.html", "../business_architecture/ontology/epm-ontology-guide.html", "../business_architecture/ontology/epm-walkthrough.html", "build.json", "NOTICE.txt"):
        assert f'href="{link}"' in template
        assert (ROOT / "horoi_viewer" / link).resolve().is_file()
    assert 'src="http' not in template and "@import" not in template
