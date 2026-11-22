# Running and changing your ontology

This handout is for the people who run the KPI Store after handover: the Data Owners, the Domain Owners, the Ontology Owner, the Architect and the platform team. You do not need to have built an ontology. You type the commands that this handout shows, and you read what they print. You never edit an ontology file by hand: the commands write every change, and they refuse a change they cannot check.

It takes you from the release zip to loaded and checked stores, and then through every kind of change: a change form, a new module, a change an AI helps to write, a check and a recovery, a replace or a reset, an upgrade of the tools, and the refresh of what people use. Each step ends with **You are done when**. Do not go on to the next step until that is true.

The release's own tests check every command and printed line in this handout. Most are quoted from the release's detailed guides, the stores runbook, `HOW-TO-UPDATE.md` and `kpi-intake/README.md`, where the tests run them. The rest run in this handout itself. The tests cannot open a browser, so the Databricks sign-in is the one command they parse and do not run. When this handout and a detailed guide seem to differ, the detailed guide is right: tell the release's team.

**Warning: a replace or a reset deletes data in the stores.** Get written authorization for the exact environment first, stop every other writer, and make sure the data can be loaded again.

## What is inside the release

| Part | What it is | Do you open it? |
|---|---|---|
| The commands, in `kpi_store/` | Everything you run: the setup check, the runner, the change commands, the upgrade | No. You run them |
| The ontology, in `business_architecture/ontology/` | The modules, their packages and their checks | No. The commands change it |
| The KPI intake pack, in `kpi-intake/` | The change forms, as an HTML page and an Excel workbook, and `kpi-intake/README.md`, which says what each form asks | Yes. You fill the forms |
| The skills, in `skills/` | The rules that the commands and the AI follow when they model, check and write | No. The commands and the AI read them |
| The stores runbook, `business_architecture/ontology/projection/ontology-stores-runbook.md` | Every detail of setting up, loading and recovering | When a step here sends you there |
| `HOW-TO-UPDATE.md` | Every detail of each kind of change | When a step here sends you there |

## The conventions

- The commands run on Windows, in PowerShell, unless a step says Git Bash.
- Start every command in the release folder, `%USERPROFILE%\kpi-store-1.1`, unless a step says otherwise.
- Write your own value where a command shows text in angle brackets, such as `<your workspace URL>`.
- The commands of sections 3 to 5 and 8 show the file names of the detailed guides' made-up examples, such as `../new-kpi/sample-spread-margin.kpi-intake.json`. Write the path of your own file in their place.
- Keep passwords, settings files and filled forms outside the release folder. The release folder is zipped and uploaded.

## 1. Set up the machine, once

1. Get the access that the runbook's "What you need" lists: the Databricks workspace and its SQL warehouse, the Neo4j Enterprise database, a local Neo4j you may empty, and the network.

   You are done when every owner has answered.

2. Install Python, Git for Windows, Java and the Databricks command line, as the runbook's "Install the programs" says. Its last step installs the Databricks command line with this command:

   ```cmd excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   winget install Databricks.DatabricksCLI
   ```

   Without administrator rights, follow the runbook's "Install the programs without administrator rights" instead. It unpacks Git, Java and the Databricks command line into your local folder, and the settings file of step 7 names them.

   You are done when every installer has finished, or the three folders are unpacked. The setup check of step 9 proves each program.

3. Read the runbook's "What Windows itself needs". For most points you do nothing. Three matter later: run the full check in Git Bash, not in PowerShell; keep the file `.gitattributes` of the release; and keep your local folder private to your account.

   You are done when you have read it.

4. Unpack the release zip to `%USERPROFILE%\kpi-store-1.1`, as the runbook's "Unpack the release" says. Open a new PowerShell window and go to the release folder:

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   cd $HOME\kpi-store-1.1
   ```

   Then put the folder in Git, as the runbook's "Keep the release folder in Git" says. Write your own name and address in the two `git config` lines.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   git init
   git config user.name "KPI Store operator"
   git config user.email "kpi-store-operator@example.invalid"
   git add -A
   git commit -m "KPI Store 1.1 as shipped"
   ```

   You are done when the commit is made. The upgrade of section 8 starts from this commit.

