"""Loads the release into a local Jena Fuseki and proves by a hash that the store holds exactly the release.

    py -m kpi_store.load_fuseki --stores <local settings file>            # start or reuse Fuseki, load, check
    py -m kpi_store.load_fuseki --stores <local settings file> --stop     # stop the Fuseki this command started

What it does, in order:
1. Checks Java (version 21 or later, which Fuseki 6.2.0's own manifest names) and the Fuseki jar's SHA-256.
2. Uses the Fuseki that answers at the dataset URL of the local settings. When none answers and the URL is on this
   machine, it starts one from the jar and waits for it. With [fuseki] data_folder the dataset is a TDB2 folder
   and survives a restart; without it the dataset is in memory and a restart empties it.
3. Builds the dataset a current store holds: for each newest release its content, its shapes and its catalog,
   and each package graph, which includes the logical models. --extra-graphs adds graphs from outside the
   release, such as the technical graph's.
4. Compares the store's RDFC-1.0 hash with the dataset's. When they are equal it writes nothing. Otherwise it
   drops the graphs of earlier versions of the release's modules, replaces every graph of the dataset in one
   request, reads everything back and compares the hashes again (the rdf-store skill's round trip).

A graph that is neither part of the dataset nor an earlier version of one of its modules is not the KPI Store's.
The load then stops and names it; --drop-unknown drops it.

Needs rdflib and pyoxigraph. Exit 0 when the hashes are equal, 1 when the load or a check fails, 2 on bad settings.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import load_databricks as ldb
from . import local_settings as ls

FUSEKI_SHA256 = "2c92c598e65ab69d99820052e05f4277ed1d77980a8845f87545ad35b71a76ee"   # jena-fuseki-server-6.2.0.jar
JAVA_MINIMUM = 21   # the jar's manifest says Java-Version: 21
JAVA_VERSION = re.compile(r'version "(\d+)(?:\.(\d+))?')
START_WAIT_SECONDS = 90
PID_FILE, LOG_FILE = "fuseki.pid", "fuseki.log"


class FusekiError(Exception):
    """The load cannot go on. The message says why and what to do."""


# ---- Java and the jar ----------------------------------------------------------------------------

def find_java(setting=None, environ=None, which=shutil.which):
    """The java executable: the settings' own, else JAVA_HOME's, else the one on PATH. None when there is none."""
    environ = os.environ if environ is None else environ
    if setting:
        return Path(setting) if Path(setting).is_file() else None
    exe = "java.exe" if os.name == "nt" else "java"
    if environ.get("JAVA_HOME") and (Path(environ["JAVA_HOME"]) / "bin" / exe).is_file():
        return Path(environ["JAVA_HOME"]) / "bin" / exe
    found = which("java")
    return Path(found) if found else None


def java_major(java, run=subprocess.run):
    """The major version `java -version` reports (8 for 1.8), or None when it cannot be read."""
    try:
        done = run([str(java), "-version"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    match = JAVA_VERSION.search((done.stderr or "") + (done.stdout or ""))
    if not match:
        return None
    first, second = int(match.group(1)), match.group(2)
    return int(second) if first == 1 and second else first


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for piece in iter(lambda: f.read(1 << 20), b""):
            digest.update(piece)
    return digest.hexdigest()


def check_java(fuseki, environ=None, which=shutil.which, run=subprocess.run):
    """The java executable, after checking its version. Raises FusekiError otherwise."""
    java = find_java(fuseki.java, environ, which)
    if java is None:
        raise FusekiError("Java was not found. Install Java 21 or later, or name it in [fuseki] java")
    major = java_major(java, run)
    if major is None or major < JAVA_MINIMUM:
        raise FusekiError(f"Java at {java} is version {major or 'unknown'}; Fuseki 6.2.0 needs {JAVA_MINIMUM} or later")
    return java


def check_jar(jar):
    """Raises FusekiError unless the jar is the pinned jena-fuseki-server-6.2.0.jar."""
    if not Path(jar).is_file():
        raise FusekiError(f"the Fuseki jar {jar} is missing; download jena-fuseki-server-6.2.0.jar and name it in [fuseki] jar")
    found = file_sha256(jar)
    if found != FUSEKI_SHA256:
        raise FusekiError(f"the Fuseki jar's SHA-256 is {found}, not the pinned {FUSEKI_SHA256}; download it again")


# ---- the server -----------------------------------------------------------------------------------

def answers(fuseki, opener=urllib.request.urlopen):
    """True when the dataset answers a query at the URL the settings name."""
    url = fuseki.query_url + "?" + urllib.parse.urlencode({"query": "ASK {}"})
    try:
        with opener(urllib.request.Request(url, headers={"Accept": "application/sparql-results+json"}), timeout=5) as r:
            return r.status == 200
    except (OSError, urllib.error.URLError):
        return False


def start_command(java, fuseki):
    """The command that starts Fuseki, as an argument list. --localhost accepts requests from this machine only."""
    store = ["--tdb2", "--loc", str(fuseki.data_folder)] if fuseki.data_folder else ["--mem"]
    return [str(java), "-jar", str(fuseki.jar), *store, "--update", "--localhost", "--port", str(fuseki.port),
            fuseki.dataset]


def start(java, fuseki, state_folder, popen=subprocess.Popen, answers=answers, sleep=time.sleep,
          wait_seconds=START_WAIT_SECONDS):
    """Starts Fuseki apart from this process, so it keeps running when the command ends, and waits until the
    dataset answers. Its output goes to fuseki.log and its process ID to fuseki.pid, both in state_folder.
    Returns the process ID."""
    if not fuseki.is_local:
        raise FusekiError("no Fuseki answers at the URL in [fuseki] url, and the URL is not on this machine, "
                          "so this command cannot start one")
    state_folder = Path(state_folder)
    state_folder.mkdir(parents=True, exist_ok=True)
    if fuseki.data_folder:
        fuseki.data_folder.mkdir(parents=True, exist_ok=True)
    # A new process group on Windows, a new session elsewhere: the server must not end with this command.
    apart = ({"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)}
             if os.name == "nt" else {"start_new_session": True})
    with (state_folder / LOG_FILE).open("ab") as log:
        process = popen(start_command(java, fuseki), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        cwd=str(state_folder), **apart)
    (state_folder / PID_FILE).write_text(f"{process.pid}\n", encoding="utf-8", newline="\n")
    waited = 0
    while not answers(fuseki):
        if process.poll() is not None:
            raise FusekiError(f"Fuseki stopped as it started (exit {process.returncode}); read {state_folder / LOG_FILE}")
        if waited >= wait_seconds:
            raise FusekiError(f"Fuseki did not answer within {wait_seconds} seconds; read {state_folder / LOG_FILE}")
        sleep(1)
        waited += 1
    return process.pid


def stop(state_folder, kill=os.kill):
    """Stops the Fuseki that start() started, by the process ID it wrote. Returns the ID, or None when there is none."""
    pid_file = Path(state_folder) / PID_FILE
    if not pid_file.is_file():
        return None
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    try:
        kill(pid, signal.SIGTERM)
    except OSError:
        pass   # it had already stopped
    pid_file.unlink()
    return pid


def ensure_running(fuseki, state_folder, environ=None, **start_options):
    """("reused" or "started", process ID or None). Java and the jar are checked only when a start is needed: a
    Fuseki that already answers needs neither on this machine."""
    if answers(fuseki):
        return "reused", None
    java = check_java(fuseki, environ)
    check_jar(fuseki.jar)
    return "started", start(java, fuseki, state_folder, **start_options)


# ---- the dataset ---------------------------------------------------------------------------------

def read_extra_graphs(path):
    """{graph IRI: file} from a JSON file that maps each graph IRI to a Turtle or N-Triples file. A relative file
    path starts at the JSON file's folder. This is how graphs from outside the release, such as the technical
    graph's, join the load."""
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise FusekiError(f"cannot read the extra graphs file {path}: {type(err).__name__}") from None
    if not isinstance(doc, dict) or not all(isinstance(k, str) and ":" in k and isinstance(v, str) for k, v in doc.items()):
        raise FusekiError("the extra graphs file must map each graph IRI to a file")
    graphs = {iri: (Path(name) if Path(name).is_absolute() else path.parent / name) for iri, name in doc.items()}
    missing = sorted(str(p) for p in graphs.values() if not p.is_file())
    if missing:
        raise FusekiError(f"the extra graphs file names {missing[0]}, which is missing")
    return graphs


