"""A block at work: its folder, its environment and its process.

Nothing runs in the tree. A context is a temporary folder, a block's home folder is temporary unless the context
keeps the real one, and no variable that names the tree reaches a block. Bash blocks run through bash with the
block as the script. PowerShell and cmd blocks are read as plain command lines and run without a shell.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from .extract import no_git_env, tree_entries
from .registry import NESTED, NESTED_FILE, Context

# After a block passes its time limit and is stopped, its output is read for this long at most. A process that
# got away may still hold the pipe open, and the check must not wait for it.
DRAIN_SECONDS = 5
# Python's text encoding settings. A block must not get them from the check's own environment: a reader on
# Windows has neither, so a command that only works with one of them must set it where the reader can see it.
ENCODING_VARIABLES = ("PYTHONUTF8", "PYTHONIOENCODING")
# A context's fixture and the programs that run its blocks find the fixture's own folder through this variable.
FIXTURE_DIR = "DOC_SNIPPETS_FIXTURE_DIR"


class CopyError(Exception):
    """The tree cannot be copied safely: a link in it leads outside it."""


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


# ---------------------------------------------------------------------------------------------------------------
# Processes


def _stop(proc):
    """Stop the process and everything it started."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # Windows has no process group to signal: taskkill /T walks the tree of child processes.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, stdin=subprocess.DEVNULL)
        proc.kill()


def run_process(args, cwd, env, timeout, typed=None):
    """Run one program with no shell. It gets no input, or the text a reader would type at its prompts. Returns
    (exit status, output); a run that passes the time limit is stopped with everything it started, and its status
    is None."""
    env = {k: v for k, v in env.items() if k != "OLDPWD"}
    env["PWD"] = str(cwd)       # the folder the process is in, never the one the check was started from
    kwargs = {"start_new_session": True} if os.name == "posix" else {}
    proc = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.PIPE if typed else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    try:
        out, _ = proc.communicate(typed.encode("utf-8") if typed else None, timeout=timeout)
        return proc.returncode, out.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        _stop(proc)
        try:
            out, _ = proc.communicate(timeout=DRAIN_SECONDS)
        except subprocess.TimeoutExpired:
            proc.stdout.close()
            out = b""
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
                r = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
                if r.returncode == 0 and r.stdout.strip():
                    _uv_dirs[variable] = r.stdout.strip()
    return _uv_dirs


# ---------------------------------------------------------------------------------------------------------------
# Contexts at work


class Instance:
    """One context at work for one document: its folder, where the next block starts, what earlier blocks
    defined, and whether one of them failed."""

    def __init__(self, context: Context, folder: Path):
        self.context = context
        self.root = folder / "work"
        self.home = folder / "home"
        self.private = folder / "private"
        self.fixture = folder / "fixture"       # where the context's fixture keeps what it made, outside the copy
        self.fixture_up = False
        self.values: dict = {}                  # the placeholders the fixture gave a value
        self.fixture_env: dict = {}             # the variables the fixture gives the context's blocks
        self.cwd = self.root
        self.defines: dict = {}
        self.failed_at = ""
        self.count = 0


def family(lang):
    return "bash" if lang in ("bash", "sh") else lang


