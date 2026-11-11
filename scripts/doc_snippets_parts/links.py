"""The relative links of the documents: each must point at a file or a folder of the tree.

A link that points nowhere fails a reader exactly where they wanted to read on. This part reads every Markdown
document and every HTML page of the tree, the generated ones too, and checks each link that names a path.

What counts as a link: in Markdown, the target of [text](target) and ![text](target), and of a reference
definition, a line of the form [name]: target. Text inside a code block or a code span is not a link. In HTML,
the href and src attributes of the page's elements; text inside a <script> or a <style> is not read, so the data
a viewer page carries is left alone.

What is not checked: a link with a scheme (http:, https:, mailto: and the like), a link that is only an anchor
(#part), and whether an anchor exists in the page it names. The path before a # or a ? is checked.

A target is compared with the tree's own list of files, letter for letter. So a link that differs from the file's
name only in case fails here, as it would on a file system that tells the two apart.
"""
from __future__ import annotations

import posixpath
import re
from html.parser import HTMLParser
from urllib.parse import unquote

from .extract import FENCE, tree_entries
from .pages import is_page

# Pages that are templates, not documents: a builder fills each in and writes the page a reader opens, and that
# page is checked. A template's links hold placeholders, or are written from the place of the page it becomes.
TEMPLATES = ("scripts/docs_template.html", "business_architecture/ontology/viewer/horoi_page.html")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
# [text](target) or [text](target "title"). The target is in <...> or runs to the first space or closing bracket,
# and may hold one level of round brackets of its own.
INLINE = re.compile(r"\]\(\s*(<[^<>\n]*>|(?:[^()\s]|\([^()\s]*\))*)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
OPEN_END = re.compile(r"\]\(\s*$")   # a line that ends where a target would start
DEFINITION = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*(<[^<>\n]*>|\S+)")


def markdown_links(text: str) -> list:
    """[(line number, target)] of a Markdown document's links, in the order they stand."""
    found, fence, opened = [], None, None
    for number, line in enumerate(text.split("\n"), 1):
        # A target may start on the line after "](". The opening line's end is then read with this line, and the
        # link counts for the line that opens it. A blank line or a code line ends the wait.
        carried, opened = opened, None
        mark = FENCE.match(line)
        if fence is None and mark:
            fence = mark.group(2)
            continue
        if fence is not None:
            if mark and mark.group(2)[0] == fence[0] and len(mark.group(2)) >= len(fence) and not mark.group(3).strip():
                fence = None
            continue
        if line.startswith("    ") or line.startswith("\t"):
            continue   # an indented code block; a link inside a deeply nested list item is missed, never misread
        plain = CODE_SPAN.sub("", line)
        definition = DEFINITION.match(plain)
        if definition:
            found.append((number, definition.group(1).strip("<>")))
            continue
        if carried and plain.strip():
            joined = INLINE.match("](" + plain.lstrip())
            if joined:
                found.append((carried, joined.group(1).strip("<>")))
                plain = plain.lstrip()[joined.end() - 2:]
        found += [(number, target.strip("<>")) for target in INLINE.findall(plain)]
        if OPEN_END.search(plain):
            opened = number
    return found


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name.lower() in ("href", "src") and value:
                self.found.append((self.getpos()[0], value.strip()))

    handle_startendtag = handle_starttag


def html_links(text: str) -> list:
    """[(line number, target)] of the href and src attributes of an HTML page's elements."""
    reader = _Links()
    reader.feed(text)
    reader.close()
    return reader.found


def link_path(doc: str, target: str):
    """The path a link names, relative to the root, or None when the link is not a path of the tree to check:
    it has a scheme, it starts with // (another host), or it is only an anchor or a query."""
    if SCHEME.match(target) or target.startswith("//"):
        return None
    path = unquote(re.split(r"[#?]", target, maxsplit=1)[0])
    if not path:
        return None
    base = "" if path.startswith("/") else posixpath.dirname(doc)
    return posixpath.normpath(posixpath.join(base, path.lstrip("/")))


def broken_links(root, docs=None) -> list:
    """One line per link that points at no file or folder of the tree: "doc:line: target". docs names the
    documents to read, relative to the root; by default every Markdown document and HTML page of the tree."""
    entries = set(tree_entries(root))
    folders = {"."} | {posixpath.dirname(e) for e in entries}
    folders |= {parent for f in list(folders) for parent in _parents(f)}
    failures = []
    for doc in sorted(docs if docs is not None else (e for e in entries if (e.lower().endswith(".md") or is_page(e))
                                                     and e not in TEMPLATES)):
        try:
            with (root / doc).open(encoding="utf-8", newline="") as f:
                text = f.read().replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError) as err:
            failures.append(f"{doc}: cannot be read ({type(err).__name__})")
            continue
        for line, target in (html_links if is_page(doc) else markdown_links)(text):
            path = link_path(doc, target)
            if path is None or path in entries or path in folders:
                continue
            said = "points outside the tree" if path.startswith("..") else "is not a file or a folder of the tree"
            failures.append(f"{doc}:{line}: the link {target} {said}")
    return failures


def _parents(folder: str):
    while folder and folder != ".":
        folder = posixpath.dirname(folder)
        yield folder or "."
