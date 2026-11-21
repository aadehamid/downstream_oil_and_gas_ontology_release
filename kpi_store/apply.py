"""The apply command: applies approved proposals to their module and releases it, or changes nothing.

    python -m kpi_store.apply <proposal folder> [<proposal folder> ...] [--release <folder>]

A proposal folder is what the propose command wrote (kpi_store/propose.py): change.kgcl, approval.json and
summary.txt, and facts.csv when some facts are ones KGCL cannot write. A term change changes the kpi module; a new KPI
changes kpi, and value-stream and data-product when it links to them (kpi_store/change/other_modules.py); a new
reference item changes its own module, system for a system and data-product for a table
(kpi_store/change/reference_items.py); a process map request changes organization, its roles and their RACI entries
(kpi_store/change/process_map.py), and core when it adds business areas, processes or steps
(kpi_store/change/core_release.py): core takes its next minor, by a builder written from release/build_core_template.py,
and every other module a patch. One run applies proposals of one kind: term changes, new KPIs, reference items of
one kind, process map requests or domain activations; a process map request that adds a business area, a process
or a step goes in a run of its own. Each changed module takes its own route, and every module that
depends on one takes a patch, once. The command refuses, before it does anything else:
- a proposal whose approval record lacks a signature its route needs (the Data Owner, or the Global Process Owner of
  a process map request, and the Architect; the Ontology Owner too for a major), or whose route is lower than its
  changes suggest (KPI-DEC-0002, Q4, Q5 and Q13);
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

A new module (kpi_store/change/new_module.py) goes in a run of its own. Its run writes the approval record, writes the
module's folder from its pattern (release/module_patterns.py) and registers the module in every place the release
lists its modules (release/register_module.py), builds its Turtle, checks that the module holds exactly the
proposal's lines and facts, writes its package at 1.0.0, rebuilds the catalog, the projection manifest, the KPI intake
pack and the pages, runs the competency questions, the module's tests and the whole-graph shapes gate, and then
writes and commits the release. It needs the Data Owner's, the Ontology Owner's and the Architect's signatures.

A new module that an AI drafted (kpi_store/change/drafted.py) goes the same way, with two more steps. Before anything
else, the plan checks that its approval record shows all five gates of KPI-DEC-0002, Q19 passed, that the draft's
files are those the record fingerprints, and that gates 1, 2 and 4 still pass against this release. The run then writes
the module's folder from the drafted pattern (release/drafted_module.py), and checks that the built folder holds
exactly the proposal's draft.

A domain activation changes no module: the ontology holds no list of domains. Its run writes the approval record and
the facts, makes the domain active in kpi-intake/settings.toml (kpi_store/change/domains.py), checks that the list
differs by exactly the facts, rebuilds the KPI intake pack and verifies it, so the KPI form offers the domain, and
then writes and commits the release as above. A domain activation needs the Domain Owner's and the Architect's
signatures.

Needs Python 3.11 or later with rdflib and pyshacl, and openpyxl when the release holds the KPI intake pack. A Git
copy needs Git; a plain folder needs none and gets the same files with no commit.
"""
import argparse
import dataclasses
import datetime as dt
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from kpi_store import cut
from kpi_store import ontology_view as ov
from kpi_store.change import (ChangeRefused, approval, core_release, domains, drafted, kgcl, kpi_tables, new_measures,
                              new_module, other_modules, process_map, proposal, reference_items)

WHAT = "the apply command"


@dataclass(frozen=True)
class Target:
    """The modules a run changes, and how: the code that writes their tables, the built files the round trip
    compares, the builders whose Turtle it verifies and the tests it runs. `module` is the one the others depend on,
    and `changed` gives each changed module's route ({} for the release's route on `module` alone)."""
    module: str
    what: str            # what one proposal is: "term change", "new KPI" or "reference item"
    apply_changes: object  # (changes, facts, scratch release) -> the rebuilt file
    outputs: tuple       # ((built file from the release's top folder, or (before, after) when the two differ,
                         #   (before, after) -> (KGCL lines, facts)), ...)
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


ORGANIZATION = Target("organization", "process map request",
                      lambda changes, facts, root: process_map.apply_changes(changes, facts, root),
                      tuple((path, lambda before, after, name=name: process_map.compare(name, before, after))
                            for name, path in process_map.BUILT.items()),
                      process_map.BUILDERS, process_map.TESTS)
DOMAINS = "domain activation"
NEW_MODULE = "new module"
CORE = "core"   # a process map request that adds a process, a step or a business area: target_of, then _core_target


