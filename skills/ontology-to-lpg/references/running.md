# Running the projection: where each step runs, pins, reports and scale

Serves the load step (rule 5, the local Neo4j) and the running step. Read it before the first load, when setting up the projection in a repository or its CI, and before each rerun. The scripts named here are in this skill's `scripts/`.

## Rules

1. **Split the steps by what they need.** CI runs only what needs no Java and no database (each line is `uv run --no-project --with rdflib python <script> ...`, with `--with pyshacl` for `validate_data.py`):

   ```bash usage=skills/ontology-to-lpg/scripts
   check_projection_rules.py --config <config> --shapes <shapes>... --releases <folder> <data>...
   validate_data.py --config <config> --shapes <shapes>... <data>...
   build.py loadable --output <temporary>/loadable.nt <data>...
   build.py check-serialised --loadable <temporary>/loadable.nt --inferred inferred.nt
   validate_data.py --config <config> --shapes <shapes>... <temporary>/loadable.nt inferred.nt
   build.py manifest --config <config> --shapes <shapes>... --loadable <temporary>/loadable.nt \
     --inferred inferred.nt --output projection-manifest.json --verify <data>...
   build.py check-report --manifest projection-manifest.json --report projection-report.json
   ```

   A workstation runs reason (ROBOT needs Java 11 or later), then load and verify with `load_verify.py` against a local Neo4j (rule 5). *Why:* CI images rarely have Java and a Neo4j with plugins, and the committed report (rule 3) carries the workstation's result into CI.

2. **Pin every tool by version, and every downloaded jar by its SHA-256, and check the checksums before each run.** Record the versions in the configuration's `versions`, which the manifest copies. For the tested versions:

   | Jar | Download URL | SHA-256 |
   |---|---|---|
   | n10s 2025.06.1 | https://github.com/neo4j-labs/neosemantics/releases/download/2025.06.1/neosemantics-2025.06.1.jar | `4c461087e08405c7cb472ecfefc043e9e8ed93628ed74988e4fda1f1bac54b3e` |
   | APOC Core 2025.06.2 | https://github.com/neo4j/apoc/releases/download/2025.06.2/apoc-2025.06.2-core.jar | `4df40cea7444ea193d08f8a679aa998c498196fe149c8c02badb998f1c9580fb` |
   | ROBOT 1.9.10 | https://github.com/ontodev/robot/releases/download/v1.9.10/robot.jar | `16a73c074f3df359a7338a84b4e0788785fe06117f931bb9796e9619ea776105` |

   Check the two plugin jars with `check_plugins.py <plugins folder>` (on Windows, `python check_plugins.py <plugins folder>`). It reads every `.jar` in the folder and compares its SHA-256 with the two pins, so a jar passes under any file name and a jar of another version fails. Check ROBOT with `shasum -a 256 <jar>`, or on Windows `certutil -hashfile <jar> SHA256`; `run_projection.py` checks it before it runs. If a checksum differs, stop: the file is not the one these rules were tested with. Take the n10s jar that matches the Neo4j version (n10s 2025.06.1 is built for Neo4j 2025.06). `load_verify.py --plugins-dir` records every jar's SHA-256 in the report. *Why:* a different jar changes which constraints run in the graph and how values round-trip.

