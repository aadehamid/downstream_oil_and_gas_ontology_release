# For the Architect: what each question feeds

This page maps the KPI intake form to the ontology. The business never sees it. It is built from `catalogue.toml`, so change the text there and run the build command of [the guide](README.md).

The check of a filled form changes nothing in the ontology. A complete KPI form becomes a proposal with the propose command, and the apply command adds it to the `kpi` module: [`HOW-TO-UPDATE.md`](../HOW-TO-UPDATE.md), "Add a KPI with the KPI intake form", has the steps. One proposal holds every module the form changes: `kpi` with the population, `value-stream` and `data-product`. The market series of 6.7 and the answer to 7.7 stay in the form's file, and the proposal's summary says so.

A complete domain activation and a complete process map request go through the same two commands. A domain activation sets the domain to active in `settings.toml`, since the ontology holds no list of domains: "Activate a domain with the domain activation form" in `HOW-TO-UPDATE.md` has the steps. A process map request adds new roles and their RACI entries to `organization`: "Add roles and RACI entries with the process map request" has the steps. A new business area, process or step needs a release of `core`, which the commands cannot make, and the propose command says so.

## Business area and domain

Two words are fixed in the intake. A business area is the function that runs a process, such as Commercial or Marketing. A domain is the data domain a KPI belongs to, such as Market Price, where the Domain Owner sits.

The ontology's property is named `core:businessDomain`, and its list is `core:BusinessDomain`. Despite the name, both hold the business area. Question 1.1 offers that list.

The ontology has no place for a KPI's domain yet, and holds no list of domains. Question 1.5 offers the list in `settings.toml`, and the answer stays in the form's file. A place in the ontology is planned for release 1.2.

## The sections and their technical names

