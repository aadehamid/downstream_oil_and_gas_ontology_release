"""The cut tool. Every cut runs on a temporary copy of this tree's ontology folder, never on the tree itself.

fixtures/cut/discovery-report.json is the report the comparison writes for the made-up sandbox workspace
(support.sandbox) against this release, with no decision yet. The expected values below are written by hand.
"""
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from kpi_store import compare, cut, discovery, ontology_view as ov, report as rep
from kpi_store.tests import support

REPORT = support.FIXTURES / "cut" / "discovery-report.json"
ONTOLOGY = Path("business_architecture") / "ontology"
RUN = "20261111T120000Z-0a1b2c3d"
RECORD = ONTOLOGY / "discovery-runs" / f"{RUN}.md"
GOLD = "idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"
SUMMARY_VIEW = "idp_sbx.semantic_sem_commercial.mips_mpr_executive_summary_fact_vw"
EXTRAS = ("R004", "R005", "R006", "R007", "R008", "R009", "R010")
NOW = dt.datetime(2026, 11, 12, 8, 30, tzinfo=dt.timezone.utc)
CORRECTED = {"data-product": ("1.2.0", "1.2.1-correction.1"), "logical-model": ("1.0.0", "1.0.1-correction.1"),
             "technical-graph": ("1.0.0", "1.0.1-correction.1"), "value-stream": ("1.2.0", "1.2.1-correction.1"),
             "integration": ("2.5.0", "2.5.1-correction.1")}

# The report fixture and the versions above are those of the release as shipped. After the first cut of a copy its
# data-product module has moved on, and these tests no longer describe it: they are skipped there.
as_shipped = pytest.mark.skipif(ov.newest_versions(support.ROOT / ov.RELEASES).get("data-product") != "1.2.0",
                                reason="this tree's data-product is no longer 1.2.0; the test cuts the release as shipped")


def release_copy(tmp_path):
    """A release folder that holds what a cut reads and writes: the ontology folder, release.json and the
    stand-alone check's exception list."""
    root = tmp_path / "release"
    shutil.copytree(support.ROOT / ONTOLOGY, root / ONTOLOGY, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(support.ROOT / "release.json", root / "release.json")
    (root / "scripts").mkdir()
    shutil.copy2(support.ROOT / cut.EXCEPTIONS, root / cut.EXCEPTIONS)
    return root


def cleared(tmp_path, decisions, run=RUN, ontology=None, rows=None, name="report"):
    """The fixture report with a decision on the rows named, written to a folder of its own. Returns the JSON path."""
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["run"]["id"] = run
    report["ontology"].update(ontology or {})
    if rows is not None:
        report["rows"] = rows
        report["blocked"] = any(r["blocks"] for r in rows)
    for row in report["rows"]:
        if row["id"] in decisions:
            row["decision"], row["decided_by"] = decisions[row["id"]], "the ontology owner"
    folder = tmp_path / name
    folder.mkdir()
    (folder / rep.JSON_NAME).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return folder / rep.JSON_NAME


class Answers:
    """Stands in for the person at the prompt: gives the answers in order and keeps the prompts."""

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def never(prompt):
    raise AssertionError(f"the cut asked: {prompt}")


def digest(root, skip=("__pycache__",)):
    h = hashlib.sha256()
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in skip)
        for name in sorted(files):
            path = Path(folder) / name
            h.update(path.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def quiet(line):
    pass


def compared(root):
    """The comparison of a release folder with the made-up sandbox workspace, as the load runs it."""
    view = ov.read(root)
    workspace, genie = support.sandbox()
    settings = support.make_settings()
    schemas = {settings.environment_name(o.full_name).rsplit(".", 1)[0] for o in view.objects.values()}
    found = discovery.discover(settings, workspace.run_sql, genie, schemas)
    return compare.compare(view, found, settings, dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.timezone.utc),
                           standing=rep.read_standing(root))


def kinds(result):
    return {k: sum(r["kind"] == k for r in result.rows) for k in {r["kind"] for r in result.rows}}


# ---------- the plan: what a cut would do, with no change to any file ----------

@as_shipped
def test_the_plan_for_the_expected_first_report_sorts_every_row(tmp_path):
    decisions = {"R001": "accept", "R002": "accept", "R003": "accept", "R020": "accept", "R011": "accept", "R019": "accept",
                 **{r: "reject" for r in EXTRAS}}
    report, sums = cut.load_report(cleared(tmp_path, decisions))
    plan = cut.plan(report, support.ROOT, sums)
    by_outcome = {}
    for item in plan.items:
        by_outcome.setdefault(item.outcome, []).append(item.row["id"])
    assert by_outcome == {
        "apply": ["R001", "R002", "R003", "R020"],
        "rejected": list(EXTRAS),
        "needs a minor version": ["R011", "R019"],
        "no decision": ["R012", "R013", "R014", "R015", "R016", "R017", "R018", "R021", "R022", "R023", "R024", "R025", "R026", "R027"],
        "waits": ["R028"]}
    assert plan.versions == CORRECTED
    assert list(plan.versions) == ["data-product", "logical-model", "technical-graph", "value-stream", "integration"]
    # Only the rename that changes more than case is breaking, and its confirmation is the new name.
    assert [(i.row["id"], i.breaking, i.confirm) for i in plan.applied] == [
        ("R001", False, "Assessment_Amount"), ("R002", True, "Change_Value_Amount"), ("R003", False, "Previous_Amount"), ("R020", False, "")]
    columns = (ONTOLOGY / "data-product" / "pricing" / "columns.csv").as_posix()
    tables = (ONTOLOGY / "data-product" / "pricing" / "tables.csv").as_posix()
    slug = "gold-mips-mpr-executive-summary-fact"
    assert plan.applied[1].text == f"column ChangeValue of {GOLD} becomes Change_Value_Amount"
    assert plan.applied[1].changes == [(columns, f"{slug} column ChangeValue", f"{slug} column Change_Value_Amount")] * 2
    assert plan.applied[0].text == f"column assessment_amount of {GOLD} becomes Assessment_Amount (case only)"
    assert plan.applied[3].text == f"{SUMMARY_VIEW} also serves the measure crack-spreads"
    assert plan.applied[3].changes == [(tables, "view-mips-mpr-executive-summary-fact-vw serves gasoline-prices;distillate-prices;crude-prices;additional-market-prices",
                                        "view-mips-mpr-executive-summary-fact-vw serves gasoline-prices;distillate-prices;crude-prices;additional-market-prices;crack-spreads")]
    text = "\n".join(cut.describe(plan))
    assert f"R002 column-renamed: column ChangeValue of {GOLD} becomes Change_Value_Amount  BREAKING" in text
    assert "  data-product 1.2.0 -> 1.2.1-correction.1" in text and "  integration 2.5.0 -> 2.5.1-correction.1" in text
    assert "Needs a minor version, so the cut leaves it (2):" in text and "Waits, so the cut leaves it (1):" in text


