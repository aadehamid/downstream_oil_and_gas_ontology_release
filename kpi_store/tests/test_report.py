"""The report's format: build, validate, write, read, and clear."""
import datetime as dt
import json

import pytest

from kpi_store import report

NOW = dt.datetime(2026, 11, 11, 12, 30, 5, tzinfo=dt.timezone.utc)


def row(kind="column-renamed", **change):
    base = {"kind": kind, "blocks": kind in report.BLOCKING_KINDS, "object": "idp_sbx.gold_sample.sample_fact",
            "ontology_value": "OldName", "found_value": "New_Name", "evidence": "made up, with a comma",
            "proposed_fix": {"action": "rename-column", "module": "data-product", "from": "OldName", "to": "New_Name"},
            "recommended": "accept", "decision": "", "decided_by": "", "note": ""}
    return {**base, **change}


def build(rows):
    run = report.new_run(NOW, "a" * 64, "b" * 64)
    return report.build("KPI Store 1.1", {"technical-graph": "1.0.0", "data-product": "1.2.0"}, run, rows,
                        {"object_names": 33, "table_edges": 40, "metric_view_sources": 3})


def test_a_built_report_has_the_agreed_shape():
    r = build([row(), row("object-extra", recommended="reject")])
    assert list(r) == ["format", "release", "ontology", "run", "blocked", "passes", "rows"]
    assert r["format"] == 1 and r["release"] == "KPI Store 1.1" and r["blocked"] is True
    assert r["ontology"] == {"data-product": "1.2.0", "technical-graph": "1.0.0"}
    assert r["run"]["at"] == "2026-11-11T12:30:05Z" and r["run"]["id"].startswith("20261111T123005Z-") and len(r["run"]["id"]) == 25
    assert r["run"]["settings_sha256"] == "a" * 64 and r["run"]["zip_sha256"] == "b" * 64
    assert r["passes"] == {"object_names": 33, "table_edges": 40, "metric_view_sources": 3}
    assert [x["id"] for x in r["rows"]] == ["R001", "R002"]
    assert list(r["rows"][0]) == ["id", "kind", "blocks", "object", "ontology_value", "found_value", "evidence", "proposed_fix",
                                 "recommended", "decision", "decided_by", "note"]
    assert build([row("column-case")])["blocked"] is False


def test_the_kinds_that_block_are_the_five_agreed_ones():
    assert report.BLOCKING_KINDS == ("object-missing", "object-renamed", "column-missing", "column-renamed", "edge-missing")
    assert report.OTHER_KINDS == ("column-case", "object-extra", "measure-link", "second-source", "no-lineage", "stale-data",
                                  "migration-pair", "question")
    assert report.DECISIONS == ("accept", "reject", "environment setting")


@pytest.mark.parametrize("change, message", [
    (lambda r: r.update(format=2), "format is 2"),
    (lambda r: r.update(blocked=False), "blocked must be true exactly when a row blocks"),
    (lambda r: r["rows"][0].update(kind="column-vanished"), "unknown kind"),
    (lambda r: r["rows"][0].update(blocks=False), "blocks must be True for kind column-renamed"),
    (lambda r: r["rows"][0].update(decision="maybe"), "decision must be empty or one of"),
    (lambda r: r["rows"][0].update(decision="accept"), "a decision needs decided_by"),
    (lambda r: r["rows"][0].pop("note"), "must hold exactly"),
    (lambda r: r["rows"][1].update(id="R001"), "used twice"),
    (lambda r: r["rows"][0].update(proposed_fix="rename"), "proposed_fix must be an object"),
    (lambda r: r["passes"].update(table_edges="40"), "passes must hold a whole number"),
    (lambda r: r["run"].pop("zip_sha256"), "run must hold"),
])
def test_a_report_that_departs_from_the_format_is_refused(change, message):
    r = build([row(), row("object-extra")])
    change(r)
    with pytest.raises(report.ReportError, match=message):
        report.validate(r)


def test_write_and_read_round_trip_with_lf_line_endings(tmp_path):
    r = build([row(), row("measure-link", evidence='a "quoted" filter\nin two lines')])
    json_path, csv_path = report.write(r, tmp_path / "out")
    assert (json_path.name, csv_path.name) == ("discovery-report.json", "discovery-report.csv")
    assert report.read(json_path) == r
    assert b"\r" not in json_path.read_bytes() and b"\r" not in csv_path.read_bytes()
    lines = csv_path.read_text(encoding="utf-8").split("\n")
    assert lines[0] == "id,kind,blocks,object,ontology_value,found_value,evidence,proposed_fix,recommended,decision,decided_by,note"
    assert lines[1].startswith('R001,column-renamed,true,idp_sbx.gold_sample.sample_fact,OldName,New_Name,"made up, with a comma","{""action"": ""rename-column""')
    with pytest.raises(report.ReportError, match="cannot read the report"):
        report.read(tmp_path / "missing.json")
    (tmp_path / "bad.json").write_text(json.dumps({"format": 1}), encoding="utf-8")
    with pytest.raises(report.ReportError, match="rows is not a list"):
        report.read(tmp_path / "bad.json")


def test_a_report_is_cleared_when_every_blocking_row_has_a_decision(tmp_path):
    r = build([row(), row("object-extra"), row("edge-missing")])
    assert not report.is_cleared(r)
    _, csv_path = report.write(r, tmp_path)
    text = csv_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    lines[1] = lines[1][: -len(",,,")] + ",accept,the owner,checked against the view"
    csv_path.write_text("﻿" + "\r\n".join(lines), encoding="utf-8")   # as a spreadsheet saves it
    half = report.apply_csv_decisions(r, csv_path)
    assert (half["rows"][0]["decision"], half["rows"][0]["decided_by"], half["rows"][0]["note"]) == ("accept", "the owner", "checked against the view")
    assert not report.is_cleared(half)
    lines[3] = lines[3][: -len(",,,")] + ",environment setting,the owner,"
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    assert report.is_cleared(report.apply_csv_decisions(r, csv_path))
    lines[2] = lines[2].replace("R002", "R009")
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(report.ReportError, match="R009"):
        report.apply_csv_decisions(r, csv_path)