5. Make the local folder and fetch the three files that the runbook's "Make the local folder and fetch three files" names. Then install the Python packages at the versions the release was tested with:

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m pip install rdflib==7.6.0 pyshacl==0.40.2 owlrl==7.6.2 pyoxigraph==0.5.13 neo4j==6.4.1 databricks-sdk==0.164.0 sqlglot==30.31.0 pyyaml==6.0.3 openpyxl==3.1.5 uv
   ```

   You are done when it ends without an error. A machine that holds the packages already says `Requirement already satisfied`.

6. Set up the local Neo4j, as the runbook's "Set up the local Neo4j" says.

   You are done when its database runs with the APOC and n10s plugins.

7. Write the two settings files, as the runbook's "Write the two settings files" says. Then tell every command where the local one is:

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   setx KPI_STORE_LOCAL "$HOME\kpi-store-local\stores.toml"
   ```

   It answers `SUCCESS: Specified value was saved.` The setting reaches new windows only, so close PowerShell, open it again, and go to the release folder as in step 4.

   You are done when you work in a new PowerShell window, in the release folder.

8. Sign in to Databricks. Your browser opens the sign-in page.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   databricks auth login --host <your workspace URL> --profile DEFAULT
   ```

   Without administrator rights, `databricks` is not on your `PATH`: start it with its path, `$HOME\kpi-store-local\databricks-cli\databricks.exe`, in place of the word `databricks`.

   You are done when the terminal says that the profile `DEFAULT` was saved.

9. Run the setup check. It only reads.

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

3. Clear the report in Excel, as the runbook's "Clear the report" says: open `discovery-report.to-clear.csv` in `%USERPROFILE%\kpi-store-local\runs\pending`, keep each decision that the runbook's table tells you to accept, and write your role or initials in `decided_by`. Save it as "CSV UTF-8".

   You are done when every row that blocks the load has a decision and your role.

4. Run the same command again. It shows the cut's plan and asks you to type two answers: the runbook's "The second run: the cut and the loads" says what to type. It takes about 40 minutes.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner
   ```

   You are done when its last line reads `every step passed`.

5. Check the stores. The sync check only reads.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.sync_check
   ```

   You are done when every line reads `current`, as these first lines do:

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
| Roles or RACI entries | Process map request | "Add roles and RACI entries with the process map request" |
| A new process, step or business area | Process map request | "Add a process, a step or a business area with the process map request" |
| A new vocabulary or reference table | New module | Section 4 below |

The steps below add a KPI, from the guide's example Sample Spread Margin, saved in a folder `new-kpi` beside the release folder. The other forms take the same four commands.

1. Check the filled form. The check changes nothing.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.intake check ../new-kpi/sample-spread-margin.kpi-intake.json
   ```

   You are done when it ends with:

   ```text excerpt=HOW-TO-UPDATE.md
   Result: the intake is complete and signed.
   ```

2. Turn the form into a proposal. It changes nothing in the ontology. It writes a proposal folder in a folder `proposals` beside the form, and names it:

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose ../new-kpi/sample-spread-margin.kpi-intake.json
   ```

   ```text excerpt=HOW-TO-UPDATE.md
   wrote the proposal ../new-kpi/proposals/NK-2026-001: 19 changes and 17 facts, route minor
   Nothing in the ontology has changed. Read each summary.txt, then apply with: python -m kpi_store.apply <proposal folder>
   ```

   You are done when it has named the proposal folder it wrote. Your proposal has its own number.

3. Open the proposal's `summary.txt` in Notepad, and have the Architect read it too. It says what the change adds, which modules it reaches, the route, who signed, and what the Architect must still do outside the form.

   You are done when the summary says what the form asked for.

4. Apply the proposal, with the folder that step 2 named. The command works in a temporary copy, rebuilds and checks each changed module, releases it, and writes and commits the release only when every step has passed.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.apply ../new-kpi/proposals/NK-2026-001
   ```

   You are done when it ends with a line that starts `Done.`, which names each changed module and its new version, and the line after it. For the example they read:

   ```text excerpt=HOW-TO-UPDATE.md
   Done. kpi is now 1.4.0, data-product 1.3.0 and value-stream 1.3.0 (minor), and 4 modules that depend on them took a new patch. The apply changed <count> files, and Git committed them.
   Run the full check before you load: bash scripts/check.sh (on Windows, in Git Bash). Then load the stores with the runner: python -m kpi_store.runner
   ```