def row(n, kind, obj, fix, ontology_value="", found_value="", decision="accept"):
    return {"id": f"R{n:03d}", "kind": kind, "blocks": kind in rep.BLOCKING_KINDS, "object": obj, "ontology_value": ontology_value,
            "found_value": found_value, "evidence": "made up", "proposed_fix": fix, "recommended": "", "decision": decision,
            "decided_by": "the ontology owner", "note": ""}


@as_shipped
def test_the_plan_applies_each_other_action_and_marks_each_removal_and_rename_breaking(tmp_path):
    crack = "idp_sbx.gold_commercial_core.mpr_mips_crack_spread_price_fact"
    detail = "idp_sbx.silver_udm_core.mpr_price_detail_fact"
    rows = [row(1, "object-renamed", crack, {"action": "rename-object", "module": "data-product", "from": crack, "to": crack + "_v2"},
                crack, crack + "_v2"),
            row(2, "column-missing", GOLD, {"action": "remove-column", "module": "data-product", "column": "Previous_amount"}, "Previous_amount"),
            row(3, "edge-missing", GOLD, {"action": "remove-edge", "module": "data-product", "from": GOLD,
                                          "to": "idp_sbx.silver_mdm_core.mips_price_group_dim"}),
            row(4, "object-missing", "prod_cat.semantic_sem_commercial.mips_mpr_benchmark_prices_fact_vw",
                {"action": "remove-object", "module": "data-product", "object": "idp_sbx.semantic_sem_commercial.mips_mpr_benchmark_prices_fact_vw"}),
            row(5, "object-missing", "prod_cat.x.y", {"action": "set-catalog-name", "setting": "names", "ontology_catalog": "idp_sbx"},
                decision="environment setting"),
            row(6, "object-extra", "idp_sbx.gold_commercial_core.sample_margin_fact",
                {"action": "add-object", "module": "data-product", "object": "idp_sbx.gold_commercial_core.sample_margin_fact"}),
            row(7, "question", SUMMARY_VIEW, {"action": "add-edge", "module": "data-product", "from": SUMMARY_VIEW, "to": detail}),
            row(8, "stale-data", GOLD, {"action": "none"}, found_value="2026-09-01T00:00:00")]
    report, sums = cut.load_report(cleared(tmp_path, {}, rows=rows))
    plan = cut.plan(report, support.ROOT, sums)
    assert [(i.row["id"], i.outcome, i.breaking, i.confirm) for i in plan.items] == [
        ("R001", "apply", True, crack + "_v2"), ("R002", "apply", True, "Previous_amount"),
        ("R003", "apply", True, "idp_sbx.silver_mdm_core.mips_price_group_dim"),
        ("R004", "apply", True, "idp_sbx.semantic_sem_commercial.mips_mpr_benchmark_prices_fact_vw"),
        ("R005", "environment setting", False, ""), ("R006", "needs a minor version", False, ""),
        ("R007", "needs a minor version", False, ""), ("R008", "not applied", False, "")]
    assert plan.items[4].text == "in kpi_store.toml, under [names], set idp_sbx to the name this environment gives that catalog"
    held = {name: plan.tables.text(name) for name in cut.TABLES}
    before = cut.Tables(support.ROOT)
    assert crack + "_v2," in held["tables"] and crack + "," not in held["tables"]
    assert "Previous_amount" in before.text("columns") and "Previous_amount" not in held["columns"]
    edge = "gold-mips-mpr-executive-summary-fact,silver-mips-price-group-dim\n"
    assert edge in before.text("lineage") and edge not in held["lineage"]
    view = "view-mips-mpr-benchmark-prices-fact-vw"
    assert all(view in before.text(n) for n in ("tables", "lineage", "view-systems", "agents"))
    assert not any(view in held[n] for n in ("tables", "lineage", "view-systems", "agents"))
    # The object R004 names is in another catalog here: the object is found by its schema and name.
    assert plan.items[3].text == "object idp_sbx.semantic_sem_commercial.mips_mpr_benchmark_prices_fact_vw is removed"


