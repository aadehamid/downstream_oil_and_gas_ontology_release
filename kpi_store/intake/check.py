"""The completeness check of a filled intake form.

    python -m kpi_store.intake check <answers.json or filled.xlsx> [--form term-change] [--pack <folder>]

It reads the form, in either format, and says in plain words, section by section, what is missing, which
questions the rules rightly skipped, where an answer routes the request, and what the derived checks found. It
ends with exit status 0 only when the intake is complete and signed, 1 when something is still to do, and 2 when
the file cannot be read.

It changes nothing in the ontology. The Architect applies a complete KPI intake by hand, with HOW-TO-UPDATE.md. A
complete term change or reference item goes to the propose command (kpi_store/propose.py).

The derived checks compare the form with kpi-intake/pick-lists.json, which the build command writes from the
release packages:

    same measure            the name, or a name close to it, is already a measure
    same name elsewhere     the name is a term of another module: consult Enterprise Data Governance
    conflicting definition  that term's definition differs: the Domain Owner decides and signs
    area and process        the chosen process belongs to another business area than the answer to 1.1
    values                  an id or a list value that the ontology does not hold
    to add first            an answer that the organization's settings added and the ontology does not hold yet
    sign-off                a signature, or the record of a consultation, is missing

A term change is also checked against the measure it names: it asks for at least one change, a new name or
definition differs from the one the measure has, an other name to add is not one already, and an other name to
remove is one the measure has.

A reference item is checked against the lists too: a kind that needs a specialist routes the form there, the name
and the other names are texts a KGCL line can hold and that no system of the ontology has, and a table's name is a
full name of the sandbox that the ontology does not hold yet.
"""
import dataclasses
import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from kpi_store.intake import rules
from kpi_store.intake.catalogue import ADDED_MARK, CHOICE_TYPES, FORMS, HIDDEN_MARK, SETTINGS_LISTS

CLOSE = 0.88        # two names at least this alike are shown to a person as a possible match
APPLY = "This check changes nothing in the ontology. The Architect applies a complete intake by hand, with HOW-TO-UPDATE.md."
PROPOSE = ("This check changes nothing in the ontology. The Architect turns a complete {} into a proposal with "
           "python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.")
TERM_CHANGES = ("T2", "T3", "T4", "T5", "T6", "T7")   # the questions of the term change that each ask for a change


@dataclass
class Report:
    lines: list = field(default_factory=list)
    blocking: list = field(default_factory=list)     # each thing that keeps the intake from being complete

    @property
    def complete(self):
        return not self.blocking

    def say(self, text=""):
        self.lines.append(text)

    def block(self, text):
        self.blocking.append(text)

    def text(self):
        return "\n".join(self.lines) + "\n"


def _norm(name):
    """A name as the check compares it: lower case, with punctuation and doubled spaces removed."""
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", name.lower()).split())


def _short(text, limit=70):
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _sections(cat, lists, intake, report):
    answers = intake.answers
    for section in cat.sections:
        if section["form"] != intake.form:
            continue
        questions = cat.questions_of(section=section["id"])
        asked = [q for q in questions if rules.is_asked(cat, answers, q)]
        skipped = [q for q in questions if q not in asked]
        missing, invalid, extra, notes = [], [], [], []
        for q in asked:
            if q["required"] == "required" and not rules.is_complete(cat, answers, q):
                if "per" in q and rules.values(answers, q["id"]):
                    missing.append(f'{q["id"]} needs one answer for each answer to {q["per"]}: {_short(q["text"])}')
                elif rules.values(answers, q["id"]) and rules.detail_required(q, answers):
                    missing.append(f'{q["id"]} also needs: {q["detail"]["label"]}')
                else:
                    missing.append(f'{q["id"]} {_short(q["text"])}')
            elif rules.detail_required(q, answers) and rules.values(answers, q["id"]) and not rules.values(answers, q["id"] + ".detail"):
                missing.append(f'{q["id"]} also needs: {q["detail"]["label"]}')
            invalid += _invalid(cat, lists, answers, q)
            notes += _hidden(cat, lists, answers, q)
        for q in skipped:
            if rules.values(answers, q["id"]):
                extra.append(f'{q["id"]} has an answer, but its rule says it is not asked ({cat.requirement(q)}). Remove the answer or correct the earlier one.')
        done = sum(1 for q in asked if rules.values(answers, q["id"]))
        title = f'{section["id"]}. {section["name"]}' if intake.form == "kpi-intake" else section["name"]
        report.say(title)
        report.say(f"  Answered {done} of the {len(asked)} questions that apply.")
        if missing:
            report.say("  Missing:")
            for line in missing:
                report.say("    " + line)
                report.block(f"{line.split(' ', 1)[0]} is missing")
        for line in invalid:
            report.say("  Not in the ontology: " + line)
            report.block(line)
        for line in extra:
            report.say("  " + line)
            report.block(line)
        for line in notes:
            report.say("  Note: " + line)
        if skipped:
            report.say("  Rightly skipped: " + "; ".join(f'{q["id"]} ({cat.requirement(q)})' for q in skipped if not rules.values(answers, q["id"])))
        if not (missing or invalid or extra):
            report.say("  Nothing is missing.")
        report.say()


