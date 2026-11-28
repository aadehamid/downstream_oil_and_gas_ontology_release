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
| `skip reason="<reason>: <detail>"` | Does not run it. Counts it under the reason. Parses it when its language is one that `parse` reads, or `python`. |
| `file=<path>` | Compares it with the whole file at that path. |
| `excerpt=<path>` | Checks that its lines are in that file, in this order and next to each other. |
| `usage=<path>` | Checks a usage pattern against the script at that path. The script must exist and have each option the block names. |
| `parse` | Parses it: `json`, `toml`, `yaml`, `ini`, `turtle`, `sparql`, `sql` or `cypher`. For `cypher` this is a token check, not a grammar check: it finds a string, a backtick name or a bracket that is never closed, and nothing else. |
| `nested` | Reads it as a small document and tests the blocks in it. The language is `markdown`. |

Use three backticks for a fence. The check cannot test code that is written any other way, and fails on it: a
block inside a block quote, a block indented by four spaces, and a raw `<pre>` or `<code>` block in a Markdown
file. An HTML page written by hand tags its `<pre>` blocks in another way, described below.

## A command: `run`

A `run` block names the context it runs in. The languages that run are `bash`, `sh`, `python`, `powershell` and
`cmd`. A context may name a program for one more language, and then a block in that language runs there: "A
statement for a store" below shows `sql` and `cypher`. Show the output in an `expect` block right after it.

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

Write a command for Windows in a `powershell` or `cmd` block, and start Python with `python`. The check reads each
line as a program and its arguments and runs it without a shell, on every platform. `python` is the Python that
runs the check. A run block that starts Python with the `py` launcher fails the check: a Python from a virtual
environment, or one that `uv` installed, has no launcher, and the first real run of the release was on such a
machine. `cd` moves the lines after it. Write paths with forward slashes, which Python on Windows
accepts.

````markdown nested
```powershell run=scratch
python -c "print('KPI Store')"
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
python -c "print('KPI Store')"
```

```text expect
KPI Store
```
````

A real shell finds `python` on `PATH`. Under `scripts/check.sh` that is the temporary environment which `uv`
makes for the check, with the check's packages and `pip`. So a line such as `python -m pip install <package>`
installs into that environment, which is deleted when the check ends, and changes no Python of the reader.

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

## A statement for a store

A SQL statement runs in a SQL editor and a Cypher statement in Neo4j Browser, so the check cannot run them as
commands. Four contexts give such a block a store to run on. `scripts/doc_snippets_fixtures.py` makes the store
of the last three, removes it when the check ends, and runs the statements of all four.

| Context | The block runs on | Write there |
|---|---|---|
| `enterprise-database` | The database `businessprocessarchitecturegraph` of the Neo4j test server, read only. | A `cypher` block that only asks. A statement that writes fails. |
| `scratch-database` | A database of 25 made-up nodes with the constraint `n10s_unique_uri`. The context makes it and drops it. | A `cypher` block that deletes. |
| `scratch-schemas` | Two schemas in the rehearsal catalog, with the four tables and the volume that a run of the KPI Store leaves. The context makes them and drops them. | A `sql` block that drops, and a `python` block that needs a notebook's `spark`. |
| `questions` | A composite database over two made-up graphs. The context makes it and drops it. | The commands of the cross-graph questions. |

A `cypher` block prints the rows of each statement: one line of column names, then one line for each row. A
`sql` block prints `OK:` and the statement, for each statement.

Each store the program makes on the Neo4j server gets a new name for the run, such as `docsnippetsscratch` and
eight digits and letters. The program stops before it makes anything when the server already holds a database or
an alias of that name. It records each thing it makes and drops only those, also after a start that failed
halfway. So it never empties or drops a database that was there before.

A statement may reach only the store of its context, and the program checks every statement of a block before
it sends the first:

- A `cypher` block for `scratch-database` starts with `MATCH`, `DROP CONSTRAINT` or `SHOW CONSTRAINTS`. One for
  `enterprise-database` starts with `MATCH`, `RETURN`, `SHOW CONSTRAINTS` or `CALL db.info()`.
- No Cypher statement may hold `USE`, also not inside a subquery, or a word that names or changes a database, an
  alias, the server or its accounts. It may call no procedure but `db.info`. The program reads the statement
  without its comments, and a procedure's name without its backticks, so neither hides a name. It refuses a `CALL`
  whose procedure name it cannot read.
