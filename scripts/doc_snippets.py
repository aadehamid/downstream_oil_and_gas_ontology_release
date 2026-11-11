#!/usr/bin/env python3
"""Test every code block in the documents: the Markdown files, and the HTML pages written by hand.

    python3 scripts/doc_snippets.py check [DOC ...]    run or check every block; exit 1 on any failure
    python3 scripts/doc_snippets.py list [DOC ...]     count the blocks of each document by tag
    python3 scripts/doc_snippets.py contexts           the contexts, and which ones can run here
    python3 scripts/doc_snippets.py html               the HTML pages with no Markdown source, and their blocks
    python3 scripts/doc_snippets.py links [DOC ...]    check that every relative link points at a file of the tree

A document that shows a command which no longer works misleads its reader. So every fenced code block carries a
tag after its language, and a <pre> block of a hand-written page carries the same tag in a data-snippet
attribute. This tool acts on the tag: it runs the block, compares it with a file or with the output of the block
before it, parses it, or counts it as skipped for a reason from a fixed list. A block with no tag, an unknown tag
or a reason outside the list fails the check. scripts/DOC-SNIPPETS.md is the guide for writers;
scripts/doc_snippets.toml holds the contexts and the reasons.

The code is in scripts/doc_snippets_parts/, one module per job. Standard library only, Python 3.11 or later.
The parsers for Turtle, SPARQL, YAML and SQL need rdflib, pyyaml and sqlglot; a `parse` block whose parser is not
installed fails with the command that installs it.
"""
import sys
from pathlib import Path

# The Cypher check imports the questions' tokenizer from the tree, and this file imports its own parts. Python
# must not leave its cache folders there: this tool only reads the tree.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from doc_snippets_parts.check import Checker, Result  # noqa: E402,F401
from doc_snippets_parts.links import broken_links, html_links, link_path, markdown_links  # noqa: E402,F401
from doc_snippets_parts.extract import SKIP_DIRS, documents, extract, tree_entries, tree_files  # noqa: E402,F401
from doc_snippets_parts.pages import extract_html, html_documents  # noqa: E402,F401
from doc_snippets_parts.match import has_fixed_text, normalise, output_matches  # noqa: E402,F401
from doc_snippets_parts.registry import NESTED, NESTED_FILE, REGISTRY, ROOT, RegistryError, load_registry  # noqa: E402,F401
from doc_snippets_parts.report import html_pages, main, tally  # noqa: E402,F401
from doc_snippets_parts.run import NotSimple, command_lines, resolve_program, run_process, split_command  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main())