def _invalid(cat, lists, answers, question):
    """Each value of a choice question that its list does not hold, as a sentence."""
    if question["type"] not in CHOICE_TYPES:
        return []
    offered = {o["id"]: o for o in rules.options(cat, lists, question, hidden=True)}
    under = {o["id"] for o in rules.options(cat, lists, question, answers, hidden=True)} if question.get("under") else None
    out = []
    held = rules.values(answers, question["id"])
    if question["type"] == "choice" and len(held) > 1:
        out.append(f'{question["id"]} takes one answer and has {len(held)}.')
    for value in held:
        if value not in offered:
            out.append(f'{question["id"]}: "{_short(value)}" is not in the list of {question["source"].split(":")[-1].replace("-", " ")}.')
        elif under is not None and value not in under:
            out.append(f'{question["id"]}: "{offered[value]["label"]}" is not under the process chosen in {question["under"]}.')
        elif "(deprecated)" in offered[value]["label"]:
            out.append(f'{question["id"]}: "{offered[value]["label"]}" is deprecated in the ontology. Choose the term that replaced it.')
    return out


def _hidden(cat, lists, answers, question):
    """Each answer that names an entry the organization's settings now hide, as a sentence. The answer stands."""
    if question["type"] not in CHOICE_TYPES:
        return []
    offered = {o["id"]: o for o in rules.options(cat, lists, question, hidden=True)}
    return [f'{question["id"]}: "{offered[v]["label"].removesuffix(HIDDEN_MARK)}" is hidden in this organization\'s settings. '
            "The forms no longer offer it. The answer was given before, and it stands."
            for v in rules.values(answers, question["id"]) if offered.get(v, {}).get("hidden")]


def _to_add(cat, lists, intake, report):
    """The answers that name an entry the organization's settings added. The ontology does not hold it yet, so the
    Architect adds it before the KPI is applied. It does not stop the intake from being complete."""
    lines = []
    for question in cat.questions_of(intake.form):
        module = SETTINGS_LISTS.get(question.get("source"))
        if not module or not rules.is_asked(cat, intake.answers, question):
            continue
        offered = {o["id"]: o for o in rules.options(cat, lists, question, hidden=True)}
        for value in rules.values(intake.answers, question["id"]):
            if offered.get(value, {}).get("added"):
                name = offered[value]["label"].removesuffix(ADDED_MARK)
                lines.append(f'{question["id"]} names "{name}". The organization\'s settings added it, and the ontology does not hold it yet. '
                             f"Add it to the {module} module with HOW-TO-UPDATE.md before you apply this KPI.")
    if lines:
        report.say("To add to the ontology first")
        for line in lines:
            report.say("  For the Architect: " + line)
        report.say()


