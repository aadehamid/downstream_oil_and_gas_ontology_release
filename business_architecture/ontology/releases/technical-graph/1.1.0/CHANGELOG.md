# technical-graph changelog

## 1.1.0 (2026-11-11)

A minor release. It adds what a technical graph built from a live platform needs: the data object on an earlier platform that a data object replaces, and the job or pipeline that builds a data object. It removes no term and deprecates none. Decided (delegated under KPI-DEC-0001): the owner's words there, "Decide anything inside the plan yourself and log it.", delegate the decisions inside the build's plan, and this release is one of them (`business_architecture/domain/kpi-store-decisions/KPI-DEC-0001.md`). The owner can reverse it.

- [minor] **`tg:replaces`**, from a data object to a data object. It names the data object on an earlier platform whose place the subject takes, such as the warehouse table a lakehouse table is migrated from. Why: no migration map exists outside the technical graph, so the graph records each pair as built. It takes any number of values, because one table can take the place of several.
- [minor] **`tg:builtBy`**, from a data object to a builder, with the classes **`tg:Builder`**, **`tg:Job`** and **`tg:Pipeline`**. Why each is needed: a live platform's lineage names the job or pipeline that wrote a table. `tg:producedBy` and `tg:PipelineStep` cannot carry that, because a pipeline step must have a place in the order of steps and a technical object has at most one, while a job has no such place and a table can have several writers. `tg:Job` and `tg:Pipeline` keep the one fact the platform gives beside the name, which of its two kinds the builder is.
- [minor] **No new term for an agent's bindings.** `tg:Agent` and `tg:binds` of 1.0.0 already cover an AI agent bound to data objects. The filters and expressions an agent holds are not modelled here: no question of this module asks for them.
- [minor] **Cardinality for five properties that 1.0.0 left without one:** `tg:readsFrom` and `tg:binds` take any number of values; `tg:detail` and `tg:tables` take at most one; the shape for `tg:rows` moved from the data object to the technical object, its domain, so it also covers a source database. The example graph already met each.
- [patch] The definition of `tg:TechnicalObject` lists a builder among its examples. Its meaning is the same.
- It answers two more competency questions, 56 (which data object on an earlier platform does this one replace) and 57 (which job or pipeline builds this data object), on the package plus the example graph, which gained made-up records for them.
- **Checks, before and after** (the ontology skill's release rule 30). `check_taxonomy.py` on the module alone: 3 findings on 1.0.0 and the same 3 on 1.1.0 (`tg:designedAs` states no range on purpose; the ranges of `tg:implements` and `tg:standsFor` are classes of kpi and system, which that run does not load). `check_cardinality.py`: 5 findings on 1.0.0, none on 1.1.0.
- It requires data-product 1.2.0, kpi 1.3.0 and system 1.5.0, as 1.0.0 did, and imports no module.

### Known gaps

- **Who answers for it (question 49)** finds no owner in the ontology today: the pricing data products record no producing process, and the two data products that do are produced by processes with no RACI assignment. Reason: the ontology holds no such link yet. Record: the decision of 2026-11-02.
- **No shape rejects a data object that replaces itself.** Reason: SHACL Core cannot compare a value with its focus node. Record: competency question 56's second query, which must return nothing, guards it.

## 1.0.0 (2026-11-02)

The module's first release, a major. Approved by the decision owner ("1. approve 1.0.0", saved in (the review comments of a subject matter expert reviewing the documents); the decision of 2026-11-02, amendment of 2026-11-02, later). It defines the kinds of thing a technical graph records about a data platform as built, and the links between them (the decision of 2026-11-02, item 2). Definitions only: the graph's nodes, row counts, refresh times and check results stay in the technical graph, never in the ontology.

- **12 classes:** `tg:TechnicalObject` and its kinds, from host and source database to table, view, metric view, definitions view, pipeline step, quality check, agent and orchestrator.
- **The check-result code list,** `tg:CheckResults`: pass, fail and differs.
- **22 properties,** 13 links and 9 values. Four reach other modules by IRI: `tg:designedAs` points a built thing to its design in data-product, `tg:layer` takes a value of data-product's layer code list, `tg:implements` names the kpi measure a metric view computes, and `tg:standsFor` names the system whose records a source database holds.
- **Its shapes,** checked with the data-product, kpi and system releases loaded.
- It answers competency questions 45 to 50, on the package plus the example graph in `technical-graph/example/`, which is test data and is not part of the package (the ontology skill's new-module rule 9).
- It requires data-product 1.2.0, kpi 1.3.0 and system 1.5.0, and imports no module.

### Known gaps

- **Who answers for it (question 49)** finds no owner in the ontology today: the pricing data products record no producing process, and the two data products that do are produced by processes with no RACI assignment.
- **The demo's technical graph keeps its own terms** until a later change moves it to this module's.
