# KPI Store runbook: the first run on the client sandbox

This guide takes you from the release zip to three loaded and checked stores: Databricks, Jena Fuseki on your Windows machine, and Neo4j Enterprise. Follow it from top to bottom, one step at a time. Every command in it is run by the document test, except the ones the section "Not yet run on Windows" lists.

One command does the work: `py -m kpi_store.runner`. You run it three times. The first run compares the ontology with the sandbox and stops on a report. You clear the report. The second run cuts a correction version and loads every store. The third run proves that nothing is left to change.

For every later change, use `HOW-TO-UPDATE.md` in the release's top folder.

## Before you start

### What you need

- A Windows 10 or Windows 11 machine on which you may install programs.
- The release zip, `kpi-store-1.1.zip`.
- The address of the sandbox workspace, as your browser shows it when you open Databricks.
- The ID of a SQL warehouse you may use in that workspace. The sync check reads through it.
- The address of the Neo4j Enterprise server, your user name there and your password.
- The database `businessprocessarchitecturegraph` on that server. The copy never creates a database. If it is missing, ask the server's administrator for it before you start.

### The limits

The run keeps three limits. Code enforces each one.

| Limit | What enforces it |
|---|---|
| The notebook writes only to `idp_sbx.kpi_store` and `idp_sbx.tech_graph`. | `kpi_store/load_databricks.py`, the class `Gate`. Every SQL statement of the notebook passes `Gate.check`, which refuses a write outside the two schemas that `kpi_store.toml` names (`write_schemas` in `kpi_store/settings.py`). A refused statement is never sent. `kpi_store/tests/test_load_databricks.py` tests it. |
| The notebook reads only the catalogs in `kpi_store.toml`. | The same `Gate.check`. It refuses a read outside `read_catalogs`. It also allows three system schemas, which discovery needs: `system.information_schema`, `system.access` and `system.lakeflow`. |
| The Neo4j load writes only to `businessprocessarchitecturegraph`. | `kpi_store/copy_enterprise.py`. `open_target` opens every session on that one name, and the server must confirm the name. It refuses the `system` database, a missing database and an alias. `check_statement` refuses any statement that creates, alters or drops a database, a user or a role. `decide` stops when the database holds a node that is not the KPI Store's. `kpi_store/tests/test_copy_enterprise.py` tests it. |

The second limit names the catalogs of the sandbox's settings: `idp_sbx` and `synapse_dev`.

### What the run writes

| Where | What the run writes there |
|---|---|
| Databricks, schema `idp_sbx.kpi_store` | The schema and the volume `releases`, when they are missing. In the volume: the zip, a copy of `kpi_store.toml`, and one `reports` folder per run. The tables `epm_triples` and `epm_store_markers`. |
| Databricks, schema `idp_sbx.tech_graph` | The schema, when it is missing. The tables `tech_graph_triples` and `tech_graph_markers`. |
| Databricks, the workspace | One notebook, `kpi_store_load`, in the folder that your local settings name. One job run per runner run, named `KPI Store load` and the run's ID. |
| Your Windows machine | The folder `C:\kpi-store-local`: each run's files, the Fuseki dataset and the Neo4j load's working files. |
| The local Neo4j | The database that your local settings name. **The load empties it first.** |
| Neo4j Enterprise | Nodes and relationships in `businessprocessarchitecturegraph`, and one constraint there, `n10s_unique_uri`. |
| The release folder | Nothing, except in the cut. The cut writes the correction version and its record. |

The run writes to no table of yours and to no other schema, catalog or database. It reads no token and stores none. Databricks access outside the notebook goes through the sign-in of the Databricks command line.

## Set up the Windows machine, once

Do this section once per machine. The setup check at its end tells you what is still missing.

### Install the programs

1. Open `https://www.python.org/downloads/windows/` and download the installer of Python 3.12, 64-bit.
2. Start the installer.
3. Tick "Add python.exe to PATH". The check script cannot find Python without it.
4. Click "Install Now".
5. Open `https://git-scm.com/download/win`, download Git for Windows and install it with its default choices. It brings `bash.exe`, which the check script needs.
6. Open `https://adoptium.net/temurin/releases/`, choose version 21 for Windows, and install it with its default choices. Fuseki 6.2.0 and ROBOT run on Java 21.
7. Open Command Prompt and install the Databricks command line. The command is from Databricks' page "Install or update the Databricks CLI" (last updated 2026-09-11).

   ```cmd skip reason="windows-only: installs a program on the reader's machine with the Windows package manager"
   winget install Databricks.DatabricksCLI
   ```

   It downloads and installs the program. The last line says that the install succeeded.

8. Open `https://neo4j.com/download/`, download Neo4j Desktop and install it.
9. Close every terminal window. A new terminal finds the new programs.

### Unpack the release

1. In File Explorer, right-click `kpi-store-1.1.zip` and choose "Extract All".
2. Type `C:\kpi-store-1.1` as the folder and click "Extract".
3. Check that `C:\kpi-store-1.1\README.md` exists. If the files lie one folder deeper, use that folder instead.

This guide calls that folder the release folder. Keep its path short. Do not put it in a folder that a sync program watches.

### Make the local folder and fetch three files

The local folder holds your settings, with a password, and everything the runs write. It must stay outside the release folder. Every command refuses a settings file inside the release folder.

1. In File Explorer, make the folder `C:\kpi-store-local`.
2. Download each file below with your browser and save it in `C:\kpi-store-local` under the name shown.

| Save as | Download from | SHA-256 |
|---|---|---|
| `jena-fuseki-server-6.2.0.jar` | `https://repo1.maven.org/maven2/org/apache/jena/jena-fuseki-server/6.2.0/jena-fuseki-server-6.2.0.jar` | `2c92c598e65ab69d99820052e05f4277ed1d77980a8845f87545ad35b71a76ee` |
| `robot.jar` (ROBOT 1.9.10) | `https://github.com/ontodev/robot/releases/download/v1.9.10/robot.jar` | `16a73c074f3df359a7338a84b4e0788785fe06117f931bb9796e9619ea776105` |
| `neosemantics-2025.06.1.jar` (n10s) | `https://github.com/neo4j-labs/neosemantics/releases/download/2025.06.1/neosemantics-2025.06.1.jar` | `4c461087e08405c7cb472ecfefc043e9e8ed93628ed74988e4fda1f1bac54b3e` |
| `apoc-2025.06.2-core.jar` (APOC) | `https://github.com/neo4j/apoc/releases/download/2025.06.2/apoc-2025.06.2-core.jar` | `4df40cea7444ea193d08f8a679aa998c498196fe149c8c02badb998f1c9580fb` |

You do not compare the checksums by hand. The setup check does it and fails on a file that differs.

### Install the Python packages

