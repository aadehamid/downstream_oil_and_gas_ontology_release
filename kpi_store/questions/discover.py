"""Reads a graph's schema and proposes which label, property or relationship type plays each role.

The schema comes from three plain queries, so it needs no plugin. `read_schema` takes a function that runs one
read query and returns its rows, so the tests pass a fake and the command line passes a driver session.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import roles as R

# Counted in full: a sample could miss a label that few nodes carry, and the drift check must not report a
# label as gone when it is only rare.
LABELS_QUERY = "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS nodes"
PROPERTIES_QUERY = "MATCH (n) UNWIND labels(n) AS label UNWIND keys(n) AS key RETURN label, key, count(*) AS nodes"
RELATIONSHIPS_QUERY = ("MATCH (a)-[r]->(b) UNWIND labels(a) AS start UNWIND labels(b) AS end "
                       "RETURN start, type(r) AS type, end, count(*) AS relationships")

MAX_HOPS = 4


@dataclass
class Schema:
    labels: dict[str, int] = field(default_factory=dict)
    properties: dict[str, set[str]] = field(default_factory=dict)
    relationships: set[tuple[str, str, str]] = field(default_factory=set)

    def types_between(self, start: str, ends) -> list[str]:
        return sorted({t for s, t, e in self.relationships if s == start and e in ends})


def read_schema(run: Callable[[str], list[dict]]) -> Schema:
    schema = Schema()
    for row in run(LABELS_QUERY):
        schema.labels[row["label"]] = row["nodes"]
    for row in run(PROPERTIES_QUERY):
        schema.properties.setdefault(row["label"], set()).add(row["key"])
    for row in run(RELATIONSHIPS_QUERY):
        schema.relationships.add((row["start"], row["type"], row["end"]))
    return schema


def _plain(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _match(candidates, names):
    """The best name for a role, how sure the match is, and the other names a person might mean.

    The first candidate, spelled exactly, scores 1.0. A later candidate scores 0.9. A name that differs only in
    case or punctuation scores 0.7. With no match the value is None and every name is offered."""
    names = sorted(names)
    found = []
    for place, candidate in enumerate(candidates):
        if candidate in names:
            found.append((1.0 if place == 0 else 0.9, candidate))
    for candidate in candidates:
        for name in names:
            if _plain(name) == _plain(candidate) and all(name != f[1] for f in found):
                found.append((0.7, name))
    if not found:
        return None, 0.0, names
    found.sort(key=lambda f: -f[0])
    return found[0][1], found[0][0], [name for _, name in found[1:]]


def _paths(schema: Schema, start: str, end: str):
    """Every shortest chain of relationship types from one label to another, by breadth-first search."""
    frontier, seen, found = [(start, ())], {start}, []
    for _ in range(MAX_HOPS):
        following, reached = [], set()
        for label, types in frontier:
            for s, t, e in sorted(schema.relationships):
                if s != label:
                    continue
                if e == end:
                    found.append(types + (t,))
                elif e not in seen:
                    following.append((e, types + (t,)))
                    reached.add(e)
        if found:
            return found
        seen |= reached
        frontier = following
    return []


def _entry(role: R.Role, value, confidence, alternatives):
    return {"graph": role.graph, "kind": role.kind, "required": role.required, "meaning": role.meaning,
            "value": value, "confidence": confidence, "alternatives": alternatives}


def propose(schemas: dict[str, Schema]) -> dict:
    """A mapping for a person to read and confirm: each role's proposed value, a confidence and the alternatives."""
    entries: dict[str, dict] = {}

    def label_of(role_name):
        return entries[role_name]["value"]

    for role in (r for r in R.ROLES if r.kind == R.LABEL):
        entries[role.name] = _entry(role, *_match(role.candidates, schemas[role.graph].labels))
    for role in (r for r in R.ROLES if r.kind != R.LABEL):
        schema = schemas[role.graph]
        if role.kind == R.PROPERTY:
            label = label_of(role.on)
            entries[role.name] = _entry(role, *(_match(role.candidates, schema.properties.get(label, ()))
                                                if label else (None, 0.0, [])))
            continue
        start, ends = label_of(role.start), [label_of(e) for e in role.ends if label_of(e)]
        if not start or not ends:
            entries[role.name] = _entry(role, None, 0.0, [])
        elif role.kind == R.RELATIONSHIP:
            types = schema.types_between(start, ends)
            value, confidence, others = _match(role.candidates, types)
            if value is None and len(types) == 1:
                # One type joins the two labels and it has another name than expected: likely, not certain.
                value, confidence, others = types[0], 0.5, []
            entries[role.name] = _entry(role, value, confidence, others)
        else:
            found = sorted(_paths(schema, start, ends[0]), key=lambda p: (-len(set(p) & set(role.candidates)), p))
            if not found:
                entries[role.name] = _entry(role, None, 0.0, [])
                continue
            best = found[0]
            sure = 1.0 if set(best) <= set(role.candidates) else 0.6
            shapes = list(dict.fromkeys((tuple(sorted(set(p))), len(p)) for p in found))
            entries[role.name] = _entry(role, {"types": list(shapes[0][0]), "max_hops": shapes[0][1]}, sure,
                                        [{"types": list(types), "max_hops": hops} for types, hops in shapes[1:]])
    return {"format": 1, "confirmed": False, "confirmed_at": "", "digest": "",
            "roles": {role.name: entries[role.name] for role in R.ROLES}}
