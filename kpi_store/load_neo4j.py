"""Loads the release into the local Neo4j, which has the n10s and APOC plugins, and runs every check there.

    py -m kpi_store.load_neo4j --stores <local settings file> [--force]

Where it sits in the run: this is the runner's neo4j step (kpi_store.runner). It runs after the Fuseki load and
before the copy to Neo4j Enterprise (kpi_store.copy_enterprise), which takes only the graph this load verified.

It reads the release folder and the local settings. It writes to the one database [neo4j.local] names, to the
projection's output folder ([projection] out: the load report and the files the copy reads), and to
<run folder>/neo4j/ (the log and the two configuration copies). It never writes into the release folder and
never touches the Enterprise server.

The local Neo4j is Neo4j Desktop on the machine that runs the loads. THE LOAD EMPTIES THE DATABASE that
[neo4j.local] names, then builds the graph again from the release files. The steps and their checks are the
ontology-to-lpg skill's (skills/ontology-to-lpg/scripts/run_projection.py), run from this release's own run
configuration with this Python and no other tool:

  project         check the rules, validate with SHACL, reason with ROBOT, write the files the load reads
  load            send the triples in the request, validate in the graph (SHACL), one fail case per compiled
                  constraint, a deliberate mutant, the round trip, and two loads whose graph hashes must be equal
  review, tags    the model review, and each node and relationship tagged with the release it came from
  release-record  one ModuleRelease node per module

Then this module loads the logical models as their own subgraph and writes the store's marker, a node labelled
EpmStoreMarker. The marker is written only when the graph's counts equal the report's and the graph holds one
release record for each newest release.

A second run on the same release finds the marker, the report and an equal graph hash, and changes nothing.
--force loads again.

What is loaded is each module's newest release in this folder, read from the catalog, with the package versions of
the projection configuration set to match. So a correction version made by the cut is the one that is loaded.

Three of the skill's scripts (model_review.py, module_tags.py, release_record.py) take the Neo4j user and database
from a login file only. This module therefore writes that file into the run folder, outside the release, readable
by this user only, for the length of the load. It is removed on every way out, a failed start and Ctrl+C included.
No password is printed or logged.

Needs rdflib, pyshacl, pyoxigraph and neo4j, Java, and ROBOT 1.9.10 at the path [projection] robot_jar names.
Exit 0 when the load is current or passed, 1 when a step or check failed, 2 on bad settings.
"""
import argparse
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from . import load_databricks as ldb
from . import load_fuseki
from . import local_settings as ls
from . import ontology_view as ov

STORE = "neo4j"   # the name the local database's marker carries
# The skill's steps this load runs, in this order: each reads what the one before it wrote.
STEPS = ("project", "load", "review", "tags", "release-record")
SKILL_SCRIPTS = Path("skills") / "ontology-to-lpg" / "scripts"
PROJECTION = Path("business_architecture") / "ontology" / "projection"
RUN_CONFIG = PROJECTION / "skill-run" / "epm-run.json"
# Files the skill's steps write into the projection's output folder. The copy to Enterprise reads them too.
REPORT, RECORDS, RUN_MANIFEST, INFERRED = "projection-report.json", "release-records.json", "run-manifest.json", "inferred.nt"
# Files this module writes into <run folder>/neo4j: the login file (removed after the load), the log, and the run
# configuration with the newest releases as its inputs.
ENV_FILE, LOG_FILE, CONFIG_FILE = "neo4j-local.env", "neo4j-load.log", "projection-run.json"
PROJECTION_CONFIG_FILE = "projection-config.json"   # the projection configuration's copy, also in the run folder
MARKER_HASH = "graph_hash"   # this load's own marker field: the verified graph's hash


class LoadError(Exception):
    """A step or a check failed. The message says which."""


# ---- the release's own code ------------------------------------------------------------------------

_CODE = {}   # {release folder: its imported modules}; it holds one entry at most (release_code)


