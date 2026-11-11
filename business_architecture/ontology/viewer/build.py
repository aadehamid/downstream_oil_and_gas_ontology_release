"""Build an offline viewer from current Turtle packages and the release catalog."""

import argparse
import base64
from collections import Counter, defaultdict
from contextlib import contextmanager
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys

import rdflib
from rdflib import BNode, Graph, Literal, RDF, RDFS, OWL, SKOS
from rdflib.namespace import DCTERMS
from rdflib.compare import to_canonical_graph

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "scripts"))
from epm_source_descriptions import neutral_source_description
sys.path.insert(0, str(HERE.parent / "release"))
from newest import version_key  # the one version order, which reads a correction version

ONTOLOGY = Path("business_architecture/ontology")
RELEASE = "KPI Store 1.1"
LABELS = (SKOS.prefLabel, RDFS.label, DCTERMS.title)
PARENTS = (RDFS.subClassOf, RDFS.subPropertyOf, SKOS.broader)
SUPPORTING_KINDS = ("Anonymous node", "Evidence", "Metadata", "Constraint")


@contextmanager
def literals_as_written():
    """Keep each typed literal's text as the package wrote it. By default rdflib rewrites it into the
    datatype's canonical form (a time ending in "Z" becomes one ending in "+00:00"), and the page must
    show the released text."""
    before = rdflib.NORMALIZE_LITERALS
    rdflib.NORMALIZE_LITERALS = False
    try:
        yield
    finally:
        rdflib.NORMALIZE_LITERALS = before


def release_files(root):
    """Only current packages; examples and history are outside this population."""
    root = Path(root)
    packages = root / ONTOLOGY / "releases"
    files = []
    for module in sorted(packages.iterdir()):
        if not module.is_dir() or module.name == "previous":
            continue
        versions = [
            p
            for p in module.iterdir()
            if p.is_dir() and version_key(p.name)
        ]
        if not versions:
            continue
        manifest_path = max(versions, key=lambda p: version_key(p.name)) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest["module"] != module.name
            or manifest["version"] != manifest_path.parent.name
        ):
            raise ValueError(f"Manifest identity mismatch: {manifest_path}")
        if manifest.get("release_candidate"):
            raise ValueError(f"Unreleased package: {manifest_path}")
        for name, expected in sorted(manifest["files"].items()):
            if not name.endswith(".ttl"):
                continue
            path = manifest_path.parent / name
            if path.resolve().parent != manifest_path.parent.resolve():
                raise ValueError(f"Invalid manifest path: {name}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Package hash mismatch: {path}")
            files.append((path, module.name, manifest["version"]))
    if not files:
        raise ValueError("No released Turtle packages found")
    catalog = packages / "catalog.ttl"
    if catalog.exists():
        files.append((catalog, None, None))
    return files


def clean_packages(root):
    """Refuse a tree whose release packages have local changes. A tree without Git has nothing to compare with."""
    if not (Path(root) / ".git").exists():
        return
    changed = subprocess.check_output(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--",
            str(ONTOLOGY / "releases"),
        ],
        text=True,
    )
    if changed:
        raise ValueError("The release packages have local changes")


def term_id(value):
    return "_:" + str(value) if isinstance(value, BNode) else str(value)


def short(value):
    return str(value).rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def build_data(root):
    """The page's data: every triple of the current packages, grouped by subject."""
    with literals_as_written():
        return _build_data(Path(root))


