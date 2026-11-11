# How to update the KPI Store ontology

This guide covers every change after the first run: a correction, a new version of a module, a new concept, a new process, a new environment and a new module. For the first run on the client sandbox, use the runbook, `business_architecture/ontology/projection/ontology-stores-runbook.md`.

Each section is a list of steps. Do them in order. The document test runs every command of this guide, except where a section says otherwise.

If your copy includes `viewer/index.html`, that page shows the ontology as you received it. Changing a package does not refresh the page.

## The words this guide uses

| Word | Meaning |
|---|---|
| Module | One part of the ontology with its own version, such as `kpi`. |
| Package | One released version of a module: the folder `business_architecture/ontology/releases/`, then the module, then the version. A package never changes after its release. A change makes a new package. |
| Release folder | The top folder of your copy, which holds `README.md` and `kpi_store`. |
| Ontology owner | The person your organisation names to decide what the ontology means. |
| Module owner | The person the ontology owner names for one module. Until a module has an owner, the ontology owner decides for it. |
| Correction version | A version that the cut tool wrote from a cleared report. Its name carries a marker: `1.2.1-correction.1`. |

The ontology owner approves every major release and every module's first release. The module owner approves minor and patch releases. The person who runs the cut approves a correction, at the cut's prompt.

## Before you change anything

You need the machine that the runbook set up. The commands start in the release folder unless a step moves you. They start Python with `py`, as on Windows.

1. Install the one more package that this guide's page builder needs.

   ```powershell run=scratch os=windows status-only
   py -m pip install "markdown-it-py>=4,<5"
   ```

