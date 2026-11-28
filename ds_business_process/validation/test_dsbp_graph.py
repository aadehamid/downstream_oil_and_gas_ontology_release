#!/usr/bin/env python3
"""Tests for dsbp_graph.py. Installed from the consistency-graph skill.

Keep the generic tests as they are. Replace the example fixture and the
example-specific tests with ones that cover every source form your parsers
read and every kind of finding your check can raise: each check needs a test
that fails when the check is removed. The relate tests skip where relate is
not installed, as on CI.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "dsbp_graph.py")
sys.path.insert(0, HERE)
import dsbp_graph  # noqa: E402

REGISTER = """# Decision register

| ID | Question | Decision | Owner's words | Date, place |
|---|---|---|---|---|
| DSBP-DEC-0001 | Q1 | First. Superseded on 2026-11-24 by DSBP-DEC-0003. | "yes" | 2026-11-23, thread |
| DSBP-DEC-0002 | Q2 | Second. Amended on 2026-11-25 by DSBP-DEC-0004. | "yes" | 2026-11-23, thread |
| DSBP-DEC-0003 | Q3 | Third, replacing 0001. | "yes" | 2026-11-24, thread |
| DSBP-DEC-0004 | Q4 (amends DSBP-DEC-0002) | Fourth. | "yes" | 2026-11-25, thread |
"""

QUESTIONS = """# Competency questions

Status: 2 of the 3 questions are locked; 1 held.

1. Which process is the parent of P?
2. Which role does R hold? *(Held: evidence needed.)*
3. Which measure does M feed?
"""

B3 = """key,baseline_id,change,decision
,CM-1,rename,DSBP-DEC-0001
,CM-2,move,DSBP-DEC-0002
,CM-3,exclude,DSBP-DEC-0003
NEW:a,,new,DSBP-DEC-0004
"""

GAPS = "id,need\nSG-01,a\nSG-02,b\n"

STATUS = """# Build status