@as_shipped
def test_a_fix_that_names_nothing_in_the_ontology_stops_the_cut(tmp_path):
    rows = [row(1, "column-renamed", GOLD, {"action": "rename-column", "module": "data-product", "from": "No_Such_Column", "to": "Other"},
                "No_Such_Column", "Other")]
    report, sums = cut.load_report(cleared(tmp_path, {}, rows=rows))
    with pytest.raises(cut.CutRefused, match="row R001 cannot be applied: the ontology's tables hold no column No_Such_Column"):
        cut.plan(report, support.ROOT, sums)


# ---------- refusals: nothing is asked and nothing changes ----------

@as_shipped
def test_an_uncleared_report_is_refused(tmp_path):
    root = release_copy(tmp_path)
    before = digest(root)
    path = cleared(tmp_path, {"R001": "accept", "R003": "accept"})   # R002 blocks the load and has no decision
    with pytest.raises(cut.CutRefused, match="the report is not cleared. Rows that block the load and have no decision: R002"):
        cut.cut(path, root, ask=never, say=quiet)
    assert digest(root) == before
    assert cut.main(["--report", str(path), "--release", str(root)]) == 1


@as_shipped
def test_a_breaking_change_without_the_typed_confirmation_is_refused(tmp_path):
    root = release_copy(tmp_path)
    before = digest(root)
    path = cleared(tmp_path, {"R002": "accept"})
    for answers in (("yes",), ("change_value_amount",), ("",)):
        ask = Answers(*answers)
        with pytest.raises(cut.CutRefused, match="row R002 was not confirmed"):
            cut.cut(path, root, ask=ask, say=quiet)
        assert ask.prompts == [f"Row R002 is a breaking change: column ChangeValue of {GOLD} becomes Change_Value_Amount. "
                               "Type Change_Value_Amount to confirm: "]
    ask = Answers("Change_Value_Amount", "y")
    with pytest.raises(cut.CutRefused, match="the cut was not approved"):
        cut.cut(path, root, ask=ask, say=quiet)
    assert ask.prompts[1] == "Type yes to cut these versions: "
    assert digest(root) == before


@as_shipped
def test_a_report_of_another_release_or_another_version_is_refused(tmp_path):
    root = release_copy(tmp_path)
    stale = cleared(tmp_path, {"R002": "accept"}, ontology={"data-product": "1.1.0"}, name="stale")
    with pytest.raises(cut.CutRefused, match="the report read data-product 1.1.0, and this release holds data-product 1.2.0"):
        cut.cut(stale, root, ask=never, say=quiet)
    other = json.loads(cleared(tmp_path, {"R002": "accept"}, name="other").read_text(encoding="utf-8"))
    other["release"] = "Another Store 9.9"
    path = tmp_path / "other" / rep.JSON_NAME
    path.write_text(json.dumps(other), encoding="utf-8")
    with pytest.raises(cut.CutRefused, match="the report is of Another Store 9.9, and this folder holds KPI Store 1.1"):
        cut.cut(path, root, ask=never, say=quiet)
    with pytest.raises(cut.CutRefused, match="the report cannot be read"):
        cut.cut(tmp_path / "absent.json", root, ask=never, say=quiet)


@as_shipped
def test_the_plan_option_shows_the_plan_and_changes_nothing(tmp_path, capsys):
    root = release_copy(tmp_path)
    before = digest(root)
    assert cut.main(["--report", str(cleared(tmp_path, {"R002": "accept"})), "--release", str(root), "--plan"]) == 0
    out = capsys.readouterr().out
    assert "The cut applies (1):" in out and "  data-product 1.2.0 -> 1.2.1-correction.1" in out
    assert digest(root) == before


# ---------- decisions that change no version ----------

@as_shipped
def test_rejections_alone_write_the_record_and_the_standing_decisions_and_no_version(tmp_path):
    root = release_copy(tmp_path)
    csv_path = tmp_path / "cleared.csv"
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    for r in report["rows"]:
        if r["id"] in EXTRAS[:2]:
            r["decision"], r["decided_by"], r["note"] = "reject", "the data platform lead", "Not a pricing table."
        if r["id"] == "R002":
            r["decision"], r["decided_by"] = "environment setting", "the data platform lead"
    csv_path.write_text(rep.to_csv(report), encoding="utf-8", newline="\n")
    path = cleared(tmp_path, {})
    said = []
    ask = Answers("yes")
    outcome = cut.cut(path, root, decisions=csv_path, ask=ask, say=said.append, now=NOW)
    assert ask.prompts == ["Type yes to cut the record of these decisions, with no new version: "]
    assert (outcome.status, outcome.plan.versions, outcome.committed) == ("recorded", {}, False)
    standing = (ONTOLOGY / "discovery-runs" / "standing-decisions.json").as_posix()
    assert outcome.files == [RECORD.as_posix(), standing]
    assert ov.newest_versions(root / ov.RELEASES)["data-product"] == "1.2.0"
    held = json.loads((root / standing).read_text(encoding="utf-8"))
    assert held["format"] == 1
    assert [(d["kind"], d["object"], d["decision"], d["run"]) for d in held["decisions"]] == [
        ("object-extra", "idp_sbx.gold_commercial_core.sample_margin_fact", "reject", RUN),
        ("object-extra", "idp_sbx.gold_commercial_core.sample_volume_fact", "reject", RUN)]
    # The key, by hand: kind, object, ontology value and found value in lower case, joined by the unit separator.
    assert held["decisions"][0]["key"] == hashlib.sha256(
        "object-extra\x1fidp_sbx.gold_commercial_core.sample_margin_fact\x1f\x1fmanaged".encode()).hexdigest()
    record = (root / RECORD).read_text(encoding="utf-8")
    assert "None. No accepted row changed the ontology." in record
    assert f"| Decisions file checksum (SHA-256) | {hashlib.sha256(csv_path.read_bytes()).hexdigest()} |" in record
    assert "| the data platform lead | rejected | no change; a standing decision keeps the row out of the next comparison; Not a pricing table. |" in record
    assert "| Cleared by | Not given |" in record
    assert any(line.startswith("Row R002: record this difference in kpi_store.toml") for line in said)
    # The next comparison leaves the two rejected rows out and still raises the others.
    result = compared(root)
    assert kinds(result)["object-extra"] == 5 and result.blocked
    assert cut.cut(path, root, decisions=csv_path, ask=never, say=quiet).status == "already cut"