def _core_target(root, proposals):
    """A run of the one process map request that adds processes, steps or business areas: core at its next minor,
    written by core_release.release, and organization too when the request adds roles or RACI entries. Its apply_changes needs
    the change id, the approval words and the date, which apply() gives it (_with_release)."""
    try:
        old, _ = core_release.core_graph(root)
    except (KeyError, OSError, ValueError) as err:
        raise ChangeRefused(f"{root} holds no released core: {err}") from None
    new = core_release.next_minor(old)
    org = any(not core_release.is_core(c) for p in proposals for c in p.changes)
    outputs = (((cut.ONTOLOGY / "releases" / "core" / old / "core.ttl", cut.ONTOLOGY / "releases" / "core" / new / "core.ttl"),
                core_release.compare),)
    if org:
        outputs += ORGANIZATION.outputs
    builders = ((core_release.RELEASE, core_release.builder_name(new)),) + core_release.READERS
    return Target(CORE, "process map request", None, outputs, builders, ORGANIZATION.tests if org else (),
                  {"core": "minor", **({"organization": "minor"} if org else {})}), (old, new)


def _with_release(target, change, words, date):
    """The core target with its apply_changes: the core release, then the roles and RACI entries on the new map."""
    def apply_changes(changes, facts, root):
        core = [c for c in changes if core_release.is_core(c)]
        core_facts = [f for f in facts if f[0].startswith("proc:")]
        core_release.release(core, core_facts, root, change, words, date)
        others = [c for c in changes if not core_release.is_core(c)]
        if others:
            process_map.apply_changes(others, [f for f in facts if not f[0].startswith("proc:")], root)
    return dataclasses.replace(target, apply_changes=apply_changes)


def _item_target(kind):
    return Target(kind.module, "reference item", lambda changes, facts, root: reference_items.apply_changes(changes, root),
                  ((kind.folder / kind.output, lambda before, after: (reference_items.compare(before, after, kind), [])),),
                  ((kind.folder, kind.builder),), ((kind.module, kind.folder, kind.tests),))


def target_of(proposals):
    """The one module the proposals change, and how. Raises ChangeRefused for proposals of two modules, of two kinds
    of item, or of term changes and new KPIs together."""
    def kind(p):
        if p.record["new_module"]:
            return NEW_MODULE
        if p.owner == "Domain Owner":
            return DOMAINS
        if p.owner == "Global Process Owner":
            return "process map request"
        made = {c.subject.split(":", 1)[0] for c in p.changes if c.kind == "create node"}
        if "measure" in made:
            return "new KPI"
        return "term change" if not made and all(c.subject.startswith("measure:") for c in p.changes) else "item"
    kinds = {kind(p) for p in proposals}
    if NEW_MODULE in kinds:
        if len(proposals) > 1:
            raise ChangeRefused("a new module is applied in a run of its own, so that its first release names its "
                                "approval. Apply the proposals one at a time")
        if not new_module.is_new_module(proposals[0].facts):
            raise ChangeRefused(f"the proposal {proposals[0].change} is approved as a new module, and its facts name none")
        return NEW_MODULE
    for one in (DOMAINS, "process map request"):
        if one in kinds and len(kinds) > 1:
            raise ChangeRefused(f"these proposals are {one}s and other changes. Apply the {one}s in a run of their own")
    if kinds == {DOMAINS}:
        return DOMAINS
    if kinds == {"process map request"}:
        if not any(core_release.is_core(c) for p in proposals for c in p.changes):
            return ORGANIZATION
        if len(proposals) > 1:
            raise ChangeRefused("A process map request that adds a process, a step or a business area is applied in a "
                                "run of its own, so that the core release names its approval. Apply the proposals one at "
                                "a time")
        return CORE
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
    if target == DOMAINS:
        for p in proposals:
            domains.check_changes(p.facts, root)
    route = proposal.highest(p.route for p in proposals)
    if target == DOMAINS:
        return proposals, target, route, {}
    if target == NEW_MODULE:
        key = next(s for s, _, _ in proposals[0].facts if s.startswith(new_module.SUBJECT))[len(new_module.SUBJECT):]
        if route != "major":
            raise ChangeRefused(f"the proposal {proposals[0].change} is approved as {route}, and a new module's first "
                                "release is a major")
        if key in cut._modules(root / cut.ONTOLOGY / "release" / "build_module.py") or (root / cut.ONTOLOGY / key).exists():
            raise ChangeRefused(f"the release holds a module or a folder named {key} already")
        if drafted.is_drafted(proposals[0].facts):   # every gate of the AI draft, checked again before anything is written
            drafted.check_proposal(proposals[0], root)
        elif "draft" in proposals[0].record:
            raise ChangeRefused(f"the proposal {proposals[0].change} holds the record of an AI draft, and its facts name "
                                "another pattern")
        return proposals, target, route, {key: (None, new_module.VERSION)}
    versions = {}
    if target == CORE:
        target, versions["core"] = _core_target(root, proposals)
    release = root / cut.ONTOLOGY / "release"
    try:
        modules = cut._modules(release / "build_module.py")
        newest = ov.release_scripts_newest(root)
    except (OSError, cut.CutRefused, ov.ReleaseError) as err:
        raise ChangeRefused(f"{root} is not a KPI Store release: {err}") from None
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
    if not versions:
        lines.append("No module of the ontology changes: the ontology holds no list of domains.")
        return lines
    lines.append(f"The route of the release: {route}. Versions it writes:")
    lines += [f"  {m} {old} -> {new}" if old else f"  {m}: a new module at {new}" for m, (old, new) in versions.items()]
    return lines


