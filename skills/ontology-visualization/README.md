# Ontology visualization

This skill helps an agent build and maintain an ontology viewer in any domain.
It focuses on whether readers can understand terms, distinguish layers and
follow connections within and between modules. It covers both new viewers and
updates after ontology releases.

Ask the agent to use `ontology-visualization` with your source release and the
questions readers need to answer. The skill helps it choose views, preserve RDF
meaning, test the interface and prepare a delivery artifact. It supports offline
and hosted viewers without prescribing one renderer.

The method keeps ontology changes separate from presentation changes. A guide
or layout update can use the same ontology release without changing packages or
reloading stores. Publication follows the consuming project's authorization and
review requirements.

## Files

| Path | Reader | Purpose |
|---|---|---|
| `SKILL.md` | Agent | Entry point and routing for a new viewer or an update. |
| `references/playbook.md` | Agent and person | The method from reader tasks through construction, validation, delivery and later releases. |
| `assets/visualization-brief.md` | Agent and person | A project brief to record scope, source and acceptance evidence. |
| `agents/openai.yaml` | Skill host | Display metadata and a suggested invocation. |
| `SOURCES.md` | Person and maintainer | Sources, provenance, limitations and update instructions. |
| `evals/README.md` | Evaluator | Behavioral tasks and assessment criteria. |
| `evals/fixtures/v1/` | Evaluator | Neutral Catalog, Lending and Workflow inputs for the evaluation tasks. |
| `README.md` | Person | This overview. |

The evaluation tasks are examples to run against a candidate viewer. Their outcomes depend on the candidate and must be recorded when the tasks are run.
