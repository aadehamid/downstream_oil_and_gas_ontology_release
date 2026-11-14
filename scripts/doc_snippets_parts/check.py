"""What each tag means, and the count of what was done."""
from __future__ import annotations

import difflib
import os
import re
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .extract import Block, documents, extract
from .match import has_fixed_text, normalise, output_matches
from .pages import extract_html, html_documents, is_page
from .parsers import PARSERS
from .registry import (NESTED, NESTED_FILE, PARSE_LANGS, PARSED_WHEN_SKIPPED, PLACEHOLDER, REGISTRY, ROOT, RUN_LANGS,
                       SAFE_VALUE, Registry, load_registry, release_digest)
from .run import CopyError, NotSimple, Runner, command_lines, family, split_command, starts_launcher
from .static import chain_order, usage_problem

OUTPUT_TAIL = 40
NESTED_NOTE = "this check was started by a block of another check, so it ran no block"
REFRESH = "python scripts/doc_snippets.py describe-release --write"
RELEASE_CHANGED = "not run: the release changed since the documents were written"
RELEASE_NOTE = ("note: the release changed since the documents were written, so this check ran no block. An example may show "
                "a version or a count of the release as it was then. scripts/DOC-SNIPPETS.md says how to bring the examples "
                "up to date (\"The release the examples describe\").")
RELEASE_STRICT = ("the documents' examples describe another release than this one: the registry holds {then} and {file} "
                  "gives {now}. Bring the examples up to date with this release, then run: " + REFRESH)