| Section | Plain name | Technical name |
|---|---|---|
| 1 | The business area | domain identification |
| 2 | What the KPI means | the controlled vocabulary |
| 3 | The facts about it | the metadata |
| 4 | Where it belongs | the taxonomy (the measure list is flat, so the taxonomy is the measure's kind) |
| 5 | Other names for it | the thesaurus (question 5.2 feeds a typed property, because the ontology has no skos:related link) |
| 6 | What it connects to | the ontology (the typed links to roles, processes, value stream steps and data products) |
| 7 | Where the data lives (IT only) | the knowledge graph |
| D | Domain activation | a data domain that is not active yet |
| P | Process map request | a business area, process, step or role that the process map lacks |
| T | Term change | a change to a measure the ontology already holds |
| R | Reference item | a new system or a new table in a module that the ontology already holds |

## What each question feeds

### KPI intake

| No. | Question | Rule | Feeds |
|---|---|---|---|
| 1.1 | Which part of the business does this KPI belong to? | Required | No property on the measure. The check compares it with `core:businessDomain` of the process chosen in 1.3. |
| 1.2 | Which process in that area is this KPI about? | Required | Narrows 1.3. Becomes `kpi:informsProcess` when 1.3 has no answer. |
| 1.3 | At which step of that process do people use the number? | Optional | `kpi:informsProcess`. |
| 1.4 | What do people decide or do with the number at that step? | Required | A check on the step. The answer stays in the form's file. The ontology has no property for it. |
| 1.5 | Which domain does this KPI belong to? | Required | No property yet. The ontology has no place for a KPI's domain. The answer stays in the form's file. |
| 1.6 | Which other domains' data does it use? | Optional | No property yet. The answer stays in the form's file. |
| 2.1 | What do you call this KPI? | Required | `skos:prefLabel`. The Architect derives `skos:notation` from it. |
| 2.2 | In one or two sentences, what does it measure? Please do not use the KPI's own name. | Required | `skos:definition`. |
| 2.3 | What does it count? | Optional | `pop:includes`. |
| 2.4 | What does it leave out? | Optional | `pop:excludes`. |
| 2.5 | Which business objective does this KPI help you track? Write "None stated" if no objective has been agreed. | Required | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). For a measure whose kind is KPI, question 4.6 names the document that records the objective. |
| 3.1 | How is it worked out, in words? What is divided by what, or taken from what? | Required if 4.1 is not "no" | `kpi:basis`. |
| 3.2 | What unit is it stated in? | Required if 4.1 is not "no" | Added to `kpi:basis`. The ontology has no unit list and no unit property. The answer also stays in the form's file. |
| 3.3 | How often do people receive this KPI, and which breakdowns do they need in the report? | Required if 4.1 is not "no" | `kpi:grain`. Despite the property's name, it holds how often the KPI is stated and its breakdowns. The grain of 3.8 has no property yet. |
| 3.4 | What do you compare it against? | Optional | `kpi:comparedAgainst`. |
| 3.5 | Where is this definition written down? Choose the document, then give its date and the page or section. | Required | `dcterms:source`, `dcterms:bibliographicCitation`, `pop:populationEvidence`. A new document also needs a tier in `authority/source-tiers.csv`, which the Architect assigns. |
| 3.6 | Does it already have an ID or a code in a report, a dashboard or a system? Write it, or write "no". | Optional | `skos:note`. The Architect assigns `dcterms:identifier`. |
| 3.7 | Who may see this KPI: anyone in the company, or only a restricted group? | Required | No property. The answer stays in the form's file. |
| 3.8 | What does one individual KPI value describe? Name its time period and the item or combination of items it covers. | Required if 4.1 is not "no" | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). `kpi:grain` holds the answer to 3.3. |
| 3.9 | What status has the Data Owner confirmed? Leave "Draft" selected until certification is confirmed. | Required | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). |
| 3.10 | What agreed data checks must pass before this KPI is used? Say what happens if a check fails. | Optional | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). |
| 3.11 | When should the Data Owner review this KPI? What agreed change would mean it should stop being used? | Optional | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). |
| 3.12 | What agreed limits call for attention or action? For each, give the condition, value, unit and action. Leave blank if none are agreed. | Optional | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). The closed shape forbids a value on a measure, so a threshold stays in the form's file. |
| 3.13 | When does each threshold start? Give its end date, or write "No end date". Use YYYY-MM-DD. | Required if 3.12 has an answer | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). |
| 4.1 | Is it a number with a way to work it out, a unit and a time period? | Required | "No" gives `kpi:measureKind` tracker or report, or not a measure when it is a request for a tool, with `kpi:classificationTest` 1. The form then skips 3.1 to 3.3 and 4.2 to 4.7. |
| 4.2 | Does it appear only when something happens, like a warning? | Required if 4.1 is "yes" | "Yes" gives kind alert, test 2. |
| 4.3 | Is its value set by an outside market or a published benchmark that the business cannot influence? | Required if 4.2 is "no" | "Yes" gives kind market indicator, test 3. |
| 4.4 | Is it worked out from market prices and the planning model, to start or to rank a decision, with no target? | Required if 4.3 is "no" | "Yes" gives kind decision-support indicator, test 3. |
| 4.5 | Does it compare actual results, or a plan, with a plan, a forecast, an earlier plan or history, for one period? | Required if 4.4 is "no" | "Yes" gives kind plan-variance diagnostic, test 4. |
| 4.6 | Has the business formally chosen this measure to track that objective, with a target and an accountable owner? | Required if 4.5 is "no" | "Yes" gives kind KPI, test 5, and a `KPI-` identifier. The document goes to `dcterms:bibliographicCitation`. "No" gives kind operational metric, test 5. The ontology never records a target's value. Thresholds stay in the form's file (3.12). |
| 4.7 | If it is not a KPI today, is it a strong candidate to become one? | Required if 4.6 is "no" | `kpi:kpiCandidate`. False for every kind but operational metric. |
| 4.8 | In one or two sentences, why does it belong to that kind? | Required | `kpi:classificationReason`. |
| 4.9 | Which topic, or family of KPIs, does it belong to, if any? | Optional | No property. The measure list is flat. The answer stays in the form's file. |
| 5.1 | What other names or short forms do people use for it? | Optional | `skos:altLabel`, one for each name. |
| 5.2 | Which measures do people mistake it for? | Optional | `kpi:notToBeConfusedWith`. |
| 5.3 | How does it differ from each of those? | Required if 5.2 has an answer | `skos:scopeNote`. Each measure named in 5.2 also needs a sentence back in its own scope note. |
| 5.4 | Does the company publish this number, or one close to it, outside the company? Which one? Write "none" if it does not. | Required | `kpi:publicCounterpart`. |
| 6.1 | Which roles use this number? | Required | `kpi:usedBy`. |
| 6.2 | Is the number used in any other process? Choose each one, or leave this empty. | Optional | More `kpi:informsProcess` links. |
| 6.3 | Which steps of a value stream use it? | Optional | One `vs:MeasureLink` for each step, with `vs:measure`. |
| 6.4 | For each of those steps, how does the step use the number: as an input, as an outside reference to compare against, or as a result it tracks? | Required if 6.3 has an answer | `vs:relationship`: informs, benchmarks or measures performance. |
| 6.5 | For each of those steps, what document tells us so? | Required if 6.3 has an answer | `dcterms:bibliographicCitation` on the link, which the shape requires. |
| 6.6 | Which data product gives this number? | Optional | Tells Digital IT where to look for the view of 7.1. `dcterms:isPartOf` of the view in 7.1. `con:publishesMeasure` if a catalog row publishes the KPI. |
| 6.7 | Is the number published as several named series, such as one for each region or market? | Asked only when the kind is market indicator | `mkt:seriesOf`, `mkt:priceOf`, `mkt:enumerates` in `market-data`. Not filled from this form. |
| 6.8 | Who is accountable for this KPI's meaning and the action taken on it? Give their position and business area, or their name. | Required | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). The ontology records roles and never a person's name. |
| 6.9 | Who maintains this KPI's definition and handles questions about its data? Give their position and business area, or their name. | Required | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). The ontology records roles and never a person's name. |
| 7.1 | Which view or table gives this KPI's values? Give the full name. | Required | `dp:servesMeasure` (the `serves_measures` column of `data-product/pricing/tables.csv`). |
| 7.2 | If it is not in the list: what is its full name, and which layer is it in? | Required if 7.1 is "not in the list" | A new row in `tables.csv`: `dp:fullName`, `dp:layer`, `skos:prefLabel`. |
| 7.3 | Which tables or views is it built from? | Required if 7.1 is "not in the list" | `prov:wasDerivedFrom` (`lineage.csv`). |
| 7.4 | Which source systems does its data come from? | Required if 7.1 is "not in the list" | `dp:dependsOnSystem`, or `dp:copiesSystem` for a replica. |
| 7.5 | Is it a foundational or a derived data product, and why? | Required if 7.1 is "not in the list" and the layer is not replica | `dp:dataProductKind`, `dp:classificationTest`, `dp:classificationReason`. |
| 7.6 | Is it in a sandbox or in production? | Required if 7.1 is "not in the list" | `dp:sandbox`. |
| 7.7 | Which measure or column of the view holds the KPI, and with what filter? | Optional | No property today. Release 1.1 lists such a link as a proposal that needs a minor version of `data-product`. |
| 7.8 | Which AI assistant or report answers from this view? | Optional | `prov:used` from a `prov:SoftwareAgent` in `data-product`. |
| 7.9 | What shows that these facts are right: a discovery run, a design document or a workspace export, and of what date? | Required if 7.1 is "not in the list" | `dcterms:source` on the platform table, which the shape requires. A new source needs a tier in `integration`. |
| 7.10 | Besides the view or table in 7.1, is there an API or file feed that supplies these values? Give its name and where its documentation is kept. Leave blank if none. | Optional | Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md). |

