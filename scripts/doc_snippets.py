#!/usr/bin/env python3
"""Test every code block in the Markdown documents.

    python3 scripts/doc_snippets.py check [DOC ...]    run or check every block; exit 1 on any failure
    python3 scripts/doc_snippets.py list [DOC ...]     count the blocks of each document by tag
    python3 scripts/doc_snippets.py contexts           the contexts, and which ones can run here
    python3 scripts/doc_snippets.py html               the HTML pages with no Markdown source, and their blocks

A document that shows a command which no longer works misleads its reader. So every fenced code block carries a
tag after its language, and this tool acts on the tag: it runs the block, compares it with a file or with the
output of the block before it, parses it, or counts it as skipped for a reason from a fixed list. A block with
no tag, an unknown tag or a reason outside the list fails the check. scripts/DOC-SNIPPETS.md is the guide for
writers; scripts/doc_snippets.toml holds the contexts and the reasons.

Nothing runs in the tree. Each context is a temporary folder, and a block's home folder is temporary too, so a
command that writes under ~ cannot reach the real one. Bash blocks run through bash with the block as the
script. PowerShell and cmd blocks are read as plain command lines and run without a shell, with `py` mapped to
this interpreter; a line that needs a real shell must say os=windows. The only text placed into a block is a
placeholder value from the registry, and it must match SAFE_VALUE.

Standard library only, Python 3.11 or later. The parsers for Turtle, SPARQL, YAML and SQL need rdflib, pyyaml
and sqlglot; a `parse` block whose parser is not installed fails with the command that installs it.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# The Cypher check imports the questions' tokenizer from the tree. Python must not leave its cache folder there:
# this tool only reads the tree.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = Path(__file__).resolve().parent / "doc_snippets.toml"

TAGS = ("run", "expect", "skip", "file", "excerpt", "parse", "nested")
RUN_LANGS = ("bash", "sh", "python", "powershell", "cmd")
PARSE_LANGS = ("json", "toml", "yaml", "turtle", "sparql", "sql", "cypher")
# A value the reader must fill in, such as <your workspace>.
PLACEHOLDER = re.compile(r"<([A-Za-z0-9][A-Za-z0-9 _-]*)>")
# A placeholder's value goes into a block's text, so it may hold no character a shell reads as syntax.
SAFE_VALUE = re.compile(r"[A-Za-z0-9._/:@=+,\\-]+")
# Set in every block's environment. A check that a block starts (scripts/check.sh in a copy of the tree) sees it
# and runs no block itself, so a guide that runs the check cannot start the check again without end.
NESTED = "DOC_SNIPPETS_NESTED"
FENCE = re.compile(r"^( *)(`{3,}|~{3,})(.*)$")
SKIP_DIRS = {".git", "__pycache__", ".venv", ".pytest_cache", "node_modules"}
OUTPUT_TAIL = 40


class RegistryError(Exception):
    """The registry file is wrong: an unknown key, a context with no base."""


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

    @property
    def where(self) -> str:
        return f"{self.doc}:{self.line}"


@dataclass
class Context:
    name: str
    base: str                                   # "empty" or "release-copy"
    git: bool = False                           # start the copy as a Git repository with one commit
    needs_env: tuple = ()                       # the context runs only when each of these is set
    pass_env: tuple = ()
    home: str = "temporary"                     # "real" keeps the reader's home, for a signed-in command line
    timeout: int = 120                          # seconds for one block
    placeholders: dict = field(default_factory=dict)
    about: str = ""

    def missing(self, environ) -> list:
        return [name for name in self.needs_env if not environ.get(name)]


@dataclass
class Registry:
    contexts: dict
    reasons: dict
    temporary: tuple


def load_registry(path: Path = REGISTRY) -> Registry:
    with path.open("rb") as f:
        data = tomllib.load(f)
    unknown = set(data) - {"reasons", "temporary_reasons", "contexts"}
    if unknown:
        raise RegistryError(f"{path.name}: unknown key {sorted(unknown)}")
    reasons = dict(data.get("reasons", {}))
    temporary = tuple(data.get("temporary_reasons", ()))
    for name, meaning in reasons.items():
        if not isinstance(meaning, str):    # a key written under [reasons] by mistake, such as temporary_reasons
            raise RegistryError(f"{path.name}: the reason {name} needs a sentence that says what it means")
    for name in temporary:
        if name not in reasons:
            raise RegistryError(f"{path.name}: temporary reason {name} is not a reason")
    contexts = {}
    for name, raw in data.get("contexts", {}).items():
        raw = dict(raw)
        extra = set(raw) - {"base", "git", "needs_env", "pass_env", "home", "timeout", "placeholders", "about"}
        if extra:
            raise RegistryError(f"{path.name}: context {name} has unknown key {sorted(extra)}")
        if raw.get("base") not in ("empty", "release-copy"):
            raise RegistryError(f"{path.name}: context {name} needs base = \"empty\" or \"release-copy\"")
        if raw.get("home", "temporary") not in ("temporary", "real"):
            raise RegistryError(f"{path.name}: context {name} needs home = \"temporary\" or \"real\"")
        contexts[name] = Context(name=name, base=raw["base"], git=bool(raw.get("git", False)),
                                 needs_env=tuple(raw.get("needs_env", ())), pass_env=tuple(raw.get("pass_env", ())),
                                 home=raw.get("home", "temporary"), timeout=int(raw.get("timeout", 120)),
                                 placeholders=dict(raw.get("placeholders", {})), about=raw.get("about", ""))
    return Registry(contexts=contexts, reasons=reasons, temporary=temporary)


# ---------------------------------------------------------------------------------------------------------------
# Reading a document


def tree_files(root: Path) -> list:
    """Every file of the tree, as paths relative to the root. Git names them when the root is a repository
    (tracked files, and new files Git does not ignore); a plain folder, such as an unpacked zip, is walked."""
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, env=_no_git_env(os.environ))
        if top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve():
            out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                                  "--exclude-standard"], capture_output=True, check=True,
                                 env=_no_git_env(os.environ)).stdout.decode("utf-8")
            return sorted(p for p in out.split("\0") if p and (root / p).is_file())
    except FileNotFoundError:
        pass
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        found += [(Path(folder) / f).relative_to(root).as_posix() for f in files]
    return sorted(found)


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


def extract(doc: str, text: str, first_line: int = 1, scope: str = ""):
    """The fenced blocks of a document's text, in order, and the problems found while reading it. A block
    tagged `nested` holds a small document of its own: its blocks follow it, in their own scope."""
    blocks, problems = [], []
    lines = text.replace("\r\n", "\n").split("\n")
    i, quoted = 0, False
    while i < len(lines):
        line = lines[i]
        m = FENCE.match(line)
        if not m:
            if re.match(r"^\s*(>\s*)+(`{3,}|~{3,})", line):
                quoted = not quoted         # the fence that opens the quoted block is reported, not the one that closes it
                if quoted:
                    problems.append(f"{doc}:{first_line + i}: a code block inside a block quote cannot be tested; "
                                    "move it out of the quote")
            i += 1
            continue
        indent, marks, info = m.group(1), m.group(2), m.group(3).strip()
        if marks[0] == "`" and "`" in info:
            i += 1          # inline code at the start of a line, not a fence
            continue
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
    return blocks, problems


# ---------------------------------------------------------------------------------------------------------------
# Comparing output


def normalise(text: str) -> list:
    """The lines of an output or of an `expect` block, as they are compared: line ends as LF, colour codes and
    spaces at a line's end removed, blank lines at the start and the end dropped."""
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _line_pattern(expected: str):
    parts, at = [], 0
    for m in PLACEHOLDER.finditer(expected):
        parts.append(re.escape(expected[at:m.start()]))
        parts.append(".+?")
        at = m.end()
    parts.append(re.escape(expected[at:]))
    return re.compile("".join(parts))


