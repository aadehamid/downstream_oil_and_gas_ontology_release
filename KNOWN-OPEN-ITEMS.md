# Known open items

This page lists what is open in KPI Store 1.1, what has not run yet and what was left for later. Each item is yours to close or to leave in your own copy. `HOW-TO-UPDATE.md` says how to change anything here.

## What has not run yet

- **On Windows, a test job ran the checks and the store loads, and nothing else.** `.github/workflows/check.yml` runs `scripts/check.sh` under Git Bash on Windows Server 2025, then the setup check, the Fuseki load, the local Neo4j load with its checks, the copy to a database named `businessprocessarchitecturegraph` on the same server, and the sync check for the three stores. All passed. The runner itself, every Databricks step, the technical graph's load, Neo4j Desktop, Excel and the installs of the runbook have not run on Windows. The runbook's section "What ran where" lists each point.
- **Seven tests of the `ontology` skill do not run on Windows.** Four need a file mode or a missing Git that Windows cannot set up. Three test how `build_docs.py` swaps the Widoco pages in and restores them; they use a shell script in place of Java. So that swap is not proven on Windows. No step of the runbook or of `HOW-TO-UPDATE.md` builds those pages.
- **The first run on the client sandbox is still to do.** The owner does it from the zip, with the runbook.
- **The run on the owner's Windows machine is still to do.** The owner runs the setup check and then the whole chain against the sandbox, from the zip and the runbook.

## What was rehearsed, and what was not

- **The loop was rehearsed on a made-up workspace only.** On a Databricks workspace with made-up tables, the load stopped on one row, a person cleared it, the cut tool wrote `1.2.1-correction.1`, the load ran, and a second run changed nothing. The sync check's Databricks part ran there too. The client's workspace is the first real one.
- **Three kinds of discovery were not rehearsed there.** The rehearsal had no Genie space, so it produced no measure-link rows. It read no builders from jobs and pipelines. Databricks had recorded no lineage for the rehearsal's own tables, so the table edges were not compared with their lineage. The lineage queries ran against the real lineage of another catalog instead.
- **The copy to Neo4j Enterprise was not tested on a server without plugins.** It was tested against a second database on a server that has the plugins. A test that pins the exact statements, and the server's query log, show that the copy uses no plugin. The client's Enterprise server is the first target without them.
- **Question 1's `replaces` link is not proven on a composite database that holds the loaded technical graph.** The four questions passed on a Neo4j Enterprise composite database with a made-up graph. The technical graph that the loader builds was read with the questions' names on a single database only.

## Questions that wait for a person

- **Benchmark Prices has no measure of its own.** Whether it gets one, or stays part of crude prices, waits for the owner or the creator of the Genie space. `business_architecture/domain/kpi-store-decisions/KPI-DEC-0001.md` records the question.
- **The ontology's own open items** are in `business_architecture/ontology/OPEN-ITEMS.md`. That page lists the points only the business can settle, the gaps the process map still records, and the work that needs no one from the business.

## Limits of this release

- **Measure links from Genie are proposed, not loaded.** The report proposes each link from a business measure to a view measure and its filter as a `measure-link` row, which does not block the load. Writing the links into the ontology waits for a minor version of the `data-product` module, with a new property for the filter.
- **The quality part of question 6 stays empty.** Nothing in this release records a quality check, so the `quality` column is an empty list until something does.
- **After a cut, `projection-report.json` describes the earlier build.** The file changes only when a fresh Neo4j load is recorded. Until then `scripts/check.sh` prints a note and still passes.
- **The stand-alone check finds known forms of outside references only.** `scripts/check_standalone.py` looks for a list of patterns, with 40 exact exceptions in `scripts/standalone-exceptions.txt`. It cannot find a reference written in a form the list does not hold.
- **The check of a Cypher block in a document is a token check.** It finds a string, a backtick name or a bracket that is never closed, and not a misspelt keyword or clauses in the wrong order. `scripts/DOC-SNIPPETS.md` says more.
- **The changelogs do not all meet the ontology skill's Known gaps convention.** The skill's `check_changelogs.py` fails on some packaged changelogs, and `scripts/check.sh` does not run it. A released package never changes, so this waits for a later release of each module.
- **No command runs on a schedule.** A store is checked and reloaded only when a person runs the commands of `HOW-TO-UPDATE.md`.
- **The two viewers show the release as cut, not your later changes.** `viewer/index.html` and `horoi_viewer/index.html` each carry a copy of the ontology data. The second page is built with Horoi 0.2.0. Both were opened and clicked through in a browser by `business_architecture/ontology/viewer/browser_check.py`, which `scripts/check.sh` does not run because it needs a browser. Rebuild both pages after a cut; `viewer/README.md` gives the two commands.
- **The copy to Enterprise judges a node by its marks, not by who wrote it.** A node that another writer made with every mark of a KPI Store node counts as the KPI Store's, and a replace deletes it. Use a database that no other writer fills with ontology nodes of this shape. The runbook's section "The limits" lists the marks.
- **A logical-model node of a model that this release no longer holds stops the copy.** It no longer counts as the KPI Store's, so a person removes it before the copy goes on.

## Gaps in the ontology's content

These were found by reading the release against the six stages of `best-practices/README.md`. None stops a load. A released package never changes, so each one waits for a new version of its module, made with the steps of `HOW-TO-UPDATE.md`.

- **87 terms have a label and no definition.** 81 are in `data-product` (for example the product lines `finance`, `hr` and `it`), 3 in `core`, 2 in `system` and 1 in `party`. Each definition must come from the business or from a source, so none was written for this release. Fix first: a patch release of `data-product`, then of the other three.
- **The taxonomy check does not run on the released modules.** `scripts/check.sh` runs the tests of `skills/ontology/scripts/check_taxonomy.py`, and never the script on a package. Run by hand with no options on the newest package of each module, it reports the 87 missing definitions and these other findings: text with no language tag (1,130 in `core`, 940 in `organization`, 275 in `kpi`, 110 in `market-data`, 91 in `party`, 65 in `data-product`, 13 in `value-stream`, 7 in `ref-mpc`), 56 notation findings in `core`, 23 domain or range findings across seven modules, 19 untyped terms in `integration` and `lane`, and 11 property-kind findings in `ref-mpc`. Some of these may be accepted with the script's options; no one has sorted them for this release. Fix second: sort the findings, release what needs a change, then add the script to `scripts/check.sh` so the gaps cannot return.
- **Only `core` states its rights.** `dcterms:rights` is in the `core` package and in no other. The owner decides what the statement says; it then goes into the next release of each module.
- **The thesaurus stage is thin.** Eight modules give terms an alternative label. No term has a `skos:related` link. Only `party` and `data-product` link to an outside vocabulary, and the release has no mapping file of its own. Add these when a reader or a tool needs them.
- **The build did not follow the six stages in every place.** The process hierarchy came before the definitions, and each package's metadata was written at release, after the ontology. `best-practices/README.md`, "Where the order differs", lists each place.

## Later, not in this release

- **A Databricks service principal for runs with no person.** The owner runs the loads now, with their own sign-in. The service principal waits for IT.
- **The n10s and APOC plugins on Neo4j Enterprise.** With them the load could run on Enterprise directly, and the copy from the local database would not be needed. This waits for IT.
- **The join from the customer logical model to the governance graph.** The governance graph does not hold the model yet.
- **Questions 8 and 11.** They ask which graph is right when the two disagree, and they were left out of this release.
- **A port to the source project.** The changes of this release have not been taken back to the project it was cut from.