@as_shipped
def test_the_comparison_leaves_out_a_standing_decision_only_for_the_same_finding():
    result = compared(support.ROOT)
    blocking = next(r for r in result.rows if r["blocks"])
    assert (blocking["ontology_value"], blocking["found_value"]) == ("ChangeValue", "Change_Value_Amount")
    view = ov.read(support.ROOT)
    workspace, genie = support.sandbox()
    settings = support.make_settings()
    found = discovery.discover(settings, workspace.run_sql, genie, {settings.environment_name(o.full_name).rsplit(".", 1)[0] for o in view.objects.values()})
    same = compare.compare(view, found, settings, NOW, standing={rep.standing_key(blocking)})
    assert not same.blocked and len(same.rows) == len(result.rows) - 1
    other = compare.compare(view, found, settings, NOW, standing={rep.standing_key({**blocking, "found_value": "Change_Amount"})})
    assert other.blocked and len(other.rows) == len(result.rows)


def test_malformed_standing_decisions_stop_the_read(tmp_path):
    assert rep.read_standing(tmp_path) == frozenset()
    path = tmp_path / rep.STANDING_DECISIONS
    path.parent.mkdir(parents=True)
    path.write_text('{"format": 1, "decisions": [{"kind": "object-extra"}]}', encoding="utf-8")
    with pytest.raises(rep.ReportError, match="cannot read the standing decisions"):
        rep.read_standing(tmp_path)


# ---------- the whole cut ----------