1. Open PowerShell.
2. Install the packages at the versions the release was tested with. The list is `PACKAGES` in `kpi_store/setup_check.py`, plus `uv`, which the check script uses.

   ```powershell run=scratch os=windows status-only
   py -m pip install rdflib==7.6.0 pyshacl==0.40.2 pyoxigraph==0.5.13 neo4j==6.4.1 databricks-sdk==0.164.0 sqlglot==30.31.0 pyyaml==6.0.3 uv
   ```

   The last line starts with `Successfully installed` and names the packages.

3. Give the check script a `python3`. Git Bash on Windows often has `python` and no `python3`, and the check script calls `python3`. This command copies `python.exe` to `python3.exe` beside it, unless that file is already there.

   ```powershell run=scratch os=windows status-only
   py -c "import pathlib, shutil, sys; exe = pathlib.Path(sys.executable); new = exe.with_name('python3.exe'); new.exists() or shutil.copyfile(exe, new)"
   ```

   It prints nothing. A file `python3.exe` now lies beside `python.exe`.

4. Make Python read and write text as UTF-8. The Windows test job runs the check script with this setting.

   ```cmd run=scratch os=windows status-only
   setx PYTHONUTF8 1
   ```

   It answers `SUCCESS: Specified value was saved.` The setting reaches new terminal windows only.

### What Windows itself needs

<!-- WINDOWS-FACTS: the lead fills this section from the Windows test job's findings (long paths, encodings, privileges). Keep the heading. -->

This section waits for the results of the Windows test job. Until it is filled, three settings are known from the code:

- Keep the release folder's path short, as "Unpack the release" says. The longest path inside the release has 95 characters.
- Set `PYTHONUTF8`, as step 4 above does.
- You need no administrator rights for any command of this guide. The installers of "Install the programs" may ask for them.

### Set up the local Neo4j

The local Neo4j checks the graph before anything goes to Enterprise. It needs two plugins that Enterprise does not have.

**The load empties the local database every time.** Make a new instance for the KPI Store. Do not use one that holds other work.

1. Open Neo4j Desktop.
2. Create a local instance. Choose version `2025.06.2`, and choose a password. Note the password.
3. On the instance's menu, choose "Open folder", then open the folder `plugins`. Note its path.
4. Copy `neosemantics-2025.06.1.jar` and `apoc-2025.06.2-core.jar` from `C:\kpi-store-local` into that `plugins` folder.
5. On the instance's menu, open `neo4j.conf`.
6. Add this line at the end of the file and save it.

   ```text skip reason="illustration: one line of the Neo4j instance's own settings file, which the setup check then proves by calling both plugins"
   dbms.security.procedures.unrestricted=apoc.*,n10s.*
   ```

7. Start the instance. If it was running, stop it and start it again.

### Write the two settings files

The release has an example of each file. Copy both, then change only the lines the steps name.

1. In File Explorer, copy `C:\kpi-store-1.1\kpi_store\kpi_store.example.toml` to `C:\kpi-store-local\kpi_store.toml`.
2. Open `C:\kpi-store-local\kpi_store.toml` in Notepad.
3. Set `warehouse_id` to the ID of your SQL warehouse. Change nothing else. The file already holds the sandbox's values:

   ```toml excerpt=kpi_store/kpi_store.example.toml
   [databricks]
   write_catalog = "idp_sbx"
   write_schema = "kpi_store"         # epm_triples and epm_store_markers live here
   tech_graph_schema = "tech_graph"
   volume = "releases"                # the volume <write_catalog>.<write_schema>.<volume>
   read_catalogs = ["idp_sbx", "synapse_dev"]
   warehouse_id = ""                  # used only outside the notebook (the sync check); may stay empty

   [names]                            # the ontology's catalog name = this environment's catalog name
   idp_sbx = "idp_sbx"
   synapse_dev = "synapse_dev"

   [skip]
   schemas = ["information_schema", "bronze_replica_*", "kpi_store_poc"]
   tables = ["*__ct", "attrep_*"]
   ```

   Leave the `sha256` line of zeros as it is. The runner writes the zip's real checksum into the copy it uploads.

4. Save the file and close Notepad.
5. In File Explorer, copy `C:\kpi-store-1.1\kpi_store\stores.example.toml` to `C:\kpi-store-local\stores.toml`.
6. Open `C:\kpi-store-local\stores.toml` in Notepad and set these lines. Leave every other line as it is.

   | Table | Line | Set it to |
   |---|---|---|
   | `[neo4j.local]` | `password` | The password you chose in Neo4j Desktop. |
   | `[neo4j.local]` | `plugins_folder` | The path of the `plugins` folder you noted, with `/` in place of each backslash. |
   | `[neo4j.enterprise]` | `uri` | The Enterprise server's address, such as `neo4j://` and the server's name and `:7687`. |
   | `[neo4j.enterprise]` | `username` | Your user name on the Enterprise server. |
   | `[neo4j.enterprise]` | `password` | Your password on the Enterprise server. |

   The `database` line of `[neo4j.enterprise]` already reads `businessprocessarchitecturegraph`. Name the database itself there, never an alias. The copy refuses an alias.

   The notebook is imported into `/Workspace/Shared/kpi_store`. If you may not write there, set `workspace_folder` to a folder of your own, such as `/Workspace/Users/` and your sign-in name and `/kpi_store`.

7. Save the file and close Notepad.
8. Tell every command where the file is. Then close PowerShell and open it again, because the setting reaches new windows only.

   ```cmd skip reason="windows-only: sets a variable of the reader's own account to a file on the reader's machine"
   setx KPI_STORE_LOCAL C:\kpi-store-local\stores.toml
   ```

   It answers `SUCCESS: Specified value was saved.` From then on no command of this guide needs the file's path.

### Sign in to Databricks

The sign-in is OAuth in your browser. No token is made or stored in a file of the release.

1. Run this command with your workspace's address in place of `<your workspace URL>`.

   ```powershell skip reason="needs-browser-sign-in: opens the sign-in page of the reader's workspace"
   databricks auth login --host <your workspace URL> --profile DEFAULT
   ```

2. Sign in on the page that opens in your browser. The terminal then says that the profile `DEFAULT` was saved.

When the sign-in expires later, a run fails at its first Databricks step. Run the same command again and repeat the run.

### Run the setup check

1. In PowerShell, go to the release folder. Every later command in this guide starts there.

   ```powershell skip reason="windows-only: moves to a folder on the reader's machine"
   cd C:\kpi-store-1.1
   ```

