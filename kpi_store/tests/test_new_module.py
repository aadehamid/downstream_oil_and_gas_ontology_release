"""The new-module form and its two patterns, a vocabulary and a reference table, through the check, the propose command
and the apply command (KPI-DEC-0002, Q4, Q10 form 6 and Q11; KPI-DEC-0004, item 1).

The check and the propose command read this tree's own pack and packages, and write proposals into a temporary folder
only. The KGCL lines and facts they expect are written by hand from the shipped examples. The apply tests run on a
temporary copy of the whole release; the tree itself is never written.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import SKOS

from kpi_store import apply as apply_cmd, cut, propose as propose_cmd
from kpi_store.change import ChangeRefused, approval, new_module as nm, proposal
from kpi_store.intake import catalogue, check, picklists
from kpi_store.tests import support
from kpi_store.tests.test_propose_apply import NOW, git, no_global_git, quiet  # noqa: F401

ROOT = support.ROOT
EXAMPLES = ROOT / "kpi-intake" / "examples"
VOCABULARY = EXAMPLES / "sample-equipment-terms.new-module.json"
TABLE = EXAMPLES / "sample-products.new-module.json"
PARTY = "https://w3id.org/mpc/ontology/modules/party/"
SIGNED = {"data-owner": {"name": "A Data Owner", "date": "2026-11-20"},
          "ontology-owner": {"name": "An Ontology Owner", "date": "2026-11-20"},
          "architect": {"name": "An Architect", "date": "2026-11-20"}}
TERM_LINES = [
    "create node term:rotating-equipment 'Rotating equipment'",
    "add definition 'Made-up equipment whose main part turns while it works.' to term:rotating-equipment",
    "create node term:pump 'Pump'",
    "add definition 'Made-up rotating equipment that moves a liquid through a pipe.' to term:pump",
    "create exact synonym 'pump unit' for term:pump",
    "create edge term:pump skos:broader term:rotating-equipment",
    "create node term:compressor 'Compressor'",
    "add definition 'Made-up rotating equipment that raises the pressure of a gas.' to term:compressor",
    "create exact synonym 'gas compressor' for term:compressor",
    "create edge term:compressor skos:broader term:rotating-equipment",
    "create node term:static-equipment 'Static equipment'",
    "add definition 'Made-up equipment that has no main part that moves while it works.' to term:static-equipment",
    "create exact synonym 'fixed equipment' for term:static-equipment",
    "create node term:heat-exchanger 'Heat exchanger'",
    "add definition 'Made-up static equipment that moves heat from one fluid to another.' to term:heat-exchanger",
    "create exact synonym 'exchanger' for term:heat-exchanger",
    "create exact synonym 'HX' for term:heat-exchanger",
    "create edge term:heat-exchanger skos:broader term:static-equipment"]
TERM_FACTS = [
    ("module:sample-equipment-terms", "pattern", "vocabulary"),
    ("module:sample-equipment-terms", "title", "Sample Equipment Terms"),
    ("module:sample-equipment-terms", "description",
     "The made-up terms that the maintenance planners of a made-up refinery use for its equipment."),
    ("module:sample-equipment-terms", "source", "A made-up equipment glossary, 2026-11-20")]
ITEM_LINES = [
    "create node item:sample-marine-diesel 'Sample Marine Diesel'",
    "create edge item:sample-marine-diesel rdf:type party:Product",
    "add definition 'A made-up marine diesel fuel that the made-up terminal sells to ships.' to item:sample-marine-diesel",
    "create edge item:sample-marine-diesel skos:inScheme party:product",
    "create node item:sample-bunker-blend 'Sample Bunker Blend'",
    "create edge item:sample-bunker-blend rdf:type party:Product",
    "add definition 'A made-up blend of residual fuel that the made-up terminal sells to ships.' to item:sample-bunker-blend",
    "create edge item:sample-bunker-blend skos:inScheme party:product"]
ITEM_FACTS = [
    ("module:sample-products", "pattern", "reference-table"),
    ("module:sample-products", "title", "Sample Products"),
    ("module:sample-products", "description",
     "The made-up products that a made-up marine terminal sells, beside the products the party module lists."),
    ("module:sample-products", "source", "A made-up product list of a made-up marine terminal, 2026-11-20"),
    ("module:sample-products", "property", "skos:definition"),
    ("module:sample-products", "property", "skos:inScheme"),
    ("module:sample-products", "property", "party:pidxProductFamily"),
    ("item:sample-marine-diesel", "party:pidxProductFamily", "D"),
    ("item:sample-bunker-blend", "party:pidxProductFamily", "F")]
HAS_EXAMPLES = (ROOT / cut.ONTOLOGY / "sample-equipment-terms").exists() or (ROOT / cut.ONTOLOGY / "sample-products").exists()
needs_fresh = pytest.mark.skipif(HAS_EXAMPLES, reason="this copy holds a module of the guide's examples already")


def answers_of(path):
    return json.loads(path.read_text(encoding="utf-8"))["answers"]


def form(folder, example, answers=None, drop=(), sign_offs=SIGNED, name="module", number=""):
    """A new-module answers file: a shipped example's answers with some replaced or left out."""
    given = {k: v for k, v in answers_of(example).items() if k not in drop}
    data = {"format": 1, "form": "new-module", "catalogue_version": "1.2", "kpi_name": name,
            "request": {"number": number} if number else {}, "answers": {**given, **(answers or {})},
            "sign_offs": sign_offs, "consulted": {}, "example_of": "", "comment": ""}
    path = Path(folder) / f"{name}.new-module.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def report(path):
    pack = ROOT / "kpi-intake"
    return check.run(path, pack)