5. See the commit.

   ```powershell excerpt=HOW-TO-UPDATE.md
   git --no-pager log --oneline -1
   ```

   You are done when it names your proposal.

6. Check the release and load the stores, as section 6, "After every change", says.

   You are done when that part is done.

## 4. Add a module

A new module goes in through the "New module" tab of the form and the same commands. It is a vocabulary, a list of terms with their definitions, or a reference table, items of a class the ontology holds already. A new module's first release is 1.0.0, a major, so the Data Owner, the Ontology Owner and the Architect sign the form. `HOW-TO-UPDATE.md`, "Add a module with the new-module form", has both kinds. The commands below are those of its example, the made-up vocabulary Sample Equipment Terms.

1. Check the form.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.intake check ../new-vocabulary/sample-equipment-terms.new-module.json
   ```

   You are done when it ends with `Result: the intake is complete and signed.`

2. Turn it into a proposal.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose ../new-vocabulary/sample-equipment-terms.new-module.json
   ```

   You are done when it has named the proposal folder it wrote, and its `summary.txt` names the module and each term.

3. Apply it, with that folder. The command writes the module's folder, registers the module in every place the release lists its modules, builds it, and releases it at 1.0.0. It took about three minutes on a Mac.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.apply ../new-vocabulary/proposals/NM-2026-001
   ```

   You are done when it ends with a line that starts `Done.` and names your module, as the example's does:

   ```text excerpt=HOW-TO-UPDATE.md
   Done. sample-equipment-terms 1.0.0 is a new module (major). The apply changed <count> files, and Git committed them.
   ```

4. Check the release and load the stores, as section 6, "After every change", says.

   You are done when that part is done.

## 5. Let an AI help

An AI can help in two ways. In both, the commands check what the AI writes, people decide and sign, and nothing reaches the ontology until the apply's checks pass.

The AI is named in your local settings file, as `HOW-TO-UPDATE.md` says in "Choose the provider" for suggestions and in "Choose the two AI providers" for new modelling: usually a model served in your Databricks workspace, approved by your IT. With such a model, the command asks the model itself. The steps below show the `by-hand` provider instead, as the guide's examples do: the command writes a prompt file, you give it to an assistant such as Genie Code, and you save its answer to a file. With a served model, leave out the steps that hand over a prompt or an answer.

The guide's examples name a settings file of their own with `--stores`. Your commands find your settings file through `KPI_STORE_LOCAL`, so leave out `--stores` and the file after it.

### Suggestions for a form

The AI suggests answers to a form before anyone signs it. `HOW-TO-UPDATE.md`, "Use AI to suggest answers (optional)", has the whole example.

1. Ask for suggestions. With the `by-hand` provider, the command writes the prompt to a file and stops.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose --ai ../ai-suggestions/unit-utilization.term-change.json --stores ../ai-suggestions/kpi-store-local.toml
   ```

   You are done when it names the prompt file it wrote.

2. Give the prompt file to the assistant, and save its answer beside the form, as the command says. Then run the command again with the answer. It shows each suggestion and asks you to accept it or not.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose --ai ../ai-suggestions/unit-utilization.term-change.json --stores ../ai-suggestions/kpi-store-local.toml --ai-answer ../ai-suggestions/unit-utilization.term-change.ai-answer.json
   ```

   You are done when the form holds the answers you accepted. The signers then sign it, and it goes on as in section 3.

### A draft of new modelling

A module that needs a class, a property or a rule of its own is new modelling. One AI drafts it, a second AI of another model family reviews it, and five gates check it. `HOW-TO-UPDATE.md`, "Draft new modelling with AI (optional)", has every step. Start from a new-module form that asks for new modelling, filled and not signed.

1. Ask the AI to draft the module. With the `by-hand` provider, the command writes the drafter's prompt to a file and stops.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose --ai-draft ../ai-modelling/sample-tank-inspections.new-module.json --stores ../ai-modelling/kpi-store-local.toml
   ```

   You are done when it names the prompt file it wrote.

