"""The `parse` tag: one parser per language. Each raises when the text is not valid."""
from __future__ import annotations

import json
import re
import sys
import tomllib

from .registry import ROOT


def parse_json(body, attrs):
    json.loads(body)


def parse_toml(body, attrs):
    tomllib.loads(body)


def parse_yaml(body, attrs):
    import yaml
    list(yaml.safe_load_all(body))


def parse_turtle(body, attrs):
    import rdflib
    # A document often shows a few triples without their prefix lines. Each prefix the block uses and does
    # not declare gets a made-up namespace, so the triples themselves are still read.
    declared = set(re.findall(r"(?im)^\s*@?prefix\s+([\w-]*):", body))
    used = set(re.findall(r"(?<![\w<:/#])([A-Za-z][\w-]*):(?!//)", body))
    made_up = "".join(f"@prefix {name}: <urn:doc-snippets:{name}#> .\n" for name in sorted(used - declared))
    rdflib.Graph().parse(data=made_up + body, format="turtle")


def parse_sparql(body, attrs):
    from rdflib.plugins.sparql import prepareQuery, prepareUpdate
    try:
        prepareQuery(body)
    except Exception as query_error:
        try:
            prepareUpdate(body)
        except Exception:
            raise query_error from None


def parse_sql(body, attrs):
    import sqlglot
    if not [s for s in sqlglot.parse(body, read=attrs.get("dialect", "databricks")) if s]:
        raise ValueError("no statement")


def parse_cypher(body, attrs):
    """A token check, not a grammar check: there is no Cypher parser here. The questions' tokenizer reads the
    text, and this finds a string, a backtick name or a bracket that is never closed, and a block with no word
    in it. Clauses in the wrong order pass."""
    sys.path.insert(0, str(ROOT))
    try:
        from kpi_store.questions.render import tokens
    finally:
        sys.path.pop(0)
    pairs, stack, found = {")": "(", "]": "[", "}": "{"}, [], tokens(body)
    for kind, text in found:
        if kind != "mark":
            continue
        if text in "'\"`":
            raise ValueError(f"a {text} that is never closed")
        if text in pairs.values():
            stack.append(text)
        elif text in pairs and (not stack or stack.pop() != pairs[text]):
            raise ValueError(f"a {text} with no opening bracket")
    if stack:
        raise ValueError(f"a {stack[-1]} that is never closed")
    if not any(kind == "word" for kind, _ in found):
        raise ValueError("no statement")


PARSERS = {"json": parse_json, "toml": parse_toml, "yaml": parse_yaml, "turtle": parse_turtle,
           "sparql": parse_sparql, "sql": parse_sql, "cypher": parse_cypher}
