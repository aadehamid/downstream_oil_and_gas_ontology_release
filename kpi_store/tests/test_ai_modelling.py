"""AI-drafted modelling under the five gates of KPI-DEC-0002, Q19 (Q17(a), Q20 and Q26).

The drafter and the reviewer work by hand, with the release's made-up sample answers (kpi_store/ai/sample-draft.json
and sample-review.json), or through the stub HTTP server of test_ai_option.py, which speaks the providers' documented
request and reply. No test reaches a real service. Forms and proposals go to temporary folders; the release tree is
only read, except by the one apply test, which runs on a scratch copy.

Each gate has a test that it passes on the sample and a test that it refuses what it must refuse:
    gate 1   a competency question with another answer, a failing example that breaks nothing, a node shape with
             no failing example, and passing examples that break a shape
    gate 2   an example that is in two disjoint classes: the reasoner finds the contradiction
    gate 3   a reviewer of the drafter's family, a reviewer with no family, and a HOLD, which propose then refuses
    gate 4   a summary that leaves out a new term
    gate 5   the propose and apply commands without the Ontology Owner's signature or with a route below major
"""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kpi_store import apply as apply_cmd, local_settings as ls, propose as propose_cmd
from kpi_store.ai import AIRefused, draft, providers
from kpi_store.change import ChangeRefused, approval, drafted, proposal
from kpi_store.intake import check
from kpi_store.tests import support
from kpi_store.tests.test_ai_option import Stub, no_proxy, quiet, settings  # noqa: F401
from kpi_store.tests.test_new_module import full_release
from kpi_store.tests.test_propose_apply import NOW, git, no_global_git  # noqa: F401

ROOT = support.ROOT
SAMPLE_DRAFT = ROOT / "kpi_store" / "ai" / "sample-draft.json"
SAMPLE_REVIEW = ROOT / "kpi_store" / "ai" / "sample-review.json"
P = "sampletankinspections"
APPROVED = {"approved_by": "An IT Approver", "approved_on": "2026-11-20"}
DRAFTER = ls.AI("by-hand", assistant="Genie Code", family="claude", **APPROVED)
REVIEWER = ls.AI("by-hand", assistant="A second assistant", family="gpt", **APPROVED)
SIGNED = {"data-owner": {"name": "A Data Owner", "date": "2026-11-20"},
          "ontology-owner": {"name": "An Ontology Owner", "date": "2026-11-20"},
          "architect": {"name": "An Architect", "date": "2026-11-20"}}
ANSWERS = {"N1": "Sample Tank Inspections", "N2": "The made-up inspections of the storage tanks of a made-up terminal.",
           "N3": "new-modelling", "N12": ["A made-up tank inspection procedure, 2026-11-20"],
           "N13": "An inspection checks one storage tank on one date, and one system that the ontology lists holds its "
                  "record. For example, the inspection of 2 November 2026 is recorded in the APS planning database."}


def form(folder, answers=None, sign_offs=None):
    data = {"format": 1, "form": "new-module", "catalogue_version": "1.2", "kpi_name": "Sample Tank Inspections",
            "request": {"number": "NM-2026-003", "date": "2026-11-20", "requester_role": "Data Owner", "invited": ""},
            "answers": {**ANSWERS, **(answers or {})}, "sign_offs": sign_offs or {}, "consulted": {},
            "example_of": "", "comment": ""}
    path = Path(folder) / "sample-tank-inspections.new-module.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def sign(path, sign_offs=SIGNED):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sign_offs"] = sign_offs
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def sample(**changes):
    """The sample draft answer, with some of its parts replaced."""
    data = json.loads(SAMPLE_DRAFT.read_text(encoding="utf-8"))
    data.update(changes)
    return data


def answer_file(folder, data, name="draft-answer.json"):
    path = Path(folder) / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def run(path, **kw):
    kw = {"drafter": DRAFTER, "reviewer": REVIEWER, "today": "2026-11-20", "say": quiet, **kw}
    return draft.run(path, ROOT, **kw)


def drafted_form(folder, review=SAMPLE_REVIEW, data=None):
    """A form with its draft and its review done, by hand, from the sample answers."""
    path = form(folder)
    run(path, answer_file=answer_file(folder, data) if data else SAMPLE_DRAFT)
    run(path, review_file=review)
    return path


def gates_of(data):
    spec = drafted.spec_of_form(ANSWERS, ROOT)
    spec, files = drafted.from_answer(json.dumps(data), spec, ROOT)
    return {g["gate"]: g for g in drafted.gates(spec, files, ROOT)}


# ---------- the pattern's checks and gates 1, 2 and 4 ----------

def test_the_sample_draft_passes_gates_1_2_and_4():
    found = gates_of(sample())
    assert [g["passed"] for g in found.values()] == [True, True, True], found
    assert "CQ1: gives the answer it expects" in found[1]["results"]
    assert any("F1: breaks shp:TankInspection" in r for r in found[1]["results"])


def test_gate_1_fails_on_a_question_whose_answer_is_not_the_one_it_expects():
    q = sample()["questions"]
    q[0]["expected"] = [["ex:inspection-1", "2026-11-03"]]
    found = gates_of(sample(questions=q))
    assert not found[1]["passed"]
    assert any(r.startswith("CQ1: expects") for r in found[1]["results"])


def test_gate_1_fails_on_a_failing_example_that_breaks_nothing():
    e = sample()["examples"]
    e["fail"][1] = dict(e["fail"][1], add=f"ex:inspection-1 {P}:recordedIn system:aps .", remove=
                        f"ex:inspection-1 {P}:recordedIn system:aps-planning-db .")
    found = gates_of(sample(examples=e))
    assert not found[1]["passed"]
    assert any("F2: should break shp:TankInspection" in r for r in found[1]["results"])