- A `sql` block holds only `DROP TABLE`, `DROP VOLUME` or `DROP SCHEMA` statements, each with `IF EXISTS` and one
  plain name.

The documents name the client's objects, such as `idp_sbx.kpi_store.epm_triples`. In `scratch-schemas` the
program replaces the two schema names of `kpi_store/kpi_store.example.toml`, in the catalog that file names, with
the two throwaway schemas. That replacement is the only way a name reaches the warehouse: the program refuses a
statement whose name is not one of those two schemas or an object in them. It also refuses a
`DROP ... IF EXISTS` that names nothing the context made, because such a statement would pass in silence
whatever name it held. So a wrong name in the document fails the block.

A `python` block in `scratch-schemas` runs as a notebook cell of the `rdf-store` skill would. It has `spark` and
`files`, and it can import `rdfstore`. Here `spark` sends each statement to the rehearsal workspace's SQL
warehouse, and `files` is the three smallest module packages of the release. A Spark session exists only inside
a Databricks notebook; the runner's `notebook` step runs the real one.

A block that empties or drops what other blocks read must not run on the stores they share. Give it one of these
contexts. When it must run on the shared stores, as the runbook's reset does, the document's next step must load
them again.

## A block the check cannot run: `skip`

Skip a block only when no test can run it. Give one of these reasons, then a colon, then the detail in a few
words.

| Reason | Use it when |
|---|---|
| `needs-client-server` | The command reads or writes a server that only the client has, and no stand-in is meaningful. |
| `needs-browser-sign-in` | The command opens a browser for a person to sign in. |
| `windows-only` | The command works only on Windows, and the Windows test job cannot run it either. |
| `destructive` | The command deletes or replaces something a test must not touch. |
| `illustration` | The block is a sketch, a formula or a form to fill in. No tool can run it or parse it. |
| `awaits-the-rewrite` | The document is about to be rewritten. This reason is temporary. |

A skipped block is still parsed when its language is one that `parse` reads, or `python`. A typing error in it
fails the check. The block then counts as checked, and the last line of the check says how many such blocks
there are. Write `text` as the language of a block that is deliberately not valid.

Every skipped block has a row in the table of "Blocks the test does not run" below. A test fails when a skipped
block has no row, so add the row when you add the block.

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

An excerpt of a Markdown file may also quote the lines of one of its blocks as that block's document reads them. A
block inside a list item stands indented in its file, and the check reads its body without the fence's indent, so
a guide can quote a command of another guide's numbered step as it reads there. Only a fence's indent comes off:
the lines of a code file, and prose that only stands indented, match where they stand. A block that quotes a
command which another document runs and checks is how one document shows that command without running it a second
time.

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

## A usage pattern: `usage`

A usage pattern shows how to call a script. It has a name in angle brackets for each value, and square brackets
around what is optional, so it cannot run. Name the script, and the check compares each option that the block
names after the script, such as `--config`, with the options the script takes. When the block calls several
scripts, name the folder that holds them all. The block fails when a script is renamed or loses an option.

How the check reads a script's options depends on the script:

- A script that builds its parser with `argparse` is asked for its own `--help`, and for the help of the
  subcommand the line names. When a package it imports is missing, the check reads its `add_argument` calls.
- A script that reads its arguments by hand is never started. The check reads the options its code handles: each
  text that is exactly `--name` and stands where the code reads its arguments. Such a place is a comparison, a
  membership test, a `case` of a match statement, a lookup such as `opts["--name"]` or `opts.get("--name")`, and a
  set, a tuple or a dict of options.

A comment, a docstring, a longer string that holds the option's text, and a name that is only given the text do
not make an option. Neither does a text in a list, which is how a command for another program is written, or a
text given to any other call, such as the message of an error. For a script that reads its arguments by hand, the
check proves that the code names the option where it reads its arguments, not what the code does with it.

````markdown nested
```bash usage=scripts/check_standalone.py
python3 scripts/check_standalone.py [--strict] [--rules] [--root <folder>]
```
````

## An example to read: `parse`

A block of data or of a query that is not a file of the release is parsed, so a typing error fails. A Turtle
block may leave out its prefix lines. An `ini` block may leave out its section heading. A command is never parsed
in place of a run: tag it `run` or `skip`.

