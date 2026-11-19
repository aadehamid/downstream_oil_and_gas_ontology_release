"""The reference-item form, its proposal and its apply (KPI-DEC-0002, Q10 form 5, with Q4 to Q7 and Q13).

The form adds a new system or a new table (a replica). The check and the propose command read this tree's own KPI
intake pack and tables, and write proposals into a temporary folder only. The KGCL lines, the routes and the table
rows they expect are written by hand. The apply tests run on a temporary copy of the release; the tree itself is
never written.
"""
import csv
import json
import shutil
from pathlib import Path

import pytest
from rdflib import Graph

from kpi_store import apply as apply_cmd, cut, ontology_view as ov, propose as propose_cmd
from kpi_store.change import ChangeRefused, approval, kgcl, proposal, reference_items as ri
from kpi_store.intake import catalogue, check, picklists
from kpi_store.intake.answers import Intake
from kpi_store.tests import support
from kpi_store.tests.test_propose_apply import NOW, SIGNED, _versions, digest, git, no_global_git, quiet, scratch_release  # noqa: F401

ROOT = support.ROOT
BASE = "https://w3id.org/mpc/ontology/"
APPLICATION = BASE + "modules/system/kind/application"
ASSETS = BASE + "source/decision-owner-pricing-assets-2026-10-25"      # names MIPS and Databricks, records the tables
EXCEL = BASE + "source/vendor-microsoft-excel"
MIPS = BASE + "modules/system/system/mips"
SYSTEM_ANSWERS = {"R1": "Acme Scheduler", "R2": "system",
                  "R3": "A made-up application that schedules the made-up work of a made-up refinery.",
                  "R4": ["ACS"], "R5": APPLICATION, "R6": ASSETS, "R7": [EXCEL]}
SYSTEM_LINES = ["create node system:acme-scheduler 'Acme Scheduler'",
                "add definition 'A made-up application that schedules the made-up work of a made-up refinery.' to system:acme-scheduler",
                "create exact synonym 'ACS' for system:acme-scheduler",
                "create edge system:acme-scheduler sys:systemKind kind:application",
                "create edge system:acme-scheduler sys:namedBy src:decision-owner-pricing-assets-2026-10-25",
                "create edge system:acme-scheduler dcterms:source src:decision-owner-pricing-assets-2026-10-25",
                "create edge system:acme-scheduler dcterms:source src:vendor-microsoft-excel"]
TABLE_ANSWERS = {"R1": "synapse_dev.replica_mips.mips_pricecurve", "R2": "table", "R8": MIPS, "R9": ASSETS}
TABLE_LINES = ["create node table:replica-mips-pricecurve 'synapse_dev.replica_mips.mips_pricecurve'",
               "create edge table:replica-mips-pricecurve dp:layer layer:replica",
               "create edge table:replica-mips-pricecurve dp:copiesSystem system:mips",
               "create edge table:replica-mips-pricecurve dcterms:source src:decision-owner-pricing-assets-2026-10-25"]


def item_form(folder, answers, sign_offs=SIGNED, name="item", number=""):
    """A reference-item answers file, written to the folder. Returns its path."""
    data = {"format": 1, "form": "reference-item", "catalogue_version": "1.2", "kpi_name": answers.get("R1", ""),
            "request": {"number": number} if number else {}, "answers": answers, "sign_offs": sign_offs,
            "consulted": {}, "example_of": "", "comment": ""}
    path = Path(folder) / f"{name}.reference-item.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def report(answers, sign_offs=SIGNED, root=ROOT):
    cat, data = catalogue.load(root / "kpi-intake"), picklists.load(root / "kpi-intake")
    return check.check(cat, data, Intake(form="reference-item", answers=answers, sign_offs=sign_offs))


# ---------- the form and its check ----------