2. Give the prompt file to the drafter's assistant, save its answer as the command says, and run the command again with the draft. It checks the draft with gates 1, 2 and 4, then writes the reviewer's prompt and stops.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose --ai-draft ../ai-modelling/sample-tank-inspections.new-module.json --stores ../ai-modelling/kpi-store-local.toml --ai-answer ../ai-modelling/sample-tank-inspections.new-module.draft-answer.json
   ```

   You are done when it says that gates 1, 2 and 4 passed and names the reviewer's prompt file. If a gate fails, it says why and keeps nothing: ask the AI again, and give it those lines.

3. Give the reviewer's prompt to the reviewer's assistant, of the other model family, save its answer as the command says, and run the command again with the review. The review is gate 3. The command writes the summary that the signers read.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose --ai-draft ../ai-modelling/sample-tank-inspections.new-module.json --stores ../ai-modelling/kpi-store-local.toml --review-answer ../ai-modelling/sample-tank-inspections.new-module.review-answer.json
   ```

   You are done when it says gate 3 passed and names the summary for the signers. If the reviewer answers HOLD, do what the guide's step 6 says.

4. The Data Owner, the Ontology Owner and the Architect read the summary, then load the form in the HTML form ("Load answers file"), sign and save it. Do not change any answer now: the next command refuses a form whose answers changed after the AI drafted the module.

   You are done when all three have signed.

5. Turn the signed form into a proposal. Then apply it, with the proposal folder the first command names.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.propose ../ai-modelling/sample-tank-inspections.new-module.json
   ```

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.apply ../ai-modelling/proposals/NM-2026-003
   ```

   You are done when the apply ends with a line that starts `Done.` and names your module, as the example's does:

   ```text excerpt=HOW-TO-UPDATE.md
   Done. sample-tank-inspections 1.0.0 is a new module (major). The apply changed <count> files, and Git committed them.
   ```

6. Check the release and load the stores, as section 6, "After every change", says.

   You are done when that part is done.

## 6. Check the release and recover

### After every change

Do these three steps after every change of sections 3 to 5, 7, 8 and 9, in this order.

1. Run the full check. Open Git Bash in the release folder: in File Explorer, right-click the folder and choose "Open Git Bash here". It took 21 minutes on a Windows machine with 4 cores.

   ```bash excerpt=HOW-TO-UPDATE.md
   bash scripts/check.sh
   ```

   You are done when its last line reads `all checks passed`. A line that starts `FAIL a store request` comes from a test that fails a write on purpose, and is expected.

2. Load the stores. Go back to PowerShell, in the release folder.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner
   ```

   You are done when its last line reads `every step passed`. If it stops on a line that starts `report: STOPPED`, the workspace differs from the release: clear the report and run again, as in section 2, steps 3 and 4.

3. Check the stores.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.sync_check
   ```

   You are done when every line reads `current`.

### When a run fails

Use these steps only when a run stops on a step.

1. Read the line the run stopped on, and fix what it says. The runbook's "When a step fails" lists each step's failures and fixes.

   You are done when you have done what the line says.

2. Run again from the step that failed, such as `fuseki`:

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --from fuseki
   ```

   You are done when the run's last line reads `every step passed`.

3. If the step `check` fails because of the machine, such as a file that another program holds open, and not because of the release, report it, and leave the step out of the run:

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --skip check
   ```

   You are done when the last line names the step that was left out. A run with a step left out never says `every step passed`.

## 7. Replace what a store holds, or reset every store

**These commands delete data.** Have the written authorization ready before you start. The two parts below are separate: do only the one you are authorized for.

### Replace what Neo4j Enterprise holds

1. Replace it, when the runbook's "Replace what Enterprise holds: one case" applies. The command loads Enterprise again and runs the sync check.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --from enterprise --replace-enterprise
   ```

   You are done when the run's last line reads `every step passed`, and its sync check reads `current` for `enterprise`.

### Empty every store and load it again

1. See what the reset would delete. It deletes nothing.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --reset --dry-run
   ```

   You are done when the person who authorized the reset has read the list.

