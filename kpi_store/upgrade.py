"""The upgrade command: brings the tools of a newer release into your copy, and keeps your ontology as it is.

    python -m kpi_store.upgrade --from kpi-store-1.3.zip --plan    # say what would change, and change nothing
    python -m kpi_store.upgrade --from kpi-store-1.3.zip           # upgrade the tools of this release folder
    python -m kpi_store.upgrade --from <unpacked folder> [--release <your release folder>] [--stores <settings>]

Why it exists: after handover your copy is the master of the ontology's content (KPI-DEC-0002, Q2). A newer release
brings tools: the commands, the scripts, the skills and the guides. This command takes those into your copy and
leaves every content file you changed as you made it (KPI-DEC-0006: a content file you left as shipped takes the new
release's version).

Which files are tools: the new release lists them in kpi_store/upgrade-paths.txt, one pattern a line. `**` matches
any number of folders, `*` any part of one name, and a line that starts with `!` takes paths out again. Every
other file is content. A content file the new release changes takes the new version when your copy left it as
shipped, and keeps your version when your copy changed it; a path that a `!` line takes out always keeps yours. No command
writes release.json, so a copy takes the new release's name with its tools. A table (a .csv file) that both changed, whose header the new release changes, is refused: your change
has to be made again in the new format. A content file that is new in
the new release, and that your copy does not have, is added, because a new tool may need it. A new file whose name
differs only in the case of its letters from one your copy has is refused, because Windows and macOS hold one file
for both.

How it works, with Git, which the runbook asks you to keep the release folder in:
1. The base is what your copy's tools were last taken from: of the tags named kpi-store-<version>-tools in your
   copy's history, which this command makes, the one of the highest version, or else the copy's first commit, the release as it was unpacked, which
   the runbook's "Keep the release folder in Git" makes. The release's name comes from its release.json. A new
   release older than the base is refused, and one of the same version changes nothing.
2. On top of the base it commits the new release's tool files, its new content files and the content files your
   copy left as shipped. The commit is not on any
   branch yet, and no file of your folder changes.
3. In a temporary copy of your folder, outside it, Git merges that commit into your work. A tool file you never
   changed takes the new version. A tool file your commands changed, such as the tables that list the modules,
   gets both changes, line by line. When the same lines changed on both sides, the upgrade stops and names the
   files. Then the release's full check, bash scripts/check.sh, runs in the temporary copy.
4. Only when the merge and the check pass, and your folder is still on the same commit and branch with nothing
   uncommitted, does the tag kpi-store-<version>-tools mark the base for the next upgrade and your folder move to
   the merged commit. A move that fails deletes the tag again.
Any refusal or failure leaves your folder, its branch, its history and its tags as they were. Before step 2 nothing
is written at all, so --plan writes nothing. After it, the objects of a refused upgrade stay in Git's store, on no
branch and under no tag, until Git's own clean-up removes them.

What it reads and writes: it reads the new release (a zip, unpacked into a temporary folder, or a folder, whose text
files must have LF line ends, as the zip's do) and your release folder, and the local settings for [tools] bash when
--stores or KPI_STORE_LOCAL names them. In your folder's Git it adds the commits and the tag. It writes the temporary copy and the check's
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

from kpi_store import cut, local_settings, runner, setup_check

PATHS_FILE = Path("kpi_store") / "upgrade-paths.txt"
RELEASE_FILE = "release.json"
RELEASE_NAME = re.compile(r"KPI Store (\d+(?:\.\d+)*)")
TAGS = "kpi-store-*-tools"
TAG = re.compile(r"kpi-store-(\d+(?:\.\d+)*)-tools")
# A zip made with macOS Finder holds this folder beside the release; it is never part of a release.
FINDER = "__MACOSX"


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


def is_own(path, patterns):
    """True when the last pattern that matches the path is a `!` line: the copy's own file, never replaced."""
    own = False
    for include, regex in patterns:
        if regex.match(path):
            own = not include
    return own


def is_tool(path, patterns):
    """True when the last pattern that matches the path includes it."""
    found = False
    for include, regex in patterns:
        if regex.match(path):
            found = include
    return found


# ---------- the new release ----------

