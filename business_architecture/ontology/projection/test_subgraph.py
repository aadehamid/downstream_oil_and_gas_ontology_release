"""Offline tests of subgraph.py: no store is contacted."""
import datetime as dt
import hashlib
import os
import sys
import types
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import subgraph as sg  # noqa: E402

NODES = [{"labels": ["LogicalModel", "Entity"], "props": {"uri": "urn:e:1", "name": "Account"}},
         {"labels": ["LogicalModel", "Attribute"], "props": {"uri": "urn:a:1", "name": "Account_Name"}}]
EDGES = [{"s": "urn:e:1", "t": "HAS_ATTRIBUTE", "o": "urn:a:1", "ontology": False, "p": {}},
         {"s": "urn:e:1", "t": "DESCRIBES", "o": "urn:r:1", "ontology": True, "p": {}}]


class Names(unittest.TestCase):
    def test_a_local_name_is_what_follows_the_last_separator(self):
        self.assertEqual(sg.local_name("http://www.w3.org/2001/XMLSchema#string"), "string")
        self.assertEqual(sg.local_name("https://w3id.org/mpc/ontology/modules/logical-model/inModel"), "inModel")
        self.assertEqual(sg.local_name("urn:example:PrimaryKey"), "PrimaryKey")

    def test_an_edge_type_is_the_predicates_local_name_in_upper_snake_case(self):
        self.assertEqual(sg.edge_type("https://w3id.org/mpc/ontology/modules/logical-model/inModel"), "IN_MODEL")
        self.assertEqual(sg.edge_type("http://www.w3.org/ns/prov#wasGeneratedBy"), "WAS_GENERATED_BY")
        self.assertEqual(sg.edge_type("urn:example:describes"), "DESCRIBES")

    def test_values_take_the_types_bolt_has(self):
        self.assertEqual(sg.neo4j_value(dt.date(2026, 11, 11)), "2026-11-11")
        self.assertEqual(sg.neo4j_value(dt.datetime(2026, 11, 11, 8, 30)), "2026-11-11T08:30:00")
        whole, part = sg.neo4j_value(Decimal("3.0")), sg.neo4j_value(Decimal("3.5"))
        self.assertEqual((whole, type(whole), part, type(part)), (3, int, 3.5, float))
        self.assertEqual((sg.neo4j_value("text"), sg.neo4j_value(True), sg.neo4j_value(7)), ("text", True, 7))


class Fingerprint(unittest.TestCase):
    def test_it_is_the_sha_256_of_these_lines_sorted(self):
        # Written by hand: one JSON line per node (labels sorted, keys sorted) and per edge (no properties, so none).
        lines = ['["urn:e:1", "DESCRIBES", "urn:r:1", true]',
                 '["urn:e:1", "HAS_ATTRIBUTE", "urn:a:1", false]',
                 '{"labels": ["Attribute", "LogicalModel"], "p": {"name": "Account_Name", "uri": "urn:a:1"}}',
                 '{"labels": ["Entity", "LogicalModel"], "p": {"name": "Account", "uri": "urn:e:1"}}']
        self.assertEqual(hashlib.sha256("\n".join(lines).encode()).hexdigest(),
                         "5079411053d5653b52db79f41db23cfcd524165b50ffef5ca1ea42edd3394a13")
        self.assertEqual(sg.fingerprint(NODES, EDGES), "5079411053d5653b52db79f41db23cfcd524165b50ffef5ca1ea42edd3394a13")

    def test_the_rows_to_load_and_the_rows_a_store_returns_give_one_fingerprint_in_any_order(self):
        live = [{"labels": list(reversed(n["labels"])), "p": dict(n["props"])} for n in reversed(NODES)]
        self.assertEqual(sg.fingerprint(live, list(reversed(EDGES))), sg.fingerprint(NODES, EDGES))

    def test_a_changed_property_label_edge_or_edge_property_changes_it(self):
        base = sg.fingerprint(NODES, EDGES)
        renamed = [{**NODES[0], "props": {**NODES[0]["props"], "name": "edited by hand"}}, NODES[1]]
        relabelled = [{**NODES[0], "labels": ["LogicalModel", "Key"]}, NODES[1]]
        retyped = [{**EDGES[0], "t": "HAS_KEY"}, EDGES[1]]
        with_props = [{**EDGES[0], "p": {"name": "connected by Account_Id"}}, EDGES[1]]
        to_ontology = [{**EDGES[0], "ontology": True}, EDGES[1]]
        prints = {sg.fingerprint(renamed, EDGES), sg.fingerprint(relabelled, EDGES), sg.fingerprint(NODES, retyped),
                  sg.fingerprint(NODES, with_props), sg.fingerprint(NODES, to_ontology), sg.fingerprint(NODES, EDGES[:1])}
        self.assertEqual(len(prints), 6)
        self.assertNotIn(base, prints)


