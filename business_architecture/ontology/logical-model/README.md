# logical-model: logical data models and their links to the ontology

The `logical-model` module holds logical data models exported from ER Studio Data Architect, each as two views (the decision of 2026-11-02). The first view is ER Studio's export, kept byte for byte, with ER Studio's namespace (`https://www.erstudio.com/semanticmodel/`), classes, properties and shapes. The second is an annotation layer in the module's namespace, `https://w3id.org/mpc/ontology/modules/logical-model/`. It says which model each entity belongs to, which system its data comes from, which `party` concept, class or code list it describes, and which `data-product` table or data product builds it. Nothing is re-minted, and ER Studio's entities stay plain OWL classes.

It answers competency questions 51 to 55 (`../competency-questions.md`, section XII). The customer logical model, the first model, ships in this release (the decision of 2026-11-02, decision 2); its export and links file were read from a folder outside the repository (the release's `HOW-TO-UPDATE.md`, "Inputs from outside the repository"). The regression runs the questions on a made-up example model.

| File | What |
|---|---|
| `vocabulary.ttl` | The class `lm:LogicalModel` and four annotation properties: `lm:inModel`, `lm:sourceSystem`, `lm:describes` and `lm:implementedBy` |
| `shapes.ttl` | The shapes an annotation layer meets, checked with the model's export and the `party`, `system` and `data-product` releases loaded |
| `build_logical_model.py` | The builder: from an export and its links file it writes `<model>.erstudio.ttl` (the export, unchanged) and `<model>.layer.ttl` (the layer). `--verify` fails unless both equal a fresh build. Its docstring lists every check |
| `example/` | The made-up example: `example-export.ttl` in ER Studio's format, `example-links.csv`, and the two graphs the builder makes from them. `scripts/check.sh` verifies them. The example is test data and never joins a package |
| `test_logical_model.py` | Tests of the vocabulary, the builder, the example, questions 53 to 55, and a negative test for each shape |

## The links file

The layer's input is a CSV file kept beside the export, one row per entity; the build fails when an entity of the export has no row, so a new entity is drafted, even as doubtful, before it ships. For the customer model it is in `models/` (the release's `HOW-TO-UPDATE.md`, "Inputs from outside the repository", says where else it may live). Its columns are:

| Column | What |
|---|---|
| `model` | The model's slug, such as `customer-logical-model` |
| `erstudio_id` | ER Studio's `dcterms:identifier` of the entity |
| `source_system` | The IRI of the source system: a `sys:System` of the `system` module or a `party:CustomerSystem` of the `party` module. Most customer systems are only in `party`, which says which of them are the same as a `system` system (`skos:exactMatch`). `none` when neither module holds the entity's system, and the row's other links still count; an empty value fails the build |
| `describes` | The IRI of a `party` concept, class or code list (a lookup table that holds a whole code list describes the list), or empty |
| `implemented_by` | The IRI of a `data-product` platform table or data product, or empty |
| `status` | `asserted` or `doubtful`. Only `asserted` rows become triples. The builder prints `doubtful` rows, with their evidence, for the decision owner |
| `evidence` | Why the links hold, or why they are doubtful |

The layer is keyed on the model and ER Studio's identifier, because ER Studio builds an entity's IRI from its name. The builder finds the entity's current IRI at each build, so a renamed entity keeps its links. An entity is an `owl:Class` of the export with that identifier: entities and attributes share one number space, so an attribute can carry the same number as an entity. The build fails when a row names an identifier no entity has, which means an annotated entity has gone from the export. It also fails when a link target is not in the newest release of its module.

## ER Studio's ontology header

