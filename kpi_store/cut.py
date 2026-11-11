"""The cut tool: turns a cleared discovery report into a correction version of the ontology.

    py -m kpi_store.cut --report discovery-report.json [--decisions discovery-report.csv] [--release .] [--approver "<role>"]
    py -m kpi_store.cut --report discovery-report.json --plan      # show what a cut would do, and change nothing

The tool reads the report, shows each row and what it will change, and asks the person who runs it to approve. It
then changes the data-product module's tables, rebuilds the module, writes the package at the correction version,
gives every module that depends on it a correction version too, rebuilds the catalog and the projection manifest,
runs the competency questions, verifies each written package against a fresh build and writes the discovery-run
record. In a Git copy it commits and tags: the cut ends with
its commit and its tag, or it changes nothing. In a plain folder it writes the same files.

All of the work happens in a temporary copy of the release. The release itself changes only after every step has
passed, so a failure leaves it as it was. A report that was cut before changes nothing.

Rules:
- A report is cut only when every row that blocks has a decision.
- A report is a file a person may have edited. An accepted row is refused unless its object, its found value and
  each field of its proposed fix have the form of a name, and the fix names its action's module. The record holds
  a value of any other row only when it has that form. It holds who decided each row, which must be a role or
  initials, and never a row's note.
- `accept` applies the row's proposed fix when a correction can hold it. A fix that adds a concept needs a minor
  version, and a question waits for its answer: the tool lists both and leaves them.
- `reject` changes nothing in the ontology. It becomes a standing decision, so the next comparison leaves the row out.
- `environment setting` changes nothing in the ontology. The tool prints what to write in kpi_store.toml.
- A breaking change needs a typed confirmation. A change is breaking when it changes or removes a name that a query
  or a load may hold: a column whose new name differs by more than case, an object's name, or the removal of a
  column, an object or a table edge. A case-only spelling and an added measure are not breaking.

Needs Python 3.11 or later with rdflib and pyshacl. It needs no Java, no bash and no Git.
"""
import argparse
import ast
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import ontology_view as ov
from . import report as rep

ONTOLOGY = Path("business_architecture") / "ontology"
RUNS = ONTOLOGY / "discovery-runs"
PRICING = ONTOLOGY / "data-product" / "pricing"
EXCEPTIONS = Path("scripts") / "standalone-exceptions.txt"
MODULE = "data-product"
TABLES = ("tables", "lineage", "columns", "agents", "view-systems")
IGNORED = {".git", "__pycache__", ".venv", ".pytest_cache"}
TEXT_SUFFIXES = {".ttl", ".json", ".jsonld", ".md", ".py", ".csv", ".nt", ".txt"}
RUN_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,99}")
NEEDS_MINOR = {"add-measure-link": "a measure link with its filter needs a new property",
               "record-replaces": "the table a Databricks table replaces belongs to the technical-graph module",
               "add-object": "a new object is a new concept",
               "add-edge": "a new table edge is new content"}
# A report is a file that a person may have edited, so the cut takes no text from it on trust. A value goes into
# the record, the standing decisions or the module's tables only when it has the form of the name it stands for.
# A column name is letters, digits, underscores and dollar signs. An object name is one to three such parts, which
# may also hold a hyphen, joined by dots. A table type is capital letters and underscores.
# Every form is applied with fullmatch: with match, a "$" would let a final line end through.
COLUMN_NAME = re.compile(r"[\w$]{1,255}")
PART = r"[\w$-]{1,255}"
NAME_PART = re.compile(PART)
OBJECT_NAME = re.compile(rf"{PART}(?:\.{PART}){{0,2}}")
FULL_NAME = re.compile(rf"{PART}(?:\.{PART}){{2}}")
TABLE_TYPE = re.compile(r"[A-Z][A-Z_]{0,39}")
# The form of the found value, by row kind. A found value of any other kind stays in the report.
FOUND_FORM = {"column-renamed": COLUMN_NAME, "column-case": COLUMN_NAME, "object-renamed": OBJECT_NAME,
              "migration-pair": OBJECT_NAME, "object-extra": TABLE_TYPE}
COLUMN_KINDS = {"column-missing", "column-renamed", "column-case"}
# The form of each field of a proposed fix, for every action the comparison writes: those a correction applies and
# those it leaves for a minor version. A fix's other fields (a Genie filter and its title) are never used or copied.
FIX_FORM = {"rename-column": {"from": COLUMN_NAME, "to": COLUMN_NAME},
            "add-serves-measure": {"view": OBJECT_NAME, "measure": NAME_PART},
            "rename-object": {"from": OBJECT_NAME, "to": FULL_NAME},
            "remove-column": {"column": COLUMN_NAME},
            "remove-edge": {"from": OBJECT_NAME, "to": OBJECT_NAME},
            "remove-object": {"object": OBJECT_NAME},
            "add-measure-link": {"view": OBJECT_NAME, "measure": NAME_PART},
            "add-object": {"object": OBJECT_NAME},
            "add-edge": {"from": OBJECT_NAME, "to": OBJECT_NAME},
            "record-replaces": {"table": OBJECT_NAME, "replaces": OBJECT_NAME},
            "set-catalog-name": {"ontology_catalog": NAME_PART},
            "none": {}}
# The module each action's fix must name. An action that is not here names none.
FIX_MODULE = {**{action: MODULE for action in ("rename-column", "add-serves-measure", "rename-object", "remove-column",
                                               "remove-edge", "remove-object", "add-measure-link", "add-object", "add-edge")},
              "record-replaces": "technical-graph"}
KEPT = "(kept in the report)"
SHA256 = re.compile(r"[0-9a-f]{64}")
RUN_AT = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
# Who decided a row, and who cleared the report: a role or initials. The record is committed, so it takes no free
# text: letters, digits, spaces, dots, hyphens and apostrophes, at most 60 characters, and no run of four digits.
ROLE = re.compile(r"(?:[^\W_]|[ .'-]){1,60}")
ROLE_HELP = ("write a role or initials, such as \"the ontology owner\": letters, digits, spaces, dots, hyphens and "
             "apostrophes, at most 60 characters, and no number of four digits or more")
