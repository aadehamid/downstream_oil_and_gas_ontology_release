#!/usr/bin/env python3
"""A consistency graph of this project's sources, rebuilt from them on every run.

Usage:
  dsbp_graph.py summary          counts of nodes by label and links by type
  dsbp_graph.py check            where the sources disagree or cannot be read (exit 1 if so)
  dsbp_graph.py impact ID        everything linked to ID within three hops (needs relate)
  dsbp_graph.py query 'CYPHER'   any Cypher, run on a read-only copy of the graph (needs relate)
  dsbp_graph.py export           the graph as a Cypher script for relate or Neo4j

Installed from the consistency-graph skill. Keep the generic core below as it is
and change only the PROJECT section: the sources, the parsers that read them,
the rules a link must follow, and the counts the sources promise.
DSBP_GRAPH_ROOT points the tool at another checkout, which the tests use.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

def repo_root(start):
    """The nearest folder above start that holds .git, wherever the tool sits in the repository."""
    path = start
    while not os.path.exists(os.path.join(path, ".git")):
        parent = os.path.dirname(path)
        if parent == path:
            return os.path.dirname(start)
        path = parent
    return path


ROOT = os.environ.get("DSBP_GRAPH_ROOT") or repo_root(os.path.dirname(os.path.abspath(__file__)))
RESERVED = {"id", "sources"}
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")  # a label or link type; the seed backtick-quotes it, so reserved words are safe
SCALAR = (str, int, float, bool)


# ----------------------------------------------------------------------------
# Generic core: reading sources, recording what each one says, finding clashes.
# ----------------------------------------------------------------------------

def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def outside_fences(text):
    """The text with every line inside fenced code blanked, so line numbers stay true."""
    out, fenced = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            out.append("")
        else:
            out.append("" if fenced else line)
    return "\n".join(out)


def same(a, b):
    """Equal in type and value, element by element in a list, so True and 1, or [1] and [1.0], differ."""
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def cells(line):
    """The cells of one table row: one outer pipe is removed from each end, never more."""
    line = line.strip()
    line = line[1:] if line.startswith("|") else line
    line = line[:-1] if line.endswith("|") else line
    return [c.strip() for c in line.split("|")]


SEPARATOR = re.compile(r"\|(\s*:?-+:?\s*\|)+")


def markdown_tables(text):
    """Every pipe table in a markdown text, outside fenced code, as (header, rows) with rows by header cell."""
    tables, lines = [], outside_fences(text).split("\n")
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and lines[i].strip().startswith("|") \
                and SEPARATOR.fullmatch(lines[i + 1].strip()):
            header = cells(lines[i])
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                row = cells(lines[j])
                rows.append({"_line": j + 1, "_cells": len(row), **dict(zip(header, row))})
                j += 1
            tables.append((header, rows))
            i = j
        else:
            i += 1
    return tables


class Graph:
    """Nodes and links with the source that stated each, and the problems met while reading."""

    def __init__(self, root):
        self.root = root
        self.nodes = {}       # id -> {"label", "props", "sources": {source: {prop: value}}}
        self.edges = {}       # (source_id, type, target_id) -> set of sources that state it
        self.problems = []

    def read(self, rel):
        """A source's text, outside fenced code; a missing source is a problem and reads as None."""
        try:
            return outside_fences(read(self.root, rel))
        except FileNotFoundError:
            message = f"{rel}: source is missing"
            if message not in self.problems:
                self.problems.append(message)
            return None

    def node(self, label, ident, source, **props):
        if not NAME.fullmatch(label):
            self.problems.append(f"{ident}: {source} gives the label {label!r}; use letters, digits and _")
            return ident
        n = self.nodes.setdefault(ident, {"label": label, "props": {}, "sources": {}, "labels": {}})
        n["labels"].setdefault(label, set()).add(source)
        stated = n["sources"].setdefault(source, {})
        for key, value in props.items():
            if key in RESERVED:
                self.problems.append(f"{ident}: {source} sets the reserved property {key!r}; rename it")
                continue
            if value is None or value == "":
                continue
            if not (isinstance(value, SCALAR) or (isinstance(value, list) and all(isinstance(v, SCALAR) for v in value))):
                self.problems.append(f"{ident}: {source} gives {key} a {type(value).__name__}; "
                                     "use text, a number, true/false or a list of those")
                continue
            if key in stated and not same(stated[key], value):
                self.problems.append(f"{ident}: {source} states {key} twice: {stated[key]!r} and {value!r}")
                continue
            stated[key] = value
            n["props"].setdefault(key, value)
        return ident

    def link(self, source_id, kind, target_id, source):
        if not NAME.fullmatch(kind):
            self.problems.append(f"{source_id}: {source} gives the link type {kind!r}; use letters, digits and _")
            return
        self.edges.setdefault((source_id, kind, target_id), set()).add(source)

    def problem(self, message):
        self.problems.append(message)

    def clashes(self):
        """A property or label two sources state differently is a clash: report both, choose neither."""
        found = []
        for ident, n in sorted(self.nodes.items()):
            if len(n["labels"]) > 1:
                said = "; ".join(f"{', '.join(sorted(srcs))} {'calls' if len(srcs) == 1 else 'call'} it a {lab}"
                                 for lab, srcs in sorted(n["labels"].items()))
                found.append(f"{ident}: sources disagree on its label: {said}")
            values = {}
            for source, props in n["sources"].items():
                for key, value in props.items():
                    # Keyed by type as well, so True and 1, or "3" and 3, count as different.
                    values.setdefault(key, {}).setdefault((type(value).__name__, repr(value)), []).append(source)
            for key, seen in sorted(values.items()):
                if len(seen) > 1:
                    said = "; ".join(f"{', '.join(sorted(s))} says {v}" for (_, v), s in sorted(seen.items()))
                    found.append(f"{ident}: sources disagree on {key}: {said}")
        return found


