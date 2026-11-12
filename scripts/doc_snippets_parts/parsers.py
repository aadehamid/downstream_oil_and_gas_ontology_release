"""The `parse` tag: one parser per language. Each raises when the text is not valid."""
from __future__ import annotations

import ast
import configparser
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


def parse_ini(body, attrs):
    """A settings file of sections and `name = value` lines. A block that shows lines of one section without
    its heading is read under a made-up heading."""
    text = body if re.search(r"(?m)^\s*\[", body) else "[doc-snippets]\n" + body
    configparser.ConfigParser(interpolation=None, strict=True).read_string(text)


def parse_python(body, attrs):
    """The syntax only: nothing is imported and nothing runs. For a skipped block."""
    ast.parse(body)


def _rdf_version(attrs):
    """rdf=1.2 names the syntax of RDF 1.2: a triple term, a reifier. rdflib does not read it, so pyoxigraph does."""
    if attrs.get("rdf", "1.1") not in ("1.1", "1.2"):
        raise ValueError("rdf= is 1.1 (the default) or 1.2")
    return attrs.get("rdf", "1.1")


def parse_turtle(body, attrs):
    # A document often shows a few triples without their prefix lines. Each prefix the block uses and does
    # not declare gets a made-up namespace, so the triples themselves are still read.
    declared = set(re.findall(r"(?im)^\s*@?prefix\s+([\w-]*):", body))
    used = set(re.findall(r"(?<![\w<:/#])([A-Za-z][\w-]*):(?!//)", body))
    made_up = "".join(f"@prefix {name}: <urn:doc-snippets:{name}#> .\n" for name in sorted(used - declared))
    if _rdf_version(attrs) == "1.2":
        import pyoxigraph
        if not list(pyoxigraph.parse(made_up + body, format=pyoxigraph.RdfFormat.TURTLE)):
            raise ValueError("no triple")
        return
    import rdflib
    rdflib.Graph().parse(data=made_up + body, format="turtle")


def parse_sparql(body, attrs):
    if _rdf_version(attrs) == "1.2":
        import pyoxigraph
        pyoxigraph.Store().query(body)      # an empty store in memory: the query is parsed and finds nothing
        return
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


def _questions_tokenizer():
    """The tokenizer of this tree's cross-graph questions. Another copy of the package may already be loaded,
    from a folder that is gone: a test that unpacks the release zip leaves one behind. So a package loaded from
    outside this tree is set aside while this one is imported, and put back afterwards."""
    root = str(ROOT.resolve())
    held = {name: module for name, module in sys.modules.items()
            if (name == "kpi_store" or name.startswith("kpi_store."))
            and not str(getattr(module, "__file__", "") or "").startswith(root)}
    if "kpi_store" not in held:
        held = {}
    saved = {name: sys.modules.pop(name) for name in [n for n in sys.modules if n == "kpi_store" or n.startswith("kpi_store.")]} if held else {}
    sys.path.insert(0, root)
    try:
        from kpi_store.questions.render import tokens
    finally:
        sys.path.remove(root)
        if saved:
            for name in [n for n in sys.modules if n == "kpi_store" or n.startswith("kpi_store.")]:
                del sys.modules[name]
            sys.modules.update(saved)
    return tokens


def parse_cypher(body, attrs):
    """A token check, not a grammar check: there is no Cypher parser here. The questions' tokenizer reads the
    text, and this finds a string, a backtick name or a bracket that is never closed, and a block with no word
    in it. Clauses in the wrong order pass."""
    tokens = _questions_tokenizer()
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


PARSERS = {"json": parse_json, "toml": parse_toml, "yaml": parse_yaml, "ini": parse_ini, "python": parse_python,
           "turtle": parse_turtle,
           "sparql": parse_sparql, "sql": parse_sql, "cypher": parse_cypher}
