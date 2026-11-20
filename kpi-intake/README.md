# KPI intake pack

Start here when the business wants a new KPI in the KPI Store. The pack holds the form that collects what the ontology needs for one KPI, a check that says whether a filled form is complete, and two filled examples.

The pack does not change the ontology. A complete, signed KPI form goes through two commands, propose and apply, and nobody edits a file: "What happens after" below says how. A complete, signed term change, for a measure the ontology already holds, goes through the same two commands: "The term change" below says how. A complete, signed reference item, for a new system or a new table, goes through them too: "The reference item" below says how.

## What is in this folder

| File | What it is |
|---|---|
| [`kpi-intake-form.html`](kpi-intake-form.html) | The form as one page. Open it in a browser. It works offline and sends nothing anywhere |
| `kpi-intake-form.xlsx` | The same form as an Excel workbook, for people who prefer Excel |
| [`how-to-use-the-form.html`](how-to-use-the-form.html) | The guide for the people who fill the form: the shared folder, the three buttons, the draft, and what happens to a saved file. Read it first |
| [`what-we-will-ask-you.md`](what-we-will-ask-you.md) | One page to send to the people you invite, before the interview |
| [`for-the-architect.md`](for-the-architect.md) | What each question feeds in the ontology, and the facts that have no place there yet |
| `examples/` | Two filled forms, each as an answers file and as a workbook: Crack Spreads Pricing and R&M Margin per Barrel |
| `catalogue.toml` | Every question, with its section, its rule and its reason. The forms are built from it |
| `settings.toml` | What belongs to your organization: the role titles and definitions, the domain list, who may see a KPI, the statuses, and what you hide from or add to the ontology's lists |
| `pick-lists.json` | The lists the forms offer, read from the release packages |
| `answers.schema.json` | The shape of an answers file, as a JSON Schema |

The HTML form, the workbook, the two pages, the pick lists and the examples are built by one command. Do not edit them by hand. "Change the form" below says what to edit. The guide `how-to-use-the-form.html` is written by hand.

## Two words: business area and domain

The form uses two words that are easy to mix up.

- A **business area** is the function that runs a process, such as Commercial or Marketing. The list comes from the ontology.
- A **domain** is the data domain a KPI belongs to, such as Market Price. Each domain has a Domain Owner. Every KPI belongs to exactly one domain. The list comes from `settings.toml`, because the ontology holds no list of domains yet.

**The domain list that ships with this release is an example.** It has eight made-up domains, two of them active, so that the forms and the examples work. Replace it with your organization's domains before the first interview. "Change the form" shows how.

## Who does what

The form's "The roles" view and the workbook's Roles sheet give each role's definition. In an intake:

| Role | What the role does in the intake |
|---|---|
| Program manager | Owns the request, decides who attends, and proposes which domain to ask |
| Business analyst | Interviews, fills the form and drafts the texts the others confirm |
| Global Process Owner, or a named delegate | Says which business area, process and step the KPI is about |
| Domain Owner | Confirms that the KPI belongs to the domain. Need not sit in the rest of the interview |
| Data Owner | Says what the KPI means and what it connects to, and signs its definition |
| Data Steward | Gives the facts about the KPI and its other names |
| Data Product Owner | Says which data product gives the KPI |
| Digital IT | Says where the data lives, in section 7, after the business has signed |
| Architect | Checks the form, signs the change and adds the KPI to the ontology |

Enterprise Data Governance is consulted when the check finds the KPI's name in another module. Privacy, Security, Compliance and Risk are consulted when the KPI is restricted.

## How an interview runs

One form is for one KPI.

1. The Program manager fills in the request: its number, its date, the requester's role and the people invited.
2. The Program manager proposes the domain and asks that domain's Domain Owner whether the KPI is in its scope.
3. The Program manager sends [`what-we-will-ask-you.md`](what-we-will-ask-you.md) to the people invited.
4. The Business analyst opens `kpi-intake-form.html` in a browser, or `kpi-intake-form.xlsx` in Excel.
5. The Business analyst asks the questions of sections 1 to 6 in order and records each answer. Each question says who answers it and why it is asked, and shows an example answer.
6. Where a question offers a list, choose from the list. If the right answer is not there, choose "Not in the list". The form then says what happens next and who does it, and gives a button that opens the smaller form.
7. Leave a question that does not apply. The HTML form hides it. In the workbook, the "Asked of" column gives each question's rule.
8. Save the answers. In the HTML form, press "Save answers to file", which downloads a file such as `crack-spreads-pricing.kpi-intake.json`. Move it from the download folder to the shared folder, as "The shared folder" below says. In Excel, save the workbook under the KPI's name.
9. Run the check on the saved file, as "Check a filled form" shows. Settle what it lists.
10. The Data Owner reads the form and signs the definition. The Domain Owner confirms the domain.
11. Digital IT fills in section 7 in the same file. To go on in the HTML form, press "Load answers file" and choose the saved file.
12. The Architect runs the check again and signs last.

