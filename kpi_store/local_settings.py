"""Reads the local store settings: one TOML file on the machine that runs the loads.

The file names the local Fuseki, the local Neo4j, the Neo4j Enterprise server, the Databricks CLI profile and the
folders the runner writes to. It also holds the two Neo4j passwords, so it stays outside the release folder: load
refuses a file inside it, and refuses a run folder, an output folder or a Fuseki data folder inside it. Paths are
compared without regard to case, as Windows compares them.

The file's path comes from --stores, or from the environment variable KPI_STORE_LOCAL. kpi_store/stores.example.toml
is the example to copy. A password is held as a Secret, whose text form is ***, so no message can print it.

Six commands read this file first: the runner, the setup check, the Fuseki and Neo4j loads, the copy to
Enterprise and the sync check. The cut tool and the questions do not read it. It is not the same file as
kpi_store.toml, which describes the Databricks environment, travels to the volume and holds no password
(kpi_store.settings). No command copies or uploads this file. This module only reads: it opens no connection
and writes nothing.

Each table of the file is optional, so a machine that runs only one command needs only that command's tables. A
command asks for a part with LocalSettings.need, which stops with the name of the missing table.

The [ai] table names the AI provider that the propose command may ask for suggestions (KPI-DEC-0002, Q16 to Q18), and
records the client's IT approval of it. It holds no key: an API key stays in an environment variable that the table
names, and a Databricks token comes from a Databricks configuration profile. kpi_store/ai/providers.py makes the call.
"""
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ENV_VAR = "KPI_STORE_LOCAL"   # names the settings file when --stores is not given
ROOT = Path(__file__).resolve().parents[1]   # the release folder this code sits in
SYSTEM_DATABASE = "system"   # Neo4j's own database of databases and users; never a place to load into

# Every table and key the file may hold. A key that is not listed is an error: a key spelled wrong must not be
# read as a key left out. Each table is optional; a step that needs a missing table stops and names it.
LAYOUT = {
    "release": {"settings": str, "run_folder": str},
    "databricks": {"profile": str, "workspace_folder": str, "cli": str, "timeout_minutes": int, "environment_version": str},
    "fuseki": {"jar": str, "url": str, "data_folder": str, "java": str},
    "neo4j": {"local": {"uri": str, "username": str, "password": str, "password_env": str, "database": str,
                        "plugins_folder": str},
              "enterprise": {"uri": str, "username": str, "password": str, "password_env": str, "database": str}},
    "projection": {"robot_jar": str, "out": str},
    "tools": {"bash": str},
    "ai": {"provider": str, "model": str, "url": str, "key_env": str, "profile": str, "assistant": str,
           "approved_by": str, "approved_on": str, "timeout_seconds": int},
}
AI_PROVIDERS = ("off", "databricks", "anthropic", "openai", "by-hand")
# The keys a table may leave out. Every other key of a table that is present is required.
# The serverless environment version the notebook run asks for when the settings name none. Version 2 has Python
# 3.11, and the rehearsal workspace gave it to the test runs, which named none (measured on 2026-11-14). A workspace's own default can be older: the first real run
# got Python 3.10 that way, and the first cut's notebook failed there.
ENVIRONMENT_VERSION = "2"
OPTIONAL = {("databricks", "cli"), ("databricks", "timeout_minutes"), ("databricks", "environment_version"), ("fuseki", "data_folder"), ("fuseki", "java"),
            ("neo4j.local", "password"), ("neo4j.local", "password_env"), ("neo4j.local", "plugins_folder"),
            ("neo4j.enterprise", "password"), ("neo4j.enterprise", "password_env"), ("tools", "bash")} | \
    {("ai", key) for key in LAYOUT["ai"] if key != "provider"}


class LocalSettingsError(Exception):
    """The local settings file is missing, wrong or inside the release folder. Nothing was read from a store."""


class Secret:
    """A password. str() and repr() give ***; only reveal() gives the text, for the driver."""

    def __init__(self, text):
        self._text = text

    def reveal(self):
        return self._text

    def __repr__(self):
        return "***"

    __str__ = __repr__


@dataclass(frozen=True)
class Neo4j:
    """One Neo4j server and the one database a command may use there: [neo4j.local] or [neo4j.enterprise]."""
    uri: str
    username: str
    password: Secret
    database: str
    plugins_folder: Path | None = None