### Domain activation

| No. | Question | Rule | Feeds |
|---|---|---|---|
| D1 | What is the domain called? | Required | The domain's name in settings.toml. The ontology has no place for a domain yet. |
| D2 | In two or three sentences, what data does the domain cover, and what does it leave to other domains? | Required | The domain's description in settings.toml. |
| D3 | Who is the Domain Owner? Give the position. | Required | Kept in the form's file. |
| D4 | Who are the Data Owners, and which part of the domain's data does each own? Write one line for each. | Required | Kept in the form's file. |
| D5 | Who are the Data Stewards? Write one line for each. | Required | Kept in the form's file. |
| D6 | Which data products belong to the domain? | Optional | `dp:DataProduct` terms in `data-product`. A new one needs a release of that module. |
| D7 | Which business areas does the domain serve? | Required | Kept in the form's file. The business areas are `core:BusinessDomain` concepts. |
| D8 | Which processes does the domain serve? | Optional | Kept in the form's file. |
| D9 | Which KPIs should be added first? | Required | One KPI intake form for each. |
| D10 | What is the written basis for the domain: a charter or a decision? Give the document and its date. | Required | Kept in the form's file. |

### Process map request

| No. | Question | Rule | Feeds |
|---|---|---|---|
| P1 | What is missing from the process map: a business area, a process, a step or a role? Name each one. | Required | A proposal for the process map, then a `core` release: `skos:prefLabel`. |
| P2 | For each missing process or step, which process in the map sits above it? | Optional | `skos:broader` and `core:businessDomain`. |
| P3 | What is the purpose of each missing process or step, in one sentence? | Optional | `skos:definition`. |
| P4 | What are the steps of each missing process, in order? | Optional | Lower levels of the process map, `core:precedes`. |
| P5 | Which roles work in these processes? | Optional | `org:Role` in `organization`, with `skos:prefLabel` and `skos:definition`. |
| P6 | For each process, which role does the work, which answers for it, which is consulted, and which is informed? Write one line for each: the process's number, the role and one of responsible, accountable, consulted or informed, with a comma between them, such as "CM 1.1.2, Business Analyst, consulted". | Optional | `orgx:ResponsibilityAssignment` with `forProcess`, `assignedRole`, `raciLevel`. |
| P7 | Which documents describe them: a process manual, a policy, a published report? | Required | `dcterms:source` IRIs and their tiers in `authority/source-tiers.csv`. |

