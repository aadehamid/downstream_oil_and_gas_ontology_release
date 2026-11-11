# Code blocks in the documents

Every code block in a Markdown document of this release is tested, and so is every code block in an HTML page
that was written by hand. `scripts/doc_snippets.py` reads each block's
tag and runs the block, compares it, parses it, or counts it as skipped for a stated reason. A block with no tag
fails `scripts/check.sh`. This page says how to write the tag.

The check reads every Markdown file that Git tracks or would add. A file that Git ignores does not ship, so the check
does not read it. In a folder with no Git, such as the unpacked zip, it reads every Markdown file. It reads the
HTML pages by the same rule; "A page written by hand" below says which ones.

The examples on this page are tested the same way. Each example is a small document inside a `markdown nested`
block, and the check tests the blocks in it.

## The tag

Write the tag on the opening fence, after the language: the language, a space, the tag. The HTML pages and the
Markdown viewers show the block as before, without the tag.

| Tag | What the check does with the block |
|---|---|
| `run=<context>` | Runs it in the context's folder. It must end with exit status 0. An `expect` block follows it, or it says `status-only`. |
| `expect` | Compares it with the output of the `run` block just before it. |
| `skip reason="<reason>: <detail>"` | Does not run it. Counts it under the reason. |
| `file=<path>` | Compares it with the whole file at that path. |
| `excerpt=<path>` | Checks that its lines are in that file, in this order and next to each other. |
| `parse` | Parses it: `json`, `toml`, `yaml`, `turtle`, `sparql`, `sql` or `cypher`. For `cypher` this is a token check, not a grammar check: it finds a string, a backtick name or a bracket that is never closed, and nothing else. |
| `nested` | Reads it as a small document and tests the blocks in it. The language is `markdown`. |

Use three backticks for a fence. The check cannot test code that is written any other way, and fails on it: a
block inside a block quote, a block indented by four spaces, and a raw `<pre>` or `<code>` block in a Markdown
file. An HTML page written by hand tags its `<pre>` blocks in another way, described below.

## A command: `run`

A `run` block names the context it runs in. The languages that run are `bash`, `sh`, `python`, `powershell` and
`cmd`. Show the output in an `expect` block right after it.

A block passes on its exit status and on its `expect` block. With no `expect` block, nothing checks what the
command prints, so the block must say so with the word `status-only`. The count at the end shows how many
blocks ran that way. Use it for a command that prints nothing, or whose output is long or changes with every
run.

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
```bash run=scratch status-only
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
  may name several contexts, with commas: `run=release-git,slow define status-only`.
- A bash block stops at its first failing command.

````markdown nested
```bash run=scratch define status-only
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

When a command asks the reader a question, give the answers in `types=`, with commas between them. The check
types each answer and a line end at the command's prompts, in that order. In a PowerShell or cmd block the
answers go to the last line's command. Say in the text around the block what the reader types and why. A
command that asks and gets no `types=` reads nothing and fails.

````markdown nested
```python run=scratch types="Change_Value_Amount,yes"
name = input("Type the new name to confirm: ")
answer = input("Type yes to cut: ")
print()
print("typed", name, "and", answer)
```

