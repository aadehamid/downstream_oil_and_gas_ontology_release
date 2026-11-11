"""Offline tests of logical_models.py (the decision of 2026-11-02, amendment "the stores"): no store is contacted. The package is
built in a temporary folder from the module's made-up example, the way a release's cut lays it out."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import logical_models as lm  # noqa: E402
import subgraph as sg  # noqa: E402
import sync_stores as ss  # noqa: E402

EXAMPLE = os.path.join(ss.REPO, "business_architecture", "ontology", "logical-model", "example")
SLUG = "example-logical-model"
VERSION_IRI = "https://w3id.org/mpc/ontology/modules/logical-model/1.0.0"
ER = "https://www.erstudio.com/semanticmodel/"


class Package(unittest.TestCase):
    """A repository root in a temporary folder whose releases hold logical-model 1.0.0 with the example model."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.folder = os.path.join(self.root, "business_architecture", "ontology", "releases", lm.MODULE, "1.0.0")
        os.makedirs(self.folder)
        names = {"logical-model.ttl": os.path.join(EXAMPLE, "..", "vocabulary.ttl"),
                 "shapes.ttl": os.path.join(EXAMPLE, "..", "shapes.ttl"),
                 f"{SLUG}.erstudio.ttl": os.path.join(EXAMPLE, f"{SLUG}.erstudio.ttl"),
                 f"{SLUG}.layer.ttl": os.path.join(EXAMPLE, f"{SLUG}.layer.ttl")}
        for name, source in names.items():
            shutil.copy(source, os.path.join(self.folder, name))
        with open(os.path.join(self.folder, "catalog.ttl"), "w") as f:
            f.write(f"<{VERSION_IRI}/catalog> <http://www.w3.org/ns/dcat#dataset> <{VERSION_IRI}> .\n")
        self.write_manifest([*names, "catalog.ttl", "logical-model.jsonld", "CHANGELOG.md"])
        for patch in (mock.patch.object(ss, "REPO", self.root), mock.patch.object(lm, "RELEASES", os.path.dirname(os.path.dirname(self.folder)))):
            patch.start()
            self.addCleanup(patch.stop)

    def write_manifest(self, files):
        with open(os.path.join(self.folder, "manifest.json"), "w") as f:
            json.dump({"module": lm.MODULE, "version": "1.0.0", "files": {n: "0" * 64 for n in files}}, f)

    def rows(self):
        return lm.graph_rows(lm.models([VERSION_IRI]))


class Held(unittest.TestCase):
    def test_this_release_holds_the_logical_model_package_and_held_agrees_with_the_catalog(self):
        self.assertIs(lm.held(), True)
        graphs = lm.package_graphs()
        self.assertEqual(lm.held(), bool(graphs))
        self.assertTrue(all(g.startswith("https://w3id.org/mpc/ontology/modules/logical-model/") for g in graphs), sorted(graphs))

    def test_releases_with_no_package_graph_load_nothing_and_report_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIs(lm.held(os.path.join(tmp, "none")), False)

        def touched(*a, **k):
            raise AssertionError("a store was contacted")
        out = io.StringIO()
        with mock.patch.object(lm, "newest", lambda ref=None: ["https://w3id.org/mpc/ontology/modules/kpi/1.3.0"]), \
                mock.patch.object(ss, "neo4j_session_from", touched), mock.patch.object(lm, "rdfstore", touched), \
                mock.patch("sys.stdout", out):
            lm.load(("neo4j", "jena"), {})
            self.assertEqual(lm.check({"neo4j": None}), [])
            self.assertEqual(lm.package_rows(), {"graphs": {}, "counts": {}, "rows": []})
        self.assertIn("nothing to load", out.getvalue())


