"""The propose command: turns signed term-change forms into proposals, and changes nothing in the ontology.

    python -m kpi_store.propose <answers file> [<answers file> ...] [--out <folder>] [--release <folder>]

Each answers file is a term-change form of the KPI intake pack (kpi-intake/README.md, "The term change"), saved
from the HTML form as JSON or filled in the workbook's Term change sheet. For each file the command:

1. runs the form's completeness check (python -m kpi_store.intake check) and refuses a form that is not complete
   and signed;
2. turns the answers into KGCL lines (kpi_store/change/kgcl.py), and checks them against the release's kpi tables
   as the apply command will apply them, without writing anything;
3. suggests the route from the kinds of change, raised by the compatibility answer (kpi_store/change/proposal.py);
4. writes one proposal folder: change.kgcl, approval.json (written from the form's sign-off) and summary.txt.

It checks every file before it writes any proposal, so a refused file leaves no proposal at all. One form gives
one proposal (KPI-DEC-0002, Q6). A KPI intake form, for a new KPI, is refused for now: the new-KPI path comes in a
later step of KPI Store 1.2.

Where the proposals go: --out names the folder; without it, a folder named "proposals" beside the first answers
file. That folder must be outside the release folder, as the filled forms are (the intake's shared folder is
outside it too): the apply command commits the release, and refuses a release with files that are not committed.
Each proposal is a folder named by the form's request number, such as TC-2026-001, or <date>-<the measure's short
key> when the form has none; with -2, -3 and so on when the name is taken.

What it reads: the answers files, the release's KPI intake pack (kpi-intake/) and the kpi module's tables. What it
writes: the proposal folders, and nothing else. Needs Python 3.11 or later with rdflib, and openpyxl for a workbook.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

from kpi_store.change import ChangeRefused, approval, kgcl, kpi_tables, proposal
from kpi_store.change.kgcl import Change

FORM = "term-change"
SIGNERS = {"data-owner": "Data Owner", "ontology-owner": "Ontology Owner", "architect": "Architect"}
NEW_KPI = ("is a KPI intake form, for a new KPI. The propose command takes term changes only for now: the path for a "
           "new KPI comes in a later step of KPI Store 1.2. Until then the Architect applies it by hand, with "
           "HOW-TO-UPDATE.md")
ROUTE_WHY = {"patch": "a patch: the changes correct or reword, and the old meaning still holds",
             "minor": "a minor: the changes add content, and the old meaning still holds",
             "major": "a major: the form says a report or an answer that used the old meaning may now be wrong"}


class ProposeRefused(Exception):
    """A file is not a complete, signed term change, or the proposals cannot be written. No proposal was written."""


def _pack(root, pack):
    from kpi_store.intake import catalogue, picklists
    pack = Path(pack) if pack else root / "kpi-intake"
    return catalogue.load(pack), picklists.load(pack)


def read_form(path, cat, data, root, stale_check=True):
    """The intake of one answers file, refused unless it is a complete, signed term change."""
    from kpi_store.intake import answers, check, picklists
    path = Path(path)
    if not path.is_file():
        raise ProposeRefused(f"{path} is not a file")
    form = FORM if path.suffix.lower() in (".xlsx", ".xlsm") else None
    try:
        intake = answers.read(path, cat, data["lists"], form)
    except answers.AnswersError as err:
        raise ProposeRefused(f"{path.name} cannot be read: {err}") from None
    if form and not intake.answers:
        raise ProposeRefused(f"{path.name}: the workbook's Term change sheet is empty. A KPI form in the workbook is for a new "
                             "KPI, and the propose command takes term changes only for now")
    if intake.form == "kpi-intake":
        raise ProposeRefused(f"{path.name} {NEW_KPI}")
    if intake.form != FORM:
        raise ProposeRefused(f"{path.name} is a {cat_form(intake.form)} form, not a term change. It changes no measure")
    stale = picklists.stale_modules(data, root) if stale_check else None
    report = check.check(cat, data, intake, stale)
    if not report.complete:
        things = "; ".join(report.blocking)
        flag = f" --form {FORM}" if form else ""
        raise ProposeRefused(f"{path.name} is not complete and signed. Run python -m kpi_store.intake check {path.as_posix()}"
                             f"{flag} for the whole report. To settle: {things}")
    return intake


def cat_form(form):
    from kpi_store.intake.catalogue import FORMS
    return FORMS.get(form, form).lower()


def changes_of(intake, lists):
    """The KGCL changes a term change asks for, in an order the apply can replay: removed other names, the rename,
    new other names, the definition, then the process links."""
    from kpi_store.intake import rules
    answers = intake.answers
    measure = next(m for m in lists["measures"] if m["id"] == rules.values(answers, "T1")[0])
    subject = f"measure:{measure['notation']}"
    changes = [Change("remove synonym", subject, text=t) for t in rules.values(answers, "T5")]
    changes += [Change("rename", subject, old=measure["label"], text=t) for t in rules.values(answers, "T2")[:1]]
    changes += [Change("create synonym", subject, text=t) for t in rules.values(answers, "T4")]
    changes += [Change("change definition", subject, text=t) for t in rules.values(answers, "T3")[:1]]
    for key, kind in (("T6", "create edge"), ("T7", "delete edge")):
        for iri in rules.real_values(answers, key):
            if not iri.startswith(kpi_tables.PREFIXES["proc"]):
                raise ProposeRefused(f"{iri} is not a process of the process map")
            changes.append(Change(kind, subject, predicate=kpi_tables.INFORMS,
                                  target="proc:" + iri[len(kpi_tables.PREFIXES["proc"]):]))
    return measure, changes


def signatures(cat, intake):
    """The approval record's signatures from the form's sign-off: each needed signer's role, name and date, and the
    words the signature means on the form."""
    out = []
    for signer in cat.signers(FORM):
        given = intake.sign_offs.get(signer["id"], {})
        signed = given.get("name", "").strip() and given.get("date", "").strip()
        if not cat.is_needed(signer, FORM, intake.answers) and not signed:
            continue   # a signature the change does not need, and that nobody gave
        out.append({"role": SIGNERS[signer["id"]], "name": given.get("name", "").strip(),
                    "date": given.get("date", "").strip(), "words": cat.meaning(signer, FORM)})
    return out


def summary(change_id, source, measure, changes, lines, route, compatible, record, processes=None):
    """summary.txt: the proposal in plain words. `processes` gives a process's label by its id (proc:<id>)."""
    label = {"proc:" + p["id"][len(kpi_tables.PREFIXES["proc"]):]: p["label"] for p in processes or []
             if p["id"].startswith(kpi_tables.PREFIXES["proc"])}
    said = {"rename": lambda c: f'Rename it from "{c.old}" to "{c.text}".',
            "change definition": lambda c: f'Change its definition to: "{c.text}"',
            "create synonym": lambda c: f'Add the other name "{c.text}".',
            "remove synonym": lambda c: f'Remove the other name "{c.text}".',
            "create edge": lambda c: f"Link it to the process {label.get(c.target, c.target)}.",
            "delete edge": lambda c: f"Remove its link to the process {label.get(c.target, c.target)}."}
    answer = {"yes": "yes", "no": "no", "not-sure": "not sure"}.get(compatible, compatible)
    text = [f"Proposal {change_id}", "",
            f"From the form: {source}",
            f'The measure: {measure["label"]} (measure:{measure["notation"]})', "",
            "What changes:"]
    text += [f"  - {said[c.kind](c)}" for c in changes]
    text += ["", f'Would every report and answer that used the old meaning still be correct? The form says: {answer}.',
             f"The route: {route}. This is {ROUTE_WHY[route]}.", "",
             "Who signed:"]
    text += [f"  - {s['role']}, on {s['date']}" for s in record["signatures"]]
    text += ["", f"The KGCL lines, in {proposal.CHANGE_FILE}:"] + [f"  {line}" for line in lines]
    text += ["", "Nothing in the ontology has changed yet. To apply this proposal, run in the release folder:",
             "  python -m kpi_store.apply <the path of this folder>", ""]
    return "\n".join(text)