A Turtle or SPARQL block that uses the syntax of RDF 1.2, such as a reifier or `isTRIPLE`, says `rdf=1.2`. The
`pyoxigraph` package then parses it, because `rdflib` does not read that syntax.

For `cypher` the check is a token check, not a grammar check, because there is no Cypher parser here. The
tokenizer of the cross-graph questions reads the block, and the check finds a string, a backtick name or a
bracket that is never closed. It does not find clauses in the wrong order or a misspelt keyword.

````markdown nested
```toml parse
[release]
zip = "kpi-store-1.2.zip"
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

```turtle parse rdf=1.2
kpi:crack-spread kpi:definedBy kpi:economics ~ kpi:definition-1 {| kpi:position 2 |} .
```

```ini parse
dbms.security.procedures.unrestricted=apoc.*,n10s.*
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
`scripts/doc_snippets.toml`. A placeholder whose value there is `fixture` gets its value from the store that the
context makes. A value may hold letters, digits and `. _ / : @ = + , -` only, because the check
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
| `term-change` | A Git copy of its own for the update guide's term change, from the form to the applied proposal. | `DOC_SNIPPETS_SLOW` is set. |
| `reference-item` | A Git copy of its own for the update guide's reference item, from the form for a new system to the applied proposal. | `DOC_SNIPPETS_SLOW` is set. |
| `new-kpi` | A Git copy of its own for the update guide's new KPI, from the KPI intake form to the applied proposal. | `DOC_SNIPPETS_SLOW` is set. |
| `stores` | A copy of the release beside a local Fuseki and a local Neo4j test server. | `KPI_STORE_TEST_FUSEKI_URL` and `KPI_STORE_TEST_NEO4J_URI` are set. |
| `databricks-free` | A copy of the release with the rehearsal workspace's profile. It keeps the real home folder. | `KPI_STORE_TEST_DATABRICKS_PROFILE` is set. |
| `reasoner` | A copy of the release, for a command that runs the ROBOT jar with Java. | `KPI_STORE_TEST_ROBOT_JAR` names the jar. |
| `empty-fuseki` | A copy of the release beside a second local Fuseki dataset that no other document loads. | `KPI_STORE_TEST_EMPTY_FUSEKI_URL` is set. |
| `first-run` | A copy of the release as a plain folder, with a prepared local settings file. It keeps the real home folder. | `KPI_STORE_TEST_LOCAL_SETTINGS` and `KPI_STORE_TEST_LPG_OUT` are set. |
| `enterprise-database`, `scratch-database`, `questions` | A copy of the release beside the Neo4j test server. "A statement for a store" describes each. | `KPI_STORE_TEST_NEO4J_URI` and `KPI_STORE_TEST_NEO4J_PASSWORD` are set. |
| `scratch-schemas` | A copy of the release beside two throwaway schemas of the rehearsal workspace. It keeps the real home folder. | `KPI_STORE_TEST_LOCAL_SETTINGS` is set. |
| `windows-account` | An empty folder on a Windows account that may be changed. It keeps the real home folder. | `DOC_SNIPPETS_WINDOWS_ACCOUNT` is set. |
| `shared-drive` | A copy of the release on a Windows machine with a stand-in for the client's shared drive: a drive `S:` that holds `Commercial Planning/Shared`. | `DOC_SNIPPETS_SHARED_DRIVE` is set. |

The `first-run` context is for the runbook, whose commands find the local settings file through the variable
`KPI_STORE_LOCAL`. The context gives its blocks that variable, with the value of `KPI_STORE_TEST_LOCAL_SETTINGS`.
The file must name test stores and a rehearsal workspace, never the client's. `KPI_STORE_TEST_LPG_OUT` is the folder that the file's `[projection]` `out` names. No block of another context gets
`KPI_STORE_LOCAL`, also when your own terminal has it set.

The `first-run` context is one chain for the whole check, because the stores it loads are shared. The registry
names the runbook as its `owner`. A block of another document that says `run=first-run` runs in the same folder,
after the runbook's blocks, and finds the stores as the runbook left them. The check reads the runbook before
such a document, wherever its name sorts. When you check such a document alone, its `first-run` blocks are
counted as skipped, and `--all-contexts` fails them. Name the runbook in the same command.

