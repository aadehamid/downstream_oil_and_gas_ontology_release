"""The process map as each core builder read it, kept as frozen files, so this tree rebuilds the same core
packages byte for byte without any Git history.

    python3 frozen_sources.py       # list each frozen map a core builder names, and whether its file is here

Each core builder names the map it was built from by a 40-character id (its SOURCE_COMMIT). A builder asks
`read(id, path)` and gets the frozen file release/frozen/<first 12 characters of the id>-<file name>.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = os.path.join(HERE, "frozen")


def package_dir(ontology, module, version):
    """A released package's folder: releases/<module>/<version>/, or the history folder
    releases/previous/<module>/<version>/ when the package is there instead (the decision of 2026-10-31)."""
    plain = os.path.join(ontology, "releases", module, version)
    previous = os.path.join(ontology, "releases", "previous", module, version)
    return previous if not os.path.isdir(plain) and os.path.isdir(previous) else plain


def frozen_path(commit, path):
    return os.path.join(FROZEN, f"{commit[:12]}-{os.path.basename(path)}")


def read(commit, path):
    """The bytes of `path` as the builder that names `commit` read it: the frozen copy."""
    frozen = frozen_path(commit, path)
    if not os.path.exists(frozen):
        raise FileNotFoundError(f"no frozen copy of {path} for {commit[:12]}: {os.path.relpath(frozen, HERE)} is missing")
    with open(frozen, "rb") as f:
        return f.read()


def is_frozen(commit, path):
    return os.path.exists(frozen_path(commit, path))


def pinned():
    """(id, path) for every frozen map a core builder names."""
    sys.path.insert(0, HERE)
    import build_core_2_2 as b22
    import build_core_2_3 as b23
    import build_core_2_4 as b24
    import build_core_next as b20
    seen = []
    for mod in (b20, b22, b23, b24):
        for name in ("EARLIER_COMMIT", "SOURCE_COMMIT"):
            commit = getattr(mod, name, None)
            if commit and (commit, mod.SOURCE_PATH) not in seen:
                seen.append((commit, mod.SOURCE_PATH))
    return seen


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    for commit, path in pinned():
        print(commit, path, "frozen" if is_frozen(commit, path) else "missing")


if __name__ == "__main__":
    main()