# ---------- the form and its check ----------

def test_the_catalogue_has_the_new_module_form_and_the_ontology_owner_signs_it_always():
    cat = catalogue.load(ROOT / "kpi-intake")
    assert catalogue.FORMS["new-module"] == "New module"
    assert [q["id"] for q in cat.questions_of("new-module")] == [f"N{i}" for i in range(1, 13)]
    signers = {s["id"]: s for s in cat.signers("new-module")}
    assert sorted(signers) == ["architect", "data-owner", "ontology-owner"]
    assert cat.is_needed(signers["ontology-owner"], "new-module", {})
    assert not cat.is_needed(signers["ontology-owner"], "term-change", {"T8": "yes"})


@needs_fresh
@pytest.mark.parametrize("example", [VOCABULARY, TABLE])
def test_each_shipped_example_is_complete_and_signed(example):
    assert report(example).complete, report(example).lines


def test_a_module_without_the_ontology_owners_signature_is_not_complete(tmp_path):
    signed = {k: v for k, v in SIGNED.items() if k != "ontology-owner"}
    found = report(form(tmp_path, VOCABULARY, sign_offs=signed))
    assert not found.complete
    assert any("Ontology Owner has not signed" in b for b in found.blocking)


def test_new_modelling_needs_a_specialist(tmp_path):
    found = report(form(tmp_path, VOCABULARY, {"N3": "new-modelling"}))
    assert not found.complete
    assert any("Needs a specialist" in line for line in found.lines)


@pytest.mark.parametrize("answers,message", [
    ({"N1": "Lane"}, 'the ontology has a module with the short key "lane" already'),
    ({"N7": ["", "Rotating equipment", "Valve", "", "Static equipment"]}, 'is under "Valve", which is not a term of N4'),
    ({"N4": ["Rotating equipment", "Pump", "pump", "Static equipment", "Heat exchanger"]}, "has the short key pump"),
])
def test_the_check_refuses_a_vocabulary_that_does_not_reconcile(tmp_path, answers, message):
    found = report(form(tmp_path, VOCABULARY, answers))
    assert not found.complete
    assert any(message in b for b in found.blocking), found.blocking


def test_the_check_refuses_an_item_with_a_value_missing(tmp_path):
    found = report(form(tmp_path, TABLE, {"N11": ["A made-up fuel. | product", "A made-up blend. | product | F"]}))
    assert any('"Sample Marine Diesel" has 2 values, and N9 picks 3' in b for b in found.blocking), found.blocking


def test_the_pick_lists_offer_classes_with_items_outside_ref_mpc_and_their_properties():
    lists = picklists.load(ROOT / "kpi-intake")["lists"]
    classes = {c["id"] for c in lists["classes"]}
    assert PARTY + "Product" in classes
    assert PARTY + "Brand" not in classes          # its items are MPC's own brands, in ref-mpc only
    assert "https://w3id.org/mpc/ontology/modules/system/System" not in classes   # the reference-item form adds systems
    properties = {p["id"]: p for p in lists["properties"]}
    assert properties[PARTY + "pidxProductFamily"]["kind"] == "typed"
    assert properties[str(SKOS.inScheme)]["kind"] == "item"
    assert not any(p["domain"] == str(SKOS.Concept) for p in lists["properties"])


# ---------- propose ----------

def propose(tmp_path, *paths):
    return propose_cmd.propose(paths, out=tmp_path / "proposals", release_root=ROOT, now=NOW, say=quiet)


