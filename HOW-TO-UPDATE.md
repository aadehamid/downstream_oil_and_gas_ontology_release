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
| Proposal | A folder that the propose command writes from one signed form of the KPI intake pack, such as a KPI intake, term-change, reference-item or new-module form: the changes as KGCL lines, the approval record and a summary, and for a new KPI a table of the facts KGCL cannot write. The apply command applies it. |
| Route | Whether a change is released as a patch, a minor or a major. "Patch, minor or major" below says which is which. |

The ontology owner approves every major release and every module's first release. The module owner approves minor and patch releases. The person who runs the cut approves a correction, at the cut's prompt.

## Before you change anything

You need the machine that the runbook set up. The commands start in the release folder unless a step moves you. They start Python with `python`, as the runbook does.

1. Install the one more package that this guide's page builder needs.

   ```powershell run=scratch os=windows status-only
   python -m pip install "markdown-it-py>=4,<5"
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

Keep the release folder in Git. The runbook's section "Keep the release folder in Git" has the commands and the rules: commit the release as it was unpacked, before any change, and commit only the release's files and your changes to them. Git then keeps your history, the cut tool commits and tags each correction, and the runner zips exactly the files that Git tracks. Keep the file `.gitattributes`: without it, Git for Windows checks text files out with other line ends, and the packages' hashes differ. A plain folder, one with no `.git` folder, works too; there the cut makes no commit and the runner zips every file except caches. In a Git folder, run `git add -A` before the check, because one test reads which pages Git tracks, and commit before a run that cuts.

## Choose the way a change goes

| What changed | The way | Section |
|---|---|---|
| Databricks renamed or removed a column, a table or a view that the ontology names. | A correction, through the report and the cut. | "A correction through the loop" |
| A column's spelling differs only in case. | The same correction. | "A correction through the loop" |
| A report row says "needs a minor version": a measure link with its filter, a new object, a new table edge, or the table that a Databricks table replaces. | A minor version of the module, with the release steps. | "The release steps" |
| A new KPI. | The KPI intake form, then the propose and apply commands. No file is edited by hand. | "Add a KPI with the KPI intake form" |
| A measure's name, definition, other names or process links. | The term-change form, then the propose and apply commands. No file is edited by hand. | "Change a measure with the term-change form" |
| A new system that a document names, or a new table that copies a table of a system. | The reference-item form, then the propose and apply commands. No file is edited by hand. | "Add a system or a table with the reference-item form" |
| A definition's wording, with the same meaning. | A patch, with the release steps. | "Change a concept's definition" |
| A new concept, alias, property or shape. | A minor version, with the release steps. | "Add a concept or a property" |
| A new business area, process or step. | The process map request form, then the propose and apply commands. The apply releases `core` and every module. No file is edited by hand. | "Add a process, a step or a business area with the process map request" |
| A process renamed, moved, described anew or removed. | A release of `core` that a specialist writes, then every module. | "Change a process" |
| The same ontology in another workspace, such as production. | New settings files. The ontology does not change. | "A new environment" |
| A data area that no module covers, whose content is a list of terms or a list of items of a class the ontology holds. | The new-module form, then the propose and apply commands. The apply releases the module at 1.0.0. No file is edited by hand. | "Add a module with the new-module form" |
| A data area that needs a new class, a new property or a rule of its own. | A new module at 1.0.0 that a specialist writes. | "Onboard another module" |
| A term that the business no longer uses, or two terms that are one. | A major version. The term is deprecated, never deleted. | "Deprecate a term" |
| A term that is listed under the wrong kind, such as a system's kind. | A major version, when an answer under the old kind is no longer right. | "Change the kind of a term" |
| Entries of the data-product catalog that are not data products. | A proposal to the portfolio file, then a major version of `data-product`. | "Move catalog entries to another class" |
| A data domain that the KPI form must offer in question 1.5. | The domain activation form, then the propose and apply commands. No file is edited by hand. | "Activate a domain with the domain activation form" |
| New roles, or new RACI entries for processes the map holds. | The process map request form, then the propose and apply commands. No file is edited by hand. | "Add roles and RACI entries with the process map request" |
| A RACI entry removed or replaced. | A proposal to the process map, then a version of `organization`. | "Change the RACI" |
| A list of allowed values that the ontology lacks, such as the data domains. | A minor version of the module that holds the list. | "Add a controlled list to a module" |

## Patch, minor or major

Classify every change before you make it. Then ask the owner who approves that kind. `skills/ontology/references/release.md` holds the full rules.

| Kind | What it covers |
|---|---|
| Major | An IRI changes or a concept is removed. A definition's meaning changes. A hierarchy change alters what a concept means. Any deprecation. A new module's first release, 1.0.0, also needs the ontology owner. |
| Minor | New concepts, aliases, references, instances or shapes that existing content already meets. |
| Patch | Typos, clearer wording with the same meaning, an added example or scope note. |
| Correction | A name in Databricks changed, and the ontology follows it. The cut tool writes it. |

Use this test. Would every query, report and answer made under the old definition still be correct under the new one? If yes, it is a patch or a minor. If no, or if you are unsure, it is a major.

**Never delete a term.** Mark it `owl:deprecated true`, add `dcterms:isReplacedBy` for its successor, keep its triples and say why in the changelog. Do this only in a major release. "Deprecate a term" has the steps.

A correction version sorts between two patches. The order is 1.2.0, 1.2.1-correction.1, 1.2.1-correction.2, 1.2.2. The next ordinary patch after a correction is 1.2.2.

## A correction through the loop

This is the normal way to follow a change in Databricks. The runner compares the ontology with the workspace on every run. If a name that the ontology holds is missing or renamed, the run stops on a report. You clear the report. The next run cuts a correction version and loads every store.

The steps are the runbook's, from "The first run" to "The sync check". Two things differ after the first run.

1. Run the runner, as in the runbook's "The first run". If it ends with `every step passed`, nothing differs and you are done.
2. If it stops on a report, clear the report, as in the runbook's "Clear the report".
3. Run the runner again and answer the cut's prompts, as in the runbook's "The second run".
4. If the `enterprise` step stops because the database holds KPI Store nodes of the earlier release, run the step again with the replace allowed. **The replace deletes every node in that database that carries the KPI Store's marks, before it copies.** The runbook's "The limits" lists the marks. If the copy still stops and names nodes, the new release dropped a model, class or label that those nodes belong to; the runbook's "Replace what Enterprise holds" says what to do.

   ```powershell run=first-run
   python -m kpi_store.runner --from enterprise --replace-enterprise
   ```

5. Read the last line. Expect `the steps that ran passed`, with the steps before `enterprise` named as left out.

   ```text expect
   run <run ID>: enterprise, sync, summary
   enterprise: <what the copy did>
   ...
   the steps that ran passed; left out: cut, check, zip, volume, upload, notebook, report, fuseki, neo4j (not run, so not checked)
   ```

The second difference is the version. A second correction to the same module counts up: `1.2.1-correction.2`.

### See the cut by itself

The runner calls the cut tool for you. To see what a cut does, run the tool on the made-up report that ships with the tests. It is the report of a made-up workspace in the sandbox's shapes. Do this in a copy of the release folder, never in the folder you load from.

1. Ask for the plan of the report as the notebook wrote it, with no decision. The tool refuses it, because the row that blocks has no decision.

   ```powershell run=correction exit=1
   python -m kpi_store.cut --report kpi_store/tests/fixtures/cut/discovery-report.json --plan
   ```

   ```text expect
   CutRefused: the report is not cleared. Rows that block the load and have no decision: R002
   ```

2. Ask for the plan with the cleared decisions. `cleared-decisions.csv` accepts the renamed column, the two case-only spellings and the second source. `--plan` changes nothing.

   ```powershell run=correction
   python -m kpi_store.cut --report kpi_store/tests/fixtures/cut/discovery-report.json --decisions kpi_store/tests/fixtures/cut/cleared-decisions.csv --plan
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
   The cut also rebuilds the KPI intake pack (kpi-intake/), whose pick lists come from these packages.
   ```

3. Cut. At the first prompt type `Change_Value_Amount`, which confirms the breaking change. At the second prompt type `yes`.

   ```powershell run=correction types="Change_Value_Amount,yes"
   python -m kpi_store.cut --report kpi_store/tests/fixtures/cut/discovery-report.json --decisions kpi_store/tests/fixtures/cut/cleared-decisions.csv --approver "the ontology owner"
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

5. Run the full check on the corrected copy. The documents' examples show the release as shipped, so on a corrected copy the check reads them and runs none. Updating the examples is part of preparing a new zip: `scripts/DOC-SNIPPETS.md` says how, under "The release the examples describe".

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

The versions in the commands are those of the release as you received it. Read the version you hold with `python next_version.py current kpi`, from the folder `business_architecture/ontology/release`.

1. List the modules to release, in order. The first line is the module you change. Each module after it depends on it and gets a patch.

   ```powershell run=release-git
   cd business_architecture/ontology/release
   python dependents.py kpi
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
   python build_measures.py --write
   ```

   ```text expect
   measures 41; <the counts by source and kind>
   wrote <the path of the measures file>
   ```

5. Set the module's new version and write its package. `start` sets the version, the date, the approver and the approval in the module's entry in `build_module.py`. It also adds a section to the top of the module's `CHANGELOG.md`.

   ```powershell run=slow
   cd ../release
   python next_version.py start kpi 1.4.0 minor --why "Adds the alias unit capacity utilization to Unit Utilization." --approver "The kpi module owner" --where "approvals/2026-11-12-kpi.md" --words "Approved as a minor."
   python build_module.py kpi --write
   ```

   ```text expect
   kpi is set to 1.4.0. Now run: python3 build_module.py kpi --write
   kpi 1.4.0: <count> triples; shapes conform
   wrote <the path of the new package>
   ```

   The write stops if the version is already released and the content differs. Raise the version first, because a released package never changes.

6. Release every module that depends on it, and finish all of them. `cascade` gives each module of step 1's list the next patch, writes its package, and moves each old package to `releases\previous`. It also changes each version in the projection's two lists, `projection/pipeline.py` and `projection/skill-run/epm-config.json`.

   ```powershell run=slow
   python next_version.py cascade kpi --approver "The kpi module owner" --where "approvals/2026-11-12-kpi.md" --words "Approved as a minor."
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
   python build_catalog.py --write
   cd ../projection
   python pipeline.py build
   cd ../regression
   python run.py
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

8. Rebuild the KPI intake pack, so that its lists offer what the release changed. The command needs the `openpyxl` package beside `rdflib` (`python -m pip install openpyxl`). `kpi-intake/README.md` explains the pack.

   ```powershell run=slow
   python -m kpi_store.intake build
   ```

   ```text expect
   wrote kpi-intake/pick-lists.json
   ...
   ```

9. In a Git copy, stage the change. Then run the full check. After a release of a module the check reads the documents' examples and runs none, as after a cut. Before you send the release on as a new zip, bring the examples up to date and record the release they describe (`scripts/DOC-SNIPPETS.md`, "The release the examples describe").

   ```bash run=slow
   git add -A
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

   After a change, the check prints a note: `projection-report.json describes an earlier build`. That file is the summary of the last Neo4j load, and it now describes the release before your change. The note does not fail the check, and it does not mean the ontology is wrong. It goes away when you have loaded the stores and recorded the new load's report with `python pipeline.py record`. The runbook's section "Record the load's report in the release folder" runs that command.

10. Search your copy for text that the change made stale, and update each document that holds it. No check catches a copy of a sentence.
11. Load the stores with the runner, and read its last line. The release is done when the sync check reads `current` on every line.

    ```powershell run=first-run
    python -m kpi_store.runner
    ```

    ```text expect
    run <run ID>: cut, check, zip, volume, upload, notebook, report, fuseki, neo4j, enterprise, sync, summary
    ...
    sync: all <count> lines read current
    ...
    every step passed
    ```

    If the `enterprise` step stops because the database holds the earlier release, see step 4 of "A correction through the loop".

## Change a measure with the term-change form

A measure of `kpi` changes through a form and two commands. Nobody edits a table or a Turtle file. The form is the "Term change" tab of the HTML form and the "Term change" sheet of the workbook. `kpi-intake/README.md`, "The term change", says what it asks and who signs.

The commands start in the release folder. Keep the filled form and the proposals in a folder beside the release folder, never inside it: the apply command commits the release, and it refuses a release with files that are not committed. The example uses the folder `term-change` beside the release folder.

1. Fill in the form, and save it to that folder. The example asks for three changes to the measure Unit Utilization: the new name "Process Unit Utilization", the other name "unit capacity utilization", and a link to the process CM 1.1.1.1 Produce Demand Forecast. The Data Owner and the Architect sign it.

   The document test writes the form's answers file with this block. If you saved the file from the form, skip it.

   ```python run=term-change
   import json
   from pathlib import Path

   folder = Path("../term-change")
   folder.mkdir(exist_ok=True)
   measure = "https://w3id.org/mpc/ontology/modules/kpi/measure/unit-utilization"
   process = "https://w3id.org/mpc/ontology/process/CM-1-1-1-1"
   answers = {"T1": measure, "T2": "Process Unit Utilization", "T4": ["unit capacity utilization"], "T6": [process], "T8": "yes"}
   form = {"format": 1, "form": "term-change", "catalogue_version": "1.2", "kpi_name": "Unit Utilization",
           "request": {"number": "TC-2026-001", "date": "2026-11-19", "requester_role": "Data Owner", "invited": ""},
           "answers": answers,
           "sign_offs": {"data-owner": {"name": "A Data Owner", "date": "2026-11-19"},
                         "architect": {"name": "An Architect", "date": "2026-11-19"}},
           "consulted": {}, "example_of": "", "comment": ""}
   path = folder / "unit-utilization.term-change.json"
   path.write_text(json.dumps(form, indent=2) + "\n", encoding="utf-8")
   print("wrote", path.name)
   ```

   ```text expect
   wrote unit-utilization.term-change.json
   ```

2. Check the form. It must end with `the intake is complete and signed`. The check also refuses a change that does not fit the measure, such as an other name it already has.

   ```powershell run=term-change
   python -m kpi_store.intake check ../term-change/unit-utilization.term-change.json
   ```

   ```text expect
   Term change check: Unit Utilization
   ...
   Result: the intake is complete and signed.
   This check changes nothing in the ontology. The Architect turns a complete term change into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
   ```

