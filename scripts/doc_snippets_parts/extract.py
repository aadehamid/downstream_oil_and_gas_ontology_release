"""The documents of the tree and the code blocks of a document."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .registry import TAGS

FENCE = re.compile(r"^( *)(`{3,}|~{3,})(.*)$")
LIST_ITEM = re.compile(r"^( *)([-*+]|\d{1,9}[.)])( +|$)")
SKIP_DIRS = {".git", "__pycache__", ".venv", ".pytest_cache", "node_modules"}


@dataclass
class Block:
    doc: str            # the document, relative to the root
    line: int           # the line of the opening fence
    lang: str
    tag: str
    value: str          # the context of a run block, the path of a file or excerpt block
    attrs: dict
    flags: set
    body: str
    scope: str = ""     # blocks of one nested example share a scope, and so their own contexts
    expect_follows: bool = False    # the next block of the scope is an `expect` block

    @property
    def where(self) -> str:
        return f"{self.doc}:{self.line}"


def no_git_env(environ) -> dict:
    return {k: v for k, v in environ.items() if not k.startswith("GIT_")}


def tree_entries(root: Path) -> list:
    """Every file and every link of the tree, as paths relative to the root. Git names them when the root is a
    repository: the files it tracks and the new files it would add. A file Git ignores does not ship, so it is
    not part of the tree. A plain folder, such as an unpacked zip, is walked whole."""
    try:
        env = no_git_env(os.environ)
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, env=env, encoding="utf-8")
        if top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve():
            out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                                  "--exclude-standard"], capture_output=True, check=True, env=env).stdout
            return sorted(p for p in out.decode("utf-8").split("\0") if p and os.path.lexists(root / p))
    except FileNotFoundError:
        pass
    found = []
    for folder, dirs, files in os.walk(root):
        links = [d for d in dirs if (Path(folder) / d).is_symlink()]
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and d not in links)
        found += [(Path(folder) / f).relative_to(root).as_posix() for f in files + links]
    return sorted(found)


def tree_files(root: Path) -> list:
    """The entries of the tree that are files, a link to a file among them."""
    return [p for p in tree_entries(root) if (root / p).is_file()]


def documents(root: Path) -> list:
    """Every Markdown document of the tree. None is left out: a folder of generated or received documents has
    no code block today, and one that gains a block must tag it like any other."""
    return [p for p in tree_files(root) if p.lower().endswith(".md")]


def parse_info(info: str):
    """A fence's info string as (language, tag, value, attributes, flags), or an error text."""
    try:
        words = shlex.split(info)
    except ValueError as e:
        return None, f"the info string cannot be read ({e})"
    if not words:
        return None, "the block has no language and no tag"
    if len(words) == 1:
        return None, f"the block has no tag after its language `{words[0]}`"
    lang, head, rest = words[0], words[1], words[2:]
    tag, _, value = head.partition("=")
    if tag not in TAGS:
        return None, f"unknown tag `{tag}`: use one of {', '.join(TAGS)}"
    attrs, flags = {}, set()
    for word in rest:
        key, eq, val = word.partition("=")
        if eq:
            if key in attrs:
                return None, f"the attribute `{key}` is given twice"
            attrs[key] = val
        else:
            flags.add(word)
    return (lang, tag, value, attrs, flags), None


