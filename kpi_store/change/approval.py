"""The approval record of one change (KPI-DEC-0002, Q4 and Q13): one JSON file per change, written by code.

Where it lives: business_architecture/ontology/approvals/<change id>.json, the folder where HOW-TO-UPDATE.md
("The release steps", step 3) keeps the approvals written by hand. The record replaces that free Markdown for the
changes the commands make.

What it holds, and nothing else:

    {"change": "<change id>",
     "route": "patch" | "minor" | "major",
     "new_module": false,
     "signatures": [{"role": "Data Owner", "name": "<name>", "date": "2026-11-19", "words": "<the approval words>"},
                    ...]}

Who signs (Q4): the Data Owner signs a KPI definition, and the Architect signs the change. A major change or a new
module also needs the Ontology Owner. read_record refuses a record that lacks a signature its route needs.

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
ROLES = ("Data Owner", "Architect", "Ontology Owner", "Domain Owner")
FIELDS = ("change", "route", "new_module", "signatures")
SIGNATURE_FIELDS = ("role", "name", "date", "words")
# The change id names the file, so it holds no path separator: the same form as a discovery run's id (cut.RUN_ID).
CHANGE_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,99}")
DATE = re.compile(r"\d{4}-\d\d-\d\d")


def required_roles(route, new_module=False):
    """The roles whose signatures a change on this route needs."""
    roles = ["Data Owner", "Architect"]
    if route == "major" or new_module:
        roles.append("Ontology Owner")
    return roles


def record_path(release_root, change_id):
    """Where the approval record of one change lives in a release."""
    if not isinstance(change_id, str) or not CHANGE_ID.fullmatch(change_id):
        raise ChangeRefused(f"the change id {change_id!r} must be 1 to 100 letters, digits, dots, hyphens or "
                            "underscores, starting with a letter or digit")
    return Path(release_root) / APPROVALS / f"{change_id}.json"


def check(record):
    """Refuses a record that is not complete. Returns the record when it is."""
    if not isinstance(record, dict):
        raise ChangeRefused("the approval record is not a JSON object")
    missing = [f for f in FIELDS if f not in record]
    if missing:
        raise ChangeRefused(f"the approval record has no {', no '.join(missing)}")
    extra = sorted(set(record) - set(FIELDS))
    if extra:
        raise ChangeRefused(f"the approval record holds fields it should not: {', '.join(extra)}")
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
    unsigned = [role for role in required_roles(record["route"], record["new_module"]) if role not in signed]
    if unsigned:
        what = "a new module" if record["new_module"] else f"a {record['route']} change"
        raise ChangeRefused(f"the change {record['change']} is not approved: {what} needs the signature of the "
                            f"{' and the '.join(unsigned)}, and the record has none")
    return record


def _is_date(text):
    try:
        dt.date.fromisoformat(text)
        return True
    except ValueError:
        return False


def write_record(release_root, change_id, route, signatures, new_module=False):
    """Checks and writes the approval record of one change, and returns its path. Refuses an incomplete record,
    and a record for a change that has one already."""
    record = check({"change": change_id, "route": route, "new_module": new_module,
                    "signatures": list(signatures) if isinstance(signatures, tuple) else signatures})
    record["signatures"] = [{f: sig[f] for f in SIGNATURE_FIELDS} for sig in record["signatures"]]
    path = record_path(release_root, change_id)
    if path.exists():
        raise ChangeRefused(f"the change {change_id} has an approval record already: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return path


def read_record(path):
    """Reads and checks one approval record. Refuses a missing, unreadable or incomplete record."""
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
    record = check(record)
    if path.name != f"{record['change']}.json":
        raise ChangeRefused(f"the approval record {path} is for the change {record['change']}, not for {path.stem}")
    return record


def holds_words(record, words):
    """True when one signature of the record carries exactly these approval words."""
    return any(sig["words"] == words for sig in record["signatures"])