2. Run the setup check. It only reads. It changes nothing on your machine or on any server.

   ```powershell run=first-run
   py -m kpi_store.setup_check
   ```

   ```text expect
   ok   python              Python <version>
   ok   packages            rdflib 7.6.0, pyshacl 0.40.2, pyoxigraph 0.5.13, neo4j 6.4.1, databricks-sdk 0.164.0, sqlglot 30.31.0, pyyaml 6.0.3
   ok   local-settings      <your local settings file>, outside the release folder
   ok   kpi-store-settings  <your settings file with its schema and volume and SQL warehouse>
   ok   java                Java <version and where it is>
   ok   fuseki-jar          <the jar> has the pinned SHA-256
   ok   robot-jar           <the jar> has the pinned SHA-256
   ok   bash                <where bash is>
   ok   uv                  <where uv is>
   ok   check-script-tools  inside bash: python3 <version> and uv <version>
   ok   databricks-cli      Databricks CLI <version and where it is>
   ok   databricks-auth     signed in through the profile <your profile>
   ok   neo4j-local         Neo4j 2025.06.2, n10s 2025.06.1, APOC 2025.06.2, database <your local database>
   ok   neo4j-plugins       <your plugins folder> holds both pinned plugin jars
   ok   neo4j-enterprise    database businessprocessarchitecturegraph is there and holds 0 node(s)
   15 of 15 checks passed
   ```

3. Read the last line. If it says `15 of 15 checks passed`, go to "The first run".
4. If a line starts with `FAIL`, do what its `fix:` line says, then run the setup check again. The table below adds what the fix line leaves out.
5. Read the line `neo4j-enterprise`. It must say `holds 0 node(s)` before your first run. If it holds nodes, stop and find out whose they are.

| Check | When it fails |
|---|---|
| `python` | Install Python 3.11 or later and start the commands with `py`. |
| `packages` | Run the `py -m pip install` line that the check prints. It names the packages that differ. |
| `local-settings` | Open a new PowerShell window, so that `KPI_STORE_LOCAL` is set. The file must lie outside the release folder. |
| `kpi-store-settings` | Correct the line that the check names in `C:\kpi-store-local\kpi_store.toml`. An empty `warehouse_id` fails this check. |
| `java` | Install Java 21 and open a new terminal. If Java is still not found, name `java.exe` in `[fuseki]` `java`. |
| `fuseki-jar`, `robot-jar` | Download the file again and save it under the name the check prints. |
| `bash` | Install Git for Windows, or name `bash.exe` in `[tools]` `bash`. |
| `uv` | Run `py -m pip install uv`. |
| `check-script-tools` | Run step 3 of "Install the Python packages" again. Python's folder and its `Scripts` folder must be on `PATH`, which the tick in the installer did. |
| `databricks-cli` | Install the Databricks command line and open a new terminal. If it is still not found, name `databricks.exe` in `[databricks]` `cli`. |
| `databricks-auth` | Sign in again ("Sign in to Databricks"). |
| `neo4j-local` | Start the instance in Neo4j Desktop. Check the password, and that the two jars and the line in `neo4j.conf` are there. Restart the instance. |
| `neo4j-plugins` | Copy the two jars into the `plugins` folder again and restart the instance. |
| `neo4j-enterprise` | Check the address, user name and password. If the database is missing, ask the server's administrator for it. |

## The first run

The first run changes nothing in the ontology and loads nothing. It checks the release, uploads it, and compares it with the sandbox.

1. See what the run will do. This prints each step's commands and runs nothing.

   ```powershell run=first-run
   py -m kpi_store.runner --dry-run
   ```

   ```text expect
   run <run ID> (dry run): cut, check, zip, volume, upload, notebook, report, fuseki, neo4j, enterprise, sync, summary
   cut: no report waits to be cut
   check: would run the check script
   ...
   summary: would print the run's summary
   ```

2. Start the first run. It takes about 20 minutes. The step `check` alone takes about 10 minutes and prints nothing until it ends.

   ```powershell run=first-run exit=3
   py -m kpi_store.runner
   ```

   ```text expect
   run <run ID>: cut, check, zip, volume, upload, notebook, report, fuseki, neo4j, enterprise, sync, summary
   cut: no report waits to be cut
   check: all checks passed
   zip: kpi-store-1.1.zip: <count> files, SHA-256 <checksum>
   volume: <the volume and what the step created>
   upload: kpi-store-1.1.zip and kpi_store.toml are in <the path in the volume>
   notebook: notebook run <number> stopped on a report: 1 row(s) block
   the notebook stopped: 1 row(s) block the load, of <count> in the report
     <row> column-renamed <catalog>.gold_commercial_core.mips_mpr_executive_summary_fact: ChangeValue -> Change_Value_Amount; recommended: accept
   report: STOPPED. Next step: clear the report: edit the decision column of <the file to clear> (each holds the recommended decision), write your role or initials in decided_by on every row you decide, save, then run the same command again
   ```

3. Read the last line. `report: STOPPED` is the result you want here. The run ended with exit code 3, which means it waits for you.

On the sandbox, the row that blocks names the catalog `idp_sbx`.

If the run ends on another line, go to "When a step fails".

## The first report

The run left three files in `C:\kpi-store-local\runs\pending`:

| File | What it is |
|---|---|
| `discovery-report.to-clear.csv` | The rows for you to clear. Each row's `decision` holds the recommended decision. |
| `discovery-report.json` | The report as the notebook wrote it. Do not edit it. |
| `discovery-report.csv` | The same rows with no decision filled in. Do not edit it. |

### The rows to expect on the sandbox

The table lists what the comparison found by hand on the sandbox on 2026-11-10. The row IDs in your report may differ. Read each row by its `kind`, `object`, `ontology_value` and `found_value`.

| Rows | `kind` | What the row says | Decide on the first run | What the cut does |
|---|---|---|---|---|
| 1 | `column-renamed`, the only row that blocks | On the gold table `mips_mpr_executive_summary_fact`, the column `ChangeValue` is now `Change_Value_Amount`. | Accept. Write your role in `decided_by`. | Applies it in the correction. It is a breaking change, so the cut asks you to type the new name. |
| 2 | `column-case` | On the same table, `assessment_amount` is spelled `Assessment_Amount` and `Previous_amount` is spelled `Previous_Amount`. | Accept both. Write your role in `decided_by`. | Applies both in the same correction. |
| 1 | `second-source` | The executive summary view also serves the measure crack spreads. | Accept. Write your role in `decided_by`. | Applies it in the same correction. |
| 8 | `measure-link` | A filter of the Genie space links the executive summary view to a measure: crack spread, gasoline basis, gasoline cash, distillate basis, distillate cash, crude, renewable and NGL. | Leave `decided_by` empty. The Genie space's creator confirms each filter first. | Nothing now. A link with its filter needs a minor version of `data-product`. |
| 1 | `question` | The benchmark prices view has no measure of its own. | Leave it. It waits for the owner or the Genie space's creator. | Nothing. It lists the row as "waits". |
| 8 | `migration-pair` | A silver or gold table is fed by the `synapse_dev` table of the same name, which it replaces. | Leave `decided_by` empty. | Nothing now. The pair needs a minor version of `technical-graph`. |
| Several | `object-extra` | Databricks holds an object that the ontology does not name: the views `mpr_mips_crack_spread_price_fact_metricsfromsilver_vw` and `mpr_mips_crack_spread_price_fact_vw`, and the unused silver and gold tables in the same schemas. | Leave `decided_by` empty. | Nothing. |

