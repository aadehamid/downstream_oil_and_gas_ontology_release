"""Reads the workspace: objects, columns, metric views, lineage, builders, Genie spaces and freshness.

Everything arrives through two injected objects: run_sql(statement), which returns a list of rows (dicts, or
Spark rows), and a Genie client with list_spaces and get_space, as databricks-sdk's WorkspaceClient().genie has.
This module imports neither Spark nor the SDK, so the tests run it against made-up rows.

Every time the platform reports is read once, here, into UTC text with its full precision (utc_precise), and
compared as a full instant. Only what a person is shown is cut to the second (utc_text).

Lineage rules: an edge is kept only when both of its tables exist today and no skip rule covers either; an edge
from a table to itself is dropped; the lineage's entity_type is not read. A column edge is kept when both of its
tables exist today, whether or not the columns do, because an old column name in the lineage is the evidence of
a rename.
"""
import datetime as dt
import json
from dataclasses import asdict, dataclass, field

from . import metric_view as mv


@dataclass
class TableInfo:
    full_name: str      # catalog.schema.name, as Databricks spells it
    catalog: str
    schema: str
    name: str
    table_type: str
    last_altered: str = ""


@dataclass
class GenieSpace:
    space_id: str
    title: str
    tables: list = field(default_factory=list)        # full names, as the space spells them
    filters: list = field(default_factory=list)       # [{"title", "sql"}]
    expressions: list = field(default_factory=list)   # [{"title", "sql"}]
    example_sqls: list = field(default_factory=list)  # [{"question", "sql"}]


@dataclass
class Discovery:
    tables: dict = field(default_factory=dict)          # {full name, lower case: TableInfo}, skipped ones left out
    columns: dict = field(default_factory=dict)         # {table, lower case: [column names as spelled]}
    metric_views: dict = field(default_factory=dict)    # {view, lower case: MetricView}
    table_edges: dict = field(default_factory=dict)     # {(source, target), lower case: {"entities", "last_event"}}
    column_edges: set = field(default_factory=set)      # {(source table, source column, target table, target column)}
    builders: dict = field(default_factory=dict)        # {entity ID: {"kind", "name"}}
    genie_spaces: list = field(default_factory=list)    # [GenieSpace]
    migration_pairs: list = field(default_factory=list) # [(source, target)], lineage edges that follow the naming rule
    notes: list = field(default_factory=list)           # what could not be read, in words

    def exists(self, name):
        return name.lower() in self.tables

    def spelled(self, name):
        """The object's name as Databricks spells it."""
        return self.tables[name.lower()].full_name

    def upstream(self, name):
        return {s for s, t in self.table_edges if t == name.lower()}

    def column_sources(self, table, column):
        return {(st, sc) for st, sc, tt, tc in self.column_edges if tt == table.lower() and tc == column.lower()}

    def last_written(self, name):
        """The newest lineage event that wrote the table, as a person is shown it (utc_text), or ""."""
        return utc_text(self.last_written_at(name))

    def last_written_at(self, name):
        """The instant of the newest lineage event that wrote the table, or None. Compare with this one."""
        return instant(newest(e["last_event"] for (s, t), e in self.table_edges.items() if t == name.lower()))

    def to_json(self):
        """The whole reading as JSON text, for the tools that build on it outside the notebook."""
        return json.dumps({
            "tables": {k: asdict(v) for k, v in sorted(self.tables.items())},
            "columns": dict(sorted(self.columns.items())),
            "metric_views": {k: asdict(v) for k, v in sorted(self.metric_views.items())},
            "table_edges": [{"source": s, "target": t, **e} for (s, t), e in sorted(self.table_edges.items())],
            "column_edges": [list(e) for e in sorted(self.column_edges)],
            "builders": dict(sorted(self.builders.items())),
            "genie_spaces": [asdict(s) for s in self.genie_spaces],
            "migration_pairs": [list(p) for p in self.migration_pairs],
            "notes": self.notes,
        }, indent=2, sort_keys=True) + "\n"


def as_dict(row):
    """A row as a dict with lower-case keys, whether it came as a dict or as a Spark row."""
    data = row.asDict() if hasattr(row, "asDict") else dict(row)
    return {str(k).lower(): v for k, v in data.items()}


def _quoted(values):
    """A SQL list of lower-case text values. The values are names the settings validated, or names read from the
    release, so a quote is never expected; one is refused all the same."""
    values = sorted({v.lower() for v in values})
    if any("'" in v or "\\" in v for v in values):
        raise ValueError("a name holds a quote or a backslash")
    return ", ".join(f"'{v}'" for v in values)


def _text(value):
    """A serialized Genie space writes long text as a list of pieces."""
    if isinstance(value, list):
        return "".join(str(v) for v in value)
    return "" if value is None else str(value)


def instant(value):
    """A platform time as a timezone-aware UTC datetime, or None when the value is empty or is no time.

    Takes a datetime, or text with a T or a space between date and time, with an offset, a trailing Z or neither.
    A time with no zone is UTC, which is what the system tables record."""
    if isinstance(value, dt.datetime):
        when = value
    elif isinstance(value, dt.date):
        when = dt.datetime(value.year, value.month, value.day)
    else:
        try:
            when = dt.datetime.fromisoformat(str(value or "").strip())
        except ValueError:
            return None
    return (when.replace(tzinfo=dt.timezone.utc) if when.tzinfo is None else when).astimezone(dt.timezone.utc)


