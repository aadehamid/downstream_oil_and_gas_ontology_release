"""The domain activation and the process map request: their proposals and their apply (KPI-DEC-0002, Q10 forms 2
and 3, with Q4 to Q7 and Q13; KPI-DEC-0004, item 1).

A domain activation makes a domain of kpi-intake/settings.toml active; a process map request adds new roles and
their RACI entries to the organization module. The check and the propose command read this tree's own pack and
tables, and write proposals into a temporary folder only. The facts, KGCL lines and rows they expect are written by
hand. The apply tests run on a temporary copy of the release; the tree itself is never written.
"""
import csv
import difflib
import json
import shutil
import tomllib
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef

from kpi_store import apply as apply_cmd, cut, propose as propose_cmd
from kpi_store.change import ChangeRefused, approval, domains, kgcl, process_map as pm, proposal
from kpi_store.intake import catalogue, check, picklists
from kpi_store.intake.answers import Intake
from kpi_store.tests import support
from kpi_store.tests.test_propose_apply import NOW, _versions, digest, git, no_global_git, quiet, scratch_release  # noqa: F401

ROOT = support.ROOT
EXAMPLES = ROOT / "kpi-intake" / "examples"
DOMAIN_EXAMPLE = EXAMPLES / "customer.domain-activation.json"
PM_EXAMPLE = EXAMPLES / "sample-pricing-coordinator.process-map-request.json"
DOMAIN_SIGNED = {"domain-owner": {"name": "A Domain Owner", "date": "2026-11-19"},
                 "architect": {"name": "An Architect", "date": "2026-11-19"}}
PM_SIGNED = {"global-process-owner": {"name": "A Global Process Owner", "date": "2026-11-19"},
             "architect": {"name": "An Architect", "date": "2026-11-19"}}
# A domain the tree holds and has not made active: the first one, so the tests hold also on a copy where the
# guide's example has made Customer active. A tree whose domains are all active skips the tests that need one.
TARGET = next((d for d in domains.read(ROOT)[1] if d["active"] is False), None)
SUBJECT = f"domain:{TARGET['id']}" if TARGET else ""
needs_inactive = pytest.mark.skipif(TARGET is None, reason="every domain of kpi-intake/settings.toml is active")
CUSTOMER_TEXT = "A made-up description of the domain, for the tests: the data it covers and the data it leaves to others."
NEW_ROLE = "Sample Terminal Scheduler: A made-up role that coordinates the daily price updates of one region."
PM_ANSWERS = {"P1": ["Sample Terminal Scheduler"], "P5": ["@new-roles"], "P5.detail": NEW_ROLE,
              "P6": ["CM 1.1.2.1, Sample Terminal Scheduler, responsible", "CM 1.1.3, Sample Terminal Scheduler, accountable",
                     "CM 1.1.2.1, Business Analyst, consulted"],
              "P7": ["A made-up regional pricing procedure, 2026-11-19"]}
A1 = "asg:CM-1-1-2-1--responsible--sample-terminal-scheduler--6896e8f0"
A2 = "asg:CM-1-1-3--accountable--sample-terminal-scheduler--6896e8f0"
A3 = f"asg:CM-1-1-2-1--consulted--business-analyst--{pm.digest('Business Analyst')}"
PM_LINES = ["create node role:sample-terminal-scheduler 'Sample Terminal Scheduler'",
            "add definition 'A made-up role that coordinates the daily price updates of one region.' to role:sample-terminal-scheduler",
            f"create edge {A1} orgm:forProcess proc:CM-1-1-2-1",
            f"create edge {A1} orgm:assignedRole role:sample-terminal-scheduler",
            f"create edge {A1} orgm:raciLevel raci:responsible",
            f"create edge {A2} orgm:forProcess proc:CM-1-1-3",
            f"create edge {A2} orgm:assignedRole role:sample-terminal-scheduler",
            f"create edge {A2} orgm:raciLevel raci:accountable",
            f"create edge {A3} orgm:forProcess proc:CM-1-1-2-1",
            f"create edge {A3} orgm:assignedRole role:business-analyst",
            f"create edge {A3} orgm:raciLevel raci:consulted"]
PM_FACTS = [("role:sample-terminal-scheduler", "skos:editorialNote",
             "Added from a process map request. Its sources: A made-up regional pricing procedure, 2026-11-19."),
            (A1, "orgm:sourceRoleText", "Sample Terminal Scheduler"), (A2, "orgm:sourceRoleText", "Sample Terminal Scheduler"),
            (A3, "orgm:sourceRoleText", "Business Analyst")]


def form(folder, kind, answers, sign_offs, name="form", number=""):
    data = {"format": 1, "form": kind, "catalogue_version": "1.2", "kpi_name": name,
            "request": {"number": number} if number else {}, "answers": answers, "sign_offs": sign_offs,
            "consulted": {}, "example_of": "", "comment": ""}
    path = Path(folder) / f"{name}.{kind}.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def domain_form(folder, answers=None, sign_offs=DOMAIN_SIGNED, name="domain", number=""):
    given = json.loads(DOMAIN_EXAMPLE.read_text(encoding="utf-8"))["answers"]
    given.update({"D1": TARGET["label"], "D2": CUSTOMER_TEXT})
    return form(folder, "domain-activation", {**given, **(answers or {})}, sign_offs, name, number)


def pm_form(folder, answers=None, sign_offs=PM_SIGNED, name="request", number=""):
    return form(folder, "process-map-request", {**PM_ANSWERS, **(answers or {})}, sign_offs, name, number)


def propose(tmp_path, path, root=ROOT):
    return propose_cmd.propose([path], tmp_path / "proposals", root, now=NOW, say=quiet)