def store_graphs(release_root, ss, extra_graphs=None):
    """{graph IRI: file} of everything the store should hold: the release's graphs (load_databricks.release_graphs)
    and the extra graphs. An extra graph may not take a release graph's name."""
    graphs = dict(ldb.release_graphs(release_root, ss))
    for iri, path in (extra_graphs or {}).items():
        if iri in graphs:
            raise FusekiError(f"the extra graph {iri} has the name of a release graph")
        graphs[iri] = Path(path)
    return graphs


def pack(rdfstore, graphs):
    """One dataset with each file under its graph IRI."""
    named = {os.path.realpath(path): iri for iri, path in graphs.items()}   # rdfstore.pack keys its names this way
    return rdfstore.pack([str(p) for p in graphs.values()], named)


def module_bases(ss):
    """The IRI every version of each module in the catalog starts with: <module IRI>/. A graph under one of them
    that the dataset does not hold is an earlier version of that module, or one of its release graphs."""
    return sorted({iri.rsplit("/", 1)[0] + "/" for iri in ss.catalog_datasets(ss.repo_file(ss.CATALOG))})


# ---- the load ------------------------------------------------------------------------------------

def _update(store, statement):
    store._request(store.update_url, "POST", statement.encode("utf-8"), {"Content-Type": "application/sparql-update"})


