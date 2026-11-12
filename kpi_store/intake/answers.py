"""The answers file of the intake form: its shape, and how to read and write it as JSON.

One file holds one filled form. The HTML form saves it, and the workbook reader (workbook.py) builds the same
structure from a filled workbook, so the check reads both the same way. kpi-intake/answers.schema.json states
the shape as a JSON Schema, and structure_problems() below checks it without any package.

    {
      "format": 1,
      "form": "kpi-intake",                 or "domain-activation"
      "catalogue_version": "1.0",
      "kpi_name": "...",                    the answer to 2.1, repeated so a person can tell files apart
      "request": {"number": "", "date": "", "requester_role": "", "invited": ""},
      "answers": {"1.1": "<id>", "5.1": ["...", "..."], "3.5.detail": "..."},
      "sign_offs": {"data-owner": {"name": "", "date": ""}},
      "consulted": {"enterprise-data-governance": {"date": "", "outcome": ""}},
      "example_of": "",                     only in the shipped examples: the measure the example copies
      "comment": ""
    }

An answer is a text, or a list of texts for a question with several answers. A choice holds the id of the chosen
item, as kpi-intake/pick-lists.json gives it. The extra text of a question is under "<question>.detail".
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from kpi_store.intake.catalogue import FORMS

FORMAT = 1


class AnswersError(Exception):
    """The file is not an answers file the check can read."""


@dataclass
class Intake:
    form: str = "kpi-intake"
    catalogue_version: str = ""
    kpi_name: str = ""
    request: dict = field(default_factory=dict)
    answers: dict = field(default_factory=dict)
    sign_offs: dict = field(default_factory=dict)
    consulted: dict = field(default_factory=dict)
    example_of: str = ""
    comment: str = ""
    unknown_keys: list = field(default_factory=list)   # answers a workbook holds under a key the catalogue lacks

    def as_dict(self):
        return {"format": FORMAT, "form": self.form, "catalogue_version": self.catalogue_version,
                "kpi_name": self.kpi_name, "request": dict(self.request), "answers": dict(self.answers),
                "sign_offs": {k: dict(v) for k, v in self.sign_offs.items()},
                "consulted": {k: dict(v) for k, v in self.consulted.items()},
                "example_of": self.example_of, "comment": self.comment}


def _text_map(value, keys, where, out):
    if not isinstance(value, dict):
        out.append(f"`{where}` must be an object")
        return
    for name, entry in value.items():
        if not isinstance(entry, dict) or set(entry) - set(keys) or not all(isinstance(v, str) for v in entry.values()):
            out.append(f"`{where}.{name}` must be an object with the texts {' and '.join(keys)}")


def structure_problems(data):
    """Every way the data is not an answers file, as sentences. An empty list means the shape is right."""
    if not isinstance(data, dict):
        return ["the file must hold one JSON object"]
    out = []
    if data.get("format") != FORMAT:
        out.append(f"`format` must be {FORMAT}")
    if data.get("form") not in FORMS:
        out.append("`form` must be " + " or ".join(f'"{f}"' for f in FORMS))
    for key in ("catalogue_version", "kpi_name", "example_of", "comment"):
        if not isinstance(data.get(key, ""), str):
            out.append(f"`{key}` must be a text")
    request = data.get("request", {})
    if not isinstance(request, dict) or not all(isinstance(v, str) for v in request.values()):
        out.append("`request` must be an object of texts")
    answers = data.get("answers")
    if not isinstance(answers, dict):
        out.append("`answers` must be an object")
    else:
        for key, value in answers.items():
            if not (isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value))):
                out.append(f"the answer to {key} must be a text or a list of texts")
    _text_map(data.get("sign_offs", {}), ("name", "date"), "sign_offs", out)
    _text_map(data.get("consulted", {}), ("date", "outcome"), "consulted", out)
    unknown = set(data) - {"format", "form", "catalogue_version", "kpi_name", "request", "answers", "sign_offs",
                           "consulted", "example_of", "comment"}
    if unknown:
        out.append("unknown keys: " + ", ".join(sorted(unknown)))
    return out


def from_dict(data):
    problems = structure_problems(data)
    if problems:
        raise AnswersError("; ".join(problems))
    return Intake(form=data["form"], catalogue_version=data.get("catalogue_version", ""),
                  kpi_name=data.get("kpi_name", ""), request=dict(data.get("request", {})),
                  answers=dict(data["answers"]), sign_offs=dict(data.get("sign_offs", {})),
                  consulted=dict(data.get("consulted", {})), example_of=data.get("example_of", ""),
                  comment=data.get("comment", ""))


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise AnswersError(f"{path} cannot be read: {e}") from None
    except ValueError as e:
        raise AnswersError(f"{path} is not JSON: {e}") from None
    return from_dict(data)


def dumps(intake):
    """The file's text. Keys keep the order of as_dict and the answers are sorted, so the same answers give the
    same bytes."""
    data = intake.as_dict()
    data["answers"] = dict(sorted(data["answers"].items(), key=lambda kv: _order(kv[0])))
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _order(key):
    """1.2 before 1.10, and a question before its detail."""
    head, _, tail = key.partition(".detail")
    parts = [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in head.replace("A", "A.").split(".") if p]
    return (parts, bool(_))


def read(path, cat, lists, form=None):
    """An Intake from an answers JSON file or a filled workbook. `form` picks the form to read from a workbook,
    which holds both; a JSON file says which form it is."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        intake = read_json(path)
        if form and intake.form != form:
            raise AnswersError(f"{path} is a {FORMS[intake.form]} form, not a {FORMS[form]} form")
        return intake
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from kpi_store.intake import workbook
        return workbook.read(path, cat, lists, form or "kpi-intake")
    raise AnswersError(f"{path} is neither a .json answers file nor a .xlsx workbook")
