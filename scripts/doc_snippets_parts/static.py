"""What the check reads without running anything: a usage pattern against its script, the order of the documents
when a chain goes on from one document into another, and the list of the blocks that no test runs."""
from __future__ import annotations

import html
import re
from pathlib import Path

from .extract import FENCE, documents, extract
from .pages import extract_html, html_documents, is_page

OPTION = re.compile(r"(?<![\w-])--[A-Za-z][A-Za-z0-9-]*")
SCRIPT = re.compile(r"[\w./\\-]+\.py\b")
KEY_LENGTH = 60


def usage_problem(root: Path, value: str, body: str):
    """Why a `usage=<path>` block is wrong, or None. The block shows how a script is called, with a name in angle
    brackets for each value and square brackets around what is optional, so it cannot run. Each of its lines must
    name a script that exists and only options that the script's own text holds as "--name". The path is the
    script, or the folder that holds every script the block names."""
    target = (root / value).resolve() if value else None
    if target is None or not target.is_relative_to(root.resolve()) or not target.exists():
        return f"`{value}` must be a script or a folder inside the release"
    lines, pending = [], ""
    for raw in body.split("\n"):
        line = raw.strip()
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        lines.append(pending + line)
        pending = ""
    checked = 0
    for line in [text for text in lines + [pending] if text.strip() and not text.lstrip().startswith("#")]:
        named = SCRIPT.search(line)
        if not named:
            return f"the line `{line[:60]}` names no script"
        script = target if target.is_file() else target / Path(named.group(0).replace("\\", "/")).name
        if target.is_file() and Path(named.group(0).replace("\\", "/")).name != target.name:
            return f"the line names {named.group(0)}, and the tag names {value}"
        if not script.is_file():
            return f"the script {script.relative_to(root.resolve()).as_posix()} does not exist"
        source = script.read_text(encoding="utf-8")
        unknown = [option for option in dict.fromkeys(OPTION.findall(line[named.end():]))
                   if f'"{option}"' not in source and f"'{option}'" not in source]
        if unknown:
            return f"{script.name} has no option {', '.join(unknown)}"
        checked += 1
    return None if checked else "the block names no script"


def chain_order(root: Path, registry, docs: list) -> list:
    """The documents in the order they are checked. A context with an owner is one chain that starts in the owner
    document, so a document that uses the context is read after the owner, wherever its name sorts."""
    docs = list(docs)
    for context in registry.contexts.values():
        if not context.owner or context.owner not in docs:
            continue
        uses = re.compile(rf"\brun=(?:[\w-]+,)*{re.escape(context.name)}(?![\w-])")
        early = [doc for doc in docs[:docs.index(context.owner)]
                 if (root / doc).is_file() and uses.search((root / doc).read_text(encoding="utf-8", errors="replace"))]
        for doc in early:
            docs.remove(doc)
        at = docs.index(context.owner) + 1
        docs[at:at] = early
    return docs


def _markdown_headings(text: str) -> list:
    """(line, heading) for each heading outside a fenced block."""
    found, closing = [], None
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if closing:
            if closing.match(line):
                closing = None
            continue
        fence = FENCE.match(line)
        if fence and not (fence.group(2)[0] == "`" and "`" in fence.group(3)):
            closing = re.compile(rf"^ *{re.escape(fence.group(2)[0])}{{{len(fence.group(2))},}}\s*$")
            continue
        heading = re.match(r" {0,3}#{1,6} +(.*?)\s*#*\s*$", line)
        if heading:
            found.append((number, heading.group(1)))
    return found


def _page_headings(text: str) -> list:
    found = []
    for m in re.finditer(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", text.replace("\r\n", "\n"), re.S | re.I):
        words = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
        found.append((text.count("\n", 0, m.start()) + 1, " ".join(words.split())))
    return found


def block_key(body: str) -> str:
    """The short text that names a block in the table of blocks that are not run: the start of its first line
    with text."""
    first = next((line.strip() for line in body.split("\n") if line.strip()), "")
    return " ".join(first.split())[:KEY_LENGTH].rstrip()


def not_run(root: Path, docs=None) -> list:
    """Every block that no test runs: the blocks tagged `skip`, as (document, heading, key, reason). An `expect`
    block after a skipped block shows that block's output and is not listed on its own."""
    out = []
    for doc in (docs or documents(root) + html_documents(root)):
        text = (root / doc).read_text(encoding="utf-8")
        blocks, _ = (extract_html if is_page(doc) else extract)(doc, text)
        headings = _page_headings(text) if is_page(doc) else _markdown_headings(text)
        for block in blocks:
            if block.tag != "skip":
                continue
            heading = next((name for line, name in reversed(headings) if line <= block.line), "")
            out.append((doc, heading, block_key(block.body), block.attrs.get("reason", "").partition(":")[0].strip()))
    return out


def table_rows(text: str, heading: str) -> list:
    """The rows of the first table under a heading of a Markdown text, each as its cells. A cell's code-span
    backticks are dropped, and `\\|` is read as a bar."""
    lines = text.replace("\r\n", "\n").split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []
    rows = []
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        rows.append([re.sub(r"^(`+) ?(.*?) ?\1$", r"\2", cell) for cell in cells])
    return [row for row in rows[2:]]
