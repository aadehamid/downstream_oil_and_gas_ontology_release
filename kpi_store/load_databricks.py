"""Loads the release into the Delta table epm_triples, and proves by a hash that nothing was lost.

Every SQL statement goes through one Gate. The Gate refuses a write outside the two KPI Store schemas and a read
outside the read catalogs and the three system schemas, so a mistake in this code cannot touch another table.

The load writes a staging table of its own, reads it back and compares its RDFC-1.0 dataset hash with the hash
of the release files. Only an equal staging table replaces epm_triples, in one statement. The staging table is
always dropped. The main table is then read back and compared again, and only then does the marker row say which
release the table holds. A second run on the same release finds the same hash and the same marker, and writes
nothing.

The row format and the hash come from the rdf-store skill's rdfstore.py, which ships in the release.
Needs rdflib, pyoxigraph and sqlglot.
"""
import base64
import datetime as dt
import hashlib
import importlib.util
import json
import re
import uuid
from pathlib import Path

from . import compare as cmp
from . import discovery as disc
from . import metric_view as mv
from . import ontology_view as ov
from . import report as rep
from .settings import SYSTEM_SCHEMAS

CATALOG = ov.RELEASES / "catalog.ttl"
MANIFEST = Path("business_architecture") / "ontology" / "projection" / "projection-manifest.json"
RDFSTORE = Path("skills") / "rdf-store" / "scripts" / "rdfstore.py"
RELEASE_GRAPHS = ("shapes", "catalog")
MARKER_FIELDS = ("catalog_datasets", "catalog_digest", "input_fingerprint")
STORE = "databricks"
CREATE_VOLUME = re.compile(r"^\s*CREATE\s+VOLUME\s+IF\s+NOT\s+EXISTS\s+([\w`.]+)\s*$", re.IGNORECASE)
BATCH = 2000


class GateRefusal(Exception):
    """The Gate refused a statement. Nothing was sent to Databricks."""


class Gate:
    """The one way to Databricks. run() checks a statement and then passes it to run_sql."""

    def __init__(self, settings, run_sql):
        self.settings, self._run_sql = settings, run_sql
        self.statements = 0

    def run(self, statement):
        self.check(statement)
        self.statements += 1
        return [disc.as_dict(r) for r in self._run_sql(statement) or []]

    def _may_read(self, name):
        parts = name.split(".")
        return (len(parts) == 3 and (parts[0] in {c.lower() for c in self.settings.read_catalogs}
                                     or ".".join(parts[:2]) in self.settings.write_schemas
                                     or ".".join(parts[:2]) in SYSTEM_SCHEMAS))

    def _may_write(self, schema):
        return schema in self.settings.write_schemas

    def check(self, statement):
        """("read" or "write", the names the statement touches). Raises GateRefusal for anything else."""
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

def catalog_datasets(release_root):
    """The version IRIs the release's catalog lists as datasets, sorted."""
    from rdflib import Graph, URIRef
    path = Path(release_root) / CATALOG
    if not path.is_file():
        raise ov.ReleaseError(f"{path} is missing")
    graph = Graph().parse(path, format="turtle")
    return sorted(str(d) for d in graph.objects(None, URIRef("http://www.w3.org/ns/dcat#dataset")))


def newest_releases(datasets):
    """Each module's newest version IRI, .../modules/<module>/<version>, by ontology_view.version_key."""
    newest = {}
    for iri in datasets:
        module, version = iri.rsplit("/", 2)[-2:]
        key = ov.version_key(version)
        if key is None:
            raise ov.ReleaseError(f"the catalog lists {iri}, whose version this code cannot order")
        if module not in newest or key > newest[module][0]:
            newest[module] = (key, iri)
    return sorted(iri for _, iri in newest.values())