```text expect
Type the new name to confirm: Type yes to cut:
typed Change_Value_Amount and yes
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

```text expect
KPI Store
```
````

The check does not set `PYTHONUTF8` or `PYTHONIOENCODING` for a block, and removes them when its own environment
has them. A reader on Windows has neither. So when a command needs one of them, the block must set it, as the
example above does.

## Output: `expect`

The check compares an `expect` block with what the block before it printed, standard output and standard error
together. Before it compares, it removes colour codes, spaces at the end of a line, and blank lines at the start
and the end. Two marks stand for text that changes from run to run:

- A placeholder in angle brackets, such as `<run id>`, stands for any text on its line.
- A line that holds only `...` stands for any number of lines, also none.

Everything else must match letter for letter.

One kind of line is left out of the output before the check compares. On a machine that has not run a `uv`
command before, `uv` first reports its own work, for example `Installed 2 packages in 3ms`. The next run does
not print it. So do not show such a line in an `expect` block: the check would never find it.

An `expect` block needs at least one line with text of its own. An empty block, a lone `...` or a line made
only of placeholders would match any output, so the check refuses it.

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
block may leave out its prefix lines. A command is never parsed in place of a run: tag it `run` or `skip`.

For `cypher` the check is a token check, not a grammar check, because there is no Cypher parser here. The
tokenizer of the cross-graph questions reads the block, and the check finds a string, a backtick name or a
bracket that is never closed. It does not find clauses in the wrong order or a misspelt keyword.

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

## A page written by hand

Most HTML pages of the release are built from a Markdown file, and the check tests them through that file. A page
written by hand has no such source, so its blocks carry the tag themselves. The check reads every HTML page that
has no Markdown file of the same name beside it and does not name the tool that built it in a `generator` line of
its head. Today these are the walkthrough, the ontology guide, the two viewers with their templates, and the
best-practice pages. A page with no code block passes.

In such a page a code block is a `<pre>` element. Write the tag in its `data-snippet` attribute: the same words
a Markdown fence carries after its backticks, the language first. The attribute changes nothing a reader sees.

```html skip reason="illustration: the form of the attribute in a page, with made-up blocks"
<pre data-snippet="bash run=release-copy"><code>python3 scripts/epm_facts.py projection</code></pre>
<pre data-snippet="text expect"><code>...
  806 in-graph constraints</code></pre>
<pre data-snippet="text skip reason=&quot;illustration: a sketch of the order of the loads&quot;"><code>Databricks, then Fuseki, then Neo4j</code></pre>
```

The same rules apply as in Markdown, with these differences:

- A `<pre>` with no `data-snippet` attribute fails the check. So does an unknown tag, as on a fence.
- The block's text is what the reader sees. The check decodes `&lt;`, `&amp;` and the other character references,
  and drops the tags inside the block, such as a `<code>` or a `<span>` that colours a word.
- Inside the attribute, write a double quote as `&quot;`, or put the attribute in single quotes.
- Another element that shows a code block, such as a `<div>`, is tested too when it carries the attribute. A
  `<code>` span inside a sentence is text and is not tested, as in Markdown.
- Text in a `<script>` or a `<style>` is never a block.
- `nested` is for Markdown documents only.

The line a failure names is the line of the block's opening tag.

## Values the reader fills in

Write a value the reader must supply as a placeholder in angle brackets: `<your workspace>`. Use lower-case
words that say what the value is.

In a `run` block, the context gives each placeholder its value, so the block still runs in the test. A
placeholder that the context does not know fails the block. The contexts' placeholders are in
`scripts/doc_snippets.toml`. A value may hold letters, digits and `. _ / : @ = + , -` only, because the check
puts it into the command.

## The contexts

A context is the folder a block runs in. Nothing runs in the release itself: each context is a temporary folder,
and a block's home folder is temporary too. No variable that names the release's folder reaches a block, and a
link in the release is copied as the file it points to. A link that leads outside the release fails the block.

`databricks-free` is the one exception. Its blocks get the real home folder, because the sign-in of the
Databricks command line is kept there. A block in that context can write to the real home folder, so write
its commands with that in mind.

| Context | What it is | Runs when |
|---|---|---|
| `scratch` | An empty folder. | Always. |
| `release-copy` | A copy of the release as a plain folder. | Always. |
| `release-git` | A copy of the release in a new Git repository with one commit. | Always. |
| `slow` | The same as `release-git`, for commands that take minutes. | `DOC_SNIPPETS_SLOW` is set. |
| `correction` | A Git copy of its own for the update guide's cut of the made-up report, which ends with the whole check. | `DOC_SNIPPETS_SLOW` is set. |
| `new-module` | A Git copy of its own for the made-up module of the update guide. | `DOC_SNIPPETS_SLOW` is set. |
| `stores` | A copy of the release beside a local Fuseki and a local Neo4j test server. | `KPI_STORE_TEST_FUSEKI_URL` and `KPI_STORE_TEST_NEO4J_URI` are set. |
| `databricks-free` | A copy of the release with the rehearsal workspace's profile. It keeps the real home folder. | `KPI_STORE_TEST_DATABRICKS_PROFILE` is set. |
| `reasoner` | A copy of the release, for a command that runs the ROBOT jar with Java. | `KPI_STORE_TEST_ROBOT_JAR` names the jar. |
| `empty-fuseki` | A copy of the release beside a second local Fuseki dataset that no other document loads. | `KPI_STORE_TEST_EMPTY_FUSEKI_URL` is set. |
| `first-run` | A copy of the release as a plain folder, with a prepared local settings file. It keeps the real home folder. | `KPI_STORE_TEST_LOCAL_SETTINGS` and `KPI_STORE_TEST_LPG_OUT` are set. |

The `first-run` context is for the runbook, whose commands find the local settings file through the variable
`KPI_STORE_LOCAL`. The context gives its blocks that variable, with the value of `KPI_STORE_TEST_LOCAL_SETTINGS`.
The file must name test stores and a rehearsal workspace, never the client's. `KPI_STORE_TEST_LPG_OUT` is the folder that the file's `[projection]` `out` names. No block of another context gets
`KPI_STORE_LOCAL`, also when your own terminal has it set.

A context is one chain. When its variable is not set, the check counts every block of the context as skipped and
prints the count with the variable to set. So keep the quick, independent commands in a context that always
runs, and give a guide whose steps take minutes one context for all its steps.

A block must be quick in a context that always runs: `scripts/check.sh` runs them all, and the whole document
check has two minutes.

A check that a block starts, such as `bash scripts/check.sh` in a copy of the release, runs no block itself, and
its last line says so. The running check proves to it that a block started it. The variable
`DOC_SNIPPETS_NESTED` set by hand proves nothing: a check that finds it without that proof fails.

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
<count> blocks: 0 run (0 status-only), <checked> checked, <skipped> skipped (<the reasons>)
this check was started by a block of another check, so it ran no block
```