def output_matches(expected: str, actual: str) -> bool:
    """True when the output is what the `expect` block shows. A placeholder such as <run id> stands for any text
    on its line; a line that is only `...` stands for any number of lines, also none."""
    want, got = normalise(expected), normalise(actual)
    patterns = [None if line.strip() == "..." else _line_pattern(line) for line in want]
    # reach[j] is true when the expected lines read so far can end exactly at output line j.
    reach = [True] + [False] * len(got)
    for pattern in patterns:
        if pattern is None:
            first = next((j for j, ok in enumerate(reach) if ok), None)
            reach = [first is not None and j >= first for j in range(len(got) + 1)]
        else:
            reach = [False] + [reach[j] and bool(pattern.fullmatch(got[j])) for j in range(len(got))]
    return reach[len(got)]


# ---------------------------------------------------------------------------------------------------------------
# Command lines without a shell


class NotSimple(Exception):
    """The line needs a real shell: a pipe, a variable, a redirection."""


# Outside quotes these belong to the shell. Inside double quotes PowerShell still reads $ and `, and cmd reads %.
_SHELL_MARKS = set("|&;<>$(){}*?%`^")
_QUOTED_MARKS = set("$`%")


def command_lines(lang: str, body: str) -> list:
    """The command lines of a PowerShell or cmd block, each as (line number in the block, text), with comments
    and blank lines dropped and a continued line joined."""
    joiner = "`" if lang == "powershell" else "^"
    out, pending, start = [], "", 0
    for n, raw in enumerate(body.split("\n"), 1):
        line = raw.strip()
        if not pending:
            if not line or (lang == "powershell" and line.startswith("#")) \
                    or (lang == "cmd" and (line.upper().startswith("REM ") or line.upper() == "REM"
                                           or line.startswith("::"))):
                continue
            start = n
        if line.endswith(joiner):
            pending += line[:-1].rstrip() + " "
            continue
        out.append((start, pending + line))
        pending = ""
    if pending:
        out.append((start, pending.strip()))
    return out