class _Loose:
    """Reads the lines outside fences and reports code that is not in a fence: a block indented by four spaces,
    and a raw <pre> or <code> block. Neither can carry a tag, so neither can be tested.

    The indented block follows CommonMark. A line is code when it is indented four or more spaces beyond the
    list item it sits in and it does not continue a paragraph. So the text of a list item, however deep, and a
    wrapped line under a paragraph are not code."""

    def __init__(self, doc):
        self.doc, self.problems = doc, []
        self.offsets = []           # where the content of each open list item starts
        self.in_paragraph = self.in_code = self.in_comment = self.quoted = False

    def not_text(self):
        """A fence, or anything else that ends a paragraph, was just read."""
        self.in_paragraph = self.in_code = False

    def line(self, number, raw):
        line = raw.expandtabs(4)
        if self.in_comment or line.strip().startswith("<!--"):
            self.in_comment = "-->" not in line
            self.not_text()
            return
        if not line.strip():
            self.in_paragraph = False
            return
        indent = len(line) - len(line.lstrip(" "))
        text = re.sub(r"`[^`]*`", "", line)
        if re.search(r"<pre\b", text, re.I) or re.match(r"\s*<code\b", text, re.I):
            self.problems.append(f"{self.doc}:{number}: a raw HTML code block cannot be tested; use a fenced block")
        if re.match(r"^\s*(>\s*)+(`{3,}|~{3,})", line):
            self.quoted = not self.quoted       # the fence that opens the quoted block is reported, not its end
            if self.quoted:
                self.problems.append(f"{self.doc}:{number}: a code block inside a block quote cannot be tested; "
                                     "move it out of the quote")
        item = LIST_ITEM.match(line)
        if item and not self.in_code:
            while self.offsets and indent < self.offsets[-1]:
                self.offsets.pop()
            if indent - (self.offsets[-1] if self.offsets else 0) < 4 or self.in_paragraph:
                spaces = len(item.group(3))
                self.offsets.append(indent + len(item.group(2)) + (spaces if 1 <= spaces <= 4 else 1))
                self.in_paragraph = True
                return
        if self.in_paragraph:
            return                              # a wrapped line of the paragraph, whatever its indent
        while self.offsets and indent < self.offsets[-1]:
            self.offsets.pop()
        if indent - (self.offsets[-1] if self.offsets else 0) >= 4:
            if not self.in_code:
                self.problems.append(f"{self.doc}:{number}: a code block indented by four spaces cannot be "
                                     "tested; use a fenced block")
            self.in_code = True
            return
        self.in_code = False
        # A heading or a rule is one line and starts no paragraph; anything else does.
        self.in_paragraph = not re.match(r" {0,3}(#{1,6}( |$)|([-*_] *){3,}$)", line)


def extract(doc: str, text: str, first_line: int = 1, scope: str = ""):
    """The fenced blocks of a document's text, in order, and the problems found while reading it. A block
    tagged `nested` holds a small document of its own: its blocks follow it, in their own scope."""
    blocks, problems = [], []
    lines = text.replace("\r\n", "\n").split("\n")
    loose = _Loose(doc)
    i = 0
    while i < len(lines):
        line = lines[i]
        m = FENCE.match(line)
        if not m or loose.in_comment or (m.group(2)[0] == "`" and "`" in m.group(3)):
            loose.line(first_line + i, line)    # also inline code that starts a line with three backticks
            i += 1
            continue
        indent, marks, info = m.group(1), m.group(2), m.group(3).strip()
        loose.not_text()
        opened, body = i, []
        i += 1
        closing = re.compile(rf"^ *{re.escape(marks[0])}{{{len(marks)},}}\s*$")
        while i < len(lines) and not closing.match(lines[i]):
            raw = lines[i]
            body.append(raw[len(indent):] if raw[:len(indent)].strip() == "" else raw.lstrip(" "))
            i += 1
        where = f"{doc}:{first_line + opened}"
        if i >= len(lines):
            problems.append(f"{where}: the code block is never closed")
            break
        i += 1
        parsed, error = parse_info(info)
        if error:
            problems.append(f"{where}: {error}")
            continue
        lang, tag, value, attrs, flags = parsed
        block = Block(doc=doc, line=first_line + opened, lang=lang, tag=tag, value=value, attrs=attrs, flags=flags,
                      body="\n".join(body), scope=scope)
        if tag == "nested":
            if lang != "markdown" or value or attrs or flags:
                problems.append(f"{where}: a nested block is written `markdown nested`, with nothing after it")
                continue
            inner, inner_problems = extract(doc, block.body, first_line + opened + 1, scope=f"{scope}/{block.line}")
            if not inner and not inner_problems:
                problems.append(f"{where}: the nested block holds no code block")
            blocks += inner
            problems += inner_problems
        else:
            blocks.append(block)
    for block, following in zip(blocks, blocks[1:]):
        block.expect_follows = following.tag == "expect" and following.scope == block.scope
    # Problems come out in the order of their lines, whichever reader found them.
    problems = sorted(problems + loose.problems, key=lambda p: int(p[len(doc) + 1:].split(":", 1)[0]))
    return blocks, problems