def test_gate_1_fails_when_a_node_shape_has_no_failing_example():
    shapes = sample()["shapes"] + f"\nshp:Other a sh:NodeShape ; sh:targetClass {P}:TankInspection ;\n" \
        f"    sh:property [ sh:path {P}:inspectionDate ; sh:maxCount 1 ] .\n"
    summary = sample()["summary"] + [{"term": "shp:Other", "meaning": "A second rule.", "example": "One date."}]
    found = gates_of(sample(shapes=shapes, summary=summary))
    assert not found[1]["passed"]
    assert "no failing example breaks shp:Other, so nothing shows that its rules hold" in found[1]["results"]


def test_gate_1_fails_when_the_passing_examples_break_a_shape():
    e = sample()["examples"]
    e["pass"] += f'ex:inspection-2 a {P}:TankInspection ; {P}:recordedIn system:aps-planning-db .\n'
    found = gates_of(sample(examples=e))
    assert not found[1]["passed"]
    assert any(r.startswith("the passing examples break the draft's shapes") for r in found[1]["results"])


def test_gate_1_fails_when_an_example_breaks_a_shape_of_a_required_module():
    e = sample()["examples"]
    e["pass"] += "ex:a-new-system a sys:System .\n"
    found = gates_of(sample(examples=e))
    assert not found[1]["passed"]
    assert any("break a shape of a module the module requires" in r for r in found[1]["results"])


def test_gate_2_the_reasoner_finds_a_thing_in_two_disjoint_classes():
    e = sample()["examples"]
    e["pass"] = e["pass"].replace(f"a {P}:TankInspection ;", f"a {P}:TankInspection, sys:System ;")
    found = gates_of(sample(examples=e))
    assert not found[2]["passed"]
    assert any("Disjoint classes" in r and "inspection-1" in r for r in found[2]["results"]), found[2]


def test_gate_4_fails_when_the_summary_leaves_out_a_new_term():
    found = gates_of(sample(summary=sample()["summary"][:-1]))
    assert not found[4]["passed"]
    assert "shp:TankInspection has no entry that says in words what it means, with an example" in found[4]["results"]


@pytest.mark.parametrize("change,message", [
    ({"model": sample()["model"] + '\nsys:System rdfs:comment "changed"@en .\n'}, "is not a term of the module's namespace"),
    ({"model": sample()["model"].replace(f"    rdfs:domain {P}:TankInspection ;\n    rdfs:range xsd:date .",
                                         "    rdfs:range xsd:date .")}, "must have exactly one rdfs:domain"),
    ({"model": sample()["model"].replace("rdfs:range sys:System", "rdfs:range sys:NoSuchClass")},
     "names sys:NoSuchClass, which neither the draft nor a module it requires defines"),
    ({"shapes": sample()["shapes"].replace(f"sh:targetClass {P}:TankInspection", "sh:targetClass sys:System")},
     "targets sys:System, which is not a term of the module"),
    ({"shapes": sample()["shapes"].replace(f"sh:path {P}:inspectionDate ; sh:minCount 1 ; sh:maxCount 1 ;",
                                           f"sh:path {P}:inspectionDate ;")}, "no shape gives the cardinality"),
    ({"questions": [dict(sample()["questions"][0], sparql="SELECT * WHERE { SERVICE <http://example.org/s> { ?s ?p ?o } "
                         f"?s a {P}:TankInspection }}")]}, "uses SERVICE, FROM or FROM NAMED"),
    ({"examples": dict(sample()["examples"], pass_=None) and {"pass": sample()["examples"]["pass"] +
      'system:aps-planning-db rdfs:comment "changed"@en .\n', "fail": sample()["examples"]["fail"]}},
     "Example data uses names of the examples namespace"),
])
def test_the_pattern_refuses_a_draft_that_does_not_have_its_form(change, message):
    with pytest.raises(ChangeRefused, match=message):
        gates_of(sample(**change))


def test_an_answer_of_another_form_is_refused_whole():
    spec = drafted.spec_of_form(ANSWERS, ROOT)
    with pytest.raises(ChangeRefused, match="exactly model, shapes, questions, examples and summary"):
        drafted.from_answer(json.dumps({"model": ""}), spec, ROOT)
    with pytest.raises(ChangeRefused, match="not JSON"):
        drafted.from_answer("here is your module", spec, ROOT)


def test_each_class_and_property_gets_the_forms_documents_as_its_citation():
    spec = drafted.spec_of_form(ANSWERS, ROOT)
    spec, files = drafted.from_answer(SAMPLE_DRAFT.read_text(encoding="utf-8"), spec, ROOT)
    assert files["model.ttl"].count('dcterms:bibliographicCitation "A made-up tank inspection procedure, 2026-11-20"@en') == 3
    assert spec["depends_on"] == ["system"]


# ---------- the AI steps, by hand ----------

