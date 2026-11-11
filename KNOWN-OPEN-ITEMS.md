# Known open items

This page lists what is open in KPI Store 1.1 and what has not run yet. Each item is yours to close or to leave in your own copy. `HOW-TO-UPDATE.md` says how to change anything here.

## What has not run yet

- **Nothing in this release has run on Windows.** The checks and the tests of the store loads ran on macOS. `.github/workflows/check.yml` holds a Windows job that runs `scripts/check.sh` under Git Bash, and that job has not completed a run. The workflow lets the Windows job fail without failing the run, because some tests still assume POSIX file modes and symbolic links.
- **The first run on the client sandbox is still to do.** The owner does it from the zip, with the runbook.
- **The run on the owner's Windows machine is still to do.** It is the setup check, then the whole chain against the sandbox.
- **The notebook's load has not run in the client workspace.** The tests of the load run against a made-up workspace in `kpi_store/tests/support.py`, and the tests of the Delta table's round trip use a stand-in for the Spark session.

## Questions that wait for a person

- **Benchmark Prices has no measure of its own.** Whether it gets one, or stays part of crude prices, waits for the owner or the creator of the Genie space. `business_architecture/domain/kpi-store-decisions/KPI-DEC-0001.md` records the question.
- **The ontology's own open items** are in `business_architecture/ontology/OPEN-ITEMS.md`. That page lists the points only the business can settle, the gaps the process map still records, and the work that needs no one from the business.

## Limits of this release

- **Measure links from Genie are proposed, not loaded.** The report proposes a link from a business measure to a view measure and its filter, as a row of kind `measure-link` that does not block the load. Writing these links into the ontology needs a minor version of the `data-product` module, with a new property for the filter.
- **The quality part of question 6 stays empty.** Question 6 follows a KPI to its source systems and adds the quality result where one is recorded. Nothing in this release records a quality check, so the `quality` column is an empty list until something does.
- **Question 1's `replaces` link is not proven on a composite database that holds the loaded technical graph.** The four questions passed on a Neo4j Enterprise composite database with a made-up graph. The technical graph that the loader builds was read with the questions' names on a single database only.
- **The check of a Cypher block in a document is a token check.** It finds a string, a backtick name or a bracket that is never closed. It does not find a misspelt keyword or clauses in the wrong order. `scripts/DOC-SNIPPETS.md` says more.
- **The changelogs do not all meet the ontology skill's Known gaps convention.** The skill's `check_changelogs.py` requires a Known gaps section that says `None.` or gives a `Reason:` and a `Record:` value for each gap. Some packaged changelogs lack the section, and others list gaps without those fields. `scripts/check.sh` does not run this check. A released package never changes, so a later release of each module closes this.
- **No command runs on a schedule.** A store is checked and reloaded only when a person runs the commands of `HOW-TO-UPDATE.md`.