2. Open Git Bash in the release folder. In File Explorer, right-click the folder and choose "Open Git Bash here".
3. Run the full check. It must end with `all checks passed`. It took about 10 minutes on a Mac and 21 minutes on a Windows machine with 4 cores. Run it in Git Bash: in PowerShell, the plain word `bash` starts the launcher of the Linux subsystem.

   ```bash run=slow
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

4. Run the full check again after each change, before you load any store.

The check proves your copy is valid. Every package equals a fresh build of its sources, the shapes conform, the competency questions answer and the tests pass. Its log shows skipped tests and one line that starts `FAIL a store request`. Both are expected: that line comes from a test that makes a write fail on purpose. Any other `FAIL` line is a real failure, and the script then does not reach its last line.

Do not edit files while the check runs. It compares the folder at its start and its end, and a change fails the run.

A Git copy keeps your history, and the cut tool then commits and tags each correction. Keep the file `.gitattributes` in a Git copy: without it, Git for Windows checks text files out with other line ends, and the packages' hashes differ. A plain folder works too. In a Git copy, run `git add -A` before the check, because one test reads which pages Git tracks.

## Choose the way a change goes

| What changed | The way | Section |
|---|---|---|
| Databricks renamed or removed a column, a table or a view that the ontology names. | A correction, through the report and the cut. | "A correction through the loop" |
| A column's spelling differs only in case. | The same correction. | "A correction through the loop" |
| A report row says "needs a minor version": a measure link with its filter, a new object, a new table edge, or the table that a Databricks table replaces. | A minor version of the module, with the release steps. | "The release steps" |
| A definition's wording, with the same meaning. | A patch, with the release steps. | "Change a concept's definition" |
| A new concept, alias, property or shape. | A minor version, with the release steps. | "Add a concept or a property" |
| A new process, or a changed one. | A release of `core`, then every module. | "Change a process" |
| The same ontology in another workspace, such as production. | New settings files. The ontology does not change. | "A new environment" |
| A data area that no module covers. | A new module at 1.0.0. | "Onboard another module" |

## Patch, minor or major

Classify every change before you make it. Then ask the owner who approves that kind. `skills/ontology/references/release.md` holds the full rules.

| Kind | What it covers |
|---|---|
| Major | An IRI changes or a concept is removed. A definition's meaning changes. A hierarchy change alters what a concept means. Any deprecation. A new module's first release, 1.0.0, also needs the ontology owner. |
| Minor | New concepts, aliases, references, instances or shapes that existing content already meets. |
| Patch | Typos, clearer wording with the same meaning, an added example or scope note. |
| Correction | A name in Databricks changed, and the ontology follows it. The cut tool writes it. |

Use this test. Would every query, report and answer made under the old definition still be correct under the new one? If yes, it is a patch or a minor. If no, or if you are unsure, it is a major.

**Never delete a term.** Mark it `owl:deprecated true`, add `dcterms:isReplacedBy` for its successor, keep its triples and say why in the changelog. Do this only in a major release.

A correction version sorts between two patches. The order is 1.2.0, 1.2.1-correction.1, 1.2.1-correction.2, 1.2.2. The next ordinary patch after a correction is 1.2.2.

## A correction through the loop

This is the normal way to follow a change in Databricks. The runner compares the ontology with the workspace on every run. If a name that the ontology holds is missing or renamed, the run stops on a report. You clear the report. The next run cuts a correction version and loads every store.

The steps are the runbook's, from "The first run" to "The sync check". Two things differ after the first run.

1. Run the runner, as in the runbook's "The first run". If it ends with `every step passed`, nothing differs and you are done.
2. If it stops on a report, clear the report, as in the runbook's "Clear the report".
3. Run the runner again and answer the cut's prompts, as in the runbook's "The second run".
4. If the `enterprise` step stops because the database holds KPI Store nodes of the earlier release, run the step again with the replace allowed. **The replace deletes every node in that database that carries the KPI Store's marks, before it copies.** The runbook's "The limits" lists the marks.

   ```powershell skip reason="needs-client-server: replaces the KPI Store's nodes in the client's Enterprise database"
   py -m kpi_store.runner --from enterprise --replace-enterprise
   ```

5. Read the last line. Expect `the steps that ran passed`, with the steps before `enterprise` named as left out.

The second difference is the version. A second correction to the same module counts up: `1.2.1-correction.2`.

### See the cut by itself

The runner calls the cut tool for you. To see what a cut does, run the tool on the made-up report that ships with the tests. It is the report of a made-up workspace in the sandbox's shapes. Do this in a copy of the release folder, never in the folder you load from.

1. Ask for the plan of the report as the notebook wrote it, with no decision. The tool refuses it, because the row that blocks has no decision.

   ```powershell run=correction exit=1
   py -m kpi_store.cut --report kpi_store/tests/fixtures/cut/discovery-report.json --plan
   ```

   ```text expect
   CutRefused: the report is not cleared. Rows that block the load and have no decision: R002
   ```

2. Ask for the plan with the cleared decisions. `cleared-decisions.csv` accepts the renamed column, the two case-only spellings and the second source. `--plan` changes nothing.

   ```powershell run=correction
   py -m kpi_store.cut --report kpi_store/tests/fixtures/cut/discovery-report.json --decisions kpi_store/tests/fixtures/cut/cleared-decisions.csv --plan
   ```

   ```text expect
   Discovery run 20261111T120000Z-0a1b2c3d of KPI Store 1.1: 28 rows.
   The cut applies (4):
     R001 column-case: column assessment_amount of idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact becomes Assessment_Amount (case only)
   ...
     R002 column-renamed: column ChangeValue of idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact becomes Change_Value_Amount  BREAKING
   ...
     R003 column-case: column Previous_amount of idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact becomes Previous_Amount (case only)
   ...
     R020 second-source: idp_sbx.semantic_sem_commercial.mips_mpr_executive_summary_fact_vw also serves the measure crack-spreads
   ...
   Waits, so the cut leaves it (1):
   ...
   No decision (<count>):
   ...
   Versions the cut writes:
     data-product 1.2.0 -> 1.2.1-correction.1
     logical-model 1.0.0 -> 1.0.1-correction.1
     technical-graph 1.1.0 -> 1.1.1-correction.1
     value-stream 1.2.0 -> 1.2.1-correction.1
     integration 2.5.0 -> 2.5.1-correction.1
   ```

3. Cut. At the first prompt type `Change_Value_Amount`, which confirms the breaking change. At the second prompt type `yes`.

   ```powershell run=correction types="Change_Value_Amount,yes"
   py -m kpi_store.cut --report kpi_store/tests/fixtures/cut/discovery-report.json --decisions kpi_store/tests/fixtures/cut/cleared-decisions.csv --approver "the ontology owner"
   ```

   ```text expect
   ...
   Done. The record is business_architecture/ontology/discovery-runs/20261111T120000Z-0a1b2c3d.md; the cut changed <count> files.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash; the runner does it).
   ```

4. In a Git copy, see the commit and the tag that the cut made. In a plain folder the cut writes the same files and makes no commit.

   ```powershell run=correction
   git --no-pager log --oneline -1
   git --no-pager tag --list
   ```

   ```text expect
   <commit> Cut data-product 1.2.1-correction.1 from discovery run 20261111T120000Z-0a1b2c3d
   data-product-1.2.1-correction.1
   ```

5. Run the full check on the corrected copy.

   ```bash run=correction
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

`business_architecture/ontology/discovery-runs/README.md` says what each decision does, what the record holds and how a standing decision works.

## The release steps

A patch, a minor and a major all end with these steps. The worked example adds the alias "unit capacity utilization" to the measure Unit Utilization in `kpi`. An alias is new content that changes no meaning, so it is a minor: `kpi` 1.3.0 becomes 1.4.0.

