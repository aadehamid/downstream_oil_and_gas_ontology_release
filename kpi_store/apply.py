"""The apply command: applies approved proposals to their module and releases it, or changes nothing.

    python -m kpi_store.apply <proposal folder> [<proposal folder> ...] [--release <folder>]

A proposal folder is what the propose command wrote (kpi_store/propose.py): change.kgcl, approval.json and
summary.txt, and facts.csv for a new KPI. A term change changes the kpi module; a new KPI changes kpi, and
value-stream and data-product when it links to them (kpi_store/change/other_modules.py); a new reference item changes
its own module, system for a system and data-product for a table (kpi_store/change/reference_items.py). One run
applies proposals of one kind: term changes, new KPIs or reference items of one kind. Each changed module takes its
own route, and every module that depends on one takes a patch, once. The command refuses, before it does anything else:
- a proposal whose approval record lacks a signature its route needs (Data Owner and Architect; the Ontology Owner
  too for a major), or whose route is lower than its changes suggest (KPI-DEC-0002, Q4, Q5 and Q13);
- proposals for two modules, for systems and tables together, or for term changes and new KPIs together;
- proposals that conflict: two that change the same field of the same measure or add the same item (Q6), or the
  same proposal twice;
- a proposal applied before: the release holds its approval record already;
- a Git copy with changes that are not committed, or with no author for the commit.

Then it works in a temporary copy of the release, as the cut does (kpi_store/cut.py), with the release's own
build scripts (Q7):
1. it writes each proposal's approval record under business_architecture/ontology/approvals/, and beside it the
   proposal's KGCL lines as <change id>.kgcl, the change file, and a new KPI's facts as <change id>.facts.csv, so
   the release keeps what each change did;
2. it applies the KGCL lines, and a new KPI's facts, to the module's tables and rebuilds the module
   (kpi_store/change/kpi_tables.py, new_measures.py or reference_items.py);
3. it compares the module before and after: the difference must be exactly the proposals' KGCL lines and facts;
4. it releases each changed module at the next version for its route, and every module that depends on one at the
   next patch, in release order (next_version.py start and build_module.py for each, then next_version.py finish),
   as next_version.py's cascade does for one module;
5. it rebuilds the catalog, the projection manifest and the KPI intake pack, runs the competency questions,
   verifies the module's Turtle, each new package, the catalog and the pack against a fresh build, and runs the
   module's tests;
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
from dataclasses import dataclass, field
from pathlib import Path

from kpi_store import cut
from kpi_store import ontology_view as ov
from kpi_store.change import ChangeRefused, approval, kpi_tables, new_measures, other_modules, proposal, reference_items

WHAT = "the apply command"


@dataclass(frozen=True)
class Target:
    """The modules a run changes, and how: the code that writes their tables, the built files the round trip
    compares, the builders whose Turtle it verifies and the tests it runs. `module` is the one the others depend on,
    and `changed` gives each changed module's route ({} for the release's route on `module` alone)."""
    module: str
    what: str            # what one proposal is: "term change", "new KPI" or "reference item"
    apply_changes: object  # (changes, facts, scratch release) -> the rebuilt file
    outputs: tuple       # ((built file from the release's top folder, (before, after) -> (KGCL lines, facts)), ...)
    builders: tuple      # ((folder, builder script), ...), each verified against a fresh build
    tests: tuple         # ((folder, unittest module), ...), with the changed module's name
    changed: dict = field(default_factory=dict)


KPI = Target("kpi", "term change", lambda changes, facts, root: kpi_tables.apply_changes(changes, root),
             ((kpi_tables.MEASURES, lambda before, after: (kpi_tables.compare(before, after), [])),),
             ((kpi_tables.KPI_FOLDER, kpi_tables.BUILDER),), (("kpi", kpi_tables.KPI_FOLDER, "test_measures"),))


def _new_kpi_target(changed):
    """A run of new KPIs: the kpi module, and the value-stream and data-product modules when the KPIs link to them.
    Every built file a new KPI may change is compared, the changed ones' builders verified and their tests run."""
    outputs = tuple((cut.ONTOLOGY / path, lambda before, after, name=name: other_modules.compare(name, before, after))
                    for name, path in other_modules.BUILT.items())
    builders = tuple(b for m in changed for b in other_modules.BUILDERS[m])
    tests = tuple((m, folder, t) for m in changed for folder, t in other_modules.TESTS[m])
    return Target("kpi", "new KPI", other_modules.apply_changes, outputs, builders, tests, changed)


