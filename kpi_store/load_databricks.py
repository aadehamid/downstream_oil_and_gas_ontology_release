"""Loads the release into the Delta table epm_triples, and proves by a hash that nothing was lost.

Every SQL statement goes through one Gate. The Gate refuses a write outside the two KPI Store schemas, and a read
outside the read catalogs, the two KPI Store schemas and the three system schemas. So a mistake in this code that
names another table is refused before the statement is sent. The Gate judges the table names in a statement; it
does not judge a read that names no table, such as a function that reads files.

The load is the rdf-store skill's round trip (rdfstore.py, which ships in the release): it writes a staging
table of its own, reads it back and compares its RDFC-1.0 dataset hash with the hash of the release files. Only
an equal staging table replaces epm_triples, in one statement. The staging table is dropped when the round trip
ends, whether it passed or failed; a run that is killed, or a drop that fails, can leave it behind. The main
table is then read back and compared again, and only then does the marker row say which release the table
holds. A second run on the same release finds the same hash and the same marker, and leaves the table and the
marker as they are. It still writes its report files to the volume.

What a current store holds, and the marker's shape, come from the release's sync_stores.py.
Needs rdflib, pyoxigraph and sqlglot.

Where it sits: this is the work of the runner's notebook step. The notebook (kpi_store/notebook/kpi_store_load.py)
checks the zip, unpacks it and calls run here with a function that runs one SQL statement on its Spark session.
run compares the ontology with the workspace, writes the report, and calls load only when no row blocks. The
technical graph's load (kpi_store.tech_graph) and the sync check use the same Gate and the helpers here.

What it writes: the tables epm_triples and epm_store_markers in the write schema, with a comment on each table and
each column (comment_statements), a staging table there for the length of the load, and the report files in the
volume. It creates the two KPI Store schemas and the volume when
they are missing. Its table writes all go to those two schemas, also when the write catalog is one of the read
catalogs. It has no command: it runs inside the notebook.
"""
import base64
import datetime as dt
import importlib.util
import json
import re
from pathlib import Path

from . import compare as cmp
from . import discovery as disc
from . import metric_view as mv
from . import ontology_view as ov
from . import report as rep
from .settings import SYSTEM_SCHEMAS

# Two scripts of the release that this module loads by path (_import): they sit in folders that are no packages.
RDFSTORE = Path("skills") / "rdf-store" / "scripts" / "rdfstore.py"
SYNC_STORES = Path("business_architecture") / "ontology" / "projection" / "sync_stores.py"
STORE = "databricks"   # this store's name in its marker row and in the sync check
# The one statement the Gate reads without the SQL parser: CREATE VOLUME IF NOT EXISTS <catalog.schema.volume>,
# and nothing after the name. Group 1 is the volume's name.
CREATE_VOLUME = re.compile(r"^\s*CREATE\s+VOLUME\s+IF\s+NOT\s+EXISTS\s+([\w`.]+)\s*$", re.IGNORECASE)
BATCH = 2000   # rows per INSERT statement, so no one statement grows with the size of the release


class GateRefusal(Exception):
    """The Gate refused a statement. Nothing was sent to Databricks."""