class Tx:
    """A transaction that records its statements. `found` says how many of an edge statement's rows find a target;
    `counts` are the ontology's counts, one pair per reading."""

    def __init__(self, found=lambda rows: len(rows), counts=((4237, 22312), (4237, 22312))):
        self.queries, self.found, self.counts = [], found, [n for pair in counts for n in pair]

    def run(self, query, **params):
        self.queries.append((query, params))
        if query.startswith("MATCH (n:Resource)") or query.startswith("MATCH (:Resource)"):
            n = self.counts.pop(0)
        else:
            n = self.found(params.get("rows", [])) if "CREATE (a)" in query else 0
        return types.SimpleNamespace(consume=lambda: None, single=lambda: {"n": n}, value=lambda: [])


class Replace(unittest.TestCase):
    marker = {"store": "neo4j", "digest": "d" * 64}

    def replace(self, tx, edge_props=True):
        return sg.replace_subgraph(tx, "neo4j", "LogicalModel", "LogicalModelMarker", NODES, EDGES, self.marker, "model", edge_props)

    def test_the_statements_run_in_this_order_and_the_marker_is_written_last(self):
        tx = Tx()
        self.assertEqual(self.replace(tx), ({"model": 1, "ontology": 1}, (4237, 22312)))
        self.assertEqual([q for q, _ in tx.queries], [
            "MATCH (n:Resource) RETURN count(n) AS n",
            "MATCH (:Resource)-[r]->(:Resource) RETURN count(r) AS n",
            "MATCH (m:LogicalModelMarker) DETACH DELETE m",
            "MATCH (n:LogicalModel) DETACH DELETE n",
            "UNWIND $rows AS row CREATE (n:$(row.labels)) SET n = row.props",
            "UNWIND $rows AS row MATCH (a:LogicalModel {uri: row.s}), (b:LogicalModel {uri: row.o}) "
            "CREATE (a)-[r:$(row.t)]->(b) SET r = row.p RETURN count(*) AS n",
            "UNWIND $rows AS row MATCH (a:LogicalModel {uri: row.s}), (b:Resource {uri: row.o}) "
            "CREATE (a)-[r:$(row.t)]->(b) SET r = row.p RETURN count(*) AS n",
            "MATCH (n:Resource) RETURN count(n) AS n",
            "MATCH (:Resource)-[r]->(:Resource) RETURN count(r) AS n",
            "CREATE (m:LogicalModelMarker) SET m = $p"])
        self.assertEqual(tx.queries[-1][1], {"p": self.marker})
        self.assertEqual((tx.queries[5][1]["rows"], tx.queries[6][1]["rows"]), ([EDGES[0]], [EDGES[1]]))

    def test_edges_without_properties_set_none(self):
        tx = Tx()
        self.replace(tx, edge_props=False)
        self.assertTrue(tx.queries[5][0].endswith("CREATE (a)-[:$(row.t)]->(b) RETURN count(*) AS n"))

    def test_an_edge_with_no_target_stops_before_the_marker_and_names_the_target(self):
        tx = Tx(found=lambda rows: 0)
        with self.assertRaisesRegex(SystemExit, r"neo4j: 1 model edges found no target, e.g. \['urn:a:1'\]; nothing was changed"):
            self.replace(tx)
        self.assertFalse(any(q.startswith("CREATE (m:") for q, _ in tx.queries))

    def test_a_move_in_the_ontologys_counts_stops_before_the_marker(self):
        tx = Tx(counts=((4237, 22312), (4237, 22311)))
        with self.assertRaisesRegex(SystemExit, r"the ontology's counts changed from \(4237, 22312\) to \(4237, 22311\)"):
            self.replace(tx)
        self.assertFalse(any(q.startswith("CREATE (m:") for q, _ in tx.queries))

    def test_the_read_queries_name_the_label_and_return_the_rows_fingerprint_takes(self):
        self.assertEqual(sg.node_query("LogicalModel"), "MATCH (n:LogicalModel) RETURN labels(n) AS labels, properties(n) AS p")
        self.assertEqual(sg.edge_query("LogicalModel"), "MATCH (a:LogicalModel)-[r]->(b) RETURN a.uri AS s, type(r) AS t, "
                                                        "b.uri AS o, b:Resource AS ontology, properties(r) AS p")


if __name__ == "__main__":
    unittest.main()