The versions in the commands are those of the release as you received it. Read the version you hold with `py next_version.py current kpi`, from the folder `business_architecture/ontology/release`.

1. List the modules to release, in order. The first line is the module you change. Each module after it depends on it and gets a patch.

   ```powershell run=release-git
   cd business_architecture/ontology/release
   py dependents.py kpi
   cd ../../..
   ```

   ```text expect
   kpi
   data-product
   market-data
   logical-model
   technical-graph
   value-stream
   integration
   ```

2. Change the module's source. A release is built from its sources, never edited in `releases`. For the example, open `business_architecture\ontology\kpi\measure-details.csv`, find the row `unit-utilization`, and change its `aliases` from `unit rates` to `unit rates;unit capacity utilization`.
3. Save the approval. Make the folder `business_architecture\ontology\approvals` if you have none. Write the sentence that approved the release in a file there, such as `2026-11-12-kpi.md`. One file can cover every module of one change.

   The document test does steps 2 and 3 with this block. If you did them by hand, skip it.

   ```python run=slow
   from pathlib import Path

   ontology = Path("business_architecture/ontology")
   table = ontology / "kpi" / "measure-details.csv"
   text = table.read_text(encoding="utf-8")
   old = ",unit rates,crude-utilization,"
   assert text.count(old) == 1
   table.write_text(text.replace(old, ",unit rates;unit capacity utilization,crude-utilization,"), encoding="utf-8", newline="\n")
   approval = ontology / "approvals" / "2026-11-12-kpi.md"
   approval.parent.mkdir(exist_ok=True)
   approval.write_text("# Approval of kpi 1.4.0\n\nApproved as a minor: the alias \"unit capacity utilization\" for Unit Utilization.\n",
                       encoding="utf-8", newline="\n")
   print("changed", table.name, "and wrote", approval.name)
   ```

   ```text expect
   changed measure-details.csv and wrote 2026-11-12-kpi.md
   ```

4. Rebuild the module's source file. Each module has its own builder in its folder. `scripts/check.sh` lists them.

   ```powershell run=slow
   cd business_architecture/ontology/kpi
   py build_measures.py --write
   ```

   ```text expect
   measures 41; <the counts by source and kind>
   wrote <the path of the measures file>
   ```

5. Set the module's new version and write its package. `start` sets the version, the date, the approver and the approval in the module's entry in `build_module.py`. It also adds a section to the top of the module's `CHANGELOG.md`.

   ```powershell run=slow
   cd ../release
   py next_version.py start kpi 1.4.0 minor --why "Adds the alias unit capacity utilization to Unit Utilization." --approver "The kpi module owner" --where "approvals/2026-11-12-kpi.md" --words "Approved as a minor."
   py build_module.py kpi --write
   ```

   ```text expect
   kpi is set to 1.4.0. Now run: python3 build_module.py kpi --write
   kpi 1.4.0: <count> triples; shapes conform
   wrote <the path of the new package>
   ```

   The write stops if the version is already released and the content differs. Raise the version first, because a released package never changes.

6. Release every module that depends on it, and finish all of them. `cascade` gives each module of step 1's list the next patch, writes its package, and moves each old package to `releases\previous`. It also changes each version in the projection's two lists, `projection/pipeline.py` and `projection/skill-run/epm-config.json`.

   ```powershell run=slow
   py next_version.py cascade kpi --approver "The kpi module owner" --where "approvals/2026-11-12-kpi.md" --words "Approved as a minor."
   ```

   ```text expect
   data-product is set to 1.2.1. Now run: python3 build_module.py data-product --write
   market-data is set to 1.1.1. Now run: python3 build_module.py market-data --write
   logical-model is set to 1.0.1. Now run: python3 build_module.py logical-model --write
   technical-graph is set to 1.1.1. Now run: python3 build_module.py technical-graph --write
   value-stream is set to 1.2.1. Now run: python3 build_module.py value-stream --write
   integration is set to 2.5.1. Now run: python3 build_module.py integration --write
   kpi 1.3.0 moved to releases/previous/; the projection's lists name 1.4.0
   data-product 1.2.0 moved to releases/previous/; the projection's lists name 1.2.1
   market-data 1.1.0 moved to releases/previous/; the projection's lists name 1.1.1
   logical-model 1.0.0 moved to releases/previous/; the projection's lists name 1.0.1
   technical-graph 1.1.0 moved to releases/previous/; the projection's lists name 1.1.1
   value-stream 1.2.0 moved to releases/previous/; the projection's lists name 1.2.1
   integration 2.5.0 moved to releases/previous/; the projection's lists name 2.5.1
   7 modules released. Now rebuild the catalog and the projection manifest, and run the check.
   ```

   The lines that say "Now run" are `start`'s own. `cascade` has already run that command for each module. `cascade` verifies each package against a fresh build before it finishes the module. If it stops halfway, fix what it names and run it again. It keeps its plan in `release\cascade-in-progress.json` until it ends, so the next run leaves a finished module alone and builds what is missing. If it names a folder that is not a whole package, delete that folder first. A build that failed midway leaves such a folder.