def _routing(cat, lists, intake, report):
    taken = rules.routes(cat, lists, intake.answers, intake.form)
    report.say("Routing")
    if not taken:
        report.say("  No answer routes this request elsewhere.")
    needs = set()
    for question, route, label in taken:
        outcome = cat.outcomes[route["outcome"]]
        report.say(f'  {outcome["title"]}: {question["id"]} is "{label}". {route["notice"]}')
        if outcome.get("next"):
            report.say("    " + outcome["next"])
        if outcome["blocks"]:
            report.block(f'{question["id"]} routes the request: {outcome["title"].lower()}')
        if outcome.get("consult"):
            needs.add(outcome["consult"])
    report.say()
    return needs


def _example(lists, notation, name, definition):
    """The measure that a shipped example copies, while the file is still that example: its name and its definition
    still equal the measure's label and definition. Once either one changes, the file is a new request, and None
    comes back. A file that is still the example adds nothing new, so letting it pass does no harm."""
    for measure in lists["measures"]:
        if (notation and measure.get("notation") == notation and _norm(name) == _norm(measure["label"])
                and _norm(definition) and _norm(definition) == _norm(measure.get("definition", ""))):
            return measure
    return None


def _derived(cat, lists, terms, intake, report):
    """The checks of the KPI form against the ontology. Returns what they require of the sign-off:
    (the consultations to record, whether the Domain Owner must sign)."""
    answers = intake.answers
    report.say("Checks against the ontology")
    found = False
    name = "".join(rules.values(answers, "2.1")[:1])
    definition = "".join(rules.values(answers, "2.2")[:1])
    consult, conflict = set(), False
    example = _example(lists, intake.example_of, name, definition)
    if intake.example_of and not example:
        found = True
        copied = next((m["label"] for m in lists["measures"] if m.get("notation") == intake.example_of), None)
        if copied:
            report.say(f'  Example changed: this file started from the shipped example of "{copied}", and its name (2.1) '
                       "or its definition (2.2) has changed since. It is checked as a new request, like any other form.")
        else:
            report.say(f'  "Example of" holds "{intake.example_of}", which is not a measure in the ontology, so it is '
                       "ignored. The file is checked as a new request, like any other form.")
    if name:
        wanted = _norm(name)
        for measure in lists["measures"]:
            names = [measure["label"]] + measure.get("other_names", [])
            exact = wanted in {_norm(n) for n in names}
            same_text = bool(definition) and _norm(definition) == _norm(measure.get("definition", ""))
            close = max(difflib.SequenceMatcher(None, wanted, _norm(n)).ratio() for n in names)
            if exact or same_text:
                found = True
                why = "has this name" if exact else "has this definition"
                if measure is example:
                    report.say(f'  Same measure: the ontology already holds "{measure["label"]}". This file is a shipped example '
                               "of that measure, filled in as if it were new, so the match is expected.")
                else:
                    report.say(f'  Same measure: the measure "{measure["label"]}" already {why}. '
                               "Stop the form. The request becomes a change to that measure.")
                    report.block(f'the measure "{measure["label"]}" already {why}')
            elif close >= CLOSE:
                found = True
                report.say(f'  Close match: the measure "{measure["label"]}" has a name close to "{name}". '
                           "Confirm with the Data Owner that the two are different measures.")
        for term in terms:
            if wanted in {_norm(n) for n in term["names"]}:
                found = True
                consult.add("enterprise-data-governance")
                report.say(f'  Same name in another module: the {term["module"]} module holds a term named "{name}" ({term["id"]}). '
                           "Consult Enterprise Data Governance and record the outcome in the sign-off block.")
                if term.get("definition") and definition and _norm(term["definition"]) != _norm(definition):
                    conflict = True
                    report.say(f'    Its definition differs: "{_short(term["definition"], 160)}" '
                               "The Domain Owner decides between the two and signs.")
    area = "".join(rules.real_values(answers, "1.1")[:1])
    process = "".join((rules.real_values(answers, "1.3") or rules.real_values(answers, "1.2"))[:1])
    by_id = {p["id"]: p for p in lists["processes"]}
    if area and process in by_id:
        entry = by_id[process]
        areas = [entry["area"]] if entry["area"] else entry["areas"]
        names = {a["id"]: a["label"] for a in lists["business-areas"]}
        if areas and area not in areas:
            found = True
            line = (f'the process "{entry["label"]}" belongs to {" and ".join(names.get(a, a) for a in areas)}, '
                    f'and the answer to 1.1 is {names.get(area, area)}')
            report.say(f"  Area and process: {line}. Return the form to the Business analyst.")
            report.block(line)
        elif not areas:
            found = True
            report.say(f'  Area and process: the process "{entry["label"]}" carries no business area in the ontology, '
                       "so the answer to 1.1 could not be compared.")
    register = {r["id"] for r in lists["roles"] if r.get("group") == "Role register"}
    outside = [r for r in rules.real_values(answers, "6.1") if r in register]
    if outside:
        found = True
        report.say(f"  Roles: {len(outside)} of the chosen roles are in the role register. The kpi builder writes only the four "
                   "planning personas today, so the Architect must extend it before these roles can be recorded.")
    if not found:
        report.say("  The name is new, and the chosen process agrees with the business area.")
    report.say()
    return consult, conflict


