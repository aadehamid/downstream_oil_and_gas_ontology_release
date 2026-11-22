# Running and changing your ontology

This handout is for the people who run the KPI Store after handover: the Data Owners, the Domain Owners, the Ontology Owner, the Architect and the platform team. You do not need to have built an ontology. You type the commands that this handout shows, and you read what they print. You never edit an ontology file by hand: the commands write every change, and they refuse a change they cannot check.

It takes you from the release zip to loaded and checked stores, and then through every kind of change: a change form, a new module, a change an AI helps to write, a check and a recovery, a replace or a reset, an upgrade of the tools, and the refresh of what people use. Each step ends with **You are done when**. Do not go on to the next step until that is true.

Every command and every printed line in this handout is quoted from the release's two detailed guides, the stores runbook and `HOW-TO-UPDATE.md`, where the release's own tests run it and compare what it prints. When this handout and a detailed guide seem to differ, the detailed guide is right: tell the release's team.

**Warning: a replace or a reset deletes data in the stores.** Get written authorization for the exact environment first, stop every other writer, and make sure the data can be loaded again.

## What is inside the release

| Part | What it is | Do you open it? |
|---|---|---|
| The commands, in `kpi_store/` | Everything you run: the setup check, the runner, the change commands, the upgrade | No. You run them |
| The ontology, in `business_architecture/ontology/` | The modules, their packages and their checks | No. The commands change it |
| The KPI intake pack, in `kpi-intake/` | The change forms, as an HTML page and an Excel workbook | Yes. You fill the forms |
| The skills, in `skills/` | The rules that the commands and the AI follow when they model, check and write | No. The commands and the AI read them |
| The stores runbook, `business_architecture/ontology/projection/ontology-stores-runbook.md` | Every detail of setting up, loading and recovering | When a step here sends you there |
| `HOW-TO-UPDATE.md` | Every detail of each kind of change | When a step here sends you there |

## The conventions

- The commands run on Windows, in PowerShell, unless a step says Git Bash.
- Start every command in the release folder, `%USERPROFILE%\kpi-store-1.1`, unless a step says otherwise.
- Write your own value where a command shows text in angle brackets, such as `<your workspace URL>`.
- Keep passwords, settings files and filled forms outside the release folder. The release folder is zipped and uploaded.

## 1. Set up the machine, once

1. Get the access the runbook's "What you need" lists: the Databricks workspace and its SQL warehouse, the Neo4j Enterprise database, a local Neo4j you may empty, and the network.

   You are done when every owner has answered.

2. Install the programs: Python, Git for Windows, Java and the Databricks command line, as the runbook's "Install the programs" says. Without administrator rights, follow "Install the programs without administrator rights" instead.

   ```cmd excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   winget install Databricks.DatabricksCLI
   ```

   You are done when a new PowerShell window finds `python`, `git`, `java` and `databricks`.

3. Unpack the release zip to `%USERPROFILE%\kpi-store-1.1`, as the runbook's "Unpack the release" says. Then put the folder in Git. Write your own name and address in the two `git config` lines.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   git init
   git config user.name "KPI Store operator"
   git config user.email "kpi-store-operator@example.invalid"
   git add -A
   git commit -m "KPI Store 1.1 as shipped"
   ```

   You are done when the commit is made. The upgrade of section 8 starts from this commit.

4. Make the local folder and fetch the three files the runbook's "Make the local folder and fetch three files" names. Then install the Python packages at the versions the release was tested with.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m pip install rdflib==7.6.0 pyshacl==0.40.2 owlrl==7.6.2 pyoxigraph==0.5.13 neo4j==6.4.1 databricks-sdk==0.164.0 sqlglot==30.31.0 pyyaml==6.0.3 openpyxl==3.1.5 uv
   ```

   You are done when the last line starts with `Successfully installed`.

5. Set up the local Neo4j, as the runbook's "Set up the local Neo4j" says.

   You are done when its database runs with the APOC and n10s plugins.

6. Write the two settings files, as the runbook's "Write the two settings files" says, and tell every command where the local one is. Then close PowerShell and open it again.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   setx KPI_STORE_LOCAL "$HOME\kpi-store-local\stores.toml"
   ```

   You are done when it answers `SUCCESS: Specified value was saved.`

7. Sign in to Databricks. Your browser opens the sign-in page.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   databricks auth login --host <your workspace URL> --profile DEFAULT
   ```

   You are done when the terminal says that the profile `DEFAULT` was saved.