@dataclass
class Result:
    failures: list = field(default_factory=list)
    ran: int = 0
    status_only: int = 0        # of the blocks that ran, those whose output nothing compares
    checked: int = 0
    skipped: Counter = field(default_factory=Counter)
    parsed: Counter = field(default_factory=Counter)    # of the checked blocks, the skipped ones that were parsed, by reason
    by_document: dict = field(default_factory=dict)
    failed_blocks: int = 0
    nested: bool = False        # a block of another check started this one, so it ran nothing
    release_changed: bool = False   # the release is not the one the examples describe, so the check ran nothing

    @property
    def total(self) -> int:
        return self.ran + self.checked + sum(self.skipped.values()) + self.failed_blocks

    def summary(self) -> str:
        text = (f"{self.total} blocks: {self.ran} run ({self.status_only} status-only), {self.checked} checked, "
                f"{sum(self.skipped.values())} skipped")
        if self.skipped:
            text += " (" + ", ".join(f"{reason} {n}" for reason, n in sorted(self.skipped.items())) + ")"
        if self.parsed:
            text += (f", {sum(self.parsed.values())} of the checked parsed but not run ("
                     + ", ".join(f"{reason} {n}" for reason, n in sorted(self.parsed.items())) + ")")
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
        self.static = static
        self.static_reason = "not run: static check"
        self.result = Result()
        self.report = report        # called with one line per block, for `check --verbose`
        self.runner = None

    # -- the public entry

    def check(self, docs=None) -> Result:
        if not self._started_by_a_block():
            return self.result
        if not self.result.nested:
            self._release_described()
        docs = documents(self.root) + html_documents(self.root) if not docs else list(docs)
        self.docs = chain_order(self.root, self.registry, docs)
        with tempfile.TemporaryDirectory(prefix="doc-snippets-") as tmp:
            self.runner = Runner(self.root, self.registry, self.environ, Path(tmp).resolve())
            try:
                for doc in self.docs:
                    self._check_document(doc)
            finally:
                for problem in self.runner.close():
                    self._fail(None, problem)
        return self.result

    def _started_by_a_block(self) -> bool:
        """Reads the two variables a running check hands its blocks (registry.NESTED). With both, and the file
        holding the same value, this check runs no block. With the variable and no such file, nothing started
        this check, and it stops: a variable alone must never turn the check off."""
        value = self.environ.get(NESTED)
        if not value:
            return True
        try:
            proof = Path(self.environ.get(NESTED_FILE) or os.devnull).read_text(encoding="utf-8")
        except OSError:
            proof = ""
        if proof != value:
            self._fail(None, f"the variable {NESTED} is set, but no running check started this one. Unset it and "
                             "run the check again: it runs nothing only when a block of another check starts it")
            return False
        self.static, self.result.nested = True, True
        self.static_reason = "not run: a check started by a block runs no block"
        return True

    def _release_described(self):
        """Compares the release with the one the registry says the examples describe (registry.release_digest).
        On another release the check runs no block, because an example may rightly differ there. With `strict`,
        which the release's builder uses, it fails instead and still runs the blocks, so the builder sees each
        example that needs a change."""
        now = release_digest(self.root, self.registry)
        if now is None or now == self.registry.sha256:
            return
        if self.strict:
            self._fail(None, RELEASE_STRICT.format(then=self.registry.sha256, file=self.registry.describes, now=now))
            return
        self.static, self.result.release_changed = True, True
        self.static_reason = RELEASE_CHANGED

    def _check_document(self, doc: str):
        path = self.root / doc
        if not path.is_file():
            self._fail(None, f"{doc}: no such document")
            return
        read = extract_html if is_page(doc) else extract
        blocks, problems = read(doc, path.read_text(encoding="utf-8"))
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
            name = state if isinstance(state, str) else f"{'checked: parsed, not run' if state[0] == 'parsed' else 'skipped'}: {state[1]}"
            tag = f"{block.tag}={block.value}" if block.value else block.tag
            self.report(f"{block.where}: {block.lang} {tag}: {name} ({time.monotonic() - started:.1f} s)")
        if isinstance(state, tuple) and state[0] == "parsed":
            self.result.checked += 1
            self.result.parsed[state[1]] += 1
        elif state == "ran":
            self.result.ran += 1
            self.result.status_only += block.tag == "run" and "status-only" in block.flags
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
        if block.lang in PARSED_WHEN_SKIPPED:
            # Nothing runs the block, so at least its text is read: a typing error in it fails.
            try:
                PARSERS[block.lang](block.body, {})
            except ImportError:
                return ("skipped", code), ""    # a `parse` block names the missing parser; a skipped one stays skipped
            except Exception as e:
                return self._fail(block, f"the skipped block is not valid {block.lang}. A skipped block in a language "
                                         "the check can parse is still parsed", f"{type(e).__name__}: {e}")
            return ("parsed", code), ""
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

    def _tag_usage(self, block, previous):
        error = self._only(block) or usage_problem(self.root, block.value, block.body)
        return self._fail(block, error) if error else ("checked", "")

    # -- parse

    def _tag_parse(self, block, previous):
        error = self._only(block, attrs={"sql": ("dialect",), "turtle": ("rdf",), "sparql": ("rdf",)}.get(block.lang, ()))
        if error:
            return self._fail(block, error)
        if block.lang not in PARSE_LANGS:
            return self._fail(block, f"`{block.lang}` cannot be parsed: `parse` reads {', '.join(PARSE_LANGS)}. "
                                     "A command is tagged `run` or `skip`")
        try:
            PARSERS[block.lang](block.body, block.attrs)
        except ImportError as e:
            return self._fail(block, f"the parser for {block.lang} is not installed ({e.name}): run the check through "
                                     "`uv run --no-project --with rdflib --with pyyaml --with sqlglot --with pyoxigraph`")
        except Exception as e:  # each parser raises its own error type; any of them means the block is wrong
            return self._fail(block, f"the block is not valid {block.lang}", f"{type(e).__name__}: {e}")
        return "checked", ""


    def _tag_expect(self, block, previous):
        error = self._only(block)
        if error or block.value:
            return self._fail(block, error or "an expect block takes no value")
        if not previous or previous[0].tag not in ("run", "skip"):
            return self._fail(block, "an expect block must come right after the `run` or `skip` block whose output it shows")
        if not has_fixed_text(block.body):
            return self._fail(block, "the expect block holds no text of its own, so it would match any output. Give "
                                     "it at least one line with words that the output must hold")
        _, state, output = previous
        if state == "failed":
            return self._fail(block, "not compared: the block before it failed")
        if state != "ran":
            return (("skipped", state[1]) if isinstance(state, tuple) else state), ""
        if not output_matches(block.body, output):
            got, want = normalise(output), normalise(block.body)
            diff = list(difflib.unified_diff(want, got, "expected", "output", lineterm="", n=2))[:60]
            return self._fail(block, f"the output of the block at line {previous[0].line} is not what this block shows",
                              "\n".join(diff))
        return "checked", ""

    # -- run

    def _tag_run(self, block, previous):
        error = self._only(block, attrs=("exit", "os", "types"), flags=("define", "status-only"))
        if error:
            return self._fail(block, error)
        if not block.value:
            return self._fail(block, "a run block names its context: `run=<context>` "
                                     f"(one of {', '.join(sorted(self.registry.contexts))})")
        if block.expect_follows and "status-only" in block.flags:
            return self._fail(block, "the block says `status-only`, but an expect block follows it. Keep one")
        if not block.expect_follows and "status-only" not in block.flags:
            return self._fail(block, "nothing checks what this block prints. Put an `expect` block right after it, "
                                     "or add `status-only` to say that only its exit status counts")
        if "," in block.value:
            return self._run_in_each(block, previous)
        context = self.registry.contexts.get(block.value)
        if context is None:
            return self._fail(block, f"no context named `{block.value}` in {REGISTRY.name}: "
                                     f"use one of {', '.join(sorted(self.registry.contexts))}")
        if block.lang not in RUN_LANGS and block.lang not in context.runs:
            return self._fail(block, f"a `{block.lang}` block cannot run in the context `{context.name}`: `run` takes "
                                     f"{', '.join(RUN_LANGS)}, and a language the context names a program for")
        if block.lang != "python" and starts_launcher(block.body):
            return self._fail(block, "the block starts Python with `py`. Write `python`: a Python from a virtual "
                                     "environment has no `py` launcher, so the command would not start there")
        wanted_os = block.attrs.get("os")
        if wanted_os not in (None, "windows", "posix"):
            return self._fail(block, "os= is `windows` or `posix`")
        if not re.fullmatch(r"\d{1,3}", block.attrs.get("exit", "0")):
            return self._fail(block, "exit= is the exit status the command must end with, a number")
        values, error = self._placeholder_values(block, context)
        if error:
            return self._fail(block, error)
        answers = [answer.strip() for answer in block.attrs.get("types", "").split(",")] if "types" in block.attrs else []
        if "types" in block.attrs and not all(answers):
            return self._fail(block, "types= holds what the reader types at each prompt, with commas between the answers")
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
        if context.owner and block.doc != context.owner and context.owner not in self.docs:
            # The chain is the owner's: without its blocks there is nothing to go on from.
            if self.all_contexts:
                return self._fail(block, f"the context `{context.name}` goes on from {context.owner}: check that "
                                         "document in the same run")
            return ("skipped", f"context {context.name} goes on from {context.owner}, which this check did not read"), ""
        try:
            instance = self.runner.instance(block, context)
        except CopyError as e:
            return self._fail(block, str(e))
        if instance.failed_at:
            return self._fail(block, f"not run: the block at line {instance.failed_at} of the same context failed")
        problem = self.runner.fixture_up(instance)
        if problem:
            instance.failed_at = str(block.line)
            return self._fail(block, f"the fixture of the context `{context.name}` could not be made", problem)
        for name in [n for n, value in values.items() if value is None]:
            values[name] = str(instance.values.get(name, ""))
            if not SAFE_VALUE.fullmatch(values[name]):
                return self._fail(block, f"the fixture of the context `{context.name}` gave the placeholder <{name}> "
                                         "no value, or one with a character that is not allowed")
        body = self._fill(block.body, values)
        instance.count += 1
        status, output, problem = self.runner.execute(block, instance, body, wanted_os, "".join(a + "\n" for a in answers) or None)
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
            instance.defines.setdefault(family(block.lang), []).append(body)
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

    def _placeholder_values(self, block, context):
        """The value of each placeholder in the block, or an error. A value comes from the context: text, or
        `env:NAME` for a variable of the environment."""
        values = {}
        for name in dict.fromkeys(PLACEHOLDER.findall(block.body)):
            source = context.placeholders.get(name)
            if source is None:
                return None, (f"the placeholder <{name}> has no value in the context `{context.name}`. Give it one "
                              f"in {REGISTRY.name}, or tag the block `skip`")
            if source == "fixture":         # the context's fixture gives the value when it is made
                values[name] = None
                continue
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
