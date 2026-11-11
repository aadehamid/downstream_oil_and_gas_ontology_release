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

On the client platform one command runs the projection and every load: the runner, `py -m kpi_store.runner`. Its `neo4j` step calls `kpi_store/load_neo4j.py`, which runs the driver on this folder's inputs against the local Neo4j, and its `enterprise` step copies the checked graph to the named database. `ontology-stores-runbook.md` in this folder gives every step, from the setup of the machine to the sync check, and says what each step of the runner does.

Two commands of this folder need no database. Run them from this folder after any input or shape changes.

1. Check the rules, validate, and compare the manifest with a fresh build. It fails unless the manifest is current. To write a new manifest, run `py pipeline.py build`.

   ```powershell run=release-copy
   cd business_architecture/ontology/projection
   py pipeline.py build --verify
   ```

   ```text expect
   Step 1 passed; loadable.nt <count> triples, inferred.nt 2
   projection-manifest.json is current
   ```

2. After a Neo4j load, take the load's result into this folder: `inferred.nt`, a summary of its report, and the manifest. The runbook's section "Record the load's report in the release folder" runs the command, `py pipeline.py record`, on a real load. It refuses a load that read other inputs than this tree's, or whose report did not pass.

The Databricks table is not loaded from here. The runner's `notebook` step loads `epm_triples` with the `rdf-store` skill's `rdfstore.py` and writes the table's marker row in `epm_store_markers`.

## Check the stores

`py -m kpi_store.sync_check` reads the four stores of the client platform and says whether each is current. The runbook's section "The sync check" shows it and how to read each line. It takes what a current store holds from `sync_stores.py` in this folder:

```powershell run=release-copy
py sync_stores.py expected
```

```text expect
{
  "catalog_datasets": 13,
...
}
```

`expected` prints what a current store's marker holds: the number of catalog datasets, their digest, the input fingerprint and the newest release IRIs. `empty_stores.py` counts what a store holds and, with `--yes`, empties it before a clean reload.

## The committed figures

`python3 scripts/epm_facts.py projection`, from the repository root, prints the figures of the last recorded load. `projection-report.json` holds them: 4,237 nodes and 22,312 relationships from 37,206 triples and 2 inferred, 0 SHACL violations in the graph over 806 in-graph constraints, the deliberate mutant caught, a round trip that lost 0 and added 0 triples, equal hashes for the sorted and shuffled loads, and every name renamed to one underscore without loss (88 keys, 52 labels, 88 node keys, 0 rel keys, 121 rels). Of the relationships, 21,883 come from the releases' triples, 427 are schema relationships from the ontology import, and 2 come from inferences. That load ran on 2026-11-04, on a Neo4j 2025.06.2 with n10s 2025.06.1.
