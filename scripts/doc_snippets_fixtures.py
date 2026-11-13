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
no token is written to a file of the release or printed. scripts/DOC-SNIPPETS.md describes the contexts for writers.
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
# A Neo4j database this file makes is named with this prefix and eight random digits and letters, all lower case
# with no separator, as a database name must be. A name is made for one run and never reused.
DATABASE_PREFIX = "docsnippets"
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


def new_name(kind: str) -> str:
    return DATABASE_PREFIX + kind + secrets.token_hex(4)


def created(folder) -> list:
    """What this fixture made on the Neo4j server, in the order it was made: [[kind, name], ...]. The file is
    written after each thing is made, so a set-up that stops halfway still knows what it must remove."""
    path = Path(folder) / STATE
    return json.loads(path.read_text(encoding="utf-8")).get("created", []) if path.is_file() else []


def record(folder, kind, name):
    (Path(folder) / STATE).write_text(json.dumps({"created": created(folder) + [[kind, name]]}) + "\n", encoding="utf-8",
                                      newline="\n")


def make(session, folder, kind, name, statement):
    """Makes one database, composite database or alias, and records it. The statement has no IF NOT EXISTS: the
    server refuses a name that is taken, so nothing that was there before is ever reused."""
    session.run(statement).consume()
    record(folder, kind, name)


def refuse_taken(session, names):
    """Stops before anything is made when the server already holds a database or an alias of a wanted name."""
    held = {str(name).lower() for name in session.run("SHOW DATABASES YIELD name RETURN name").value()}
    held |= {str(name).lower() for name in session.run("SHOW ALIASES FOR DATABASE YIELD name RETURN name").value()}
    taken = sorted(name for name in names if name.lower() in held)
    if taken:
        raise Refused(f"the server already holds {', '.join(taken)}. The fixture makes its own databases and never "
                      "uses one that is there; nothing was changed")


DROP = {"database": "DROP DATABASE {name} IF EXISTS WAIT", "composite": "DROP COMPOSITE DATABASE {name} IF EXISTS WAIT",
        "alias": "DROP ALIAS {name} IF EXISTS FOR DATABASE"}


def remove_created(driver, folder) -> int:
    """Drops what this fixture recorded as made, newest first, and nothing else. Each drop is tried; what could not
    be dropped is printed with the statement that drops it by hand. Returns the number left behind."""
    left = []
    with driver.session(database="system") as session:
        for kind, name in reversed(created(folder)):
            if not name.startswith(DATABASE_PREFIX):
                raise Refused(f"{name} is not a name this fixture makes")
            try:
                session.run(DROP[kind].format(name=name)).consume()
            except Exception as error:   # the next one is still tried
                left.append((kind, name, type(error).__name__))
    (Path(folder) / STATE).write_text(json.dumps({"created": [[kind, name] for kind, name, _ in reversed(left)]}) + "\n",
                                      encoding="utf-8", newline="\n")
    for kind, name, why in left:
        print(f"left behind: the {kind} {name} ({why}). Remove it by hand, in the system database: {DROP[kind].format(name=name)}")
    return len(left)


