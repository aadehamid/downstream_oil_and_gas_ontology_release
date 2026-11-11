"""Stand-ins for the local stores, for the tests: local settings written to a temporary folder, a Neo4j session
that answers the statements the KPI Store sends from a small in-memory graph, and a Fuseki store over a dataset in
memory. Every name and value is made up."""
import json
import re
from pathlib import Path

from kpi_store import local_settings as ls
from kpi_store.tests import support

STORES_TEXT = (support.ROOT / "kpi_store" / "stores.example.toml").read_text(encoding="utf-8")


def local_settings(folder, release_root=None, environ=None, **replace):
    """LocalSettings from the example file, written into folder, with whole lines replaced by key:
    local_settings(tmp, database='database = "other"'). A key that occurs twice is replaced everywhere."""
    text = STORES_TEXT.replace("C:/kpi-store-local", Path(folder).as_posix())
    for key, line in replace.items():
        text, n = re.subn(rf"(?m)^{key} = .*$", line, text)
        assert n >= 1, key
    Path(folder).mkdir(parents=True, exist_ok=True)
    path = Path(folder) / "stores.toml"
    path.write_text(text, encoding="utf-8", newline="\n")
    settings = Path(folder) / "kpi_store.toml"
    if not settings.exists():
        settings.write_text(support.SETTINGS_TEXT, encoding="utf-8", newline="\n")
    return ls.load(path, environ or {}, release_root or support.ROOT)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def single(self):
        return self.rows[0] if self.rows else None

    def data(self):
        return self.rows

    def value(self):
        return [next(iter(r.values())) for r in self.rows]

    def consume(self):
        return None


def owns(labels, props, params):
    """Whether a node is the KPI Store's, written out by hand for the stand-in database: the label and what only
    the KPI Store's load writes on such a node."""
    def under(value):
        return isinstance(value, str) and any(value.startswith(b) for b in params["bases"])
    projected = all(label == "Resource" or label.startswith(tuple(params["prefixes"])) for label in labels)
    return bool(("Resource" in labels and props.get("uri") is not None and under(props.get("graph")) and projected)
                or ("ModuleRelease" in labels and under(props.get("version_iri")))
                or ("Module" in labels and under(props.get("uri")))
                or ("EpmStoreMarker" in labels and props.get("store") == params["store"] and props.get("catalog_digest") is not None)
                or ("LogicalModel" in labels and str(props.get("uri") or "").startswith(tuple(params["lm_bases"]) or ("\0",))
                    and all(label in params["lm_labels"] for label in labels)
                    and (props.get("slug") in params["lm_slugs"]
                         or bool(props.get("models")) and all(m in params["lm_slugs"] for m in props["models"])))
                or ("LogicalModelMarker" in labels and props.get("store") == params["store"] and props.get("digest") is not None)
                or ("Tech" in labels and str(props.get("uri") or "").startswith(params["tech_base"])
                    and all(label == "Tech" or label in params["tech_classes"] for label in labels))
                or ("TechGraphMarker" in labels and props.get("store") == params["store"] and props.get("digest") is not None))


