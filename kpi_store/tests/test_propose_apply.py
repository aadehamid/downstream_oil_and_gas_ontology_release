"""The term-change form, the propose command and the apply command (KPI-DEC-0002, Q4 to Q7, Q10 form 4 and Q13).

The propose tests read this tree's own KPI intake pack and kpi tables, and write proposals into a temporary folder
only. They pick their measure and processes from the tree, so they hold on a tree that has moved on, and the KGCL
lines and routes they expect are written by hand from those values. The apply tests that change a release run on a
temporary copy of it; the tree itself is never written.
"""
import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from rdflib import Graph, URIRef

from kpi_store import apply as apply_cmd, cut, ontology_view as ov, propose as propose_cmd
from kpi_store.change import ChangeRefused, approval, kgcl, kpi_tables, proposal
from kpi_store.change.kgcl import Change
from kpi_store.intake import catalogue, check, picklists
from kpi_store.intake.answers import Intake
from kpi_store.tests import support

ROOT = support.ROOT
ONTOLOGY = Path("business_architecture") / "ontology"
NOW = dt.datetime(2026, 11, 19, 9, 0, tzinfo=dt.timezone.utc)
MEASURE_NS, PROC_NS = kpi_tables.PREFIXES["measure"], kpi_tables.PREFIXES["proc"]
SIGNED = {"data-owner": {"name": "A Data Owner", "date": "2026-11-19"},
          "architect": {"name": "An Architect", "date": "2026-11-19"}}
MAJOR_SIGNED = dict(SIGNED, **{"ontology-owner": {"name": "An Ontology Owner", "date": "2026-11-19"}})


def quiet(line):
    pass


def pick(root):
    """From a release: a measure with an other name and a process link that the pick lists offer, a second such
    process it is not linked to, and the measure's pick-list entry."""
    lists = picklists.load(root / "kpi-intake")["lists"]
    offered = {p["id"] for p in lists["processes"]}
    g = Graph().parse(root / kpi_tables.MEASURES)
    for measure in lists["measures"]:
        linked = sorted(str(o) for o in g.objects(URIRef(measure["id"]), URIRef(kpi_tables.PREFIXES["kpi"] + "informsProcess")))
        linked = [p for p in linked if p in offered]
        if measure["other_names"] and linked:
            free = next(p["id"] for p in lists["processes"] if p["id"] not in linked and p["level"] >= 4)
            return measure, linked[0], free
    raise AssertionError("no measure of the tree has both an other name and a process link")


def form(folder, measure, answers, sign_offs=SIGNED, name="change"):
    """A term-change answers file for the measure, written to the folder. Returns its path."""
    data = {"format": 1, "form": "term-change", "catalogue_version": "1.2", "kpi_name": measure["label"],
            "request": {}, "answers": {"T1": measure["id"], "T8": "yes", **answers}, "sign_offs": sign_offs,
            "consulted": {}, "example_of": "", "comment": ""}
    path = Path(folder) / f"{name}.term-change.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def curie(iri):
    return "proc:" + iri[len(PROC_NS):]


# ---------- the form and its check ----------

def test_the_term_change_form_is_one_more_form_of_the_pack():
    cat = catalogue.load()
    assert catalogue.FORMS["term-change"] == "Term change"
    assert [q["id"] for q in cat.questions_of("term-change")] == ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
    assert cat.by_id["T8"]["text"] == "Would every report and answer that used the old meaning still be correct?"
    assert [o["label"] for o in cat.fixed_list(cat.by_id["T8"]["source"])] == ["Yes", "No", "Not sure"]
    assert [s["id"] for s in cat.signers("term-change")] == ["data-owner", "ontology-owner", "architect"]
    owner = cat.sign_off["signer"][[s["id"] for s in cat.sign_off["signer"]].index("ontology-owner")]
    for answer, needed in (("yes", False), ("no", True), ("not-sure", True)):
        assert cat.is_needed(owner, "term-change", {"T8": answer}) is needed, answer


