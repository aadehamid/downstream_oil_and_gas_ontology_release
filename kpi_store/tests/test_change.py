"""The change core (kpi_store/change): KGCL lines, the approval record, the apply to the kpi tables and the round trip.

The KGCL and approval tests use values written by hand. The apply and round-trip tests run on a scratch copy of the
real kpi module, made in a temporary folder with only what its builder reads; the real tables are never written.
They pick their measures from the copy's own tables, so they hold on a copy that has moved on from the release as
shipped. Every line the code writes is checked against the official KGCL parser, kgcl-schema 0.7.0, which only
these tests need.
"""
import csv
import json
import shutil
from pathlib import Path

import pytest
from kgcl_schema.grammar.parser import parse_statement
from kgcl_schema.grammar.render_operations import render
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import SKOS

from kpi_store.change import ChangeRefused, approval, kgcl, kpi_tables
from kpi_store.change.kgcl import Change
from kpi_store.tests import support

KPI = support.ROOT / kpi_tables.KPI_FOLDER
ONTOLOGY = support.ROOT / "business_architecture" / "ontology"
INFORMS = URIRef(kpi_tables.PREFIXES["kpi"] + "informsProcess")


def official(line):
    """The official parser reads the line, and its renderer writes the same line back."""
    parsed = parse_statement(line)
    assert render(parsed) == line
    return parsed


# ---------- KGCL: each statement form, read and written, with values written by hand ----------

FORMS = [
    ("create exact synonym 'unit capacity utilization' for measure:unit-utilization",
     Change("create synonym", "measure:unit-utilization", text="unit capacity utilization")),
    ("remove synonym 'unit rates' for measure:unit-utilization",
     Change("remove synonym", "measure:unit-utilization", text="unit rates")),
    ("change definition of measure:crude-utilization to 'Fresh crude charged as a share of crude capacity, for one refinery and month.'",
     Change("change definition", "measure:crude-utilization",
            text="Fresh crude charged as a share of crude capacity, for one refinery and month.")),
    ("rename measure:unit-utilization from 'Unit Utilization' to 'Process Unit Utilization'",
     Change("rename", "measure:unit-utilization", old="Unit Utilization", text="Process Unit Utilization")),
    ("create edge measure:crude-utilization kpi:informsProcess proc:CM-1-1-4-4",
     Change("create edge", "measure:crude-utilization", predicate="kpi:informsProcess", target="proc:CM-1-1-4-4")),
    ("delete edge measure:unit-utilization kpi:informsProcess proc:CM-1-1-7-2-5",
     Change("delete edge", "measure:unit-utilization", predicate="kpi:informsProcess", target="proc:CM-1-1-7-2-5")),
]


@pytest.mark.parametrize("line,change", FORMS, ids=[c.kind for _, c in FORMS])
def test_each_form_reads_and_writes_as_the_official_grammar_does(line, change):
    assert kgcl.read_line(line) == change
    assert kgcl.write_line(change) == line
    official(line)


def test_the_official_parser_reads_the_same_values():
    synonym = official(FORMS[0][0])
    assert (synonym.about_node, synonym.new_value, synonym.qualifier) == ("measure:unit-utilization", "unit capacity utilization", "exact")
    removed = official(FORMS[1][0])
    assert (removed.about_node, removed.old_value) == ("measure:unit-utilization", "unit rates")
    definition = official(FORMS[2][0])
    assert (definition.about_node, definition.new_value) == ("measure:crude-utilization", FORMS[2][1].text)
    renamed = official(FORMS[3][0])
    assert (renamed.about_node, renamed.old_value, renamed.new_value) == (
        "measure:unit-utilization", "Unit Utilization", "Process Unit Utilization")
    edge = official(FORMS[4][0])
    assert (edge.subject, edge.predicate, edge.object) == ("measure:crude-utilization", "kpi:informsProcess", "proc:CM-1-1-4-4")


def test_a_double_quote_inside_text_reads_and_writes():
    line = "change definition of measure:crack-spreads to 'The \"3-2-1\" crack spread, in $/bbl.'"
    change = kgcl.read_line(line)
    assert change.text == 'The "3-2-1" crack spread, in $/bbl.'
    assert kgcl.write_line(change) == line
    assert official(line).new_value == 'The "3-2-1" crack spread, in $/bbl.'


