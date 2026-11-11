"""Offline tests of empty_stores.py: no store is contacted."""
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import empty_stores as es  # noqa: E402

SETTINGS = {"NEO4J_URI": "bolt://db.example:7687", "NEO4J_PASSWORD": "p", "EPM_JENA_QUERY": "http://jena.example/ds/query"}


class Session:
    """A Neo4j session holding `held` nodes; a delete takes up to 5000 of them."""

    def __init__(self, held):
        self.held, self.queries = held, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run(self, query):
        self.queries.append(query)
        if "DELETE" in query:
            gone = min(self.held, 5000)
            self.held -= gone
            return mock.Mock(single=lambda: {"c": gone})
        return mock.Mock(single=lambda: {"n": self.held})


class Neo4j(unittest.TestCase):
    def one(self, session, *args):
        opened = []

        def open_session(values):
            opened.append(values.get("NEO4J_DATABASE"))
            return contextlib.nullcontext(), session
        with mock.patch.object(es.ss, "neo4j_session_from", open_session):
            return es.one_store("neo4j", *args), opened

    def test_counting_deletes_nothing(self):
        session = Session(12000)
        self.assertEqual(self.one(session, False, SETTINGS), ({"store": "neo4j", "held": 12000}, [None]))
        self.assertEqual(session.queries, ["MATCH (n) RETURN count(n) AS n"])

    def test_yes_empties_the_named_database_in_batches(self):
        session = Session(12000)
        result, opened = self.one(session, True, SETTINGS, "one")
        self.assertEqual(result, {"store": "neo4j", "database": "one", "held": 12000, "after": 0})
        self.assertEqual(opened, ["one"])
        self.assertEqual(sum("DELETE" in q for q in session.queries), 4)  # 5000, 5000, 2000, then none left

    def test_yes_without_a_database_name_is_refused_before_anything_connects(self):
        def touched(values):
            raise AssertionError("a database was opened")
        with mock.patch.object(es.ss, "neo4j_session_from", touched), self.assertRaisesRegex(SystemExit, "name it with --database"):
            es.one_store("neo4j", True, SETTINGS)

    def test_a_database_other_than_the_settings_is_refused(self):
        def touched(values):
            raise AssertionError("a database was opened")
        with mock.patch.object(es.ss, "neo4j_session_from", touched), self.assertRaisesRegex(SystemExit, "nothing was changed"):
            es.one_store("neo4j", True, SETTINGS | {"NEO4J_DATABASE": "one"}, "two")


class Jena(unittest.TestCase):
    def test_counting_sends_no_update_and_yes_drops_every_graph_of_the_dataset(self):
        sent, held = [], [{"a": 3, "a/shapes": 2}]

        def update(url, statement):
            sent.append((url, statement))
            held[0] = {}
        with mock.patch.object(es.ss, "read_jena", lambda url: held[0]), mock.patch.object(es, "jena_update", update):
            self.assertEqual(es.one_store("jena", False, SETTINGS), {"store": "jena", "held": 5})
            self.assertEqual(sent, [])
            self.assertEqual(es.one_store("jena", True, SETTINGS), {"store": "jena", "held": 5, "after": 0})
        self.assertEqual(sent, [("http://jena.example/ds/query", "DROP ALL")])

    def test_the_update_goes_to_the_update_url_beside_the_query_url(self):
        requests = []

        def urlopen(request, timeout):
            requests.append((request.full_url, request.get_method(), request.data))
            return mock.Mock(close=lambda: None)
        with mock.patch.object(es.urllib.request, "urlopen", urlopen):
            es.jena_update("http://jena.example/ds/query", "DROP ALL")
        self.assertEqual(requests, [("http://jena.example/ds/update", "POST", b"update=DROP+ALL")])


class Main(unittest.TestCase):
    def run_main(self, argv, values=SETTINGS):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(es.ss, "settings", lambda: values):
            code = es.main(argv)
        return code, [json.loads(line) for line in out.getvalue().splitlines()]

    def test_an_unreachable_store_is_reported_without_its_message_and_fails_only_a_delete(self):
        def down(values):
            raise ConnectionError("bolt://db.example:7687 refused")
        with mock.patch.object(es.ss, "neo4j_session_from", down):
            self.assertEqual(self.run_main(["--store", "neo4j"]), (0, [{"store": "neo4j", "unreachable": "ConnectionError"}]))
            self.assertEqual(self.run_main(["--store", "neo4j", "--database", "one", "--yes"]),
                             (1, [{"store": "neo4j", "unreachable": "ConnectionError"}]))

    def test_a_neo4j_refusal_comes_before_any_store_is_emptied(self):
        sent = []
        for argv, values, said in (
                (["--store", "jena", "--store", "neo4j", "--database", "two", "--yes"], SETTINGS | {"NEO4J_DATABASE": "one"},
                 "neo4j: --database two is not the database the settings name; nothing was changed"),
                (["--store", "jena", "--store", "neo4j", "--yes"], SETTINGS,
                 "neo4j: --yes deletes every node of one database; name it with --database")):
            with self.subTest(argv), mock.patch.object(es.ss, "read_jena", lambda url: {"a": 3}), \
                    mock.patch.object(es, "jena_update", lambda url, statement: sent.append(statement)), \
                    self.assertRaises(SystemExit) as stop:
                self.run_main(argv, values)
            self.assertEqual(str(stop.exception), said)
            self.assertEqual(sent, [])   # Jena, named first, was not dropped

    def test_a_missing_setting_is_named(self):
        self.assertEqual(self.run_main(["--store", "jena"], {}), (0, [{"store": "jena", "unreachable": "Unset: EPM_JENA_QUERY"}]))

    def test_databricks_is_not_a_store_this_tool_takes(self):
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stderr(io.StringIO()):
            es.main(["--store", "databricks"])
        self.assertEqual(stop.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