def _build_data(root):
    graph = Graph()
    membership = defaultdict(set)
    inputs = []
    for path, module, version in release_files(root):
        part = to_canonical_graph(Graph().parse(path, format="turtle"))
        # Canonical blank IDs from different files must remain scoped to their file.
        # Forward slashes on every system, so Windows builds the same page.
        prefix = hashlib.sha256(path.relative_to(root).as_posix().encode()).hexdigest()[:16]

        def scoped(node):
            return BNode(prefix + str(node)) if isinstance(node, BNode) else node

        for s, p, o in part:
            triple = tuple(scoped(n) for n in (s, p, o))
            graph.add(triple)
            if module:
                membership[triple[0]].add((module, version))
        inputs.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    nodes = []
    subjects = set(graph.subjects())
    for s in sorted(subjects, key=term_id):
        types = set(graph.objects(s, RDF.type))
        labels = [
            o for p in LABELS for o in graph.objects(s, p) if isinstance(o, Literal)
        ]
        labels.sort(key=lambda o: (o.language not in ("en", None), str(o)))
        label = (
            str(labels[0])
            if labels
            else ("Anonymous constraint" if isinstance(s, BNode) else short(s))
        )
        kind = "Individual"
        if isinstance(s, BNode):
            kind = "Anonymous node"
        elif OWL.Class in types or RDFS.Class in types:
            kind = "Class"
        elif any(
            t in types
            for t in (
                RDF.Property,
                OWL.ObjectProperty,
                OWL.DatatypeProperty,
                OWL.AnnotationProperty,
            )
        ):
            kind = "Property"
        elif SKOS.Concept in types:
            kind = "Concept"
        elif SKOS.ConceptScheme in types:
            kind = "Concept scheme"
        elif OWL.Ontology in types or any(
            short(t) in ("Catalog", "Dataset", "Distribution") for t in types
        ):
            kind = "Metadata"
        elif any(
            short(t) in ("CanonicalFact", "EvidenceRow", "BibliographicResource")
            for t in types
        ):
            kind = "Evidence"
        elif any(str(t).startswith("http://www.w3.org/ns/shacl#") for t in types):
            kind = "Constraint"
        values = []
        for p, o in sorted(
            graph.predicate_objects(s),
            key=lambda v: (str(v[0]), term_id(v[1]), v[1].n3()),
        ):
            values.append(
                {
                    "p": str(p),
                    "v": term_id(o),
                    "literal": isinstance(o, Literal),
                    "lang": o.language if isinstance(o, Literal) else None,
                    "datatype": str(o.datatype)
                    if isinstance(o, Literal) and o.datatype
                    else None,
                }
            )
        nodes.append(
            {
                "id": term_id(s),
                "label": label,
                "kind": kind,
                "modules": [
                    {"name": m, "version": v}
                    for m, v in sorted(membership[s] or {("Release metadata", RELEASE)})
                ],
                "parents": sorted(
                    term_id(o)
                    for p in PARENTS
                    for o in graph.objects(s, p)
                    if o in subjects
                ),
                "values": values,
            }
        )
    counts = dict(sorted(Counter(n["kind"] for n in nodes).items()))
    return {
        "release": RELEASE,
        "nodes": nodes,
        "inputs": inputs,
        "counts": counts,
        "triples": len(graph),
        "supportingKinds": SUPPORTING_KINDS,
        "terms": sum(n["kind"] not in SUPPORTING_KINDS for n in nodes),
    }


def embed(data):
    """The data as JSON that is safe inside a script element."""
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )


def write_page(output, page):
    """Write UTF-8 with LF line ends, so every system writes the same bytes."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        f.write(page)


def render(root, compare=None, require_clean=True):
    """The page's text and its data, without writing a file."""
    root = Path(root).resolve()
    if require_clean:
        clean_packages(root)
    data = build_data(root)
    if compare:
        compare = Path(compare).resolve()
        expected_inputs = [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(
                    neutral_source_description(path.read_bytes().decode("utf-8")).encode("utf-8")
                ).hexdigest(),
            }
            for path, _, _ in release_files(root)
        ]
        other_inputs = [
            {
                "path": path.relative_to(compare).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path, _, _ in release_files(compare)
        ]
        if other_inputs != expected_inputs:
            raise ValueError("The compared tree's packages differ from the source tree's")
        # Emit the compared tree's data, so its source titles and file hashes agree
        # with the files recipients receive. Only the exact source-title substitution
        # above may differ between the two trees, even in a metadata graph.
        data = build_data(compare)
    font_css = "".join(
        '@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:'
        + weight
        + ";src:url(data:font/woff2;base64,"
        + base64.b64encode(
            (HERE / "fonts" / ("plex-" + weight + ".woff2")).read_bytes()
        ).decode()
        + ') format("woff2");}'
        for weight in ("400", "500", "600")
    )
    page = (
        (HERE / "viewer.html")
        .read_text(encoding="utf-8")
        .replace("/* EMBEDDED_FONTS */", font_css)
    )
    page = page.replace(
        "FONT_LICENSE_TEXT", html.escape((HERE / "fonts/OFL.txt").read_text(encoding="utf-8"))
    )
    return page.replace("/* EMBEDDED_DATA */", embed(data)), data


def build(root, output, compare=None, require_clean=True):
    page, data = render(root, compare, require_clean)
    write_page(output, page)
    return {k: data[k] for k in ("release", "counts", "terms", "triples")}


def is_current(root, output):
    """True when the page at `output` equals a fresh build from the tree's packages."""
    output = Path(output)
    page, _ = render(root, require_clean=False)
    return output.is_file() and output.read_bytes() == page.encode("utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, help="the release folder")
    p.add_argument("--out", required=True, help="the page to write, or with --check the page to compare")
    p.add_argument("--compare")
    p.add_argument("--check", action="store_true", help="write nothing; fail when the page differs from a fresh build")
    args = p.parse_args(argv)
    if args.check:
        if is_current(args.source, args.out):
            print(f"{args.out} is current")
            return 0
        print(f"{args.out} differs from a fresh build; run this command again without --check", file=sys.stderr)
        return 1
    print(json.dumps(build(args.source, args.out, args.compare), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