def _unpack(zip_path, into):
    """Unpacks the release zip into a new folder. Refuses a file that is not a zip, a zip with no file, an entry that
    would land outside the folder or names no file, and a link. Leaves out the folder macOS Finder adds (FINDER)."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = []
            for info in archive.infolist():
                name = PurePosixPath(info.filename)
                if FINDER in name.parts:
                    continue
                if (name.is_absolute() or ".." in name.parts or "\\" in info.filename or ":" in info.filename
                        or not name.parts or name.parts == (".",)):
                    raise UpgradeRefused(f"the zip holds the entry {info.filename!r}, which would land outside the "
                                         "release folder or names no file")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise UpgradeRefused(f"the zip holds the link {info.filename!r}; a release zip holds files only")
                members.append(info)
            if not any(not m.is_dir() for m in members):
                raise UpgradeRefused(f"{zip_path} holds no file")
            # On Windows and macOS one entry would land on the other as it is unpacked, so the plan never sees both.
            twins = sorted(set(case_twins(m.filename for m in members).values()))
            if twins:
                raise UpgradeRefused(f"the zip holds names that differ only in the case of their letters: "
                                     f"{', '.join(twins[0])}, and Windows and macOS hold one file for both")
            archive.extractall(into, members)
    except UpgradeRefused:
        raise
    # Each kind of stream raises its own error for damage (zlib, bz2, lzma), and zipfile others for a password, an
    # unknown compression or a short file: any of them means the zip cannot be read.
    except Exception as err:
        raise UpgradeRefused(f"{zip_path} cannot be read as a zip ({type(err).__name__}: {err})") from None
    entries = list(Path(into).iterdir())
    # A zip made by hand may hold the release in one top folder; the runner's zip holds its files at the top.
    if len(entries) == 1 and entries[0].is_dir() and not (Path(into) / RELEASE_FILE).exists():
        return entries[0]
    return Path(into)


def case_twins(paths):
    """{name: every spelling of its group, itself included, sorted} for every name, of a whole path or of a folder
    on its way, that has another spelling among these paths differing only in the case of its letters. Paths are read as zipfile unpacks them:
    "./" and doubled slashes are left out, so "./kpi_store//A.py" is "kpi_store/A.py"."""
    spellings = {}
    for path in paths:
        parts = PurePosixPath(path).parts
        for end in range(1, len(parts) + 1):
            name = "/".join(parts[:end])
            spellings.setdefault(name.casefold(), set()).add(name)
    return {name: tuple(sorted(names)) for names in spellings.values() if len(names) > 1 for name in names}


def _release_name(text, where):
    try:
        name = json.loads(text).get("release", "")
    except (ValueError, AttributeError):
        name = ""
    if not isinstance(name, str) or not RELEASE_NAME.fullmatch(name):
        raise UpgradeRefused(f"{where} does not name a release such as \"KPI Store 1.2\" under \"release\"")
    return name


def version(release):
    """The release's version as numbers, so 1.10 comes after 1.9."""
    return tuple(int(part) for part in RELEASE_NAME.fullmatch(release).group(1).split("."))


def _files(folder):
    """Every file of the new release by its path with forward slashes, leaving out Git's folder, caches and FINDER."""
    out = {}
    for path in sorted(Path(folder).rglob("*")):
        rel = path.relative_to(folder)
        if (cut.IGNORED | {FINDER}) & set(rel.parts) or not path.is_file():
            continue
        out[rel.as_posix()] = path
    return out


def _windows_line_ends(files):
    """The text files that hold a CRLF line end. The release zip holds LF line ends only, as .gitattributes keeps
    the copy's; a file of bytes (with a NUL in it) is not text and is left out."""
    found = []
    for rel, path in files.items():
        data = path.read_bytes()
        if b"\r\n" in data and b"\0" not in data:
            found.append(rel)
    return found


def tag_name(release):
    return f"kpi-store-{RELEASE_NAME.fullmatch(release).group(1)}-tools"


# ---------- Git ----------

def _git(root, *args, stdin=None, env=None):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, encoding="utf-8",
                          env={**{k: v for k, v in os.environ.items() if k not in cut.GIT_PLACE}, **(env or {})},
                          input=stdin, check=False)


