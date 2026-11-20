"""A process map request's new processes, steps and business areas, and the core release the apply command makes for
them (KPI-DEC-0002, Q10 form 2, with Q4 to Q7 and Q13; KPI-DEC-0004, item 1).

The check and the propose command read this tree's own pack, map and core, and write proposals into a temporary
folder only. The KGCL lines and facts they expect are written by hand. The apply tests run on a temporary copy of the
release; the tree itself is never written.
"""
import csv
import json
import shutil
import sys
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import SKOS

from kpi_store import apply as apply_cmd, cut, propose as propose_cmd
from kpi_store.change import ChangeRefused, approval, core_release as cr, kgcl, process_map as pm, proposal
from kpi_store.intake import picklists
from kpi_store.tests import support
from kpi_store.tests.test_domain_and_process_map import PM_SIGNED, form
from kpi_store.tests.test_propose_apply import NOW, _versions, digest, git, no_global_git, quiet, scratch_release  # noqa: F401

ROOT = support.ROOT
RELEASE = ROOT / cr.RELEASE
PROC, AREA = cr.PREFIXES["proc"], cr.PREFIXES["area"]
EXAMPLE = ROOT / "kpi-intake" / "examples" / "sample-blend-planning.process-map-request.json"
PURPOSE = "Plan the made-up loads of one made-up terminal for the coming week. It covers the loading plan only."
NEW = {"P1": ["Sample Terminal Planning"], "P2": [PROC + "CM-1-1"], "P3": [PURPOSE],
       "P6": ["Sample Terminal Planning, Business Analyst, accountable"], "P7": ["A made-up terminal manual, 2026-11-20"]}


def numbered(parent_id):
    """The number the propose command gives a new child of a process of this tree: computed here from the map and the
    identity map, so the tests hold on a copy that has gained processes."""
    data, rows = pm.read_map(ROOT)[1], cr.read_identity(ROOT)
    return cr.next_number(pm.processes(data)[parent_id], data, rows)


NUMBER = numbered("CM 1.1")
SLUG = cr.slug_of(NUMBER)
A = f"asg:{SLUG}--accountable--business-analyst--{pm.digest('Business Analyst')}"
LINES = [f"create node proc:{SLUG} 'Sample Terminal Planning'",
         f"add definition 'Plan the made-up loads of one made-up terminal for the coming week.' to proc:{SLUG}",
         f"create edge proc:{SLUG} skos:broader proc:CM-1-1",
         f"create edge proc:{SLUG} core:businessDomain area:commercial",
         f"create edge {A} orgm:forProcess proc:{SLUG}",
         f"create edge {A} orgm:assignedRole role:business-analyst",
         f"create edge {A} orgm:raciLevel raci:accountable"]
FACTS = [(f"proc:{SLUG}", "skos:notation", NUMBER), (f"proc:{SLUG}", "core:taxonomyLevel", "3"),
         (f"proc:{SLUG}", "skos:scopeNote", "It covers the loading plan only."),
         (A, "orgm:sourceRoleText", "Business Analyst")]


def request(folder, answers=None, name="request", number=""):
    return form(folder, "process-map-request", {**NEW, **(answers or {})}, PM_SIGNED, name, number)


def propose(tmp_path, path, root=ROOT):
    return propose_cmd.propose([path], tmp_path / "proposals", root, now=NOW, say=quiet)


def release_module(name):
    sys.path.insert(0, str(RELEASE))
    try:
        return __import__(name)
    finally:
        sys.path.remove(str(RELEASE))


# ---------- the rules the core builders follow ----------

def test_the_prefixes_and_the_sentence_rule_are_the_core_builders():
    first, maps = release_module("build_core_next"), release_module("build_core_2_2")
    assert cr.PREFIXES["area"] == str(first.DOMAIN) and cr.PREFIXES["proc"] == maps.PROC
    assert cr.PREFIXES["core"] == str(maps.CORE)
    for text in ("One sentence.", "First one. Second (with A. Capital). Third.", "No end", "A. b. C d.", "x (y. Z) w. Q."):
        assert cr.split_description(text) == maps.split_description(text), text


