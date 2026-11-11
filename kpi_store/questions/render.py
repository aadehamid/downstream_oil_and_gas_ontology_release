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
QUESTIONS = ("q1", "q4", "q6", "q7")

# The two graph names reach `USE graph.byName(...)` as parameters, so no database name is written into a query.
GRAPH_PARAMS = {R.GOVERNANCE: "governance_graph", R.BPA: "bpa_graph"}

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
    question: str
    title: str
    query: str
    params: dict
    language_tagged: tuple[str, ...] = ()
    roles: tuple[str, ...] = field(default_factory=tuple)


def template_text(question: str) -> str:
    if question not in QUESTIONS:
        raise RenderError(f"no question named {question}: choose one of {', '.join(QUESTIONS)}")
    with (TEMPLATES / f"{question}.cypher").open(encoding="utf-8", newline="\n") as f:
        return f.read()


def code_only(text: str, keep_names: bool = False) -> str:
    """The text with comments, quoted strings, backtick names and placeholders blanked, so a word inside one of
    them is never read as a clause. `keep_names` leaves the backtick names in."""
    parts = [r"/\*.*?\*/", r"//[^\n]*", r"'(?:\\.|[^'\\])*'", r'"(?:\\.|[^"\\])*"', r"\{\{.*?\}\}"]
    if not keep_names:
        parts.append(r"`(?:``|[^`])*`")
    return re.sub("|".join(parts), " ", text, flags=re.S)


# The two subquery forms the templates use: CALL { ... } and CALL (a, b) { ... }. Nothing else may follow CALL.
SUBQUERY = re.compile(r"\s*(\(\s*(\*|[A-Za-z_]\w*(\s*,\s*[A-Za-z_]\w*)*)?\s*\)\s*)?\{")


def refuse_writes(text: str) -> None:
    code = code_only(text)
    for word in WRITE_WORDS:
        if re.search(rf"(?<![A-Za-z0-9_$.]){word}(?![A-Za-z0-9_])", code, re.I):
            raise RenderError(f"refused: the template holds the write clause {word}; questions only read")
    # An allow list, read with the backtick names still in place: a procedure whose name is written in backticks
    # must not pass as a subquery.
    named = code_only(text, keep_names=True)
    for call in re.finditer(r"(?<![A-Za-z0-9_$.`])CALL(?![A-Za-z0-9_`])", named, re.I):
        if not SUBQUERY.match(named, call.end()):
            raise RenderError("refused: the template calls a procedure; after CALL only a subquery may follow, "
                              "as CALL { or CALL (...) {")
    if re.search(r"\bIN\s+(\w+\s+){0,2}TRANSACTIONS\b", code, re.I):
        raise RenderError("refused: the template opens its own transactions; a question runs in one read transaction")


def _header(text: str):
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
    if not isinstance(name, str) or not name or "\x00" in name:
        raise RenderError(f"not a usable name: {name!r}")
    return "`" + name.replace("`", "``") + "`"


def _identifier(kind: str, role_name: str, mapping: dict, schemas: dict[str, Schema]) -> str:
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
    refuse_writes(text)
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
    undeclared = sorted(set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", code_only(query))) - set(values))
    if undeclared:
        raise RenderError(f"the template uses the parameter {', '.join(undeclared)} and does not declare it")
    return Rendered(question, title, query, values, tagged, tuple(dict.fromkeys(used)))


def render(question: str, mapping: dict, schemas: dict[str, Schema], params: dict | None = None,
           graphs: dict[str, str] | None = None) -> Rendered:
    return render_text(question, template_text(question), mapping, schemas, params, graphs)
