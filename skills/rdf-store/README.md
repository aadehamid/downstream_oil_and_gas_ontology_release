# rdf-store

An agent skill for loading RDF releases into a triple store and proving that nothing was lost. The agent loads each release file as its own named graph, exports everything the store holds, and compares the two sides by their RDF Dataset Canonicalization (RDFC-1.0) hash. Equal hashes mean every triple, literal, datatype, language tag and graph came back, and nothing was added.

It supports two stores: Apache Jena Fuseki (or any store that speaks the SPARQL 1.1 Graph Store Protocol), started with Java from the plain Apache jar, and a Delta table in Databricks, written and read by a notebook's own Spark session. The skill was split out of `ontology-to-lpg` on 2026-10-24, so the projection skill keeps Neo4j and this one keeps the triple stores.

This README is for people. Agents read `SKILL.md` and the files it points to.

## How to use it

1. Start Fuseki. Download `jena-fuseki-server-6.2.0.jar`, check its SHA-256 (`references/stores.md` gives the value and the command), and run `java -jar jena-fuseki-server-6.2.0.jar --mem --update --localhost --port 3030 /ds`.
2. Round-trip your releases. The command below sends the library example of the `ontology-to-lpg` skill, so you can run it as written, from this release's top folder. `<your Fuseki address>` is the dataset's address, `http://127.0.0.1:3030/ds` for the server of step 1. For your releases, name every release file at the end instead. The tool needs the pyoxigraph package (`py -m pip install pyoxigraph`). On macOS or Linux, write `python3` for `py`.

   The dataset must hold nothing but what this command loads. The comparison reads everything the store holds, so a graph from another load fails it.

   ```powershell run=empty-fuseki
   cd skills/rdf-store
   py scripts/rdfstore.py roundtrip --store fuseki --gsp <your Fuseki address>/data --query <your Fuseki address>/query --update <your Fuseki address>/update --report report.json ../ontology-to-lpg/templates/library-module.ttl
   ```

   ```text expect
   ...
     "hashes_equal": true,
     "expected_quads": 100,
     "actual_quads": 100,
   ...
   PASS the store's copy has the same RDFC-1.0 hash
   ```

   It prints `PASS` and exits 0 when the store's copy has the same hash, or prints a diff and exits 1. `--update` publishes everything in one request, which SPARQL 1.1 Update says a store SHOULD apply atomically; any failure ends the run with exit 1, and the store should then be reloaded.

3. For Databricks, run the round trip inside a notebook, where Spark already exists: import `rdfstore.py` and call `roundtrip(SparkStore(spark, "<catalog>.<schema>.<table>"), pack(files))`. The rows go to a staging table first; the live table is replaced only when the staging copy matches. It needs no host name, warehouse or credential (`references/stores.md`).
4. To get Fuseki's copy back as files, export it. `copy.nq` must not exist yet, and the `ttl` folder must be empty or absent.

   ```powershell run=empty-fuseki
   py scripts/rdfstore.py export --store fuseki --gsp <your Fuseki address>/data --query <your Fuseki address>/query --out copy.nq --ttl-dir ttl
   ```

   ```text expect
   wrote copy.nq: 100 quads in 1 graphs
   ```

## Tested on

On 2026-11-11 the 39 graphs of a 13-module ontology's newest releases (40,692 quads: each module's content, shapes and catalog) round-tripped with equal RDFC-1.0 hashes through Fuseki 6.2.0, started with Java 21 from the plain jar and published in one update request. The load took 1.5 seconds and the export and comparison 0.8 seconds. An export of that store rebuilt a property graph with the hash of the one built from the files.

The Delta table path is tested against a stand-in Spark session that decodes every statement `SparkStore` sends, including a 100,000-row load in 50 statements. It has not been run in a Databricks workspace by this skill's tests; run it in yours to prove it there.

## Files

- `SKILL.md`: the steps the agent follows.
- `scripts/rdfstore.py` and `scripts/test_rdf_store.py`: the tool and its tests.
- `references/`: the proof and the stores.
- `SOURCES.md`: every source, with its version and date.