def questions_graphs():
    """(alias, file of statements) for the two made-up graphs of the cross-graph questions, and the function that
    reads such a file. Only the builder's data is used. Its own build() makes or reuses databases of fixed names
    and empties them, which is right for its test server and wrong here, so it is not called."""
    import importlib.util
    path = ROOT / "kpi_store" / "tests" / "fixtures" / "questions" / "build_graph.py"
    spec = importlib.util.spec_from_file_location("doc_snippets_questions_build_graph", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [(alias, file_name) for alias, (_, file_name) in module.MEMBERS.items()], module.statements


def questions_up(driver, folder, names=None):
    """A composite database over two new databases, each loaded with one made-up graph. `names` maps composite
    and each alias to the database name to make; a run makes its own."""
    graphs, read = questions_graphs()
    names = names or {key: new_name(key) for key in ["composite"] + [alias for alias, _ in graphs]}
    with driver.session(database="system") as session:
        refuse_taken(session, names.values())
        for alias, _ in graphs:
            make(session, folder, "database", names[alias], f"CREATE DATABASE {names[alias]} WAIT")
        make(session, folder, "composite", names["composite"], f"CREATE COMPOSITE DATABASE {names['composite']} WAIT")
        for alias, _ in graphs:
            make(session, folder, "alias", f"{names['composite']}.{alias}",
                 f"CREATE ALIAS {names['composite']}.{alias} FOR DATABASE {names[alias]}")
    for alias, file_name in graphs:     # each database is new and empty, so nothing is deleted before the load
        with driver.session(database=names[alias]) as session:
            for statement in read(file_name):
                session.run(statement).consume()
    return names


def questions(word):
    folder = fixture_dir()
    with neo4j_driver() as driver:
        if word == "down":
            if remove_created(driver, folder):
                raise Refused("not everything the fixture made could be removed")
            print("removed the composite database and its two databases")
            return
        names = questions_up(driver, folder)
        user = os.environ.get("KPI_STORE_TEST_NEO4J_USER") or "neo4j"
        # The settings file holds no password. The commands read each value from the environment first, so the six
        # variables below decide, whatever the terminal that started the check holds. values.json is in the check's
        # temporary folder, which the check deletes.
        (folder / "questions.toml").write_text(
            f'[neo4j]\nuri = "{os.environ["KPI_STORE_TEST_NEO4J_URI"]}"\nuser = "{user}"\n'
            f'composite = "{names["composite"]}"\ngovernance_alias = "governance"\nbpa_alias = "bpa"\n',
            encoding="utf-8", newline="\n")
        write_values(folder, {"your settings file": "../fixture/questions.toml",
                              "your mapping file": "../fixture/mapping.json", "a folder": "../fixture/answers"},
                     {"KPI_STORE_NEO4J_URI": os.environ["KPI_STORE_TEST_NEO4J_URI"], "KPI_STORE_NEO4J_USER": user,
                      "KPI_STORE_NEO4J_PASSWORD": os.environ["KPI_STORE_TEST_NEO4J_PASSWORD"],
                      "KPI_STORE_NEO4J_COMPOSITE": names["composite"], "KPI_STORE_NEO4J_GOVERNANCE_ALIAS": "governance",
                      "KPI_STORE_NEO4J_BPA_ALIAS": "bpa"})
        print(f"made the composite database {names['composite']} over two made-up graphs")


def scratch_up(driver, folder, name=None):
    """A new database with a few nodes, their relationships and the one constraint that the load and the copy make,
    so that a statement which empties a database has something to delete."""
    name = name or new_name("scratch")
    with driver.session(database="system") as session:
        refuse_taken(session, [name])
        make(session, folder, "database", name, f"CREATE DATABASE {name} WAIT")
    with driver.session(database=name) as session:
        session.run("CREATE CONSTRAINT n10s_unique_uri FOR (r:Resource) REQUIRE r.uri IS UNIQUE").consume()
        session.run("UNWIND range(1, 25) AS i CREATE (:Resource {uri: 'urn:doc-snippets:' + toString(i)})").consume()
        session.run("MATCH (a:Resource), (b:Resource) WHERE a.uri < b.uri AND rand() < 0.2 "
                    "CREATE (a)-[:MADE_UP]->(b)").consume()
    return name


def scratch_database(word):
    folder = fixture_dir()
    with neo4j_driver() as driver:
        if word == "down":
            if remove_created(driver, folder):
                raise Refused("not everything the fixture made could be removed")
            print("removed the throwaway database")
            return
        name = scratch_up(driver, folder)
    print(f"made the database {name} with 25 nodes and the constraint n10s_unique_uri")


# What a Cypher block may start with. A block for the throwaway database empties it and looks at it, as the runbook's
# "How to undo" does. A block for a named database only asks.
CYPHER_STARTS = {"scratch": (r"MATCH\b", r"DROP\s+CONSTRAINT\b", r"SHOW\s+CONSTRAINTS\b"),
                 "read": (r"MATCH\b", r"RETURN\b", r"SHOW\s+CONSTRAINTS\b", r"CALL\s+db\.info\s*\(\s*\)")}
# Words that name or change a database, a server or its accounts. None may stand anywhere in a statement, also not
# inside a subquery: USE would send the statement to another database than the one the session was opened on.
CYPHER_REFUSED = re.compile(r"\b(USE|DATABASES?|ALIAS(?:ES)?|COMPOSITE|GRAPH|SERVERS?|USERS?|ROLES?|PRIVILEGES?|GRANT|DENY|"
                            r"REVOKE|LOAD|START|STOP|ALTER|TERMINATE)\b", re.I)
# One piece of a statement that is not plain code: a string, a name in backticks (a doubled backtick stands for one
# inside the name), or a comment. Read in this order from the left, so a comment mark inside a string is text and a
# quote inside a comment is comment.
CYPHER_PIECE = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`]|``)*`|/\*.*?\*/|//[^\n]*""", re.S)
# CALL and what follows it. `CALL (n) { ... }` and `CALL { ... }` are subqueries, which stay. Anything else is a
# procedure call, and its name is one or more plain names with dots between them.
CYPHER_CALL = re.compile(r"\bCALL\b\s*(?![\s({])", re.I)
CYPHER_PROCEDURE = re.compile(r"[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*")
UNREADABLE = "\x00"   # stands for a name in backticks that is not a plain name; no check reads past it


def cypher_views(statement: str):
    """(the statement for the keyword checks, the statement for the procedure check). Both have no comment, because
    the server reads none, and '' for each string. In the first, a name in backticks is '' too, so a word in a name
    is not read as a keyword. In the second, such a name is the name itself when it is a plain name, as the server
    reads it, so CALL `apoc`.x() is read as a call of apoc.x."""
    def piece(found, names):
        text = found.group(0)
        if text.startswith("/"):
            return " "
        if not text.startswith("`") or not names:
            return "''"
        name = text[1:-1].replace("``", "`")
        return name if re.fullmatch(r"[A-Za-z_]\w*", name) else UNREADABLE
    return (CYPHER_PIECE.sub(lambda found: piece(found, False), statement),
            CYPHER_PIECE.sub(lambda found: piece(found, True), statement))


def check_cypher(statement: str, kind: str) -> str:
    """The statement, or Refused: it may reach only the database its session was opened on. Comments are taken out
    and text inside quotes and backticks is set aside first (cypher_views), so a word in a string is not read as a
    keyword, a keyword cannot hide in one, and a comment or a pair of backticks cannot hide a procedure's name."""
    bare, named = cypher_views(statement)
    if not any(re.match(start, bare.lstrip(), re.I) for start in CYPHER_STARTS[kind]):
        raise Refused(f"a statement here starts with MATCH, {'DROP CONSTRAINT or SHOW CONSTRAINTS' if kind == 'scratch' else 'RETURN, SHOW CONSTRAINTS or CALL db.info()'}: {statement[:60]}")
    word = CYPHER_REFUSED.search(bare)
    if word:
        raise Refused(f"the statement holds {word.group(1).upper()}, which names or changes a database or the server: {statement[:60]}")
    for call in CYPHER_CALL.finditer(named):
        name = CYPHER_PROCEDURE.match(named, call.end())
        if not name or named[name.end():name.end() + 1] in (UNREADABLE, ".", "`"):
            raise Refused(f"the statement holds a CALL whose procedure name cannot be read: {statement[:60]}")
        procedure = re.sub(r"\s", "", name.group(0))
        if procedure.lower() != "db.info":
            raise Refused(f"the statement calls the procedure {procedure}: {statement[:60]}")
    return statement


def cypher(database, path):
    """Runs each statement of the file in the database, as Neo4j Browser does, and prints the rows it returns.
    `scratch` is the database this context's fixture made. Any other name is read only: a statement that writes
    fails there. Every statement is checked first (check_cypher), and none is sent when one is refused."""
    scratch = database == "scratch"
    if scratch:
        made = [name for kind, name in created(fixture_dir()) if kind == "database"]
        if len(made) != 1:
            raise Refused("the throwaway database was not made: run the fixture's `up` first")
        database = made[0]
    checked = [check_cypher(statement, "scratch" if scratch else "read")
               for statement in statements(Path(path).read_text(encoding="utf-8"))]
    from neo4j import READ_ACCESS, WRITE_ACCESS
    with neo4j_driver() as driver:
        with driver.session(database=database, default_access_mode=WRITE_ACCESS if scratch else READ_ACCESS) as session:
            for statement in checked:
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


def write_values(folder, placeholders, env=None):
    (folder / "values.json").write_text(json.dumps({"placeholders": placeholders, "env": env or {}}, indent=2) + "\n",
                                        encoding="utf-8", newline="\n")


def scratch_names(example, catalog, schema):
    """What the documents' names become on the throwaway schemas: the example settings' two schemas, in the
    catalog the documents name, to the fixture's two."""
    return {f"{example.write_catalog}.{example.write_schema}": f"{catalog}.{schema}",
            f"{example.write_catalog}.{example.tech_graph_schema}": f"{catalog}.{schema}_tech"}


DROP_STATEMENT = re.compile(r"DROP\s+(TABLE|VOLUME|SCHEMA)\s+IF\s+EXISTS\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,2})",
                            re.I)


def to_scratch(statement: str, names: dict):
    """(kind, the fixture's name) for a statement of a document, or Refused. A statement is one
    DROP TABLE|VOLUME|SCHEMA IF EXISTS with one name, which is what the runbook's "How to undo" holds. The name
    must be one the documents use, a key of `names` or an object in it; it is replaced by the fixture's. So no
    name a document writes reaches the warehouse, and a statement that names anything else is never sent."""
    found = DROP_STATEMENT.fullmatch(statement.strip())
    if not found:
        raise Refused(f"only one DROP TABLE, DROP VOLUME or DROP SCHEMA with IF EXISTS and one plain name may run here: {statement[:80]}")
    kind, name = found.group(1).upper(), found.group(2)
    for document_name, scratch_name in names.items():
        own = name.lower() == document_name.lower()
        if (own and kind == "SCHEMA") or (kind != "SCHEMA" and name.lower().startswith(document_name.lower() + ".")
                                          and "." not in name[len(document_name) + 1:]):
            return kind, scratch_name + name[len(document_name):]
    raise Refused(f"the statement names {name}: only the throwaway schemas may be changed")


def only_inside(statement: str, schema: str) -> str:
    """The statement, or Refused when it names anything outside one schema. For the statements that the rdf-store
    skill's own code builds for a table of that schema. Text in quotes is set aside; a backtick name is refused,
    because it could spell a name this check does not read."""
    bare = re.sub(r"'(?:[^']|'')*'", "''", statement)
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", bare)
    outside = [name for name in names if not name.lower().startswith(schema.lower() + ".")]
    if "`" in bare or outside or not names:
        raise Refused("the statement names " + (", ".join(outside) or "a quoted name or no table")
                      + f": only tables of {schema} may be used")
    return statement


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
    wanted = [(statement, *to_scratch(statement, names)) for statement in statements(Path(path).read_text(encoding="utf-8"))]
    for statement, kind, name in wanted:     # every statement was checked before the first one is sent
        if not exists(run_sql, kind, name):
            raise Refused(f"{statement} names nothing that a run of the KPI Store makes")
        run_sql(f"DROP {kind} IF EXISTS {name}")
        if exists(run_sql, kind, name):
            raise Refused(f"{statement} left its object in place")
        print("OK: " + statement)


class WarehouseSession:
    """What `spark` is to a block that calls only spark.sql(statement) and reads the result with collect(): each
    statement runs on the rehearsal workspace's SQL warehouse, and may name only the throwaway schema."""

    def __init__(self, run_sql, allowed):
        self.run_sql, self.allowed = run_sql, allowed

    def sql(self, statement):
        rows = self.run_sql(only_inside(statement, self.allowed))

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