def test_a_straight_apostrophe_is_written_as_the_typographic_one_and_read_back():
    # The grammar has no escape for ', so a line writes it as ’, which the official tools take unchanged.
    line = "create exact synonym 'MPC’s margin – R&M' for measure:rm-margin-per-barrel"
    assert kgcl.read_line(line).text == "MPC's margin – R&M"
    assert kgcl.write_line(kgcl.read_line(line)) == line
    assert official(line).new_value == "MPC’s margin – R&M"
    rename = Change("rename", "measure:x", old="MPC's margin", text="MPC's R&M margin")
    assert kgcl.write_line(rename) == "rename measure:x from 'MPC’s margin' to 'MPC’s R&M margin'"
    official(kgcl.write_line(rename))
    assert kgcl.read_line(kgcl.write_line(rename)) == rename


def test_a_text_that_holds_a_real_typographic_apostrophe_is_refused():
    for change in (Change("change definition", "measure:x", text="MPC’s margin"),
                   Change("rename", "measure:x", old="Old", text="MPC’s"),
                   Change("create synonym", "measure:x", text="it’s")):
        with pytest.raises(ChangeRefused, match="typographic apostrophe"):
            kgcl.write_line(change)


def test_a_change_file_reads_line_by_line_and_skips_blank_lines():
    text = FORMS[0][0] + "\n\n" + FORMS[3][0] + "\n"
    changes = kgcl.read_lines(text)
    assert changes == [FORMS[0][1], FORMS[3][1]]
    assert kgcl.write_lines(changes) == FORMS[0][0] + "\n" + FORMS[3][0] + "\n"


def test_the_grammar_has_no_escape_for_a_straight_single_quote():
    # kgcl.lark: SINGLE_QUOTE_LITERAL is "'" /((?!\').)*/ "'". Neither doubling nor a backslash escapes a quote,
    # and a synonym cannot be double-quoted. So a line that tries any of them is refused.
    for line in ("create exact synonym 'MPC''s margin' for measure:x", "create exact synonym 'MPC\\'s margin' for measure:x",
                 "create exact synonym \"MPC's margin\" for measure:x"):
        with pytest.raises(Exception):
            parse_statement(line)
        with pytest.raises(ChangeRefused):
            kgcl.read_line(line)


def test_the_official_renderer_writes_a_backslash_twice_so_the_text_is_refused():
    line = "change definition of measure:x to 'a\\b'"
    assert render(parse_statement(line)) != line
    with pytest.raises(ChangeRefused, match="backslash"):
        kgcl.read_line(line)
    with pytest.raises(ChangeRefused, match="backslash"):
        kgcl.write_line(Change("change definition", "measure:x", text="a\\b"))


@pytest.mark.parametrize("text,reason", [("", "empty"), (" padded", "starts or ends with a space"),
                                         ("two\nlines", "line break"), ("tab\there", "control character"),
                                         ("first\u2028second", "line break"), ("first\u2029second", "line break")])
def test_text_that_a_line_cannot_carry_is_refused(text, reason):
    with pytest.raises(ChangeRefused, match=reason):
        kgcl.write_line(Change("create synonym", "measure:x", text=text))


@pytest.mark.parametrize("line", [
    "obsolete measure:unit-utilization",
    "create synonym 'unit rates' for measure:unit-utilization",           # no qualifier
    "create narrow synonym 'unit rates' for measure:unit-utilization",    # another qualifier
    "create exact synonym 'unit rates'@en for measure:unit-utilization",  # a language tag
    "change definition of measure:x from 'old' to 'new'",
    "rename 'Unit Utilization' to 'New'",                                  # no id
    "rename measure:x from 'a' as 'b'",
    "create edge <https://w3id.org/mpc/ontology/modules/kpi/measure/x> kpi:informsProcess proc:CM-1",
    "create  edge measure:x kpi:informsProcess proc:CM-1",                 # two spaces
    "create edge measure:x kpi:informsProcess proc:CM-1 ",                 # a space at the end
    "add definition 'text' to measure:x",
    "",
])
def test_any_other_line_is_not_a_change_this_release_applies(line):
    with pytest.raises(ChangeRefused, match="not a change this release applies"):
        kgcl.read_line(line)