def _report(root, measure, answers, sign_offs=SIGNED):
    cat, data = catalogue.load(root / "kpi-intake"), picklists.load(root / "kpi-intake")
    intake = Intake(form="term-change", answers={"T1": measure["id"], "T8": "yes", **answers}, sign_offs=sign_offs)
    return check.check(cat, data, intake)


def test_the_check_refuses_a_term_change_that_asks_for_nothing_or_does_not_fit_the_measure():
    measure, linked, free = pick(ROOT)
    other = measure["other_names"][0]
    assert _report(ROOT, measure, {"T4": ["a made-up other name"]}).complete
    cases = [({}, "the form asks for no change: answer at least one of T2 to T7"),
             ({"T2": measure["label"]}, f'T2: "{measure["label"]}" is the measure\'s name already. Leave T2 empty to keep it'),
             ({"T3": measure["definition"]}, "T3 is the measure's definition already. Leave T3 empty to keep it"),
             ({"T4": [other]}, f'T4: "{other}" is an other name of the measure already'),
             ({"T4": ["one; two"]}, 'T4: "one; two" holds a semicolon, which the ontology\'s tables use between other names'),
             ({"T5": ["a made-up other name"]}, 'T5: "a made-up other name" is not an other name of the measure.'),
             ({"T2": "MPC’s name"}, "T2: \"MPC’s name\": the text holds the typographic apostrophe"),
             ({"T6": [free], "T7": [free]}, "T6 and T7 both name the process")]
    for answers, reason in cases:
        report = _report(ROOT, measure, answers)
        assert not report.complete, answers
        assert any(line.startswith(reason) for line in report.blocking), (answers, report.blocking)


def test_a_rename_may_keep_the_old_name_as_an_other_name():
    measure, linked, free = pick(ROOT)
    renamed = f"{measure['label']} (renamed)"
    assert _report(ROOT, measure, {"T2": renamed, "T4": [measure["label"]]}).complete
    report = _report(ROOT, measure, {"T2": renamed, "T4": [renamed]})
    assert report.blocking == [f'T4: "{renamed}" is the measure\'s name, so it cannot be an other name too']


def test_the_check_asks_for_the_ontology_owner_only_when_the_answer_makes_the_change_major():
    measure, linked, free = pick(ROOT)
    report = _report(ROOT, measure, {"T3": "A made-up definition.", "T8": "not-sure"})
    assert report.blocking == ['the Ontology Owner has not signed: "This change alters what the measure means, and I '
                               'approve it as a major change."']
    assert _report(ROOT, measure, {"T3": "A made-up definition.", "T8": "no"}, MAJOR_SIGNED).complete
    text = _report(ROOT, measure, {"T3": "A made-up definition."}).text()
    assert 'Ontology Owner ("This change alters what the measure means, and I approve it as a major change."): not needed.' in text
    assert text.splitlines()[0] == f"Term change check: {measure['label']}"


# ---------- propose ----------

def _cases(measure, linked, free):
    """(the answers, the KGCL lines, the route), written by hand for each kind of change."""
    m, label, other = f"measure:{measure['notation']}", measure["label"], measure["other_names"][0]
    return {
        "rename": ({"T2": f"{label} (renamed)"}, [f"rename {m} from '{label}' to '{label} (renamed)'"], "patch"),
        "definition": ({"T3": "A made-up definition, with MPC's apostrophe."},
                       [f"change definition of {m} to 'A made-up definition, with MPC’s apostrophe.'"], "patch"),
        "new other name": ({"T4": ["a made-up other name"]}, [f"create exact synonym 'a made-up other name' for {m}"], "minor"),
        "removed other name": ({"T5": [other]}, [f"remove synonym '{other}' for {m}"], "patch"),
        "process link": ({"T6": [free]}, [f"create edge {m} kpi:informsProcess {curie(free)}"], "minor"),
        "removed process link": ({"T7": [linked]}, [f"delete edge {m} kpi:informsProcess {curie(linked)}"], "patch"),
        "rename and new other name": ({"T2": f"{label} (renamed)", "T4": ["a made-up other name"]},
                                      [f"rename {m} from '{label}' to '{label} (renamed)'",
                                       f"create exact synonym 'a made-up other name' for {m}"], "minor"),
        "rename, answered no": ({"T2": f"{label} (renamed)", "T8": "no"},
                                [f"rename {m} from '{label}' to '{label} (renamed)'"], "major"),
        "new other name, answered not sure": ({"T4": ["a made-up other name"], "T8": "not-sure"},
                                              [f"create exact synonym 'a made-up other name' for {m}"], "major"),
    }


