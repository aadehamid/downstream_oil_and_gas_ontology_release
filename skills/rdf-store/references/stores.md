# Stores

## Jena Fuseki, and any Graph Store Protocol store

Jena Fuseki is the default store. Use the plain Apache download, one jar, started with Java:

1. Download `jena-fuseki-server-6.2.0.jar` from `https://repo1.maven.org/maven2/org/apache/jena/jena-fuseki-server/6.2.0/`.
2. Check its SHA-256. It must be `2c92c598e65ab69d99820052e05f4277ed1d77980a8845f87545ad35b71a76ee`. On Windows run `certutil -hashfile jena-fuseki-server-6.2.0.jar SHA256`; on macOS or Linux run `shasum -a 256 jena-fuseki-server-6.2.0.jar`.
3. Start it: `java -jar jena-fuseki-server-6.2.0.jar --mem --update --localhost --port 3030 /ds`. Leave the window open; Ctrl+C stops the server.

`--mem` keeps the dataset `/ds` in memory, `--update` allows writes, and `--localhost` accepts requests from this machine only. The server answers `http://127.0.0.1:3030/$/ping` when it is up. The endpoints:

- Graph Store Protocol: `http://127.0.0.1:<port>/ds/data`
- SPARQL query: `http://127.0.0.1:<port>/ds/query`
- SPARQL update: `http://127.0.0.1:<port>/ds/update`

`roundtrip --store fuseki --gsp <data URL> --query <query URL> --update <update URL>` works with any store that implements the SPARQL 1.1 Graph Store HTTP Protocol (indirect graph identification, `?graph=<IRI>`), the SPARQL 1.1 Protocol and SPARQL 1.1 Update.

- **Publishing.** With `--update`, the whole dataset goes in one SPARQL Update request (`DROP SILENT GRAPH` then `INSERT DATA` per graph). SPARQL 1.1 Update says "Each request SHOULD be treated atomically": a SHOULD, not a guarantee. A store that applies it that way leaves itself as it was when the request fails; one that does not can be left with some graphs dropped. Without `--update`, each graph is replaced by its own HTTP PUT, and a failure part way leaves some graphs new and some old. Either failure stops the run with exit 1, never a pass; reload the store before you trust it. This skill has not tested a failure part way through a live Fuseki update.
- **Blank nodes stay in one graph.** Each graph travels as its own document, so a blank node that occurs in two graphs cannot survive the trip; the run refuses such a dataset (exit 2) before any request. Skolemize it, or keep each blank node in one graph.
- **Exporting.** The script lists the store's named graphs with a SPARQL query, reads each back with HTTP GET as N-Triples, and reads the default graph with `?default`. Each graph is a separate document, so its blank nodes are standardized apart from every other graph's.

An in-memory dataset starts empty on every restart, which makes "nothing you have not loaded" (SKILL.md, step 3) a restart away.

## Databricks: a Delta triple table

Spark is the only Databricks path. A Databricks notebook already has a Spark session, `spark`, so the load needs no host name, no warehouse and no credential. There is no command for it, because there is no Spark outside the notebook. The notebook imports `rdfstore.py` and calls it:

```python skip reason="needs-client-server: needs a Spark session in a Databricks workspace"
import rdfstore as rs
dataset = rs.pack(files)                      # one named graph per file
store = rs.SparkStore(spark, "<catalog>.<schema>.<table>")
passed, report = rs.roundtrip(store, dataset)
```

`SparkStore` calls one method of the session, `spark.sql(<statement>)`, and reads rows with `.collect()` on its result. The schema must exist. The table name is one to three parts of letters, digits and `_`; any other name is refused before a statement runs. The run touches two tables: `<table>` and a staging table of its own, `<table>__staging_<random>`, so two runs on one table never verify or promote each other's rows.

- **Staging, then one replace.** The rows go into the run's staging table, which `roundtrip` exports and compares first. Only a staging copy with the same hash replaces `<table>`, in one `CREATE OR REPLACE TABLE <table> AS SELECT * FROM <staging>`, a single Delta transaction. The staging table is dropped whatever happens. The live table is then read back and compared again, since that is what consumers see. When two runs target one table, the last to replace it wins. A failure or a mismatch before the replace leaves the previous `<table>` as it was (the report says `"published": false`).
- **Unsupported terms are refused first.** RDF 1.2 triple terms and literals with a base direction raise `BadInput` before any statement runs.
- **Reading it back.** `store.export()` returns the live table as a dataset. `rs.dataset_hash(dataset)` gives its RDFC-1.0 hash, and `rs.nquads_text(dataset)` its sorted N-Quads.

The table is N-Quads as columns:

| Column | Holds |
|---|---|
| `subject` | an IRI, or `_:label` for a blank node (an IRI always has a scheme, which cannot start with `_`) |
| `predicate` | an IRI |
| `object` | the IRI, `_:label` for a blank node, or the literal's lexical form |
| `object_kind` | `iri`, `bnode` or `literal`: the same text can be any of the three, so the kind has its own column |
| `datatype` | a literal's datatype IRI; NULL for a language-tagged literal and for an IRI or blank node |
| `lang` | a literal's language tag, else NULL |
| `graph` | the named graph's IRI; NULL for the default graph |

Every value travels base64-encoded inside the INSERT and is decoded in SQL (`decode(unbase64(...), 'UTF-8')`), so no text from the data is ever read as SQL, whatever quotes or backslashes it holds. Rows go in batches of 2,000 per statement.

The table is a store, not a reasoner or a SPARQL endpoint: query it with SQL, or export it from the notebook to rebuild a triple store or a property graph.