def check(graph):
    """Every finding: unreadable sources, clashes, broken or missing links, wrong counts."""
    counts = EXPECTED_COUNTS(graph)  # first, so a missing promise it reports is not lost
    findings = list(graph.problems) + graph.clashes()
    for (src, kind, dst), sources in sorted(graph.edges.items()):
        for end in (src, dst):
            if end not in graph.nodes:
                findings.append(f"{src} -{kind}-> {dst}: {end} is not defined by any source "
                                f"(stated in {', '.join(sorted(sources))})")
    for label, kind, direction, why in REQUIRED_LINKS:
        if direction not in ("out", "in"):
            findings.append(f"REQUIRED_LINKS: {label} {kind} has direction {direction!r}; use 'out' or 'in'")
            continue
        for ident, n in sorted(graph.nodes.items()):
            if n["label"] != label:
                continue
            ends = [e for e in graph.edges if e[1] == kind and (e[0] if direction == "out" else e[2]) == ident]
            if not ends:
                findings.append(f"{ident}: a {label} with no {kind} link ({why})")
    for label, expected, where in counts:
        actual = sum(1 for n in graph.nodes.values() if n["label"] == label)
        if actual != expected:
            findings.append(f"{label}: the sources define {actual}, but {where} says {expected}")
    return findings


def cypher_seed(graph):
    """The graph as one Cypher script, one statement per line."""
    def lit(v):
        return "null" if v is None else json.dumps(v, ensure_ascii=False)
    out = []
    for label in sorted({n["label"] for n in graph.nodes.values()}):
        out.append(f"CREATE CONSTRAINT `{label.lower()}_id` IF NOT EXISTS FOR (n:`{label}`) REQUIRE n.id IS UNIQUE;")
    for ident, n in sorted(graph.nodes.items()):
        props = {"id": ident, **n["props"], "sources": sorted(n["sources"])}
        body = ", ".join(f"`{k}`: {lit(v)}" for k, v in props.items())
        out.append(f"CREATE (:`{n['label']}` {{{body}}});")
    for (src, kind, dst), sources in sorted(graph.edges.items()):
        if src in graph.nodes and dst in graph.nodes:
            out.append(f"MATCH (a {{id: {lit(src)}}}), (b {{id: {lit(dst)}}}) "
                       f"CREATE (a)-[:`{kind}` {{sources: {lit(sorted(sources))}}}]->(b);")
    return "\n".join(out) + "\n"