The report may also hold `stale-data` rows. Each says that a table had no write for 35 days. They need no decision.

The report also counts what passed. Open `discovery-report.json` in Notepad and find `"passes"` near the top. Expect these three numbers:

```json parse
{"object_names": 33, "table_edges": 40, "metric_view_sources": 3}
```

They mean that all 33 object names of the ontology exist, all 40 table edges are in the lineage, and all 3 metric views read the sources the ontology names.

A row without your role in `decided_by` stays undecided, whatever its `decision` column holds. The next run reports it again. So you lose nothing by leaving a row.

Three decisions exist. `accept` applies the row's proposed fix, when a correction can hold it. `reject` changes nothing and records a standing decision, and the comparison then leaves that finding out for good. `environment setting` changes nothing in the ontology and tells you what to write in `kpi_store.toml`. Use `reject` on an `object-extra` row only when you are sure that the ontology must never name the object.

### When your report differs from the table

Do not clear a row that you do not understand.

| What you see | What to do |
|---|---|
| More than one row blocks, or another row blocks. | Stop. Do not run the command again. Report the rows' `kind`, `object`, `ontology_value` and `found_value` to the person who gave you the release. |
| A row of a kind the table does not list, which does not block. | Leave its `decided_by` empty and go on. Report it afterwards. |
| No `measure-link`, `second-source` or `question` row. | Go on. The notebook could list no Genie space with your sign-in. Report it afterwards. |
| The three numbers under `"passes"` are lower, and no extra row blocks. | Go on only when a `no-lineage` row explains each missing table edge. Otherwise stop and report it. |
| A step of this guide does not work as written. | That is a bug in the guide or in the code. Report the step and what the screen showed. |

### Clear the report

**Do not delete a row, and do not change any column but `decision`, `decided_by` and `note`.** A file with a missing row stops the next run.

1. In File Explorer, open `C:\kpi-store-local\runs\pending`.
2. Open `discovery-report.to-clear.csv` in Excel.
3. Find each row that the table above tells you to accept.
4. Check that the row's `decision` reads `accept`.
5. Type your role or your initials in the row's `decided_by`, such as `the ontology owner`. The record of the cut keeps this text, so it takes a role or initials only: letters, digits, spaces, dots, hyphens and apostrophes. It refuses an e-mail address and a number of four digits or more.
6. Leave `decided_by` empty on every other row.
7. Choose "File", "Save As", and the file type "CSV UTF-8 (Comma delimited)". Keep the file's name and folder.
8. Close Excel. The runner cannot read the file while Excel holds it open.

The document test cannot open Excel. It does steps 2 to 8 with the block below, which writes the role on the rows of the three kinds that the table accepts. An agent that follows this guide may run it too. If you cleared the file by hand, skip it.

```python run=first-run
import csv
import os
import tomllib
from pathlib import Path

settings = Path(os.environ["KPI_STORE_LOCAL"])
with settings.open("rb") as f:
    run_folder = Path(tomllib.load(f)["release"]["run_folder"])
if not run_folder.is_absolute():
    run_folder = settings.parent / run_folder
path = run_folder / "pending" / "discovery-report.to-clear.csv"
with path.open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
for row in rows:
    if row["kind"] in ("column-renamed", "column-case", "second-source") and row["decision"] == "accept":
        row["decided_by"] = "the ontology owner"
with path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
print("decided:", ", ".join(row["kind"] for row in rows if row["decided_by"]))
```

```text expect
decided: <the kind of each row that now has your role>
```

## The second run: the cut and the loads

The second run is the same command. It finds the cleared report and hands it to the cut tool. The cut tool shows its plan and asks you two things. After the cut, the run goes on by itself through every load.

**The cut changes the release folder.** It writes `data-product` `1.2.1-correction.1`, and a correction version of each module that requires it: `logical-model`, `technical-graph`, `value-stream` and `integration`. It works in a temporary copy first. Your folder changes only after every step of the cut has passed.

1. Run the same command again. It takes about 40 minutes.

   ```powershell run=first-run types="Change_Value_Amount,yes"
   py -m kpi_store.runner
   ```

2. Read the plan that the cut tool prints. Check that "The cut applies" lists only the rows you accepted.
3. At the prompt `Type Change_Value_Amount to confirm:`, type `Change_Value_Amount` and press Enter. The prompt names the row and the change before it.
4. At the prompt `Type yes to cut these versions:`, type `yes` and press Enter.
5. Wait for the last line. Expect `every step passed`.

   ```text expect
   ...
   The cut applies (<count>):
   ...
   Versions the cut writes:
     data-product 1.2.0 -> 1.2.1-correction.1
     logical-model 1.0.0 -> 1.0.1-correction.1
     technical-graph 1.1.0 -> 1.1.1-correction.1
     value-stream 1.2.0 -> 1.2.1-correction.1
     integration 2.5.0 -> 2.5.1-correction.1
   ...
   cut: cut the cleared report: <count> row(s) decided, <count> left undecided
   check: all checks passed
   zip: kpi-store-1.1.zip: <count> files, SHA-256 <checksum>
   volume: <the volume> is there
   upload: kpi-store-1.1.zip and kpi_store.toml are in <the path in the volume>
   notebook: notebook run <number> loaded: <count> triples in <catalog>.<schema>.epm_triples, hash <hash>
   report: no row blocks; Databricks marker of <time>, <count> rows; technical graph loaded in Databricks, its file fetched
   fuseki: loaded, <count> graphs, <count> triples, RDFC-1.0 hash <hash> equal in the store and the release files (<which server and where it keeps the data>); technical graph loaded, <count> triples
   neo4j: loaded, <count> nodes, <count> relationships, 0 SHACL violations over <count> constraints, round trip lost 0 and added 0, graph hash <hash>; technical graph loaded, <count> nodes
   enterprise: copied, <count> nodes, <count> relationships, graph hash <hash> equal to the local graph's; technical graph loaded, <count> nodes
   ...
   sync: all <count> lines read current
   summary of run <run ID>:
   ...
   summary: the run's files are in <the folder of the run>
   every step passed
   ```

If you type anything else at a prompt, the cut changes nothing and the run stops at `cut: FAILED`. The report stays in `pending`. Run the same command again.

If the run stops after the cut, do not clear the report again. The cut is done. Go to "When a step fails" and go on from the step that failed.

### What each line tells you