def test_the_writer_refuses_an_unknown_kind_and_an_id_without_a_prefix():
    with pytest.raises(ChangeRefused, match="not a change this release applies"):
        kgcl.write_line(Change("obsolete", "measure:x"))
    with pytest.raises(ChangeRefused, match="prefix:name"):
        kgcl.write_line(Change("create synonym", "unit-utilization", text="unit rates"))
    with pytest.raises(ChangeRefused, match="prefix:name"):
        kgcl.write_line(Change("create edge", "measure:x", predicate="informsProcess", target="proc:CM-1"))


# ---------- the approval record ----------

DATA_OWNER = {"role": "Data Owner", "name": "A. Sample", "date": "2026-11-19",
              "words": "Approved as a minor: the alias \"unit capacity utilization\" for Unit Utilization."}
ARCHITECT = {"role": "Architect", "name": "B. Example", "date": "2026-11-19", "words": "Approved as a minor."}
ONTOLOGY_OWNER = {"role": "Ontology Owner", "name": "C. Placeholder", "date": "2026-11-20",
                  "words": "Approved as a major: Unit Utilization’s new meaning."}


def test_a_record_is_written_where_approvals_live_and_reads_back(tmp_path):
    path = approval.write_record(tmp_path, "2026-11-19-kpi-alias", "minor", [DATA_OWNER, ARCHITECT])
    assert path == tmp_path / "business_architecture" / "ontology" / "approvals" / "2026-11-19-kpi-alias.json"
    record = approval.read_record(path)
    assert record == {"change": "2026-11-19-kpi-alias", "route": "minor", "new_module": False,
                      "signatures": [DATA_OWNER, ARCHITECT]}
    assert approval.holds_words(record, "Approved as a minor.")
    assert not approval.holds_words(record, "Approved as a major.")
    # The existing rule for approvals: the approval words appear in the file.
    assert "Approved as a minor." in path.read_text(encoding="utf-8")
    assert ONTOLOGY_OWNER["words"] in approval.write_record(tmp_path, "c2", "major", [DATA_OWNER, ARCHITECT, ONTOLOGY_OWNER]).read_text(encoding="utf-8")


@pytest.mark.parametrize("route,new_module,signatures,missing", [
    ("minor", False, [DATA_OWNER], "Architect"),
    ("patch", False, [ARCHITECT], "Data Owner"),
    ("major", False, [DATA_OWNER, ARCHITECT], "Ontology Owner"),
    ("minor", True, [DATA_OWNER, ARCHITECT], "Ontology Owner"),
])
def test_a_record_without_a_signature_its_route_needs_is_refused(tmp_path, route, new_module, signatures, missing):
    with pytest.raises(ChangeRefused, match=f"needs the signature of the {missing}"):
        approval.write_record(tmp_path, "c1", route, signatures, new_module=new_module)
    assert not (tmp_path / approval.APPROVALS).exists()


def test_the_roles_each_route_needs():
    assert approval.required_roles("patch") == ["Data Owner", "Architect"]
    assert approval.required_roles("minor") == ["Data Owner", "Architect"]
    assert approval.required_roles("major") == ["Data Owner", "Architect", "Ontology Owner"]
    assert approval.required_roles("minor", new_module=True) == ["Data Owner", "Architect", "Ontology Owner"]


@pytest.mark.parametrize("change,message", [
    ({"route": "huge"}, "is not patch, minor or major"),
    ({"change": "../escape"}, "change id"),
    ({"new_module": "no"}, "true or false"),
    ({"signatures": []}, "no signatures"),
    ({"signatures": [dict(DATA_OWNER, role="Manager"), ARCHITECT]}, "not a role that signs"),
    ({"signatures": [dict(DATA_OWNER, date="2026-02-30"), ARCHITECT]}, "YYYY-MM-DD"),
    ({"signatures": [dict(DATA_OWNER, date="19/11/2026"), ARCHITECT]}, "YYYY-MM-DD"),
    ({"signatures": [dict(DATA_OWNER, words="  "), ARCHITECT]}, "signature 1 has no words"),
    ({"signatures": [DATA_OWNER, {k: v for k, v in ARCHITECT.items() if k != "name"}]}, "signature 2 has no name"),
    ({"signatures": [dict(DATA_OWNER, name="A.\nSample"), ARCHITECT]}, "control character"),
    ({"signatures": [dict(DATA_OWNER, email="a@example.com"), ARCHITECT]}, "fields it should not: email"),
    ({"extra": 1}, "fields it should not: extra"),
])
def test_an_incomplete_or_wrong_record_is_refused_on_read(tmp_path, change, message):
    record = dict({"change": "c1", "route": "minor", "new_module": False, "signatures": [DATA_OWNER, ARCHITECT]}, **change)
    path = tmp_path / "c1.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ChangeRefused, match=message):
        approval.read_record(path)


