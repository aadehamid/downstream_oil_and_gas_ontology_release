"""The approval record of one change (KPI-DEC-0002, Q4 and Q13): one JSON file per change, written by code.

Where it lives: business_architecture/ontology/approvals/<change id>.json, the folder where HOW-TO-UPDATE.md
("The release steps", step 3) keeps the approvals written by hand. The record replaces that free Markdown for the
changes the commands make.

What it holds, and nothing else:

    {"change": "<change id>",
     "route": "patch" | "minor" | "major",
     "new_module": false,
     "signatures": [{"role": "Data Owner", "name": "<name>", "date": "2026-11-19", "words": "<the approval words>"},
                    ...],
     "ai": {...},                 only when the form had an AI step (check_ai says what it holds)
     "draft": {...},              only for a module an AI drafted (check_draft says what it holds)
     "after": ["<change id>", ...]}   only for a KPI proposed with the forms it waits on: the proposals to apply first

Who signs (Q4): the Data Owner signs a KPI definition, and the Architect signs the change. A major change or a new
module also needs the Ontology Owner. A domain activation needs the Domain Owner in place of the Data Owner, and a
process map request the Global Process Owner (Q4, and the sign-off block of kpi-intake/catalogue.toml): the caller
names that role with `owner`.
read_record refuses a record that lacks a signature its route needs.

The approval words are kept exactly as signed. The file is UTF-8 and keeps every character as it is, so words with
no double quote and no backslash appear in the file text as signed, which is the existing rule for approvals
(release/test_build_module.py, approval_holds). holds_words checks a record's words by their value.
"""
import datetime as dt
import json
import re
import unicodedata
from pathlib import Path

from . import ChangeRefused

APPROVALS = Path("business_architecture") / "ontology" / "approvals"
ROUTES = ("patch", "minor", "major")
ROLES = ("Data Owner", "Architect", "Ontology Owner", "Domain Owner", "Global Process Owner")
FIELDS = ("change", "route", "new_module", "signatures")
SIGNATURE_FIELDS = ("role", "name", "date", "words")
# The record of an AI step (KPI-DEC-0002, Q20; kpi_store/ai/suggest.py): who was asked, under whose approval, with
# which instructions, the fingerprints of the prompt and of what it answered, and each suggestion with the person's
# choice. The record keeps no prompt text: the prompt holds the form's answers before signing.
AI_FIELDS = ("format", "form", "provider", "assistant", "model", "model_version", "endpoint", "approved_by",
             "approved_on", "asked_on", "skills", "prompt_sha256", "output_sha256", "suggestions")
AI_PROVIDERS = ("databricks", "anthropic", "openai", "by-hand")
AI_SUGGESTION_FIELDS = ("question", "current", "suggested", "reason", "answer", "accepted")
SHA256 = re.compile(r"[0-9a-f]{64}")
# The record of an AI draft of new modelling (KPI-DEC-0002, Q17(a), Q19 and Q20; kpi_store/ai/draft.py and
# kpi_store/change/drafted.py): the module's settings, the fingerprint of the form's answers it was drafted from, the
# drafter and the reviewer, the reviewer's verdict and findings, each file of the draft with its SHA-256, and the
# result of each gate. Like the AI step's record, it keeps no prompt text.
DRAFT_FIELDS = ("format", "form", "module", "form_sha256", "drafter", "reviewer", "parts", "gates")
DRAFT_STEP_FIELDS = ("provider", "assistant", "family", "model", "model_version", "endpoint", "approved_by", "approved_on",
                     "asked_on", "skills", "prompt_sha256", "output_sha256")
DRAFT_MODULE_FIELDS = ("module", "pattern", "prefix", "title", "description", "citation", "depends_on", "prefixes")
VERDICTS = ("PASS", "HOLD")
# The change id names the file, so it holds no path separator: the same form as a discovery run's id (cut.RUN_ID).
CHANGE_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,99}")
DATE = re.compile(r"\d{4}-\d\d-\d\d")


def required_roles(route, new_module=False, owner="Data Owner"):
    """The roles whose signatures a change on this route needs. `owner` is the role that answers for the content:
    the Data Owner, or the Domain Owner of a domain activation, or the Global Process Owner of a process map request."""
    roles = [owner, "Architect"]
    if route == "major" or new_module:
        roles.append("Ontology Owner")
    return roles


