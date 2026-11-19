r"""KPI Store's own small reader and writer of KGCL, the Knowledge Graph Change Language (KPI-DEC-0002, "Change format").

It reads and writes six statement forms only, spelled as the official grammar spells them (kgcl-schema 0.7.0,
src/kgcl_schema/grammar/kgcl.lark), with one space between words:

    create exact synonym '<text>' for <id>
    remove synonym '<text>' for <id>
    change definition of <id> to '<text>'
    rename <id> from '<old text>' to '<new text>'
    create edge <id> <predicate> <id>
    delete edge <id> <predicate> <id>

Any other line is refused with "not a change this release applies".

An <id> is a CURIE: a prefix of letters, digits and underscores, a colon, then no space and no quote
(measure:crude-utilization). The grammar's other spellings of an id, <IRI> and a quoted label, are not read.

Quotes. The grammar's single-quoted text is "'" INNER "'", where INNER is /((?!\').)*/: it has no escape, so a
straight single quote (') cannot appear inside the text at all. Tested on kgcl-schema 0.7.0: 'MPC''s' and 'MPC\'s'
both fail to parse, and a synonym cannot be double-quoted. A double quote inside the text is fine. So the writer
puts each straight apostrophe of a text as the typographic one, ’ (U+2019), which the grammar takes and the
official renderer writes unchanged, and the reader turns each ’ back into a straight apostrophe. The tables keep
straight apostrophes, and the round trip is exact. A text that already holds a real ’ is refused, because the
reader could not tell it from an apostrophe (decided under the delegation on 2026-11-19: 487 of 17,101
source-table cells hold a straight apostrophe, and none of the tables the change forms write holds a ’).
It also refuses a backslash, because the official renderer writes it twice, and a line break or other control
character, because a KGCL line is one line. Text may not be empty or start or end with a space.

The tests check every line this module writes against the official parser: parse_statement(line), then render(),
gives the same line. The release does not need kgcl-schema at run time.
"""
import re
import unicodedata
from dataclasses import dataclass

from . import ChangeRefused

KINDS = ("create synonym", "remove synonym", "change definition", "rename", "create edge", "delete edge")
NOT_APPLIED = "not a change this release applies"
TYPOGRAPHIC = "\u2019"   # how a KGCL line writes a straight apostrophe of a text

_ID = r"[A-Za-z0-9_]+:[^\s']+"
_TEXT = r"'([^']*)'"
_FORMS = {
    "create synonym": re.compile(rf"create exact synonym {_TEXT} for ({_ID})"),
    "remove synonym": re.compile(rf"remove synonym {_TEXT} for ({_ID})"),
    "change definition": re.compile(rf"change definition of ({_ID}) to {_TEXT}"),
    "rename": re.compile(rf"rename ({_ID}) from {_TEXT} to {_TEXT}"),
    "create edge": re.compile(rf"create edge ({_ID}) ({_ID}) ({_ID})"),
    "delete edge": re.compile(rf"delete edge ({_ID}) ({_ID}) ({_ID})"),
}
ID = re.compile(_ID)


@dataclass(frozen=True)
class Change:
    """One KGCL statement. `subject` is the id the statement is about. `text` is the synonym, the new definition
    or the new name; `old` is a rename's current name. An edge has `predicate` and `target` instead of text."""
    kind: str
    subject: str
    text: str = ""
    old: str = ""
    predicate: str = ""
    target: str = ""


def text_problem(text):
    """Why a text cannot go into a KGCL line, or None when it can."""
    if not text:
        return "the text is empty"
    if text != text.strip():
        return "the text starts or ends with a space"
    if TYPOGRAPHIC in text:
        return (f"the text holds the typographic apostrophe {TYPOGRAPHIC}, which a KGCL line uses to write a straight "
                "apostrophe; write it as a straight apostrophe (')")
    if "\\" in text:
        return "the text holds a backslash, which the official KGCL tools would write twice"
    if any(unicodedata.category(c) == "Cc" for c in text):
        return "the text holds a line break or another control character, and a KGCL line is one line"
    return None


def _texts(change):
    """The quoted texts of a change: a rename has two, an edge none, the others one."""
    if change.kind == "rename":
        return (change.old, change.text)
    return () if change.kind.endswith("edge") else (change.text,)


def _encode(text):
    return text.replace("'", TYPOGRAPHIC)


def _decode(text):
    return text.replace(TYPOGRAPHIC, "'")


def _check_text(text, line):
    problem = text_problem(text)
    if problem:
        raise ChangeRefused(f"{problem}: {line}")


def read_line(line):
    """The Change one KGCL line states. Raises ChangeRefused for any other line."""
    for kind, form in _FORMS.items():
        m = form.fullmatch(line)
        if not m:
            continue
        if kind in ("create synonym", "remove synonym"):
            change = Change(kind, subject=m.group(2), text=_decode(m.group(1)))
        elif kind == "change definition":
            change = Change(kind, subject=m.group(1), text=_decode(m.group(2)))
        elif kind == "rename":
            change = Change(kind, subject=m.group(1), old=_decode(m.group(2)), text=_decode(m.group(3)))
        else:
            change = Change(kind, subject=m.group(1), predicate=m.group(2), target=m.group(3))
        for text in _texts(change):
            _check_text(text, line)
        return change
    raise ChangeRefused(f"{NOT_APPLIED}: {line}")


def read_lines(text):
    """The Changes of a change file: one KGCL line each. Blank lines are skipped; any other line must be a change."""
    return [read_line(line) for line in text.splitlines() if line.strip()]


def write_line(change):
    """The KGCL line of one Change. Raises ChangeRefused when the change cannot be written."""
    if change.kind not in KINDS:
        raise ChangeRefused(f"{NOT_APPLIED}: {change.kind}")
    ids = (change.subject, change.predicate, change.target) if change.kind.endswith("edge") else (change.subject,)
    for value in ids:
        if not ID.fullmatch(value or ""):
            raise ChangeRefused(f"{value!r} is not an id of the form prefix:name (for {change.kind})")
    for text in _texts(change):
        problem = text_problem(text)
        if problem:
            raise ChangeRefused(f"{problem} (for {change.kind} of {change.subject})")
    if change.kind == "create synonym":
        return f"create exact synonym '{_encode(change.text)}' for {change.subject}"
    if change.kind == "remove synonym":
        return f"remove synonym '{_encode(change.text)}' for {change.subject}"
    if change.kind == "change definition":
        return f"change definition of {change.subject} to '{_encode(change.text)}'"
    if change.kind == "rename":
        return f"rename {change.subject} from '{_encode(change.old)}' to '{_encode(change.text)}'"
    return f"{change.kind} {change.subject} {change.predicate} {change.target}"


def write_lines(changes):
    """A change file's text: one line per change, each ending with a line end."""
    return "".join(write_line(c) + "\n" for c in changes)
