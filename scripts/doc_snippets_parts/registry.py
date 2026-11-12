"""The registry: the contexts a block may run in, the reasons a block may be skipped for, and the release the
documents' examples describe."""
from __future__ import annotations

import hashlib
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
# An example shows what a command printed on the release as it was when the documents were written: its versions,
# its counts. After a correction or a new version of a module the same command prints something else, and that
# is right. So the registry records which release the examples describe, as the SHA-256 of one file that changes
# with every package version (the catalog of all releases). On any other release the check runs no block.
SHA256 = re.compile(r"[0-9a-f]{64}")
DESCRIBES_LINE = re.compile(r'^(sha256\s*=\s*")[0-9a-f]{64}(")', re.M)


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
    describes: str = ""         # the file whose digest names the release the examples describe; "" compares nothing
    sha256: str = ""            # that file's digest when the examples were last brought up to date


def load_registry(path: Path = REGISTRY) -> Registry:
    with path.open("rb") as f:
        data = tomllib.load(f)
    unknown = set(data) - {"reasons", "temporary_reasons", "contexts", "describes"}
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
    describes = dict(data.get("describes", {}))
    if "describes" in data:
        name, digest = describes.get("file"), describes.get("sha256")
        if set(describes) != {"file", "sha256"} or not isinstance(name, str) or not name or Path(name).is_absolute():
            raise RegistryError(f"{path.name}: [describes] needs file, a path relative to the release's top folder, and sha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise RegistryError(f"{path.name}: [describes] sha256 must be 64 hexadecimal digits in lower case")
    return Registry(contexts=contexts, reasons=reasons, temporary=temporary,
                    describes=describes.get("file", ""), sha256=describes.get("sha256", ""))


def release_digest(root: Path, registry: Registry) -> str | None:
    """The digest of the release in `root`: the SHA-256 of the file the registry names, with CRLF line ends read
    as LF, so a checkout on Windows gives the same value. None when the registry names no file or the folder
    does not hold it: then there is no release to compare, as in a folder a test writes."""
    target = Path(root) / registry.describes if registry.describes else None
    if target is None or not target.is_file():
        return None
    return hashlib.sha256(target.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write_release_digest(path: Path, digest: str) -> bool:
    """Writes the digest into the registry file's [describes] table. Returns False when the file has no such line."""
    text = path.read_text(encoding="utf-8")
    new, count = DESCRIBES_LINE.subn(lambda m: m.group(1) + digest + m.group(2), text)
    if count != 1:
        return False
    if new != text:
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(new)
    return True