**Set `DOC_SNIPPETS_WINDOWS_ACCOUNT` only on an account you can throw away.** A block of `windows-account`
changes a setting of the Windows account that runs the check, as `setx` does. The Windows test job sets the
variable. On a reader's machine it is not set, so `scripts/check.sh` never runs such a block there.

**Set `DOC_SNIPPETS_SHARED_DRIVE` only where drive `S:` is a stand-in.** A block of `shared-drive` writes the
folder `KPI-intake` under `S:/Commercial Planning/Shared` and a check report beside a file there. The Windows
test job makes that drive with `subst`, over a folder of its own, and puts the release's example in it.

A context is one chain. When its variable is not set, the check counts every block of the context as skipped and
prints the count with the variable to set. So keep the quick, independent commands in a context that always
runs, and give a guide whose steps take minutes one context for all its steps.

A block must be quick in a context that always runs: `scripts/check.sh` runs them all. Keep such a block to
seconds on a fast machine. Its limit is ten minutes, because a slow machine takes several times as long.

A check that a block starts, such as `bash scripts/check.sh` in a copy of the release, runs no block itself, and
its last line says so. The running check proves to it that a block started it. The variable
`DOC_SNIPPETS_NESTED` set by hand proves nothing: a check that finds it without that proof fails.

To add a context, add a table to `scripts/doc_snippets.toml`. The comments there explain each key. A context
that needs a store of its own names a `fixture`. That is a command, which the check runs with `up` before the
context's first block and with `down` when the check ends.

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
python scripts/doc_snippets.py check scripts/DOC-SNIPPETS.md --verbose
```

```text expect
...
<count> blocks: 0 run (0 status-only), <checked> checked, <skipped> skipped (<the reasons>)
this check was started by a block of another check, so it ran no block
```

`--verbose` prints one line for each block. With no document, the check reads every Markdown document and every
HTML page written by hand.
`check --static` reads the tags, the files and the parsed blocks and runs nothing. `list` counts the blocks of
each document by tag, and `contexts` says which contexts can run on this machine. `not-run` prints one table row
for each skipped block, for the table of "Blocks the test does not run".

These three commands are tested in a copy of the release. A check that a block starts runs no block, so in the
test they read the tags and stop there.

The parsers need four packages. When they are not installed, start the check through `uv`:

```bash run=release-copy
uv run -q --no-project --with rdflib --with pyyaml --with sqlglot --with pyoxigraph python scripts/doc_snippets.py check scripts/DOC-SNIPPETS.md
```

```text expect
<count> blocks: 0 run (0 status-only), <checked> checked, <skipped> skipped (<the reasons>)
this check was started by a block of another check, so it ran no block
```

To run a context that is off, set its variable. **The slow context takes many minutes.** The slow blocks of
`HOW-TO-UPDATE.md` run the whole of `scripts/check.sh`.

```bash run=release-copy
DOC_SNIPPETS_SLOW=1 uv run -q --no-project --with rdflib --with pyyaml --with sqlglot --with pyoxigraph python scripts/doc_snippets.py check HOW-TO-UPDATE.md
```

```text expect
<count> blocks: 0 run (0 status-only), <checked> checked, <skipped> skipped (<the reasons>)
this check was started by a block of another check, so it ran no block
```

At the cut, set the variable of every context and add `--strict --all-contexts`. `--all-contexts` fails a block
whose context cannot run, so nothing is skipped for a missing server.

## The release the examples describe

An example shows what a command printed on the release as it was shipped: a version, a count of triples, a
refusal that names a version. After a correction, or after a new version of a module, the same command prints
something else, and that is right. So the registry records which release the examples describe. The `[describes]`
table of `scripts/doc_snippets.toml` holds the SHA-256 of `business_architecture/ontology/releases/catalog.ttl`,
the catalog of every release package. `build_catalog.py --write` writes that file, and it changes with every
package version. The check reads CRLF line ends as LF, so a checkout on Windows gives the same value.

The check compares the recorded value with the catalog it finds.

| The release is | `check` | `check --strict` |
|---|---|---|
| the one the examples describe | Runs every block. | Runs every block. |
| another one | Runs no block and ends with exit 0, unless a tag, a file or a parsed block is wrong. | Fails, and still runs every block. |

On another release the check still reads every tag, compares the `file` and `excerpt` blocks and parses the
`parse` blocks. It counts each block it did not run under "not run: the release changed since the documents were
written", and a note after the count says the same. So `scripts/check.sh` passes on a corrected release, and the
runner can load it.

`check --strict` is for the person who builds a release to send on. It fails with the two values, and it runs
every block, so that each example that no longer holds fails with its line.

When you prepare a new zip from a changed release, bring the examples up to date:

1. Run `check --strict`, and change each example that fails.
2. Record the release that the examples now describe:

   ```powershell run=release-copy
   python scripts/doc_snippets.py describe-release --write
   ```

   ```text expect
   the documents' examples describe this release (business_architecture/ontology/releases/catalog.ttl, SHA-256 <a digest>)
   ```

   The test runs the command on the release as shipped, where the recorded value is already right, so it writes
   nothing and prints the line above. On a changed release its line starts with `wrote` and holds the new value.

With no option, the command writes nothing and says whether the recorded value is this release's. It ends with
exit 1 when it is not:

```powershell run=release-copy
python scripts/doc_snippets.py describe-release
```

```text expect
the documents' examples describe this release (business_architecture/ontology/releases/catalog.ttl, SHA-256 <a digest>)
```

`scripts/check-pinned.sh` runs a test that the recorded value is the catalog's, so a release cannot be built with
an old value. A folder that holds no catalog file has no release to compare, and the check runs there as on the
release the examples describe.

## What the check prints

Each failure is one line with the document and the line of the block, then the end of the block's output. The
last line counts the blocks. "checked" counts the blocks that were compared or parsed, and "status-only" the
blocks that ran with no `expect` block. This is the count for a document with four parsed blocks and one sketch:

```powershell run=release-copy
python scripts/doc_snippets.py check skills/ontology-to-lpg/references/design-rules.md
```

```text expect
5 blocks: 0 run (0 status-only), 4 checked, 1 skipped (illustration 1)
this check was started by a block of another check, so it ran no block
```

When a skipped block was parsed, the line ends with their number and reasons, such as
`1 of the checked parsed but not run (needs-client-server 1)`.

`python scripts/doc_snippets.py html` lists the HTML pages written by hand, with the number of `<pre>` blocks in each.

## Blocks the test does not run

Every other block of the documents is run, compared with a file, checked against a script or parsed. The blocks in
this table are tagged `skip`, and no test runs them. Each row says why, what is done instead, and who can run the
block.

A test in `scripts/test_doc_snippets.py` compares this table with the documents. It fails when a skipped block
has no row here, and when a row names a block that is gone. The first four cells must be the block's document,
the heading it stands under, the start of its first line and its reason. `python scripts/doc_snippets.py not-run`
prints those four cells for every skipped block. Write the last two cells yourself.

| Document | Heading | The block starts with | Reason | What is done instead | Who can run it |
|---|---|---|---|---|---|
| `.agents/skills/project-memory/SKILL.md` | Recall first | `scripts/memory.sh brief # most recent current facts` | `needs-client-server` | `scripts/test_memory.py` runs `brief`, `recall`, `about`, `history` and `asof` against a fresh store where `relate` is installed. CI has no `relate`, so those tests skip there. | An agent on a machine with `relate`, in a checkout with the memory store. |
| `.agents/skills/project-memory/SKILL.md` | Save before you finish | `scripts/memory.sh remember - <<'JSON'` | `needs-client-server` | `scripts/test_memory.py` saves episodes of this shape into a fresh store where `relate` is installed, and checks the validation and supersession. CI has no `relate`, so those tests skip there. | An agent on a machine with `relate`, in a checkout with the memory store. |
| `.agents/skills/project-memory/SKILL.md` | Serving memory over MCP | `relate serve --mcp stdio --database "$(scripts/memory.sh pat` | `needs-client-server` | Nothing; it starts a long-running server. `relate` documents the command. | An agent on a machine with `relate`, in a checkout with the memory store. |
| `.claude/skills/project-memory/SKILL.md` | Recall first | `scripts/memory.sh brief # most recent current facts` | `needs-client-server` | The same block as the `.agents/skills/project-memory/SKILL.md` row, read through the link. `scripts/test_memory.py` runs `brief`, `recall`, `about`, `history` and `asof` against a fresh store where `relate` is installed. CI has no `relate`, so those tests skip there. | An agent on a machine with `relate`, in a checkout with the memory store. |
| `.claude/skills/project-memory/SKILL.md` | Save before you finish | `scripts/memory.sh remember - <<'JSON'` | `needs-client-server` | The same block as the `.agents/skills/project-memory/SKILL.md` row, read through the link. `scripts/test_memory.py` saves episodes of this shape into a fresh store where `relate` is installed, and checks the validation and supersession. CI has no `relate`, so those tests skip there. | An agent on a machine with `relate`, in a checkout with the memory store. |
| `.claude/skills/project-memory/SKILL.md` | Serving memory over MCP | `relate serve --mcp stdio --database "$(scripts/memory.sh pat` | `needs-client-server` | The same block as the `.agents/skills/project-memory/SKILL.md` row, read through the link. Nothing; it starts a long-running server. `relate` documents the command. | An agent on a machine with `relate`, in a checkout with the memory store. |
| `business_architecture/domain/decision-packages/2026-10-14/step9-walkthrough.md` | Question 1. Approve the controlled-value shapes | `Constraint Violation in HasValueConstraintComponent` | `illustration` | It is a shortened quote of a validation report in a dated decision record. `business_architecture/ontology/validation/test_controlled_values.py` tests that a value from the wrong list fails these shapes. | Nobody. It is a quote, not a command. |
| `business_architecture/ontology/MODULES.md` | One walk across modules | `Gulf Coast 3-2-1 crack spread (market-data)` | `illustration` | It is a sketch. Each link in it is quoted earlier on the page in a Turtle block, and those blocks are parsed. | Nobody. It is a sketch. |
| `business_architecture/ontology/build/r1/r1-consumer-inventory-checklist.md` | R1 Hierarchy-Consumer Inventory — Team Checklist | `Downstream Operations > Commercial & Marketing > Planning &` | `illustration` | Nothing. The block holds two texts to search for in tools outside this release. | The team that owns each tool, by hand. |
| `business_architecture/ontology/build/r1/r1-consumer-inventory-checklist.md` | G. Attestation | `Asset class: _______________ Owner: _______________ Date: __` | `illustration` | Nothing. It is a form. | A person fills it in by hand. |
| `business_architecture/ontology/projection/ontology-stores-runbook.md` | Sign in to Databricks | `databricks auth login --host <your workspace URL> --profile` | `needs-browser-sign-in` | The command cannot end without a person in a browser, so nothing runs it. Three things are tested in its place. The Windows test job runs `databricks auth login --help` with the same program and fails when `--host` or `--profile` is not among its options. The setup check's `databricks-auth` line passes only for a profile that is signed in, and the document test runs that check with the rehearsal workspace's profile. The Windows test job has no browser, so it signs in with a token from a secret. | A person, in a browser. |
| `HANDOUT.md` | 1. Set up the machine, once | `& "$HOME\kpi-store-local\databricks-cli\databricks.exe" auth` | `needs-browser-sign-in` | It is the runbook's sign-in with the path of the unpacked command line, which the runbook's row above stands for. The Windows test job runs the command line from that unpacked folder, named in the settings. | A person, in a browser. |
| `business_architecture/reference/internal/crack-spread-kpi-definition.md` | 3.2 Core formulas | `3-2-1 Ex-RVO, $/bbl` | `illustration` | It is the client's formula, quoted as text. `scripts/test_doc_snippets.py` reads it from the document and works it out (`test_the_formulas_quoted_as_text_in_the_crack_spread_definition_hold`). | Nobody runs it. The test works it out. |
| `business_architecture/reference/internal/crack-spread-kpi-definition.md` | 3.2 Core formulas | `3-2-1 Inc-RVO, $/bbl` | `illustration` | It is the client's formula, quoted as text. `scripts/test_doc_snippets.py` reads it from the document and works it out (`test_the_formulas_quoted_as_text_in_the_crack_spread_definition_hold`). | Nobody runs it. The test works it out. |
| `business_architecture/reference/internal/crack-spread-kpi-definition.md` | 4.4 MPC-weighted 3-2-1 | `Before 5 May 2024: (USGC × 0.40) + (Chicago × 0.40) + (LA ×` | `illustration` | It is the client's formula, quoted as text. `scripts/test_doc_snippets.py` reads it from the document and works it out (`test_the_formulas_quoted_as_text_in_the_crack_spread_definition_hold`). | Nobody runs it. The test works it out. |
| `ds_business_process/validation/README.md` | Run them | `uv run --with rdflib --with pyshacl --with owlready2 python` | `illustration` | The angle brackets stand for files a batch makes. `scripts/check.sh` runs the same tests with pinned versions (`ds_business_process/validation` and the batch tests). | Anyone, with their own candidate files. |
| `scripts/DOC-SNIPPETS.md` | A block the check cannot run: `skip` | `databricks auth login` | `needs-browser-sign-in` | It is this page's example of the `skip` tag, so it must be skipped. `scripts/test_doc_snippets.py` tests the tag. | A person, in a browser. |
| `scripts/DOC-SNIPPETS.md` | A block the check cannot run: `skip` | `Databricks -> Fuseki -> Neo4j` | `illustration` | It is this page's example of a sketch. `scripts/test_doc_snippets.py` tests the tag. | Nobody. It is a sketch. |
| `scripts/DOC-SNIPPETS.md` | A page written by hand | `<pre data-snippet="bash run=release-copy"><code>python3 scri` | `illustration` | It shows three made-up blocks of a page. `scripts/test_doc_snippets.py` runs blocks written in this form (`test_a_page_block_runs_as_the_text_its_reader_sees`). | Nobody. The three blocks are made up. |
| `skills/ontology-to-lpg/references/design-rules.md` | Mental model | `literal object -> node property` | `illustration` | It is a sketch of the rules that the same page states. The skill's `test_projection.py` tests the rules. | Nobody. It is a sketch. |
| `skills/ontology-to-lpg/references/pipeline.md` | The pipeline: check, reason, serialise, load, verify | `module.ttl ──┐` | `illustration` | It is a drawing of the five steps. The commands of each step are run blocks further down the page. | Nobody. It is a drawing. |
| `kpi-intake/how-to-use-the-form.html` | The name of an answers file | `crack-spreads-pricing.kpi-intake.json` | `illustration` | It is a file name. `kpi_store/intake/browser_check.py` checks the name that the form proposes for a download. | Nobody. It is a name. |