B3 has 1 renames, 1 moves, 1 exclusions and 1 new concepts (DSBP-DEC-0001 to 0004).
Turn `registers/skill-gaps.csv` (2 rows) into a pull request. 2 Step 4 relationship facts.
See `registers/decision-register.md`.
"""

GOAL = "# Goal\n\n1. Every file has a row in `migration/files.csv`.\n"

FACTS = "subject,predicate,object\na,b,c\nd,e,f\n"

GENERIC_TABLE = "| Decision | Title |\n|---|---|\n| D1 | Use a queue |\n| D2 | Use a cache |\n"

SOURCES = {
    dsbp_graph.REGISTER: REGISTER, dsbp_graph.QUESTIONS: QUESTIONS, dsbp_graph.B3_CHANGES: B3,
    dsbp_graph.SKILL_GAPS: GAPS, dsbp_graph.BUILD_STATUS: STATUS, dsbp_graph.GOAL: GOAL,
    dsbp_graph.STEP4_FACTS: FACTS,
}


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for rel, text in SOURCES.items():
            write(self.root, rel, text)

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self):
        return dsbp_graph.check(dsbp_graph.build(self.root))

    def cli(self, *args):
        env = dict(os.environ, DSBP_GRAPH_ROOT=self.root)
        return subprocess.run([sys.executable, SCRIPT, *args], env=env, capture_output=True, text=True, timeout=60)


class Generic(Fixture):
    def test_markdown_tables_read_rows_by_header(self):
        tables = dsbp_graph.markdown_tables(GENERIC_TABLE + "\ntext\n\n| A | B |\n|:-|-:|\n| 1 | 2 |\n")
        self.assertEqual([h for h, _ in tables], [["Decision", "Title"], ["A", "B"]])
        self.assertEqual(tables[1][1][0]["B"], "2")

    def test_an_empty_last_cell_with_no_space_is_kept(self):
        # "| 1 ||" ends with two pipes: removing every outer pipe would lose the empty cell.
        tables = dsbp_graph.markdown_tables("| A | B | C |\n|---|---|---|\n| 1 | 2 ||\n")
        row = tables[0][1][0]
        self.assertEqual((row["_cells"], row["C"]), (3, ""))

    def test_a_separator_needs_dashes(self):
        # "| : | : |" holds only colons; it is a row, not the line under a header.
        self.assertEqual(dsbp_graph.markdown_tables("| P | Q |\n| : | : |\n| r | s |\n"), [])

    def test_tables_in_fenced_code_are_skipped(self):
        text = "```\n| X | Y |\n|---|---|\n| in | code |\n```\n| A |\n|---|\n| 1 |\n"
        self.assertEqual([h for h, _ in dsbp_graph.markdown_tables(text)], [["A"]])

    def test_clashes_compare_type_as_well_as_value(self):
        g = dsbp_graph.Graph(self.root)
        g.node("Valve", "V-1", "a.md", size="3", open=True)
        g.node("Valve", "V-1", "b.json", size=3, open=1)
        clashes = g.clashes()
        self.assertEqual(len(clashes), 2, clashes)
        self.assertTrue(any("size" in c and "'3'" in c and "says 3" in c for c in clashes), clashes)

    def test_one_source_stating_a_value_twice_compares_type(self):
        g = dsbp_graph.Graph(self.root)
        g.node("Valve", "V-1", "a.json", open=True, n=1)
        g.node("Valve", "V-1", "a.json", open=1, n=1.0)
        self.assertEqual(len([p for p in g.problems if "states" in p and "twice" in p]), 2, g.problems)

    def test_one_source_stating_a_list_twice_compares_element_types(self):
        g = dsbp_graph.Graph(self.root)
        g.node("Valve", "V-1", "a.json", nums=[1], flags=[True], same=[1, "a"])
        g.node("Valve", "V-1", "a.json", nums=[1.0], flags=[1], same=[1, "a"])
        self.assertEqual(sorted(p.split(" states ")[1].split(" ")[0] for p in g.problems), ["flags", "nums"])

    def test_list_properties_reach_the_cypher_and_other_shapes_are_refused(self):
        g = dsbp_graph.Graph(self.root)
        g.node("Pump", "P-1", "a.md", tags=["a", "b"], size=3, spec={"x": 1})
        self.assertIn('`tags`: ["a", "b"]', dsbp_graph.cypher_seed(g))
        self.assertEqual([p for p in g.problems if "gives spec a dict" in p], [
            "P-1: a.md gives spec a dict; use text, a number, true/false or a list of those"])

    def test_labels_and_link_types_must_be_plain_names(self):
        g = dsbp_graph.Graph(self.root)
        g.node("Work Request", "WR-1", "a.md")
        g.node("Pump", "P-1", "a.md")
        g.node("Pump", "P-2", "a.md")
        g.link("P-1", "clarified by", "P-2", "a.md")
        self.assertIn("WR-1: a.md gives the label 'Work Request'; use letters, digits and _", g.problems)
        self.assertIn("P-1: a.md gives the link type 'clarified by'; use letters, digits and _", g.problems)
        seed = dsbp_graph.cypher_seed(g)
        self.assertNotIn("Work Request", seed)
        self.assertNotIn("clarified by", seed)

    def test_missing_sources_are_reported_once_each(self):
        empty = tempfile.TemporaryDirectory()
        try:
            findings = dsbp_graph.check(dsbp_graph.build(empty.name))
        finally:
            empty.cleanup()
        self.assertEqual(sorted(f for f in findings if "missing" in f),
                         sorted(f"{rel}: source is missing" for rel in
                                (dsbp_graph.REGISTER, dsbp_graph.QUESTIONS, dsbp_graph.B3_CHANGES,
                                 dsbp_graph.SKILL_GAPS, dsbp_graph.BUILD_STATUS)))

    def test_reserved_property_names_are_refused(self):
        g = dsbp_graph.Graph(self.root)
        g.node("Pump", "P-1", "a.md", id="other", sources="x")
        self.assertEqual(len([p for p in g.problems if "reserved property" in p]), 2, g.problems)
        self.assertNotIn('"other"', dsbp_graph.cypher_seed(g))

    def test_a_bad_required_link_direction_is_reported(self):
        saved = dsbp_graph.REQUIRED_LINKS
        dsbp_graph.REQUIRED_LINKS = [("Change", "CITES", "outbound", "x")]
        try:
            self.assertIn("REQUIRED_LINKS: Change CITES has direction 'outbound'; use 'out' or 'in'",
                          self.findings())
        finally:
            dsbp_graph.REQUIRED_LINKS = saved

    def test_argument_errors_come_before_reading_sources(self):
        empty = tempfile.TemporaryDirectory()
        try:
            env = dict(os.environ, DSBP_GRAPH_ROOT=empty.name)
            for args in (("nonsense",), ("summary", "x"), ("impact",)):
                with self.subTest(args):
                    p = subprocess.run([sys.executable, SCRIPT, *args], env=env, capture_output=True, text=True, timeout=60)
                    self.assertEqual(p.returncode, 2, p.stderr)
                    self.assertNotIn("Traceback", p.stderr)
        finally:
            empty.cleanup()

    def test_two_sources_that_disagree_make_a_clash_not_a_choice(self):
        g = dsbp_graph.Graph(self.root)
        g.node("Pump", "P-1", "spec.md", name="Feed pump")
        g.node("Pump", "P-1", "sheet.py", name="FEED PUMP A")
        g.node("Pump", "P-1", "other.md")
        clashes = g.clashes()
        self.assertEqual(len(clashes), 1)
        self.assertIn("sheet.py says 'FEED PUMP A'", clashes[0])
        self.assertIn("spec.md says 'Feed pump'", clashes[0])

    def test_one_id_with_two_labels_names_every_source_on_each_side(self):
        g = dsbp_graph.Graph(self.root)
        g.node("Pump", "X-1", "a.md")
        g.node("Valve", "X-1", "b.md")
        g.node("Pump", "X-1", "c.md")
        g.node("Tank", "X-1", "d.md")
        self.assertEqual(g.clashes(), ["X-1: sources disagree on its label: a.md, c.md call it a Pump; "
                                       "d.md calls it a Tank; b.md calls it a Valve"])

    def test_cli_arguments(self):
        self.assertEqual(self.cli("summary").returncode, 0)
        for args in (("summary", "x"), ("check", "--strict"), ("export", "x"), ("impact",),
                     ("impact", "nope"), ("query",), ("nonsense",), ("help", "x")):
            with self.subTest(args):
                self.assertEqual(self.cli(*args).returncode, 2, args)


class Project(Fixture):
    def test_consistent_sources_pass(self):
        self.assertEqual(self.findings(), [])
        p = self.cli("check")
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "dsbp_graph: the sources agree"))

    def test_summary_counts(self):
        self.assertEqual(json.loads(self.cli("summary").stdout), {
            "nodes": {"Change": 4, "Decision": 4, "Document": 6, "PendingPath": 1, "Question": 3, "SkillGap": 2},
            "links": {"AMENDS": 1, "CITES": 16, "PROMISES": 1, "SUPERSEDED_BY": 1}})

    def test_short_and_range_citations_expand(self):
        self.assertEqual([i for _, i in dsbp_graph.cited("DSBP-DEC-0012 and 0016 to 0018, 0020")],
                         ["DSBP-DEC-0012", "DSBP-DEC-0016", "DSBP-DEC-0017", "DSBP-DEC-0018", "DSBP-DEC-0020"])

    def test_each_kind_of_finding_is_reported(self):
        # (finding, file to change, old text, new text): one case per check, so removing a check fails its case.
        cases = [
            # Link to nothing: a cited decision the register does not hold.
            ("DSBP-DEC-0009 is not defined by any source", dsbp_graph.BUILD_STATUS, "0001 to 0004", "0001 to 0004, 0009"),
            ("DSBP-DEC-0009 is not defined by any source", dsbp_graph.B3_CHANGES, "new,DSBP-DEC-0004", "new,DSBP-DEC-0009"),
            # Link stated on one side only.
            ("DSBP-DEC-0004 amends DSBP-DEC-0002, but DSBP-DEC-0002's row does not name DSBP-DEC-0004",
             dsbp_graph.REGISTER, " Amended on 2026-11-25 by DSBP-DEC-0004.", ""),
            ("DSBP-DEC-0001 superseded by DSBP-DEC-0003, but DSBP-DEC-0003's row does not name DSBP-DEC-0001",
             dsbp_graph.REGISTER, "Third, replacing 0001.", "Third."),
            # Element with a required link missing.
            ("B3:CM-2: a Change with no CITES link", dsbp_graph.B3_CHANGES, "move,DSBP-DEC-0002", "move,"),
            # Counts that do not add up.
            ("says 2 of 3 questions are locked; ds_business_process/foundations/competency-questions.md locks 1 of 3",
             dsbp_graph.QUESTIONS, "3. Which measure does M feed?", "3. Which measure does M feed? *(Held)*"),
            ("says 2 questions are held", dsbp_graph.QUESTIONS, "1 held.", "2 held."),
            ("says B3 has {'rename': 2, 'move': 1, 'exclude': 1, 'new': 1}", dsbp_graph.BUILD_STATUS,
             "1 renames", "2 renames"),
            ("SkillGap: the sources define 2, but ds_business_process/BUILD-STATUS.md says 3",
             dsbp_graph.BUILD_STATUS, "(2 rows)", "(3 rows)"),
            ("says 3 Step 4 facts", dsbp_graph.BUILD_STATUS, "2 Step 4", "3 Step 4"),
            ("promises no skill-gap count", dsbp_graph.BUILD_STATUS, "(2 rows)", "(two rows)"),
            # Link to nothing: a path no file holds; in GOAL it is pending, not a finding.
            ("points to registers/gone.md, which is not in the repository", dsbp_graph.BUILD_STATUS,
             "registers/decision-register.md", "registers/gone.md"),
            # Unreadable source form.
            ("row has 4 cells, the header 5", dsbp_graph.REGISTER, '| "yes" | 2026-11-25, thread |', "| x |"),
            ("'DSBP-DEC-4' is not a decision ID", dsbp_graph.REGISTER, "| DSBP-DEC-0004 |", "| DSBP-DEC-4 |"),
            ("row has neither a key nor a baseline ID", dsbp_graph.B3_CHANGES, ",CM-3,", ",,"),
        ]
        for message, rel, old, new in cases:
            with self.subTest(message):
                self.tearDown()
                self.setUp()
                self.assertIn(old, SOURCES[rel])
                write(self.root, rel, SOURCES[rel].replace(old, new, 1))
                findings = self.findings()
                self.assertTrue(any(message in f for f in findings), findings)
                p = self.cli("check")
                self.assertEqual(p.returncode, 1)
                self.assertIn("finding(s)", p.stderr)

    def test_a_path_a_done_line_promises_is_pending(self):
        graph = dsbp_graph.build(self.root)
        self.assertEqual(graph.nodes["migration/files.csv"]["label"], "PendingPath")
        self.assertEqual(self.findings(), [])

    def test_the_validation_folder_is_not_read(self):
        write(self.root, "ds_business_process/validation/notes.md", "DSBP-DEC-0099 and `registers/none.md`\n")
        self.assertEqual(self.findings(), [])

    def test_text_inside_fenced_code_is_not_read(self):
        write(self.root, dsbp_graph.BUILD_STATUS, STATUS + "\n```\nDSBP-DEC-0099 (9 rows)\n```\n")
        self.assertEqual(self.findings(), [])


@unittest.skipUnless(shutil.which("relate"), "relate is not installed")
class Queries(Fixture):
    def test_reserved_words_as_labels_and_link_types_load(self):
        g = dsbp_graph.Graph(self.root)
        for label, ident in (("Order", "O-1"), ("Match", "M-1"), ("NULL", "N-1"), ("WHERE", "W-1")):
            g.node(label, ident, "a.md", tags=["x"])
        g.link("O-1", "IN", "M-1", "a.md")
        g.link("N-1", "true", "W-1", "a.md")
        rows = dsbp_graph.run_relate(g, "MATCH (a)-[r]->(b) RETURN a.id AS a, type(r) AS t ORDER BY a", {})
        self.assertEqual([json.loads(r) for r in rows], [{"a": "N-1", "t": "true"}, {"a": "O-1", "t": "IN"}])

    def test_impact_reaches_linked_nodes(self):
        p = self.cli("impact", "DSBP-DEC-0002")
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = {r["id"]: r["hops"] for r in map(json.loads, p.stdout.splitlines())}
        self.assertEqual(rows["DSBP-DEC-0004"], 1)
        self.assertEqual(rows["B3:CM-2"], 1)
        self.assertEqual(rows[dsbp_graph.BUILD_STATUS], 1)

    def test_query_is_read_only(self):
        p = self.cli("query", "MATCH (c:Change) RETURN count(c) AS n")
        self.assertEqual(json.loads(p.stdout.splitlines()[0]), {"n": 4})
        self.assertNotEqual(self.cli("query", "MATCH (c:Change) DETACH DELETE c").returncode, 0)
        p = self.cli("query", "--version")
        self.assertNotEqual(p.returncode, 0)
        # relate read it as a statement and rejected its syntax; read as a flag it would print its version.
        self.assertIn("syntax error", p.stderr)
        self.assertNotIn("Relate v", p.stderr + p.stdout)

    def test_export_loads_and_keeps_sources(self):
        rows = dsbp_graph.run_relate(dsbp_graph.build(self.root),
                                     "MATCH (:Change {id: 'B3:CM-2'})-[r:CITES]->(d) RETURN d.id AS d, r.sources AS s", {})
        self.assertEqual([json.loads(r) for r in rows],
                         [{"d": "DSBP-DEC-0002", "s": [dsbp_graph.B3_CHANGES]}])


if __name__ == "__main__":
    unittest.main()