def _item_target(kind):
    return Target(kind.module, "reference item", lambda changes, facts, root: reference_items.apply_changes(changes, root),
                  ((kind.folder / kind.output, lambda before, after: (reference_items.compare(before, after, kind), [])),),
                  ((kind.folder, kind.builder),), ((kind.module, kind.folder, kind.tests),))


def target_of(proposals):
    """The one module the proposals change, and how. Raises ChangeRefused for proposals of two modules, of two kinds
    of item, or of term changes and new KPIs together."""
    def kind(p):
        made = {c.subject.split(":", 1)[0] for c in p.changes if c.kind == "create node"}
        if "measure" in made:
            return "new KPI"
        return "term change" if not made and all(c.subject.startswith("measure:") for c in p.changes) else "item"
    kinds = {kind(p) for p in proposals}
    if "item" in kinds and len(kinds) > 1:
        raise ChangeRefused("these proposals change two modules: the kpi module and the module of a new reference "
                            "item. Apply them one module at a time")
    if kinds == {"new KPI", "term change"}:
        raise ChangeRefused("these proposals are term changes and new KPIs. Apply the new KPIs first, then the "
                            "term changes, one run each")
    if kinds == {"new KPI"}:
        changed, noted = {}, {}
        for p in proposals:   # each proposal must make whole measures, and whole links, itself
            kpi, kpi_facts, *_ = other_modules.split(p.changes, p.facts)
            new_measures.measures(kpi, kpi_facts)
            for subject, _ in new_measures.return_notes(kpi, kpi_facts):
                if subject in noted:
                    raise ChangeRefused(f"the proposals {noted[subject]} and {p.change} both add a sentence to the scope "
                                        f"note of {subject}. Apply them one at a time")
                noted[subject] = p.change
            # Each module the proposal changes takes the higher of the route its lines suggest and the proposal's.
            for m, suggested in other_modules.modules_of(p.changes).items():
                changed[m] = proposal.highest([changed.get(m, suggested), suggested, p.route])
        return _new_kpi_target({m: changed[m] for m in other_modules.BUILDERS if m in changed})
    stray = [p.change for p in proposals if p.facts]
    if stray:
        raise ChangeRefused(f"the proposal {', '.join(stray)} holds {proposal.FACTS_FILE}, which only a new KPI has")
    if kinds == {"term change"}:
        return KPI
    kinds = {reference_items.kind_of(p.changes).name for p in proposals}   # each proposal must make whole items itself
    if len(kinds) != 1:
        raise ChangeRefused("one apply adds items of one kind. Apply the proposals for each kind of item on its own")
    return _item_target(reference_items.KINDS[kinds.pop()])


def next_version(current, route, newest):
    """The version after `current` for a route: 1.3.0 gives 1.3.1, 1.4.0 or 2.0.0. A patch after a correction version
    takes the next patch, as next_version.py's cascade does: 1.3.1-correction.1 gives 1.3.2."""
    key = newest.version_key(current)
    if key is None:
        raise ChangeRefused(f"{current!r} is not a version")
    major, minor, patch, _ = key
    return {"patch": f"{major}.{minor}.{patch + 1}", "minor": f"{major}.{minor + 1}.0", "major": f"{major + 1}.0.0"}[route]


def plan(folders, root):
    """The proposals, read and checked, the module they change (a Target), the route of the release and {module:
    (current, new version)} for that module and every module that depends on it, in release order. Reads the release
    and writes nothing."""
    if not folders:
        raise ChangeRefused("name at least one proposal folder")
    proposals = [proposal.read(f) for f in folders]
    # Case does not count: on Windows and macOS approvals/TC-1.json and approvals/tc-1.json are one file.
    ids = [p.change.lower() for p in proposals]
    twice = sorted({p.change for p in proposals if ids.count(p.change.lower()) > 1})
    if twice:
        raise ChangeRefused(f"the proposal {', '.join(twice)} is named twice")
    clash = proposal.conflicts(proposals)
    if clash:
        raise ChangeRefused("the proposals conflict, so none was applied: " + "; ".join(clash)
                            + ". Apply one, then make a new form for the other from the changed ontology")
    target = target_of(proposals)
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
    changed = target.changed or {target.module: route}
    order = cut._run("list the modules to release", ["dependents.py", target.module], release).split()
    for module in order:
        spec = modules[module]
        if spec.get("stage") is not None:
            raise ChangeRefused(f"{module} {spec['version']} is a release candidate; release it before a change")
        versions[module] = (spec["version"], next_version(spec["version"], changed.get(module, "patch"), newest))
    return proposals, target, route, versions


