"""The command line."""
from __future__ import annotations

import argparse
import os
import re
import tomllib
from collections import Counter
from pathlib import Path

from .check import NESTED_NOTE, REFRESH, RELEASE_NOTE, Checker
from .extract import documents, extract
from .links import broken_links
from .pages import extract_html, html_documents, is_page
from .registry import REGISTRY, ROOT, RegistryError, load_registry, release_digest, write_release_digest


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


def describe_release(root: Path, registry, registry_path: Path, write: bool) -> int:
    """Says whether the registry's digest is this release's, or with `write` records this release's digest."""
    if not registry.describes:
        print(f"FAIL {registry_path.name} has no [describes] table, so it names no release")
        return 1
    now = release_digest(root, registry)
    if now is None:
        print(f"FAIL the file {registry.describes} does not exist, so this folder holds no release to describe")
        return 1
    if now == registry.sha256:
        print(f"the documents' examples describe this release ({registry.describes}, SHA-256 {now})")
        return 0
    if not write:
        print(f"FAIL the documents' examples describe another release: {registry_path.name} holds {registry.sha256}, and "
              f"{registry.describes} gives {now}. Bring the examples up to date, then run: {REFRESH}")
        return 1
    if not write_release_digest(registry_path, now):
        print(f"FAIL {registry_path.name} has no sha256 line to write to")
        return 1
    print(f"wrote {now} to {registry_path.name}: the documents' examples now describe this release")
    return 0


def main(argv=None, registry_path: Path = REGISTRY) -> int:
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
    links = sub.add_parser("links", help="check that every relative link of the documents points into the tree")
    links.add_argument("docs", nargs="*", help="documents, relative to the top folder (default: every one)")
    describe = sub.add_parser("describe-release", help="say whether the examples describe this release, or record that they do")
    how = describe.add_mutually_exclusive_group()
    how.add_argument("--write", action="store_true", help="record this release's digest in the registry")
    how.add_argument("--check", action="store_true", help="write nothing; exit 1 when the digest differs (the default)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        registry = load_registry(registry_path)
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
        if result.release_changed:
            print(RELEASE_NOTE)
        return 1 if result.failures else 0
    if args.command == "describe-release":
        return describe_release(root, registry, registry_path, args.write)
    if args.command == "links":
        failures = broken_links(root, relative(args.docs) or None)
        for failure in failures:
            print("FAIL " + failure)
        print(f"{len(failures)} broken link(s)" if failures else "every relative link points at a file or a folder of the tree")
        return 1 if failures else 0
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