def _change_id(out, root, number, notation, today, taken):
    """The proposal's name: the form's request number when it has the form of a change id, else <date>-<the measure's
    short key>; with -2, -3 and so on when a proposal or an approval record of that name exists already."""
    base = number if approval.CHANGE_ID.fullmatch(number or "") else f"{today}-{notation}"
    change, n = base, 1
    while change.lower() in taken or (out / change).exists() or approval.record_path(root, change).exists():
        n += 1
        change = f"{base}-{n}"
    return change


def propose(files, out=None, release_root=".", pack=None, now=None, say=print):
    """Checks every answers file, then writes one proposal folder for each and returns their paths. Raises
    ProposeRefused, with no proposal written, when any file is refused. `pack` is a KPI intake pack folder other
    than the release's own; the check then does not compare its pick lists with the release's packages."""
    root = Path(release_root).resolve()
    files = [Path(f) for f in files]
    if not files:
        raise ProposeRefused("name at least one answers file")
    out = Path(out) if out else files[0].parent / "proposals"
    if out.resolve() == root or out.resolve().is_relative_to(root):
        raise ProposeRefused(f"{out} is inside the release folder. Keep proposals outside it, as the filled forms are: the "
                             "apply command commits the release and refuses one with files that are not committed. "
                             "Name another folder with --out")
    try:
        cat, data = _pack(root, pack)
    except Exception as err:   # the catalogue's and the pick lists' own errors say what is wrong
        raise ProposeRefused(f"the KPI intake pack cannot be read: {err}") from None
    today = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%d")
    planned, taken = [], set()
    for path in files:
        intake = read_form(path, cat, data, root, stale_check=pack is None)
        measure, changes = changes_of(intake, data["lists"])
        try:
            kpi_tables.check_changes(changes, root)
        except ChangeRefused as err:
            raise ProposeRefused(f"{path.name} asks for a change the kpi module cannot take: {err}") from None
        compatible = "".join(intake.answers.get("T8", "") or "")
        route = proposal.route_of(changes, compatible)
        change = _change_id(out, root, intake.request.get("number", "").strip(), measure["notation"], today, taken)
        taken.add(change.lower())   # case does not count: on Windows and macOS TC-1 and tc-1 are one folder
        record = {"change": change, "route": route, "new_module": False, "signatures": signatures(cat, intake)}
        try:
            approval.check(record)
        except ChangeRefused as err:
            raise ProposeRefused(f"{path.name}: the sign-off cannot become an approval record: {err}") from None
        lines = [kgcl.write_line(c) for c in changes]
        text = summary(change, path.name, measure, changes, lines, route, compatible, record, data["lists"]["processes"])
        planned.append((out / change, changes, record, text, lines))
    written = []
    for folder, changes, record, text, lines in planned:
        proposal.write(folder, changes, record, text)
        written.append(folder)
        say(f"wrote the proposal {folder.as_posix()}: {len(lines)} change{'s' if len(lines) != 1 else ''}, route {record['route']}")
    say("Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>")
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kpi_store.propose",
                                 description="Turn signed term-change forms into proposals. Changes nothing in the ontology.")
    ap.add_argument("files", nargs="+", help="term-change answers files (.json, or a filled workbook)")
    ap.add_argument("--out", help="the folder the proposals go in (default: a folder named proposals beside the first file); "
                                  "it must be outside the release folder")
    ap.add_argument("--release", default=".", help="the release's top folder (default: this folder)")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        propose(a.files, a.out, a.release)
    except (ProposeRefused, ChangeRefused, OSError) as err:
        print(f"Not proposed: {err}. No proposal was written.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