def test_a_new_number_skips_the_numbers_any_process_holds():
    data, rows = pm.read_map(ROOT)[1], cr.read_identity(ROOT)
    parent = pm.processes(data)["CM 1.1"]
    held = cr.numbers(data, rows)
    number = cr.next_number(parent, data, rows)
    assert number.startswith("CM 1.1.") and number not in held
    # CM 1.1.7 is a child of the refining branch, not of CM 1.1: the number is still taken.
    assert "CM 1.1.7" in held and int(number.rsplit(".", 1)[1]) > len(parent["children"])
    assert cr.next_number(parent, data, rows, taken={number}) != number


def test_the_builder_is_the_template_with_its_block_filled_and_it_compiles():
    template = (ROOT / cr.TEMPLATE).read_text(encoding="utf-8")
    constants = {"VERSION": "9.9.0", "ISSUED": "2026-11-20", "BASE_VERSION": "9.8.0", "EARLIER_COMMIT": "a" * 40,
                 "SOURCE_COMMIT": "b" * 40, "APPROVAL": ("approvals/X.json", "Approved."), "DECISIONS": ["approvals/X.json"],
                 "APPROVED_NODE": {"CM 1.1.9": ({"id": "CM 1.1.9", "level": 3, "name": "N"}, "CM-1-1", "commercial")},
                 "APPROVED_AREAS": {"new-area": ("New Area", "A made-up area.")}}
    text = cr.builder_text(template, constants, "Build core 9.9.0.\n")
    assert text.startswith('"""Build core 9.9.0.\n"""') and "FILL IN" in text
    assert "VERSION = '9.9.0'\n" in text and 'VERSION, ISSUED = "X.Y.Z"' not in text
    assert text.split("# --- FILL IN", 1)[1].split("\n# ----", 1)[1] == template.split("# --- FILL IN", 1)[1].split("\n# ----", 1)[1]
    with pytest.raises(ChangeRefused, match="is not laid out as the release ships it"):
        cr.builder_text(template.replace("# --- FILL IN", "# FILL IN"), constants, "x")
    with pytest.raises(ChangeRefused, match="the core builder does not compile"):
        cr.builder_text(template + "\ndef broken(:\n", constants, "x")


@pytest.mark.parametrize("lines,facts,message", [
    (LINES[:1], [], "has no definition"),
    (LINES[:4], FACTS[:1], "has no core:taxonomyLevel"),
    (LINES[:4], [(f"proc:{SLUG}", "skos:notation", "CM 1.1.99"), FACTS[1]], "is not one whose slug is"),
    (LINES[:4], [FACTS[0], (f"proc:{SLUG}", "core:taxonomyLevel", "three")], "is not a number"),
    (LINES[:4], FACTS[:2] + [(f"proc:{SLUG}", "skos:scopeNote", "lower case rest.")],
     "its definition must be one sentence and its scope note the rest"),
    (LINES[:4], FACTS[:3] + [(f"proc:{SLUG}", "skos:note", "x")], "a new process's facts are"),
    (["create node area:x 'X'"], [], "needs a create node line and an add definition line"),
    (LINES[:4] + [f"create edge proc:{SLUG} skos:broader proc:CM-1-2"], FACTS[:3], "a new process or step takes")])
def test_the_lines_of_a_new_process_are_refused_unless_complete(lines, facts, message):
    with pytest.raises(ChangeRefused, match=message):
        cr.split([kgcl.read_line(line) for line in lines], facts)


def changed(parent="CM-1-1", number=None, level=3, area="commercial", name="Sample Terminal Planning"):
    lines, facts = cr.node_changes(number or NUMBER, level, name, PURPOSE, parent, area)
    return lines, facts


@pytest.mark.parametrize("parts,message", [
    (dict(parent="L0-downstream-operations", number="X 1", level=1), "is not a process of the process map with a number"),
    (dict(number="CM 1.1.1"), "is a process of the process map already"),
    (dict(number="CM 1.2.99"), "is not one of a child of CM 1.1"),
    (dict(level=4), "is at level 4, and a child of CM 1.1 is at level 3"),
    (dict(area="no-such-area"), "is neither a business area of core"),
    (dict(name="Demand Forecasting"), 'has a process named "Demand Forecasting" already')])
