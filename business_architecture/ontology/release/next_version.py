#!/usr/bin/env python3
"""The repetitive parts of a new version, so a change that reaches many modules is not many hand edits.

    python3 next_version.py start <module> <new version> <patch|minor|major> --why "<one sentence>" \
        --approver "<who>" --where "<where the approval is recorded>" --words "<the sentence that approved it>" [--date YYYY-MM-DD]
    python3 build_module.py <module> --write
    python3 next_version.py finish <module> <old version>
    python3 next_version.py current <module>
    python3 next_version.py cascade <module> --approver "<who>" --where "<where>" --words "<the sentence>"

`start` sets the entry in build_module.py's MODULES (version, issued, approver, approval) and adds a section at the top of
the module's CHANGELOG.md, carrying forward its open gaps. `finish` moves the old package to releases/previous/ and
changes the version in projection/pipeline.py and projection/skill-run/epm-config.json. `current` prints the version the entry holds. You may do any of this by hand.

`cascade` does the rest of a release once the changed module's own new package is written. It gives each module that
depends on the changed one the next patch version (start), writes its package (build_module.py --write), and then
finishes every module, the changed one first. It verifies each package against a fresh build before it finishes
the module. It keeps its plan in cascade-in-progress.json until it ends. Run again after a failure, it takes the
plan up where it stopped: it builds what is missing, and for a module whose old package is already moved it
writes the projection's lists and the stand-alone exceptions again, in case the earlier run stopped before them. A version folder that a
failed build left half written stops it, with the folder to delete.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import newest as newest_on_disk  # noqa: E402

ONTOLOGY = os.path.dirname(HERE)


def set_entry(text, module, version, date, approver, where, words):
    """build_module.py's text with one module's entry changed. It adds `approver` when the entry has none."""
    start = text.find(f'    "{module}": {{\n')
    if start < 0:
        raise SystemExit(f"{module} has no entry in MODULES")
    end = text.index("\n    },\n", start)
    entry = text[start:end]
    entry, n = re.subn(r'"version": "[^"]+"', f'"version": "{version}"', entry, count=1)
    if not n:
        raise SystemExit(f"{module}'s entry has no version")
    fields = re.search(r'^( *)"version": .*$', entry, re.M)
    line = re.sub(r'\s*"(?:issued|approver)": "[^"]*",?', "", fields.group(0)).rstrip(" ,") + ","
    entry = entry.replace(fields.group(0), line, 1)
    # A line that holds only these two fields, one or both: start writes both on one line, so a second start
    # must remove that line, or the entry would hold each key twice and Python would keep the old value.
    entry = re.sub(r'^ *(?:"(?:approver|issued)": "(?:[^"\\]|\\.)*",? *)+\n', "", entry, flags=re.M)
    entry = re.sub(r'^ *"approval": \((?:[^()]|\([^()]*\))*\),\n', "", entry, flags=re.M)
    pad = fields.group(1)
    added = (f'{line}\n{pad}"approver": {quoted(approver)}, "issued": "{date}",\n'
             f'{pad}"approval": ({quoted(where)}, {quoted(words)}),')
    return text[:start] + entry.replace(line, added, 1) + text[end:]


def quoted(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def open_gaps(changelog):
    """The Known gaps of the newest section, or "None."."""
    m = re.search(r"^### Known gaps\n+(.*?)(?=^## |^### |\Z)", changelog, re.M | re.S)
    return m.group(1).strip() if m else "None."


def add_section(changelog, version, date, kind, why, module):
    """The changelog with a new section under its title line, the open gaps carried forward."""
    title, rest = (changelog.split("\n", 1) + [""])[:2] if changelog.startswith("# ") else (f"# {module} changelog", changelog)
    section = (f"## {version} ({date})\n\nA {kind} release. {why}\n\n- [{kind}] {why}\n\n"
               f"### Known gaps\n\n{open_gaps(changelog)}\n\n")
    return f"{title}\n\n{section}{rest.lstrip()}"


def set_lists(pipeline, config, module, old, new):
    """The two lists of versions with one module's version changed."""
    a, n = re.subn(rf'\("{re.escape(module)}", "{re.escape(old)}"\)', f'("{module}", "{new}")', pipeline)
    b, k = re.subn(rf'"{re.escape(module)}": "{re.escape(old)}"', f'"{module}": "{new}"', config)
    if not n or not k:
        raise SystemExit(f"{module} {old} is not in the projection's lists: pipeline.py {n}, epm-config.json {k}")
    return a, b


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def start(a, ontology=ONTOLOGY):
    path = os.path.join(ontology, "release", "build_module.py")
    write(path, set_entry(read(path), a.module, a.version, a.date, a.approver, a.where, a.words))
    log = os.path.join(ontology, "releases", a.module, "CHANGELOG.md")
    write(log, add_section(read(log) if os.path.exists(log) else "", a.version, a.date, a.kind, a.why, a.module))
    print(f"{a.module} is set to {a.version}. Now run: python3 build_module.py {a.module} --write")


