"""Reads and validates kpi_store.toml, the one settings file of a KPI Store environment.

The file sits in the volume beside the release zip, never inside it. A missing or wrong file raises
SettingsError, and the caller stops before any read or write.
"""
import fnmatch
import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
PATTERN = re.compile(r"^[A-Za-z0-9_*?]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ZIP_NAME = re.compile(r"^[A-Za-z0-9._-]+\.zip$")
SPACE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
SYSTEM_SCHEMAS = ("system.information_schema", "system.access", "system.lakeflow")

# Every table and key the file may hold, with the type of each value. Anything else is an error: a key
# spelled wrong must not be read as a key left out.
LAYOUT = {
    "release": {"zip": str, "sha256": str},
    "databricks": {"write_catalog": str, "write_schema": str, "tech_graph_schema": str, "volume": str,
                   "read_catalogs": list, "warehouse_id": str},
    "names": None,   # free keys: ontology catalog name = environment catalog name
    "skip": {"schemas": list, "tables": list},
    "genie": {"spaces": list},
}
OPTIONAL = {("databricks", "warehouse_id")}


class SettingsError(Exception):
    """The settings file is missing or wrong. Nothing was read or written."""


@dataclass(frozen=True)
class Settings:
    zip_name: str
    zip_sha256: str
    write_catalog: str
    write_schema: str
    tech_graph_schema: str
    volume: str
    read_catalogs: tuple
    warehouse_id: str
    names: dict          # ontology catalog name, lower case, to this environment's catalog name
    skip_schemas: tuple
    skip_tables: tuple
    genie_spaces: tuple
    sha256: str          # of the settings file's bytes, for the report
    folder: Path         # the folder that holds the settings file and the zip

    @property
    def zip_path(self):
        return self.folder / self.zip_name

    @property
    def store_schema(self):
        return f"{self.write_catalog}.{self.write_schema}"

    @property
    def triples_table(self):
        return f"{self.store_schema}.epm_triples"

    @property
    def markers_table(self):
        return f"{self.store_schema}.epm_store_markers"

    @property
    def write_schemas(self):
        """The two schemas the KPI Store may write to, lower case."""
        return (f"{self.write_catalog}.{self.write_schema}".lower(),
                f"{self.write_catalog}.{self.tech_graph_schema}".lower())

    def environment_name(self, full_name):
        """An ontology object's name in this environment: its catalog translated by [names]."""
        catalog, _, rest = full_name.partition(".")
        return f"{self.names.get(catalog.lower(), catalog)}.{rest}"

    def skipped(self, schema, table=None):
        """True when a skip rule covers the schema, or the table when one is given. Case is ignored."""
        if any(fnmatch.fnmatchcase(schema.lower(), p.lower()) for p in self.skip_schemas):
            return True
        return table is not None and any(fnmatch.fnmatchcase(table.lower(), p.lower()) for p in self.skip_tables)


def _strings(where, value, pattern, what, allow_empty=True):
    if not all(isinstance(v, str) for v in value):
        raise SettingsError(f"{where} must be a list of strings")
    for v in value:
        if not pattern.match(v):
            raise SettingsError(f"{where} holds {v!r}, which is not {what}")
    if not allow_empty and not value:
        raise SettingsError(f"{where} must name at least one value")
    if len({v.lower() for v in value}) != len(value):
        raise SettingsError(f"{where} names a value twice")
    return tuple(value)


def parse(data, folder=Path(".")):
    """Settings from the file's bytes. Raises SettingsError with the first problem found."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as err:
        raise SettingsError(f"the settings file is not valid TOML: {err}") from None
    for table in doc:
        if table not in LAYOUT:
            raise SettingsError(f"unknown table [{table}]")
    for table, keys in LAYOUT.items():
        if not isinstance(doc.get(table), dict):
            raise SettingsError(f"table [{table}] is missing")
        if keys is None:
            continue
        for key in doc[table]:
            if key not in keys:
                raise SettingsError(f"unknown key {key!r} in [{table}]")
        for key, kind in keys.items():
            if key not in doc[table]:
                if (table, key) in OPTIONAL:
                    continue
                raise SettingsError(f"[{table}] lacks {key!r}")
            if not isinstance(doc[table][key], kind):
                raise SettingsError(f"[{table}] {key} must be a {'list' if kind is list else 'string'}")
    release, bricks = doc["release"], doc["databricks"]
    if not ZIP_NAME.match(release["zip"]):
        raise SettingsError("[release] zip must be a file name ending in .zip, with no folder")
    if not SHA256.match(release["sha256"]):
        raise SettingsError("[release] sha256 must be 64 lower-case hexadecimal digits")
    for key in ("write_catalog", "write_schema", "tech_graph_schema", "volume"):
        if not IDENTIFIER.match(bricks[key]):
            raise SettingsError(f"[databricks] {key} must be letters, digits and _ only")
    if bricks["write_schema"].lower() == bricks["tech_graph_schema"].lower():
        raise SettingsError("[databricks] write_schema and tech_graph_schema must differ")
    warehouse = bricks.get("warehouse_id", "")
    if warehouse and not IDENTIFIER.match(warehouse):
        raise SettingsError("[databricks] warehouse_id must be letters, digits and _ only")
    read = _strings("[databricks] read_catalogs", bricks["read_catalogs"], IDENTIFIER, "a catalog name", allow_empty=False)
    if "system" in {c.lower() for c in read}:
        raise SettingsError("[databricks] read_catalogs must not name system; the three system schemas are always read")
    names = {}
    for ontology_name, here in doc["names"].items():
        if not isinstance(here, str) or not IDENTIFIER.match(ontology_name) or not IDENTIFIER.match(here):
            raise SettingsError(f"[names] {ontology_name} must map one catalog name to another")
        if here.lower() not in {c.lower() for c in read}:
            raise SettingsError(f"[names] maps {ontology_name} to {here}, which read_catalogs does not name")
        if ontology_name.lower() in names:
            raise SettingsError(f"[names] names {ontology_name} twice")
        names[ontology_name.lower()] = here
    return Settings(
        zip_name=release["zip"], zip_sha256=release["sha256"],
        write_catalog=bricks["write_catalog"], write_schema=bricks["write_schema"],
        tech_graph_schema=bricks["tech_graph_schema"], volume=bricks["volume"], read_catalogs=read,
        warehouse_id=warehouse, names=names,
        skip_schemas=_strings("[skip] schemas", doc["skip"]["schemas"], PATTERN, "a name or a * pattern"),
        skip_tables=_strings("[skip] tables", doc["skip"]["tables"], PATTERN, "a name or a * pattern"),
        genie_spaces=_strings("[genie] spaces", doc["genie"]["spaces"], SPACE_ID, "a space ID"),
        sha256=hashlib.sha256(data).hexdigest(), folder=Path(folder))


def load(path):
    """Settings from the file at path. A file that is missing or cannot be read raises SettingsError."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as err:
        raise SettingsError(f"cannot read the settings file {path}: {type(err).__name__}") from None
    return parse(data, path.parent)


def file_sha256(path):
    """The SHA-256 of a file, read in pieces so a large zip does not fill memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for piece in iter(lambda: f.read(1 << 20), b""):
            digest.update(piece)
    return digest.hexdigest()


def check_zip(settings):
    """The zip's checksum, after checking it equals the one the settings name. Raises SettingsError otherwise."""
    if not settings.zip_path.is_file():
        raise SettingsError(f"the release zip {settings.zip_name} is not beside the settings file")
    found = file_sha256(settings.zip_path)
    if found != settings.zip_sha256:
        raise SettingsError(f"the release zip's SHA-256 is {found}, not the {settings.zip_sha256} the settings name")
    return found
