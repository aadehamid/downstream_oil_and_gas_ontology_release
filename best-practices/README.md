# The order of the build, and why it makes sense

The KPI Store ontology was built in an order. This page reads that order as six stages. Each stage prepares the next one: a controlled vocabulary, metadata standards, a taxonomy, a thesaurus, an ontology and a knowledge graph. For each stage the page says what the stage is, why it comes at that point, and where this release holds it.

The order of the stages follows the one described in "The Ontology Pipeline: A Semantic Knowledge Management Framework", Jessica Talisman, *Intentional Arrangement* (a newsletter on Substack), 26 May 2025. The account of each stage below is this release's own, and each stage names the public standard it rests on.

The six stages are a way to read the build. They are not the method the build followed. The method is the `ontology` skill in `skills/ontology/`, which has gated steps, Step 0 to Step 12 (`skills/ontology/SKILL.md`). The order of the steps matches the order of the stages in most places. "Where the order differs" below lists the places where it does not.

| Stage | The skill's steps that do its work |
|---|---|
| 1. Controlled vocabulary | Step 0 (the sector's reference framework), Step 8 (which areas are in scope), Step 2 (one identity for each term) and the labels and definitions of Step 3 |
| 2. Metadata standards | Step 1 (the policies for IRIs, language, versions, licence and sources) and Step 10 (the release package) |
| 3. Taxonomy | The hierarchy of Step 3 |
| 4. Thesaurus | No step of its own. Aliases and scope notes are written in Step 3. Links to outside vocabularies are surveyed in Step 0 and recorded in Step 7 |
| 5. Ontology | The classes and properties of Step 3, then Steps 4, 5, 6 and 7, the shapes of Step 9 and the regression of Step 11. Step 1 locks the questions that Step 11 tests |
| 6. Knowledge graph | Step 10 (the released packages and their catalog) and Step 12 (the projection into a property graph) |

## What this folder holds

| File | What it holds |
|---|---|
| `README.md` | This page |
| [controlled-vocabulary.md](controlled-vocabulary.md) | A guide to the first stage: how to hunt the words, split them into meanings, and record a preferred label, a scope note, a stable ID, the aliases and the map of local keys for each. Its example is made up. |
| [controlled-vocabulary.html](controlled-vocabulary.html) | The same guide as a page for a browser |
| [controlled-vocabulary-end-to-end.png](controlled-vocabulary-end-to-end.png) | A diagram of the guide's four steps |

The folder has a guide for the first stage only. For the other five stages, the method is the `ontology` skill.

## Stage 1: controlled vocabulary

A controlled vocabulary is the list of the terms the business uses, with one meaning for each term. Each meaning gets one preferred label, a definition and an ID that does not change. The vocabulary does not arrange the terms or relate them to one another.

It comes first because every later stage is built from these terms. If two teams mean two things by "customer", a hierarchy built on that word puts unlike things under one parent, and a measure defined with it counts the wrong population. To correct the word later, a person must change every place that used it.

Where this release does it:

- The module files state each term in Turtle. A concept has a `skos:prefLabel`, and in most cases a `skos:definition` and a `skos:notation`. A class or a property has an `rdfs:label` and a `skos:definition`. The source files are in each module's folder under [`business_architecture/ontology/`](../business_architecture/ontology/), for example `party/code-lists.ttl`. The released copies are `business_architecture/ontology/releases/<module>/<version>/<module>.ttl`.
- The term's IRI is its ID. Step 2 of the skill requires that nothing identifies a term by its label.
- [`business_architecture/domain/business-glossary.md`](../business_architecture/domain/business-glossary.md) defines the terms the project's own documents use, such as "measure definition" and "reference fact", with the words to avoid for each. It is a short list. It does not repeat the terms in the modules.
- The shapes in `releases/core/2.4.0/shapes.ttl` require exactly one English preferred label on each process. [`business_architecture/ontology/validation/test_release_package_shapes.py`](../business_architecture/ontology/validation/test_release_package_shapes.py) runs every package's shapes, and `scripts/check.sh` runs that test.
- [controlled-vocabulary.md](controlled-vocabulary.md) describes the method for this stage, with a made-up example. It is not the record of how this release's terms were agreed.

The standard for this stage is ANSI/NISO Z39.19-2005 (R2010), *Guidelines for the Construction, Format, and Management of Monolingual Controlled Vocabularies*. The `ontology` skill checked its rules for labels, definitions and scope notes against that standard, rule by rule (`skills/ontology/references/quality.md`, "The vocabulary standards behind these rules"). The terms are written in SKOS (*SKOS Simple Knowledge Organization System Reference*, W3C Recommendation, 18 August 2009).

This stage has gaps. Not every term has a definition. `skills/ontology/scripts/check_taxonomy.py`, run by hand on the newest package of each module, reports 87 terms with no `skos:definition`: 81 in `data-product`, 3 in `core`, 2 in `system` and 1 in `party`.

## Stage 2: metadata standards

Metadata standards are the fixed set of facts recorded about each term and about each release: its title, its version, its date, its source and its licence. They are written with public vocabularies, so that another tool can read them without a private agreement.

It comes second because a term with no source and no version cannot be checked or corrected. Without this stage, a reader cannot tell which release a definition came from, what it was built on, or whether the file in hand is the released file.

Where this release does it:

- Each module file has an `owl:Ontology` header. In `releases/kpi/1.3.0/kpi.ttl` the header holds `dcterms:title`, `dcterms:description`, `dcterms:issued`, `dcterms:modified`, `dcterms:requires`, `owl:versionIRI` and `owl:versionInfo`.
- Each package has a `catalog.ttl`. It describes the release as a `dcat:Dataset` with a title, an issue date, a version and one `dcat:Distribution` for each file. [`business_architecture/ontology/releases/catalog.ttl`](../business_architecture/ontology/releases/catalog.ttl) is the combined catalog of all thirteen packages.
- Each package has a `manifest.json`. It names the module, the version, the decisions behind the release, the approval, and the SHA-256 of each file.
- Terms cite their sources with Dublin Core terms: `dcterms:source` and `dcterms:bibliographicCitation`.
- `scripts/check.sh` runs `build_module.py <module> --verify` for each module and `build_catalog.py --verify` for the combined catalog. Both are in `business_architecture/ontology/release/`.

The standards for this stage are *DCMI Metadata Terms* (Dublin Core Metadata Initiative, 2020-01-20) and *Data Catalog Vocabulary (DCAT) Version 3* (W3C Recommendation, 22 August 2024). The headers also use the version properties of OWL. Two things are thin. Only `core` carries a rights statement (`dcterms:rights`), in its header and in its catalog record. The other twelve packages carry none. PROV-O appears in `data-product` and in the shapes of `technical-graph`, where it describes how one data object derives from another. No package uses PROV-O (*PROV-O: The PROV Ontology*, W3C Recommendation, 30 April 2013) to describe its own release.

## Stage 3: taxonomy

A taxonomy arranges the terms of one kind into a hierarchy, from the general to the specific. Each term has one parent, so each term has one path to the top.

It comes after the vocabulary and the metadata because a hierarchy needs clean terms to arrange. With two names for one meaning, the same thing sits in two branches. With no definitions, nobody can say whether a term belongs under its parent, and the tree grows by habit until it is too large to check.

Where this release does it:

- The `core` module holds the process hierarchy. Each process is a `skos:Concept` in one concept scheme, and `skos:broader` names its parent. The hierarchy comes from `business_architecture/business_process/downstream_process_map.json`.
- The other modules hold code lists as concept schemes. Most are flat lists. `data-product` and `party` have short hierarchies.
- A shape in `releases/core/2.4.0/shapes.ttl` allows at most one `skos:broader` on a process, and the parent must be a concept. A shape in `data-product` requires exactly one segment above each product line.
- Two competency questions test the tree. `business_architecture/ontology/regression/queries/q02a-no-parent.rq` must find no process without a parent, except the top ones. `q01b-path-to-root.rq` must find no process without a path to the top. `regression/run.py` runs them, and `scripts/check.sh` runs `run.py`.
- `skills/ontology/scripts/check_taxonomy.py` checks one parent for each concept and no cycles. `scripts/check.sh` runs that script's tests. It does not run the script on the released modules. Run by hand on the newest package of each module, its parent check reports nothing. Its other checks report findings, most of them text with no language tag.

The standard for this stage is again ANSI/NISO Z39.19-2005 (R2010), which gives the rules for a hierarchy and the test for a parent. The skill's rule of one parent for each concept is stricter than the standard, which allows more than one, and `quality.md` records that difference. The hierarchy is written with `skos:broader` of SKOS.

## Stage 4: thesaurus

A thesaurus adds two kinds of relation to the hierarchy. The first says that two words mean the same thing: an alias, or a match to a term in another vocabulary. The second says that two terms are related although neither is the parent of the other.

It comes after the taxonomy because these relations hold between terms that already have a place. An alias needs a preferred term to point to. If this stage is skipped, a person who searches with their own word finds nothing, and a term cannot be compared with the same term in a public vocabulary.

Where this release does it:

- Aliases are `skos:altLabel`. Eight modules have them, and `core` has the most. Scope notes are `skos:scopeNote`.
- Matches to outside vocabularies are in two modules. `party` has `skos:closeMatch` and `skos:broadMatch` links to the Open Energy Ontology, FOAF and the W3C Organization Ontology. `data-product` has one `skos:closeMatch`, to `dcat:Dataset`. The `skos:exactMatch` links in `party` point to the `system` module of this release, not outside it.
- The skill records a set of mappings as an SSSOM file, and `skills/ontology/scripts/check_sssom.py` checks one. `scripts/check.sh` runs it on the skill's template, `skills/ontology/templates/mappings.sssom.tsv`.

The standards for this stage are ISO 25964-1:2011, *Thesauri for information retrieval*, and ISO 25964-2:2013, *Interoperability with other vocabularies*. The skill names them as the international counterparts of ANSI/NISO Z39.19-2005 (R2010). It did not read their text, and no rule of the skill claims to follow their clauses (`skills/ontology/SOURCES.md`). The aliases and the matches are written with the label and mapping properties of SKOS.

This is the thinnest stage. The release has no `skos:related` link. It states a relation between two terms as a typed property, such as `core:informedBy`, which belongs to stage 5. It has no SSSOM file of its own: its matches are triples in the two modules. The outside matches are few, and eleven modules have none.

## Stage 5: ontology

An ontology says what kinds of things exist and how they relate. It adds classes, properties with a domain and a range, and rules that data must meet. A taxonomy can say that one process sits under another. An ontology can say that a measure informs a process, and that every measure must have a kind.

It comes after the first four stages because a class or a property is a commitment about terms that must already be clear. If the vocabulary is unsettled, the rules are written against words that will change, and each change breaks the rules that used them.

Where this release does it:

- Thirteen modules hold the classes and properties. [`business_architecture/ontology/MODULES.md`](../business_architecture/ontology/MODULES.md) lists the modules, what each holds and how they link.
- Each package has a `shapes.ttl` with its SHACL shapes. `validation/test_release_package_shapes.py` checks each package against its own shapes. `validation/test_all_module_shapes.py` runs all the shapes together over the whole graph. `scripts/check.sh` runs both.
- The competency questions are the acceptance test. [`business_architecture/ontology/competency-questions.md`](../business_architecture/ontology/competency-questions.md) lists the 57 questions. `business_architecture/ontology/regression/` holds their queries, and `expected.csv` gives each question its status: 56 are answerable and 1 is parked.

The standards for this stage are OWL 2 (*OWL 2 Web Ontology Language Document Overview (Second Edition)*, W3C Recommendation, 11 December 2012) for the classes and properties, and SHACL (*Shapes Constraint Language (SHACL)*, W3C Recommendation, 20 July 2017) for the rules.

## Stage 6: knowledge graph

A knowledge graph is the first five stages put together and loaded where people and programs can query them. It holds the terms, their hierarchy, their links and the facts stated with them, as one graph.

It comes last because it only assembles what the earlier stages made. A graph loaded from an unsettled vocabulary or an unchecked ontology gives answers that nobody can trace, and the store does not show the fault.

Where this release does it:

- The released packages under `business_architecture/ontology/releases/` are the master copy of the graph.
- The release loads three stores: the Delta table `epm_triples` in Databricks, one Apache Jena Fuseki dataset with a named graph for each release file, and a property graph in Neo4j. The top [`README.md`](../README.md) describes them. [`business_architecture/ontology/projection/ontology-stores-runbook.md`](../business_architecture/ontology/projection/ontology-stores-runbook.md) gives the steps, and the code is in `kpi_store/`.
- Each load checks that the store holds the release. Databricks and Fuseki compare hashes. Neo4j runs the shapes in the graph and reads the graph back as triples.
- Two pages show the graph in a browser, offline: [`viewer/index.html`](../viewer/index.html) and [`horoi_viewer/index.html`](../horoi_viewer/index.html).

The standards for this stage are RDF (*RDF 1.1 Concepts and Abstract Syntax*, W3C Recommendation, 25 February 2014) for the graph and SPARQL (*SPARQL 1.1 Query Language*, W3C Recommendation, 21 March 2013) for the questions asked of it. The packages are RDF, the competency questions are SPARQL queries, and Fuseki answers SPARQL. The Neo4j graph is a property graph, which is not RDF, and it is queried in Cypher.

The ontology holds definitions and reference facts. It does not hold records such as customers, invoices or measure values, which stay in the business systems. So this is a graph of what the business's terms mean, with no business records in it.

## Where the order differs

The build's order matches the six stages in most places. It differs in these:

- **The hierarchy came before the definitions.** The build started from a process map that already had a tree. The skill's Step 3 turned the tree into a SKOS taxonomy first, and the definitions were written and reviewed afterwards, in batches. In the six stages, the definitions of stage 1 come before the tree of stage 3.
- **The questions came before the vocabulary.** Step 1 locks the competency questions before any modelling. They test stage 5, and they were written before stage 1 was complete. The skill does this so that the questions decide what the ontology must hold.
- **The release metadata came late.** The policies of stage 2 were set at Step 1. The package, its catalog and its manifest were written at Step 10, after the ontology.
- **Taxonomy and classes share a step.** Step 3 builds the hierarchy and the first classes and properties together. The six stages put them two stages apart.
- **The thesaurus has no step.** Its parts were written in Steps 0, 3 and 7, and it is the thinnest stage, as "Stage 4" above says.

## The six stages in one table

| Stage | What it adds | The standard it rests on | Where it is in this release |
|---|---|---|---|
| 1. Controlled vocabulary | One meaning for each term, with a preferred label, a definition and a stable ID | ANSI/NISO Z39.19-2005 (R2010); SKOS | `skos:prefLabel` and `skos:definition` in each module's Turtle; `business_architecture/domain/business-glossary.md`; the guide in this folder |
| 2. Metadata standards | A title, a version, a date and a source for each release and each term, in public vocabularies | DCMI Metadata Terms; DCAT Version 3 | Each package's Turtle header, `catalog.ttl` and `manifest.json`; `releases/catalog.ttl` |
| 3. Taxonomy | A hierarchy with one parent for each term | ANSI/NISO Z39.19-2005 (R2010); SKOS | `skos:broader` in `core`; the concept schemes of the other modules; the shape in `core`'s `shapes.ttl`; competency questions 1 and 2 |
| 4. Thesaurus | Aliases, matches to other vocabularies and related terms | ISO 25964-1:2011 and ISO 25964-2:2013; SKOS | `skos:altLabel` and `skos:scopeNote`; the matches in `party` and `data-product`; no `skos:related` |
| 5. Ontology | Classes, properties and rules | OWL 2; SHACL | The thirteen modules in `MODULES.md`; each package's `shapes.ttl`; the 57 competency questions and their regression |
| 6. Knowledge graph | All of it together, loaded and queried | RDF 1.1; SPARQL 1.1 | The released packages; `epm_triples` in Databricks, the Fuseki dataset and the Neo4j graph; `viewer/` and `horoi_viewer/` |
