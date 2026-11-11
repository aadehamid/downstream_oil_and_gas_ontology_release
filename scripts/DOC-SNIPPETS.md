# Code blocks in the documents

Every code block in a Markdown document of this release is tested. `scripts/doc_snippets.py` reads each block's
tag and runs the block, compares it, parses it, or counts it as skipped for a stated reason. A block with no tag
fails `scripts/check.sh`. This page says how to write the tag.

The examples on this page are tested the same way. Each example is a small document inside a `markdown nested`
block, and the check tests the blocks in it.

## The tag

Write the tag on the opening fence, after the language: the language, a space, the tag. The HTML pages and the
Markdown viewers show the block as before, without the tag.

| Tag | What the check does with the block |
|---|---|
| `run=<context>` | Runs it in the context's folder. It must end with exit status 0. |
| `expect` | Compares it with the output of the `run` block just before it. |
| `skip reason="<reason>: <detail>"` | Does not run it. Counts it under the reason. |
| `file=<path>` | Compares it with the whole file at that path. |
| `excerpt=<path>` | Checks that its lines are in that file, in this order and next to each other. |
| `parse` | Parses it: `json`, `toml`, `yaml`, `turtle`, `sparql`, `sql` or `cypher`. |
| `nested` | Reads it as a small document and tests the blocks in it. The language is `markdown`. |

Use three backticks for a fence. Do not put a block inside a block quote: the check cannot test it there.

## A command: `run`

A `run` block names the context it runs in. The languages that run are `bash`, `sh`, `python`, `powershell` and
`cmd`. Show the output in an `expect` block right after it.

````markdown nested
```python run=scratch
print("loaded", 3 * 4, "graphs")
```

```text expect
loaded 12 graphs
```
````

Blocks of one document that name the same context run in the order they appear, in one folder. A later block
finds the files an earlier block made. This is how the steps of a guide build on each other.

````markdown nested
```bash run=scratch
mkdir reports
echo "blocked: 1 row" > reports/first.txt
```

```bash run=scratch
cat reports/first.txt
```

```text expect
blocked: 1 row
```
````

Three rules follow from the fact that the reader types the blocks into one terminal:

- A bash block starts in the folder that the block before it left. The first block starts in the context's top
  folder.
- A variable or a function lasts beyond its block only when the block says `define`. The check runs a `define`
  block, then puts its text in front of every later block of the same language in that context. A `define` block
  may name several contexts, with commas: `run=release-git,slow define`.
- A bash block stops at its first failing command.

````markdown nested
```bash run=scratch define
ONT=business_architecture/ontology
```

```bash run=scratch
echo "$ONT/release"
```

```text expect
business_architecture/ontology/release
```
````

When a command must stop with an error, name the exit status: `run=scratch exit=2`.

````markdown nested
```python run=scratch exit=2
import sys
print("the report has 1 blocking row")
sys.exit(2)
```

```text expect
the report has 1 blocking row
```
````

## Commands for Windows

Write a command for Windows in a `powershell` or `cmd` block, with the `py` launcher. The check reads each line
as a program and its arguments and runs it without a shell, on every platform. `py` and `python` are the Python
that runs the check. `cd` moves the lines after it. Write paths with forward slashes, which Python on Windows
accepts.

````markdown nested
```powershell run=scratch
py -c "print('KPI Store')"
```

```text expect
KPI Store
```
````

A line with shell syntax (a pipe, a redirection, a variable such as `$env:NAME`) fails this reading. Rewrite the
line without it when you can. When the line needs a real shell, add `os=windows`: the block then runs in
PowerShell or cmd on Windows, and every other platform counts it as skipped under `windows-only`.

````markdown nested
```powershell run=scratch os=windows
$env:PYTHONUTF8 = "1"
py -c "print('KPI Store')"
```
````

## Output: `expect`

The check compares an `expect` block with what the block before it printed, standard output and standard error
together. Before it compares, it removes colour codes, spaces at the end of a line, and blank lines at the start
and the end. Two marks stand for text that changes from run to run:

- A placeholder in angle brackets, such as `<run id>`, stands for any text on its line.
- A line that holds only `...` stands for any number of lines, also none.

Everything else must match letter for letter.

````markdown nested
```python run=scratch
import os
print("run", os.getpid(), "started")
print("step one")
print("step two")
print("all checks passed")
```

```text expect
run <run id> started
...
all checks passed
```
````

An `expect` block after a `skip` block is counted as skipped under the same reason.

## A block the check cannot run: `skip`

Skip a block only when a test on this machine cannot run it. Give one of these reasons, then a colon, then the
detail in a few words.

| Reason | Use it when |
|---|---|
| `needs-client-server` | The command reads or writes a server that only the client has. |
| `needs-browser-sign-in` | The command opens a browser for a person to sign in. |
| `windows-only` | The command works only on Windows, and the Windows test cannot run it either. |
| `destructive` | The command deletes or replaces something a test must not touch. |
| `illustration` | The block is a sketch, a formula or a usage pattern. Nobody types it or copies it. |
| `awaits-the-rewrite` | The document is about to be rewritten. This reason is temporary. |

````markdown nested
```bash skip reason="needs-browser-sign-in: opens the sign-in page of the workspace"
databricks auth login
```

```text skip reason="illustration: a sketch of the order of the loads"
Databricks -> Fuseki -> Neo4j
```
````