def test_by_hand_the_command_writes_each_prompt_and_stops(tmp_path):
    path = form(tmp_path)
    assert run(path) is None
    prompt = path.with_name(path.stem + draft.DRAFT_PROMPT)
    text = prompt.read_text(encoding="utf-8")
    for name in draft.DRAFT_SKILLS:
        assert (ROOT / name).read_text(encoding="utf-8") in text
    assert ANSWERS["N13"] in text and "sys:System (class)" in text
    assert not path.with_name(path.stem + drafted.RECORD_SUFFIX).exists()
    assert run(path, answer_file=SAMPLE_DRAFT) is None
    review = path.with_name(path.stem + draft.REVIEW_PROMPT).read_text(encoding="utf-8")
    for name in draft.REVIEW_SKILLS:
        assert (ROOT / name).read_text(encoding="utf-8") in review
    assert "## model.ttl" in review and "Gate 2, the reasoner finds the model consistent: passed" in review
    record_path = run(path, review_file=SAMPLE_REVIEW)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    approval.check_draft(record, signed=False)
    assert [g["gate"] for g in record["gates"]] == [1, 2, 3, 4] and all(g["passed"] for g in record["gates"])
    # Q20: the fingerprints of the prompts and the answers, and no prompt text.
    assert record["drafter"]["prompt_sha256"] == hashlib.sha256(prompt.read_bytes()).hexdigest()
    assert record["drafter"]["output_sha256"] == hashlib.sha256(SAMPLE_DRAFT.read_bytes()).hexdigest()
    assert record["reviewer"]["output_sha256"] == hashlib.sha256(SAMPLE_REVIEW.read_bytes()).hexdigest()
    assert record["drafter"]["skills"][0] == {"path": "skills/ontology/SKILL.md", "sha256": hashlib.sha256(
        (ROOT / "skills/ontology/SKILL.md").read_bytes()).hexdigest()}
    assert ANSWERS["N13"] not in record_path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["answers"] == ANSWERS   # the AI changes no answer
    summary = path.with_name(path.stem + draft.SIGNERS_SUMMARY).read_text(encoding="utf-8")
    assert 'The class "tank inspection"' in summary and "The reviewer's verdict: PASS." in summary


def test_a_draft_that_fails_a_gate_keeps_nothing(tmp_path):
    path = form(tmp_path)
    bad = sample(summary=sample()["summary"][:-1])
    with pytest.raises(AIRefused, match="did not pass gate 4"):
        run(path, answer_file=answer_file(tmp_path, bad))
    assert not path.with_name(path.stem + drafted.RECORD_SUFFIX).exists()
    assert not path.with_name(path.stem + drafted.FOLDER_SUFFIX).exists()


@pytest.mark.parametrize("reviewer,message", [
    (ls.AI("by-hand", assistant="Another", family="Claude", **APPROVED), 'both of the family "claude"'),
    (ls.AI("by-hand", assistant="Another", **APPROVED), r"\[ai_reviewer\] family must name"),
    (ls.AI("off"), r"\[ai_reviewer\] provider is"),
])
def test_gate_3_needs_a_reviewer_of_another_family(tmp_path, reviewer, message):
    with pytest.raises(AIRefused, match=message):
        run(form(tmp_path), reviewer=reviewer)


def test_a_signed_form_and_a_form_of_another_pattern_are_refused(tmp_path):
    with pytest.raises(AIRefused, match="signed already"):
        run(form(tmp_path, sign_offs=SIGNED))
    with pytest.raises(AIRefused, match="new modelling"):
        run(form(tmp_path, {"N3": "vocabulary"}))


def test_a_hold_is_recorded_and_the_propose_command_refuses_the_form(tmp_path):
    hold = answer_file(tmp_path, {"verdict": "HOLD", "findings": [
        {"gate": "Step 3", "finding": "The definition of tank inspection names no tank."}]}, "hold.json")
    path = drafted_form(tmp_path, review=hold)
    record = json.loads(path.with_name(path.stem + drafted.RECORD_SUFFIX).read_text(encoding="utf-8"))
    assert record["reviewer"]["verdict"] == "HOLD"
    assert [g["passed"] for g in record["gates"] if g["gate"] == 3] == [False]
    sign(path)
    with pytest.raises(propose_cmd.ProposeRefused, match="gate 3"):
        propose_cmd.propose([path], release_root=ROOT, now=NOW, say=quiet)


def test_a_review_answer_of_another_form_is_refused(tmp_path):
    path = form(tmp_path)
    run(path, answer_file=SAMPLE_DRAFT)
    for bad, message in (({"verdict": "OK", "findings": []}, "is not of the form"),
                         ({"verdict": "HOLD", "findings": []}, "HOLD with no finding")):
        with pytest.raises(AIRefused, match=message):
            run(path, review_file=answer_file(tmp_path, bad, "review.json"))


# ---------- the AI steps, through the providers (a stub server) ----------

def test_the_drafter_and_the_reviewer_are_called_with_their_skills(tmp_path, monkeypatch):
    no_proxy(monkeypatch)
    stub = Stub()
    try:
        stub.replies["/v1/messages"] = (200, {"model": "claude-made-up-1", "stop_reason": "end_turn",
                                              "content": [{"type": "text", "text": SAMPLE_DRAFT.read_text(encoding="utf-8")}]})
        stub.replies["/v1/chat/completions"] = (200, {"model": "gpt-made-up-2", "choices": [
            {"finish_reason": "stop", "message": {"content": SAMPLE_REVIEW.read_text(encoding="utf-8")}}]})
        d = ls.AI("anthropic", model="claude-made-up", key_env="DRAFT_KEY", url=stub.url + "/v1/messages", family="claude",
                  **APPROVED)
        r = ls.AI("openai", model="gpt-made-up", key_env="REVIEW_KEY", url=stub.url + "/v1/chat/completions",
                  family="gpt", **APPROVED)
        path = form(tmp_path)
        record_path = run(path, drafter=d, reviewer=r, environ={"DRAFT_KEY": "k1", "REVIEW_KEY": "k2"})
    finally:
        stub.close()
    first, second = stub.requests
    skills = lambda names: "\n\n".join((ROOT / n).read_bytes().decode("utf-8") for n in names)
    assert first["body"]["system"] == [{"type": "text", "text": skills(draft.DRAFT_SKILLS)}]
    assert first["body"]["max_tokens"] == draft.MAX_TOKENS
    assert first["headers"]["authorization"] == "Bearer k1"
    assert second["body"]["messages"][0] == {"role": "system", "content": skills(draft.REVIEW_SKILLS)}
    assert second["headers"]["authorization"] == "Bearer k2"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert (record["drafter"]["model_version"], record["reviewer"]["model_version"]) == ("claude-made-up-1", "gpt-made-up-2")
    assert record["drafter"]["endpoint"] == stub.url + "/v1/messages"
    assert "k1" not in record_path.read_text(encoding="utf-8") and "k2" not in record_path.read_text(encoding="utf-8")


