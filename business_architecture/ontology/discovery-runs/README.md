# Discovery runs

This folder holds one record for each discovery report that was cut into the ontology, and the standing decisions. The cut tool, `kpi_store/cut.py`, writes both. Do not edit a record by hand.

A discovery run compares the ontology with the Databricks workspace and writes a report. A person clears the report: each row gets the decision `accept`, `reject` or `environment setting`. The cut tool then turns the cleared report into a correction version of the ontology.

## What a correction version is

A correction version carries a marker in its name: `1.2.1-correction.1`.

- A correction to a plain version takes the next patch number and the marker. A correction to `data-product` 1.2.0 is `1.2.1-correction.1`.
- A correction to a correction keeps the three numbers and counts up. The next one is `1.2.1-correction.2`.
- Every module that requires the corrected module gets a correction version too, because a package names the exact version of each module it requires.
- The next ordinary patch after a correction is `1.2.2`. No plain `1.2.1` is released beside the corrections.

The order is 1.2.0, 1.2.1-correction.1, 1.2.1-correction.2, 1.2.2. One function decides it for every script: `version_key` in `business_architecture/ontology/release/newest.py`.

## Cut a cleared report

Run the tool from the release's top folder. It needs Python 3.11 or later with `rdflib` and `pyshacl`. It needs no Java, no bash and no Git.

```powershell run=release-copy
py -m kpi_store.cut --report kpi_store/tests/fixtures/cut/discovery-report.json --decisions kpi_store/tests/fixtures/cut/cleared-decisions.csv --approver "the ontology owner" --plan
```

```text expect
Discovery run 20261111T120000Z-0a1b2c3d of KPI Store 1.1: 28 rows.
The cut applies (4):
...
  integration 2.5.0 -> 2.5.1-correction.1
```

The example names the made-up report and decisions that ship with the tests, and `--plan` changes nothing. For your report, name its two files and leave `--plan` out. `HOW-TO-UPDATE.md`, "See the cut by itself", runs the whole cut on the same report.

- `--report` names the report's JSON file. To use decisions written in a CSV file, add `--decisions` and that file, or give the CSV file as `--report` when the JSON file of the same name lies beside it.
- `--approver` is optional. Write the role or the initials of the person who cleared the report, such as "the ontology owner". The tool refuses anything else: it takes letters, digits, spaces, dots, hyphens and apostrophes, at most 60 characters, at least one letter, and no number of four digits or more. The same rule holds for the "decided by" of each row in the report. The record is committed, so it must hold no address and no phone number.
- `--plan` shows what the cut would do and changes nothing.

The tool shows each row and what it will change. It then asks two things:

1. For each breaking change, type the text it prints, such as the column's new name.
2. Type `yes` to approve the cut.

A change is breaking when it changes or removes a name that a query or a load may hold: a column whose new name differs by more than case, an object's name, or the removal of a column, an object or a table edge. A case-only spelling and an added measure are not breaking.

The tool works in a temporary copy of the release. Your folder changes only after every step has passed. If a step fails, your folder is as it was. A report that was cut before changes nothing.

In a Git copy the tool commits the change and tags it `data-product-<version>`. The cut ends with its commit and its tag, or it changes nothing. It never pushes. Before it changes a file, the tool checks what Git needs and refuses the cut when one of these is missing:

- Git is installed.
- The copy has no change that is not committed.
- Git has a `user.name` and a `user.email`. If not, the tool prints the two `git config` commands to run.
- The tag does not exist yet.

If the commit is made and Git cannot make the tag, the tool says so and stops. Run the same command again: it makes the tag on the cut's commit.

If the commit itself fails, the tool puts back the files it wrote, from the copies it kept, and takes them out of Git's index. It touches no other file. If it cannot put a file back, it names that file and says what state it is in.

A plain folder, one with no `.git` folder, needs no Git. The tool writes the same files there.

After a cut, run the full check before you load any store. On Windows, run it in Git Bash:

```bash run=slow
bash scripts/check.sh
```

```text expect
...
all checks passed
```

## What each decision does

| Decision | What the cut does |
|---|---|
| `accept` | Applies the row's proposed fix to the data-product module's tables in `data-product/pricing/`: a renamed column, a case-only spelling, a renamed object, a second view that serves a measure, or the removal of a column, an object or a table edge. |
| `accept`, when the fix adds a concept | Nothing. A measure link with its filter, a new object, a new table edge and the table a Databricks table replaces each need a minor version, made with the release steps in `HOW-TO-UPDATE.md`. The tool lists the row as "needs a minor version". |
| `reject` | Changes nothing in the ontology. The row becomes a standing decision. |
| `environment setting` | Changes nothing in the ontology. The tool prints what to write in `kpi_store.toml`. |
| None, on a row that does not block | Nothing. A question for the owner is listed as "waits". |

The tool refuses a report in which a row that blocks the load has no decision.

A report is a file that a person may have edited, so the tool takes no text from it on trust. It refuses an accepted row unless the row's object, its found value and each field of its proposed fix have the form of a name, and the fix names the module its action belongs to. This holds for every accepted row, also one the tool then leaves for a minor version. A column name is letters, digits, underscores and dollar signs. An object name is one to three such parts, which may also hold a hyphen, joined by dots. A column or an object whose name has another form goes through the release steps in `HOW-TO-UPDATE.md`.

## The record

Each cut writes `<run ID>.md` here. Each corrected module's changelog names it, and each package's manifest names it under `approved_by`. The record has these parts:

| Part | What it holds |
|---|---|
| The table at the top | The run ID and time, the SHA-256 of the report file, of the decisions file when one was used, of the settings file and of the release zip, the module versions the report read, when the cut ran, who cleared the report (the `--approver` text) and the approval. |
| Versions written | Each module, the version it had, the version the cut wrote, and why. |
| Rows | Every row of the report: its kind, whether it blocks, the object, the ontology's value, the found value, the decision, who decided, what the cut did, and why, in the tool's own words. |
| Changes | For each applied row: the file, the value before and the value after. |
| Files the cut changed | Every path the cut added, changed or removed. |

The report stays in the volume. From a row's object, ontology value and found value, the record holds names only. A value that does not have the form of a name, such as a Genie filter's title, the time of a table's last write or anything a person typed into one of these fields, appears as "(kept in the report)". The record holds no evidence text, no query result and no filter. It does not hold a row's note: a note is free text and stays in the report. It holds who decided each row, which must be a role or initials.

## Standing decisions

`standing-decisions.json` lists the rows that a cleared report rejected. The next comparison reads it and leaves those rows out, so a person decides each finding once.

```json parse
{
  "format": 1,
  "decisions": [
    {"key": "<SHA-256>", "kind": "object-extra", "object": "idp_sbx.gold_commercial_core.sample_margin_fact",
     "ontology_value": "", "decision": "reject", "run": "<run ID>"}
  ]
}
```

`key` is the SHA-256 of the row's kind, object, ontology value and found value, in lower case. A finding with another found value is a new finding, and the comparison reports it. To see a rejected finding again, delete its entry and commit the change.
