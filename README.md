# KPI Store 1.1

KPI Store 1.1 is a business ontology for downstream oil and gas, with the code that loads it into one data platform and checks each load. The platform is Databricks, then Apache Jena Fuseki on Windows, then Neo4j Enterprise. Everything here can be rebuilt and checked from this folder alone.

To see the ontology first, open [the ontology viewer](viewer/index.html) in a browser. It shows this release as received, works offline and needs no setup. [The viewer's instructions](viewer/README.md) say how to use it.

To ask for a new KPI, start in [`kpi-intake/`](kpi-intake/README.md). It holds the form a business analyst fills in with the business, as a page and as an Excel workbook, and the check that says whether a filled form is complete.

## What KPI Store does

KPI Store loads the released ontology packages of this folder into three stores. The packages are the master copy, and each store holds a copy of them.

| Store | What it holds | How it is loaded |
|---|---|---|
| Databricks | The Delta table `epm_triples`, and the marker table `epm_store_markers`, which says which release the table holds | A notebook on serverless compute, with the notebook's own session |
| Apache Jena Fuseki | One dataset, with one named graph for each release file | A command on Windows, with Java and the plain Apache jar |
| Neo4j | A property graph in a local database that has the n10s and APOC plugins, and a copy of it in one database on Neo4j Enterprise | One command on Windows loads and checks the local database. A second command copies the checked graph to Enterprise, which needs no plugin |

Before the Databricks load, the notebook compares the ontology with the workspace. It reads the tables, columns, metric views, lineage and Genie spaces that the workspace reports. When an object, a column or a table edge that the ontology names is missing or renamed in Databricks, the load stops. The notebook then writes a report, `discovery-report.json`, with the same rows in `discovery-report.csv`. A person clears the report by writing a decision on each row that blocks. The cut tool turns the cleared report into a correction version of the ontology, such as `1.2.1-correction.1`.

The notebook loads the zip in the volume, so a correction reaches Databricks only in a new zip. After you clear the report, run the same runner command again. Its `cut` step runs the cut tool. Its `zip` step builds a new zip from the corrected folder and writes the zip's checksum into a copy of the settings. Its `upload` step copies both to the volume, and its `notebook` step loads that zip. A cut that you run by hand with `py -m kpi_store.cut` changes this folder only. Run the runner's `zip` and `upload` steps afterwards, or the notebook still reads the earlier zip.

Each load proves that the store holds the release. Databricks and Fuseki compare a hash of what the store holds with a hash of the release files. Neo4j runs the validation shapes in the graph and reads the graph back as triples, which must equal the triples that went in.

The notebook writes to two schemas only, and the code refuses any other write. The settings file names both, with the catalogs the notebook may read:

```toml excerpt=kpi_store/kpi_store.example.toml
[databricks]
write_catalog = "idp_sbx"
write_schema = "kpi_store"         # epm_triples and epm_store_markers live here
tech_graph_schema = "tech_graph"
volume = "releases"                # the volume <write_catalog>.<write_schema>.<volume>
read_catalogs = ["idp_sbx", "synapse_dev"]
```

Beside those catalogs the notebook reads three system schemas: `system.information_schema`, `system.access` and `system.lakeflow`. No command here needs a token. The notebook uses its own session, and the commands on Windows use the sign-in of the Databricks command line.

## The two step-by-step guides

Follow a guide for every run. This page gives no steps.

- For the first run, follow the runbook, [`business_architecture/ontology/projection/ontology-stores-runbook.md`](business_architecture/ontology/projection/ontology-stores-runbook.md). It goes from the zip to three stores that are loaded and checked.
- For every later update, follow [`HOW-TO-UPDATE.md`](HOW-TO-UPDATE.md). It also says how to add a module.

## What is in this folder

| Path | What it holds |
|---|---|
| `kpi_store/` | The code that reads the workspace, compares it with the ontology, writes the report and loads the stores. `kpi_store/kpi_store.example.toml` is the settings example, and `kpi_store/notebook/kpi_store_load.py` is the Databricks notebook |
| `kpi_store/questions/` | Four questions that join the KPI Store graph to a governance graph in one Neo4j composite database, as query templates |
| `business_architecture/ontology/` | The ontology: each module's sources and builder, the released packages (`releases/`), the projection into Neo4j (`projection/`), the competency questions and their regression, the validation shapes and the documents |
| `business_architecture/business_process/` | The process authority: the downstream process map, the two value streams, the office lanes and the data-product portfolio, as JSON, with their tests. Their schemas are in `business_architecture/schema/` |
| `business_architecture/reference/` | The evidence behind the definitions: MPC's public filings, the industry view, the APQC framework and vendor descriptions |
| `business_architecture/domain/` | The business glossary, the data domains, the problem statement, the decision packages and this release's decision records (`kpi-store-decisions/`) |
| `skills/` | Five agent skills: `ontology` (the method), `ontology-to-lpg` (the projection into a property graph), `rdf-store` (triple stores), `ontology-visualization` (the viewer playbook) and `clear-writing` |
| `viewer/` and `horoi_viewer/` | Two pages that show the ontology in a browser, offline |
| `kpi-intake/` | The KPI intake pack: the form for one new KPI as a page and as a workbook, its guide, two filled examples, and the question catalogue the forms are built from. `kpi_store/intake/` holds its code |
| `best-practices/` | The order of the build, read as six stages from a controlled vocabulary to a knowledge graph, with the reason for the order. Also a guide to the first stage, the controlled vocabulary, with a made-up example |
| `scripts/` | `check.sh`, the one command that proves your copy is valid, and the tools it runs. `DOC-SNIPPETS.md` says how the code blocks in the documents are tested |
| `HOW-TO-UPDATE.md` | The guide for every update after the first run |
| `KNOWN-OPEN-ITEMS.md` | What is open, and what has not run yet |
| `release.json` | The release's name and build date, and the files the logical models were built from |

To understand the ontology, open `business_architecture/ontology/epm-ontology-guide.html` in a browser. It explains what the ontology is for, why it is split into modules and what each module holds. `business_architecture/ontology/epm-walkthrough.html` is the longer account of how the ontology was built.

## Before you run anything

The loads run on a Windows machine. Set these up once. The runbook gives the steps, and the setup check tests each item and prints the fix for any that fails.

| What you need | Why |
|---|---|
| Python 3.11 or later, with the `py` launcher | The KPI Store commands are Python modules, and the documents start them with `py`. The check is a bash script, and the sign-in is the Databricks command line; both have their own rows below |
| Java 21 | Fuseki 6.2.0 and ROBOT, the reasoner, run on Java. This release was tested with Java 21 |
| Git for Windows, for Git Bash, and [uv](https://docs.astral.sh/uv/) | The full check, `scripts/check.sh`, is a bash script. It runs each check through uv, which fetches the test packages. The script takes the first of `python3`, `python` and `py` that is Python 3.11 or later. Run it from Git Bash or through the runner: in PowerShell, the plain word `bash` starts the launcher of the Linux subsystem |
| The Databricks command line, signed in with OAuth (`databricks auth login`) | The commands on Windows upload the release and start the notebook with this sign-in |
| `jena-fuseki-server-6.2.0.jar` | The Fuseki server. `skills/rdf-store/references/stores.md` gives the download address and the SHA-256 |
| `robot.jar`, ROBOT 1.9.10 | The reasoner that runs before the Neo4j load. `skills/ontology-to-lpg/references/running.md` gives the download address and the SHA-256 |
| Neo4j Desktop, with a Neo4j 2025.06.2 database that has the APOC and n10s plugins | The local database, where the graph is loaded and checked |
| The name of the database on Neo4j Enterprise, your user name and your password | The copy writes to this one database |

Two settings files stay outside this folder. `kpi_store.toml` names the Databricks catalogs, the schemas and the skip rules of one environment. It goes in the Databricks volume beside the release zip, never inside the zip. The local settings file names the stores and tools on your machine, and it holds the Neo4j passwords. Keep it in a folder outside this one. Nothing in this folder holds a login.

## The commands

The runbook says when to run each command and what it prints. This table says only what each command is for.

| Command | What it does |
|---|---|
| `py -m kpi_store.setup_check` | Checks the one-time setup of the machine and prints the fix for each failure |
| `py -m kpi_store.runner` | Runs the whole chain, from a cleared report to the sync check |
| `py -m kpi_store.runner --reset` | Empties the four stores after it shows what it will delete and you type `reset`, so the next run loads them again from nothing |
| `py -m kpi_store.cut` | Turns a cleared report into a correction version of the ontology |
| `py -m kpi_store.load_fuseki` | Loads the release into the local Fuseki and proves by a hash that the store holds exactly the release |
| `py -m kpi_store.load_neo4j` | Empties the local Neo4j database, loads the release into it and runs every check there |
| `py -m kpi_store.copy_enterprise` | Copies the checked graph from the local Neo4j to the one named database on Neo4j Enterprise, and checks the copy |
| `py -m kpi_store.sync_check` | Says whether each store holds the release in this folder: current, or behind |
| `py -m kpi_store.questions.run ask <question> --settings <file> --mapping <file> --out <folder>` | Asks one of the four cross-graph questions (`q1`, `q4`, `q6`, `q7`) and writes its rows. The other subcommands are `discover`, `confirm` and `check`, which make and check the mapping file that `ask` needs. `py -m kpi_store.questions.run --help` lists them |
| `py -m kpi_store.intake check <file>` | Says what a filled KPI intake form still lacks. `py -m kpi_store.intake build` rebuilds the forms from the catalogue and the release packages. `py -m kpi_store.intake folders <place>` makes the shared folder a team keeps its answers files in |
| `bash scripts/check.sh` | Proves that this copy of the release is valid |

## Run the checks

`scripts/check.sh` is the one check of the release. It verifies that every released package equals a fresh build from its sources. It also runs the competency-question regression, every test file, the code blocks of the documents and the check that nothing here refers to anything outside this folder. Run it in Git Bash, from this folder. It takes several minutes and ends with "all checks passed".

```bash run=slow
bash scripts/check.sh
```

```text expect
...
all checks passed
```

The check passes in a Git copy and in a plain folder, such as the unpacked zip. `bash scripts/check-pinned.sh` is separate and optional. It asks whether your copy still equals this release as shipped. After your first change some of its tests fail. That says only that your copy differs from the release as shipped.

Two quick commands show what the release holds. Both need the rdflib package (`py -m pip install rdflib`). The first lists the released modules, each with its version, the modules it requires and its number of triples. In a plain folder the first line says that the commit is unknown.

```powershell run=release-copy
py scripts/epm_facts.py modules
```

```text expect
commit <the commit>: 13 released modules
...
```

The second asks the ontology one competency question. `py ask.py` with no name lists the questions, and `business_architecture/ontology/competency-questions.md` explains them.

```powershell run=release-copy
cd business_architecture/ontology/regression
py ask.py q36-the-crack
```

```text expect
Q36 If an assistant asks for "the crack", which measure is official, and which nearby ones are not it?
...
```

## The logical models

The `logical-model` module holds logical data models exported from ER Studio Data Architect. Each model's export and links file are in `business_architecture/ontology/logical-model/models/`, beside the two graphs built from them. `<model>.erstudio.ttl` is ER Studio's export in ER Studio's own namespace, `https://www.erstudio.com/semanticmodel/`. `<model>.layer.ttl` holds the annotations that link the model's entities to the `party`, `system` and `data-product` modules. `release.json` and the package's `manifest.json` list the files the models were built from under `augment`, each with its SHA-256. The made-up model in `logical-model/example/` is test data. `HOW-TO-UPDATE.md` says how to add a model.

## Names, namespaces and terms

- "KPI Store" is the name of this release. Some names in the code and the stores keep the earlier prefix `epm`: the tables `epm_triples` and `epm_store_markers`, the settings that start with `EPM_`, and file names such as `scripts/epm_facts.py`. They belong to KPI Store.
- The ontology's IRIs begin with `https://w3id.org/mpc/ontology/`. They identify terms and resolve nowhere. They are not issued by Marathon Petroleum, and nothing here is Marathon's own or endorsed by it. The namespaces will be reviewed and approved by the Data, Analytics and Insight team. Until then they are working names.
- In the Neo4j graph every label, relationship type and property is `prefix_name`, with one underscore (`skos_prefLabel`, `vs_Stage`).
- "Decision owner" in the documents and the sources means the subject matter expert who reviewed the documents and recorded each decision. Quotes attributed to "a subject matter expert reviewing the documents" are their words. For your own changes, your ontology owner holds this role.
- A claim that rests on peers reads as the industry view: "Industry standard, and analysis of publicly available filings from peers (U.S. refiners)".

## Licences and sources

The APQC Process Classification Framework for Downstream Petroleum is used with attribution under the APQC/IBM licence. Its notice is in `business_architecture/reference/README.md` and travels with every copy. The second viewer uses the page styles of Horoi under the Apache License 2.0. Its licence and notice are in `horoi_viewer/`. Each skill lists its sources, with versions and dates, in its `SOURCES.md`. Every other fact cites its source where it is used.

## Who to ask

Ask the owner of this release, who is the decision owner of the records in `business_architecture/domain/kpi-store-decisions/`. A step of a guide that does not work as written is a fault in the guide, so report it to the owner. Send a question about a Genie measure or its filter to the creator of that Genie space.