def expected(release_root):
    """What a current store's marker holds, from the catalog and the projection manifest, plus "newest": the version
    IRIs a current store holds."""
    datasets = catalog_datasets(release_root)
    manifest = Path(release_root) / MANIFEST
    try:
        fingerprint = json.loads(manifest.read_text(encoding="utf-8"))["input_fingerprint"]
    except (OSError, ValueError, KeyError):
        raise ov.ReleaseError(f"{manifest} is missing or holds no input_fingerprint") from None
    return {"catalog_datasets": len(datasets),
            "catalog_digest": hashlib.sha256("\n".join(datasets).encode()).hexdigest(),
            "input_fingerprint": fingerprint, "newest": newest_releases(datasets)}


def release_graphs(release_root):
    """{graph IRI: file} of what a current store holds. For each newest release: its content under the version IRI,
    its shapes and catalog under <version IRI>/shapes and /catalog, and each further Turtle file its manifest lists
    under <version IRI>/<file name without .ttl>. Stops when the catalog and the folders disagree on the newest
    version of a module, because the store would then hold one and the comparison would read the other."""
    releases = Path(release_root) / ov.RELEASES
    graphs = {}
    for iri in expected(release_root)["newest"]:
        module, version = iri.rsplit("/", 2)[-2:]
        on_disk = ov.newest_version(module, releases)
        if on_disk != version:
            raise ov.ReleaseError(f"the catalog's newest {module} is {version}, and the newest package folder is {on_disk}")
        folder = releases / module / version
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        own = {f"{module}.ttl", *(f"{n}.ttl" for n in RELEASE_GRAPHS)}
        graphs[iri] = folder / f"{module}.ttl"
        for name in RELEASE_GRAPHS:
            graphs[f"{iri}/{name}"] = folder / f"{name}.ttl"
        for name in sorted(n for n in manifest.get("files", {}) if n.endswith(".ttl") and n not in own):
            graphs[f"{iri}/{name[:-len('.ttl')]}"] = folder / name
    missing = sorted(str(p) for p in graphs.values() if not p.is_file())
    if missing:
        raise ov.ReleaseError(f"the release lacks {missing[0]}")
    return graphs