| Line | What it proves |
|---|---|
| `cut` | The cut wrote the correction versions and the record `business_architecture\ontology\discovery-runs\` and the run's ID and `.md`. |
| `check` | The release folder, with the correction, passes every check of the release. |
| `zip`, `upload` | The zip of the corrected release and the settings with its checksum are in the volume. |
| `notebook`, with `loaded` | No row blocks any more. The notebook loaded `epm_triples`, read it back, and found the same RDFC-1.0 hash as the release files. Then it wrote the marker row. |
| `report` | The runner fetched the technical graph's file, which the notebook built from the workspace's real objects. |
| `fuseki` | Fuseki holds the release. Its hash equals the release files' hash. |
| `neo4j` | The local Neo4j holds the release, and every check passed there: 0 SHACL violations, and a round trip that lost 0 triples and added 0. |
| `enterprise` | `businessprocessarchitecturegraph` holds a copy whose graph hash equals the local graph's. |
| `sync` | Every store reads `current`. |

`loaded` in the `notebook` line is the word to look for. `current` and `marked` also mean that Databricks holds this release. `blocked` means that a row still blocks.

### Replace what Enterprise holds: one case

The copy stops when `businessprocessarchitecturegraph` already holds KPI Store nodes of another release. It then says how many, and changes nothing. This happens after any later change to the ontology, and after a copy that was cut off halfway.

**The replace deletes every KPI Store node in that database before it copies.** It deletes no other node. When the database holds a node that is not the KPI Store's, the copy stops whatever you decided.

If the `enterprise` step stops for that reason, run the step again with the replace allowed:

```powershell skip reason="needs-client-server: replaces the KPI Store's nodes in the client's Enterprise database"
py -m kpi_store.runner --from enterprise --replace-enterprise
```

Do not add `--replace-enterprise` to a first run. An empty database needs no replace, and without the option the copy cannot delete anything.

## The sync check

The sync check reads the four stores and writes nothing. The runner ran it as its `sync` step. Run it alone whenever you want to know whether a store is behind.

```powershell run=first-run
py -m kpi_store.sync_check
```

```text expect
databricks      current     <why>
jena            current     <why>
neo4j           current     <why>
enterprise      current     <why>
lm:neo4j        current     <why>
lm:enterprise   current     <why>
tech:databricks current     <why>
tech:jena       current     <why>
tech:neo4j      current     <why>
tech:enterprise current     <why>
```

Each line names a store, then its status, then the reason.

| Line | What it compares |
|---|---|
| `databricks` | The marker row and the rows per graph of `epm_triples` with the release folder. |
| `jena` | Each named graph's triple count in Fuseki with the release folder. |
| `neo4j`, `enterprise` | The database's marker, its counts and its graph hash with the release folder. |
| `lm:neo4j`, `lm:enterprise` | The logical models in that database with the release's logical-model package. |
| `tech:` and a store | The technical graph in that store with the file the runner last fetched. |

| Status | Meaning | What to do |
|---|---|---|
| `current` | The store holds this release. | Nothing. |
| `behind` | The store holds another release. | Run the runner again. |
| `changed` | The store's content changed after its load. | Run the runner again. Find out what wrote to the store. |
| `unmarked` | The store holds data and no marker. | Run the runner again. |
| `empty` | The store holds nothing. Fuseki reads `empty` when its data folder was deleted. | Run the runner again. |
| `unreachable` | The store did not answer, or a setting is missing. The reason says which. | Start the store, or correct the setting. |
| `not checked` | No technical graph file was fetched yet. | Run `py -m kpi_store.runner --from notebook`. |

The command ends with exit code 0 only when every line reads `current`.

## Run it again: nothing changes

A second run on the same release must change nothing. It proves that the loads are repeatable.

1. Run the same command a third time. It takes about 20 minutes.

   ```powershell run=first-run
   py -m kpi_store.runner
   ```

   ```text expect
   run <run ID>: cut, check, zip, volume, upload, notebook, report, fuseki, neo4j, enterprise, sync, summary
   cut: no report waits to be cut
   check: all checks passed
   zip: kpi-store-1.1.zip: <count> files, SHA-256 <checksum>
   volume: <the volume> is there
   upload: kpi-store-1.1.zip and kpi_store.toml are in <the path in the volume>
   notebook: notebook run <number> current: <count> triples in <catalog>.<schema>.epm_triples, hash <hash>
   report: no row blocks; Databricks marker of <time>, <count> rows; technical graph <its status> in Databricks, its file fetched
   fuseki: current, <count> graphs, <count> triples, RDFC-1.0 hash <hash> equal in the store and the release files (<which server and where it keeps the data>); technical graph <its status>, <count> triples
   neo4j: current, <count> nodes, <count> relationships, 0 SHACL violations over <count> constraints, round trip lost 0 and added 0, graph hash <hash>; technical graph <its status>, <count> nodes
   enterprise: current, <count> nodes, <count> relationships, graph hash <hash> equal to the local graph's; technical graph <its status>, <count> nodes
   ...
   sync: all <count> lines read current
   summary of run <run ID>:
   ...
   every step passed
   ```

2. Check that the lines `notebook`, `fuseki`, `neo4j` and `enterprise` each say `current` right after the step's name. `current` means the step found this release in the store and wrote nothing.

The end of each line names the technical graph, and that part may say `loaded`. The notebook builds the technical graph again from the workspace on every run. When the workspace's objects, lineage or jobs changed since the last run, the graph differs and each store loads it again. The runs of this guide are themselves jobs in the workspace, so this happened in the test.

The loads are done. Keep `C:\kpi-store-local` and the release folder. The release folder now holds the correction, and every later change starts from it.

## What the runner does, step by step

The runner is `kpi_store/runner.py`. It runs twelve steps in order and stops at the first one that fails. Each step prints one line and writes its result to the run's folder, under `steps`. You can run the chain by hand, one step at a time, with `--only` and the step's name. A step run that way continues the newest run. Its last line names the steps it left out. Only a run of the whole chain says `every step passed`.

The commands below ran after the third run, so each finds its work done.

### `cut`

It calls the cut tool, `kpi_store/cut.py`, when a cleared report waits in `runs\pending`. The cut tool reads the report and your decisions, shows its plan, and asks you to approve. It then changes the tables of the `data-product` module, rebuilds the module, and writes the correction version of it and of each module that requires it. It works in a temporary copy and changes the release folder only when every step has passed.

It reads `runs\pending\discovery-report.json` and `discovery-report.to-clear.csv`. It writes new packages under `business_architecture\ontology\releases`, and the record of the cut under `business_architecture\ontology\discovery-runs`. With no report waiting, it does nothing.

```powershell run=first-run
py -m kpi_store.runner --only cut
```

```text expect
run <run ID>: cut
cut: no report waits to be cut
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `check`

It runs `scripts/check.sh` with bash. The script rebuilds every package and compares it with the one on disk. It runs the competency questions and every test. It checks that the generated pages equal their sources and that every code block of the documents works.

It reads the release folder. It writes only `check.log` in the run's folder. It takes about 10 minutes.

```powershell run=first-run
py -m kpi_store.runner --only check
```