def _out(root, *args, **kw):
    done = _git(root, *args, **kw)
    if done.returncode != 0:
        raise UpgradeRefused(f"git {args[0]} failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout


def _ready(root):
    """Git is installed, the folder is a Git copy with every change committed, and Git knows who commits."""
    state = cut._git_state(root)
    if state == "none":
        raise UpgradeRefused("this release folder is not a Git copy. The upgrade keeps your changes by Git's history, "
                             "so put the folder in Git first, as the runbook's \"Keep the release folder in Git\" "
                             "says. A copy you never changed can instead be replaced by the new zip")
    if state == "no git":
        raise UpgradeRefused("this folder is a Git copy, and Git is not installed. Install Git, then upgrade again")
    if state == "no author":
        raise UpgradeRefused("this Git copy has no user.name or user.email, so the upgrade could not commit. Run these "
                             'two commands, then upgrade again:\n  git config user.name "<your name or role>"\n'
                             '  git config user.email "<your e-mail address>"')
    if state == "dirty":
        cut._git_ready(root, "", what="the upgrade")   # raises CutRefused, which names the files


def _base(root):
    """The commit the copy's tools were last taken from, and the release it holds: the tag of the highest version
    among the kpi-store-<version>-tools tags in HEAD's history, else the copy's one first commit."""
    tags = [name for name in _out(root, "tag", "--merged", "HEAD", "--list", TAGS).split() if TAG.fullmatch(name)]
    if tags:
        tag = max(tags, key=lambda name: version(f"KPI Store {TAG.fullmatch(name).group(1)}"))
        commit = _out(root, "rev-list", "-n", "1", f"refs/tags/{tag}").strip()
        # The tag names the tools' release. The release.json at the tag is content, the copy's own, so it is not read.
        return commit, f"KPI Store {TAG.fullmatch(tag).group(1)}", f"the tag {tag}"
    roots = _out(root, "rev-list", "--max-parents=0", "HEAD").split()
    if len(roots) != 1:
        raise UpgradeRefused("this copy's history has more than one first commit, so the upgrade cannot tell which "
                             "release it started from")
    shown = _git(root, "show", f"{roots[0]}:{RELEASE_FILE}")
    release = _release_name(shown.stdout if shown.returncode == 0 else "", f"the {RELEASE_FILE} of this copy's first commit")
    return roots[0], release, "the first commit"


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
    """Git's blob ids of these files (absolute paths), in order, from one Git command; `write` also stores them.
    Bytes are taken as they are (--no-filters): the files hold LF line ends (_windows_line_ends)."""
    if not paths:
        return []
    args = ["hash-object", "--no-filters", "--stdin-paths"] + (["-w"] if write else [])
    return _out(root, *args, stdin="".join(f"{p}\n" for p in paths)).split()


# ---------- the plan ----------

class Plan:
    def __init__(self, base, base_release, base_from, release, head, branch, entries=None, updated=(), merged=(),
                 removed=(), added=(), kept=(), renewed=()):
        self.base, self.base_release, self.base_from, self.release = base, base_release, base_from, release
        self.head, self.branch, self.entries = head, branch, entries or {}
        self.updated, self.merged, self.removed = list(updated), list(merged), list(removed)
        self.added, self.kept, self.renewed = list(added), list(kept), list(renewed)

    def describe(self):
        def some(paths):
            head = ", ".join(paths[:5])
            return head + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")
        lines = [f"From {self.base_release} (at {self.base_from}) to the tools of {self.release}."]
        for label, paths in (("tool files that take the new version", self.updated),
                             ("tool files you changed, which get both changes", self.merged),
                             ("tool files the new release removes", self.removed),
                             ("new files added", self.added),
                             ("content files you left as shipped, which take the new version", self.renewed),
                             ("content files the new release changes, which keep your version", self.kept)):
            lines.append(f"  {len(paths)} {label}" + (f": {some(paths)}" if paths else ""))
        return "\n".join(lines)


def plan(root, new_root):
    """Works out the upgrade and writes nothing, not even to Git's object store: the base, and what happens to each
    file. plan.entries holds, by path, (mode, blob, file) for each file to commit and None for each to remove."""
    root, new_root = Path(root), Path(new_root)
    if not (new_root / PATHS_FILE).is_file():
        raise UpgradeRefused(f"the new release has no {PATHS_FILE.as_posix()}, so it is not a release this command "
                             "can upgrade from")
    release = _release_name((new_root / RELEASE_FILE).read_text(encoding="utf-8") if (new_root / RELEASE_FILE).is_file()
                            else "", f"the new release's {RELEASE_FILE}")
    patterns = read_patterns((new_root / PATHS_FILE).read_text(encoding="utf-8"))
    base, base_release, base_from = _base(root)
    head = _out(root, "rev-parse", "HEAD").strip()
    branch = _git(root, "symbolic-ref", "-q", "HEAD").stdout.strip()
    the_plan = Plan(base, base_release, base_from, release, head, branch)
    if version(release) <= version(base_release):
        return the_plan
    new = _files(new_root)
    crlf = _windows_line_ends(new)
    if crlf:
        raise UpgradeRefused(f"the new release's files have Windows line ends (CRLF): {', '.join(crlf[:5])}"
                             f"{' and more' if len(crlf) > 5 else ''}. Give the zip as the release's team sent it")
    old, now = _tree(root, base), _tree(root, head)
    ids = dict(zip(sorted(new), _blobs(root, [str(new[p].resolve()) for p in sorted(new)], write=False)))
    twins = case_twins(set(old) | set(now) | set(new))
    for path in sorted(set(old) | set(new)):
        tool = is_tool(path, patterns)
        if path in new and (tool or (path not in old and path not in now)):
            blob = ids[path]
            if path in old and old[path][1] == blob:
                continue
            parts = PurePosixPath(path).parts
            prefixes = ["/".join(parts[:end]) for end in range(1, len(parts) + 1)]
            clashing = next((name for name in prefixes if name in twins), None)
            if path not in old and clashing:
                raise UpgradeRefused(f"the new release's {path} differs only in the case of its letters from "
                                     f"{', '.join(n for n in twins[clashing] if n != clashing)}, and Windows and macOS hold one "
                                     "file or folder for both")
            the_plan.entries[path] = (old.get(path, ("100644",))[0], blob, new[path])
            if path not in old:
                the_plan.added.append(path)
            elif now.get(path, (None, None))[1] not in (old[path][1], blob):
                the_plan.merged.append(path)
            else:
                the_plan.updated.append(path)
        elif path in old and tool:
            the_plan.entries[path] = None
            the_plan.removed.append(path)
        elif path in new and path in old and ids[path] != old[path][1]:
            as_shipped = now.get(path, (None, None))[1] == old[path][1]
            if as_shipped and not is_own(path, patterns):
                the_plan.entries[path] = (old[path][0], ids[path], new[path])
                the_plan.renewed.append(path)
                continue
            if path in now and not as_shipped and path.endswith(".csv"):
                before = _out(root, "cat-file", "blob", old[path][1]).split("\n", 1)[0]
                after = new[path].read_text(encoding="utf-8").split("\n", 1)[0]
                if before.strip() != after.strip():
                    raise UpgradeRefused(
                        f"the new release changes the columns of {path}, and this copy changed that table too, so the "
                        "copy's change cannot be kept as it is. Make it again in the new format: replace the release "
                        "with the new zip, as the runbook's \"Replace the release with a newer zip\" says, then let "
                        "the runner cut a correction again from a new report, and propose and apply a change from a "
                        "form again from its form")
            the_plan.kept.append(path)
        elif path in new and path not in old:
            the_plan.kept.append(path)
    return the_plan


def _vendor(root, the_plan):
    """Stores the files and commits, on top of the base, the new release's tool files and new files, through a
    temporary index. The commit is on no branch, and the folder's own index and files are not touched."""
    files = [(p, e) for p, e in the_plan.entries.items() if e is not None]
    written = _blobs(root, [str(e[2].resolve()) for _, e in files], write=True)
    if written != [e[1] for _, e in files]:
        raise UpgradeRefused("a file of the new release changed while the upgrade read it")
    with tempfile.TemporaryDirectory(prefix="kpi-store-upgrade-index-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _out(root, "read-tree", the_plan.base, env=env)
        lines = [f"0 {'0' * 40}\t{p}" if e is None else f"{e[0]} {e[1]}\t{p}" for p, e in the_plan.entries.items()]
        _out(root, "update-index", "-z", "--index-info", stdin="".join(line + "\0" for line in lines), env=env)
        tree = _out(root, "write-tree", env=env).strip()
    return _out(root, "commit-tree", tree, "-p", the_plan.base, "-m", f"The tools of {the_plan.release}",
                "-m", "Made by python -m kpi_store.upgrade: the new release's tool files and new files on top of the "
                      "tools this copy had. The merge commit after it brings them into the copy.").strip()


# ---------- the upgrade ----------

def _check_command(root, stores, environ):
    """bash scripts/check.sh, with the bash of the local settings' [tools] bash when --stores or KPI_STORE_LOCAL
    names the settings file, as the runner does, else the one the setup check finds."""
    setting = None
    named = stores or environ.get(local_settings.ENV_VAR)
    if named:
        try:
            setting = local_settings.load(named, environ, release_root=root).bash
        except local_settings.LocalSettingsError as err:
            raise UpgradeRefused(f"the local settings could not be read: {err}") from None
    bash = setup_check.find_bash(setting)
    if bash is None:
        raise UpgradeRefused("bash was not found, and the check is a bash script. Install Git for Windows, or name "
                             "bash.exe in [tools] bash; python -m kpi_store.setup_check --only bash says more")
    return [str(bash), "scripts/check.sh"]


def upgrade(release_root=".", source=None, plan_only=False, say=print, check=None, stores=None, environ=None):
    """Upgrades the tools of the release folder from `source`, a zip or a folder. `check` is the command the merged
    copy must pass, by default bash scripts/check.sh (_check_command)."""
    root = Path(release_root).resolve()
    environ = os.environ if environ is None else environ
    _ready(root)
    source = Path(source).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="kpi-store-upgrade-") as tmp:
        try:
            is_file, is_dir = source.is_file(), source.is_dir()
            digest = hashlib.sha256(source.read_bytes()).hexdigest() if is_file else None
        except OSError as err:
            raise UpgradeRefused(f"{source} cannot be read ({type(err).__name__})") from None
        if is_file:
            say(f"The zip's SHA-256 is {digest}.")
            new_root = _unpack(source, Path(tmp) / "new")
        elif is_dir:
            new_root = source
        else:
            raise UpgradeRefused(f"{source} is neither a zip nor a folder")
        the_plan = plan(root, new_root)
        if version(the_plan.release) < version(the_plan.base_release):
            raise UpgradeRefused(f"the new release is {the_plan.release}, older than the tools of {the_plan.base_release} "
                                 "that this copy has")
        if version(the_plan.release) == version(the_plan.base_release):
            say(the_plan.describe())
            say(f"This copy has the tools of {the_plan.release} already. Nothing was changed.")
            return the_plan
        say(the_plan.describe())
        if not the_plan.entries:
            say("The new release changes no tool file. Nothing was changed.")
            return the_plan
        if plan_only:
            say("This was the plan only. Nothing was changed.")
            return the_plan
        check = check or _check_command(root, stores, environ)
        tag = tag_name(the_plan.release)
        if cut._tag_exists(root, tag):
            raise UpgradeRefused(f"this copy already has the tag {tag}, which the upgrade would make. Find out what it "
                                 f"marks, and delete it (git tag -d {tag}) only if it is a mistake")
        commit = _vendor(root, the_plan)
        merged = _merge_and_check(root, commit, the_plan, Path(tmp), say, check)
        _move(root, merged, commit, tag, the_plan)
    say(f"Upgraded to the tools of {the_plan.release}. The tag {tag} marks them for the next upgrade.")
    return the_plan


def _merge_and_check(root, commit, the_plan, tmp, say, check):
    """Merges the tools commit into HEAD in a temporary worktree and runs the check there. Returns the merge commit.
    The worktree is removed, and Git's list of worktrees pruned, however this ends."""
    work = tmp / "copy"
    try:
        _out(root, "worktree", "add", "-q", "--detach", str(work), the_plan.head)
        done = _git(work, "merge", "-q", "--no-ff", "-m", f"Upgrade the tools to {the_plan.release}",
                    "-m", f"Made by python -m kpi_store.upgrade from {the_plan.base_release}.", commit)
        if done.returncode != 0:
            both = [p for p in _git(work, "diff", "--name-only", "-z", "--diff-filter=U").stdout.split("\0") if p]
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
        shutil.rmtree(work, ignore_errors=True)
        _git(root, "worktree", "prune")


def _move(root, merged, commit, tag, the_plan):
    """Tags the tools commit, then moves the folder to the merge commit. It first makes sure the folder is still on
    the commit and the branch the plan read, with nothing uncommitted. A failed tag changes nothing; a failed move
    deletes the tag again."""
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    branch = _git(root, "symbolic-ref", "-q", "HEAD").stdout.strip()
    if head != the_plan.head or branch != the_plan.branch or cut._uncommitted(root):
        raise UpgradeRefused("the folder changed while the check ran: its commit, its branch or its files. Upgrade again")
    _out(root, "tag", tag, commit)
    done = _git(root, "merge", "-q", "--ff-only", merged)
    if done.returncode != 0:
        _git(root, "tag", "-d", tag)
        raise UpgradeRefused(f"git merge failed: {(done.stderr or done.stdout).strip()}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kpi_store.upgrade",
                                 description="Bring the tools of a newer release into this copy, and keep its content.")
    ap.add_argument("--from", dest="source", required=True, help="the new release: its zip, or the unpacked folder")
    ap.add_argument("--release", default=".", help="your release folder (default: this folder)")
    ap.add_argument("--plan", action="store_true", help="say what would change, and change nothing")
    ap.add_argument("--stores", help="the local settings file, for its [tools] bash (default: KPI_STORE_LOCAL)")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not shutil.which("git"):
        print("Not upgraded: Git is not installed. Nothing was changed.", file=sys.stderr)
        return 1
    try:
        upgrade(a.release, a.source, plan_only=a.plan, stores=a.stores)
    except (UpgradeRefused, cut.CutRefused) as err:
        print(f"Not upgraded: {err}. Nothing was changed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