The check with `--strict` fails on `awaits-the-rewrite`. The cut runs `--strict`, so no such block may remain.
Any other reason is a deliberate change to `scripts/doc_snippets.toml` and to the test that pins the list.

## A file or a part of one: `file` and `excerpt`

When a block shows the content of a file of the release, name the file. The path starts at the release's top
folder. `file=` is for the whole file and `excerpt=` for some lines of it. The block fails when the file changes
and the document does not.

````markdown nested
```csv file=skills/ontology/templates/regression-expected.csv
question,status,queries,waits_for
CQ1,drafted,,
CQ2,drafted,,
```

```toml excerpt=scripts/doc_snippets.toml
[contexts.scratch]
base = "empty"
```
````

## An example to read: `parse`

A block of data or of a query that is not a file of the release is parsed, so a typing error fails. A Turtle
block may leave out its prefix lines. Cypher has no parser here: the check reads it with the tokenizer of the
cross-graph questions and tests that every string is closed and every bracket has its partner. A command is
never parsed in place of a run: tag it `run` or `skip`.

````markdown nested
```toml parse
[release]
zip = "kpi-store-1.1.zip"
sha256 = "<64 hex>"
```

```turtle parse
kpi:crack-spread skos:prefLabel "Crack spread"@en .
```

```sparql parse
SELECT ?measure WHERE { ?measure a <https://example.org/Measure> }
```

```cypher parse
MATCH (n:Resource {uri: $uri}) RETURN n.uri AS uri
```
````

## Values the reader fills in

Write a value the reader must supply as a placeholder in angle brackets: `<your workspace>`. Use lower-case
words that say what the value is.

In a `run` block, the context gives each placeholder its value, so the block still runs in the test. A
placeholder that the context does not know fails the block. The contexts' placeholders are in
`scripts/doc_snippets.toml`. A value may hold letters, digits and `. _ / : @ = + , -` only, because the check
puts it into the command.

## The contexts

A context is the folder a block runs in. Nothing runs in the release itself: each context is a temporary folder,
and a block's home folder is temporary too.

| Context | What it is | Runs when |
|---|---|---|
| `scratch` | An empty folder. | Always. |
| `release-copy` | A copy of the release as a plain folder. | Always. |
| `release-git` | A copy of the release in a new Git repository with one commit. | Always. |
| `slow` | The same as `release-git`, for commands that take minutes. | `DOC_SNIPPETS_SLOW` is set. |
| `stores` | A copy of the release beside a local Fuseki and a local Neo4j test server. | `KPI_STORE_TEST_FUSEKI_URL` and `KPI_STORE_TEST_NEO4J_URI` are set. |
| `databricks-free` | A copy of the release with the rehearsal workspace's profile. It keeps the real home folder. | `KPI_STORE_TEST_DATABRICKS_PROFILE` is set. |

A context is one chain. When its variable is not set, the check counts every block of the context as skipped and
prints the count with the variable to set. So keep the quick, independent commands in a context that always
runs, and give a guide whose steps take minutes one context for all its steps.

A block must be quick in a context that always runs: `scripts/check.sh` runs them all, and the whole document
check has two minutes.

A check that a block starts, such as `bash scripts/check.sh` in a copy of the release, runs no block itself.

To add a context, add a table to `scripts/doc_snippets.toml`. The comments there explain each key.

````markdown nested
```toml parse
[contexts.second-run]
base = "release-copy"
needs_env = ["KPI_STORE_TEST_SECOND_RUN"]
timeout = 600

[contexts.second-run.placeholders]
"your report" = "discovery-report.json"
```
````

## Run the check

Run it from the release's top folder. For one document:

```powershell run=release-copy
py scripts/doc_snippets.py check scripts/DOC-SNIPPETS.md --verbose
```

```text expect
...
<count> blocks: <the counts>
```

`--verbose` prints one line for each block. With no document, the check reads every Markdown document.
`check --static` reads the tags, the files and the parsed blocks and runs nothing. `list` counts the blocks of
each document by tag, and `contexts` says which contexts can run on this machine.

These three commands are tested in a copy of the release. A check that a block starts runs no block, so in the
test they read the tags and stop there.

The parsers need three packages. When they are not installed, start the check through `uv`:

```bash run=release-copy
uv run --no-project --with rdflib --with pyyaml --with sqlglot python3 scripts/doc_snippets.py check scripts/DOC-SNIPPETS.md
```

To run a context that is off, set its variable. For the slow context:

**This takes many minutes.** The slow blocks of that guide run the whole of `scripts/check.sh`.

```bash run=release-copy
DOC_SNIPPETS_SLOW=1 uv run --no-project --with rdflib --with pyyaml --with sqlglot python3 scripts/doc_snippets.py check HOW-TO-UPDATE.md
```

At the cut, set the variable of every context and add `--strict --all-contexts`. `--all-contexts` fails a block
whose context cannot run, so nothing is skipped for a missing server.

## What the check prints

Each failure is one line with the document and the line of the block, then the end of the block's output. The
last line counts the blocks:

```text skip reason="illustration: the shape of the count, whose numbers change with every document"
88 blocks: 7 run, 26 checked, 55 skipped (awaits-the-rewrite 20, illustration 29, needs-client-server 1, ...)
```

The check reads Markdown only. An HTML page with no Markdown source is out of its reach.
`py scripts/doc_snippets.py html` lists those pages with the number of code blocks in each.