def default_graph_triples(store):
    body = urllib.parse.urlencode({"query": "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"}).encode()
    _, data = store._request(store.query_url, "POST", body, {"Content-Type": "application/x-www-form-urlencoded",
                                                             "Accept": "application/sparql-results+json"})
    return int(json.loads(data)["results"]["bindings"][0]["n"]["value"])


def load(store, dataset, rdfstore, bases, drop_unknown=False):
    """Makes the store hold exactly the dataset. Returns a dict whose "status" is one of:

    current    the store's hash already equals the dataset's; nothing was written
    loaded     the graphs were replaced, read back, and the hashes are equal
    mismatch   the hashes differ after the load (see "comparison")

    Raises FusekiError, before any write, when the store holds a graph that is not the KPI Store's (see the
    module's text) and drop_unknown is false."""
    want_hash = rdfstore.dataset_hash(dataset)
    wanted = set(rdfstore.named_graphs(dataset))
    held = set(store.graphs())
    in_default = default_graph_triples(store)
    result = {"dataset_hash": want_hash, "graphs": len(wanted), "triples": len(dataset)}
    if held == wanted and not in_default and rdfstore.dataset_hash(store.export()) == want_hash:
        return {**result, "status": "current", "store_hash": want_hash, "dropped": []}
    stale = sorted(held - wanted)
    earlier = [g for g in stale if g.startswith(tuple(bases))]
    unknown = [g for g in stale if g not in earlier] + (["(the default graph)"] if in_default else [])
    if unknown and not drop_unknown:
        raise FusekiError(f"the dataset holds {len(unknown)} graph(s) that are not the KPI Store's, e.g. {unknown[:3]}. "
                          "Nothing was written. Name a dataset of the KPI Store's own, or pass --drop-unknown to drop them")
    drops = [f"DROP SILENT GRAPH <{g}>" for g in stale if g in earlier or drop_unknown]
    if in_default and drop_unknown:
        drops.append("DROP SILENT DEFAULT")
    if drops:
        _update(store, " ;\n".join(drops))
    passed, comparison = rdfstore.roundtrip(store, dataset)
    result |= {"store_hash": comparison["actual_hash"], "dropped": stale if drop_unknown else earlier}
    if not passed:
        return {**result, "status": "mismatch", "comparison": {k: comparison[k] for k in ("expected_quads", "actual_quads", "diff") if k in comparison}}
    return {**result, "status": "loaded"}


