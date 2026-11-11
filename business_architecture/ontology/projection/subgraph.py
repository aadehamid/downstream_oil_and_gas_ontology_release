"""A subgraph that shares a Neo4j database with the ontology and stays apart from it.

The ontology's nodes carry the label Resource. A subgraph has its own label on every node (LogicalModel, for example)
and one marker node that says which files it was loaded from. The projection's counts, hash and round trip read
Resource nodes only, so a subgraph never moves them. logical_models.py loads the logical models through this module.
The KPI Store's technical graph (kpi_store/tech_graph.py) is loaded the same way, under its own label and marker.

This module is a library with no command. It reads and writes only through the session or transaction it is given.
It creates and deletes only nodes that carry the subgraph's label or its marker's label, and the relationships that
start at a subgraph node. Such a relationship may end at a Resource node. It also reads Resource nodes: it counts
them and the relationships between them, and matches them as the ends of those relationships. It creates, changes
and deletes no Resource node and no relationship between two Resource nodes.

Needs only the standard library. The session or transaction comes from the caller.
"""
import datetime as dt
import hashlib
import json
import re
from decimal import Decimal


def local_name(iri):
    """The part of an IRI after its last #, / or :."""
    return re.split(r"[#/:]", str(iri))[-1]


def edge_type(predicate):
    """A predicate's relationship type: readsFrom gives READS_FROM, prov:wasGeneratedBy gives WAS_GENERATED_BY."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", local_name(predicate)).upper()


def neo4j_value(value):
    """A literal as Neo4j stores it. Dates become ISO text. A decimal becomes an integer when whole and a float
    otherwise, because Bolt has no decimal type."""
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, str):
        return str(value)  # rdflib returns a language-tagged label as a Literal
    return value


def ontology_counts(session):
    """What the projection counts: Resource nodes and the relationships between them."""
    nodes = session.run("MATCH (n:Resource) RETURN count(n) AS n").single()["n"]
    edges = session.run("MATCH (:Resource)-[r]->(:Resource) RETURN count(r) AS n").single()["n"]
    return nodes, edges


def node_query(label):
    """The Cypher that reads a subgraph's nodes as the rows fingerprint takes."""
    return f"MATCH (n:{label}) RETURN labels(n) AS labels, properties(n) AS p"


def edge_query(label):
    """The Cypher that reads a subgraph's edges, with each edge's properties, as the rows fingerprint takes."""
    return (f"MATCH (a:{label})-[r]->(b) RETURN a.uri AS s, type(r) AS t, b.uri AS o, b:Resource AS ontology, "
            "properties(r) AS p")


def replace_subgraph(tx, store, label, marker_label, nodes, edges, marker, kind, edge_props=False):
    """Replaces a subgraph and its marker inside the caller's transaction.

    Every node labelled `label` and the one node labelled `marker_label` go. Then `nodes` ({"labels", "props"}) are
    created. Each of `edges` ({"s", "t", "o", "ontology"}, with "p" for its properties when edge_props) starts at a
    node of the subgraph. It ends at another node of the subgraph (a `kind` edge) or at an ontology node.
    Raises SystemExit, before anything commits, when an edge finds no target or the ontology's counts move.
    Returns ({kind: edges made, "ontology": edges made}, the ontology's counts).

    Nothing here commits. The function relies on its caller to commit after it returns and to roll back when it
    raises; both callers in this release do. The old subgraph and its marker then stay until the new one passed its
    checks, and the words "nothing was changed" in the messages below are true. The marker is created last, so
    inside the transaction no marker exists for a subgraph that failed a check. Edges are created by MATCH on both
    ends, so an edge whose end is missing creates nothing. The check is a count: edges made against rows sent. It
    assumes one node per uri, and it does not see an edge whose "ontology" value is neither true nor false, which
    belongs to neither pass."""
    before = ontology_counts(tx)   # compared with the counts at the end: a check by count, not by content
    tx.run(f"MATCH (m:{marker_label}) DETACH DELETE m").consume()
    tx.run(f"MATCH (n:{label}) DETACH DELETE n").consume()
    tx.run("UNWIND $rows AS row CREATE (n:$(row.labels)) SET n = row.props", rows=nodes).consume()
    create = "CREATE (a)-[r:$(row.t)]->(b) SET r = row.p" if edge_props else "CREATE (a)-[:$(row.t)]->(b)"
    made = {kind: 0, "ontology": 0}
    for each, target in ((kind, label), ("ontology", "Resource")):
        rows = [e for e in edges if e["ontology"] == (each == "ontology")]
        made[each] = tx.run(f"UNWIND $rows AS row MATCH (a:{label} {{uri: row.s}}), (b:{target} {{uri: row.o}}) "
                            f"{create} RETURN count(*) AS n", rows=rows).single()["n"]
        if made[each] != len(rows):
            found = set(tx.run(f"UNWIND $uris AS u MATCH (b:{target} {{uri: u}}) RETURN b.uri AS u",
                               uris=sorted({e["o"] for e in rows})).value())
            missing = sorted({e["o"] for e in rows} - found)
            raise SystemExit(f"{store}: {len(rows) - made[each]} {each} edges found no target, e.g. {missing[:5]}; "
                             "nothing was changed")
    after = ontology_counts(tx)
    if before != after:
        raise SystemExit(f"{store}: the ontology's counts changed from {before} to {after}; nothing was changed")
    tx.run(f"CREATE (m:{marker_label}) SET m = $p", p=marker).consume()
    return made, after


def fingerprint(nodes, edges):
    """A subgraph's content as one SHA-256, the same from the rows to load and from the rows a store returns.

    Nodes are {"labels", "p"} (what node_query returns) or {"labels", "props"} (the rows to load). Edges are
    {"s", "t", "o", "ontology"}, with "p" for an edge's properties, which count when it has any.

    Each node and edge becomes one line of JSON with sorted keys, and the lines are sorted before they are hashed.
    So the order the rows arrive in, which a database does not promise, never changes the result."""
    lines = [json.dumps({"labels": sorted(n["labels"]), "p": n.get("p", n.get("props"))}, sort_keys=True, default=str)
             for n in nodes]
    lines += [json.dumps([e["s"], e["t"], e["o"], bool(e["ontology"])] + ([e["p"]] if e.get("p") else []),
                         sort_keys=True, default=str) for e in edges]
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()
