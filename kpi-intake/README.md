# KPI intake pack

Start here when the business wants a new KPI in the KPI Store. The pack holds the form that collects what the ontology needs for one KPI, a check that says whether a filled form is complete, and two filled examples.

The pack does not change the ontology. A complete, signed form goes to the Architect, who adds the KPI by hand with the release steps of [`HOW-TO-UPDATE.md`](../HOW-TO-UPDATE.md). Commands that propose and apply the change from a form are planned for a later release.

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
py -m kpi_store.intake folders .
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
py -m pip install openpyxl rdflib
```

Run the check from the release's top folder. This is the check of the first shipped example:

```powershell run=release-copy
py -m kpi_store.intake check kpi-intake/examples/crack-spreads-pricing.json
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
This check changes nothing in the ontology. The Architect applies a complete intake by hand, with HOW-TO-UPDATE.md.
```

A workbook is checked the same way:

```powershell run=release-copy
py -m kpi_store.intake check kpi-intake/examples/rm-margin-per-barrel.xlsx
```

```text expect
KPI intake check: R&M Margin per Barrel
...
Kind of measure: operational metric (decided by 4.6, test 5).
...
Result: the intake is complete and signed.
This check changes nothing in the ontology. The Architect applies a complete intake by hand, with HOW-TO-UPDATE.md.
```

Add `--report` to also write the report beside the file, under the same name with `.check.txt` in place of `.json`. A workbook holds three forms, so its report also names the form: `rm-margin-per-barrel.xlsx` gives `rm-margin-per-barrel.kpi-intake.check.txt`. The Architect keeps that report with the file in `3-checked`.

The check prints, section by section, what is missing and which questions the rules rightly skipped. Then it prints the kind of measure, where an answer routes the request, what it found in the ontology, and who has signed. The last lines give the result.

| Exit status | Meaning |
|---|---|
| 0 | The form is complete and signed |
| 1 | Something is still to settle. The result lists each thing |
| 2 | The file could not be read |

The check looks for these things in the ontology:

- **The same measure.** The name, or one of its other names, is already a measure. The form stops, and the request becomes a change to that measure. A name that is only close is shown for a person to judge.
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
| The domain in 1.5 is not active, or is not in the list | **Domain activation.** Fill in the "Domain activation" form | The Domain Owner answers and signs. The Architect signs the change |
| The business area, the process, the step or a role is not in the list (1.1, 1.2, 1.3, 6.1, 6.3) | **Process map request.** Fill in the "Process map request" form. It is smaller, and it is not a domain activation | The Global Process Owner answers and signs. The Architect signs and proposes the change to the process map |
| The KPI is restricted (3.7) | **Review.** Bring Privacy, Security, Compliance and Risk into the request, and record the date and the outcome in the sign-off block | The Program manager |

The two smaller forms are tabs of the HTML form and sheets of the workbook. Each saves to its own answers file. "Load answers file" opens a file in the form it was saved from, whichever tab is open, and says which. It leaves out an answer under a number that form does not ask, and lists it. It refuses a file that is not an answers file, says what is wrong, and keeps the answers on the page.

Check a workbook's sheet by naming the form:

```powershell run=release-copy exit=1
py -m kpi_store.intake check kpi-intake/kpi-intake-form.xlsx --form domain-activation
```

```text expect
Domain activation check: (no name yet)
...
Result: not complete. 10 things to settle:
...
This check changes nothing in the ontology. The Architect applies a complete intake by hand, with HOW-TO-UPDATE.md.
```

The blank form has eight required questions and two signatures, so the check lists ten things.

When a domain activation is signed, set that domain to `active = true` in `settings.toml` and rebuild the forms. The KPI form can then go on. This step is the analyst's. The form keeps it out of the notice that the business reads, under "For the analyst".

## What happens after

1. The Architect reads [`for-the-architect.md`](for-the-architect.md), which says what each answer feeds.
2. The Architect adds the KPI to the `kpi` module's tables and follows "The release steps" in [`HOW-TO-UPDATE.md`](../HOW-TO-UPDATE.md). A KPI with a value stream step, a new view or a new source document also needs a release of `value-stream`, `data-product` or `integration`.
3. The Architect rebuilds this pack, so that the lists offer the new KPI.
4. Keep the filled form. It holds the signers' names and the answers that the ontology has no place for.

Keep your organization's filled forms in the shared folder, as "The shared folder" above says. A client's filled form does not belong in the release folder.

## Change the form

Three files are yours to edit. After any change, rebuild.

- `settings.toml` holds the role titles and definitions, the domain list, the answers to "who may see it", the statuses, and what your organization hides from or adds to the ontology's lists. Change a title or a definition there and keep the `id`.
- `catalogue.toml` holds the questions. Its first lines explain the file. You can change any text, a rule, a time estimate or the sign-off block. A new question needs an `id` that no other question has.
- `examples/examples.toml` names the measures that the two examples copy.

The Architect, or whoever maintains the form, edits `settings.toml`. The business users never do. Edit it when a role title or a definition changes, when the domain list changes, or when an entry of a list is to be hidden or added. Then run `py -m kpi_store.intake build`, and copy the new form to the shared folder with `py -m kpi_store.intake folders <place>`, as "The shared folder" above shows.

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

After the build, [`for-the-architect.md`](for-the-architect.md) shows the list as the forms offer it. This is its line for the roles: 64 of the 65 entries are offered, one is hidden, and one is added.

```markdown excerpt=kpi-intake/for-the-architect.md
| `roles` | 6.1 and P5 | 64 of 65 | 1 | Value Chain Optimization Director |
```

A hidden entry stays known. An answers file that already holds it still passes the check, with the note "hidden in this organization's settings". When a form names an added entry, the check tells the Architect to add it to the ontology first. The build stops when a name under `hide` or `keep_only` matches no entry, so a misspelt name cannot go unnoticed. It also stops when `add` names an entry that `hide` hides, or when two added entries share a label.

When the ontology has gained an added entry under the same label, rebuild and leave the entry under `add` for now. The forms then offer the ontology's entry only. An answer that a form in progress saved under the added entry is read as the ontology's entry, and the check says "is now in the ontology; the answer was read as that entry". `for-the-architect.md` names each such entry. Remove it from `add` once no form in progress uses it.

Question 6.1 still has the option "A role that is not in the list", which sends the request to a process map request. Use `add` for a role your organization has already decided on, and that option for a role the interview finds.

The two examples use the domains `market-price` and `financial-performance`. When you replace the list, also change the two `"1.5"` lines in `examples/examples.toml` to domains of your own.

Rebuild from the release's top folder. The build needs the `rdflib` and `openpyxl` packages. On the release as received it has nothing to write:

```powershell run=release-copy
py -m kpi_store.intake build
```

```text expect
the intake pack is current; nothing was written
```

After a change it prints one line for each file it wrote. It stops with the reason when a file is wrong, for example when a rule names a question that does not exist.

The build writes only inside the pack folder it is given, which is `kpi-intake` unless you name another with `--pack`. It does not follow a link there. If a generated file or the `examples` folder is a link, the build stops and names it, and `--check` does the same.

Rebuild after every release of a module too, because the lists come from the newest packages. To see whether the pack is current without writing anything, add `--check`:

```powershell run=release-copy
py -m kpi_store.intake build --check
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
the intake form passed all 21 proofs
```
