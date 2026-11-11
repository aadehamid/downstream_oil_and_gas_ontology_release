# One run, every store, every check: `run_projection.py`

Read it when a project projects its release more than once, or into more than one store, and wants one command instead of its own scripts around this skill's. `run_projection.py` runs steps 2 to 6, add-ons F, H, I, J and M, the `rdf-store` skill's round trip through Jena Fuseki and a rebuild from that store, all from one run configuration, and runs every check each of them has. It runs the skill's own scripts; it adds no check of its own except the rebuild's two comparisons.

```bash skip reason="illustration: a usage pattern, where square brackets mark the optional arguments"
uv run --no-project --with rdflib python scripts/run_projection.py --config run.json --plan
uv run --no-project --with rdflib python scripts/run_projection.py --config run.json [--only a,b] [--skip a,b]
```

`--plan` lists the steps that would run, and why any is skipped, and runs nothing. It needs uv, and Java 11 or later for ROBOT. It starts and stops no server: the Neo4j servers and the Fuseki datasets the configuration names must already run (`running.md`, rule 5; the `rdf-store` skill's `references/stores.md`). It reads no password: the env files are passed to the scripts by path.

## First, choose releases or files

The run configuration's `mode` says what is projected. Without one, the driver prints this choice and stops, so ask the user before writing the configuration:

| Mode | What it takes | For | Against |
|---|---|---|---|
| `releases` (recommended) | Versioned packages: each data file has one `owl:versionIRI` and pins what it requires | The pins and the closure of requirements are checked, every node is tagged with its release, the module graph shows what requires what, and a store copy traces back to a release | You need packages first |
| `files` | Any Turtle or N-Triples files, or folders of them | Works on what you have now, with the same loads, hashes, round trips and rebuild | No version pins or closure check; without SHACL shapes the projection uses defaults derived from the data |

When the user picks releases and has none, the driver stops and points to the `ontology` skill's guided packaging walk-through (`skills/data/ontology/scripts/build_package.py`), which builds them. The walk-through is being built separately; until it lands, package with the `ontology` skill's Step 10 (release and publication), or choose files.

## The run configuration

A JSON object. Paths are relative to the configuration's own folder, so it can sit in the project repository, beside the projection configuration. Copy `templates/run-config.json`.

| Key | Needed by | What it holds |
|---|---|---|
| `projection_config` | every step | The projection configuration (`templates/projection-config.json`). |
| `mode` | every step | `releases` or `files` (above). |
| `data`, `shapes` | every step | Releases: the released package files, and the shape files (each release's and any whole-graph ones). Or give `inputs_script` instead. Files: `shapes` is optional. |
| `files` | files mode | RDF files (`.ttl`, `.nt`) or folders; a folder gives every such file under it, in path order. |
| `graphs` | files mode, optional | `{file: graph IRI}` for a file with no `owl:versionIRI`. |
| `inputs_script` | instead of `data` and `shapes` | A Python script printing one absolute path per line for `<script> data` and `<script> shapes`, when the project keeps its list elsewhere. It runs with rdflib, pySHACL and the neo4j driver. |
| `releases` | releases mode | The folder of released packages, `<module>/<X.Y.Z>/`, for the pin check. |
| `out` | every step | The output folder. It must be outside the repository that holds the configuration. |
| `robot_jar` | `project` | ROBOT 1.9.10. Its SHA-256 is checked before any command runs (`running.md`, rule 2). |
| `manual_cases` | `load`, optional | Passed to `load_verify.py --manual-cases`. |
| `release_graphs` | `jena`, `rebuild` | The other files of each release that the store copy holds, by name without `.ttl` (for example `["shapes", "catalog"]`): `<name>.ttl` beside each data file, loaded as the graph `<version IRI>/<name>`. |
| `neo4j_env` | `load`, `review`, `tags`, `release-record`, `copy`, `explore`, `rebuild` | An env file, outside the repository, naming the local Neo4j that has n10s and APOC: `NEO4J_URI` (such as `bolt://127.0.0.1:7687`), `NEO4J_USERNAME`, `NEO4J_PASSWORD`, optional `NEO4J_DATABASE`. **The `load` step empties that database.** |
| `plugins_dir` | `load`, optional | The local Neo4j's plugins folder. `check_plugins.py` must find the two pinned jars there before the load starts (`running.md`, rule 2), and the report records each jar's SHA-256. |
| `target_env` | `copy` | An env file naming the copy's target, a server that needs no plugin: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` for the named database the copy and its checks use. It must differ from `neo4j_env`. |
| `replace_target` | `copy`, optional | `true` passes `--replace` to `copy_graph.py`, which deletes everything on the target first. A rebuild that copies needs it, because the target then holds the first copy. |
| `queries` | `explore` | The project's saved walks for `explore.py compare`. |
| `rebuild` | `rebuild` | `{"source": "repo" or "jena", "out": <folder>}`. |
| `rdf_store` | `jena`, `explore`, `rebuild` | The `rdf-store` skill folder; by default `../rdf-store` beside this skill. |
| `jena`, `explore_fuseki`, `triplestore_fuseki` | the step of that name (`explore` for `explore_fuseki`, `triplestore` for `triplestore_fuseki`) | The URL of a Fuseki dataset, such as `http://127.0.0.1:3030/ds`, started with `--update`. Each step empties its dataset (`DROP ALL`) before it loads, so each key must name a dataset of its own that holds nothing else: three servers on three ports, or one server with three datasets. |
| `separator` | `load`, `review`, `tags`, `graph-type`, `copy`, `explore`, `rebuild`, optional | What sits between a prefix and a local name in the kept graph: underscores only, `"_"` for one. n10s writes two; with another value every check runs on n10s's names first, then every label, relationship type and property key is renamed, the rename is proven lossless on a dump of the whole graph or the load fails with no report (`pipeline.md`, rule 11; `rename_lossless` in the report), and the hashes are of the renamed graph. The value is passed as `--separator` to every script that reads or describes the graph (`load_verify.py`, `model_review.py` locally and on the copy, `module_tags.py`, `build.py graph-type`, `explore.py`, and the rebuild's run of each), so the review, the tags, the `GRAPH TYPE` and the walks read the renamed names. A value that is not a string of underscores is refused when the configuration is read, before `--plan` prints anything; under a separator other than n10s's, a prefix that holds the separator, or n10s's own two underscores, is refused by each of those scripts before it loads, queries or writes. `copy_graph.py` takes no separator: it copies the names as they are. |

A step whose key is missing is skipped and says so: no `target_env`, no `copy`; no `jena`, no Jena round trip. A step that needs an earlier one's output stops with a message when it isn't there. The steps that read the local graph (`review`, `tags`, `release-record`, `copy`, `explore`) read whatever the local Neo4j holds, so run `load` first; the copy refuses a source whose hash is not the report's.

## Files mode

Each file is one named graph. Its name is its `owl:versionIRI` when it has one; else its entry in `graphs`; else `urn:ontology-to-lpg:file:` and its path relative to the run configuration. A `graphs` entry for a file that has an `owl:versionIRI` is refused, so the store and Neo4j always name a file alike. Every store gets each file under that name (`rdfstore.py --graph FILE=IRI`), `module_tags.py --graph` tags each node and relationship with it, and `explore.py --files` reads every graph in the store as a package.

Without `shapes`, the driver writes `default-shapes.ttl` into `out`: one `sh:NodeShape` per class the data types a node with (outside the RDF, RDFS, OWL, SHACL and XSD namespaces), and for each predicate the class's instances use (subclasses' instances included), a property shape with the counts the data shows: `sh:maxCount` the most values one instance has, and `sh:minCount 1` when every instance has one. The inverse ends of the qualified-relation classes the projection configuration registers get a shape on `sh:inversePath`, counted the same way, as Rule 4a requires. The data conforms by construction, and the load's gates (compiled rows, a fail case each, the mutant) have something to check. n10s's defaults decide the rest: a literal becomes a property, an IRI a relationship.

