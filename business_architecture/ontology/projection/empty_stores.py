"""Counts what a Neo4j database or a Jena dataset holds and, with --yes, empties it before a clean reload.

    python3 empty_stores.py --store neo4j --store jena                                   # counts only: changes nothing
    python3 empty_stores.py --store neo4j --database <name> --store jena --yes           # deletes, then counts again

Without --yes it writes nothing. The addresses and the Neo4j login come from sync_stores.settings.
In Neo4j, --yes deletes every node of one database, so it also needs --database with that database's name, and
refuses when the settings name another one. In Jena it drops every graph of the dataset.
It never touches Databricks: the load that writes the triple table replaces it.
Prints one JSON line per store, with no login value. A store that cannot be read says "unreachable" and the error's
name. With --yes, a store that cannot be read fails the command.
Needs neo4j for Neo4j (uv run --with neo4j ...).

No step of the KPI Store runner calls this file: each store load replaces what it loaded before. It is a tool to run
by hand, for a store that must start empty. The stores are handled in the order the --store options name them, and
one store's deletion is not undone when a later store fails or is refused.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

import sync_stores as ss


def neo4j_counts(session):
    return session.run("MATCH (n) RETURN count(n) AS n").single()["n"]


def empty_neo4j(session):
    """Deletes in batches, so a store of any size fits one transaction per batch. Returns the nodes deleted.
    It deletes every node, whatever its label: the ontology, each subgraph beside it and every marker."""
    deleted = 0
    while True:
        n = session.run("MATCH (n) WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS c").single()["c"]
        deleted += n
        if n == 0:
            return deleted


def jena_update(query_url, statement):
    """Sends one SPARQL Update to the dataset whose query URL this is; its update URL sits beside it."""
    url = query_url.rsplit("/", 1)[0] + "/update"
    body = urllib.parse.urlencode({"update": statement}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=120).close()


def one_store(store, yes, values, database=None):
    """One store's count and, with yes, its count after emptying, as the JSON line's dict.

    For Neo4j the two refusals come before the connection is opened. The settings may name no database, and the
    server's default could then be any database, so --yes must name the one to empty. When the settings do name a
    database, a --database that differs from it is refused, so a mistyped name does not empty another database on
    the same server. When the settings name none, --database is the only check: the database it names is emptied."""
    if store == "jena":
        query_url = ss.need(values, "EPM_JENA_QUERY")
        held = sum(ss.read_jena(query_url).values())
        if yes:
            jena_update(query_url, "DROP ALL")
            return {"store": store, "held": held, "after": sum(ss.read_jena(query_url).values())}
        return {"store": store, "held": held}
    if yes and not database:
        raise SystemExit("neo4j: --yes deletes every node of one database; name it with --database")
    if database and values.get("NEO4J_DATABASE") not in (None, database):
        raise SystemExit(f"neo4j: --database {database} is not the database the settings name; nothing was changed")
    driver, session = ss.neo4j_session_from(values | ({"NEO4J_DATABASE": database} if database else {}))
    with driver, session:
        held = neo4j_counts(session)
        named = {"database": database} if database else {}
        if yes:
            empty_neo4j(session)
            return {"store": store, **named, "held": held, "after": neo4j_counts(session)}
        return {"store": store, **named, "held": held}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--store", action="append", required=True, choices=ss.READ_HERE)
    ap.add_argument("--database", help="neo4j: the database to count or empty; --yes needs it")
    ap.add_argument("--yes", action="store_true", help="delete; without it, count only")
    args = ap.parse_args(argv)
    values = ss.settings()
    failed = False
    for store in args.store:
        try:
            print(json.dumps(one_store(store, args.yes, values, args.database)))
        except Exception as err:  # the reason, never a value: a driver's message can carry an address
            failed = failed or args.yes  # a store that did not answer was not emptied
            print(json.dumps({"store": store, "unreachable": ss.reason(err)[len("unreachable ("):-1]}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
