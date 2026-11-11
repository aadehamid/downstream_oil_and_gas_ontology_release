"""The registry: the contexts a block may run in and the reasons a block may be skipped for."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "scripts" / "doc_snippets.toml"

TAGS = ("run", "expect", "skip", "file", "excerpt", "parse", "nested")
RUN_LANGS = ("bash", "sh", "python", "powershell", "cmd")
PARSE_LANGS = ("json", "toml", "yaml", "turtle", "sparql", "sql", "cypher")
# A value the reader must fill in, such as <your workspace>.
PLACEHOLDER = re.compile(r"<([A-Za-z0-9][A-Za-z0-9 _-]*)>")
# A placeholder's value goes into a block's text, so it may hold no character a shell reads as syntax.
SAFE_VALUE = re.compile(r"[A-Za-z0-9._/:@=+,\\-]+")
# A check that a block starts (scripts/check.sh in a copy of the tree) must run no block itself, or a guide that
# runs the check would start the check again without end. The running check hands its blocks a random value in
# NESTED and, in NESTED_FILE, the path of a file in its temporary folder that holds the same value. A check that
# finds both, and finds them equal, was started by a block and runs nothing. The variable alone proves nothing:
# a check that finds it without the file refuses to go on, so no leftover variable can turn the check off.
NESTED = "DOC_SNIPPETS_NESTED"
NESTED_FILE = "DOC_SNIPPETS_NESTED_FILE"


class RegistryError(Exception):
    """The registry file is wrong: an unknown key, a context with no base."""


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
    set_env: dict = field(default_factory=dict)  # variables a block gets: text, or env:NAME for another variable's value
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
        extra = set(raw) - {"base", "git", "needs_env", "pass_env", "home", "timeout", "placeholders", "set_env", "about"}
        if extra:
            raise RegistryError(f"{path.name}: context {name} has unknown key {sorted(extra)}")
        if raw.get("base") not in ("empty", "release-copy"):
            raise RegistryError(f"{path.name}: context {name} needs base = \"empty\" or \"release-copy\"")
        if raw.get("home", "temporary") not in ("temporary", "real"):
            raise RegistryError(f"{path.name}: context {name} needs home = \"temporary\" or \"real\"")
        contexts[name] = Context(name=name, base=raw["base"], git=bool(raw.get("git", False)),
                                 needs_env=tuple(raw.get("needs_env", ())), pass_env=tuple(raw.get("pass_env", ())),
                                 home=raw.get("home", "temporary"), timeout=int(raw.get("timeout", 120)),
                                 placeholders=dict(raw.get("placeholders", {})), set_env=dict(raw.get("set_env", {})),
                                 about=raw.get("about", ""))
    return Registry(contexts=contexts, reasons=reasons, temporary=temporary)
