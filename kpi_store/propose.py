"""The propose command: turns signed term-change and reference-item forms into proposals, and changes nothing in
the ontology.

    python -m kpi_store.propose <answers file> [<answers file> ...] [--out <folder>] [--release <folder>]

Each answers file is a term-change or reference-item form of the KPI intake pack (kpi-intake/README.md, "The term
change" and "The reference item"), saved from the HTML form as JSON or filled in the workbook's sheet of that
form. For each file the command:

1. runs the form's completeness check (python -m kpi_store.intake check) and refuses a form that is not complete
   and signed;
2. turns the answers into KGCL lines (kpi_store/change/kgcl.py), and checks them against the release's tables as
   the apply command will apply them, without writing anything: the kpi tables for a term change, the system or
   the data-product tables for a new item (kpi_store/change/reference_items.py);
3. suggests the route from the kinds of change, raised by the compatibility answer of a term change
   (kpi_store/change/proposal.py); a new item is a minor;
4. writes one proposal folder: change.kgcl, approval.json (written from the form's sign-off) and summary.txt.

It checks every file before it writes any proposal, so a refused file leaves no proposal at all. One form gives
one proposal (KPI-DEC-0002, Q6). A KPI intake form, for a new KPI, is refused for now: the new-KPI path comes in a
later step of KPI Store 1.2.

Where the proposals go: --out names the folder; without it, a folder named "proposals" beside the first answers
file. That folder must be outside the release folder, as the filled forms are (the intake's shared folder is
outside it too): the apply command commits the release, and refuses a release with files that are not committed.
Each proposal is a folder named by the form's request number, such as TC-2026-001, or <date>-<the short key of the
measure or the new item> when the form has none; with -2, -3 and so on when the name is taken.

What it reads: the answers files, the release's KPI intake pack (kpi-intake/) and the tables of the module it changes. What it
writes: the proposal folders, and nothing else. Needs Python 3.11 or later with rdflib, and openpyxl for a workbook.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

from kpi_store.change import ChangeRefused, approval, kgcl, kpi_tables, proposal, reference_items
from kpi_store.change.kgcl import Change

FORM, ITEM = "term-change", "reference-item"
FORMS = (FORM, ITEM)
SIGNERS = {"data-owner": "Data Owner", "ontology-owner": "Ontology Owner", "architect": "Architect"}
NEW_KPI = ("is a KPI intake form, for a new KPI. The propose command takes term changes and reference items only for "
           "now: the path for a new KPI comes in a later step of KPI Store 1.2. Until then the Architect applies it "
           "by hand, with HOW-TO-UPDATE.md")
ROUTE_WHY = {"patch": "a patch: the changes correct or reword, and the old meaning still holds",
             "minor": "a minor: the changes add content, and the old meaning still holds",
             "major": "a major: the form says a report or an answer that used the old meaning may now be wrong"}


class ProposeRefused(Exception):
    """A file is not a complete, signed term change or reference item, or the proposals cannot be written. No
    proposal was written."""


def _pack(root, pack):
    from kpi_store.intake import catalogue, picklists
    pack = Path(pack) if pack else root / "kpi-intake"
    return catalogue.load(pack), picklists.load(pack)


def read_form(path, cat, data, root, stale_check=True):
    """The intake of one answers file, refused unless it is a complete, signed term change or reference item. A
    workbook gives the form of its Term change sheet or of its Reference item sheet, whichever is filled."""
    from kpi_store.intake import answers, check, picklists
    path = Path(path)
    if not path.is_file():
        raise ProposeRefused(f"{path} is not a file")
    workbook = path.suffix.lower() in (".xlsx", ".xlsm")
    try:
        if workbook:
            filled = [i for i in (answers.read(path, cat, data["lists"], f) for f in FORMS) if i.answers]
        else:
            filled = [answers.read(path, cat, data["lists"])]
    except answers.AnswersError as err:
        raise ProposeRefused(f"{path.name} cannot be read: {err}") from None
    if workbook and not filled:
        raise ProposeRefused(f"{path.name}: the workbook's Term change and Reference item sheets are empty. A KPI form in "
                             "the workbook is for a new KPI, and the propose command takes term changes and reference "
                             "items only for now")
    if len(filled) > 1:
        raise ProposeRefused(f"{path.name}: the workbook holds a term change and a reference item. One form gives one "
                             "proposal: fill one of the two sheets in each workbook")
    intake = filled[0]
    if intake.form == "kpi-intake":
        raise ProposeRefused(f"{path.name} {NEW_KPI}")
    if intake.form not in FORMS:
        raise ProposeRefused(f"{path.name} is a {cat_form(intake.form)} form, not a term change or a reference item. "
                             "It changes nothing in the ontology")
    stale = picklists.stale_modules(data, root) if stale_check else None
    report = check.check(cat, data, intake, stale)
    if not report.complete:
        things = "; ".join(report.blocking)
        flag = f" --form {intake.form}" if workbook else ""
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


def item_changes(intake, lists):
    """The short key of the new item and the KGCL changes a reference item asks for, in the order the apply reads
    them: the new node, its definition and other names, then its links."""
    from kpi_store.intake import rules
    answers = intake.answers
    name, kind = rules.values(answers, "R1")[0], rules.values(answers, "R2")[0]
    if kind not in reference_items.KINDS:
        raise ProposeRefused(f"a {kind} needs a specialist; the form check says why")

    def linked(iri):
        found = reference_items.curie(iri)
        if not found:
            raise ProposeRefused(f"{iri} is not an item the reference-item form can link to")
        return found
    if kind == "system":
        key = reference_items.slug_of("system", name)
        subject = f"system:{key}"
        changes = [Change("create node", subject, text=name),
                   Change("add definition", subject, text=rules.values(answers, "R3")[0])]
        changes += [Change("create synonym", subject, text=t) for t in rules.values(answers, "R4")]
        named = rules.values(answers, "R6")[0]
        changes += [Change("create edge", subject, predicate="sys:systemKind", target=linked(rules.values(answers, "R5")[0])),
                    Change("create edge", subject, predicate="sys:namedBy", target=linked(named))]
        sources = list(dict.fromkeys([named, *rules.real_values(answers, "R7")]))
        changes += [Change("create edge", subject, predicate="dcterms:source", target=linked(s)) for s in sources]
    else:
        system = linked(rules.values(answers, "R8")[0])
        key = reference_items.slug_of("table", name, system.split(":", 1)[1])
        subject = f"table:{key}"
        changes = [Change("create node", subject, text=name),
                   Change("create edge", subject, predicate="dp:layer", target="layer:replica"),
                   Change("create edge", subject, predicate="dp:copiesSystem", target=system),
                   Change("create edge", subject, predicate="dcterms:source", target=linked(rules.values(answers, "R9")[0]))]
    return key, changes


def signatures(cat, intake):
    """The approval record's signatures from the form's sign-off: each needed signer's role, name and date, and the
    words the signature means on the form."""
    out = []
    for signer in cat.signers(intake.form):
        given = intake.sign_offs.get(signer["id"], {})
        signed = given.get("name", "").strip() and given.get("date", "").strip()
        if not cat.is_needed(signer, intake.form, intake.answers) and not signed:
            continue   # a signature the change does not need, and that nobody gave
        out.append({"role": SIGNERS[signer["id"]], "name": given.get("name", "").strip(),
                    "date": given.get("date", "").strip(), "words": cat.meaning(signer, intake.form)})
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


def item_summary(change_id, source, key, changes, lines, route, record, lists):
    """summary.txt of a reference item: the new item in plain words."""
    label = {i["id"]: i["label"] for name in ("systems", "system-kinds", "system-sources", "table-sources")
             for i in lists.get(name, [])}

    def named(target):
        return label.get(str(reference_items.iri(target)), target)
    kind = reference_items.BY_PREFIX[changes[0].subject.split(":", 1)[0]]
    said = {"add definition": lambda c: f'Its definition: "{c.text}"',
            "create synonym": lambda c: f'The other name "{c.text}".'}
    edge = {"sys:systemKind": "Its kind: {}.", "sys:namedBy": "The document that names it: {}.",
            "dcterms:source": "A source it rests on: {}.", "dp:layer": "Its layer: replica, a copy of a system's table.",
            "dp:copiesSystem": "The system whose table it copies: {}."}
    text = [f"Proposal {change_id}", "", f"From the form: {source}",
            f'The new item: {kind.what}, "{changes[0].text}" ({changes[0].subject}), in the {kind.module} module', "",
            "What it adds:", f'  - {kind.what[0].upper() + kind.what[1:]} named "{changes[0].text}".']
    for c in changes[1:]:
        text.append("  - " + (said[c.kind](c) if c.kind in said else edge[c.predicate].format(named(c.target))))
    text += ["", f"The route: {route}. This is {ROUTE_WHY[route]}.", "", "Who signed:"]
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
        if intake.form == ITEM:
            key, changes = item_changes(intake, data["lists"])
            module, checks, compatible = "new item's", reference_items.check_changes, "yes"
        else:
            measure, changes = changes_of(intake, data["lists"])
            key, module, checks = measure["notation"], "kpi", kpi_tables.check_changes
            compatible = "".join(intake.answers.get("T8", "") or "")
        try:
            checks(changes, root)
        except ChangeRefused as err:
            raise ProposeRefused(f"{path.name} asks for a change the {module} module cannot take: {err}") from None
        route = proposal.route_of(changes, compatible)
        change = _change_id(out, root, intake.request.get("number", "").strip(), key, today, taken)
        taken.add(change.lower())   # case does not count: on Windows and macOS TC-1 and tc-1 are one folder
        record = {"change": change, "route": route, "new_module": False, "signatures": signatures(cat, intake)}
        try:
            approval.check(record)
        except ChangeRefused as err:
            raise ProposeRefused(f"{path.name}: the sign-off cannot become an approval record: {err}") from None
        lines = [kgcl.write_line(c) for c in changes]
        if intake.form == ITEM:
            text = item_summary(change, path.name, key, changes, lines, route, record, data["lists"])
        else:
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
                                 description="Turn signed term-change and reference-item forms into proposals. Changes nothing in "
                                             "the ontology.")
    ap.add_argument("files", nargs="+", help="term-change or reference-item answers files (.json, or a filled workbook)")
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