def run(local, release_root, state_folder=None, extra_graphs=None, drop_unknown=False, start_server=True, environ=None):
    """The whole step: the server, the dataset, the load. Returns load()'s dict with "server" and "url" added."""
    fuseki = local.need("fuseki")
    state_folder = Path(state_folder) if state_folder else local.need("run_folder") / "fuseki"
    if start_server:
        server, pid = ensure_running(fuseki, state_folder, environ)
    elif answers(fuseki):
        server, pid = "reused", None
    else:
        raise FusekiError("no Fuseki answers at the URL in [fuseki] url")
    rdfstore, ss = ldb.import_rdfstore(release_root), ldb.import_sync_stores(release_root)
    dataset = pack(rdfstore, store_graphs(release_root, ss, extra_graphs))
    store = rdfstore.FusekiStore(fuseki.data_url, fuseki.query_url, fuseki.update_url)
    result = load(store, dataset, rdfstore, module_bases(ss), drop_unknown)
    return {**result, "server": server, "pid": pid, "url": fuseki.url,
            "persistent": bool(fuseki.data_folder), "extra_graphs": sorted(extra_graphs or {})}


def line(result):
    """The one line a person reads."""
    kept = "kept on disk" if result["persistent"] else "in memory: a restart empties it"
    head = f"fuseki: {result['status']}, {result['graphs']} graphs, {result['triples']} triples"
    if result["status"] == "mismatch":
        return f"{head}; the store's hash {result['store_hash']} is not the release's {result['dataset_hash']}"
    return f"{head}, RDFC-1.0 hash {result['dataset_hash']} equal in the store and the release files ({result['server']} server, {kept})"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kpi_store.load_fuseki", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--extra-graphs", help="a JSON file that maps graph IRIs to files outside the release")
    ap.add_argument("--drop-unknown", action="store_true", help="drop graphs that are not the KPI Store's")
    ap.add_argument("--no-start", action="store_true", help="do not start Fuseki; fail when none answers")
    ap.add_argument("--stop", action="store_true", help="stop the Fuseki this command started, and do nothing else")
    ap.add_argument("--json", action="store_true", help="print the result as JSON instead of one line")
    args = ap.parse_args(argv)
    try:
        local = ls.load(ls.locate(args.stores))
        if args.stop:
            pid = stop(local.need("run_folder") / "fuseki")
            print(f"fuseki: stopped process {pid}" if pid else "fuseki: this command started no Fuseki that still runs")
            return 0
        extra = read_extra_graphs(args.extra_graphs) if args.extra_graphs else None
        result = run(local, Path(args.release), extra_graphs=extra, drop_unknown=args.drop_unknown,
                     start_server=not args.no_start)
    except ls.LocalSettingsError as err:
        print(f"fuseki: {err}", file=sys.stderr)
        return 2
    except (FusekiError, ldb.ov.ReleaseError) as err:
        print(f"fuseki: FAILED. {err}", file=sys.stderr)
        return 1
    except (OSError, urllib.error.URLError) as err:
        print(f"fuseki: FAILED. The store did not answer ({type(err).__name__})", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2) if args.json else line(result))
    return 0 if result["status"] in ("current", "loaded") else 1


if __name__ == "__main__":
    sys.exit(main())