# ---------- the check's last line ----------

@pytest.mark.parametrize("kind,words", [("domain-activation", "domain activation"),
                                        ("process-map-request", "process map request")])
def test_the_checks_last_line_names_the_propose_command(kind, words):
    cat, data = catalogue.load(ROOT / "kpi-intake"), picklists.load(ROOT / "kpi-intake")
    r = check.check(cat, data, Intake(form=kind, answers={}, sign_offs={}))
    assert r.lines[-1] == (f"This check changes nothing in the ontology. The Architect turns a complete {words} into a "
                           "proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.")
    assert "by hand" not in r.text()


@pytest.mark.parametrize("path", [DOMAIN_EXAMPLE, PM_EXAMPLE])
def test_the_shipped_examples_are_complete_and_signed(path):
    assert check.run(path, ROOT / "kpi-intake").complete


# ---------- the domain activation ----------

HELD = [{"id": "customer", "label": "Customer", "description": "Old.", "active": False},
        {"id": "market-price", "label": "Market Price", "description": "Prices.", "active": True}]


def slug(text):
    return "-".join("".join(c if c.isalnum() else " " for c in text.lower()).split())


def test_the_facts_of_a_domain_activation():
    assert domains.facts_of("customer", "New  text.\n", HELD, slug) == [
        ("domain:customer", "description", "New text."), ("domain:customer", "active", "true")]
    assert domains.facts_of("Customer", "Old.", HELD, slug) == [("domain:customer", "active", "true")]
    assert domains.facts_of("Asset Data", "Equipment.", HELD, slug) == [
        ("domain:asset-data", "label", "Asset Data"), ("domain:asset-data", "description", "Equipment."),
        ("domain:asset-data", "active", "true")]


@pytest.mark.parametrize("name,text,message", [
    ("Market Price", "Prices.", 'the domain "Market Price" is active already'),
    ("", "Anything.", "needs the domain's name"), ("Customer", " ", "what data it covers"),
    ("!!", "Anything.", "has no letter or digit"),
    ("Customer!", "Anything.", None)])
def test_a_domain_activation_that_does_not_fit_is_refused(name, text, message):
    if message is None:   # a name that only matches another domain's short key, not its label
        with pytest.raises(ChangeRefused, match="and another domain of kpi-intake/settings.toml has it"):
            domains.facts_of(name, text, HELD, slug)
        return
    with pytest.raises(ChangeRefused, match=message):
        domains.facts_of(name, text, HELD, slug)


def settings_text(held):
    return "".join(f'[[list.domains]]\nid = "{d["id"]}"\nlabel = "{d["label"]}"\ndescription = "{d["description"]}"\n'
                   f'active = {str(d["active"]).lower()}\n\n' for d in held)


@pytest.mark.parametrize("facts,message", [
    ([("domain:", "label", "X"), ("domain:", "description", "Y"), ("domain:", "active", "true")], "domain:<id>"),
    ([("domain:market-price", "active", "true")], 'the domain "Market Price" is active already'),
    ([("domain:market-price", "description", "Changed.")], "domain:market-price gets no active,true fact"),
    ([("domain:customer", "label", "Client"), ("domain:customer", "active", "true")], "the list holds domain:customer"),
    ([("domain:customer", "description", "A."), ("domain:customer", "description", "B."),
      ("domain:customer", "active", "true")], "domain:customer gets two description facts"),
    ([("domain:customer", "description", "Old."), ("domain:customer", "active", "true")], "has that description already")])
def test_facts_that_no_domain_activation_gives_are_refused(facts, message):
    with pytest.raises(ChangeRefused, match=message):
        domains.edit(settings_text(HELD), facts)


@pytest.mark.parametrize("after", [
    settings_text(HELD) + '[[list.domains]]\nid = "phantom"\n',
    settings_text(HELD).replace('label = "Customer"\n', ""),
    settings_text(HELD).replace('id = "customer"\n', ""),
    settings_text(HELD).replace('label = "Customer"\n', 'label = "Customer"\nextra = "bad"\n'),
    settings_text(HELD) + settings_text(HELD[:1]),
    settings_text(HELD) + '[[list.status]]\nid = "new"\nlabel = "New"\n'])
def test_the_round_trip_of_settings_refuses_a_change_that_no_fact_states(tmp_path, after):
    for name, content in (("before", settings_text(HELD)), ("after", after)):
        (tmp_path / name / "kpi-intake").mkdir(parents=True)
        (tmp_path / name / domains.SETTINGS).write_text(content, encoding="utf-8")
    with pytest.raises(ChangeRefused):
        domains.compare(tmp_path / "before", tmp_path / "after")
    (tmp_path / "after" / domains.SETTINGS).write_text(settings_text(HELD).replace("active = false", "active = true"),
                                                      encoding="utf-8")
    assert domains.compare(tmp_path / "before", tmp_path / "after") == [("domain:customer", "active", "true")]