```text expect
run <run ID>: check
check: all checks passed
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `zip`

It packs the release folder into one zip, in `runner.py` itself. The same files always give the same zip: the entries are sorted, each has one fixed date, and text files get the same line ends. It then copies your `kpi_store.toml` and writes the zip's SHA-256 into the copy.

It reads the release folder and `C:\kpi-store-local\kpi_store.toml`. It writes the zip and the settings copy to the run's folder, under `upload`. It stops when a settings file in the release folder holds a password.

```powershell run=first-run
py -m kpi_store.runner --only zip
```

```text expect
run <run ID>: zip
zip: kpi-store-1.1.zip: <count> files, SHA-256 <checksum>
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `volume`

It asks Databricks, through the Databricks command line, whether the schema and the volume exist. It creates each one that is missing.

It reads `write_catalog`, `write_schema` and `volume` from `kpi_store.toml`. It writes nothing when both exist.

```powershell run=first-run
py -m kpi_store.runner --only volume
```

```text expect
run <run ID>: volume
volume: <the volume> is there
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `upload`

It copies the zip, then the settings copy, into the volume with the Databricks command line. The zip goes first, so the settings never name a zip that is not there.

It reads the two files of the `zip` step. It writes them to the volume and replaces the ones of the run before.

```powershell run=first-run
py -m kpi_store.runner --only upload
```

```text expect
run <run ID>: upload
upload: kpi-store-1.1.zip and kpi_store.toml are in <the path in the volume>
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `notebook`

It imports `kpi_store/notebook/kpi_store_load.py` into the workspace folder as the notebook `kpi_store_load`. It submits the notebook as a one-time job run on serverless compute, waits for it, and reads its result.

The notebook has five cells.

| Cell | What it does |
|---|---|
| 1 | Text. It says what the notebook does and lists its three parameters: `settings_path`, `mode` and `stale_after_days`. |
| 2 | Installs five Python packages at pinned versions for this run: `databricks-sdk`, `pyoxigraph`, `rdflib`, `sqlglot` and `pyyaml`. |
| 3 | Restarts Python, so that the run uses the packages of cell 2. |
| 4 | Defines the work. `bootstrap` reads `kpi_store.toml` from the volume, checks the zip's SHA-256 against it, unpacks the zip and validates the settings. `main` then runs the release's own code from the zip. |
| 5 | Runs `main` and ends the run with a summary in JSON, which the runner reads. |

`main` calls `kpi_store/load_databricks.py`. That code reads the workspace (`kpi_store/discovery.py`): the objects and columns, the metric view definitions, the lineage, the jobs that build the tables and the Genie spaces. It compares them with the ontology (`kpi_store/compare.py`) and writes the report. If a row blocks, it stops there. Otherwise it writes the release's triples to a staging table, reads them back, and compares their hash with the release files' hash. Only an equal staging table replaces `epm_triples`. Then it writes the marker row. Last, it builds the technical graph from what it read (`kpi_store/tech_graph.py`) and loads it the same way.

The notebook reads the catalogs that `kpi_store.toml` names and three system schemas. It writes to the two schemas of the limits, and to the volume: the report files and `tech-graph.nq`, in one `reports` folder per run.

```powershell run=first-run
py -m kpi_store.runner --only notebook
```

```text expect
run <run ID>: notebook
notebook: notebook run <number> current: <count> triples in <catalog>.<schema>.epm_triples, hash <hash>
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `report`

When the notebook stopped on a report, this step fetches the report from the volume into `runs\pending`. It prints the rows that block, writes the copy for you to clear, and stops the run. When the notebook loaded, it fetches `tech-graph.nq` into `runs\tech-graph` instead, and checks that the file is the one the notebook loaded.

```powershell run=first-run
py -m kpi_store.runner --only report
```

```text expect
run <run ID>: report
report: no row blocks; <the marker and the technical graph>
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `fuseki`

It calls `kpi_store/load_fuseki.py`. That code checks Java and the jar's checksum. It uses the Fuseki that answers at the address of your local settings, or starts one from the jar. It builds the dataset that a current store holds and compares its RDFC-1.0 hash with the store's. When the hashes are equal it writes nothing. Otherwise it drops the graphs of earlier versions, replaces every graph, reads all of it back and compares again. Then it loads the technical graph.

It reads the release folder and `runs\tech-graph\tech-graph.nq`. It writes to the Fuseki dataset, which is kept in `C:\kpi-store-local\fuseki-db`.

```powershell run=first-run
py -m kpi_store.runner --only fuseki
```

```text expect
run <run ID>: fuseki
fuseki: current, <what Fuseki holds>
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `neo4j`

It calls `kpi_store/load_neo4j.py`, which runs the `ontology-to-lpg` skill's steps. It checks the projection's rules, validates the release with SHACL, and runs the reasoner with ROBOT. **It empties the local database.** It sends the triples in the request, validates the graph with SHACL in the database, and proves each compiled constraint with a failing case. It exports the graph again and compares it with what it loaded. It loads twice and compares the two graph hashes. Last, it loads the logical models and the technical graph, and writes the marker.

It reads the release folder and `robot.jar`. It writes to the local database, and its working files and report to `C:\kpi-store-local\lpg-out`. When the database already holds this release, it writes nothing.

```powershell run=first-run
py -m kpi_store.runner --only neo4j
```

```text expect
run <run ID>: neo4j
neo4j: current, <what the local Neo4j holds>
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `enterprise`

It calls `kpi_store/copy_enterprise.py`. That code checks that the local graph is the one the load verified. It reads the local graph and writes it to `businessprocessarchitecturegraph` with plain Cypher, because the Enterprise server has no plugin. It then compares the copy's graph hash with the local graph's, checks the counts and each release tag, and writes the marker last.

It reads the local database and the load's report. It writes only to the one Enterprise database. When that database already holds this release, it writes nothing.

```powershell run=first-run
py -m kpi_store.runner --only enterprise
```

```text expect
run <run ID>: enterprise
enterprise: current, <what Enterprise holds>
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `sync`

It calls `kpi_store/sync_check.py`, which "The sync check" above describes. It reads the four stores and writes nothing to them.

```powershell run=first-run
py -m kpi_store.runner --only sync
```

```text expect
run <run ID>: sync
...
sync: all <count> lines read current
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

### `summary`

It prints each step's result in this run, and writes `summary.json` in the run's folder.

```powershell run=first-run
py -m kpi_store.runner --only summary
```