### Term change

| No. | Question | Rule | Feeds |
|---|---|---|---|
| T1 | Which measure do you want to change? | Required | The measure the KGCL lines are about: `measure:<its short key>`. |
| T2 | What should the measure be called from now on? Leave this empty to keep its name. | Optional | A rename: `skos:prefLabel`. |
| T3 | What should its definition say from now on? Leave this empty to keep the definition. | Optional | A changed definition: `skos:definition`. |
| T4 | Which other names should it gain? | Optional | A new other name: `skos:altLabel`. |
| T5 | Which of its other names should it lose? Write each one as the ontology holds it. | Optional | A removed other name: `skos:altLabel`. |
| T6 | Which processes should the measure be linked to, in addition to the ones it has? | Optional | A new link: `kpi:informsProcess`. |
| T7 | Which processes should the measure no longer be linked to? | Optional | A removed link: `kpi:informsProcess`. |
| T8 | Would every report and answer that used the old meaning still be correct? | Required | The route of the proposal. The answer can only raise the route that the changes suggest, never lower it. |

### Reference item

| No. | Question | Rule | Feeds |
|---|---|---|---|
| R1 | What is the new item called? | Required | The new item and its name: `skos:prefLabel` (the KGCL line `create node`). The item's short key is made from it. |
| R2 | What kind of item is it? | Required | The module that holds the item: system for a system, data-product for a table. |
| R3 | What does the system do? Say it in one or two sentences, without repeating its name. | Required if R2 is "a system that a document names: an application, an office tool or a working document" | `skos:definition` (the KGCL line `add definition`). |
| R4 | What other names or short forms do people use for the system? | Optional if R2 is "a system that a document names: an application, an office tool or a working document" | `skos:altLabel`, one for each name. |
| R5 | What kind of system is it? | Required if R2 is "a system that a document names: an application, an office tool or a working document" | `sys:systemKind`. |
| R6 | Which document names the system? | Required if R2 is "a system that a document names: an application, an office tool or a working document" | `sys:namedBy`, and `dcterms:source`. |
| R7 | Which other documents does the description of the system rest on? | Optional if R2 is "a system that a document names: an application, an office tool or a working document" | More `dcterms:source` links. |
| R8 | Which system's table does the table copy? | Required if R2 is "a table in databricks that copies a table of a system (a replica)" | `dp:copiesSystem`. The table is a replica: `dp:layer` is `layer:replica`. |
| R9 | Which document records the table? | Required if R2 is "a table in databricks that copies a table of a system (a replica)" | `dcterms:source`. |