@pytest.mark.parametrize("field", approval.FIELDS)
def test_a_record_missing_a_field_is_refused(tmp_path, field):
    record = {"change": "c1", "route": "minor", "new_module": False, "signatures": [DATA_OWNER, ARCHITECT]}
    del record[field]
    path = tmp_path / "c1.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ChangeRefused, match=f"has no {field}"):
        approval.read_record(path)


def test_a_missing_unreadable_misnamed_or_repeated_record_is_refused(tmp_path):
    with pytest.raises(ChangeRefused, match="has no approval record"):
        approval.read_record(tmp_path / "none.json")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ChangeRefused, match="not valid JSON"):
        approval.read_record(tmp_path / "bad.json")
    path = approval.write_record(tmp_path, "c1", "minor", [DATA_OWNER, ARCHITECT])
    shutil.copy(path, tmp_path / "c2.json")
    with pytest.raises(ChangeRefused, match="is for the change c1, not for c2"):
        approval.read_record(tmp_path / "c2.json")
    with pytest.raises(ChangeRefused, match="has an approval record already"):
        approval.write_record(tmp_path, "c1", "minor", [DATA_OWNER, ARCHITECT])


# ---------- the apply to the kpi tables, and the round trip ----------

@pytest.fixture
def scratch(tmp_path):
    """A scratch release with only what the kpi builder reads: the kpi tables, the builder and its output,
    release/newest.py and the newest core package's core.ttl and manifest."""
    root = tmp_path / "release"
    kpi = root / kpi_tables.KPI_FOLDER
    kpi.mkdir(parents=True)
    for path in sorted(KPI.glob("*.csv")) + [KPI / kpi_tables.BUILDER, KPI / "measures.ttl"]:
        shutil.copy2(path, kpi / path.name)
    (root / "business_architecture" / "ontology" / "release").mkdir()
    shutil.copy2(ONTOLOGY / "release" / "newest.py", root / "business_architecture" / "ontology" / "release" / "newest.py")
    core = max((p for p in (ONTOLOGY / "releases" / "core").iterdir() if (p / "manifest.json").is_file()),
               key=lambda p: tuple(int(n) for n in p.name.split(".")))
    target = root / "business_architecture" / "ontology" / "releases" / "core" / core.name
    target.mkdir(parents=True)
    for name in ("core.ttl", "manifest.json"):
        shutil.copy2(core / name, target / name)
    return root