def test_a_new_process_that_does_not_fit_the_map_is_refused(parts, message):
    lines, facts = changed(**parts)
    with pytest.raises(ChangeRefused, match=message):
        cr.check_changes(lines, facts, ROOT)


def test_a_step_below_the_sixth_level_is_refused():
    data = pm.read_map(ROOT)[1]
    deepest = next(n for n in pm.processes(data).values() if n["level"] == 6)
    rows = {r["skos_notation"]: r["slug"] for r in cr.read_identity(ROOT) if r.get("skos_notation")}
    number = cr.next_number(deepest, data, cr.read_identity(ROOT))
    lines, facts = cr.node_changes(number, 7, "Too Deep", PURPOSE, rows[deepest["id"]], "commercial")
    with pytest.raises(ChangeRefused, match="the map has 6 levels"):
        cr.check_changes(lines, facts, ROOT)


def test_the_round_trip_refuses_a_difference_that_no_line_states_and_leaves_out_the_header():
    before = Graph() + cr.core_graph(ROOT)[1]
    after = Graph() + before
    header = URIRef(cr.PREFIXES["core"][:-1])
    from rdflib.namespace import OWL
    after.set((header, OWL.versionInfo, Literal("9.9.9")))
    assert cr.compare(before, after) == ([], [])
    after.add((URIRef(PROC + "CM-1-1"), SKOS.altLabel, Literal("A made-up name", lang="en")))
    with pytest.raises(ChangeRefused, match="core differs in 1 ways that no line and no fact of a process map request states"):
        cr.compare(before, after)


# ---------- the propose command ----------

def test_propose_turns_a_new_process_and_its_raci_into_kgcl_lines_and_facts(tmp_path):
    [folder] = propose(tmp_path, request(tmp_path, number="PM-9"))
    assert (folder / "change.kgcl").read_text(encoding="utf-8").splitlines() == LINES
    assert proposal.read_facts((folder / "facts.csv").read_text(encoding="utf-8"), "PM-9") == FACTS
    summary = (folder / "summary.txt").read_text(encoding="utf-8")
    assert (f"  - A new process, {NUMBER} Sample Terminal Planning (proc:{SLUG}), at level 3, under CM 1.1 Planning & "
            "Scheduling, in the business area Commercial.") in summary
    assert proposal.read(folder).owner == "Global Process Owner"
    for line in LINES:
        assert kgcl.write_line(kgcl.read_line(line)) == line


def test_propose_adds_a_business_area_and_a_process_in_it(tmp_path):
    answers = {"P1": ["Sample Area", "Sample Terminal Planning"], "P2": ["@business-area", PROC + "CM-1-1"],
               "P3": ["A made-up business area of the tests.", PURPOSE], "P8": "@new-area"}
    [folder] = propose(tmp_path, request(tmp_path, answers))
    lines = (folder / "change.kgcl").read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["create node area:sample-area 'Sample Area'",
                         "add definition 'A made-up business area of the tests.' to area:sample-area"]
    assert f"create edge proc:{SLUG} core:businessDomain area:sample-area" in lines


@pytest.mark.parametrize("answers,message", [
    ({"P2": [PROC + "CM-1"]}, "whose processes belong to .* business areas. Say in P8 which one it belongs to"),
    ({"P3": [""]}, 'P3 gives no purpose for "Sample Terminal Planning"'),
    ({"P2": [PROC + "CM-1-1-1-1-1-9"]}, "is not complete and signed"),   # the check finds a place no list holds
    ({"P2": []}, 'P1 names "Sample Terminal Planning", which is neither a role .* Say in P2 where it goes'),
    ({"P2": ["@role"]}, 'P2 says "Sample Terminal Planning" is a new role, and P5 does not describe it'),
    ({"P8": "@new-area"}, "P8 names the new business area of this request, and the request adds 0"),
    ({"P2": [PROC + "L0-downstream-operations"], "P8": AREA + "commercial"}, "has no number in the process map"),
    ({"P1": ["Commercial"], "P2": ["@business-area"], "P3": ["A made-up area."], "P6": []},
     "core holds that business area already"),
    ({"P6": ["Sample Terminal Planning, Business Analyst, consulted"]}, "would have RACI entries and no accountable role")])
