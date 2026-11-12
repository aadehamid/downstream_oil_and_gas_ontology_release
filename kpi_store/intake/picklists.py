"""Builds the intake form's pick lists from the release packages, and reads the built file back.

The forms offer a list wherever the ontology already holds the answers: the business areas, the process tree, the
measures, the roles and so on. build() reads the newest package of each module and returns the lists, with a
term index for the check of names. The build command writes the result to kpi-intake/pick-lists.json. The check
and the forms read that file, so they need no rdflib and agree with each other.

Every item has an `id` (the term's IRI, or a module's name) and a `label` (what a person sees). Labels are unique
within a list, because a workbook cell holds the label and the reader must find the id again.

A deprecated term stays in its list with "(deprecated)" in its label, so the lists count what the ontology holds.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from kpi_store import ontology_view

BASE = "https://w3id.org/mpc/ontology/"
CORE = BASE + "modules/core/"
KPI = BASE + "modules/kpi/"
VS = BASE + "modules/value-stream/"
DP = BASE + "modules/data-product/"
SYSTEM = BASE + "modules/system/"
AUTHORITY = BASE + "modules/authority/"
SKOS = "http://www.w3.org/2004/02/skos/core#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
DCTERMS = "http://purl.org/dc/terms/"
ORG_ROLE = "http://www.w3.org/ns/org#Role"
OWL_DEPRECATED = "http://www.w3.org/2002/07/owl#deprecated"
FILE = "pick-lists.json"
LABEL_LIMIT = 200   # a workbook's list validation compares at most 255 characters, so a long title is cut


class Release:
    """The newest package of every module, parsed once. Needs rdflib."""

    def __init__(self, root):
        from rdflib import Graph
        self.root = Path(root)
        releases = self.root / ontology_view.RELEASES
        if not releases.is_dir():
            raise ontology_view.ReleaseError(f"{releases} is missing")
        self.versions = ontology_view.newest_versions(releases)
        self.graphs = {}
        for module, version in self.versions.items():
            path = releases / module / version / f"{module}.ttl"
            if not path.is_file():
                raise ontology_view.ReleaseError(f"{path} is missing")
            self.graphs[module] = Graph().parse(path, format="turtle")

    def graph(self, module):
        if module not in self.graphs:
            raise ontology_view.ReleaseError(f"the release holds no {module} package")
        return self.graphs[module]

    def text(self, module, subject, predicate):
        """One literal of a term as text, or "" when the term has none. The first in text order when it has several."""
        from rdflib import URIRef
        values = sorted(str(o) for o in self.graph(module).objects(URIRef(subject), URIRef(predicate)))
        return values[0] if values else ""

    def texts(self, module, subject, predicate):
        from rdflib import URIRef
        return sorted(str(o) for o in self.graph(module).objects(URIRef(subject), URIRef(predicate)))

    def subjects(self, module, predicate, obj):
        from rdflib import URIRef
        return sorted(str(s) for s in self.graph(module).subjects(URIRef(predicate), URIRef(obj)))

    def instances(self, module, cls):
        return self.subjects(module, RDF_TYPE, cls)

    def deprecated(self, module, subject):
        return bool(self.text(module, subject, OWL_DEPRECATED))


def _unique_labels(items):
    """Makes each label unique in its list, by adding the end of the id to a label that occurs twice."""
    counts = Counter(item["label"] for item in items)
    for item in items:
        if counts[item["label"]] > 1:
            item["label"] = f'{item["label"]} [{item["id"].rstrip("/").rsplit("/", 1)[-1]}]'
    labels = [item["label"] for item in items]
    assert len(set(labels)) == len(labels), "two items of one list have the same label and the same id ending"
    return items


def _sorted(items):
    return sorted(_unique_labels(items), key=lambda item: (item["label"].casefold(), item["id"]))


def _cut(text):
    return text if len(text) <= LABEL_LIMIT else text[:LABEL_LIMIT - 3].rstrip() + "..."


def _simple(release, module, subjects, label=SKOS + "prefLabel"):
    items = []
    for s in subjects:
        name = release.text(module, s, label) or s.rstrip("/").rsplit("/", 1)[-1]
        items.append({"id": s, "label": name + (" (deprecated)" if release.deprecated(module, s) else "")})
    return _sorted(items)


def _processes(release):
    """The process tree of core. Each entry carries its level, its parent, its own business area, and every area
    that it or a process under it carries. The forms narrow question 1.2 by that last list."""
    from rdflib import URIRef
    g = release.graph("core")
    level_p, area_p, broader = URIRef(CORE + "taxonomyLevel"), URIRef(CORE + "businessDomain"), URIRef(SKOS + "broader")
    entries = {}
    for s, level in g.subject_objects(level_p):
        s = str(s)
        notation = release.text("core", s, SKOS + "notation")
        name = release.text("core", s, SKOS + "prefLabel")
        parent = g.value(URIRef(s), broader)
        area = g.value(URIRef(s), area_p)
        entries[s] = {"id": s, "label": (f"{notation} {name}" if notation else name)
                      + (" (deprecated)" if release.deprecated("core", s) else ""),
                      "level": int(level), "parent": str(parent) if parent is not None else "",
                      "area": str(area) if area is not None else "", "areas": set()}
    for entry in entries.values():
        if entry["area"]:
            at = entry
            while at is not None:      # the area counts for the process and for every process above it
                at["areas"].add(entry["area"])
                at = entries.get(at["parent"])
    for entry in entries.values():
        entry["areas"] = sorted(entry["areas"])
    return _sorted(list(entries.values()))


def _business_areas(release, processes):
    in_use = {p["area"] for p in processes if p["area"]}
    items = _simple(release, "core", release.subjects("core", SKOS + "inScheme", CORE + "BusinessDomain"))
    for item in items:
        item["in_use"] = item["id"] in in_use
    return items


def _measures(release):
    items = []
    for s in release.instances("kpi", KPI + "MeasureDefinition"):
        items.append({"id": s, "label": release.text("kpi", s, SKOS + "prefLabel"),
                      "notation": release.text("kpi", s, SKOS + "notation"),
                      "other_names": release.texts("kpi", s, SKOS + "altLabel"),
                      "definition": release.text("kpi", s, SKOS + "definition")})
    return _sorted(items)


def _roles(release):
    """The role register of organization and the planning personas of kpi. A persona that shares its name with a
    register role says so in its label."""
    register = _simple(release, "organization", release.instances("organization", ORG_ROLE))
    names = {item["label"] for item in register}
    for item in register:
        item["group"] = "Role register"
    personas = _simple(release, "kpi", release.instances("kpi", ORG_ROLE))
    for item in personas:
        item["group"] = "Planning persona"
        if item["label"] in names:
            item["label"] += " (planning persona)"
    return _sorted(register + personas)


def _value_stream_steps(release):
    from rdflib import URIRef
    g = release.graph("value-stream")
    stage_of = {str(step): str(stage) for stage, step in g.subject_objects(URIRef(VS + "hasProcess"))}
    stream_of = {str(stage): str(stream) for stream, stage in g.subject_objects(URIRef(VS + "hasStage"))}
    items = []
    for s in release.instances("value-stream", VS + "ValueStreamProcess"):
        stage = stage_of.get(s, "")
        stream = stream_of.get(stage, "")
        stream_name = release.text("value-stream", stream, SKOS + "prefLabel") if stream else ""
        items.append({"id": s, "label": release.text("value-stream", s, SKOS + "prefLabel"),
                      "group": stream_name,
                      "stage": release.text("value-stream", stage, SKOS + "prefLabel") if stage else ""})
    return _sorted(items)


def _relationships(release):
    items = []
    for s in release.subjects("value-stream", SKOS + "inScheme", VS + "MeasureRelationship"):
        name = release.text("value-stream", s, SKOS + "prefLabel")
        items.append({"id": s, "label": f'{name}: {release.text("value-stream", s, SKOS + "definition")}'})
    return _sorted(items)


def _platform_tables(release):
    items = []
    for s in release.instances("data-product", DP + "PlatformTable"):
        layer = release.text("data-product", s, DP + "layer")
        items.append({"id": s, "label": release.text("data-product", s, DP + "fullName"),
                      "layer": layer, "product": release.text("data-product", s, DCTERMS + "isPartOf")})
    return _sorted(items)


def _sources(release):
    """The sources that carry an evidence tier in integration. A source's title is in the module that cites it."""
    from rdflib import URIRef
    titles = {}
    for module in sorted(release.graphs):
        for s, title in release.graph(module).subject_objects(URIRef(DCTERMS + "title")):
            titles.setdefault(str(s), set()).add(str(title))
    items = []
    for s in release.instances("integration", DCTERMS + "BibliographicResource"):
        if not release.text("integration", s, AUTHORITY + "evidenceTier"):
            continue
        tail = s.rstrip("/").rsplit("/", 1)[-1]
        title = sorted(titles.get(s, {tail}))[0]
        items.append({"id": s, "label": _cut(title), "tier": release.text("integration", s, AUTHORITY + "evidenceTier").rsplit("/", 1)[-1]})
    return _sorted(items)


