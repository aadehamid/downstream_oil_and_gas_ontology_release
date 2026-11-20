"""A proposal: one signed term change, new reference item, new KPI, domain activation or process map request, as the
files the apply command reads (KPI-DEC-0002, Q4, Q5, Q6, Q10 and Q13; KPI-DEC-0004, item 1).

One form gives one proposal (Q6). A proposal is one folder, named by its change id, that holds three files, and a
fourth when some facts are ones KGCL cannot write:

    change.kgcl     the KGCL lines, one per change, as kgcl.py writes them; empty for a domain activation
    approval.json   the approval record of the change, in the form approval.py checks, written from the form's
                    sign-off: each signer's role, name, date and the words the signature means
    summary.txt     the same for a person, in plain words: what changes, the route, and who signed
    facts.csv       the facts KGCL cannot write, one row each, with the columns measure, property and value; the
                    first column may name any item. A new KPI's (new_measures.py says which), a process map
                    request's (process_map.py) and a domain activation's, which holds nothing else (domains.py)

Who answers for the content, and so signs beside the Architect (Q4), follows from what the proposal changes: the
Domain Owner for a domain activation, the Global Process Owner for roles and their RACI entries, and the Data Owner
for everything else (owner_of).

The route (Q5). Each kind of change suggests one: a new other name and a new process link add content, so they
are minor, and so is a new reference item or a new KPI (its create node line and the lines about the new node); a rename, a new
definition, a removed other name and a removed process link are patch. A proposal takes
the highest route among its changes. The answer to "Would every report and answer that used the old meaning still
be correct?" can only raise it: "no" or "not sure" makes it major. The approval record holds the route, and read()
refuses a record whose route is lower than its changes suggest.

Two proposals conflict when they touch the same field of the same measure: its name, its definition, its other
names or its process links, when both add the same new item or the same line, or when both change the same domain
(Q6). The apply command refuses conflicting
proposals before it writes anything.

Nothing here writes outside the folder it is given.
"""
import csv
import dataclasses
import io
import json
from dataclasses import dataclass
from pathlib import Path

from . import ChangeRefused, approval, kgcl

CHANGE_FILE, APPROVAL_FILE, SUMMARY_FILE, FACTS_FILE = "change.kgcl", "approval.json", "summary.txt", "facts.csv"
FACT_COLUMNS = ("measure", "property", "value")
ROUTE_OF = {"create synonym": "minor", "create edge": "minor", "rename": "patch", "change definition": "patch",
            "remove synonym": "patch", "delete edge": "patch", "create node": "minor", "add definition": "minor"}
RAISED_BY = ("no", "not-sure")   # the answers to the compatibility question that make a change major
FIELD = {"rename": "name", "change definition": "definition", "create synonym": "other names",
         "remove synonym": "other names", "create edge": "process links", "delete edge": "process links",
         "add definition": "definition"}


def highest(routes):
    """The highest of these routes: major over minor over patch."""
    return max(routes, key=approval.ROUTES.index)


def route_of(changes, compatible="yes"):
    """The route the changes suggest, raised to major when the compatibility answer is "no" or "not sure". A domain
    activation has no KGCL line, and adds a choice to the forms: a minor."""
    route = highest(ROUTE_OF[c.kind] for c in changes) if changes else "minor"
    return "major" if compatible in RAISED_BY else route


DOMAIN = "domain:"                     # the subject of a domain activation's facts (domains.py)
PROCESS_MAP_PREFIXES = ("role", "asg")  # the subjects of a process map request's lines (process_map.py)


def owner_of(changes, facts=()):
    """The role that signs for the content of these changes beside the Architect."""
    if not changes and facts and all(s.startswith(DOMAIN) for s, _, _ in facts):
        return "Domain Owner"
    if any(c.subject.split(":", 1)[0] in PROCESS_MAP_PREFIXES for c in changes):
        return "Global Process Owner"
    return "Data Owner"


@dataclass
class Proposal:
    folder: Path
    change: str          # the change id: the folder's name and the approval record's name
    changes: list        # the kgcl.Change of each line, in the file's order
    lines: list          # the KGCL lines
    record: dict         # the approval record, checked
    facts: list = dataclasses.field(default_factory=list)   # (measure, property, value) of facts.csv, in order

    @property
    def route(self):
        return self.record["route"]

    @property
    def owner(self):
        return owner_of(self.changes, self.facts)


def facts_text(facts):
    """facts.csv's text: the header and one row per fact, with LF line ends."""
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(FACT_COLUMNS)
    writer.writerows(facts)
    return out.getvalue()


