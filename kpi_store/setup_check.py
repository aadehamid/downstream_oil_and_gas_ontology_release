"""Checks the one-time setup of the machine that runs the KPI Store loads, and prints the one fix for each failure.

    py -m kpi_store.setup_check --stores <local settings file>              # every check
    py -m kpi_store.setup_check --stores <local settings file> --only java  # one check
    py -m kpi_store.setup_check --list                                      # the checks' names

The checks, in order: python, packages, local-settings, kpi-store-settings, java, fuseki-jar, robot-jar, bash, uv,
check-script-tools, databricks-cli, databricks-auth, neo4j-local, neo4j-plugins, neo4j-enterprise.

Each check prints "ok" or "FAIL" with what it found, and a failed check prints one line that fixes it. A check
that needs the local settings file fails with that file's fix when the file is missing. No check changes
anything: the Neo4j checks only read, and no password is printed.

Run it once on a new machine, before the first run of the runner (kpi_store.runner), and again after you change
the machine. The runner does not call it. The runner does use two functions of this file, find_bash and
find_databricks, so both commands look for those tools in the same places.

The checks follow the chain's needs in order: Python and its packages; the two settings files; Java and the
Fuseki jar for the Fuseki load; the ROBOT jar for the Neo4j load; bash and uv for scripts/check.sh; the Databricks
CLI and its sign-in; then the local Neo4j with its plugins and the Neo4j Enterprise database.

Each check is a function that takes the Context and returns (passed, what it found, the fix). CHECKS, near the
end, maps each check's name to its function and sets the order.

Exit 0 when every check passed, 1 when one failed, 2 on bad arguments.
"""
import argparse
import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import load_fuseki
from . import local_settings as ls
from . import settings as settings_module

PYTHON_MINIMUM = (3, 11)   # the first Python with tomllib, which reads both settings files
# The versions the release was tested with. The notebook installs the same ones where it needs them.
PACKAGES = {"rdflib": "7.6.0", "pyshacl": "0.40.2", "pyoxigraph": "0.5.13", "neo4j": "6.4.1",
            "databricks-sdk": "0.164.0", "sqlglot": "30.31.0", "pyyaml": "6.0.3"}
# A jar is accepted by its checksum, not by its file name: a jar of another version may still start, and may
# behave differently from the one the release was tested with.
ROBOT_SHA256 = "16a73c074f3df359a7338a84b4e0788785fe06117f931bb9796e9619ea776105"   # ROBOT 1.9.10
# The local Neo4j and its two plugins, at the versions the load and its checks were tested with. The check
# accepts no other: n10s imports the ontology, and its result must be the one the checks expect.
NEO4J_VERSION, N10S_VERSION, APOC_VERSION = "2025.06.2", "2025.06.1", "2025.06.2"
# Where Git for Windows puts bash.exe. C:\Windows\System32\bash.exe is not a bash: it starts the Linux subsystem.
GIT_BASH_FOLDERS = ("{ProgramFiles}/Git/bin", "{ProgramFiles(x86)}/Git/bin", "{LOCALAPPDATA}/Programs/Git/bin")
# What scripts/check.sh does to find its Python, then uv. Prints "<name> <major> <minor>" and uv's version line.
CHECK_SCRIPT_TOOLS = ("for p in python3 python py; do "
                      "if \"$p\" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then "
                      "\"$p\" -c 'import sys; print(sys.argv[1], sys.version_info[0], sys.version_info[1])' \"$p\"; "
                      "uv --version; exit; fi; done; exit 1")
# The one fix for every check that could not read the local settings file.
SETTINGS_FIX = ("Copy kpi_store/stores.example.toml to a folder outside the release folder, fill it in, and pass "
                "its path with --stores or set KPI_STORE_LOCAL to it")


