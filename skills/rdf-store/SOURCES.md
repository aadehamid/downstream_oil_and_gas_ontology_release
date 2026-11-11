# Sources

This file lists every source the rdf-store skill draws on: what the skill took from each, the version or date used, and how to check for a newer one. Agents do not read it. All text in the skill is our own wording.

Last full review: 2026-10-24; sections 4 and 5 updated 2026-11-11. Check the sources below every three months, and whenever pyoxigraph, Jena Fuseki or a W3C specification below publishes a new version.

## 1. The owner's decision to split the skill

- **What it is:** the owner's instruction of 2026-10-24: "I like the idea of splitting it from the projection skill", answering "should we have a skill that loads .ttl files to any typical triple store, using Jena as default. The skill should alos be able to load .ttl to databrick in a way that there is no loss of data and we go from Databrick to .ttl and back without losing data."
- **What the skill took:** its scope (any SPARQL 1.1 store with Jena as the default, and Databricks), the round trip as the test, and the plain Delta triple table the owner chose over OntoBricks for the lossless store.

## 2. W3C specifications

| Source | Version and date | Used in | What the skill took |
|---|---|---|---|
| RDF Dataset Canonicalization (RDFC-1.0), https://www.w3.org/TR/rdf-canon/ | W3C Recommendation, 21 May 2024; read 2026-10-24 | `references/no-loss.md`; `rdfstore.py` | The canonical form of a dataset, blank nodes included, as the no-loss proof; the canonical N-Quads form of each quad, sorted, as the text that is hashed. |
| RDF 1.1 N-Quads, https://www.w3.org/TR/n-quads/ | W3C Recommendation, 25 February 2014; read 2026-10-24 | `references/no-loss.md`, `stores.md` | N-Quads as the exchange format, since its fourth term carries the graph; the Delta table's columns. RDF 1.2 N-Quads (https://www.w3.org/TR/rdf12-n-quads/) is a Working Draft of 23 October 2026; its triple terms and directional literals are not stored. |
| SPARQL 1.1 Graph Store HTTP Protocol, https://www.w3.org/TR/sparql11-http-rdf-update/ | W3C Recommendation, 21 March 2013; read 2026-10-24 | `references/stores.md`; `FusekiStore` | PUT, GET and DELETE of a named graph with indirect identification (`?graph=<IRI>`), and `?default` for the default graph. |
| SPARQL 1.1 Update, https://www.w3.org/TR/sparql11-update/ | W3C Recommendation, 21 March 2013; read 2026-10-25 | `references/stores.md`; `FusekiStore.publish` | One update request for the whole dataset, because "Each request SHOULD be treated atomically by a SPARQL 1.1 Update service" (quoted). |
| RDF 1.1 Concepts and Abstract Syntax, section 3.5, https://www.w3.org/TR/rdf11-concepts/#section-skolemization | W3C Recommendation, 25 February 2014; read 2026-10-24 | `references/no-loss.md`; `skolemize` | Skolem IRIs under `/.well-known/genid/`. |

## 3. pyoxigraph

- **What it is:** Python bindings of Oxigraph, an RDF library and store in Rust. https://pypi.org/project/pyoxigraph/
- **Version used:** 0.5.13, published to PyPI 2026-10-22; read 2026-10-24.
- **What the skill took:** parsing and writing Turtle, N-Triples and N-Quads, and `Dataset.canonicalize(CanonicalizationAlgorithm.RDFC_1_0)`. Chosen because it is maintained (a release two days before), implements RDFC-1.0 by name, and is one wheel with no system dependencies. On 2026-10-24 its output matched the W3C test suite's expected results (https://w3c.github.io/rdf-canon/tests/) for rdfc10 tests 002 (no blank nodes), 016, 017 and 044 (blank nodes); test 001 is an empty dataset. The three blank-node cases are pinned byte for byte in `scripts/testdata/rdfc10-cases.json` and run in the tests. rdflib 7.6.0's `to_canonical_graph` is not RDFC-1.0; PyLD 3.3.0 implements the older URDNA2015 for JSON-LD.
- **How to check for updates:** `curl -s https://pypi.org/pypi/pyoxigraph/json | python3 -c 'import json,sys; print(json.load(sys.stdin)["info"]["version"])'`.

## 4. Apache Jena Fuseki

- **What it is:** Jena's SPARQL server, as the plain Apache download: one jar, `jena-fuseki-server-6.2.0.jar`, from Maven Central (https://repo1.maven.org/maven2/org/apache/jena/jena-fuseki-server/6.2.0/), started with Java.
- **Version used:** 6.2.0; run 2026-11-11 on Java 21.0.2 with `java -jar jena-fuseki-server-6.2.0.jar --mem --update --localhost --port <port> /ds`.
- **The pin:** SHA-256 `2c92c598e65ab69d99820052e05f4277ed1d77980a8845f87545ad35b71a76ee`, computed 2026-10-23 from the jar whose SHA-1 matched Maven Central's, and again on 2026-11-11 from the jar that run used. `references/stores.md` gives the check; a test holds the two documents to this value.
- **What the skill took:** the default store, with an in-memory dataset `/ds` and its `/data`, `/query` and `/update` endpoints.
- **How to check for updates:** `curl -s https://repo1.maven.org/maven2/org/apache/jena/jena-fuseki-server/maven-metadata.xml | grep release`.

## 5. Spark SQL and Delta on Databricks

- **What it is:** the Spark session a Databricks notebook already has (`spark`), and Delta tables in Unity Catalog.
- **Version used:** none run by this skill's tests, which use a stand-in session that decodes the statements `SparkStore` sends. Run the round trip in your own workspace to prove it there; its result is the proof for that workspace.
- **What the skill took:** `spark.sql(<statement>)` and `.collect()` on its result, the only two calls `SparkStore` makes; `CREATE OR REPLACE TABLE ... USING DELTA`; `CREATE OR REPLACE TABLE ... AS SELECT` as the one replace; `FROM VALUES` with `unbase64` and `decode` to keep data text out of the SQL.
- **How to check for updates:** the Databricks SQL language reference for `unbase64`, `decode` and `CREATE TABLE`.