def release_code(release_root):
    """The release's modules this load calls, imported from the release folder: the ontology-to-lpg skill's
    scripts and the projection folder's sync_stores and logical_models. Those folders are not packages, and their
    files import each other by plain name, so both folders go on the import path."""
    root = Path(release_root).resolve()
    if root in _CODE:
        return _CODE[root]
    # The modules are imported by plain name, so Python keeps one copy of each. A second folder would get the
    # first folder's code under its own name, and load that folder's rules. Refuse instead.
    if _CODE:
        raise LoadError("one process loads one release folder; start a new one for another folder")
    for folder in (root / SKILL_SCRIPTS, root / PROJECTION):
        if not folder.is_dir():
            raise LoadError(f"the release lacks {folder}")
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    import build
    import copy_graph
    import load_verify
    import logical_models
    import module_tags
    import pipeline
    import release_record
    import run_projection
    import sync_stores
    _CODE[root] = SimpleNamespace(rp=run_projection, cg=copy_graph, lv=load_verify, rr=release_record, mt=module_tags,
                                  build=build, ss=sync_stores, lm=logical_models, pipeline=pipeline)
    return _CODE[root]


def connect(neo4j):
    """A driver for one of the two Neo4j servers of the local settings."""
    from neo4j import GraphDatabase
    # The server's notifications (a label that does not exist yet, for example) are not errors, and the driver
    # would print each with its query.
    return GraphDatabase.driver(neo4j.uri, auth=(neo4j.username, neo4j.password.reveal()), notifications_min_severity="OFF")


def release_label(release_root, ss):
    """What a marker names as its source: the release's name, with the commit when the folder is a Git checkout."""
    name = ov.release_name(release_root)
    return f"{name} at {ss.commit()}" if (Path(release_root) / ".git").exists() else name


# ---- the run configuration and the skill's steps ---------------------------------------------------

def run_config(release_root, local, env_file):
    """This release's run configuration with every path made absolute and the local store added."""
    source = Path(release_root).resolve() / RUN_CONFIG
    try:
        cfg = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise LoadError(f"cannot read the run configuration {source}: {type(err).__name__}") from None
    for key in ("projection_config", "inputs_script", "releases", "queries"):
        if key in cfg:
            cfg[key] = str((source.parent / cfg[key]).resolve())
    neo4j = local.need("neo4j_local")
    cfg |= {"out": str(local.need("projection_out")), "robot_jar": str(local.need("robot_jar")), "neo4j_env": str(env_file)}
    if neo4j.plugins_folder:
        cfg["plugins_dir"] = str(neo4j.plugins_folder)
    return cfg