## The facts one new KPI needs, and the questions that supply them

| Fact | Property or pattern | Module | Status | Supplied by | Note |
|---|---|---|---|---|---|
| F1 Name | `skos:prefLabel`, exactly one, English | kpi | required | 2.1 |  |
| F2 Definition | `skos:definition`, exactly one | kpi | required | 2.2 |  |
| F3 Short key | `skos:notation`, exactly one | kpi | required | Derived from 2.1 | Derived from the name. |
| F4 Place in the measure list | `skos:inScheme` and `skos:topConceptOf` `kpi:Measures`, `rdf:type` | kpi | required | Derived | Fixed values. |
| F5 Kind of measure | `kpi:measureKind`, exactly one of eight | kpi | required | 4.1, 4.2, 4.3, 4.4, 4.5, 4.6 | Derived from the first answer that decides. |
| F6 Which test decided the kind | `kpi:classificationTest`, 1 to 5 | kpi | required | 4.1, 4.2, 4.3, 4.4, 4.5, 4.6 | Derived. |
| F7 Why it has that kind | `kpi:classificationReason`, exactly one | kpi | required | 4.8 |  |
| F8 KPI candidate | `kpi:kpiCandidate`, true or false. Only an operational metric can be true | kpi | required | 4.7 | False unless the kind is operational metric. |
| F9 Source | `dcterms:source`, at least one IRI. The IRI needs a row in `authority/source-tiers.csv` | kpi and integration | required | 3.5 | A new source document needs a row in `kpi/measure-sources.csv` and an evidence tier. |
| F10 Identifier | `dcterms:identifier`, `KPI-nnnn` or `OPM-nnnn`. Required unless the kind is tracker or report, or not a measure | kpi | required | Derived | The next free `KPI-` or `OPM-` number. |
| F11 Where the source says it | `dcterms:bibliographicCitation`, at most one | kpi | usual | 3.5, 4.6 |  |
| F12 Process it informs | `kpi:informsProcess`, any number | kpi, pointing into core | usual | 1.2, 1.3, 6.2 |  |
| F13 Roles that use it | `kpi:usedBy`, any number | kpi | usual | 6.1 | The kpi builder accepts only the four planning personas today. |
| F14 How it is formed | `kpi:basis`, at most one | kpi | usual | 3.1, 3.2 |  |
| F15 Grain | `kpi:grain`, at most one. Not allowed on a tracker, report or non-measure | kpi | usual | 3.3 |  |
| F16 What it is compared against | `kpi:comparedAgainst`, at most one | kpi | usual | 3.4 |  |
| F17 Closest published measure | `kpi:publicCounterpart`, at most one | kpi | usual | 5.4 |  |
| F18 Other names | `skos:altLabel`, any number | kpi | optional | 5.1 |  |
| F19 What it is not | `skos:scopeNote`, at most one | kpi | optional | 5.3 |  |
| F20 Measures it is mistaken for | `kpi:notToBeConfusedWith`, any number | kpi | optional | 5.2 |  |
| F21 What it counts and leaves out | `pop:includes`, `pop:excludes`, `pop:populationEvidence` | kpi | optional | 2.3, 2.4, 3.5 |  |
| F22 An ID another asset gives it | `skos:note`, at most one | kpi | optional | 3.6 |  |
| F23 Change history | `skos:changeNote` | kpi | optional | Derived | Derived from the request number. |
| F24 Value stream step that uses it | A `vs:MeasureLink` on a step, with `vs:measure`, `vs:relationship` and a `dcterms:bibliographicCitation` | value-stream | optional | 6.3, 6.4, 6.5 | The value-stream builder reads the link from the process authority's files, which change by proposal. |
| F25 The view that gives its values | `dp:servesMeasure` from a platform table to the measure | data-product | optional | 7.1 |  |
| F26 Facts about that view | `dp:fullName`, `dp:layer`, `prov:wasDerivedFrom`, `dp:dependsOnSystem`, `dcterms:isPartOf`, `dp:sandbox`, `dp:dataProductKind` with its test and reason, `dcterms:source` | data-product | optional | 6.6, 7.2, 7.3, 7.4, 7.5, 7.6, 7.8, 7.9 | Needed only when the view is new. |
| F27 The data product that publishes it | `con:publishesMeasure` | integration | optional | 6.6 | The ontology holds no instance today. |
| F28 Market series behind it | `mkt:seriesOf`, `mkt:priceOf`, `mkt:enumerates`. Market indicators only | market-data | outside this form | 6.7 | Not supplied. Question 6.7 only detects the need. |
| F29 The metric view that computes it, as built | `tg:implements` | technical-graph | outside this form | Derived | The discovery finds it. It is a record in the technical graph, not in the ontology. |