DEFAULT_APPROVER = "The person who ran the cut"
CHECK_COMMAND = "bash scripts/check.sh"
GIT_PLACE = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_NAMESPACE"}


class CutRefused(Exception):
    """The report or the person's answer stops the cut. Nothing was changed."""


class CutFailed(Exception):
    """A step of the cut failed. The release is as it was before the cut."""


class CutIncomplete(Exception):
    """The cut is committed and Git could not tag it. Running the same command again finishes the tag."""


@dataclass
class Item:
    """One report row and what the cut does with it."""
    row: dict
    outcome: str                    # apply, already applied, needs a minor version, waits, rejected,
    #                                 environment setting, no decision, not applied
    text: str                       # what changes, or why nothing does
    breaking: bool = False
    confirm: str = ""               # what the person types to confirm a breaking change
    changes: list = field(default_factory=list)   # [(file, before, after)]


@dataclass
class Plan:
    report: dict
    items: list
    versions: dict                  # {module: (current version, correction version)}, in release order; empty when no row applies
    tables: object                  # the pricing tables with every applied row's change
    already_cut: bool = False       # the release holds this run's record already

    @property
    def applied(self):
        return [i for i in self.items if i.outcome == "apply"]


@dataclass
class Outcome:
    status: str                     # cut, recorded (decisions only, no version), already cut, planned
    plan: Plan
    record: Path | None = None      # the discovery-run record, relative to the release root
    files: list = field(default_factory=list)       # every path the cut changed, added or removed
    committed: bool = False
    tag: str = ""
    messages: list = field(default_factory=list)    # what the person still does


# ---------- the module's input tables ----------