class PackageGraphs(Package):
    def test_the_manifest_names_the_package_graphs_and_nothing_else(self):
        want = {f"{VERSION_IRI}/{SLUG}.erstudio": f"business_architecture/ontology/releases/{lm.MODULE}/1.0.0/{SLUG}.erstudio.ttl",
                f"{VERSION_IRI}/{SLUG}.layer": f"business_architecture/ontology/releases/{lm.MODULE}/1.0.0/{SLUG}.layer.ttl"}
        self.assertEqual(ss.package_graphs(VERSION_IRI, "worktree"), want)
        self.assertTrue(lm.held())
        self.assertEqual(lm.models([VERSION_IRI]), [(SLUG, want[f"{VERSION_IRI}/{SLUG}.erstudio"], want[f"{VERSION_IRI}/{SLUG}.layer"])])

    def test_a_current_jena_and_delta_hold_each_package_graph_with_the_files_triple_count(self):
        from rdflib import Graph
        want = ss.jena_graphs([VERSION_IRI], "worktree")
        self.assertEqual(set(want), {VERSION_IRI, f"{VERSION_IRI}/shapes", f"{VERSION_IRI}/catalog",
                                     f"{VERSION_IRI}/{SLUG}.erstudio", f"{VERSION_IRI}/{SLUG}.layer"})
        self.assertEqual(want[f"{VERSION_IRI}/{SLUG}.erstudio"], len(Graph().parse(os.path.join(EXAMPLE, f"{SLUG}.erstudio.ttl"))))
        held = dict(want)
        del held[f"{VERSION_IRI}/{SLUG}.layer"]
        self.assertEqual(ss.judge_jena(held, want)[0], "behind")  # a reload without the model graphs

    def test_a_model_without_its_layer_stops_the_load(self):
        self.write_manifest(["logical-model.ttl", "shapes.ttl", "catalog.ttl", f"{SLUG}.erstudio.ttl"])
        with self.assertRaisesRegex(SystemExit, "lacks its layer"):
            lm.models([VERSION_IRI])

    def test_a_release_set_without_the_module_has_no_model(self):
        self.assertEqual(lm.models(["https://w3id.org/mpc/ontology/modules/kpi/1.3.0"]), [])


class Subgraph(Package):
    def test_every_node_is_a_logical_model_node_and_none_is_a_resource(self):
        nodes, _ = self.rows()
        kinds = {}
        for n in nodes:
            self.assertEqual(n["labels"][0], lm.LABEL)
            self.assertNotIn("Resource", n["labels"])
            kinds.setdefault(n["labels"][1], []).append(n["props"])
        self.assertEqual({k: len(v) for k, v in kinds.items()}, {"Model": 1, "Entity": 3, "Attribute": 7, "Key": 3})
        account = next(p for p in kinds["Entity"] if p["erstudio_id"] == "101")
        self.assertEqual((account["name"], account["models"]), ("Example_Account_Dim", [SLUG]))
        self.assertTrue(account["description"].startswith("An invented table of example accounts"))
        name = next(p for p in kinds["Attribute"] if p["name"] == "Account_Name")
        self.assertEqual((name["datatype"], name["business_term"]), ("string", ER + "Term_Example_Account_Name"))
        self.assertEqual(sorted(p["key_type"] for p in kinds["Key"]), ["AlternateKey", "PrimaryKey", "PrimaryKey"])

    def test_the_edges_hold_the_attributes_keys_relationships_and_the_layers_links(self):
        _, edges = self.rows()
        types = {}
        for e in edges:
            types.setdefault(e["t"], []).append(e)
        self.assertEqual({t: len(v) for t, v in types.items()},
                         {"IN_MODEL": 3, "HAS_ATTRIBUTE": 7, "HAS_KEY": 3, "ON_ATTRIBUTE": 3, "RELATES_TO": 1,
                          "SOURCE_SYSTEM": 2, "DESCRIBES": 2, "IMPLEMENTED_BY": 1})
        relates = types["RELATES_TO"][0]  # ER Studio's inverse twin is left out
        self.assertEqual((relates["s"], relates["o"], relates["p"]["name"]),
                         (ER + "example_core_Example_Account_Dim", ER + "example_core_Example_Contact_Dim", "connected by Account_Id"))
        self.assertTrue(all(e["ontology"] for t in ("SOURCE_SYSTEM", "DESCRIBES", "IMPLEMENTED_BY") for e in types[t]))
        self.assertFalse(any(e["ontology"] for t in ("IN_MODEL", "HAS_ATTRIBUTE", "HAS_KEY", "ON_ATTRIBUTE") for e in types[t]))
        self.assertIn("https://w3id.org/mpc/ontology/modules/party/CustomerAccount", {e["o"] for e in types["DESCRIBES"]})

    def test_the_digest_covers_each_model_file_by_name_and_content(self):
        files = lm.models([VERSION_IRI])
        first = lm.digest(files)
        with open(os.path.join(self.folder, f"{SLUG}.layer.ttl"), "a") as f:
            f.write("\n# changed\n")
        self.assertNotEqual(lm.digest(files), first)