class FakeNeo4j:
    """One database: nodes as (labels, properties), a count of relationships between Resource nodes, and a name.
    run() answers the statements below and fails on any other, so a new statement cannot pass unseen."""

    def __init__(self, name="neo4j", ident="db-1"):
        self.name, self.ident = name, ident
        self.nodes = []          # [(labels, props)]
        self.relationships = 0   # between Resource nodes
        self.statements = []
        self.closed = False

    def add(self, labels, n=1, **props):
        self.nodes += [(list(labels), dict(props)) for _ in range(n)]

    def count(self, label):
        return sum(1 for labels, _ in self.nodes if label in labels)

    def writes(self):
        return [s for s in self.statements if re.search(r"\b(CREATE|MERGE|DELETE|SET|DROP)\b", s)]

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def run(self, query, parameters=None, **kwargs):
        text = " ".join(getattr(query, "text", query).split())
        params = dict(parameters or {}, **kwargs)
        self.statements.append(text)
        if text.startswith("CALL db.info() YIELD name"):
            return Result([{"name": self.name}])
        if text.startswith("CALL db.info() YIELD id"):
            return Result([{"id": self.ident}])
        if text.startswith("MATCH (n) WITH labels(n) AS labels, coalesce((n:Resource AND ") and text.endswith("RETURN own, labels, count(*) AS n"):
            groups = {}
            for labels, props in self.nodes:
                key = (owns(labels, props, params), tuple(labels))
                groups[key] = groups.get(key, 0) + 1
            return Result([{"own": own, "labels": list(labels), "n": n} for (own, labels), n in groups.items()])
        if text.startswith("MATCH (n) WHERE NOT coalesce((n:Resource AND ") and text.endswith("LIMIT 5"):
            foreign = [(l, p) for l, p in self.nodes if not owns(l, p, params)]
            return Result([{"labels": list(l), "uri": p.get("uri")} for l, p in foreign[:5]])
        if text.startswith("MATCH (n) WHERE coalesce((n:Resource AND ") and text.endswith("CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 1000 ROWS"):
            self.nodes = [(l, p) for l, p in self.nodes if not owns(l, p, params)]
            return Result([])
        if text == "MATCH (n) RETURN count(n) AS n":
            return Result([{"n": len(self.nodes)}])
        if text == "MATCH (n:Resource) RETURN count(n) AS n":
            return Result([{"n": self.count("Resource")}])
        if text == "MATCH (:Resource)-[r]->(:Resource) RETURN count(r) AS n":
            return Result([{"n": self.relationships}])
        if text == "MATCH (r:ModuleRelease) RETURN r.version_iri AS iri":
            return Result([{"iri": p["version_iri"]} for labels, p in self.nodes if "ModuleRelease" in labels])
        if text == "MATCH (m:EpmStoreMarker {store: $s}) RETURN properties(m) AS p":
            found = [p for labels, p in self.nodes if "EpmStoreMarker" in labels and p.get("store") == params["s"]]
            return Result([{"p": found[0]}] if found else [])
        if text == "MERGE (m:EpmStoreMarker {store: $s}) SET m = $p":
            self.nodes = [(l, p) for l, p in self.nodes if not ("EpmStoreMarker" in l and p.get("store") == params["s"])]
            self.nodes.append((["EpmStoreMarker"], json.loads(json.dumps(params["p"]))))
            return Result([])
        raise AssertionError(f"the fake Neo4j does not know this statement: {text[:160]}")


class FakeDriver:
    """A driver over named FakeNeo4j databases. It records the database each session was opened on."""

    def __init__(self, databases, default="neo4j"):
        self.databases, self.default, self.opened = databases, default, []

    def session(self, database=None):
        self.opened.append(database)
        if (database or self.default) not in self.databases:
            raise LookupError("no such database")
        return self.databases[database or self.default]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


class FakeFuseki:
    """A Graph Store Protocol store in memory, with the methods rdfstore.FusekiStore has. It records its writes."""

    update_url, query_url = "http://fuseki.invalid/ds/update", "http://fuseki.invalid/ds/query"

    def __init__(self, rdfstore, alter=False):
        import pyoxigraph as ox
        self.ox, self.rs = ox, rdfstore
        self.dataset = ox.Dataset()
        self.writes = []
        self.alter = alter   # change one triple as the dataset is published, as a faulty store would

    def graphs(self):
        return self.rs.named_graphs(self.dataset)

    def add(self, graph, n=1):
        target = self.ox.DefaultGraph() if graph is None else self.ox.NamedNode(graph)
        for i in range(n):
            self.dataset.add(self.ox.Quad(self.ox.NamedNode(f"urn:sample:s{i}"), self.ox.NamedNode("urn:sample:p"),
                                          self.ox.Literal("made up"), target))

    def _drop(self, graph):
        for quad in list(self.dataset.quads_for_graph_name(graph)):
            self.dataset.remove(quad)

    def _request(self, url, method="GET", data=None, headers=None):
        if url == self.query_url:
            n = len(list(self.dataset.quads_for_graph_name(self.ox.DefaultGraph())))
            return 200, json.dumps({"results": {"bindings": [{"n": {"value": str(n)}}]}}).encode()
        assert url == self.update_url and method == "POST", url
        for statement in data.decode("utf-8").split(" ;\n"):
            self.writes.append(statement)
            m = re.match(r"DROP SILENT GRAPH <([^>]+)>$", statement)
            if m:
                self._drop(self.ox.NamedNode(m.group(1)))
            elif statement == "DROP SILENT DEFAULT":
                self._drop(self.ox.DefaultGraph())
            else:
                raise AssertionError(f"the fake Fuseki does not know this update: {statement[:80]}")
        return 200, b""

    def publish(self, dataset):
        self.writes.append("publish")
        for graph in self.rs.named_graphs(dataset):
            self._drop(self.ox.NamedNode(graph))
        for i, quad in enumerate(dataset):
            if self.alter and i == 0:
                quad = self.ox.Quad(quad.subject, quad.predicate, self.ox.Literal("altered"), quad.graph_name)
            self.dataset.add(quad)

    def export(self):
        return self.ox.Dataset(self.dataset)
