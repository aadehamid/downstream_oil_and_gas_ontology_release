"""The upgrade command: brings the tools of a newer release into your copy, and keeps your ontology as it is.

    python -m kpi_store.upgrade --from kpi-store-1.3.zip --plan    # say what would change, and change nothing
    python -m kpi_store.upgrade --from kpi-store-1.3.zip           # upgrade the tools of this release folder
    python -m kpi_store.upgrade --from <unpacked folder> [--release <your release folder>]

Why it exists: after handover your copy is the master of the ontology's content (KPI-DEC-0002, Q2). A newer release
brings only tools: the commands, the scripts, the skills and the guides. This command takes those into your copy and
leaves every content file as you made it.

Which files are tools: the new release lists them in kpi_store/upgrade-paths.txt, one pattern a line. `**` matches
any number of folders, `*` any part of one name, and a line that starts with `!` takes paths out again. Every
other file is content. A content file the new release changes keeps your version. A content file that is new in
the new release, and that your copy does not have, is added, because a new tool may need it.

How it works, with Git, which the runbook asks you to keep the release folder in:
1. The base is what your copy's tools were last taken from: the newest tag named kpi-store-<version>-tools in your
   copy's history, which this command makes, or else the first commit, "KPI Store <version> as shipped", which the
   runbook's "Keep the release folder in Git" makes.
2. On top of the base it commits the new release's tool files and its new content files. The commit is not on any
   branch yet, and no file of your folder changes.
3. In a temporary copy of your folder, outside it, Git merges that commit into your work. A tool file you never
   changed takes the new version. A tool file your commands changed, such as the tables that list the modules,
   gets both changes, line by line. When the same lines changed on both sides, the upgrade stops and names the
   files. Then the release's full check, bash scripts/check.sh, runs in the temporary copy.
4. Only when the merge and the check pass does your folder move to the merged commit, and the tag
   kpi-store-<version>-tools marks the base for the next upgrade.
Any refusal or failure before step 4 leaves your folder, its history and its tags as they were.

What it reads and writes: it reads the new release (a zip, unpacked into a temporary folder, or a folder) and your
release folder. In your folder's Git it adds the commits and the tag. It writes the temporary copy and the check's
log in the system's temporary folder; the log stays there when the check fails, and the message names it. It does
not write kpi_store.toml, the local settings or any store, and it opens no network connection.

Needs Python 3.11 or later, Git, and bash for the check (Git for Windows brings it).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from kpi_store import cut, runner, setup_check

PATHS_FILE = Path("kpi_store") / "upgrade-paths.txt"
RELEASE_FILE = "release.json"
SHIPPED = re.compile(r"(KPI Store \d+(?:\.\d+)*) as shipped")
RELEASE_NAME = re.compile(r"KPI Store (\d+(?:\.\d+)*)")
TAGS = "kpi-store-*-tools"


class UpgradeRefused(Exception):
    """The upgrade cannot go ahead. Nothing in the release folder changed."""


# ---------- which files are tools ----------

def _pattern(line):
    """One pattern of upgrade-paths.txt as a regular expression over a path with forward slashes."""
    out, at = [], 0
    while at < len(line):
        if line.startswith("**/", at):
            out.append("(?:.*/)?")
            at += 3
        elif line.startswith("**", at):
            out.append(".*")
            at += 2
        elif line[at] == "*":
            out.append("[^/]*")
            at += 1
        elif line[at] == "?":
            out.append("[^/]")
            at += 1
        else:
            out.append(re.escape(line[at]))
            at += 1
    return re.compile("".join(out) + r"\Z")


def read_patterns(text):
    """The (include, regex) pairs of upgrade-paths.txt, in order. Blank lines and lines starting with # are left out."""
    pairs = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        include = not line.startswith("!")
        pairs.append((include, _pattern(line.lstrip("!"))))
    return pairs


def is_tool(path, patterns):
    """True when the last pattern that matches the path includes it."""
    found = False
    for include, regex in patterns:
        if regex.match(path):
            found = include
    return found


# ---------- the new release ----------

