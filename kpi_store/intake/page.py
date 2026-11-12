"""The HTML form: one offline page, built from form.html and the catalogue.

form.html beside this module is the page's template. It holds the styles, the markup (as <template> elements)
and the script. render() puts the form's data into it as one JSON block. The page needs no network: it loads no
script, style or font from anywhere.

The data is the catalogue as the script needs it, with each question's rule already put in words, and the pick
lists that a question names. Two builds of the same inputs give the same bytes on every system.
"""
import json
from pathlib import Path

from kpi_store.intake.catalogue import FORMS

TEMPLATE = Path(__file__).resolve().parent / "form.html"
MARK = "/* EMBEDDED_DATA */"


def data(cat, built, examples):
    """What the page embeds. `built` is the pick lists as picklists.build gives them; `examples` is the example
    answer of each question."""
    questions = []
    for q in cat.questions:
        item = {k: v for k, v in q.items() if k not in ("feeds", "fact", "asked_of", "example", "rows")}
        item["asked_of_text"] = cat.asked_of(q)
        item["requirement"] = cat.requirement(q)
        if examples.get(q["id"]):
            item["example"] = examples[q["id"]]
        questions.append(item)
    used = sorted({q["source"] for q in cat.questions if q.get("source") and ":" not in q["source"]})
    lists = {}
    for name in used:
        # The definition of a measure is for the check. The page compares names only.
        lists[name] = [{k: v for k, v in item.items() if k != "definition"} for item in built["lists"][name]]
    # The names of the terms that the other modules hold, by module, and whether each term has a definition. The
    # page looks the KPI's name up in them, as the check does: a term with a definition may conflict with the KPI's
    # own, and then the Domain Owner signs. The definitions themselves stay out of the page.
    term_names = {}
    for term in built.get("terms", []):
        held = term_names.setdefault(term["module"], {"defined": set(), "undefined": set()})
        held["defined" if term.get("definition") else "undefined"].update(term["names"])
    return {
        "release": cat.release,
        "catalogue_version": cat.version,
        "built_from": built["versions"],
        "forms": FORMS,
        "roles": list(cat.roles.values()),
        "sections": cat.sections,
        "questions": questions,
        "choices": cat.choices,
        "settings_lists": cat.settings_lists,
        "outcomes": cat.outcomes,
        "sign_off": cat.sign_off,
        "request_fields": cat.request_fields,
        "kind_rules": cat.kind_rules,
        "explainer": cat.explainer,
        "lists": lists,
        "term_names": {module: {key: sorted(names) for key, names in held.items()} for module, held in sorted(term_names.items())},
    }


def embed(value):
    """The data as JSON that is safe inside a script element."""
    # The keys keep the order they were given: the forms and the roles are shown in the catalogue's order.
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace("&", "\\u0026"))


def render(cat, built, examples):
    """The page's text."""
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(MARK) != 1:
        raise ValueError(f"{TEMPLATE} must hold the mark {MARK} exactly once")
    return template.replace(MARK, embed(data(cat, built, examples)))