def _round_trip(root, staging, proposals, target):
    """The difference between each built file before and after is exactly the proposals' KGCL lines and facts."""
    back = []
    for path, compare in target.outputs:
        before, after = path if isinstance(path, tuple) else (path, path)
        lines, facts = compare(root / before, staging / after)
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
    path = approval.write_record(staging, p.change, p.route, p.record["signatures"], p.record["new_module"], p.owner,
                                 p.record.get("ai"), p.record.get("draft"))
    if p.lines:
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
    for line in describe(proposals, route, versions):
        say(line)
    try:
        git = cut._git_ready(root, "", WHAT)
    except cut.CutRefused as err:
        raise ChangeRefused(str(err)) from None
    if target == DOMAINS:
        return _apply_domains(root, proposals, git, say, before_step)
    if target == NEW_MODULE:
        return _apply_new_module(root, proposals[0], versions, git, say, before_step, now)
    module, changed = target.module, _changed(target)
    now = now or dt.datetime.now(dt.timezone.utc)
    date = now.strftime("%Y-%m-%d")
    modules = {m: v for m, v in versions.items() if m != CORE}   # the modules build_module.py and next_version.py release
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
    if module == CORE:
        target = _with_release(target, lead.change, words, date)
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
        for m, (old_m, new_m) in modules.items():   # core's package is written with the changes, by its own builder
            kind, reason = (routes[m], why) if m in routes else ("patch", DEPENDENT_WHY)
            step(f"set {m} to {new_m}", lambda m=m, new_m=new_m, kind=kind, reason=reason: cut._run(
                f"set {m}", ["next_version.py", "start", m, new_m, kind, "--why", reason, *signed], release))
            step(f"write the {m} package", lambda m=m: cut._run(f"write the {m} package",
                                                                 ["build_module.py", m, "--write"], release))
        for m, (old_m, _) in versions.items():
            step(f"finish {m}", lambda m=m, old_m=old_m: cut._run(f"finish {m}", ["next_version.py", "finish", m, old_m],
                                                                  release))
        verify = [(f"the Turtle of {b}", [b, "--verify"], staging / f) for f, b in target.builders]
        cut._outputs(staging, modules, cut._has_intake(staging), step, verify)
        for m, f, t in target.tests:
            step(f"run the {m} module's tests", lambda m=m, f=f, t=t: cut._run(f"run the {m} module's tests",
                                                                               ["-m", "unittest", "-q", t], staging / f))
        step("check that the release agrees with itself", lambda: cut._versions_agree(staging, modules))
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