def test_the_reference_item_form_is_one_more_form_of_the_pack():
    cat = catalogue.load()
    assert catalogue.FORMS["reference-item"] == "Reference item"
    assert [q["id"] for q in cat.questions_of("reference-item")] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9"]
    assert [o["id"] for o in cat.fixed_list(cat.by_id["R2"]["source"])] == [
        "system", "table", "built-table", "source", "role", "data-product"]
    # The four kinds that need a specialist each route there, and the form adds the other two.
    assert {r["when"]: r["outcome"] for r in cat.by_id["R2"]["route"]} == {
        "built-table": "needs-specialist", "source": "needs-specialist", "role": "needs-specialist",
        "data-product": "needs-specialist"}
    assert cat.outcomes["needs-specialist"]["blocks"] is True
    assert [s["id"] for s in cat.signers("reference-item")] == ["data-owner", "architect"]
    owner = cat.signers("reference-item")[0]
    assert cat.meaning(owner, "reference-item") == "The new item is right as this form describes it: its name, what it is and what it links to."
    # The lists the form picks from: the kinds of system, and the documents the system and the tables cite.
    lists = picklists.load(ROOT / "kpi-intake")["lists"]
    # A guide's worked example may add a kind or a document to a copy of the release, so these are what it holds at least.
    assert {"Application", "Office tool", "Working document"} <= {i["label"] for i in lists["system-kinds"]}
    assert ASSETS in {i["id"] for i in lists["system-sources"]} and EXCEL in {i["id"] for i in lists["system-sources"]}
    assert BASE + "source/downstream-process-map" not in {i["id"] for i in lists["system-sources"]}
    assert ASSETS in {i["id"] for i in lists["table-sources"]}


@pytest.mark.parametrize("kind,reason", [
    ("role", "RACI lists of the process map"), ("source", "the integration module, which gives every source its evidence tier"),
    ("data-product", "portfolio file of the process authority"), ("built-table", "a data product")])
def test_a_kind_that_needs_a_specialist_is_refused_with_its_reason(kind, reason):
    r = report({"R1": "Anything", "R2": kind})
    assert not r.complete
    assert "R2 routes the request: needs a specialist" in r.blocking
    assert reason in r.text() and "Needs a specialist" in r.text()


def test_a_complete_system_and_a_complete_table_pass_the_check():
    for answers in (SYSTEM_ANSWERS, TABLE_ANSWERS):
        r = report(answers)
        assert r.complete, r.blocking
        assert "  The new item fits the ontology." in r.lines
        assert r.lines[-1].startswith("This check changes nothing in the ontology. The Architect turns a complete reference item into a proposal")


@pytest.mark.parametrize("answers,blocking", [
    (dict(SYSTEM_ANSWERS, R1="MIPS"), 'R1: "MIPS" is a name of a system the ontology holds already'),
    (dict(SYSTEM_ANSWERS, R1="Market Information and Pricing System"),
     'R1: "Market Information and Pricing System" is a name of a system the ontology holds already'),
    (dict(SYSTEM_ANSWERS, R1="mips!"), 'R1: the ontology has a system with the short key "mips" already. Give the system a name of its own'),
    (dict(SYSTEM_ANSWERS, R1="--"), 'R1: "--" has no letter or digit to make the short key of the system from'),
    (dict(SYSTEM_ANSWERS, R4=["A;B"]), 'R4: "A;B" holds a semicolon, which the ontology\'s tables use between other names'),
    (dict(SYSTEM_ANSWERS, R4=["Acme Scheduler"]), 'R4: "Acme Scheduler" is the name of the system, so it cannot be an other name too'),
    (dict(SYSTEM_ANSWERS, R3="Two\nlines."), 'R3: "Two\nlines.": the text holds a line break or another control character, and a KGCL line is one line'),
    (dict(TABLE_ANSWERS, R1="replica_mips.pricecurve"), 'R1: "replica_mips.pricecurve" is not a full name of the form catalog.schema.table'),
    (dict(TABLE_ANSWERS, R1="prod.replica_mips.pricecurve"),
     "R1: the ontology holds the sandbox's tables only, whose names start with idp_sbx. or synapse_dev."),
    (dict(TABLE_ANSWERS, R1="synapse_dev.replica_mips.MIPS_CURRENCY"), "R1: the ontology holds the table synapse_dev.replica_mips.MIPS_CURRENCY already"),
    (dict(TABLE_ANSWERS, R1="synapse_dev.other.currency"), 'R1: the ontology has a table with the short key "replica-mips-currency" already'),
])
def test_the_check_refuses_an_item_that_does_not_fit_the_ontology(answers, blocking):
    r = report(answers)
    assert blocking in r.blocking, r.blocking