@as_shipped
def test_the_change_value_rename_goes_through_the_whole_cut_in_a_plain_folder_and_a_second_correction_counts_up(tmp_path):
    root = release_copy(tmp_path)
    path = cleared(tmp_path, {"R002": "accept", **{r: "reject" for r in EXTRAS}})
    ask, said = Answers("Change_Value_Amount", "yes"), []
    outcome = cut.cut(path, root, approver="the ontology owner", ask=ask, say=said.append, now=NOW)
    assert (outcome.status, outcome.committed, outcome.tag) == ("cut", False, "")
    assert outcome.plan.versions == CORRECTED
    assert [s for s in said if s.startswith("... verify")] == [
        "... verify the module's Turtle", "... verify the data-product package", "... verify the logical-model package",
        "... verify the technical-graph package", "... verify the value-stream package", "... verify the integration package",
        "... verify the catalog"]
    # The release is written last, after every check.
    assert said.index("... verify the catalog") < said.index("... check that the release agrees with itself") < said.index("... write the release")
    assert said[-2].startswith(f"Done. The record is {RECORD.as_posix()}; the cut changed ")
    assert outcome.messages == ["Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash; the runner does it)."]

    # The release now names the column as the workspace does, at the correction version.
    view = ov.read(root)
    gold = sorted(c.name for c in view.columns if c.table == GOLD)
    assert gold == ["Change_Value_Amount", "Previous_amount", "assessment_amount"]
    assert view.versions["data-product"] == "1.2.1-correction.1"
    assert {m: v for m, v in view.versions.items() if "correction" in v} == {m: new for m, (old, new) in CORRECTED.items()}
    releases = root / ov.RELEASES
    for module, (old, new) in CORRECTED.items():
        assert sorted(p.name for p in (releases / module).iterdir()) == [new, "CHANGELOG.md"]
        assert (releases / "previous" / module / old / "manifest.json").is_file()
    package = releases / "data-product" / "1.2.1-correction.1"
    turtle = (package / "data-product.ttl").read_text(encoding="utf-8")
    assert "owl:versionIRI dp:1.2.1-correction.1 ;" in turtle and "@prefix dp: <https://w3id.org/mpc/ontology/modules/data-product/> ." in turtle
    assert 'owl:versionInfo "1.2.1-correction.1"' in turtle
    assert "gold-mips-mpr-executive-summary-fact--change_value_amount" in turtle and "changevalue" not in turtle.lower()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.2.1-correction.1"
    assert manifest["approved_by"] == {"who": "the ontology owner", "recorded_in": f"discovery-runs/{RUN}.md",
                                       "words": f"Typed yes to approve the cut of discovery run {RUN}."}
    requires = json.loads((releases / "integration" / "2.5.1-correction.1" / "manifest.json").read_text(encoding="utf-8"))["depends_on"]
    assert (requires["data-product"], requires["value-stream"], requires["kpi"]) == ("1.2.1-correction.1", "1.2.1-correction.1", "1.3.0")
    changelog = (package / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.startswith("# data-product changelog\n\n## 1.2.1-correction.1 (2026-11-12)\n\nA patch release. "
                                f"A correction from discovery run {RUN}, rows R002: column ChangeValue of {GOLD} becomes "
                                f"Change_Value_Amount. Record: discovery-runs/{RUN}.md.\n")

    # The catalog, the projection manifest and the folders agree, which the load requires.
    from kpi_store import load_databricks as ld
    newest = ld.expected(root)["newest"]
    assert "https://w3id.org/mpc/ontology/modules/data-product/1.2.1-correction.1" in newest and len(newest) == 13
    assert len(ld.release_graphs(root)) == 41
    projection = json.loads((root / ONTOLOGY / "projection" / "projection-manifest.json").read_text(encoding="utf-8"))
    assert "releases/data-product/1.2.1-correction.1/data-product.ttl" in projection["inputs"]
    assert not any("/1.2.0/" in p for p in projection["inputs"] if p.startswith("releases/data-product/"))

    # The record: what the plan allows, and nothing of the report's evidence or of a Genie filter.
    record = (root / RECORD).read_text(encoding="utf-8")
    report_sum = hashlib.sha256(path.read_bytes()).hexdigest()
    for line in (f"| Run | {RUN} |", f"| Report checksum (SHA-256) | {report_sum} |", "| Settings checksum (SHA-256) | " + "5" * 64 + " |",
                 "| Cut at | 2026-11-12T08:30:00Z |", "| Cleared by | the ontology owner |",
                 "| data-product | 1.2.0 | 1.2.1-correction.1 | Rows R002 |",
                 f"| R002 | column-renamed | yes | {GOLD} | ChangeValue | Change_Value_Amount | accept | the ontology owner | apply | "
                 f"column ChangeValue of {GOLD} becomes Change_Value_Amount |",
                 "| R002 | business_architecture/ontology/data-product/pricing/columns.csv | gold-mips-mpr-executive-summary-fact column ChangeValue | "
                 "gold-mips-mpr-executive-summary-fact column Change_Value_Amount |",
                 "- `business_architecture/ontology/releases/data-product/1.2.1-correction.1/manifest.json`",
                 f"- `{RECORD.as_posix()}`"):
        assert line in record, line
    assert "KPI filter" not in record and "column lineage holds" not in record and "WHERE" not in record
    # The eight measure links and the second source name a Genie filter, and the second source's ontology value is a sentence.
    assert record.count("(kept in the report)") == 10
    assert RECORD.as_posix() in outcome.files and len(outcome.files) > 60

    # The next comparison no longer stops, and no longer raises the rejected extras.
    result = compared(root)
    assert not result.blocked
    assert result.passes == {"object_names": 33, "table_edges": 40, "metric_view_sources": 3}
    assert kinds(result) == {"column-case": 2, "migration-pair": 8, "measure-link": 8, "second-source": 1, "question": 1}

    # The same report again changes nothing.
    after_first = digest(root)
    again = cut.cut(path, root, approver="the ontology owner", ask=never, say=quiet)
    assert again.status == "already cut" and digest(root) == after_first
    # The same run with other decisions is not cut a second time.
    with pytest.raises(cut.CutRefused, match="records a cut of this run from another report file"):
        cut.cut(cleared(tmp_path, {"R002": "reject"}, name="changed"), root, ask=never, say=quiet)
    # A report made before the cut names the version it read, so it is refused.
    with pytest.raises(cut.CutRefused, match="the report read data-product 1.2.0, and this release holds data-product 1.2.1-correction.1"):
        cut.cut(cleared(tmp_path, {"R002": "accept"}, run="20261112T090000Z-11112222", name="old"), root, ask=never, say=quiet)

    # A correction to the correction: the two case-only spellings and the second source, from the next run's report.
    second = cleared(tmp_path, {"R001": "accept", "R003": "accept", "R020": "accept"}, run="20261113T070000Z-99990000",
                     ontology={m: new for m, (old, new) in CORRECTED.items()},
                     rows=[r for r in json.loads(REPORT.read_text(encoding="utf-8"))["rows"] if r["id"] in ("R001", "R003", "R020")], name="second")
    ask = Answers("yes")   # nothing here is breaking, so the only prompt is the approval
    outcome = cut.cut(second, root, ask=ask, say=quiet, now=NOW)
    assert outcome.plan.versions["data-product"] == ("1.2.1-correction.1", "1.2.1-correction.2")
    assert outcome.plan.versions["integration"] == ("2.5.1-correction.1", "2.5.1-correction.2")
    view = ov.read(root)
    assert view.versions["data-product"] == "1.2.1-correction.2"
    assert sorted(c.name for c in view.columns if c.table == GOLD) == ["Assessment_Amount", "Change_Value_Amount", "Previous_Amount"]
    assert "crack-spreads" in view.objects[SUMMARY_VIEW].measures
    assert sorted(p.name for p in (releases / "previous" / "data-product").iterdir()) == ["1.1.0", "1.2.0", "1.2.1-correction.1"]
    manifest = json.loads((releases / "data-product" / "1.2.1-correction.2" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["approved_by"]["who"] == "The person who ran the cut"
    assert kinds(compared(root)) == {"migration-pair": 8, "measure-link": 8, "question": 1}
    # The stand-alone check's exception follows each package: one line per package that holds the changelog's text.
    exceptions = (root / cut.EXCEPTIONS).read_text(encoding="utf-8")
    for line in ("releases/previous/data-product/1.2.0/CHANGELOG.md", "releases/previous/data-product/1.2.1-correction.1/CHANGELOG.md",
                 "releases/data-product/1.2.1-correction.2/CHANGELOG.md"):
        assert exceptions.count(f"business_architecture/ontology/{line} :: other-release :: ") == 1, line
    assert "releases/data-product/1.2.0/CHANGELOG.md" not in exceptions


def git(root, *args):
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def no_global_git(monkeypatch):
    """Git reads no configuration but the repository's own, so the tests do not depend on the machine's author."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)


@as_shipped
@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_failure_leaves_the_tree_untouched_and_a_cut_in_local_git_commits_and_tags(tmp_path, no_global_git):
    root = release_copy(tmp_path)
    git(root, "init", "-q", "-b", "work")
    git(root, "config", "user.name", "Sample Runner")
    git(root, "config", "user.email", "runner@example.invalid")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "The release as received")
    assert git(root, "remote") == ""
    path = cleared(tmp_path, {"R001": "accept", "R002": "accept", "R003": "accept", "R020": "accept"})
    before, head = digest(root), git(root, "rev-parse", "HEAD")

    # A change that is not committed stops the cut before it asks anything.
    (root / "note.txt").write_text("not committed\n", encoding="utf-8")
    with pytest.raises(cut.CutRefused, match="has changes that are not committed"):
        cut.cut(path, root, ask=never, say=quiet)
    (root / "note.txt").unlink()

    # A failure after the packages are written, and a failing step of the release's own scripts.
    steps = []

    def fail_at_the_catalog(name):
        steps.append(name)
        if name == "rebuild the catalog":
            raise RuntimeError("made-up failure")
    with pytest.raises(cut.CutFailed, match="the step 'rebuild the catalog' failed: RuntimeError: made-up failure. The release is as it was."):
        cut.cut(path, root, ask=Answers("Change_Value_Amount", "yes"), say=quiet, before_step=fail_at_the_catalog)
    assert "write the integration package" in steps and "move integration 2.5.0 to releases/previous" in steps
    assert "verify the catalog" not in steps   # the cut stopped at the failing step
    assert digest(root) == before and git(root, "status", "--porcelain") == "" and git(root, "rev-parse", "HEAD") == head
    with pytest.raises(cut.CutFailed, match=r"the step 'list the modules to release' failed \(dependents.py data-product\)"):
        cut._run("list the modules to release", ["dependents.py", "data-product"], root)   # the script is not in this folder
    with pytest.raises(cut.CutFailed, match="the step 'write the release' failed"):
        (tmp_path / "staging").mkdir()
        (tmp_path / "staging" / "a.txt").write_text("new", encoding="utf-8")
        (tmp_path / "target").mkdir()
        (tmp_path / "target" / "a.txt").write_text("old", encoding="utf-8")
        cut._Steps(quiet, None)("write the release", lambda: cut._apply(tmp_path / "target", tmp_path / "staging", ["a.txt", "b.txt"], tmp_path / "backup"))
    assert (tmp_path / "target" / "a.txt").read_text(encoding="utf-8") == "old"   # the file written before the failure is put back

    # The cut itself: one commit by the configured author, one tag, a clean tree, and no remote needed.
    outcome = cut.cut(path, root, ask=Answers("Change_Value_Amount", "yes"), say=quiet, now=NOW)
    assert (outcome.status, outcome.committed, outcome.tag) == ("cut", True, "data-product-1.2.1-correction.1")
    assert git(root, "status", "--porcelain") == ""
    assert git(root, "log", "--format=%an <%ae>%n%s%n%b", "-1").splitlines()[:3] == [
        "Sample Runner <runner@example.invalid>", f"Cut data-product 1.2.1-correction.1 from discovery run {RUN}",
        f"The record is {RECORD.as_posix()}."]
    assert git(root, "rev-list", "--count", "HEAD").strip() == "2"
    assert git(root, "tag", "--points-at", "HEAD").split() == ["data-product-1.2.1-correction.1"]
    committed = set(git(root, "show", "--name-only", "--no-renames", "--format=", "HEAD").split())
    assert committed == set(outcome.files)
    assert sorted(c.name for c in ov.read(root).columns if c.table == GOLD) == ["Assessment_Amount", "Change_Value_Amount", "Previous_Amount"]
    assert kinds(compared(root)) == {"object-extra": 7, "migration-pair": 8, "measure-link": 8, "question": 1}


def small_git_release(tmp_path):
    """A small release in a Git copy with no author: enough for a cut that writes no version."""
    root = tmp_path / "release"
    (root / ONTOLOGY / "data-product").mkdir(parents=True)
    shutil.copytree(support.ROOT / ONTOLOGY / "data-product" / "pricing", root / ONTOLOGY / "data-product" / "pricing")
    shutil.copytree(support.ROOT / ONTOLOGY / "releases" / "data-product", root / ov.RELEASES / "data-product")
    shutil.copytree(support.ROOT / ONTOLOGY / "releases" / "kpi", root / ov.RELEASES / "kpi")
    shutil.copytree(support.ROOT / ONTOLOGY / "release", root / ONTOLOGY / "release", ignore=shutil.ignore_patterns("__pycache__", "frozen"))
    shutil.copy2(support.ROOT / "release.json", root / "release.json")
    git(root, "init", "-q", "-b", "work")
    git(root, "add", "-A")
    git(root, "-c", "user.name=Setup", "-c", "user.email=setup@example.invalid", "commit", "-q", "-m", "The release as received")
    return root


def with_author(root):
    git(root, "config", "user.name", "Sample Runner")
    git(root, "config", "user.email", "runner@example.invalid")


@as_shipped
@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_git_copy_that_cannot_commit_is_refused_before_anything_changes(tmp_path, no_global_git, monkeypatch):
    root = small_git_release(tmp_path)
    path = cleared(tmp_path, {"R004": "reject", "R002": "reject"})
    before, head = digest(root), git(root, "rev-parse", "HEAD")
    assert cut._git_state(root) == "no author"
    with pytest.raises(cut.CutRefused) as refused:
        cut.cut(path, root, ask=never, say=quiet, now=NOW)
    assert str(refused.value) == (
        "this Git copy has no user.name or user.email, so the cut could not commit. Run these two commands, then cut:\n"
        '  git config user.name "<your name or role>"\n  git config user.email "<your e-mail address>"\n'
        "A plain folder, one with no .git folder, needs no Git.")
    assert digest(root) == before and git(root, "status", "--porcelain") == "" and not (root / RECORD).exists()
    # A Git copy on a machine without Git is refused too.
    with monkeypatch.context() as m:
        m.setattr(cut.shutil, "which", lambda name: None)
        with pytest.raises(cut.CutRefused, match="this folder is a Git copy, and Git is not installed"):
            cut.cut(path, root, ask=never, say=quiet, now=NOW)
    assert digest(root) == before
    # With an author the same cut commits, and makes no tag because it wrote no version.
    with_author(root)
    outcome = cut.cut(path, root, ask=Answers("yes"), say=quiet, now=NOW)
    assert (outcome.status, outcome.committed, outcome.tag) == ("recorded", True, "")
    assert git(root, "status", "--porcelain") == "" and git(root, "rev-list", "--count", "HEAD").strip() == "2"
    assert git(root, "rev-parse", "HEAD") != head and git(root, "tag") == ""
    assert git(root, "log", "-1", "--format=%s").strip() == f"Record the decisions of discovery run {RUN}"


@as_shipped
@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_failed_commit_puts_the_release_back_and_a_failed_tag_is_finished_by_the_next_run(tmp_path, no_global_git, monkeypatch):
    root = small_git_release(tmp_path)
    with_author(root)
    report_path = cleared(tmp_path, {"R002": "accept"})
    report, sums = cut.load_report(report_path)
    plan = cut.Plan(report, [], {"data-product": ("1.2.0", "1.2.1-correction.1")}, None)
    record = f"# Discovery run {RUN}\n\n| Report checksum (SHA-256) | {sums['report']} |\n\n| data-product | 1.2.0 | 1.2.1-correction.1 | Rows R002 |\n"
    files = ("__pycache__", ".git")   # Git's own folder changes when Git resets; the release's files must not
    real, before = cut._git, digest(root, files)

    def failing(verb):
        def run(root_, *args):
            if args[0] == verb:
                return subprocess.CompletedProcess(args, 1, "", f"made-up {verb} failure")
            return real(root_, *args)
        return run

    # The commit fails after the files are written: the release goes back to its last commit.
    (root / RECORD).parent.mkdir(parents=True)
    (root / RECORD).write_text(record, encoding="utf-8")
    monkeypatch.setattr(cut, "_git", failing("commit"))
    with pytest.raises(cut.CutFailed, match="git commit failed: made-up commit failure. The release is as it was."):
        cut._commit(root, "ready", plan, cut.Outcome("cut", plan, RECORD))
    assert digest(root, files) == before and git(root, "status", "--porcelain") == "" and not (root / RECORD).exists()
    assert git(root, "rev-list", "--count", "HEAD").strip() == "1"

    # The tag fails after the commit: the cut is not complete, and says how to finish.
    (root / RECORD).parent.mkdir(parents=True)
    (root / RECORD).write_text(record, encoding="utf-8")
    monkeypatch.setattr(cut, "_git", failing("tag"))
    with pytest.raises(cut.CutIncomplete, match="the cut is committed, and git tag data-product-1.2.1-correction.1 failed: made-up tag failure. "
                                                "Run the same command again to finish the tag."):
        cut._commit(root, "ready", plan, cut.Outcome("cut", plan, RECORD))
    cut_commit = git(root, "rev-parse", "HEAD").strip()
    assert git(root, "rev-list", "--count", "HEAD").strip() == "2" and git(root, "tag") == ""
    assert cut.main(["--report", str(report_path), "--release", str(root)]) == 1   # still failing: the command says so
    monkeypatch.setattr(cut, "_git", real)

    # A later commit must not take the tag: the next run of the same report tags the cut's own commit.
    (root / "later.txt").write_text("later work\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "Later work")
    said = []
    outcome = cut.cut(report_path, root, ask=never, say=said.append)
    assert (outcome.status, outcome.tag) == ("already cut", "data-product-1.2.1-correction.1")
    assert git(root, "rev-parse", "data-product-1.2.1-correction.1^{commit}").strip() == cut_commit
    assert said[-1] == f"The tag data-product-1.2.1-correction.1 was missing. It now marks the cut's commit {cut_commit[:12]}."
    # Once the tag is there, a further run has nothing to do.
    said.clear()
    assert cut.cut(report_path, root, ask=never, say=said.append).tag == "data-product-1.2.1-correction.1"
    assert said[-1].endswith("Nothing to do.")


@as_shipped
@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_tag_that_exists_already_stops_the_cut_before_anything_changes(tmp_path, no_global_git):
    root = release_copy(tmp_path)
    git(root, "init", "-q", "-b", "work")
    with_author(root)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "The release as received")
    git(root, "tag", "data-product-1.2.1-correction.1")
    before = digest(root)
    with pytest.raises(cut.CutRefused, match="this Git copy already has the tag data-product-1.2.1-correction.1, which the cut would make"):
        cut.cut(cleared(tmp_path, {"R002": "accept"}), root, ask=never, say=quiet)
    assert digest(root) == before and git(root, "status", "--porcelain") == "" and git(root, "rev-list", "--count", "HEAD").strip() == "1"


# ---------- the report is data a person may have edited ----------

def edited(tmp_path, change, decisions, name):
    """The fixture report with one row changed by `change(row)`, written to a folder of its own."""
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    for r in report["rows"]:
        change(r)
    return cleared(tmp_path, decisions, rows=report["rows"], name=name)


@as_shipped
@pytest.mark.parametrize("field, value, why", [
    ("found_value", "jane.doe@example.com", "its found value is not a name"),
    ("found_value", "Change Value; see the note", "its found value is not a name"),
    ("object", "ask jane.doe@example.com", "its object is not an object name"),
    ("fix.to", "../../x", "the 'to' of its proposed fix is not a name"),
    ("fix.to", "jane.doe@example.com", "the 'to' of its proposed fix is not a name"),
    ("fix.from", "ChangeValue\nsecond line", "the 'from' of its proposed fix is not a name"),
    ("fix.to", 7, "the 'to' of its proposed fix is not a name"),
    ("fix.module", "../../x", "its proposed fix names a module other than data-product"),
    ("fix.module", "kpi", "its proposed fix names a module other than data-product"),
    ("fix.module", "no-such-module", "its proposed fix names a module other than data-product"),
])
def test_an_accepted_row_with_anything_but_names_is_refused(tmp_path, field, value, why):
    def change(r):
        if r["id"] == "R002":
            if field.startswith("fix."):
                r["proposed_fix"][field[4:]] = value
            else:
                r[field] = value
    root = release_copy(tmp_path)
    before = digest(root)
    with pytest.raises(cut.CutRefused) as refused:
        cut.cut(edited(tmp_path, change, {"R002": "accept"}, "edited"), root, ask=never, say=quiet)
    assert str(refused.value) == f"row R002 cannot be applied: {why}. Correct the report, or reject the row."
    assert digest(root) == before


@as_shipped
def test_a_table_or_view_value_that_is_a_path_is_refused(tmp_path):
    def change(r):
        if r["id"] == "R020":
            r["proposed_fix"]["view"] = "../../x"
    report, sums = cut.load_report(edited(tmp_path, change, {"R020": "accept", "R002": "reject"}, "path"))
    with pytest.raises(cut.CutRefused, match="row R020 cannot be applied: the 'view' of its proposed fix is not a name"):
        cut.plan(report, support.ROOT, sums)
    rows = [row(1, "object-missing", GOLD, {"action": "remove-object", "module": "data-product", "object": "../../x"})]
    report, sums = cut.load_report(cleared(tmp_path, {}, rows=rows, name="object"))
    with pytest.raises(cut.CutRefused, match="row R001 cannot be applied: the 'object' of its proposed fix is not a name"):
        cut.plan(report, support.ROOT, sums)


@as_shipped
def test_the_record_and_the_standing_decisions_hold_no_text_that_is_not_a_name(tmp_path):
    def change(r):
        if r["id"] == "R002":      # a name-kind row that is rejected: its edited found value must not be copied
            r["found_value"] = "jane.doe@example.com"
        if r["id"] == "R004":
            r["object"], r["ontology_value"], r["found_value"] = "ask jane.doe@example.com", "call 555 0100", "managed by jane"
        if r["id"] == "R001":      # no decision: recorded as a row, never applied
            r["ontology_value"] = "jane.doe@example.com"
    root = release_copy(tmp_path)
    cut.cut(edited(tmp_path, change, {"R002": "reject", "R004": "reject"}, "edited"), root, ask=Answers("yes"), say=quiet, now=NOW)
    record = (root / RECORD).read_text(encoding="utf-8")
    standing = (root / rep.STANDING_DECISIONS).read_text(encoding="utf-8")
    for text in ("jane", "example.com", "555 0100"):
        assert text not in record and text not in standing, text
    assert f"| R002 | column-renamed | yes | {GOLD} | ChangeValue | (kept in the report) | reject |" in record
    assert "| R004 | object-extra | no | (kept in the report) | (kept in the report) | (kept in the report) | reject |" in record
    assert f"| R001 | column-case | no | {GOLD} | (kept in the report) | Assessment_Amount | none |" in record
    assert "| R005 | object-extra | no | idp_sbx.gold_commercial_core.sample_volume_fact |   | MANAGED | none |" in record
    held = json.loads(standing)["decisions"]
    assert [(d["kind"], d["object"], d["ontology_value"]) for d in held] == [
        ("column-renamed", GOLD, "ChangeValue"), ("object-extra", "(kept in the report)", "(kept in the report)")]


def test_a_report_whose_run_fields_are_not_a_time_and_checksums_is_refused(tmp_path):
    for n, (key, value) in enumerate((("at", "yesterday, by jane.doe@example.com"), ("settings_sha256", "jane.doe@example.com"),
                                      ("zip_sha256", "7" * 63))):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        report["run"][key] = value
        path = tmp_path / f"run-{n}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(cut.CutRefused, match="the report's run must hold its time as"):
            cut.load_report(path)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["ontology"]["jane.doe@example.com"] = "1.0.0"
    report["ontology"]["kpi"] = "the newest one"
    (tmp_path / "ontology.json").write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(cut.CutRefused, match="the report's ontology versions are not module names with versions: 'jane.doe@example.com', 'kpi'"):
        cut.load_report(tmp_path / "ontology.json")