def utc_text(value):
    """A platform time as a person is shown it, in the report and the technical graph: YYYY-MM-DDTHH:MM:SSZ, in
    UTC, to the second. "" when the value is empty or is no time. Never order times by this text: it drops the
    part of a second, so order instants (instant) or the reading's own text (utc_precise)."""
    when = instant(value)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ") if when else ""


def utc_precise(value):
    """A platform time as the reading and its JSON hold it: YYYY-MM-DDTHH:MM:SS.ffffffZ, in UTC, always with six
    digits, so nothing the platform reported is lost and a tool that reads the JSON orders times as this code
    does. "" when the value is empty or is no time."""
    when = instant(value)
    return when.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if when else ""


def newest(values):
    """The newest of some platform times, compared as full instants, as utc_precise; "" when none is a time."""
    found = [when for when in map(instant, values) if when]
    return utc_precise(max(found)) if found else ""


def migration_pair(source, target):
    """True when a lineage edge follows the migration naming rule: <catalog a>.<schema>.<table> feeds
    <catalog b>.<layer>_<schema>.<table>. Case is ignored."""
    s, t = source.lower().split("."), target.lower().split(".")
    return (len(s) == 3 and len(t) == 3 and s[0] != t[0] and s[2] == t[2]
            and t[1].endswith("_" + s[1]) and len(t[1]) > len(s[1]) + 1)


def parse_space(space_id, title, serialized):
    """A GenieSpace from a serialized space (version 2): its tables, its SQL snippets and its example SQL."""
    doc = json.loads(serialized) if isinstance(serialized, str) else (serialized or {})
    space = GenieSpace(space_id=str(space_id), title=str(title or ""))
    sources = doc.get("data_sources") or {}
    for kind in ("tables", "metric_views"):
        space.tables += [str(t["identifier"]) for t in sources.get(kind) or [] if t.get("identifier")]
    instructions = doc.get("instructions") or {}
    snippets = instructions.get("sql_snippets") or {}
    for key, target in (("filters", space.filters), ("expressions", space.expressions)):
        for item in snippets.get(key) or []:
            title_text = _text(item.get("display_name")) or _text(item.get("alias")) or _text(item.get("id"))
            target.append({"title": title_text, "sql": _text(item.get("sql")).strip()})
    for item in instructions.get("example_question_sqls") or []:
        space.example_sqls.append({"question": _text(item.get("question")).strip(), "sql": _text(item.get("sql")).strip()})
    return space


def read_genie(genie, space_ids=()):
    """([GenieSpace], [notes]). With no IDs, reads every space the caller can list. A space that cannot be read
    becomes a note, so one closed space does not hide the others."""
    spaces, notes, listed = [], [], {}
    if not space_ids:
        token = None
        while True:
            page = genie.list_spaces(page_token=token) if token else genie.list_spaces()
            for s in getattr(page, "spaces", None) or []:
                listed[s.space_id] = s.title
            token = getattr(page, "next_page_token", None)
            if not token:
                break
    for space_id in space_ids or sorted(listed):
        try:
            full = genie.get_space(space_id, include_serialized_space=True)
            spaces.append(parse_space(space_id, getattr(full, "title", None) or listed.get(space_id), getattr(full, "serialized_space", None)))
        except Exception as err:   # no access, or a shape this code does not know: say so and read the next one
            notes.append(f"Genie space {space_id} could not be read ({type(err).__name__})")
    return spaces, notes


