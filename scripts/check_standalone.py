"""Check that this tree refers to nothing outside itself.

    python3 scripts/check_standalone.py            # every tracked text file, minus the pending list
    python3 scripts/check_standalone.py --strict   # every tracked text file; the pending list is ignored
    python3 scripts/check_standalone.py --rules    # print the deny list

The tree must stand alone: a reader who has only this folder must be able to follow every reference in it.
Each rule below denies one kind of reference that leads outside (RULES), or one part that was removed and that
documents must no longer mention. Public sources and licences stay; GitHub links are checked against an allow
list of the public projects the tree cites (GITHUB_OWNERS).

scripts/standalone-pending.txt lists the paths that are not clean yet, one glob and its reason per line. The
check skips those paths, and it fails when a glob matches no file or matches only clean files, so the list can
only shrink. --strict ignores the list; the final cut must pass with --strict.

A finding prints as `path:line: [rule] the text that matched`. The exit status is 1 when there is a finding or a
stale pending line, else 0.
"""
import argparse
import fnmatch
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING = os.path.join("scripts", "standalone-pending.txt")
# These two files state the deny list and hold one failing line per rule, so they cannot pass it.
OWN_FILES = {"scripts/check_standalone.py", "scripts/test_check_standalone.py"}

# The public projects the tree cites on GitHub, in lower case. A link to any other owner is a finding: add an
# owner here only when the link is a public source or a licence.
GITHUB_OWNERS = {
    "apache", "cmader", "databricks", "databrickslabs", "datatreehouse", "dbpedia", "dgarijo", "jbarrasa",
    "kvistgaard", "mattpocock", "monarch-initiative", "neo4j", "neo4j-contrib", "neo4j-labs", "ontodev", "rdflib",
    "stevehedden",
}

# A colour written in digits alone (#000, #333333) looks like a reference number. It is a colour when it has a
# colour's length, follows a colon, a quote, an equals sign or a border style, and ends where a CSS value ends.
_COLOUR = re.compile(r"""(?:(?<=[:"'=])|(?<=:\s)|(?<=\bsolid\s)|(?<=\bdashed\s)|(?<=\bdotted\s))"""
                     r"""\#(?:\d{3}|\d{4}|\d{6}|\d{8})(?=\s*(?:[;"'),}]|!important|$))""")
# A grade of fuel oil or diesel is written with a number sign (#2 diesel, diesel #2, No. #6 fuel oil).
_FUEL_GRADE = re.compile(r"\#[1-6](?=\s+(?:diesel|fuel|heating|oil|distillate)\b)|(?<=diesel\s)\#[1-6]\b|(?<=oil\s)\#[1-6]\b", re.I)
_NUMBER_SIGN = re.compile(r"(?<![&\w/#])\#\d+\b(?![\w-])")
_GITHUB = re.compile(r"(?<![\w.-])(?:raw\.githubusercontent|github)\.com/([A-Za-z0-9_.-]+)", re.I)


def _number_sign(line):
    """Each `#<digits>` used as a reference: not a character reference (&#8203;), not a URL fragment
    (page.html#3), not a colour and not a fuel grade."""
    spared = [m.span() for pattern in (_COLOUR, _FUEL_GRADE) for m in pattern.finditer(line)]
    return [m for m in _NUMBER_SIGN.finditer(line) if not any(a <= m.start() < b for a, b in spared)]


def _github(line):
    """Each GitHub link whose owner is not on the allow list."""
    return [m for m in _GITHUB.finditer(line) if m.group(1).lower() not in GITHUB_OWNERS]


# A public project's own issue, cited as a source, is named with the project ("OEO issue 1958").
_NUMBERED = re.compile(r"\b(?:PRs?|[Pp]ull [Rr]equests?|[Ii]ssues?)\s+\#?\d+\b")
_PUBLIC_ISSUE = re.compile(r"\bOEO issue \d+\b")


def _numbered_item(line):
    """Each "PR 123", "pull request 123" or "issue 45", except a public project's issue cited as a source."""
    spared = [m.span() for m in _PUBLIC_ISSUE.finditer(line)]
    return [m for m in _NUMBERED.finditer(line) if not any(a <= m.start() < b for a, b in spared)]


def _regex(pattern, flags=0):
    compiled = re.compile(pattern, flags)
    return lambda line: list(compiled.finditer(line))