def read_facts(text, name):
    """The facts of a facts.csv text, as (measure, property, value) rows. Refuses another header or a short row."""
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as err:
        raise ChangeRefused(f"the proposal {name}: {FACTS_FILE} cannot be read ({err})") from None
    if not rows or tuple(rows[0]) != FACT_COLUMNS:
        raise ChangeRefused(f"the proposal {name}: {FACTS_FILE} must start with the header {','.join(FACT_COLUMNS)}")
    for n, row in enumerate(rows[1:], 2):
        if len(row) != len(FACT_COLUMNS):
            raise ChangeRefused(f"the proposal {name}: row {n} of {FACTS_FILE} has {len(row)} values, not 3")
    return [tuple(row) for row in rows[1:]]


def write(folder, changes, record, summary, facts=()):
    """Writes one proposal folder and returns it, with facts.csv when there are facts. Refuses a folder that exists,
    an incomplete record and a change that has no KGCL line."""
    folder = Path(folder)
    record = approval.check(record, owner_of(changes, facts))
    if record["change"] != folder.name:
        raise ChangeRefused(f"the approval record is for {record['change']}, and the folder is {folder.name}")
    text = kgcl.write_lines(changes)
    if folder.exists():
        raise ChangeRefused(f"{folder} exists already; a proposal is written once")
    folder.mkdir(parents=True)
    files = [(CHANGE_FILE, text), (APPROVAL_FILE, json.dumps(record, ensure_ascii=False, indent=2) + "\n"),
             (SUMMARY_FILE, summary)]
    if facts:
        files.append((FACTS_FILE, facts_text(facts)))
    for name, content in files:
        with (folder / name).open("w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    return folder


def read(folder):
    """One proposal folder, checked: its KGCL lines read, its approval record complete for its route, and that route
    not lower than its changes suggest. Raises ChangeRefused with the reason in plain words."""
    folder = Path(folder).resolve()   # so "." has a name, and on Windows the name has the case it has on disk
    if not folder.is_dir():
        raise ChangeRefused(f"{folder} is not a proposal folder: it does not exist or is not a folder")
    missing = [name for name in (CHANGE_FILE, APPROVAL_FILE) if not (folder / name).is_file()]
    if missing:
        raise ChangeRefused(f"the proposal {folder.name} has no {' and no '.join(missing)}")
    try:
        lines = [line for line in (folder / CHANGE_FILE).read_text(encoding="utf-8").splitlines() if line.strip()]
        record = json.loads((folder / APPROVAL_FILE).read_text(encoding="utf-8"))
        facts_file = folder / FACTS_FILE
        facts = read_facts(facts_file.read_text(encoding="utf-8"), folder.name) if facts_file.is_file() else []
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise ChangeRefused(f"the proposal {folder.name} cannot be read ({type(err).__name__}: {err})") from None
    changes = [kgcl.read_line(line) for line in lines]
    if not changes and not (facts and owner_of(changes, facts) == "Domain Owner"):
        raise ChangeRefused(f"the proposal {folder.name} holds no change")
    try:
        record = approval.check(record, owner_of(changes, facts))
    except ChangeRefused as err:
        raise ChangeRefused(f"the proposal {folder.name} is not approved: {err}") from None
    if record["change"] != folder.name:
        raise ChangeRefused(f"the approval record in {folder.name} is for the change {record['change']}")
    least = route_of(changes)
    if approval.ROUTES.index(record["route"]) < approval.ROUTES.index(least):
        raise ChangeRefused(f"the proposal {folder.name} is approved as {record['route']}, and its changes need at least "
                            f"{least}")
    return Proposal(folder, record["change"], changes, lines, record, facts)


def conflicts(proposals):
    """Each pair of proposals that touch the same field of the same measure, or add the same item, as a sentence.
    Empty when none do."""
    seen, out = {}, []
    for proposal in proposals:
        made = {c.subject for c in proposal.changes if c.kind == "create node"}
        # A link from anything but a measure (a new KPI's link from a value stream step, a view or an assistant)
        # conflicts only with the same line: two new KPIs may each link the same step or view. Every other change
        # conflicts by its field.
        keys = {(s, "new item", "") for s in made} | {
            (c.subject, "line", kgcl.write_line(c)) if c.kind == "create edge" and not c.subject.startswith("measure:")
            else (c.subject, "field", FIELD[c.kind])
            for c in proposal.changes if c.subject not in made}
        keys |= {(s, "domain", "") for s, _, _ in proposal.facts if s.startswith(DOMAIN)}
        for key in sorted(keys):
            if key in seen and seen[key] != proposal.change:
                subject, kind, detail = key
                if kind == "new item":
                    out.append(f"the proposals {seen[key]} and {proposal.change} both add {subject}")
                elif kind == "domain":
                    out.append(f"the proposals {seen[key]} and {proposal.change} both change the domain {subject}")
                elif kind == "line":
                    out.append(f"the proposals {seen[key]} and {proposal.change} both add the line {detail}")
                else:
                    out.append(f"the proposals {seen[key]} and {proposal.change} both change the {detail} of {subject}")
            seen.setdefault(key, proposal.change)
    return out