7. Rebuild the catalog, then the projection manifest, then run the competency questions.

   ```powershell run=slow
   py build_catalog.py --write
   cd ../projection
   py pipeline.py build
   cd ../regression
   py run.py
   cd ../../..
   ```

   ```text expect
   catalog: 13 releases from 13 packages
   wrote <the path of the catalog file>
   Step 1 passed; loadable.nt <count> triples, inferred.nt 2
   wrote projection-manifest.json
   ...
   competency coverage on <the core package>: 57 questions; answerable 56, partial 0, waiting 0, parked 1
   ```

8. In a Git copy, stage the change. Then run the full check.

   ```bash run=slow
   git add -A
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

   After a change, the check prints a note: `projection-report.json describes an earlier build`. That file is the summary of the last Neo4j load, and it now describes the release before your change. The note does not fail the check, and it does not mean the ontology is wrong. It goes away when you have loaded the stores and recorded the new load's report with `py pipeline.py record`. The runbook's section "Record the load's report in the release folder" runs that command.

9. Search your copy for text that the change made stale, and update each document that holds it. No check catches a copy of a sentence.
10. Load the stores with the runner, and read its last line. The release is done when the sync check reads `current` on every line.

    ```powershell skip reason="needs-client-server: loads the client's Databricks and Enterprise database"
    py -m kpi_store.runner
    ```

    If the `enterprise` step stops because the database holds the earlier release, see step 4 of "A correction through the loop".

## Change a concept's definition

A new wording with the same meaning is a patch. If the meaning changes, the release is a major, and the ontology owner approves it.

1. Find where the definition lives. Most sources are tables and Turtle files in the module's folder, so search there for the text. A file that starts "Built by" is generated: edit the source it names.
2. Edit the text in that source. Keep the citation of its source. If the new wording rests on a new source, cite it.
3. Follow "The release steps" from step 3. In step 5, use `patch` and the next patch version.

For `lane`, the source is `business_architecture/business_process/office_lanes.json`. Rewording a lane there is still a release of `lane`.

## Add a concept or a property

A new term that removes nothing is a minor.

1. Add the term to the module's `vocabulary.ttl`, with `rdfs:label`, `skos:definition`, and its source in `dcterms:bibliographicCitation`. Copy a neighbouring term of the same kind, because the module's tests may ask for more.
2. Add what checks it to the module's `shapes.ttl`. Each property on a class states its cardinality in a `sh:property` line on that class's shape.
3. If the module also has a closed shape, add the property to its `sh:ignoredProperties` list too. `kpi/shapes.ttl` needs both: the line on `shp:Measure`, and the list on `shp:NoValuesOnMeasures`.
4. For a value on instances, add a column to the module's table and to its builder. Give every row the column, even when it is empty, because a short row passes with no warning.
5. For a concept in a code list, add a row to that list's table.
6. Add a test that names the term, in the module's `test_*.py`.
7. Follow "The release steps" from step 3.

When the source of a term is your owner's request, cite the file that holds their approval.

### A report row that needs a minor version

The cut tool leaves four kinds of accepted rows, and lists each as "needs a minor version". Each goes in by the steps above.

| Row | Module | What to add |
|---|---|---|
| `measure-link` | `data-product` | A property for the filter, in `vocabulary.ttl` and `shapes.ttl`, and the link with its filter in the module's tables. The Genie space's creator confirms each filter first. Take the change through the `ontology` skill's gates. |
| `migration-pair` | `technical-graph` | The table that a Databricks table replaces. |
| A new object, from an `object-extra` row you accepted | `data-product` | A row in `data-product/pricing/tables.csv`, and its lineage in `lineage.csv`. |
| A new table edge, from a `question` row | `data-product` | A row in `data-product/pricing/lineage.csv`. |

## Change a process

The process map is the source of the taxonomy in `core`. Every module depends on `core`, so this is the widest change. A change to an existing process's meaning is a major. A new process is a minor.

The document test does not run this section's commands. Each needs your own edits to a new builder first. The steps it ends with, the cascade and the check, are tested in "The release steps".

1. Copy `business_architecture\business_process\downstream_process_map.json` into `business_architecture\ontology\release\frozen`. Name the copy with a label of 12 letters or digits, a hyphen, and the file's name, such as `before202611-downstream_process_map.json`.
2. Add the node to `downstream_process_map.json`, with its `id`, `level`, `name` and `description`. The builder makes the description's first sentence the definition and the rest the scope note. So put the whole definition in the first sentence.
3. Add its row to `business_architecture\ontology\build\output\step2-identity-map.json`, beside its siblings, with the same fields. Copy `minted` and `deprecated` from a sibling: `false` for an ordinary new process.
4. Copy the changed map into `frozen` too, under a second label, such as `after2026110-downstream_process_map.json`.
5. Save the approval, as step 3 of "The release steps" says.
6. In `business_architecture\ontology\release`, copy `build_core_template.py` to `build_core_2_5.py`. The name is for the first change to this release. A later change raises it.
7. Fill in the block that the new builder marks: the two labels, the new version and the approval. To change an existing node's ID or description, read `build_core_2_2.py`, which applies those changes.
8. Write the changelog `business_architecture\ontology\releases\core\CHANGELOG-2.5.0.md`, in the form of `CHANGELOG-2.4.0.md` beside it.
9. Add a short test, `test_build_core_2_5.py`, beside the builder. It says what the release adds and that it removes no IRI. Add it to the test list in `scripts/check.sh`.
10. From the folder `release`, write the package with `py build_core_2_5.py --write`.
11. Move the folder `releases\core\2.4.0` into `releases\previous\core`. Make that folder first if it is missing.
12. Rebuild every module's source file, since each reads `core`. `scripts/check.sh` lists the builders after the comment on each module's source Turtle. Run each from its folder with `--write`.
13. From the folder `release`, release every module with `py next_version.py cascade core`, with `--approver`, `--where` and `--words` as in "The release steps".
14. Change the version of `core` by hand in `PACKAGES` in `projection/pipeline.py` and under `packages` in `projection/skill-run/epm-config.json`.
15. Follow "The release steps" from step 7.

In a Git copy you may name the two copies of the map by the first 12 characters of their commits instead.

## A new environment

The same ontology loads into another workspace with new settings files. The ontology does not change. The ontology names its catalogs `idp_sbx` and `synapse_dev`. The `[names]` table says what each is called in the new environment.

1. Copy `C:\kpi-store-local\kpi_store.toml` to a new file beside it, such as `kpi_store.prod.toml`.
2. In the new file, set `write_catalog` and `read_catalogs` to the new environment's catalogs.
3. In `[names]`, set each of the ontology's two catalog names to the catalog that holds those objects in the new environment.
4. Set `warehouse_id` to a SQL warehouse of the new workspace.
5. Copy `C:\kpi-store-local\stores.toml` to a new file, such as `stores.prod.toml`.
6. In the new file, set `settings` to the new `kpi_store` file, and `run_folder` to a new folder, such as `C:/kpi-store-local/runs-prod`.
7. In `[databricks]`, set `profile` to a profile that you signed in to the new workspace with.
8. Set `[neo4j.enterprise]` to the new environment's server and database.
9. Run every command for that environment with `--stores` and the new file.

The new settings file has this shape. The names in angle brackets are yours to fill in.

```toml parse
[release]
zip = "kpi-store-1.1.zip"
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