def discover(settings, run_sql, genie=None, schemas=()):
    """A Discovery of the workspace. schemas names the schemas, as catalog.schema, whose columns, metric views and
    column lineage are read: the ones that hold the ontology's objects. The tables of a Genie space add theirs."""
    found = Discovery()
    catalogs = _quoted(settings.read_catalogs)
    in_scope = {c.lower() for c in settings.read_catalogs}
    for row in map(as_dict, run_sql(
            "SELECT table_catalog, table_schema, table_name, table_type, last_altered "
            f"FROM system.information_schema.tables WHERE lower(table_catalog) IN ({catalogs})")):
        if str(row["table_catalog"]).lower() not in in_scope:
            continue
        info = TableInfo(f"{row['table_catalog']}.{row['table_schema']}.{row['table_name']}", row["table_catalog"],
                         row["table_schema"], row["table_name"], str(row.get("table_type") or ""), utc_precise(row.get("last_altered")))
        if not settings.skipped(info.schema, info.name):
            found.tables[info.full_name.lower()] = info

    if genie is None:
        found.notes.append("Genie spaces were not read: no Genie client was given")
    else:
        try:
            found.genie_spaces, notes = read_genie(genie, settings.genie_spaces)
            found.notes += notes
        except Exception as err:   # the Genie API as a whole is closed to the caller
            found.notes.append(f"Genie spaces could not be listed ({type(err).__name__})")

    scope = {s.lower() for s in schemas}
    for space in found.genie_spaces:
        scope |= {t.lower().rsplit(".", 1)[0] for t in space.tables if t.lower() in found.tables}
    scope = {s for s in scope if s.split(".")[0] in in_scope}
    if scope:
        for row in map(as_dict, run_sql(
                "SELECT table_catalog, table_schema, table_name, column_name, ordinal_position "
                "FROM system.information_schema.columns "
                f"WHERE lower(concat(table_catalog, '.', table_schema)) IN ({_quoted(scope)})")):
            table = f"{row['table_catalog']}.{row['table_schema']}.{row['table_name']}".lower()
            if table in found.tables and table.rsplit(".", 1)[0] in scope:
                found.columns.setdefault(table, []).append((int(row.get("ordinal_position") or 0), str(row["column_name"])))
        found.columns = {t: [name for _, name in sorted(cols)] for t, cols in found.columns.items()}

    for key, info in sorted(found.tables.items()):
        if info.table_type.upper() == "METRIC_VIEW" and key.rsplit(".", 1)[0] in scope:
            try:
                rows = run_sql(f"DESCRIBE TABLE EXTENDED `{info.catalog}`.`{info.schema}`.`{info.name}` AS JSON")
                text = next(iter(as_dict(rows[0]).values()))
                view = mv.parse_describe_json(text)
                view.name = info.full_name
                found.metric_views[key] = view
            except Exception as err:   # one view that cannot be read must not stop the rest; the comparison reports it
                found.notes.append(f"metric view {info.full_name} could not be read ({type(err).__name__}: {err})")

    def kept(source, target):
        s, t = source.lower(), target.lower()
        return s != t and s in found.tables and t in found.tables

    for row in map(as_dict, run_sql(
            "SELECT source_table_full_name, target_table_full_name, entity_id, max(event_time) AS last_event "
            "FROM system.access.table_lineage "
            "WHERE source_table_full_name IS NOT NULL AND target_table_full_name IS NOT NULL "
            f"AND lower(source_table_catalog) IN ({catalogs}) AND lower(target_table_catalog) IN ({catalogs}) "
            "GROUP BY source_table_full_name, target_table_full_name, entity_id")):
        source, target = row.get("source_table_full_name"), row.get("target_table_full_name")
        if not source or not target or not kept(source, target):
            continue
        edge = found.table_edges.setdefault((source.lower(), target.lower()), {"entities": [], "last_event": ""})
        if row.get("entity_id") and str(row["entity_id"]) not in edge["entities"]:
            edge["entities"] = sorted(edge["entities"] + [str(row["entity_id"])])
        edge["last_event"] = newest([edge["last_event"], row.get("last_event")])
    found.migration_pairs = sorted(e for e in found.table_edges if migration_pair(*e))

    if scope:
        for row in map(as_dict, run_sql(
                "SELECT source_table_full_name, source_column_name, target_table_full_name, target_column_name "
                "FROM system.access.column_lineage "
                "WHERE source_table_full_name IS NOT NULL AND target_table_full_name IS NOT NULL "
                "AND source_column_name IS NOT NULL AND target_column_name IS NOT NULL "
                f"AND lower(concat(target_table_catalog, '.', target_table_schema)) IN ({_quoted(scope)}) "
                "GROUP BY source_table_full_name, source_column_name, target_table_full_name, target_column_name")):
            if all(row.get(k) for k in ("source_table_full_name", "source_column_name", "target_table_full_name", "target_column_name")) \
                    and kept(row["source_table_full_name"], row["target_table_full_name"]):
                found.column_edges.add((row["source_table_full_name"].lower(), row["source_column_name"].lower(),
                                        row["target_table_full_name"].lower(), row["target_column_name"].lower()))

    entities = sorted({e for edge in found.table_edges.values() for e in edge["entities"]})
    if entities:
        ids = _quoted(entities)
        for kind, table, key in (("job", "system.lakeflow.jobs", "job_id"), ("pipeline", "system.lakeflow.pipelines", "pipeline_id")):
            latest = {}
            try:
                rows = run_sql(f"SELECT {key}, name, change_time FROM {table} WHERE lower({key}) IN ({ids})")
            except Exception as err:   # the lakeflow schema may be closed to the caller; builders are a note, not a gate
                found.notes.append(f"{table} could not be read ({type(err).__name__})")
                continue
            for row in map(as_dict, rows):
                # An ID is kept exactly as the platform gives it: two IDs that differ in case are two builders.
                # The time is ordered in full: two versions saved within one second are still two instants.
                entity, changed = str(row[key]), utc_precise(row.get("change_time"))
                # The table keeps every name an ID has had: the newest row holds the current one. Rows of exactly
                # the same instant are settled by name, so the order the rows arrive in never decides.
                if entity in entities and (entity not in latest or (changed, str(row.get("name") or "")) > latest[entity]):
                    latest[entity] = (changed, str(row.get("name") or ""))
            for entity, (_, name) in latest.items():
                found.builders[entity] = {"kind": kind, "name": name}
    return found