@pytest.mark.parametrize("case", ["rename", "definition", "new other name", "removed other name", "process link",
                                  "removed process link", "rename and new other name", "rename, answered no",
                                  "new other name, answered not sure"])
def test_propose_writes_the_kgcl_lines_and_the_route_for_each_kind_of_change(tmp_path, case):
    measure, linked, free = pick(ROOT)
    answers, lines, route = _cases(measure, linked, free)[case]
    signed = MAJOR_SIGNED if route == "major" else SIGNED
    said = []
    folders = propose_cmd.propose([form(tmp_path, measure, answers, signed)], tmp_path / "out", ROOT, now=NOW, say=said.append)
    assert folders == [tmp_path / "out" / f"2026-11-19-{measure['notation']}"]
    folder = folders[0]
    assert sorted(p.name for p in folder.iterdir()) == ["approval.json", "change.kgcl", "summary.txt"]
    assert (folder / "change.kgcl").read_text(encoding="utf-8") == "".join(line + "\n" for line in lines)
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    roles = ["Data Owner", "Ontology Owner", "Architect"] if route == "major" else ["Data Owner", "Architect"]
    assert (record["change"], record["route"], [s["role"] for s in record["signatures"]]) == (folder.name, route, roles)
    assert record["signatures"][-1]["words"] == "The form is complete, and I approve the change to the ontology."
    summary = (folder / "summary.txt").read_text(encoding="utf-8")
    assert f"The route: {route}." in summary and f"The measure: {measure['label']} (measure:{measure['notation']})" in summary
    assert said[0] == f"wrote the proposal {folder.as_posix()}: {len(lines)} change{'s' if len(lines) > 1 else ''}, route {route}"
    # The proposal reads back as the apply command reads it.
    read = proposal.read(folder)
    assert (read.lines, read.route) == (lines, route)


def test_propose_refuses_a_form_that_is_not_complete_and_signed_and_writes_nothing(tmp_path):
    measure, linked, free = pick(ROOT)
    unsigned = form(tmp_path, measure, {"T4": ["a made-up other name"]}, {"data-owner": SIGNED["data-owner"]}, "unsigned")
    with pytest.raises(propose_cmd.ProposeRefused, match=r"unsigned.term-change.json is not complete and signed\. .*"
                                                         r"the Architect has not signed"):
        propose_cmd.propose([unsigned], tmp_path / "out", ROOT, now=NOW, say=quiet)
    nothing = form(tmp_path, measure, {}, name="nothing")
    with pytest.raises(propose_cmd.ProposeRefused, match="the form asks for no change"):
        propose_cmd.propose([nothing], tmp_path / "out", ROOT, now=NOW, say=quiet)
    major = form(tmp_path, measure, {"T2": "A made-up name", "T8": "no"}, name="major")
    with pytest.raises(propose_cmd.ProposeRefused, match="the Ontology Owner has not signed"):
        propose_cmd.propose([major], tmp_path / "out", ROOT, now=NOW, say=quiet)
    # A good file and a bad one: the bad one stops both, so no proposal is written at all.
    good = form(tmp_path, measure, {"T4": ["a made-up other name"]}, name="good")
    with pytest.raises(propose_cmd.ProposeRefused, match="unsigned.term-change.json is not complete"):
        propose_cmd.propose([good, unsigned], tmp_path / "out", ROOT, now=NOW, say=quiet)
    # A date the approval record cannot hold.
    dated = form(tmp_path, measure, {"T4": ["a made-up other name"]},
                 dict(SIGNED, architect={"name": "An Architect", "date": "19 November"}), "dated")
    with pytest.raises(propose_cmd.ProposeRefused, match=r"the sign-off cannot become an approval record: .*YYYY-MM-DD"):
        propose_cmd.propose([dated], tmp_path / "out", ROOT, now=NOW, say=quiet)
    assert not (tmp_path / "out").exists()