The rule check runs without `--releases`, so version pins and the closure of requirements are not checked. The run says so, and so does `run-manifest.json`.

## The run manifest

The `project` step writes `<out>/run-manifest.json`: the mode, each data and shape file with its SHA-256 (and, in files mode, its graph name and where the name came from), each release's `catalog.ttl` with its SHA-256, whether the shapes were derived, and the notes above. The rebuild refuses to compare with `out` when any of those files has changed, or a catalog has been added or removed, since. `release_record.py` refuses a file whose path and SHA-256 are not in it.

## The steps and their checks

| Step | What runs | It passes when |
|---|---|---|
| `project` | `check_projection_rules.py`, `validate_data.py`, `build.py merge`, ROBOT ELK, `build.py inferred`, `loadable`, `check-serialised`, `validate_data.py` again on both files, `build.py manifest`, then the advisory `in_graph_shapes.py` | every script exits 0: checks V1 to V5 (`multi-store.md`) |
| `load` | `check_plugins.py` when `plugins_dir` is set, `load_verify.py --env <neo4j_env>` (it empties the database, then sends the triples in the request), `build.py check-report` | the report is written and `check-report` passes: V6 to V12 |
| `review` | `model_review.py` on the local graph, written to `model-review.json` | no ERROR finding |
| `tags` | `module_tags.py tag`, `check`, `modules` on the local graph (add-on F) | every node and relationship carries exactly one tag, equal to its package |
| `release-record` | `release_record.py records`, `write` and `check` on the local graph, into `release-records.json` (add-on M). Files mode skips it | one record per module, every field read back, and the graph hash unchanged and equal to the report's |
| `graph-type` | `build.py graph-type` to `graph-type.cypher` (add-on H) | the statement is written; apply it by hand |
| `triplestore` | the `triplestore_fuseki` dataset, emptied, then `triplestore.py` (add-on J) | the per-graph, per-predicate and three-way counts match the report |
| `copy` | `copy_graph.py --source-env <neo4j_env> --target-env <target_env>` (add-on I), then `module_tags.py check` and `modules`, `release_record.py write` and `check` when this load has records, and `model_review.py` there | the target's graph hash equals the source's and the report's, the tags check passes there, the records read back, and no ERROR finding |
| `jena` | the `jena` dataset, emptied, then `rdfstore.py roundtrip` of the data files and their release graphs (files mode: each file under its graph name) | the store's export has the files' RDFC-1.0 hash |
| `explore` | the `explore_fuseki` dataset, emptied and loaded with the data and `inferred.nt`, then `explore.py compare` against the local graph and, when this run copied, against the target | every saved walk and the module map give the same edges, nodes and tags in Neo4j and in Jena |
| `rebuild` | see below | the store's export hashes equal to the release, the rebuild's triples and graph hashes equal this run's, and its own load, tags, release records, copy and walks pass |