# ---------- the check, the propose command and gate 5 ----------

def test_the_check_takes_new_modelling_and_needs_n13(tmp_path):
    found = check.run(form(tmp_path, sign_offs=SIGNED), ROOT / "kpi-intake")
    assert found.complete, found.lines
    assert any("--ai-draft" in line for line in found.lines)
    found = check.run(form(tmp_path, {"N13": ""}, sign_offs=SIGNED), ROOT / "kpi-intake")
    assert not found.complete


def test_a_signed_form_without_a_draft_is_refused(tmp_path):
    path = form(tmp_path, sign_offs=SIGNED)
    with pytest.raises(propose_cmd.ProposeRefused, match="no AI draft beside it"):
        propose_cmd.propose([path], release_root=ROOT, now=NOW, say=quiet)


def test_the_proposal_holds_the_draft_and_every_gate(tmp_path):
    path = drafted_form(tmp_path)
    sign(path)
    folder, = propose_cmd.propose([path], release_root=ROOT, now=NOW, say=quiet)
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert record["route"] == "major" and record["new_module"] is True
    assert [(g["gate"], g["passed"]) for g in record["draft"]["gates"]] == [(n, True) for n in range(1, 6)]
    assert sorted(p.name for p in (folder / "draft").iterdir()) == sorted(drafted.pattern(ROOT).FILES)
    lines = (folder / "change.kgcl").read_text(encoding="utf-8").splitlines()
    assert f"create node {P}:TankInspection 'tank inspection'" in lines
    assert f"create edge {P}:recordedIn rdfs:range sys:System" in lines
    p = proposal.read(folder)
    assert apply_cmd.plan([folder], ROOT)[1] == apply_cmd.NEW_MODULE   # the apply's checks pass before it writes
    assert "Gate 5, the Ontology Owner signs, and the release is 1.0.0: passed." in (folder / "summary.txt").read_text(encoding="utf-8")
    assert p.facts[0] == ("module:sample-tank-inspections", "pattern", "drafted")