def _apply_domains(root, proposals, git, say, before_step):
    """A run of domain activations: the approval records and facts, the list of domains of settings.toml, and the KPI
    intake pack rebuilt and verified, in a temporary copy first. Returns the paths the release changed."""
    if not cut._has_intake(root):
        raise ChangeRefused("the release holds no KPI intake pack, and a domain activation changes the pack's settings")
    records = [f"approvals/{p.change}.json" for p in proposals]
    facts = [f for p in proposals for f in p.facts]
    step = cut._Steps(say, before_step)
    intake = [*cut.INTAKE]
    with tempfile.TemporaryDirectory(prefix="kpi-store-apply-") as tmp:
        staging, backup = Path(tmp) / "release", Path(tmp) / "backup"
        step("copy the release", lambda: shutil.copytree(root, staging, ignore=shutil.ignore_patterns(*cut.IGNORED)))
        for p in proposals:
            step(f"write the approval record of {p.change}", lambda p=p: _write_record(staging, p))
        step(f"make the domain active in {domains.SETTINGS.as_posix()}", lambda: domains.apply_changes(facts, staging))

        def round_trip():
            back = [",".join(f) for f in domains.compare(root, staging)]
            if sorted(back) != sorted(",".join(f) for f in facts):
                raise cut.CutFailed(f"{domains.SETTINGS.as_posix()} does not hold exactly the proposals' facts: "
                                    f"{back}. The release is as it was.")
        step(f"compare {domains.SETTINGS.as_posix()} before and after", round_trip)
        step("rebuild the KPI intake pack", lambda: cut._run("rebuild the KPI intake pack", [*intake, "--root", str(staging)], staging))
        step("verify the KPI intake pack", lambda: cut._run("verify the KPI intake pack",
                                                            [*intake, "--root", str(staging), "--check"], staging))
        labels = {d["id"]: d["label"] for d in domains.read(staging)[1]}
        names = ", ".join(sorted(labels[s.split(":", 1)[1]] for s in {s for s, _, _ in facts}))
        files = cut._difference(root, staging)
        step("write the release", lambda: cut._apply(root, staging, files, backup))
        if git != "none":
            name = f"the domain activation {proposals[0].change}" if len(proposals) == 1 else f"{len(proposals)} domain activations"
            body = "\n".join([f"Approval records: {', '.join(records)}.", "", "The facts (item, property, value):"]
                             + [",".join(f) for f in facts])
            cut._commit_paths(root, files, f"Apply {name}: {names} active", body, backup, WHAT)
    many = len({s for s, _, _ in facts}) > 1
    say(f"Done. The domain{'s' if many else ''} {names} {'are' if many else 'is'} now active, and the KPI form offers "
        f"{'them' if many else 'it'} in question 1.5. The apply changed "
        f"{len(files)} files" + (", and Git committed them." if git != "none" else "."))
    say(f"Run the full check: {cut.CHECK_COMMAND} (on Windows, in Git Bash). No store needs loading: the ontology has "
        "not changed.")
    return files


def _holds_the_proposal(key, lines, facts, proposed_lines, proposed_facts):
    """Raises CutFailed unless a new module's lines and facts, read back from its Turtle, are the proposal's: the same
    lines and facts, and the properties of a reference table in the proposal's order, which is the order of its
    table's columns."""
    facts, proposed = [tuple(f) for f in facts], [tuple(f) for f in proposed_facts]
    if sorted(lines) != sorted(proposed_lines) or sorted(facts) != sorted(proposed):
        missing = sorted(set(proposed_lines) - set(lines)) + sorted(",".join(f) for f in set(proposed) - set(facts))
        extra = sorted(set(lines) - set(proposed_lines)) + sorted(",".join(f) for f in set(facts) - set(proposed))
        raise cut.CutFailed(f"the {key} module does not hold exactly the proposal's changes: missing "
                            f"{missing or 'none'}, more {extra or 'none'}. The release is as it was.")
    order = lambda rows: [f[2] for f in rows if f[0].startswith(new_module.SUBJECT) and f[1] == "property"]
    if order(facts) != order(proposed):
        raise cut.CutFailed(f"the {key} module does not hold the proposal's properties in the order of the proposal: "
                            f"{', '.join(order(facts))}, and the proposal asks for {', '.join(order(proposed))}. "
                            "The release is as it was.")


def _holds_the_draft(staging, key, files, p):
    """Raises CutFailed unless a drafted module's folder holds exactly the proposal's draft, and its KGCL lines are the
    proposal's."""
    try:
        drafted.compare(staging, key, files)
        built = drafted.read_files(staging / cut.ONTOLOGY / key, staging)
        lines = [kgcl.write_line(c) for c in drafted.changes_of(p.record["draft"]["module"], built, staging)]
    except ChangeRefused as err:
        raise cut.CutFailed(f"{err}. The release is as it was.") from None
    if lines != p.lines:
        raise cut.CutFailed(f"the {key} module's lines are not the proposal's. The release is as it was.")