`--verbose` prints one line for each block. With no document, the check reads every Markdown document and every
HTML page written by hand.
`check --static` reads the tags, the files and the parsed blocks and runs nothing. `list` counts the blocks of
each document by tag, and `contexts` says which contexts can run on this machine.

These three commands are tested in a copy of the release. A check that a block starts runs no block, so in the
test they read the tags and stop there.

The parsers need three packages. When they are not installed, start the check through `uv`:

```bash run=release-copy
uv run -q --no-project --with rdflib --with pyyaml --with sqlglot python scripts/doc_snippets.py check scripts/DOC-SNIPPETS.md
```

```text expect
<count> blocks: 0 run (0 status-only), <checked> checked, <skipped> skipped (<the reasons>)
this check was started by a block of another check, so it ran no block
```

To run a context that is off, set its variable. **The slow context takes many minutes.** The slow blocks of
`HOW-TO-UPDATE.md` run the whole of `scripts/check.sh`.

```bash run=release-copy
DOC_SNIPPETS_SLOW=1 uv run -q --no-project --with rdflib --with pyyaml --with sqlglot python scripts/doc_snippets.py check HOW-TO-UPDATE.md
```

```text expect
<count> blocks: 0 run (0 status-only), <checked> checked, <skipped> skipped (<the reasons>)
this check was started by a block of another check, so it ran no block
```

At the cut, set the variable of every context and add `--strict --all-contexts`. `--all-contexts` fails a block
whose context cannot run, so nothing is skipped for a missing server.

## What the check prints

Each failure is one line with the document and the line of the block, then the end of the block's output. The
last line counts the blocks. "checked" counts the blocks that were compared or parsed, and "status-only" the
blocks that ran with no `expect` block:

```text skip reason="illustration: the shape of the count, whose numbers change with every document"
121 blocks: 18 run (9 status-only), 43 checked, 60 skipped (awaits-the-rewrite 21, illustration 31, ...)
```

`py scripts/doc_snippets.py html` lists the HTML pages written by hand, with the number of `<pre>` blocks in each.

## The links of the documents

A second command reads every Markdown document and every HTML page of the tree, the generated pages too, and
checks that each relative link points at a file or a folder of the tree:

```powershell run=release-copy
py scripts/doc_snippets.py links
```

```text expect
every relative link points at a file or a folder of the tree
```

A broken link is one `FAIL` line with the document, the line and the link, and the command then ends with exit 1.
`scripts/check.sh` runs it. The command does not check a link with a scheme, such as `https:`, a link that is
only an anchor, or whether an anchor exists in the page it names. It compares names letter for letter, so a link
that differs from the file's name only in case fails. Two page templates are left out, because a builder fills
them in: `scripts/docs_template.html` and `business_architecture/ontology/viewer/horoi_page.html`.