def test_the_tests_load_when_every_domain_is_active(monkeypatch):
    import importlib.util
    read = domains.read
    monkeypatch.setattr(domains, "read", lambda root: (read(root)[0], [{**d, "active": True} for d in read(root)[1]]))
    spec = importlib.util.spec_from_file_location("all_domains_active", __file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TARGET is None


@needs_inactive
def test_the_edit_of_settings_changes_only_the_domains_lines_and_the_round_trip_gives_the_facts(tmp_path):
    text = (ROOT / domains.SETTINGS).read_text(encoding="utf-8")
    facts = [(SUBJECT, "description", 'A "quoted" text'), (SUBJECT, "active", "true"),
             ("domain:asset-data", "label", "Asset Data"), ("domain:asset-data", "description", "Equipment."),
             ("domain:asset-data", "active", "true")]
    new, wanted = domains.edit(text, facts)
    diff = [line for line in difflib.ndiff(text.split("\n"), new.split("\n")) if line[:1] in "+-"]
    assert sorted(line for line in diff if line[0] == "-") == [
        "- active = false", f"- description = {json.dumps(TARGET['description'], ensure_ascii=False)}"]
    assert sorted(line for line in diff if line[0] == "+") == sorted([
        '+ description = "A \\"quoted\\" text"', "+ active = true", "+ ", "+ [[list.domains]]", '+ id = "asset-data"',
        '+ label = "Asset Data"', '+ description = "Equipment."', "+ active = true"])
    assert tomllib.loads(new)["list"]["domains"] == wanted and wanted[-1]["id"] == "asset-data"
    for name, content in (("before", text), ("after", new)):
        (tmp_path / name / "kpi-intake").mkdir(parents=True)
        (tmp_path / name / domains.SETTINGS).write_text(content, encoding="utf-8")
    assert domains.compare(tmp_path / "before", tmp_path / "after") == sorted(facts)


@needs_inactive
def test_a_settings_file_laid_out_otherwise_and_a_fact_of_another_form_are_refused():
    text = (ROOT / domains.SETTINGS).read_text(encoding="utf-8")
    head = f'id = "{TARGET["id"]}"\nlabel = "{TARGET["label"]}"'
    block = f'{head}\ndescription = {json.dumps(TARGET["description"], ensure_ascii=False)}\nactive = false\n'
    assert head in text and block in text
    inline = text.replace(head, head + " # a comment")
    with pytest.raises(ChangeRefused, match="is not laid out as the release ships it"):
        domains.edit(text.replace(block, block.replace("active = false\n", "")), [(SUBJECT, "active", "true")])
    assert next(d for d in domains.edit(inline, [(SUBJECT, "active", "true")])[1] if d["id"] == TARGET["id"])["active"] is True
    with pytest.raises(ChangeRefused, match="gets active false"):
        domains.edit(text, [(SUBJECT, "active", "false")])
    with pytest.raises(ChangeRefused, match="domain:<id>,<label, description, active>"):
        domains.edit(text, [(SUBJECT, "owner", "Someone")])
    with pytest.raises(ChangeRefused, match="the facts give it no label"):
        domains.edit(text, [("domain:new-one", "active", "true")])


@needs_inactive
def test_propose_turns_a_domain_activation_into_facts_and_no_kgcl_line(tmp_path):
    [folder] = propose(tmp_path, domain_form(tmp_path, number="DA-1"))
    assert folder.name == "DA-1" and (folder / "change.kgcl").read_text(encoding="utf-8") == ""
    assert proposal.read_facts((folder / "facts.csv").read_text(encoding="utf-8"), "DA-1") == [
        (SUBJECT, "description", CUSTOMER_TEXT), (SUBJECT, "active", "true")]
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert record["route"] == "minor" and [s["role"] for s in record["signatures"]] == ["Domain Owner", "Architect"]
    assert record["signatures"][0]["words"] == "The domain is described rightly in this form, and I am its owner."
    summary = (folder / "summary.txt").read_text(encoding="utf-8")
    assert "  - It becomes active, so the KPI form offers it in question 1.5." in summary
    assert "no module of the ontology changes" in summary and "A Domain Owner" not in summary
    read = proposal.read(folder)
    assert read.owner == "Domain Owner" and read.changes == []


def test_propose_refuses_a_domain_that_is_active_already_and_writes_nothing(tmp_path):
    with pytest.raises(propose_cmd.ProposeRefused, match='the domain "Market Price" is active already'):
        propose(tmp_path, domain_form(tmp_path, {"D1": "Market Price"}))
    assert not (tmp_path / "proposals").exists()


@needs_inactive
def test_a_domain_activation_needs_the_domain_owner_and_the_architect(tmp_path):
    with pytest.raises(propose_cmd.ProposeRefused, match="is not complete and signed"):
        propose(tmp_path, domain_form(tmp_path, sign_offs={"architect": DOMAIN_SIGNED["architect"]}))
    [folder] = propose(tmp_path, domain_form(tmp_path))
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    record["signatures"] = [s for s in record["signatures"] if s["role"] != "Domain Owner"]
    (folder / "approval.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ChangeRefused, match="needs the signature of the Domain Owner"):
        proposal.read(folder)


@needs_inactive
@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_domain_activation_goes_from_the_form_to_a_committed_release_and_the_kpi_form_offers_the_domain(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    held = _versions(root)
    cat = catalogue.load(root / "kpi-intake")
    assert next(d for d in cat.fixed_list("settings:domains") if d["id"] == TARGET["id"])["active"] is False
    [folder] = propose(tmp_path, domain_form(tmp_path, number="DA-1"), root)
    said = []
    files = apply_cmd.apply([folder], root, say=said.append, now=NOW)
    assert "No module of the ontology changes: the ontology holds no list of domains." in said
    assert said[-2].startswith(f"Done. The domain {TARGET['label']} is now active, and the KPI form offers it in question 1.5.")
    assert _versions(root) == held and git(root, "status", "--porcelain") == ""
    assert git(root, "log", "-1", "--format=%s").strip() == f"Apply the domain activation DA-1: {TARGET['label']} active"
    assert set(git(root, "show", "--name-only", "--format=", "HEAD").split()) == set(files)
    assert {"kpi-intake/settings.toml", "kpi-intake/kpi-intake-form.html", "business_architecture/ontology/approvals/DA-1.json",
            "business_architecture/ontology/approvals/DA-1.facts.csv"} <= set(files)
    assert not approval.record_path(root, "DA-1").with_suffix(".kgcl").exists()
    entry = next(d for d in catalogue.load(root / "kpi-intake").fixed_list("settings:domains") if d["id"] == TARGET["id"])
    assert entry["active"] is True and entry["description"] == CUSTOMER_TEXT
    assert approval.read_record(approval.record_path(root, "DA-1"), "Domain Owner")["route"] == "minor"
    with pytest.raises(ChangeRefused, match="needs the signature of the Data Owner"):
        approval.read_record(approval.record_path(root, "DA-1"))
    # The pack the release now holds is current, and the KPI form no longer sends a KPI of the domain to a domain
    # activation.
    cut._run("check the pack", [*cut.INTAKE, "--root", str(root), "--check"], root)
    cat, data = catalogue.load(root / "kpi-intake"), picklists.load(root / "kpi-intake")
    kpi = check.check(cat, data, Intake(form="kpi-intake", answers={"1.5": TARGET["id"]}, sign_offs={}))
    assert "Domain activation needed" not in kpi.text()
    before = check.check(catalogue.load(ROOT / "kpi-intake"), picklists.load(ROOT / "kpi-intake"),
                         Intake(form="kpi-intake", answers={"1.5": TARGET["id"]}, sign_offs={}))
    assert "Domain activation needed" in before.text()
    with pytest.raises(ChangeRefused, match="the proposal DA-1 was applied before"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)


@needs_inactive
def test_apply_refuses_a_domain_activation_with_other_changes_and_two_of_one_domain(tmp_path):
    [one] = propose(tmp_path, domain_form(tmp_path, number="DA-1"))
    [two] = propose(tmp_path, domain_form(tmp_path, name="again", number="DA-2"))
    [request] = propose(tmp_path, pm_form(tmp_path, number="PM-1"))
    with pytest.raises(ChangeRefused, match=f"the proposals DA-1 and DA-2 both change the domain {SUBJECT}"):
        apply_cmd.apply([one, two], ROOT, say=quiet)
    with pytest.raises(ChangeRefused, match="these proposals are domain activations and other changes"):
        apply_cmd.apply([one, request], ROOT, say=quiet)


@needs_inactive
def test_a_failing_step_of_a_domain_activation_leaves_the_release_as_it_was(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    [folder] = propose(tmp_path, domain_form(tmp_path), root)
    before = digest(root)

    def fail(name):
        if name == "verify the KPI intake pack":
            raise RuntimeError("made-up failure")
    with pytest.raises(cut.CutFailed, match="the step 'verify the KPI intake pack' failed: RuntimeError: made-up failure"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW, before_step=fail)
    assert digest(root) == before


# ---------- the process map request ----------

def test_the_prefixes_are_the_builders_namespaces():
    text = lambda name: (ROOT / pm.FOLDER / name).read_text(encoding="utf-8")
    for prefix in ("role", "asg", "raci", "orgm"):
        assert f'"{pm.PREFIXES[prefix]}"' in text("build_roles.py") + text("build_assignments.py"), prefix
    assert pm.PREFIXES["proc"] == "https://w3id.org/mpc/ontology/process/"


def test_the_assignment_id_is_the_one_build_assignments_makes():
    import sys
    sys.path.insert(0, str(ROOT / pm.FOLDER))
    try:
        import build_assignments as ba
    finally:
        sys.path.remove(str(ROOT / pm.FOLDER))
    iri = ba.assignment_iri(URIRef(pm.PREFIXES["proc"] + "CM-1-1-2"), "accountable", "trader", "Traders")
    assert pm.curie(iri) == pm.assignment("CM-1-1-2", "accountable", "trader", "Traders")


def test_propose_turns_a_process_map_request_into_kgcl_lines_and_facts(tmp_path):
    [folder] = propose(tmp_path, pm_form(tmp_path, number="PM-1"))
    assert (folder / "change.kgcl").read_text(encoding="utf-8").splitlines() == PM_LINES
    assert proposal.read_facts((folder / "facts.csv").read_text(encoding="utf-8"), "PM-1") == PM_FACTS
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert record["route"] == "minor" and [s["role"] for s in record["signatures"]] == ["Global Process Owner", "Architect"]
    summary = (folder / "summary.txt").read_text(encoding="utf-8")
    assert ('  - A RACI entry: "Sample Terminal Scheduler" is accountable for the process CM 1.1.3 Distribution Planning & Scheduling and Inventory Management.'
            in summary)
    assert proposal.read(folder).owner == "Global Process Owner"
    for line in PM_LINES:   # each line is one the official parser reads and renders back
        assert kgcl.write_line(kgcl.read_line(line)) == line


@pytest.mark.parametrize("answers,message", [
    ({"P1": ["Sample Terminal Scheduler", "A Made-up Area"]}, 'P1 names "A Made-up Area", which is neither a role'),
    ({"P6": ["CM 9.9.9, Sample Terminal Scheduler, responsible"]}, 'P6, line 1: "CM 9.9.9" is neither a process of the process map'),
    ({"P6": ["CM 1.1.2, Sample Terminal Scheduler, owner"]}, '"owner" is not one of responsible'),
    ({"P6": ["CM 1.1.2 Sample Terminal Scheduler responsible"]}, "is not written as"),
    ({"P6": ["CM 1.1.2, A Made-up Role, consulted", "CM 1.1.2, Sample Terminal Scheduler, consulted"]},
     '"A Made-up Role" is neither a role of the organization module nor a new role of P5'),
    ({"P6": ["CM 1.1.2.1, Business Analyst, consulted"]}, "the new role role:sample-terminal-scheduler is in no RACI entry"),
    ({"P5.detail": "Sample Terminal Scheduler coordinates prices"}, "is not a new role written as"),
    ({"P5.detail": "Business Analyst: Analyses.", "P1": ["Business Analyst"]}, "holds that role already"),
    ({"P5.detail": ""}, "To settle: P5 is missing"),
    ({"P1": ["Price-Lead", "Price Lead"], "P5.detail": "Price-Lead: Sets regional prices.\nPrice Lead: Reviews regional prices.",
      "P6": ["CM 1.1.2, Price Lead, consulted"]}, 'P5: "Price Lead" has the short key price-lead, as "Price-Lead" has'),
    ({"P6": ["CM 1.1.2.new, Sample Terminal Scheduler, responsible"]}, '"CM 1.1.2.new" is neither a process of the process map'),
    ({"P6": ["CM 1.1.2a, Sample Terminal Scheduler, responsible"]}, '"CM 1.1.2a" is neither a process of the process map'),
    ({"P6": ["CM 1.1.2 New Pricing Step, Sample Terminal Scheduler, responsible"]}, "is neither a process of the process map"),
    ({"P6": ["CM 1.1.2.1, Business Analyst, responsible"], "P1": ["Business Analyst"], "P5": [], "P5.detail": ""},
     'has "Business Analyst" as responsible already')])
def test_propose_refuses_a_process_map_request_it_cannot_apply_and_writes_nothing(tmp_path, answers, message):
    with pytest.raises(propose_cmd.ProposeRefused, match=message):
        propose(tmp_path, pm_form(tmp_path, answers))
    assert not (tmp_path / "proposals").exists()


@pytest.mark.parametrize("lines,facts,message", [
    (PM_LINES[:1], [], "needs a create node line, an add definition line"),
    (PM_LINES[2:4], PM_FACTS[1:2], "needs exactly one orgm:raciLevel line"),
    (PM_LINES[2:5], [], "needs a orgm:sourceRoleText fact"),
    ([line.replace(A3, A3[:-8] + "00000000") for line in PM_LINES[8:]], [(A3[:-8] + "00000000", "orgm:sourceRoleText",
                                                                          "Business Analyst")], "is not one for"),
    (PM_LINES[8:], PM_FACTS[3:] + [("asg:other", "orgm:sourceRoleText", "x")], "a fact is about an assignment that no line"),
    (["create edge role:x skos:broader role:y"], [], "a process map request adds roles"),
    (PM_LINES + PM_LINES[:1], PM_FACTS, "role:sample-terminal-scheduler has two create node lines"),
    (PM_LINES, PM_FACTS + PM_FACTS[:1], "role:sample-terminal-scheduler has two skos:editorialNote facts"),
    (PM_LINES[8:], PM_FACTS[3:] + [("role:x", "skos:note", "x")], "a process map request's fact is")])
def test_the_lines_of_a_process_map_request_are_refused_unless_complete(lines, facts, message):
    with pytest.raises(ChangeRefused, match=message):
        pm.split([kgcl.read_line(line) for line in lines], facts)


APOSTROPHE_ANSWERS = {"P1": ["Director's Office"], "P5.detail": "Director\u2019s Office: Runs the director\u2019s pricing desk.",
                      "P6": ["CM 1.1.2.1, Director\u2019s Office, consulted", "CM 1.1.3, Director's Office, accountable"]}


def test_a_role_named_with_either_apostrophe_gets_the_text_its_kgcl_line_reads_back(tmp_path):
    [folder] = propose(tmp_path, pm_form(tmp_path, APOSTROPHE_ANSWERS, number="PM-1"))
    changes = kgcl.read_lines((folder / "change.kgcl").read_text(encoding="utf-8"))
    facts = proposal.read_facts((folder / "facts.csv").read_text(encoding="utf-8"), "PM-1")
    assert [c.text for c in changes if c.kind != "create edge"] == ["Director's Office", "Runs the director's pricing desk."]
    assert {v for _, p, v in facts if p == pm.TEXT} == {"Director's Office"}
    tag = pm.digest("Director's Office")
    assert {c.subject for c in changes if c.kind == "create edge"} == {
        f"asg:CM-1-1-2-1--consulted--director-s-office--{tag}", f"asg:CM-1-1-3--accountable--director-s-office--{tag}"}
    pm.check_changes(changes, facts, ROOT)


def test_the_round_trip_refuses_a_new_node_that_states_nothing():
    from rdflib.namespace import DCTERMS, RDF
    source = URIRef(pm.BASE + "source/downstream-process-map")
    for name, prefix, kind in (("roles", "role", URIRef("http://www.w3.org/ns/org#Role")),
                               ("assignments", "asg", URIRef(pm.PREFIXES["orgm"] + "ResponsibilityAssignment"))):
        before = Graph().parse(ROOT / pm.BUILT[name])
        after = Graph() + before
        phantom = URIRef(pm.PREFIXES[prefix] + "phantom")
        after += [(phantom, RDF.type, kind), (phantom, DCTERMS.source, source)]
        with pytest.raises(ChangeRefused, match=f"{phantom} is new, and no line and no fact states it"):
            pm.compare(name, before, after)


@pytest.mark.parametrize("broken", ["settings", "map"])
def test_propose_refuses_a_release_it_cannot_read_in_a_plain_sentence(tmp_path, broken):
    root = scratch_release(tmp_path, git_copy=False)
    if broken == "settings":
        path, make = root / domains.SETTINGS, lambda: domain_form(tmp_path, {"D1": "A Made-up Domain"})
        path.write_text(path.read_text(encoding="utf-8") + "\n[[list.domains]\n", encoding="utf-8")
    else:
        path, make = root / pm.MAP, lambda: pm_form(tmp_path)
        path.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=4) + "\n", encoding="utf-8")
    with pytest.raises(propose_cmd.ProposeRefused, match="settings.toml is not valid TOML|is not laid out as the release ships it"):
        propose(tmp_path, make(), root)
    assert not (tmp_path / "proposals").exists()


def test_a_map_laid_out_otherwise_is_refused(tmp_path):
    root = tmp_path / "release"
    shutil.copytree(ROOT / pm.MAP.parent, root / pm.MAP.parent)
    path = root / pm.MAP
    path.write_text(path.read_text(encoding="utf-8").replace('\n  {\n', '\n  {  \n', 1), encoding="utf-8")
    with pytest.raises(ChangeRefused, match="is not laid out as the release ships it"):
        pm.read_map(root)


def test_the_round_trip_refuses_a_difference_that_no_line_of_a_process_map_request_states():
    before = Graph().parse(ROOT / pm.BUILT["roles"])
    after = Graph() + before
    role = URIRef(pm.PREFIXES["role"] + "business-analyst")
    after.add((role, URIRef(pm.PREFIXES["skos"] + "altLabel"), Literal("BA", lang="en")))
    with pytest.raises(ChangeRefused, match="the graphs differ in 1 ways that no line and no fact of a process map request"):
        pm.compare("roles", before, after)
    assert pm.compare("roles", before, Graph() + before) == ([], [])


def test_the_role_figures_leave_out_what_the_form_added(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / pm.FOLDER))
    try:
        import test_roles as tr
    finally:
        sys.path.remove(str(ROOT / pm.FOLDER))
    (tmp_path / "PM-1.kgcl").write_text("".join(line + "\n" for line in PM_LINES), encoding="utf-8")
    (tmp_path / "PM-1.facts.csv").write_text(proposal.facts_text(PM_FACTS), encoding="utf-8")
    monkeypatch.setattr(tr, "APPROVALS", str(tmp_path))
    names, entries = tr.added_by_forms()
    assert names == {"sample-terminal-scheduler": "Sample Terminal Scheduler"}
    assert entries == {("CM-1-1-2-1", "responsible", "Sample Terminal Scheduler"),
                       ("CM-1-1-3", "accountable", "Sample Terminal Scheduler"),
                       ("CM-1-1-2-1", "consulted", "Business Analyst")}
    entries, register, roles = tr.br.load()
    added = [("CM 1.1.3", "accountable", "Sample Terminal Scheduler")]
    register = register + [{"source_text": "Sample Terminal Scheduler", "roles": "sample-terminal-scheduler",
                            "rule": "exact", "qualifier": ""}]
    roles = roles + [{"slug": "sample-terminal-scheduler", "kind": "position", "replaced_by": ""}]
    assert tr.before_the_forms(entries + added, register, roles) == (entries, register[:-1], roles[:-1])


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_process_map_request_goes_from_the_form_to_a_committed_minor_release_of_organization(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    kept = {name: tmp_path / f"{name}-before.ttl" for name in pm.BUILT}
    for name, path in pm.BUILT.items():
        shutil.copy2(root / path, kept[name])
    held = _versions(root)
    had_raci = "raci" in pm.processes(json.loads((root / pm.MAP).read_text(encoding="utf-8")))["CM 1.1.3"]
    [folder] = propose(tmp_path, pm_form(tmp_path, number="PM-1"), root)
    said = []
    files = apply_cmd.apply([folder], root, say=said.append, now=NOW)
    k = [int(n) for n in held["organization"].split(".")]
    new = f"{k[0]}.{k[1] + 1}.0"
    assert f"  organization {held['organization']} -> {new}" in said
    assert said[-2].startswith(f"Done. organization is now {new} (minor)")
    assert _versions(root)["organization"] == new and git(root, "status", "--porcelain") == ""
    assert git(root, "log", "-1", "--format=%s").strip() == f"Apply the process map request PM-1: organization {new}"
    assert set(git(root, "show", "--name-only", "--no-renames", "--format=", "HEAD").split()) == set(files)
    rows = lambda name: list(csv.DictReader((root / pm.FOLDER / f"{name}.csv").open(encoding="utf-8")))
    assert rows("roles")[-1] == {"slug": "sample-terminal-scheduler", "label": "Sample Terminal Scheduler",
                                 "preferred_label": "", "kind": "position", "replaced_by": "", "replaced_label_kind": "",
                                 "definition": "A made-up role that coordinates the daily price updates of one region.",
                                 "note": PM_FACTS[0][2], "question": ""}
    assert rows("role-register")[-1] == {"source_text": "Sample Terminal Scheduler", "roles": "sample-terminal-scheduler",
                                         "rule": "exact", "qualifier": ""}
    nodes = pm.processes(json.loads((root / pm.MAP).read_text(encoding="utf-8")))
    if not had_raci:   # a process with no RACI gains the four lists, after its description
        assert nodes["CM 1.1.3"]["raci"] == {"responsible": [], "accountable": ["Sample Terminal Scheduler"],
                                             "consulted": [], "informed": []}
        assert list(nodes["CM 1.1.3"]).index("raci") == list(nodes["CM 1.1.3"]).index("description") + 1
    assert nodes["CM 1.1.3"]["raci"]["accountable"][-1] == "Sample Terminal Scheduler"
    assert nodes["CM 1.1.2.1"]["raci"]["responsible"][-1] == "Sample Terminal Scheduler"
    assert nodes["CM 1.1.2.1"]["raci"]["consulted"][-1] == "Business Analyst"
    # The round trip of both built files, and the change file and facts the release keeps.
    back = [pm.compare(name, kept[name], root / path) for name, path in pm.BUILT.items()]
    assert sorted(line for lines, _ in back for line in lines) == sorted(PM_LINES)
    assert sorted(row for _, rows_ in back for row in rows_) == sorted(PM_FACTS)
    assert approval.record_path(root, "PM-1").with_suffix(".kgcl").read_text(encoding="utf-8").splitlines() == PM_LINES
    lists = picklists.load(root / "kpi-intake")
    assert "Sample Terminal Scheduler" in {i["label"] for i in lists["lists"]["roles"]}
    assert picklists.stale_modules(lists, root) == {}


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_role_named_with_an_apostrophe_goes_from_the_form_to_a_committed_release(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    [folder] = propose(tmp_path, pm_form(tmp_path, APOSTROPHE_ANSWERS, number="PM-1"), root)
    apply_cmd.apply([folder], root, say=quiet, now=NOW)
    rows = list(csv.DictReader((root / pm.FOLDER / "role-register.csv").open(encoding="utf-8")))
    assert rows[-1]["source_text"] == "Director's Office" and git(root, "status", "--porcelain") == ""


def test_a_failing_step_of_a_process_map_request_leaves_the_release_as_it_was(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    [folder] = propose(tmp_path, pm_form(tmp_path), root)
    before = digest(root)

    def fail(name):
        if name == "run the organization module's tests":
            raise RuntimeError("made-up failure")
    with pytest.raises(cut.CutFailed, match="the step 'run the organization module's tests' failed"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW, before_step=fail)
    assert digest(root) == before


def test_a_process_map_request_needs_the_global_process_owner(tmp_path):
    with pytest.raises(propose_cmd.ProposeRefused, match="is not complete and signed"):
        propose(tmp_path, pm_form(tmp_path, sign_offs={"architect": PM_SIGNED["architect"]}))
    assert approval.required_roles("minor", owner="Global Process Owner") == ["Global Process Owner", "Architect"]
    assert proposal.owner_of([kgcl.read_line(PM_LINES[0])]) == "Global Process Owner"
    assert proposal.owner_of([], [("domain:customer", "active", "true")]) == "Domain Owner"
    assert proposal.owner_of([kgcl.read_line("create exact synonym 'x' for measure:unit-utilization")]) == "Data Owner"


# ---------- a KPI form with the forms it waits on, in one propose run ----------

BLEND_EXAMPLE = EXAMPLES / "sample-blend-planning.process-map-request.json"
KPI_EXAMPLE = EXAMPLES / "rm-margin-per-barrel.json"
COMMERCIAL = "https://w3id.org/mpc/ontology/modules/core/business-domain/commercial"
# Names of the tests' own, so the tests hold on a copy where the guide's examples were applied.
TEST_PROCESS = "Sample Blend Planning for the Tests"


def blend_request(folder, name=TEST_PROCESS):
    """A process map request that adds a process under CM 1.1, made from the shipped example."""
    answers = dict(json.loads(BLEND_EXAMPLE.read_text(encoding="utf-8"))["answers"],
                   P1=[name], P6=[f"{name}, Business Analyst, accountable"])
    return form(folder, "process-map-request", answers, PM_SIGNED, "blend", "PM-T1")


def waiting_kpi(folder, process=None, domain=None, detail=None):
    """A signed KPI form, made from the shipped example, that names a missing process in 1.2 and a domain in 1.5."""
    data = json.loads(KPI_EXAMPLE.read_text(encoding="utf-8"))
    answers = {k: v for k, v in data["answers"].items() if not k.startswith(("1.3", "5.1"))}
    answers.update({"2.1": "Sample Margin for the Tests", "2.2": "A made-up margin per barrel, for the tests."})
    if process:
        answers.update({"1.1": COMMERCIAL, "1.2": "@not-in-list", "1.2.detail": process})
    if domain:
        answers["1.5"] = domain
    if detail:
        answers["1.5.detail"] = detail
    return form(folder, "kpi-intake", answers, data["sign_offs"], "margin", "KPI-T1")


def release_with_reference(tmp_path):
    """A plain copy of the release, with the reference documents that a core release reads."""
    root = scratch_release(tmp_path, git_copy=False)
    shutil.copytree(ROOT / "business_architecture" / "reference", root / "business_architecture" / "reference")
    return root


def test_a_kpi_form_that_waits_on_a_form_the_run_lacks_is_refused_as_before(tmp_path):
    kpi = waiting_kpi(tmp_path, process=TEST_PROCESS)
    others = [domain_form(tmp_path, number="DA-T1")] if TARGET else []
    with pytest.raises(propose_cmd.ProposeRefused, match="margin.kpi-intake.json is not complete and signed.*1.2 routes "
                                                          "the request: process map request needed"):
        propose_cmd.propose([*others, kpi], tmp_path / "proposals", ROOT, now=NOW, say=quiet)
    assert not (tmp_path / "proposals").exists()


@needs_inactive
def test_a_kpi_form_waits_on_the_domain_activation_of_its_run_and_follows_it(tmp_path):
    root = release_with_reference(tmp_path)
    before = digest(root)
    said = []
    folders = propose_cmd.propose([waiting_kpi(tmp_path, domain=TARGET["id"]), domain_form(tmp_path, number="DA-T1")],
                                  tmp_path / "proposals", root, now=NOW, say=said.append)
    assert [f.name for f in folders] == ["DA-T1", "KPI-T1"]
    summary = (tmp_path / "proposals" / "KPI-T1" / "summary.txt").read_text(encoding="utf-8")
    assert "Apply this proposal after DA-T1: the KPI form names what it adds" in summary
    assert proposal.read(folders[1]).record["after"] == ["DA-T1"]
    order = said.index("Apply these in this order, one run each, as each KPI form names what the forms before it add:")
    assert said[order + 1:order + 3] == [f"  python -m kpi_store.apply {(tmp_path / 'proposals' / n).as_posix()}"
                                         for n in ("DA-T1", "KPI-T1")]
    assert digest(root) == before   # the release itself does not change
    # The KPI cannot be applied before the domain activation: its domain would not be active.
    with pytest.raises(ChangeRefused, match="the proposal KPI-T1 follows DA-T1, which this release has not applied"):
        apply_cmd.apply([folders[1]], root, say=quiet, now=NOW)
    assert digest(root) == before


@needs_inactive
@pytest.mark.parametrize("label", ["Sample Domain for the Tests", None])
def test_a_not_in_the_list_domain_is_read_as_the_domain_its_activation_adds_or_makes_active(tmp_path, label):
    root = release_with_reference(tmp_path)
    name = label or TARGET["label"]   # a new domain, or one the list holds as not active
    activation = domain_form(tmp_path, {"D1": name}, number="DA-T1")
    kpi = waiting_kpi(tmp_path, domain="@not-in-list", detail=name.upper().replace("'", "\u2019"))
    folders = propose_cmd.propose([kpi, activation], tmp_path / "proposals", root, now=NOW, say=quiet)
    assert [f.name for f in folders] == ["DA-T1", "KPI-T1"]


def test_a_kpi_form_with_another_thing_to_settle_is_refused_before_any_form_is_applied(tmp_path):
    kpi = json.loads(waiting_kpi(tmp_path, process=TEST_PROCESS).read_text(encoding="utf-8"))
    kpi["sign_offs"].pop("architect")
    path = form(tmp_path, "kpi-intake", kpi["answers"], kpi["sign_offs"], "margin", "KPI-T1")
    with pytest.raises(propose_cmd.ProposeRefused, match="margin.kpi-intake.json is not complete and signed\\. Run"):
        propose_cmd.propose([blend_request(tmp_path), path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)
    assert not (tmp_path / "proposals").exists()


@pytest.mark.parametrize("label,detail,same", [
    ("CM 1.1.8 Sample Blend Planning", "sample  blend planning", True),
    ("CM 1.1.8 Sample Blend Planning", "Blend Planning", False),
    ("CM 1.1.8 Trader\u2019s Blend", "Trader's Blend", True),
    ("Commercial", "commercial", True)])
def test_a_missing_name_is_compared_in_any_case_and_without_the_process_number(label, detail, same):
    option = {"label": label, **({"level": 3} if label.startswith("CM ") else {})}
    assert (propose_cmd._fold(propose_cmd._plain(option)) == propose_cmd._fold(detail)) is same


@needs_inactive
def test_a_missing_name_that_no_form_of_the_run_adds_is_refused(tmp_path):
    root = release_with_reference(tmp_path)
    kpi = waiting_kpi(tmp_path, domain="@not-in-list", detail="A Domain No Form Adds")
    with pytest.raises(propose_cmd.ProposeRefused, match="margin.kpi-intake.json is not complete and signed even after "
                                                          "DA-T1.*1.5 routes the request: domain activation needed"):
        propose_cmd.propose([domain_form(tmp_path, number="DA-T1"), kpi], tmp_path / "proposals", root, now=NOW, say=quiet)
    assert not (tmp_path / "proposals").exists()


def test_a_kpi_form_names_the_process_its_process_map_request_adds(tmp_path):
    root = release_with_reference(tmp_path)
    before = digest(root)
    lists = picklists.load(root / "kpi-intake")["lists"]
    held = {p["id"] for p in lists["processes"]}
    # With a domain activation too, when the tree has a domain that is not active: it comes first.
    domain = [domain_form(tmp_path, number="DA-T1")] if TARGET else []
    kpi_form = waiting_kpi(tmp_path, process=TEST_PROCESS.upper(), domain=TARGET["id"] if TARGET else None)
    folders = propose_cmd.propose([kpi_form, blend_request(tmp_path), *domain], tmp_path / "proposals", root, now=NOW,
                                  say=quiet)
    first = ["DA-T1"] if TARGET else []
    assert [f.name for f in folders] == ["PM-T1", *first, "KPI-T1"]
    request, kpi = proposal.read(folders[0]), proposal.read(folders[-1])
    assert kpi.record["after"] == [*first, "PM-T1"]
    [made] = [c.subject for c in request.changes if c.kind == "create node" and c.subject.startswith("proc:")]
    assert pm.PREFIXES["proc"] + made.split(":", 1)[1] not in held
    links = [c.target for c in kpi.changes if c.predicate == "kpi:informsProcess"]
    assert links[0] == made   # the name is read in any case, and the answer becomes the new process
    assert f"Apply this proposal after {' and '.join([*first, 'PM-T1'])}" in (folders[-1] / "summary.txt").read_text(encoding="utf-8")
    assert digest(root) == before


@pytest.mark.parametrize("after,ok", [(["DA-T1", "PM-T1"], True), ([], False), ("DA-T1", False), (["../DA-T1"], False)])
def test_the_approval_record_names_the_proposals_it_follows_as_change_ids(after, ok):
    record = {"change": "KPI-T1", "route": "minor", "new_module": False, "after": after,
              "signatures": [{"role": r, "name": "A signer", "date": "2026-11-19", "words": "I approve."}
                             for r in ("Data Owner", "Architect")]}
    if ok:
        assert approval.check(record)["after"] == after
    else:
        with pytest.raises(ChangeRefused):
            approval.check(record)