def _term_change(lists, intake, report):
    """The checks of a term change against the measure it names: it asks for at least one change, and each change
    fits the measure as the pick lists hold it. The apply command checks the same against the kpi tables again."""
    from kpi_store.change.kgcl import text_problem
    answers = intake.answers
    measure = next((m for m in lists["measures"] if m["id"] in rules.values(answers, "T1")), None)
    lines = []
    if not any(rules.values(answers, q) for q in TERM_CHANGES):
        lines.append("the form asks for no change: answer at least one of T2 to T7")
    for key in ("T2", "T3", "T4", "T5"):
        for text in rules.values(answers, key):
            problem = text_problem(text)
            if problem:
                lines.append(f'{key}: "{_short(text)}": {problem}')
    name, definition = "".join(rules.values(answers, "T2")[:1]), "".join(rules.values(answers, "T3")[:1])
    gained, lost = rules.values(answers, "T4"), rules.values(answers, "T5")
    if measure:
        others = measure.get("other_names", [])
        if name == measure["label"]:
            lines.append(f'T2: "{name}" is the measure\'s name already. Leave T2 empty to keep it')
        elif name in others and name not in lost:
            lines.append(f'T2: "{name}" is an other name of the measure. List it under T5 too, so it stops being one')
        if definition and definition == measure.get("definition", ""):
            lines.append("T3 is the measure's definition already. Leave T3 empty to keep it")
        for other in gained:
            if ";" in other:
                lines.append(f'T4: "{_short(other)}" holds a semicolon, which the ontology\'s tables use between other names')
            elif other in others:
                lines.append(f'T4: "{other}" is an other name of the measure already')
            elif other == (name or measure["label"]):   # the old name may stay as an other name after a rename
                lines.append(f'T4: "{other}" is the measure\'s name, so it cannot be an other name too')
        for other in lost:
            if other not in others:
                held = "; ".join(f'"{o}"' for o in others) or "none"
                lines.append(f'T5: "{other}" is not an other name of the measure. Its other names are: {held}')
    for other in sorted(set(gained) & set(lost)):
        lines.append(f'T4 and T5 both name "{other}"')
    labels = {p["id"]: p["label"] for p in lists["processes"]}
    for process in sorted(set(rules.real_values(answers, "T6")) & set(rules.real_values(answers, "T7"))):
        lines.append(f'T6 and T7 both name the process "{labels.get(process, process)}"')
    report.say("Checks of the change")
    for line in lines:
        report.say("  " + line + ".")
        report.block(line)
    if not lines:
        report.say("  Each change fits the measure.")
    report.say()