class Runner:
    """Makes the folder of each context and runs blocks in it, for one check of one tree."""

    def __init__(self, root: Path, registry, environ: dict, tmp: Path):
        self.root, self.registry, self.environ, self.tmp = root, registry, environ, tmp
        self._instances: dict = {}
        self._entries = None
        self._token = None

    def instance(self, block, context) -> Instance:
        """The context's folder for this block's document, made on first use. Raises CopyError."""
        # A context with an owner is one chain for the whole check: a block of another document goes on in the
        # folder the owner's blocks left.
        key = ("", "", context.name) if context.owner else (block.doc, block.scope, context.name)
        if key not in self._instances:
            folder = self.tmp / f"c{len(self._instances)}"
            instance = Instance(context, folder)
            for sub in (instance.root, instance.home, instance.private, instance.fixture):
                sub.mkdir(parents=True)
            if context.base == "release-copy":
                self._copy_release(instance.root)
                if context.git:
                    self._start_git(instance)
            self._instances[key] = instance
        return self._instances[key]

    def _copy_release(self, target: Path):
        """Copy every file of the tree. A link is copied as what it points to, so that a block which writes
        through it changes the copy and not the tree. A link that leads outside the tree is refused."""
        if self._entries is None:
            self._entries = tree_entries(self.root)
        top = self.root.resolve()
        for rel in self._entries:
            source, dest = self.root / rel, target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not source.is_symlink():
                shutil.copy2(source, dest)
                continue
            real = source.resolve()
            if not real.is_relative_to(top):
                raise CopyError(f"the link {rel} leads outside the release, so the release cannot be copied")
            if real.is_dir():
                shutil.copytree(real, dest, symlinks=False, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            elif real.is_file():
                shutil.copy2(real, dest)
            else:
                raise CopyError(f"the link {rel} leads to nothing, so the release cannot be copied")

    def _start_git(self, instance):
        env = self.env(instance)
        for args in (["init", "-q", "-b", "work"], ["config", "user.name", "Document test"],
                     ["config", "user.email", "document-test@example.invalid"], ["config", "commit.gpgsign", "false"],
                     ["add", "-A"], ["commit", "-q", "-m", "The release as received"]):
            subprocess.run(["git", *args], cwd=instance.root, env=env, check=True, capture_output=True)

    def _nested_token(self) -> dict:
        if self._token is None:
            self._token = secrets.token_hex(16)
            (self.tmp / "nested-token").write_text(self._token, encoding="utf-8", newline="\n")
        return {NESTED: self._token, NESTED_FILE: str(self.tmp / "nested-token")}

    def env(self, instance) -> dict:
        """The environment of a block. It holds no variable of another context, no Git variable, no encoding
        setting, and no variable whose value names the tree, so a block finds the tree only if its text says
        where it is. PATH stays: the programs a block starts are found through it."""
        context = instance.context
        keep = set(context.needs_env) | set(context.pass_env)
        # A variable that some context sets for its blocks reaches no block from outside: the reader's own
        # KPI_STORE_LOCAL, for one, must never point a tested command at the reader's real stores.
        gates = {name for c in self.registry.contexts.values() for name in (*c.needs_env, *c.pass_env, *c.set_env)}
        tree = {str(self.root), str(self.root.resolve())}
        env = {k: v for k, v in no_git_env(self.environ).items()
               if (k not in gates or k in keep) and k not in ENCODING_VARIABLES
               and (k.upper() == "PATH" or not any(name in v for name in tree))}
        for name, source in context.set_env.items():
            env[name] = self.environ.get(source[4:], "") if source.startswith("env:") else source
        env.update(_uv_environment())
        env.update(self._nested_token())
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if context.fixture or context.runs:
            env[FIXTURE_DIR] = str(instance.fixture)
        env.update(instance.fixture_env)
        if context.home == "temporary":
            env.update({"HOME": str(instance.home), "USERPROFILE": str(instance.home)})
            for name in [k for k in env if k.startswith("XDG_")]:
                del env[name]
        return env

    def _fixture(self, instance, word):
        """Runs the context's fixture command with `up` or `down`. Returns (exit status, output)."""
        env = self.env(instance)
        try:
            command = resolve_program(split_command(instance.context.fixture) + [word], env.get("PATH"))
        except (NotSimple, FileNotFoundError) as e:
            return 1, f"the fixture command cannot be started ({e})"
        return run_process(command, instance.root, env, instance.context.timeout)

    def fixture_up(self, instance):
        """Makes the context's fixture before its first block. Returns None, or why it could not be made. The
        fixture may leave values.json in its folder: {"placeholders": {name: value}, "env": {name: value}}. The
        variables are for a value the registry must not hold, such as the test server's password."""
        if instance.fixture_up or not instance.context.fixture:
            return None
        status, output = self._fixture(instance, "up")
        if status != 0:
            self._fixture(instance, "down")     # whatever a failed `up` left behind is removed; its own result is not read
            return output or "(no output)"
        instance.fixture_up = True
        values = instance.fixture / "values.json"
        if values.is_file():
            given = json.loads(values.read_text(encoding="utf-8"))
            instance.values = dict(given.get("placeholders", {}))
            instance.fixture_env = {str(name): str(value) for name, value in given.get("env", {}).items()}
        return None

    def close(self) -> list:
        """Removes every fixture that was made. Returns one text for each that could not be removed."""
        problems = []
        for instance in self._instances.values():
            if instance.fixture_up:
                status, output = self._fixture(instance, "down")
                instance.fixture_up = False
                if status != 0:
                    problems.append(f"the fixture of the context `{instance.context.name}` could not be removed\n"
                                    + "\n".join("    | " + line for line in (output or "").strip().split("\n")[-20:]))
        return problems

    def execute(self, block, instance, body, wanted_os, typed=None):
        """Runs the block's text. `typed` is what the reader types at the block's prompts, one answer per line.
        Returns (exit status, output, problem): the problem says why the block could not run at all."""
        env, timeout = self.env(instance), instance.context.timeout
        script = instance.private / f"block-{instance.count}"
        prelude = "\n".join(instance.defines.get(family(block.lang), []))
        if block.lang in instance.context.runs:
            # The context names the program that runs this language: a statement for a store, for one. The
            # program gets the block's text as a file, and its output and exit status are the block's.
            script = script.with_suffix("." + block.lang)
            script.write_text(body + "\n", encoding="utf-8", newline="\n")
            try:
                command = resolve_program(split_command(instance.context.runs[block.lang]) + [str(script)], env.get("PATH"))
            except (NotSimple, FileNotFoundError) as e:
                return None, None, f"the program that runs a `{block.lang}` block in this context cannot be started ({e})"
            status, output = run_process(command, instance.cwd, env, timeout, typed)
            return status, output, None
        if family(block.lang) == "bash":
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
            status, output = run_process([bash, str(script)], instance.cwd, env, timeout, typed)
            if state.is_file() and status is not None:
                left = Path(state.read_text(encoding="utf-8").strip())
                if left.is_dir():
                    instance.cwd = left
            return status, output, None
        if block.lang == "python":
            script = script.with_suffix(".py")
            script.write_text(f"{prelude}\n{body}\n", encoding="utf-8", newline="\n")
            status, output = run_process([sys.executable, "-B", str(script)], instance.cwd, env, timeout, typed)
            return status, output, None
        if wanted_os == "windows":
            return self._execute_windows_shell(block, instance, script, prelude, body, env, timeout, typed)
        return self._execute_lines(block, instance, prelude + "\n" + body, env, timeout, typed)

    @staticmethod
    def _execute_lines(block, instance, text, env, timeout, typed=None):
        """PowerShell or cmd lines, each run as a program with its arguments. `cd` moves the next line's folder.
        Typed answers go to the last line's program: the lines before it prepare, and the last one asks."""
        lines = command_lines(block.lang, text)
        output = []
        for position, (_, line) in enumerate(lines, 1):
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
            status, text_out = run_process(command, instance.cwd, env, timeout, typed if position == len(lines) else None)
            output.append(text_out)
            if status != 0:
                return status, "".join(output), None
        return 0, "".join(output), None

    @staticmethod
    def _execute_windows_shell(block, instance, script, prelude, body, env, timeout, typed=None):
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
        status, output = run_process(command, instance.cwd, env, timeout, typed)
        return status, output, None