def split_command(line: str) -> list:
    """A plain command line as its arguments. Quotes group words and are removed; a backslash is an ordinary
    character, as in a Windows path. Raises NotSimple for anything a shell would have to interpret."""
    args, current, quote, started = [], [], None, False
    for char in line:
        if quote:
            if char == quote:
                quote = None
            elif quote == '"' and char in _QUOTED_MARKS:
                raise NotSimple(f"`{char}` inside double quotes")
            else:
                current.append(char)
        elif char in "\"'":
            quote, started = char, True
        elif char.isspace():
            if started:
                args.append("".join(current))
                current, started = [], False
        elif char in _SHELL_MARKS:
            raise NotSimple(f"`{char}`")
        else:
            current.append(char)
            started = True
    if quote:
        raise NotSimple("a quote that is never closed")
    if started:
        args.append("".join(current))
    return args


def resolve_program(args: list, path: str | None) -> list:
    """The arguments with the program made runnable here: `py` and `python` are this interpreter (a version
    flag such as -3 is dropped), and any other program is found on the path."""
    name = args[0].lower()
    if name in ("py", "py.exe"):
        rest = args[1:]
        if rest and re.fullmatch(r"-\d(\.\d+)?", rest[0]):
            rest = rest[1:]
        return [sys.executable, "-B"] + rest
    if name in ("python", "python3", "python.exe"):
        return [sys.executable, "-B"] + args[1:]
    found = shutil.which(args[0], path=path)
    if not found:
        raise FileNotFoundError(args[0])
    return [found] + args[1:]


# ---------------------------------------------------------------------------------------------------------------
# Running


def _no_git_env(environ) -> dict:
    return {k: v for k, v in environ.items() if not k.startswith("GIT_")}


def _run(args, cwd, env, timeout):
    """Run one program with no shell and no input. Returns (exit status, output); a run that passes the time
    limit is stopped with everything it started, and its status is None."""
    kwargs = {"start_new_session": True} if os.name == "posix" else {}
    proc = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, **kwargs)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        out, _ = proc.communicate()
        return None, out.decode("utf-8", errors="replace")


_uv_dirs = None


def _uv_environment() -> dict:
    """Where uv keeps its cache and its Python versions. A block gets a temporary home, and uv finds both through
    the home folder, so without these names every `uv run` in a block would download its packages again."""
    global _uv_dirs
    if _uv_dirs is None:
        _uv_dirs = {}
        if shutil.which("uv"):
            for variable, command in (("UV_CACHE_DIR", ["uv", "cache", "dir"]),
                                      ("UV_PYTHON_INSTALL_DIR", ["uv", "python", "dir"])):
                if os.environ.get(variable):
                    continue
                r = subprocess.run(command, capture_output=True, text=True)
                if r.returncode == 0 and r.stdout.strip():
                    _uv_dirs[variable] = r.stdout.strip()
    return _uv_dirs


class Instance:
    """One context at work for one document: its folder, where the next block starts, what earlier blocks
    defined, and whether one of them failed."""

    def __init__(self, context: Context, folder: Path):
        self.context = context
        self.root = folder / "work"
        self.home = folder / "home"
        self.private = folder / "private"
        self.cwd = self.root
        self.defines: dict = {}
        self.failed_at = ""
        self.count = 0