def test_propose_refuses_an_incomplete_form_and_a_folder_inside_the_release(tmp_path):
    # Each of the five forms has its proposal: a new KPI's is tested in kpi_store/tests/test_new_kpi.py, and a
    # domain activation's and a process map request's in kpi_store/tests/test_domain_and_process_map.py.
    other = tmp_path / "x.process-map-request.json"
    other.write_text(json.dumps({"format": 1, "form": "process-map-request", "answers": {}}), encoding="utf-8")
    with pytest.raises(propose_cmd.ProposeRefused, match="x.process-map-request.json is not complete and signed"):
        propose_cmd.propose([other], tmp_path / "out", ROOT, now=NOW, say=quiet)
    measure, linked, free = pick(ROOT)
    with pytest.raises(propose_cmd.ProposeRefused, match="is inside the release folder"):
        propose_cmd.propose([form(tmp_path, measure, {"T4": ["x"]})], ROOT / "proposals", ROOT, now=NOW, say=quiet)
    assert not (ROOT / "proposals").exists()


def test_two_forms_give_two_proposals_and_a_taken_name_counts_up(tmp_path):
    measure, linked, free = pick(ROOT)
    one = form(tmp_path, measure, {"T4": ["a made-up other name"]}, name="one")
    two = form(tmp_path, measure, {"T3": "A made-up definition."}, name="two")
    folders = propose_cmd.propose([one, two], tmp_path / "out", ROOT, now=NOW, say=quiet)
    assert [f.name for f in folders] == [f"2026-11-19-{measure['notation']}", f"2026-11-19-{measure['notation']}-2"]
    assert propose_cmd.main([str(one), "--out", str(tmp_path / "out"), "--release", str(ROOT)]) == 0
    assert len(list((tmp_path / "out").iterdir())) == 3
    # The form's request number names the proposal when it has the form of a change id.
    numbered = json.loads(one.read_text(encoding="utf-8"))
    numbered["request"] = {"number": "TC-2026-007"}
    one.write_text(json.dumps(numbered), encoding="utf-8")
    assert [f.name for f in propose_cmd.propose([one], tmp_path / "out", ROOT, now=NOW, say=quiet)] == ["TC-2026-007"]
    assert proposal.read(tmp_path / "out" / "TC-2026-007").change == "TC-2026-007"
    # Case does not count in a change id: Windows and macOS read TC-2026-009 and tc-2026-009 as one folder.
    for path, number in ((one, "TC-2026-009"), (two, "tc-2026-009")):
        held = json.loads(path.read_text(encoding="utf-8"))
        held["request"] = {"number": number}
        path.write_text(json.dumps(held), encoding="utf-8")
    assert [f.name for f in propose_cmd.propose([one, two], tmp_path / "out", ROOT, now=NOW, say=quiet)] == [
        "TC-2026-009", "tc-2026-009-2"]


def test_a_proposal_folder_is_read_by_its_own_name_from_any_path(tmp_path, monkeypatch):
    measure, linked, free = pick(ROOT)
    [folder] = propose_cmd.propose([form(tmp_path, measure, {"T4": ["a made-up other name"]})], tmp_path / "out", ROOT,
                                   now=NOW, say=quiet)
    monkeypatch.chdir(folder)
    assert proposal.read(".").change == folder.name


