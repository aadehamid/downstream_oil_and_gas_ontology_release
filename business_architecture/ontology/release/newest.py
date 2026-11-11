"""What is newest on disk, and what a write may overwrite. Standard library only, so any builder can import it.

A builder or test that needs "the current core" asks here, so a new core release needs no edit to them.

This file is a library with no command. It reads folder and file names under releases/ and release/, and the text
of a package about to be overwritten. It writes nothing.

The KPI Store uses two things from it. version_key is the one order of versions: the loads and the sync check use it
to pick each module's newest package (through kpi_store/ontology_view.py and projection/sync_stores.py), so a
correction version is loaded in place of the version it corrects. correction_version is how the cut tool
(kpi_store/cut.py) names the version it writes.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY = os.path.dirname(HERE)
CORE_BUILDER = re.compile(r"build_core_(\d+)_(\d+)\.py")   # applied with fullmatch, so no name with a line end passes
# A version as a pattern, for a builder or test that finds one inside a longer text.
VERSION_PATTERN = r"\d+\.\d+\.\d+(?:-correction\.\d+)?"
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-correction\.(\d+))?")


def version_key(version):
    """The order of a version, and the one place that decides it. A correction version,
    <major>.<minor>.<patch>-correction.<n>, is newer than the plain version of the same three numbers and older than
    the next patch: 1.2.0, 1.2.1, 1.2.1-correction.1, 1.2.1-correction.2, 1.2.2. This is not SemVer's order, where a
    suffix after a hyphen sorts before the plain version. Returns None for any other text."""
    m = VERSION.fullmatch(version)   # fullmatch: with match and "$", a version with a final line end would pass
    return tuple(int(n or 0) for n in m.groups()) if m else None


def correction_version(current):
    """The version a correction to `current` gets. A correction to a plain version takes the next patch number and
    the marker: 1.2.0 gives 1.2.1-correction.1. A correction to a correction keeps the three numbers and counts up:
    1.2.1-correction.1 gives 1.2.1-correction.2. No plain 1.2.1 is ever released beside them: the next ordinary
    patch after a correction is 1.2.2, so SemVer's order and version_key agree on every tree."""
    key = version_key(current)
    if key is None:
        raise ValueError(f"{current!r} is not a version")
    major, minor, patch, n = key
    return f"{major}.{minor}.{patch}-correction.{n + 1}" if n else f"{major}.{minor}.{patch + 1}-correction.1"


def newest_version(module, ontology=ONTOLOGY):
    """A module's newest version folder in releases/<module>/ that holds a manifest, by version_key, never by text."""
    folder = os.path.join(ontology, "releases", module)
    versions = [v for v in os.listdir(folder)
                if version_key(v) and os.path.isfile(os.path.join(folder, v, "manifest.json"))]
    if not versions:
        raise FileNotFoundError(f"{folder} holds no released package")
    return max(versions, key=version_key)


def core_file(name="core.ttl", ontology=ONTOLOGY):
    """A file of the newest core package."""
    return os.path.join(ontology, "releases", "core", newest_version("core", ontology), name)


def core_builder(release=HERE):
    """The module name of the newest numbered core builder, build_core_<major>_<minor>; importing it gives its VERSION
    and BASE. A patch of core is a new builder too, named for its major and minor."""
    found = [(int(m.group(1)), int(m.group(2)), f) for f in os.listdir(release) for m in [CORE_BUILDER.fullmatch(f)] if m]
    if not found:
        raise FileNotFoundError(f"{release} holds no build_core_<major>_<minor>.py")
    return max(found)[2][:-3]


def refuse_overwrite(out, files, what, rebuild_released=False):
    """Stop before a write changes a released package: a released package never changes, so a change needs a new
    version. A package that does not exist yet, or a write that changes nothing, passes. `--rebuild-released` is for a
    rebuild of the whole set from its sources, which changes what the packages are built from."""
    if rebuild_released or not os.path.isfile(os.path.join(out, "manifest.json")):
        return
    changed = []
    for name, text in sorted(files.items()):
        path = os.path.join(out, name)
        if not os.path.exists(path):
            changed.append(name)
            continue
        with open(path, encoding="utf-8") as f:
            if f.read() != text:
                changed.append(name)
    if changed:
        raise SystemExit(f"{what} is already released and this build differs in {', '.join(changed)}. A released package "
                         "never changes: raise the version first, then write. To restore what the sources say, without "
                         "a new version, pass --rebuild-released.")