## The rebuild

`rebuild` proves the graph can be rebuilt from a store's copy alone. It needs `project` and `load` to have run into `out` (in this run or an earlier one), with the inputs `run-manifest.json` records. It loads the same local Neo4j again: `load_verify.py` empties it first, and the equal graph hashes prove the rebuilt graph is the one the first load verified.

1. With `source` `jena`, it exports everything the store holds (`rdfstore.py export --ttl-dir`), packs the release files the same way the round trip did, and requires equal RDFC-1.0 hashes (`rdfstore.py compare`). A rebuild from Jena loads Jena first when this run hasn't. With `repo`, it takes the repository files.
2. It maps the exported graphs to the inputs. A data file maps to the graph named by its `owl:versionIRI` (in files mode, by its graph name), and a release graph's shapes file to `<version IRI>/<name>`. A shape file that is no release graph, such as a whole-graph shapes file, was never in the store, so it comes from the repository, and the run says which.
3. It runs `project` and `load` into `rebuild.out`, then requires `loadable.nt` and `inferred.nt` to hold the first run's triples, compared as RDF 1.1 terms, and both reports to hold exactly `determinism_hash_sorted` and `determinism_hash_shuffled`, non-empty and equal to the first run's. A store export may write a literal typed `xsd:string` as a plain literal, which RDF 1.1 defines as the same term, so the files need not be byte-equal. The equal graph hashes prove Neo4j holds the same graph.
4. It tags, writes the release records (releases mode), copies when `target_env` is set (with `replace_target`), and explores when `queries` is set.

`run_projection.py compare-triples <rebuild out> <baseline out>` and `compare-reports <rebuild report> <baseline report>` run step 3's two checks on their own.

## What it leaves behind

The run starts no server and stops none. The local Neo4j holds the last load (after a rebuild, the rebuilt graph, which has the same hash), the target holds the copy, the `jena` dataset holds the release, and the `explore_fuseki` and `triplestore_fuseki` datasets hold what their steps loaded. A Fuseki dataset started with `--mem` empties when its server stops. To empty a Neo4j database, delete only what the run loaded.