3. Turn the form into a proposal. The command writes the folder `proposals/TC-2026-001` beside the form, named by the form's request number. It holds `change.kgcl` (the changes as KGCL lines), `approval.json` (the signatures, from the form) and `summary.txt`. It changes nothing in the ontology. Several forms in one command give one proposal each.

   ```powershell run=term-change
   python -m kpi_store.propose ../term-change/unit-utilization.term-change.json
   ```

   ```text expect
   wrote the proposal ../term-change/proposals/TC-2026-001: 3 changes, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

4. Read `summary.txt`. It says what changes, the route and who signed. The route comes from the changes: a new other name or a new process link is a minor, and a rename, a new definition or a removal is a patch. When the form's answer to T8 is "no" or "not sure", the route is a major, and the Ontology Owner must have signed the form.

   ```python run=term-change
   print(open("../term-change/proposals/TC-2026-001/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal TC-2026-001
   ...
   What changes:
     - Rename it from "Unit Utilization" to "Process Unit Utilization".
     - Add the other name "unit capacity utilization".
     - Link it to the process CM 1.1.1.1 Produce Demand Forecast.
   ...
   The route: minor. This is a minor: the changes add content, and the old meaning still holds.
   ...
   ```

5. Apply the proposal. The command refuses a proposal that lacks a signature, and two proposals that change the same field of the same measure. It then works on a temporary copy of the release: it changes the `kpi` tables, rebuilds the module, checks that the difference is exactly the proposal's lines, releases `kpi` and every module that depends on it, rebuilds the catalog, the projection manifest and the KPI intake pack, and runs the checks. Only when every step has passed does it write the release and commit it. If a step fails, the release is as it was, and the command says why. It took about 90 seconds on a Mac.

   ```powershell run=term-change
   python -m kpi_store.apply ../term-change/proposals/TC-2026-001
   ```

   ```text expect
   1 proposal to apply:
     TC-2026-001: minor, signed by Data Owner, Architect
   ...
     kpi 1.3.0 -> 1.4.0
   ...
   ... write the release
   Done. kpi is now 1.4.0 (minor), and 6 modules that depend on it took a new patch. The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

6. See the commit and the new version.

   ```powershell run=term-change
   git --no-pager log --oneline -1
   cd business_architecture/ontology/release
   python next_version.py current kpi
   ```

   ```text expect
   <commit> Apply the term change TC-2026-001: kpi 1.4.0
   1.4.0
   ```

7. Run the full check, as in "Before you change anything", step 3. Then load the stores with the runner, as in step 11 of "The release steps".

## Add a system or a table with the reference-item form

A new system or a new table goes in through a form and the same two commands as a term change. Nobody edits a table or a Turtle file. The form is the "Reference item" tab of the HTML form and the "Reference item" sheet of the workbook. `kpi-intake/README.md`, "The reference item", says what it asks and who signs.

The form adds two kinds of item:

- a system that a document names, such as an application. It goes into the `system` module.
- a table in Databricks that copies a table of a system (a replica). It goes into the `data-product` module.

The form refuses the other kinds it names, and says why each needs a specialist: a table built from other tables, a source document, a role and a data product.

The commands start in the release folder. Keep the filled form and the proposal in a folder beside the release folder, never inside it, as for a term change. The example uses the folder `reference-item` beside the release folder.

1. Fill in the form, and save it to that folder. The example adds a made-up system, Sample Scheduler, which the document of the pricing assets names. The Data Owner and the Architect sign it.

   The document test writes the form's answers file with this block. If you saved the file from the form, skip it.

   ```python run=reference-item
   import json
   from pathlib import Path

   folder = Path("../reference-item")
   folder.mkdir(exist_ok=True)
   source = "https://w3id.org/mpc/ontology/source/decision-owner-pricing-assets-2026-10-25"
   answers = {"R1": "Sample Scheduler", "R2": "system",
              "R3": "A made-up application that schedules the work of a made-up refinery, for this guide.",
              "R4": ["SSched"], "R5": "https://w3id.org/mpc/ontology/modules/system/kind/application", "R6": source}
   form = {"format": 1, "form": "reference-item", "catalogue_version": "1.2", "kpi_name": "Sample Scheduler",
           "request": {"number": "RI-2026-001", "date": "2026-11-19", "requester_role": "Data Owner", "invited": ""},
           "answers": answers,
           "sign_offs": {"data-owner": {"name": "A Data Owner", "date": "2026-11-19"},
                         "architect": {"name": "An Architect", "date": "2026-11-19"}},
           "consulted": {}, "example_of": "", "comment": ""}
   path = folder / "sample-scheduler.reference-item.json"
   path.write_text(json.dumps(form, indent=2) + "\n", encoding="utf-8")
   print("wrote", path.name)
   ```

   ```text expect
   wrote sample-scheduler.reference-item.json
   ```

2. Check the form. It must end with `the intake is complete and signed`. The check also refuses an item that does not fit the ontology, such as a name that a system has already.

   ```powershell run=reference-item
   python -m kpi_store.intake check ../reference-item/sample-scheduler.reference-item.json
   ```

   ```text expect
   Reference item check: Sample Scheduler
   ...
   Result: the intake is complete and signed.
   This check changes nothing in the ontology. The Architect turns a complete reference item into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
   ```

3. Turn the form into a proposal. The command writes the folder `proposals/RI-2026-001` beside the form, with `change.kgcl`, `approval.json` and `summary.txt`. It changes nothing in the ontology. A new item is always a minor.

   ```powershell run=reference-item
   python -m kpi_store.propose ../reference-item/sample-scheduler.reference-item.json
   ```

   ```text expect
   wrote the proposal ../reference-item/proposals/RI-2026-001: 6 changes, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

4. Read `summary.txt`. It says what the new item is, what it links to and who signed.

   ```python run=reference-item
   print(open("../reference-item/proposals/RI-2026-001/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal RI-2026-001
   ...
   What it adds:
     - A system named "Sample Scheduler".
     - Its definition: "A made-up application that schedules the work of a made-up refinery, for this guide."
     - The other name "SSched".
     - Its kind: Application.
   ...
   The route: minor. This is a minor: the changes add content, and the old meaning still holds.
   ...
   ```

5. Apply the proposal. The command works as it does for a term change, on the item's module: it adds the item's rows to the module's tables in a temporary copy of the release, rebuilds the module, checks that the difference is exactly the proposal's lines, releases the module and every module that depends on it, and runs the checks. Only when every step has passed does it write the release and commit it. It also keeps the proposal's lines beside the approval record, as `approvals/RI-2026-001.kgcl`. If a step fails, the release is as it was.

   ```powershell run=reference-item
   python -m kpi_store.apply ../reference-item/proposals/RI-2026-001
   ```

   ```text expect
   1 proposal to apply:
     RI-2026-001: minor, signed by Data Owner, Architect
   ...
     system 1.5.0 -> 1.6.0
   ...
   ... write the release
   Done. system is now 1.6.0 (minor), and 7 modules that depend on it took a new patch. The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

6. See the commit and the new version.

   ```powershell run=reference-item
   git --no-pager log --oneline -1
   cd business_architecture/ontology/release
   python next_version.py current system
   ```

   ```text expect
   <commit> Apply the reference item RI-2026-001: system 1.6.0
   1.6.0
   ```

7. Run the full check, as in "Before you change anything", step 3. Then load the stores with the runner, as in step 11 of "The release steps".

A table goes the same way. Its form names the table's full name in R1 (for example `synapse_dev.replica_mips.mips_sample`), "table" in R2, the system whose table it copies in R8 and the document that records it in R9. The apply then releases the `data-product` module.

## Add a KPI with the KPI intake form

A new KPI goes in through the KPI intake form and the same two commands as a term change. Nobody edits a table or a Turtle file. The form is the "KPI intake" tab of the HTML form and the KPI sheets of the workbook. `kpi-intake/README.md` says what it asks and who signs.

The proposal of a new KPI holds two files of changes. `change.kgcl` holds what KGCL can say: the KPI's name, definition, other names, kind, source, roles, processes and the measures it is mistaken for. `facts.csv` holds the text facts that KGCL cannot write, one row each, with the columns measure, property and value: how it is worked out, how often it is stated, what it is compared against, why it has its kind, and the like. On kgcl-schema 0.7.0 a quoted text in a KGCL line about a link loses its quotes, so these facts have no KGCL line (KPI-DEC-0004). The apply writes both, checks both against the rebuilt module, and gives the KPI its identifier, the next free `KPI-` or `OPM-` number.

One proposal holds every module the form changes, and one apply releases them all:

- `kpi`: the KPI, and what it counts and leaves out (2.3, 2.4), which ship in the `kpi` package as its population. Each measure that 5.2 names as mistaken for it gains a sentence at the end of its own scope note, which names the new KPI.
- `value-stream`: a link from each value stream step of 6.3 to the KPI, with how the step uses it (6.4) and the document that says so (6.5). The apply writes each link into the step's list in `business_architecture/business_process/value_stream_*.json`, which the module's builder reads.
- `data-product`: the view of 7.1 serves the KPI, and the assistant of 7.8 answers from that view. The propose command checks that 6.6 names the data product the view is part of.

Each changed module takes its own minor, and every module that depends on one takes a patch, once. The apply compares each rebuilt module with the proposal's lines and facts, and makes one commit. Two answers stay in the form's file, and `summary.txt` says so: the market series of 6.7, which the form does not collect, and 7.7, for which the ontology has no property yet.

The propose command refuses a form that the modules cannot take as they stand, and says why:

- a name or an other name that a measure has already. A change to that measure goes through the term-change form;
- a role in 6.1 that is not one of the four planning personas, the only roles the `kpi` module records today;
- a view in 7.1 that the ontology does not hold, a table that is not a metric view, or an assistant in 7.8 that the `data-product` module does not hold. A new view or assistant needs a specialist, as the reference-item form says of a table built from other tables;
- when 7.1 names a view, a data product in 6.6 other than the one that view is part of, or one that the ontology does not hold;
- an assistant in 7.8 when 7.1 names no view for it to answer from;
- a step in 6.3 that the ontology does not hold. A new value stream step goes to the process map request;
- 2.4 without 2.3, because a population says what the KPI counts before what it leaves out;
- more than one document in 3.5, or a document that 3.5 does not offer and `kpi/measure-sources.csv` does not hold. A new source document needs a specialist, because its evidence tier is in the `integration` module. A document that 3.5 offers is in the ontology already, with its title and its tier: when `kpi/measure-sources.csv` has no row for it yet, the apply adds one, with that title.

The commands start in the release folder. Keep the filled form and the proposal in a folder beside the release folder, never inside it, as for a term change. The example uses the folder `new-kpi` beside the release folder.

1. Fill in the form, and save it to that folder. The example starts from the shipped example Crack Spreads Pricing and gives it a made-up name, Sample Spread Margin, a definition and an other name of its own, so it is a new measure. It also leaves out the example's answer to 3.6, which is about the measure the example copies. The Data Owner, the Domain Owner and the Architect sign it.

   The document test writes the form's answers file with this block. If you saved the file from the form, skip it.

   ```python run=new-kpi
   import json
   from pathlib import Path

   folder = Path("../new-kpi")
   folder.mkdir(exist_ok=True)
   form = json.loads(Path("kpi-intake/examples/crack-spreads-pricing.json").read_text(encoding="utf-8"))
   answers = form["answers"]
   answers["2.1"] = form["kpi_name"] = "Sample Spread Margin"
   answers["2.2"] = "A made-up market margin for this guide: a product's price less the price of the crude it is made from."
   answers["5.1"] = ["sample spread"]
   del answers["3.6"]
   form["example_of"], form["comment"] = "", ""
   form["request"] = {"number": "NK-2026-001", "date": "2026-11-19", "requester_role": "Data Owner", "invited": ""}
   form["sign_offs"] = {"data-owner": {"name": "A Data Owner", "date": "2026-11-19"},
                        "domain-confirmation": {"name": "A Domain Owner", "date": "2026-11-19"},
                        "architect": {"name": "An Architect", "date": "2026-11-19"}}
   path = folder / "sample-spread-margin.kpi-intake.json"
   path.write_text(json.dumps(form, indent=2) + "\n", encoding="utf-8")
   print("wrote", path.name)
   ```

   ```text expect
   wrote sample-spread-margin.kpi-intake.json
   ```

2. Check the form. It must end with `the intake is complete and signed`.

   ```powershell run=new-kpi
   python -m kpi_store.intake check ../new-kpi/sample-spread-margin.kpi-intake.json
   ```

   ```text expect
   KPI intake check: Sample Spread Margin
   ...
   Kind of measure: market indicator (decided by 4.3, test 3).
   ...
     The name is new, and the chosen process agrees with the business area.
   ...
   Result: the intake is complete and signed.
   This check changes nothing in the ontology. The Architect turns a complete KPI intake into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
   ```

3. Turn the form into a proposal. The command writes the folder `proposals/NK-2026-001` beside the form, with `change.kgcl`, `facts.csv`, `approval.json` and `summary.txt`. It changes nothing in the ontology. A new KPI is always a minor.

   ```powershell run=new-kpi
   python -m kpi_store.propose ../new-kpi/sample-spread-margin.kpi-intake.json
   ```

   ```text expect
   wrote the proposal ../new-kpi/proposals/NK-2026-001: 19 changes and 17 facts, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

4. Read `summary.txt`. It says what the new KPI is, what it links to in each module, its facts, the modules it reaches, what the Architect must still do outside the form, and who signed.

   ```python run=new-kpi
   print(open("../new-kpi/proposals/NK-2026-001/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal NK-2026-001
   ...
   What it adds, as KGCL lines in change.kgcl:
     - A measure named "Sample Spread Margin".
     - Its definition: "A made-up market margin for this guide: a product's price less the price of the crude it is made from."
     - The other name "sample spread".
     - Its kind: market indicator.
   ...
   What it adds, as facts in facts.csv (KGCL cannot write them):
     - A strong candidate to become a KPI: false.
     - The test that decided its kind: 3.
   ...
   Its identifier: the apply gives it the next free OPM- number.

   The changes reach these modules: kpi (minor), data-product (minor), value-stream (minor).

   For the Architect: 6.7 is yes. The market-data module needs the KPI's named series, which this form does not collect. Model them in market-data, as the check's routing says.

   The route: minor. This is a minor: the changes add content, and the old meaning still holds.
   ...
   ```

5. Apply the proposal. The command works as it does for a term change, on each module the proposal changes: in a temporary copy of the release it adds the KPI's rows to the `kpi` tables, its population, its value stream links and its view's row, rebuilds `kpi`, `data-product` and `value-stream`, checks that each module's difference is exactly the proposal's lines and facts, releases each changed module at its own minor and gives every module that depends on them a patch, rebuilds the catalog, the projection manifest and the KPI intake pack, and runs the checks. Only when every step has passed does it write the release and commit it. It keeps the proposal's lines and facts beside the approval record, as `approvals/NK-2026-001.kgcl` and `approvals/NK-2026-001.facts.csv`. If a step fails, the release is as it was. It took about 100 seconds on a Mac.

   ```powershell run=new-kpi
   python -m kpi_store.apply ../new-kpi/proposals/NK-2026-001
   ```

   ```text expect
   1 proposal to apply:
     NK-2026-001: minor, signed by Data Owner, Domain Owner, Architect
   ...
     kpi 1.3.0 -> 1.4.0
     data-product 1.2.0 -> 1.3.0
   ...
     value-stream 1.2.0 -> 1.3.0
   ...
   ... write the release
   Done. kpi is now 1.4.0, data-product 1.3.0 and value-stream 1.3.0 (minor), and 4 modules that depend on them took a new patch. The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

6. See the commit, the new version and the KPI's identifier.

   ```powershell run=new-kpi
   git --no-pager log --oneline -1
   cd business_architecture/ontology/release
   python next_version.py current kpi
   cd ../kpi
   python -c "print(open('measure-identifiers.csv', encoding='utf-8').read().splitlines()[-1])"
   ```

   ```text expect
   <commit> Apply the new KPI NK-2026-001: kpi 1.4.0, data-product 1.3.0, value-stream 1.3.0
   1.4.0
   sample-spread-margin,OPM-0031
   ```

7. Run the full check, as in "Before you change anything", step 3. Then load the stores with the runner, as in step 11 of "The release steps".

## Activate a domain with the domain activation form

A data domain becomes active through a form and the same two commands as a term change. Nobody edits `settings.toml` by hand. The form is the "Domain activation" tab of the HTML form and the "Domain activation" sheet of the workbook. `kpi-intake/README.md`, "The domain activation", says what it asks and who signs.

The ontology holds no list of domains. Question 1.5 of the KPI form reads the list in `kpi-intake/settings.toml`. So the apply changes that list and rebuilds the forms, and no module of the ontology changes. The proposal holds no KGCL line. Its `facts.csv` gives each field of the domain's entry that changes: `active`, the `description` from D2, and the `label` of a domain the list does not hold yet.

The commands start in the release folder. Keep the filled form and the proposal in a folder beside the release folder, never inside it, as for a term change. The example uses the folder `domain-activation` beside the release folder.

1. Fill in the form, and save it to that folder. The example is the shipped example `kpi-intake/examples/customer.domain-activation.json`. It activates Customer, a domain of the example list that is not active. Its people and documents are made up, and the Domain Owner and the Architect sign it.

   The document test copies the example to the folder with this block. If you saved the file from the form, skip it.

   ```python run=domain-activation
   import shutil
   from pathlib import Path

   folder = Path("../domain-activation")
   folder.mkdir(exist_ok=True)
   path = shutil.copy("kpi-intake/examples/customer.domain-activation.json", folder)
   print("copied", Path(path).name)
   ```

   ```text expect
   copied customer.domain-activation.json
   ```

2. Check the form. It must end with `the intake is complete and signed`.

   ```powershell run=domain-activation
   python -m kpi_store.intake check ../domain-activation/customer.domain-activation.json
   ```

   ```text expect
   Domain activation check: Customer
   ...
   Result: the intake is complete and signed.
   This check changes nothing in the ontology. The Architect turns a complete domain activation into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
   ```

3. Turn the form into a proposal. The command writes the folder `proposals/DA-2026-001` beside the form. It refuses a domain that is active already.

   ```powershell run=domain-activation
   python -m kpi_store.propose ../domain-activation/customer.domain-activation.json
   ```

   ```text expect
   wrote the proposal ../domain-activation/proposals/DA-2026-001: 2 facts, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

4. Read `summary.txt`. It says what changes and who signed.

   ```python run=domain-activation
   print(open("../domain-activation/proposals/DA-2026-001/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal DA-2026-001
   ...
   What changes:
     - The domain is in the list of domains, and is not active.
   ...
     - It becomes active, so the KPI form offers it in question 1.5.
   ...
   ```

5. Apply the proposal. The command refuses a proposal that lacks the Domain Owner's or the Architect's signature. It then works on a temporary copy of the release: it makes the domain active, checks that the list of domains differs by exactly the proposal's facts, and rebuilds and verifies the KPI intake pack. Only then does it write the release and commit it.

   ```powershell run=domain-activation
   python -m kpi_store.apply ../domain-activation/proposals/DA-2026-001
   ```

   ```text expect
   1 proposal to apply:
     DA-2026-001: minor, signed by Domain Owner, Architect
   ...
   No module of the ontology changes: the ontology holds no list of domains.
   ...
   ... write the release
   Done. The domain Customer is now active, and the KPI form offers it in question 1.5. The apply changed <count> files, and Git committed them.
   Run the full check: bash scripts/check.sh (on Windows, in Git Bash). No store needs loading: the ontology has not changed.
   ```

6. See the commit and the active domains.

   ```powershell run=domain-activation
   git --no-pager log --oneline -1
   python -c "import tomllib; print([d['label'] for d in tomllib.load(open('kpi-intake/settings.toml', 'rb'))['list']['domains'] if d['active']])"
   ```

   ```text expect
   <commit> Apply the domain activation DA-2026-001: Customer active
   ['Customer', 'Market Price', 'Financial Performance']
   ```

7. Run the full check, as in "Before you change anything", step 3. The KPI form now offers the domain in question 1.5.

## Add roles and RACI entries with the process map request

New roles, and new RACI entries for processes that the process map holds, go in through the process map request form and the same two commands. Nobody edits the process map or a table by hand. The form is the "Process map request" tab of the HTML form and the "Process map request" sheet of the workbook. `kpi-intake/README.md`, "The process map request", says what the propose command reads and who signs.

The change is in the `organization` module. A new role becomes a row of `organization/roles.csv` and of `organization/role-register.csv`. A RACI entry becomes the role's name in one of the four lists of the process's `raci` object in `business_architecture/business_process/downstream_process_map.json`. `change.kgcl` holds each new role and the three links of each assignment. `facts.csv` holds each new role's note and the role's name as each entry gives it. The figures in `organization/test_roles.py` leave out what the form added, as the figures in the other modules' tests do.

A new business area, process or step goes in through the same form, with a release of `core`: see "Add a process, a step or a business area with the process map request".

The commands start in the release folder. Keep the filled form and the proposal in a folder beside the release folder, never inside it. The example uses the folder `process-map-request` beside the release folder.

1. Fill in the form, and save it to that folder. The example is the shipped example `kpi-intake/examples/sample-pricing-coordinator.process-map-request.json`. It adds a made-up role, Sample Pricing Coordinator. The role is responsible for CM 1.1.2.1 Model and System Maintenance and accountable for CM 1.1.2 Regional Optimization. The Global Process Owner and the Architect sign it.

   The document test copies the example to the folder with this block. If you saved the file from the form, skip it.

   ```python run=process-map-request
   import shutil
   from pathlib import Path

   folder = Path("../process-map-request")
   folder.mkdir(exist_ok=True)
   path = shutil.copy("kpi-intake/examples/sample-pricing-coordinator.process-map-request.json", folder)
   print("copied", Path(path).name)
   ```

   ```text expect
   copied sample-pricing-coordinator.process-map-request.json
   ```

2. Check the form. It must end with `the intake is complete and signed`.

   ```powershell run=process-map-request
   python -m kpi_store.intake check ../process-map-request/sample-pricing-coordinator.process-map-request.json
   ```

   ```text expect
   Process map request check: Sample Pricing Coordinator
   ...
   Result: the intake is complete and signed.
   This check changes nothing in the ontology. The Architect turns a complete process map request into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
   ```

3. Turn the form into a proposal. The command writes the folder `proposals/PM-2026-001` beside the form.

   ```powershell run=process-map-request
   python -m kpi_store.propose ../process-map-request/sample-pricing-coordinator.process-map-request.json
   ```

   ```text expect
   wrote the proposal ../process-map-request/proposals/PM-2026-001: 8 changes and 3 facts, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

4. Read `summary.txt`. It names the new role and each RACI entry.

   ```python run=process-map-request
   print(open("../process-map-request/proposals/PM-2026-001/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal PM-2026-001
   ...
   What it adds:
     - A new role named "Sample Pricing Coordinator" (role:sample-pricing-coordinator), a position.
       Its definition: "A made-up role that coordinates the daily price updates of one region."
     - A RACI entry: "Sample Pricing Coordinator" is responsible for the process CM 1.1.2.1 Model and System Maintenance.
     - A RACI entry: "Sample Pricing Coordinator" is accountable for the process CM 1.1.2 Regional Optimization.
   ...
   ```

5. Apply the proposal. The command refuses a proposal that lacks the Global Process Owner's or the Architect's signature. It then works on a temporary copy of the release. It writes the rows and the RACI entries, rebuilds the roles and the assignments, and checks that the difference is exactly the proposal's lines and facts. It releases `organization` and the modules that depend on it, rebuilds the catalog, the projection manifest and the KPI intake pack, and runs the checks. Only then does it write the release and commit it.

   ```powershell run=process-map-request
   python -m kpi_store.apply ../process-map-request/proposals/PM-2026-001
   ```

   ```text expect
   1 proposal to apply:
     PM-2026-001: minor, signed by Global Process Owner, Architect
   ...
     organization 2.2.0 -> 2.3.0
   ...
   ... write the release
   Done. organization is now 2.3.0 (minor), and 2 modules that depend on it took a new patch. The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

6. See the commit and the new version.

   ```powershell run=process-map-request
   git --no-pager log --oneline -1
   cd business_architecture/ontology/release
   python next_version.py current organization
   ```

   ```text expect
   <commit> Apply the process map request PM-2026-001: organization 2.3.0
   2.3.0
   ```

7. Run the full check, as in "Before you change anything", step 3. Then load the stores with the runner, as in step 11 of "The release steps". The forms list the new role after the apply's rebuild of the pack.

## Use AI to suggest answers (optional)

An AI can read a filled form before anyone signs it, and suggest clearer answers. It is off until the client's IT approves a provider. What the AI writes is only a suggestion: you accept or reject each one, the signers sign the answers as they then stand, and the propose command checks the form as it checks every form. The AI never applies anything. Without `--ai`, the propose command works exactly as the sections above say.

The AI reads the answers that people wrote in words, and the form's choices of a measure or a process. It also reads the names of what the release holds, such as its measures and its processes, so that it can say "this matches the measure Unit Utilization". Its instructions are the release's own skills, the files `skills/ontology/SKILL.md` and `skills/clear-writing/SKILL.md`, so the rules are the same whichever model the client picks. You never need to open them.

Each AI step leaves a record beside the form: the provider, the model and its version, the address it called, who approved the provider and when, each skill file with its SHA-256, the SHA-256 of the prompt, the SHA-256 of the AI's answer, and each suggestion with your choice. The record keeps no text of the prompt, because the prompt holds the form's answers before anyone signed them. The prompt's SHA-256 is that of the skills' text, a blank line and the task, which is exactly what the by-hand prompt file holds. The proposal keeps the record in `summary.txt` and in `approval.json`, and the apply command keeps it in the release's approval record.

### Choose the provider

The provider goes in the `[ai]` table of your local settings file, the file that `KPI_STORE_LOCAL` names. `kpi_store/stores.example.toml` shows the table, switched off. The client's IT chooses one provider and approves it once. Write who approved it in `approved_by`, and the date in `approved_on`. The command refuses AI until both are there. **Never write a key in the file.** Name the environment variable that holds the key in `key_env`.

| `provider` | What the command uses | What the table also needs |
|---|---|---|
| `databricks`, the usual choice | A model served in the client's Databricks workspace, so the form stays with the client | `model`: the name of the serving endpoint. `profile`: the Databricks configuration profile you signed in with (`databricks auth login`) |
| `anthropic` | The Anthropic Messages API | `model` and `key_env` |
| `openai` | OpenAI chat completions | `model` and `key_env` |
| `by-hand` | No call. The command writes the prompt to a file, you give it to an assistant such as Genie Code, and you save its answer to a file | `assistant`: its name, such as `"Genie Code"` |

A table for a model served in Databricks looks like this:

```toml parse
[ai]
provider = "databricks"
model = "kpi-suggestions"
profile = "DEFAULT"
approved_by = "An IT Approver"
approved_on = "2026-11-20"
```

### Use Genie Code as the assistant

Genie Code is the assistant in the Databricks workspace. It follows Agent Skills, and the release's `skills` folder holds such skills. The prompt file already holds the text of the two skills the AI follows, so any assistant works. To give Genie Code the skills' reference files too, register the folder once. The Databricks page "Extend Genie Code with agent skills" (https://docs.databricks.com/aws/en/genie-code/skills, section "Add skills from another folder", last updated 2026-11-18) gives these steps:

1. Put the release's `skills` folder in a workspace folder that you can read, such as a Databricks Git folder.
2. In Genie Code, click **Customizations**, then **Skills**.
3. Click **New**, then **Add from workspace folder**.
4. Choose the `skills` folder itself: the folder that holds `ontology` and `clear-writing`, not one of them.

### A worked example, by hand

The example asks for suggestions on a term change of the measure Unit Utilization. Its requester wrote the new name as "process unit utilisation" and a new other name as "unit cap util". The commands start in the release folder. Keep the form, the settings and the AI's files in a folder beside the release folder. The example uses the folder `ai-suggestions`.

1. Fill in the form and save it, but do not sign it yet. Add the `[ai]` table to your local settings file.

   The document test writes the form and a settings file that holds only the `[ai]` table, with this block. If you saved the form from the HTML form, skip it, and name your own settings file in the commands below.

   ```python run=ai-suggestions
   import json
   from pathlib import Path

   folder = Path("../ai-suggestions")
   folder.mkdir(exist_ok=True)
   measure = "https://w3id.org/mpc/ontology/modules/kpi/measure/unit-utilization"
   answers = {"T1": measure, "T2": "process unit utilisation", "T4": ["unit cap util"], "T8": "yes"}
   form = {"format": 1, "form": "term-change", "catalogue_version": "1.2", "kpi_name": "Unit Utilization",
           "request": {"number": "TC-2026-002", "date": "2026-11-20", "requester_role": "Data Owner", "invited": ""},
           "answers": answers, "sign_offs": {}, "consulted": {}, "example_of": "", "comment": ""}
   (folder / "unit-utilization.term-change.json").write_text(json.dumps(form, indent=2) + "\n", encoding="utf-8")
   settings = ['[ai]', 'provider = "by-hand"', 'assistant = "Genie Code"', 'approved_by = "An IT Approver"',
               'approved_on = "2026-11-20"']
   (folder / "kpi-store-local.toml").write_text("\n".join(settings) + "\n", encoding="utf-8")
   print("wrote the form and the settings")
   ```

   ```text expect
   wrote the form and the settings
   ```

2. Ask for suggestions. With the by-hand provider, the command writes the prompt to a file and stops. It refuses a form that anyone has signed.

   ```powershell run=ai-suggestions
   python -m kpi_store.propose --ai ../ai-suggestions/unit-utilization.term-change.json --stores ../ai-suggestions/kpi-store-local.toml
   ```

   ```text expect
   wrote the prompt for the AI: ../ai-suggestions/unit-utilization.term-change.ai-prompt.txt
   Give that file to Genie Code. Save its answer, the JSON it writes, in a file such as ../ai-suggestions/unit-utilization.term-change.ai-answer.json. Then run this command again with --ai-answer <that file>.
   ```

3. Give the prompt file to the assistant. Save its answer, the JSON it writes, as `unit-utilization.term-change.ai-answer.json` in the same folder.

   The document test copies the release's sample answer, which is made up, with this block.

   ```powershell run=ai-suggestions status-only
   python -c "import shutil; shutil.copy('kpi_store/ai/sample-answer.json', '../ai-suggestions/unit-utilization.term-change.ai-answer.json')"
   ```

4. Run the command again with the answer. It checks the answer strictly, and refuses the whole answer if it is not the JSON the prompt asks for. It then shows each suggestion and asks you to accept it or not. The example accepts the new name and rejects the other name, so you type `yes`, then `no`. To give the choices from a file instead, add `--ai-choices <file>`, where the file holds `{"T2": "yes", "T4": "no"}`. The command writes each accepted answer into the form, and the record of the AI step beside it.

   ```powershell run=ai-suggestions types="yes,no"
   python -m kpi_store.propose --ai ../ai-suggestions/unit-utilization.term-change.json --stores ../ai-suggestions/kpi-store-local.toml --ai-answer ../ai-suggestions/unit-utilization.term-change.ai-answer.json
   ```

   ```text expect
   read the answer of Genie Code from ../ai-suggestions/unit-utilization.term-change.ai-answer.json
   the AI suggested 2 changes
   Suggestion 1 of 2, for T2: What should the measure be called from now on? Leave this empty to keep its name.
     The answer now: "process unit utilisation"
     The suggestion: "Process Unit Utilization"
     Why: The release writes the names of its measures with capital initials and US spelling, as the measure Unit Utilization shows.
   Accept this suggestion? Type yes or no: Suggestion 2 of 2, for T4: Which other names should it gain?
     The answer now: ["unit cap util"]
     The suggestion: ["unit capacity utilization"]
     Why: An other name works best when it is the words people say in full, so a search finds it.
   Accept this suggestion? Type yes or no: accepted 1 of 2 suggestions; wrote it into unit-utilization.term-change.json
   wrote the record of the AI step: ../ai-suggestions/unit-utilization.term-change.ai.json
   Next: the signers read the form as it now stands and sign it. Then turn it into a proposal with: python -m kpi_store.propose ../ai-suggestions/unit-utilization.term-change.json
   ```

   With the `databricks`, `anthropic` or `openai` provider, step 2 asks the AI itself and goes straight on to the suggestions, so there is no prompt file and no `--ai-answer`.

5. The signers load the form in the HTML form ("Load answers file"), read the answers as they now stand, sign, and save it. The Data Owner and the Architect sign this one.

   The document test signs the form with this block.

   ```python run=ai-suggestions
   import json
   from pathlib import Path

   path = Path("../ai-suggestions/unit-utilization.term-change.json")
   form = json.loads(path.read_text(encoding="utf-8"))
   form["sign_offs"] = {"data-owner": {"name": "A Data Owner", "date": "2026-11-20"},
                        "architect": {"name": "An Architect", "date": "2026-11-20"}}
   path.write_text(json.dumps(form, indent=2) + "\n", encoding="utf-8")
   print("signed", form["answers"]["T2"])
   ```

   ```text expect
   signed Process Unit Utilization
   ```

6. Turn the signed form into a proposal, as for any form. The command finds the record beside the form and keeps it.

   ```powershell run=ai-suggestions
   python -m kpi_store.propose ../ai-suggestions/unit-utilization.term-change.json
   ```

   ```text expect
   wrote the proposal ../ai-suggestions/proposals/TC-2026-002: 2 changes, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

7. Read `summary.txt`. It lists each suggestion, your choice, and whether the signed form still holds an accepted answer.

   ```python run=ai-suggestions
   print(open("../ai-suggestions/proposals/TC-2026-002/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal TC-2026-002
   ...
     - Rename it from "Unit Utilization" to "Process Unit Utilization".
     - Add the other name "unit cap util".
   ...
   AI suggestions: Genie Code was asked on <date>, with the provider approved by An IT Approver on 2026-11-20.
     - T2, accepted (the signed form holds it): "Process Unit Utilization". Why: The release writes the names of its measures with capital initials and US spelling, as the measure Unit Utilization shows.
     - T4, rejected: ["unit capacity utilization"]. Why: An other name works best when it is the words people say in full, so a search finds it.
     The whole record, with its fingerprints, is in approval.json under "ai".
   ...
   ```

You are done when the proposal's `summary.txt` lists each AI suggestion with your choice, and its `approval.json` holds the record under `"ai"`. Then apply the proposal as the section for its form says.

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

### A new role or a new system

A role and a system are rows in tables. Neither needs a change to `vocabulary.ttl` or `shapes.ttl`, so steps 1 to 3 above do not apply. Both are a minor.

A new role that a process names in its RACI goes in with the process map request form: see "Add roles and RACI entries with the process map request". The steps below are for any other role.

A role is in two tables of `business_architecture\ontology\organization`.

1. Add the role's row to `roles.csv`: its `slug`, its `label`, its `kind` (`position` or `team`), its `definition` and a `note` that names its source.
2. Add the role's name to `role-register.csv`, as the process map spells it, with the role's `slug`.
3. Check that a RACI list of the process map names the role. The build refuses a role that no process names. For a role that no process names yet, start with "Change the RACI", which has every step and a worked example.
4. Change the figures in `test_roles.py`, then run `python build_roles.py --write` and `python build_assignments.py --write`.

A system is in the tables of `business_architecture\ontology\system`. A system that a document names, and not the process map, goes in with the reference-item form: see "Add a system or a table with the reference-item form". The steps below are for a system the process map names, or one that cites a new source.

1. For a system that the process map names in a `systems` field, add its row to `systems.csv` and its name to `register.csv`.
2. For a system that another source names, such as SharePoint, add its row to `other-systems.csv`, with the key of that source in `named_by`.
3. Add the system's definition to `definitions.csv`, with the keys of its sources. A system that the process map does not name must have a definition.
4. A source that is new to the module is a row in `sources.csv`: its key, its title and its tier. Give the source the same tier in `authority\source-tiers.csv`. That table is part of `integration`, so the new row means a minor version of `integration` after `system`.
5. Change the figures in `test_systems.py`: `test_figures` and `test_definitions`. Then run `python build_systems.py --write`.

Then follow "The release steps" from step 3.

### A report row that needs a minor version

The cut tool leaves four kinds of accepted rows, and lists each as "needs a minor version". Each goes in by the steps above.

| Row | Module | What to add |
|---|---|---|
| `measure-link` | `data-product` | A property for the filter, in `vocabulary.ttl` and `shapes.ttl`, and the link with its filter in the module's tables. The Genie space's creator confirms each filter first. Take the change through the `ontology` skill's gates. |
| `migration-pair` | `technical-graph` | The table that a Databricks table replaces. |
| A new object, from an `object-extra` row you accepted | `data-product` | A row in `data-product/pricing/tables.csv`, and its lineage in `lineage.csv`. |
| A new table edge, from a `question` row | `data-product` | A row in `data-product/pricing/lineage.csv`. |

## The worked examples of the next five sections

The next five sections each end with a worked example on made-up data. One helper, `release/update_examples.py`, makes the hand edits of each example. These are the rows, the terms, the shapes and the figures in the tests. The commands after the helper are the ones you run for a real change. Read the helper's functions as the pattern for your own change. It has one function for each file.

**Run an example in a copy of the release, never in the folder you load the stores from.** Use a fresh copy for each example, because two examples may change the same module.

The examples are made for KPI Store 1.1 as shipped. The helper looks for the exact text it changes. In a release that has moved on, a file may no longer hold that text. The helper then stops with a line that starts `refused:`, names the file and changes nothing, with `--plan` and with `--write`. It also refuses a copy that holds the example already, and a file or a folder that is a link, a hard link included. It does not lock the copy, so let no other program change the copy while the helper runs. The steps above each example still hold for a release that has moved on. Only the example's own figures and versions are those of the release as shipped. No example is your organisation's answer. Your business says which role replaces a role, what kind a system is, what class a catalog entry has, who is responsible for a process and what the domains are.

Five things hold in all five sections.

- The module's tests state its figures by hand. A test file such as `organization/test_roles.py` says how many terms of each kind the module holds, for example 3 deprecated roles and 57 live ones. A real change moves those figures, and the test fails until you change the figure in the test. That is on purpose. The figure in the test comes from the decision, and the build must agree with it. Each example's plan names the test file it changes.
- A change to a file in `business_architecture\business_process` starts as a proposal. The process map and the portfolio file are there. Write the change as a file in the folder `proposals` beside them, in the form of `MPC-P12-shared-process-names.md`. It states the gap, the proposal, and how the ontology takes it. Change the file only after your ontology owner has accepted the proposal.
- One test fails after a release that leaves `data-product` at its version. A release of `organization` gives `integration` a new version and leaves `data-product` as it is. The cut tool's tests cut the versions of the release as shipped, so they are then skipped, and one test fails to say so. Add its name as a new last line of `scripts/pinned-tests.txt`. The name is `kpi_store/tests/test_cut.py::test_the_baseline_is_this_trees_or_data_product_has_moved_on`. The line says that your copy has moved on from the release as shipped. The two examples that release `organization` add it.
- After a release, the full check reads the documents' examples and runs none. Step 9 of "The release steps" says why, and what to do before you send the release on.
- The document test follows the five examples in one Git copy, one after another. Before each example it puts the copy back to the release as shipped, with the first block of the example. **That block throws away every change in the folder.** Skip it in a fresh copy, and never run it in a folder that holds work you want to keep.

## Deprecate a term

Use this when the business says that a term is no longer used, or that two terms are one. Use it also to replace a role by one other role in every RACI entry that names it. Never delete the term. Mark it deprecated, name the term that replaces it, and keep everything it has. A deprecation is a major release, because an answer that named the term is no longer current. The ontology owner approves it.

The steps are for a role. This release leaves one such case open, whether "Black Oil Manager" is a real role (`KNOWN-OPEN-ITEMS.md`, item 2). The paragraph after the steps says what differs in other modules.

1. Ask the business two questions. Is the role real? If it is not, which role does its work? The second answer names the successor.
2. Save the answer as the approval, as step 3 of "The release steps" says.
3. Open `business_architecture\ontology\organization\roles.csv` and find the role's row. The row of Black Oil Manager starts `black-oil-manager`.
4. In that row, set `replaced_by` to the `slug` of the successor.
5. Set `replaced_label_kind` to `alt`. The successor then takes the old name as an alternative label. Write `hidden` only when the old name is a misspelling.
6. Write in `note` why the role is deprecated and who said so. Start with "Deprecated:", as the three deprecated roles of this release do. Search the file for `rcvo-advisor` to see one.
7. Leave the role's `slug` and `label`, its row in `role-register.csv` and the process map as they are. **Do not rewrite the role's name in the process map.** The process map keeps the name its source uses, the register still maps that name to the role, and the build gives each of its assignments to the successor. If you rewrite the name, the build stops with `register row ... is not in the source`. If you then remove the register row, it stops with `role ... is not used by the register`.
8. Change the figures in `organization\test_roles.py`. `test_the_figures_match_the_decision_record` states the count of deprecated and live roles. `test_the_answers_point_the_right_way` lists each deprecated role with its successor.
9. Rebuild the roles, then the assignments, from the folder `organization`. The commands are `python build_roles.py --write` and `python build_assignments.py --write`.
10. Release `organization` as a major, with "The release steps" from step 5. Write `major` and the next major version in `start`. The cascade gives `integration` and `ref-mpc` a patch each.
11. Add the line to `scripts/pinned-tests.txt` that "The worked examples of the next five sections" names.
12. Follow "The release steps" from step 7 to the end.

The builders do the rest.

- The role keeps its IRI and every triple it had. It gains `owl:deprecated true` and `dcterms:isReplacedBy` with its successor. The successor gains the old name as a label.
- Each assignment of the role keeps its IRI and its source text, and now names the successor. The shapes reject an assignment that names a deprecated role. The ledger `raci-conservation.csv` counts the moved assignments in its last line.
- The role register still reconciles with the process map. The build fails if the process map names a role text that the register lacks, or the register holds a role that no text names.
- The competency questions answer as before. Question 5 now gives the successor wherever the deprecated role was named.

The intake form keeps a deprecated role in its list of roles, with "(deprecated)" after the name, and still offers it. To stop offering it, name the role under `hide` in `[pick_list.roles]` of `kpi-intake/settings.toml`. This release hides Black Oil Manager already, and that line still holds after the deprecation, because `hide` takes the role's name with or without the mark. The check of a filled form that names a deprecated role says so, and asks for the term that replaced it.

**This release cannot deprecate a role that has no successor.** The builder marks a role as deprecated only through `replaced_by`, and every assignment must name a live role. If the business says that nobody does the role's work, the entry in the process map is wrong, and "Change the RACI" says how to change it. The builder then refuses the role, because no text of the process map names it. Until the builder can write such a role, keep the role as it is and hide it in the form.

In another module, look first at how its builder writes a deprecated term. Search the module's builder for `deprecated`. In this release the builders of `organization`, `party` and `core` write one. A module whose builder cannot needs that change to the builder first, with a test.

### A worked example: the role Black Oil Manager is deprecated

The example pretends that the business gave this answer: the Asphalt Manager does the work of the Black Oil Manager. **The answer is made up.** `organization` 2.2.0 becomes 3.0.0.

The commands start in the top folder of the copy.

1. Start from a copy of the release as shipped. The document test puts its copy back with this block. In a fresh copy, skip it.

   ```powershell run=slow status-only
   git reset -q --hard
   git clean -q -fd
   ```

2. List the files the example changes. This changes nothing.

   ```powershell run=slow
   cd business_architecture/ontology/release
   python update_examples.py deprecate-role --plan
   ```

   ```text expect
   would change business_architecture/ontology/organization/roles.csv
   would change business_architecture/ontology/organization/test_roles.py
   would change scripts/pinned-tests.txt
   would change business_architecture/ontology/approvals/example-deprecate-role.md
   ```

3. Make the hand edits of steps 2 to 8 and of step 11 above.

   ```powershell run=slow
   python update_examples.py deprecate-role --write
   ```

   ```text expect
   changed business_architecture/ontology/organization/roles.csv
   ...
   Now build: cd ../organization, then build_roles.py --write and build_assignments.py --write. HOW-TO-UPDATE.md has the steps after it.
   ```

4. Rebuild the roles and the assignments. The first line counts 4 deprecated roles, one more than before. The count of entries and of role names is the same as before, because the process map has not changed. The third line ends with 13 moved assignments, which are the 3 of this release and the 10 of Black Oil Manager.

   ```powershell run=slow
   cd ../organization
   python build_roles.py --write
   python build_assignments.py --write
   ```

   ```text expect
   processes with RACI 153; RACI entries 913; distinct source strings 91; roles 60; positions 54; teams 6; deprecated roles 4; live roles 56; compound strings 11; role references after splitting 940
   wrote <the path of the roles file>
   processes with RACI in the source 153; RACI entries in the source 913; <the counts by level>; assignments moved to a successor role 13; SHACL conforms
   wrote assignments.ttl and raci-conservation.csv
   ```

5. Read the assignments. Every RACI entry that named Black Oil Manager is still there, with its text and its IRI, and now names Asphalt Manager. This is the whole of replacing a role in every entry that names it.

   ```powershell run=slow
   python -c "t = open('assignments.ttl', encoding='utf-8').read(); print(t.count('Black oil manager'), 'assignments keep the text Black oil manager;', t.count('--black-oil-manager--'), 'keep their IRI;', t.count('assignedRole role:black-oil-manager '), 'name the deprecated role')"
   ```

   ```text expect
   10 assignments keep the text Black oil manager; 10 keep their IRI; 0 name the deprecated role
   ```

6. Set the new version, write the package and release the modules that depend on it.

   ```powershell run=slow
   cd ../release
   python next_version.py start organization 3.0.0 major --why "Deprecates the role Black Oil Manager into Asphalt Manager." --approver "The ontology owner" --where "approvals/example-deprecate-role.md" --words "Approved as a major: Black Oil Manager is deprecated into Asphalt Manager."
   python build_module.py organization --write
   python next_version.py cascade organization --approver "The ontology owner" --where "approvals/example-deprecate-role.md" --words "Approved as a major: Black Oil Manager is deprecated into Asphalt Manager."
   ```

   ```text expect
   organization is set to 3.0.0. Now run: python3 build_module.py organization --write
   organization 3.0.0: <count> triples; shapes conform
   wrote <the path of the new package>
   integration is set to 2.5.1. Now run: python3 build_module.py integration --write
   ref-mpc is set to 1.3.1. Now run: python3 build_module.py ref-mpc --write
   organization 2.2.0 moved to releases/previous/; the projection's lists name 3.0.0
   integration 2.5.0 moved to releases/previous/; the projection's lists name 2.5.1
   ref-mpc 1.3.0 moved to releases/previous/; the projection's lists name 1.3.1
   3 modules released. Now rebuild the catalog and the projection manifest, and run the check.
   ```

7. Rebuild the catalog, the projection manifest, the competency questions, the KPI intake pack and the pages.

   ```powershell run=slow
   python build_catalog.py --write
   cd ../projection
   python pipeline.py build
   cd ../regression
   python run.py
   cd ../../..
   python -m kpi_store.intake build
   python scripts/build_docs_html.py
   ```

   ```text expect
   catalog: 13 releases from 13 packages
   ...
   competency coverage on <the core package>: 57 questions; answerable 56, partial 0, waiting 0, parked 1
   wrote kpi-intake/pick-lists.json
   ...
   ```

8. Read the role's entry in the form's list. It carries the mark, and the form's settings still hide it.

   ```powershell run=slow
   python -c "import json; print([(r['label'], r.get('hidden', False)) for r in json.load(open('kpi-intake/pick-lists.json', encoding='utf-8'))['lists']['roles'] if 'Black Oil' in r['label']])"
   ```

   ```text expect
   [('Black Oil Manager (deprecated)', True)]
   ```

9. Run the helper again. It refuses a copy that holds the example, and changes nothing.

   ```powershell run=slow exit=1
   python business_architecture/ontology/release/update_examples.py deprecate-role --write
   ```

   ```text expect
   refused: this copy holds the example deprecate-role already; nothing was changed
   ```

10. Stage the change and run the full check. On Windows, run it in Git Bash.

    ```bash run=slow
    git add -A
    bash scripts/check.sh
    ```

    ```text expect
    ...
    all checks passed
    ```

## Change the kind of a term

Use this when a term is listed under the wrong kind. This release leaves the case of Databricks open. `system` lists it with the kind "application", and it is the data platform (`KNOWN-OPEN-ITEMS.md`, item 4).

"Kind" has two meanings here, and the steps differ.

- The first is the kind a module gives its terms. In `system`, the kind is a value of the code list `sys:SystemKind`, and the property `sys:systemKind` holds it. The list has three values, which are application, office tool and working document. The shape allows a system exactly one. So you replace the value. You never add a second one. The term keeps its IRI and its class, `sys:System`. The steps below are for this meaning.
- The second is the kind of thing a term is in the ontology. It is a concept, a class, a property, a value of a code list or a named real thing. One IRI has one of these, for good. If a term has the wrong one, add a new term of the right kind and deprecate the old one into it, with "Deprecate a term".

A changed kind is a major release when an answer given under the old kind is no longer right. After the Databricks change, the answer "Databricks is an application" is wrong, and the definitions that name the three kinds change too. So it is a major, and the ontology owner approves it.

1. Agree the kind with the ontology owner. If the list lacks it, agree the new value's name and its definition, with the source of the definition.
2. For a new value, open `business_architecture\ontology\system\vocabulary.ttl`. Add the value after `kind:document`, as a copy of those two lines with its own name, notation and definition.
3. In the same file, add the value to `skos:hasTopConcept` of `sys:SystemKind`.
4. In the same file, change each definition that names the kinds one by one. `sys:SystemKind` and `sys:systemKind` have such a definition.
5. In `system\shapes.ttl`, add the value to the `sh:in` list of `sys:systemKind`. The shape checks every system's kind against this list, so a value that is not in it fails the build.
6. In `system\build_systems.py`, add the value's notation to `KINDS`.
7. Change the system's row. A system that the process map names is in `system\systems.csv`. Any other system, such as Databricks, is in `system\other-systems.csv`. Set its `kind` to the value's notation.
8. Change the count of each kind in `test_figures`, in `system\test_systems.py`. Add a line to `test_kinds` that names the system and its kind.
9. Rebuild with `python build_systems.py --write`, from the folder `system`.
10. Release `system` as a major, with "The release steps" from step 3. The cascade gives seven modules a patch each. They are `data-product`, `party`, `logical-model`, `ref-mpc`, `technical-graph`, `value-stream` and `integration`.

Nothing outside `system` reads a system's kind in this release. The links from a platform table to a system, `dp:copiesSystem` and `dp:dependsOnSystem`, point at the system whatever its kind is. No competency question asks for the kind.

The intake form does not read the kind either. Question 7.4 offers every system of the module. So Databricks is still offered as a source system after this change, unless the form hides it. Keep it under `hide` in `[pick_list.systems]` of `kpi-intake/settings.toml`, where this release has it.

### A worked example: Databricks becomes a data platform

The example adds a fourth kind, "data platform", and gives it to Databricks. **The new kind's definition is made up.** `system` 1.5.0 becomes 2.0.0.

The commands start in the top folder of the copy.

1. Start from a copy of the release as shipped. The document test puts its copy back with this block. In a fresh copy, skip it.

   ```powershell run=slow status-only
   git reset -q --hard
   git clean -q -fd
   ```

2. List the files the example changes. This changes nothing.

   ```powershell run=slow
   cd business_architecture/ontology/release
   python update_examples.py system-kind --plan
   ```

   ```text expect
   would change business_architecture/ontology/system/vocabulary.ttl
   would change business_architecture/ontology/system/shapes.ttl
   would change business_architecture/ontology/system/build_systems.py
   would change business_architecture/ontology/system/other-systems.csv
   would change business_architecture/ontology/system/test_systems.py
   would change business_architecture/ontology/approvals/example-system-kind.md
   ```

3. Make the hand edits of steps 2 to 8 above, and write the approval.

   ```powershell run=slow
   python update_examples.py system-kind --write
   ```

   ```text expect
   changed business_architecture/ontology/system/vocabulary.ttl
   ...
   Now build: cd ../system, then build_systems.py --write. HOW-TO-UPDATE.md has the steps after it.
   ```

4. Rebuild the systems. The line counts 39 applications, one fewer than before, and 1 data platform.

   ```powershell run=slow
   cd ../system
   python build_systems.py --write
   ```

   ```text expect
   map strings 45; systems 49; defined 47; application 39; office-tool 4; document 5; data-platform 1; no-system strings 4; processes with a systems field 165; processes with a link 162; links 306; links waiting for a core release 0
   wrote <the path of the systems file>
   ```

5. Set the new version, write the package and release the modules that depend on it.

   ```powershell run=slow
   cd ../release
   python next_version.py start system 2.0.0 major --why "Adds the system kind data platform and gives it to Databricks." --approver "The ontology owner" --where "approvals/example-system-kind.md" --words "Approved as a major: the system kind data platform, and Databricks as a data platform."
   python build_module.py system --write
   python next_version.py cascade system --approver "The ontology owner" --where "approvals/example-system-kind.md" --words "Approved as a major: the system kind data platform, and Databricks as a data platform."
   ```

   ```text expect
   system is set to 2.0.0. Now run: python3 build_module.py system --write
   system 2.0.0: <count> triples; shapes conform
   wrote <the path of the new package>
   ...
   system 1.5.0 moved to releases/previous/; the projection's lists name 2.0.0
   data-product 1.2.0 moved to releases/previous/; the projection's lists name 1.2.1
   party 2.1.0 moved to releases/previous/; the projection's lists name 2.1.1
   logical-model 1.0.0 moved to releases/previous/; the projection's lists name 1.0.1
   ref-mpc 1.3.0 moved to releases/previous/; the projection's lists name 1.3.1
   technical-graph 1.1.0 moved to releases/previous/; the projection's lists name 1.1.1
   value-stream 1.2.0 moved to releases/previous/; the projection's lists name 1.2.1
   integration 2.5.0 moved to releases/previous/; the projection's lists name 2.5.1
   8 modules released. Now rebuild the catalog and the projection manifest, and run the check.
   ```

6. Rebuild the catalog, the projection manifest, the competency questions, the KPI intake pack and the pages.

   ```powershell run=slow
   python build_catalog.py --write
   cd ../projection
   python pipeline.py build
   cd ../regression
   python run.py
   cd ../../..
   python -m kpi_store.intake build
   python scripts/build_docs_html.py
   ```

   ```text expect
   catalog: 13 releases from 13 packages
   ...
   competency coverage on <the core package>: 57 questions; answerable 56, partial 0, waiting 0, parked 1
   wrote kpi-intake/pick-lists.json
   ...
   ```

7. Stage the change and run the full check. On Windows, run it in Git Bash.

   ```bash run=slow
   git add -A
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

## Move catalog entries to another class

Use this when entries of the data-product catalog are not data products. This release leaves that open for 36 of the 49 entries, which are functional areas or portfolios (`KNOWN-OPEN-ITEMS.md`, item 5).

The catalog is built from the portfolio file, `business_architecture\business_process\data_product_portfolio.json`. The file has 3 segments, 19 product lines and 49 entries in the lists it names `portfolios`. The builder gives each segment the class `dp:PortfolioSegment`, each line `dp:DataProductLine` and each entry `dp:DataProduct`. The module has no class for a portfolio or a functional area, and the builder cannot tell one entry from another. So this change has four parts. They are a proposal to the portfolio file, a class to move to, a change to the builder, and a release.

An entry that moves keeps its IRI, its name and its place in its line. It is the same thing under its right class, so it is not deprecated. A list of the data products no longer holds it, so the release is a major. The ontology owner approves it.

1. List the entries to move, and agree the class of each with the ontology owner.
2. Search your copy for the `id` of each entry, such as `dp-hr`. A value stream, a row of `data-product\links.csv` or a platform table may name it. A link that needs a data product stops the build once the entry has moved, so settle each one first.
3. Write the proposal, as "The worked examples of the next five sections" says. It names each entry and its new kind.
4. When the proposal is accepted, give each entry a field for its kind in the portfolio file. The example writes `"kind": "portfolio"`. Allow the field in the file's schema too, `business_architecture\schema\data_product_portfolio.schema.json`. A test compares the file with its schema.
5. Add the class to `business_architecture\ontology\data-product\vocabulary.ttl`, with `rdfs:label`, `skos:definition` and its source in `dcterms:bibliographicCitation`.
6. Change `data-product\shapes.ttl` in three places. Add the class to the targets of `shp:PortfolioItem` and of `shp:ActiveIsDefined`. Add a shape of its own, which says that the entry sits in one line, has one status and is not also a data product.
7. Change `data-product\build_data_products.py` in four places. It must refuse a kind it does not know, give an entry the class of its kind, write a history note that says what the entry was before, and count the two classes apart. The helper's function `entry_builder` shows each place.
8. Change the count of terms, the figures and the count of data products in `data-product\test_data_products.py`. Add a test that the new shape rejects an entry of both classes.
9. Rebuild with `python build_data_products.py --write`, from the folder `data-product`.
10. Release `data-product` as a major, with "The release steps" from step 3. The cascade gives `logical-model`, `technical-graph`, `value-stream` and `integration` a patch each.

The intake form offers the data products in question 6.6. Its list holds every `dp:DataProduct`, so an entry that moved leaves it. `[pick_list.data-products]` in `kpi-intake/settings.toml` names the 13 data products under `keep_only`. The build of the pack stops on a name there that is no longer in the list. So if you move an entry that `keep_only` names, remove its name there. When all 36 have moved, the list holds only the data products. Delete the table `[pick_list.data-products]` then, so that the form offers a data product the ontology gains later.

### A worked example: the entry HR becomes a data portfolio

The example moves one entry, HR, to a new class, `dp:DataPortfolio`. **The class, its definition and the proposal are made up.** `data-product` 1.2.0 becomes 2.0.0.

The commands start in the top folder of the copy.

1. Start from a copy of the release as shipped. The document test puts its copy back with this block. In a fresh copy, skip it.

   ```powershell run=slow status-only
   git reset -q --hard
   git clean -q -fd
   ```

2. List the files the example changes. This changes nothing.

   ```powershell run=slow
   cd business_architecture/ontology/release
   python update_examples.py move-entry --plan
   ```

   ```text expect
   would change business_architecture/business_process/proposals/EXAMPLE-P02-portfolio-entry.md
   would change business_architecture/business_process/data_product_portfolio.json
   would change business_architecture/schema/data_product_portfolio.schema.json
   would change business_architecture/ontology/data-product/vocabulary.ttl
   would change business_architecture/ontology/data-product/shapes.ttl
   would change business_architecture/ontology/data-product/build_data_products.py
   would change business_architecture/ontology/data-product/test_data_products.py
   would change business_architecture/ontology/approvals/example-move-entry.md
   ```

3. Make the hand edits of steps 3 to 8 above, and write the approval.

   ```powershell run=slow
   python update_examples.py move-entry --write
   ```

   ```text expect
   changed business_architecture/business_process/proposals/EXAMPLE-P02-portfolio-entry.md
   ...
   Now build: cd ../data-product, then build_data_products.py --write. HOW-TO-UPDATE.md has the steps after it.
   ```

4. Rebuild the catalog's entries. The line counts 48 data products, one fewer than before, and 1 data portfolio.

   ```powershell run=slow
   cd ../data-product
   python build_data_products.py --write
   ```

   ```text expect
   segments 3; lines 19; data products 48; data portfolios 1; active products 16; defined_only products 32; open_decision products 0; parked without a description 32; process links 2; links waiting for a core release 0
   wrote <the path of the data products file>
   ```

5. Set the new version, write the package and release the modules that depend on it.

   ```powershell run=slow
   cd ../release
   python next_version.py start data-product 2.0.0 major --why "Moves the catalog entry HR to the new class data portfolio." --approver "The ontology owner" --where "approvals/example-move-entry.md" --words "Approved as a major: the catalog entry HR is a data portfolio."
   python build_module.py data-product --write
   python next_version.py cascade data-product --approver "The ontology owner" --where "approvals/example-move-entry.md" --words "Approved as a major: the catalog entry HR is a data portfolio."
   ```

   ```text expect
   data-product is set to 2.0.0. Now run: python3 build_module.py data-product --write
   data-product 2.0.0: <count> triples; shapes conform
   wrote <the path of the new package>
   ...
   data-product 1.2.0 moved to releases/previous/; the projection's lists name 2.0.0
   logical-model 1.0.0 moved to releases/previous/; the projection's lists name 1.0.1
   technical-graph 1.1.0 moved to releases/previous/; the projection's lists name 1.1.1
   value-stream 1.2.0 moved to releases/previous/; the projection's lists name 1.2.1
   integration 2.5.0 moved to releases/previous/; the projection's lists name 2.5.1
   5 modules released. Now rebuild the catalog and the projection manifest, and run the check.
   ```

6. Rebuild the catalog, the projection manifest, the competency questions, the KPI intake pack and the pages. The pages now include the proposal's page.

   ```powershell run=slow
   python build_catalog.py --write
   cd ../projection
   python pipeline.py build
   cd ../regression
   python run.py
   cd ../../..
   python -m kpi_store.intake build
   python scripts/build_docs_html.py
   ```

   ```text expect
   catalog: 13 releases from 13 packages
   ...
   competency coverage on <the core package>: 57 questions; answerable 56, partial 0, waiting 0, parked 1
   wrote kpi-intake/pick-lists.json
   ...
   ```

7. Stage the change and run the full check. On Windows, run it in Git Bash.

   ```bash run=slow
   git add -A
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

## Change the RACI

Use this to replace or remove who is responsible, accountable, consulted and informed for a process. New roles and new entries for a process the map holds go in with the process map request form instead: see "Add roles and RACI entries with the process map request". The steps below still show how the sources fit together. This release leaves open the RACI of your organisation's governance roles (`KNOWN-OPEN-ITEMS.md`, item 8).

`organization` builds its RACI from the process map. A process there may have a `raci` object with four lists, named `responsible`, `accountable`, `consulted` and `informed`. Each entry of a list is the name of a role, as text. The role register, `organization\role-register.csv`, maps each name to one or more roles of `organization\roles.csv`. The builder writes one assignment for each entry and each role it names. It infers nothing from the hierarchy. A process with no `raci` object gets no assignment, whatever the processes above and below it have.

Four cases differ in what you do and in the kind of release.

| What changes | What to do | Release |
|---|---|---|
| New roles, or new entries. | The steps below. | A minor. |
| An entry is removed, or a role is replaced in some entries while other entries still name it. | The steps below. Rewrite those entries in the process map. | A major, because the assignments of the old entries leave the module. |
| One role replaces another in every entry that names it. | "Deprecate a term". Leave the process map and the register as they are. | A major. |
| A role leaves every entry, and no one role replaces it. | Not possible in this release. "Deprecate a term" says why. | |

The third case is never done in the process map. The build refuses a role that no entry names, and a role is never deleted. So the name stays in the process map, and the deprecation gives each of its assignments to the successor. If the successor is a new role, add it first with the steps below, in the same release.

1. Get the RACI from the business as a document with a date. It has one line for each process, role and level.
2. Check that each line names a process of the process map. This module holds assignments for those processes only. A RACI for anything else, such as the governance of a data domain, needs that process first ("Change a process"), or a module of its own ("Onboard another module").
3. Write the proposal, as "The worked examples of the next five sections" says. It names each process and its four lists, and the date of the RACI.
4. When the proposal is accepted, write the four lists into the process map, in the `raci` object of each process. Give a process that has none a `raci` object after its `name`.
5. For each role name that is new to the process map, add a row to `role-register.csv`. `source_text` is the name exactly as the process map spells it. `roles` is the `slug` of the role. `rule` is `exact` when the name is spelt as the role's `label`. `build_roles.py` checks each of the other rules.
6. For each new role, add a row to `roles.csv`. It holds the role's `slug`, its `label` as the source spells it, its `kind` (`position` or `team`), its `definition`, and a `note` that names the source and its date. Give the row every column, also the empty ones.
7. To give an existing role your organisation's title, set its `preferred_label`. The role keeps its `slug`, and the name in the process map becomes an alternative label.
8. Change the figures in `organization\test_roles.py`. `test_the_figures_match_the_decision_record` states the counts of processes, entries, role names and roles.
9. Rebuild the roles, then the assignments, from the folder `organization`. The commands are `python build_roles.py --write` and `python build_assignments.py --write`. The second prints the ledger. In it, the entries plus the extra roles of entries that name two roles equal the assignments.
10. Release `organization`, with "The release steps" from step 3. The cascade gives `integration` and `ref-mpc` a patch each.
11. Add the line to `scripts/pinned-tests.txt` that "The worked examples of the next five sections" names.

The shapes and the tests then hold you to these rules.

- An assignment has one process, one role, one of the four levels, the text of its entry and a source.
- An assignment names a live role, never a deprecated one.
- A role has one English name and cites its source.
- The register holds each role name of the process map once, and every role is named by a row of the register.

**An assignment carries no date in this release.** Each one cites the process map as its source. Write the date of your RACI in the proposal and in the `note` of each new role.

The intake form offers every role of the register in question 6.1 after the next build of the pack. If `kpi-intake/settings.toml` adds a role under `add` that the register now holds, remove it there once no form in progress names it, as "Change the form" in `kpi-intake/README.md` says.

### A worked example: a RACI for one process, with two new roles

The example gives the process CM 1.1.2 Regional Optimization a RACI. Two of its four roles are new: Sample Data Steward and Sample Domain Owner. **The roles, the RACI and the proposal are made up.** The example removes nothing, so the release is a minor: `organization` 2.2.0 becomes 2.3.0.

The commands start in the top folder of the copy.

1. Start from a copy of the release as shipped. The document test puts its copy back with this block. In a fresh copy, skip it.

   ```powershell run=slow status-only
   git reset -q --hard
   git clean -q -fd
   ```

2. List the files the example changes. This changes nothing.

   ```powershell run=slow
   cd business_architecture/ontology/release
   python update_examples.py raci --plan
   ```

   ```text expect
   would change business_architecture/business_process/proposals/EXAMPLE-P01-sample-raci.md
   would change business_architecture/business_process/downstream_process_map.json
   would change business_architecture/ontology/organization/role-register.csv
   would change business_architecture/ontology/organization/roles.csv
   would change business_architecture/ontology/organization/test_roles.py
   would change scripts/pinned-tests.txt
   would change business_architecture/ontology/approvals/example-raci.md
   ```

3. Make the hand edits of steps 3 to 8 and of step 11 above, and write the approval.

   ```powershell run=slow
   python update_examples.py raci --write
   ```

   ```text expect
   changed business_architecture/business_process/proposals/EXAMPLE-P01-sample-raci.md
   ...
   Now build: cd ../organization, then build_roles.py --write and build_assignments.py --write. HOW-TO-UPDATE.md has the steps after it.
   ```

4. Rebuild the roles and the assignments. The lines count one more process with a RACI, four more entries, two more roles and four more assignments than before.

   ```powershell run=slow
   cd ../organization
   python build_roles.py --write
   python build_assignments.py --write
   ```

   ```text expect
   processes with RACI 154; RACI entries 917; distinct source strings 93; roles 62; positions 56; teams 6; deprecated roles 3; live roles 59; compound strings 11; role references after splitting 944
   wrote <the path of the roles file>
   processes with RACI in the source 154; RACI entries in the source 917; extra roles from compound strings 27; assignments emitted 944; <the counts by level>; SHACL conforms
   wrote assignments.ttl and raci-conservation.csv
   ```

5. Set the new version, write the package and release the modules that depend on it.

   ```powershell run=slow
   cd ../release
   python next_version.py start organization 2.3.0 minor --why "Adds two roles and the RACI of CM 1.1.2." --approver "The organization module owner" --where "approvals/example-raci.md" --words "Approved as a minor: two roles and the RACI of CM 1.1.2."
   python build_module.py organization --write
   python next_version.py cascade organization --approver "The organization module owner" --where "approvals/example-raci.md" --words "Approved as a minor: two roles and the RACI of CM 1.1.2."
   ```

   ```text expect
   organization is set to 2.3.0. Now run: python3 build_module.py organization --write
   organization 2.3.0: <count> triples; shapes conform
   wrote <the path of the new package>
   ...
   organization 2.2.0 moved to releases/previous/; the projection's lists name 2.3.0
   integration 2.5.0 moved to releases/previous/; the projection's lists name 2.5.1
   ref-mpc 1.3.0 moved to releases/previous/; the projection's lists name 1.3.1
   3 modules released. Now rebuild the catalog and the projection manifest, and run the check.
   ```

6. Rebuild the catalog, the projection manifest, the competency questions, the KPI intake pack and the pages. The pages now include the proposal's page.

   ```powershell run=slow
   python build_catalog.py --write
   cd ../projection
   python pipeline.py build
   cd ../regression
   python run.py
   cd ../../..
   python -m kpi_store.intake build
   python scripts/build_docs_html.py
   ```

   ```text expect
   catalog: 13 releases from 13 packages
   ...
   competency coverage on <the core package>: 57 questions; answerable 56, partial 0, waiting 0, parked 1
   wrote kpi-intake/pick-lists.json
   ...
   ```

7. Stage the change and run the full check. On Windows, run it in Git Bash.

   ```bash run=slow
   git add -A
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

## Add a controlled list to a module

Use this when a property must take its value from a fixed list that the ontology does not hold yet. This release leaves the data domains open. The intake form asks for a KPI's domain, and the ontology holds no list of domains (`KNOWN-OPEN-ITEMS.md`, item 7). A new list removes nothing, so the release is a minor.

A controlled list is a SKOS concept scheme. Each value is a `skos:Concept` in the list's own scheme, and the shape of the property that points at the list checks that scheme.

First decide where the list lives.

- Put the list in the module whose property points at it. `system` holds its kinds this way, `organization` its RACI levels, and `data-product` its statuses and its layers.
- A module can point only at a module it depends on. `python dependents.py <module>`, from the folder `release`, prints the modules that depend on one.
- Give the list a module of its own when its values carry facts of their own that a competency question asks for, or when two modules that do not depend on each other must point at it. Then follow "Onboard another module".

For the domains, the first property is a KPI's domain, so the list goes in `kpi`. `data-product` depends on `kpi` and can point at the list later. The domains with their owners are more than a list. An owner is a role of `organization`, and `organization` does not depend on `kpi`. That part needs a module of its own.

1. Write the competency question that the list answers.
2. Write the list as a table in the module's folder. Each value is one row with an id, a name and a definition. The example's table is `kpi\data-domains.csv`.
3. Write a builder that writes the table as Turtle, with `--write` and `--verify`. It gives each value its types, `skos:inScheme` and `skos:topConceptOf` with the list's scheme, a label, a notation, a definition and its source. The example's builder is `kpi\build_data_domains.py`.
4. Add three terms to the module's `vocabulary.ttl`. They are the scheme, the class of its values, and the property that points at the list. Give the property one `rdfs:domain`, and `skos:Concept` as its `rdfs:range`.
5. Change the module's `shapes.ttl` in four places. Add the property's cardinality to the shape of the class that carries it. In `kpi`, add the property to the `sh:ignoredProperties` list of the closed shape too. Add a shape for a value of the list. Add a shape with `sh:targetObjectsOf` the property, which requires `skos:inScheme` to be the list's scheme. Without that last shape, a value from another list passes.
6. Add the builder's Turtle file to the module's `parts` in `release\build_module.py`, and to the module's files in `regression\run.py`. For `kpi`, add it also to `test_kpi_holds_the_measures_and_the_populations` in `release\test_build_module.py`, which names the module's files by hand.
7. Add two lines to `scripts/check.sh`. One runs the builder with `--verify`. The other names the list's test file in the test list.
8. Add the file to the module's row in `business_architecture\ontology\MODULES.md`.
9. Add the question's text to `competency-questions.md`, its row to `regression\expected.csv` and its query to `regression\queries`.
10. Write the test file. It states the values by hand, and proves that the shapes reject a value from another list.
11. To give a term its value, add a column to the term's table and a line to its builder, as step 4 of "Add a concept or a property" says.
12. Build the list, then release the module as a minor, with "The release steps" from step 3.

**The intake form cannot take a new list from the ontology in this release.** The lists that the form reads from the ontology are fixed in `kpi_store/intake/picklists.py`. Question 1.5 reads the domains from `[[list.domains]]` in `kpi-intake/settings.toml`. That list also says which domain is active, which the ontology's list does not. So keep the list in `settings.toml`, and give each domain there the `id` it has in the ontology's table. Then an answer in a form names the same domain as the ontology.

### A worked example: a list of data domains in `kpi`

The example adds a list of two data domains to `kpi`, and the property `kpi:dataDomain` that points at it. **The two domains are made up.** No measure gets a domain. `kpi` 1.3.0 becomes 1.4.0.

The commands start in the top folder of the copy.

1. Start from a copy of the release as shipped. The document test puts its copy back with this block. In a fresh copy, skip it.

   ```powershell run=slow status-only
   git reset -q --hard
   git clean -q -fd
   ```

2. List the files the example changes. This changes nothing.

   ```powershell run=slow
   cd business_architecture/ontology/release
   python update_examples.py domain-list --plan
   ```

   ```text expect
   would change business_architecture/ontology/kpi/data-domains.csv, build_data_domains.py and test_data_domains.py
   would change business_architecture/ontology/kpi/vocabulary.ttl
   would change business_architecture/ontology/kpi/shapes.ttl
   would change business_architecture/ontology/release/build_module.py and test_build_module.py
   would change scripts/check.sh
   would change business_architecture/ontology/regression/ and business_architecture/ontology/competency-questions.md
   would change business_architecture/ontology/MODULES.md
   would change business_architecture/ontology/approvals/example-domain-list.md
   ```

3. Make the hand edits of steps 2 to 10 above, and write the approval.

   ```powershell run=slow
   python update_examples.py domain-list --write
   ```

   ```text expect
   changed business_architecture/ontology/kpi/data-domains.csv, build_data_domains.py and test_data_domains.py
   ...
   Now build: cd ../kpi, then build_data_domains.py --write. HOW-TO-UPDATE.md has the steps after it.
   ```

4. Build the list from its table.

   ```powershell run=slow
   cd ../kpi
   python build_data_domains.py --write
   ```

   ```text expect
   data domains 2
   wrote data-domains.ttl
   ```

5. Set the new version, write the package and release the modules that depend on it.

   ```powershell run=slow
   cd ../release
   python next_version.py start kpi 1.4.0 minor --why "Adds a list of data domains and the property that points at it." --approver "The kpi module owner" --where "approvals/example-domain-list.md" --words "Approved as a minor: a list of data domains and the property that points at it."
   python build_module.py kpi --write
   python next_version.py cascade kpi --approver "The kpi module owner" --where "approvals/example-domain-list.md" --words "Approved as a minor: a list of data domains and the property that points at it."
   ```

   ```text expect
   kpi is set to 1.4.0. Now run: python3 build_module.py kpi --write
   kpi 1.4.0: <count> triples; shapes conform
   wrote <the path of the new package>
   ...
   kpi 1.3.0 moved to releases/previous/; the projection's lists name 1.4.0
   ...
   7 modules released. Now rebuild the catalog and the projection manifest, and run the check.
   ```

6. Rebuild the catalog, the projection manifest, the competency questions, the KPI intake pack and the pages. The count of questions is one higher than before, because the list's question is number 58.

   ```powershell run=slow
   python build_catalog.py --write
   cd ../projection
   python pipeline.py build
   cd ../regression
   python run.py
   cd ../../..
   python -m kpi_store.intake build
   python scripts/build_docs_html.py
   ```

   ```text expect
   catalog: 13 releases from 13 packages
   ...
   competency coverage on <the core package>: 58 questions; answerable 57, partial 0, waiting 0, parked 1
   wrote kpi-intake/pick-lists.json
   ...
   ```

7. Stage the change and run the full check. On Windows, run it in Git Bash.

   ```bash run=slow
   git add -A
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

## Add a process, a step or a business area with the process map request

A new business area, process or step goes in through the process map request form and the same two commands. Nobody edits the process map, a builder or a Turtle file by hand. `kpi-intake/README.md`, "The process map request", says what the propose command reads and who signs.

The process map is the source of `core`, and every module depends on `core`. So the apply makes a release of `core` at its next minor version, and every module that depends on it takes a patch. It does each of the steps that "Change a process" below lists for a specialist:

- it adds each new node to `business_architecture/business_process/downstream_process_map.json`, under its parent, and its row to `business_architecture/ontology/build/output/step2-identity-map.json`;
- it freezes the map as it leaves it in `business_architecture/ontology/release/frozen`, named by the first twelve characters of the map's SHA-256;
- it writes the next core builder, such as `build_core_2_5.py`, from `build_core_template.py`, with the template's block of constants filled in from the proposal, and checks that the builder compiles and holds those constants;
- it writes the core changelog, runs the builder, and checks that the difference between the two core releases is exactly the proposal's lines and facts;
- it checks that every module's source Turtle still equals a fresh build, releases every module, and runs the checks.

`change.kgcl` holds each new node's name, definition, parent and business area. `facts.csv` holds its number, its level and its scope note, which KGCL cannot write. A request adds one level of the map: a step of a new process goes in with a request of its own, once the process is in the map.

The commands start in the release folder. Keep the filled form and the proposal in a folder beside the release folder, never inside it. The example uses the folder `new-process` beside the release folder.

1. Fill in the form, and save it to that folder. The example is the shipped example `kpi-intake/examples/sample-blend-planning.process-map-request.json`. It adds a made-up process, Sample Blend Planning, under CM 1.1 Planning & Scheduling, and makes the role Business Analyst accountable for it. The processes under CM 1.1 all belong to the business area Commercial, so P8 is empty and the new process takes Commercial. The Global Process Owner and the Architect sign it.

   The document test copies the example to the folder with this block. If you saved the file from the form, skip it.

   ```python run=new-process
   import shutil
   from pathlib import Path

   folder = Path("../new-process")
   folder.mkdir(exist_ok=True)
   path = shutil.copy("kpi-intake/examples/sample-blend-planning.process-map-request.json", folder)
   print("copied", Path(path).name)
   ```

   ```text expect
   copied sample-blend-planning.process-map-request.json
   ```

2. Check the form. It must end with `the intake is complete and signed`.

   ```powershell run=new-process
   python -m kpi_store.intake check ../new-process/sample-blend-planning.process-map-request.json
   ```

   ```text expect
   Process map request check: Sample Blend Planning
   ...
   Result: the intake is complete and signed.
   This check changes nothing in the ontology. The Architect turns a complete process map request into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
   ```

3. Turn the form into a proposal. The command writes the folder `proposals/PM-2026-002` beside the form. It gives the new process its number, CM 1.1.8: the first number under CM 1.1 that no process of the map holds.

   ```powershell run=new-process
   python -m kpi_store.propose ../new-process/sample-blend-planning.process-map-request.json
   ```

   ```text expect
   wrote the proposal ../new-process/proposals/PM-2026-002: 7 changes and 4 facts, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

4. Read `summary.txt`. It names the new process, where it goes, its business area and its RACI entry.

   ```python run=new-process
   print(open("../new-process/proposals/PM-2026-002/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal PM-2026-002
   ...
   What it adds:
     - A new process, CM 1.1.8 Sample Blend Planning (proc:CM-1-1-8), at level 3, under CM 1.1 Planning & Scheduling, in the business area Commercial.
       Its definition: "Plan the made-up blends of one made-up region for the coming month."
       Its scope note: "It covers the blend recipes, not the blending itself."
     - A RACI entry: "Business Analyst" is accountable for the process CM 1.1.8 Sample Blend Planning.
   ...
   ```

5. Apply the proposal. The command refuses a proposal that lacks the Global Process Owner's or the Architect's signature. It works on a temporary copy of the release, and writes the release and commits it only when every step has passed. It took about three minutes on a Mac.

   ```powershell run=new-process
   python -m kpi_store.apply ../new-process/proposals/PM-2026-002
   ```

   ```text expect
   1 proposal to apply:
     PM-2026-002: minor, signed by Global Process Owner, Architect
   ...
     core 2.4.0 -> 2.5.0
   ...
     organization 2.2.0 -> 2.3.0
   ...
   ... write the release
   Done. core is now 2.5.0 and organization 2.3.0 (minor), and 11 modules that depend on them took a new patch. The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

6. See the commit, the new core builder and the new process in the KPI form's list.

   ```powershell run=new-process
   git --no-pager log --oneline -1
   python -c "import json; print([p['label'] for p in json.load(open('kpi-intake/pick-lists.json', encoding='utf-8'))['lists']['processes'] if p['label'].startswith('CM 1.1.8 ')])"
   cd business_architecture/ontology/release
   python -c "import newest; print(newest.core_builder())"
   cd ../../..
   ```

   ```text expect
   <commit> Apply the process map request PM-2026-002: core 2.5.0, organization 2.3.0
   ['CM 1.1.8 Sample Blend Planning']
   build_core_2_5
   ```

7. Run the full check, as in "Before you change anything", step 3. Then load the stores with the runner, as in step 11 of "The release steps".

## Change a process

This section is for a specialist. A process that is renamed, moved, described anew or removed has no form: the process map request adds new processes only. A change to an existing process's meaning is a major.

The document test does not run this section's commands. Each needs your own edits to a new builder first. The steps it ends with, the cascade and the check, are tested in "The release steps".

1. Copy `business_architecture\business_process\downstream_process_map.json` into `business_architecture\ontology\release\frozen`. Name the copy with a label of 12 letters or digits, a hyphen, and the file's name, such as `before202611-downstream_process_map.json`.
2. Make the change to the node in `downstream_process_map.json`. A builder makes a description's first sentence the definition and the rest the scope note. So put the whole definition in the first sentence.
3. Make the same change to its row of `business_architecture\ontology\build\output\step2-identity-map.json`.
4. Copy the changed map into `frozen` too, under a second label, such as `after2026110-downstream_process_map.json`.
5. Save the approval, as step 3 of "The release steps" says.
6. In `business_architecture\ontology\release`, copy `build_core_template.py` to `build_core_2_5.py`. The name is for the first change to this release. A later change raises it.
7. Fill in the block that the new builder marks: the two labels, the new version and the approval. The template adds nodes only and stops on any other change, so write the builder's change of your own: `build_core_2_2.py` applies new IDs and descriptions, and `build_core_2_4.py` renames.
8. Write the changelog `business_architecture\ontology\releases\core\CHANGELOG-2.5.0.md`, in the form of `CHANGELOG-2.4.0.md` beside it.
9. Add a short test, `test_build_core_2_5.py`, beside the builder. It says what the release adds and that it removes no IRI. Add it to the test list in `scripts/check.sh`.
10. From the folder `release`, write the package with `python build_core_2_5.py --write`.
11. Move the folder `releases\core\2.4.0` into `releases\previous\core`. Make that folder first if it is missing.
12. Rebuild every module's source file, since each reads `core`. `scripts/check.sh` lists the builders after the comment on each module's source Turtle. Run each from its folder with `--write`.
13. From the folder `release`, release every module with `python next_version.py cascade core`, with `--approver`, `--where` and `--words` as in "The release steps".
14. Change the version of `core` by hand in `PACKAGES` in `projection/pipeline.py` and under `packages` in `projection/skill-run/epm-config.json`.
15. Follow "The release steps" from step 7.

In a Git copy you may name the two copies of the map by the first 12 characters of their commits instead.

## A new environment

The same ontology loads into another workspace with new settings files. The ontology does not change. The ontology names its catalogs `idp_sbx` and `synapse_dev`. The `[names]` table says what each is called in the new environment.

1. Copy `%USERPROFILE%\kpi-store-local\kpi_store.toml` to a new file beside it, such as `kpi_store.prod.toml`.
2. In the new file, set `write_catalog` and `read_catalogs` to the new environment's catalogs.
3. In `[names]`, set each of the ontology's two catalog names to the catalog that holds those objects in the new environment.
4. Set `warehouse_id` to a SQL warehouse of the new workspace.
5. Copy `%USERPROFILE%\kpi-store-local\stores.toml` to a new file, such as `stores.prod.toml`.
6. In the new file, set `settings` to the new `kpi_store` file, and `run_folder` to a new folder, such as `runs-prod`. A path without a drive starts at the folder of the settings file.
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
python -c "from kpi_store import settings; s = settings.load('kpi_store/kpi_store.example.toml'); print(s.write_schemas, s.read_catalogs, s.names)"
```

```text expect
('idp_sbx.kpi_store', 'idp_sbx.tech_graph') ('idp_sbx', 'synapse_dev') {'idp_sbx': 'idp_sbx', 'synapse_dev': 'synapse_dev'}
```

The first run in a new environment is a first run. Follow the runbook from "Run the setup check", with `--stores` and the new file on every command. A name that differs in the new environment is an `environment setting` row or a correction, as the report says.

**A correction changes the ontology for every environment.** Accept a rename only when the name changed everywhere. When it differs in one environment only, decide the row as `environment setting`.

## Add a module with the new-module form

A new module goes in through the new-module form and the same two commands as a term change. Nobody writes a table, a builder, a shape or a Turtle file by hand. The form is the "New module" tab of the HTML form and the "New module" sheet of the workbook. `kpi-intake/README.md`, "The new module", says what it asks and who signs.

The form makes a module of one of two patterns:

- a vocabulary: terms, each with a definition, other names and at most one broader term of the same vocabulary. The module holds them as a SKOS concept scheme of its own.
- a reference table: items of a class that the ontology holds already, such as products, each with one value of each of a few properties that the ontology holds already. The form offers the classes whose items the ontology holds outside `ref-mpc`, and the properties of those classes.

A module that needs a new class, a new property or a rule of its own is new modelling. An AI can draft it under five extra gates, as "Draft new modelling with AI (optional)" below says. Without AI, it needs a specialist, and "Onboard another module" below is the specialist's path.

The proposal holds each term or item as KGCL lines in `change.kgcl`: its name, its definition, its other names, its broader term, its class and its links to other items. `facts.csv` holds the module itself (its pattern, title, description and documents) and each text or value of an item that KGCL cannot write. The propose command builds the module in memory and runs every shape of the release over it, so a class's own rules, such as "a product is in the product list", stop a proposal that breaks them.

A new module's first release is 1.0.0, a major. So the Data Owner, the Ontology Owner and the Architect sign the form, and the apply command refuses a proposal without the Ontology Owner's signature. The apply works on a temporary copy of the release. It writes the module's folder from its pattern (`business_architecture/ontology/release/module_patterns.py`): the table, a builder, the shapes, a test file and a README. It registers the module in every place that "Register the module in every place" lists, with the functions of `business_architecture/ontology/release/register_module.py`. It builds the module, checks that the module holds exactly the proposal's lines and facts, and releases it at 1.0.0. It then rebuilds the catalog, the projection manifest, the competency questions, the KPI intake pack and the pages, and runs the module's tests and the whole-graph shapes gate. Only when every step has passed does it write the release and commit it.

**Run the examples below in a copy of the release, never in the folder you load the stores from.** Each adds a made-up module to the ontology. The commands start in the top folder of the copy. Keep the filled form and the proposal in a folder beside it, never inside it.

### A vocabulary

1. Fill in the form, and save it to the folder `new-vocabulary` beside the release folder. The example is the shipped example `kpi-intake/examples/sample-equipment-terms.new-module.json`. It asks for a made-up vocabulary, Sample Equipment Terms, of five terms: two at the top, and three under them. The Data Owner, the Ontology Owner and the Architect sign it.

   The document test copies the example to the folder with this block. If you saved the file from the form, skip it.

   ```python run=new-vocabulary
   import shutil
   from pathlib import Path

   folder = Path("../new-vocabulary")
   folder.mkdir(exist_ok=True)
   path = shutil.copy("kpi-intake/examples/sample-equipment-terms.new-module.json", folder)
   print("copied", Path(path).name)
   ```

   ```text expect
   copied sample-equipment-terms.new-module.json
   ```

2. Check the form. It must end with `the intake is complete and signed`. The check also refuses a vocabulary that does not reconcile, such as a term under a term that the list does not name.

   ```powershell run=new-vocabulary
   python -m kpi_store.intake check ../new-vocabulary/sample-equipment-terms.new-module.json
   ```

   ```text expect
   New module check: Sample Equipment Terms
   ...
   Result: the intake is complete and signed.
   This check changes nothing in the ontology. The Architect turns a complete new module into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
   ```

3. Turn the form into a proposal. The command writes the folder `proposals/NM-2026-001` beside the form. It changes nothing in the ontology. It took about 20 seconds on a Mac, because it runs every shape of the release over the module.

   ```powershell run=new-vocabulary
   python -m kpi_store.propose ../new-vocabulary/sample-equipment-terms.new-module.json
   ```

   ```text expect
   wrote the proposal ../new-vocabulary/proposals/NM-2026-001: 18 changes and 4 facts, route major
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

4. Read `summary.txt`. It names the module, each term and where it sits, the route and who signed.

   ```python run=new-vocabulary
   print(open("../new-vocabulary/proposals/NM-2026-001/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal NM-2026-001
   ...
   What it adds:
     - A vocabulary of 5 terms, as a SKOS concept scheme.
     - The term "Rotating equipment" (a top term): "Made-up equipment whose main part turns while it works."
     - The term "Pump" (under "Rotating equipment"): "Made-up rotating equipment that moves a liquid through a pipe."
   ...
   The route: major. This is a major: a new module's first release is 1.0.0, and the Ontology Owner approves it.
   ...
   ```

5. Apply the proposal. It took about three minutes on a Mac.

   ```powershell run=new-vocabulary
   python -m kpi_store.apply ../new-vocabulary/proposals/NM-2026-001
   ```

   ```text expect
   1 proposal to apply:
     NM-2026-001: major, signed by Data Owner, Ontology Owner, Architect
   ...
     sample-equipment-terms: a new module at 1.0.0
   ...
   ... write the release
   Done. sample-equipment-terms 1.0.0 is a new module (major). The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

6. See the commit, the new version and the module's own check of its build.

   ```powershell run=new-vocabulary
   git --no-pager log --oneline -1
   cd business_architecture/ontology/release
   python next_version.py current sample-equipment-terms
   cd ../sample-equipment-terms
   python build_sample_equipment_terms.py --verify
   ```

   ```text expect
   <commit> Apply the new module NM-2026-001: sample-equipment-terms 1.0.0
   1.0.0
   terms 5; top terms 2
   terms.ttl is current
   ```

7. Run the full check, as in "Before you change anything", step 3. Then load the stores with the runner, as in step 11 of "The release steps". The projection takes every module in its package list, so the new module goes into every store with the others.

### A reference table

A reference table names a class in N8, picks properties in N9, and gives each item one value of each property in N11, in the order of N9, with a vertical bar (`|`) between two values. A value that links to another item names that item as the ontology holds it: here `product`, the last part of the IRI of the party module's product list.

1. Fill in the form, and save it to the folder `new-reference-table` beside the release folder. The example is the shipped example `kpi-intake/examples/sample-products.new-module.json`. It asks for a made-up module, Sample Products, of two made-up products of the class Product of the `party` module. Each has a definition, the product list it is in and a PIDX product family. The Data Owner, the Ontology Owner and the Architect sign it.

   The document test copies the example to the folder with this block. If you saved the file from the form, skip it.

   ```python run=new-reference-table
   import shutil
   from pathlib import Path

   folder = Path("../new-reference-table")
   folder.mkdir(exist_ok=True)
   path = shutil.copy("kpi-intake/examples/sample-products.new-module.json", folder)
   print("copied", Path(path).name)
   ```

   ```text expect
   copied sample-products.new-module.json
   ```

2. Check the form. It must end with `the intake is complete and signed`. The check also refuses an item that lacks a value of a property that N9 picks.

   ```powershell run=new-reference-table
   python -m kpi_store.intake check ../new-reference-table/sample-products.new-module.json
   ```

   ```text expect
   New module check: Sample Products
   ...
   Result: the intake is complete and signed.
   This check changes nothing in the ontology. The Architect turns a complete new module into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
   ```

3. Turn the form into a proposal. The command refuses a property of another class, a value that names no item of the ontology, a value of the wrong kind, and a rule of the class that the items break. It writes the folder `proposals/NM-2026-002` beside the form.

   ```powershell run=new-reference-table
   python -m kpi_store.propose ../new-reference-table/sample-products.new-module.json
   ```

   ```text expect
   wrote the proposal ../new-reference-table/proposals/NM-2026-002: 8 changes and 9 facts, route major
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

4. Read `summary.txt`. It names the class, each item and its values, and the modules the new module requires.

   ```python run=new-reference-table
   print(open("../new-reference-table/proposals/NM-2026-002/summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   Proposal NM-2026-002
   ...
   What it adds:
     - A reference table of 2 items of the class party:Product, which the party module defines. Each item has a name and one value of: definition (skos:definition), list it is in (skos:inScheme), PIDX product family (party:pidxProductFamily).
   ...
     - It requires the newest party.
   ...
   ```

5. Apply the proposal. It took about three minutes on a Mac.

   ```powershell run=new-reference-table
   python -m kpi_store.apply ../new-reference-table/proposals/NM-2026-002
   ```

   ```text expect
   1 proposal to apply:
     NM-2026-002: major, signed by Data Owner, Ontology Owner, Architect
   ...
     sample-products: a new module at 1.0.0
   ...
   ... write the release
   Done. sample-products 1.0.0 is a new module (major). The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

6. See the commit and the module's own check of its build.

   ```powershell run=new-reference-table
   git --no-pager log --oneline -1
   cd business_architecture/ontology/sample-products
   python build_sample_products.py --verify
   ```

   ```text expect
   <commit> Apply the new module NM-2026-002: sample-products 1.0.0
   items 2; properties 3
   items.ttl is current
   ```

7. Run the full check, as in "Before you change anything", step 3. Then load the stores with the runner, as in step 11 of "The release steps".

## Draft new modelling with AI (optional)

Some modules need something the new-module form cannot make by itself: a new class, a new property or a rule of its own. This is called new modelling. In the form, N3 is then "Something else", and N13 asks you to say in your own words what the module must let people say. An AI then drafts the module, and a second AI checks the draft. Nobody writes a file of the ontology by hand.

The draft is only a proposal. The AI applies nothing. It must pass five gates before the apply command takes it:

| Gate | What must be true | Who checks it |
|---|---|---|
| 1 | Every competency question gives the answer the AI said it would give. Competency questions are SPARQL queries that the new module must be able to answer. The example data that should pass meets every rule, and each example that should fail breaks the rule it names. | The command |
| 2 | A reasoner finds the new module, its examples and the modules it rests on consistent: no thing is, for example, in two classes that exclude each other. The reasoner is owlrl, the OWL 2 RL reasoner that comes with pyshacl. | The command |
| 3 | A second AI, of another model family, reviews the draft against the ontology skill's rules and answers PASS or HOLD. A HOLD stops the proposal. | The second AI |
| 4 | A summary says in plain words what each new class, property and rule means, with an example. | The command |
| 5 | The Ontology Owner signs. The module's first release is 1.0.0, a major. | The Ontology Owner, and the command |

The command also refuses a draft that changes anything the release holds already. A draft adds terms of its own only. It may use the release's classes and properties, but it cannot change them.

The AI steps come before anyone signs, so that each signer reads the draft first. The propose command and the apply command then run gates 1, 2 and 4 again, and check that the form and the draft are as the AI steps saw them.

The AI steps leave a record beside the form. For the drafter and the reviewer each, it names the provider, the model's family, the model and its version, the address called, who approved the provider and when, each skill file with its SHA-256, the SHA-256 of the prompt and the SHA-256 of the answer. It also holds the SHA-256 of each file of the draft and of the form's answers, the reviewer's verdict and findings, and the result of each gate. It keeps no text of the prompt. The proposal keeps the record in `approval.json`, under `"draft"`, and the apply command keeps it in the release's approval record.

**Run the example below in a copy of the release, never in the folder you load the stores from.** It adds a made-up module to the ontology. The commands start in the top folder of the copy. Keep the form and the AI's files in a folder beside it. The example uses the folder `ai-modelling`.

### Choose the two AI providers

The drafter goes in the `[ai]` table of your local settings file, as in "Use AI to suggest answers (optional)", "Choose the provider". The reviewer goes in a second table, `[ai_reviewer]`, with the same keys. `kpi_store/stores.example.toml` shows both tables, switched off. The client's IT approves each provider once. Each table also names its model's family in `family`, such as `"claude"`, `"gpt"` or `"llama"`. The command refuses two tables of the same family, because gate 3 needs a second opinion from another kind of model.

The by-hand provider works for both. The command then writes each prompt to a file. You give the file to an assistant, such as Genie Code, and save its answer to a file. Use two assistants that run models of two families.

### The steps

1. Fill in the new-module form and save it, but do not sign it. In N3, choose "Something else: a new class, a new property or a rule of its own". In N13, say what the module must let people say, with one example. Add the `[ai]` and `[ai_reviewer]` tables to your local settings file.

   The example asks for a made-up module, Sample Tank Inspections: an inspection checks one storage tank on one date, and one system of the ontology holds its record. The document test writes the form and a settings file with only the two tables, with this block. If you saved the form from the HTML form, skip it, and name your own settings file in the commands below.

   ```python run=ai-modelling
   import json
   from pathlib import Path

   folder = Path("../ai-modelling")
   folder.mkdir(exist_ok=True)
   answers = {"N1": "Sample Tank Inspections",
              "N2": "The made-up inspections of the storage tanks of a made-up terminal.",
              "N3": "new-modelling", "N12": ["A made-up tank inspection procedure, 2026-11-20"],
              "N13": "An inspection checks one storage tank on one date, and one system that the ontology lists "
                     "holds its record. For example, the inspection of 2 November 2026 is recorded in the APS "
                     "planning database."}
   form = {"format": 1, "form": "new-module", "catalogue_version": "1.2", "kpi_name": "Sample Tank Inspections",
           "request": {"number": "NM-2026-003", "date": "2026-11-20", "requester_role": "Data Owner", "invited": ""},
           "answers": answers, "sign_offs": {}, "consulted": {}, "example_of": "", "comment": ""}
   (folder / "sample-tank-inspections.new-module.json").write_text(json.dumps(form, indent=2) + "\n", encoding="utf-8")
   settings = ['[ai]', 'provider = "by-hand"', 'assistant = "Genie Code"', 'family = "claude"',
               'approved_by = "An IT Approver"', 'approved_on = "2026-11-20"', '',
               '[ai_reviewer]', 'provider = "by-hand"', 'assistant = "A second assistant"', 'family = "gpt"',
               'approved_by = "An IT Approver"', 'approved_on = "2026-11-20"']
   (folder / "kpi-store-local.toml").write_text("\n".join(settings) + "\n", encoding="utf-8")
   print("wrote the form and the settings")
   ```

   ```text expect
   wrote the form and the settings
   ```

   You are done when the form is saved with N3 and N13 answered and no signature, and the settings file holds both tables.

2. Ask the AI to draft the module. With the by-hand provider, the command writes the drafter's prompt to a file and stops. It refuses a form that anyone has signed.

   ```powershell run=ai-modelling
   python -m kpi_store.propose --ai-draft ../ai-modelling/sample-tank-inspections.new-module.json --stores ../ai-modelling/kpi-store-local.toml
   ```

   ```text expect
   wrote the prompt for the AI: ../ai-modelling/sample-tank-inspections.new-module.draft-prompt.txt
   Give that file to Genie Code. Save its answer, the JSON it writes, in a file such as ../ai-modelling/sample-tank-inspections.new-module.draft-answer.json. Then run this command again with --ai-answer <that file>.
   ```

   You are done when the folder holds `sample-tank-inspections.new-module.draft-prompt.txt`.

3. Give the prompt file to the drafter's assistant. Save its answer, the JSON it writes, as `sample-tank-inspections.new-module.draft-answer.json` in the same folder.

   The document test copies the release's sample draft, which is made up, with this block.

   ```powershell run=ai-modelling status-only
   python -c "import shutil; shutil.copy('kpi_store/ai/sample-draft.json', '../ai-modelling/sample-tank-inspections.new-module.draft-answer.json')"
   ```

   You are done when the answer file is in the folder.

4. Run the command again with the draft. It checks the draft strictly and runs gates 1, 2 and 4. If one fails, it says why and keeps nothing: ask the AI again, and give it those lines. If all pass, it writes the draft's files to the folder `sample-tank-inspections.new-module.draft` and the record of the draft beside them. Then it writes the reviewer's prompt and stops.

   ```powershell run=ai-modelling
   python -m kpi_store.propose --ai-draft ../ai-modelling/sample-tank-inspections.new-module.json --stores ../ai-modelling/kpi-store-local.toml --ai-answer ../ai-modelling/sample-tank-inspections.new-module.draft-answer.json
   ```

   ```text expect
   read the draft of Genie Code from ../ai-modelling/sample-tank-inspections.new-module.draft-answer.json
   gate 1, competency questions and examples: passed
   gate 2, the reasoner finds the model consistent: passed
   gate 4, a plain-words summary for the signers: passed
   wrote the draft: ../ai-modelling/sample-tank-inspections.new-module.draft, and its record: ../ai-modelling/sample-tank-inspections.new-module.draft.json
   wrote the prompt for the AI: ../ai-modelling/sample-tank-inspections.new-module.review-prompt.txt
   Give that file to A second assistant. Save its answer, the JSON it writes, in a file such as ../ai-modelling/sample-tank-inspections.new-module.review-answer.json. Then run this command again with --review-answer <that file>.
   ```

   You are done when the command says that gates 1, 2 and 4 passed and the folder holds `sample-tank-inspections.new-module.review-prompt.txt`.

5. Give the review prompt to the reviewer's assistant, of the other model family. Save its answer as `sample-tank-inspections.new-module.review-answer.json` in the same folder.

   The document test copies the release's sample review, which is made up, with this block.

   ```powershell run=ai-modelling status-only
   python -c "import shutil; shutil.copy('kpi_store/ai/sample-review.json', '../ai-modelling/sample-tank-inspections.new-module.review-answer.json')"
   ```

   You are done when the answer file is in the folder.

6. Run the command again with the review. The review becomes gate 3. The command writes the summary that the signers read, `sample-tank-inspections.new-module.draft-summary.txt`.

   ```powershell run=ai-modelling
   python -m kpi_store.propose --ai-draft ../ai-modelling/sample-tank-inspections.new-module.json --stores ../ai-modelling/kpi-store-local.toml --review-answer ../ai-modelling/sample-tank-inspections.new-module.review-answer.json
   ```

   ```text expect
   read the review of A second assistant from ../ai-modelling/sample-tank-inspections.new-module.review-answer.json
   gate 3, a second model of another family reviewed the draft: passed (PASS)
   ...
   wrote the record of the review: ../ai-modelling/sample-tank-inspections.new-module.draft.json
   wrote the summary for the signers: ../ai-modelling/sample-tank-inspections.new-module.draft-summary.txt
   Next: the signers read the summary and sign the form: the Data Owner, the Ontology Owner and the Architect. Then turn it into a proposal with: python -m kpi_store.propose ../ai-modelling/sample-tank-inspections.new-module.json
   ```

   If the reviewer answers HOLD, the command lists its findings and the propose command will refuse the form. Change the form as the findings say, delete the record and the draft folder, and start again at step 2.

   With the `databricks`, `anthropic` or `openai` provider, the command asks each AI itself, so steps 2 to 6 are one run with no prompt files and no `--ai-answer` or `--review-answer`.

   You are done when the command says gate 3 passed and the folder holds the summary.

7. The signers read the summary, then load the form in the HTML form ("Load answers file"), sign and save it. The Data Owner, the Ontology Owner and the Architect sign. By signing, they accept the draft as a whole. Do not change any answer now: the propose command refuses a form whose answers changed after the AI drafted the module.

   ```python run=ai-modelling
   print(open("../ai-modelling/sample-tank-inspections.new-module.draft-summary.txt", encoding="utf-8").read())
   ```

   ```text expect
   The AI draft of the new module "Sample Tank Inspections" (sample-tank-inspections)
   ...
   What the new things mean, as the AI wrote it for the signers:
     - The class "tank inspection" (sampletankinspections:TankInspection): One check of one storage tank's condition on one date. It is never a system itself.
       For example: The check of a made-up tank on 2 November 2026, recorded in the APS planning database.
   ...
   The gates (KPI-DEC-0002, Q19):
     - Gate 1, competency questions and examples: passed.
   ...
     - Gate 2, the reasoner finds the model consistent: passed.
   ...
     - Gate 3, a second model of another family reviewed the draft: passed.
   ...
     - Gate 4, a plain-words summary for the signers: passed.
   ...
   The reviewer's verdict: PASS.
   ...
   When you sign the form, you accept this draft whole. Gate 5: the Ontology Owner signs, and the module's first release is 1.0.0, a major.
   ```

   The document test signs the form with this block.

   ```python run=ai-modelling
   import json
   from pathlib import Path

   path = Path("../ai-modelling/sample-tank-inspections.new-module.json")
   form = json.loads(path.read_text(encoding="utf-8"))
   form["sign_offs"] = {"data-owner": {"name": "A Data Owner", "date": "2026-11-20"},
                        "ontology-owner": {"name": "An Ontology Owner", "date": "2026-11-20"},
                        "architect": {"name": "An Architect", "date": "2026-11-20"}}
   path.write_text(json.dumps(form, indent=2) + "\n", encoding="utf-8")
   print("signed by", ", ".join(sorted(form["sign_offs"])))
   ```

   ```text expect
   signed by architect, data-owner, ontology-owner
   ```

   You are done when the three signers have signed the form.

8. Turn the signed form into a proposal. The command runs gates 1, 2 and 4 again against the release as it is now, and adds gate 5 from the Ontology Owner's signature. It changes nothing in the ontology.

   ```powershell run=ai-modelling
   python -m kpi_store.propose ../ai-modelling/sample-tank-inspections.new-module.json
   ```

   ```text expect
   wrote the proposal ../ai-modelling/proposals/NM-2026-003: 10 changes and 4 facts, route major
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

   You are done when the command has written the folder `proposals/NM-2026-003`. Its `summary.txt` lists every gate as passed, and its `approval.json` holds the record of the draft under `"draft"`.

9. Apply the proposal. The apply checks every gate again before it writes anything. It then works as for any new module: it writes the module's folder from the draft, with a builder, a test file and a README, registers the module, releases it at 1.0.0, and runs every check. It took about four minutes on a Mac.

   ```powershell run=ai-modelling
   python -m kpi_store.apply ../ai-modelling/proposals/NM-2026-003
   ```

   ```text expect
   1 proposal to apply:
     NM-2026-003: major, signed by Data Owner, Ontology Owner, Architect
   ...
     sample-tank-inspections: a new module at 1.0.0
   ...
   ... write the sample-tank-inspections module's folder from its AI draft and register it in every place
   ...
   ... run every module's shapes over the whole graph
   ...
   ... write the release
   Done. sample-tank-inspections 1.0.0 is a new module (major). The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

   You are done when the command ends with `Done. sample-tank-inspections 1.0.0 is a new module (major).`

10. See the commit and the module's own check. Its builder runs gates 1, 2 and 4 again each time the full check runs.

    ```powershell run=ai-modelling
    git --no-pager log --oneline -1
    cd business_architecture/ontology/sample-tank-inspections
    python build_sample_tank_inspections.py --verify
    ```

    ```text expect
    <commit> Apply the new module NM-2026-003: sample-tank-inspections 1.0.0
    classes 1; properties 2; node shapes 1; questions 1; failing examples 2
    gate 1, competency questions and examples: passed
    gate 2, the reasoner finds the model consistent: passed
    gate 4, a plain-words summary for the signers: passed
    model.ttl and shapes.ttl are current
    ```

    You are done when the builder says `model.ttl and shapes.ttl are current`. Then run the full check, as in "Before you change anything", step 3, and load the stores with the runner, as in step 11 of "The release steps".

## Onboard another module

A module is one part of the ontology with its own version, such as `kpi`. Add a module when a new data area brings terms that no module owns. A vocabulary or a reference table goes through the new-module form ("Add a module with the new-module form" above). This section is the specialist's path, for a module that the form's patterns do not cover and that no AI drafts: one with a new class, a new property or a rule of its own. It says how to decide, where to register the module, and how its tables join the discovery comparison. It ends with a made-up example that you can run.

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
4. Run the builder from `business_architecture/ontology/data-product`: `python build_pricing.py --write`. It fails on a name that does not resolve.
5. Release `data-product` as a minor version, with its cascade ("The release steps").
6. Run `python -m kpi_store.runner`. The run now compares the new tables with the workspace.

The cut tool applies corrections to the tables in `data-product/pricing/` only. A difference in any other module's content goes through the release steps of this guide, not through the cut.

### Release the module at 1.0.0

1. Run the module's builder with `--write`, from the module's folder.
2. Write the package: `python build_module.py <module> --write`, from `business_architecture/ontology/release`.
3. Rebuild the catalog: `python build_catalog.py --write`, from the same folder.
4. Rebuild the projection manifest: `python pipeline.py build`, from `business_architecture/ontology/projection`.
5. Run the competency questions: `python run.py`, from `business_architecture/ontology/regression`.
6. Rebuild the KPI intake pack: `python -m kpi_store.intake build`, from the top folder. Its lists name the release's modules.
7. Rebuild the pages: `python scripts/build_docs_html.py`, from the top folder.
8. Run the full check. Do not share the module until it prints `all checks passed`.

A first release needs no cascade. No released module requires the new one yet. A module that should link to it does so in its own next release.

### Reload the stores

The projection takes every module in `PACKAGES`, so the new module goes into Neo4j with the others. No store needs a setting of its own for it.

1. Run `python -m kpi_store.runner --replace-enterprise`. The Enterprise database holds the earlier release, so the copy needs the replace.
2. Read the last line. Expect `every step passed`.
3. Run `python -m kpi_store.sync_check`. Every line must read `current`.

The runbook, `business_architecture/ontology/projection/ontology-stores-runbook.md`, explains each line of both commands.

### A worked example: the made-up module `sample-area`

The release holds a helper, `release/onboard_example.py`, that onboards one made-up module. It writes the six files of the folder and registers the module in each place of the table above. Read its functions as the pattern for your own module: it has one function per place.

**Run the example in a copy of the release, never in the folder you load the stores from.** It adds a made-up module to the ontology.

The commands start in the top folder of the copy.

1. List the places. This changes nothing.

   ```powershell run=new-module
   cd business_architecture/ontology/release
   python onboard_example.py --plan
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
   python onboard_example.py --write
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
   python build_sample_areas.py --write
   ```

   ```text expect
   areas 3; covered processes 3
   wrote sample-areas.ttl
   ```

4. Write the package at 1.0.0, then rebuild the catalog.

   ```powershell run=new-module
   cd ../release
   python build_module.py sample-area --write
   python build_catalog.py --write
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
   python pipeline.py build
   ```

   ```text expect
   ...
   wrote projection-manifest.json
   ```

6. Run the competency questions. The count is one higher than before: the module's question is number 58.

   ```powershell run=new-module
   cd ../regression
   python run.py
   ```

   ```text expect
   competency coverage on <the core release>: 58 questions; answerable 57, partial 0, waiting 0, parked 1
   ```

7. Rebuild the KPI intake pack. Its lists name the release's modules, so a new module makes them older than the packages, and the full check then stops on the pack.

   ```powershell run=new-module status-only
   cd ../../..
   python -m kpi_store.intake build
   ```

8. Rebuild the pages, and tell Git about the new files. One test reads which pages Git tracks.

   ```powershell run=new-module status-only
   python scripts/build_docs_html.py
   git add -A
   ```

9. Run the full check. It takes about 10 minutes. On Windows, run it in Git Bash.

   ```bash run=new-module
   bash scripts/check.sh
   ```

   ```text expect
   ...
   all checks passed
   ```

10. Run the helper again. It refuses a copy that holds the module, and changes nothing.

    ```powershell run=new-module exit=1
    cd business_architecture/ontology/release
    python onboard_example.py --write
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
   python build_logical_model.py --export models/customer-logical-model.erstudio.ttl --links models/customer-logical-model.links.csv --model customer-logical-model --title "Customer logical model" --out models --verify
   ```

3. In `release/build_module.py`, add the model's two graph files to the `graphs` list of the `logical-model` entry: the `.erstudio.ttl` file and the `.layer.ttl` file that the builder wrote.
4. In `scripts/check.sh`, add the new model's four options to the line that runs `build_logical_model.py`, so that the check rebuilds every model.
5. Release `logical-model` as a minor, with "The release steps" from step 3.

The stores load each model: Fuseki and Databricks its two graphs as named graphs, the two Neo4j databases the model as its own subgraph. The sync check prints an `lm:` line for each Neo4j database.

A build can also read a model's files from a folder outside your copy. Point `--export` and `--links` at them, and keep `--out` at `models`. List each file with its SHA-256 in the `augment` list of the `logical-model` entry, and compare the files with those hashes before you build from them again.

## Keep the catalog, the regression and the projection current

| Part | Command, from its folder | When |
|---|---|---|
| The catalog, `releases/catalog.ttl` | `python build_catalog.py --write`, in `release` | After any package is written. |
| The regression | `python run.py`, in `regression` | After any change. A new question goes in `regression/expected.csv`, with its query in `regression/queries`. |
| The projection manifest | `python pipeline.py build`, in `projection` | After any package is written. The check fails until you run it. |

Step 7 of "The release steps" runs all three.

## Keep every store in step

Your packages are the master copy. Each store is a copy that falls behind when you release.

1. After every release, run the runner. It loads Databricks, Fuseki, the local Neo4j and Enterprise, and then runs the sync check.
2. To see later which store is behind, run the sync check alone. The runbook's "The sync check" shows the command and how to read each line.
3. To repair a store, run the runner again. Do not fix a store by hand.
4. To load every store again from nothing, for example to show the load, follow the runbook's "Empty every store and load again".

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
4. Write every package again in the order `dependents.py core` prints. Then rebuild the catalog, the projection manifest and the KPI intake pack, as steps 7 and 8 of "The release steps" say, and run the full check.

## What you can ignore

These describe how the ontology was first built. You need none of them to update it.

- Part 2 of `business_architecture/ontology/epm-walkthrough.html`, and the folder `build`, apart from the identity map named above.
- The folder `step4` and the older core builders, `build_core_next.py` and `build_core_2_1.py`, which rebuild earlier releases.
- The folder `release/frozen`, apart from the copies you add.
- `business_architecture/domain/decision-packages`, questions put to the subject matter expert during the build.
- `business_architecture/ontology/business-closeout.md`, and any note in a README or changelog dated before you received this release.