def _workbook(path, measure, answers, sign_offs):
    """A filled workbook whose Term change sheet holds these answers and signatures."""
    from kpi_store.intake import workbook
    cat, data = catalogue.load(ROOT / "kpi-intake"), picklists.load(ROOT / "kpi-intake")
    filled = Intake(form="term-change", answers={"T1": measure["id"], "T8": "yes", **answers}, sign_offs=sign_offs)
    workbook.save(workbook.build(cat, data["lists"], others={"term-change": filled}), path)
    return path


def test_propose_reads_a_filled_workbook_and_names_the_whole_check_command_when_it_refuses_one(tmp_path):
    measure, linked, free = pick(ROOT)
    good = _workbook(tmp_path / "good.xlsx", measure, {"T4": ["a made-up other name"]}, SIGNED)
    [folder] = propose_cmd.propose([good], tmp_path / "out", ROOT, now=NOW, say=quiet)
    assert (folder / "change.kgcl").read_text(encoding="utf-8") == \
        f"create exact synonym 'a made-up other name' for measure:{measure['notation']}\n"
    unsigned = _workbook(tmp_path / "unsigned.xlsx", measure, {"T4": ["a made-up other name"]}, {"data-owner": SIGNED["data-owner"]})
    with pytest.raises(propose_cmd.ProposeRefused) as refused:
        propose_cmd.propose([unsigned], tmp_path / "out2", ROOT, now=NOW, say=quiet)
    assert f"Run python -m kpi_store.intake check {unsigned.as_posix()} --form term-change for the whole report" in str(refused.value)