def _reference_item(lists, terms, intake, report):
    """The checks of a new system or table against the lists. The propose command checks the same against the
    module's tables again. A kind that needs a specialist is refused by its route, so it is not checked here."""
    from kpi_store.change.kgcl import text_problem
    from kpi_store.change.reference_items import SANDBOX, slug_of
    from kpi_store.cut import FULL_NAME
    answers = intake.answers
    kind = "".join(rules.values(answers, "R2")[:1])
    if kind not in ("system", "table"):
        return
    name = "".join(rules.values(answers, "R1")[:1])
    others = rules.values(answers, "R4") if kind == "system" else []
    lines = []
    for key, text in [("R1", name), *(("R4", o) for o in others), ("R3", "".join(rules.values(answers, "R3")[:1]))]:
        problem = text and text_problem(text)
        if problem:
            lines.append(f'{key}: "{_short(text)}": {problem}')
    if kind == "system" and name:
        system_ns = "https://w3id.org/mpc/ontology/modules/system/system/"
        held = {}
        for term in terms:
            if term["id"].startswith(system_ns):
                for n in term["names"]:
                    held.setdefault(n.casefold(), n)
        keys = {i["id"].rsplit("/", 1)[-1] for i in lists["systems"]}
        key = slug_of("system", name)
        if not key:
            lines.append(f'R1: "{_short(name)}" has no letter or digit to make the short key of the system from')
        elif key in keys:
            lines.append(f'R1: the ontology has a system with the short key "{key}" already. Give the system a name of its own')
        for k, n in [("R1", name), *(("R4", o) for o in others)]:
            if n.casefold() in held:
                lines.append(f'{k}: "{n}" is a name of a system the ontology holds already')
        for o in others:
            if ";" in o:
                lines.append(f'R4: "{_short(o)}" holds a semicolon, which the ontology\'s tables use between other names')
            elif o == name:
                lines.append(f'R4: "{o}" is the name of the system, so it cannot be an other name too')
        for o in sorted({o for o in others if others.count(o) > 1}):
            lines.append(f'R4 names "{o}" twice')
    if kind == "table" and name:
        if not FULL_NAME.fullmatch(name):
            lines.append(f'R1: "{_short(name)}" is not a full name of the form catalog.schema.table')
        elif not name.startswith(SANDBOX):
            lines.append(f'R1: the ontology holds the sandbox\'s tables only, whose names start with {" or ".join(SANDBOX)}')
        if name.casefold() in {i["label"].casefold() for i in lists["platform-tables"]}:
            lines.append(f'R1: the ontology holds the table {name} already')
        system = "".join(rules.real_values(answers, "R8")[:1])
        key = slug_of("table", name, system.rsplit("/", 1)[-1]) if system else ""
        if key and key in {i["id"].rsplit("/", 1)[-1] for i in lists["platform-tables"]}:
            lines.append(f'R1: the ontology has a table with the short key "{key}" already')
    report.say("Checks of the new item")
    for line in lines:
        report.say("  " + line + ".")
        report.block(line)
    if not lines:
        report.say("  The new item fits the ontology.")
    report.say()


def _sign_off(cat, intake, report, consult, conflict):
    report.say("Sign-off")
    for signer in cat.signers(intake.form):
        needed = cat.is_needed(signer, intake.form, intake.answers, conflict)
        given = intake.sign_offs.get(signer["id"], {})
        signed = bool(given.get("name", "").strip() and given.get("date", "").strip())
        meaning = cat.meaning(signer, intake.form)
        role = f'{cat.roles[signer["role"]]["short"]} ("{meaning}")'
        if signed:
            report.say(f'  {role}: signed on {given["date"].strip()}.')
        elif needed:
            report.say(f"  {role}: not signed. A signature needs a name and a date.")
            report.block(f'the {cat.roles[signer["role"]]["short"]} has not signed: "{meaning}"')
        else:
            report.say(f"  {role}: not needed. {signer['required'].split('.')[0]}.")
    for item in cat.sign_off["consulted"]:
        if intake.form != "kpi-intake" or item["id"] not in consult:
            continue
        given = intake.consulted.get(item["id"], {})
        if given.get("date", "").strip() and given.get("outcome", "").strip():
            report.say(f'  {item["who"]}: consulted on {given["date"].strip()}. Outcome: {given["outcome"].strip()}')
        else:
            report.say(f'  {item["who"]}: to consult. Record the date and the outcome.')
            report.block(f'{item["who"]} must be consulted, and the form records no date and outcome')
    report.say()