def test_propose_refuses_a_new_item_it_cannot_place_and_writes_nothing(tmp_path, answers, message):
    with pytest.raises(propose_cmd.ProposeRefused, match=message):
        propose(tmp_path, request(tmp_path, answers))
    assert not (tmp_path / "proposals").exists()


def test_a_place_the_process_list_does_not_hold_is_refused():
    lists = picklists.load(ROOT / "kpi-intake")["lists"]
    data = pm.read_map(ROOT)[1]
    with pytest.raises(propose_cmd.ProposeRefused, match='P2: the place of "X" is not a process of the process map'):
        propose_cmd._new_items({"P1": ["X"], "P2": [AREA + "commercial"], "P3": ["A made-up purpose."]}, lists, {},
                               pm.slugs(ROOT), data, cr.read_identity(ROOT))


def test_the_steps_of_p4_stay_in_the_forms_file(tmp_path):
    [folder] = propose(tmp_path, request(tmp_path, {"P4": ["A made-up step"]}))
    assert "For the Architect: P4 stays in the form's file." in (folder / "summary.txt").read_text(encoding="utf-8")


def test_the_shipped_example_is_complete_and_signed():
    from kpi_store.intake import check
    assert check.run(EXAMPLE, ROOT / "kpi-intake").complete


# ---------- the apply command ----------