Every ER Studio export declares the same node, `https://www.erstudio.com/semanticmodel/Ontology`, with the model's title and creation time. The builder checks the header in each model's own graph and never compares it across models. It fails only if an export declares an ontology other than ER Studio's. Each model's export stays in its own file, so the builder never merges two headers. The header's creation time is copied onto the model's own individual, `lm:model/<slug>`, which also carries the model's title and slug. No query reads ER Studio's header; they find a model through `lm:inModel`. A store that loads two models into one graph merges their headers, so the stores keep each export in its own named graph ("In the stores", below).

The builder fails on any other IRI that two models of a build both define, including models already built into the same folder. ER Studio's shared vocabulary terms (`:Attribute`, `:PrimaryKey`, `:AlternateKey` and its annotation properties) are not collisions. Neither is a term that both models describe in the same way, such as a glossary scheme or term or a reused attribute; an entity is never exempt.

## ER Studio's own shapes

An export holds SHACL shapes of its own: one per key, with the key type, the entity it targets and a SPARQL check that the key is unique. They do not run as the module's shapes and do not join the whole-graph gate (`../validation/test_all_module_shapes.py`). In the gate they load as data only. The reasons:

- They constrain records of the model's entities, such as rows of a customer table. The ontology never holds records ("define, don't record"), so over the ontology they would check nothing.
- Their SPARQL uses ER Studio's prefix without declaring it (the shapes have no `sh:prefixes`), and its nested `SELECT` does not return `$this`. pySHACL refuses both once a record is there.

Question 53 reads the key shapes, so the builder checks their structure instead. Each must have a primary or alternate key type, target one entity of the export, and constrain only that entity's attributes.

## Business terms

ER Studio marks an attribute's link to a business glossary with `:businessTerm`, and sets `:externalTermLinkMissing` to true when it has none. The made-up example links one attribute to a glossary term so that question 54 has a term to find. The form of that link (an IRI of a `skos:Concept` in ER Studio's glossary scheme) is assumed: check how your export writes it before relying on question 54's first query. Question 54's second query lists the attributes with no `:businessTerm`, and reports the flag beside each one.

## In the stores

The newest releases hold this module, so the ontology stores hold it (the decision of 2026-11-02, amendment "the stores"). The projection loads the module's vocabulary into the local Neo4j like every package's, and `../projection/logical_models.py load` adds the models:

- Jena and the Delta table `epm_triples` hold each model's export and layer as named graphs of their own, `<version IRI>/<slug>.erstudio` and `<version IRI>/<slug>.layer`, found from the package's `manifest.json`.
- The Neo4j database the settings name holds each model in full as a subgraph labelled `LogicalModel`, apart from the ontology's `Resource` nodes: a `Model` node, each `Entity` with its name and description, its `Attribute` and `Key` nodes, `RELATES_TO` edges between entities, and `SOURCE_SYSTEM`, `DESCRIBES` and `IMPLEMENTED_BY` edges to the ontology nodes its layer names. The script's docstring lists every property.

The projection's round-trip checks read only `Resource` nodes, so they never read the subgraph. `../projection/sync_stores.py check` counts the named graphs with the release graphs and compares the subgraph with the package's graphs on an `lm:<store>` line, by a marker and a fingerprint of its content. The labels, node shapes and loader are a build choice delegated to the build's agent, under the subject matter expert's decision of 2026-10-12.

## Adding a logical model

A new logical model joins this module as another model; it does not become a new module (the decision of 2026-11-02, decision 3). Clean its export if it passed through email or a word processor, draft its links file, run the builder with a new slug, and resolve every `doubtful` row with the decision owner. The method is the `ontology` skill's `references/logical-model.md`. The guide, `../epm-ontology-guide.html`, explains the design in "Adding a logical model", with this module's made-up example. The walkthrough, `../epm-walkthrough.html`, gives the steps and commands in "Add a logical model". the decision of 2026-11-02 records the decision.

**Status:** released in this release as `logical-model 1.0.0`, with 1 logical model: `customer-logical-model`. Each model's export and links file are in `models/`, with the two graphs the builder made from them; `../releases/logical-model/` holds the package. The made-up example stays test data.