def test_the_check_asks_a_systems_questions_only_for_a_system_and_both_signatures():
    r = report({**TABLE_ANSWERS, "R3": "A definition a table does not take."})
    assert any(b.startswith("R3 has an answer, but its rule says it is not asked") for b in r.blocking)
    r = report(SYSTEM_ANSWERS, sign_offs={"data-owner": SIGNED["data-owner"]})
    assert not r.complete and any("Architect" in b for b in r.blocking)


# ---------- the KGCL lines of a new item ----------

def test_the_two_new_statement_forms_read_and_write_as_the_official_grammar_does():
    from kgcl_schema.grammar.parser import parse_statement
    from kgcl_schema.grammar.render_operations import render
    for line in SYSTEM_LINES + TABLE_LINES:
        assert kgcl.write_line(kgcl.read_line(line)) == line
        assert render(parse_statement(line)) == line


def test_the_prefixes_are_the_builders_namespaces():
    import importlib.util

    def builder(path):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    bs = builder(ROOT / ri.SYSTEM_FOLDER / "build_systems.py")
    bp = builder(ROOT / ri.KINDS["table"].folder / "build_pricing.py")
    assert (ri.PREFIXES["system"], ri.PREFIXES["kind"], ri.PREFIXES["sys"], ri.PREFIXES["src"]) == \
        (str(bs.SYSTEM), str(bs.KIND), str(bs.SYS), str(bs.SRC))
    assert (ri.PREFIXES["table"], ri.PREFIXES["layer"], ri.PREFIXES["dp"], ri.PREFIXES["system"]) == \
        (str(bp.TABLE), str(bp.LAYER), str(bp.DP), str(bp.SYSTEM))
    assert ri.SANDBOX == ("idp_sbx.", "synapse_dev.")


@pytest.mark.parametrize("lines,message", [
    (SYSTEM_LINES[2:], "a reference item adds new items only, and this line is about an item that no 'create node' line"),
    ([SYSTEM_LINES[0], *SYSTEM_LINES[2:]], "system:acme-scheduler has no definition"),
    (SYSTEM_LINES[:4] + SYSTEM_LINES[5:], "needs exactly one sys:namedBy link, and has 0"),
    (SYSTEM_LINES[:6], None),   # the naming document as the only source is complete
    (SYSTEM_LINES[:5] + SYSTEM_LINES[6:], "the document that names a system is also one of its sources"),
    (SYSTEM_LINES + ["rename system:acme-scheduler from 'Acme Scheduler' to 'Acme'"], "takes a name, a definition, other names and links"),
    (TABLE_LINES + ["add definition 'A table.' to table:replica-mips-pricecurve"], "a table of the reference-item form takes a name and links"),
    ([TABLE_LINES[0], "create edge table:replica-mips-pricecurve dp:layer layer:gold", *TABLE_LINES[2:]], "the form adds a replica only"),
    ([TABLE_LINES[0].replace("synapse_dev.", "prod."), *TABLE_LINES[1:]], "the module holds the sandbox's tables only"),
    (SYSTEM_LINES + TABLE_LINES, "one apply adds items of one kind"),
    (["create exact synonym 'x' for measure:a"], "a reference item is a system (system:<id>) or a table (table:<id>)"),
])
def test_the_lines_of_a_new_item_are_refused_unless_complete(lines, message):
    changes = kgcl.read_lines("\n".join(lines))
    if message is None:
        ri.kind_of(changes)
        return
    with pytest.raises(ChangeRefused, match=message.replace("(", r"\(").replace(")", r"\)")):
        ri.kind_of(changes)


