"""What the check reads without running anything: a usage pattern against its script, the order of the documents
when a chain goes on from one document into another, and the list of the blocks that no test runs."""
from __future__ import annotations

import ast
import html
import os
import re
import subprocess
import sys
from pathlib import Path

from .extract import FENCE, documents, extract
from .pages import extract_html, html_documents, is_page

OPTION = re.compile(r"(?<![\w-])--[A-Za-z][A-Za-z0-9-]*")
SCRIPT = re.compile(r"[\w./\\-]+\.py\b")
KEY_LENGTH = 60


def declared_options(source: str) -> set:
    """The options a script's argument parser declares: each text that starts with -- among the first arguments
    of a call to add_argument. Read from the script's syntax tree, so an option that is only named in a comment,
    a docstring or another string is not one."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "add_argument":
            found |= {arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                      and arg.value.startswith("--")}
    return found


def help_options(script: Path, subcommand=None):
    """The options the script's own --help names, for the script or for one of its subcommands. None when the
    script cannot print its help here: a package it imports is missing, or it has no such subcommand."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"PYTHONDONTWRITEBYTECODE": "1",
                                                                                 "PYTHONIOENCODING": "utf-8", "COLUMNS": "200"}
    try:
        script = script.resolve()
        done = subprocess.run([sys.executable, "-B", str(script), *([subcommand] if subcommand else []), "--help"],
                              cwd=script.parent, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = done.stdout.decode("utf-8", errors="replace")
    if done.returncode != 0 or "usage:" not in text.lower():
        return None
    return set(OPTION.findall(text))


# Methods that look a text up in the arguments or compare it with one: opts.get("--name"), argv.index("--name"),
# arg.startswith("--name").
LOOKUPS = {"get", "pop", "setdefault", "index", "count", "remove", "discard", "startswith", "__contains__"}


def handled_options(source: str) -> set:
    """The options that a script with a parser of its own handles: each text that is exactly --name and stands where
    the code reads its arguments. Such a place is a comparison or a membership test ("--name" in opts, arg ==
    "--name"), a `case` of a match statement, a lookup (opts["--name"], opts.get("--name"), argv.index("--name")),
    and a set, a tuple or a dict of options. A docstring, a comment, a longer string that holds the text, a name
    that is only given the text (x = "--name"), a list, which is how a command for another program is written, and
    an argument of any other call, such as SystemExit("--name"), are not counted. This reads where the code names
    the option, not what it does with it, which is the most a check can read from a hand-written parser."""
    found = set()
    for parent in ast.walk(ast.parse(source)):
        if isinstance(parent, ast.Compare):
            near = [parent.left, *parent.comparators]
        elif isinstance(parent, (ast.Set, ast.Tuple)):
            near = parent.elts
        elif isinstance(parent, ast.Dict):
            near = [*parent.keys, *parent.values]
        elif isinstance(parent, ast.Subscript):
            near = [parent.slice]
        elif isinstance(parent, ast.MatchValue):
            near = [parent.value]
        elif isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute) and parent.func.attr in LOOKUPS:
            near = parent.args
        else:
            continue
        found |= {node.value for node in near if isinstance(node, ast.Constant) and isinstance(node.value, str)
                  and OPTION.fullmatch(node.value)}
    return found


def script_options(script: Path, subcommand=None):
    """(the options the script takes, how they were read): "help", "declared" or "handled".

    A script that builds an argparse parser is asked for its own --help, and with a subcommand for that
    subcommand's too. When it cannot run here, because a package it imports is missing, its add_argument calls are
    read instead. A script with no such call parses its arguments by hand. It is never started, because nothing
    says what it would do with --help; the options its code handles are read from its text (handled_options)."""
    source = script.read_text(encoding="utf-8")
    declared = declared_options(source)
    if not declared:
        return handled_options(source), "handled"
    top = help_options(script)
    if top is None:
        return declared, "declared"
    return top | ((help_options(script, subcommand) or set()) if subcommand else set()), "help"


def usage_problem(root: Path, value: str, body: str):
    """Why a `usage=<path>` block is wrong, or None. The block shows how a script is called, with a name in angle
    brackets for each value and square brackets around what is optional, so it cannot run. Each of its lines must
    name a script that exists and only options that the script's argument parser takes (script_options). The path
    is the script, or the folder that holds every script the block names."""
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
        rest = line[named.end():]
        first = re.match(r"\s+([a-z][a-z0-9-]*)(?=\s|$)", rest)      # a subcommand, such as `build.py manifest`
        taken, _ = script_options(script, first.group(1) if first else None)
        unknown = [option for option in dict.fromkeys(OPTION.findall(rest)) if option not in taken]
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