@dataclass(frozen=True)
class Fuseki:
    """The local Fuseki, from [fuseki]. The properties give the URLs of one dataset's endpoints."""
    jar: Path
    url: str                  # the dataset's URL, such as http://127.0.0.1:3030/ds
    data_folder: Path | None  # a TDB2 folder that keeps the dataset across restarts; None keeps it in memory
    java: Path | None

    @property
    def query_url(self):
        return self.url + "/query"

    @property
    def data_url(self):
        return self.url + "/data"

    @property
    def update_url(self):
        return self.url + "/update"

    @property
    def ping_url(self):
        """The server's own "are you up" address, which is not under the dataset."""
        parts = urlsplit(self.url)
        return f"{parts.scheme}://{parts.netloc}/$/ping"

    @property
    def port(self):
        return urlsplit(self.url).port or 80

    @property
    def dataset(self):
        return urlsplit(self.url).path

    @property
    def is_local(self):
        """True when the URL names this machine. The Fuseki load starts a server itself only then."""
        return urlsplit(self.url).hostname in ("127.0.0.1", "localhost", "::1")


@dataclass(frozen=True)
class Databricks:
    """How this machine reaches Databricks, from [databricks]: the name of a CLI profile. No secret is kept here."""
    profile: str
    workspace_folder: str     # the workspace folder the notebook is imported into
    cli: Path | None          # the CLI's path when it is not on PATH
    timeout_minutes: int      # how long the runner waits for the notebook run; 60 when not set
    environment_version: str  # the serverless environment version of the notebook run; "" leaves it to the workspace


@dataclass(frozen=True)
class AI:
    """The AI provider, from [ai]. No key is kept here: key_env names the environment variable that holds it."""
    provider: str             # one of AI_PROVIDERS; "off" when the table is missing
    model: str = ""           # databricks: the serving endpoint's name; anthropic and openai: the model's name
    url: str = ""             # the address of the call, when it is not the provider's usual one
    key_env: str = ""         # the environment variable that holds the API key or the Databricks token
    profile: str = ""         # databricks: the Databricks configuration profile that gives the host and the token
    assistant: str = ""       # by-hand: the assistant the person gives the prompt to, such as Genie Code
    approved_by: str = ""     # who approved the provider for the client's IT
    approved_on: str = ""     # the date of that approval, YYYY-MM-DD
    timeout_seconds: int = 120


AI_OFF = AI("off")


@dataclass(frozen=True)
class LocalSettings:
    """The whole file. A part is None when its table is missing; ask for a part a step needs with need()."""
    path: Path
    settings: Path | None     # this environment's kpi_store.toml, on this machine
    run_folder: Path | None
    databricks: Databricks | None
    fuseki: Fuseki | None
    neo4j_local: Neo4j | None
    neo4j_enterprise: Neo4j | None
    robot_jar: Path | None
    projection_out: Path | None
    bash: Path | None
    ai: AI = AI_OFF

    def need(self, name):
        """The value of one part, or LocalSettingsError naming the table a step cannot run without."""
        value = getattr(self, name)
        if value is None:
            table = {"settings": "[release]", "run_folder": "[release]", "neo4j_local": "[neo4j.local]",
                     "neo4j_enterprise": "[neo4j.enterprise]", "robot_jar": "[projection]",
                     "projection_out": "[projection]"}.get(name, f"[{name}]")
            raise LocalSettingsError(f"the local settings file lacks {table}, which this step needs")
        return value


def is_inside(path, folder):
    """True when path is the folder or lies under it. Both are resolved, and case is ignored, as on Windows."""
    one = [p.casefold() for p in Path(path).expanduser().resolve().parts]
    two = [p.casefold() for p in Path(folder).expanduser().resolve().parts]
    return one[:len(two)] == two


def locate(argument=None, environ=None):
    """The settings file's path: the --stores argument, else KPI_STORE_LOCAL. Raises when neither names one."""
    environ = os.environ if environ is None else environ
    value = argument or environ.get(ENV_VAR)
    if not value:
        raise LocalSettingsError(f"name the local settings file with --stores <file>, or set {ENV_VAR}")
    return Path(value).expanduser()