## The kind of measure

Section 4 asks its tests in order. The first answer in this table that matches decides the kind.

| Question | Answer | Kind | Test |
|---|---|---|---|
| 4.1 | no | tracker or report | 1 |
| 4.2 | yes | alert | 2 |
| 4.3 | yes | market indicator | 3 |
| 4.4 | yes | decision-support indicator | 3 |
| 4.5 | yes | plan-variance diagnostic | 4 |
| 4.6 | yes | KPI | 5 |
| 4.6 | no | operational metric | 5 |

## Facts with no place in the ontology yet

The form asks for some of these and keeps the answers in its own file. `KNOWN-OPEN-ITEMS.md` at the top of the release lists them too.

| Fact | Question | Note |
|---|---|---|
| The domain of a KPI | 1.5 | The ontology has no place for a KPI's domain, and holds no list of domains. The list is in settings.toml. A place in the ontology is planned for release 1.2. |
| The other domains whose data a KPI uses | 1.6 | The answer stays in the form's file. |
| The business area of a measure | 1.1 | The check compares the answer with the area of the chosen process. The answer stays in the form's file. |
| The decision the KPI supports | 1.4 | The ontology answers only with the process link. The answer stays in the form's file. |
| The unit, as a value of its own | 3.2 | The unit is words inside `kpi:basis`. The answer also stays in the form's file. |
| Who may see the KPI | 3.7 | The answer stays in the form's file and routes the request to the reviews. |
| The topic, or family, of the KPI | 4.9 | The measure list is flat. The answer stays in the form's file. |
| The measure or column of the view that holds the KPI, with its filter | 7.7 | It needs a minor version of `data-product` with a new property. |
| The strategic objective a measure serves | 2.5 | For a KPI, question 4.6 names the document that records the objective. The objective's own words stay in the form's file. |
| The grain, as a value of its own | 3.8 | `kpi:grain` holds how often the KPI is stated and its breakdowns (3.3). The answer stays in the form's file. |
| The status of a KPI: draft, certified or retired | 3.9 | The answer stays in the form's file. The status list is in settings.toml. |
| The quality rule of a KPI | 3.10 | The answer stays in the form's file. |
| When a KPI is reviewed and what retires it | 3.11 | The answer stays in the form's file. |
| The thresholds of a KPI | 3.12 | The closed shape forbids a value on a measure. Question 4.6 names the document that records a KPI's target. The thresholds stay in the form's file. |
| The dates from which the thresholds apply | 3.13 | The answer stays in the form's file. |
| The named owner of a KPI | 6.8 | For a KPI, question 4.6 names the document that records the accountable owner. The owner's title or name stays in the form's file. |
| The named steward of a KPI | 6.9 | The answer stays in the form's file. |
| An API or another access path to the KPI's values | 7.10 | The answer stays in the form's file. |
| The direction of a good value | Not asked | The form does not ask for it. |

