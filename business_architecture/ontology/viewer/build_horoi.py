"""Build the ontology reference page (horoi_viewer/index.html) and its build record.

    python3 business_architecture/ontology/viewer/build_horoi.py --source . --out horoi_viewer
    python3 business_architecture/ontology/viewer/build_horoi.py --source . --out horoi_viewer --check

The page is horoi_page.html with the release's data inside it. The data is the full viewer's data (build.py),
plus what the reference page needs to list the modules: each module's name, title, description and the
versions it requires, read from the module's own ontology statement. The build record (build.json) names the
release, the input files with their checksums, the counts and the page's checksum.

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

# The public Horoi commit the page's styles were adapted from (horoi_viewer/NOTICE.txt).
HOROI_COMMIT = "33caa8cc916e7efb767a5c2831216ff1cb11c509"
DCTERMS = "http://purl.org/dc/terms/"


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
                "label": titles[0],
                "description": descriptions[0],
                "requires": stated("requires"),
            }
        )
    return info


def build_data(root):
    root = Path(root).resolve()
    data = viewer.build_data(root)
    info = module_info(root, data)
    supporting = set(data["supportingKinds"])
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