def run_relate(graph, statement, params):
    """Load the graph into a scratch store, then run the statement on it read-only."""
    if not shutil.which("relate"):
        sys.exit("dsbp_graph: relate is not installed. Install it with: curl -sSfL https://relatedb.ai/install.sh | bash")
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "graph")
        seed = subprocess.run(["relate", "query", "--database", db, "--mode", "jsonl"],
                              input=cypher_seed(graph), capture_output=True, text=True)
        if seed.returncode != 0:
            sys.stderr.write(seed.stdout + seed.stderr)
            sys.exit(seed.returncode)
        args = ["relate", "query", "--database", db, "--read-only", "--mode", "jsonl", "--max-rows", "0"]
        for key, value in params.items():
            args += ["--param", f"{key}={json.dumps(value)}"]
        # --command takes the statement as its value, so a statement starting with - is never a flag.
        p = subprocess.run(args + ["--command", statement], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        sys.stderr.write(p.stdout + p.stderr)
        sys.exit(p.returncode)
    return [line for line in p.stdout.splitlines() if line.startswith("{")]


def usage(text):
    print("usage: dsbp_graph.py " + text, file=sys.stderr)
    return 2


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd, args = (argv[0], argv[1:]) if argv else ("help", [])
    if cmd in ("help", "-h", "--help"):
        if args:
            return usage("help takes no arguments")
        print(__doc__.split("\n\nInstalled")[0].strip())
        return 0
    wanted = {"impact": 1, "query": 1, "summary": 0, "check": 0, "export": 0}
    if cmd not in wanted:
        return usage("summary|check|impact|query|export, or help")
    if len(args) != wanted[cmd]:
        return usage({"impact": "impact ID", "query": "query 'CYPHER'"}.get(cmd, f"{cmd} takes no arguments"))
    graph = build(ROOT)
    if cmd == "impact":
        if args[0] not in graph.nodes:
            print(f"dsbp_graph: no node {args[0]}", file=sys.stderr)
            return 2
        statement = ("MATCH p = (n {id: $id})-[*1..3]-(m) WHERE m <> n "
                     "RETURN m.id AS id, labels(m)[0] AS label, min(length(p)) AS hops ORDER BY hops, id")
        for row in run_relate(graph, statement, {"id": args[0]}):
            print(row)
        return 0
    if cmd == "query":
        for row in run_relate(graph, args[0], {}):
            print(row)
        return 0
    if cmd == "summary":
        labels, kinds = {}, {}
        for n in graph.nodes.values():
            labels[n["label"]] = labels.get(n["label"], 0) + 1
        for (_, kind, _) in graph.edges:
            kinds[kind] = kinds.get(kind, 0) + 1
        print(json.dumps({"nodes": dict(sorted(labels.items())), "links": dict(sorted(kinds.items()))}))
        return 0
    if cmd == "check":
        findings = check(graph)
        for f in findings:
            print("dsbp_graph: " + f, file=sys.stderr)
        print(f"dsbp_graph: {len(findings)} finding(s)" if findings else "dsbp_graph: the sources agree",
              file=sys.stderr if findings else sys.stdout)
        return 1 if findings else 0
    sys.stdout.write(cypher_seed(graph))
    return 0


# ----------------------------------------------------------------------------
# PROJECT: DS_Business_Process. The documents of the build (decision register,
# goal, build status, foundations, registers, batches) and the data files they
# describe. Design: DSBP-DEC-0050. Each check names its kind in the skill's
# check catalog.
# ----------------------------------------------------------------------------

DSBP = "ds_business_process"
REGISTER = f"{DSBP}/registers/decision-register.md"
QUESTIONS = f"{DSBP}/foundations/competency-questions.md"
B3_CHANGES = f"{DSBP}/batches/B3-structure/expected-changes.csv"
SKILL_GAPS = f"{DSBP}/registers/skill-gaps.csv"
BUILD_STATUS = f"{DSBP}/BUILD-STATUS.md"
GOAL = f"{DSBP}/GOAL.md"
STEP4_FACTS = "business_architecture/ontology/step4/canonical-facts.csv"
# The documents whose citations, paths and counts are read: every text file of the build
# except the validation folder, whose tests hold made-up IDs on purpose.
DOC_SUFFIXES = (".md", ".csv", ".yaml")
SKIP_DIRS = {f"{DSBP}/validation"}
# A cited path is checked only when it starts in a folder of this repository or of the build;
# others (a path inside a cited standard's own files) lead outside on purpose.
PATH_ROOTS = {"research", "registers", "foundations", "batches", "validation", "migration", "vision", "reviews",
              "tooling", DSBP, "scripts", "business_architecture", "kpi_store", "skills"}
PATH = re.compile(r"`([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.(?:md|csv|py|ttl|yaml|txt|json))`")
CITE = re.compile(r"DSBP-DEC-(\d{4})((?:(?:,| and|, and| to) \d{4})*)")
# Links one decision's row states to another, and the way each reads. A link is stated on the row
# that holds the phrase; the other row must name it back.
DECISION_LINKS = [
    ("AMENDS", re.compile(r"\bamends (DSBP-DEC-\d{4})")),
    ("REFINES", re.compile(r"\brefines (DSBP-DEC-\d{4})")),
    ("CONFIRMS", re.compile(r"\bConfirms (DSBP-DEC-\d{4})")),
    ("SUPERSEDED_BY", re.compile(r"\bSuperseded on \d{4}-\d{2}-\d{2} by (DSBP-DEC-\d{4})")),
    ("WIDENED_BY", re.compile(r"\bWidened \d{4}-\d{2}-\d{2} [^(]*\((DSBP-DEC-\d{4})\)")),
]
# Promised counts in prose, read where any document states them.
CQ_LOCKED = re.compile(r"\b(\d+) of the (\d+) (?:competency )?questions\b")
CQ_HELD = re.compile(r"\b(\d+) (?:are )?held\b")
B3_KINDS = re.compile(r"\b(\d+) renames, (\d+) moves, (\d+) exclusions\b[^|]*?\b(\d+) new concepts\b")
GAP_ROWS = re.compile(r"`registers/skill-gaps\.csv` \((\d+) rows\b")
FACTS = re.compile(r"\b(\d[\d,]*) Step 4 relationship facts\b")

# (label, link type, "out" or "in", why the link is required)
REQUIRED_LINKS = [
    ("Change", "CITES", "out", "every batch change names the decision that approved it"),
]


def EXPECTED_COUNTS(graph):
    """(label, count, where the count is promised). Read the promise from a source, never type it here."""
    text = graph.read(BUILD_STATUS)
    if text is None:
        return []
    m = GAP_ROWS.search(text)
    if not m:
        graph.problem(f"{BUILD_STATUS}: promises no skill-gap count (expected `registers/skill-gaps.csv` (N rows ...))")
        return []
    return [("SkillGap", int(m.group(1)), BUILD_STATUS)]


def documents(root):
    """Every text file of the build that states citations, paths or counts, sorted."""
    out = []
    for folder, dirs, files in os.walk(os.path.join(root, DSBP)):
        rel_dir = os.path.relpath(folder, root).replace(os.sep, "/")
        dirs[:] = sorted(d for d in dirs if f"{rel_dir}/{d}" not in SKIP_DIRS and not d.startswith("."))
        out += [f"{rel_dir}/{f}" for f in files if f.endswith(DOC_SUFFIXES)]
    return sorted(out)


def cited(text):
    """(line number, decision ID) for every decision a text cites, short and range forms included."""
    out = []
    for no, line in enumerate(text.split("\n"), 1):
        for m in CITE.finditer(line):
            ids, prev = [int(m.group(1))], None
            for sep, num in re.findall(r"(,|, and| and| to) (\d{4})", m.group(2)):
                n = int(num)
                ids += list(range(ids[-1] + 1, n + 1)) if sep == " to" else [n]
            out += [(no, f"DSBP-DEC-{i:04d}") for i in ids]
    return out


def csv_rows(graph, rel):
    text = graph.read(rel)
    if text is None:
        return None
    import csv
    import io
    return list(csv.DictReader(io.StringIO(text)))


def read_register(graph):
    """Decision nodes, and the links between decisions each row states."""
    rows = {}
    for header, table in markdown_tables(graph.read(REGISTER) or ""):
        if header[:3] != ["ID", "Question", "Decision"]:  # the decisions, not the open-questions table
            continue
        for row in table:
            if row["_cells"] != len(header):
                graph.problem(f"{REGISTER}:{row['_line']}: row has {row['_cells']} cells, the header {len(header)}")
                continue
            ident = row["ID"]
            if not re.fullmatch(r"DSBP-DEC-\d{4}", ident):
                graph.problem(f"{REGISTER}:{row['_line']}: {ident!r} is not a decision ID")
                continue
            graph.node("Decision", ident, REGISTER, question=row.get("Question"), date=row.get("Date, place"))
            rows[ident] = (row["_line"], " | ".join(row.get(h, "") for h in header))
    for ident, (line, text) in sorted(rows.items()):
        for kind, pattern in DECISION_LINKS:
            for target in pattern.findall(text):
                graph.link(ident, kind, target, REGISTER)
                if target in rows and not names(rows[target][1], ident):
                    graph.problem(f"{REGISTER}:{line}: {ident} {kind.lower().replace('_', ' ')} {target}, "
                                  f"but {target}'s row does not name {ident}")
    return rows


def names(text, ident):
    """Whether a text names a decision, in its full or four-digit form."""
    return bool(re.search(rf"\b(?:DSBP-DEC-)?{ident[-4:]}\b", text))


def read_questions(graph):
    text = graph.read(QUESTIONS)
    if text is None:
        return
    for no, line in enumerate(text.split("\n"), 1):
        m = re.match(r"(\d+)\. ", line)
        if m:
            graph.node("Question", f"CQ-{int(m.group(1))}", QUESTIONS,
                       status="held" if "*(Held" in line else "locked")


def read_documents(graph):
    """What each document cites, points to and promises."""
    questions = [n for n in graph.nodes.values() if n["label"] == "Question"]
    held = sum(1 for n in questions if n["props"].get("status") == "held")
    b3 = csv_rows(graph, B3_CHANGES) or []
    kinds = {k: sum(1 for r in b3 if r.get("change") == k) for k in ("rename", "move", "exclude", "new")}
    facts = None
    if os.path.exists(os.path.join(graph.root, STEP4_FACTS)):
        facts = len(csv_rows(graph, STEP4_FACTS))
    for rel in documents(graph.root):
        text = graph.read(rel)
        if text is None:
            continue
        graph.node("Document", rel, rel)
        for no, ident in cited(text):
            graph.link(rel, "CITES", ident, f"{rel}:{no}")
        for no, line in enumerate(text.split("\n"), 1):
            where = f"{rel}:{no}"
            for p in PATH.findall(line):
                if p.split("/")[0] not in PATH_ROOTS or "personal-agent-skills" in line:
                    continue
                here = os.path.dirname(rel)
                if any(os.path.exists(os.path.join(graph.root, base, p)) for base in (here, DSBP, "")):
                    continue
                if rel == GOAL:  # a done line promises files a later step makes
                    graph.node("PendingPath", p, where)
                    graph.link(rel, "PROMISES", p, where)
                else:
                    graph.problem(f"{where}: points to {p}, which is not in the repository")
            if questions:
                for locked, total in CQ_LOCKED.findall(line):
                    if (int(locked), int(total)) != (len(questions) - held, len(questions)):
                        graph.problem(f"{where}: says {locked} of {total} questions are locked; "
                                      f"{QUESTIONS} locks {len(questions) - held} of {len(questions)}")
                for n in CQ_HELD.findall(line):
                    if int(n) != held:
                        graph.problem(f"{where}: says {n} questions are held; {QUESTIONS} holds {held}")
            for m in B3_KINDS.findall(line):
                said = dict(zip(("rename", "move", "exclude", "new"), map(int, m)))
                if b3 and said != kinds:
                    graph.problem(f"{where}: says B3 has {said}; {B3_CHANGES} has {kinds}")
            for n in FACTS.findall(line):
                if facts is not None and int(n.replace(",", "")) != facts:
                    graph.problem(f"{where}: says {n} Step 4 facts; {STEP4_FACTS} has {facts}")


def build(root):
    graph = Graph(root)
    read_register(graph)
    read_questions(graph)
    for no, row in enumerate(csv_rows(graph, B3_CHANGES) or [], 2):
        ident = row.get("key") or row.get("baseline_id")  # a new concept has a key, a changed one its baseline ID
        if not ident:
            graph.problem(f"{B3_CHANGES}:{no}: row has neither a key nor a baseline ID")
            continue
        key = graph.node("Change", f"B3:{ident}", B3_CHANGES, change=row.get("change"))
        if row.get("decision"):
            graph.link(key, "CITES", row["decision"], B3_CHANGES)
    for row in csv_rows(graph, SKILL_GAPS) or []:
        graph.node("SkillGap", row.get("id") or row.get(next(iter(row))), SKILL_GAPS)
    read_documents(graph)
    return graph


if __name__ == "__main__":
    sys.exit(main())