The HTML form keeps an unsaved draft in the browser, so a reload does not lose it. A draft that the form cannot read, or that lacks a form or a part of one, is not restored, in whole, and the form says so. The draft stays on that one machine and browser. The saved file is the record. "Clear this form" asks first, then empties the form in view. It changes no saved file.

Each section's line in the HTML form counts the required answers left, then the optional questions that have no answer. An answer that needs more text, such as the name of a missing step, counts as a required answer left until that text is there. A section whose answer routes the request shows "Routed" and the form the request goes to. The sign-off line counts only the signatures the form needs. The Domain Owner's second signature on the KPI form is needed only when the check finds a conflicting definition, and the form says so. The form holds the names of the other modules' terms, and whether each has a definition, but not the definitions. When the KPI's name is one of them, the form says so. When that term has a definition and question 2.2 has an answer, the form also counts that signature as needed until the check has run. The form cannot compare the two definitions, so it may ask for this signature when the check later finds them equal.

The request's number, date, requester and invited people are under "Request details" at the top of the form. That part closes to one line once it is filled. Each section's introduction is under "About this section".

The HTML form opens in the light theme. The theme list beside "Version" changes it to dark or to the system's setting, and the browser remembers the choice. A printed form is always light. In a narrow window or at a high zoom, a "View" list replaces the tabs and a "Sections" button opens the section list.

The interview for sections 1 to 6 takes about 65 minutes for a typical KPI:

| Section | What it settles | Questions | Asked for a typical KPI | Minutes |
|---|---|---|---|---|
| 1. The business area | The business area, the process, the step and the domain | 6 | 5 to 6 | 8 |
| 2. What the KPI means | One name and one meaning, what it counts and leaves out, and the strategic objective it serves | 5 | 5 | 13 |
| 3. The facts about it | How it is worked out, its unit, how often it is stated, its grain, its written source, who may see it, its status, its quality rule, its review and its thresholds | 13 | 12 to 13 | 17 |
| 4. Where it belongs | The kind of measure, by up to five yes or no questions | 9 | 4 to 6 | 6 |
| 5. Other names for it | Other names, and the measures it is mistaken for | 4 | 4 | 6 |
| 6. What it connects to | The roles that use it, its named owner and steward, other processes, value stream steps and the data product | 9 | 6 to 8 | 14 |
| Total | | 46 | about 39 | 64 |
| 7. Where the data lives (IT only) | The view or table that gives the values, and an API if there is one | 10 | 4 to 10 | 20 to 30 |

Section 7 takes Digital IT 20 to 30 minutes with no business person present.

## The shared folder

A team that works offline keeps its answers files in one shared folder with a fixed layout. [`how-to-use-the-form.html`](how-to-use-the-form.html) explains it to the people who use it. This command makes the folder `KPI-intake` in the place you name, here the release's top folder, and copies the two forms and the guide into it:

```powershell run=release-copy
python -m kpi_store.intake folders .
```

```text expect
made KPI-intake/the-form
made KPI-intake/1-in-progress
made KPI-intake/2-ready-for-check
made KPI-intake/3-checked
copied KPI-intake/the-form/kpi-intake-form.html
copied KPI-intake/the-form/kpi-intake-form.xlsx
copied KPI-intake/the-form/how-to-use-the-form.html
wrote KPI-intake/READ-ME.txt
KPI-intake is ready
```

| Folder | What it holds | Who puts a file in |
|---|---|---|
| `the-form` | The HTML form, the Excel form and the guide | The Architect, with this command |
| `1-in-progress` | Answers files that are still being filled | The Business analyst, after every save |
| `2-ready-for-check` | Answers files that are filled, and signed by the business | The Business analyst |
| `3-checked` | Complete answers files, each with the report of its check | The Architect |

