# Property-graph projection (Step 12)

Projects the KPI Store ontology into a Neo4j labelled property graph with the `ontology-to-lpg` skill's driver, `run_projection.py` (method version 2.3; Rule 4a, qualified-relation nodes). Turtle stays the master copy; the graph can be rebuilt from it at any time. The design is the decision of 2026-10-13, and the policy and the one local Neo4j are the decision of 2026-11-01. It projects every released package under `../releases/`, each at its newest version, with each package's own shapes.

## What each store holds

Each module package has three graphs: `<module>.ttl` (the content), `shapes.ttl` (the rules) and `catalog.ttl` (the DCAT release record). `../MODULES.md` describes each module's three files and what each package is built from.

| Store | `<module>.ttl` | `shapes.ttl` | `catalog.ttl` |
|---|---|---|---|
| Jena, one Fuseki dataset served by the plain Apache jar | All | All | All |
| Databricks, the Delta table `epm_triples`, loaded by a notebook | All | All | All |
| Neo4j, one local database with n10s and APOC, and its copy in a named database on another server | All | Not as nodes: they validate the release | Not in full: one `ModuleRelease` node per module |

- **All the content.** Neo4j gets all of `<module>.ttl`, with no selective projection, so the round trip keeps proving 0 lost and 0 added.
- **The shapes validate the release.** pySHACL runs them before the load and n10s runs them in the graph at the load. They are not projected as nodes.
- **One release record per module.** A node labelled `ModuleRelease`, linked to the module's `owl_Ontology` node by `DESCRIBES`. Its fields are `module`, `version`, `version_iri`, `ontology`, `download_url`, `conforms`, `in_graph_constraints`, `violations`, `shapes_sha256`, `projection_version` and `loaded_at`, each from the release's own files or the run's report. `conforms`, `in_graph_constraints` and `violations` describe the whole load, because the shapes run over every module together. The node has no `Resource` label and the link starts outside `Resource`, so the graph hash, the counts, the module tags and the round trip read neither, and no field enters a hash. To read them: `MATCH (r:ModuleRelease)-[:DESCRIBES]->(o) RETURN r.module, r.version, r.conforms, r.violations, r.loaded_at, o.uri ORDER BY r.module`.
- **One form, one local database.** The local Neo4j is loaded and checked first. The copy takes the checked graph over the driver to a server that needs no plugin, and its graph hash must equal the local one. Every node and relationship carries a `graph` property giving its release's version IRI, and the ontology import adds `n4sch__` schema nodes and relationships.
- **A release's logical models.** A package may also carry graphs of its own, which its `manifest.json` lists beside the three. Only the `logical-model` module does. `logical_models.py load` puts each model's ER Studio export and annotation layer into Jena as named graphs, `<version IRI>/<slug>.erstudio` and `<version IRI>/<slug>.layer`, and each model in full into the Neo4j database the settings name as a subgraph labelled `LogicalModel`, never `Resource`, with a `LogicalModelMarker`. The same named graphs go into `epm_triples` with the load that writes the table; `logical_models.package_rows` returns their rows. The projection's counts, hash and round trip never read the subgraph; `sync_stores.py check` reports it on an `lm:neo4j` line (the decision of 2026-11-02, amendment "the stores").
- **Two labels on a class.** A class is one node with two labels: `owl_Class`, from its own triple in the Turtle, and `n4sch_Class`, from the ontology import, which also writes the schema relationships. They are not two nodes. Count classes with one label: 46 nodes carry both.

| File | What it is |
|---|---|
| `pipeline.py` | What runs with no database, in CI: `build` checks the rules, validates and writes the manifest; `build --verify` fails unless the manifest is current; `record --run <driver out>` takes a driver run's `inferred.nt` and a summary of its report into this folder. It also holds the input lists the driver reads |
| `inferred.nt` | The reasoner's inferences about the domain, from the last driver run |
| `projection-manifest.json` | Input and shape hashes, triple counts, the input fingerprint, the pinned versions, the listed release gaps (none since `integration` 2.0.0, the decision of 2026-10-23) |
| `projection-report.json` | A summary of the last load's report, for the fingerprint it names. The full report stays in the driver's output folder |
| `skill-run/` | The driver's run configuration, its input list and the saved walks (`skill-run/README.md`) |
| `test_pipeline.py` | The rule checks, the build, the record, and that the report is current and passed |
| `empty_stores.py` | Counts what a Neo4j database or a Jena dataset holds and, with `--yes`, empties it before a clean reload. `test_empty_stores.py` holds its offline tests |
| `skill-run/environment.example` | Every setting `sync_stores.py`, `empty_stores.py` and `logical_models.py` read: the Neo4j address, login and database, and the Jena query URL |
| `sync_stores.py` | Says what a current store holds (`expected`), judges a Neo4j database and a Jena dataset against this tree's newest catalog (`check`), and writes the Neo4j marker after checking the database (`mark`). Its functions also judge the Delta table `epm_triples` from rows and a marker that a caller has read |
| `logical_models.py` | Loads a release's logical models when the newest releases hold the `logical-model` module: the models' graphs into Jena, and each model as a `LogicalModel` subgraph into Neo4j. `package_rows` returns the rows the load of `epm_triples` adds. Its docstring lists the labels, node shapes and edges |
| `test_logical_models.py` | The offline tests of `logical_models.py`, on a package built in a temporary folder from the module's made-up example |
| `test_sync_stores.py` | The offline tests of `sync_stores.py` |
| `subgraph.py` | Replaces and fingerprints a subgraph that shares a Neo4j database with the ontology and stays apart from it. `test_subgraph.py` holds its offline tests |