class Tx:
    """A Neo4j transaction that records its statements and finds every edge's target."""

    def __init__(self):
        self.queries, self.state = [], "open"

    def run(self, query, **params):
        self.queries.append((query, params))
        n = len(params.get("rows", [])) if "CREATE (a)" in query else 0
        return types.SimpleNamespace(consume=lambda: None, single=lambda: {"n": n}, value=lambda: [])

    def commit(self):
        self.state = "committed"

    def rollback(self):
        self.state = "rolled back"

    def closed(self):
        return self.state != "open"


class Loading(Package):
    def session(self, tx):
        class Session:
            def begin_transaction(self):
                return tx

            def run(self, *a, **k):
                raise AssertionError("a write outside the transaction")
        return Session()

    def test_neo4j_gets_the_subgraph_and_its_marker_in_one_committed_transaction_apart_from_resource(self):
        tx = Tx()
        with mock.patch("sys.stdout", io.StringIO()):
            lm.load_neo4j(self.session(tx), lm.models([VERSION_IRI]))
        self.assertEqual(tx.state, "committed")
        queries = [q for q, _ in tx.queries]
        self.assertIn("MATCH (m:LogicalModelMarker) DETACH DELETE m", queries)
        self.assertIn("MATCH (n:LogicalModel) DETACH DELETE n", queries)
        created = next(p["rows"] for q, p in tx.queries if q.startswith("UNWIND $rows AS row CREATE (n:"))
        self.assertTrue(all(r["labels"][0] == "LogicalModel" and "Resource" not in r["labels"] for r in created))
        edge_queries = [q for q in queries if "CREATE (a)" in q]
        self.assertEqual(len(edge_queries), 2)
        self.assertTrue(all("SET r = row.p" in q for q in edge_queries))
        self.assertIn("(b:LogicalModel {uri: row.o})", edge_queries[0])
        self.assertIn("(b:Resource {uri: row.o})", edge_queries[1])
        marker = tx.queries[-1]
        self.assertEqual(marker[0], "CREATE (m:LogicalModelMarker) SET m = $p")
        self.assertEqual((marker[1]["p"]["digest"], marker[1]["p"]["models"], marker[1]["p"]["store"], marker[1]["p"]["nodes"]),
                         (lm.digest(lm.models([VERSION_IRI])), [SLUG], "neo4j", 14))

    def test_an_edge_with_no_target_rolls_back_and_writes_no_marker(self):
        tx = Tx()
        tx.run = lambda query, **params: (tx.queries.append((query, params)) or
                                          types.SimpleNamespace(consume=lambda: None, single=lambda: {"n": 0}, value=lambda: []))
        with self.assertRaisesRegex(SystemExit, "edges found no target"):
            lm.load_neo4j(self.session(tx), lm.models([VERSION_IRI]))
        self.assertEqual(tx.state, "rolled back")
        self.assertFalse(any(q.startswith("CREATE (m:LogicalModelMarker)") for q, _ in tx.queries))

    def fake_rdfstore(self, published):
        class Fuseki:
            def __init__(self, gsp, query, update):
                published.append(("store", gsp, query, update))

            def publish(self, dataset):
                published.append(("publish", dataset))
        return types.SimpleNamespace(pack=lambda paths, named: sorted(named.values()), FusekiStore=Fuseki,
                                     to_rows=lambda dataset: [("s", "p", "o", "iri", None, None, g) for g in dataset])

    def test_jena_gets_every_package_graph_in_one_update_under_its_graph_iri(self):
        published = []
        graphs = lm.package_graphs([VERSION_IRI])
        with mock.patch("sys.stdout", io.StringIO()):
            lm.load_jena(self.fake_rdfstore(published), graphs, "http://jena.example/ds/query")
        self.assertEqual(published, [("store", "http://jena.example/ds/data", "http://jena.example/ds/query", "http://jena.example/ds/update"),
                                     ("publish", [f"{VERSION_IRI}/{SLUG}.erstudio", f"{VERSION_IRI}/{SLUG}.layer"])])

    def test_the_triple_tables_load_gets_the_graphs_their_counts_and_their_rows_with_no_connection(self):
        from rdflib import Graph
        found = lm.package_rows(self.fake_rdfstore([]), [VERSION_IRI])
        export, layer = f"{VERSION_IRI}/{SLUG}.erstudio", f"{VERSION_IRI}/{SLUG}.layer"
        self.assertEqual(found["graphs"], {export: f"business_architecture/ontology/releases/logical-model/1.0.0/{SLUG}.erstudio.ttl",
                                           layer: f"business_architecture/ontology/releases/logical-model/1.0.0/{SLUG}.layer.ttl"})
        self.assertEqual(found["counts"], {export: len(Graph().parse(os.path.join(EXAMPLE, f"{SLUG}.erstudio.ttl"))),
                                           layer: len(Graph().parse(os.path.join(EXAMPLE, f"{SLUG}.layer.ttl")))})
        self.assertEqual(found["rows"], [("s", "p", "o", "iri", None, None, export), ("s", "p", "o", "iri", None, None, layer)])

    def test_the_real_row_format_gives_one_row_per_triple_of_each_package_graph(self):
        try:
            rs = lm.rdfstore()
        except ImportError:
            self.skipTest("pyoxigraph is not installed")
        found = lm.package_rows(rs, [VERSION_IRI])
        per_graph = {}
        for row in found["rows"]:
            per_graph[row[6]] = per_graph.get(row[6], 0) + 1  # the graph column is the last of rdfstore.COLUMNS
        self.assertEqual(rs.COLUMNS[6], "graph")
        self.assertEqual(per_graph, found["counts"])

    def test_load_sends_each_store_its_part_at_the_address_the_settings_name(self):
        calls = []
        session = contextlib.nullcontext()
        with mock.patch.object(lm, "newest", lambda ref=None: [VERSION_IRI]), mock.patch.object(lm, "rdfstore", lambda skills: "rs"), \
                mock.patch.object(lm, "load_jena", lambda rs, g, url: calls.append(("jena", rs, sorted(g), url))), \
                mock.patch.object(ss, "neo4j_session_from", lambda values: (contextlib.nullcontext(), session)), \
                mock.patch.object(lm, "load_neo4j", lambda s, files: calls.append(("neo4j", s, [f[0] for f in files]))):
            lm.load(("neo4j", "jena"), {"EPM_JENA_QUERY": "http://jena.example/ds/query"})
            with self.assertRaises(ss.Unset):
                lm.load(("jena",), {})
        graphs = [f"{VERSION_IRI}/{SLUG}.erstudio", f"{VERSION_IRI}/{SLUG}.layer"]
        self.assertEqual(calls, [("jena", "rs", graphs, "http://jena.example/ds/query"), ("neo4j", session, [SLUG])])