8. Run the setup check from the release folder. It only reads.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   cd $HOME\kpi-store-1.1
   ```

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.setup_check
   ```

   You are done when its last line reads:

   ```text excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   15 of 15 checks passed
   ```

   A line that starts with `FAIL` names its fix. Do it, then run the setup check again.

## 2. Load the stores for the first time

The first run compares the release with your workspace and stops on a report. You decide each row of the report. The second run then corrects the release and loads every store.

1. See what the run will do. It runs nothing.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --dry-run
   ```

   You are done when it lists the steps, from `cut` to `summary`.

2. Start the first run. It took about 40 minutes on the Windows laptop of the first real run.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner
   ```

   You are done when it stops with a line that starts `report: STOPPED`. That is the result you want here.

3. Clear the report in Excel, as the runbook's "Clear the report" says: open `discovery-report.to-clear.csv` in `%USERPROFILE%\kpi-store-local\runs\pending`, keep each decision the runbook's table tells you to accept, and write your role or initials in `decided_by`. Save it as "CSV UTF-8".

   You are done when every row that blocks the load has a decision and your role.

4. Run the same command again. It shows the cut's plan and asks you to type two answers. The runbook's "The second run: the cut and the loads" says what to type. It takes about 40 minutes.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner
   ```

   You are done when its last line reads `every step passed`.

5. Check the four stores. The sync check only reads.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.sync_check
   ```

   You are done when every line reads `current`:

   ```text excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   databricks      current     <why>
   jena            current     <why>
   neo4j           current     <why>
   enterprise      current     <why>
   ```

## 3. Make an everyday change with a form

Every everyday change goes the same way: someone fills a form, the signers sign it, you check it, a command turns it into a proposal, and a second command applies the proposal and releases the changed modules. Nobody edits a table or a Turtle file. If a step fails, the release is as it was.

The forms are in the KPI intake pack: `kpi-intake/kpi-intake-form.html`, which works offline in a browser, and the same form as `kpi-intake/kpi-intake-form.xlsx`. `kpi-intake/how-to-use-the-form.html` says how to fill and save one. Keep the filled form, and the proposal the command writes beside it, in a folder beside the release folder, never inside it.

| The change | The form | Its section in `HOW-TO-UPDATE.md` |
|---|---|---|
| A new KPI | KPI intake | "Add a KPI with the KPI intake form" |
| A changed measure | Term change | "Change a measure with the term-change form" |
| A new system or table | Reference item | "Add a system or a table with the reference-item form" |
| A domain the ontology should use | Domain activation | "Activate a domain with the domain activation form" |
| Roles, RACI entries or a new process | Process map request | "Add roles and RACI entries with the process map request" |
| A new vocabulary or reference table | New module | Section 4 below |

The steps below add a KPI. The other forms take the same four commands, with their own file and proposal names.

1. Check the filled form. The check changes nothing.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.intake check ../new-kpi/sample-spread-margin.kpi-intake.json
   ```

   You are done when it ends with:

   ```text excerpt=HOW-TO-UPDATE.md
   Result: the intake is complete and signed.
   ```

2. Turn the form into a proposal. It writes a folder under `proposals`, beside the form, and changes nothing in the ontology.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose ../new-kpi/sample-spread-margin.kpi-intake.json
   ```

   ```text excerpt=HOW-TO-UPDATE.md
   wrote the proposal ../new-kpi/proposals/NK-2026-001: 19 changes and 17 facts, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

   You are done when the folder `proposals/NK-2026-001` exists.

3. Read the proposal's `summary.txt`, and have the Architect read it too. Open it in Notepad, or print it with the line below. It says what the change adds, which modules it reaches, the route, who signed, and what the Architect must still do outside the form.

   ```python excerpt=HOW-TO-UPDATE.md
   print(open("../new-kpi/proposals/NK-2026-001/summary.txt", encoding="utf-8").read())
   ```

   You are done when the summary says what the form asked for.

4. Apply the proposal. It works in a temporary copy, rebuilds and checks each changed module, releases it, and writes and commits the release only when every step has passed.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.apply ../new-kpi/proposals/NK-2026-001
   ```

   You are done when it ends with these lines:

   ```text excerpt=HOW-TO-UPDATE.md
   Done. kpi is now 1.4.0, data-product 1.3.0 and value-stream 1.3.0 (minor), and 4 modules that depend on them took a new patch. The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

5. See the commit.

   ```powershell excerpt=HOW-TO-UPDATE.md
   git --no-pager log --oneline -1
   ```

   You are done when it names the proposal.

6. Run the full check, as section 6 says, then load the stores with the runner, as in section 2, step 4.

   You are done when the sync check reads `current` on every line.

## 4. Add a module

A new module goes in through the "New module" tab of the form and the same commands. It is a vocabulary, a list of terms with their definitions, or a reference table, items of a class the ontology holds already. A new module's first release is 1.0.0, a major, so the Data Owner, the Ontology Owner and the Architect sign the form. `HOW-TO-UPDATE.md`, "Add a module with the new-module form", has both kinds.

1. Check the form.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.intake check ../new-vocabulary/sample-equipment-terms.new-module.json
   ```

   You are done when it ends with `Result: the intake is complete and signed.`