## The lists your settings change

Four of the forms' lists come from the ontology. `settings.toml` says, under `[pick_list.<name>]`, what your organization hides from each and adds to each. The ontology is not changed. This table is rebuilt with the pack and shows each list as it stands.

The Architect, or whoever maintains the form, edits `settings.toml`. The business users never do. Edit it when a role title or a definition changes, when the domain list changes, or when an entry of a list is to be hidden or added. Then run `python -m kpi_store.intake build`.

| List | Questions | Offered | Hidden | Added |
|---|---|---|---|---|
| `sources` | 3.5 | 4 of 106 | 102 | None |
| `roles` | 6.1 and P5 | 64 of 65 | 1 | Value Chain Optimization Director |
| `data-products` | 6.6 and D6 | 13 of 49 | 36 | None |
| `systems` | 7.4 | 45 of 50 | 5 | SharePoint |

- `sources` offers only the 4 entries that `keep_only` names, and so hides the other 102.
- `sources` shows 2 entries under a label of your settings (`labels`): MPC Economics, 3-2-1 Crack Spread KPI Definition; Value Chain Optimization Decision Support and Visualization: the planning team's measure list. The answers file keeps each entry's id.
- `roles` hides: Black Oil Manager.
- `roles` adds: Value Chain Optimization Director. Each is offered with the mark "new, not yet in the ontology". When a form names one, the check tells you to add it to the `organization` module before you apply the KPI.
- `data-products` offers only the entries that `keep_only` names, and so hides: BP&A; Brand Data & Integration; DevSecOps; ES&S; Field Operations; Gathering & Compression; GIS; HES&S; HR; IT; Legal; Loss Control; Marine & Rail Ops; Measurement & Lab; Operations & Administration; Ops Intel; Ops Support; OT Communication Platform; OT Compute Platforms; OT Platform Development; OT Windows Platforms; Pipeline Ops & Integrity; Pipeline OT; Pipeline RA&S; Processing & Fractionation; Quality Assurance; Quality Assurance (Software); Reliability Center; Retail Payments; S&BD; SC; Service Management; Terminal Automation; Terminal Ops (IT); Terminal OT; Truck Ops.
- `systems` hides: Databricks; MS Excel; MS Outlook; MS PowerPoint; MS Teams.
- `systems` adds: SharePoint. Each is offered with the mark "new, not yet in the ontology". When a form names one, the check tells you to add it to the `system` module before you apply the KPI.

Keep the lists in step with the ontology:

- A hidden entry stays known. A form that already holds it still checks, with a note.
- A list with `keep_only` offers nothing new by itself. When a release of `data-product` adds a data product, the rebuild adds its name to the hidden entries above. Add the name to `keep_only` to offer it.
- A list with `hide` offers every new entry of the ontology as soon as the pack is rebuilt.
- A list uses `keep_only`, or `hide` and `hide_tiers`, never both.
- When you have added an entry to the ontology under the same label, rebuild. Leave the entry under `add` for now: the forms offer the ontology's entry only, and an answer that a form in progress saved under the added entry is read as the ontology's. The list above then names the entry. Remove it from `add` once no form in progress uses it. After that, such an answer no longer checks.
- The build stops when `add` names an entry that `hide` names, when an added entry matches more than one entry, or when two added entries share a label.
- One rule reads every saved answer: a saved value names an entry when it is the entry's id, an id your settings once added it under, its label of today or a label it had before, with or without the mark of a hidden or a new entry.
- `KNOWN-OPEN-ITEMS.md` lists the changes to the ontology that these settings stand in for.