def _unpack(zip_path, into):
    """Unpacks the release zip into a new folder, refusing an entry that would land outside it or is a link."""
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in info.filename or ":" in info.filename:
                raise UpgradeRefused(f"the zip holds the entry {info.filename!r}, which would land outside the release folder")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise UpgradeRefused(f"the zip holds the link {info.filename!r}; a release zip holds files only")
        archive.extractall(into)
    entries = [p for p in Path(into).iterdir()]
    # A zip made by hand may hold the release in one top folder; the runner's zip holds its files at the top.
    if len(entries) == 1 and entries[0].is_dir() and not (Path(into) / RELEASE_FILE).exists():
        return entries[0]
    return Path(into)


def _release_name(text, where):
    try:
        name = json.loads(text).get("release", "")
    except (ValueError, AttributeError):
        name = ""
    if not isinstance(name, str) or not RELEASE_NAME.fullmatch(name):
        raise UpgradeRefused(f"{where} does not name a release such as \"KPI Store 1.2\" under \"release\"")
    return name


def _files(folder):
    """Every file of the new release by its path with forward slashes, leaving out Git's folder and caches."""
    out = {}
    for path in sorted(Path(folder).rglob("*")):
        rel = path.relative_to(folder)
        if cut.IGNORED & set(rel.parts) or not path.is_file():
            continue
        out[rel.as_posix()] = path
    return out


def tag_name(release):
    return f"kpi-store-{RELEASE_NAME.fullmatch(release).group(1)}-tools"


# ---------- Git ----------

def _git(root, *args, stdin=None, env=None):
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, encoding="utf-8",
                          env={**{k: v for k, v in os.environ.items() if k not in cut.GIT_PLACE}, **(env or {})},
                          input=stdin, check=False)
    return done