An answers file keeps the name the form gives it, such as `crack-spreads-pricing.kpi-intake.json`. Run the command again after you rebuild the pack. It replaces the three files in `the-form` and changes nothing in the numbered folders.

## Check a filled form

The check reads an answers file or a filled workbook. It needs Python 3.11 or later. Reading a workbook also needs the `openpyxl` package.

```powershell run=scratch os=windows status-only
python -m pip install openpyxl rdflib
```

Run the check from the release's top folder. This is the check of the first shipped example:

```powershell run=release-copy
python -m kpi_store.intake check kpi-intake/examples/crack-spreads-pricing.json
```

```text expect
KPI intake check: Crack Spreads Pricing
Catalogue 1.2. Pick lists of KPI Store 1.1.

1. The business area
  Answered 5 of the 6 questions that apply.
  Nothing is missing.
...
Kind of measure: market indicator (decided by 4.3, test 3).

Routing
  For the Architect: 6.7 is "Yes". The series need modelling in the market-data module. The Architect does that outside this form.

Checks against the ontology
  Same measure: the ontology already holds "Crack Spreads Pricing". This file is a shipped example of that measure, filled in as if it were new, so the match is expected.

Sign-off
...
Result: the intake is complete and signed.
This check changes nothing in the ontology. The Architect turns a complete KPI intake into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
```

A workbook is checked the same way:

```powershell run=release-copy
python -m kpi_store.intake check kpi-intake/examples/rm-margin-per-barrel.xlsx
```

```text expect
KPI intake check: R&M Margin per Barrel
...
Kind of measure: operational metric (decided by 4.6, test 5).
...
Result: the intake is complete and signed.
This check changes nothing in the ontology. The Architect turns a complete KPI intake into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
```

Add `--report` to also write the report beside the file, under the same name with `.check.txt` in place of `.json`. The report of a workbook also says "workbook" and names the form: `rm-margin-per-barrel.xlsx` gives `rm-margin-per-barrel.kpi-intake.workbook.check.txt`. So an answers file and a workbook of one KPI, and two forms of one workbook, never share a report. The Architect keeps that report with the file in `3-checked`.

The check prints, section by section, what is missing and which questions the rules rightly skipped. Then it prints the kind of measure, where an answer routes the request, what it found in the ontology, and who has signed. The last lines give the result.

| Exit status | Meaning |
|---|---|
| 0 | The form is complete and signed |
| 1 | Something is still to settle. The result lists each thing |
| 2 | A tool error: the file, the pack or the release could not be read, or the report could not be written. The message says which |

The check looks for these things in the ontology:

- **The same measure.** The name, or one of its other names, is already a measure, or the definition is a measure's definition. The form stops, and the request becomes a change to that measure. A name that is only close is shown for a person to judge. A shipped example matches its own measure on purpose, and the check expects that match only while the example's name (2.1) and definition (2.2) are unchanged.
- **The same name in another module.** The check asks you to consult Enterprise Data Governance and to record the date and the outcome in the sign-off block. If that term's definition differs, the Domain Owner decides between the two and signs.
- **Area and process.** The chosen process belongs to another business area than the answer to 1.1.
- **Values.** An answer names something that the lists do not hold, or a term the ontology marks as deprecated. An answer that names an entry your settings now hide still passes, with a note.
- **To add first.** An answer names an entry that your settings added and the ontology does not hold yet. The check tells the Architect to add it to its module with `HOW-TO-UPDATE.md` before the KPI is applied. It does not stop the intake from being complete.
- **Sign-off.** A signature needs a name and a date.

If a module was released after the pick lists were built, the check stops and asks you to rebuild them first.

## Where an answer routes the request

Three answers send the request somewhere before the KPI can be added. The form shows a notice when you give one, and the check lists them under "Routing".

| The answer | Where the request goes | Who acts |
|---|---|---|
| The domain in 1.5 is not active, or is not in the list | **Domain activation.** Fill in the "Domain activation" form | The Domain Owner answers and signs. The Architect signs the change, then turns the form into a proposal with `python -m kpi_store.propose` and applies it with `python -m kpi_store.apply` |
| The business area, the process, the step or a role is not in the list (1.1, 1.2, 1.3, 6.1, 6.3) | **Process map request.** Fill in the "Process map request" form. It is smaller, and it is not a domain activation | The Global Process Owner answers and signs. The Architect signs the change, then proposes and applies it with the same two commands. They add new roles and RACI entries. A new business area, process or step needs a release of `core`, which the commands cannot make, so it needs a specialist |
| The KPI is restricted (3.7) | **Review.** Bring Privacy, Security, Compliance and Risk into the request, and record the date and the outcome in the sign-off block | The Program manager |