class Drift(Package):
    def session(self, nodes, edges, marker):
        class Result(list):
            def single(self):
                return self[0] if self else None

        class Session:
            def run(_, query, **kw):
                if "LogicalModelMarker" in query:
                    return Result([{"p": marker}] if marker else [])
                return Result(nodes if query == "MATCH (n:LogicalModel) RETURN labels(n) AS labels, properties(n) AS p" else edges)
        return Session()

    def status(self, nodes, edges, marker):
        with mock.patch.object(lm, "newest", lambda ref=None: [VERSION_IRI]):
            return lm.check({"neo4j": lm.read_marker(self.session(nodes, edges, marker))})

    def test_each_status(self):
        nodes, edges = self.rows()
        live = [{"labels": n["labels"], "p": dict(n["props"])} for n in nodes]
        marker = {"digest": lm.digest(lm.models([VERSION_IRI])), "marked_at": "t"}
        self.assertEqual([r[:2] for r in self.status(live, edges, marker)], [("neo4j", "current")])
        live[1]["p"]["description"] = "edited by hand"
        self.assertEqual(self.status(live, edges, marker)[0][1], "changed")
        self.assertEqual(self.status(live, edges, {**marker, "digest": "e" * 64})[0][1], "behind")
        self.assertEqual(self.status(live, edges, None)[0][1], "unmarked")
        edited = [dict(e) for e in edges]
        relates = next(e for e in edited if e["t"] == "RELATES_TO")
        relates["p"] = {**relates["p"], "name": "renamed"}
        self.assertEqual(self.status([{"labels": n["labels"], "p": dict(n["props"])} for n in nodes], edited, marker)[0][1], "changed")

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        subprocess.run(["git", "-C", self.root, *args], check=True, capture_output=True, env=env)

    def commit_catalog(self, with_package):
        """Writes the repository's catalog, with or without the package's dataset, and commits the tree; returns the commit."""
        catalog = os.path.join(self.root, ss.CATALOG)
        with open(catalog, "w") as f:
            f.write(f"<{VERSION_IRI}/../catalog> <http://www.w3.org/ns/dcat#dataset> <{VERSION_IRI}> .\n" if with_package else "")
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", "c")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        return subprocess.run(["git", "-C", self.root, "rev-parse", "HEAD"], capture_output=True, text=True, env=env).stdout.strip()

    def lines(self, ref):
        return [r[:2] for r in lm.check({"neo4j": None}, ref)]  # a database whose subgraph was wiped: no marker

    def test_the_lm_line_follows_the_ref_that_holds_the_package_not_the_working_tree(self):
        self.git("init", "-q")
        ref = self.commit_catalog(with_package=True)
        shutil.rmtree(self.folder)  # the tree has no package; the ref does
        with open(os.path.join(self.root, ss.CATALOG), "w") as f:
            f.write("")
        self.assertEqual(self.lines(ref), [("neo4j", "unmarked")])
        self.assertEqual(self.lines("worktree"), [])

    def test_the_lm_line_follows_a_ref_that_holds_no_package_though_the_working_tree_does(self):
        self.git("init", "-q")
        ref = self.commit_catalog(with_package=False)
        with open(os.path.join(self.root, ss.CATALOG), "w") as f:
            f.write(f"<{VERSION_IRI}/../catalog> <http://www.w3.org/ns/dcat#dataset> <{VERSION_IRI}> .\n")
        self.assertEqual(self.lines(ref), [])
        self.assertEqual(self.lines("worktree"), [("neo4j", "unmarked")])

    def test_a_database_that_could_not_be_read_says_so(self):
        with mock.patch.object(lm, "newest", lambda ref=None: [VERSION_IRI]):
            self.assertEqual(lm.check({"neo4j": "unreachable (ServiceUnavailable)", "enterprise": None})[0],
                             ("neo4j", "unreachable", "unreachable (ServiceUnavailable)"))
            self.assertEqual([r[:2] for r in lm.check({"neo4j": "unreachable (ServiceUnavailable)", "enterprise": None})],
                             [("neo4j", "unreachable"), ("enterprise", "unmarked")])


if __name__ == "__main__":
    unittest.main()