def _check_layout(doc, layout, where=""):
    """Refuses a table or a key that LAYOUT does not list, and a value of the wrong type. type() is compared
    exactly, so true or false is not taken for a whole number."""
    for key, value in doc.items():
        name = f"{where}{key}"
        if key not in layout:
            if where == "ai." and any(word in key.lower() for word in ("key", "token", "secret", "password")):
                raise LocalSettingsError(f"[ai] {key} is not a setting: the file holds no key or token. Put the key in an "
                                         "environment variable, and name the variable with key_env")
            raise LocalSettingsError(f"unknown {'key' if where else 'table'} {name!r}")
        kind = layout[key]
        if isinstance(kind, dict):
            if not isinstance(value, dict):
                raise LocalSettingsError(f"[{name}] must be a table")
            _check_layout(value, kind, name + ".")
        elif type(value) is not kind:
            raise LocalSettingsError(f"{name} must be {'a whole number' if kind is int else 'text'}")


def _required(doc, table, keys):
    """Raises when a table that is present lacks a key that is not in OPTIONAL."""
    for key in keys:
        if (table, key) not in OPTIONAL and key not in doc:
            raise LocalSettingsError(f"[{table}] lacks {key!r}")


def _neo4j(doc, table, environ, base):
    """A Neo4j from one [neo4j.*] table. The password comes from the file or from an environment variable the
    file names, and from exactly one of the two, so it is never unclear which one a connection used."""
    _required(doc, table, LAYOUT["neo4j"][table.split(".")[1]])
    given = [k for k in ("password", "password_env") if doc.get(k)]
    if len(given) != 1:
        raise LocalSettingsError(f"[{table}] needs exactly one of password and password_env")
    if doc.get("password_env"):
        text = environ.get(doc["password_env"])
        if not text:
            raise LocalSettingsError(f"[{table}] password_env names {doc['password_env']}, which is not set")
    else:
        text = doc["password"]
    if not doc["uri"].startswith(("bolt://", "bolt+s://", "bolt+ssc://", "neo4j://", "neo4j+s://", "neo4j+ssc://")):
        raise LocalSettingsError(f"[{table}] uri must be a bolt:// or neo4j:// address")
    # An address is printed in messages and logs; a password inside it would be printed with it.
    if "@" in urlsplit(doc["uri"]).netloc:
        raise LocalSettingsError(f"[{table}] uri must not hold a user name or a password")
    database = doc["database"].strip()
    if not database or database.lower() == SYSTEM_DATABASE:
        raise LocalSettingsError(f"[{table}] database must name a database, and never the system database")
    plugins = doc.get("plugins_folder")
    return Neo4j(doc["uri"], doc["username"], Secret(text), database, _path(plugins, base) if plugins else None)