```text expect
run <run ID>: summary
summary of run <run ID>:
...
summary: the run's files are in <the folder of the run>
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

## When a step fails

Each run ends with one of four exit codes. The last line of the run says which case you are in.

| Exit code | Last line | Meaning | What to do |
|---|---|---|---|
| 0 | `every step passed`, or `the steps that ran passed` and the steps left out | Every step that ran passed. | Nothing. |
| 1 | The step's name and `FAILED`, with the reason | A step failed. No later step ran. | Fix what the line names, then go on from that step. |
| 2 | `runner:` and the reason | A settings file is wrong or missing. Nothing ran. | Correct the file the line names. Run the setup check. |
| 3 | The step's name and `STOPPED. Next step:` | The run waits for you. | Do what the line says, then run the same command again. |

To go on from the step that failed, name it after `--from`. The run then continues the newest run and repeats nothing before that step. Its last line names the steps before it as left out. For example, when the Fuseki load failed:

```powershell run=first-run
py -m kpi_store.runner --from fuseki
```

```text expect
run <run ID>: fuseki, neo4j, enterprise, sync, summary
fuseki: current, <what Fuseki holds>
neo4j: current, <what the local Neo4j holds>
enterprise: current, <what Enterprise holds>
...
sync: all <count> lines read current
summary of run <run ID>:
...
the steps that ran passed; left out: <the other steps> (not run, so not checked)
```

The steps, in order, are `cut`, `check`, `zip`, `volume`, `upload`, `notebook`, `report`, `fuseki`, `neo4j`, `enterprise`, `sync` and `summary`. Each step's result is a file in `C:\kpi-store-local\runs`, in the run's folder, under `steps`.

| Step that failed | Likely cause | What to do |
|---|---|---|
| `cut` | You typed another answer, or a row's `decided_by` is not a role. | Correct the file if the line says so. Run the same command again. |
| `check` | A check of the release failed. The line names `check.log` in the run's folder. | Read the end of `check.log`. See "Not yet run on Windows" for the one case in which you may leave the step out. |
| `zip` | A file in the release folder sets a password. | Move that file out of the release folder. Run `py -m kpi_store.runner --from zip`. |
| `volume`, `upload` | The sign-in expired, or you may not create the schema. | Sign in again. If the line prints two SQL statements, run them in a Databricks SQL editor. Then run `py -m kpi_store.runner --from volume`. |
| `notebook` | The notebook run failed, or it still runs after 60 minutes. | Read the reason in the line. Run `py -m kpi_store.runner --from notebook`. A run that still runs is waited for again, not started twice. |
| `fuseki` | Java or the jar is missing, or the port is in use. | Run the setup check. Then run `py -m kpi_store.runner --from fuseki`. |
| `neo4j` | The local instance is stopped, or a plugin is missing. | Start the instance. Run the setup check. Then run `py -m kpi_store.runner --from neo4j`. |
| `enterprise` | The server did not answer, or the database holds nodes. | Read the line. For KPI Store nodes of another release, see "Replace what Enterprise holds". For any other node, stop and ask whose it is. |
| `sync` | A store is not current. The lines above name it. | Run the runner from the step that loads that store. |

A store load never runs after a notebook run that did not load. The run then stops with exit code 3 and says why.

To run one store's load by itself, use `--only` and the step's name, as "What the runner does, step by step" shows. The runner hands each load the technical graph's file. A load module started alone, such as `py -m kpi_store.load_fuseki`, does not know that file. The Fuseki load then stops, because it finds the technical graph's named graph and cannot tell whose it is.

## Record the load's report in the release folder

The release folder holds a summary of the last Neo4j load, `business_architecture\ontology\projection\projection-report.json`. After a cut it describes the release before the cut. The check script then prints a note that the report describes an earlier build. The note does not fail the check. This step replaces the summary with the one of your load.

1. Go to the projection's folder.
2. Take the load's result into the release folder. Write the folder that `[projection]` `out` names in your local settings in place of `<your Neo4j load folder>`.

   ```powershell run=first-run
   cd business_architecture/ontology/projection
   py pipeline.py record --run <your Neo4j load folder>
   cd ../../..
   ```

   ```text expect
   ...
   recorded: <count> nodes, <count> relationships, <count> triples and 2 inferred
   ```


3. Run the sync check again. Every line must still read `current`, because the record changes no package.

   ```powershell run=first-run status-only
   py -m kpi_store.sync_check
   ```

The command refuses a load that read other files than this release folder's, and a load whose report did not pass.

## How to undo

Each store is a copy of the release folder. You can empty a store and load it again at any time. This section returns each store to its state before your first run.

### The release folder

The cut is the only step that changed the release folder.

1. Rename `C:\kpi-store-1.1`, for example to `C:\kpi-store-1.1-with-correction`.
2. Unpack `kpi-store-1.1.zip` again, as in "Unpack the release".

The stores then read `behind` until you load them again from that folder.

### Databricks

Before the first run, the two schemas held no KPI Store table.

**These statements delete the KPI Store's four tables.** They touch no other table.

1. Open a SQL editor in the Databricks workspace.
2. Run these statements.

   ```sql skip reason="destructive: drops the four tables the run wrote in the client's workspace"
   DROP TABLE IF EXISTS idp_sbx.kpi_store.epm_triples;
   DROP TABLE IF EXISTS idp_sbx.kpi_store.epm_store_markers;
   DROP TABLE IF EXISTS idp_sbx.tech_graph.tech_graph_triples;
   DROP TABLE IF EXISTS idp_sbx.tech_graph.tech_graph_markers;
   ```

3. To remove the uploaded zip, the settings copy and the reports too, drop the volume. **This deletes every report the runs wrote.**

   ```sql skip reason="destructive: drops the volume the run made in the client's workspace"
   DROP VOLUME IF EXISTS idp_sbx.kpi_store.releases;
   ```

4. To remove the two schemas, drop them without `CASCADE`. Databricks then refuses a schema that still holds anything, so nothing of anyone else's can be lost.

   ```sql skip reason="destructive: drops the two schemas the run made in the client's workspace"
   DROP SCHEMA IF EXISTS idp_sbx.kpi_store;
   DROP SCHEMA IF EXISTS idp_sbx.tech_graph;
   ```

5. In the workspace browser, delete the notebook `kpi_store_load` from the folder that your local settings name.

### Fuseki

1. Stop the Fuseki that the load started. The command stops only that process.

   ```powershell run=first-run
   py -m kpi_store.load_fuseki --stop
   ```

   ```text expect
   fuseki: stopped process <number>
   ```

2. In File Explorer, delete the folder `C:\kpi-store-local\fuseki-db`. The dataset is gone with it.

### The local Neo4j

The load emptied the local database before it loaded. What that database held before cannot come back. This is why the setup asks for a new instance.

1. To remove the KPI Store's copy, delete the instance in Neo4j Desktop.

### Neo4j Enterprise

Before the first run, `businessprocessarchitecturegraph` held no node. The setup check's `neo4j-enterprise` line showed that.

**The first statement deletes every node in the database you are connected to.** Run it only in `businessprocessarchitecturegraph`, and only if that database held 0 nodes before your first run.

1. Open Neo4j Browser or the Query tool on the Enterprise server.
2. Choose the database `businessprocessarchitecturegraph`.
3. Check which database you are in. The answer must be `businessprocessarchitecturegraph`.

   ```cypher skip reason="needs-client-server: asks the client's Enterprise server which database the session is in"
   CALL db.info() YIELD name RETURN name
   ```

4. Delete the nodes, then the one constraint the copy made.

   ```cypher skip reason="destructive: deletes every node of the database the reader is connected to"
   MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS;
   DROP CONSTRAINT n10s_unique_uri IF EXISTS;
   ```

### The runs' files

1. Delete the folder `C:\kpi-store-local\runs` to remove every run's files and reports from your machine.

## Where you can run it from

### A laptop

This is the design of this release. One person runs the runner on a Windows machine that reaches Databricks, the local stores and the Enterprise server.

| Machine | State |
|---|---|
| Windows 10 or 11 | The design. No run has happened on Windows yet. "Not yet run on Windows" lists what that leaves open. |
| macOS | Every run of this guide's chain so far happened here. Write `python3` where this guide writes `py`. Git Bash, `setx` and the copy of `python3.exe` are not needed. |

### A pipeline

This is not part of this release's tested path. The paragraphs below say what the code does today.

A run that finds no report to cut asks nothing. The document test runs the third run of this guide with no keyboard attached, and it passes. So a scheduler can start the same command, `py -m kpi_store.runner`, and read its exit code.

Two things need a person today.

| What | Why a pipeline cannot do it |
|---|---|
| Clearing the report | It is a judgement. A run that finds a blocking row ends with exit code 3 and waits. |
| The cut's two answers | The cut tool reads them from the keyboard. With no keyboard it changes nothing and the run ends with exit code 1. |

The sign-in is the third limit. Today it is `databricks auth login`, which opens a browser, and its session expires. A pipeline has no browser. This release makes and stores no token, so it has no other way in.

A service principal changes that. Databricks' page "Authorize service principal access with OAuth M2M" (last updated 2026-10-30, `https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m`) describes the sign-in: OAuth for machines, with a client ID and a client secret. The runner passes `--profile` and the profile's name to every Databricks command. The sync check opens the Databricks SDK with the same profile. So the pipeline needs a profile in the file `.databrickscfg` in its home folder, with the three fields that the page names:

```ini skip reason="illustration: the shape of a profile for a service principal, whose secret comes from the pipeline's secret store"
[kpi-store-pipeline]
host          = <your workspace URL>
client_id     = <the service principal's client ID>
client_secret = <the service principal's secret>
```

The pipeline writes that file from its secret store when a job starts, and deletes it when the job ends. `[databricks]` `profile` in the local settings then names `kpi-store-pipeline`. No run of this release has used such a profile.

### Inside Databricks

Part of the chain already runs there. The `notebook` step is a serverless job run in the workspace. It covers the comparison, the report, the load of `epm_triples` and the technical graph's tables.

| Part | Inside Databricks today |
|---|---|
| The comparison, the report and the Databricks load | Yes. The notebook does them. |
| A schedule | Not built. A Databricks job could run the notebook `kpi_store_load` on a schedule with the parameter `mode` set to `check`, which writes the report and loads nothing. This release ships no job definition. |
| The zip and the settings in the volume | No. The runner uploads them from your machine. |
| The cut | No. It changes the release folder and asks a person. |
| The Fuseki load and the two Neo4j loads | No. They need a network path from Databricks to those servers, and this release assumes none. |

## What changes later

Nothing in this section is part of this release's tested path.

### With a Databricks service principal

| Topic | Today | With a service principal |
|---|---|---|
| Who runs the job | You. The notebook runs with your rights. | The service principal. It needs the rights the run uses: to create the two schemas and the volume in the write catalog, to read the read catalogs and the three system schemas, to read the Genie spaces, and to write the workspace folder. |
| The sign-in | `databricks auth login` in a browser. | A profile with a client ID and a secret, as "A pipeline" shows. Nobody signs in. |
| The schedule | You start each run. | A scheduler starts the runner, or a Databricks job runs the notebook in `check` mode. |
| What stays manual | Clearing the report and the cut's two answers. | The same. |

### With n10s and APOC on Neo4j Enterprise

Today the load runs on a local Neo4j that has the two plugins, and a copy in plain Cypher takes the checked graph to Enterprise. That is what the code supports.

With the plugins on Enterprise, the load and the SHACL checks could run there directly. That is not built. Pointing `[neo4j.local]` at the Enterprise database is not the way: the load empties the database it is pointed at, every node of it, and the limit of this release is that it deletes KPI Store nodes only. A direct load needs new code that removes only the KPI Store's nodes before it loads, as the copy does today. Until then, keep the local Neo4j and the copy.

## Not yet run on Windows

The whole chain of this guide ran on macOS against a rehearsal Databricks workspace in the sandbox's shapes, a local Fuseki 6.2.0 and a local Neo4j 2025.06.2 Enterprise with n10s 2025.06.1 and APOC 2025.06.2. It never ran on Windows, and it never ran on the client's sandbox or the client's Enterprise server. Each point below is written from the code and from the vendor's documentation.

| What | Why it is not proven | If it fails |
|---|---|---|
| Every step of "Install the programs" and "Unpack the release" | No Windows machine ran them. | Report the step. |
| The three commands of "Install the Python packages" | They are marked for Windows, and no Windows test has run yet. | Report the command and its output. |
| The steps of "Set up the local Neo4j" | They follow Neo4j Desktop's documentation ("Instance management"). Menu names may differ in your version. The goal of each step is in its text. | Reach the same goal by the menu your version has. The setup check proves the result. |
| `setx KPI_STORE_LOCAL` | It changes your account's settings, so no test runs it. | Add `--stores C:\kpi-store-local\stores.toml` to every command of this guide instead. |
| The step `check` of the runner, which runs `scripts/check.sh` in Git Bash | The check script has passed on macOS and Linux only. Some of its tests may assume file modes or links that Windows lacks. | See below. |
| Clearing the report in Excel | The test edits the file with Python. The runner reads the CSV as UTF-8, with or without a byte-order mark, and reads only the columns `id`, `decision`, `decided_by` and `note`. | Edit the same three cells in Notepad instead. They are the last three values of each line. |
| Starting and stopping Fuseki from the runner | The start uses `java.exe` and the stop reads the process list with PowerShell. Both ran on macOS only. | Run the setup check. Report the line. |
| The SQL and Cypher of "How to undo" | They delete, so no test runs them against a client server. The Cypher ran once on the local test server. | Do not improvise. Report it. |
| The rows of "The rows to expect on the sandbox" | They come from a comparison by hand. The rehearsal workspace gave the one blocking row and the two case-only rows. It has no Genie space, so no test produced the Genie rows. | Follow "When your report differs from the table". |

If the step `check` fails on Windows, read the end of `check.log`. If the failing test is about the release's content, stop and report it. If it is about Windows itself, such as a file mode or a link, report it and leave the step out of the run:

```powershell skip reason="windows-only: the fallback for a check script that fails on Windows for a reason of Windows itself"
py -m kpi_store.runner --skip check
```

A run with a step left out never says `every step passed`. Its last line names the step that was left out. On the first run the release folder is the one that was checked before it was zipped. After the cut, the cut tool has already verified each package it wrote against a fresh build and has run the competency questions.