`scripts/check.sh` runs `pipeline.py build --verify` and the tests. The load needs Java and a running Neo4j, so it runs on a workstation, not in CI.

## Settings

`sync_stores.py`, `empty_stores.py` and `logical_models.py` read one set of settings: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` and `EPM_JENA_QUERY`. Copy `skill-run/environment.example` to a file outside the repository, fill it in, and name that file in `EPM_STORES_ENV`. A value set in the process environment wins over the file. No command prints a password.

## Run the projection

Run it after any input or shape changes. You need [uv](https://docs.astral.sh/uv/), Java 11 or later ([ROBOT's Getting Started](https://robot.obolibrary.org/): "make sure you have Java 11 or later installed"), and a local Neo4j 2025.06.2 that already runs with the n10s and APOC Core jars in its `plugins` folder. The driver starts and stops no server. It is in the `ontology-to-lpg` skill, in the `scripts/` folder of `$SKILLS/ontology-to-lpg`; the skill's `references/running.md`, rule 5, says how to prepare the Neo4j server, and the `rdf-store` skill's `references/stores.md` says how to start Fuseki from the Apache jar.

1. Download ROBOT 1.9.10 (it runs the ELK reasoner), and check its SHA-256. Run these commands in a folder outside the repository; the jar never goes into this tree. If the checksum differs, stop: the driver refuses another file. On Windows, check it with `certutil -hashfile robot.jar SHA256`.

   ```bash skip reason="awaits-the-rewrite: written for the stores of the earlier platform"
   cd <a folder outside the repository>
   curl -L -o robot.jar https://github.com/ontodev/robot/releases/download/v1.9.10/robot.jar
   shasum -a 256 robot.jar
   # expect 16a73c074f3df359a7338a84b4e0788785fe06117f931bb9796e9619ea776105
   ```

2. Copy `skill-run/epm-run.json` to a folder outside the repository, set `robot_jar` to the jar's path and `out` to your output folder, and add the keys that name your stores (`skill-run/README.md` lists them). Then run the driver with the copy. It checks, reasons, empties and loads the local Neo4j, writes the release records, and runs each further step whose key the copy holds: the copy to the named database, the Jena round trip, the walks and the rebuild. `--plan` lists the steps first and runs nothing.

   ```bash skip reason="awaits-the-rewrite: written for the stores of the earlier platform"
   cd "$SKILLS/ontology-to-lpg/scripts"
   uv run --no-project --with rdflib python run_projection.py --config <your copy of epm-run.json> --plan
   uv run --no-project --with rdflib python run_projection.py --config <your copy of epm-run.json>
   ```

3. Take the result into this folder, from this folder. It refuses a run that read other inputs than this tree's, or whose report did not pass. Commit `inferred.nt`, the manifest and the report together.

   ```bash skip reason="awaits-the-rewrite: written for the stores of the earlier platform"
   uv run --with rdflib --with pyshacl python pipeline.py record --run <your output folder>
   ```

4. Load the logical models, then write the Neo4j marker. `mark` checks the database against this tree first and stops, writing nothing, when it does not match.

   ```bash skip reason="awaits-the-rewrite: written for the stores of the earlier platform"
   uv run --with rdflib --with neo4j --with pyoxigraph python logical_models.py load
   uv run --with rdflib --with neo4j python sync_stores.py mark
   ```

The Databricks table is not loaded from here. A notebook loads `epm_triples` with the `rdf-store` skill's `rdfstore.py` and writes the table's marker row in `epm_store_markers`.

## Check the stores

```bash skip reason="awaits-the-rewrite: written for the stores of the earlier platform"
uv run --with rdflib python sync_stores.py expected
uv run --with rdflib --with neo4j python sync_stores.py check
```

`expected` prints what a current store's marker holds: the number of catalog datasets, their digest, the input fingerprint and the newest release IRIs. `check` reads the Neo4j database and the Jena dataset the settings name and says whether each is current; `--store` limits it to one. `empty_stores.py` counts what a store holds and, with `--yes`, empties it before a clean reload.

## The committed figures

`python3 scripts/epm_facts.py projection`, from the repository root, prints the figures of the last recorded load. `projection-report.json` holds them: 4,237 nodes and 22,312 relationships from 37,206 triples and 2 inferred, 0 SHACL violations in the graph over 806 in-graph constraints, the deliberate mutant caught, a round trip that lost 0 and added 0 triples, equal hashes for the sorted and shuffled loads, and every name renamed to one underscore without loss (88 keys, 52 labels, 88 node keys, 0 rel keys, 121 rels). Of the relationships, 21,883 come from the releases' triples, 427 are schema relationships from the ontology import, and 2 come from inferences. That load ran on 2026-11-04, on a Neo4j 2025.06.2 with n10s 2025.06.1.
