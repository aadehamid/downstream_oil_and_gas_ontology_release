"""Builds a query from a template and a confirmed mapping.

A template never holds a label, a property or a relationship type. It holds role placeholders:
`{{label:system.node}}`, `{{property:system.code}}`, `{{relationship:policy.applies_to}}` and
`{{path:system_to_table}}`. The renderer replaces each one with the mapped name, checked against the live schema
and quoted with backticks. Values never enter the text: they travel as query parameters.

Lines between `//#if <role> ...` and `//#endif` stay only when every named role has a value, with an optional
`//#else` part for when one has none. That is how a question leaves out a part the graph cannot answer.

The header is the comment lines at the top:

    // title: <what the question asks>
    // param: <name> | required | <meaning>
    // param: <name> | default <JSON value> | <meaning>
    // needs-any: <role> <role> ...        at least one of these roles must have a value
    // language-tagged: <column> ...       columns whose text ends in a language tag such as @en

The header ends at the first line that is not a comment. Any other comment line, in the header or below it, is
for the reader. It stays in the query text and the server ignores it.

`run.py` calls `render` once per question, after the drift check. This module reads the template files and
writes nothing. The order inside `render_text` matters: it refuses an unconfirmed mapping, then a template that
could write, and only then builds the text.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import mapping as M
from . import roles as R
from .discover import Schema

TEMPLATES = Path(__file__).resolve().parent / "templates"
# The questions that can be asked, each a file in templates/. The numbers are the questions' own, so they have gaps.
QUESTIONS = ("q1", "q4", "q6", "q7")

# The two graph names reach `USE graph.byName(...)` as parameters, so no database name is written into a query.
GRAPH_PARAMS = {R.GOVERNANCE: "governance_graph", R.BPA: "bpa_graph"}

# A role placeholder: two braces, the kind, a colon, the role's name, two braces. Group 1 is the kind, group 2 the name.
PLACEHOLDER = re.compile(r"\{\{\s*([a-z]+)\s*:\s*([A-Za-z0-9_.]+)\s*\}\}")

# Every clause that can change a graph, a database or the server. A procedure call is refused too, because a
# procedure can write: the templates need none.
WRITE_WORDS = ("CREATE", "MERGE", "SET", "DELETE", "DETACH", "REMOVE", "DROP", "FOREACH", "LOAD", "ALTER",
               "INSERT", "GRANT", "DENY", "REVOKE", "RENAME", "START", "STOP", "TERMINATE", "ENABLE", "DEALLOCATE",
               "REALLOCATE", "DRYRUN")


class RenderError(Exception):
    """The template cannot become a query: a write clause, an unknown role, a missing parameter."""


@dataclass
class Rendered:
    """A query ready to run: its text, its parameters with the two graph names, the columns that hold
    language-tagged text, and the roles its placeholders used."""
    question: str
    title: str
    query: str
    params: dict
    language_tagged: tuple[str, ...] = ()
    roles: tuple[str, ...] = field(default_factory=tuple)


def template_text(question: str) -> str:
    """A question's template, read from templates/. The name is checked against QUESTIONS first, so no text from
    the command line becomes part of a path."""
    if question not in QUESTIONS:
        raise RenderError(f"no question named {question}: choose one of {', '.join(QUESTIONS)}")
    with (TEMPLATES / f"{question}.cypher").open(encoding="utf-8", newline="\n") as f:
        return f.read()


def code_only(text: str) -> str:
    """The text with comments, quoted strings, backtick names and placeholders blanked, so a word inside one of
    them is never read as a parameter."""
    pattern = re.compile(r"/\*.*?\*/|//[^\n]*|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:``|[^`])*`|\{\{.*?\}\}",
                         re.S)
    return pattern.sub(" ", text)


# One Cypher token. The order of the alternatives matters: a comment, a string and a backtick name are tried before
# a bare word, so a word inside one of them is never a separate token.
TOKEN = re.compile(r"""
      (?P<skip>\s+|/\*.*?\*/|//[^\n]*)                   # white space and comments say nothing
    | (?P<text>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")      # a quoted string
    | (?P<name>`(?:``|[^`])*`)                           # a name in backticks
    | (?P<placeholder>\{\{.*?\}\})                       # a role placeholder
    | (?P<param>\$[A-Za-z0-9_]+)                         # a parameter
    | (?P<word>\w+)                            # a keyword, a variable or a number
    | (?P<mark>.)                                        # any other single character
""", re.S | re.X)


def tokens(text: str) -> list[tuple[str, str]]:
    """The text as (kind, text) pairs, without white space and comments. A string, a backtick name, a placeholder
    and a parameter are each one token, so nothing inside one is ever read as a keyword."""
    return [(match.lastgroup, match.group()) for match in TOKEN.finditer(text) if match.lastgroup != "skip"]


def _is_subquery(found: list[tuple[str, str]], at: int) -> bool:
    """True when the tokens from `at` open a subquery: `{`, or an import list in parentheses and then `{`.
    The import list is empty, `*`, or variable names with commas between them."""
    def mark(i, char):
        return i < len(found) and found[i] == ("mark", char)

    if mark(at, "{"):
        return True
    if not mark(at, "("):
        return False
    at += 1
    if mark(at, "*"):
        at += 1
    else:
        while at < len(found) and found[at][0] == "word":
            at += 1
            if not mark(at, ","):
                break
            if at + 1 >= len(found) or found[at + 1][0] != "word":
                return False                   # a comma with no name after it
            at += 1
    return mark(at, ")") and mark(at + 1, "{")


def refuse_writes(text: str) -> None:
    """Raises RenderError when the template holds a clause that could change anything. The questions are also
    run in a read transaction (run.py), so this is the first of two guards. It stops a bad template before it
    reaches the server, with a message that names the clause."""
    found = tokens(text)
    for i, (kind, word) in enumerate(found):
        # A word after a dot is a property name, such as n.set. Everywhere else a bare word can be a keyword.
        if kind != "word" or (i and found[i - 1] == ("mark", ".")):
            continue
        keyword = word.upper()
        if keyword in WRITE_WORDS:
            raise RenderError(f"refused: the template holds the write clause {keyword}; questions only read")
        # An allow list: after CALL only a subquery may follow. Any other form is a procedure call, and a
        # procedure can write.
        if keyword == "CALL" and not _is_subquery(found, i + 1):
            raise RenderError("refused: the template calls a procedure; after CALL only a subquery may follow, "
                              "as CALL { or CALL (variables) {")
        # CALL { ... } IN TRANSACTIONS commits in batches, which a single read transaction cannot hold.
        if keyword == "IN":
            following = [w.upper() for k, w in found[i + 1:i + 4] if k == "word"]
            if "TRANSACTIONS" in following:
                raise RenderError("refused: the template opens its own transactions; a question runs in one "
                                  "read transaction")


def _header(text: str):
    """The template's header: (title, {parameter: its rule}, the needs-any groups, the language-tagged columns).
    It reads the comment lines at the top and stops at the first line of query or the first //# directive. A
    comment line with no known key is prose and is passed over."""
    title, params, needs_any, tagged = "", {}, [], ()
    for line in text.splitlines():
        if not line.startswith("//") or line.startswith("//#"):
            break
        key, _, rest = line[2:].partition(":")
        key, rest = key.strip(), rest.strip()
        if key == "title":
            title = rest
        elif key == "param":
            name, rule, *_ = [part.strip() for part in rest.split("|")] + [""]
            if rule == "required":
                params[name] = {"required": True}
            elif rule.startswith("default "):
                params[name] = {"required": False, "default": json.loads(rule[len("default "):])}
            else:
                raise RenderError(f"parameter {name}: write 'required' or 'default <JSON value>'")
        elif key == "needs-any":
            needs_any.append(rest.split())
        elif key == "language-tagged":
            tagged = tuple(rest.split())
    return title, params, needs_any, tagged


def _conditionals(text: str, mapping: dict) -> str:
    """The template without its //# directive lines and without the parts whose roles have no value. Blocks
    nest: a line stays only when every block around it stays."""
    kept, open_ifs = [], []          # one entry per open //#if: does its current part stay?
    for number, line in enumerate(text.splitlines(), 1):
        directive = line.strip()
        if directive.startswith("//#if "):
            names = directive[len("//#if "):].split()
            unknown = [name for name in names if name not in R.BY_NAME]
            if unknown:
                raise RenderError(f"line {number}: no role named {', '.join(unknown)}")
            open_ifs.append(all(M.value_of(mapping, name) is not None for name in names))
        elif directive == "//#else":
            if not open_ifs:
                raise RenderError(f"line {number}: //#else without //#if")
            open_ifs[-1] = not open_ifs[-1]
        elif directive == "//#endif":
            if not open_ifs:
                raise RenderError(f"line {number}: //#endif without //#if")
            open_ifs.pop()
        elif directive.startswith("//#"):
            raise RenderError(f"line {number}: {directive} is not //#if, //#else or //#endif")
        elif all(open_ifs):
            kept.append(line)
    if open_ifs:
        raise RenderError("an //#if has no //#endif")
    return "\n".join(kept) + "\n"


def quote(name: str) -> str:
    """The name in backticks, with a backtick inside it doubled, so the server reads any label or property name
    as one name and never as query text."""
    if not isinstance(name, str) or not name or "\x00" in name:
        raise RenderError(f"not a usable name: {name!r}")
    return "`" + name.replace("`", "``") + "`"


def _identifier(kind: str, role_name: str, mapping: dict, schemas: dict[str, Schema]) -> str:
    """The text that replaces one placeholder: the role's confirmed value, quoted. The value must be in the live
    schema, so a name reaches a query only when the graph holds it now. A path becomes its types joined with
    bars and its length, such as :`HOSTS`|`CONTAINS`*1..2, for use inside a relationship's square brackets."""
    try:
        role = R.role(role_name)
    except KeyError as error:
        raise RenderError(str(error.args[0])) from None
    if kind != role.kind:
        raise RenderError(f"role {role_name} is a {role.kind}, and the template uses it as a {kind}")
    value, schema = M.value_of(mapping, role_name), schemas[role.graph]
    if value is None:
        raise RenderError(f"role {role_name}: nothing plays it, and the question needs it")
    if role.kind == R.LABEL:
        known = value in schema.labels
    elif role.kind == R.PROPERTY:
        known = value in schema.properties.get(M.value_of(mapping, role.on), ())
    elif role.kind == R.RELATIONSHIP:
        known = any(value == t for _, t, _ in schema.relationships)
    else:
        types, hops = value.get("types") or [], value.get("max_hops")
        known = (bool(types) and all(any(name == t for _, t, _ in schema.relationships) for name in types)
                 and isinstance(hops, int) and not isinstance(hops, bool) and 1 <= hops <= 5)
        if known:
            return ":" + "|".join(quote(name) for name in types) + f"*1..{hops}"
    if not known:
        raise RenderError(f"role {role_name}: {value} is not in the {role.graph} graph's schema")
    return quote(value)


def render_text(question: str, text: str, mapping: dict, schemas: dict[str, Schema], params: dict | None = None,
                graphs: dict[str, str] | None = None) -> Rendered:
    """The query for one template text. `graphs` gives each graph's name inside the composite database."""
    M.require_confirmed(mapping)
    refuse_writes(text)   # on the template as written, before any name from the mapping enters the text
    title, declared, needs_any, tagged = _header(text)
    for group in needs_any:
        unknown = [name for name in group if name not in R.BY_NAME]
        if unknown:
            raise RenderError(f"needs-any: no role named {', '.join(unknown)}")
        if all(M.value_of(mapping, name) is None for name in group):
            raise RenderError(f"question {question} needs one of the roles {', '.join(group)}, and none has a value")
    used = []

    def replace(match):
        used.append(match.group(2))
        return _identifier(match.group(1), match.group(2), mapping, schemas)

    body = _conditionals(text, mapping)
    # Anything in double braces that is not a well-formed placeholder is a typing mistake in the template. Left
    # alone it would reach the server as query text.
    for found in re.findall(r"\{\{.*?\}\}", body, re.S):
        if not PLACEHOLDER.fullmatch(found):
            raise RenderError(f"{found} is not a placeholder of the form {{{{kind:role}}}}")
    query = PLACEHOLDER.sub(replace, body)

    supplied = dict(params or {})
    unknown = sorted(set(supplied) - set(declared))
    if unknown:
        raise RenderError(f"question {question} has no parameter {', '.join(unknown)}")
    values = {}
    for name, rule in declared.items():
        if name in supplied:
            values[name] = supplied[name]
        elif rule["required"]:
            raise RenderError(f"question {question} needs the parameter {name}")
        else:
            values[name] = rule["default"]
    for graph, name in GRAPH_PARAMS.items():
        values[name] = (graphs or {}).get(graph, graph)
    # Every $name in the query's code must have a value now. A template that uses a parameter its header does
    # not declare would otherwise fail on the server with a less clear message.
    undeclared = sorted(set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", code_only(query))) - set(values))
    if undeclared:
        raise RenderError(f"the template uses the parameter {', '.join(undeclared)} and does not declare it")
    return Rendered(question, title, query, values, tagged, tuple(dict.fromkeys(used)))


def render(question: str, mapping: dict, schemas: dict[str, Schema], params: dict | None = None,
           graphs: dict[str, str] | None = None) -> Rendered:
    """The query for one of the release's questions, from its template file."""
    return render_text(question, template_text(question), mapping, schemas, params, graphs)