def _out(root, *args, **kw):
    done = _git(root, *args, **kw)
    if done.returncode != 0:
        raise UpgradeRefused(f"git {args[0]} failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout


def _base(root):
    """The commit the copy's tools were last taken from, and the release it holds."""
    found = _git(root, "describe", "--tags", "--abbrev=0", "--match", TAGS, "HEAD")
    if found.returncode == 0:
        tag = found.stdout.strip()
        commit = _out(root, "rev-list", "-n", "1", tag).strip()
        # The tag names the tools' release. The release.json at the tag is content, the copy's own, so it is not read.
        return commit, f"KPI Store {tag[len('kpi-store-'):-len('-tools')]}", f"the tag {tag}"
    roots = _out(root, "rev-list", "--max-parents=0", "HEAD").split()
    if len(roots) != 1:
        raise UpgradeRefused("this copy's history has more than one first commit, so the upgrade cannot tell which "
                             "release it started from")
    subject = _out(root, "log", "-1", "--format=%s", roots[0]).strip()
    match = SHIPPED.fullmatch(subject)
    if not match:
        raise UpgradeRefused(f"this copy's first commit is \"{subject}\", not \"KPI Store <version> as shipped\" as the "
                             "runbook's \"Keep the release folder in Git\" makes it, so the upgrade cannot tell which "
                             "files came from the release")
    return roots[0], match.group(1), "the first commit"


def _tree(root, commit):
    """{path: (mode, blob)} for every file of the commit."""
    out = {}
    for entry in _out(root, "ls-tree", "-r", "-z", commit).split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        mode, _, blob = meta.split()
        out[path] = (mode, blob)
    return out


def _blobs(root, paths, write):
    """Git's blob ids of these files, in order, from one Git command; `write` also stores them. Bytes are taken as
    they are (--no-filters): the release zip holds LF line ends, as .gitattributes keeps them in the copy."""
    if not paths:
        return []
    args = ["hash-object", "--no-filters", "--stdin-paths"] + (["-w"] if write else [])
    return _out(root, *args, stdin="".join(f"{p}\n" for p in paths)).split()


# ---------- the plan ----------

class Plan:
    def __init__(self, base, base_release, base_from, release, updated, merged, removed, added, kept):
        self.base, self.base_release, self.base_from, self.release = base, base_release, base_from, release
        self.updated, self.merged, self.removed, self.added, self.kept = updated, merged, removed, added, kept

    def describe(self):
        def some(paths):
            head = ", ".join(paths[:5])
            return head + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")
        lines = [f"From {self.base_release} (at {self.base_from}) to the tools of {self.release}."]
        for label, paths in (("tool files that take the new version", self.updated),
                             ("tool files you changed, which get both changes", self.merged),
                             ("tool files the new release removes", self.removed),
                             ("new files added", self.added),
                             ("content files the new release changes, which keep your version", self.kept)):
            lines.append(f"  {len(paths)} {label}" + (f": {some(paths)}" if paths else ""))
        return "\n".join(lines)


def plan(root, new_root):
    """Works out the upgrade without writing anything but Git objects: the base, and what happens to each file."""
    root, new_root = Path(root), Path(new_root)
    if not (new_root / PATHS_FILE).is_file():
        raise UpgradeRefused(f"the new release has no {PATHS_FILE.as_posix()}, so it is not a release this command "
                             "can upgrade from")
    release = _release_name((new_root / RELEASE_FILE).read_text(encoding="utf-8") if (new_root / RELEASE_FILE).is_file()
                            else "", f"the new release's {RELEASE_FILE}")
    patterns = read_patterns((new_root / PATHS_FILE).read_text(encoding="utf-8"))
    base, base_release, base_from = _base(root)
    head = _out(root, "rev-parse", "HEAD").strip()
    if base_release == release:
        return None, Plan(base, base_release, base_from, release, [], [], [], [], [])
    old, now, new = _tree(root, base), _tree(root, head), _files(new_root)
    taken = [p for p in sorted(new) if is_tool(p, patterns) or p not in old]
    blobs = dict(zip(taken, _blobs(root, [str(new[p]) for p in taken], write=True)))
    compared = [p for p in sorted(new) if p in old and p not in blobs]
    ids = dict(zip(compared, _blobs(root, [str(new[p]) for p in compared], write=False)))
    entries, updated, merged, removed, added, kept = {}, [], [], [], [], []
    for path in sorted(set(old) | set(new)):
        tool = is_tool(path, patterns)
        if path in blobs:
            blob = blobs[path]
            mode = old.get(path, ("100644",))[0]
            if path in old and old[path][1] == blob:
                continue
            entries[path] = (mode, blob)
            if path not in old:
                added.append(path)
            elif now.get(path, (None, None))[1] not in (old[path][1], blob):
                merged.append(path)
            else:
                updated.append(path)
        elif path in old and tool:
            entries[path] = None
            removed.append(path)
        elif path in ids and ids[path] != old[path][1]:
            kept.append(path)
    if not entries:
        return None, Plan(base, base_release, base_from, release, [], [], [], [], kept)
    commit = _vendor(root, base, entries, release)
    return commit, Plan(base, base_release, base_from, release, updated, merged, removed, added, kept)


def _vendor(root, base, entries, release):
    """Commits, on top of the base, the new release's tool files and new files, through a temporary index. The
    commit is on no branch, and the folder's own index and files are not touched."""
    with tempfile.TemporaryDirectory(prefix="kpi-store-upgrade-index-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _out(root, "read-tree", base, env=env)
        lines = [f"0 {'0' * 40}\t{p}" if e is None else f"{e[0]} {e[1]}\t{p}" for p, e in entries.items()]
        _out(root, "update-index", "-z", "--index-info", stdin="".join(line + "\0" for line in lines), env=env)
        tree = _out(root, "write-tree", env=env).strip()
    return _out(root, "commit-tree", tree, "-p", base, "-m", f"The tools of {release}",
                "-m", "Made by python -m kpi_store.upgrade: the new release's tool files and new files on top of the "
                      "tools this copy had. The merge commit after it brings them into the copy.").strip()


# ---------- the upgrade ----------

def upgrade(release_root=".", source=None, plan_only=False, say=print, check=None):
    """Upgrades the tools of the release folder from `source`, a zip or a folder. `check` is the command the merged
    copy must pass, by default bash scripts/check.sh with the bash the setup check finds."""
    root = Path(release_root).resolve()
    state = cut._git_ready(root, "", what="the upgrade")
    if state == "none":
        raise UpgradeRefused("this release folder is not a Git copy. The upgrade keeps your changes by Git's history, "
                             "so put the folder in Git first, as the runbook's \"Keep the release folder in Git\" "
                             "says. A copy you never changed can instead be replaced by the new zip")
    source = Path(source)
    with tempfile.TemporaryDirectory(prefix="kpi-store-upgrade-") as tmp:
        if source.is_file():
            say(f"The zip's SHA-256 is {hashlib.sha256(source.read_bytes()).hexdigest()}.")
            new_root = _unpack(source, Path(tmp) / "new")
        elif source.is_dir():
            new_root = source
        else:
            raise UpgradeRefused(f"{source} is neither a zip nor a folder")
        commit, the_plan = plan(root, new_root)
        say(the_plan.describe())
        if the_plan.base_release == the_plan.release:
            say(f"This copy has the tools of {the_plan.release} already. Nothing was changed.")
            return the_plan
        if commit is None:
            say("The new release changes no tool file. Nothing was changed.")
            return the_plan
        if plan_only:
            say("This was the plan only. Nothing was changed.")
            return the_plan
        if check is None:
            bash = setup_check.find_bash()
            if bash is None:
                raise UpgradeRefused("bash was not found, and the check is a bash script. Install Git for Windows; "
                                     "python -m kpi_store.setup_check --only bash says more")
            check = [str(bash), "scripts/check.sh"]
        tag = tag_name(the_plan.release)
        if cut._tag_exists(root, tag):
            raise UpgradeRefused(f"this copy already has the tag {tag}, which the upgrade would make. Find out what it "
                                 f"marks, and delete it (git tag -d {tag}) only if it is a mistake")
        merged = _merge_and_check(root, commit, the_plan, Path(tmp), say, check)
        _move(root, merged, commit, tag)
    say(f"Upgraded to the tools of {the_plan.release}. The tag {tag} marks them for the next upgrade.")
    return the_plan


def _merge_and_check(root, commit, the_plan, tmp, say, check):
    """Merges the tools commit into HEAD in a temporary worktree and runs the check there. Returns the merge commit."""
    work = tmp / "copy"
    _out(root, "worktree", "add", "-q", "--detach", str(work), "HEAD")
    try:
        done = _git(work, "merge", "-q", "--no-ff", "-m", f"Upgrade the tools to {the_plan.release}",
                    "-m", f"Made by python -m kpi_store.upgrade from {the_plan.base_release}.", commit)
        if done.returncode != 0:
            both = _git(work, "diff", "--name-only", "--diff-filter=U").stdout.split()
            _git(work, "merge", "--abort")
            if both:
                raise UpgradeRefused("the new tools and your changes changed the same lines of "
                                     f"{', '.join(both)}. Send this message and those files to the release's team")
            raise UpgradeRefused(f"git merge failed: {(done.stderr or done.stdout).strip()}")
        say("The merge passed. The full check runs on the merged copy now; it takes about 20 minutes.")
        ran = subprocess.run(check, cwd=str(work), capture_output=True, encoding="utf-8", errors="replace",
                             env={k: v for k, v in os.environ.items() if k not in cut.GIT_PLACE}, check=False)
        lines = [line for line in ran.stdout.strip().splitlines() if line.strip()]
        if ran.returncode != 0 or not lines or lines[-1].strip() != runner.CHECK_PASSED:
            log = Path(tempfile.mkdtemp(prefix="kpi-store-upgrade-check-")) / "check.log"
            log.write_text(ran.stdout + ran.stderr, encoding="utf-8")
            raise UpgradeRefused(f"the full check failed on the merged copy (exit {ran.returncode}); its output is in "
                                 f"{log}. Send it to the release's team")
        return _out(work, "rev-parse", "HEAD").strip()
    finally:
        _git(root, "worktree", "remove", "--force", str(work))
        _git(root, "worktree", "prune")


def _move(root, merged, commit, tag):
    """Moves the folder to the merge commit, which is HEAD's child, and tags the tools commit."""
    if cut._uncommitted(root):
        raise UpgradeRefused("the folder changed while the check ran. Commit or put aside the changes, then upgrade again")
    _out(root, "merge", "-q", "--ff-only", merged)
    _out(root, "tag", tag, commit)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kpi_store.upgrade",
                                 description="Bring the tools of a newer release into this copy, and keep its content.")
    ap.add_argument("--from", dest="source", required=True, help="the new release: its zip, or the unpacked folder")
    ap.add_argument("--release", default=".", help="your release folder (default: this folder)")
    ap.add_argument("--plan", action="store_true", help="say what would change, and change nothing")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not shutil.which("git"):
        print("Not upgraded: Git is not installed. Nothing was changed.", file=sys.stderr)
        return 1
    try:
        upgrade(a.release, a.source, plan_only=a.plan)
    except (UpgradeRefused, cut.CutRefused) as err:
        print(f"Not upgraded: {err}. Nothing was changed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
