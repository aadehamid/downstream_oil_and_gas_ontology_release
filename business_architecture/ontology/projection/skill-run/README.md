# Running the ontology-to-lpg skill on the KPI Store inputs

The `ontology-to-lpg` skill's `run_projection.py` (version 2.3 of its method) runs the projection of the KPI Store release and every check, from the run configuration in this folder. It is the one loader (the decision of 2026-11-01). The driver writes nothing into the repository; `../pipeline.py record` takes its `inferred.nt` and a summary of its report into `../` afterwards, and `../pipeline.py build --verify` keeps checking the inputs in CI.

## What is here

| File | What it is |
|---|---|
| `epm-run.json` | The run configuration: releases mode, the inputs from `inputs.py`, each release's `shapes` and `catalog` graphs, the saved walks, and one underscore as the separator. Its `out` and `robot_jar` are defaults under the home folder, outside the repository; set both in your copy. It names no store address: `environment.example` lists those settings. |
| `inputs.py` | The one input list. It imports `INPUTS`, `SHAPES` and `PACKAGES` from `../pipeline.py` and prints them as absolute paths (`data`, `shapes`, `releases`). Importing `pipeline.py` runs nothing: its `main()` runs only when the file is run as a script. |
| `epm-config.json` | The skill's projection configuration for these inputs: Rule 4a, the module namespaces and prefixes, the qualified-relation classes, the package versions (equal to `PACKAGES`) and one release exception: `tg:designedAs` has no range, on purpose (technical-graph 1.0.0, 2026-11-02; the decision of 2026-11-02). |
| `queries.json` | The 14 saved walks the explore step compares in Neo4j and Jena: one from each kind of node a module holds as instances (technical-graph holds none: its vocabulary has no instances), plus a process across modules, a value stream end to end and a measure back to its processes. |
| `test_skill_run.py` | Checks that `inputs.py` lists exactly the pipeline's inputs and shapes, that each file exists, that `epm-config.json` pins the same packages, that `epm-run.json` names this folder's files (each must exist), keeps outputs and ROBOT under the home folder, which CI cannot check, and holds no other key, that every release has its `shapes` and `catalog` files, and that each saved walk is well formed. `scripts/check.sh` runs it. |
| `environment.example` | The settings `../sync_stores.py`, `../empty_stores.py` and `../logical_models.py` read, each commented out. |

## Running it

`epm-run.json` names no store, so a run with it alone checks, reasons and stops before the load. Copy it to a folder outside the repository, make its paths absolute, and add the keys for the stores you have. Each key that is missing skips its step, and the run says so.

| Key | What it names |
|---|---|
| `neo4j_env` | An env file outside the repository for the local Neo4j that has n10s and APOC: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` and, optionally, `NEO4J_DATABASE`. The `load` step empties that database |
| `plugins_dir` | The local Neo4j's `plugins` folder. `check_plugins.py` must find the two pinned jars there before the load starts |
| `target_env` | An env file for the copy's target, a server that needs no plugin, with `NEO4J_DATABASE` naming the database the copy uses. It must differ from `neo4j_env` |
| `replace_target` | `true` lets the copy delete what the target database holds first |
| `jena` | The URL of a Fuseki dataset started with `--update`, such as `http://127.0.0.1:3030/ds`. The step empties it before it loads |
| `explore_fuseki`, `triplestore_fuseki` | A Fuseki dataset of its own for the walks, and one for the triple-store counts |
| `rebuild` | `{"source": "jena" or "repo", "out": <folder>}`, to prove the graph can be rebuilt from the store's copy |

With the skill folder in `$SKILLS`:

```
cd "$SKILLS/ontology-to-lpg/scripts"
uv run --no-project --with rdflib python3 run_projection.py --config <your copy of epm-run.json> --plan
uv run --no-project --with rdflib python3 run_projection.py --config <your copy of epm-run.json>
```

`--plan` lists the steps and why any is skipped, and runs nothing. The run needs uv, Java 11 or later and ROBOT 1.9.10 at the path `robot_jar` names. It starts and stops no server: the Neo4j servers and the Fuseki datasets the copy names must already run. The skill's `references/running.md`, rule 5, says how to prepare the local Neo4j, and the `rdf-store` skill's `references/stores.md` says how to start Fuseki from the Apache jar. The driver reads no password: it passes each env file to the skill's scripts by path (`load_verify.py --env`, `copy_graph.py --source-env` and `--target-env`).

The Databricks table `epm_triples` is not a step of this run. A notebook loads it with the `rdf-store` skill's `rdfstore.py`.

The skill's `references/run-config.md` describes each key, each step and the check it runs. Steps 2 to 4 cover checks V1 to V5 of the skill's validation path and the load covers V6 to V12. The copy, the triple-store counts and the round trips cover the rest, up to V14. For the `GRAPH TYPE` checks G1 to G4, the `graph-type` step writes the statement; applying it, reading it back with `SHOW CURRENT GRAPH TYPE` and probing it with a write that breaks it are done by hand.