def carry_exceptions(ontology, module, old, new):
    """The stand-alone check lists, by path, text that a released package holds and may keep
    (scripts/standalone-exceptions.txt). finish moves the old package and the new one holds the same changelog, so
    each such line follows its package to releases/previous/, and the new package gets a line when it holds the same
    text as often. The cut tool does the same for a correction. A tree with no such list is left alone."""
    path = os.path.join(ontology, "..", "..", "scripts", "standalone-exceptions.txt")
    if not os.path.isfile(path):
        return
    here = "business_architecture/ontology/releases"
    prefix, out = f"{here}/{module}/{old}/", []
    for line in read(path).splitlines():
        parts = [part.strip() for part in line.split(" :: ")]
        if len(parts) != 5 or line.startswith("#") or not parts[0].startswith(prefix):
            out.append(line)
            continue
        name = parts[0][len(prefix):]
        out.append(" :: ".join([f"{here}/previous/{module}/{old}/{name}", *parts[1:]]))
        fresh = os.path.join(ontology, "releases", module, new, name)
        if os.path.isfile(fresh) and str(read(fresh).count(parts[2])) == parts[3]:
            out.append(" :: ".join([f"{here}/{module}/{new}/{name}", *parts[1:]]))
    # Written beside the list and then moved over it: a stop halfway leaves the whole old list, never a part of it,
    # so a rerun still finds every line it has to move.
    with open(path + ".new", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    os.replace(path + ".new", path)


def finish(a, ontology=ONTOLOGY):
    newest = [v for v in os.listdir(os.path.join(ontology, "releases", a.module)) if newest_on_disk.version_key(v)]
    new = max(newest, key=newest_on_disk.version_key)
    if new == a.old:
        raise SystemExit(f"{a.module} {a.old} is still the newest package: write the new one first")
    folder = os.path.join(ontology, "releases", "previous", a.module)
    source, target = os.path.join(ontology, "releases", a.module, a.old), os.path.join(folder, a.old)
    pipeline, config = (os.path.join(ontology, "projection", "pipeline.py"),
                        os.path.join(ontology, "projection", "skill-run", "epm-config.json"))
    # Everything that can stop this is checked before anything changes.
    p, c = set_lists(read(pipeline), read(config), a.module, a.old, new)
    if not os.path.isdir(source) or os.path.exists(target):
        raise SystemExit(f"cannot move {source} to {target}: the source is missing or the target exists")
    # A failed write (a full disk) stops here with nothing changed; the two replaces are renames in one folder.
    write(pipeline + ".new", p)
    write(config + ".new", c)
    os.makedirs(folder, exist_ok=True)
    shutil.move(source, target)
    os.replace(pipeline + ".new", pipeline)
    os.replace(config + ".new", config)
    carry_exceptions(ontology, a.module, a.old, new)
    print(f"{a.module} {a.old} moved to releases/previous/; the projection's lists name {new}")


def settle(ontology, module, old, new):
    """What finish does after it has moved the old package: the version in the projection's two lists, and the
    stand-alone exceptions. Safe to repeat: a list that names the new version already is left as it is. A finish
    that stopped between the move and these writes leaves them undone, so cascade runs this for every module whose
    old package is already moved."""
    pipeline, config = (os.path.join(ontology, "projection", "pipeline.py"),
                        os.path.join(ontology, "projection", "skill-run", "epm-config.json"))
    p = re.sub(rf'\("{re.escape(module)}", "{re.escape(old)}"\)', f'("{module}", "{new}")', read(pipeline))
    c = re.sub(rf'"{re.escape(module)}": "{re.escape(old)}"', f'"{module}": "{new}"', read(config))
    if f'("{module}", "{new}")' not in p or f'"{module}": "{new}"' not in c:
        raise SystemExit(f"{module} {new} is not in the projection's lists, and {old} is not there to replace")
    for path, text in ((pipeline, p), (config, c)):
        if text != read(path):
            write(path + ".new", text)
            os.replace(path + ".new", path)
    carry_exceptions(ontology, module, old, new)


def current_version(module, ontology=ONTOLOGY):
    text = read(os.path.join(ontology, "release", "build_module.py"))
    start_at = text.find(f'    "{module}": {{\n')
    if start_at < 0:
        raise SystemExit(f"{module} has no entry in MODULES")
    found = re.search(r'"version": "([^"]+)"', text[start_at:text.index("\n    },\n", start_at)])
    if not found:
        raise SystemExit(f"{module}'s entry has no version")
    return found.group(1)


def current(a, ontology=ONTOLOGY):
    print(current_version(a.module, ontology))


def next_patch(version):
    """The next ordinary patch. 1.2.0 gives 1.2.1. A correction version gives the patch after it: 1.2.1-correction.2
    gives 1.2.2, because no plain 1.2.1 is released beside the corrections."""
    key = newest_on_disk.version_key(version)
    if key is None:
        raise SystemExit(f"{version!r} is not a version")
    return f"{key[0]}.{key[1]}.{key[2] + 1}"


def packages(module, ontology=ONTOLOGY):
    """The versions of a module's packages in releases/<module>/, oldest first."""
    folder = os.path.join(ontology, "releases", module)
    found = [v for v in os.listdir(folder) if newest_on_disk.version_key(v)] if os.path.isdir(folder) else []
    return sorted(found, key=newest_on_disk.version_key)


def run_script(args, ontology=ONTOLOGY):
    """Runs one of the release scripts with this Python, from the release folder, and returns what it printed. Each
    run is a new process, so it reads build_module.py as start has just left it."""
    done = subprocess.run([sys.executable, "-B", *args], cwd=os.path.join(ontology, "release"), capture_output=True,
                          text=True, encoding="utf-8")
    if done.returncode != 0:
        raise SystemExit(f"{' '.join(args)} failed:\n{(done.stdout + done.stderr).strip()}")
    return done.stdout


CASCADE_PLAN = "cascade-in-progress.json"


def cascade_plan(a, ontology, order):
    """{module: [old version, new version]} for the changed module and each module that depends on it, in release
    order. It is worked out once and kept in release/cascade-in-progress.json until the cascade ends, so a run that
    stopped halfway is taken up where it stopped: a finished module holds one package again, and without the plan
    it could not be told from a module that was never started."""
    path = os.path.join(ontology, "release", CASCADE_PLAN)
    if os.path.isfile(path):
        kept = json.loads(read(path))
        if kept.get("module") != a.module:
            raise SystemExit(f"a cascade of {kept.get('module')} stopped halfway. Finish it first: run cascade "
                             f"{kept.get('module')} again")
        return kept["versions"], path
    versions = {}
    if a.module != "core":   # core is released by hand first, and its list holds only the modules that depend on it
        held = packages(a.module, ontology)
        if len(held) != 2:
            raise SystemExit(f"write {a.module}'s new package first: releases/{a.module}/ must hold the old package and "
                             f"the new one, and it holds {', '.join(held) or 'none'}")
        versions[a.module] = held
    for module in order:
        if module != a.module:
            old = current_version(module, ontology)
            versions[module] = [old, next_patch(old)]
    write(path, json.dumps({"module": a.module, "versions": versions}, indent=2) + "\n")
    return versions, path


def cascade(a, ontology=ONTOLOGY, order=None, build=None, verify=None, finish_one=None):
    """The rest of a release, after the changed module's own new package is written. Every package is verified
    against a fresh build (build_module.py --verify) before its module is finished: a folder that a failed build
    left half written is never taken for a package."""
    order = order if order is not None else run_script(["dependents.py", a.module], ontology).split()
    build = build or (lambda module: run_script(["build_module.py", module, "--write"], ontology))
    verify = verify or (lambda module: run_script(["build_module.py", module, "--verify"], ontology))
    finish_one = finish_one or (lambda module, old: finish(argparse.Namespace(module=module, old=old), ontology))
    versions, plan = cascade_plan(a, ontology, order)
    to_finish = []
    for module, (old, new) in versions.items():
        held = packages(module, ontology)
        if held == [new] and os.path.isdir(os.path.join(ontology, "releases", "previous", module, old)):
            settle(ontology, module, old, new)   # an earlier finish may have stopped right after the move
            print(f"{module} {new} is finished already")
            continue
        if new not in held:
            if module == a.module:
                raise SystemExit(f"releases/{module}/ no longer holds {new}. Write {module}'s package again, then run cascade again")
            if current_version(module, ontology) != new:   # an earlier run may have set the version and stopped in the build
                start(argparse.Namespace(module=module, version=new, kind="patch", date=a.date, why=a.why,
                                         approver=a.approver, where=a.where, words=a.words), ontology)
            build(module)
        try:
            verify(module)
        except SystemExit as err:
            raise SystemExit(f"releases/{module}/{new} is not a whole package: it does not equal a fresh build. Delete "
                             f"that folder, then run cascade again{'' if module != a.module else ' after you have written the package again'}.\n{err}") from None
        to_finish.append((module, old))
    for module, old in to_finish:
        finish_one(module, old)
    os.remove(plan)
    print(f"{len(versions)} modules released. Now rebuild the catalog and the projection manifest, and run the check.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("module"); s.add_argument("version"); s.add_argument("kind", choices=("patch", "minor", "major"))
    s.add_argument("--why", required=True); s.add_argument("--approver", required=True)
    s.add_argument("--where", required=True); s.add_argument("--words", required=True)
    s.add_argument("--date", default=datetime.date.today().isoformat())
    f = sub.add_parser("finish")
    f.add_argument("module"); f.add_argument("old")
    c = sub.add_parser("current")
    c.add_argument("module")
    k = sub.add_parser("cascade")
    k.add_argument("module"); k.add_argument("--approver", required=True)
    k.add_argument("--where", required=True); k.add_argument("--words", required=True)
    k.add_argument("--why", default="Takes the new version of what it requires; nothing else changes.")
    k.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    {"start": start, "finish": finish, "current": current, "cascade": cascade}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