2. Run the reset. It asks you to type the word `reset`.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.runner --reset
   ```

   You are done when it has emptied each store it lists.

3. Check the stores.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.sync_check
   ```

   You are done when each store that was emptied reads `unmarked`, as the first line does here:

   ```text excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   databricks      unmarked    <why>
   ```

4. Load every store again and check them, as section 6, "After every change", steps 2 and 3, say.

   You are done when the sync check reads `current` on every line.

## 8. Upgrade the tools from a newer release

Your copy is the master of the ontology. A newer release from the release's team brings new tools: the commands, the scripts, the skills and the guides. The upgrade takes them into your copy and keeps every change you applied. It runs the full check on the merged copy, and changes your folder only when that passes. `HOW-TO-UPDATE.md`, "Upgrade the tools from a newer release", says how it decides which files are tools.

1. Save the new zip beside the release folder. The commands below name it `kpi-store-newer.zip`, as the guide's example does: write the name of the zip you received.

   You are done when the zip is beside the release folder.

2. Make sure every change in the release folder is committed: the upgrade refuses a copy with changes that are not committed. The change commands commit their own changes. A file you changed by hand, as in section 9, you commit as section 9 shows.

   You are done when the upgrade's plan, in step 3, does not refuse the copy.

3. See what the upgrade would do. The plan changes nothing.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.upgrade --from ../kpi-store-newer.zip --plan
   ```

   You are done when the zip's SHA-256 in the first line equals the one the release's team sent you, and you have read the plan.

4. Upgrade. It takes about 20 minutes, most of it the full check.

   ```powershell excerpt=HOW-TO-UPDATE.md
   python -m kpi_store.upgrade --from ../kpi-store-newer.zip
   ```

   You are done when it ends with a line that starts `Upgraded to the tools of`. When it stops instead, your folder is as it was: send its message, and the files or the log it names, to the release's team.

5. Run the setup check again, because a newer release may name newer versions of the programs and packages. If it fails, do what its `fix:` lines say.

   ```powershell excerpt=business_architecture/ontology/projection/ontology-stores-runbook.md
   python -m kpi_store.setup_check
   ```

   You are done when its last line reads `15 of 15 checks passed`.

6. Load the stores and check them, as section 6, "After every change", steps 2 and 3, say.

   You are done when the sync check reads `current` on every line.

## 9. Refresh what people use

The change commands of sections 3 to 5 rebuild what they change, including the KPI intake pack's forms and the release's pages, and commit it. After a change, people still need the new forms. When the Architect changes the form's own settings, `kpi-intake/settings.toml`, the pack needs a rebuild and a commit by hand. The steps below show both.

1. When you have changed `kpi-intake/settings.toml`, as `kpi-intake/README.md`, "Change the form", says, rebuild the pack.

   The document test changes the settings with this block. You changed yours in Notepad, so skip it.

   ```python run=release-git
   from pathlib import Path

   path = Path("kpi-intake/settings.toml")
   path.write_text(path.read_text(encoding="utf-8") + "\n# A change by the Architect.\n", encoding="utf-8", newline="\n")
   print("changed", path)
   ```

   ```text expect
   changed kpi-intake/settings.toml
   ```

   ```powershell run=release-git status-only
   python -m kpi_store.intake build
   ```

   You are done when it ends without an error.

2. Commit what you changed by hand, with a message that says what it was.

   ```powershell run=release-git status-only
   git add -A
   git commit -q -m "Change the KPI intake pack's settings"
   ```

   ```powershell run=release-git
   git --no-pager log --oneline -1
   ```

   ```text expect
   <commit> Change the KPI intake pack's settings
   ```

   You are done when the log names your commit.

3. After any change of sections 3 to 5 or 9, give people the new forms. Copy them into the team's shared folder with the `folders` command, as `kpi-intake/README.md`, "The shared folder", shows, with the place of your shared folder in place of its `.`. It replaces the forms and the guide in `the-form`, and changes nothing in the folders that hold people's answers.

   You are done when the `folders` command ends with:

   ```text excerpt=kpi-intake/README.md
   KPI-intake is ready
   ```

4. Check the release and load the stores, as section 6, "After every change", says.

   You are done when that part is done.
