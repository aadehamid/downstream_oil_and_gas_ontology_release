"""Builds the intake form's pick lists from the release packages, and reads the built file back.

The forms offer a list wherever the ontology already holds the answers: the business areas, the process tree, the
measures, the roles and so on. build() reads the newest package of each module and returns the lists, with a
term index for the check of names. The build command writes the result to kpi-intake/pick-lists.json. The check
and the forms read that file, so they need no rdflib and agree with each other.

Every item has an `id` (the term's IRI, or a module's name) and a `label` (what a person sees). Labels are unique
within a list, because a workbook cell holds the label and the reader must find the id again.

A deprecated term stays in its list with "(deprecated)" in its label, so the lists count what the ontology holds.
The settings may still name it by its label without that mark, so a `hide` written before the deprecation holds.

apply_settings() then marks the lists with what the organization's settings.toml says under [pick_list.<name>]. A
hidden entry stays in its list with "hidden": true, so the forms do not offer it and the check still knows it. An
added entry joins its list with "added": true, an id that starts with "new:" and a label that says it is new. When
the ontology has since gained an entry of the same label, the added entry is not offered a second time: its id
becomes an alias of the ontology's entry ("aliases" on that entry), so an answer saved under it is still read.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from kpi_store import ontology_view
from kpi_store.intake.catalogue import ADDED, ADDED_MARK, SETTINGS_LISTS, CatalogueError

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
DEPRECATED_MARK = " (deprecated)"
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


def _named(items, name):
    """The entries the settings mean by a name: an id, the last part of an id, or a label. When no entry has the
    name, it is read as the ontology's own label of a deprecated term, which this build shows with a mark."""
    hits = [i for i in items if name in (i["id"], i["label"], i["id"].rstrip("/").rsplit("/", 1)[-1])]
    return hits or [i for i in items if i["label"] == name + DEPRECATED_MARK]


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
        items.append({"id": s, "label": name + (DEPRECATED_MARK if release.deprecated(module, s) else "")})
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
                      + (DEPRECATED_MARK if release.deprecated("core", s) else ""),
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


def build(root, release=None):
    """The pick lists, the term index and the versions they were read from, as plain data."""
    release = release or Release(root)
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


def apply_settings(built, pick_lists):
    """Marks the built lists with the settings of [pick_list.<name>], in place, and returns `built`.

    `hide`, `keep_only` and `labels` name an entry by its label as the ontology gives it, by its id, or by the last
    part of its id. `hide_tiers` names the evidence tiers of the sources to hide. `labels` gives an entry the label
    the forms and the check show in place of the ontology's. The entry keeps its id, and its earlier label stays
    known under "was", so a workbook filled before the change still reads. Raises CatalogueError when a name matches no entry of its list, so a
    misspelt name cannot hide nothing unnoticed. An added entry that matches an entry of the ontology, by the
    entry's label of today, its ontology label or the last part of its id, becomes an alias of that entry and is
    not offered a second time. The entry stays hidden when `keep_only` or `hide_tiers` leaves it out. Raises too
    when an added entry matches several entries, or an entry that `hide` names. rules.py states how a stored
    value then finds its entry."""
    problems = []
    for name in SETTINGS_LISTS:
        change = pick_lists.get(name) or {}
        items = built["lists"][name]
        where = f"settings.toml, [pick_list.{name}]"

        def matched(key):
            wanted = list(change.get(key, []))
            found = {w: _named(items, w) for w in wanted}
            for w in wanted:
                if not found[w]:
                    problems.append(f"{where}: `{key}` names {w!r}, which is no entry of the list. Write the label as the list shows it, or the id.")
            return {i["id"] for hits in found.values() for i in hits}

        ontology_label = {i["id"]: i["label"] for i in items}
        hidden = matched("hide")
        named_hidden = set(hidden)       # the entries `hide` names itself
        if change.get("keep_only"):
            kept = matched("keep_only")
            hidden |= {i["id"] for i in items if i["id"] not in kept}
        tiers = set(change.get("hide_tiers", []))
        for tier in sorted(tiers - {i.get("tier") for i in items}):
            problems.append(f"{where}: `hide_tiers` names {tier!r}, which is no tier of a source in the list")
        hidden |= {i["id"] for i in items if i.get("tier") in tiers}
        for item in items:
            if item["id"] in hidden:
                item["hidden"] = True
        renamed = {}
        for wanted, label in (change.get("labels") or {}).items():
            hits = _named(items, wanted)
            if not hits:
                problems.append(f"{where}: `labels` names {wanted!r}, which is no entry of the list. Write the label as the ontology gives it, or the id.")
            for item in hits:
                renamed[item["id"]] = label.strip()
        for item in items:
            if item["id"] in renamed and renamed[item["id"]] != item["label"]:
                item["was"], item["label"] = sorted(set(item.get("was", [])) | {item["label"]}), renamed[item["id"]]
        shown = [i["label"].casefold() for i in items]
        for label in sorted({l for l in shown if shown.count(l) > 1}):
            problems.append(f"{where}: `labels` gives two entries the label {label!r}. Each entry needs a label of its own.")
        taken = set()
        for entry in change.get("add", []):
            key = entry["label"].strip().casefold()
            if key in taken:
                problems.append(f"{where}: two added entries have the label {entry['label']!r}")
                continue
            taken.add(key)
            # The ontology may have gained this entry since it was added: under the same label, under a label the
            # settings have since changed, or under the same short id.
            same = [i for i in items if not i.get("added") and (
                key in {n.strip().casefold() for n in [i["label"], ontology_label[i["id"]]]}
                or i["id"].rstrip("/").rsplit("/", 1)[-1] == entry["id"])]
            if len(same) > 1:
                problems.append(f"{where}: the added entry {entry['label']!r} matches {len(same)} entries of the list: "
                                + ", ".join(repr(i["label"]) for i in same) + ". Give it a label or an id that only one of them has, or remove it.")
            elif same and same[0]["id"] in named_hidden:
                problems.append(f"{where}: `hide` hides {same[0]['label']!r} and `add` adds it. Remove one of the two.")
            elif same:
                # Answers saved under the added id, or under its label, are read as the ontology's entry. The entry
                # keeps what the settings say of it otherwise: it stays hidden when keep_only does not name it.
                item = same[0]
                item["aliases"] = sorted(set(item.get("aliases", [])) | {ADDED + entry["id"]})
                if entry["label"].strip() != item["label"]:
                    item["was"] = sorted(set(item.get("was", [])) | {entry["label"].strip()})
            else:
                items.append({"id": ADDED + entry["id"], "label": entry["label"].strip() + ADDED_MARK, "added": True})
        built["lists"][name] = sorted(items, key=lambda item: (item["label"].casefold(), item["id"]))
    if problems:
        raise CatalogueError("\n".join(problems))
    return built


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