@pytest.mark.parametrize("old,new,message", [
    ("src:vendor-microsoft-excel", "src:a-made-up-document", "src:a-made-up-document is not a document of system/sources.csv. A new source document needs a specialist"),
    ("kind:application", "kind:spreadsheet", "kind:spreadsheet is not a kind of system the system module holds"),
    ("'ACS'", "'MIPS'", "the system mips has the name 'MIPS' already"),
    ("system:mips", "system:a-made-up-system", "system:a-made-up-system is not a system of the system module"),
    ("src:decision-owner-pricing-assets-2026-10-25", "src:dehghani-data-mesh-2019", None),   # in pricing/sources.csv
])
def test_an_item_that_does_not_fit_the_tables_is_refused(old, new, message):
    lines = [line.replace(old, new) for line in (SYSTEM_LINES if "system:mips" not in old else TABLE_LINES)]
    if old.startswith("src:decision"):
        lines = [line.replace(old, new) for line in TABLE_LINES]
    changes = kgcl.read_lines("\n".join(lines))
    if message is None:
        ri.check_changes(changes, ROOT)
        return
    with pytest.raises(ChangeRefused, match=message):
        ri.check_changes(changes, ROOT)


# ---------- propose ----------

@pytest.mark.parametrize("answers,lines,name", [(SYSTEM_ANSWERS, SYSTEM_LINES, "acme-scheduler"),
                                                (TABLE_ANSWERS, TABLE_LINES, "replica-mips-pricecurve")], ids=["system", "table"])
def test_propose_writes_the_kgcl_lines_of_a_new_item_as_a_minor(tmp_path, answers, lines, name):
    said = []
    [folder] = propose_cmd.propose([item_form(tmp_path, answers)], tmp_path / "out", ROOT, now=NOW, say=said.append)
    assert folder == tmp_path / "out" / f"2026-11-19-{name}"
    assert (folder / "change.kgcl").read_text(encoding="utf-8") == "".join(line + "\n" for line in lines)
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert (record["route"], [s["role"] for s in record["signatures"]]) == ("minor", ["Data Owner", "Architect"])
    assert record["signatures"][0]["words"] == "The new item is right as this form describes it: its name, what it is and what it links to."
    summary = (folder / "summary.txt").read_text(encoding="utf-8")
    assert "The route: minor. This is a minor: the changes add content, and the old meaning still holds." in summary
    assert said[0] == f"wrote the proposal {folder.as_posix()}: {len(lines)} changes, route minor"
    read = proposal.read(folder)
    assert (read.lines, read.route) == (lines, "minor")


def test_the_summary_of_a_system_says_what_it_adds_in_plain_words(tmp_path):
    [folder] = propose_cmd.propose([item_form(tmp_path, SYSTEM_ANSWERS, number="RI-2026-001")], tmp_path / "out", ROOT,
                                   now=NOW, say=quiet)
    assert folder.name == "RI-2026-001"
    summary = (folder / "summary.txt").read_text(encoding="utf-8")
    for line in ('The new item: a system, "Acme Scheduler" (system:acme-scheduler), in the system module',
                 '  - A system named "Acme Scheduler".',
                 '  - Its definition: "A made-up application that schedules the made-up work of a made-up refinery."',
                 '  - The other name "ACS".', "  - Its kind: Application.",
                 "  - The document that names it: the subject matter expert's Databricks pricing metric views, their lineage "
                 "and the Genie agents' instructions (idp_sbx sandbox), shared on 2026-10-25 (the decision of 2026-10-25)."):
        assert line in summary.splitlines(), line


def test_propose_refuses_an_item_that_needs_a_specialist_and_writes_nothing(tmp_path):
    with pytest.raises(propose_cmd.ProposeRefused, match="R2 routes the request: needs a specialist"):
        propose_cmd.propose([item_form(tmp_path, {"R1": "Planner", "R2": "role"})], tmp_path / "out", ROOT, now=NOW, say=quiet)
    assert not (tmp_path / "out").exists()