class Tables:
    """The data-product module's pricing tables, the files that build_pricing.py reads."""

    def __init__(self, release_root):
        self.rows, self.fields = {}, {}
        for name in TABLES:
            path = Path(release_root) / PRICING / f"{name}.csv"
            try:
                with path.open(encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    self.rows[name], self.fields[name] = list(reader), list(reader.fieldnames or [])
            except OSError:
                raise CutRefused(f"{path} is missing: this folder is not a KPI Store release") from None

    def text(self, name):
        out = io.StringIO(newline="")
        writer = csv.DictWriter(out, self.fields[name], lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.rows[name])
        return out.getvalue()

    def write(self, release_root):
        for name in TABLES:
            _write(Path(release_root) / PRICING / f"{name}.csv", self.text(name))

    def slug(self, full_name):
        """The table's slug from its full name. The catalog is left out when the full name matches none, because
        a report names the object as this environment spells its catalog."""
        tables = self.rows["tables"]
        found = [t["slug"] for t in tables if t["name"].lower() == full_name.lower()]
        if not found:
            rest = full_name.lower().split(".", 1)[-1]
            found = [t["slug"] for t in tables if t["name"].lower().split(".", 1)[-1] == rest]
        if len(found) != 1:
            raise Unappliable(f"the ontology's tables name {full_name} {len(found)} times")
        return found[0]

    def name(self, slug):
        return next(t["name"] for t in self.rows["tables"] if t["slug"] == slug)


class Unappliable(Exception):
    """An accepted row's fix does not fit the tables."""


def _file(name):
    return (PRICING / f"{name}.csv").as_posix()


def _rename_column(tables, row, fix):
    slug, old, new = tables.slug(row["object"]), fix["from"], fix["to"]
    changes = []
    for mine, table_key, column_key in (("column", "table", "column"), ("source column", "from_table", "from_column")):
        for r in tables.rows["columns"]:
            if r[table_key] == slug and r[column_key] == old:
                r[column_key] = new
                changes.append((_file("columns"), f"{slug} {mine} {old}", f"{slug} {mine} {new}"))
    if not changes:
        held = any((r["table"], r["column"]) == (slug, new) or (r["from_table"], r["from_column"]) == (slug, new)
                   for r in tables.rows["columns"])
        if held:
            return None
        raise Unappliable(f"the ontology's tables hold no column {old} of {tables.name(slug)}")
    breaking = old.lower() != new.lower()
    return (f"column {old} of {tables.name(slug)} becomes {new}" + ("" if breaking else " (case only)"), breaking, new, changes)


def _add_serves_measure(tables, row, fix):
    slug, measure = tables.slug(fix["view"]), fix["measure"]
    table = next(t for t in tables.rows["tables"] if t["slug"] == slug)
    served = [m for m in table["serves_measures"].split(";") if m]
    if measure in served:
        return None
    table["serves_measures"] = ";".join(served + [measure])
    return (f"{table['name']} also serves the measure {measure}", False, "",
            [(_file("tables"), f"{slug} serves {';'.join(served) or 'no measure'}", f"{slug} serves {table['serves_measures']}")])


def _rename_object(tables, row, fix):
    if any(t["name"].lower() == fix["to"].lower() for t in tables.rows["tables"]):
        return None
    slug = tables.slug(fix["from"])
    table = next(t for t in tables.rows["tables"] if t["slug"] == slug)
    old, table["name"] = table["name"], fix["to"]
    return (f"object {old} becomes {fix['to']}", True, fix["to"], [(_file("tables"), f"{slug} named {old}", f"{slug} named {fix['to']}")])


def _remove_column(tables, row, fix):
    slug, column = tables.slug(row["object"]), fix["column"]
    keep = [r for r in tables.rows["columns"]
            if (r["table"], r["column"]) != (slug, column) and (r["from_table"], r["from_column"]) != (slug, column)]
    gone = len(tables.rows["columns"]) - len(keep)
    if not gone:
        return None
    tables.rows["columns"] = keep
    return (f"column {column} of {tables.name(slug)} is removed", True, column,
            [(_file("columns"), f"{gone} row(s) name {slug} column {column}", "removed")])


def _remove_edge(tables, row, fix):
    down, up = tables.slug(fix["from"]), tables.slug(fix["to"])
    lineage = [r for r in tables.rows["lineage"] if (r["table"], r["derived_from"]) != (down, up)]
    if len(lineage) == len(tables.rows["lineage"]):
        return None
    columns = [r for r in tables.rows["columns"] if (r["table"], r["from_table"]) != (down, up)]
    changes = [(_file("lineage"), f"{down} is derived from {up}", "removed")]
    if len(columns) != len(tables.rows["columns"]):
        changes.append((_file("columns"), f"{len(tables.rows['columns']) - len(columns)} row(s) from {up} to {down}", "removed"))
    tables.rows["lineage"], tables.rows["columns"] = lineage, columns
    return (f"the edge from {tables.name(up)} to {tables.name(down)} is removed", True, tables.name(up), changes)


def _remove_object(tables, row, fix):
    try:
        slug = tables.slug(fix["object"])
    except Unappliable:
        return None
    name, changes = tables.name(slug), []
    for table, keys in (("tables", ("slug",)), ("lineage", ("table", "derived_from")), ("columns", ("table", "from_table")),
                        ("view-systems", ("view",))):
        keep = [r for r in tables.rows[table] if all(r[k] != slug for k in keys)]
        if len(keep) != len(tables.rows[table]):
            changes.append((_file(table), f"{len(tables.rows[table]) - len(keep)} row(s) name {slug}", "removed"))
            tables.rows[table] = keep
    for agent in tables.rows["agents"]:
        uses = [u for u in agent["uses"].split(";") if u]
        if slug in uses:
            agent["uses"] = ";".join(u for u in uses if u != slug)
            changes.append((_file("agents"), f"{agent['slug']} uses {slug}", "removed"))
    return (f"object {name} is removed", True, name, changes)


APPLY = {"rename-column": _rename_column, "add-serves-measure": _add_serves_measure, "rename-object": _rename_object,
         "remove-column": _remove_column, "remove-edge": _remove_edge, "remove-object": _remove_object}


# ---------- reading the report and planning ----------

def load_report(report_path, decisions=None):
    """The validated report, and the SHA-256 of each file read. `report_path` is the JSON file, or the cleared CSV
    when the JSON file of the same name lies beside it. `decisions` is a cleared CSV to apply to the JSON file."""
    report_path = Path(report_path)
    if report_path.suffix.lower() == ".csv":
        report_path, decisions = report_path.with_suffix(".json"), decisions or report_path
    try:
        report = rep.read(report_path)
        sums = {"report": _sha(report_path.read_bytes())}
        if decisions:
            report = rep.apply_csv_decisions(report, decisions)
            sums["decisions"] = _sha(Path(decisions).read_bytes())
    except (rep.ReportError, OSError, KeyError) as err:
        raise CutRefused(f"the report cannot be read: {err}") from None
    run = report["run"]
    if not RUN_ID.fullmatch(run["id"]):
        raise CutRefused(f"the report's run ID {run['id']!r} cannot name a file")
    # The record copies these, so each must have its form.
    if not RUN_AT.fullmatch(run["at"]) or not SHA256.fullmatch(run["settings_sha256"]) or not SHA256.fullmatch(run["zip_sha256"]):
        raise CutRefused("the report's run must hold its time as <date>T<time>Z and two SHA-256 checksums in lower-case hexadecimal")
    newest = ov.release_scripts_newest()
    odd = sorted(m for m, v in report["ontology"].items() if not NAME_PART.fullmatch(m) or newest.version_key(v) is None)
    if odd:
        raise CutRefused(f"the report's ontology versions are not module names with versions: {', '.join(repr(m) for m in odd)}")
    for row in report["rows"]:
        if row["decided_by"] and not is_role(row["decided_by"]):
            raise CutRefused(f"row {row['id']}: its 'decided by' is not a role or initials. In the report, {ROLE_HELP}.")
    return report, sums


def is_role(text):
    """True when the text names who decided in the form the record may hold: a role or initials."""
    return isinstance(text, str) and bool(ROLE.fullmatch(text)) and text == text.strip() and not re.search(r"\d{4}", text)


def record_path(report):
    return RUNS / f"{report['run']['id']}.md"


def plan(report, release_root, sums=None):
    """A Plan: what a cut of this report does to this release. It reads the release and changes nothing."""
    root = Path(release_root)
    tables = Tables(root)
    record = root / record_path(report)
    if record.is_file():
        cut_from = re.search(r"^\| Report checksum \(SHA-256\) \| ([0-9a-f]{64}) \|$", record.read_text(encoding="utf-8"), re.M)
        if sums and cut_from and cut_from.group(1) != sums["report"]:
            raise CutRefused(f"{record_path(report).as_posix()} records a cut of this run from another report file. "
                             "A run is cut once: run the discovery again to get a new report.")
        return Plan(report, [], {}, tables, already_cut=True)
    try:
        release = ov.release_name(root)
        held = ov.newest_versions(root / ov.RELEASES)
    except ov.ReleaseError as err:
        raise CutRefused(str(err)) from None
    if report["release"] != release:
        raise CutRefused(f"the report is of {report['release']}, and this folder holds {release}")
    read, now = report["ontology"].get(MODULE), held.get(MODULE)
    if read != now:
        raise CutRefused(f"the report read {MODULE} {read}, and this release holds {MODULE} {now}. "
                         "Run the discovery again on this release.")
    open_rows = [r["id"] for r in report["rows"] if r["blocks"] and not r["decision"]]
    if open_rows:
        raise CutRefused(f"the report is not cleared. Rows that block the load and have no decision: {', '.join(open_rows)}")
    items = [_item(row, tables) for row in report["rows"]]
    versions = _versions(root) if any(i.outcome == "apply" for i in items) else {}
    return Plan(report, items, versions, tables)


def _item(row, tables):
    fix, decision = row["proposed_fix"], row["decision"]
    action = fix.get("action", "none")
    if decision == "reject":
        return Item(row, "rejected", "no change; a standing decision keeps the row out of the next comparison")
    if decision == "accept":
        _check_fix(row, action)   # before anything else: an accepted row is refused unless it holds names only
    if _is_setting(row):
        return Item(row, "environment setting", _setting(row))
    if action == "none" and row["kind"] == "question":
        return Item(row, "waits", "a question for the owner; no change is proposed")
    if not decision:
        return Item(row, "no decision", "left as it is")
    if action in NEEDS_MINOR:
        return Item(row, "needs a minor version", NEEDS_MINOR[action])
    if action == "none":
        return Item(row, "not applied", "the row proposes no change")
    try:
        done = APPLY[action](tables, row, fix)
    except Unappliable as err:
        raise CutRefused(f"row {row['id']} cannot be applied: {err}") from None
    except KeyError as err:
        raise CutRefused(f"row {row['id']}: its proposed fix lacks {err}") from None
    if done is None:
        return Item(row, "already applied", "the ontology holds this change already")
    text, breaking, confirm, changes = done
    return Item(row, "apply", text, breaking, confirm, changes)


def _is_setting(row):
    """True when the row's decision makes it a line for kpi_store.toml."""
    return row["decision"] == "environment setting" or (row["decision"] == "accept" and row["proposed_fix"].get("action") == "set-catalog-name")


def _check_fix(row, action):
    """Stops the cut when an accepted row holds anything but names, whatever the cut then does with the row: the
    action must be one the comparison writes, its fix must name the action's module, and the object, the found value
    and each field of the fix must have the form of the name they stand for. A row that proposes no change has no
    object to apply, so its object is left to the record's own rule (_recorded)."""
    fix = row["proposed_fix"]

    def refuse(what):
        raise CutRefused(f"row {row['id']} cannot be applied: {what}. Correct the report, or reject the row.")
    if action not in FIX_FORM:
        refuse("its proposed fix names an action the cut does not know")
    if action in FIX_MODULE and fix.get("module") != FIX_MODULE[action]:
        refuse(f"its proposed fix names a module other than {FIX_MODULE[action]}")
    for key, form in FIX_FORM[action].items():
        if not isinstance(fix.get(key), str) or not form.fullmatch(fix[key]):
            refuse(f"the '{key}' of its proposed fix is not a name")
    if action != "none" and not OBJECT_NAME.fullmatch(row["object"]):
        refuse("its object is not an object name")
    form = FOUND_FORM.get(row["kind"])
    if form and row["found_value"] and not form.fullmatch(row["found_value"]):
        refuse("its found value is not a name")


def _recorded(row):
    """The row's object, ontology value and found value as the record and the standing decisions may hold them:
    each as it is when it has the form of a name, and "(kept in the report)" otherwise. Evidence, query results,
    Genie filter text and anything a person typed into these fields stay in the report."""
    def name(value, form):
        return value if not value or (form and form.fullmatch(value)) else KEPT
    return (name(row["object"], OBJECT_NAME),
            name(row["ontology_value"], COLUMN_NAME if row["kind"] in COLUMN_KINDS else OBJECT_NAME),
            name(row["found_value"], FOUND_FORM.get(row["kind"])))


def _setting(row):
    fix = row["proposed_fix"]
    if fix.get("action") == "set-catalog-name":
        catalog = fix.get("ontology_catalog")
        catalog = catalog if isinstance(catalog, str) and NAME_PART.fullmatch(catalog) else "the ontology's catalog name"
        return f"in kpi_store.toml, under [names], set {catalog} to the name this environment gives that catalog"
    return (f"record this difference in kpi_store.toml ([names] for a catalog's name, [skip] for a schema or a table "
            f"to leave out); the ontology keeps {_recorded(row)[1] or _recorded(row)[0]}")


def _versions(root):
    """{module: (current, correction version)} for data-product and every module that depends on it, in the order
    to release them."""
    release = root / ONTOLOGY / "release"
    modules = _modules(release / "build_module.py")
    newest = ov.release_scripts_newest(root)
    order = _run("list the modules to release", ["dependents.py", MODULE], release).split()
    versions = {}
    for module in order:
        spec = modules[module]
        if spec.get("stage") is not None:
            raise CutRefused(f"{module} {spec['version']} is a release candidate; release it before a correction")
        versions[module] = (spec["version"], newest.correction_version(spec["version"]))
    return versions


def _modules(builder):
    """build_module.py's MODULES table, read without importing the builder."""
    for node in ast.parse(builder.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "MODULES":
            return ast.literal_eval(node.value)
    raise CutRefused(f"{builder} holds no MODULES table")


def describe(plan_):
    """The plan as lines for the person who approves it."""
    report = plan_.report
    lines = [f"Discovery run {report['run']['id']} of {report['release']}: {len(report['rows'])} rows."]
    if plan_.already_cut:
        return lines + [f"This run was cut before: {record_path(report).as_posix()} records it. Nothing to do."]
    for title, outcomes in (("The cut applies", ("apply",)), ("Already in the ontology", ("already applied",)),
                            ("Needs a minor version, so the cut leaves it", ("needs a minor version",)),
                            ("Waits, so the cut leaves it", ("waits",)),
                            ("Rejected, recorded as a standing decision", ("rejected",)),
                            ("Environment settings, for kpi_store.toml", ("environment setting",)),
                            ("Not applied", ("not applied",)), ("No decision", ("no decision",))):
        chosen = [i for i in plan_.items if i.outcome in outcomes]
        if not chosen:
            continue
        lines.append(f"{title} ({len(chosen)}):")
        for i in chosen:
            mark = "  BREAKING" if i.breaking else ""
            where = "" if i.outcome == "apply" else f"{_recorded(i.row)[0]}: "
            lines.append(f"  {i.row['id']} {i.row['kind']}: {where}{i.text}{mark}")
            lines += [f"      {file}: {before} -> {after}" for file, before, after in i.changes]
    if plan_.versions:
        lines.append("Versions the cut writes:")
        lines += [f"  {m} {old} -> {new}" for m, (old, new) in plan_.versions.items()]
    else:
        lines.append("No row changes the ontology, so the cut writes no version.")
    return lines


# ---------- the cut ----------

def cut(report_path, release_root=".", decisions=None, approver=None, ask=input, say=print, now=None, plan_only=False,
        before_step=None):
    """Cuts the report into the release and returns an Outcome. `ask(prompt)` returns what the person typed and
    `say(line)` shows a line. `before_step(name)` is called before each step, for a caller that follows progress.
    Raises CutRefused when the report, the Git copy or an answer stops the cut and CutFailed when a step fails; the
    release is unchanged in both cases. In a Git copy a cut ends with its commit and its tag, or changes nothing.
    The one exception raises CutIncomplete: the commit is made and Git could not tag it. The same call again
    finishes the tag."""
    root = Path(release_root).resolve()
    _requirements()
    if approver is not None and not is_role(approver):
        raise CutRefused(f"--approver is not a role or initials: {ROLE_HELP}.")
    report, sums = load_report(report_path, decisions)
    plan_ = plan(report, root, sums)
    for line in describe(plan_):
        say(line)
    if plan_only:
        return Outcome("already cut" if plan_.already_cut else "planned", plan_, record_path(report) if plan_.already_cut else None)
    if plan_.already_cut:
        outcome = Outcome("already cut", plan_, record_path(report))
        if _finish_tag(root, report, outcome, say):
            _follow_up(report, True, outcome, say)
        return outcome
    git = _git_ready(root, plan_)
    for item in plan_.applied:
        if item.breaking:
            typed = ask(f"Row {item.row['id']} is a breaking change: {item.text}. Type {item.confirm} to confirm: ")
            if typed.strip() != item.confirm:
                raise CutRefused(f"row {item.row['id']} was not confirmed; nothing was changed")
    what = "these versions" if plan_.versions else "the record of these decisions, with no new version"
    if ask(f"Type yes to cut {what}: ").strip().lower() != "yes":
        raise CutRefused("the cut was not approved; nothing was changed")
    now = now or dt.datetime.now(dt.timezone.utc)
    step = _Steps(say, before_step)
    with tempfile.TemporaryDirectory(prefix="kpi-store-cut-") as tmp:
        staging, backup = Path(tmp) / "release", Path(tmp) / "backup"
        step("copy the release", lambda: shutil.copytree(root, staging, ignore=shutil.ignore_patterns(*IGNORED)))
        _build(plan_, staging, approver, now, step)
        step("write the standing decisions", lambda: _write_standing(plan_, staging))
        files = _difference(root, staging)
        record = _record(plan_, sums, approver, now, sorted(set(files) | {record_path(report).as_posix()}))
        _write(staging / record_path(report), record)
        files = _difference(root, staging)
        step("write the release", lambda: _apply(root, staging, files, backup))
        outcome = Outcome("cut" if plan_.versions else "recorded", plan_, record_path(report), sorted(files))
        try:
            # Inside the temporary folder: a failed commit restores the release from the backup kept there.
            _commit(root, git, plan_, outcome, backup)
        except CutIncomplete:
            _follow_up(report, bool(plan_.versions), outcome, say)   # the cut is made, so what follows it still applies
            raise
    say(f"Done. The record is {record_path(report).as_posix()}; the cut changed {len(files)} files.")
    _follow_up(report, bool(plan_.versions), outcome, say)
    return outcome


def _follow_up(report, wrote_version, outcome, say):
    """What the person does after a cut: each environment setting, and the full check when a version was written.
    Shown on every path that ends with a cut or with a finished tag, and kept in the outcome's messages."""
    messages = [f"Row {row['id']}: {_setting(row)}." for row in report["rows"] if _is_setting(row)]
    if wrote_version:
        messages.append(f"Run the full check before you load: {CHECK_COMMAND} (on Windows, in Git Bash; the runner does it).")
    for message in messages:
        outcome.messages.append(message)
        say(message)


class _Steps:
    def __init__(self, say, before_step):
        self.say, self.before_step = say, before_step

    def __call__(self, name, action):
        self.say(f"... {name}")
        try:
            if self.before_step:
                self.before_step(name)
            return action()
        except (CutFailed, CutRefused):
            raise
        except Exception as err:
            raise CutFailed(f"the step '{name}' failed: {type(err).__name__}: {err}. The release is as it was.") from err


def _requirements():
    missing = [name for name in ("rdflib", "pyshacl") if not _importable(name)]
    if missing:
        raise CutRefused(f"the cut needs the Python package{'s' if len(missing) > 1 else ''} {' and '.join(missing)}: "
                         f"py -m pip install {' '.join(missing)}")


def _importable(name):
    import importlib.util
    return importlib.util.find_spec(name) is not None


def _run(name, args, cwd):
    """Runs one of the release's own scripts with this Python, without a shell, and returns what it printed."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    done = subprocess.run([sys.executable, "-B", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                          env=env, check=False)
    if done.returncode != 0:
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-25:])
        raise CutFailed(f"the step '{name}' failed ({' '.join(args)}):\n{tail}\nThe release is as it was.")
    return done.stdout


def _approval(report):
    return f"Typed yes to approve the cut of discovery run {report['run']['id']}."


def _build(plan_, staging, approver, now, step):
    """Every change of the cut, made in the staging copy."""
    report = plan_.report
    if not plan_.versions:
        return
    ontology, release = staging / ONTOLOGY, staging / ONTOLOGY / "release"
    record = record_path(report)
    step("write the module's tables", lambda: plan_.tables.write(staging))
    step("rebuild the module's Turtle", lambda: _run("rebuild the module's Turtle", ["build_pricing.py", "--write"], ontology / MODULE))
    # The package's manifest names the record only when the file exists, so a first copy is written before the build.
    _write(staging / record, f"# Discovery run {report['run']['id']}\n")
    where = record.relative_to(ONTOLOGY).as_posix()
    rows = ", ".join(i.row["id"] for i in plan_.applied)
    for module, (old, new) in plan_.versions.items():
        why = (f"A correction from discovery run {report['run']['id']}, rows {rows}: "
               + "; ".join(i.text for i in plan_.applied) + f". Record: {where}." if module == MODULE else
               f"Takes the correction version of what it requires (discovery run {report['run']['id']}); nothing else "
               f"changes. Record: {where}.")
        args = ["next_version.py", "start", module, new, "patch", "--why", why, "--approver", approver or DEFAULT_APPROVER,
                "--where", where, "--words", _approval(report), "--date", now.strftime("%Y-%m-%d")]
        step(f"set {module} to {new}", lambda args=args, module=module: _run(f"set {module}", args, release))
        step(f"write the {module} package", lambda module=module: _run(f"write the {module} package",
                                                                         ["build_module.py", module, "--write"], release))
    for module, (old, new) in plan_.versions.items():
        step(f"move {module} {old} to releases/previous", lambda module=module, old=old: _run(
            f"move {module} {old}", ["next_version.py", "finish", module, old], release))
    step("carry the stand-alone exceptions to the moved packages", lambda: _carry_exceptions(staging, plan_.versions))
    step("rebuild the catalog", lambda: _run("rebuild the catalog", ["build_catalog.py", "--write"], release))
    step("rebuild the projection manifest", lambda: _run("rebuild the projection manifest", ["pipeline.py", "build"], ontology / "projection"))
    step("run the competency questions", lambda: _run("run the competency questions", ["run.py"], ontology / "regression"))
    # The checks of scripts/check.sh that need no bash and that this cut can change: each written file must equal
    # a fresh build of its source. The projection manifest was built one step ago by the same code.
    verify = [("the module's Turtle", ["build_pricing.py", "--verify"], ontology / MODULE)]
    verify += [(f"the {module} package", ["build_module.py", module, "--verify"], release) for module in plan_.versions]
    verify += [("the catalog", ["build_catalog.py", "--verify"], release)]
    for name, args, cwd in verify:
        step(f"verify {name}", lambda name=name, args=args, cwd=cwd: _run(f"verify {name}", args, cwd))
    step("check that the release agrees with itself", lambda: _agreement(plan_, staging))


def _agreement(plan_, staging):
    """The checks a load makes before it reads the release: each version is the newest folder and the catalog's
    newest, the projection manifest names it, and the data-product package holds every applied change."""
    from rdflib import Graph, Namespace
    releases = staging / ov.RELEASES
    held = ov.newest_versions(releases)
    listed = {str(d).rsplit("/", 2)[-2]: str(d).rsplit("/", 1)[-1] for d in Graph().parse(releases / "catalog.ttl", format="turtle")
              .objects(None, Namespace("http://www.w3.org/ns/dcat#").dataset)}
    manifest = json.loads((staging / ONTOLOGY / "projection" / "projection-manifest.json").read_text(encoding="utf-8"))
    for module, (old, new) in plan_.versions.items():
        if held.get(module) != new or listed.get(module) != new:
            raise CutFailed(f"{module}: the newest folder is {held.get(module)} and the catalog lists {listed.get(module)}, not {new}")
        if f"releases/{module}/{new}/{module}.ttl" not in manifest["inputs"]:
            raise CutFailed(f"the projection manifest does not name {module} {new}")
        if not (releases / "previous" / module / old / "manifest.json").is_file():
            raise CutFailed(f"{module} {old} is not in releases/previous")
    after = Tables(staging)
    for name in TABLES:
        if after.text(name) != plan_.tables.text(name):
            raise CutFailed(f"{name}.csv does not hold the planned change")
    view = ov.read(staging)
    columns = {(c.table.lower(), c.name) for c in view.columns}
    for item in plan_.applied:
        fix = item.row["proposed_fix"]
        if fix["action"] == "rename-column":
            table = plan_.tables.name(plan_.tables.slug(item.row["object"])).lower()
            if (table, fix["to"]) not in columns or (table, fix["from"]) in columns:
                raise CutFailed(f"the {MODULE} package does not hold row {item.row['id']}'s change")


def _carry_exceptions(staging, versions):
    """The stand-alone check lists, by path, text that a released package holds and may keep. A cut moves each old
    package and writes a new one with the same changelog, so each such line follows its package to
    releases/previous/, and the new package gets a line when it holds the same text as often."""
    path = staging / EXCEPTIONS
    if not path.is_file():
        return
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split(" :: ")]
        moved = None
        if len(parts) == 5 and not line.startswith("#"):
            for module, (old, new) in versions.items():
                prefix = f"{(ONTOLOGY / 'releases' / module / old).as_posix()}/"
                if parts[0].startswith(prefix):
                    moved = (module, old, new, parts[0][len(prefix):])
        if not moved:
            out.append(line)
            continue
        module, old, new, name = moved
        out.append(" :: ".join([f"{(ONTOLOGY / 'releases' / 'previous' / module / old).as_posix()}/{name}", *parts[1:]]))
        fresh = staging / ONTOLOGY / "releases" / module / new / name
        if fresh.is_file() and str(fresh.read_text(encoding="utf-8").count(parts[2])) == parts[3]:
            out.append(" :: ".join([f"{(ONTOLOGY / 'releases' / module / new).as_posix()}/{name}", *parts[1:]]))
    _write(path, "\n".join(out) + "\n")


def _write_standing(plan_, staging):
    rejected = [i.row for i in plan_.items if i.outcome == "rejected"]
    if not rejected:
        return
    path = staging / rep.STANDING_DECISIONS
    held = json.loads(path.read_text(encoding="utf-8"))["decisions"] if path.is_file() else []
    keys = {d["key"] for d in held}
    for row in rejected:
        if rep.standing_key(row) not in keys:
            held.append({"key": rep.standing_key(row), "kind": row["kind"], "object": _recorded(row)[0],
                         "ontology_value": _recorded(row)[1], "decision": "reject", "run": plan_.report["run"]["id"]})
    _write(path, json.dumps({"format": 1, "decisions": held}, indent=2, ensure_ascii=False) + "\n")


# ---------- the discovery-run record ----------

def _cell(text):
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip() or " "


def _record(plan_, sums, approver, now, files):
    report, run = plan_.report, plan_.report["run"]
    cut_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    head = [("Run", run["id"]), ("Run at", run["at"]), ("Release", report["release"]),
            ("Report checksum (SHA-256)", sums["report"])]
    if "decisions" in sums:
        head.append(("Decisions file checksum (SHA-256)", sums["decisions"]))
    head += [("Settings checksum (SHA-256)", run["settings_sha256"]), ("Release zip checksum (SHA-256)", run["zip_sha256"]),
             ("Ontology the report read", ", ".join(f"{m} {v}" for m, v in sorted(report["ontology"].items()))),
             ("Cut at", cut_at), ("Cleared by", approver or "Not given"),
             ("Approval", f"{_approval(report)} The person who ran the cut typed it at {cut_at}.")]
    lines = [f"# Discovery run {run['id']}", "",
             "The record of one cut: the decisions on a discovery report and what they changed in the ontology. "
             "The cut tool wrote it. The report itself is not kept in this folder.", "",
             "| Field | Value |", "|---|---|"]
    lines += [f"| {k} | {_cell(v)} |" for k, v in head]
    lines += ["", "## Versions written", ""]
    if plan_.versions:
        lines += ["| Module | From | To | Why |", "|---|---|---|---|"]
        rows = ", ".join(i.row["id"] for i in plan_.applied)
        lines += [f"| {m} | {old} | {new} | {'Rows ' + rows if m == MODULE else 'Requires the correction version of a module above'} |"
                  for m, (old, new) in plan_.versions.items()]
    else:
        lines.append("None. No accepted row changed the ontology.")
    lines += ["", "## Rows", "", "| Row | Kind | Blocks | Object | Ontology value | Found value | Decision | Decided by | Outcome | Why |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for i in plan_.items:
        r = i.row
        # "Why" is the tool's own wording. The person's note stays in the report.
        lines.append("| " + " | ".join(_cell(c) for c in (
            r["id"], r["kind"], "yes" if r["blocks"] else "no", *_recorded(r),
            r["decision"] or "none", r["decided_by"], i.outcome, i.text)) + " |")
    lines += ["", "## Changes", ""]
    changes = [(i.row["id"], *c) for i in plan_.applied for c in i.changes]
    if changes:
        lines += ["| Row | File | Before | After |", "|---|---|---|---|"]
        lines += ["| " + " | ".join(_cell(c) for c in change) + " |" for change in changes]
    else:
        lines.append("None.")
    lines += ["", "## Files the cut changed", ""] + [f"- `{f}`" for f in files] + [""]
    return "\n".join(lines)


# ---------- from the staging copy to the release ----------

def _files(root):
    out = {}
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED)
        for name in names:
            path = Path(folder) / name
            out[path.relative_to(root).as_posix()] = path
    return out


def _difference(root, staging):
    """Every path that differs between the release and the staging copy. A text file a script wrote with CRLF line
    ends (Windows) is first set back to LF, so a cut writes the same bytes on every platform."""
    before, after = _files(root), _files(staging)
    changed = []
    for rel, path in after.items():
        data = path.read_bytes()
        if rel in before and before[rel].read_bytes() == data:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES and b"\r\n" in data:
            data = data.replace(b"\r\n", b"\n")
            path.write_bytes(data)
            if rel in before and before[rel].read_bytes() == data:
                continue
        changed.append(rel)
    return sorted(changed + [rel for rel in before if rel not in after])


def _apply(root, staging, files, backup):
    """Writes the changed files into the release, keeping a copy of each file it replaces or removes in `backup`.
    A failure puts every file back."""
    done = []
    try:
        for rel in files:
            target, source, kept = root / rel, staging / rel, backup / rel
            if target.exists():
                kept.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, kept)
            done.append(rel)
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            else:
                target.unlink()
    except BaseException:
        _restore(root, done, backup)
        raise
    _prune(root, files)


def _restore(root, files, backup):
    """Puts back exactly the paths the cut wrote: a file the cut changed or removed is copied back from the backup,
    and a file the cut created is deleted. No other path is touched. Returns the paths it could not put back, each
    with its state; an empty list means the release's files are as they were."""
    failed = []
    for rel in files:
        target, kept = root / rel, backup / rel
        try:
            if kept.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(kept, target)
            elif target.exists():
                target.unlink()
        except OSError as err:
            state = "still holds the cut's content" if kept.is_file() else "is a file the cut created and could not be deleted"
            failed.append(f"{rel} ({state}: {type(err).__name__})")
    _prune(root, files)
    return failed


def _prune(root, files):
    """Removes each folder the change left empty."""
    for folder in sorted({(root / rel).parent for rel in files}, key=lambda p: len(p.parts), reverse=True):
        while folder != root and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent


# ---------- Git, when the release is a Git copy ----------

def _git(root, *args, stdin=None):
    # A caller such as a Git hook sets these to its own repository; the cut works on the release it was given.
    env = {k: v for k, v in os.environ.items() if k not in GIT_PLACE}
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", env=env,
                          input=stdin, check=False)


def _paths(files):
    """The paths as Git reads them from standard input, so a cut of many files meets no limit on a command's length."""
    return "\0".join(files) + "\0"


def _git_state(root):
    """"none" for a plain folder, "no git" for a Git copy on a machine without Git, "dirty" when the copy has changes
    that are not committed, "no author" when Git has no user.name or user.email, else "ready"."""
    if not (root / ".git").exists():
        return "none"
    if not shutil.which("git"):
        return "no git"
    if _git(root, "status", "--porcelain").stdout.strip():
        return "dirty"
    if any(not _git(root, "config", key).stdout.strip() for key in ("user.name", "user.email")):
        return "no author"
    return "ready"


def _tag(plan_):
    return f"{MODULE}-{plan_.versions[MODULE][1]}" if plan_.versions else ""


def _tag_exists(root, tag):
    return _git(root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode == 0


def _git_ready(root, plan_):
    """Everything Git needs for the commit and the tag, checked before any file changes. Returns "none" for a plain
    folder and "ready" for a Git copy; anything else stops the cut."""
    state = _git_state(root)
    plain = "A plain folder, one with no .git folder, needs no Git."
    if state == "no git":
        raise CutRefused(f"this folder is a Git copy, and Git is not installed, so the cut could not commit. Install Git, then cut. {plain}")
    if state == "dirty":
        raise CutRefused("this Git copy has changes that are not committed. Commit them or put them aside, then cut.")
    if state == "no author":
        raise CutRefused("this Git copy has no user.name or user.email, so the cut could not commit. Run these two commands, "
                         'then cut:\n  git config user.name "<your name or role>"\n  git config user.email "<your e-mail address>"\n' + plain)
    tag = _tag(plan_)
    if state == "ready" and tag and _tag_exists(root, tag):
        raise CutRefused(f"this Git copy already has the tag {tag}, which the cut would make. Find out what it marks, "
                         f"and delete it (git tag -d {tag}) only if it is a mistake. Then cut.")
    return state


def _commit(root, git, plan_, outcome, backup):
    """Commits the paths the cut wrote and tags the commit. A failed commit puts the release back from the backup
    (_undo). A failed tag leaves the commit and raises CutIncomplete: the same command again finishes the tag
    (_finish_tag)."""
    if git == "none":
        return
    run, tag = plan_.report["run"]["id"], _tag(plan_)
    subject = (f"Cut {MODULE} {plan_.versions[MODULE][1]} from discovery run {run}" if plan_.versions
               else f"Record the decisions of discovery run {run}")
    spec = ["--pathspec-from-file=-", "--pathspec-file-nul"]
    for args in (["add", "-A", *spec], ["commit", "-q", "-m", subject, "-m", f"The record is {outcome.record.as_posix()}.", *spec]):
        done = _git(root, *args, stdin=_paths(outcome.files))
        if done.returncode != 0:
            raise CutFailed(f"git {args[0]} failed: {(done.stderr or done.stdout).strip()}. " + _undo(root, outcome.files, backup))
    outcome.committed = True
    if tag:
        _make_tag(root, tag, "HEAD")
        outcome.tag = tag


def _undo(root, files, backup):
    """After a failed commit: puts back the paths the cut wrote, from the backup, and takes them out of Git's index.
    It touches no other path, so a file Git was told to ignore or to assume unchanged keeps its content. Returns
    the sentence that says what state the release is in."""
    failed = _restore(root, files, backup)
    unstage = _git(root, "reset", "-q", *["--pathspec-from-file=-", "--pathspec-file-nul"], stdin=_paths(files))
    if not failed and unstage.returncode == 0:
        return "The release is as it was."
    said = []
    if failed:
        said.append(f"The release could NOT be put back in full. These {len(failed)} paths are not as they were: "
                    + "; ".join(failed) + ". Every other path is as it was.")
    else:
        said.append("The release's files are as they were.")
    if unstage.returncode != 0:
        said.append(f"Git could not take the cut's paths out of its index (git reset failed: "
                    f"{(unstage.stderr or unstage.stdout).strip()}), so some may still be staged: look at git status.")
    return " ".join(said)


def _make_tag(root, tag, commit):
    done = _git(root, "tag", tag, commit)
    if done.returncode != 0:
        raise CutIncomplete(f"the cut is committed, and git tag {tag} failed: {(done.stderr or done.stdout).strip()}. "
                            "Run the same command again to finish the tag.")


def _finish_tag(root, report, outcome, say):
    """For a run that was cut before: makes the cut's tag when the Git copy lacks it, on the commit that added the
    run's record. A cut whose tag failed is finished this way. Returns True when it made the tag."""
    if _git_state(root) in ("none", "no git"):
        return
    written = re.search(rf"^\| {re.escape(MODULE)} \| \S+ \| (\S+) \|", (root / record_path(report)).read_text(encoding="utf-8"), re.M)
    if not written or ov.release_scripts_newest(root).version_key(written.group(1)) is None:
        return   # the cut wrote no version, so it has no tag
    tag = f"{MODULE}-{written.group(1)}"
    if _tag_exists(root, tag):
        outcome.tag = tag
        return
    commit = _git(root, "log", "-1", "--format=%H", "--diff-filter=A", "--", record_path(report).as_posix()).stdout.strip()
    if not commit:
        raise CutIncomplete(f"the cut's files are in this Git copy and are not committed, so the tag {tag} cannot be made. "
                            "Commit them, then run the same command again.")
    _make_tag(root, tag, commit)
    outcome.tag = tag
    say(f"The tag {tag} was missing. It now marks the cut's commit {commit[:12]}.")
    return True


# ---------- helpers and the command line ----------

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="py -m kpi_store.cut", description="Cut a cleared KPI Store discovery report into a correction version.")
    ap.add_argument("--report", required=True, help="discovery-report.json, or the cleared discovery-report.csv beside it")
    ap.add_argument("--decisions", help="a cleared CSV whose decisions replace those in the JSON file")
    ap.add_argument("--release", default=".", help="the release's top folder (default: this folder)")
    ap.add_argument("--approver", help="the role or initials of the person who clears the report, such as \"the ontology owner\"; a name, "
                                       "an address or a number is refused")
    ap.add_argument("--plan", action="store_true", help="show what a cut would do and change nothing")
    a = ap.parse_args(argv)
    try:
        cut(a.report, a.release, a.decisions, a.approver, plan_only=a.plan)
    except EOFError:
        print("No answer was typed; nothing was changed.", file=sys.stderr)
        return 1
    except (CutRefused, CutFailed, CutIncomplete) as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
