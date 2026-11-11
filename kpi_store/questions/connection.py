"""Where the composite database is, read from a settings file or the environment, never from the release.

The settings file is TOML:

    [neo4j]
    uri = "bolt://host:7687"
    user = "..."
    password = "..."
    composite = "<the composite database>"
    governance_alias = "<the governance graph's alias in it>"
    bpa_alias = "<the KPI Store graph's alias in it>"

Each value can also come from the environment, which wins: KPI_STORE_NEO4J_URI, KPI_STORE_NEO4J_USER,
KPI_STORE_NEO4J_PASSWORD, KPI_STORE_NEO4J_COMPOSITE, KPI_STORE_NEO4J_GOVERNANCE_ALIAS and
KPI_STORE_NEO4J_BPA_ALIAS.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import roles as R

KEYS = ("uri", "user", "password", "composite", "governance_alias", "bpa_alias")
RELEASE_ROOT = Path(__file__).resolve().parents[2]


class SettingsError(Exception):
    """The connection settings are missing or wrong."""


@dataclass(frozen=True)
class Connection:
    uri: str
    user: str
    composite: str
    governance_alias: str
    bpa_alias: str
    password: str = field(repr=False)     # kept out of every printed form of the settings

    @property
    def graphs(self) -> dict[str, str]:
        """Each graph's name as `USE graph.byName` takes it: the composite, a dot, the alias."""
        return {R.GOVERNANCE: f"{self.composite}.{self.governance_alias}",
                R.BPA: f"{self.composite}.{self.bpa_alias}"}


def _inside_release(resolved: Path) -> bool:
    chain = [resolved, *resolved.parents]
    root = os.path.normcase(str(RELEASE_ROOT))
    if any(os.path.normcase(str(folder)) == root for folder in chain):
        return True
    # Spelling is not enough: a file system that ignores case, or a link, gives one folder two names.
    for folder in chain:
        try:
            if folder.exists() and os.path.samefile(folder, RELEASE_ROOT):
                return True
        except OSError:
            continue
    return False


def outside_release(path: Path, what: str) -> Path:
    """The path, refused when it is inside the release folder: an environment's own files never ship."""
    resolved = Path(path).expanduser().resolve()
    if _inside_release(resolved):
        raise SettingsError(f"{what} must be outside the release folder {RELEASE_ROOT}")
    return resolved


def read(path: Path | None, environ=None) -> Connection:
    environ = os.environ if environ is None else environ
    values = {}
    if path is not None:
        path = outside_release(path, "the settings file")
        try:
            with path.open("rb") as f:
                values = dict(tomllib.load(f).get("neo4j", {}))
        except FileNotFoundError:
            raise SettingsError(f"no settings file at {path}") from None
        except tomllib.TOMLDecodeError as error:
            raise SettingsError(f"{path} is not valid TOML: {error}") from None
    for key in KEYS:
        if environ.get("KPI_STORE_NEO4J_" + key.upper()):
            values[key] = environ["KPI_STORE_NEO4J_" + key.upper()]
    missing = [key for key in KEYS if not isinstance(values.get(key), str) or not values[key]]
    if missing:
        raise SettingsError("the connection settings lack " + ", ".join(missing)
                            + ": give them in the settings file's [neo4j] table or in KPI_STORE_NEO4J_* variables")
    for key in ("composite", "governance_alias", "bpa_alias"):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", values[key]):
            raise SettingsError(f"{key} is not a database name: {values[key]}")
    return Connection(**{key: values[key] for key in KEYS})
