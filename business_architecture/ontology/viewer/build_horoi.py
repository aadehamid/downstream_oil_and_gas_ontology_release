"""Build the ontology reference page (horoi_viewer/index.html) and its build record.

    python3 business_architecture/ontology/viewer/build_horoi.py --source . --out horoi_viewer
    python3 business_architecture/ontology/viewer/build_horoi.py --source . --out horoi_viewer --check

The page is horoi_page.html with the release's data inside it. The data is the full viewer's data (build.py),
plus what the reference page needs to list the modules: each module's name, title, description and the
versions it requires, read from the module's own ontology statement. The build record (build.json) names the
release, the Horoi version, the input files with their checksums, the counts and the page's checksum.

The page shows each name without a leading "MPC ": the whole reference is MPC's, so the word says nothing there.
This is a choice of what the page shows and of nothing else. The released packages keep their names, and a term's
page still lists the name as its package states it, among its statements (shown_names).
Decided (delegated under KPI-DEC-0001); the owner's words are in
business_architecture/domain/kpi-store-decisions/answers/2026-11-14-reference-page-names.md.

--check writes nothing. It fails when the page or the record differs from a fresh build.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("viewer_builder", HERE / "build.py")
viewer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(viewer)

# The public Horoi release whose page styles this page adapts, and the commit its tag names
# (horoi_viewer/NOTICE.txt).
HOROI_VERSION = "0.2.0"
HOROI_COMMIT = "e0660af0f795ebfeb6f1354a69b3b0c47ebafba6"
DCTERMS = "http://purl.org/dc/terms/"
# The word the page leaves off the front of every name it shows, a source's name and a column's name included: the
# owner's goal for the release says that no shown name starts with it. A column's name joins the word with an
# underscore, as in MPC_Cost_Center_Id, so both forms go.
IMPLIED_PREFIXES = ("MPC ", "MPC_")


def shown_name(label):
    """The name as the page shows it: without the leading "MPC " or "MPC_". "MPC" inside a name stays, and so does
    a name that would be empty without the word."""
    for prefix in IMPLIED_PREFIXES:
        if label.startswith(prefix):
            rest = label[len(prefix):]
            return rest if rest.strip() else label
    return label


def shown_names(data):
    """Gives every node the name the page shows, in place. A node whose name changes keeps the name of its package
    as releasedLabel, so that a search for the old name still finds it. The node's statements are not touched: they
    are what the packages state."""
    for node in data["nodes"]:
        shown = shown_name(node["label"])
        if shown != node["label"]:
            node["releasedLabel"], node["label"] = node["label"], shown
    return data


def module_info(root, data):
    """One entry per current module, in name order, from the module's ontology statement."""
    nodes = {n["id"]: n for n in data["nodes"]}
    versions = sorted({(module, version) for _, module, version in viewer.release_files(root) if module})
    info = []
    for module, version in versions:
        manifest = Path(root) / viewer.ONTOLOGY / "releases" / module / version / "manifest.json"
        iri = json.loads(manifest.read_text(encoding="utf-8"))["ontology_iri"]
        if iri not in nodes:
            raise ValueError(f"No package states the ontology {iri} that {module} {version} names")

        def stated(name):
            return sorted(v["v"] for v in nodes[iri]["values"] if v["p"] == DCTERMS + name)

        titles, descriptions = stated("title"), stated("description")
        if len(titles) != 1 or len(descriptions) != 1:
            raise ValueError(f"{iri} needs exactly one title and one description")
        info.append(
            {
                "name": module,
                "version": version,
                "id": iri,
                "label": shown_name(titles[0]),
                "description": descriptions[0],
                "requires": stated("requires"),
            }
        )
    return info


def build_data(root):
    root = Path(root).resolve()
    data = viewer.build_data(root)
    info = module_info(root, data)
    shown_names(data)
    supporting = set(data["supportingKinds"])
    data["horoiVersion"] = HOROI_VERSION
    data["horoiCommit"] = HOROI_COMMIT
    data["moduleInfo"] = info
    data["referenceModules"] = [m["name"] for m in info]
    data["referenceTerms"] = [n["id"] for n in data["nodes"] if n["kind"] not in supporting]
    return data


def render(root):
    """The page's text and its build record's text, without writing a file."""
    data = build_data(root)
    page = (HERE / "horoi_page.html").read_text(encoding="utf-8").replace("/* EMBEDDED_DATA */", viewer.embed(data))
    record = {
        "release": data["release"],
        "horoi_version": HOROI_VERSION,
        "horoi_commit": HOROI_COMMIT,
        "modules": [{"name": m["name"], "version": m["version"]} for m in data["moduleInfo"]],
        "inputs": data["inputs"],
        "reference_terms": len(data["referenceTerms"]),
        "triples_available": data["triples"],
        "index_sha256": hashlib.sha256(page.encode("utf-8")).hexdigest(),
    }
    return page, json.dumps(record, indent=2) + "\n"


def build(root, out):
    page, record = render(root)
    out = Path(out)
    viewer.write_page(out / "index.html", page)
    viewer.write_page(out / "build.json", record)
    return json.loads(record)


def stale(root, out):
    """The files under `out` that differ from a fresh build."""
    out = Path(out)
    fresh = dict(zip(("index.html", "build.json"), render(root)))
    return [
        name
        for name, text in fresh.items()
        if not (out / name).is_file() or (out / name).read_bytes() != text.encode("utf-8")
    ]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True, help="the release folder")
    p.add_argument("--out", required=True, help="the folder that holds index.html and build.json")
    p.add_argument("--check", action="store_true", help="write nothing; fail when a file differs from a fresh build")
    args = p.parse_args(argv)
    if args.check:
        differs = stale(args.source, args.out)
        if differs:
            print(f"{args.out}: {' and '.join(differs)} differ from a fresh build; run this command again without --check", file=sys.stderr)
            return 1
        print(f"{args.out} is current")
        return 0
    record = build(args.source, args.out)
    print(json.dumps({k: v for k, v in record.items() if k != "inputs"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