def record_path(release_root, change_id):
    """Where the approval record of one change lives in a release."""
    if not isinstance(change_id, str) or not CHANGE_ID.fullmatch(change_id):
        raise ChangeRefused(f"the change id {change_id!r} must be 1 to 100 letters, digits, dots, hyphens or "
                            "underscores, starting with a letter or digit")
    return Path(release_root) / APPROVALS / f"{change_id}.json"


def check(record, owner="Data Owner"):
    """Refuses a record that is not complete. Returns the record when it is. `owner` as for required_roles."""
    if not isinstance(record, dict):
        raise ChangeRefused("the approval record is not a JSON object")
    missing = [f for f in FIELDS if f not in record]
    if missing:
        raise ChangeRefused(f"the approval record has no {', no '.join(missing)}")
    extra = sorted(set(record) - set(FIELDS) - {"ai", "draft", "after"})
    if extra:
        raise ChangeRefused(f"the approval record holds fields it should not: {', '.join(extra)}")
    if "after" in record:   # the proposals of the same propose run to apply first (kpi_store/propose.py)
        after = record["after"]
        if not isinstance(after, list) or not after or not all(isinstance(c, str) for c in after):
            raise ChangeRefused("the approval record's after must be a list of change ids")
        for change in after:
            record_path(".", change)   # the id's form
    if "ai" in record:
        check_ai(record["ai"])
    if "draft" in record:
        if record.get("new_module") is not True:
            raise ChangeRefused("the record of an AI draft belongs to a new module only")
        check_draft(record["draft"], signed=True)
    record_path(".", record["change"])   # the id's form
    if record["route"] not in ROUTES:
        raise ChangeRefused(f"the route {record['route']!r} is not patch, minor or major")
    if not isinstance(record["new_module"], bool):
        raise ChangeRefused("new_module must be true or false")
    signatures = record["signatures"]
    if not isinstance(signatures, list) or not signatures:
        raise ChangeRefused("the approval record has no signatures")
    for n, sig in enumerate(signatures, 1):
        if not isinstance(sig, dict):
            raise ChangeRefused(f"signature {n} is not a JSON object")
        missing = [f for f in SIGNATURE_FIELDS if not isinstance(sig.get(f), str) or not sig.get(f).strip()]
        if missing:
            raise ChangeRefused(f"signature {n} has no {', no '.join(missing)}")
        extra = sorted(set(sig) - set(SIGNATURE_FIELDS))
        if extra:
            raise ChangeRefused(f"signature {n} holds fields it should not: {', '.join(extra)}")
        if sig["role"] not in ROLES:
            raise ChangeRefused(f"signature {n}: {sig['role']!r} is not a role that signs ({', '.join(ROLES)})")
        if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in sig["name"]):
            raise ChangeRefused(f"signature {n}: the name holds a line break or another control character")
        if not DATE.fullmatch(sig["date"]) or not _is_date(sig["date"]):
            raise ChangeRefused(f"signature {n}: the date {sig['date']!r} is not a date written as YYYY-MM-DD")
    signed = {sig["role"] for sig in signatures}
    unsigned = [role for role in required_roles(record["route"], record["new_module"], owner) if role not in signed]
    if unsigned:
        what = "a new module" if record["new_module"] else f"a {record['route']} change"
        raise ChangeRefused(f"the change {record['change']} is not approved: {what} needs the signature of the "
                            f"{' and the '.join(unsigned)}, and the record has none")
    return record


