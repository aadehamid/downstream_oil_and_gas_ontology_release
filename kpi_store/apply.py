"""The apply command: applies approved proposals to the kpi module and releases it, or changes nothing.

    python -m kpi_store.apply <proposal folder> [<proposal folder> ...] [--release <folder>]

A proposal folder is what the propose command wrote (kpi_store/propose.py): change.kgcl, approval.json and
summary.txt. The command refuses, before it does anything else:
- a proposal whose approval record lacks a signature its route needs (Data Owner and Architect; the Ontology Owner
  too for a major), or whose route is lower than its changes suggest (KPI-DEC-0002, Q4, Q5 and Q13);
- proposals that conflict: two that change the same field of the same measure (Q6), or the same proposal twice;
- a proposal applied before: the release holds its approval record already;
- a Git copy with changes that are not committed, or with no author for the commit.

Then it works in a temporary copy of the release, as the cut does (kpi_store/cut.py), with the release's own
build scripts (Q7):
1. it writes each proposal's approval record under business_architecture/ontology/approvals/;
2. it applies the KGCL lines to the kpi tables and rebuilds the kpi module (kpi_store/change/kpi_tables.py);
3. it compares the kpi module before and after: the difference must be exactly the proposals' KGCL lines;
4. it releases kpi at the next version for the highest route among the proposals (next_version.py start and
   build_module.py), and gives every module that depends on kpi the next patch (next_version.py cascade);
5. it rebuilds the catalog, the projection manifest and the KPI intake pack, runs the competency questions,
   verifies the kpi module's Turtle, each new package, the catalog and the pack against a fresh build, and runs
   the kpi module's tests;
6. only when every step has passed, it copies the result into the release and, in a Git copy, commits it.
A failure at any step leaves the release as it was, and the command says why. It does not load any store: load
them afterwards with the runner (python -m kpi_store.runner).

Needs Python 3.11 or later with rdflib and pyshacl, and openpyxl when the release holds the KPI intake pack. A Git
copy needs Git; a plain folder needs none and gets the same files with no commit.
"""
import argparse
import datetime as dt
import shutil
import sys
import tempfile
from pathlib import Path

from kpi_store import cut
from kpi_store import ontology_view as ov
from kpi_store.change import ChangeRefused, approval, kpi_tables, proposal

MODULE = "kpi"
WHAT = "the apply command"


def next_version(current, route, newest):
    """The version after `current` for a route: 1.3.0 gives 1.3.1, 1.4.0 or 2.0.0. A patch after a correction version
    takes the next patch, as next_version.py's cascade does: 1.3.1-correction.1 gives 1.3.2."""
    key = newest.version_key(current)
    if key is None:
        raise ChangeRefused(f"{current!r} is not a version")
    major, minor, patch, _ = key
    return {"patch": f"{major}.{minor}.{patch + 1}", "minor": f"{major}.{minor + 1}.0", "major": f"{major + 1}.0.0"}[route]


def plan(folders, root):
    """The proposals, read and checked, the route of the release and {module: (current, new version)} for kpi and
    every module that depends on it, in release order. Reads the release and writes nothing."""
    if not folders:
        raise ChangeRefused("name at least one proposal folder")
    proposals = [proposal.read(f) for f in folders]
    ids = [p.change for p in proposals]
    twice = sorted({i for i in ids if ids.count(i) > 1})
    if twice:
        raise ChangeRefused(f"the proposal {', '.join(twice)} is named twice")
    clash = proposal.conflicts(proposals)
    if clash:
        raise ChangeRefused("the proposals conflict, so none was applied: " + "; ".join(clash)
                            + ". Apply one, then make a new form for the other from the changed measure")
    for p in proposals:
        if approval.record_path(root, p.change).exists():
            raise ChangeRefused(f"the proposal {p.change} was applied before: "
                                f"{approval.record_path(root, p.change).relative_to(root).as_posix()} holds its approval record")
    route = proposal.highest(p.route for p in proposals)
    release = root / cut.ONTOLOGY / "release"
    try:
        modules = cut._modules(release / "build_module.py")
        newest = ov.release_scripts_newest(root)
    except (OSError, cut.CutRefused, ov.ReleaseError) as err:
        raise ChangeRefused(f"{root} is not a KPI Store release: {err}") from None
    versions = {}
    for module in cut._run("list the modules to release", ["dependents.py", MODULE], release).split():
        spec = modules[module]
        if spec.get("stage") is not None:
            raise ChangeRefused(f"{module} {spec['version']} is a release candidate; release it before a change")
        versions[module] = (spec["version"], next_version(spec["version"], route if module == MODULE else "patch", newest))
    return proposals, route, versions


def describe(proposals, route, versions):
    """The plan as lines for the person who runs the command."""
    lines = [f"{len(proposals)} proposal{'s' if len(proposals) != 1 else ''} to apply:"]
    for p in proposals:
        signed = ", ".join(s["role"] for s in p.record["signatures"])
        lines.append(f"  {p.change}: {p.route}, signed by {signed}")
        lines += [f"    {line}" for line in p.lines]
    lines.append(f"The route of the release: {route}. Versions it writes:")
    lines += [f"  {m} {old} -> {new}" for m, (old, new) in versions.items()]
    return lines