def _rows(root, name):
    with (root / kpi_tables.KPI_FOLDER / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return {r["measure_id"]: r for r in csv.DictReader(f)}


def _real_bytes():
    return {p.name: p.read_bytes() for p in sorted(KPI.glob("*.csv")) + [KPI / "measures.ttl"]}


def _pick(root):
    """Two measures of the copy and one process: `a` has a synonym and a process link, `b` lacks that process."""
    g = Graph().parse(root / kpi_tables.MEASURES)
    details, names = _rows(root, kpi_tables.DETAILS), _rows(root, kpi_tables.CLASSIFICATION)
    def links(m):
        return {kpi_tables._curie(o) for o in g.objects(URIRef(kpi_tables.PREFIXES["measure"] + m), INFORMS)}

    for a, d in details.items():
        if d["aliases"] and links(a):
            process = sorted(links(a))[0]
            b = next(m for m in details if m != a and process not in links(m))
            return a, b, process, names[a]["name"], kpi_tables._split(d["aliases"])[0]
    raise AssertionError("no measure of the copy has both a synonym and a process link")


def test_the_prefixes_are_the_builders():
    bound = {p: str(ns) for p, ns in Graph().parse(KPI / "measures.ttl").namespaces()}
    assert {p: bound[p] for p in kpi_tables.PREFIXES} == kpi_tables.PREFIXES


def test_a_change_file_applied_to_a_scratch_copy_comes_back_from_the_compare(scratch):
    real = _real_bytes()
    a, b, process, name, alias = _pick(scratch)
    before = Graph().parse(scratch / kpi_tables.MEASURES)
    lines = [
        f"rename measure:{a} from '{name}' to '{name} (renamed)'",
        f"create exact synonym 'a \"made-up\" synonym' for measure:{a}",
        f"remove synonym '{alias}' for measure:{a}",
        f"change definition of measure:{b} to 'A made-up definition, written for the round trip.'",
        f"create edge measure:{b} kpi:informsProcess {process}",
        f"delete edge measure:{a} kpi:informsProcess {process}",
    ]
    changes = kgcl.read_lines("\n".join(lines) + "\n")
    after = kpi_tables.apply_changes(changes, scratch)
    assert after == scratch / kpi_tables.MEASURES
    back = kpi_tables.compare(before, after)
    assert sorted(back) == sorted(lines)
    for line in back:
        official(line)
    # The tables hold the changes, and nothing else changed in them.
    names, details = _rows(scratch, kpi_tables.CLASSIFICATION), _rows(scratch, kpi_tables.DETAILS)
    assert names[a]["name"] == f"{name} (renamed)"
    assert alias not in kpi_tables._split(details[a]["aliases"])
    assert 'a "made-up" synonym' in kpi_tables._split(details[a]["aliases"])
    assert details[b]["definition"] == "A made-up definition, written for the round trip."
    # The edge is written as the process's notation from the core, not as the id's slug.
    notation = str(Graph().parse(next((scratch / "business_architecture" / "ontology" / "releases" / "core").glob("*/core.ttl")))
                   .value(URIRef(kpi_tables.PREFIXES["proc"] + process.split(":", 1)[1]), SKOS.notation))
    assert notation != process.split(":", 1)[1]
    assert notation in kpi_tables._split(details[b]["informs_process"])
    assert notation not in kpi_tables._split(details[a]["informs_process"])
    for table, changed in ((kpi_tables.CLASSIFICATION, {a}), (kpi_tables.DETAILS, {a, b})):
        real_rows = {r["measure_id"]: r for r in csv.DictReader((real[f"{table}.csv"]).decode("utf-8").splitlines())}
        assert {m for m, r in _rows(scratch, table).items() if r != real_rows[m]} == changed
        assert set(_rows(scratch, table)) == set(real_rows)
    # The real tables and the real measures.ttl were not written.
    assert _real_bytes() == real


def test_the_same_graph_gives_no_line():
    assert kpi_tables.compare(KPI / "measures.ttl", KPI / "measures.ttl") == []


def test_a_difference_no_line_states_is_refused():
    before = Graph().parse(KPI / "measures.ttl")
    after = Graph()
    for t in before:
        after.add(t)
    subject = next(before.subjects(SKOS.definition, None))
    after.add((subject, SKOS.note, Literal("a note", lang="en")))
    with pytest.raises(ChangeRefused, match="1 ways that no supported KGCL line states"):
        kpi_tables.compare(before, after)


@pytest.mark.parametrize("line,message", [
    ("rename measure:no-such-measure from 'A' to 'B'", "is not a measure of the kpi module"),
    ("rename persona:prompt-planner from 'A' to 'B'", "changes only measures"),
    ("rename measure:{a} from 'Not The Name' to 'B'", "the measure's name is"),
    ("rename measure:{a} from '{name}' to '{name}'", "the new name is the current name"),
    ("rename measure:{a} from '{name}' to '{alias}'", "the new name is one of the measure's synonyms"),
    ("change definition of measure:{a} to '{definition}'", "the new definition is the current definition"),
    ("create exact synonym '{alias}' for measure:{a}", "has this synonym already"),
    ("create exact synonym '{name}' for measure:{a}", "may not repeat the measure's name"),
    ("create exact synonym 'one;two' for measure:{a}", "semicolon"),
    ("remove synonym 'no such synonym' for measure:{a}", "has no such synonym"),
    ("create edge measure:{a} kpi:usedBy proc:CM-1", "the only edge this release applies"),
    ("create edge measure:{a} kpi:informsProcess persona:prompt-planner", "points at a process"),
    ("create edge measure:{a} kpi:informsProcess proc:NO-SUCH-PROCESS", "is not a process of the newest core"),
    ("create edge measure:{a} kpi:informsProcess {process}", "informs this process already"),
    ("delete edge measure:{b} kpi:informsProcess {process}", "does not inform this process"),
])
def test_a_change_that_does_not_fit_the_tables_is_refused_and_nothing_is_written(scratch, line, message):
    a, b, process, name, alias = _pick(scratch)
    before = {p.name: p.read_bytes() for p in (scratch / kpi_tables.KPI_FOLDER).iterdir()}
    with pytest.raises(ChangeRefused, match=message):
        definition = _rows(scratch, kpi_tables.DETAILS)[a]["definition"]
        change = kgcl.read_line(line.format(a=a, b=b, process=process, name=name, alias=alias,
                                            definition=definition.replace("'", "\u2019")))
        kpi_tables.apply_changes([change], scratch)
    assert {p.name: p.read_bytes() for p in (scratch / kpi_tables.KPI_FOLDER).iterdir()} == before


def test_a_later_change_that_conflicts_stops_the_earlier_ones_too(scratch):
    a, b, process, name, alias = _pick(scratch)
    before = {p.name: p.read_bytes() for p in (scratch / kpi_tables.KPI_FOLDER).iterdir()}
    first = f"rename measure:{a} from '{name}' to 'Renamed once'"
    second = f"rename measure:{a} from '{name}' to 'Renamed twice'"
    with pytest.raises(ChangeRefused, match="the measure's name is 'Renamed once'"):
        kpi_tables.apply_changes(kgcl.read_lines(first + "\n" + second), scratch)
    assert {p.name: p.read_bytes() for p in (scratch / kpi_tables.KPI_FOLDER).iterdir()} == before


def test_an_empty_change_list_and_a_folder_without_kpi_tables_are_refused(tmp_path):
    with pytest.raises(ChangeRefused, match="no changes"):
        kpi_tables.apply_changes([], tmp_path)
    with pytest.raises(ChangeRefused, match="no changes"):
        kpi_tables.apply_changes((c for c in []), tmp_path)
    with pytest.raises(ChangeRefused, match="not a KPI Store release"):
        kpi_tables.apply_changes([FORMS[0][1]], tmp_path)


def test_a_definition_with_a_straight_apostrophe_round_trips_and_the_table_keeps_it(scratch):
    a, b, process, name, alias = _pick(scratch)
    before = Graph().parse(scratch / kpi_tables.MEASURES)
    text = "MPC's made-up definition, for the round trip of an apostrophe."
    line = kgcl.write_line(Change("change definition", f"measure:{b}", text=text))
    assert line == f"change definition of measure:{b} to 'MPC’s made-up definition, for the round trip of an apostrophe.'"
    assert render(parse_statement(line)) == line
    after = kpi_tables.apply_changes([kgcl.read_line(render(parse_statement(line)))], scratch)
    assert _rows(scratch, kpi_tables.DETAILS)[b]["definition"] == text
    assert kpi_tables.compare(before, after) == [line]


def test_apply_refuses_a_value_that_holds_a_real_typographic_apostrophe(scratch):
    a, b, process, name, alias = _pick(scratch)
    with pytest.raises(ChangeRefused, match="typographic apostrophe"):
        kpi_tables.apply_changes([Change("change definition", f"measure:{b}", text="MPC’s margin")], scratch)


def test_compare_gives_lines_in_an_order_that_apply_can_replay(scratch, tmp_path):
    # A rename that keeps the old name as a synonym: the rename must come back before the synonym.
    a, b, process, name, alias = _pick(scratch)
    clean = tmp_path / "clean"
    shutil.copytree(scratch, clean)
    before = Graph().parse(scratch / kpi_tables.MEASURES)
    lines = [f"rename measure:{a} from '{name}' to '{name} (renamed)'",
             f"create exact synonym '{name}' for measure:{a}",
             f"remove synonym '{alias}' for measure:{a}"]
    back = kpi_tables.compare(before, kpi_tables.apply_changes(kgcl.read_lines("\n".join(lines)), scratch))
    assert back == [lines[2], lines[0], lines[1]]
    replayed = kpi_tables.apply_changes(kgcl.read_lines("\n".join(back)), clean)
    assert replayed.read_bytes() == (scratch / kpi_tables.MEASURES).read_bytes()


def _measure(g):
    """The first measure of a graph, by IRI."""
    return min(s for s in g.subjects(SKOS.definition, None) if str(s).startswith(kpi_tables.PREFIXES["measure"]))


def _changed(change):
    """A copy of the real measures graph, with change(graph) applied."""
    g = Graph().parse(KPI / "measures.ttl")
    change(g)
    return g


@pytest.mark.parametrize("change", [
    lambda g: [(g.remove((s, SKOS.prefLabel, o)), g.add((s, SKOS.prefLabel, Literal(str(o), lang="fr"))))
               for s, o in [(_measure(g), g.value(_measure(g), SKOS.prefLabel))]],
    lambda g: [(g.remove((s, SKOS.prefLabel, o)), g.add((s, SKOS.prefLabel, Literal(str(o)))))
               for s, o in [(_measure(g), g.value(_measure(g), SKOS.prefLabel))]],
    lambda g: g.add((_measure(g), SKOS.altLabel, Literal("unit rates", lang="fr"))),
    lambda g: g.add((_measure(g), SKOS.altLabel, Literal(42))),
    lambda g: g.add((_measure(g), INFORMS,
                     Literal(kpi_tables.PREFIXES["proc"] + "CM-1-1-4-4"))),
    lambda g: g.add((_measure(g), INFORMS, URIRef(kpi_tables.PREFIXES["proc"]))),
    lambda g: [g.remove((s, SKOS.definition, o)) for s, o in [(_measure(g), g.value(_measure(g), SKOS.definition))]],
], ids=["name language changed", "name language dropped", "synonym in French", "typed synonym",
        "edge to a literal", "edge to the bare namespace", "definition removed"])
def test_compare_refuses_a_difference_that_is_not_a_supported_line(change):
    with pytest.raises(ChangeRefused, match="no supported KGCL line states"):
        kpi_tables.compare(KPI / "measures.ttl", _changed(change))


@pytest.mark.parametrize("subject", ['measure:a"b', "measure:a\x00b", "measure:a\\b"])
def test_an_id_with_a_character_the_grammar_does_not_take_is_refused(subject):
    with pytest.raises(ChangeRefused, match="prefix:name"):
        kgcl.write_line(Change("create synonym", subject, text="unit rates"))
    with pytest.raises(ChangeRefused):
        kgcl.read_line(f"create exact synonym 'unit rates' for {subject}")


def test_write_record_refuses_an_extra_signature_field_and_signatures_that_are_not_a_list(tmp_path):
    with pytest.raises(ChangeRefused, match="fields it should not: email"):
        approval.write_record(tmp_path, "c1", "minor", [dict(DATA_OWNER, email="a@example.com"), ARCHITECT])
    with pytest.raises(ChangeRefused, match="no signatures"):
        approval.write_record(tmp_path, "c1", "minor", None)
    with pytest.raises(ChangeRefused, match="control character"):
        approval.write_record(tmp_path, "c1", "minor", [dict(DATA_OWNER, name="A. Sample"), ARCHITECT])
    assert not (tmp_path / approval.APPROVALS).exists()


def test_a_copy_without_the_newest_core_refuses_an_edge(scratch):
    a, b, process, name, alias = _pick(scratch)
    (scratch / "business_architecture" / "ontology" / "release" / "newest.py").unlink()
    with pytest.raises(ChangeRefused, match="no readable newest core package"):
        kpi_tables.apply_changes([Change("create edge", f"measure:{b}", predicate="kpi:informsProcess", target=process)],
                                 scratch)


def test_a_builder_that_fails_becomes_a_refusal(scratch):
    a, b, process, name, alias = _pick(scratch)
    (scratch / kpi_tables.KPI_FOLDER / kpi_tables.BUILDER).write_text('import sys\nsys.exit("made-up failure")\n',
                                                                      encoding="utf-8")
    with pytest.raises(ChangeRefused, match="(?s)the kpi builder refused the changed tables.*made-up failure"):
        kpi_tables.apply_changes([Change("create synonym", f"measure:{a}", text="a made-up synonym")], scratch)