def _apply_new_module(root, p, versions, git, say, before_step, now):
    """A run of one new module: its folder written from the proposal and registered in every place, its Turtle built
    and compared with the proposal, its first package written, then the catalog, the projection manifest, the KPI
    intake pack, the competency questions and the pages rebuilt and verified, and its tests and the whole-graph
    shapes gate run, in a temporary copy first. Returns the paths the release changed."""
    (key, (_, version)), = versions.items()
    date = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%d")
    words = next(s["words"] for s in p.record["signatures"] if s["role"] == "Ontology Owner")
    step = cut._Steps(say, before_step)
    ontology = cut.ONTOLOGY
    with tempfile.TemporaryDirectory(prefix="kpi-store-apply-") as tmp:
        staging, backup = Path(tmp) / "release", Path(tmp) / "backup"
        release, folder = staging / ontology / "release", staging / ontology / key
        step("copy the release", lambda: shutil.copytree(root, staging, ignore=shutil.ignore_patterns(*cut.IGNORED)))
        step(f"write the approval record of {p.change}", lambda: _write_record(staging, p))
        if drafted.is_drafted(p.facts):
            files = drafted.read_files(p.folder / drafted.DRAFT_FOLDER, staging)
            step(f"write the {key} module's folder from its AI draft and register it in every place",
                 lambda: drafted.write(p, files, staging, words, date))
            mp = drafted.pattern(staging)
            compare = lambda: _holds_the_draft(staging, key, files, p)
        else:
            step(f"write the {key} module's folder and register it in every place",
                 lambda: new_module.write(p.changes, p.facts, staging, p.change, words, date))
            mp = new_module.patterns(staging)
            compare = lambda: _holds_the_proposal(key, *new_module.compare(staging, key), p.lines, p.facts)
        builder = mp.builder_name(key)
        step(f"build the {key} module's Turtle", lambda: cut._run(f"build the {key} module's Turtle", [builder, "--write"], folder))

        step(f"compare the {key} module with the proposal", compare)
        step(f"write the {key} package", lambda: cut._run(f"write the {key} package", ["build_module.py", key, "--write"], release))
        cut._outputs(staging, versions, cut._has_intake(staging), step,
                     (f"the Turtle of {builder}", [builder, "--verify"], folder))
        step("rebuild the pages", lambda: cut._run("rebuild the pages", ["scripts/build_docs_html.py"], staging))
        step("verify the pages", lambda: cut._run("verify the pages", ["scripts/build_docs_html.py", "--check"], staging))
        step(f"run the {key} module's tests", lambda: cut._run(f"run the {key} module's tests",
                                                                ["-m", "unittest", "-q", mp.test_name(key)[:-3]], folder))
        step("run every module's shapes over the whole graph", lambda: cut._run(
            "run every module's shapes over the whole graph", ["-m", "unittest", "-q", "test_all_module_shapes"],
            staging / ontology / "validation"))
        step("check that the release agrees with itself", lambda: _new_module_agrees(staging, key, version))
        files = cut._difference(root, staging)
        step("write the release", lambda: cut._apply(root, staging, files, backup))
        if git != "none":
            body = "\n".join([f"Approval record: approvals/{p.change}.json.", "", "The KGCL lines:", *p.lines, "",
                              "The facts (item, property, value):", *[",".join(f) for f in p.facts]])
            cut._commit_paths(root, files, f"Apply the new module {p.change}: {key} {version}", body, backup, WHAT)
    say(f"Done. {key} {version} is a new module (major). The apply changed {len(files)} files"
        + (", and Git committed them." if git != "none" else "."))
    say(f"Run the full check before you load: {cut.CHECK_COMMAND} (on Windows, in Git Bash). Then load the stores with "
        "the runner: python -m kpi_store.runner")
    return files


def _new_module_agrees(staging, key, version):
    """The new package is the module's newest folder and the catalog's, the projection manifest names it, and the
    example that MODULES.md quotes for it is in the package."""
    import json
    from rdflib import Graph, Namespace
    releases = staging / ov.RELEASES
    if ov.newest_versions(releases).get(key) != version:
        raise cut.CutFailed(f"{key}: the newest folder is not {version}")
    listed = {str(d).rsplit("/", 2)[-2]: str(d).rsplit("/", 1)[-1] for d in Graph().parse(releases / "catalog.ttl", format="turtle")
              .objects(None, Namespace("http://www.w3.org/ns/dcat#").dataset)}
    if listed.get(key) != version:
        raise cut.CutFailed(f"the catalog does not list {key} {version}")
    manifest = json.loads((staging / cut.ONTOLOGY / "projection" / "projection-manifest.json").read_text(encoding="utf-8"))
    if f"releases/{key}/{version}/{key}.ttl" not in manifest["inputs"]:
        raise cut.CutFailed(f"the projection manifest does not name {key} {version}")
    text = (staging / cut.ONTOLOGY / "MODULES.md").read_text(encoding="utf-8")
    block = text.split(f"<!-- module: {key} -->\n```turtle parse\n", 1)[1].split("```", 1)[0]
    package = Graph().parse(releases / key / version / f"{key}.ttl", format="turtle")
    if set(Graph().parse(data=block, format="turtle")) - set(package):
        raise cut.CutFailed(f"MODULES.md quotes a triple of {key} that its package does not hold")


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