[databricks]
write_catalog = "<your production catalog>"
write_schema = "kpi_store"
tech_graph_schema = "tech_graph"
volume = "releases"
read_catalogs = ["<your production catalog>", "<its Synapse catalog>"]
warehouse_id = "<a SQL warehouse ID>"

[names]
idp_sbx = "<your production catalog>"
synapse_dev = "<its Synapse catalog>"

[skip]
schemas = ["information_schema", "bronze_replica_*"]
tables = ["*__ct", "attrep_*"]

[genie]
spaces = []
```

Each catalog in `[names]` must also be in `read_catalogs`. Two ontology catalogs may not share one catalog of the environment. The settings reader refuses both mistakes before any read or write. To check a settings file before you use it, load it. The example loads the file that ships with the release:

```powershell run=release-copy
py -c "from kpi_store import settings; s = settings.load('kpi_store/kpi_store.example.toml'); print(s.write_schemas, s.read_catalogs, s.names)"
```

```text expect
('idp_sbx.kpi_store', 'idp_sbx.tech_graph') ('idp_sbx', 'synapse_dev') {'idp_sbx': 'idp_sbx', 'synapse_dev': 'synapse_dev'}
```

The first run in a new environment is a first run. Follow the runbook from "Run the setup check", with `--stores` and the new file on every command. A name that differs in the new environment is an `environment setting` row or a correction, as the report says.

**A correction changes the ontology for every environment.** Accept a rename only when the name changed everywhere. When it differs in one environment only, decide the row as `environment setting`.

## Onboard another module

A module is one part of the ontology with its own version, such as `kpi`. Add a module when a new data area brings terms that no module owns. This section says how to decide, where to register the module, and how its tables join the discovery comparison. It ends with a made-up example that you can run.

`skills/ontology/references/new-module.md` holds the full method and its gates. Read it before you start a real module.

### Decide whether the area needs a module

1. Write the competency question that the existing modules cannot answer. If you find none, stop: the area needs no module.
2. Check that no module owns the area already. `business_architecture/ontology/MODULES.md` lists what each module holds.
3. If a module owns the area, extend that module with a minor version ("The release steps"). Do not add a second owner.
4. Ask your ontology owner to approve the new module and to name its owner. The ontology owner approves every first release.
5. Save the approving sentence in a file under `business_architecture/ontology/approvals/`. The module's entry names that file.

### Write the module's folder

Copy the shape of `business_architecture/ontology/lane/`, the smallest module. Write six files in a new folder named after the module.

| File | What it holds |
|---|---|
| `README.md` | What the module holds, in a few sentences, and a table of its files. |
| `vocabulary.ttl` | Each class, property and concept scheme, with `rdfs:label`, `skos:definition` and `dcterms:bibliographicCitation`. Give each property one `rdfs:domain` and one `rdfs:range`. Point to another module's term by its IRI. Never define it again. |
| `shapes.ttl` | The SHACL shapes. Give each property of a class a `sh:property` line. Write no apostrophe in a `sh:message`. |
| A table, as CSV | The module's instances, one row each. |
| A builder | It reads the table and writes the instances as Turtle. Give it `--write` and `--verify`. |
| A test file | The build is current, the instances are the table's, and the shapes reject a wrong instance. |

Cite a source in words, with `dcterms:bibliographicCitation`. A `dcterms:source` link needs a row in `authority/source-tiers.csv`, and that table is part of `integration`. Such a row means a minor version of `integration` after your module.

### Register the module in every place

A place you miss fails a check, or leaves the module out of a store without a word. Register the module in each place below before you build.

| Place | What to add |
|---|---|
| `business_architecture/ontology/release/build_module.py` | An entry in `MODULES`: title, description, `version` `1.0.0`, `stage` `None`, approver, approval, issued, parts, shapes, `depends_on` and decisions. |
| `business_architecture/ontology/releases/<module>/CHANGELOG.md` | A new file: a title line, then the section of the first release, with "Known gaps". |
| `scripts/check.sh` | Three lines: `build_module.py <module> --verify`, the builder's `--verify`, and the test file in the test list. |
| `business_architecture/ontology/projection/pipeline.py` | The module and its version in `PACKAGES`, its name in `OWN`, and its prefix in `PREFIXES`. |
| `business_architecture/ontology/projection/skill-run/epm-config.json` | The namespace under `own_namespaces`, the prefix under `prefixes`, and the version under `packages`. |
| `business_architecture/ontology/regression/` | The question's row in `expected.csv`, its query in `queries/`, and the module's files in the list in `run.py`. |
| `business_architecture/ontology/validation/test_all_module_shapes.py` | The module's `shapes.ttl` in `SHAPE_FILES`. |
| `business_architecture/ontology/competency-questions.md` | The new question, numbered after the last one. |
| `business_architecture/ontology/MODULES.md` | A row in the table of what each package is built from, and a section with an example that starts with a `module:` comment line. The example's triples must be in the released package. |
| `scripts/build_docs_html.py` | The module's folder in `MODULE_READMES`, so that its README gets a page. |

Two more places apply to some modules only. Add a row to `scripts/epm_facts.py`, in the `coverage` table, when processes link to the module and you want them counted. Add the module to `depends_on` of `integration` at the next release of `integration`, if `integration` links to it.

### Give the area's tables their place in the discovery comparison

The comparison before each Databricks load reads the platform tables of the `data-product` module. A table that is not there is not compared. So a new data area joins the comparison through `data-product`, whether or not it also gets a module of its own.

**An object, a column or a table edge that the ontology names and the workspace lacks stops the load.** Add a table only when it exists in the workspace under that name.

1. Add a row for each table and view of the area to `business_architecture/ontology/data-product/pricing/tables.csv`. Use the names the workspace uses.
2. Add a row for each hop of the area's lineage to `lineage.csv`, in the same folder.
3. Add a row for each value column to `columns.csv`, in the same folder.
4. Run the builder from `business_architecture/ontology/data-product`: `py build_pricing.py --write`. It fails on a name that does not resolve.
5. Release `data-product` as a minor version, with its cascade ("The release steps").
6. Run `py -m kpi_store.runner`. The run now compares the new tables with the workspace.

The cut tool applies corrections to the tables in `data-product/pricing/` only. A difference in any other module's content goes through the release steps of this guide, not through the cut.

### Release the module at 1.0.0

1. Run the module's builder with `--write`, from the module's folder.
2. Write the package: `py build_module.py <module> --write`, from `business_architecture/ontology/release`.
3. Rebuild the catalog: `py build_catalog.py --write`, from the same folder.
4. Rebuild the projection manifest: `py pipeline.py build`, from `business_architecture/ontology/projection`.
5. Run the competency questions: `py run.py`, from `business_architecture/ontology/regression`.
6. Rebuild the pages: `py scripts/build_docs_html.py`, from the top folder.
7. Run the full check. Do not share the module until it prints `all checks passed`.

A first release needs no cascade. No released module requires the new one yet. A module that should link to it does so in its own next release.

### Reload the stores

The projection takes every module in `PACKAGES`, so the new module goes into Neo4j with the others. No store needs a setting of its own for it.

1. Run `py -m kpi_store.runner --replace-enterprise`. The Enterprise database holds the earlier release, so the copy needs the replace.
2. Read the last line. Expect `every step passed`.
3. Run `py -m kpi_store.sync_check`. Every line must read `current`.

The runbook, `business_architecture/ontology/projection/ontology-stores-runbook.md`, explains each line of both commands.

### A worked example: the made-up module `sample-area`

The release holds a helper, `release/onboard_example.py`, that onboards one made-up module. It writes the six files of the folder and registers the module in each place of the table above. Read its functions as the pattern for your own module: it has one function per place.

**Run the example in a copy of the release, never in the folder you load the stores from.** It adds a made-up module to the ontology.

The commands start in the top folder of the copy.

1. List the places. This changes nothing.

   ```powershell run=new-module
   cd business_architecture/ontology/release
   py onboard_example.py --plan
   ```

   ```text expect
   would register in business_architecture/ontology/sample-area/
   would register in business_architecture/ontology/approvals/sample-area-1.0.0.md
   would register in business_architecture/ontology/release/build_module.py
   would register in business_architecture/ontology/releases/sample-area/CHANGELOG.md
   would register in scripts/check.sh
   would register in business_architecture/ontology/projection/pipeline.py
   would register in business_architecture/ontology/projection/skill-run/epm-config.json
   would register in business_architecture/ontology/regression/
   would register in business_architecture/ontology/validation/test_all_module_shapes.py
   would register in business_architecture/ontology/competency-questions.md
   would register in business_architecture/ontology/MODULES.md
   would register in scripts/build_docs_html.py
   ```

2. Write the module's folder and register the module.

   ```powershell run=new-module
   py onboard_example.py --write
   ```

   ```text expect
   registered in business_architecture/ontology/sample-area/
   ...
   registered in scripts/build_docs_html.py
   Now build: cd ../sample-area, then build_sample_areas.py --write. HOW-TO-UPDATE.md has the steps after it.
   ```

3. Build the module's instances from its table.

   ```powershell run=new-module
   cd ../sample-area
   py build_sample_areas.py --write
   ```

   ```text expect
   areas 3; covered processes 3
   wrote sample-areas.ttl
   ```

4. Write the package at 1.0.0, then rebuild the catalog.

   ```powershell run=new-module
   cd ../release
   py build_module.py sample-area --write
   py build_catalog.py --write
   ```

   ```text expect
   sample-area 1.0.0: 52 triples; shapes conform
   wrote <the package folder>
   catalog: 14 releases from 14 packages
   wrote <the catalog file>
   ```

5. Rebuild the projection manifest. The projection now takes the module.

   ```powershell run=new-module
   cd ../projection
   py pipeline.py build
   ```

   ```text expect
   ...
   wrote projection-manifest.json
   ```

6. Run the competency questions. The count is one higher than before: the module's question is number 58.

   ```powershell run=new-module
   cd ../regression
   py run.py
   ```

   ```text expect
   competency coverage on <the core release>: 58 questions; answerable 57, partial 0, waiting 0, parked 1
   ```

7. Rebuild the pages, and tell Git about the new files. One test reads which pages Git tracks.

   ```powershell run=new-module status-only
   cd ../../..
   py scripts/build_docs_html.py
   git add -A
   ```

8. Run the full check. It takes about 10 minutes. On Windows, run it in Git Bash.

   ```bash run=new-module
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