Some blocks run in a test and still not everywhere:

- **Nothing runs on the client's sandbox or the client's Enterprise server.** The `first-run` chain loads a
  rehearsal workspace and local test servers. The SQL and the Cypher of the runbook's "How to undo" run on
  throwaway schemas and a throwaway database, not on the objects they name.
- **The Windows test job signs in to a rehearsal Databricks workspace, never the client's.** The sign-in is a
  secret kept in the settings of the repository on GitHub. The release itself holds no token, no workspace
  address and no warehouse id. The job writes to two schemas and one workspace folder that it names after the
  run, and it removes them at its end. A pull request from a fork gets no secret, so its run skips that job and
  says so. `.github/workflows/check.yml` describes the job.
- **A block that says `os=windows` runs on Windows only.** `scripts/check.sh` runs it in the Windows test job. A
  block of the `windows-account` context or the `shared-drive` context runs in the job `stores` of the same
  workflow. So the runbook's `winget` command and the guide's two shared-drive commands are run there and nowhere
  else.
- **The store contexts run only where their variables are set.** `scripts/check.sh` on a reader's machine sets
  none, so it counts those blocks as skipped and names the variable. The cut sets them all and adds
  `--all-contexts`.

## The links of the documents

A second command reads every Markdown document and every HTML page of the tree, the generated pages too, and
checks that each relative link points at a file or a folder of the tree:

```powershell run=release-copy
python scripts/doc_snippets.py links
```

```text expect
every relative link points at a file or a folder of the tree
```

A broken link is one `FAIL` line with the document, the line and the link, and the command then ends with exit 1.
`scripts/check.sh` runs it. The command does not check a link with a scheme, such as `https:`, a link that is
only an anchor, or whether an anchor exists in the page it names. It compares names letter for letter, so a link
that differs from the file's name only in case fails. Two page templates are left out, because a builder fills
them in: `scripts/docs_template.html` and `business_architecture/ontology/viewer/horoi_page.html`.