def test_the_command_line_says_why_in_one_line(tmp_path, capsys):
    measure, linked, free = pick(ROOT)
    path = form(tmp_path, measure, {}, name="nothing")
    assert propose_cmd.main([str(path), "--out", str(tmp_path / "out"), "--release", str(ROOT)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Not proposed: nothing.term-change.json is not complete and signed.") and err.count("\n") == 1
    assert err.rstrip().endswith("No proposal was written.")


# ---------- the route and the conflicts ----------

def test_the_route_comes_from_the_change_types_and_the_answer_only_raises_it():
    s, e = Change("create synonym", "measure:a", text="x"), Change("delete edge", "measure:a", predicate="kpi:informsProcess", target="proc:p")
    r = Change("rename", "measure:a", old="A", text="B")
    assert [proposal.route_of(c) for c in ([r], [e], [s], [r, s], [r, e])] == ["patch", "patch", "minor", "minor", "patch"]
    assert [proposal.route_of([r], answer) for answer in ("yes", "no", "not-sure")] == ["patch", "major", "major"]
    assert proposal.highest(["patch", "major", "minor"]) == "major"


def _write(folder, lines, route="minor", signatures=None, change=None):
    """A proposal folder written by hand, without the propose command."""
    folder.mkdir(parents=True)
    (folder / "change.kgcl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    record = {"change": change or folder.name, "route": route, "new_module": False, "signatures": signatures or [
        {"role": "Data Owner", "name": "A Data Owner", "date": "2026-11-19", "words": "Right."},
        {"role": "Architect", "name": "An Architect", "date": "2026-11-19", "words": "Approved."}]}
    (folder / "approval.json").write_text(json.dumps(record), encoding="utf-8")
    return folder


def test_apply_refuses_a_proposal_without_the_signatures_its_route_needs_and_changes_nothing(tmp_path):
    line = "create exact synonym 'a made-up other name' for measure:a"
    unsigned = _write(tmp_path / "unsigned", [line], signatures=[
        {"role": "Data Owner", "name": "A Data Owner", "date": "2026-11-19", "words": "Right."}])
    with pytest.raises(ChangeRefused, match="the proposal unsigned is not approved: .*needs the signature of the Architect"):
        apply_cmd.apply([unsigned], ROOT, say=quiet)
    major = _write(tmp_path / "major", [line], route="major")
    with pytest.raises(ChangeRefused, match="the proposal major is not approved: .*needs the signature of the Ontology Owner"):
        apply_cmd.apply([major], ROOT, say=quiet)
    lowered = _write(tmp_path / "lowered", [line], route="patch")
    with pytest.raises(ChangeRefused, match="the proposal lowered is approved as patch, and its changes need at least minor"):
        apply_cmd.apply([lowered], ROOT, say=quiet)
    with pytest.raises(ChangeRefused, match="the proposal missing has no approval.json"):
        (tmp_path / "missing").mkdir()
        (tmp_path / "missing" / "change.kgcl").write_text(line + "\n", encoding="utf-8")
        apply_cmd.apply([tmp_path / "missing"], ROOT, say=quiet)
    other = _write(tmp_path / "other", [line], change="another-change")
    with pytest.raises(ChangeRefused, match="the approval record in other is for the change another-change"):
        apply_cmd.apply([other], ROOT, say=quiet)


def test_apply_refuses_proposals_that_conflict_or_repeat_before_it_writes_anything(tmp_path):
    one = _write(tmp_path / "one", ["rename measure:a from 'A' to 'B'", "create exact synonym 'x' for measure:a"])
    two = _write(tmp_path / "two", ["rename measure:a from 'A' to 'C'"], route="patch")
    three = _write(tmp_path / "three", ["create exact synonym 'y' for measure:b", "remove synonym 'z' for measure:a"])
    with pytest.raises(ChangeRefused, match="the proposals conflict, so none was applied: the proposals one and two both change "
                                            "the name of measure:a; the proposals one and three both change the other names "
                                            "of measure:a"):
        apply_cmd.apply([one, two, three], ROOT, say=quiet)
    with pytest.raises(ChangeRefused, match="the proposal one is named twice"):
        apply_cmd.apply([one, one], ROOT, say=quiet)
    # Two folders whose names differ only in case would write one approval record on Windows and macOS.
    upper = _write(tmp_path / "a" / "TC-1", ["create exact synonym 'y' for measure:c"])
    lower = _write(tmp_path / "b" / "tc-1", ["create exact synonym 'y' for measure:d"])
    with pytest.raises(ChangeRefused, match="the proposal TC-1, tc-1 is named twice"):
        apply_cmd.apply([upper, lower], ROOT, say=quiet)
    # A definition and a process link of the same measure are other fields, so they do not conflict.
    assert proposal.conflicts([proposal.read(_write(tmp_path / "four", ["change definition of measure:a to 'D'"], "patch")),
                               proposal.read(_write(tmp_path / "five", ["create edge measure:a kpi:informsProcess proc:p"]))]) == []


def test_the_next_version_for_each_route():
    newest = ov.release_scripts_newest(ROOT)
    assert [apply_cmd.next_version("1.3.0", r, newest) for r in ("patch", "minor", "major")] == ["1.3.1", "1.4.0", "2.0.0"]
    assert apply_cmd.next_version("1.3.1-correction.2", "patch", newest) == "1.3.2"


# ---------- apply, end to end, on a scratch copy of the release ----------

LPG_SCRIPTS = Path("skills") / "ontology-to-lpg" / "scripts"


def scratch_release(tmp_path, git_copy):
    """A copy of what a change reads and writes: the ontology folder, the process authority that the kpi module's
    tests read, release.json, the stand-alone exceptions, the KPI intake pack, the kpi_store code and the
    ontology-to-lpg skill's scripts. With git_copy,
    a Git repository with the copy as its one commit."""
    root = tmp_path / "release"
    shutil.copytree(ROOT / ONTOLOGY, root / ONTOLOGY, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "business_architecture" / "business_process", root / "business_architecture" / "business_process",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "release.json", root / "release.json")
    shutil.copy2(ROOT / ".gitignore", root / ".gitignore")   # as a real release has it, so Python's cache stays out
    (root / "scripts").mkdir()
    shutil.copy2(ROOT / cut.EXCEPTIONS, root / cut.EXCEPTIONS)
    shutil.copytree(ROOT / "kpi-intake", root / "kpi-intake")
    shutil.copytree(ROOT / "kpi_store", root / "kpi_store", ignore=shutil.ignore_patterns("__pycache__", "tests"))
    # The projection's Neo4j specification maps the shapes with the ontology-to-lpg skill's scripts.
    shutil.copytree(ROOT / LPG_SCRIPTS, root / LPG_SCRIPTS, ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
    if git_copy:
        git(root, "init", "-q", "-b", "work")
        git(root, "config", "user.name", "Sample Runner")
        git(root, "config", "user.email", "runner@example.invalid")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "The release as received")
    return root


def git(root, *args):
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def no_global_git(monkeypatch):
    """Git reads no configuration but the repository's own, so the tests do not depend on the machine's author."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_DIR",
                 "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)


def digest(root):
    h = hashlib.sha256()
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__",))
        for name in sorted(files):
            path = Path(folder) / name
            h.update(path.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def _versions(root):
    return ov.newest_versions(root / ov.RELEASES)


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_rename_a_new_other_name_and_a_process_link_go_from_the_form_to_a_committed_minor_release(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    measure, linked, free = pick(root)
    m, label = f"measure:{measure['notation']}", measure["label"]
    path = form(tmp_path, measure, {"T2": f"{label} (renamed)", "T4": ["a made-up other name"], "T6": [free]})
    [folder] = propose_cmd.propose([path], tmp_path / "proposals", root, now=NOW, say=quiet)
    lines = [f"rename {m} from '{label}' to '{label} (renamed)'", f"create exact synonym 'a made-up other name' for {m}",
             f"create edge {m} kpi:informsProcess {curie(free)}"]
    assert (folder / "change.kgcl").read_text(encoding="utf-8").splitlines() == lines
    before, held = root / kpi_tables.MEASURES, _versions(root)
    kept = tmp_path / "measures-before.ttl"
    shutil.copy2(before, kept)
    order = cut._run("list", ["dependents.py", "kpi"], root / ONTOLOGY / "release").split()
    k = ov.version_key(held["kpi"])
    expected = {"kpi": f"{k[0]}.{k[1] + 1}.0"}
    expected.update({mod: f"{ov.version_key(held[mod])[0]}.{ov.version_key(held[mod])[1]}.{ov.version_key(held[mod])[2] + 1}"
                     for mod in order if mod != "kpi"})

    # A change that is not committed stops the apply before it does anything.
    (root / "note.txt").write_text("not committed\n", encoding="utf-8")
    with pytest.raises(ChangeRefused, match="has changes that are not committed: note.txt. Commit them or put them aside, then run it again"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)
    (root / "note.txt").unlink()

    said = []
    files = apply_cmd.apply([folder], root, say=said.append, now=NOW)
    assert said[0] == "1 proposal to apply:" and f"  kpi {held['kpi']} -> {expected['kpi']}" in said
    steps = [line[4:] for line in said if line.startswith("... ")]
    assert steps.index("compare the kpi module before and after") < steps.index(f"set kpi to {expected['kpi']}") \
        < steps.index("rebuild the catalog") < steps.index("run the kpi module's tests") < steps.index("write the release")
    assert said[-2].startswith(f"Done. kpi is now {expected['kpi']} (minor), and {len(order) - 1} modules that depend on it took a new patch.")
    # The release holds the new versions, one commit with exactly the changed files, and a clean tree.
    assert {mod: v for mod, v in _versions(root).items() if mod in expected} == expected
    assert git(root, "status", "--porcelain") == ""
    assert git(root, "log", "-1", "--format=%s").strip() == f"Apply the term change {folder.name}: kpi {expected['kpi']}"
    assert set(git(root, "show", "--name-only", "--no-renames", "--format=", "HEAD").split()) == set(files)
    # The round trip: the difference between the kpi module before and after is exactly the proposal's lines.
    assert sorted(kpi_tables.compare(kept, before)) == sorted(lines)
    # The approval record is in the release, and the new kpi package names it with the Architect's words.
    record = approval.read_record(approval.record_path(root, folder.name))
    assert record["route"] == "minor" and approval.holds_words(record, "The form is complete, and I approve the change to the ontology.")
    manifest = json.loads((root / ov.RELEASES / "kpi" / expected["kpi"] / "manifest.json").read_text(encoding="utf-8"))
    assert f"approvals/{folder.name}.json" in json.dumps(manifest)
    # The KPI intake pack was rebuilt, so the form's pick lists offer the new name and are current.
    lists = picklists.load(root / "kpi-intake")
    assert lists["versions"]["kpi"] == expected["kpi"] and picklists.stale_modules(lists, root) == {}
    assert next(x for x in lists["lists"]["measures"] if x["id"] == measure["id"])["label"] == f"{label} (renamed)"
    # The same proposal again is refused: the release holds its record.
    with pytest.raises(ChangeRefused, match=f"the proposal {folder.name} was applied before"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)


def test_a_minor_and_a_major_together_release_a_major_that_names_the_ontology_owners_record_and_words(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    measure, linked, free = pick(root)
    lists = picklists.load(root / "kpi-intake")["lists"]
    other = next(m for m in lists["measures"] if m["id"] != measure["id"])
    one = form(tmp_path, measure, {"T4": ["a made-up other name"]}, name="minor")
    two = form(tmp_path, other, {"T3": "A made-up definition.", "T8": "no"}, MAJOR_SIGNED, name="major")
    minor, major = propose_cmd.propose([one, two], tmp_path / "proposals", root, now=NOW, say=quiet)
    held = _versions(root)["kpi"]
    apply_cmd.apply([minor, major], root, say=quiet, now=NOW)
    new = f"{ov.version_key(held)[0] + 1}.0.0"
    assert _versions(root)["kpi"] == new
    manifest = json.loads((root / ov.RELEASES / "kpi" / new / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["approved_by"] == {"who": "The Ontology Owner", "recorded_in": f"approvals/{major.name}.json",
                                       "words": "This change alters what the measure means, and I approve it as a major change."}


def test_a_failing_step_and_a_builder_error_roll_everything_back(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    measure, linked, free = pick(root)
    path = form(tmp_path, measure, {"T4": ["a made-up other name"]})
    [folder] = propose_cmd.propose([path], tmp_path / "proposals", root, now=NOW, say=quiet)
    before = digest(root)

    # A failure after the packages are written and moved, in the temporary copy.
    steps = []

    def fail_at_the_catalog(name):
        steps.append(name)
        if name == "rebuild the catalog":
            raise RuntimeError("made-up failure")
    with pytest.raises(cut.CutFailed, match="the step 'rebuild the catalog' failed: RuntimeError: made-up failure. The release is as it was."):
        apply_cmd.apply([folder], root, say=quiet, now=NOW, before_step=fail_at_the_catalog)
    assert "finish kpi" in steps and "write the release" not in steps
    assert digest(root) == before

    # The kpi builder fails on the changed tables.
    builder = root / kpi_tables.KPI_FOLDER / kpi_tables.BUILDER
    builder.write_text('import sys\nsys.exit("made-up builder failure")\n', encoding="utf-8")
    before = digest(root)
    with pytest.raises(cut.CutFailed, match="(?s)the step 'apply the changes to the kpi tables and rebuild the kpi module' "
                                            "failed: ChangeRefused: the kpi builder refused the changed tables.*made-up builder failure"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)
    assert digest(root) == before
    assert not approval.record_path(root, folder.name).exists()


def test_the_command_line_of_apply_says_why_and_changes_nothing(tmp_path, capsys):
    folder = _write(tmp_path / "unsigned", ["create exact synonym 'x' for measure:a"], signatures=[
        {"role": "Data Owner", "name": "A Data Owner", "date": "2026-11-19", "words": "Right."}])
    assert apply_cmd.main([str(folder), "--release", str(ROOT)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Not applied: the proposal unsigned is not approved") and err.rstrip().endswith("Nothing was changed.")
    assert err.count("\n") == 1
