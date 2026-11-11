"""Offline tests of sync_stores.py: no store is contacted."""
import contextlib
import inspect
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sync_stores as ss  # noqa: E402


class Expected(unittest.TestCase):
    def test_the_working_tree_gives_every_catalog_dataset_and_the_manifest_fingerprint(self):
        want = ss.expected()
        datasets = ss.catalog_datasets(ss.repo_file(ss.CATALOG))
        self.assertEqual(want["catalog_datasets"], len(datasets))
        self.assertEqual(want["catalog_datasets"], len(set(datasets)))
        with open(os.path.join(ss.REPO, ss.MANIFEST), encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(want["input_fingerprint"], manifest["input_fingerprint"])

    def test_newest_takes_each_modules_highest_version_numerically(self):
        base = "https://w3id.org/mpc/ontology/modules/"
        iris = [base + "kpi/1.2.0", base + "kpi/1.10.0", base + "core/2.4.0", base + "core/2.3.0"]
        self.assertEqual(ss.newest_releases(iris), [base + "core/2.4.0", base + "kpi/1.10.0"])

    def test_one_newest_release_per_module_in_the_catalog(self):
        want = ss.expected()
        modules = [iri.rsplit("/", 2)[-2] for iri in want["newest"]]
        self.assertEqual(len(modules), len(set(modules)))
        self.assertIn("https://w3id.org/mpc/ontology/modules/kpi/1.3.0", want["newest"])


class Drift(unittest.TestCase):
    want = {"catalog_datasets": 50, "catalog_digest": "d", "input_fingerprint": "f", "newest": [], "jena_graphs": {"g": 1}}

    def marker(self, **over):
        return {"catalog_datasets": 50, "catalog_digest": "d", "input_fingerprint": "f", "count": [4193, 21767],
                "marked_at": "2026-10-29T00:00:00Z", "commit": "abc"} | over

    def statuses(self, markers, live, stores=ss.STORES):
        return {s: status for s, status, _ in ss.drift(markers, live, self.want, stores)}

    def test_each_status(self):
        markers = {"neo4j": self.marker(catalog_digest="old"), "enterprise": self.marker(), "databricks": None}
        live = {"neo4j": [4193, 21767], "enterprise": [0, 0], "jena": {"g": 1}, "databricks": [40169]}
        self.assertEqual(self.statuses(markers, live, ("neo4j", "enterprise", "jena", "databricks")),
                         {"neo4j": "behind", "enterprise": "changed", "jena": "current", "databricks": "unmarked"})
        self.assertEqual(self.statuses({"neo4j": self.marker()}, {"neo4j": [4193, 21767]})["neo4j"], "current")

    def delta(self, held):
        """Databricks' status when its marker and its total row count match, from its rows per graph."""
        want = self.want | {"jena_graphs": {"a": 3, "a/shapes": 2, "a/catalog": 1, "a/m.erstudio": 5, "a/m.layer": 4}}
        live = {"databricks": [sum(held.values())], "databricks_graphs": held}
        return ss.drift({"databricks": self.marker(count=live["databricks"])}, live, want, ("databricks",))[0][1:]

    held = {"a": 3, "a/shapes": 2, "a/catalog": 1, "a/m.erstudio": 5, "a/m.layer": 4}

    def test_delta_with_every_graph_at_its_release_count_reads_current(self):
        self.assertEqual(self.delta(self.held)[0], "current")

    def test_a_missing_package_graph_in_delta_reads_changed_although_the_total_holds(self):
        status, why = self.delta({k: v for k, v in self.held.items() if k != "a/m.layer"} | {"a": 7})
        self.assertEqual((status, "a/m.layer" in why), ("changed", True))

    def test_two_delta_graphs_moved_by_one_each_way_read_changed_although_the_total_holds(self):
        status, why = self.delta(self.held | {"a/m.erstudio": 6, "a/m.layer": 3})
        self.assertEqual((status, "a/m.erstudio" in why), ("changed", True))

    def test_an_extra_delta_graph_reads_changed_although_the_total_holds(self):
        status, why = self.delta(self.held | {"old": 1, "a": 2})
        self.assertEqual((status, "old" in why), ("changed", True))

    def test_delta_rows_in_no_graph_read_changed_and_do_not_crash(self):
        held = ss.rows_per_graph([(None, 2), ("a", 1)])
        self.assertEqual(held, {"(the default graph)": 2, "a": 1})
        status, why = self.delta(self.held | {"(the default graph)": 2, "a": 1})
        self.assertEqual((status, "(the default graph)" in why), ("changed", True))

    def test_jena_is_judged_from_its_graphs_with_no_marker(self):
        want = {"a": 1, "a/shapes": 2}
        self.assertEqual(ss.judge_jena({"a": 1, "a/shapes": 2}, want)[0], "current")
        self.assertEqual(ss.judge_jena({}, want)[0], "empty")
        self.assertEqual(ss.judge_jena({"a": 1}, want)[0], "behind")
        self.assertEqual(ss.judge_jena({"a": 1, "a/shapes": 2, "old": 9}, want)[0], "behind")
        self.assertEqual(ss.judge_jena({"a": 1, "a/shapes": 3}, want)[0], "changed")
        self.assertEqual(ss.judge_jena({"a": 1, "a/shapes": 2, "(the default graph)": 4}, want)[0], "behind")

    def test_a_graph_named_apart_stays_out_of_the_release_comparison(self):
        want, other = {"a": 1}, "urn:example:another-load"
        self.assertEqual(ss.judge_jena({"a": 1, other: 5}, want)[0], "behind")  # a stray, unless the caller names it
        self.assertEqual(ss.judge_jena({"a": 1, other: 5}, want, (other,)), ("current", "1 graphs, 1 triples, each equal to the release files"))
        self.assertEqual(ss.judge_jena({other: 5}, want, (other,))[0], "empty")
        rows = ss.drift({}, {"jena": {"a": 1, other: 5}}, {"jena_graphs": want, "jena_apart": (other,)}, ("jena",))
        self.assertEqual(rows[0][:2], ("jena", "current"))

    def test_an_unreachable_store_says_so_even_with_a_marker(self):
        markers = {s: self.marker() for s in ss.STORES}
        live = {"neo4j": "unreachable (ServiceUnavailable)", "jena": {"g": 1}, "databricks": [4193, 21767]}
        self.assertEqual(self.statuses(markers, live), {"neo4j": "unreachable", "jena": "current", "databricks": "current"})

    def test_every_store_is_reported_and_only_those_named(self):
        self.assertEqual([s for s, _, _ in ss.drift({}, {}, self.want)], ["neo4j", "jena", "databricks"])
        self.assertEqual([s for s, _, _ in ss.drift({}, {}, self.want, ("neo4j",))], ["neo4j"])


class Settings(unittest.TestCase):
    def file(self, text):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8", newline="\n")
        self.addCleanup(os.unlink, tmp.name)
        with tmp:
            tmp.write(text)
        return tmp.name

    def test_the_file_gives_the_values_and_the_environment_wins(self):
        path = self.file("# the stores\nNEO4J_URI=bolt://db.example:7687\nNEO4J_PASSWORD='secret'\n"
                         "NEO4J_DATABASE=one\nEPM_JENA_QUERY=http://jena.example/ds/query\nOTHER=ignored\n")
        self.assertEqual(ss.settings({"EPM_STORES_ENV": path, "NEO4J_DATABASE": "two"}),
                         {"NEO4J_URI": "bolt://db.example:7687", "NEO4J_PASSWORD": "secret", "NEO4J_DATABASE": "two",
                          "EPM_JENA_QUERY": "http://jena.example/ds/query"})

    def test_the_example_file_lists_exactly_the_settings_each_commented_out(self):
        with open(os.path.join(HERE, "skill-run", "environment.example"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        keys = [line[2:].split("=")[0] for line in lines if line.startswith("# ") and "=" in line and line[2:].split("=")[0].isupper()]
        self.assertEqual(keys, ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE", "EPM_JENA_QUERY"])
        self.assertEqual(tuple(keys), ss.SETTINGS)
        self.assertEqual(ss.read_env(os.path.join(HERE, "skill-run", "environment.example")), {})  # nothing is set as shipped

    def test_nothing_set_gives_no_address_at_all(self):
        self.assertEqual(ss.settings({}), {})  # no default points at a local port

    def test_a_missing_setting_is_named_before_anything_connects(self):
        with self.assertRaises(ss.Unset) as stop:
            ss.neo4j_session_from({"NEO4J_URI": "bolt://db.example:7687"})
        self.assertEqual(str(stop.exception), "NEO4J_PASSWORD")
        self.assertEqual(ss.reason(stop.exception), "unreachable (Unset: NEO4J_PASSWORD)")

    def test_a_reason_never_carries_an_errors_message(self):
        self.assertEqual(ss.reason(ConnectionError("bolt://db.example:7687 refused")), "unreachable (ConnectionError)")

    def test_the_session_opens_the_database_the_settings_name(self):
        opened = []
        driver = mock.Mock(session=lambda database=None: opened.append(database) or "session")
        fake = mock.Mock(GraphDatabase=mock.Mock(driver=lambda uri, auth: opened.append((uri, auth)) or driver))
        with mock.patch.dict(sys.modules, {"neo4j": fake}):
            ss.neo4j_session_from({"NEO4J_URI": "bolt://db.example:7687", "NEO4J_PASSWORD": "p", "NEO4J_DATABASE": "one"})
            ss.neo4j_session_from({"NEO4J_URI": "bolt://db.example:7687", "NEO4J_PASSWORD": "p", "NEO4J_USERNAME": "u"})
        self.assertEqual(opened, [("bolt://db.example:7687", ("neo4j", "p")), "one",
                                  ("bolt://db.example:7687", ("u", "p")), None])


class Reading(unittest.TestCase):
    def test_check_reads_and_judges_only_the_stores_named(self):
        def touched(*a, **k):
            raise AssertionError("a store was read for a check that did not name it")
        with mock.patch.object(ss, "neo4j_session_from", touched), mock.patch.object(ss, "read_jena", lambda url: {"g": 1}):
            markers, live, models = ss.read_stores(("jena",), {"EPM_JENA_QUERY": "http://jena.example/ds/query"})
        self.assertEqual((markers, live, models), ({"jena": None}, {"jena": {"g": 1}}, {}))

    def test_a_store_with_no_setting_or_no_answer_reads_as_unreachable_not_a_crash(self):
        markers, live, models = ss.read_stores(("neo4j", "jena"), {})
        self.assertEqual(live, {"neo4j": "unreachable (Unset: NEO4J_URI)", "jena": "unreachable (Unset: EPM_JENA_QUERY)"})
        self.assertEqual(models, {"neo4j": "unreachable (Unset: NEO4J_URI)"})

        def down(values):
            raise ConnectionError("bolt://db.example:7687 refused")
        with mock.patch.object(ss, "neo4j_session_from", down):
            self.assertEqual(ss.read_stores(("neo4j",), {})[1], {"neo4j": "unreachable (ConnectionError)"})

    def test_jena_counts_each_graph_and_names_the_default_graph_only_when_it_holds_triples(self):
        asked = []

        def select(default):
            def run(url, query):
                asked.append(url)
                if "GRAPH ?g" in query:
                    return [{"g": {"value": "a"}, "n": {"value": "3"}}, {"g": {"value": "a/shapes"}, "n": {"value": "2"}}]
                return [{"n": {"value": str(default)}}]
            return run
        with mock.patch.object(ss, "jena_select", select(0)):
            self.assertEqual(ss.read_jena("http://jena.example/ds/query"), {"a": 3, "a/shapes": 2})
        with mock.patch.object(ss, "jena_select", select(4)):
            self.assertEqual(ss.read_jena("http://jena.example/ds/query"), {"a": 3, "a/shapes": 2, "(the default graph)": 4})
        self.assertEqual(set(asked), {"http://jena.example/ds/query"})

    def run_main(self, argv, read):
        want = {"catalog_datasets": 50, "catalog_digest": "d", "input_fingerprint": "f", "newest": [], "jena_graphs": {"g": 1}}
        refs, out = [], io.StringIO()
        with mock.patch.object(ss, "read_stores", read), mock.patch.object(ss, "settings", lambda: {}), \
                mock.patch.object(ss, "expected_for", lambda ref, stores: refs.append(ref) or want), \
                mock.patch("logical_models.check", lambda markers, ref=None: refs.append(ref) or []), \
                mock.patch("sys.stdout", out):
            code = ss.main(argv)
        return code, refs, [line.split()[:2] for line in out.getvalue().splitlines()]

    def test_check_reads_this_tree_by_default_and_fails_when_a_store_is_not_current(self):
        named = []

        def read(stores, values, name):
            named.append((stores, name))
            return {}, {"jena": {"g": 1}}, {}
        code, refs, lines = self.run_main(["check"], read)
        self.assertEqual((code, refs), (1, ["worktree", "worktree"]))  # no Git ref unless one is named
        self.assertEqual(lines, [["neo4j", "unmarked"], ["jena", "current"]])
        code, refs, lines = self.run_main(["check", "--store", "jena", "--ref", "v1"], read)
        self.assertEqual((code, refs, lines), (0, ["v1", "v1"], [["jena", "current"]]))
        self.assertEqual(named, [(("neo4j", "jena"), "neo4j"), (("jena",), "neo4j")])

    def test_check_prints_an_lm_line_and_fails_when_a_logical_model_is_not_current(self):
        want = {"catalog_datasets": 1, "catalog_digest": "d", "input_fingerprint": "f", "newest": []}
        marker = want | {"count": [1, 2], "marked_at": "t", "commit": "c"}
        out = io.StringIO()
        with mock.patch.object(ss, "read_stores", lambda stores, values, name: ({"neo4j": marker}, {"neo4j": [1, 2]}, {"neo4j": None})), \
                mock.patch.object(ss, "expected_for", lambda ref, stores: want), \
                mock.patch("logical_models.check", lambda markers, ref=None: [(s, "unmarked", "") for s in markers]):
            self.assertIs(ss.check(("neo4j",), "worktree", {}, out=out), False)
        self.assertEqual([line.split() for line in out.getvalue().splitlines()], [["neo4j", "current", "marked", "t", "at", "commit", "c"],
                                                                                  ["lm:neo4j", "unmarked"]])

    def test_the_commands_are_expected_check_and_mark_and_nothing_reloads(self):
        for gone in (["sync"], ["check", "--cloud"], ["check", "--store", "databricks"]):
            with self.assertRaises(SystemExit) as stop, contextlib.redirect_stderr(io.StringIO()):
                ss.main(gone)
            self.assertEqual(stop.exception.code, 2, gone)


class ReleaseGraphs(unittest.TestCase):
    def test_the_release_graphs_are_the_run_configurations(self):
        with open(os.path.join(HERE, "skill-run", "epm-run.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg["release_graphs"], ["shapes", "catalog"])
        self.assertEqual(ss.RELEASE_GRAPHS, ("shapes", "catalog"))

    def test_a_current_jena_holds_every_newest_release_three_times_and_each_package_graph(self):
        newest = ss.newest_releases(ss.catalog_datasets(ss.repo_file(ss.CATALOG)))
        want = ss.jena_graphs(newest)
        extra = {g for iri in newest for g in ss.package_graphs(iri)}  # the releases' package graphs, if any
        self.assertEqual(len(want), 3 * len(newest) + len(extra))
        self.assertTrue(all(want.values()))
        self.assertEqual({f"{iri}/{n}" for iri in newest for n in ("shapes", "catalog")} | set(newest) | extra, set(want))


class OntologyLabelsOnly(unittest.TestCase):
    """A subgraph, the marker and the release records share a Neo4j database with the ontology. This pins the exact
    Cypher of the counts, which reads :Resource nodes and the edges between them, so none of those moves them. The
    skill's test_release_record.py pins the hash and the round trip."""

    def test_the_counts_read_resource_nodes_and_the_edges_between_them(self):
        queries = []

        class Session:
            def run(self, query):
                queries.append(query)
                return mock.Mock(single=lambda: {"n": 0})
        self.assertEqual(ss.resource_counts(Session()), (0, 0))
        self.assertEqual(queries, ["MATCH (n:Resource) RETURN count(n) AS n", "MATCH (:Resource)-[r]->(:Resource) RETURN count(r) AS n"])


class Session:
    """A Neo4j session that holds the given counts, release records and marker, and records what is written."""

    def __init__(self, nodes, edges, records, marker=None):
        self.nodes, self.edges, self.records, self.marker, self.written = nodes, edges, records, marker, []

    def run(self, query, **params):
        if query.startswith("MERGE"):
            self.written.append((query, params))
            return mock.Mock(consume=lambda: None)
        if "ModuleRelease" in query:
            return mock.Mock(value=lambda: self.records)
        if "EpmStoreMarker" in query:
            held = self.marker if self.marker and self.marker.get("store") == params["s"] else None
            return mock.Mock(single=lambda: {"p": held} if held else None)
        return mock.Mock(single=lambda: {"n": self.nodes if "(n:Resource)" in query else self.edges})


class Neo4jMarker(unittest.TestCase):
    want = {"catalog_datasets": 50, "catalog_digest": "d", "input_fingerprint": "f", "newest": ["a", "b"]}

    def setUp(self):
        with open(ss.REPORT, encoding="utf-8") as f:
            self.report = json.load(f)

    def session(self, nodes=0, edges=0, records=("b", "a"), marker=None):
        return Session(self.report["nodes"] + nodes, self.report["relationships"] + edges, list(records), marker)

    def test_counts_equal_to_the_committed_report_and_one_record_per_release_pass(self):
        self.assertEqual((self.report["nodes"], self.report["relationships"]), (4237, 22312))
        self.assertEqual(ss.neo4j_checked("neo4j", self.session(), self.want), [4237, 22312])

    def test_other_counts_or_records_are_refused(self):
        with self.assertRaisesRegex(SystemExit, "relationships"):
            ss.neo4j_checked("neo4j", self.session(edges=1), self.want)
        with self.assertRaisesRegex(SystemExit, "release record"):
            ss.neo4j_checked("neo4j", self.session(records=["a"]), self.want)

    def test_mark_writes_the_marker_only_after_the_check_and_under_the_name_given(self):
        session = self.session()
        with mock.patch.object(ss, "now", lambda: "2026-11-11T00:00:00Z"), mock.patch.object(ss, "commit", lambda: "abc12345"):
            written = ss.mark_neo4j(session, "enterprise", self.want)
        marker = {"catalog_datasets": 50, "catalog_digest": "d", "input_fingerprint": "f", "marked_at": "2026-11-11T00:00:00Z",
                  "commit": "abc12345", "store": "enterprise", "count": [4237, 22312]}
        self.assertEqual(written, marker)
        self.assertEqual(session.written, [("MERGE (m:EpmStoreMarker {store: $s}) SET m = $p", {"s": "enterprise", "p": marker})])
        refused = self.session(nodes=1)
        with self.assertRaises(SystemExit):
            ss.mark_neo4j(refused, "enterprise", self.want)
        self.assertEqual(refused.written, [])

    def test_the_marker_is_read_by_its_name_with_the_live_counts(self):
        held = {"store": "enterprise", "count": [4237, 22312]}
        self.assertEqual(ss.read_neo4j(self.session(marker=held), "enterprise"), (held, [4237, 22312]))
        self.assertEqual(ss.read_neo4j(self.session(marker=held)), (None, [4237, 22312]))  # the default name is neo4j

    def test_the_neo4j_marker_is_never_a_resource(self):
        source = inspect.getsource(ss)
        self.assertEqual(ss.MARKER_LABEL, "EpmStoreMarker")
        self.assertNotIn(":EpmStoreMarker:Resource", source)
        self.assertNotRegex(source, r"\(m:Resource")

    def test_a_marker_has_the_fields_every_store_shares(self):
        want = self.want | {"jena_graphs": {"a": 3}}
        self.assertEqual(ss.marker(want, "databricks", [6], "KPI Store 1.1 0f0f", "2026-11-11T00:00:00Z"),
                         {"catalog_datasets": 50, "catalog_digest": "d", "input_fingerprint": "f", "marked_at": "2026-11-11T00:00:00Z",
                          "commit": "KPI Store 1.1 0f0f", "store": "databricks", "count": [6]})
        self.assertEqual((ss.TRIPLES_TABLE, ss.MARKER_TABLE), ("epm_triples", "epm_store_markers"))


class CheckedRows(unittest.TestCase):
    """A load that stopped part way, with every graph present, must not be marked current."""
    want = {"newest": ["a"], "jena_graphs": {"a": 3, "a/shapes": 2, "a/catalog": 1}}

    def test_a_table_with_every_graph_at_its_release_count_passes(self):
        self.assertEqual(ss.checked_rows({"a": 3, "a/shapes": 2, "a/catalog": 1}, self.want), [6])

    def test_a_partial_load_with_every_graph_present_is_refused(self):
        with self.assertRaisesRegex(SystemExit, "another row count"):
            ss.checked_rows({"a": 2, "a/shapes": 2, "a/catalog": 1}, self.want)

    def test_a_missing_or_stray_graph_is_refused(self):
        with self.assertRaisesRegex(SystemExit, "lacks 1 graph"):
            ss.checked_rows({"a": 3, "a/shapes": 2}, self.want)
        with self.assertRaisesRegex(SystemExit, "holds 1 other"):
            ss.checked_rows({"a": 3, "a/shapes": 2, "a/catalog": 1, "old": 4}, self.want)


class WithoutGit(unittest.TestCase):
    def test_a_tree_without_git_has_no_commit_and_reads_its_own_files(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ss, "REPO", tmp):
            with open(os.path.join(tmp, "a.txt"), "w", encoding="utf-8", newline="\n") as f:
                f.write("held\n")
            self.assertEqual(ss.commit(), "unknown (not a Git checkout)")

            def git(*a, **k):
                raise AssertionError("Git was run in a tree without Git")
            with mock.patch.object(ss.subprocess, "run", git):
                self.assertEqual((ss.repo_file("a.txt"), ss.repo_file("a.txt", "worktree")), ("held\n", "held\n"))
                self.assertEqual(ss.repo_bytes("a.txt", "worktree"), b"held\n")


if __name__ == "__main__":
    unittest.main()
