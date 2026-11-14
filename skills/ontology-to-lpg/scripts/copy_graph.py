#!/usr/bin/env python3
"""Copy a validated projection from the Neo4j that built it to a named database on another Neo4j,
then prove the copy is identical by the graph hash.

The target needs no plugin. n10s and APOC run only where the projection is built and verified
(load_verify.py); this script copies the result with plain Cypher over the Python driver, and calls
neither n10s nor APOC on either server.

Run: uv run --no-project --with rdflib --with neo4j python copy_graph.py \
         (--source-env <file> | --source bolt://<host>:<port>) [--source-database <name>] \
         --target-env <file> [--target-database <name>] --report <projection-report.json> \
         [--batch 1000] [--replace] [--query-timeout <seconds>]
     On Windows, after `python -m pip install rdflib neo4j`: python copy_graph.py ...

--source-env and --target-env each name a file of KEY=VALUE lines, kept outside the repository:
NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD and optionally NEO4J_DATABASE. With --source, the source's
user and password come from the environment instead: NEO4J_PASSWORD, and NEO4J_USERNAME (default
neo4j). --source-database and --target-database name the database on each side and override the
file's NEO4J_DATABASE; without either, the server's default database is used. No password is printed.

What it copies: every :Resource node (labels and properties, the n10s schema nodes included,
because the graph hash and the round trip count them) and every relationship between two :Resource
nodes. It leaves out n10s's own configuration nodes (_GraphConfig, _NsPrefDef,
_n10sValidatorConfig), which have no Resource label. It creates the uniqueness constraint on
:Resource(uri) on the target first, then writes nodes and relationships in batches with UNWIND and
dynamic labels and types (Cypher 5.26 and later).

--report is required: the projection report load_verify.py wrote. The script reads it before it
touches either database and stops (exit 2) unless the report earns its pass: passed alone is not
trusted, and build.report_earned rechecks every field check-report checks except the fingerprints
(the numbers, equal hashes, a passing case for every compiled row, the mutant). It also stops on an
unknown flag, such as the old --expect-hash, and (exit 1, before any write or delete) when the
target is the source database, compared by the id db.info() returns on both, so one server's two
databases are two and one database under two addresses is one. It then hashes the source and stops (exit 1), before writing or deleting anything on
the target, unless that hash equals the report's determinism_hash_sorted: only the verified graph is
copied. It refuses a target that holds any node unless --replace is given, which deletes everything
on the target first (in batches). After the copy it hashes the target exactly as load_verify.py
does and fails unless it equals the source hash. Every printed value is shell-quoted.

Exit 0 when the hashes match, 1 when a copy or check fails, 2 on bad input.

In the KPI Store load, the copy to Neo4j Enterprise (kpi_store/copy_enterprise.py) does not run this command. It
imports this file and calls database_identity, graph_hash and copy on its own two sessions, because it guards the
target more closely than main does: it stops when the target holds a node that is not the KPI Store's, and its
replace deletes only the KPI Store's own nodes, where --replace here deletes every node of the target.
"""
import os
import sys

import build
from shell import Refusal, error_line, q, redact, unverified_report
import load_verify as lv

CONFIG_LABELS = ("_GraphConfig", "_NsPrefDef", "_n10sValidatorConfig")
NODES = ("MATCH (n:Resource) RETURN n.uri AS uri, labels(n) AS labels, properties(n) AS props "
         "ORDER BY n.uri SKIP $skip LIMIT $limit")
# The relationship's own ID ends the order: two relationships of one type between the same two nodes, with no uri,
# tie on everything before it, and a tie could repeat or miss one of them at a page's edge.
EDGES = ("MATCH (a:Resource)-[r]->(b:Resource) RETURN a.uri AS s, type(r) AS t, b.uri AS o, properties(r) AS props "
         "ORDER BY s, t, o, r.uri, elementId(r) SKIP $skip LIMIT $limit")
WRITE_NODES = "UNWIND $rows AS row CREATE (n:$(row.labels)) SET n = row.props"
WRITE_EDGES = ("UNWIND $rows AS row MATCH (a:Resource {uri: row.s}), (b:Resource {uri: row.o}) "
               "CREATE (a)-[r:$(row.t)]->(b) SET r = row.props")