def describe(proposals, route, versions):
    """The plan as lines for the person who runs the command."""
    lines = [f"{len(proposals)} proposal{'s' if len(proposals) != 1 else ''} to apply:"]
    for p in proposals:
        signed = ", ".join(s["role"] for s in p.record["signatures"])
        lines.append(f"  {p.change}: {p.route}, signed by {signed}")
        lines += [f"    {line}" for line in p.lines]
        lines += [f"    fact {','.join(f)}" for f in p.facts]
    lines.append(f"The route of the release: {route}. Versions it writes:")
    lines += [f"  {m} {old} -> {new}" for m, (old, new) in versions.items()]
    return lines


def _round_trip(root, staging, proposals, target):
    """The difference between each built file before and after is exactly the proposals' KGCL lines and facts."""
    back = []
    for path, compare in target.outputs:
        lines, facts = compare(root / path, staging / path)
        back += lines + [",".join(f) for f in facts]
    wanted = [line for p in proposals for line in p.lines] + [",".join(f) for p in proposals for f in p.facts]
    if sorted(back) != sorted(wanted):
        missing, extra = sorted(set(wanted) - set(back)), sorted(set(back) - set(wanted))
        raise cut.CutFailed(f"the {_named(target)} module{'s do' if len(_changed(target)) > 1 else ' does'} not hold exactly the proposals' changes: missing "
                            f"{missing or 'none'}, more {extra or 'none'}. The release is as it was.")


def _changed(target):
    return list(target.changed or [target.module])


def _named(target):
    names = _changed(target)
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


DEPENDENT_WHY = "Takes the new version of what it requires; nothing else changes."   # as next_version.py's cascade


def _write_record(staging, p):
    """The approval record of one proposal, its change file beside it, and a new KPI's facts."""
    path = approval.write_record(staging, p.change, p.route, p.record["signatures"], p.record["new_module"])
    with path.with_suffix(".kgcl").open("w", encoding="utf-8", newline="\n") as f:
        f.write("".join(line + "\n" for line in p.lines))
    if p.facts:
        with path.with_suffix(".facts.csv").open("w", encoding="utf-8", newline="") as f:
            f.write(proposal.facts_text(p.facts))


