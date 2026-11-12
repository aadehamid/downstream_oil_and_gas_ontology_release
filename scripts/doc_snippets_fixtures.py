#!/usr/bin/env python3
"""The stand-ins that a few blocks of the documents run against, for scripts/doc_snippets.py.

A document block that deletes, or that needs a server only the client has, cannot run on the stores the other
blocks share. A context of scripts/doc_snippets.toml gives such a block a small store of its own. This file makes
that store before the context's first block (`up`), runs the block's statement on it, and removes it when the
check ends (`down`). The check starts every command here from a copy of the release, with the variable
DOC_SNIPPETS_FIXTURE_DIR naming a folder outside that copy where a fixture keeps what it made.

    py scripts/doc_snippets_fixtures.py questions up|down             a composite database over two made-up graphs
    py scripts/doc_snippets_fixtures.py scratch-database up|down      one throwaway database on the test server
    py scripts/doc_snippets_fixtures.py scratch-schemas up|down       two throwaway schemas in the rehearsal catalog
    py scripts/doc_snippets_fixtures.py cypher <database|scratch> <file>     run the file's Cypher statements
    py scripts/doc_snippets_fixtures.py sql <file>                    run the file's SQL on the throwaway schemas
    py scripts/doc_snippets_fixtures.py notebook <file>               run the file's Python as a notebook cell would

The Neo4j test server is the one KPI_STORE_TEST_NEO4J_URI, KPI_STORE_TEST_NEO4J_USER and
KPI_STORE_TEST_NEO4J_PASSWORD name. The Databricks workspace is the one of the local settings file that
KPI_STORE_TEST_LOCAL_SETTINGS names; that file must name a rehearsal catalog, never the client's. No password and
no token is written to a file or printed. scripts/DOC-SNIPPETS.md describes the contexts for writers.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURE_DIR = "DOC_SNIPPETS_FIXTURE_DIR"
# Fixed names, all lower case with no separator, as a Neo4j database name must be. They say whose they are.
QUESTIONS = {"composite": "docsnippetsquestions", "governance": "docsnippetsgovernance", "bpa": "docsnippetsbpa"}
SCRATCH_DATABASE = "docsnippetsscratch"
SCHEMA_PREFIX = "doc_snippets_"
STATE = "state.json"


class Refused(Exception):
    """The fixture will not touch what it was pointed at."""


def fixture_dir() -> Path:
    folder = os.environ.get(FIXTURE_DIR)
    if not folder:
        raise Refused(f"{FIXTURE_DIR} is not set: scripts/doc_snippets.py starts this command, not a person")
    return Path(folder)


def statements(text: str) -> list:
    """The statements of a block: split at each `;` that ends a line, with `//` and `--` comment lines dropped."""
    lines = [line for line in text.split("\n") if not line.lstrip().startswith(("//", "--"))]
    return [part.strip() for part in re.split(r";[ \t]*(?:\n|$)", "\n".join(lines)) if part.strip()]


def table_text(columns, rows) -> str:
    """A result as text: the column names, then one line per row."""
    def cell(value):
        return "null" if value is None else str(value)
    return "\n".join([", ".join(columns)] + [", ".join(cell(row[c]) for c in columns) for row in rows])


# ---- Neo4j ----------------------------------------------------------------------------------------------

def neo4j_driver():
    uri, password = os.environ.get("KPI_STORE_TEST_NEO4J_URI"), os.environ.get("KPI_STORE_TEST_NEO4J_PASSWORD")
    if not uri or not password:
        raise Refused("no test server named: set KPI_STORE_TEST_NEO4J_URI and KPI_STORE_TEST_NEO4J_PASSWORD")
    from neo4j import GraphDatabase
    return GraphDatabase.driver(uri, auth=(os.environ.get("KPI_STORE_TEST_NEO4J_USER") or "neo4j", password),
                                notifications_min_severity="OFF")


def questions_builder():
    """The builder of the cross-graph questions' made-up graphs, pointed at this fixture's own databases. Its own
    names include businessprocessarchitecturegraph, which other blocks load, so they are replaced."""
    import importlib.util
    path = ROOT / "kpi_store" / "tests" / "fixtures" / "questions" / "build_graph.py"
    spec = importlib.util.spec_from_file_location("doc_snippets_questions_build_graph", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.COMPOSITE = QUESTIONS["composite"]
    module.MEMBERS = {alias: (QUESTIONS[alias], file_name) for alias, (_, file_name) in module.MEMBERS.items()}
    return module


def questions(word):
    build = questions_builder()
    with neo4j_driver() as driver:
        if word == "up":
            build.build(driver)
            folder = fixture_dir()
            # The password is not written: the context hands it to the command in KPI_STORE_NEO4J_PASSWORD.
            (folder / "questions.toml").write_text(
                f'[neo4j]\nuri = "{os.environ["KPI_STORE_TEST_NEO4J_URI"]}"\n'
                f'user = "{os.environ.get("KPI_STORE_TEST_NEO4J_USER") or "neo4j"}"\n'
                f'composite = "{build.COMPOSITE}"\ngovernance_alias = "governance"\nbpa_alias = "bpa"\n',
                encoding="utf-8", newline="\n")
            write_values(folder, {"your settings file": "../fixture/questions.toml",
                                  "your mapping file": "../fixture/mapping.json", "a folder": "../fixture/answers"})
            print(f"made the composite database {build.COMPOSITE} over two made-up graphs")
            return
        with driver.session(database="system") as session:
            for alias in build.MEMBERS:
                session.run(f"DROP ALIAS {build.COMPOSITE}.{alias} IF EXISTS FOR DATABASE").consume()
            session.run(f"DROP COMPOSITE DATABASE {build.COMPOSITE} IF EXISTS WAIT").consume()
            for database, _ in build.MEMBERS.values():
                session.run(f"DROP DATABASE {database} IF EXISTS WAIT").consume()
        print(f"removed the composite database {build.COMPOSITE} and its two databases")


def scratch_database(word):
    """A database with a few nodes, their relationships and the one constraint that the load and the copy make, so
    that a statement which empties a database has something to delete."""
    with neo4j_driver() as driver:
        with driver.session(database="system") as session:
            session.run(f"DROP DATABASE {SCRATCH_DATABASE} IF EXISTS WAIT").consume()
            if word == "down":
                print(f"removed the database {SCRATCH_DATABASE}")
                return
            session.run(f"CREATE DATABASE {SCRATCH_DATABASE} WAIT").consume()
        with driver.session(database=SCRATCH_DATABASE) as session:
            session.run("CREATE CONSTRAINT n10s_unique_uri FOR (r:Resource) REQUIRE r.uri IS UNIQUE").consume()
            session.run("UNWIND range(1, 25) AS i CREATE (:Resource {uri: 'urn:doc-snippets:' + toString(i)})").consume()
            session.run("MATCH (a:Resource), (b:Resource) WHERE a.uri < b.uri AND rand() < 0.2 "
                        "CREATE (a)-[:MADE_UP]->(b)").consume()
    print(f"made the database {SCRATCH_DATABASE} with 25 nodes and the constraint n10s_unique_uri")


def cypher(database, path):
    """Runs each statement of the file in the database, as Neo4j Browser does, and prints the rows it returns.
    Any name but `scratch` is read only: a statement that writes fails there."""
    scratch = database == "scratch"
    from neo4j import READ_ACCESS, WRITE_ACCESS
    with neo4j_driver() as driver:
        with driver.session(database=SCRATCH_DATABASE if scratch else database,
                            default_access_mode=WRITE_ACCESS if scratch else READ_ACCESS) as session:
            for statement in statements(Path(path).read_text(encoding="utf-8")):
                result = session.run(statement)     # its own transaction, which CALL { } IN TRANSACTIONS needs
                columns, rows = result.keys(), [record.data() for record in result]
                if columns:
                    print(table_text(columns, rows))


# ---- Databricks -----------------------------------------------------------------------------------------

def databricks():
    """(the test environment's settings, the example settings whose names the documents use, run_sql). Refuses
    a settings file that writes to the catalog the documents name: that is the client's, not a rehearsal's."""
    from kpi_store import local_settings, settings, sync_check
    path = os.environ.get("KPI_STORE_TEST_LOCAL_SETTINGS")
    if not path:
        raise Refused("no local settings file named: set KPI_STORE_TEST_LOCAL_SETTINGS")
    local = local_settings.load(path, release_root=ROOT)
    here = settings.load(local.need("settings"))
    example = settings.load(ROOT / "kpi_store" / "kpi_store.example.toml")
    if here.write_catalog.lower() == example.write_catalog.lower():
        raise Refused(f"the settings write to {here.write_catalog}, the catalog the documents name. A test writes "
                      "only to a rehearsal catalog")
    if not here.warehouse_id:
        raise Refused("the settings name no SQL warehouse, so no statement can run from this machine")
    client = sync_check.workspace_client(local.need("databricks").profile)
    return here, example, sync_check.statement_runner(client, here.warehouse_id)


def write_values(folder, placeholders):
    (folder / "values.json").write_text(json.dumps({"placeholders": placeholders}, indent=2) + "\n", encoding="utf-8",
                                        newline="\n")


def scratch_names(example, catalog, schema):
    """What the documents' names become on the throwaway schemas: the example settings' two schemas, in the
    catalog the documents name, to the fixture's two."""
    return {f"{example.write_catalog}.{example.write_schema}": f"{catalog}.{schema}",
            f"{example.write_catalog}.{example.tech_graph_schema}": f"{catalog}.{schema}_tech"}


def to_scratch(statement: str, names: dict) -> str:
    """The statement with each name of the documents replaced by the fixture's. Refuses a statement that then
    still names anything outside the throwaway schemas, or that names nothing at all."""
    def swap(match):
        dotted = match.group(0)
        for document_name, scratch_name in names.items():
            if dotted.lower() == document_name.lower() or dotted.lower().startswith(document_name.lower() + "."):
                return scratch_name + dotted[len(document_name):]
        return dotted
    mapped = re.sub(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", swap, statement)
    found = re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", mapped)
    allowed = tuple(name.lower() for name in names.values())
    outside = [name for name in found if not (name.lower() in allowed or name.lower().startswith(tuple(a + "." for a in allowed)))]
    if outside or not found:
        raise Refused("the statement names " + (", ".join(outside) if outside else "no object")
                      + ": only the throwaway schemas may be changed")
    return mapped


def scratch_schemas(word):
    """Two schemas with what a run of the KPI Store leaves in them: the four tables and the volume."""
    from kpi_store import reset
    import dataclasses
    folder = fixture_dir()
    here, example, run_sql = databricks()
    if word == "down":
        state = json.loads((folder / STATE).read_text(encoding="utf-8")) if (folder / STATE).is_file() else {}
        for schema in state.get("schemas", []):
            if not schema.split(".")[-1].startswith(SCHEMA_PREFIX):
                raise Refused(f"{schema} is not a schema this fixture made")
            run_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        print("removed " + (", ".join(state.get("schemas", [])) or "nothing"))
        return
    schema = SCHEMA_PREFIX + secrets.token_hex(4)
    scratch = dataclasses.replace(here, write_schema=schema, tech_graph_schema=schema + "_tech")
    schemas = [f"{scratch.write_catalog}.{scratch.write_schema}", f"{scratch.write_catalog}.{scratch.tech_graph_schema}"]
    # The state is written first, so `down` removes whatever a failed `up` left behind.
    (folder / STATE).write_text(json.dumps({"schemas": schemas, "catalog": scratch.write_catalog, "schema": schema}) + "\n",
                                encoding="utf-8", newline="\n")
    for name in schemas:
        run_sql(f"CREATE SCHEMA {name}")
    for table in reset.databricks_tables(scratch):
        run_sql(f"CREATE TABLE {table} (made_up STRING)")
    run_sql(f"CREATE VOLUME {schemas[0]}.{scratch.volume}")
    write_values(folder, {"catalog": scratch.write_catalog, "schema": schema, "table": "made_up_triples"})
    print(f"made {schemas[0]} and {schemas[1]} with four tables and the volume {scratch.volume}")


def scratch_state():
    path = fixture_dir() / STATE
    if not path.is_file():
        raise Refused("the throwaway schemas were not made: run the fixture's `up` first")
    return json.loads(path.read_text(encoding="utf-8"))


def exists(run_sql, kind, name) -> bool:
    catalog, schema, *rest = name.split(".")
    if kind == "SCHEMA":
        return bool(run_sql(f"SHOW SCHEMAS IN {catalog} LIKE '{schema}'"))
    listing = "VOLUMES" if kind == "VOLUME" else "TABLES"
    return bool(run_sql(f"SHOW {listing} IN {catalog}.{schema} LIKE '{rest[0]}'"))


def sql(path):
    """Runs each statement of the file on the throwaway schemas. A DROP ... IF EXISTS must name something that is
    there: a statement that drops nothing would pass in silence, whatever name it holds."""
    state = scratch_state()
    here, example, run_sql = databricks()
    names = scratch_names(example, state["catalog"], state["schema"])
    for statement in statements(Path(path).read_text(encoding="utf-8")):
        mapped = to_scratch(statement, names)
        drop = re.match(r"\s*DROP\s+(TABLE|VOLUME|SCHEMA)\s+IF\s+EXISTS\s+([\w.]+)", mapped, re.I)
        if drop and not exists(run_sql, drop.group(1).upper(), drop.group(2)):
            raise Refused(f"{statement} names nothing that a run of the KPI Store makes")
        run_sql(mapped)
        if drop and exists(run_sql, drop.group(1).upper(), drop.group(2)):
            raise Refused(f"{statement} left its object in place")
        print("OK: " + statement)


class WarehouseSession:
    """What `spark` is to a block that calls only spark.sql(statement) and reads the result with collect(): each
    statement runs on the rehearsal workspace's SQL warehouse, and may name only the throwaway schema."""

    def __init__(self, run_sql, allowed):
        self.run_sql, self.allowed = run_sql, allowed

    def sql(self, statement):
        to_scratch(re.sub(r"'(?:[^']|'')*'", "''", statement), {self.allowed: self.allowed})    # the guard only
        rows = self.run_sql(statement)

        class Result:
            def collect(self):
                return [tuple(row.values()) for row in rows]
        return Result()


def notebook(path):
    """Runs the file's Python with the two names a Databricks notebook of the rdf-store skill has: `spark`, and
    `files`, here three small files of the release. rdfstore.py is importable, as it is in the notebook."""
    state = scratch_state()
    here, example, run_sql = databricks()
    sys.path.insert(0, str(ROOT / "skills" / "rdf-store" / "scripts"))
    releases = ROOT / "business_architecture" / "ontology" / "releases"
    # A module's package file is <module>/<version>/<module>.ttl. The three smallest keep the load to a few statements.
    packages = [p for p in releases.glob("*/*/*.ttl") if p.stem == p.parent.parent.name]
    files = [str(p) for p in sorted(packages, key=lambda p: (p.stat().st_size, p.as_posix()))[:3]]
    if len(files) < 3:
        raise Refused("the release holds fewer than three module packages to load")
    scope = {"__name__": "__main__", "spark": WarehouseSession(run_sql, f"{state['catalog']}.{state['schema']}"),
             "files": files}
    exec(compile(Path(path).read_text(encoding="utf-8"), str(path), "exec"), scope)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    fixtures = {"questions": questions, "scratch-database": scratch_database, "scratch-schemas": scratch_schemas}
    try:
        if len(args) == 2 and args[0] in fixtures and args[1] in ("up", "down"):
            fixtures[args[0]](args[1])
        elif len(args) == 3 and args[0] == "cypher":
            cypher(args[1], args[2])
        elif len(args) == 2 and args[0] in ("sql", "notebook"):
            {"sql": sql, "notebook": notebook}[args[0]](args[1])
        else:
            print(__doc__.split("\n\n")[2], file=sys.stderr)
            return 2
    except Refused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
