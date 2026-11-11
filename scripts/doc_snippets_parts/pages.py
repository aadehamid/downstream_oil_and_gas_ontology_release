"""The code blocks of an HTML page that was written by hand.

A page built from a Markdown file is tested through that file. A page written by hand has no such source, so its
blocks carry the tag themselves: a <pre> element, or any other element that shows code as a block, has the
attribute data-snippet, which holds what a Markdown fence holds after its backticks.

    <pre data-snippet="bash run=release-copy">python3 scripts/epm_facts.py counts</pre>
    <pre data-snippet="text expect">...</pre>
    <pre data-snippet="text skip reason=&quot;illustration: the shape of a report row&quot;">...</pre>

The attribute changes nothing a reader sees. A <pre> with no data-snippet fails the check, as a fence with no tag
does. The standard library's parser reads the page, so text in a <script> or a <style> is never a block.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from .extract import Block, parse_info, tree_files

ATTRIBUTE = "data-snippet"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_MAY_HOLD_A_BLOCK = re.compile(r"<pre\b|data-snippet", re.I)


def is_page(doc: str) -> bool:
    return doc.lower().endswith((".html", ".htm"))


def html_documents(root) -> list:
    """Every HTML page of the tree that no Markdown file is the source of: no Markdown file has its name, and it
    does not say which tool built it. None is left out: a page with no block passes, and one that gains a block
    must tag it."""
    files = set(tree_files(root))
    out = []
    for page in sorted(p for p in files if is_page(p)):
        if page.rsplit(".", 1)[0] + ".md" in files:
            continue
        with (root / page).open(encoding="utf-8", errors="replace") as f:
            head = f.read(20000)
        if 'name="generator"' not in head:
            out.append(page)
    return out


class _Reader(HTMLParser):
    def __init__(self, doc):
        super().__init__(convert_charrefs=True)
        self.doc, self.found, self.problems = doc, [], []
        self.open_tag, self.depth, self.line, self.info, self.text = None, 0, 0, None, []

    def handle_starttag(self, tag, attrs):
        if self.open_tag:
            self.depth += tag == self.open_tag
            if tag == "br":
                self.text.append("\n")
            return
        info = dict(attrs).get(ATTRIBUTE)
        if tag != "pre" and info is None:
            return
        line = self.getpos()[0]
        if tag in VOID:
            self.problems.append(f"{self.doc}:{line}: a <{tag}> element holds no text, so it cannot be a code block")
            return
        self.open_tag, self.depth, self.line, self.info, self.text = tag, 1, line, info, []

    def handle_startendtag(self, tag, attrs):
        if not self.open_tag:
            self.handle_starttag(tag, attrs)
            if self.open_tag == tag:
                self.handle_endtag(tag)
        elif tag == "br":
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag != self.open_tag:
            return
        self.depth -= 1
        if self.depth == 0:
            self.found.append((self.line, self.open_tag, self.info, "".join(self.text)))
            self.open_tag = None

    def handle_data(self, data):
        if self.open_tag:
            self.text.append(data)


def extract_html(doc: str, text: str):
    """The code blocks of a page's text, in order, and the problems found while reading it. A block's text is
    what the reader sees: character references are decoded and the tags inside it are dropped."""
    if not _MAY_HOLD_A_BLOCK.search(text):
        return [], []
    reader = _Reader(doc)
    reader.feed(text.replace("\r\n", "\n"))
    reader.close()
    blocks, problems = [], list(reader.problems)
    if reader.open_tag:
        problems.append(f"{doc}:{reader.line}: the <{reader.open_tag}> code block is never closed")
    for line, tag, info, body in reader.found:
        where = f"{doc}:{line}"
        if info is None:
            problems.append(f"{where}: the <pre> block has no {ATTRIBUTE} attribute. Write "
                            f"{ATTRIBUTE}=\"<language> <tag>\", as on a Markdown fence")
            continue
        parsed, error = parse_info(info)
        if error:
            problems.append(f"{where}: {error}")
            continue
        lang, name, value, attrs, flags = parsed
        if name == "nested":
            problems.append(f"{where}: a nested block is for a Markdown document, not for a page")
            continue
        # A browser drops the line break right after <pre>, so the block's text starts on the next line.
        blocks.append(Block(doc=doc, line=line, lang=lang, tag=name, value=value, attrs=attrs, flags=flags,
                            body=body[1:] if tag == "pre" and body.startswith("\n") else body))
    for block, following in zip(blocks, blocks[1:]):
        block.expect_follows = following.tag == "expect"
    problems.sort(key=lambda p: int(p[len(doc) + 1:].split(":", 1)[0]))
    return blocks, problems
