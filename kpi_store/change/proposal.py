"""A proposal: one signed term change or new reference item, as the files the apply command reads (KPI-DEC-0002, Q4,
Q5, Q6, Q10 and Q13).

One form gives one proposal (Q6). A proposal is one folder, named by its change id, that holds three files:

    change.kgcl     the KGCL lines, one per change, as kgcl.py writes them
    approval.json   the approval record of the change, in the form approval.py checks, written from the form's
                    sign-off: each signer's role, name, date and the words the signature means
    summary.txt     the same for a person, in plain words: what changes, the route, and who signed

The route (Q5). Each kind of change suggests one: a new other name and a new process link add content, so they
are minor, and so is a new reference item (its create node line and the lines about the new node); a rename, a new
definition, a removed other name and a removed process link are patch. A proposal takes
the highest route among its changes. The answer to "Would every report and answer that used the old meaning still
be correct?" can only raise it: "no" or "not sure" makes it major. The approval record holds the route, and read()
refuses a record whose route is lower than its changes suggest.

Two proposals conflict when they touch the same field of the same measure: its name, its definition, its other
names or its process links, or when both add the same new item (Q6). The apply command refuses conflicting
proposals before it writes anything.

Nothing here writes outside the folder it is given.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from . import ChangeRefused, approval, kgcl

CHANGE_FILE, APPROVAL_FILE, SUMMARY_FILE = "change.kgcl", "approval.json", "summary.txt"
ROUTE_OF = {"create synonym": "minor", "create edge": "minor", "rename": "patch", "change definition": "patch",
            "remove synonym": "patch", "delete edge": "patch", "create node": "minor", "add definition": "minor"}
RAISED_BY = ("no", "not-sure")   # the answers to the compatibility question that make a change major
FIELD = {"rename": "name", "change definition": "definition", "create synonym": "other names",
         "remove synonym": "other names", "create edge": "process links", "delete edge": "process links"}


def highest(routes):
    """The highest of these routes: major over minor over patch."""
    return max(routes, key=approval.ROUTES.index)


def route_of(changes, compatible="yes"):
    """The route the changes suggest, raised to major when the compatibility answer is "no" or "not sure"."""
    route = highest(ROUTE_OF[c.kind] for c in changes)
    return "major" if compatible in RAISED_BY else route


@dataclass
class Proposal:
    folder: Path
    change: str          # the change id: the folder's name and the approval record's name
    changes: list        # the kgcl.Change of each line, in the file's order
    lines: list          # the KGCL lines
    record: dict         # the approval record, checked

    @property
    def route(self):
        return self.record["route"]


def write(folder, changes, record, summary):
    """Writes one proposal folder and returns it. Refuses a folder that exists, an incomplete record and a change
    that has no KGCL line."""
    folder = Path(folder)
    record = approval.check(record)
    if record["change"] != folder.name:
        raise ChangeRefused(f"the approval record is for {record['change']}, and the folder is {folder.name}")
    text = kgcl.write_lines(changes)
    if folder.exists():
        raise ChangeRefused(f"{folder} exists already; a proposal is written once")
    folder.mkdir(parents=True)
    for name, content in ((CHANGE_FILE, text), (APPROVAL_FILE, json.dumps(record, ensure_ascii=False, indent=2) + "\n"),
                          (SUMMARY_FILE, summary)):
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
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise ChangeRefused(f"the proposal {folder.name} cannot be read ({type(err).__name__}: {err})") from None
    changes = [kgcl.read_line(line) for line in lines]
    if not changes:
        raise ChangeRefused(f"the proposal {folder.name} holds no change")
    try:
        record = approval.check(record)
    except ChangeRefused as err:
        raise ChangeRefused(f"the proposal {folder.name} is not approved: {err}") from None
    if record["change"] != folder.name:
        raise ChangeRefused(f"the approval record in {folder.name} is for the change {record['change']}")
    least = route_of(changes)
    if approval.ROUTES.index(record["route"]) < approval.ROUTES.index(least):
        raise ChangeRefused(f"the proposal {folder.name} is approved as {record['route']}, and its changes need at least "
                            f"{least}")
    return Proposal(folder, record["change"], changes, lines, record)


def conflicts(proposals):
    """Each pair of proposals that touch the same field of the same measure, or add the same item, as a sentence.
    Empty when none do."""
    seen, out = {}, []
    for proposal in proposals:
        made = {c.subject for c in proposal.changes if c.kind == "create node"}
        keys = {(s, "new item") for s in made} | {(c.subject, FIELD[c.kind]) for c in proposal.changes if c.subject not in made}
        for key in sorted(keys):
            if key in seen and seen[key] != proposal.change:
                if key[1] == "new item":
                    out.append(f"the proposals {seen[key]} and {proposal.change} both add {key[0]}")
                else:
                    out.append(f"the proposals {seen[key]} and {proposal.change} both change the {key[1]} of {key[0]}")
            seen.setdefault(key, proposal.change)
    return out