@dataclass
class Result:
    failures: list = field(default_factory=list)
    ran: int = 0
    checked: int = 0
    skipped: Counter = field(default_factory=Counter)
    by_document: dict = field(default_factory=dict)
    failed_blocks: int = 0

    @property
    def total(self) -> int:
        return self.ran + self.checked + sum(self.skipped.values()) + self.failed_blocks

    def summary(self) -> str:
        text = f"{self.total} blocks: {self.ran} run, {self.checked} checked, {sum(self.skipped.values())} skipped"
        if self.skipped:
            text += " (" + ", ".join(f"{reason} {n}" for reason, n in sorted(self.skipped.items())) + ")"
        if self.failed_blocks:
            text += f", {self.failed_blocks} failed"
        return text


class Checker:
    """Checks documents against one tree. `static` reads and compares but starts nothing; `strict` refuses the
    temporary reasons; `all_contexts` fails a block whose context cannot run here instead of counting it."""

    def __init__(self, root: Path = ROOT, registry: Registry | None = None, *, strict=False, all_contexts=False,
                 static=False, environ=None, report=None):
        self.root = Path(root)
        self.registry = registry or load_registry()
        self.strict, self.all_contexts = strict, all_contexts
        self.environ = dict(os.environ if environ is None else environ)
        self.static = static or bool(self.environ.get(NESTED))
        self.static_reason = "not run: a check started by a block runs no block" if self.environ.get(NESTED) \
            else "not run: static check"
        self.result = Result()
        self.report = report        # called with one line per block, for `check --verbose`
        self._instances: dict = {}
        self._files = None
        self._tmp = None

    # -- the public entry

    def check(self, docs=None) -> Result:
        docs = documents(self.root) if not docs else list(docs)
        with tempfile.TemporaryDirectory(prefix="doc-snippets-") as tmp:
            self._tmp = Path(tmp).resolve()
            for doc in docs:
                self._check_document(doc)
        return self.result

    def _check_document(self, doc: str):
        path = self.root / doc
        if not path.is_file():
            self._fail(None, f"{doc}: no such document")
            return
        blocks, problems = extract(doc, path.read_text(encoding="utf-8"))
        tally = self.result.by_document.setdefault(doc, Counter())
        for problem in problems:
            self.result.failures.append(problem)
            self.result.failed_blocks += 1
            tally["(untagged or unreadable)"] += 1
        previous = None             # (block, how it ended, its output) of the block just before, in the same scope
        for block in blocks:
            tally[block.tag] += 1
            if previous and previous[0].scope != block.scope:
                previous = None
            outcome = self._check_block(block, previous)
            previous = (block, *outcome)

    # -- one block

    def _check_block(self, block: Block, previous):
        """Checks one block and returns (how it ended, its output). The first is "ran", "checked", "failed" or
        ("skipped", reason)."""
        handler = getattr(self, f"_tag_{block.tag}")
        started = time.monotonic()
        outcome = handler(block, previous)
        state = outcome[0]
        if self.report:
            name = state if isinstance(state, str) else f"skipped: {state[1]}"
            tag = f"{block.tag}={block.value}" if block.value else block.tag
            self.report(f"{block.where}: {block.lang} {tag}: {name} ({time.monotonic() - started:.1f} s)")
        if state == "ran":
            self.result.ran += 1
        elif state == "checked":
            self.result.checked += 1
        elif state == "failed":
            self.result.failed_blocks += 1
        else:
            self.result.skipped[state[1]] += 1
        return outcome

    def _fail(self, block, message, output=None):
        text = f"{block.where}: {message}" if block else message
        if output is not None:
            tail = normalise(output)[-OUTPUT_TAIL:]
            text += "\n" + "\n".join("    | " + line for line in tail) if tail else "\n    | (no output)"
        self.result.failures.append(text)
        return "failed", ""

    def _only(self, block, attrs=(), flags=()):
        extra = sorted(set(block.attrs) - set(attrs)) + sorted(block.flags - set(flags))
        return f"`{extra[0]}` is not something a `{block.tag}` block takes" if extra else None

    # -- skip

    def _tag_skip(self, block, previous):
        error = self._only(block, attrs=("reason",)) or self._reason_error(block)
        if error:
            return self._fail(block, error)
        code = block.attrs["reason"].partition(":")[0].strip()
        if self.strict and code in self.registry.temporary:
            return self._fail(block, f"the reason `{code}` is temporary and must be gone at the cut")
        return ("skipped", code), ""

    def _reason_error(self, block):
        if block.value:
            return "a skip is written `skip reason=\"<reason>: <detail>\"`"
        reason = block.attrs.get("reason", "")
        code, colon, detail = reason.partition(":")
        if not reason:
            return "a skipped block needs reason=\"<reason>: <detail>\""
        if code.strip() not in self.registry.reasons:
            return f"`{code.strip()}` is not an allowed reason: use one of {', '.join(sorted(self.registry.reasons))}"
        if not colon or len(detail.strip()) < 8:
            return f"the reason `{code.strip()}` needs a detail after a colon, in a few words"
        return None

    # -- file, excerpt

    def _read_target(self, block):
        if block.value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", block.value):
            return None, f"`{block.value}` must be a path relative to the release's top folder"
        target = (self.root / block.value).resolve()
        if not block.value or not target.is_relative_to(self.root.resolve()):
            return None, f"`{block.value}` must be a path inside the release"
        if not target.is_file():
            return None, f"the file {block.value} does not exist"
        return normalise(target.read_text(encoding="utf-8")), None

    def _tag_file(self, block, previous):
        error = self._only(block)
        if error:
            return self._fail(block, error)
        real, error = self._read_target(block)
        if error:
            return self._fail(block, error)
        shown = normalise(block.body)
        if shown != real:
            diff = list(difflib.unified_diff(real, shown, block.value, "the block", lineterm="", n=1))[:30]
            return self._fail(block, f"the block differs from {block.value}", "\n".join(diff))
        return "checked", ""

    def _tag_excerpt(self, block, previous):
        error = self._only(block)
        if error:
            return self._fail(block, error)
        real, error = self._read_target(block)
        if error:
            return self._fail(block, error)
        shown = normalise(block.body)
        if not shown:
            return self._fail(block, "the excerpt is empty")
        if not any(real[i:i + len(shown)] == shown for i in range(len(real) - len(shown) + 1)):
            best = max(real, key=lambda line: difflib.SequenceMatcher(None, line, shown[0]).ratio(), default="")
            return self._fail(block, f"the lines are not in {block.value}, in this order and next to each other",
                              f"the block starts: {shown[0]}\nthe closest line: {best}")
        return "checked", ""

    # -- parse

    def _tag_parse(self, block, previous):
        error = self._only(block, attrs=("dialect",) if block.lang == "sql" else ())
        if error:
            return self._fail(block, error)
        if block.lang not in PARSE_LANGS:
            return self._fail(block, f"`{block.lang}` cannot be parsed: `parse` reads {', '.join(PARSE_LANGS)}. "
                                     "A command is tagged `run` or `skip`")
        try:
            getattr(self, f"_parse_{block.lang}")(block)
        except ImportError as e:
            return self._fail(block, f"the parser for {block.lang} is not installed ({e.name}): run the check through "
                                     "`uv run --no-project --with rdflib --with pyyaml --with sqlglot`")
        except Exception as e:  # each parser raises its own error type; any of them means the block is wrong
            return self._fail(block, f"the block is not valid {block.lang}", f"{type(e).__name__}: {e}")
        return "checked", ""

    @staticmethod
    def _parse_json(block):
        json.loads(block.body)

    @staticmethod
    def _parse_toml(block):
        tomllib.loads(block.body)

    @staticmethod
    def _parse_yaml(block):
        import yaml
        list(yaml.safe_load_all(block.body))

    @staticmethod
    def _parse_turtle(block):
        import rdflib
        # A document often shows a few triples without their prefix lines. Each prefix the block uses and does
        # not declare gets a made-up namespace, so the triples themselves are still read.
        declared = set(re.findall(r"(?im)^\s*@?prefix\s+([\w-]*):", block.body))
        used = set(re.findall(r"(?<![\w<:/#])([A-Za-z][\w-]*):(?!//)", block.body))
        made_up = "".join(f"@prefix {name}: <urn:doc-snippets:{name}#> .\n" for name in sorted(used - declared))
        rdflib.Graph().parse(data=made_up + block.body, format="turtle")

    @staticmethod
    def _parse_sparql(block):
        from rdflib.plugins.sparql import prepareQuery, prepareUpdate
        try:
            prepareQuery(block.body)
        except Exception as query_error:
            try:
                prepareUpdate(block.body)
            except Exception:
                raise query_error from None

    @staticmethod
    def _parse_sql(block):
        import sqlglot
        if not [s for s in sqlglot.parse(block.body, read=block.attrs.get("dialect", "databricks")) if s]:
            raise ValueError("no statement")

    def _parse_cypher(self, block):
        """Cypher has no parser here. The questions' tokenizer reads the text, and this checks what it can: every
        string and name is closed and every bracket has its partner."""
        sys.path.insert(0, str(ROOT))
        try:
            from kpi_store.questions.render import tokens
        finally:
            sys.path.pop(0)
        pairs, stack = {")": "(", "]": "[", "}": "{"}, []
        for kind, text in tokens(block.body):
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
        if not any(kind == "word" for kind, _ in tokens(block.body)):
            raise ValueError("no statement")

    # -- expect

    def _tag_expect(self, block, previous):
        error = self._only(block)
        if error or block.value:
            return self._fail(block, error or "an expect block takes no value")
        if not previous or previous[0].tag not in ("run", "skip"):
            return self._fail(block, "an expect block must come right after the `run` or `skip` block whose output it shows")
        _, state, output = previous
        if state == "failed":
            return self._fail(block, "not compared: the block before it failed")
        if state != "ran":
            return state, ""
        if not output_matches(block.body, output):
            got, want = normalise(output), normalise(block.body)
            diff = list(difflib.unified_diff(want, got, "expected", "output", lineterm="", n=2))[:60]
            return self._fail(block, f"the output of the block at line {previous[0].line} is not what this block shows",
                              "\n".join(diff))
        return "checked", ""

    # -- run

    def _tag_run(self, block, previous):
        error = self._only(block, attrs=("exit", "os"), flags=("define",))
        if error:
            return self._fail(block, error)
        if block.lang not in RUN_LANGS:
            return self._fail(block, f"a `{block.lang}` block cannot run: `run` takes {', '.join(RUN_LANGS)}")
        if not block.value:
            return self._fail(block, "a run block names its context: `run=<context>` "
                                     f"(one of {', '.join(sorted(self.registry.contexts))})")
        if "," in block.value:
            return self._run_in_each(block, previous)
        context = self.registry.contexts.get(block.value)
        if context is None:
            return self._fail(block, f"no context named `{block.value}` in {REGISTRY.name}: "
                                     f"use one of {', '.join(sorted(self.registry.contexts))}")
        wanted_os = block.attrs.get("os")
        if wanted_os not in (None, "windows", "posix"):
            return self._fail(block, "os= is `windows` or `posix`")
        if not re.fullmatch(r"\d{1,3}", block.attrs.get("exit", "0")):
            return self._fail(block, "exit= is the exit status the command must end with, a number")
        values, error = self._placeholder_values(block, context)
        if error:
            return self._fail(block, error)
        if block.lang in ("powershell", "cmd") and wanted_os != "windows":
            # Read the lines now, so a line that needs a shell fails on every machine, also where nothing runs.
            for n, line in command_lines(block.lang, PLACEHOLDER.sub("x", block.body)):
                try:
                    if not split_command(line):
                        raise NotSimple("an empty command")
                except NotSimple as e:
                    return self._fail(block, f"line {block.line + n} is not a plain command line ({e}). Write it "
                                             "without shell syntax, or add os=windows so that it runs in a real "
                                             "shell on Windows only")
        if self.static:
            return ("skipped", self.static_reason), ""
        this_os = "windows" if os.name == "nt" else "posix"
        if wanted_os and wanted_os != this_os:
            return ("skipped", f"{wanted_os}-only"), ""
        missing = context.missing(self.environ)
        if missing:
            if self.all_contexts:
                return self._fail(block, f"the context `{context.name}` cannot run: set {', '.join(missing)}")
            return ("skipped", f"context {context.name} is off (set {', '.join(missing)})"), ""
        instance = self._instance(block, context)
        if instance.failed_at:
            return self._fail(block, f"not run: the block at line {instance.failed_at} of the same context failed")
        body = self._fill(block.body, values)
        instance.count += 1
        status, output, problem = self._execute(block, instance, body, wanted_os)
        if problem:
            instance.failed_at = str(block.line)
            return self._fail(block, problem, output)
        want = int(block.attrs.get("exit", "0"))
        if status != want:
            instance.failed_at = str(block.line)
            ended = "ran past its time limit of " + str(instance.context.timeout) + " seconds" if status is None \
                else f"ended with exit status {status}, not {want}"
            return self._fail(block, f"the block {ended} (context {context.name})", output)
        if "define" in block.flags:
            instance.defines.setdefault(self._family(block.lang), []).append(body)
        return "ran", output

    def _run_in_each(self, block, previous):
        """A `define` block may name several contexts, with commas: it runs in each, so each has what it defines.
        It ends as the worst of its runs: failed, else ran when at least one context ran it, else skipped."""
        if "define" not in block.flags:
            return self._fail(block, "only a `define` block may name more than one context")
        outcomes = []
        for name in block.value.split(","):
            one = Block(**{**block.__dict__, "value": name.strip()})
            outcomes.append(self._tag_run(one, previous))
        states = [state for state, _ in outcomes]
        if "failed" in states:
            return "failed", ""
        return next((o for o in outcomes if o[0] == "ran"), outcomes[0])

    @staticmethod
    def _family(lang):
        return "bash" if lang in ("bash", "sh") else lang

    def _placeholder_values(self, block, context):
        """The value of each placeholder in the block, or an error. A value comes from the context: text, or
        `env:NAME` for a variable of the environment."""
        values = {}
        for name in dict.fromkeys(PLACEHOLDER.findall(block.body)):
            source = context.placeholders.get(name)
            if source is None:
                return None, (f"the placeholder <{name}> has no value in the context `{context.name}`. Give it one "
                              f"in {REGISTRY.name}, or tag the block `skip`")
            if source.startswith("env:"):
                value = self.environ.get(source[4:], "")
                if not value and not context.missing(self.environ) and not self.static:
                    return None, f"the placeholder <{name}> reads the variable {source[4:]}, which is not set"
            else:
                value = source
            if value and not SAFE_VALUE.fullmatch(value):
                return None, f"the value of the placeholder <{name}> holds a character that is not allowed"
            values[name] = value
        return values, None

    @staticmethod
    def _fill(body, values):
        return PLACEHOLDER.sub(lambda m: values.get(m.group(1)) or m.group(0), body)

    def _instance(self, block, context) -> Instance:
        key = (block.doc, block.scope, context.name)
        if key not in self._instances:
            folder = self._tmp / f"c{len(self._instances)}"
            instance = Instance(context, folder)
            for sub in (instance.root, instance.home, instance.private):
                sub.mkdir(parents=True)
            if context.base == "release-copy":
                self._copy_release(instance.root)
                if context.git:
                    self._start_git(instance)
            self._instances[key] = instance
        return self._instances[key]

    def _copy_release(self, target: Path):
        if self._files is None:
            self._files = tree_files(self.root)
        for rel in self._files:
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / rel, dest, follow_symlinks=False)

    def _start_git(self, instance):
        env = self._env(instance)
        for args in (["init", "-q", "-b", "work"], ["config", "user.name", "Document test"],
                     ["config", "user.email", "document-test@example.invalid"], ["config", "commit.gpgsign", "false"],
                     ["add", "-A"], ["commit", "-q", "-m", "The release as received"]):
            subprocess.run(["git", *args], cwd=instance.root, env=env, check=True, capture_output=True)

    def _env(self, instance) -> dict:
        context = instance.context
        keep = set(context.needs_env) | set(context.pass_env)
        gates = {name for c in self.registry.contexts.values() for name in (*c.needs_env, *c.pass_env)}
        env = {k: v for k, v in _no_git_env(self.environ).items() if k not in gates or k in keep}
        env.update(_uv_environment())
        env.update({NESTED: "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
        if context.home == "temporary":
            env.update({"HOME": str(instance.home), "USERPROFILE": str(instance.home)})
            for name in [k for k in env if k.startswith("XDG_")]:
                del env[name]
        return env

    def _execute(self, block, instance, body, wanted_os):
        """Runs the block's text. Returns (exit status, output, problem): the problem says why the block could not
        run at all."""
        env, timeout = self._env(instance), instance.context.timeout
        script = instance.private / f"block-{instance.count}"
        family = self._family(block.lang)
        prelude = "\n".join(instance.defines.get(family, []))
        if family == "bash":
            bash = shutil.which("bash")
            if not bash:
                return None, None, "bash is not installed, so the block cannot run"
            state = instance.private / "cwd"
            state.unlink(missing_ok=True)
            env["DOC_SNIPPETS_CWD_FILE"] = str(state)
            # The reader types the blocks into one terminal, so a later block starts in the folder an earlier
            # one left. The trap records that folder; -W gives a Windows path under Git Bash.
            script.write_text("set -euo pipefail\n"
                              "trap '{ pwd -W 2>/dev/null || pwd -P; } > \"$DOC_SNIPPETS_CWD_FILE\"' EXIT\n"
                              f"{prelude}\n{body}\n", encoding="utf-8", newline="\n")
            status, output = _run([bash, str(script)], instance.cwd, env, timeout)
            if state.is_file() and status is not None:
                left = Path(state.read_text(encoding="utf-8").strip())
                if left.is_dir():
                    instance.cwd = left
            return status, output, None
        if family == "python":
            script = script.with_suffix(".py")
            script.write_text(f"{prelude}\n{body}\n", encoding="utf-8", newline="\n")
            status, output = _run([sys.executable, "-B", str(script)], instance.cwd, env, timeout)
            return status, output, None
        if wanted_os == "windows":
            return self._execute_windows_shell(block, instance, script, prelude, body, env, timeout)
        return self._execute_lines(block, instance, prelude + "\n" + body, env, timeout)

    def _execute_lines(self, block, instance, text, env, timeout):
        """PowerShell or cmd lines, each run as a program with its arguments. `cd` moves the next line's folder."""
        output = []
        for n, line in command_lines(block.lang, text):
            args = split_command(line)
            if args[0].lower() in ("cd", "chdir", "set-location"):
                target = (instance.cwd / args[-1]).resolve() if len(args) > 1 else instance.cwd
                if not target.is_dir():
                    return 1, "".join(output) + f"cd: no folder {args[-1]}\n", None
                instance.cwd = target
                continue
            try:
                command = resolve_program(args, env.get("PATH"))
            except FileNotFoundError:
                return None, "".join(output), f"the program `{args[0]}` is not installed, so the line cannot run"
            status, text_out = _run(command, instance.cwd, env, timeout)
            output.append(text_out)
            if status != 0:
                return status, "".join(output), None
        return 0, "".join(output), None

    @staticmethod
    def _execute_windows_shell(block, instance, script, prelude, body, env, timeout):
        if block.lang == "powershell":
            shell = shutil.which("pwsh") or shutil.which("powershell")
            if not shell:
                return None, None, "PowerShell is not installed, so the block cannot run"
            script = script.with_suffix(".ps1")
            script.write_text(f"$ErrorActionPreference = 'Stop'\n{prelude}\n{body}\nexit $LASTEXITCODE\n",
                              encoding="utf-8-sig", newline="\r\n")
            command = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        else:
            script = script.with_suffix(".bat")
            script.write_text(f"@echo off\r\n{prelude}\r\n{body}\r\n", encoding="utf-8", newline="")
            command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(script)]
        status, output = _run(command, instance.cwd, env, timeout)
        return status, output, None


# ---------------------------------------------------------------------------------------------------------------
# The other commands


def tally(root: Path, docs=None) -> dict:
    """The blocks of each document, counted by tag (a skip by its reason)."""
    out = {}
    for doc in (docs or documents(root)):
        blocks, problems = extract(doc, (root / doc).read_text(encoding="utf-8"))
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
    This tool cannot reach them: a page is counted here so that someone decides how it is tested."""
    files = set(tree_files(root))
    out = []
    for page in sorted(p for p in files if p.lower().endswith((".html", ".htm"))):
        if page.rsplit(".", 1)[0] + ".md" in files:
            continue
        text = (root / page).read_text(encoding="utf-8", errors="replace")
        if 'name="generator"' in text:
            continue
        pre = re.findall(r"<pre\b.*?</pre>", text, re.S | re.I)
        rest = re.sub(r"<pre\b.*?</pre>", "", text, flags=re.S | re.I)
        out.append((page, len(pre), len(re.findall(r"<code\b", rest, re.I))))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Test every code block in the Markdown documents.")
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
    sub.add_parser("html", help="the HTML pages with no Markdown source")
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


if __name__ == "__main__":
    sys.exit(main())