def read_env_file(path):
    """KEY=VALUE lines; blank lines and # comments ignored; quotes around a value removed."""
    values = {}
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep:
                raise Refusal(f"the env file: line {number} is not KEY=VALUE")
            values[key.strip()] = value.strip().strip('"').strip("'")
    missing = [k for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD") if not values.get(k)]
    if missing:
        raise Refusal(f"the env file lacks {', '.join(missing)}")
    return values


def describe_target(values, database=None):
    """The target as it may be printed: never the password, every value shell-quoted. database is the
    one the copy writes to, when it is not the file's own."""
    uri = redact(values["NEO4J_URI"])
    database = database or values.get("NEO4J_DATABASE")
    if database:
        return f"{q(uri)} as {q(values['NEO4J_USERNAME'])} (database {q(database)})"
    return f"{q(uri)} as {q(values['NEO4J_USERNAME'])}"


def source_connection(opts, environ=None):
    """(uri, (user, password), database) of the source: --source-env, or --source with NEO4J_USERNAME
    (default neo4j) and NEO4J_PASSWORD in the environment. --source-database overrides the file's."""
    environ = os.environ if environ is None else environ
    if ("--source" in opts) == ("--source-env" in opts):
        raise Refusal("give exactly one of --source and --source-env")
    if "--source-env" in opts:
        values = read_env_file(opts["--source-env"])
        found = values["NEO4J_URI"], (values["NEO4J_USERNAME"], values["NEO4J_PASSWORD"]), values.get("NEO4J_DATABASE")
    else:
        if not environ.get("NEO4J_PASSWORD"):
            raise Refusal("set NEO4J_PASSWORD to the source's password, or give --source-env")
        found = opts["--source"], (environ.get("NEO4J_USERNAME") or "neo4j", environ["NEO4J_PASSWORD"]), None
    return found[0], found[1], opts.get("--source-database") or found[2] or None


def verified_hash(report_path):
    """The determinism_hash_sorted of a report that earned its pass, or ValueError. passed alone is
    not trusted: build.report_earned recomputes every check that needs no manifest (the numbers,
    equal hashes, a passing case for every compiled row, the mutant)."""
    import json
    with open(report_path, encoding="utf-8") as f:
        rep = json.load(f)
    fails = build.report_earned(rep)
    if fails:
        raise unverified_report(fails)
    return rep["determinism_hash_sorted"]


def database_identity(session):
    """The id Neo4j gives the database a session opens (db.info()): the same database answers with
    the same id whatever URI, host alias or scheme reached it."""
    return session.run("CALL db.info() YIELD id RETURN id").single()["id"]


def batches(session, query, size):
    """The query's rows, one page of `size` at a time, so no request holds the whole graph. The query must take
    $skip and $limit and return its rows in one fixed order, or a page could repeat or miss a row."""
    skip = 0
    while True:
        rows = session.run(query, skip=skip, limit=size).data()
        if not rows:
            return
        yield rows
        skip += size


def graph_hash(session):
    """The hash of the :Resource graph a session reads, computed as load_verify.py computes the report's two hashes,
    so the source, the report and the target are compared on one measure."""
    return lv.hash_graph(session)[0]


def count_nodes(session):
    return session.run("MATCH (n) RETURN count(n) AS n").single()["n"]


def empty_target(session, size):
    """Deletes every node of the target, whatever its label, in transactions of `size` rows, so a large graph does
    not need one transaction that holds all of it. main reaches this only with --replace."""
    session.run(f"MATCH (n) CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS OF {int(size)} ROWS").consume()


def copy(source, target, size):
    """Copies every :Resource node, then every relationship between two of them, in batches of `size`. Returns the
    counts copied. It deletes nothing and does not check the result: the caller clears the target of :Resource
    nodes before and compares the hashes after.

    The constraint comes first. It gives the target the index on :Resource(uri) that each relationship's two
    lookups use, and it makes a second copy into a target that still holds the nodes fail instead of doubling them.
    The nodes come before the relationships because a relationship is created by matching both of its ends."""
    copied = {"nodes": 0, "relationships": 0}
    # Plain Cypher only: the constraint keeps n10s's name, but the target needs no n10s to hold it.
    target.run("CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE").consume()
    for rows in batches(source, NODES, size):
        target.run(WRITE_NODES, rows=[{"labels": r["labels"], "props": r["props"]} for r in rows]).consume()
        copied["nodes"] += len(rows)
    for rows in batches(source, EDGES, size):
        target.run(WRITE_EDGES, rows=rows).consume()
        copied["relationships"] += len(rows)
    return copied


FLAGS = ("--source", "--source-env", "--source-database", "--target-env", "--target-database", "--report",
         "--replace", "--batch", "--query-timeout")


def main(argv):
    try:
        opts, rest = build.options(argv, flags=("--replace",))
        unknown = sorted(set(opts) - set(FLAGS))
        if rest or unknown:
            # Counted, never shown: an unknown option or a stray value is text the user supplied.
            raise Refusal(f"unknown option(s) or argument(s): {len(rest) + len(unknown)}; the flags are "
                          + ", ".join(FLAGS))
        build.need(opts, "--target-env", "--report")
        try:
            size = int(opts.get("--batch", 1000))
        except ValueError:
            raise Refusal("--batch needs a whole number") from None
        if size < 1:   # a page of no rows copies nothing, and the run would end as a failed copy, not as bad input
            raise Refusal("--batch needs a whole number of 1 or more")
        timeout = lv.query_timeout(opts)
        source_uri, source_auth, source_db = source_connection(opts)
        target_values = read_env_file(opts["--target-env"])
        target_db = opts.get("--target-database") or target_values.get("NEO4J_DATABASE") or None
        expected = verified_hash(opts["--report"])
    except (OSError, ValueError) as exc:
        print(f"ERROR {q(error_line('the arguments, an env file or the report could not be read', exc))}",
              file=sys.stderr)
        return 2
    from neo4j import GraphDatabase
    try:
        with GraphDatabase.driver(source_uri, auth=source_auth) as src_driver, \
                GraphDatabase.driver(target_values["NEO4J_URI"],
                                     auth=(target_values["NEO4J_USERNAME"], target_values["NEO4J_PASSWORD"])) as dst_driver:
            with src_driver.session(database=source_db) as raw_source, dst_driver.session(database=target_db) as raw_target:
                # Every statement on either side carries the server-side timeout (load_verify.Timed).
                source, target = lv.Timed(raw_source, timeout), lv.Timed(raw_target, timeout)
                # Compared by the server's own database id, before anything is written or deleted:
                # bolt://127.0.0.1 and bolt://localhost, or neo4j:// and bolt://, can reach one database.
                if database_identity(source) == database_identity(target):
                    print("FAIL the target is the source database (same db.info() id); --replace would delete "
                          "the verified graph. Nothing was written.")
                    return 1
                source_hash = graph_hash(source)
                if source_hash != expected:
                    print(f"FAIL the source graph hash {q(source_hash)} is not the report's {q(expected)}; "
                          "nothing was written to the target")
                    return 1
                present = count_nodes(target)
                if present and not opts.get("--replace"):
                    print(f"FAIL the target {describe_target(target_values, target_db)} holds {q(present)} nodes; "
                          "pass --replace to delete them first")
                    return 1
                if present:
                    empty_target(target, size)
                copied = copy(source, target, size)
                target_hash = graph_hash(target)
    except Exception as exc:  # a driver, network or Cypher error
        # The driver's own text can carry a URI with its password, so only the type is printed.
        print(f"FAIL the copy stopped on a driver, network or Cypher error ({q(type(exc).__name__)}); "
              "the target may hold a partial copy")
        return 1
    print(f"copied {q(copied['nodes'])} nodes and {q(copied['relationships'])} relationships to "
          f"{describe_target(target_values, target_db)}")
    if target_hash != source_hash:
        print(f"FAIL the target hash {q(target_hash)} differs from the source hash {q(source_hash)}")
        return 1
    print(f"the target hash equals the source hash: {q(source_hash)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