def check_ai(ai, step=False):
    """Refuses a record of an AI step that lacks a field, holds one more, or holds a value of the wrong form. `step`
    is the record as the AI step writes it beside the form; the approval record's adds `kept` to each suggestion:
    whether the signed form holds the suggested answer."""
    def fail(what):
        raise ChangeRefused(f"the record of the AI step {what}")

    def text(value):
        return isinstance(value, str) and value.strip() != ""

    def answer(value):
        return isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value))
    if not isinstance(ai, dict) or tuple(sorted(ai)) != tuple(sorted(AI_FIELDS)):
        fail("must hold exactly " + ", ".join(AI_FIELDS))
    if type(ai["format"]) is not int or ai["format"] != 1:
        fail("has a format that is not 1")
    if not all(isinstance(ai[f], str) for f in AI_FIELDS if f not in ("format", "skills", "suggestions")):
        fail("has a field of the wrong type")
    if ai["provider"] not in AI_PROVIDERS:
        fail("names no provider that makes suggestions: " + ", ".join(AI_PROVIDERS))
    if not text(ai["form"]) or not text(ai["approved_by"]):
        fail("must name the form and who approved the provider")
    for f in ("approved_on", "asked_on"):
        if not DATE.fullmatch(ai[f]) or not _is_date(ai[f]):
            fail(f"has a {f} that is not a date written as YYYY-MM-DD")
    if ai["provider"] == "by-hand" and (not text(ai["assistant"]) or ai["endpoint"]):
        fail("of the by-hand provider must name the assistant, and no endpoint")
    if ai["provider"] != "by-hand" and (not text(ai["model"]) or not text(ai["endpoint"])):
        fail("must name the model and the endpoint it called")
    if not all(SHA256.fullmatch(ai[f]) for f in ("prompt_sha256", "output_sha256")):
        fail("has a fingerprint that is not a SHA-256")
    skills = ai["skills"]
    if not isinstance(skills, list) or not skills or not all(
            isinstance(s, dict) and set(s) == {"path", "sha256"} and text(s["path"])
            and isinstance(s["sha256"], str) and SHA256.fullmatch(s["sha256"]) for s in skills):
        fail("must name each skill file with its SHA-256")
    fields = set(AI_SUGGESTION_FIELDS) | (set() if step else {"kept"})
    if not isinstance(ai["suggestions"], list) or not all(
            isinstance(s, dict) and set(s) == fields and text(s["question"]) and text(s["reason"])
            and all(answer(s[f]) for f in ("current", "suggested", "answer")) and isinstance(s["accepted"], bool)
            and isinstance(s.get("kept", False), bool) for s in ai["suggestions"]):
        fail("must give each suggestion as " + ", ".join(sorted(fields)) + ", with a question and a reason in words")
    return ai


def check_draft(draft, signed):
    """Refuses a record of an AI draft that lacks a field, holds one more, or holds a value of the wrong form.
    `signed` is the record as a proposal and the approval record keep it: reviewed, with every gate from 1 to 5
    passed. Beside a form before signing, the review and gate 3 may still be missing, and a gate may have failed."""
    def fail(what):
        raise ChangeRefused(f"the record of the AI draft {what}")

    def text(value):
        return isinstance(value, str) and value.strip() != ""

    def step(value, fields, who):
        if not isinstance(value, dict) or tuple(sorted(value)) != tuple(sorted(fields)):
            fail(f"must give the {who} as exactly " + ", ".join(fields))
        if not all(isinstance(value[f], str) for f in DRAFT_STEP_FIELDS if f != "skills"):
            fail(f"gives the {who} a field of the wrong type")
        if value["provider"] not in AI_PROVIDERS or not text(value["family"]) or not text(value["approved_by"]):
            fail(f"must name the {who}'s provider, its model family and who approved it")
        if value["family"] != value["family"].strip():
            fail(f"gives the {who}'s family with spaces around it")
        for f in ("approved_on", "asked_on"):
            if not DATE.fullmatch(value[f]) or not _is_date(value[f]):
                fail(f"gives the {who} a {f} that is not a date written as YYYY-MM-DD")
        if value["provider"] == "by-hand" and (not text(value["assistant"]) or value["endpoint"]):
            fail(f"of a by-hand {who} must name the assistant, and no endpoint")
        if value["provider"] != "by-hand" and (not text(value["model"]) or not text(value["endpoint"])):
            fail(f"must name the {who}'s model and the endpoint it called")
        if not all(SHA256.fullmatch(value[f]) for f in ("prompt_sha256", "output_sha256")):
            fail(f"gives the {who} a fingerprint that is not a SHA-256")
        if not isinstance(value["skills"], list) or not value["skills"] or not all(
                isinstance(s, dict) and set(s) == {"path", "sha256"} and text(s["path"])
                and isinstance(s["sha256"], str) and SHA256.fullmatch(s["sha256"]) for s in value["skills"]):
            fail(f"must name each skill file the {who} followed, with its SHA-256")
    if not isinstance(draft, dict) or tuple(sorted(draft)) != tuple(sorted(DRAFT_FIELDS)):
        fail("must hold exactly " + ", ".join(DRAFT_FIELDS))
    if type(draft["format"]) is not int or draft["format"] != 1 or draft["form"] != "new-module":
        fail("must be of format 1, for a new-module form")
    module = draft["module"]
    if not isinstance(module, dict) or tuple(sorted(module)) != tuple(sorted(DRAFT_MODULE_FIELDS)) or \
            module["pattern"] != "drafted" or not all(text(module[f]) for f in ("module", "prefix", "title", "description",
                                                                                 "citation")) or \
            not isinstance(module["depends_on"], list) or not all(text(m) for m in module["depends_on"]) or \
            len(set(module["depends_on"])) != len(module["depends_on"]) or not isinstance(module["prefixes"], dict) or \
            not all(text(k) and text(v) for k, v in module["prefixes"].items()):
        fail("must give the module's settings as exactly " + ", ".join(DRAFT_MODULE_FIELDS) + ", of the drafted pattern")
    if not isinstance(draft["form_sha256"], str) or not SHA256.fullmatch(draft["form_sha256"]):
        fail("must give the SHA-256 of the form's answers")
    step(draft["drafter"], DRAFT_STEP_FIELDS, "drafter")
    reviewer = draft["reviewer"]
    if reviewer is not None or signed:
        step(reviewer, DRAFT_STEP_FIELDS + ("verdict", "findings"), "reviewer")
        if reviewer["verdict"] not in VERDICTS or not isinstance(reviewer["findings"], list) or not all(
                isinstance(f, dict) and set(f) == {"gate", "finding"} and text(f["gate"]) and text(f["finding"])
                for f in reviewer["findings"]):
            fail("must give the reviewer's verdict, PASS or HOLD, and each finding as gate and finding, in words")
        if reviewer["family"].strip().casefold() == draft["drafter"]["family"].strip().casefold():
            fail("names a reviewer of the drafter's own model family; gate 3 needs another family")
    if not isinstance(draft["parts"], list) or not draft["parts"] or not all(
            isinstance(p, dict) and set(p) == {"path", "sha256"} and text(p["path"]) and isinstance(p["sha256"], str)
            and SHA256.fullmatch(p["sha256"]) for p in draft["parts"]):
        fail("must name each file of the draft with its SHA-256")
    gates = draft["gates"]
    if not isinstance(gates, list) or not all(
            isinstance(g, dict) and set(g) == {"gate", "name", "passed", "results"} and type(g["gate"]) is int
            and text(g["name"]) and isinstance(g["passed"], bool) and isinstance(g["results"], list)
            and all(text(r) for r in g["results"]) for g in gates):
        fail("must give each gate as gate, name, passed and results")
    numbers = [g["gate"] for g in gates]
    if len(set(numbers)) != len(numbers) or not set(numbers) <= {1, 2, 3, 4, 5}:
        fail("gives a gate twice, or a gate that is not 1 to 5")
    if (3 in numbers) != (reviewer is not None):
        fail("gives gate 3 without a reviewer, or a reviewer without gate 3")
    if signed:
        if sorted(numbers) != [1, 2, 3, 4, 5] or not all(g["passed"] for g in gates) or reviewer["verdict"] != "PASS":
            fail("of a proposal must show every gate from 1 to 5 passed, and the reviewer's PASS")
    return draft


