"""Reads the local store settings: one TOML file on the machine that runs the loads.

The file names the local Fuseki, the local Neo4j, the Neo4j Enterprise server, the Databricks CLI profile and the
folders the runner writes to. It also holds the two Neo4j passwords, so it stays outside the release folder: load
refuses a file inside it, and refuses a run folder, an output folder or a Fuseki data folder inside it. Paths are
compared without regard to case, as Windows compares them.

The file's path comes from --stores, or from the environment variable KPI_STORE_LOCAL. kpi_store/stores.example.toml
is the example to copy. A password is held as a Secret, whose text form is ***, so no message can print it.
"""
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ENV_VAR = "KPI_STORE_LOCAL"
ROOT = Path(__file__).resolve().parents[1]   # the release folder this code sits in
SYSTEM_DATABASE = "system"

# Every table and key the file may hold. A key that is not listed is an error: a key spelled wrong must not be
# read as a key left out. Each table is optional; a step that needs a missing table stops and names it.
LAYOUT = {
    "release": {"settings": str, "run_folder": str},
    "databricks": {"profile": str, "workspace_folder": str, "cli": str, "timeout_minutes": int},
    "fuseki": {"jar": str, "url": str, "data_folder": str, "java": str},
    "neo4j": {"local": {"uri": str, "username": str, "password": str, "password_env": str, "database": str,
                        "plugins_folder": str},
              "enterprise": {"uri": str, "username": str, "password": str, "password_env": str, "database": str}},
    "projection": {"robot_jar": str, "out": str},
    "tools": {"bash": str},
}
OPTIONAL = {("databricks", "cli"), ("databricks", "timeout_minutes"), ("fuseki", "data_folder"), ("fuseki", "java"),
            ("neo4j.local", "password"), ("neo4j.local", "password_env"), ("neo4j.local", "plugins_folder"),
            ("neo4j.enterprise", "password"), ("neo4j.enterprise", "password_env"), ("tools", "bash")}


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
    uri: str
    username: str
    password: Secret
    database: str
    plugins_folder: Path | None = None


@dataclass(frozen=True)
class Fuseki:
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
        return urlsplit(self.url).hostname in ("127.0.0.1", "localhost", "::1")


@dataclass(frozen=True)
class Databricks:
    profile: str
    workspace_folder: str     # the workspace folder the notebook is imported into
    cli: Path | None
    timeout_minutes: int


@dataclass(frozen=True)
class LocalSettings:
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
    for key, value in doc.items():
        name = f"{where}{key}"
        if key not in layout:
            raise LocalSettingsError(f"unknown {'key' if where else 'table'} {name!r}")
        kind = layout[key]
        if isinstance(kind, dict):
            if not isinstance(value, dict):
                raise LocalSettingsError(f"[{name}] must be a table")
            _check_layout(value, kind, name + ".")
        elif type(value) is not kind:
            raise LocalSettingsError(f"{name} must be {'a whole number' if kind is int else 'text'}")


def _required(doc, table, keys):
    for key in keys:
        if (table, key) not in OPTIONAL and key not in doc:
            raise LocalSettingsError(f"[{table}] lacks {key!r}")


def _neo4j(doc, table, environ, base):
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
    if "@" in urlsplit(doc["uri"]).netloc:
        raise LocalSettingsError(f"[{table}] uri must not hold a user name or a password")
    database = doc["database"].strip()
    if not database or database.lower() == SYSTEM_DATABASE:
        raise LocalSettingsError(f"[{table}] database must name a database, and never the system database")
    plugins = doc.get("plugins_folder")
    return Neo4j(doc["uri"], doc["username"], Secret(text), database, _path(plugins, base) if plugins else None)


def _path(value, base):
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
    if fuseki is not None:
        _required(fuseki, "fuseki", LAYOUT["fuseki"])
        parts = urlsplit(fuseki["url"])
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.path.count("/") != 1 \
                or len(parts.path) < 2 or parts.query or parts.username:
            raise LocalSettingsError("[fuseki] url must be a dataset URL such as http://127.0.0.1:3030/ds")
    if projection is not None:
        _required(projection, "projection", LAYOUT["projection"])
    neo4j = doc.get("neo4j", {})
    found = LocalSettings(
        path=path,
        settings=_path(release["settings"], base) if release else None,
        run_folder=_path(release["run_folder"], base) if release else None,
        databricks=Databricks(bricks["profile"].strip(), bricks["workspace_folder"],
                              _path(bricks["cli"], base) if bricks.get("cli") else None,
                              bricks.get("timeout_minutes", 60)) if bricks else None,
        fuseki=Fuseki(_path(fuseki["jar"], base), fuseki["url"].rstrip("/"),
                      _path(fuseki["data_folder"], base) if fuseki.get("data_folder") else None,
                      _path(fuseki["java"], base) if fuseki.get("java") else None) if fuseki else None,
        neo4j_local=_neo4j(neo4j["local"], "neo4j.local", environ, base) if "local" in neo4j else None,
        neo4j_enterprise=_neo4j(neo4j["enterprise"], "neo4j.enterprise", environ, base) if "enterprise" in neo4j else None,
        robot_jar=_path(projection["robot_jar"], base) if projection else None,
        projection_out=_path(projection["out"], base) if projection else None,
        bash=_path(doc["tools"]["bash"], base) if doc.get("tools", {}).get("bash") else None)
    # What the runner writes must stay out of the folder it zips and uploads.
    for name, value in (("[release] settings", found.settings), ("[release] run_folder", found.run_folder),
                        ("[projection] out", found.projection_out),
                        ("[fuseki] data_folder", found.fuseki.data_folder if found.fuseki else None)):
        if value is not None and is_inside(value, release_root):
            raise LocalSettingsError(f"{name} is inside the release folder; name a folder outside it")
    return found


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
