"""The command line."""
from __future__ import annotations

import argparse
import os
import re
import tomllib
from collections import Counter
from pathlib import Path

from .check import NESTED_NOTE, Checker
from .extract import documents, extract
from .pages import extract_html, html_documents, is_page
from .registry import ROOT, RegistryError, load_registry


def tally(root: Path, docs=None) -> dict:
    """The blocks of each document, counted by tag (a skip by its reason)."""
    out = {}
    for doc in (docs or documents(root) + html_documents(root)):
        read = extract_html if is_page(doc) else extract
        blocks, problems = read(doc, (root / doc).read_text(encoding="utf-8"))
        counts = Counter()
        for block in blocks:
            if block.tag == "skip":
                counts["skip " + block.attrs.get("reason", "").partition(":")[0].strip()] += 1
            elif block.tag == "run":
                counts[f"run={block.value}" + (" define" if "define" in block.flags else "")] += 1
            else:
                counts[block.tag] += 1
        if problems:
            counts["(untagged or unreadable)"] = len(problems)
        if counts:
            out[doc] = counts
    return out


def html_pages(root: Path) -> list:
    """(page, <pre> blocks, <code> spans outside them) for each HTML page that no Markdown file is the source of.
    The check reads the blocks of these pages; a <code> span in a sentence is text, as in Markdown."""
    out = []
    for page in html_documents(root):
        text = (root / page).read_text(encoding="utf-8", errors="replace")
        pre = re.findall(r"<pre\b.*?</pre>", text, re.S | re.I)
        rest = re.sub(r"<pre\b.*?</pre>", "", text, flags=re.S | re.I)
        out.append((page, len(pre), len(re.findall(r"<code\b", rest, re.I))))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="doc_snippets.py",
                                     description="Test every code block in the documents.")
    parser.add_argument("--root", type=Path, default=ROOT, help="the top folder of the release (default: this one)")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="run or check every block")
    check.add_argument("docs", nargs="*", help="documents, relative to the top folder (default: every one)")
    check.add_argument("--strict", action="store_true", help="fail on a temporary reason; used at the cut")
    check.add_argument("--all-contexts", action="store_true",
                       help="fail when a context cannot run here, instead of counting its blocks as skipped")
    check.add_argument("--static", action="store_true", help="check the tags, files and parses; run nothing")
    check.add_argument("--verbose", "-v", action="store_true", help="print one line per block")
    listing = sub.add_parser("list", help="count the blocks of each document by tag")
    listing.add_argument("docs", nargs="*")
    sub.add_parser("contexts", help="the contexts, and which ones can run here")
    sub.add_parser("html", help="the HTML pages with no Markdown source, which the check reads too")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        registry = load_registry()
    except (RegistryError, tomllib.TOMLDecodeError) as e:
        print(f"FAIL {e}")
        return 1

    def relative(docs):
        return [Path(os.path.abspath(d)).relative_to(root).as_posix() if os.path.isabs(d) else Path(d).as_posix()
                for d in docs]

    if args.command == "check":
        result = Checker(root, registry, strict=args.strict, all_contexts=args.all_contexts,
                         static=args.static, report=print if args.verbose else None).check(relative(args.docs))
        for failure in result.failures:
            print("FAIL " + failure)
        print(result.summary())
        if result.nested:
            print(NESTED_NOTE)
        return 1 if result.failures else 0
    if args.command == "list":
        total = Counter()
        for doc, counts in tally(root, relative(args.docs)).items():
            total.update(counts)
            print(f"{sum(counts.values()):4d}  {doc}: " + ", ".join(f"{k} {n}" for k, n in sorted(counts.items())))
        print(f"{sum(total.values()):4d}  total: " + ", ".join(f"{k} {n}" for k, n in sorted(total.items())))
        return 0
    if args.command == "contexts":
        for context in registry.contexts.values():
            missing = context.missing(os.environ)
            state = "runs here" if not missing else "off: set " + ", ".join(missing)
            print(f"{context.name}: {state}. {context.about}")
        return 0
    for page, pre, code in html_pages(root):
        print(f"{pre:4d} pre, {code:4d} code  {page}")
    return 0