# (rule, what it denies, a function from a line to its matches)
RULES = [
    ("other-branch", "another repository's branch: \"main branch\", \"on main\", \"from main\", \"origin/main\"",
     _regex(r"\bmain branch\b|\bmain repo(?:sitory)?\b|\b(?i:on|from|of|in|into|to) main\b(?![\w(-]|\.\w)"
            r"|\b(?i:on|from|of|in|into|to) `main`|\borigin/main\b")),
    ("other-release", "the release this tree was cut from, by its old name",
     _regex(r"(?<![A-Za-z])share[ _-]releases?(?![A-Za-z])", re.I)),
    ("reference-number", "a pull request or issue number written as #<digits>", _number_sign),
    ("pull-request", "a pull request or issue named by its number",
     _numbered_item),
    ("decision-record", "a decision record kept elsewhere", _regex(r"EPM-DEC-")),
    ("session", "a session or a handoff folder", _regex(r"~/\.claude|(?<![\w-])\.claude/|\bhandoffs?/|\bhandoff folder", re.I)),
    ("removed-demo", "the removed demo", _regex(r"(?<![\w-])demos/|\bpricing demo\b", re.I)),
    ("removed-aura", "the removed AuraDB copy", _regex(r"\baura(?:db)?\b", re.I)),
    ("removed-docker", "the removed Docker stores", _regex(r"docker", re.I)),
    ("removed-token", "the removed token connector", _regex(r"\baccess tokens?\b|DATABRICKS_TOKEN", re.I)),
    ("github-link", "a GitHub link to an owner that is not an allowed public source", _github),
]


def findings_in(text):
    """(line number, rule, matched text) for every match of every rule, in line order."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for rule, _, matches in RULES:
            for m in matches(line):
                found.append((number, rule, m.group(0)))
    return found


def tracked_files(root=ROOT):
    """Every tracked path from the root; in a tree without Git, every file in it."""
    if os.path.exists(os.path.join(root, ".git")):  # a folder, or a file in a worktree
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        out = subprocess.run(["git", "-C", root, "ls-files", "-z"], check=True, capture_output=True, env=env,
                             stdin=subprocess.DEVNULL).stdout
        names = [os.fsdecode(n) for n in out.split(b"\0") if n]
    else:
        skip = {".git", "__pycache__", ".venv", ".pytest_cache"}
        names = []
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in skip]
            names += [os.path.relpath(os.path.join(folder, f), root).replace(os.sep, "/") for f in files]
    return sorted(n for n in names if os.path.isfile(os.path.join(root, n)))


def read_text(path):
    """The file's text, or None for a file that is not UTF-8 text (an image, a workbook, a font)."""
    with open(path, "rb") as f:
        data = f.read()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def read_pending(root=ROOT):
    """[(glob, reason)] from the pending list. A line is `<glob> :: <reason>`; `#` starts a comment. In a glob
    `*` matches any run of characters, `/` included, so `skills/**` covers everything under skills/."""
    path = os.path.join(root, PENDING)
    if not os.path.exists(path):
        return []
    entries, problems = [], []
    with open(path, encoding="utf-8") as f:
        for number, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            glob, sep, reason = (part.strip() for part in line.partition(" :: "))
            if not sep or not glob or not reason:
                problems.append(f"{PENDING}:{number}: write `<glob> :: <reason>`")
            else:
                entries.append((glob, reason))
    if problems:
        raise ValueError("\n".join(problems))
    return entries


def check(root=ROOT, strict=False):
    """(findings, stale pending lines, summary). A finding is `path:line: [rule] text`."""
    pending = [] if strict else read_pending(root)
    findings, dirty = [], {}
    for name in tracked_files(root):
        if name in OWN_FILES:
            continue
        text = read_text(os.path.join(root, name))
        if text is None:
            continue
        found = findings_in(text)
        if not found:
            continue
        globs = [glob for glob, _ in pending if fnmatch.fnmatchcase(name, glob)]
        if globs:
            for glob in globs:
                dirty.setdefault(glob, {})[name] = len(found)
        else:
            findings += [f"{name}:{number}: [{rule}] {matched}" for number, rule, matched in found]
    names = tracked_files(root)
    stale = []
    for glob, _ in pending:
        if not any(fnmatch.fnmatchcase(name, glob) for name in names):
            stale.append(f"{PENDING}: `{glob}` matches no file; remove the line")
        elif glob not in dirty:
            stale.append(f"{PENDING}: every file under `{glob}` is clean; remove the line")
    summary = [f"pending `{glob}`: {sum(dirty.get(glob, {}).values())} findings in {len(dirty.get(glob, {}))} files ({reason})"
               for glob, reason in pending]
    return findings, stale, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check that this tree refers to nothing outside itself.")
    ap.add_argument("--strict", action="store_true", help="ignore the pending list; the final cut must pass this")
    ap.add_argument("--rules", action="store_true", help="print the deny list and stop")
    ap.add_argument("--root", default=ROOT, help="the tree to check (default: this one)")
    args = ap.parse_args(argv)
    if args.rules:
        for rule, what, _ in RULES:
            print(f"{rule}: {what}")
        return 0
    try:
        findings, stale, summary = check(args.root, args.strict)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    for line in findings + stale:
        print(line)
    for line in summary:
        print(line)
    if findings or stale:
        print(f"not stand-alone: {len(findings)} findings, {len(stale)} stale pending lines", file=sys.stderr)
        return 1
    print("stand-alone" + ("" if args.strict or not summary else f", except the {len(summary)} pending paths above"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