The two smaller forms are tabs of the HTML form and sheets of the workbook. Each saves to its own answers file. "Load answers file" opens a file in the form it was saved from, whichever tab is open, and says which. It leaves out an answer under a number that form does not ask, and lists it. It refuses a file that is not an answers file, says what is wrong, and keeps the answers on the page.

Check a workbook's sheet by naming the form:

```powershell run=release-copy exit=1
python -m kpi_store.intake check kpi-intake/kpi-intake-form.xlsx --form domain-activation
```

```text expect
Domain activation check: (no name yet)
...
Result: not complete. 10 things to settle:
...
This check changes nothing in the ontology. The Architect turns a complete domain activation into a proposal with python -m kpi_store.propose <this file>, as HOW-TO-UPDATE.md says.
```

The blank form has eight required questions and two signatures, so the check lists ten things.

## The domain activation

The domain activation makes a domain of `settings.toml` active, so the KPI form offers it in question 1.5. The ontology holds no list of domains, so no module of the ontology changes.

The propose command reads D1 and D2 only. When D1 names a domain of the list, by its label or its id, the apply sets it to `active = true` and gives it the description of D2. When D1 names no domain of the list, the apply adds the domain at the end of the list, with the short key of D1 as its id, and makes it active. The other answers stay in the form's file. The propose command refuses a domain that is active already.

Who signs: the Domain Owner, then the Architect, last. The apply then rebuilds the forms, and the KPI form can go on. `HOW-TO-UPDATE.md`, "Activate a domain with the domain activation form", has the steps, with the example `examples/customer.domain-activation.json`.

## The process map request

The process map request adds new roles and their RACI entries to the `organization` module. Each RACI entry names a process that the process map holds already.

| No. | What the propose command reads |
|---|---|
| P1 | Each name must be a role: one of the organization module, or a new role of P5 |
| P5 | The text field gives each new role on a line of its own, as its name, a colon and one sentence on what it does. That sentence becomes the role's definition. A new role is a position |
| P6 | One RACI entry on each line: the process's number, the role and the level, with a comma between them, such as `CM 1.1.2, Business Analyst, consulted` |
| P7 | The documents, which the note of each new role cites |

The propose command refuses an answer to P2, P3 or P4, and a name in P1 that is not a role. Each of them asks for a new business area, process or step, which needs a release of `core`. The commands cannot make one, so the Architect takes that request to a specialist. It also refuses a new role that no line of P6 names, because the module holds a role only when a process names it.

Who signs: the Global Process Owner, then the Architect, last. `HOW-TO-UPDATE.md`, "Add roles and RACI entries with the process map request", has the steps, with the example `examples/sample-pricing-coordinator.process-map-request.json`.

## The term change

The fourth form changes a measure the ontology already holds. It is the "Term change" tab of the HTML form and the "Term change" sheet of the workbook, and it saves to its own answers file, `<measure>.term-change.json`. A new KPI uses the KPI form instead.