def write_env_file(path, neo4j):
    """The login file the skill's scripts read. It is created for this user only (mode 600 where the system
    honours it), and a write that fails removes what it wrote."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)   # never write through a file someone else may have opened
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"NEO4J_URI={neo4j.uri}\nNEO4J_USERNAME={neo4j.username}\nNEO4J_PASSWORD={neo4j.password.reveal()}\n"
                    f"NEO4J_DATABASE={neo4j.database}\n")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


@contextlib.contextmanager
def login_file(path, neo4j):
    """The login file for the length of a with block. The clean-up scope opens before the file is created, so no
    way out of the block, an error or Ctrl+C included, leaves the file."""
    try:
        yield write_env_file(path, neo4j)
    finally:
        Path(path).unlink(missing_ok=True)


def newest_inputs(release_root, newest, code):
    """(data files, shape files, {module: version}) of the newest releases, as the projection reads them: each
    module's package file and its shapes, then the shape files outside the packages. The modules keep the order
    the projection's own list gives them; the versions come from `newest`, the catalog's newest version IRIs, so a
    version the list does not name yet, such as a correction, is the one that is read."""
    ontology = Path(release_root).resolve() / "business_architecture" / "ontology"
    versions = {iri.rsplit("/", 2)[-2]: iri.rsplit("/", 2)[-1] for iri in newest}
    listed = [module for module, _ in code.pipeline.PACKAGES]
    order = [m for m in listed if m in versions] + sorted(set(versions) - set(listed))
    folders = [ontology / "releases" / module / versions[module] for module in order]
    data = [folder / f"{module}.ttl" for module, folder in zip(order, folders)]
    shapes = [folder / "shapes.ttl" for folder in folders]
    shapes += [ontology / path for path in code.pipeline.SHAPES if not path.startswith("releases/")]
    missing = [str(p) for p in data + shapes if not p.is_file()]
    if missing:
        raise LoadError(f"the release lacks {missing[0]}")
    return [str(p) for p in data], [str(p) for p in shapes], {module: versions[module] for module in order}


def with_newest_inputs(cfg_doc, release_root, newest, code, run_dir):
    """The run configuration that reads the newest releases: its input list written out, and a copy of the
    projection configuration, in the run folder, whose package versions are those releases'."""
    data, shapes, versions = newest_inputs(release_root, newest, code)
    try:
        projection = json.loads(Path(cfg_doc["projection_config"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise LoadError(f"cannot read the projection configuration: {type(err).__name__}") from None
    projection["packages"] = versions
    copy = Path(run_dir) / PROJECTION_CONFIG_FILE
    copy.write_text(json.dumps(projection, indent=2) + "\n", encoding="utf-8", newline="\n")
    # inputs_script would make the driver ask the projection's own list for the inputs. The list written out
    # below replaces it, so the versions read are the catalog's newest.
    cfg = {k: v for k, v in cfg_doc.items() if k != "inputs_script"}
    return cfg | {"data": data, "shapes": shapes, "projection_config": str(copy)}


def plain_command(cmd, prefixes, java=None):
    """A command of the skill's driver, run with this Python instead of through uv, and with the Java the settings
    found. The driver writes each Python command as (uv run ... python, script, arguments)."""
    cmd = list(cmd)
    for prefix in prefixes:
        if cmd[:len(prefix)] == list(prefix):
            return [sys.executable] + cmd[len(prefix):]
    if cmd and cmd[0] == "java" and java:
        return [str(java)] + cmd[1:]
    return cmd


def step_runner(prefixes, log_path, java=None, run=subprocess.run):
    """The run(cmd, cwd, env, capture) function the skill's driver calls. Each command's output goes to the log file,
    so the load prints one line and the detail stays in the run folder."""
    def run_step(cmd, cwd=None, env=None, capture=False):
        # No .pyc files appear in the release folder, and each script reads and prints UTF-8, which is not the
        # default on Windows.
        env = dict(os.environ if env is None else env) | {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
        with Path(log_path).open("a", encoding="utf-8", newline="\n") as log:
            log.write("--- " + " ".join(str(c) for c in cmd[-6:]) + "\n")   # the command's end names the script
            log.flush()
            done = run(plain_command(cmd, prefixes, java), cwd=cwd, env=env, stdin=subprocess.DEVNULL, text=True,
                       encoding="utf-8", stdout=subprocess.PIPE if capture else log, stderr=log)
        return done.returncode, (done.stdout if capture else None)
    return run_step


# ---- the checks around the skill's steps -----------------------------------------------------------

def read_report(out, code, want=None):
    """The load's report from the output folder, or LoadError unless it earned its pass (build.report_earned). With
    want, the report must also be of this release: its input fingerprint equals the projection manifest's."""
    path = Path(out) / REPORT
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise LoadError(f"there is no load report at {path}; run the local Neo4j load first") from None
    fails = code.build.report_earned(report)
    if fails:
        raise LoadError(f"the load report at {path} did not pass {len(fails)} check(s), e.g. {fails[0]}")
    if want is not None and report.get("input_fingerprint") != want["input_fingerprint"]:
        raise LoadError(f"the load report at {path} is of other release files than this folder's (its input "
                        "fingerprint differs from the projection manifest's); run the local Neo4j load again")
    return report


def release_records(session):
    """The version IRIs of the release records the database holds, sorted."""
    return sorted(session.run("MATCH (r:ModuleRelease) RETURN r.version_iri AS iri").value())


def mark(session, store, want, report, ss, commit):
    """Writes the store's marker after two checks: the graph's counts equal the report's, and the graph holds one
    release record for each newest release. Returns the marker. Raises LoadError, writing nothing, otherwise."""
    nodes, edges = ss.resource_counts(session)
    if (nodes, edges) != (report["nodes"], report["relationships"]):
        raise LoadError(f"{store}: {nodes} nodes and {edges} relationships, not the report's {report['nodes']} and "
                        f"{report['relationships']}; no marker was written")
    records = release_records(session)
    if records != sorted(want["newest"]):
        raise LoadError(f"{store}: its {len(records)} release record(s) are not one for each of the "
                        f"{len(want['newest'])} newest releases; no marker was written")
    marker = ss.marker(want, store, [nodes, edges], commit_text=commit) | {MARKER_HASH: report["determinism_hash_sorted"]}
    # SET m = $p replaces every property, so nothing of an earlier marker stays on the node.
    session.run(f"MERGE (m:{ss.MARKER_LABEL} {{store: $s}}) SET m = $p", s=store, p=marker).consume()
    return marker


def models_status(session, store, newest, code):
    """(the release's logical-model files, the subgraph's status in this database). No files means the release
    holds no logical model, and the status is then "none"."""
    files = code.lm.models(newest)
    if not files:
        return files, "none"
    nodes, edges = code.lm.graph_rows(files)
    rows = code.lm.drift({store: code.lm.read_marker(session)}, code.lm.digest(files), code.lm.content(nodes, edges))
    return files, rows[0][1]


def load_models(session, store, newest, code, log):
    """Loads the logical models as their own subgraph unless it is current. Returns its status afterwards."""
    files, status = models_status(session, store, newest, code)
    if not files or status == "current":
        return status
    with contextlib.redirect_stdout(log):   # the loader prints its own lines; they belong in the log
        try:
            code.lm.load_neo4j(session, files, store)
        except SystemExit as stop:   # the loader's own refusal, with its reason
            raise LoadError(str(stop)) from None
    return models_status(session, store, newest, code)[1]


def is_current(session, store, want, report, code, sep):
    """True when the database already holds the verified graph of this release: its marker names this release and
    the report's hash, the graph hashes to it now, and it holds the release records."""
    marker, counts = code.ss.read_neo4j(session, store)
    if not marker or any(marker.get(k) != want[k] for k in code.ss.MARKER_FIELDS):
        return False
    if marker.get(MARKER_HASH) != report["determinism_hash_sorted"] or list(marker.get("count") or []) != counts:
        return False
    if release_records(session) != sorted(want["newest"]):
        return False
    # The graph hash reads every node and relationship, so it comes last, after the cheap comparisons passed.
    return code.lv.hash_graph(session, sep)[0] == report["determinism_hash_sorted"]


# ---- the load ------------------------------------------------------------------------------------

def load(local, release_root, run_dir=None, force=False, code=None, connect=connect, run=subprocess.run,
         extra_loads=()):
    """The whole step. Returns a dict whose "status" is "current" (nothing was changed) or "loaded". Raises
    LoadError when a step or a check fails.

    extra_loads are functions (session, store name) -> dict that load a subgraph of their own, apart from the
    ontology's Resource nodes, after the logical models and before the marker. They also run when the ontology is
    current, so each must leave a current subgraph alone. The technical graph joins here (tech_graph_loader)."""
    code = code or release_code(release_root)
    neo4j, out = local.need("neo4j_local"), local.need("projection_out")
    run_dir = Path(run_dir) if run_dir else local.need("run_folder") / "neo4j"
    run_dir.mkdir(parents=True, exist_ok=True)
    want = ldb.expected(release_root, code.ss)
    env_file = run_dir / ENV_FILE
    cfg_doc = run_config(release_root, local, env_file)
    sep = cfg_doc.get("separator", code.lv.N10S_SEP)
    result = {"store": STORE, "database": neo4j.database, "out": str(out), "log": str(run_dir / LOG_FILE)}

    # First, the way out that changes nothing: an earlier load's report is of this release and passed, and the
    # database still holds the graph that report verified.
    if not force and (out / REPORT).is_file():
        try:
            report = read_report(out, code, want)
            with connect(neo4j) as driver, driver.session(database=neo4j.database) as session:
                if is_current(session, STORE, want, report, code, sep) and \
                        models_status(session, STORE, want["newest"], code)[1] in ("current", "none"):
                    # The ontology is current. A subgraph beside it may still be behind, so its load runs; it
                    # leaves a current subgraph alone.
                    extras = [extra(session, STORE) for extra in extra_loads]
                    return {**result, "status": "current", **summary(report), "extra_loads": extras,
                            "marker": code.ss.read_neo4j(session, STORE)[0]}
        except LoadError:
            pass   # a report that did not pass is replaced by the load below

    # The load itself. From here the skill's load step empties the database and builds the graph again.
    java = load_fuseki.find_java((local.fuseki.java if local.fuseki else None))   # ROBOT runs on Java
    config_path = run_dir / CONFIG_FILE
    config_path.write_text(json.dumps(with_newest_inputs(cfg_doc, release_root, want["newest"], code, run_dir), indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    with login_file(env_file, neo4j):
        with (run_dir / LOG_FILE).open("a", encoding="utf-8", newline="\n") as log:
            try:
                cfg = code.rp.read_config(str(config_path))
                driver_run = code.rp.Driver(cfg, run=step_runner((code.rp.PY, code.rp.RS), run_dir / LOG_FILE, java, run),
                                            log=lambda text: print(text, file=log, flush=True))
                driver_run.run_steps(list(STEPS))
            except code.rp.Failed as err:
                raise LoadError(f"the local load stopped: {err}. The detail is in {run_dir / LOG_FILE}") from None
            except (OSError, ValueError) as err:
                raise LoadError(f"the local load stopped ({type(err).__name__}): {err if isinstance(err, ValueError) else ''}") from None
            # The marker comes last, after the report passed and every subgraph loaded. A load that stops earlier
            # leaves the database unmarked, and the sync check then reads it as not current.
            report = read_report(out, code, want)
            with connect(neo4j) as driver, driver.session(database=neo4j.database) as session:
                models = load_models(session, STORE, want["newest"], code, log)
                extras = [extra(session, STORE) for extra in extra_loads]
                marker = mark(session, STORE, want, report, code.ss, release_label(release_root, code.ss))
    return {**result, "status": "loaded", **summary(report), "logical_models": models, "extra_loads": extras, "marker": marker}


def tech_graph_loader(graph_files, release_root):
    """The extra load that puts the technical graph beside the ontology (kpi_store.tech_graph.load_neo4j): plain
    Cypher, in one transaction, and nothing when the database already holds these files."""
    def load_tech_graph(session, store):
        from . import tech_graph
        try:
            return {"name": "technical graph", **tech_graph.load_neo4j(session, graph_files, store, release_root)}
        except (tech_graph.TechGraphError, SystemExit) as err:   # the loader's own refusal, with its reason
            raise LoadError(f"the technical graph was not loaded: {err}") from None
    return load_tech_graph


def summary(report):
    """The figures of a load report that a person reads."""
    cases = report.get("fail_cases", [])
    return {"nodes": report["nodes"], "relationships": report["relationships"],
            "graph_hash": report["determinism_hash_sorted"],
            "shacl_violations_in_graph": report["shacl_violations_in_graph"],
            "in_graph_constraints": report["in_graph_shape_constraints"],
            "fail_cases_passed": sum(1 for c in cases if c["status"] in ("passed", "no-op")), "fail_cases": len(cases),
            "roundtrip_lost": report["roundtrip_lost"], "roundtrip_added": report["roundtrip_added"]}


def line(result):
    """The one line a person reads."""
    return (f"neo4j (local, database {result['database']}): {result['status']}, {result['nodes']} nodes, "
            f"{result['relationships']} relationships, {result['shacl_violations_in_graph']} SHACL violations over "
            f"{result['in_graph_constraints']} constraints, round trip lost {result['roundtrip_lost']} and added "
            f"{result['roundtrip_added']}, graph hash {result['graph_hash']}" + extras_text(result))


def extras_text(result):
    """What the extra loads did, for the one line: "; technical graph loaded, 61 nodes"."""
    return "".join(f"; {e['name']} {e['status']}, {e['nodes']} nodes" for e in result.get("extra_loads") or ()
                   if isinstance(e, dict) and {"name", "status", "nodes"} <= set(e))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kpi_store.load_neo4j", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stores", help=f"the local settings file (default: the one {ls.ENV_VAR} names)")
    ap.add_argument("--release", default=str(ls.ROOT), help="the release folder (default: the one this code is in)")
    ap.add_argument("--tech-graph", help="the technical graph's file, tech-graph.nq, to load beside the ontology")
    ap.add_argument("--force", action="store_true", help="empty the local database and load again, even when it is current")
    ap.add_argument("--json", action="store_true", help="print the result as JSON instead of one line")
    args = ap.parse_args(argv)
    try:
        local = ls.load(ls.locate(args.stores), release_root=Path(args.release))
        extras = (tech_graph_loader([Path(args.tech_graph)], Path(args.release)),) if args.tech_graph else ()
        result = load(local, Path(args.release), force=args.force, extra_loads=extras)
    except ls.LocalSettingsError as err:
        print(f"neo4j (local): {err}", file=sys.stderr)
        return 2
    except (LoadError, ov.ReleaseError) as err:
        print(f"neo4j (local): FAILED. {err}", file=sys.stderr)
        return 1
    except Exception as err:   # a driver error's text can carry an address, so only its type is printed
        print(f"neo4j (local): FAILED. The database did not answer ({type(err).__name__})", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str) if args.json else line(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