def _terms(release):
    """Every named term of every module except the measures, with its names and its definition. The check looks a
    new KPI's name up here."""
    from rdflib import URIRef
    measures = set(release.instances("kpi", KPI + "MeasureDefinition"))
    terms = []
    for module in sorted(release.graphs):
        g = release.graph(module)
        names = defaultdict(set)
        for predicate in (SKOS + "prefLabel", SKOS + "altLabel", RDFS_LABEL):
            for s, o in g.subject_objects(URIRef(predicate)):
                if isinstance(s, URIRef) and str(s) not in measures:
                    names[str(s)].add(str(o))
        for s in sorted(names):
            terms.append({"id": s, "module": module, "names": sorted(names[s]),
                          "definition": release.text(module, s, SKOS + "definition")})
    return terms


def build(root):
    """The pick lists, the term index and the versions they were read from, as plain data."""
    release = Release(root)
    processes = _processes(release)
    areas = _business_areas(release, processes)
    modules = [{"id": m, "label": m} for m in sorted(release.versions)]
    lists = {
        "business-areas": areas,
        "processes": processes,
        "measures": _measures(release),
        "roles": _roles(release),
        "value-stream-steps": _value_stream_steps(release),
        "measure-relationships": _relationships(release),
        "data-products": _simple(release, "data-product", release.instances("data-product", DP + "DataProduct")),
        "platform-tables": _platform_tables(release),
        "layers": _simple(release, "data-product", release.subjects("data-product", SKOS + "inScheme", DP + "Layer")),
        "data-product-kinds": _simple(release, "data-product", release.subjects("data-product", SKOS + "inScheme", DP + "DataProductKind")),
        "systems": _simple(release, "system", release.instances("system", SYSTEM + "System")),
        "sources": _sources(release),
        "modules": modules,
        "areas-and-modules": [{"id": a["id"], "label": "Business area: " + a["label"]} for a in areas]
                             + [{"id": "module:" + m["id"], "label": "Module: " + m["label"]} for m in modules],
    }
    return {"release": ontology_view.release_name(root), "versions": dict(sorted(release.versions.items())),
            "lists": lists, "terms": _terms(release)}


def dumps(data):
    """The file's text: sorted keys and one item per line, so two builds of the same packages are the same bytes."""
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def load(folder):
    """The built pick lists of a pack folder."""
    path = Path(folder) / FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ontology_view.ReleaseError(f"{path} cannot be read ({e}); build it with: py -m kpi_store.intake build") from None


def stale_modules(data, root):
    """The modules whose newest package is not the one the lists were built from: {module: (built from, now)}."""
    now = ontology_view.newest_versions(Path(root) / ontology_view.RELEASES)
    built = data.get("versions", {})
    return {m: (built.get(m, "none"), now.get(m, "none")) for m in sorted(set(built) | set(now)) if built.get(m) != now.get(m)}
