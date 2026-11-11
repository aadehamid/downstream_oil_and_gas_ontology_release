#!/usr/bin/env python3
"""Check that a Neo4j plugins folder holds the two plugin jars this skill was tested with.

Run: python3 check_plugins.py <plugins folder>
     On Windows: py check_plugins.py <plugins folder>

The local Neo4j that builds the projection needs n10s (neosemantics) and APOC Core. Neo4j Desktop
shows the folder under the DBMS's "Open folder" menu, as "Plugins". The check reads every .jar in the
folder and compares its SHA-256 with the pins below (references/running.md, rule 2), so a jar passes
under any file name and a jar of another version fails under the right one. Standard library only.

Exit 0 when both pinned jars are there, 1 when one is missing, 2 when the folder cannot be read.
"""
import hashlib
import sys
from pathlib import Path

from shell import q

# plugin: (the file name its publisher gives it, SHA-256)
PINS = {
    "n10s 2025.06.1": ("neosemantics-2025.06.1.jar", "4c461087e08405c7cb472ecfefc043e9e8ed93628ed74988e4fda1f1bac54b3e"),
    "APOC Core 2025.06.2": ("apoc-2025.06.2-core.jar", "4df40cea7444ea193d08f8a679aa998c498196fe149c8c02badb998f1c9580fb"),
}


def checksums(folder):
    """{jar file name: SHA-256} for every .jar directly in the folder."""
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(folder).iterdir()) if path.is_file() and path.suffix == ".jar"}


def check(found):
    """(lines for the jars found, lines for the pins missing) from {file name: SHA-256}."""
    by_sum = {}
    for name, digest in found.items():
        by_sum.setdefault(digest, name)
    present, missing = [], []
    for plugin, (name, digest) in PINS.items():
        if digest in by_sum:
            present.append((plugin, by_sum[digest]))
        else:
            missing.append((plugin, name, digest))
    return present, missing


def main(argv):
    if len(argv) != 1:
        print("usage: check_plugins.py <plugins folder>", file=sys.stderr)
        return 2
    try:
        found = checksums(argv[0])
    except OSError as exc:
        print(f"ERROR the plugins folder could not be read ({q(type(exc).__name__)})", file=sys.stderr)
        return 2
    present, missing = check(found)
    for plugin, name in present:
        print(f"OK {q(plugin)}: {q(name)} has the pinned SHA-256")
    for plugin, name, digest in missing:
        print(f"FAIL {q(plugin)}: no jar in the folder has SHA-256 {q(digest)}; put {q(name)} there and restart Neo4j")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