def _resolve(cat, lists, intake):
    """The intake with each answer on a list the settings can change read as its entry's id of today, by the one
    rule of rules.py, and a sentence for each answer stored under an addition the ontology has since gained. The
    file itself is not changed."""
    answers, notes = dict(intake.answers), []
    for question in cat.questions_of(intake.form):
        if question["type"] not in CHOICE_TYPES or question.get("source") not in SETTINGS_LISTS or question["id"] not in answers:
            continue
        known = rules.resolver(cat, lists, question)
        labels = {item["id"]: item["label"] for item in lists[question["source"]]}
        read = []
        for value in rules.positions(answers, question["id"]):
            if value in known and not value.startswith("@"):
                value, gained = known[value]
                if gained:
                    notes.append(f'{question["id"]}: "{labels[value]}" is now in the ontology; the answer was read as that entry.')
            if value not in read or "per" in question:
                read.append(value)
        answers[question["id"]] = rules.as_answer(question, read)
    return dataclasses.replace(intake, answers=answers), notes


def check(cat, data, intake, stale=None):
    """The report on one filled form. `data` is the built pick lists; `stale` names the modules whose packages are
    newer than the lists."""
    lists, terms = data["lists"], data.get("terms", [])
    report = Report()
    intake, renamed = _resolve(cat, lists, intake)
    first = "2.1" if intake.form == "kpi-intake" else cat.questions_of(intake.form)[0]["id"]
    name = intake.kpi_name or "; ".join(rules.values(intake.answers, first)[:2])
    if intake.form == "term-change":   # the name of the measure, not its IRI
        name = next((m["label"] for m in lists["measures"] if m["id"] == name), name)
    report.say(f'{FORMS[intake.form]} check: {name or "(no name yet)"}')
    report.say(f'Catalogue {cat.version}. Pick lists of {data.get("release", cat.release)}.')
    if intake.catalogue_version and intake.catalogue_version != cat.version:
        report.say(f"Note: the form was filled with catalogue {intake.catalogue_version}. This check uses {cat.version}.")
    if stale:
        changed = ", ".join(f"{m} ({old} then, {new} now)" for m, (old, new) in stale.items())
        report.say(f"The pick lists are older than the release packages: {changed}. Rebuild them first: python -m kpi_store.intake build")
        report.block("the pick lists are older than the release packages")
    for key in intake.unknown_keys:
        report.say(f"Note: the workbook holds an answer under {key}, which is no question of this form. It was not read.")
    for line in renamed:
        report.say("Note: " + line)
    report.say()
    _sections(cat, lists, intake, report)
    if intake.form == "kpi-intake":
        rule = rules.kind(cat, intake.answers)
        if rule:
            report.say(f'Kind of measure: {rule["kind"]} (decided by {rule["question"]}, test {rule["test"]}).'
                       + (" " + rule["note"] if rule.get("note") else ""))
        else:
            report.say("Kind of measure: not decided yet. Answer section 4.")
        report.say()
    consult = _routing(cat, lists, intake, report)
    _to_add(cat, lists, intake, report)
    conflict = False
    if intake.form == "kpi-intake":
        more, conflict = _derived(cat, lists, terms, intake, report)
        consult |= more
    if intake.form == "term-change":
        _term_change(lists, intake, report)
    if intake.form == "reference-item":
        _reference_item(lists, terms, intake, report)
    _sign_off(cat, intake, report, consult, conflict)
    if report.complete:
        report.say("Result: the intake is complete and signed.")
    else:
        count = len(report.blocking)
        report.say(f"Result: not complete. {count} {'thing' if count == 1 else 'things'} to settle:")
        for line in report.blocking:
            report.say("  - " + line)
    report.say(PROPOSE.format(FORMS[intake.form].lower()) if intake.form in ("term-change", "reference-item") else APPLY)
    return report


def run(path, pack, form=None, root=None):
    """Reads the pack and the file, and returns the report. Raises CatalogueError, AnswersError or ReleaseError."""
    from kpi_store.intake import answers, catalogue, picklists
    pack = Path(pack)
    cat = catalogue.load(pack)
    data = picklists.load(pack)
    intake = answers.read(path, cat, data["lists"], form)
    stale = picklists.stale_modules(data, root) if root else None
    return check(cat, data, intake, stale)
