"""The mapping file: which label, property or relationship type plays each role, as a person confirmed it.

The file lives outside the release folder, because it describes one environment's governance graph. `drift`
compares it with the live schema and names every role whose label, property or relationship type is gone.

The file's life: `discover` writes a proposal (`discover.propose`), a person corrects it, and `confirm` marks it
as confirmed and stores a digest of its values. After that the file is only read. `render.py` refuses a mapping
that is not confirmed, and `run.py` runs `drift` before every question, so a question never runs on a graph whose
schema changed since the confirmation. This module reads and writes the mapping file and nothing else.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from . import roles as R
from .discover import Schema


class MappingError(Exception):
    """The mapping cannot be used: not confirmed, changed after it was confirmed, or out of step with the graph."""


def load(path: Path) -> dict:
    """The mapping file's content. Raises MappingError when the file is missing, is not JSON or has another format."""
    try:
        with Path(path).open(encoding="utf-8", newline="\n") as f:
            mapping = json.load(f)
    except FileNotFoundError:
        raise MappingError(f"no mapping file at {path}: run discover first") from None
    except json.JSONDecodeError as error:
        raise MappingError(f"{path} is not valid JSON: {error}") from None
    if mapping.get("format") != 1 or not isinstance(mapping.get("roles"), dict):
        raise MappingError(f"{path} is not a role mapping of format 1")
    return mapping


def save(path: Path, mapping: dict) -> None:
    """Writes the mapping file with sorted keys and LF line ends, so the same mapping gives the same file."""
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
        json.dump(mapping, f, indent=2, sort_keys=True)
        f.write("\n")


def value_of(mapping: dict, role_name: str):
    """The confirmed value of a role, or None when the role is optional and nothing plays it."""
    R.role(role_name)
    return mapping["roles"].get(role_name, {}).get("value")


def digest(mapping: dict) -> str:
    """A SHA-256 of every role's value. The notes around a value (confidence, alternatives, meaning) are left
    out: only a change of a value changes which label, property or relationship type a query names."""
    values = {name: entry.get("value") for name, entry in mapping["roles"].items()}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()


def is_confirmed(mapping: dict) -> bool:
    # The digest ties the confirmation to the values the person saw. An edit after it needs a new confirmation.
    return mapping.get("confirmed") is True and mapping.get("digest") == digest(mapping)


def require_confirmed(mapping: dict) -> None:
    """Raises MappingError unless is_confirmed holds, and says which of its two tests failed."""
    if mapping.get("confirmed") is not True:
        raise MappingError("the role mapping is not confirmed: read it, then run confirm")
    if mapping.get("digest") != digest(mapping):
        raise MappingError("the role mapping changed after it was confirmed: run confirm again")


def drift(mapping: dict, schemas: dict[str, Schema]) -> list[str]:
    """One line per role that no longer fits the live schema. An empty list means the mapping still holds."""
    problems = []
    for role in R.ROLES:
        if role.name not in mapping["roles"]:
            problems.append(f"role {role.name}: not in the mapping; run discover again")
            continue
        value, schema = value_of(mapping, role.name), schemas[role.graph]
        where = f"in the {role.graph} graph"
        if value is None:
            if role.required:
                problems.append(f"role {role.name}: required, and nothing plays it")
            continue
        if role.kind == R.LABEL:
            if value not in schema.labels:
                problems.append(f"role {role.name}: label {value} no longer exists {where}")
        elif role.kind == R.PROPERTY:
            label = value_of(mapping, role.on)
            if label is None:
                problems.append(f"role {role.name}: its label role {role.on} has no value")
            elif value not in schema.properties.get(label, ()):
                problems.append(f"role {role.name}: property {value} is no longer on label {label} {where}")
        else:
            start = value_of(mapping, role.start)
            ends = [value_of(mapping, e) for e in role.ends if value_of(mapping, e)]
            if start is None or not ends:
                problems.append(f"role {role.name}: its label roles {role.start} and {', '.join(role.ends)} "
                                "have no value")
            elif role.kind == R.RELATIONSHIP:
                if value not in schema.types_between(start, ends):
                    problems.append(f"role {role.name}: relationship type {value} no longer runs from {start} "
                                    f"to {' or '.join(ends)} {where}")
            else:
                problems.extend(_path_drift(role, value, start, ends[0], schema, where))
    return problems


def _path_drift(role, value, start, end, schema, where):
    """The drift lines for one path role: its value must have the right form, each of its types must still
    exist, and the types must still lead from the start label to the end label within max_hops steps."""
    # The renderer writes max_hops into the query as the upper bound of a variable-length pattern. The limit of 5
    # keeps a hand-edited mapping from asking the server for a search of any length. bool is refused by name
    # because Python counts True as the integer 1.
    if (not isinstance(value, dict) or not value.get("types") or not isinstance(value.get("max_hops"), int)
            or isinstance(value["max_hops"], bool) or not 1 <= value["max_hops"] <= 5):
        return [f"role {role.name}: a path needs a list of types and max_hops from 1 to 5"]
    live = {t for _, t, _ in schema.relationships}
    gone = [t for t in value["types"] if t not in live]
    if gone:
        return [f"role {role.name}: relationship type {', '.join(gone)} no longer exists {where}"]
    # Walk the schema, not the data: one step moves from every label reached so far along the path's types.
    reached, frontier = {start}, {start}
    for _ in range(value["max_hops"]):
        frontier = {e for s, t, e in schema.relationships if s in frontier and t in value["types"]}
        reached |= frontier
        if end in frontier:
            return []
    return [f"role {role.name}: no path of {', '.join(value['types'])} leads from {start} to {end} {where} "
            f"in {value['max_hops']} steps"]


def confirm(mapping: dict, schemas: dict[str, Schema], now: dt.datetime | None = None) -> dict:
    """The mapping marked as confirmed. Refuses a mapping that does not fit the live schema. The digest is taken
    last, over the values as confirmed, so is_confirmed can tell a later edit."""
    problems = drift(mapping, schemas)
    if problems:
        raise MappingError("the mapping does not fit the graphs:\n  " + "\n  ".join(problems))
    now = now or dt.datetime.now(dt.timezone.utc)
    confirmed = dict(mapping, confirmed=True, confirmed_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    confirmed["digest"] = digest(confirmed)
    return confirmed
