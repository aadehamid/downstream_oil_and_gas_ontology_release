"""Reads the intake catalogue (catalogue.toml) and the organization's settings (settings.toml), and validates them.

The catalogue is the one place a question is written. The forms, the check and the generated pages all read it
through this module, so a mistake in the file is reported here, once, with the question it belongs to.

A pick list has one of three sources, and a question names it in `source`:

    "<name>"            a list read from the release packages (ONTOLOGY_LISTS, built by picklists.py)
    "choices:<name>"    a short fixed list in the catalogue, the same in every organization
    "settings:<name>"   a list the organization sets for itself in settings.toml; an item may say active = false

Standard library only (tomllib).
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PACK = Path(__file__).resolve().parents[2] / "kpi-intake"   # the pack's folder in this release
FORMS = {"kpi-intake": "KPI intake", "domain-activation": "Domain activation", "process-map-request": "Process map request"}
TYPES = ("text", "long_text", "choice", "multi_choice", "list")
CHOICE_TYPES = ("choice", "multi_choice")
MANY_TYPES = ("multi_choice", "list")          # the answer is a list of values
ONTOLOGY_LISTS = (
    "business-areas", "processes", "measures", "roles", "value-stream-steps", "measure-relationships",
    "data-products", "platform-tables", "layers", "data-product-kinds", "systems", "sources", "modules",
    "areas-and-modules",
)
INACTIVE = "@inactive"      # a route's `when` that matches any chosen item whose settings say active = false
DEFAULT_ROWS = 5            # rows the workbook gives a question with several answers


class CatalogueError(Exception):
    """The catalogue or the settings file is wrong. The message lists every problem found."""


@dataclass
class Catalogue:
    version: str
    release: str
    roles: dict                      # {id: role}, in the settings file's order
    sections: list
    questions: list
    choices: dict                    # {name: [item]} from the catalogue
    settings_lists: dict             # {name: [item]} from settings.toml
    outcomes: dict
    sign_off: dict
    request_fields: list
    kind_rules: list
    explainer: dict
    facts: list
    gaps: list
    architect_notes: list = field(default_factory=list)
    by_id: dict = field(default_factory=dict)

    def section(self, section_id):
        return next(s for s in self.sections if s["id"] == section_id)

    def form_of(self, question):
        return self.section(question["section"])["form"]

    def questions_of(self, form=None, section=None):
        return [q for q in self.questions
                if (form is None or self.form_of(q) == form) and (section is None or q["section"] == section)]

    def fixed_list(self, source):
        """The items of a "choices:" or "settings:" source, or None for a list the ontology holds."""
        kind, _, name = source.partition(":")
        if kind == "choices":
            return self.choices[name]
        if kind == "settings":
            return self.settings_lists[name]
        return None

    def signers(self, form):
        return [s for s in self.sign_off["signer"] if form in s["forms"]]

    def asked_of(self, question):
        """Who answers, as the forms print it."""
        return question.get("asked_of_text") or ", ".join(self.roles[r]["short"] for r in question["asked_of"])

    def requirement(self, question):
        """The rule in plain words: required, optional, or the condition."""
        base = "Required" if question["required"] == "required" else "Optional"
        if question.get("ask_when_text"):
            return question["ask_when_text"]
        parts = []
        for cond in question.get("ask_when", []):
            if "is" in cond:
                parts.append(f'{cond["question"]} is "{self.option_label(cond["question"], cond["is"])}"')
            elif "is_not" in cond:
                parts.append(f'{cond["question"]} is not "{self.option_label(cond["question"], cond["is_not"])}"')
            else:
                parts.append(f'{cond["question"]} has an answer' if cond["answered"] else f'{cond["question"]} has no answer')
        return base + (" if " + " and ".join(parts) if parts else "")

    def option_label(self, question_id, option_id):
        """The label of one of a question's catalogue options: a fixed choice or a special option. An item of a
        list the ontology holds has no label here, so its id comes back."""
        question = self.by_id[question_id]
        fixed = self.fixed_list(question.get("source", "")) or []
        for item in list(fixed) + question.get("option", []):
            if item["id"] == option_id:
                return item["label"].lower()
        return option_id.rsplit("/", 1)[-1]


def _read(path):
    try:
        with Path(path).open("rb") as f:
            return tomllib.load(f)
    except OSError as e:
        raise CatalogueError(f"{path} cannot be read: {e}") from None
    except tomllib.TOMLDecodeError as e:
        raise CatalogueError(f"{path} is not valid TOML: {e}") from None


def load(folder=PACK):
    """The catalogue of a pack folder, validated. Raises CatalogueError with every problem it finds."""
    folder = Path(folder)
    raw, settings = _read(folder / "catalogue.toml"), _read(folder / "settings.toml")
    problems = []
    for key in ("version", "release", "section", "question", "outcome", "sign_off", "request_field", "kind_rule",
                "explainer", "fact", "gap"):
        if key not in raw:
            problems.append(f"catalogue.toml has no `{key}`")
    if "role" not in settings:
        problems.append("settings.toml has no `role`")
    if problems:
        raise CatalogueError("\n".join(problems))
    cat = Catalogue(
        version=str(raw["version"]), release=str(raw["release"]),
        roles={r["id"]: r for r in settings["role"]},
        sections=raw["section"], questions=raw["question"], choices=raw.get("choices", {}),
        settings_lists=settings.get("list", {}), outcomes=raw["outcome"], sign_off=raw["sign_off"],
        request_fields=raw["request_field"], kind_rules=raw["kind_rule"], explainer=raw["explainer"],
        facts=raw["fact"], gaps=raw["gap"], architect_notes=raw.get("architect", {}).get("notes", []))
    for question in cat.questions:
        cat.by_id.setdefault(question.get("id"), question)
    problems = _problems(cat)
    if problems:
        raise CatalogueError("\n".join(problems))
    return cat


def _problems(cat):
    """Every way the two files contradict themselves, as sentences."""
    out = []
    seen = set()
    section_ids = [s.get("id") for s in cat.sections]
    for s in cat.sections:
        for key in ("id", "form", "name", "technical_name", "audience", "about", "who", "done_when"):
            if not s.get(key):
                out.append(f"section {s.get('id')!r} has no `{key}`")
        if s.get("form") not in FORMS:
            out.append(f"section {s.get('id')!r} names the form {s.get('form')!r}; the forms are {', '.join(FORMS)}")
    if len(set(section_ids)) != len(section_ids):
        out.append("two sections have the same id")
    for name, items in list(cat.choices.items()) + list(cat.settings_lists.items()):
        ids = [i.get("id") for i in items]
        if len(set(ids)) != len(ids) or not all(i.get("id") and i.get("label") for i in items):
            out.append(f"the list {name!r} needs an id and a label on every item, and no id twice")
    for role_id, role in cat.roles.items():
        for key in ("title", "short", "definition", "in_intake"):
            if not role.get(key):
                out.append(f"role {role_id!r} has no `{key}`")
    for q in cat.questions:
        qid = q.get("id")
        where = f"question {qid!r}"
        if not qid:
            out.append("a question has no id")
            continue
        if qid in seen:
            out.append(f"{where}: the id is used twice")
        seen.add(qid)
        for key in ("section", "text", "asked_of", "type", "required", "why", "feeds"):
            if not q.get(key):
                out.append(f"{where} has no `{key}`")
        if q.get("section") not in section_ids:
            out.append(f"{where} names the section {q.get('section')!r}, which does not exist")
        if q.get("type") not in TYPES:
            out.append(f"{where} has the type {q.get('type')!r}; the types are {', '.join(TYPES)}")
        if q.get("required") not in ("required", "optional"):
            out.append(f"{where}: `required` is \"required\" or \"optional\"")
        for role in q.get("asked_of", []):
            if role not in cat.roles:
                out.append(f"{where} is asked of {role!r}, which is no role in settings.toml")
        source = q.get("source")
        if q.get("type") in CHOICE_TYPES:
            if not source:
                out.append(f"{where} is a choice and names no `source`")
            elif ":" in source:
                kind, _, name = source.partition(":")
                held = {"choices": cat.choices, "settings": cat.settings_lists}.get(kind)
                if held is None or name not in held:
                    out.append(f"{where} names the list {source!r}, which does not exist")
            elif source not in ONTOLOGY_LISTS:
                out.append(f"{where} names the list {source!r}; the ontology's lists are {', '.join(ONTOLOGY_LISTS)}")
        elif source:
            out.append(f"{where} is not a choice, so it takes no `source`")
        option_ids = [o.get("id", "") for o in q.get("option", [])]
        if not all(o.startswith("@") for o in option_ids) or len(set(option_ids)) != len(option_ids):
            out.append(f"{where}: each special option needs its own id that starts with @")
        try:
            fixed = cat.fixed_list(source or "") or []
        except KeyError:        # a list that does not exist; reported above
            fixed = []
        known = set(option_ids) | {i["id"] for i in fixed}
        for route in q.get("route", []):
            if route.get("outcome") not in cat.outcomes:
                out.append(f"{where} routes to {route.get('outcome')!r}, which is no outcome")
            if route.get("when") != INACTIVE and route.get("when") not in known:
                out.append(f"{where} routes on {route.get('when')!r}, which is none of its options")
            if not route.get("notice"):
                out.append(f"{where} has a route with no `notice`")
            for other in route.get("request_questions", []):
                if other not in cat.by_id:
                    out.append(f"{where} routes to the question {other!r}, which does not exist")
        for cond in q.get("ask_when", []):
            target = cat.by_id.get(cond.get("question"))
            if target is None:
                out.append(f"{where} depends on the question {cond.get('question')!r}, which does not exist")
            elif cond.get("question") == qid:
                out.append(f"{where} depends on itself")
            if sum(key in cond for key in ("is", "is_not", "answered")) != 1:
                out.append(f"{where}: a condition has exactly one of `is`, `is_not` and `answered`")
        for key in ("narrow_by", "under", "per"):
            if key in q and q[key] not in cat.by_id:
                out.append(f"{where}: `{key}` names the question {q[key]!r}, which does not exist")
        if "per" in q and q.get("type") not in MANY_TYPES:
            out.append(f"{where}: `per` needs a question with several answers")
        detail = q.get("detail")
        if detail is not None:
            if not detail.get("label") or detail.get("type") not in ("text", "long_text"):
                out.append(f"{where}: its detail needs a label and the type text or long_text")
            if detail.get("required_when") not in {"always", "never"} | known:
                out.append(f"{where}: its detail is required when {detail.get('required_when')!r}, which is none of its options")
        for fact in q.get("fact", []):
            if fact not in {f["id"] for f in cat.facts}:
                out.append(f"{where} feeds the fact {fact!r}, which does not exist")
    for name, cycle in _cycles(cat):
        out.append(f"question {name!r} depends on itself through {' and '.join(cycle)}")
    for rule in cat.kind_rules:
        if rule.get("question") not in cat.by_id:
            out.append(f"a kind rule names the question {rule.get('question')!r}, which does not exist")
    for fact in cat.facts:
        for qid in fact.get("supplied_by", []):
            if qid not in cat.by_id:
                out.append(f"fact {fact.get('id')!r} is supplied by {qid!r}, which does not exist")
    for gap in cat.gaps:
        if gap.get("question") and gap["question"] not in cat.by_id:
            out.append(f"a gap names the question {gap['question']!r}, which does not exist")
    consulted = {c["id"] for c in cat.sign_off.get("consulted", [])}
    for signer in cat.sign_off.get("signer", []):
        if signer.get("role") not in cat.roles:
            out.append(f"the signer {signer.get('id')!r} has the role {signer.get('role')!r}, which is no role")
        if not set(signer.get("forms", [])) <= set(FORMS):
            out.append(f"the signer {signer.get('id')!r} names a form that does not exist")
        if signer.get("when") not in ("always", "conflict"):
            out.append(f"the signer {signer.get('id')!r}: `when` is \"always\" or \"conflict\"")
    for name, outcome in cat.outcomes.items():
        if outcome.get("consult") and outcome["consult"] not in consulted:
            out.append(f"the outcome {name!r} names {outcome['consult']!r}, which the sign-off block does not hold")
        if not outcome.get("title") or "blocks" not in outcome:
            out.append(f"the outcome {name!r} needs a title and `blocks`")
    return out


def _cycles(cat):
    """Each question whose `ask_when` leads back to itself, with the path."""
    found = []
    for q in cat.questions:
        path, todo = [], [(q["id"], [])]
        visited = set()
        while todo:
            current, trail = todo.pop()
            for cond in cat.by_id.get(current, {}).get("ask_when", []):
                target = cond.get("question")
                if target == q["id"] and trail:
                    path = trail + [current]
                    todo = []
                    break
                if target in cat.by_id and target not in visited:
                    visited.add(target)
                    todo.append((target, trail + [current]))
        if path:
            found.append((q["id"], path))
    return found
