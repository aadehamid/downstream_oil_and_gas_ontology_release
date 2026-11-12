"""The rules of the intake form: which questions are asked, what a question offers, the kind of measure, the routes.

The check and the workbook reader use these functions. The HTML form applies the same rules in its own script,
from the same catalogue data, and a browser proof checks that the two agree on the examples.

An answer is a text or a list of texts. A choice holds the id of the chosen item. A special option's id starts
with "@" (for example "@not-in-list").

How a stored value finds its entry. An answers file and a browser draft store an entry's id; a workbook cell
stores its label. The organization's settings can hide an entry, give it another label, or add one that the
ontology later gains, so a value stored under earlier settings may no longer be the entry's id or label of today.
One rule reads them all, and resolver() below is that rule:

    A stored value names an entry when it is the entry's id, an id the settings once added it under ("new:<id>"),
    its label of today, or a label it had before (the ontology's own label, or the label of the `add` entry), and
    a label counts with or without the mark of a hidden entry or of a new entry at its end.

Every such value is read as the entry's one id of today. The check (check._resolve), the workbook reader
(workbook.read) and the HTML form (resolverOf in form.html, for a loaded file and a restored draft) all read a
stored value through this rule. picklists.apply_settings writes what the rule needs on each entry: "aliases" (the
added ids) and "was" (the earlier labels). A value that was stored under an added id or under a label with the
"new" mark, for an entry the ontology has since gained, is also flagged, so the reader can say what it did.
"""
from kpi_store.intake.catalogue import ADDED_MARK, CHOICE_TYPES, HIDDEN_MARK, INACTIVE, MANY_TYPES, SETTINGS_LISTS


def values(answers, key):
    """An answer as a list of its non-empty texts."""
    value = answers.get(key)
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [str(v).strip() for v in items if str(v).strip()]


def real_values(answers, key):
    """The values that are not special options."""
    return [v for v in values(answers, key) if not v.startswith("@")]


def is_asked(cat, answers, question, _seen=None):
    """True when every condition of the question holds. A condition on a question that is itself not asked reads
    that question as unanswered, so a chain of yes and no tests stops where it should."""
    seen = _seen or set()
    for cond in question.get("ask_when", []):
        target = cat.by_id[cond["question"]]
        asked = target["id"] not in seen and is_asked(cat, answers, target, seen | {question["id"]})
        held = values(answers, target["id"]) if asked else []
        if "is" in cond and cond["is"] not in held:
            return False
        if "is_not" in cond and cond["is_not"] in held:
            return False
        if "answered" in cond and bool(held) != cond["answered"]:
            return False
    return True


def options(cat, lists, question, answers=None, hidden=False):
    """What a choice question offers, as items with an id and a label: the list's items that the question's levels
    allow, then the question's special options. With answers, a question that says `under` offers only the
    entries under the chosen process. An entry that the organization's settings hide is not offered. With
    hidden=True it is there too, with the mark in its label, for a reader that must know an answer given before
    the entry was hidden."""
    source = question.get("source")
    if question["type"] not in CHOICE_TYPES:
        return []
    fixed = cat.fixed_list(source)
    if fixed is not None:
        items = [dict(item, label=item["label"] + (" (not active)" if item.get("active") is False else "")) for item in fixed]
    else:
        items = [dict(i, label=i["label"] + HIDDEN_MARK) if i.get("hidden") else i for i in lists[source] if hidden or not i.get("hidden")]
        if "levels" in question:
            low, high = question["levels"]
            items = [i for i in items if low <= i["level"] <= high]
        if answers is not None and question.get("under"):
            top = real_values(answers, question["under"])
            if top:
                by_id = {i["id"]: i for i in lists[source]}
                items = [i for i in items if _is_under(by_id, i, top[0])]
    return items + [{"id": o["id"], "label": o["label"]} for o in question.get("option", [])]


def resolver(cat, lists, question):
    """{stored value: (the entry's id, gained)} for a choice question, by the one rule of this module's docstring.
    `gained` is True for a value stored while the entry was only an addition of the settings."""
    out = {}
    if question["type"] not in CHOICE_TYPES:
        return out
    offered = options(cat, lists, question, hidden=True)
    for option in offered:
        out[option["id"]] = (option["id"], False)
    for option in offered:
        out.setdefault(option["label"], (option["id"], False))
    source = question.get("source", "")
    if source not in SETTINGS_LISTS:
        return out
    for item in lists[source]:
        plain = item["label"].removesuffix(ADDED_MARK) if item.get("added") else item["label"]
        gained = bool(item.get("aliases"))
        for name in [plain] + list(item.get("was", [])):
            for mark in ("", HIDDEN_MARK, ADDED_MARK):
                out.setdefault(name + mark, (item["id"], gained and mark == ADDED_MARK))
        for alias in item.get("aliases", []):
            out.setdefault(alias, (item["id"], True))
    return out


def _is_under(by_id, item, ancestor):
    at = by_id.get(item["parent"])
    while at is not None:
        if at["id"] == ancestor:
            return True
        at = by_id.get(at["parent"])
    return False


def positions(answers, key):
    """An answer as a list that keeps its empty places, so a `per` answer stays beside the step it belongs to."""
    value = answers.get(key)
    if value is None:
        return []
    return [str(v).strip() for v in (value if isinstance(value, list) else [value])]


def per_missing(answers, question):
    """For a `per` question: the answers of the question it follows that still lack their own entry here."""
    mine = positions(answers, question["id"])
    return [v for i, v in enumerate(positions(answers, question["per"]))
            if v and not v.startswith("@") and not (i < len(mine) and mine[i])]


def detail_required(question, answers):
    """True when the question's extra text field must be filled."""
    detail = question.get("detail")
    if not detail or detail["required_when"] == "never":
        return False
    if detail["required_when"] == "always":
        return True
    return detail["required_when"] in values(answers, question["id"])


def is_complete(cat, answers, question):
    """True when an asked question has all it needs: its answer, one answer per step for a `per` question, and
    its extra text when that is required."""
    if "per" in question:
        if per_missing(answers, question):
            return False
    elif not values(answers, question["id"]):
        return False
    return not detail_required(question, answers) or bool(values(answers, question["id"] + ".detail"))


def kind(cat, answers):
    """The kind of measure that section 4's answers give: the first kind rule whose question is asked and has that
    answer. None when no rule has decided yet."""
    for rule in cat.kind_rules:
        question = cat.by_id[rule["question"]]
        if is_asked(cat, answers, question) and rule["answer"] in values(answers, question["id"]):
            return rule
    return None


def routes(cat, lists, answers, form):
    """Each route that an answer has taken: (question, route, the answer's label)."""
    taken = []
    for question in cat.questions_of(form):
        if not question.get("route") or not is_asked(cat, answers, question):
            continue
        held = values(answers, question["id"])
        offered = {o["id"]: o for o in options(cat, lists, question)}
        for route in question["route"]:
            if route["when"] == INACTIVE:
                hits = [v for v in held if offered.get(v, {}).get("active") is False]
            else:
                hits = [v for v in held if v == route["when"]]
            for hit in hits:
                taken.append((question, route, offered.get(hit, {}).get("label", hit)))
    return taken


def as_answer(question, texts):
    """A list of texts as the answer of this question: a list for a question with several answers, else one text."""
    if question["type"] in MANY_TYPES:
        return list(texts)
    return texts[0] if texts else ""