| No. | Question | Rule |
|---|---|---|
| T1 | Which measure do you want to change? (a list of the ontology's measures) | Required |
| T2 | What should the measure be called from now on? | Optional |
| T3 | What should its definition say from now on? | Optional |
| T4 | Which other names should it gain? | Optional |
| T5 | Which of its other names should it lose? | Optional |
| T6 | Which processes should the measure be linked to, in addition to the ones it has? (a list of the processes) | Optional |
| T7 | Which processes should the measure no longer be linked to? (a list of the processes) | Optional |
| T8 | Would every report and answer that used the old meaning still be correct? (yes, no, not sure) | Required |

The check refuses a term change that asks for no change, and a change that does not fit the measure: a new name or definition that is the one it has, an other name it has already, or an other name to remove that it does not have.

Who signs: the Data Owner, then the Architect, last. When the answer to T8 is "no" or "not sure", the change is a major, and the Ontology Owner signs too. The propose command copies each signature into the proposal's approval record, with the words the signature means on the form.

Check a term change as any other form: `python -m kpi_store.intake check <the file>`. Then the Architect turns it into a proposal and applies it, with the steps of "Change a measure with the term-change form" in [`HOW-TO-UPDATE.md`](../HOW-TO-UPDATE.md). Keep the filled form and its proposal in a folder outside the release folder.

## The reference item

The fifth form adds a new item to a module the ontology already holds. It is the "Reference item" tab of the HTML form and the "Reference item" sheet of the workbook, and it saves to its own answers file, `<item>.reference-item.json`. It adds two kinds of item: a system that a document names, and a table in Databricks that copies a table of a system (a replica).

| No. | Question | Rule |
|---|---|---|
| R1 | What is the new item called? (a table's full name: catalog.schema.table) | Required |
| R2 | What kind of item is it? (a list of six kinds) | Required |
| R3 | What does the system do? | Required for a system |
| R4 | What other names or short forms do people use for the system? | Optional, for a system |
| R5 | What kind of system is it? (application, office tool or working document) | Required for a system |
| R6 | Which document names the system? (a list of the documents the system module cites) | Required for a system |
| R7 | Which other documents does the description of the system rest on? (the same list) | Optional, for a system |
| R8 | Which system's table does the table copy? (a list of the systems) | Required for a table |
| R9 | Which document records the table? (a list of the documents that record the module's tables) | Required for a table |

Four kinds in R2 route the form to "needs a specialist", and the form says why:

- A table or a view that Databricks builds from other tables is a data product. It needs its kind, the test that decided it, the reason and its lineage.
- A source document changes two modules: the one that cites it, and the integration module, which gives it its evidence tier.
- A role comes from the RACI lists of the process map. It starts with the process map request.
- A data product of the catalog comes from the portfolio file of the process authority.

The check also refuses an item that does not fit the ontology: a name or an other name that a system has already, a name with no letter or digit, an other name with a semicolon, and a table whose name is not a full name of the sandbox or is one the ontology holds.

Who signs: the Data Owner, then the Architect, last. A new item is always a minor, so the Ontology Owner does not sign.

Check a reference item as any other form: `python -m kpi_store.intake check <the file>`. Then the Architect turns it into a proposal and applies it, with the steps of "Add a system or a table with the reference-item form" in [`HOW-TO-UPDATE.md`](../HOW-TO-UPDATE.md).

## What happens after

For a KPI form:

1. The Architect reads [`for-the-architect.md`](for-the-architect.md), which says what each answer feeds.
2. The Architect turns the form into a proposal with `python -m kpi_store.propose <the file>` and applies it with `python -m kpi_store.apply <the proposal folder>`, with the steps of "Add a KPI with the KPI intake form" in [`HOW-TO-UPDATE.md`](../HOW-TO-UPDATE.md). One proposal holds every module the form changes: the KPI's name, definition, other names and links as KGCL lines in `change.kgcl`, and the text facts that KGCL cannot write, such as how it is worked out, in `facts.csv`. It covers the `kpi` module and the KPI's population (2.3, 2.4), its value stream steps (6.3 to 6.5), the view that gives its values and the assistant that answers from it (6.6, 7.1, 7.8), and a sentence back in the scope note of each measure it is mistaken for (5.2). The apply releases each changed module and rebuilds this pack, so that the lists offer the new KPI.
3. Two answers stay in the form's file, and the proposal's `summary.txt` says so: the market series of 6.7, which the form does not collect, and 7.7, for which the ontology has no property yet.
4. The propose command refuses a form whose roles in 6.1 are not planning personas; whose 3.5 names more than one document, or one that 3.5 does not offer and `kpi/measure-sources.csv` does not hold; whose 2.4 has no 2.3; whose 6.3 names a step the ontology does not hold; whose 7.1 is a view the ontology does not hold or a table that is not a metric view; whose 6.6, when 7.1 names a view, is not that view's data product or is one the ontology does not hold; whose 7.8 is an assistant the ontology does not hold, or is given when 7.1 names no view; or whose name or other names a measure has already. When the document of 3.5 has no row in `kpi/measure-sources.csv` yet, the apply adds one, with the document's title in the ontology.
5. Keep the filled form. It holds the signers' names and the answers that the ontology has no place for.

Keep your organization's filled forms in the shared folder, as "The shared folder" above says. A client's filled form does not belong in the release folder.

## Change the form

Three files are yours to edit. After any change, rebuild.

- `settings.toml` holds the role titles and definitions, the domain list, the answers to "who may see it", the statuses, and what your organization hides from or adds to the ontology's lists. Change a title or a definition there and keep the `id`.
- `catalogue.toml` holds the questions. Its first lines explain the file. You can change any text, a rule, a time estimate or the sign-off block. A new question needs an `id` that no other question has.
- `examples/examples.toml` names the measures that the two examples copy.

The Architect, or whoever maintains the form, edits `settings.toml`. The business users never do. Edit it when a role title or a definition changes, when the domain list changes, or when an entry of a list is to be hidden or added. Then run `python -m kpi_store.intake build`, and copy the new form to the shared folder with `python -m kpi_store.intake folders <place>`, as "The shared folder" above shows.

A question takes its list from one of three places, which its `source` names:

| `source` | Where the list is |
|---|---|
| A plain name, such as `"measures"` | The ontology. The build reads it from the release packages |
| `"choices:<name>"` | `catalogue.toml`. A short list that is the same in every organization, such as yes and no |
| `"settings:<name>"` | `settings.toml`. A list your organization sets for itself |

To replace the example domain list, edit the `[[list.domains]]` entries of `settings.toml`. Each domain has an `id`, a `label`, a one-line `description` of the data it covers, and `active`. This is one entry of the example list:

```toml excerpt=kpi-intake/settings.toml
[[list.domains]]
id = "market-price"
label = "Market Price"
description = "Prices set outside the company: crude and product benchmarks, differentials and crack spreads."
active = true
```

A domain with `active = false` stays in the list, marked "not active". Choosing it routes the request to domain activation. The route is in `catalogue.toml`, on question 1.5:

```toml excerpt=kpi-intake/catalogue.toml
  [[question.route]]
  when = "@inactive"
  outcome = "domain-activation"
  notice = "This domain is not active yet. The KPI cannot be added until the domain is activated."
```

### Hide or add an entry of one of the ontology's lists

Four lists come from the ontology: `sources` (question 3.5), `roles` (6.1), `data-products` (6.6) and `systems` (7.4). A table `[pick_list.<name>]` in `settings.toml` says what your organization hides from a list and what it adds. The ontology is not changed. This is the table for the roles as shipped. It hides one role and adds one that the ontology does not hold yet:

```toml excerpt=kpi-intake/settings.toml
[pick_list.roles]
hide = ["Black Oil Manager"]

[[pick_list.roles.add]]
id = "value-chain-optimization-director"
label = "Value Chain Optimization Director"
```

| Key | What it does |
|---|---|
| `hide` | The forms do not offer these entries. Name each by its label, as the ontology gives it, by its id, or by the last part of its id |
| `hide_tiers` | For `sources` only: hides every source of these evidence tiers |
| `keep_only` | The opposite of `hide`: the forms offer only these entries. A list uses `keep_only`, or `hide` and `hide_tiers`, never both |
| `labels` | The label the forms and the check show for an entry, in place of the ontology's. The answers file still keeps the entry's id, and a workbook filled under the earlier label still reads |
| `add` | An entry with an `id` and a `label`. The forms offer it, marked "new, not yet in the ontology" |

After the build, [`for-the-architect.md`](for-the-architect.md) shows each list as the forms offer it: how many entries it offers, how many it hides, and what it adds. This is its line on what your settings add to the roles list:

```markdown excerpt=kpi-intake/for-the-architect.md
- `roles` adds: Value Chain Optimization Director. Each is offered with the mark "new, not yet in the ontology". When a form names one, the check tells you to add it to the `organization` module before you apply the KPI.
```

A hidden entry stays known. An answers file that already holds it still passes the check, with the note "hidden in this organization's settings". When a form names an added entry, the check tells the Architect to add it to the ontology first. The build stops when a name under `hide` or `keep_only` matches no entry, so a misspelt name cannot go unnoticed. It also stops when `add` names an entry that `hide` names, when an added entry matches more than one entry, or when two added entries share a label.

When the ontology has gained an added entry under the same label, rebuild and leave the entry under `add` for now. The forms then offer the ontology's entry only. An answer that a form in progress saved under the added entry is read as the ontology's entry, and the check says "is now in the ontology; the answer was read as that entry". `for-the-architect.md` names each such entry. Remove it from `add` once no form in progress uses it. The entry is matched by its label, by the label the ontology gives it when your `labels` table shows it under another, or by the last part of its id. When the list uses `keep_only`, add the entry's name there to offer it; until then it is hidden, and saved answers are still read.

One rule reads every saved answer, in an answers file, a browser draft and a workbook: a saved value names an entry when it is the entry's id, an id your settings once added it under, its label of today or a label it had before, with or without the mark of a hidden or a new entry.

Question 6.1 still has the option "A role that is not in the list", which sends the request to a process map request. Use `add` for a role your organization has already decided on, and that option for a role the interview finds.

The two examples use the domains `market-price` and `financial-performance`. When you replace the list, also change the two `"1.5"` lines in `examples/examples.toml` to domains of your own.

Rebuild from the release's top folder. The build needs the `rdflib` and `openpyxl` packages. On the release as received it has nothing to write:

```powershell run=release-copy
python -m kpi_store.intake build
```

```text expect
the intake pack is current; nothing was written
```

After a change it prints one line for each file it wrote. It stops with the reason when a file is wrong, for example when a rule names a question that does not exist.

The build writes only inside the pack folder it is given, which is `kpi-intake` unless you name another with `--pack`. It does not follow a link there. If a generated file or the `examples` folder is a link, the build stops and names it, and `--check` does the same.

Rebuild after every release of a module too, because the lists come from the newest packages. The cut tool (`python -m kpi_store.cut`) runs this build itself, so after a correction the pack is already current. To see whether the pack is current without writing anything, add `--check`:

```powershell run=release-copy
python -m kpi_store.intake build --check
```

```text expect
the intake pack is current
```

Two builds of the same files write the same bytes for every text file. A workbook's file format stores the time of writing, so the build compares a workbook by its content: the sheet names, every cell and the dropdowns. It leaves a workbook alone when the content is current.

## The answers file

"Save answers to file" writes one JSON file for one form. [`answers.schema.json`](answers.schema.json) gives its shape. This is the start of the first example:

```json excerpt=kpi-intake/examples/crack-spreads-pricing.json
{
  "format": 1,
  "form": "kpi-intake",
  "catalogue_version": "1.2",
  "kpi_name": "Crack Spreads Pricing",
```

`answers` holds each answer under its question's number. A question with several answers holds a list. A chosen item is stored by its id, which for a list of the ontology is the term's IRI. The id of an entry that `settings.toml` adds starts with `new:`. The extra text of a question is under the number with `.detail`, such as `3.5.detail`. `sign_offs` holds each signer's name and date, and `consulted` holds the date and outcome of each consultation.

In the workbook, column G of each sheet is hidden and names each row. The check finds the answers by it, so do not delete it.

## The two examples

Each example is a measure the ontology already holds, filled in as if it were new. The build reads every answer it can from the ontology, word for word. The few answers that the ontology does not hold start with "Illustration:", and each example's comment lists them. The signer names are placeholders.

To start a new KPI from an example, change its name and its definition. The check then treats the file as a new request. A file that keeps an example's definition under a new name, or its name with a new definition, is stopped as the same measure.

- Crack Spreads Pricing is a market indicator. The third question of section 4 decides its kind, so the rest are skipped. It has a view, a data product and two value stream steps.
- R&M Margin per Barrel is an operational metric and a KPI candidate. It answers all the questions of section 4. The ontology names no role, no data product and no view for it.

To see an example in the HTML form, press "Load answers file" and choose its `.json` file.

## Test the form in a browser

`scripts/check.sh` tests the catalogue, the check and the build. It does not open a browser. After you change `kpi_store/intake/form.html` or the catalogue, run the browser check from the release's top folder. It needs `uv`, a network connection the first time (`uv` fetches the `playwright` package) and an installed Google Chrome or Microsoft Edge. It downloads no browser and takes about 15 seconds.

```powershell run=slow
uv run --quiet --no-project --with playwright==1.65.0 python kpi_store/intake/browser_check.py
```

```text expect
intake  1 load         pass
intake  2 fill         pass
intake  3 narrow list  pass
intake  4 conditional  pass
intake  5 routing      pass
intake  6 save         pass
intake  7 load file    pass
intake  8 draft        pass
intake  9 phone        pass
intake  10 theme       pass
intake  11 next step   pass
intake  12 bad file    pass
intake  13 other form  pass
intake  14 detail      pass
intake  15 conflict    pass
intake  16 bad draft   pass
intake  17 hidden      pass
intake  18 added       pass
intake  19 new fields  pass
intake  20 guide       pass
intake  21 alias       pass
the intake form passed all 22 proofs
```