def read(folder):
    return proposal.read(folder)


@needs_fresh
def test_a_vocabulary_becomes_its_terms_lines_and_the_modules_facts(tmp_path):
    folder, = propose(tmp_path, form(tmp_path, VOCABULARY, number="NM-1"))
    p = read(folder)
    assert (p.lines, p.facts, p.route, p.record["new_module"]) == (TERM_LINES, TERM_FACTS, "major", True)
    assert [s["role"] for s in p.record["signatures"]] == ["Data Owner", "Ontology Owner", "Architect"]
    assert 'The term "Pump" (under "Rotating equipment")' in (folder / "summary.txt").read_text(encoding="utf-8")


@needs_fresh
def test_a_reference_table_becomes_its_items_lines_and_facts(tmp_path):
    folder, = propose(tmp_path, form(tmp_path, TABLE, number="NM-2"))
    p = read(folder)
    assert (p.lines, p.facts, p.route) == (ITEM_LINES, ITEM_FACTS, "major")


@needs_fresh
@pytest.mark.parametrize("answers,message", [
    # A property of another class.
    ({"N9": [str(SKOS.definition), str(SKOS.inScheme), PARTY + "carries"]}, "is a property of data flow, and the items are of product"),
    # A value that names nothing the release holds.
    ({"N11": ["A made-up fuel. | no-such-list | D", "A made-up blend. | product | F"]}, 'the value "no-such-list", which names no'),
    # A value of the wrong datatype is refused by the table's checks, a shape the release holds by the shapes.
    ({"N11": ["A made-up fuel. | product | DD", "A made-up blend. | product | F"]}, "PIDX product family is one capital letter"),
    # A class's own rule that the properties leave unmet: a product is in the product list.
    ({"N9": [str(SKOS.definition)], "N11": ["A made-up fuel.", "A made-up blend."]}, "does not meet the release's shapes"),
])
def test_propose_refuses_a_reference_table_the_release_cannot_take(tmp_path, answers, message):
    with pytest.raises(propose_cmd.ProposeRefused) as refused:
        propose_cmd.propose([form(tmp_path, TABLE, answers)], out=tmp_path / "proposals", release_root=ROOT,
                            pack=ROOT / "kpi-intake", now=NOW, say=quiet)
    assert message in str(refused.value)
    assert not (tmp_path / "proposals").exists()


@needs_fresh
def test_check_changes_refuses_a_line_the_pattern_does_not_take():
    lines = [nm.kgcl.read_line(line) for line in TERM_LINES]
    with pytest.raises(ChangeRefused, match="a vocabulary's lines are about its terms"):
        nm.check_changes(lines + [nm.kgcl.read_line("create edge measure:x skos:broader term:pump")], TERM_FACTS, ROOT)
    with pytest.raises(ChangeRefused, match="a vocabulary takes no property"):
        nm.check_changes(lines, TERM_FACTS + [("term:pump", "skos:notation", "P1")], ROOT)
    cycle = lines + [nm.kgcl.read_line("create edge term:rotating-equipment skos:broader term:pump")]
    with pytest.raises(ChangeRefused, match="comes back to"):
        nm.check_changes(cycle, TERM_FACTS, ROOT)


@needs_fresh
def test_a_class_the_form_does_not_offer_is_refused_with_the_reason():
    lines = [nm.kgcl.read_line(line.replace("party:Product", "sys:System")) for line in ITEM_LINES]
    with pytest.raises(ChangeRefused, match="the reference-item form adds systems"):
        nm.check_changes(lines, ITEM_FACTS, ROOT)


@needs_fresh
def test_the_table_checks_refuse_a_row_that_does_not_reconcile():
    mp = nm.patterns(ROOT)
    spec = {"module": "x", "pattern": "reference-table", "properties": [
        {"iri": "http://purl.org/dc/terms/date", "curie": "dcterms:date", "label": "date", "kind": "typed",
         "datatype": "http://www.w3.org/2001/XMLSchema#date"}], "prefixes": {}, "depends_on": []}
    found = mp.problems(spec, [{"item_id": "a", "name": "A", "dcterms:date": "2026-13-40"},
                               {"item_id": "a", "name": "a", "dcterms:date": "2026-11-20"}])
    assert any("is not a value of the datatype" in f for f in found)
    assert any("the key is used twice" in f for f in found)
    assert any("is used twice" in f and "name" in f for f in found)


# ---------- apply ----------