def _is_date(text):
    try:
        dt.date.fromisoformat(text)
        return True
    except ValueError:
        return False


def write_record(release_root, change_id, route, signatures, new_module=False, owner="Data Owner", ai=None, draft=None,
                 after=None):
    """Checks and writes the approval record of one change, and returns its path. Refuses an incomplete record,
    and a record for a change that has one already. `ai` is the record of the form's AI step, when it had one,
    `draft` the record of a module's AI draft, and `after` the proposals the change was applied after."""
    record = check({"change": change_id, "route": route, "new_module": new_module,
                    "signatures": list(signatures) if isinstance(signatures, tuple) else signatures,
                    **({"ai": ai} if ai is not None else {}), **({"draft": draft} if draft is not None else {}),
                    **({"after": after} if after is not None else {})}, owner)
    record["signatures"] = [{f: sig[f] for f in SIGNATURE_FIELDS} for sig in record["signatures"]]
    path = record_path(release_root, change_id)
    if path.exists():
        raise ChangeRefused(f"the change {change_id} has an approval record already: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return path


def read_record(path, owner="Data Owner"):
    """Reads and checks one approval record. Refuses a missing, unreadable or incomplete record. `owner` as for
    required_roles."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ChangeRefused(f"the change has no approval record: {path} is missing") from None
    except (OSError, UnicodeDecodeError) as err:
        raise ChangeRefused(f"the approval record {path} cannot be read ({type(err).__name__})") from None
    try:
        record = json.loads(text)
    except json.JSONDecodeError as err:
        raise ChangeRefused(f"the approval record {path} is not valid JSON (line {err.lineno})") from None
    record = check(record, owner)
    if path.name != f"{record['change']}.json":
        raise ChangeRefused(f"the approval record {path} is for the change {record['change']}, not for {path.stem}")
    return record


def holds_words(record, words):
    """True when one signature of the record carries exactly these approval words."""
    return any(sig["words"] == words for sig in record["signatures"])