9. Run the helper again. It refuses a copy that holds the module, and changes nothing.

   ```powershell run=new-module exit=1
   cd business_architecture/ontology/release
   py onboard_example.py --write
   ```

   ```text expect
   refused: this release holds the module sample-area already; nothing was changed
   ```

The copy now holds the made-up module. Delete the copy when you have read what the helper changed.

## Add a logical model

`logical-model` holds logical data models exported from ER Studio Data Architect. A new model joins this module as one more model. It is not a new module.

Each model is two files in `business_architecture\ontology\logical-model\models`: ER Studio's Turtle export, saved as the model's name and `.erstudio.ttl`, and a links file, the model's name and `.links.csv`. Name the model in lower-case words joined by hyphens. `logical-model/README.md` describes the links file's columns. Only rows marked `asserted` become triples. Every link target must be in the newest package of its module.

1. Save the two files in `models`.
2. Build the model's graphs with `--write`. The command below is the one for the made-up model that ships with the release, with `--verify`, which changes nothing. For your model, change the four names and write `--write` in place of `--verify`.

   ```powershell run=release-copy status-only
   cd business_architecture/ontology/logical-model
   py build_logical_model.py --export models/customer-logical-model.erstudio.ttl --links models/customer-logical-model.links.csv --model customer-logical-model --title "Customer logical model" --out models --verify
   ```