def full_release(tmp_path):
    """A Git copy of the whole release, as a reader's copy is."""
    root = tmp_path / "release"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".pytest_cache"))
    git(root, "init", "-q", "-b", "work")
    git(root, "config", "user.name", "Sample Runner")
    git(root, "config", "user.email", "runner@example.invalid")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "The release as received")
    return root


@needs_fresh
def test_apply_refuses_a_new_module_without_the_ontology_owner(tmp_path):
    folder, = propose(tmp_path, form(tmp_path, VOCABULARY, number="NM-3"))
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    record["signatures"] = [s for s in record["signatures"] if s["role"] != "Ontology Owner"]
    (folder / "approval.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ChangeRefused, match="a new module needs the signature of the Ontology Owner"):
        apply_cmd.plan([folder], ROOT)


@needs_fresh
def test_apply_takes_one_new_module_a_run(tmp_path):
    one, two = propose(tmp_path, form(tmp_path, VOCABULARY, number="NM-4", name="a"),
                       form(tmp_path, TABLE, number="NM-5", name="b"))
    with pytest.raises(ChangeRefused, match="a new module is applied in a run of its own"):
        apply_cmd.plan([one, two], ROOT)


@needs_fresh
def test_compare_refuses_a_triple_no_line_states(tmp_path):
    root = tmp_path / "release"
    shutil.copytree(ROOT / cut.ONTOLOGY / "release", root / cut.ONTOLOGY / "release",
                    ignore=shutil.ignore_patterns("__pycache__", "frozen"))
    mp = nm.patterns(root)
    spec, rows = nm.split([nm.kgcl.read_line(line) for line in TERM_LINES], TERM_FACTS, ROOT)
    folder = root / cut.ONTOLOGY / spec["module"]
    folder.mkdir()
    (folder / mp.builder_name(spec["module"])).write_text(mp.builder_text(spec, "NM-6"), encoding="utf-8")
    g = mp.build(spec, rows)
    assert nm.compare_graph(g, spec, mp) == (sorted(TERM_LINES), TERM_FACTS)
    g.add((URIRef(mp.item_base(spec) + "pump"), SKOS.note, nm_literal("A note no line states.")))
    with pytest.raises(ChangeRefused, match="1 triples that no line and no fact"):
        nm.compare_graph(g, spec, mp)


def nm_literal(text):
    from rdflib import Literal
    return Literal(text, lang="en")


@needs_fresh
@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
@pytest.mark.parametrize("example,key,lines,output", [
    (VOCABULARY, "sample-equipment-terms", TERM_LINES, "terms.ttl"),
    (TABLE, "sample-products", ITEM_LINES, "items.ttl")])
def test_apply_writes_registers_and_releases_the_module(tmp_path, no_global_git, example, key, lines, output):
    root = full_release(tmp_path)
    folder, = propose_cmd.propose([form(tmp_path, example, number="NM-2026-009")], out=tmp_path / "proposals",
                                  release_root=root, now=NOW, say=quiet)
    said = []
    files = apply_cmd.apply([folder], root, say=said.append, now=NOW)
    assert said[-2].startswith(f"Done. {key} 1.0.0 is a new module (major).")
    assert git(root, "log", "-1", "--format=%s").strip() == f"Apply the new module NM-2026-009: {key} 1.0.0"
    assert git(root, "status", "--porcelain") == ""
    ont = root / cut.ONTOLOGY
    package = Graph().parse(ont / "releases" / key / "1.0.0" / f"{key}.ttl")
    assert nm.compare(root, key)[0] == sorted(lines)
    assert len(package) > len(Graph().parse(ont / key / output))   # the header of the package is added
    manifest = json.loads((ont / "releases" / key / "1.0.0" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["approved_by"]["who"] == "The Ontology Owner"
    assert manifest["approved_by"]["recorded_in"] == "approvals/NM-2026-009.json"
    assert approval.read_record(ont / "approvals" / "NM-2026-009.json")["new_module"] is True
    for place in ("scripts/check.sh", f"{cut.ONTOLOGY.as_posix()}/projection/pipeline.py",
                  f"{cut.ONTOLOGY.as_posix()}/MODULES.md", f"{cut.ONTOLOGY.as_posix()}/competency-questions.md"):
        assert place in files and key in (root / place).read_text(encoding="utf-8")
    # A role names the approver in the graph files; the signer's name stays in the approval record only.
    for path in (ont / "releases" / key / "1.0.0").iterdir():
        assert "A Data Owner" not in path.read_text(encoding="utf-8")
    # The same proposal again is refused: the release holds its approval record and the module.
    with pytest.raises(ChangeRefused):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)