3. **Commit a manifest and a report that go stale on their own.** `build.py manifest` writes the manifest: the SHA-256 of each data and shape file, the triple counts, the input fingerprint (`pipeline.md`, rule 5), the shapes fingerprint (the SHA-256 of every shape file's bytes, concatenated in the order given), the Rule 4 option and its reason, the release exceptions and the versions; with `--verify` it fails when the committed manifest differs. `load_verify.py` writes the report, in the shape of `templates/projection-report.json`. Its fields:

   | Field | Meaning |
   |---|---|
   | `input_fingerprint`, `shapes_fingerprint` | As in the manifest. |
   | `left_out_before_import` | One object per term the import-safe shapes leave out: `{"shape": <IRI or blank-node id>, "constraint": <predicate IRI>, "reason": <text>}` (`pipeline.md`, rule 13). |
   | `compiled`, `not_compiled`, `prediction_differences` | The `listShapes()` rows as read from the engine; each constraint of the shapes file with no matching row (target, path, param and value); and where the `in_graph_shapes.py` prediction and the engine differ, for information (`pipeline.md`, rule 13). |
   | `shapes_import_rows`, `in_graph_shape_constraints` | The rows the shapes import returned, and the `listShapes()` count (`pipeline.md`, rule 11). |
   | `shacl_violations_in_graph` | Violations after the load; must be 0. |
   | `fail_cases` | One object per compiled row: its target, path, param and value, the Cypher (generated, or from `--manual-cases`), the focus, the expected path and components, the components reported on that path, and a status: `passed`, `no-op`, `failed` or `no case` (`pipeline.md`, rule 14). |
   | `mutant`, `in_graph_mutant_violations` | The mutant's focus and property, its violations (must be above 0) and the violations after the restore (must be 0). |
   | `export_rows`, `schema_rows_skipped`, `roundtrip_lost`, `roundtrip_added` | The raw export rows, the schema rows left out, and the triples lost and added; the last two must be 0. |
   | `determinism_hash_sorted`, `determinism_hash_shuffled` | Must be equal (`pipeline.md`, rule 17). |
   | `separator`, `renamed`, `rename_lossless` | What the kept graph puts between a prefix and a local name: `"__"` (n10s's own) unless the run gave `--separator`. With another value, `renamed` counts the labels, relationship types, node property keys and relationship property keys the run renamed, and `keys`, the distinct property keys over both kinds, the count the first reports gave (`{"labels", "rels", "node_keys", "rel_keys", "keys"}`; `{}` under n10s's names) and `rename_lossless` must be `true`: the dump of every node and relationship before the rename, with those renames applied, equalled the dump after, on both loads (`pipeline.md`, rule 11). A run whose rename is not proven writes no report, so a report with `rename_lossless` anything but `true`, or a separator other than `"__"` or a non-zero count in `renamed` without it, fails `check-report`, `copy_graph.py` and `triplestore.py`, under the one rule `load_verify.py` itself applies. |
   | `nodes`, `relationships`, `schema_relationships` | Counts after the sorted load: every `:Resource` node (schema nodes included), every relationship between two `:Resource` nodes, and how many of those are schema relationships from `onto.import` (their type starts with `n4sch` and the separator: `n4sch__` under n10s's names). To compare data between runs, use `nodes` and `relationships` minus `schema_relationships` (the data relationships); the schema part changes whenever a class or property is added. |
   | `versions`, `plugin_jars_sha256` | The configuration's versions, and each jar's SHA-256 in the plugins folder. |
   | `export_predicate_counts` | Triples per predicate in the export, schema rows left out; the triple-store add-on compares a store with it (`add-ons.md`). |
   | `passed` | `true`: `load_verify.py` writes the report only when every check passed. |
   | `samples` | Up to ten lost or added triples, five violations and five failed cases. |

   `build.py check-report` fails when the report's fingerprints differ from the manifest's, or when any check in it did not pass: it needs `passed: true`, at least one fail case, a non-empty `compiled` list (a missing or empty one fails), a fail case for every row in it and every case `passed` or `no-op`, a mutant that caught a violation and was restored, equal hashes, zero round-trip differences, and `rename_lossless: true` whenever the report names a separator other than n10s's or states the field at all. The template, with its empty values, fails on purpose. A report is written only at the end of a run that passed: `load_verify.py` deletes the report and `<report>.failed` when it starts, before it reads any flag, writes a temporary file beside the report and renames it into place only after every check passed. A run that stops leaves no report: a failed check writes its details to `<report>.failed` (exit 1), a driver, network or file error writes nothing (exit 1), and bad input writes nothing (exit 2). *Why:* a projection result that outlives its inputs, or a run that did not finish, is a false pass, and a shape can change while the loaded triples do not.

4. **Commit `inferred.nt`, the manifest and the report together, after one full workstation run.** Keep `loadable.nt`, `merged.ttl` and the downloads out of the repository; they are rebuilt from the Turtle files. *Why:* the three describe one run, and CI compares them with each other.

5. **Load into a local Neo4j that already runs, with the two pinned plugins, and send the triples in the request.** The skill starts and stops no server. Use Neo4j 2025.06.2 on the same machine: on Windows, a local DBMS in Neo4j Desktop. The server needs three things:

   - the n10s and APOC Core jars of rule 2 in its `plugins` folder (`check_plugins.py <plugins folder>` must exit 0);
   - the line `dbms.security.procedures.unrestricted=apoc.*,n10s.*` in its `neo4j.conf`;
   - a restart after either change.

   Keep the address and the login in an env file outside the repository, readable by you alone: `NEO4J_URI` (such as `bolt://127.0.0.1:7687`), `NEO4J_USERNAME`, `NEO4J_PASSWORD` and optionally `NEO4J_DATABASE`. Every script that reads the graph takes that file as `--env <file>` and never prints the password.

   **The load empties the database it is pointed at:** every node, then every constraint. Give it a database that holds nothing else. Community edition has one user database, so there the DBMS itself must be the projection's own.

   Then, in this order:
   1. run `load_verify.py` as its docstring shows, with `--env <file>` (or `--bolt <URI>` with `NEO4J_PASSWORD` and `NEO4J_USERNAME` in the environment), `--database <name>` when the file names none and the default is not the one you want, `--plugins-dir <plugins folder>`, and the configuration, shape, data, `merged.ttl`, `loadable.nt`, `inferred.nt` and `--report` arguments, and `--separator` when the kept graph should use another separator than n10s's (`pipeline.md`, rule 11; give the same value to every later command that reads the names back; `copy_graph.py` takes none);
   2. if it exits 1 or 2, stop here and do not run `check-report`. No report exists then; on exit 1 after the database checks, `<report>.failed` holds the values. The run deleted the report path when it started, so if that path is the committed report, restore it (`git restore projection-report.json`) and never stage `<report>.failed`. To try again after a fix (a case with status `no case` needs a manual case in a `--manual-cases` file, `pipeline.md`, rule 14), rerun step 1; `load_verify.py` empties the database itself. Every rerun runs every case again;
   3. run `build.py check-report --manifest projection-manifest.json --report projection-report.json`, as in rule 1; if you copy the graph to another Neo4j (`add-ons.md`, add-on I), do it now, before anything else writes to the local graph.

   *Why:* the triples travel in the request (n10s's `import.inline` procedures), so the server reads no file: it needs no import folder, no file-access setting and no shared disk, and the same command works against a server on another machine. The ontology and the shapes go in one request each, because n10s's ontology import reads a declaration and the triples that use it together (split into requests of seven lines, it loaded 38 of the template's 51 ontology triples) and shapes hold blank nodes. `loadable.nt` and `inferred.nt` hold one triple per line and no blank node (`design-rules.md`, Rule 3), so they go in batches of whole lines, at most 1,000,000 bytes each; every request must return `OK`, and the triples loaded must add up to the file's lines. The determinism check empties the database between its two loads (`pipeline.md`, rule 17).

6. **Change only the loader as the graph grows:**

   | Size | Loader | What changes |
   |---|---|---|
   | Up to about 10M triples | n10s `rdf.import.inline`, in batches of lines | Nothing |
   | About 10M to 1B+ triples | Generate node and relationship CSVs from `loadable.nt` and `inferred.nt` with the same mapping, then `neo4j-admin database import` | Only the load step |
   | Incremental updates | Load each delta with n10s (MERGE by `uri`); delete with `n10s.rdf.delete` | Add a periodic full rebuild and compare hashes |

   *Why:* the mapping rules do not depend on size, so the checks and the verify step stay valid.

7. **Explore a graph read-only through the official Neo4j MCP server.** Neo4j's MCP server (https://github.com/neo4j/mcp, README at commit `1210b0e8f0`, read 2026-10-24) gives an agent `get-schema`, `read-cypher`, `write-cypher` and `list-gds-procedures` on a running Neo4j. Point it at the verified local graph or its copy with `NEO4J_MCP_READ_ONLY=true`, which disables `write-cypher`. That is a guard, not a boundary: the README warns that `read-cypher` relies on Neo4j classifying each query as read-only, and "custom procedures or functions incorrectly classified as read-only by Neo4j may bypass this check". For a hard boundary, give the server a database user with read-only privileges, and do not install custom procedures you have not reviewed. *Why:* the graph is a projection of the Turtle release; a fix made through the server would be lost at the next rebuild and would break the hash that proves the copy (`add-ons.md`, add-on I).