def test_propose_refuses_a_form_whose_answers_or_draft_changed_after_the_ai_step(tmp_path):
    path = drafted_form(tmp_path)
    sign(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["answers"]["N2"] = "Something the AI did not read."
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(propose_cmd.ProposeRefused, match="answers changed after the AI drafted"):
        propose_cmd.propose([path], release_root=ROOT, now=NOW, say=quiet)
    data["answers"]["N2"] = ANSWERS["N2"]
    path.write_text(json.dumps(data), encoding="utf-8")
    model = path.with_name(path.stem + drafted.FOLDER_SUFFIX) / "model.ttl"
    model.write_text(model.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(propose_cmd.ProposeRefused, match="not those the AI drafted"):
        propose_cmd.propose([path], release_root=ROOT, now=NOW, say=quiet)


def _proposal(tmp_path):
    path = drafted_form(tmp_path)
    sign(path)
    folder, = propose_cmd.propose([path], release_root=ROOT, out=tmp_path / "proposals", now=NOW, say=quiet)
    return folder


def _edit(folder, change):
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    change(record)
    (folder / "approval.json").write_text(json.dumps(record), encoding="utf-8")


@pytest.mark.parametrize("change,message", [
    (lambda r: r.update(signatures=[s for s in r["signatures"] if s["role"] != "Ontology Owner"]),
     "needs the signature of the Ontology Owner"),
    (lambda r: r["draft"]["reviewer"].update(verdict="HOLD"), "every gate from 1 to 5 passed"),
    (lambda r: r["draft"].update(gates=[g for g in r["draft"]["gates"] if g["gate"] != 5]), "every gate from 1 to 5"),
    (lambda r: r["draft"]["reviewer"].update(family="Claude"), "of the drafter's own model family"),
    (lambda r: r.update(route="minor"), "a new module's first release is a major"),
])
def test_apply_refuses_a_proposal_whose_gates_do_not_all_pass(tmp_path, change, message):
    folder = _proposal(tmp_path)
    _edit(folder, change)
    with pytest.raises(ChangeRefused, match=message):
        apply_cmd.plan([folder], ROOT)


def test_apply_refuses_a_proposal_whose_draft_files_changed(tmp_path):
    folder = _proposal(tmp_path)
    shapes = folder / "draft" / "shapes.ttl"
    shapes.write_text(shapes.read_text(encoding="utf-8").replace("sh:minCount 1", "sh:minCount 0"), encoding="utf-8")
    with pytest.raises(ChangeRefused, match="not those the AI drafted"):
        apply_cmd.plan([folder], ROOT)


# ---------- the apply ----------

def test_apply_releases_the_drafted_module_at_1_0_0(tmp_path, no_global_git):
    folder = _proposal(tmp_path)
    root = full_release(tmp_path)
    apply_cmd.apply([folder], root, say=quiet, now=NOW)
    module = root / "business_architecture" / "ontology" / "sample-tank-inspections"
    assert sorted(p.name for p in module.iterdir() if p.name != "__pycache__") == sorted(
        drafted.pattern(ROOT).FILES + ("README.md", "README.html", "build_sample_tank_inspections.py",
                                       "test_sample_tank_inspections.py"))
    done = subprocess.run([sys.executable, "build_sample_tank_inspections.py", "--verify"], cwd=module,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "gate 2, the reasoner finds the model consistent: passed" in done.stdout
    kept = json.loads((root / "business_architecture/ontology/approvals/NM-2026-003.json").read_text(encoding="utf-8"))
    assert kept["draft"] == json.loads((folder / "approval.json").read_text(encoding="utf-8"))["draft"]
    assert (root / "business_architecture/ontology/releases/sample-tank-inspections/1.0.0/sample-tank-inspections.ttl").is_file()
    assert "Apply the new module NM-2026-003: sample-tank-inspections 1.0.0" in git(root, "log", "--oneline", "-1")


# ---------- the settings ----------

def test_the_settings_name_the_reviewer_in_ai_reviewer_and_refuse_a_key_there(tmp_path):
    text = ('[ai]\nprovider = "by-hand"\nassistant = "Genie Code"\nfamily = "claude"\napproved_by = "An IT Approver"\n'
            'approved_on = "2026-11-20"\n\n[ai_reviewer]\nprovider = "openai"\nmodel = "gpt-made-up"\nkey_env = "REVIEW_KEY"\n'
            'family = "gpt"\napproved_by = "An IT Approver"\napproved_on = "2026-11-20"\n')
    found = ls.load(settings(tmp_path, text), environ={}, release_root=ROOT)
    assert (found.ai.family, found.ai_reviewer.provider, found.ai_reviewer.family) == ("claude", "openai", "gpt")
    with pytest.raises(ls.LocalSettingsError, match=r"\[ai_reviewer\] api_key is not a setting"):
        ls.load(settings(tmp_path, text + 'api_key = "x"\n'), environ={}, release_root=ROOT)


# ---------- the first review's findings ----------

R1 = [
    # 1: a SHACL rule, or any term outside SHACL Core, in the shapes
    ({"shapes": sample()["shapes"].replace(
        "sh:targetClass sampletankinspections:TankInspection ;",
        "sh:targetClass sampletankinspections:TankInspection ;\n"
        "    sh:rule [ a sh:TripleRule ; sh:subject sys:System ; sh:predicate rdfs:comment ; sh:object \"x\" ] ;")},
     "not a term of SHACL Core"),
    # 2: a SERVICE written with an escape, and a module term in a comment only
    ({"questions": [dict(sample()["questions"][0], sparql=
        "SELECT ?i WHERE { S\\u0045RVICE <http://127.0.0.1:9/sparql> { ?s ?p ?o } ?i a sampletankinspections:TankInspection }")]},
     "SERVICE"),
    ({"questions": [dict(sample()["questions"][0], sparql="# sampletankinspections:TankInspection\nASK { ?s ?p ?o }",
                         expected=True)]}, "names no term of the module"),
    ({"questions": [dict(sample()["questions"][0], sparql=
        "CONSTRUCT { ?i ?p ?o } WHERE { ?i a sampletankinspections:TankInspection ; ?p ?o }")]}, "SELECT or ASK"),
    # 3 and 5: a shape not typed sh:NodeShape, an orphan property shape, a nested one, a deactivated one
    ({"shapes": sample()["shapes"] + "\nshp:Hidden sh:targetClass sampletankinspections:TankInspection ;\n"
      "    sh:property [ sh:path sampletankinspections:recordedIn ; sh:maxCount 1 ] .\n"}, "typed sh:NodeShape"),
    ({"shapes": sample()["shapes"].replace(
        "sh:path sampletankinspections:recordedIn ; sh:minCount 1 ; sh:maxCount 1 ;", "sh:path sampletankinspections:recordedIn ;")
      + "\nshp:Orphan a sh:PropertyShape ; sh:path sampletankinspections:recordedIn ; sh:minCount 1 .\n"},
     "sh:PropertyShape|blank node reached"),
    ({"shapes": sample()["shapes"].replace(
        "sh:message \"An inspection has exactly one date.\" ]",
        "sh:message \"An inspection has exactly one date.\" ;\n"
        "                  sh:property [ sh:path sampletankinspections:inspectionDate ; sh:minCount 1 ] ]")},
     "nested"),
    ({"shapes": sample()["shapes"].replace("sh:targetClass", "sh:deactivated true ;\n    sh:targetClass")}, "sh:deactivated"),
    # 4: sameAs to a term of the release
    ({"model": sample()["model"] + "\nsampletankinspections:Alias a owl:NamedIndividual ; rdfs:label \"alias\"@en ;\n"
      "    skos:definition \"An alias.\"@en ; owl:sameAs system:aps-planning-db .\n"}, "owl:sameAs"),
    # 6: an example with a blank-node subject
    ({"examples": {"pass": sample()["examples"]["pass"] + "[] a sys:System .\n", "fail": sample()["examples"]["fail"]}},
     "blank node"),
    # 9: a term of two kinds, and an individual with two labels
    ({"model": sample()["model"] + "\nsampletankinspections:TankA a owl:NamedIndividual ;\n"
      "    rdfs:label \"Tank A\"@en, \"Primary tank\"@en ; skos:definition \"A made-up tank.\"@en .\n"}, "exactly one English label"),
    ({"model": sample()["model"].replace("sampletankinspections:TankInspection a owl:Class ;",
                                         "sampletankinspections:TankInspection a owl:Class, owl:NamedIndividual ;")},
     "one kind"),
]


@pytest.mark.parametrize("change,message", R1)
def test_round_1_the_pattern_refuses_what_the_review_found(change, message):
    with pytest.raises(ChangeRefused, match=message):
        gates_of(sample(**change))


def test_round_1_a_query_may_name_a_variable_from():
    q = dict(sample()["questions"][0], sparql="SELECT ?inspection ?from WHERE { ?inspection a sampletankinspections:TankInspection ;"
             " sampletankinspections:recordedIn system:aps-planning-db ; sampletankinspections:inspectionDate ?from }")
    assert gates_of(sample(questions=[q]))[1]["passed"]


def test_round_1_a_definition_kgcl_cannot_carry_is_refused_before_anyone_signs(tmp_path):
    bad = sample(model=sample()["model"].replace("The date on which the inspection took place.", "Line one.\\nLine two."))
    path = form(tmp_path)
    with pytest.raises(AIRefused):
        run(path, answer_file=answer_file(tmp_path, bad))
    assert not path.with_name(path.stem + drafted.RECORD_SUFFIX).exists()


@pytest.mark.parametrize("change,message", [
    (lambda r: r["draft"]["module"].update(prefix="aaa"), "prefix"),
    (lambda r: r["draft"]["module"].update(depends_on=["kpi", "system"]), "depends_on"),
    (lambda r: r["draft"]["module"]["prefixes"].update(evil="https://attacker.example/"), "prefixes"),
    (lambda r: r["draft"]["module"].update(depends_on=["no-such-module"]), "depends_on|no-such-module"),
    (lambda r: r["draft"]["module"].update(depends_on=[123]), "depends_on"),
    (lambda r: r["draft"]["reviewer"].update(family="claude "), "family"),
])
def test_round_1_apply_refuses_tampered_module_settings_and_families(tmp_path, change, message):
    folder = _proposal(tmp_path)
    _edit(folder, change)
    with pytest.raises(ChangeRefused, match=message):
        apply_cmd.plan([folder], ROOT)


def test_round_1_a_resumed_draft_checks_the_families_and_gates_before_the_review(tmp_path):
    path = form(tmp_path)
    run(path, answer_file=SAMPLE_DRAFT)
    prompt = path.with_name(path.stem + draft.REVIEW_PROMPT)
    prompt.unlink()
    swapped = ls.AI("by-hand", assistant="Another", family="claude", **APPROVED)
    with pytest.raises(AIRefused, match="family"):
        run(path, drafter=ls.AI("by-hand", assistant="Genie Code", family="gpt", **APPROVED), reviewer=swapped)
    assert not prompt.exists()
    record_path = path.with_name(path.stem + drafted.RECORD_SUFFIX)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["gates"] = []
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(AIRefused, match="gate"):
        run(path)
    assert not prompt.exists()


# ---------- the second review's findings ----------

SEE = "\nsampletankinspections:TankInspection rdfs:seeAlso [\n    {} ] .\n"
R2 = [
    # 4 and 6: blank nodes and terms outside the model's allowlist
    (SEE.format("owl:unionOf ( sys:System ) ;\n    rdfs:subClassOf [ a owl:Restriction ; owl:onProperty rdfs:comment ; "
                "owl:hasValue \"altered\"@en ]"), "blank node"),
    (SEE.format("owl:oneOf ( system:aps-planning-db ) ;\n    rdfs:subClassOf [ a owl:Restriction ; owl:onProperty "
                "rdfs:comment ; owl:hasValue \"altered\"@en ]"), "blank node"),
    (SEE.format("owl:sourceIndividual system:aps-planning-db ; owl:assertionProperty rdfs:comment ; "
                "owl:targetValue \"blocked\"@en"), "blank node"),
    (SEE.format("a sys:System"), "blank node"),
    ("\nsampletankinspections:TankInspection rdfs:seeAlso sys:System .\n", "rdfs:seeAlso"),
    ("\nsampletankinspections:recordedIn a owl:FunctionalProperty .\n", "owl:FunctionalProperty"),
    ("\nsampletankinspections:TankInspection sampletankinspections:recordedIn system:aps-planning-db .\n",
     "only on the module's own individuals"),
]


@pytest.mark.parametrize("more,message", R2)
def test_round_2_the_model_takes_only_its_allowlist(more, message):
    with pytest.raises(ChangeRefused, match=message):
        gates_of(sample(model=sample()["model"] + more))


@pytest.mark.parametrize("sparql,expected", [
    ("SELECT ?s ?i WHERE { ?s ^sampletankinspections:recordedIn ?i }", [["system:aps-planning-db", "ex:inspection-1"]]),
    ("SELECT ?i ?l WHERE { ?i sampletankinspections:recordedIn/skos:prefLabel ?l }", [["ex:inspection-1", "APS Planning DB"]]),
    ("SELECT ?i ?d WHERE { ?i sampletankinspections:inspectionDate+ ?d }", [["ex:inspection-1", "2026-11-02"]]),
])
def test_round_2_a_question_may_name_a_module_term_in_a_property_path(sparql, expected):
    q = dict(sample()["questions"][0], sparql=sparql, expected=expected)
    found = gates_of(sample(questions=[q]))
    assert found[1]["passed"], found[1]["results"]


# ---------- the quick check's findings ----------

QC_HEAD = f"""{P}:{{n}} a owl:Class ; rdfs:label "{{n}}"@en ; skos:definition "A helper."@en ;
    dcterms:bibliographicCitation "Ref" """
QC = {
    "subPropertyOf owl:sameAs": f"""
{P}:Alias a owl:Class ; rdfs:label "Alias"@en ; skos:definition "Helper class."@en ; dcterms:bibliographicCitation "Ref" .
{P}:aliasOf a owl:ObjectProperty ; rdfs:label "alias of"@en ; skos:definition "Alias link."@en ;
    dcterms:bibliographicCitation "Ref" ; rdfs:domain {P}:Alias ; rdfs:range {P}:Alias ; rdfs:subPropertyOf owl:sameAs .
{P}:Spoof a owl:NamedIndividual ; rdfs:label "Spoof"@en ; skos:definition "Spoof."@en ; rdfs:comment "altered"@en ;
    {P}:aliasOf system:aps-planning-db .
""",
    "subClassOf owl:FunctionalProperty": f"""
{P}:FuncProp a owl:Class ; rdfs:label "FuncProp"@en ; skos:definition "Marker."@en ; dcterms:bibliographicCitation "Ref" ;
    rdfs:subClassOf owl:FunctionalProperty .
{P}:LinkNode a owl:Class ; rdfs:label "LinkNode"@en ; skos:definition "Node."@en ; dcterms:bibliographicCitation "Ref" .
{P}:link a owl:ObjectProperty, {P}:FuncProp ; rdfs:label "link"@en ; skos:definition "Links nodes."@en ;
    dcterms:bibliographicCitation "Ref" ; rdfs:domain {P}:LinkNode ; rdfs:range {P}:LinkNode .
{P}:Bridge a owl:NamedIndividual ; rdfs:label "Bridge"@en ; skos:definition "Bridge."@en ; rdfs:comment "altered"@en ;
    {P}:link {P}:Bridge ; {P}:link system:aps-planning-db .
""",
    "range retypes a release item": f"""
{P}:Tag a owl:Class ; rdfs:label "Tag"@en ; skos:definition "Marker."@en ; dcterms:bibliographicCitation "Ref" .
{P}:tags a owl:ObjectProperty ; rdfs:label "tags"@en ; skos:definition "Tags a resource."@en ;
    dcterms:bibliographicCitation "Ref" ; rdfs:domain {P}:Tag ; rdfs:range {P}:Tag .
{P}:Tagger a owl:NamedIndividual ; rdfs:label "Tagger"@en ; skos:definition "Tagger."@en ;
    {P}:tags system:aps-planning-db .
"""}


@pytest.mark.parametrize("name", sorted(QC))
def test_qc_a_gate_2_refuses_a_model_that_changes_a_release_term(name):
    """A: the reasoner's rule by meaning, run on gate 2 alone, with no check of the form before it."""
    dm = drafted.pattern(ROOT)
    spec = dict(drafted.spec_of_form(ANSWERS, ROOT), depends_on=["system"],
                prefixes={"sys": "https://w3id.org/mpc/ontology/modules/system/",
                          "system": "https://w3id.org/mpc/ontology/modules/system/system/"})
    data = sample(model=sample()["model"] + QC[name])
    texts = {dm.MODEL: data["model"], dm.SHAPES: data["shapes"], dm.QUESTIONS: json.dumps(data["questions"]),
             dm.EXAMPLES: json.dumps(data["examples"]), dm.SUMMARY: json.dumps(data["summary"])}
    draft_ = dm.Draft(spec, texts)
    context_data, _ = dm.context(spec, str(ROOT / "business_architecture" / "ontology"))
    passed, lines = dm.gate_2(draft_, context_data)
    assert not passed
    assert any("system:aps-planning-db" in line and "would change" in line for line in lines), lines


@pytest.mark.parametrize("more,message", [
    (f"\n{P}:Alias a owl:Class ; rdfs:label \"Alias\"@en ; skos:definition \"A.\"@en ; rdfs:subClassOf owl:FunctionalProperty .\n",
     "rdfs:subClassOf"),
    (f"\n{P}:recordedIn rdfs:subPropertyOf owl:sameAs .\n", "rdfs:subPropertyOf"),
    (f"\n{P}:Spoof a owl:NamedIndividual, system:aps-planning-db ; rdfs:label \"S\"@en ; skos:definition \"S.\"@en .\n",
     "types"),
    (f"\n{P}:TankInspection a sys:System .\n", "types"),
    (f"\n{P}:TankInspection rdfs:domain sys:System .\n", "rdfs:domain"),
    (f"\n{P}:recordedIn rdfs:subPropertyOf {P}:TankInspection .\n", "rdfs:subPropertyOf"),
    (f"\n{P}:TankInspection owl:disjointWith owl:Thing .\n", "owl:disjointWith"),
])
def test_qc_b_schema_triples_take_a_module_subject_and_a_module_or_required_object(more, message):
    with pytest.raises(ChangeRefused, match=message):
        gates_of(sample(model=sample()["model"] + more))


def test_qc_c_a_defined_term_that_is_no_property_is_refused_as_a_predicate():
    with pytest.raises(ChangeRefused, match="not a property"):
        gates_of(sample(model=sample()["model"] +
                        f"\n{P}:TankInspection {P}:TankInspection system:aps-planning-db .\n"))


@pytest.mark.parametrize("spoil", ["extra", "failed"])
def test_qc_d_the_resume_guard_itself_refuses_a_failed_gate_entry(tmp_path, spoil):
    path = form(tmp_path)
    run(path, answer_file=SAMPLE_DRAFT)
    prompt = path.with_name(path.stem + draft.REVIEW_PROMPT)
    prompt.unlink()
    record_path = path.with_name(path.stem + drafted.RECORD_SUFFIX)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if spoil == "extra":   # a gate list that is not 1, 2 and 4
        record["gates"].append({"gate": 5, "name": "an extra entry", "passed": True, "results": ["not signed"]})
    else:                  # gates 1, 2 and 4, one of them failed
        record["gates"][0]["passed"] = False
    approval.check_draft(record, signed=False)   # the record passes the field checks, so the guard is what refuses
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(AIRefused, match="does not show gates 1, 2 and 4 passed"):
        run(path)
    assert not prompt.exists()


# ---------- the second quick check's findings ----------

def _gate_2_with(more_data, more_pass):
    """Gate 2 on the sample draft, with made-up axioms added to the required modules and triples to its examples."""
    from rdflib import Graph
    dm = drafted.pattern(ROOT)
    spec = drafted.spec_of_form(ANSWERS, ROOT)
    spec, files = drafted.from_answer(SAMPLE_DRAFT.read_text(encoding="utf-8"), spec, ROOT)
    examples = json.loads(files[dm.EXAMPLES])
    examples["pass"] += more_pass
    draft_ = dm.Draft(dict(spec, prefixes=dict(spec["prefixes"], core="https://w3id.org/mpc/ontology/core/",
                                                 proc="https://w3id.org/mpc/ontology/process/")),
                      dict(files, **{dm.EXAMPLES: json.dumps(examples)}))
    data, _ = dm.context(spec, str(ROOT / "business_architecture" / "ontology"))
    data += Graph().parse(data=dm.header(draft_.spec) + more_data, format="turtle")
    return dm.gate_2(draft_, data)


MADE_UP = """sys:hostedOn a owl:ObjectProperty ; owl:inverseOf sys:hosts .
sys:hosts a owl:ObjectProperty .
sys:relatedTo a owl:ObjectProperty, owl:SymmetricProperty .
"""


def test_qc2_1_a_link_back_from_the_release_through_its_own_inverse_or_symmetric_property_is_allowed():
    passed, lines = _gate_2_with(MADE_UP, "ex:inspection-1 sys:hostedOn system:aps-planning-db ;\n"
                                          "    sys:relatedTo system:aps .\n")
    assert passed, lines


def test_qc2_1_a_type_or_sameas_side_effect_through_a_release_property_is_still_refused():
    more = MADE_UP + "sys:hostedOn rdfs:range sys:Systems .\nsys:onlyOne a owl:ObjectProperty, owl:FunctionalProperty .\n"
    passed, lines = _gate_2_with(more, "ex:inspection-1 sys:hostedOn system:aps-planning-db .\n"
                                       "ex:k sys:onlyOne system:aps . ex:k sys:onlyOne system:aps-planning-db .\n")
    assert not passed
    assert any("rdf:type" in line for line in lines) and any("owl:sameAs" in line for line in lines), lines


def test_qc3_3_a_type_or_sameas_side_effect_onto_a_draft_term_is_still_refused():
    """The object of each side effect is a term of the draft, so only the link-back rule's own guard refuses them."""
    more = MADE_UP + f"sys:hostedOn rdfs:range {P}:TankInspection .\nsys:onlyOne a owl:ObjectProperty, owl:FunctionalProperty .\n"
    passed, lines = _gate_2_with(more, "ex:inspection-1 sys:hostedOn system:aps-planning-db .\n"
                                       "ex:k sys:onlyOne system:aps . ex:k sys:onlyOne ex:other .\n")
    assert not passed
    assert any(f"rdf:type {P}:TankInspection" in line for line in lines), lines
    assert any("owl:sameAs ex:other" in line for line in lines), lines


def test_qc2_1_an_example_linked_to_core_and_system_terms_makes_no_false_refusal():
    # core's functional properties, with one value each, as core's own sequences use them
    passed, lines = _gate_2_with("", "ex:sequence-1 core:earlierProcess proc:CM-1-1-4 ;\n"
                                     "    core:laterProcess proc:CM-1-1-3-7-9 .\n")
    assert passed, lines


@pytest.mark.parametrize("more,message", [
    (f'\n{P}:TankInspection rdf:type "http://www.w3.org/2002/07/owl#Class" .\n', "types"),
    ("", 'rdfs:range "http://www.w3.org/2001/XMLSchema#date" is not taken'),   # the schema check, not the one-range one
])
def test_qc2_2_a_literal_is_no_type_and_no_datatype(more, message):
    model = sample()["model"] + more
    if not more:   # the datatype property's one range, written as a literal
        model = model.replace("rdfs:range xsd:date", '"rdfs:range "http://www.w3.org/2001/XMLSchema#date"'[1:])
    with pytest.raises(ChangeRefused, match=message):
        gates_of(sample(model=model))


def test_qc2_3_problems_needs_the_required_modules():
    dm = drafted.pattern(ROOT)
    import inspect
    assert inspect.signature(dm.problems).parameters["data"].default is inspect.Parameter.empty


# ---------- the third quick check's findings ----------

@pytest.mark.parametrize("more_data,more_pass", [
    ("sys:hosts a owl:ObjectProperty .\n", "system:aps-planning-db sys:hosts ex:inspection-1 .\n"),
    ("", "system:aps-planning-db sys:System ex:inspection-1 .\n"),
])
def test_qc3_1_gate_2_refuses_a_triple_about_a_release_term_that_the_draft_asserts(more_data, more_pass):
    passed, lines = _gate_2_with(more_data, more_pass)
    assert not passed and any("would change the release term system:aps-planning-db" in line for line in lines), lines


def test_qc3_1_an_asserted_reflexive_sameas_is_no_change_because_the_release_closure_holds_it():
    """Not a defect: the reasoner gives every term x owl:sameAs x, so the release's closure already holds it."""
    passed, lines = _gate_2_with("", "system:aps-planning-db owl:sameAs system:aps-planning-db .\n")
    assert passed, lines


def test_qc3_2_a_link_back_needs_a_property_the_release_declares():
    passed, lines = _gate_2_with("", "ex:p owl:inverseOf sys:System .\nex:inspection-1 ex:p system:aps-planning-db .\n")
    assert not passed and any("sys:System ex:inspection-1" in line for line in lines), lines


@pytest.mark.parametrize("more_pass", ["system:aps-planning-db sys:hosts ex:inspection-1 .\n",
                                       "ex:p owl:inverseOf sys:System .\nex:inspection-1 ex:p system:aps-planning-db .\n"])
def test_qc3_the_whole_command_refuses_the_reviews_inputs(more_pass):
    examples = dict(sample()["examples"], **{"pass": sample()["examples"]["pass"] + more_pass})
    try:
        found = gates_of(sample(examples=examples))
    except ChangeRefused:
        return   # the form checks refuse it
    assert not found[2]["passed"], found[2]
