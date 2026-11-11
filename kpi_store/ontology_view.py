"""Reads the release packages: the platform objects, their columns, the table edges and the measures they serve.

The data-product package names every table, view and metric view as a dp:PlatformTable. The comparison with the
workspace needs only the facts below, so this module reduces the package to them. Needs rdflib.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

RELEASES = Path("business_architecture") / "ontology" / "releases"
DP = "https://w3id.org/mpc/ontology/modules/data-product/"
PROV_DERIVED = "http://www.w3.org/ns/prov#wasDerivedFrom"
SKOS = "http://www.w3.org/2004/02/skos/core#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-correction\.(\d+))?$")


class ReleaseError(Exception):
    """The release folder does not hold what a load needs."""


def version_key(version):
    """The order of a version folder's name. A correction version, <major>.<minor>.<patch>-correction.<n>, is newer
    than the plain version of the same three numbers and older than the next patch: 1.2.0, 1.2.1, 1.2.1-correction.1,
    1.2.1-correction.2, 1.2.2. This is not SemVer's order, where a suffix after a hyphen sorts before the plain
    version. Returns None for any other name."""
    m = VERSION.match(version)
    return tuple(int(n or 0) for n in m.groups()) if m else None


def newest_version(module, releases):
    """A module's newest version folder that holds a manifest.json, by version_key, never by text."""
    folder = Path(releases) / module
    versions = [p.name for p in folder.iterdir() if version_key(p.name) and (p / "manifest.json").is_file()] if folder.is_dir() else []
    if not versions:
        raise ReleaseError(f"{folder} holds no released package")
    return max(versions, key=version_key)


def newest_versions(releases):
    """{module: newest version} for every module folder under releases/ that holds a released package."""
    out = {}
    for folder in sorted(Path(releases).iterdir()):
        if folder.is_dir() and folder.name != "previous":
            try:
                out[folder.name] = newest_version(folder.name, releases)
            except ReleaseError:
                continue
    return out


@dataclass(frozen=True)
class PlatformObject:
    iri: str
    full_name: str        # catalog.schema.name, as the ontology spells it
    layer: str            # replica, silver, gold or metric-view
    measures: tuple       # notations of the measures the object serves


@dataclass(frozen=True)
class PlatformColumn:
    iri: str
    table: str            # the table's full name, as the ontology spells it
    name: str             # the column's name, as the ontology spells it
    derived_from: tuple   # ((table full name, column name), ...) of the columns it derives from


@dataclass(frozen=True)
class Measure:
    iri: str
    notation: str
    label: str
    alt_labels: tuple


@dataclass
class OntologyView:
    versions: dict = field(default_factory=dict)   # {module: version} of the packages read
    objects: dict = field(default_factory=dict)    # {full name, lower case: PlatformObject}
    columns: list = field(default_factory=list)    # [PlatformColumn]
    edges: set = field(default_factory=set)        # {(downstream, upstream)}, full names in lower case
    measures: dict = field(default_factory=dict)   # {notation: Measure}, only those an object serves

    def upstream(self, name):
        return {up for down, up in self.edges if down == name.lower()}


def _package_file(folder, module):
    path = Path(folder) / f"{module}.ttl"
    if not path.is_file():
        raise ReleaseError(f"{path} is missing")
    return path


def read_packages(data_product, kpi=None):
    """An OntologyView from a data-product package folder and, for the measures' labels, a kpi package folder."""
    from rdflib import Graph, URIRef

    def tail(iri):
        return str(iri).rstrip("/").rsplit("/", 1)[-1]

    g = Graph().parse(_package_file(data_product, "data-product"), format="turtle")
    rdf_type, derived = URIRef(RDF_TYPE), URIRef(PROV_DERIVED)
    tables = {}
    for t in g.subjects(rdf_type, URIRef(DP + "PlatformTable")):
        full_name = g.value(t, URIRef(DP + "fullName"))
        if full_name is None:
            raise ReleaseError(f"{t} is a platform table with no dp:fullName")
        tables[t] = str(full_name)
    view = OntologyView()
    for t, full_name in tables.items():
        layer = g.value(t, URIRef(DP + "layer"))
        measures = tuple(sorted(tail(m) for m in g.objects(t, URIRef(DP + "servesMeasure"))))
        if full_name.lower() in view.objects:
            raise ReleaseError(f"two platform tables are named {full_name}")
        view.objects[full_name.lower()] = PlatformObject(str(t), full_name, tail(layer) if layer else "", measures)
        # prov:wasDerivedFrom also links columns, so an edge counts only between two platform tables.
        view.edges |= {(full_name.lower(), tables[up].lower()) for up in g.objects(t, derived) if up in tables}
    columns = {c: (g.value(c, URIRef(DP + "columnOf")), g.value(c, URIRef(DP + "columnName")))
               for c in g.subjects(rdf_type, URIRef(DP + "PlatformColumn"))}
    for c, (table, name) in sorted(columns.items()):
        if table not in tables or name is None:
            raise ReleaseError(f"{c} lacks dp:columnOf a platform table or dp:columnName")
        sources = tuple(sorted((tables[columns[u][0]], str(columns[u][1])) for u in g.objects(c, derived) if u in columns))
        view.columns.append(PlatformColumn(str(c), tables[table], str(name), sources))
    served = {m for o in view.objects.values() for m in o.measures}
    labels = Graph().parse(_package_file(kpi, "kpi"), format="turtle") if kpi else Graph()
    for t in g.subjects(rdf_type, URIRef(DP + "PlatformTable")):
        for m in g.objects(t, URIRef(DP + "servesMeasure")):
            if tail(m) in served and tail(m) not in view.measures:
                label = labels.value(m, URIRef(SKOS + "prefLabel"))
                alts = tuple(sorted(str(a) for a in labels.objects(m, URIRef(SKOS + "altLabel"))))
                view.measures[tail(m)] = Measure(str(m), tail(m), str(label or tail(m)), alts)
    return view


def read(release_root):
    """An OntologyView of the newest packages under the release's root folder."""
    releases = Path(release_root) / RELEASES
    if not releases.is_dir():
        raise ReleaseError(f"{releases} is missing")
    versions = newest_versions(releases)
    for module in ("data-product", "kpi"):
        if module not in versions:
            raise ReleaseError(f"the release holds no {module} package")
    view = read_packages(releases / "data-product" / versions["data-product"], releases / "kpi" / versions["kpi"])
    view.versions = versions
    return view


def release_name(release_root):
    """The release's name from release.json at its root, such as "KPI Store 1.1"."""
    path = Path(release_root) / "release.json"
    try:
        return str(json.loads(path.read_text(encoding="utf-8"))["release"])
    except (OSError, ValueError, KeyError):
        raise ReleaseError(f"{path} is missing or names no release") from None