2. Turn it into a proposal.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose ../new-vocabulary/sample-equipment-terms.new-module.json
   ```

   ```text excerpt=HOW-TO-UPDATE.md
   wrote the proposal ../new-vocabulary/proposals/NM-2026-001: 18 changes and 4 facts, route major
   ```

   You are done when its `summary.txt` names the module and each term.

3. Apply it. It writes the module's folder, registers the module in every place the release lists its modules, builds it, and releases it at 1.0.0. It took about three minutes on a Mac.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.apply ../new-vocabulary/proposals/NM-2026-001
   ```

   You are done when it ends with:

   ```text excerpt=HOW-TO-UPDATE.md
   Done. sample-equipment-terms 1.0.0 is a new module (major). The apply changed <count> files, and Git committed them.
   ```

4. Run the full check and load the stores, as in section 3, step 6.

   You are done when the sync check reads `current` on every line.

## 5. Let an AI help

An AI can help in two ways. In both, the commands check what the AI writes, people decide and sign, and nothing reaches the ontology until the apply's checks pass. Name the AI in the local settings file, as `HOW-TO-UPDATE.md`, "Choose the provider", says: usually a model served in your Databricks workspace, approved by your IT. The steps below use the `by-hand` provider, with which the command writes a prompt file, you give it to an assistant such as Genie Code, and you save its answer. With another provider, the command asks the model itself.

**Suggestions for a form.** The AI suggests answers to a form before anyone signs it. `HOW-TO-UPDATE.md`, "Use AI to suggest answers (optional)", has the whole example.

1. Ask for suggestions. The command writes the prompt to a file and stops.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose --ai ../ai-suggestions/unit-utilization.term-change.json --stores ../ai-suggestions/kpi-store-local.toml
   ```

   You are done when it names the prompt file it wrote.

2. Give the prompt file to the assistant, and save its answer beside the form. Then run the command again with the answer. It shows each suggestion and asks you to accept it or not.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose --ai ../ai-suggestions/unit-utilization.term-change.json --stores ../ai-suggestions/kpi-store-local.toml --ai-answer ../ai-suggestions/unit-utilization.term-change.ai-answer.json
   ```

   You are done when the form holds the answers you accepted. The signers then sign it, and it goes on as in section 3.

**A draft of new modelling.** A module that needs a class, a property or a rule of its own is new modelling. One AI drafts it, a second AI of another family reviews it, and five gates check it. `HOW-TO-UPDATE.md`, "Draft new modelling with AI (optional)", has every step, with the prompt files and the two answers.