def _round_trip(root, staging, proposals):
    """The difference between the kpi module before and after is exactly the proposals' KGCL lines."""
    back = kpi_tables.compare(root / kpi_tables.MEASURES, staging / kpi_tables.MEASURES)
    wanted = [line for p in proposals for line in p.lines]
    if sorted(back) != sorted(wanted):
        missing, extra = sorted(set(wanted) - set(back)), sorted(set(back) - set(wanted))
        raise cut.CutFailed(f"the kpi module does not hold exactly the proposals' changes: missing {missing or 'none'}, "
                            f"more {extra or 'none'}. The release is as it was.")


def apply(folders, release_root=".", say=print, now=None, before_step=None):
    """Applies the proposals and returns the paths the release changed. Raises ChangeRefused when a proposal or the
    release stops it before anything is done, and cut.CutFailed when a step fails: the release is then as it was,
    unless the message names paths that could not be put back. `before_step(name)` is called before each step."""
    root = Path(release_root).resolve()
    try:
        cut._requirements(root)
    except cut.CutRefused as err:
        raise ChangeRefused(str(err)) from None
    proposals, route, versions = plan(folders, root)
    for line in describe(proposals, route, versions):
        say(line)
    try:
        git = cut._git_ready(root, "", WHAT)
    except cut.CutRefused as err:
        raise ChangeRefused(str(err)) from None
    now = now or dt.datetime.now(dt.timezone.utc)
    date = now.strftime("%Y-%m-%d")
    old, new = versions[MODULE]
    records = [f"approvals/{p.change}.json" for p in proposals]
    # The approval that the new kpi version names: the first record, and the Architect's words, which every record
    # holds, as signed. The changelog lists every record.
    words = next(s["words"] for s in proposals[0].record["signatures"] if s["role"] == "Architect")
    approver = "The Ontology Owner" if route == "major" else "The Architect"
    why = (f"Applies the term change{'s' if len(proposals) > 1 else ''} {', '.join(p.change for p in proposals)}: "
           + "; ".join(line for p in proposals for line in p.lines) + f". Approval records: {', '.join(records)}.")
    signed = ["--approver", approver, "--where", records[0], "--words", words, "--date", date]
    ontology = cut.ONTOLOGY
    step = cut._Steps(say, before_step)
    with tempfile.TemporaryDirectory(prefix="kpi-store-apply-") as tmp:
        staging, backup = Path(tmp) / "release", Path(tmp) / "backup"
        release, kpi = staging / ontology / "release", staging / kpi_tables.KPI_FOLDER
        step("copy the release", lambda: shutil.copytree(root, staging, ignore=shutil.ignore_patterns(*cut.IGNORED)))
        for p in proposals:
            step(f"write the approval record of {p.change}", lambda p=p: approval.write_record(
                staging, p.change, p.route, p.record["signatures"], p.record["new_module"]))
        changes = [c for p in proposals for c in p.changes]
        step("apply the changes to the kpi tables and rebuild the kpi module", lambda: kpi_tables.apply_changes(changes, staging))
        step("compare the kpi module before and after", lambda: _round_trip(root, staging, proposals))
        step(f"set {MODULE} to {new}", lambda: cut._run(f"set {MODULE}", ["next_version.py", "start", MODULE, new, route,
                                                                           "--why", why, *signed], release))
        step(f"write the {MODULE} package", lambda: cut._run(f"write the {MODULE} package",
                                                             ["build_module.py", MODULE, "--write"], release))
        step(f"release the modules that depend on {MODULE}", lambda: cut._run(
            f"release the modules that depend on {MODULE}", ["next_version.py", "cascade", MODULE, *signed], release))
        cut._outputs(staging, versions, cut._has_intake(staging), step,
                     ("the kpi module's Turtle", [kpi_tables.BUILDER, "--verify"], kpi))
        step("run the kpi module's tests", lambda: cut._run("run the kpi module's tests",
                                                            ["-m", "unittest", "-q", "test_measures"], kpi))
        step("check that the release agrees with itself", lambda: cut._versions_agree(staging, versions))
        files = cut._difference(root, staging)
        step("write the release", lambda: cut._apply(root, staging, files, backup))
        if git != "none":
            subject = f"Apply {'the term change ' + proposals[0].change if len(proposals) == 1 else f'{len(proposals)} term changes'}: {MODULE} {new}"
            body = "\n".join([f"Approval records: {', '.join(records)}.", "", "The KGCL lines:"]
                             + [line for p in proposals for line in p.lines])
            cut._commit_paths(root, files, subject, body, backup, WHAT)
    others = len(versions) - 1
    say(f"Done. {MODULE} is now {new} ({route}), and {others} module{'s' if others != 1 else ''} that depend on it "
        f"took a new patch. The apply changed {len(files)} files" + (", and Git committed them." if git != "none" else "."))
    say(f"Run the full check before you load: {cut.CHECK_COMMAND} (on Windows, in Git Bash). Then load the stores with "
        "the runner: python -m kpi_store.runner")
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kpi_store.apply",
                                 description="Apply approved proposals to the kpi module and release it, or change nothing.")
    ap.add_argument("folders", nargs="+", help="proposal folders, as the propose command wrote them")
    ap.add_argument("--release", default=".", help="the release's top folder (default: this folder)")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        apply(a.folders, a.release)
    except (ChangeRefused, cut.CutRefused) as err:
        print(f"Not applied: {err}. Nothing was changed.", file=sys.stderr)
        return 1
    except cut.CutFailed as err:
        # One line says why; the lines the failing script printed, when there are some, follow it.
        first, _, rest = str(err).partition("\n")
        print(f"Not applied: {first}", file=sys.stderr)
        if rest:
            print(rest, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