@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_new_process_goes_from_the_form_to_a_core_release_and_a_step_under_it_to_the_next(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    # The apply verifies every module's source Turtle that reads core; the apqc list's builder reads a workbook too.
    shutil.copytree(ROOT / "business_architecture" / "reference", root / "business_architecture" / "reference")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "The reference documents the apqc list reads")
    held = _versions(root)
    k = [int(n) for n in held["core"].split(".")]
    new = f"{k[0]}.{k[1] + 1}.0"
    builder = f"build_core_{k[0]}_{k[1] + 1}"
    before = tmp_path / "core-before.ttl"
    shutil.copy2(root / cut.ONTOLOGY / "releases" / "core" / held["core"] / "core.ttl", before)
    [folder] = propose(tmp_path, request(tmp_path, number="PM-9"), root)
    said = []
    files = apply_cmd.apply([folder], root, say=said.append, now=NOW)
    assert f"  core {held['core']} -> {new}" in said
    assert said[-2].startswith(f"Done. core is now {new} and organization ")
    assert git(root, "status", "--porcelain") == ""
    assert git(root, "log", "-1", "--format=%s").strip().startswith(f"Apply the process map request PM-9: core {new}, organization ")
    assert set(git(root, "show", "--name-only", "--no-renames", "--format=", "HEAD").split()) == set(files)
    after = _versions(root)
    assert after["core"] == new and all(after[m] != held[m] for m in after)   # every module took a new version
    release = root / cr.RELEASE
    assert (release / f"{builder}.py").is_file() and cut._run("verify", [f"{builder}.py", "--verify"], release)
    assert (root / cr.CHANGELOGS / f"CHANGELOG-{new}.md").read_text(encoding="utf-8").count("Sample Terminal Planning") == 1
    assert (root / cut.ONTOLOGY / "releases" / "previous" / "core" / held["core"]).is_dir()
    # The map, the identity map and the frozen copy.
    text, data = pm.read_map(root)
    node = pm.processes(data)[NUMBER]
    assert node["name"] == "Sample Terminal Planning" and node["description"] == PURPOSE and node["level"] == 3
    assert node["raci"]["accountable"] == ["Business Analyst"]
    row = next(r for r in cr.read_identity(root) if r["skos_notation"] == NUMBER)
    assert row == {"uri": PROC + SLUG, "slug": SLUG, "level": 3, "name": "Sample Terminal Planning",
                   "skos_notation": NUMBER, "parent_slug": "CM-1-1", "minted": False, "proposed_repo_id": NUMBER,
                   "deprecated": False}
    # The frozen map is the map core was built from: the RACI entries came after it, and core does not read them.
    source = cr.newest_builder(root)[1]
    frozen = (root / cr.FROZEN / f"{source[:12]}-downstream_process_map.json").read_text(encoding="utf-8")
    import hashlib
    assert source == hashlib.sha256(frozen.encode()).hexdigest()[:40]

    def without_raci(node):
        if isinstance(node, dict):
            return {k: without_raci(v) for k, v in node.items() if k != "raci"}
        return [without_raci(v) for v in node] if isinstance(node, list) else node
    assert without_raci(json.loads(frozen)) == without_raci(data) and json.loads(frozen) != data
    # The round trip of core, the KPI form's list, and the approval record and change file the release keeps.
    lines, facts = cr.compare(before, root / cut.ONTOLOGY / "releases" / "core" / new / "core.ttl")
    assert lines == sorted(LINES[:4]) and facts == sorted(FACTS[:3])
    lists = picklists.load(root / "kpi-intake")
    entry = next(p for p in lists["lists"]["processes"] if p["id"] == PROC + SLUG)
    assert entry["areas"] == [AREA + "commercial"] and picklists.stale_modules(lists, root) == {}
    assert approval.record_path(root, "PM-9").with_suffix(".kgcl").read_text(encoding="utf-8").splitlines() == LINES

    # A step under the new process, on the release the first apply left: the next core, built on the generated one.
    step = {"P1": ["Sample Terminal Loading"], "P2": [PROC + SLUG], "P3": ["Load the made-up trucks of the made-up plan."],
            "P6": [], "P7": ["The same made-up manual"]}
    [folder] = propose(tmp_path, request(tmp_path, step, name="step", number="PM-10"), root)
    lines = (folder / "change.kgcl").read_text(encoding="utf-8").splitlines()
    assert lines[2:] == [f"create edge proc:{SLUG}-1 skos:broader proc:{SLUG}",
                         f"create edge proc:{SLUG}-1 core:businessDomain area:commercial"]
    apply_cmd.apply([folder], root, say=quiet, now=NOW)
    assert _versions(root)["core"] == f"{k[0]}.{k[1] + 2}.0" and git(root, "status", "--porcelain") == ""
    assert pm.processes(pm.read_map(root)[1])[f"{NUMBER}.1"]["level"] == 4
    assert cr.newest_builder(root)[0] == f"build_core_{k[0]}_{k[1] + 2}"