1. Ask the AI to draft the module from the unsigned new-module form.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose --ai-draft ../ai-modelling/sample-tank-inspections.new-module.json --stores ../ai-modelling/kpi-store-local.toml
   ```

   You are done when the guide's steps 2 to 7 are done: the draft passed its gates, the reviewer said PASS, and the three signers signed the form.

2. Turn the signed form into a proposal, and apply it.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose ../ai-modelling/sample-tank-inspections.new-module.json
   ```

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.apply ../ai-modelling/proposals/NM-2026-003
   ```

   You are done when the apply ends with:

   ```text excerpt=HOW-TO-UPDATE.md
   Done. sample-tank-inspections 1.0.0 is a new module (major). The apply changed <count> files, and Git committed them.
   ```

3. Run the full check and load the stores, as in section 3, step 6.

## 6. Check the release and recover from a failure

1. Run the full check after every change, before you load. Open Git Bash in the release folder: in File Explorer, right-click the folder and choose "Open Git Bash here". It took 21 minutes on a Windows machine with 4 cores.

   ```bash excerpt=HOW-TO-UPDATE.md
   bash scripts/check.sh
   ```

   You are done when its last line reads `all checks passed`. A line that starts `FAIL a store request` comes from a test that fails a write on purpose, and is expected.

2. See which store is behind, at any time. The sync check only reads.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.sync_check
   ```

   You are done when you know which lines do not read `current`. The runbook's "The sync check" says what each status means.

3. When a run stops on a step, read the line it names, fix what it says, and run again from that step. The runbook's "When a step fails" lists each step's failures and fixes. For example, to start again at the Fuseki load:

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --from fuseki
   ```

   You are done when the run's last line reads `every step passed`.

4. If the check step fails because of the machine, such as a file another program holds open, and not because of the release, report it and leave the step out of the run:

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --skip check
   ```

   You are done when the last line names the step that was left out. A run with a step left out never says `every step passed`.

## 7. Replace what a store holds, or reset every store

**These commands delete data.** Have the written authorization ready before you start.

1. Replace what Neo4j Enterprise holds, when the runbook's "Replace what Enterprise holds: one case" applies.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --from enterprise --replace-enterprise
   ```

   You are done when the sync check reads `current` for `enterprise`.

2. To empty every store and load it again, first see what the reset would delete. It deletes nothing.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --reset --dry-run
   ```

   You are done when the person who authorized the reset has read the list.

3. Run the reset. It asks you to type the word `reset`.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --reset
   ```

   You are done when the sync check reads `unmarked` for each store that was emptied.

4. Load every store again, as in section 2, step 4.

   You are done when the sync check reads `current` on every line.

## 8. Upgrade the tools from a newer release

Your copy is the master of the ontology. A newer release from the release's team brings new tools: the commands, the scripts, the skills and the guides. The upgrade takes them into your copy and keeps every change you applied. It runs the full check on the merged copy, and changes your folder only when that passes. `HOW-TO-UPDATE.md`, "Upgrade the tools from a newer release", says how it decides which files are tools.

1. Save the new zip beside the release folder. Commit every change in the release folder first: the upgrade refuses a copy with changes that are not committed. Then see what the upgrade would do. The plan changes nothing.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.upgrade --from ../kpi-store-newer.zip --plan
   ```

   You are done when the zip's SHA-256 in the first line equals the one the release's team sent you, and you have read the plan.

2. Upgrade. It takes about 20 minutes, most of it the full check.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.upgrade --from ../kpi-store-newer.zip
   ```

   You are done when it ends with a line that starts `Upgraded to the tools of`. When it stops instead, your folder is as it was: send its message, and the files or the log it names, to the release's team.

3. Load the stores with the runner, as in section 2, step 4.

   You are done when the sync check reads `current` on every line.

## 9. Refresh what people use

The commands of sections 3 to 5 rebuild what they change: the KPI intake pack's lists and the release's pages. After a change, people still need the new copies.

1. Rebuild the KPI intake pack, when you have changed `kpi-intake/settings.toml`, for example to add a domain or a role title.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.intake build
   ```

   Then copy the new forms into the team's shared folder with the `folders` command, as `kpi-intake/README.md`, "The shared folder", shows. It replaces the forms and the guide in `the-form`, and changes nothing in the folders that hold people's answers.

   You are done when the `folders` command ends with:

   ```text excerpt=kpi-intake/README.md
   KPI-intake is ready
   ```

2. Rebuild the release's pages after you have changed a guide.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python scripts/build_docs_html.py
   ```

   You are done when the full check passes: it fails when a page differs from a fresh build.

3. Load the stores, as in section 2, step 4, so that Databricks, the two Neo4j databases and Fuseki hold the new release.

   You are done when the sync check reads `current` on every line.