3. In `release/build_module.py`, add the model's two graph files to the `graphs` list of the `logical-model` entry: the `.erstudio.ttl` file and the `.layer.ttl` file that the builder wrote.
4. In `scripts/check.sh`, add the new model's four options to the line that runs `build_logical_model.py`, so that the check rebuilds every model.
5. Release `logical-model` as a minor, with "The release steps" from step 3.

The stores load each model: Fuseki and Databricks its two graphs as named graphs, the two Neo4j databases the model as its own subgraph. The sync check prints an `lm:` line for each Neo4j database.

A build can also read a model's files from a folder outside your copy. Point `--export` and `--links` at them, and keep `--out` at `models`. List each file with its SHA-256 in the `augment` list of the `logical-model` entry, and compare the files with those hashes before you build from them again.

## Keep the catalog, the regression and the projection current

| Part | Command, from its folder | When |
|---|---|---|
| The catalog, `releases/catalog.ttl` | `py build_catalog.py --write`, in `release` | After any package is written. |
| The regression | `py run.py`, in `regression` | After any change. A new question goes in `regression/expected.csv`, with its query in `regression/queries`. |
| The projection manifest | `py pipeline.py build`, in `projection` | After any package is written. The check fails until you run it. |

Step 7 of "The release steps" runs all three.