def test_a_failing_step_of_a_core_release_leaves_the_release_as_it_was(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    [folder] = propose(tmp_path, request(tmp_path), root)
    before = digest(root)

    def fail(name):
        if name == "run the competency questions":
            raise RuntimeError("made-up failure")
    with pytest.raises(cut.CutFailed, match="the step 'run the competency questions' failed: RuntimeError: made-up failure"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW, before_step=fail)
    assert digest(root) == before


def test_apply_refuses_a_core_proposal_whose_lines_do_not_fit(tmp_path):
    folder = tmp_path / "PM-1"
    folder.mkdir()
    lines, facts = changed(number="CM 1.1.1")
    (folder / "change.kgcl").write_text(kgcl.write_lines(lines), encoding="utf-8")
    (folder / "facts.csv").write_text(proposal.facts_text(facts), encoding="utf-8")
    record = {"change": "PM-1", "route": "minor", "new_module": False, "signatures": [
        {"role": "Global Process Owner", "name": "G", "date": "2026-11-20", "words": "Right."},
        {"role": "Architect", "name": "A", "date": "2026-11-20", "words": "Approved."}]}
    (folder / "approval.json").write_text(json.dumps(record), encoding="utf-8")
    root = scratch_release(tmp_path, git_copy=False)
    before = digest(root)
    with pytest.raises((ChangeRefused, cut.CutFailed), match="is a process of the process map already"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)
    assert digest(root) == before


# ---------- what the first review found ----------

def _new_proc(after, slug="CM-1-1-99", provenance=("Added in core 9.9.0.",)):
    """The triples a core builder writes for a new process, into the Graph `after`."""
    from rdflib.namespace import DCTERMS, RDF, XSD
    s = URIRef(PROC + slug)
    for p, o in ((RDF.type, SKOS.Concept), (SKOS.inScheme, URIRef(cr.PREFIXES["core"][:-1])),
                 (SKOS.prefLabel, Literal("Made-up Process", lang="en")), (SKOS.definition, Literal("Made up.", lang="en")),
                 (SKOS.broader, URIRef(PROC + "CM-1-1")), (URIRef(cr.PREFIXES["core"] + "businessDomain"), URIRef(AREA + "commercial")),
                 (SKOS.notation, Literal("CM 1.1.99")), (URIRef(cr.PREFIXES["core"] + "taxonomyLevel"), Literal(3, datatype=XSD.integer))):
        after.add((s, p, o))
    for text in provenance:
        after.add((s, DCTERMS.provenance, text if isinstance(text, Literal) else Literal(text, lang="en")))
    return after


def test_the_round_trip_refuses_a_new_concept_that_no_line_makes_whole():
    from rdflib.namespace import DCTERMS, RDF
    before = Graph() + cr.core_graph(ROOT)[1]
    areas, scheme = URIRef(cr.PREFIXES["core"] + "BusinessDomain"), URIRef(cr.PREFIXES["core"][:-1])
    lines, facts = cr.compare(before, _new_proc(Graph() + before))   # a whole new process passes
    assert len(lines) == 4 and len(facts) == 2

    def ghost(subject, in_scheme):
        s = URIRef(subject)
        return [(s, RDF.type, SKOS.Concept), (s, SKOS.inScheme, in_scheme), (s, DCTERMS.provenance, Literal("x", lang="en"))]
    for extra in ([(areas, SKOS.hasTopConcept, URIRef(AREA + "ghost"))], ghost(PROC + "Ghost", scheme),
                  ghost(cr.PREFIXES["core"] + "Ghost", areas)):
        after = Graph() + before
        for t in extra:
            after.add(t)
        with pytest.raises(ChangeRefused, match="core differs in"):
            cr.compare(before, after)
    for provenance in (("Added in core 9.9.0.", "A second provenance."), (Literal("Added in core 9.9.0."),)):
        with pytest.raises(ChangeRefused, match="core differs in"):
            cr.compare(before, _new_proc(Graph() + before, provenance=provenance))


def test_two_lines_that_name_or_define_one_new_item_twice_are_refused():
    for second in ("create node area:x 'Y'", "add definition 'Two.' to area:x"):
        with pytest.raises(ChangeRefused, match="a new business area takes create node and add definition"):
            cr.split([kgcl.read_line(line) for line in ("create node area:x 'X'", "add definition 'One.' to area:x", second)], [])


def test_a_request_that_adds_a_core_item_is_applied_in_a_run_of_its_own(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    raci = {"P1": ["Business Analyst"], "P2": [], "P3": [], "P6": ["CM 1.1.1, Business Analyst, accountable"]}
    [first] = propose(tmp_path, request(tmp_path, raci, name="raci", number="PM-8"), root)
    [second] = propose(tmp_path, request(tmp_path, number="PM-9"), root)
    with pytest.raises(ChangeRefused, match="A process map request that adds a process, a step or a business area is "
                                            "applied in a run of its own"):
        apply_cmd.plan([first, second], root)


def test_two_new_processes_of_one_name_in_one_request_are_refused(tmp_path):
    answers = {"P1": ["Quality Check", "Quality Check", "Blend Check"], "P2": [PROC + "CM-1-1", PROC + "CM-1-2", PROC + "CM-1-1"],
               "P3": ["Check the made-up blends.", "Check the made-up schedules.", "Check the made-up plans."],
               "P8": AREA + "commercial", "P6": ["Quality Check, Business Analyst, accountable"]}
    with pytest.raises(propose_cmd.ProposeRefused, match='P1 names "Quality Check" twice'):
        propose(tmp_path, request(tmp_path, answers))