def _path(value, base):
    """A path of the file: ~ is expanded, and a relative path starts at the folder of the settings file."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def parse(data, path, environ=None, release_root=ROOT):
    """LocalSettings from the file's bytes. path is the file's own path: relative paths in the file start at its
    folder. Raises LocalSettingsError with the first problem found."""
    environ = os.environ if environ is None else environ
    path = Path(path).expanduser()
    if is_inside(path, release_root):
        raise LocalSettingsError("the local settings file is inside the release folder; move it outside, "
                                 "because it holds passwords and the release folder is zipped and uploaded")
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as err:
        # The parser's message can quote a line of the file, and a line can hold a password.
        raise LocalSettingsError(f"the local settings file is not valid TOML ({type(err).__name__})") from None
    _check_layout(doc, LAYOUT)
    base = path.resolve().parent
    release = doc.get("release")
    bricks, fuseki, projection = doc.get("databricks"), doc.get("fuseki"), doc.get("projection")
    if release is not None:
        _required(release, "release", LAYOUT["release"])
    if bricks is not None:
        _required(bricks, "databricks", LAYOUT["databricks"])
        if not bricks["workspace_folder"].startswith("/") or bricks["workspace_folder"].endswith("/"):
            raise LocalSettingsError("[databricks] workspace_folder must start with / and not end with /")
        if not bricks["profile"].strip():
            raise LocalSettingsError("[databricks] profile must name a Databricks CLI profile")
        if bricks.get("timeout_minutes", 60) < 1:
            raise LocalSettingsError("[databricks] timeout_minutes must be 1 or more")
        if not re.fullmatch(r"[1-9][0-9]?|", bricks.get("environment_version", ENVIRONMENT_VERSION).strip()):
            raise LocalSettingsError('[databricks] environment_version must be a number in quotes, such as "2", or "" '
                                     "to leave the choice to the workspace")
    if fuseki is not None:
        _required(fuseki, "fuseki", LAYOUT["fuseki"])
        # The URL must be a server and exactly one dataset name, with nothing after it: the query, data and update
        # URLs are built by adding to it.
        parts = urlsplit(fuseki["url"])
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.path.count("/") != 1 \
                or len(parts.path) < 2 or parts.query or parts.username:
            raise LocalSettingsError("[fuseki] url must be a dataset URL such as http://127.0.0.1:3030/ds")
    if projection is not None:
        _required(projection, "projection", LAYOUT["projection"])
    ai = doc.get("ai")
    if ai is not None:
        _required(ai, "ai", LAYOUT["ai"])
        if ai["provider"] not in AI_PROVIDERS:
            raise LocalSettingsError("[ai] provider must be " + ", ".join(f'"{p}"' for p in AI_PROVIDERS))
        if ai.get("timeout_seconds", 120) < 1:
            raise LocalSettingsError("[ai] timeout_seconds must be 1 or more")
    neo4j = doc.get("neo4j", {})
    found = LocalSettings(
        path=path,
        settings=_path(release["settings"], base) if release else None,
        run_folder=_path(release["run_folder"], base) if release else None,
        databricks=Databricks(bricks["profile"].strip(), bricks["workspace_folder"],
                              _path(bricks["cli"], base) if bricks.get("cli") else None,
                              bricks.get("timeout_minutes", 60),
                              bricks.get("environment_version", ENVIRONMENT_VERSION).strip()) if bricks else None,
        fuseki=Fuseki(_path(fuseki["jar"], base), fuseki["url"].rstrip("/"),
                      _path(fuseki["data_folder"], base) if fuseki.get("data_folder") else None,
                      _path(fuseki["java"], base) if fuseki.get("java") else None) if fuseki else None,
        neo4j_local=_neo4j(neo4j["local"], "neo4j.local", environ, base) if "local" in neo4j else None,
        neo4j_enterprise=_neo4j(neo4j["enterprise"], "neo4j.enterprise", environ, base) if "enterprise" in neo4j else None,
        robot_jar=_path(projection["robot_jar"], base) if projection else None,
        projection_out=_path(projection["out"], base) if projection else None,
        bash=_path(doc["tools"]["bash"], base) if doc.get("tools", {}).get("bash") else None,
        ai=AI(**{k: (v.strip() if isinstance(v, str) else v) for k, v in ai.items()}) if ai else AI_OFF)
    return check_outside(found, release_root)


def check_outside(local, release_root):
    """The settings, after checking that the file itself and every folder the commands write to lie outside the
    release folder, which is zipped and uploaded. Each command calls this with the release folder it was given,
    which need not be the folder this code is in."""
    if is_inside(local.path, release_root):
        raise LocalSettingsError("the local settings file is inside the release folder; move it outside, "
                                 "because it holds passwords and the release folder is zipped and uploaded")
    for name, value in (("[release] settings", local.settings), ("[release] run_folder", local.run_folder),
                        ("[projection] out", local.projection_out),
                        ("[fuseki] data_folder", local.fuseki.data_folder if local.fuseki else None)):
        if value is not None and is_inside(value, release_root):
            raise LocalSettingsError(f"{name} is inside the release folder; name a folder outside it")
    return local


def load(path, environ=None, release_root=ROOT):
    """LocalSettings from the file at path. A file that is missing or cannot be read raises LocalSettingsError."""
    path = Path(path).expanduser()
    if is_inside(path, release_root):   # refused before the file is opened
        raise LocalSettingsError("the local settings file is inside the release folder; move it outside, "
                                 "because it holds passwords and the release folder is zipped and uploaded")
    try:
        data = path.read_bytes()
    except OSError as err:
        raise LocalSettingsError(f"cannot read the local settings file {path}: {type(err).__name__}") from None
    return parse(data, path, environ, release_root)