## Keep every store in step

Your packages are the master copy. Each store is a copy that falls behind when you release.

1. After every release, run the runner. It loads Databricks, Fuseki, the local Neo4j and Enterprise, and then runs the sync check.
2. To see later which store is behind, run the sync check alone. The runbook's "The sync check" shows the command and how to read each line.
3. To repair a store, run the runner again. Do not fix a store by hand.

A release is done only when every line of the sync check reads `current`.

## The optional check against this release

`scripts/check-pinned.sh` asks a different question from `scripts/check.sh`: does your copy still equal KPI Store 1.1 as shipped? Its tests pin versions, counts, approvals and the figures in the guide. They pass on the release as shipped. After your first change some of them fail. That means only that your copy has moved on. Ignore them from then on, or edit `scripts/pinned-tests.txt` when you want your own pins.

The documents that state figures or versions describe KPI Store 1.1 as shipped. They do not update themselves. Update the ones your readers use.

## The namespace

The IRIs begin with `https://w3id.org/mpc/ontology/`. Keep them as working names unless you have a reason to change them. They identify terms and resolve nowhere. A term's IRI is its identity, so a change is a major release of every module.

If you do change the namespace, do it first, before other changes, and with the ontology owner's approval.

1. Raise `core` and every module to the next major version, following the sections above.
2. Replace the base in the sources: the module folders, the process map's identity map, the builders, the folder `projection`, the shapes and the regression queries.
3. Leave `releases\previous` alone. Those packages keep the old IRIs, because a released package never changes.
4. Write every package again in the order `dependents.py core` prints, and run the full check.

## What you can ignore

These describe how the ontology was first built. You need none of them to update it.

- Part 2 of `business_architecture/ontology/epm-walkthrough.html`, and the folder `build`, apart from the identity map named above.
- The folder `step4` and the older core builders, `build_core_next.py` and `build_core_2_1.py`, which rebuild earlier releases.
- The folder `release/frozen`, apart from the copies you add.
- `business_architecture/domain/decision-packages`, questions put to the subject matter expert during the build.
- `business_architecture/ontology/business-closeout.md`, and any note in a README or changelog dated before you received this release.