# ---------- apply, end to end, on a scratch copy of the release ----------

def _next(held, module, route):
    k = ov.version_key(held[module])
    return f"{k[0]}.{k[1] + 1}.0" if route == "minor" else f"{k[0]}.{k[1]}.{k[2] + 1}"


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_a_new_system_then_a_table_that_copies_it_go_from_the_form_to_two_committed_minor_releases(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    system_file = root / ri.SYSTEM_FOLDER / "systems.ttl"
    kept = tmp_path / "systems-before.ttl"
    shutil.copy2(system_file, kept)
    held = _versions(root)
    [folder] = propose_cmd.propose([item_form(tmp_path, SYSTEM_ANSWERS, number="RI-1")], tmp_path / "proposals", root,
                                   now=NOW, say=quiet)
    said = []
    files = apply_cmd.apply([folder], root, say=said.append, now=NOW)
    new = _next(held, "system", "minor")
    order = cut._run("list", ["dependents.py", "system"], root / cut.ONTOLOGY / "release").split()
    assert said[0] == "1 proposal to apply:" and f"  system {held['system']} -> {new}" in said
    steps = [line[4:] for line in said if line.startswith("... ")]
    assert steps.index("compare the system module before and after") < steps.index(f"set system to {new}") \
        < steps.index("run the system module's tests") < steps.index("write the release")
    assert said[-2].startswith(f"Done. system is now {new} (minor), and {len(order) - 1} modules that depend on it took a new patch.")
    assert _versions(root)["system"] == new and git(root, "status", "--porcelain") == ""
    assert git(root, "log", "-1", "--format=%s").strip() == f"Apply the reference item RI-1: system {new}"
    assert set(git(root, "show", "--name-only", "--no-renames", "--format=", "HEAD").split()) == set(files)
    # The rows the form added, written by hand.
    rows = lambda name: list(csv.DictReader((root / ri.SYSTEM_FOLDER / f"{name}.csv").open(encoding="utf-8")))
    assert rows("other-systems")[-1] == {"slug": "acme-scheduler", "label": "Acme Scheduler", "alt_labels": "ACS",
                                         "kind": "application", "named_by": "decision-owner-pricing-assets-2026-10-25"}
    assert rows("definitions")[-1] == {"slug": "acme-scheduler", "definition": SYSTEM_ANSWERS["R3"],
                                       "sources": "decision-owner-pricing-assets-2026-10-25;vendor-microsoft-excel", "note": ""}
    # The round trip, and the record and change file the release keeps.
    assert sorted(ri.compare(kept, system_file, "system")) == sorted(SYSTEM_LINES)
    assert approval.read_record(approval.record_path(root, "RI-1"))["route"] == "minor"
    assert approval.record_path(root, "RI-1").with_suffix(".kgcl").read_text(encoding="utf-8").splitlines() == SYSTEM_LINES
    lists = picklists.load(root / "kpi-intake")
    assert "Acme Scheduler" in {i["label"] for i in lists["lists"]["systems"]} and picklists.stale_modules(lists, root) == {}

    # A table that copies the new system, on the release the first apply left.
    held = _versions(root)
    table = dict(TABLE_ANSWERS, R1="synapse_dev.replica_acme.plan", R8=BASE + "modules/system/system/acme-scheduler")
    [folder] = propose_cmd.propose([item_form(tmp_path, table, number="RI-2", name="table")], tmp_path / "proposals", root,
                                   now=NOW, say=quiet)
    assert (folder / "change.kgcl").read_text(encoding="utf-8").splitlines() == [
        "create node table:replica-acme-scheduler-plan 'synapse_dev.replica_acme.plan'",
        "create edge table:replica-acme-scheduler-plan dp:layer layer:replica",
        "create edge table:replica-acme-scheduler-plan dp:copiesSystem system:acme-scheduler",
        "create edge table:replica-acme-scheduler-plan dcterms:source src:decision-owner-pricing-assets-2026-10-25"]
    apply_cmd.apply([folder], root, say=quiet, now=NOW)
    new = _next(held, "data-product", "minor")
    assert _versions(root)["data-product"] == new and git(root, "status", "--porcelain") == ""
    assert git(root, "log", "-1", "--format=%s").strip() == f"Apply the reference item RI-2: data-product {new}"
    tables = list(csv.DictReader((root / cut.PRICING / "tables.csv").open(encoding="utf-8")))
    assert tables[-1] == {"slug": "replica-acme-scheduler-plan", "name": "synapse_dev.replica_acme.plan", "layer": "replica",
                          "copies_system": "acme-scheduler", "kind": "", "classification_test": "",
                          "classification_reason": "", "serves_measures": "", "source": "decision-owner-pricing-assets-2026-10-25"}


def test_a_builder_error_and_a_failing_step_roll_everything_back(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    [folder] = propose_cmd.propose([item_form(tmp_path, SYSTEM_ANSWERS)], tmp_path / "proposals", root, now=NOW, say=quiet)
    before = digest(root)

    def fail_at_the_tests(name):
        if name == "run the system module's tests":
            raise RuntimeError("made-up failure")
    with pytest.raises(cut.CutFailed, match="the step 'run the system module's tests' failed: RuntimeError: made-up failure. The release is as it was."):
        apply_cmd.apply([folder], root, say=quiet, now=NOW, before_step=fail_at_the_tests)
    assert digest(root) == before

    (root / ri.SYSTEM_FOLDER / "build_systems.py").write_text('import sys\nsys.exit("made-up builder failure")\n', encoding="utf-8")
    before = digest(root)
    with pytest.raises(cut.CutFailed, match="(?s)the system builder refused the changed tables.*made-up builder failure"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW)
    assert digest(root) == before
    assert not approval.record_path(root, folder.name).exists()


def _write(folder, lines, change=None):
    folder.mkdir(parents=True)
    (folder / "change.kgcl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    record = {"change": change or folder.name, "route": "minor", "new_module": False, "signatures": [
        {"role": "Data Owner", "name": "A Data Owner", "date": "2026-11-19", "words": "Right."},
        {"role": "Architect", "name": "An Architect", "date": "2026-11-19", "words": "Approved."}]}
    (folder / "approval.json").write_text(json.dumps(record), encoding="utf-8")
    return folder


def test_apply_refuses_two_modules_and_two_proposals_that_add_the_same_item(tmp_path):
    term = _write(tmp_path / "term", ["create exact synonym 'a made-up other name' for measure:unit-utilization"])
    one, two = _write(tmp_path / "one", SYSTEM_LINES), _write(tmp_path / "two", SYSTEM_LINES)
    table = _write(tmp_path / "table", TABLE_LINES)
    for folders, message in (([term, one], "these proposals change two modules"),
                             ([one, table], "one apply adds items of one kind"),
                             ([one, two], "the proposals one and two both add system:acme-scheduler")):
        with pytest.raises(ChangeRefused, match=message):
            apply_cmd.apply(folders, ROOT, say=quiet)


def test_the_round_trip_refuses_a_difference_that_no_line_of_a_new_item_states(tmp_path):
    before = Graph().parse(ROOT / ri.SYSTEM_FOLDER / "systems.ttl")
    after = Graph() + before
    from rdflib import Literal, URIRef
    from rdflib.namespace import SKOS
    mips = URIRef(MIPS)
    after.remove((mips, SKOS.prefLabel, None))
    after.add((mips, SKOS.prefLabel, Literal("MIPS renamed", lang="en")))
    with pytest.raises(ChangeRefused, match="the graphs differ in 2 ways that no line of a new system states"):
        ri.compare(before, after, "system")
    assert ri.compare(before, Graph() + before, "system") == []