class Context:
    """What the checks read: the local settings (or why they could not be read) and the machine. Tests replace
    run, which and connect."""

    def __init__(self, stores=None, environ=None, run=subprocess.run, which=shutil.which, connect=None,
                 release_root=ls.ROOT, version=None, installed=importlib.metadata.version):
        self.environ = os.environ if environ is None else environ
        self.run, self.which, self.release_root = run, which, Path(release_root)
        self.version = version or sys.version_info[:3]
        self.installed = installed
        self.connect = connect
        # Settings that cannot be read do not stop the command: the checks that need none still run, and each
        # check that needs them fails with the settings' own fix (needs_settings).
        self.local, self.local_error = None, None
        try:
            self.local = ls.load(ls.locate(stores, self.environ), self.environ, self.release_root)
        except ls.LocalSettingsError as err:
            self.local_error = str(err)

    def call(self, cmd, timeout=120):
        """(exit code, output) of a command run with no shell. A command that cannot start gives (None, "")."""
        try:
            done = self.run([str(c) for c in cmd], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return None, ""
        return done.returncode, (done.stdout or "") + (done.stderr or "")


def passed(detail):
    """A check's result when it passed: what it found, and no fix."""
    return True, detail, ""


def failed(detail, fix):
    """A check's result when it failed: what it found, and the one line that fixes it."""
    return False, detail, fix


def needs_settings(check):
    """A check that reads the local settings: without them it fails with the settings' own fix."""
    def wrapped(ctx):
        if ctx.local is None:
            return failed(f"needs the local settings file: {ctx.local_error}", SETTINGS_FIX)
        try:
            return check(ctx)
        except ls.LocalSettingsError as err:
            return failed(str(err), "Add the missing table to the local settings file; kpi_store/stores.example.toml shows it")
    wrapped.__name__ = check.__name__
    return wrapped


# ---- the tools --------------------------------------------------------------------------------------
# The runner calls these two as well, so a tool the setup check found is the one the runner uses.

def find_bash(setting=None, environ=None, which=shutil.which, windows=None):
    """bash for scripts/check.sh. On Windows: the settings' own, else bash.exe beside Git, else Git's usual
    folders. Elsewhere: the one on PATH. None when there is none."""
    environ = os.environ if environ is None else environ
    windows = os.name == "nt" if windows is None else windows
    if setting:
        return Path(setting) if Path(setting).is_file() else None
    if not windows:
        found = which("bash")
        return Path(found) if found else None
    candidates = []
    git = which("git")
    if git:   # <Git>/cmd/git.exe or <Git>/bin/git.exe; bash.exe is in <Git>/bin
        candidates.append(Path(git).parent.parent / "bin" / "bash.exe")
    for folder in GIT_BASH_FOLDERS:
        try:
            candidates.append(Path(folder.format(**environ)) / "bash.exe")
        except KeyError:
            continue
    found = which("bash")
    if found and "system32" not in found.lower():   # the one in System32 starts the Linux subsystem (above)
        candidates.append(Path(found))
    return next((c for c in candidates if c.is_file()), None)


def find_databricks(local=None, which=shutil.which):
    """The Databricks CLI: the settings' own, else the one on PATH (databricks.exe on Windows). None when missing."""
    if local is not None and local.databricks is not None and local.databricks.cli:
        return local.databricks.cli if local.databricks.cli.is_file() else None
    found = which("databricks")
    return Path(found) if found else None


# ---- the checks -------------------------------------------------------------------------------------
# In the order they run. A later check may tell the person to fix an earlier one first.

def python(ctx):
    """The Python that runs this command must be 3.11 or later."""
    found = ".".join(str(p) for p in ctx.version)
    if tuple(ctx.version[:2]) < PYTHON_MINIMUM:
        return failed(f"Python {found}", "Install Python 3.11 or later from https://www.python.org/downloads/ and run "
                                        "the commands with the py launcher")
    return passed(f"Python {found}")


def packages(ctx):
    """Every package in PACKAGES is installed at exactly its pinned version. The fix is one pip command that
    names only the packages that are missing or differ."""
    wrong = []
    for name, version in PACKAGES.items():
        try:
            have = ctx.installed(name)
        except importlib.metadata.PackageNotFoundError:
            have = None
        if have != version:
            wrong.append((name, version, have))
    if wrong:
        said = ", ".join(f"{n} {have or 'missing'} (need {v})" for n, v, have in wrong)
        return failed(said, "py -m pip install " + " ".join(f"{n}=={v}" for n, v, _ in wrong))
    return passed(", ".join(f"{n} {v}" for n, v in PACKAGES.items()))


def local_settings(ctx):
    """The local settings file was found, is valid, and lies outside the release folder (kpi_store.local_settings)."""
    if ctx.local is None:
        return failed(ctx.local_error, SETTINGS_FIX)
    return passed(f"{ctx.local.path}, outside the release folder")


@needs_settings
def kpi_store_settings(ctx):
    """The kpi_store.toml that the local settings name is valid, and names a SQL warehouse."""
    path = ctx.local.need("settings")
    try:
        found = settings_module.load(path)
    except settings_module.SettingsError as err:
        return failed(str(err), f"Copy kpi_store/kpi_store.example.toml to {path} and fill it in")
    if not found.warehouse_id:   # the notebook needs none, but the sync check reads the triple table through one
        return failed(f"{path} names no SQL warehouse, so the sync check cannot read Databricks",
                      f"In {path} set [databricks] warehouse_id to the ID of a SQL warehouse you may use")
    return passed(f"{path}: writes to {found.store_schema}, volume {found.volume}, SQL warehouse {found.warehouse_id}")


@needs_settings
def java(ctx):
    """A Java that Fuseki can run on is found: the one the settings name, or the one load_fuseki.find_java finds."""
    fuseki = ctx.local.fuseki
    found = load_fuseki.find_java(fuseki.java if fuseki else None, ctx.environ, ctx.which)
    fix = "Install a Java 21 runtime, such as Eclipse Temurin 21, open a new terminal, and if java is still not found name java.exe in [fuseki] java"
    if found is None:
        return failed("Java was not found", fix)
    major = load_fuseki.java_major(found, ctx.run)
    if major is None or major < load_fuseki.JAVA_MINIMUM:
        return failed(f"{found} is Java {major or 'of an unknown version'}; Fuseki 6.2.0 needs {load_fuseki.JAVA_MINIMUM} or later", fix)
    return passed(f"Java {major} at {found}")


def _jar(path, want, name, url):
    """Checks that a jar is there and has the pinned SHA-256. The fix names the public download and where to save it."""
    if not path.is_file():
        return failed(f"{path} is missing", f"Download {name} from {url} and save it as {path}")
    found = load_fuseki.file_sha256(path)
    if found != want:
        return failed(f"{path} has SHA-256 {found}, not {want}", f"Download {name} again from {url} and save it as {path}")
    return passed(f"{path} has the pinned SHA-256")


@needs_settings
def fuseki_jar(ctx):
    """The Fuseki server jar the local settings name is the pinned jena-fuseki-server-6.2.0.jar."""
    return _jar(ctx.local.need("fuseki").jar, load_fuseki.FUSEKI_SHA256, "jena-fuseki-server-6.2.0.jar",
                "https://repo1.maven.org/maven2/org/apache/jena/jena-fuseki-server/6.2.0/")


@needs_settings
def robot_jar(ctx):
    """The ROBOT jar the local settings name is the pinned 1.9.10. The Neo4j load's projection runs it."""
    return _jar(ctx.local.need("robot_jar"), ROBOT_SHA256, "robot.jar (ROBOT 1.9.10)",
                "https://github.com/ontodev/robot/releases/download/v1.9.10/robot.jar")


def bash(ctx):
    """A bash is found for scripts/check.sh, which the runner's check step runs (find_bash)."""
    found = find_bash(ctx.local.bash if ctx.local else None, ctx.environ, ctx.which)
    if found is None:
        return failed("bash was not found; scripts/check.sh is a bash script",
                      "Install Git for Windows from https://git-scm.com/download/win (it brings bash.exe), or name bash.exe in [tools] bash")
    return passed(str(found))


def uv(ctx):
    """scripts/check.sh runs every check through uv, which fetches the test dependencies."""
    found = ctx.which("uv")
    if not found:
        return failed("uv was not found; scripts/check.sh runs its checks through uv", "py -m pip install uv")
    return passed(str(found))


def check_script_tools(ctx):
    """scripts/check.sh calls Python and uv from inside bash, so both must be found there. It takes the first of
    python3, python and py that runs and is 3.11 or later; this check does the same. Windows often has no
    python3.exe, or one that only opens the Store, so a name counts only when it runs."""
    found = find_bash(ctx.local.bash if ctx.local else None, ctx.environ, ctx.which)
    if found is None:
        return failed("bash was not found, so the check script cannot run", "Fix the bash check first")
    code, out = ctx.call([found, "-c", CHECK_SCRIPT_TOOLS])
    words = out.split()
    if code != 0 or len(words) < 5:
        return failed("inside bash, Python 3.11 or later (python3, python or py) or uv was not found; scripts/check.sh calls both",
                      "Run py -m pip install uv, then add the folder of python.exe and the folder of uv.exe to PATH and open a new terminal")
    return passed(f"inside bash: {words[0]} {words[1]}.{words[2]} and {words[3]} {words[4]}")


def databricks_cli(ctx):
    """The Databricks CLI is found and starts. The runner's volume, upload, notebook and report steps go through
    it. The sync check reads Databricks through the SDK instead, with the same profile."""
    found = find_databricks(ctx.local, ctx.which)
    fix = ("Install the Databricks CLI as its documentation says (\"Install or update the Databricks CLI\", "
           "https://docs.databricks.com/aws/en/dev-tools/cli/install), open a new terminal, and if it is still not "
           "found name databricks.exe in [databricks] cli")
    if found is None:
        return failed("the Databricks CLI was not found", fix)
    code, out = ctx.call([found, "--version"])
    if code != 0:
        return failed(f"{found} did not run", fix)
    return passed(f"{out.strip().splitlines()[0] if out.strip() else 'Databricks CLI'} at {found}")


@needs_settings
def databricks_auth(ctx):
    """The CLI profile the local settings name is signed in: the CLI can say who the current user is. The check
    stores nothing; the sign-in itself is the CLI's own (OAuth)."""
    profile = ctx.local.need("databricks").profile
    found = find_databricks(ctx.local, ctx.which)
    if found is None:
        return failed("the Databricks CLI was not found, so the sign-in cannot be checked", "Fix the databricks-cli check first")
    code, _ = ctx.call([found, "current-user", "me", "--profile", profile, "--output", "json"])
    if code != 0:
        return failed(f"the profile {profile} is not signed in",
                      f"databricks auth login --host <your workspace> --profile {profile}")
    return passed(f"signed in through the profile {profile}")


def _connect(ctx, neo4j):
    """A Neo4j driver for one server of the local settings. The tests pass their own through Context.connect."""
    if ctx.connect is not None:
        return ctx.connect(neo4j)
    from . import load_neo4j
    return load_neo4j.connect(neo4j)


@needs_settings
def neo4j_local(ctx):
    """The local Neo4j answers, and it, n10s and APOC are at the pinned versions. Two read-only queries."""
    neo4j = ctx.local.need("neo4j_local")
    try:
        with _connect(ctx, neo4j) as driver, driver.session(database=neo4j.database) as session:
            kernel = session.run("CALL dbms.components() YIELD name, versions WHERE name = 'Neo4j Kernel' "
                                 "RETURN versions[0] AS v").single()["v"]
            try:
                found = session.run("RETURN n10s.version() AS n10s, apoc.version() AS apoc").single()
                n10s, apoc = found["n10s"], found["apoc"]
            except Exception:
                return failed(f"Neo4j {kernel} answers, but n10s or APOC does not",
                              f"In Neo4j Desktop install the plugins n10s {N10S_VERSION} and APOC {APOC_VERSION} for this DBMS, allow them "
                              "(dbms.security.procedures.unrestricted=n10s.*,apoc.*), and restart the DBMS")
    except Exception as err:
        return failed(f"the local Neo4j did not answer ({type(err).__name__})",
                      "Start the DBMS in Neo4j Desktop, and check the address, user, password and database in [neo4j.local]")
    if (kernel, n10s, apoc) != (NEO4J_VERSION, N10S_VERSION, APOC_VERSION):
        return failed(f"Neo4j {kernel}, n10s {n10s}, APOC {apoc}",
                      f"Use a Neo4j {NEO4J_VERSION} DBMS with the plugins n10s {N10S_VERSION} and APOC {APOC_VERSION}")
    return passed(f"Neo4j {kernel}, n10s {n10s}, APOC {apoc}, database {neo4j.database}")


@needs_settings
def neo4j_plugins(ctx):
    """The two plugin jars in [neo4j.local] plugins_folder have the pinned checksums, by the ontology-to-lpg
    skill's check_plugins. The folder is optional: without it the check passes and says the jars were not checked."""
    folder = ctx.local.need("neo4j_local").plugins_folder
    if folder is None:
        return passed("skipped: [neo4j.local] plugins_folder is not set, so the jars are not checked by checksum")
    from . import load_neo4j
    # check_plugins is a script of the skill, in a folder that is no package, so its folder goes on the import path.
    scripts = ctx.release_root / load_neo4j.SKILL_SCRIPTS
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import check_plugins
    try:
        _, missing = check_plugins.check(check_plugins.checksums(folder))
    except OSError as err:
        return failed(f"{folder} could not be read ({type(err).__name__})", "Correct [neo4j.local] plugins_folder")
    if missing:
        return failed(f"{folder} lacks {', '.join(plugin for plugin, _, _ in missing)}",
                      f"Put {' and '.join(name for _, name, _ in missing)} in {folder} and restart the DBMS")
    return passed(f"{folder} holds both pinned plugin jars")


@needs_settings
def neo4j_enterprise(ctx):
    """The Enterprise server answers and has the database the settings name. The check opens it the way the copy
    does (copy_enterprise.open_target), so a database that the copy could not open fails here first. The copy's
    other refusals, such as nodes that are not the KPI Store's, are not tested here. The check only counts nodes."""
    from . import copy_enterprise
    neo4j = ctx.local.need("neo4j_enterprise")
    try:
        with _connect(ctx, neo4j) as driver, copy_enterprise.open_target(driver, neo4j.database) as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
    except copy_enterprise.Refused as err:
        return failed(str(err), f"Ask the server's administrator for the database {neo4j.database}, or correct [neo4j.enterprise] database")
    except Exception as err:
        return failed(f"the Enterprise server did not answer ({type(err).__name__})",
                      "Check the address, user and password in [neo4j.enterprise], and that this machine reaches the server")
    return passed(f"database {neo4j.database} is there and holds {nodes} node(s)")


# The checks by the names --only and --list use, in the order they run.
CHECKS = {"python": python, "packages": packages, "local-settings": local_settings,
          "kpi-store-settings": kpi_store_settings, "java": java, "fuseki-jar": fuseki_jar, "robot-jar": robot_jar,
          "bash": bash, "uv": uv, "check-script-tools": check_script_tools, "databricks-cli": databricks_cli,
          "databricks-auth": databricks_auth, "neo4j-local": neo4j_local, "neo4j-plugins": neo4j_plugins,
          "neo4j-enterprise": neo4j_enterprise}


def run_checks(ctx, names=None):
    """[(name, passed, detail, fix)] for the named checks, in CHECKS' order."""
    return [(name, *check(ctx)) for name, check in CHECKS.items() if names is None or name in names]


def main(argv=None, context=Context):
    """Runs the checks and prints one line per check, a fix under each failure, and the count. Returns the exit code."""
    ap = argparse.ArgumentParser(prog="kpi_store.setup_check", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--only", action="append", choices=tuple(CHECKS), help="run only this check; may be repeated")
    ap.add_argument("--list", action="store_true", help="print the checks' names and stop")
    args = ap.parse_args(argv)
    if args.list:
        print("\n".join(CHECKS))
        return 0
    results = run_checks(context(args.stores, release_root=Path(args.release)), args.only)
    for name, ok, detail, fix in results:
        print(f"{'ok  ' if ok else 'FAIL'} {name:<19} {detail}")
        if not ok:
            print(f"     fix: {fix}")
    bad = sum(1 for _, ok, _, _ in results if not ok)
    print(f"{len(results) - bad} of {len(results)} checks passed" + ("" if not bad else f"; fix the {bad} above and run this again"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