def import_rdfstore(release_root):
    """The rdf-store skill's module, loaded from the release by its path: its folder name is not a package name."""
    path = Path(release_root) / RDFSTORE
    spec = importlib.util.spec_from_file_location("kpi_store_rdfstore", path)
    if spec is None or not path.is_file():
        raise ov.ReleaseError(f"{path} is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_dataset(release_root, rdfstore):
    """The dataset a current store holds: one named graph per file of release_graphs."""
    import os
    graphs = release_graphs(release_root)
    named = {os.path.realpath(path): iri for iri, path in graphs.items()}   # rdfstore.pack keys its names this way
    return rdfstore.pack([str(p) for p in graphs.values()], named)


# ---- the load ----------------------------------------------------------------------------------

def _literal(text):
    """Text as a SQL expression that no quote or backslash in it can break: base64, decoded in SQL."""
    return "decode(unbase64('" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "'), 'UTF-8')"


def _export(gate, table, rdfstore):
    rows = gate.run(f"SELECT {', '.join(rdfstore.COLUMNS)} FROM {table}")
    return rdfstore.from_rows(tuple(r[c] for c in rdfstore.COLUMNS) for r in rows)


def _own_tables(gate, settings):
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
    gate.run(f"CREATE TABLE IF NOT EXISTS {settings.markers_table} (store STRING, marker STRING) USING DELTA "
             "COMMENT 'Which release each KPI Store table was loaded from'")
    gate.run(f"DELETE FROM {settings.markers_table} WHERE store = '{STORE}'")
    gate.run(f"INSERT INTO {settings.markers_table} (store, marker) SELECT '{STORE}', {_literal(json.dumps(marker, sort_keys=True))}")


def load(gate, settings, release_root, commit, now=None, rdfstore=None, batch=BATCH):
    """Loads the release into epm_triples and marks it. Returns a dict whose "status" is one of:

    current           the table and its marker already hold this release; nothing was written
    marked            the table already held this release; only the marker was written
    loaded            the table was replaced through the staging check, read back, and marked
    staging-mismatch  the staging table's hash differed; the main table is untouched (see "comparison")
    main-mismatch     the main table's hash differed after the replace; no marker was written
    """
    rdfstore = rdfstore or import_rdfstore(release_root)
    now = now or dt.datetime.now(dt.timezone.utc)
    dataset = build_dataset(release_root, rdfstore)
    rows = rdfstore.to_rows(dataset)   # refuses what the table cannot hold, before the store is touched
    lines = rdfstore.canonical_lines(dataset)
    want_hash = rdfstore.lines_hash(lines)
    want = expected(release_root)
    marker = {**{k: want[k] for k in MARKER_FIELDS}, "store": STORE, "count": [len(rows)], "dataset_hash": want_hash}
    result = {"table": settings.triples_table, "dataset_hash": want_hash, "count": len(rows)}

    def stamped():
        return {**marker, "marked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "commit": commit}

    if "epm_triples" in _own_tables(gate, settings):
        if rdfstore.dataset_hash(_export(gate, settings.triples_table, rdfstore)) == want_hash:
            held = read_marker(gate, settings) or {}
            if all(held.get(k) == v for k, v in marker.items()):
                return {**result, "status": "current", "marker": held}
            _write_marker(gate, settings, stamped())
            return {**result, "status": "marked", "marker": stamped()}

    # One staging table per run, so two runs never check or promote each other's rows.
    staging = f"{settings.triples_table}__staging_{uuid.uuid4().hex[:12]}"
    try:
        gate.run(rdfstore.create_sql(staging))
        for start in range(0, len(rows), batch):
            gate.run(rdfstore.insert_sql(staging, rows[start:start + batch]))
        passed, comparison = rdfstore.compare(dataset, _export(gate, staging, rdfstore), lines)
        if not passed:
            return {**result, "status": "staging-mismatch", "comparison": comparison}
        gate.run(f"CREATE OR REPLACE TABLE {settings.triples_table} AS SELECT * FROM {staging}")
    finally:
        gate.run(f"DROP TABLE IF EXISTS {staging}")
    passed, comparison = rdfstore.compare(dataset, _export(gate, settings.triples_table, rdfstore), lines)
    if not passed:
        return {**result, "status": "main-mismatch", "comparison": comparison}
    _write_marker(gate, settings, stamped())
    return {**result, "status": "loaded", "marker": stamped()}


# ---- the whole run -------------------------------------------------------------------------------

def _write_text(path, text):
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
    for schema in (settings.write_schema, settings.tech_graph_schema):
        gate.run(f"CREATE SCHEMA IF NOT EXISTS {settings.write_catalog}.{schema}")
    gate.run(f"CREATE VOLUME IF NOT EXISTS {settings.store_schema}.{settings.volume}")

    schemas = {settings.environment_name(o.full_name).rsplit(".", 1)[0] for o in view.objects.values()}
    found = disc.discover(settings, gate.run, genie, schemas)
    comparison = cmp.compare(view, found, settings, now, stale_after_days)
    run_record = rep.new_run(now, settings.sha256, zip_sha256 or settings.zip_sha256)
    report = rep.build(release, view.versions, run_record, comparison.rows, comparison.passes)
    run_dir = out_dir / "reports" / run_record["id"]
    paths = rep.write(report, run_dir)
    rep.write(report, out_dir)
    _write_text(run_dir / "discovery.json", found.to_json())
    summary = {"release": release, "run": run_record["id"], "blocked": report["blocked"], "passes": report["passes"],
               "rows": len(report["rows"]), "blocking_rows": [r["id"] for r in report["rows"] if r["blocks"]],
               "report_json": str(paths[0]), "report_csv": str(paths[1]), "notes": found.notes}
    if report["blocked"]:
        return {**summary, "status": "blocked"}
    if mode == "check":
        return {**summary, "status": "checked"}
    loaded = load(gate, settings, release_root, f"{release} (zip sha256 {run_record['zip_sha256']})", now, rdfstore)
    return {**summary, **loaded}