class Gate:
    """The one way to Databricks. run() checks a statement and then passes it to run_sql."""

    def __init__(self, settings, run_sql):
        self.settings, self._run_sql = settings, run_sql
        self.statements = 0

    def run(self, statement):
        """Checks the statement, then runs it. A refused statement raises before anything is sent."""
        self.check(statement)
        self.statements += 1
        return [disc.as_dict(r) for r in self._run_sql(statement) or []]

    def _may_read(self, name):
        """True for a full three-part name in a read catalog, a KPI Store schema or one of the system schemas. A
        shorter name is refused: Databricks would complete it from the session, and the Gate could not tell where
        it points."""
        parts = name.split(".")
        return (len(parts) == 3 and (parts[0] in {c.lower() for c in self.settings.read_catalogs}
                                     or ".".join(parts[:2]) in self.settings.write_schemas
                                     or ".".join(parts[:2]) in SYSTEM_SCHEMAS))

    def _may_write(self, schema):
        return schema in self.settings.write_schemas

    def check(self, statement):
        """("read" or "write", the names the statement touches). Raises GateRefusal for anything else."""
        # The check works on the parsed statement, not on its text: it finds the one target a statement writes
        # and every table name it reads, wherever they stand, in a subquery too. Anything it cannot parse is
        # refused. A read that names no table, such as a function that reads files, has no name to judge.
        import sqlglot
        from sqlglot import exp
        volume = CREATE_VOLUME.match(statement)
        if volume:
            name = volume.group(1).replace("`", "").lower()
            if name.count(".") != 2 or not self._may_write(name.rsplit(".", 1)[0]):
                raise GateRefusal(f"refused: a volume outside the KPI Store's schemas: {name}")
            return "write", [name]
        try:
            trees = [t for t in sqlglot.parse(statement, read="databricks") if t is not None]
        except sqlglot.errors.SqlglotError:
            raise GateRefusal("refused: the statement cannot be parsed") from None
        if len(trees) != 1:
            raise GateRefusal("refused: one statement at a time")
        tree = trees[0]

        def name_of(table):
            return ".".join(p for p in (table.catalog, table.db, table.name) if p).lower()

        # The writes that pass: create a table or a schema, insert, delete, drop a table, the CREATE VOLUME above,
        # and the comments below. A statement that drops a schema, or creates a view or a function, is refused.
        target = None
        if isinstance(tree, (exp.Create, exp.Insert, exp.Delete, exp.Drop)):
            kind = (tree.args.get("kind") or "TABLE").upper()
            if isinstance(tree, (exp.Create, exp.Drop)) and kind not in ("TABLE", "SCHEMA") or isinstance(tree, exp.Drop) and kind != "TABLE":
                raise GateRefusal(f"refused: {type(tree).__name__} {kind} is not a statement the KPI Store runs")
            if isinstance(tree, exp.Drop):
                # sqlglot keeps a DROP's tables in a list. Two tables in one DROP are refused: the second would
                # otherwise be read as a table the statement only reads.
                dropped = tree.args.get("tables") or [tree.this]
                target = dropped[0] if len(dropped) == 1 else None
            else:
                target = tree.this.this if isinstance(tree.this, exp.Schema) else tree.this
            if not isinstance(target, exp.Table):
                raise GateRefusal("refused: the statement's target is not a table or a schema")
            written = name_of(target)
            schema = written if kind == "SCHEMA" else written.rsplit(".", 1)[0]
            if written.count(".") != (1 if kind == "SCHEMA" else 2) or not self._may_write(schema):
                raise GateRefusal(f"refused: a write outside the KPI Store's schemas: {written}")
        # The comments the load writes on its own tables (comment_statements): COMMENT ON TABLE, and ALTER TABLE
        # with ALTER COLUMN ... COMMENT and nothing else. Any other ALTER, and a comment on anything but a table, is
        # refused.
        elif isinstance(tree, (exp.Comment, exp.Alter)):
            kind = str(tree.args.get("kind") or "").upper()
            actions = tree.args.get("actions") or [] if isinstance(tree, exp.Alter) else []
            only_comments = all(isinstance(a, exp.AlterColumn)
                                and {k for k, v in a.args.items() if v not in (None, False)} == {"this", "comment"}
                                for a in actions)
            if kind != "TABLE" or not isinstance(tree.this, exp.Table) or (isinstance(tree, exp.Alter) and not (actions and only_comments)):
                raise GateRefusal(f"refused: {type(tree).__name__} {kind} is not a statement the KPI Store runs")
            target = tree.this
            written = name_of(target)
            if written.count(".") != 2 or not self._may_write(written.rsplit(".", 1)[0]):
                raise GateRefusal(f"refused: a write outside the KPI Store's schemas: {written}")
        # The only reads: SELECT and DESCRIBE. Every other kind of statement is refused, an UPDATE or a MERGE too.
        elif not isinstance(tree, (exp.Select, exp.Describe)):
            raise GateRefusal(f"refused: {type(tree).__name__} is not a statement the KPI Store runs")
        # Only a reference to a WITH clause's query, in that clause's scope, may go without three parts.
        defined = mv.cte_references(tree)
        touched = [name_of(target)] if target is not None else []
        for table in tree.find_all(exp.Table):
            if table is target or id(table) in defined:
                continue
            name = name_of(table)
            if not self._may_read(name):
                raise GateRefusal(f"refused: a read outside the read catalogs and the system schemas: {name or '(no name)'}")
            touched.append(name)
        return ("write" if target is not None else "read"), touched


