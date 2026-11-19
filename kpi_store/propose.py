"""The propose command: turns signed term-change, reference-item and KPI intake forms into proposals, and changes
nothing in the ontology.

    python -m kpi_store.propose <answers file> [<answers file> ...] [--out <folder>] [--release <folder>]

Each answers file is a term-change, reference-item or KPI intake form of the KPI intake pack (kpi-intake/README.md,
"The term change", "The reference item" and "Turning a filled KPI form into a proposal"), saved from the HTML form
as JSON or filled in the workbook. For each file the command:

1. runs the form's completeness check (python -m kpi_store.intake check) and refuses a form that is not complete
   and signed;
2. turns the answers into KGCL lines (kpi_store/change/kgcl.py), and checks them against the release's tables as
   the apply command will apply them, without writing anything: the kpi tables for a term change or a new KPI
   (kpi_store/change/new_measures.py), the system or the data-product tables for a new item
   (kpi_store/change/reference_items.py);
3. suggests the route from the kinds of change, raised by the compatibility answer of a term change
   (kpi_store/change/proposal.py); a new item and a new KPI are a minor;
4. writes one proposal folder: change.kgcl, approval.json (written from the form's sign-off) and summary.txt, and
   for a new KPI facts.csv, the facts KGCL cannot write (KPI-DEC-0004, item 1).

A new KPI's proposal holds every module it changes (kpi_store/change/other_modules.py): the measure and what it counts
and leaves out (kpi), the value stream steps that use it (value-stream), the view that gives its values and the
assistant that answers from it (data-product), and a sentence back in the scope note of each measure it is mistaken
for. A new step, view or assistant is refused: the step goes to the process map request, and a view or an assistant
needs a specialist. The answers the ontology has no place for stay in the form's file, and summary.txt names what
the Architect must still do outside the form.

It checks every file before it writes any proposal, so a refused file leaves no proposal at all. One form gives
one proposal (KPI-DEC-0002, Q6).

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

from kpi_store.change import ChangeRefused, approval, kgcl, kpi_tables, new_measures, other_modules, proposal, reference_items
from kpi_store.change.kgcl import Change

FORM, ITEM, KPI = "term-change", "reference-item", "kpi-intake"
FORMS = (FORM, ITEM)
SIGNERS = {"data-owner": "Data Owner", "ontology-owner": "Ontology Owner", "architect": "Architect",
           "domain-confirmation": "Domain Owner", "domain-owner": "Domain Owner"}
ROUTE_WHY = {"patch": "a patch: the changes correct or reword, and the old meaning still holds",
             "minor": "a minor: the changes add content, and the old meaning still holds",
             "major": "a major: the form says a report or an answer that used the old meaning may now be wrong"}


class ProposeRefused(Exception):
    """A file is not a complete, signed KPI intake, term change or reference item, or the proposals cannot be
    written. No proposal was written."""


def _pack(root, pack):
    from kpi_store.intake import catalogue, picklists
    pack = Path(pack) if pack else root / "kpi-intake"
    return catalogue.load(pack), picklists.load(pack)


def read_form(path, cat, data, root, stale_check=True):
    """The intake of one answers file, refused unless it is a complete, signed term change, reference item or KPI
    intake. A workbook gives the form of its Term change sheet or of its Reference item sheet, whichever is filled,
    and its KPI form when neither is."""
    from kpi_store.intake import answers, check, picklists
    path = Path(path)
    if not path.is_file():
        raise ProposeRefused(f"{path} is not a file")
    workbook = path.suffix.lower() in (".xlsx", ".xlsm")
    try:
        if workbook:
            filled = [i for i in (answers.read(path, cat, data["lists"], f) for f in FORMS) if i.answers]
            filled = filled or [i for i in [answers.read(path, cat, data["lists"], KPI)] if i.answers]
        else:
            filled = [answers.read(path, cat, data["lists"])]
    except answers.AnswersError as err:
        raise ProposeRefused(f"{path.name} cannot be read: {err}") from None
    if workbook and not filled:
        raise ProposeRefused(f"{path.name}: the workbook holds no filled form: its KPI form, Term change and Reference item "
                             "sheets are empty")
    if len(filled) > 1:
        raise ProposeRefused(f"{path.name}: the workbook holds a term change and a reference item. One form gives one "
                             "proposal: fill one of the two sheets in each workbook")
    intake = filled[0]
    if intake.form not in (*FORMS, KPI):
        raise ProposeRefused(f"{path.name} is a {cat_form(intake.form)} form, not a KPI intake, a term change or a "
                             "reference item. It changes nothing in the ontology")
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


def kpi_changes(cat, intake, lists, root):
    """The short key of a new measure, the KGCL changes and the facts a KPI intake asks for, and the questions it
    answers that feed another module: (key, changes, facts, [(question, module)]). The facts are those KGCL cannot
    write (kpi_store/change/new_measures.py)."""
    from kpi_store.intake import check, rules
    answers = check._resolve(cat, lists, intake)[0].answers
    one = lambda key: "".join(rules.real_values(answers, key)[:1])
    name = one("2.1")
    key = reference_items.slug(name)
    if not key:
        raise ProposeRefused(f'2.1: "{name}" has no letter or digit to make the short key of the measure from')
    subject = f"measure:{key}"

    def linked(question, value, prefix, what):
        found = other_modules.curie(value)
        if not found or found.split(":", 1)[0] != prefix:
            label = next((i["label"] for items in lists.values() if isinstance(items, list) for i in items
                          if isinstance(i, dict) and i.get("id") == value), value)
            raise ProposeRefused(f'{question} names "{label}", which is not {what}')
        return found
    rule = rules.kind(cat, answers)
    kind = rule["kind"].lower().replace(" ", "-")
    sources = rules.real_values(answers, "3.5")
    if len(sources) != 1:
        raise ProposeRefused(f"3.5 names {len(sources)} documents, and the kpi module records one source for each measure. "
                             "Name the document that defines the measure")
    offered = {i["id"] for i in lists["sources"] if not i.get("hidden")}
    held = {new_measures.PREFIXES["src"] + r["slug"]
            for r in new_measures._read(root, (new_measures.SOURCES,)).rows[new_measures.SOURCES]}
    if sources[0] not in offered | held:
        raise ProposeRefused("3.5 names a document that the form does not offer. The kpi module takes a document of its "
                             "own sources or one that 3.5 offers")
    changes = [Change("create node", subject, text=name), Change("add definition", subject, text=one("2.2"))]
    changes += [Change("create synonym", subject, text=t) for t in rules.values(answers, "5.1")]
    edge = lambda predicate, target: Change("create edge", subject, predicate=predicate, target=target)
    changes += [edge("kpi:measureKind", f"kind:{kind}"),
                edge("dcterms:source", linked("3.5", sources[0], "src", "a document of the ontology"))]
    changes += [edge("kpi:usedBy", linked("6.1", r, "persona", "one of the planning personas, the only roles the kpi "
                                          "module records today. Another role needs a specialist to extend the kpi builder"))
                for r in rules.real_values(answers, "6.1")]
    processes = list(dict.fromkeys([one("1.3") or one("1.2"), *rules.real_values(answers, "6.2")]))
    changes += [edge("kpi:informsProcess", linked("1.2, 1.3 or 6.2", p, "proc", "a process of the process map")) for p in processes if p]
    changes += [edge("kpi:notToBeConfusedWith", linked("5.2", m, "measure", "a measure of the kpi module"))
                for m in rules.real_values(answers, "5.2")]
    candidate = kind == "operational-metric" and one("4.7") == "yes"
    basis, unit = one("3.1"), one("3.2")
    facts = [("kpi:kpiCandidate", "true" if candidate else "false"), ("kpi:classificationTest", str(rule["test"])),
             ("kpi:classificationReason", one("4.8")), ("kpi:comparedAgainst", one("3.4")),
             ("kpi:publicCounterpart", one("5.4")), ("dcterms:bibliographicCitation", "; ".join(v for v in (one("3.5.detail"), one("4.6.detail")) if v)),
             ("kpi:grain", one("3.3")), ("kpi:basis", f"{basis}; unit: {unit}" if basis and unit else basis),
             ("skos:scopeNote", one("5.3"))]
    if one("3.6").lower() not in ("", "no", "none"):
        facts.append(("skos:note", one("3.6")))
    facts = [(subject, prop, value) for prop, value in facts if value]
    # What it counts and leaves out (2.3, 2.4): the populations, which ship in the kpi package.
    if one("2.4") and not one("2.3"):
        raise ProposeRefused("2.4 says what the KPI leaves out, and 2.3 does not say what it counts. Answer 2.3 too, "
                             "or leave 2.4 empty")
    if one("2.3"):
        facts += [(subject, "pop:includes", one("2.3"))] + ([(subject, "pop:excludes", one("2.4"))] if one("2.4") else [])
        facts.append((subject, "pop:populationEvidence", one("3.5.detail")))
    # The value stream steps that use it (6.3 to 6.5): one measure link each.
    steps, relationships, bases = (rules.positions(answers, q) for q in ("6.3", "6.4", "6.5"))
    seen = set()
    for i, step in enumerate(steps):
        if step == "@not-in-list":
            raise ProposeRefused("6.3 names a step that the ontology does not hold. A new value stream step goes to the "
                                 "process map request")
        if not step or step.startswith("@"):
            continue
        step = linked("6.3", step, "vsprocess", "a step of a value stream")
        if step in seen:
            raise ProposeRefused(f"6.3 names the step {step} twice. A step takes one link to a measure")
        seen.add(step)
        relationship = linked("6.4", relationships[i] if i < len(relationships) else "", "rel", "a way a step uses a measure")
        link = f"mlink:{step.split(':', 1)[1]}--{key}"
        changes += [Change("create edge", step, predicate="vs:measureLink", target=link),
                    Change("create edge", link, predicate="vs:measure", target=subject),
                    Change("create edge", link, predicate="vs:relationship", target=relationship)]
        facts.append((link, "dcterms:bibliographicCitation", bases[i] if i < len(bases) else ""))
    # The view that gives its values (7.1), the data product it is part of (6.6) and the assistant (7.8).
    if "@not-in-list" in rules.values(answers, "7.1"):
        raise ProposeRefused("7.1 names a view that the ontology does not hold. A new view is a data product, and needs a "
                             "specialist, as the reference-item form says of a table built from other tables")
    pricing = other_modules._pricing(root, ("tables", "agents"))
    if one("7.1"):
        view = linked("7.1", one("7.1"), "table", "a table of the data-product module")
        row = next((t for t in pricing.rows["tables"] if t["slug"] == view.split(":", 1)[1]), {})
        if row.get("layer") != "metric-view":
            raise ProposeRefused(f"7.1 names {view}, which is not a metric view. Only a metric view serves a measure")
        if "@not-in-list" in rules.values(answers, "6.6"):
            raise ProposeRefused(f"6.6 names a data product that the ontology does not hold, and the view of 7.1 is part "
                                 f"of {other_modules.WHOLE}")
        product = linked("6.6", one("6.6"), "product", "a data product") if one("6.6") else other_modules.WHOLE
        if product != other_modules.WHOLE:
            raise ProposeRefused(f"6.6 names {product}, and the view of 7.1 is part of {other_modules.WHOLE}")
        changes.append(Change("create edge", view, predicate="dp:servesMeasure", target=subject))
        if one("7.8"):
            agent = next((a for a in pricing.rows["agents"] if a["label"].casefold() == one("7.8").casefold()), None)
            if agent is None:
                raise ProposeRefused(f'7.8 names "{one("7.8")}", which is not an assistant of the data-product module. '
                                     "A new assistant needs a specialist")
            if view.split(":", 1)[1] not in agent["uses"].split(";"):
                changes.append(Change("create edge", f"agent:{agent['slug']}", predicate="prov:used", target=view))
    elif one("7.8"):
        raise ProposeRefused("7.8 names an assistant, and 7.1 names no view for it to answer from")
    # A sentence back in the scope note of each measure it is mistaken for (5.2).
    for m in rules.real_values(answers, "5.2"):
        facts.append((linked("5.2", m, "measure", "a measure of the kpi module"), "skos:scopeNote",
                      f"Not {name}: the scope note of {name} says how the two differ."))
    notes = []
    if one("6.7") == "yes":
        notes.append("6.7 is yes. The market-data module needs the KPI's named series, which this form does not "
                     "collect. Model them in market-data, as the check's routing says.")
    if one("7.7"):
        notes.append("7.7 stays in the form's file: the ontology has no property for the measure or column of a view yet.")
    return key, changes, facts, notes


RELATIONSHIP_WORDS = {"informs": "as an input", "benchmarks": "as a benchmark", "measures-performance": "as a result it tracks"}
FACT_WORDS = {"pop:includes": 'What it counts: "{}"', "pop:excludes": 'What it leaves out: "{}"',
              "pop:populationEvidence": 'Where its population is written down: "{}"',
              "kpi:kpiCandidate": "A strong candidate to become a KPI: {}.", "kpi:classificationTest": "The test that decided its kind: {}.",
              "kpi:classificationReason": 'Why it has that kind: "{}"', "kpi:comparedAgainst": 'What it is compared against: "{}"',
              "kpi:publicCounterpart": 'Its closest published measure: "{}"', "dcterms:bibliographicCitation": 'Where the source says it: "{}"',
              "kpi:grain": 'How often it is stated, and its breakdowns: "{}"', "kpi:basis": 'How it is worked out: "{}"',
              "skos:scopeNote": 'How it differs from the measures it is mistaken for: "{}"',
              "skos:note": 'An ID another asset gives it: "{}"'}


def kpi_summary(change_id, source, changes, facts, notes, lines, route, record, lists):
    """summary.txt of a new KPI: the new measure, and what it changes in the other modules, in plain words."""
    label = {i["id"]: i["label"] for name in ("sources", "roles", "processes", "measures", "value-stream-steps", "platform-tables")
             for i in lists.get(name, [])}

    def named(target):
        return label.get(other_modules.iri(target), target)
    step_of = {c.target: c.subject for c in changes if c.predicate == "vs:measureLink"}
    edge = {"kpi:measureKind": lambda t: f"Its kind: {new_measures.tail(t).replace('-', ' ')}.",
            "dcterms:source": lambda t: f"The document it comes from: {named(t)}.",
            "kpi:usedBy": lambda t: f"A role that uses it: {named(t)}.",
            "kpi:informsProcess": lambda t: f"A process it informs: {named(t)}.",
            "kpi:notToBeConfusedWith": lambda t: f"A measure it is mistaken for: {named(t)}."}

    def said(c):
        if c.kind == "add definition":
            return f'Its definition: "{c.text}"'
        if c.kind == "create synonym":
            return f'The other name "{c.text}".'
        if c.predicate == "vs:relationship":
            return (f"A value stream step that uses it: {named(step_of[c.subject])}, "
                    f"{RELATIONSHIP_WORDS[new_measures.tail(c.target)]}.")
        if c.predicate == "dp:servesMeasure":
            return f"The view that gives its values: {named(c.subject)}."
        if c.predicate == "prov:used":
            return f"An assistant that now answers from that view: {c.subject}."
        return edge[c.predicate](c.target) if c.predicate in edge else None
    first = changes[0]
    text = [f"Proposal {change_id}", "", f"From the form: {source}",
            f'The new measure: "{first.text}" ({first.subject}), in the kpi module', "",
            f"What it adds, as KGCL lines in {proposal.CHANGE_FILE}:", f'  - A measure named "{first.text}".']
    text += [f"  - {said(c)}" for c in changes[1:] if said(c)]
    text += ["", f"What it adds, as facts in {proposal.FACTS_FILE} (KGCL cannot write them):"]
    for subject, prop, value in facts:
        if subject.startswith("mlink:"):
            text.append(f'  - What says the step {named(step_of[subject])} uses it: "{value}"')
        elif subject != first.subject:
            text.append(f'  - A sentence for the scope note of {named(subject)}: "{value}"')
        else:
            text.append(f"  - {FACT_WORDS[prop].format(value)}")
    kind = new_measures.tail(next(c.target for c in changes if c.predicate == "kpi:measureKind"))
    prefix = new_measures.PREFIX.get(kind)
    text += ["", f"Its identifier: the apply gives it the next free {prefix}- number." if prefix else
             f"Its identifier: none, because a {kind.replace('-', ' ')} takes none."]
    reached = other_modules.modules_of(changes)
    text += ["", "The changes reach these modules: " + ", ".join(f"{m} ({r})" for m, r in reached.items()) + "."]
    text += [""] + [f"For the Architect: {note}" for note in notes] if notes else []
    text += ["", f"The route: {route}. This is {ROUTE_WHY[route]}.", "", "Who signed:"]
    text += [f"  - {s['role']}, on {s['date']}" for s in record["signatures"]]
    text += ["", f"The KGCL lines, in {proposal.CHANGE_FILE}:"] + [f"  {line}" for line in lines]
    text += ["", f"The facts, in {proposal.FACTS_FILE}:"] + [f"  {row}" for row in proposal.facts_text(facts).splitlines()]
    text += ["", "Nothing in the ontology has changed yet. To apply this proposal, run in the release folder:",
             "  python -m kpi_store.apply <the path of this folder>", ""]
    return "\n".join(text)


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
        facts = []
        if intake.form == KPI:
            key, changes, facts, notes = kpi_changes(cat, intake, data["lists"], root)
            module, compatible = "kpi", "yes"
            checks = lambda changes, root: other_modules.check_changes(changes, facts, root)
        elif intake.form == ITEM:
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
        if intake.form == KPI:
            text = kpi_summary(change, path.name, changes, facts, notes, lines, route, record, data["lists"])
        elif intake.form == ITEM:
            text = item_summary(change, path.name, key, changes, lines, route, record, data["lists"])
        else:
            text = summary(change, path.name, measure, changes, lines, route, compatible, record, data["lists"]["processes"])
        planned.append((out / change, changes, record, text, lines, facts))
    written = []
    for folder, changes, record, text, lines, facts in planned:
        proposal.write(folder, changes, record, text, facts)
        written.append(folder)
        more = f" and {len(facts)} fact{'s' if len(facts) != 1 else ''}" if facts else ""
        say(f"wrote the proposal {folder.as_posix()}: {len(lines)} change{'s' if len(lines) != 1 else ''}{more}, "
            f"route {record['route']}")
    say("Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>")
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kpi_store.propose",
                                 description="Turn signed KPI intake, term-change and reference-item forms into proposals. "
                                             "Changes nothing in the ontology.")
    ap.add_argument("files", nargs="+", help="KPI intake, term-change or reference-item answers files (.json, or a filled workbook)")
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
