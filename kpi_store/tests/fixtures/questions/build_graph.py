"""Builds the made-up test graphs on a Neo4j Enterprise test server: two databases, one composite database
over them with two aliases, and the two fixture graphs.

    python kpi_store/tests/fixtures/questions/build_graph.py --uri bolt://127.0.0.1:17811 --user neo4j

The password comes from the environment variable KPI_STORE_TEST_NEO4J_PASSWORD. Run it only against a test
server: it replaces what the two databases hold. It refuses a database that holds any node without the
fixture's madeUp property, so a real graph is never replaced.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPOSITE = "enterpriseknowledgegraph"
MEMBERS = {"governance": ("governancemetadata", "governance.cypher"),
           "bpa": ("businessprocessarchitecturegraph", "bpa.cypher")}


def statements(name: str) -> list[str]:
    with (HERE / name).open(encoding="utf-8", newline="\n") as f:
        lines = [line for line in f.read().splitlines() if not line.startswith("//")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def build(driver) -> None:
    with driver.session(database="system") as session:
        for database, _ in MEMBERS.values():
            session.run(f"CREATE DATABASE {database} IF NOT EXISTS WAIT").consume()
        session.run(f"CREATE COMPOSITE DATABASE {COMPOSITE} IF NOT EXISTS WAIT").consume()
        for alias, (database, _) in MEMBERS.items():
            session.run(f"CREATE ALIAS {COMPOSITE}.{alias} IF NOT EXISTS FOR DATABASE {database}").consume()
    for database, file_name in MEMBERS.values():
        with driver.session(database=database) as session:
            real = session.run("MATCH (n) WHERE n.madeUp IS NULL RETURN count(n) AS nodes").single()["nodes"]
            if real:
                raise SystemExit(f"refused: database {database} holds {real} nodes that are not the fixture's")
            session.run("MATCH (n) DETACH DELETE n").consume()
            for statement in statements(file_name):
                session.run(statement).consume()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--uri", required=True)
    parser.add_argument("--user", default="neo4j")
    args = parser.parse_args(argv)
    password = os.environ.get("KPI_STORE_TEST_NEO4J_PASSWORD")
    if not password:
        raise SystemExit("set KPI_STORE_TEST_NEO4J_PASSWORD to the test server's password")
    from neo4j import GraphDatabase
    with GraphDatabase.driver(args.uri, auth=(args.user, password),
                              notifications_min_severity="OFF") as driver:
        build(driver)
    print("built the made-up governance and KPI Store graphs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