# ---- what a current store holds ------------------------------------------------------------

def _import(release_root, relative, name):
    """A module of the release, loaded by its path: these folders are not packages."""
    path = Path(release_root) / relative
    spec = importlib.util.spec_from_file_location(name, path) if path.is_file() else None
    if spec is None:
        raise ov.ReleaseError(f"{path} is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def import_rdfstore(release_root):
    """The rdf-store skill's module, from the release: the row format, the hash, and the staging round trip."""
    return _import(release_root, RDFSTORE, "kpi_store_rdfstore")


def import_sync_stores(release_root):
    """The release's sync_stores module, which says what a current store holds. It reads the tree it sits in, so
    loading it from the release's root makes it describe that release."""
    return _import(release_root, SYNC_STORES, "kpi_store_sync_stores")


def expected(release_root, sync_stores=None):
    """What a current store's marker holds (sync_stores.MARKER_FIELDS), plus "newest": the version IRIs a current
    store holds."""
    ss = sync_stores or import_sync_stores(release_root)
    try:
        return ss.expected()
    except (OSError, ValueError, KeyError) as err:
        raise ov.ReleaseError(f"the release's catalog or projection manifest cannot be read, or lists a version this "
                              f"code cannot order: {type(err).__name__}: {err}") from None


def release_graphs(release_root, sync_stores=None):
    """{graph IRI: file} of what a current store holds, the graph set of sync_stores.jena_graphs with each graph's
    file: for each newest release, its content under the version IRI, each release graph (sync_stores.RELEASE_GRAPHS)
    under <version IRI>/<name>, and each package graph (sync_stores.package_graphs). Stops when the catalog and the
    folders disagree on the newest version of a module, because the store would then hold one and the comparison
    would read the other."""
    ss = sync_stores or import_sync_stores(release_root)
    root, releases = Path(release_root), Path(release_root) / ov.RELEASES
    graphs = {}
    for iri in expected(release_root, ss)["newest"]:
        module, version = iri.rsplit("/", 2)[-2:]
        on_disk = ov.newest_version(module, releases)
        if on_disk != version:
            raise ov.ReleaseError(f"the catalog's newest {module} is {version}, and the newest package folder is {on_disk}")
        folder = releases / module / version
        graphs[iri] = folder / f"{module}.ttl"
        for name in ss.RELEASE_GRAPHS:
            graphs[f"{iri}/{name}"] = folder / f"{name}.ttl"
        for graph, path in ss.package_graphs(iri).items():
            graphs[graph] = root / path
    missing = sorted(str(p) for p in graphs.values() if not p.is_file())
    if missing:
        raise ov.ReleaseError(f"the release lacks {missing[0]}")
    return graphs


def build_dataset(release_root, rdfstore, sync_stores=None):
    """The dataset a current store holds: one named graph per file of release_graphs."""
    import os
    graphs = release_graphs(release_root, sync_stores)
    named = {os.path.realpath(path): iri for iri, path in graphs.items()}   # rdfstore.pack keys its names this way
    return rdfstore.pack([str(p) for p in graphs.values()], named)


# ---- the load ----------------------------------------------------------------------------------

# The table's row format, the hash and the staging round trip are the rdf-store skill's, so the Delta table
# has the row format of every other table that skill writes. This block adds the Gate and the marker.

class GatedSpark:
    """The Spark session that rdfstore.SparkStore asks for, with every statement sent through the Gate. SparkStore
    calls sql(statement) and then collect(), and reads each row as a tuple in column order."""

    def __init__(self, gate):
        self.gate = gate

    def sql(self, statement):
        rows = [tuple(row.values()) for row in self.gate.run(statement)]
        return type("Rows", (), {"collect": lambda self: rows})()


def _literal(text):
    """Text as a SQL expression that no quote or backslash in it can break: base64, decoded in SQL."""
    return "decode(unbase64('" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "'), 'UTF-8')"


# ---- the comments on the tables ----------------------------------------------------------------

# The comments the load writes on the tables it creates, so that Unity Catalog, Genie and a person see what each
# table and column holds. The tables hold the release as rows of the rdf-store skill's format (rdfstore.COLUMNS), so
# their columns mean what that format says. A replace by CREATE ... AS SELECT keeps no comment, and Databricks takes
# no column list beside AS SELECT, so the comments are written after the table is created.
TRIPLES_COMMENT = ("The KPI Store release as RDF quads, one row per quad: each newest package's content, shapes "
                   "and catalog, each in a named graph of its own. epm_store_markers says which release it holds.")
TRIPLE_COLUMNS = {
    "subject": "The quad's subject: an IRI, or a blank node written _: followed by its label.",
    "predicate": "The quad's predicate, an IRI.",
    "object": "The quad's object: an IRI, a blank node or the text of a literal. object_kind says which.",
    "object_kind": "What object holds: iri, bnode or literal.",
    "datatype": "The datatype IRI of a literal without a language tag. NULL for an IRI, a blank node or a literal "
                "with a language tag.",
    "lang": "The language tag of a literal, such as en. NULL otherwise.",
    "graph": "The IRI of the named graph the quad belongs to.",
}
MARKERS_COMMENT = "Which release each KPI Store table was loaded from"
MARKER_COLUMNS = {
    "store": "The store the row describes.",
    "marker": "JSON: what the table was loaded from, its row count and hash, and when the row was written.",
}


def sql_string(text):
    """Text as a SQL string literal for a comment. Databricks reads a backslash in a literal as an escape (the
    STRING type page of its SQL reference, "Literals"), so a backslash and a quote are each escaped with one; a line
    end or a tab becomes a space. The statement goes to spark.sql, so no notebook widget reads a $ in it."""
    return "'" + " ".join(str(text).split()).replace("\\", "\\\\").replace("'", "\\'") + "'"


def comment_statements(table, table_comment, columns):
    """The statements that write a comment on the table and on each of its columns: COMMENT ON TABLE, then one
    ALTER TABLE ... ALTER COLUMN ... COMMENT per column, which every Databricks Runtime with Delta reads."""
    return [f"COMMENT ON TABLE {table} IS {sql_string(table_comment)}"] + [
        f"ALTER TABLE {table} ALTER COLUMN {column} COMMENT {sql_string(text)}" for column, text in columns.items()]


def write_comments(gate, table, table_comment, columns):
    """Writes the comments of comment_statements through the Gate."""
    for statement in comment_statements(table, table_comment, columns):
        gate.run(statement)


def _own_tables(gate, settings):
    """The names of the tables in the write schema, in lower case. Asked first, so a table that is not there yet
    is seen as missing and never read."""
    rows = gate.run("SELECT table_name FROM system.information_schema.tables "
                    f"WHERE lower(table_catalog) = '{settings.write_catalog.lower()}' "
                    f"AND lower(table_schema) = '{settings.write_schema.lower()}'")
    return {str(r["table_name"]).lower() for r in rows}


def read_marker(gate, settings):
    """The store's marker as a dict, or None when the marker table or the row is missing or unreadable."""
    if "epm_store_markers" not in _own_tables(gate, settings):
        return None
    rows = gate.run(f"SELECT marker FROM {settings.markers_table} WHERE store = '{STORE}'")
    try:
        return json.loads(rows[0]["marker"]) if rows else None
    except (TypeError, ValueError):
        return None


def _write_marker(gate, settings, marker):
    """Replaces this store's row in the marker table. load calls it only after a hash comparison of the table
    passed. The row is deleted and then inserted, in two statements: a run stopped between them leaves the store
    with no marker row, and a later run writes it again."""
    gate.run(f"CREATE TABLE IF NOT EXISTS {settings.markers_table} (store STRING, marker STRING) USING DELTA "
             f"COMMENT {sql_string(MARKERS_COMMENT)}")
    write_comments(gate, settings.markers_table, MARKERS_COMMENT, MARKER_COLUMNS)
    gate.run(f"DELETE FROM {settings.markers_table} WHERE store = '{STORE}'")
    gate.run(f"INSERT INTO {settings.markers_table} (store, marker) SELECT '{STORE}', {_literal(json.dumps(marker, sort_keys=True))}")


def load(gate, settings, release_root, commit, now=None, rdfstore=None, batch=BATCH, sync_stores=None):
    """Loads the release into epm_triples and marks it. Returns a dict whose "status" is one of:

    current           the table and its marker already hold this release; nothing was written
    marked            the table already held this release; only the comments and the marker were written
    loaded            the table was replaced through the staging check, read back, commented and marked
    staging-mismatch  the staging table's hash differed; the main table is untouched (see "comparison")
    main-mismatch     the main table's hash differed after the replace; no marker was written

    The staging table, the hash check, the replace and the read back are rdfstore.roundtrip's, on an
    rdfstore.SparkStore whose statements all pass the Gate. Its report tells the two mismatches apart: "published"
    is false when the staging table differed, and true when the main table differed after the replace."""
    rdfstore = rdfstore or import_rdfstore(release_root)
    ss = sync_stores or import_sync_stores(release_root)
    now = now or dt.datetime.now(dt.timezone.utc)
    dataset = build_dataset(release_root, rdfstore, ss)
    want_hash = rdfstore.dataset_hash(dataset)
    # The marker's common fields have one source, sync_stores.marker. dataset_hash is this load's own field: it lets
    # a second run see that the table still holds this release.
    marker = ss.marker(expected(release_root, ss), STORE, [len(dataset)], commit_text=commit,
                       marked_at=now.strftime("%Y-%m-%dT%H:%M:%SZ")) | {"dataset_hash": want_hash}
    # The fields that say which release the table holds. The time and the commit text differ from run to run, so
    # they are left out when a marker is compared.
    stable = {k: v for k, v in marker.items() if k not in ("marked_at", "commit")}
    result = {"table": settings.triples_table, "dataset_hash": want_hash, "count": len(dataset)}
    store = rdfstore.SparkStore(GatedSpark(gate), settings.triples_table)
    store.BATCH = batch

    # First read what the table holds now. When its hash already equals the release's, nothing is loaded: at most
    # the marker is written. This is what makes a second run leave the table as it is.
    if ss.TRIPLES_TABLE in _own_tables(gate, settings) and rdfstore.dataset_hash(store.export()) == want_hash:
        held = read_marker(gate, settings) or {}
        if all(held.get(k) == v for k, v in stable.items()):
            return {**result, "status": "current", "marker": held}
        write_comments(gate, settings.triples_table, TRIPLES_COMMENT, TRIPLE_COLUMNS)   # a run stopped before its marker
        _write_marker(gate, settings, marker)
        return {**result, "status": "marked", "marker": marker}

    # The load itself: staging table, hash check, replace, read back. The marker is written last and only after
    # both hash checks passed.
    passed, comparison = rdfstore.roundtrip(store, dataset)
    if not passed:
        return {**result, "status": "main-mismatch" if comparison.get("published") else "staging-mismatch", "comparison": comparison}
    write_comments(gate, settings.triples_table, TRIPLES_COMMENT, TRIPLE_COLUMNS)   # the replace kept none
    _write_marker(gate, settings, marker)
    if comparison.get("staging_not_dropped"):   # the load passed; a person drops the table the round trip could not
        result["staging_not_dropped"] = comparison["staging_not_dropped"]
    return {**result, "status": "loaded", "marker": marker}


# ---- the whole run -------------------------------------------------------------------------------

def _write_text(path, text):
    """Writes text as UTF-8 with LF line ends, and makes the folder when it is missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def run(settings, release_root, run_sql, genie=None, zip_sha256="", mode="load", out_dir=None, now=None,
        stale_after_days=cmp.STALE_AFTER_DAYS, rdfstore=None):
    """The notebook's whole job after the settings and the zip are checked. Creates the schemas and the volume when
    missing, reads the workspace, compares it with the ontology, and writes the report. When no row blocks and mode
    is "load", loads epm_triples. mode "check" stops after the report. stale_after_days None leaves freshness out.

    Each run writes its files to <out_dir>/reports/<run ID>/ and copies the two report files to <out_dir>, where
    the newest report is always found. out_dir defaults to the folder of the settings file: the volume.

    Returns a summary dict. "status" is "blocked" (a row blocks; nothing was loaded), "checked" (mode "check", no
    row blocks) or one of load()'s statuses.
    """
    if mode not in ("load", "check"):
        raise ValueError(f"mode must be load or check, not {mode!r}")
    now = now or dt.datetime.now(dt.timezone.utc)
    out_dir = Path(out_dir) if out_dir else settings.folder
    release = ov.release_name(release_root)
    view = ov.read(release_root)
    release_graphs(release_root)   # a release whose catalog and folders disagree stops here, before Databricks is touched
    gate = Gate(settings, run_sql)
    # Besides its tables and its files in the volume, the run creates these when they are missing: the two KPI
    # Store schemas and the volume.
    for schema in (settings.write_schema, settings.tech_graph_schema):
        gate.run(f"CREATE SCHEMA IF NOT EXISTS {settings.write_catalog}.{schema}")
    gate.run(f"CREATE VOLUME IF NOT EXISTS {settings.store_schema}.{settings.volume}")

    # Read the workspace, compare, and write the report: in the run's own folder, and then at the top of the
    # volume, over the report of the run before. discovery.json keeps the whole reading for the technical graph.
    schemas = {settings.environment_name(o.full_name).rsplit(".", 1)[0] for o in view.objects.values()}
    found = disc.discover(settings, gate.run, genie, schemas)
    comparison = cmp.compare(view, found, settings, now, stale_after_days, rep.read_standing(release_root))
    run_record = rep.new_run(now, settings.sha256, zip_sha256 or settings.zip_sha256)
    report = rep.build(release, view.versions, run_record, comparison.rows, comparison.passes)
    run_dir = out_dir / "reports" / run_record["id"]
    paths = rep.write(report, run_dir)
    rep.write(report, out_dir)
    _write_text(run_dir / "discovery.json", found.to_json())
    summary = {"release": release, "run": run_record["id"], "blocked": report["blocked"], "passes": report["passes"],
               "rows": len(report["rows"]), "blocking_rows": [r["id"] for r in report["rows"] if r["blocks"]],
               "report_json": str(paths[0]), "report_csv": str(paths[1]), "notes": found.notes}
    # The report decides. A row that blocks ends the run here, before any triple is written.
    if report["blocked"]:
        return {**summary, "status": "blocked"}
    if mode == "check":
        return {**summary, "status": "checked"}
    loaded = load(gate, settings, release_root, f"{release} (zip sha256 {run_record['zip_sha256']})", now, rdfstore)
    return {**summary, **loaded}