def apply(folders, release_root=".", say=print, now=None, before_step=None):
    """Applies the proposals and returns the paths the release changed. Raises ChangeRefused when a proposal or the
    release stops it before anything is done, and cut.CutFailed when a step fails: the release is then as it was,
    unless the message names paths that could not be put back. `before_step(name)` is called before each step."""
    root = Path(release_root).resolve()
    try:
        cut._requirements(root)
    except cut.CutRefused as err:
        raise ChangeRefused(str(err)) from None
    proposals, target, route, versions = plan(folders, root)
    module, changed = target.module, _changed(target)
    for line in describe(proposals, route, versions):
        say(line)
    try:
        git = cut._git_ready(root, "", WHAT)
    except cut.CutRefused as err:
        raise ChangeRefused(str(err)) from None
    now = now or dt.datetime.now(dt.timezone.utc)
    date = now.strftime("%Y-%m-%d")
    records = [f"approvals/{p.change}.json" for p in proposals]
    # The approval that the new version names: the record of a proposal on the release's route, and the words of
    # the signer that route needs, as signed: the Ontology Owner for a major, else the Architect. The changelog lists
    # every record.
    lead = next(p for p in proposals if p.route == route)
    role = "Ontology Owner" if route == "major" else "Architect"
    words = next(s["words"] for s in lead.record["signatures"] if s["role"] == role)
    many = len(proposals) > 1
    kept = [f"approvals/{p.change}.facts.csv" for p in proposals if p.facts]
    why = (f"Applies the {target.what}{'s' if many else ''} {', '.join(p.change for p in proposals)}: "
           + "; ".join(line for p in proposals for line in p.lines) + f". Approval records: {', '.join(records)}."
           + (f" Facts: {', '.join(kept)}." if kept else ""))
    signed = ["--approver", f"The {role}", "--where", f"approvals/{lead.change}.json", "--words", words, "--date", date]
    ontology = cut.ONTOLOGY
    step = cut._Steps(say, before_step)
    with tempfile.TemporaryDirectory(prefix="kpi-store-apply-") as tmp:
        staging, backup = Path(tmp) / "release", Path(tmp) / "backup"
        release = staging / ontology / "release"
        step("copy the release", lambda: shutil.copytree(root, staging, ignore=shutil.ignore_patterns(*cut.IGNORED)))
        for p in proposals:
            step(f"write the approval record of {p.change}", lambda p=p: _write_record(staging, p))
        changes = [c for p in proposals for c in p.changes]
        facts = [f for p in proposals for f in p.facts]
        names = _named(target)
        step(f"apply the changes to the {names} tables and rebuild the {names} module{'s' if len(changed) > 1 else ''}",
             lambda: target.apply_changes(changes, facts, staging))
        step(f"compare the {names} module{'s' if len(changed) > 1 else ''} before and after",
             lambda: _round_trip(root, staging, proposals, target))
        routes = target.changed or {module: route}
        # Each module in release order: a changed one on its own route, every other one that depends on one a patch,
        # as next_version.py's cascade gives them. Each package is written after those it requires; then each module
        # is finished, which moves its old package to releases/previous/.
        for m, (old_m, new_m) in versions.items():
            kind, reason = (routes[m], why) if m in routes else ("patch", DEPENDENT_WHY)
            step(f"set {m} to {new_m}", lambda m=m, new_m=new_m, kind=kind, reason=reason: cut._run(
                f"set {m}", ["next_version.py", "start", m, new_m, kind, "--why", reason, *signed], release))
            step(f"write the {m} package", lambda m=m: cut._run(f"write the {m} package",
                                                                 ["build_module.py", m, "--write"], release))
        for m, (old_m, _) in versions.items():
            step(f"finish {m}", lambda m=m, old_m=old_m: cut._run(f"finish {m}", ["next_version.py", "finish", m, old_m],
                                                                  release))
        verify = [(f"the Turtle of {b}", [b, "--verify"], staging / f) for f, b in target.builders]
        cut._outputs(staging, versions, cut._has_intake(staging), step, verify)
        for m, f, t in target.tests:
            step(f"run the {m} module's tests", lambda m=m, f=f, t=t: cut._run(f"run the {m} module's tests",
                                                                               ["-m", "unittest", "-q", t], staging / f))
        step("check that the release agrees with itself", lambda: cut._versions_agree(staging, versions))
        files = cut._difference(root, staging)
        step("write the release", lambda: cut._apply(root, staging, files, backup))
        if git != "none":
            name = f"the {target.what} {proposals[0].change}" if not many else f"{len(proposals)} {target.what}s"
            subject = f"Apply {name}: " + ", ".join(f"{m} {versions[m][1]}" for m in changed)
            body = "\n".join([f"Approval records: {', '.join(records)}.", "", "The KGCL lines:"]
                             + [line for p in proposals for line in p.lines]
                             + (["", "The facts (measure, property, value):"] + [",".join(f) for f in facts] if facts else []))
            cut._commit_paths(root, files, subject, body, backup, WHAT)
    others = len(versions) - len(changed)
    now_at = [f"{m} {versions[m][1]}" for m in changed]
    now_at = now_at[0] if len(now_at) == 1 else f"{', '.join(now_at[:-1])} and {now_at[-1]}"
    say(f"Done. {now_at.replace(' ', ' is now ', 1)} ({route}), "
        f"and {others} module{'s' if others != 1 else ''} that depend on {'it' if len(changed) == 1 else 'them'} "
        f"took a new patch. The apply changed {len(files)} files" + (", and Git committed them." if git != "none" else "."))
    say(f"Run the full check before you load: {cut.CHECK_COMMAND} (on Windows, in Git Bash). Then load the stores with "
        "the runner: python -m kpi_store.runner")
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kpi_store.apply",
                                 description="Apply approved proposals to their module and release it, or change nothing.")
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
