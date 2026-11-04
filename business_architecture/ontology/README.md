# Ontology — Downstream Process Map

The published home of the downstream process-map ontology build: the
playbook (the method), the acceptance
test (competency questions), and the reproducible build scripts with their outputs.

**Start here.** This README is the single entry point. Three documents, three
roles, and a fourth to read first if you are new (`epm-ontology-guide.html`, below the table):

| File | Role | Read it for |
|------|------|-------------|
| The `ontology` skill's guide (`skills/ontology/references/playbook.md`, the skills folder) | **Playbook**: a company-neutral method for building an ontology from scratch | Foundations, Steps 0 to 12, policies (§2), promoting provisional data (§3), standards (§4), soundness checks (§5), working agreements (§6), a worked example in a neutral domain (§7). *2026-10-25:* moved from this folder into the skill, which tests that it names no project's records, companies or paths (the decision of 2026-10-25) |
| `MODULES.md` | **Module guide**: the released modules and how they connect | What each module holds, the three kinds of content, each link between modules with a real example from the releases, and one walk across modules |

**Want the whole story?** The walkthrough tells it end to end: the business and its value streams, the gaps found in the processes and how each was filled or why it stays open, how the ontology was built from that, the stores, the technical graph, how the measures tie to both graphs, how they stay in step with Git, and the pricing demo, with 36 steps to rebuild it. Read it here as `epm-walkthrough.html`, or as the same page published (private; ask the decision owner for access). When the walkthrough changes, edit this file and publish it again. It sits above the documents here and points to them for depth:

| Your question | Read |
|---|---|
| What did we build, and how, end to end? | The walkthrough |
| How were the process definitions decided? | `business-process-architecture-playbook.md` |
| How do you build an ontology, for any domain? | The `ontology` skill's guide |
| How do you project an ontology into a graph store with nothing lost? | The `ontology-to-lpg` skill's playbook |
| What must the ontology be able to answer? | `competency-questions.md`, and the guide's list with each status |
| What does the finished ontology hold, and why these modules? | `epm-ontology-guide.html`, then `MODULES.md` |
| How do I load it into a store and query it? | `projection/ontology-stores-runbook.html` |
| How do I change the ontology, or add a module? | `epm-walkthrough.html`, "How to change the ontology" |
| How do I add a logical data model, such as an ER Studio export? | `epm-ontology-guide.html`, "Adding a logical model", for the design; `epm-walkthrough.html`, "Add a logical model", for the steps; the `ontology` skill's `references/logical-model.md` for the method |
| Why is something the way it is? | `../domain/decisions/` |
| What is still open on the ontology, and what do we need from the business? | `OPEN-ITEMS.md`, with the full wording in `business-closeout.md` |

The two skill playbooks stay company-neutral, so they name each other and the kinds of document a project keeps, and not these EPM files.

**New to the ontology?** Open `epm-ontology-guide.html` in a browser. It explains what the ontology is for, why it is split into modules, what each module holds and why, and follows one pricing measure, the crack spread, through every module, with diagrams and a query you can run. Its figures are a dated snapshot; `MODULES.md` and `scripts/epm_facts.py` stay the current reference.

Check the playbook's §2 Policies before making any modeling choice. The maintenance rule was decided on
2026-10-05 (the decision of 2026-10-05). The playbook was then rewritten as a
company-neutral method, and the amendment the decision of 2026-10-05 was decided on
2026-10-06: project decisions get a decision record, and the playbook changes only when the method changes.

For current figures (ledger, gate, taxonomy size, Phase 1 rows) and one row's
status, run `python3 scripts/epm_facts.py counts` or `row REL-xxxxx` from the repo
root.

## Modules

The ontology ships as modules, each released and versioned on its own. `core` is the process
map, and most other modules add one kind of thing and link it to core's processes. Four do not:
`market-data` links to `kpi`'s measures, `ref-mpc` holds company facts in the terms of
`organization` and `party`, `integration` holds rules about the other modules' links, and
`technical-graph` links what is built on a data platform to `data-product`, `kpi` and `system`.
`MODULES.md` shows each link with an
example quoted from the releases.

| Module | What it is for |
|---|---|
| `core` | The process map: processes as a hierarchy, the approved relationships between them and their evidence |
| `organization` | Roles, RACI assignments, and the control relationship between legal entities |
| `party` | The customer domain: the customer model, customer systems and data flows, and the customer lifecycle |
| `kpi` | What each measure means, never its value, with the population it counts |
| `data-product` | The data-product portfolio: segments, product lines and data products |
| `value-stream` | The value streams, as an overlay of steps that realize core processes |
| `system` | The systems, office tools and working documents the process map names |
| `lane` | The office lanes, and the processes the process map places in them |
| `market-data` | The recipes of market series, such as crack spreads, never their prices |
| `ref-mpc` | The company-specific facts: MPC and MPLX; the only module that is not company-neutral |
| `integration` | Rules across modules: which links certify (placement), which source wins (authority), and what consumers may bind and answer (consumer) |
| `technical-graph` | The vocabulary of what was built on the data platform, never the graph's records; it answers competency questions 45 to 50 |

*2026-11-02:* `technical-graph`, the twelfth module, is released as 1.0.0, which the subject matter expert approved (the decision of 2026-11-02).

*2026-11-02:* the `logical-model` module, which keeps logical data models exported from ER Studio and links their entities to `party`, `system` and `data-product`, has its machinery in `logical-model/` (the decision of 2026-11-02). Its first model, the customer logical model, ships in the release as `logical-model 1.0.0`, which the subject matter expert approved on 2026-11-02 (the decision of 2026-11-02, amendment); the release cut builds the package. The figures on this page do not count it. It answers competency questions 51 to 55 on a made-up example model.

For versions, what each module requires and triple counts, run
`uv run --with rdflib python scripts/epm_facts.py modules`. It also says what each release was built
from where its manifest records that ("built from (release manifest)"); for the other releases it
shows the source folders the builder packages today ("sources (builder today)"), which a later
change to the builder can move away from what the release was built from. For which processes have a RACI
assignment, a system, a KPI, a lane, a value-stream step or a data product, run
`uv run --with rdflib python scripts/epm_facts.py coverage` (see `--help` for other process sets).
The dated diagram "EPM ontology: modules and how they connect (2026-11-03)" shows module dependencies,
including the logical-model module added by the shared release cut: a link not included in this release.

## Contents

| Path | What |
|------|------|
| The `ontology` skill's guide | **Playbook** (the method, normative): policies, method, standards, soundness, working agreements, a neutral worked example; in the skills folder since 2026-10-25 (the decision of 2026-10-25) |
| `MODULES.md` | **Module guide**: each released module, how the modules connect, with examples quoted from the releases (tested by `scripts/test_modules_guide.py`) |
| `epm-ontology-guide.html` | **Ontology guide**, a standalone page for a person: why modules, each module and why it exists, the module map, and the crack-spread measure traced through every module, with diagrams |
| `step4/` | Step 4 working area: verb-predicate mapping, evidence gate, canonical facts, correction backlog (see `step4/README.md`) |
| `step4/evidence-discipline.md` | The approved Step 4 evidence discipline text, moved word for word from the playbook on 2026-10-05 |
| `../domain/decisions/` | Project decision records (the decision records) |
| `competency-questions.md` | The 55-question acceptance baseline (44 until 2026-11-02, when the technical-graph module's six were added: the decision of 2026-11-02; then 50 until the logical-model module's five were added the same day: the decision of 2026-11-02), tested by the Step 11 regression in `regression/` |
| `projection/` | Step 12: the pipeline that projects the ontology into Neo4j, its manifest and its last report (the decision of 2026-10-13) |
| `validation/` | Step 9 shapes run against the released modules: controlled values (the decision of 2026-10-13) |
| `provenance/` | The Step 6 definition-to-run pattern: the shapes a consumer's run must meet, an example run and tests (the decision of 2026-10-13) |
| `ref-mpc/` | The Step 5 reference instances for MPC: MPC, MPLX, MPC's control of MPLX, segments and refineries, from the FY2025 10-K (the decision of 2026-10-13); and MPC and MPLX as parties in the `party` module's terms, moved from `party/` on 2026-10-22 (the decision of 2026-10-21, the decision of 2026-10-22); released as 1.2.0 with the parties (the decision of 2026-10-22); and, since 2026-10-27, MPC's brands Marathon, ARCO and Tesoro as `party:Brand` individuals, released as 1.3.0 (the decision of 2026-10-27, amendment of 2026-10-27) |
| `kpi/` | The Step 7 kpi module: 41 measure definitions classified by kind (the decision of 2026-10-18), the measure-kind code list, planning personas and process links (the decision of 2026-10-18); released as 1.0.0 (`releases/kpi/1.0.0/`), approved by the decision owner, and 1.0.1, a patch naming the measure list's source (VCO DSV); 1.1.0 (`releases/kpi/1.1.0/`), a minor carrying the measure populations, with the measure shape closed (the decision of 2026-10-22) |
| `party/` | The Steps 5 to 7 `party` module, which owns the Customer domain's concepts: the decision owner's conceptual model of Customer as fifteen entity classes (17 with Person and Organization), party roles as dated nodes, twelve code lists including 14 roles and 14 customer classes with MPC's C1 to C8, and SHACL (the decision of 2026-10-21, the decision of 2026-10-21); the customer's 42 systems, 35 data flows and 275 Create and Enrich attributes, with four more code lists for them (the decision of 2026-10-21); the customer lifecycle, linked to core processes and systems (the decision of 2026-10-21); released as 1.0.0 on 2026-10-22 (the decision of 2026-10-22) *2026-10-26:* released as 1.1.0 (the decision of 2026-10-23), 1.2.0 (the decision of 2026-10-25) and 1.3.0, which defines 38 of its 42 customer systems (the decision of 2026-10-26); 1.4.0 matches 12 of them to the system module and rewords its one shape message with an apostrophe (the decision of 2026-10-26); *2026-10-27:* 2.0.0, a major, takes the customer inputs of that day: Dealer Master masters the ship-to stations and jobbers are mastered in SAP MDG and RightAngle, with the sub-jobber role, the dealer classes, 50 customer systems (20 matched to the system module), 48 flows and one deprecated sourcing (the decision of 2026-10-27). |
| `population/` | What eight MPC-defined measures include and exclude, from MPC's wording (the decision of 2026-10-19); released in `kpi` 1.1.0 (the decision of 2026-10-22) |
| `consumer/` | Rules for consumers: the catalog binding and what an agent may answer and must refuse (the decision of 2026-10-19); released in `integration` 1.0.0 (the decision of 2026-10-22) |
| `apqc/` | The full APQC Downstream Petroleum PCF 7.2.2 element list (2,012 elements), a reference for Q11 (the decision of 2026-10-19); a reference file, in no package (the decision of 2026-10-22) |
| `authority/` | Step 9: the evidence tier of every cited source, so the best-tier source wins when two disagree (the decision of 2026-10-19); released in `integration` 1.0.0 (the decision of 2026-10-22) |
| `placement/` | The placement kinds: which placing properties certify (only producing a data product) and which give context (the decision of 2026-10-19); released in `integration` 1.0.0 (the decision of 2026-10-22) |
| `market-data/` | The Step 7 market-data module (*2026-10-26:* 1.1.0 adds 2 series, 40 market prices and the views' series enumerations, the decision of 2026-10-25): 13 series of the crack-spreads measure, from MPC Economics' definition first (six regional ex-RIN series, the NYMEX 3-2-1, two MPC-weighted blends), then MPC's FY2025 Form 10-K, Item 7, and CME Group, with their benchmarks and regions (the decision of 2026-10-19, the decision of 2026-10-20); released as 1.0.0 on 2026-10-22 (the decision of 2026-10-22) |
| `technical-graph/` | The technical-graph module: the vocabulary of what was built on the data platform, its shapes and an example graph that is test data, answering questions 45 to 50; released as 1.0.0 on 2026-11-02 (the decision of 2026-11-02) |
| `logical-model/` | The logical-model module's machinery: its vocabulary, shapes, builder and a made-up example model that is test data, answering questions 51 to 55. The customer model it holds is released as `logical-model 1.0.0` (the decision of 2026-11-02) |
| `lane/` | The Step 7 lane module: the four office lanes and the seven processes the process map places in them (the decision of 2026-10-19); released as 1.0.0 on 2026-10-22 (the decision of 2026-10-22) |
| `system/` | The Step 7 system module (*2026-10-26:* 34 systems since 1.2.0, with MIPS and Databricks; 1.1.0 and 1.2.0 define 18, the decision of 2026-10-25, the decision of 2026-10-25; 1.3.0 defines 14 more from the repository, 32 of 34, the decision of 2026-10-26; 1.4.0 adds MPC-P11's seven systems and 21 links, 39 of 41 defined, the decision of 2026-10-26; 1.5.0 adds eight systems the process map does not name, from the customer inputs of 2026-10-27, 47 of 49 defined, the decision of 2026-10-27): the systems come from the process map's system strings (32 in 1.0.0), merged on spelling through a register, with their kind and the processes they support (the decision of 2026-10-19); released as 1.0.0 on 2026-10-22 (the decision of 2026-10-22) |
| `value-stream/` | The Step 7 value-stream module: the Commercial Hydrocarbon Lifecycle and Order to Cash, their stages, capabilities and 58 value-stream processes, which realize core processes, produce and consume data products and carry the MPC-P09 measure links (the decision of 2026-10-19); released as 1.0.0 on 2026-10-22 (the decision of 2026-10-22) |
| `data-product/` | The Step 7 data-product module: the portfolio's 3 segments, 19 lines and 48 data products as definitions (49 since Customer Master, 2026-10-23, the decision of 2026-10-23), 33 of them parked for lack of a description, mapped to DCAT, not imported (the decision of 2026-10-19); released as 1.0.0 on 2026-10-22 (the decision of 2026-10-22) |
| `organization/` | The Step 5 organization module: the RACI assignment and control vocabulary, its SHACL shapes and tests (the decision of 2026-10-13), the role register with the roles built from it (the decision of 2026-10-13), and the RACI assignments with their ledger (the decision of 2026-10-13) |
| `regression/` | The Step 11 SPARQL regression: one query per tested part of a question, each question's status, and the runner `check.sh` calls |
| `release/`, `releases/` | Release builders and packages: `core` 1.0.0 (the decision of 2026-10-13), organization 1.0.0 and ref-mpc 1.0.0 (the decision of 2026-10-13), core 2.0.0 (the decision of 2026-10-13), core 2.1.0 (the decision of 2026-10-18), core 2.2.0 (the decision of 2026-10-22), organization 2.0.0 and ref-mpc 1.1.0 (the decision of 2026-10-18), and kpi 1.0.0 and 1.0.1 (the decision of 2026-10-18), and party 1.0.0 (the decision of 2026-10-22), and data-product, value-stream, system, lane and market-data 1.0.0 (the decision of 2026-10-22), and integration 1.0.0 (the decision of 2026-10-22), and kpi 1.1.0 (the decision of 2026-10-22), and ref-mpc 1.2.0 (the decision of 2026-10-22), and core 2.3.0 (the decision of 2026-10-23), and core 2.4.0 (the decision of 2026-10-26), and value-stream 1.1.0 (the decision of 2026-10-23), and data-product 1.1.0 (the decision of 2026-10-23), and party 1.1.0 (the decision of 2026-10-23), and kpi 1.1.1 (the decision of 2026-10-23), and integration 2.0.0 (the decision of 2026-10-23); system 1.1.0, party 1.2.0 and integration 2.1.0 (the decision of 2026-10-25, in the item G change); kpi 1.2.0, market-data 1.1.0, data-product 1.2.0, system 1.2.0 and integration 2.2.0 (the decision of 2026-10-25, in the item F change); system 1.3.0, party 1.3.0 and integration 2.3.0 (the decision of 2026-10-26, in the item G descriptions change); system 1.4.0 and party 1.4.0 (the decision of 2026-10-26, in the MPC-P11 change); party 2.0.0, system 1.5.0, integration 2.4.0 and ref-mpc 1.3.0 (the decision of 2026-10-27, in the customer inputs change); organization 2.2.0 (the decision of 2026-10-18, amendment of 2026-10-28); party 2.1.0 and integration 2.5.0 (the decision of 2026-10-25, amendment of 2026-10-28); kpi 1.3.0, the measures' KPI and OPM identifiers (the decision of 2026-10-28); technical-graph 1.0.0, the module's first release (the decision of 2026-11-02); `releases/catalog.ttl`, one DCAT catalog of every release, built by `release/build_catalog.py` (the decision of 2026-10-22) |
| `apqc-scope-decisions.md` | One-at-a-time in/out-of-scope calls for the seven APQC gap candidates |
| `apqc-crosscheck-report.md` | Repo process map vs APQC Downstream PCF v7.2.2 consistency check (2026-09-17) |
| `build/step2-identity-map.py` | Reproducible script: URI slug for every one of the 680 nodes |
| `build/apqc_crosscheck.py` | Reproducible script: cited-ID check + coverage scores vs the vendored v7.2.2 workbook |
| `build/output/step2-identity-map.json` | 680 rows: uri, slug, level, name, skos_notation, parent_slug, minted flag |
| `build/output/step2-identity-report.md` | Identity normalization summary |
| `build/output/apqc_crosscheck_results.json` | Raw cross-check scores |
| `build/step3-skos-taxonomy.py` | Reproducible script: 680 `skos:Concept` taxonomy with URIs, labels, definitions, scope notes, APQC + validator + human-author provenance (`--adoptions`, `--authored`) |
| `build/output/step3-taxonomy.ttl` | The SKOS taxonomy. Measured on `main` 37ab0a0 (2026-09-30): 14,496 triples, 683 `skos:Concept`, 681 `skos:broader` links, 680 concepts with `skos:definition`. Still carries the provisional `intake:` annotations until the `core` 1.0.0 release |
| `build/output/step3-taxonomy-report.md` | Step 3 build summary |
| `build/step3b-definition-triangulation.py` | Reproducible script: APQC candidate matching + EIA/web triangulation over the 503 definition gaps |
| `build/step3b-merge-validations.py` | Merge automated + human validation records into final adoption decisions |
| `build/output/step3b-definition-review.csv` | All 503 definition-gap review rows: 1 adopted, 10 rejected at the human gate, 14 human-authored in Step 3c; L4–L6 authoring continues in the intake workbook |
| `build/output/step3b-adoptions.json` | The single adopted definition (internal marketing communications strategy) with provenance |
| `build/output/step3b-web-input.json` | 131 strong-match rows sent for web validation |
| `build/output/step3b-web-validations.json` | 111 automated web-validation records |
| `build/output/step3b-web-validations-manual.json` | 11 human-vetted manual validation records |
| `build/output/step3c-authored-definitions.json` | 14 human-authored L1–L3 definitions (approved by the decision owner 2026-09-18) merged into the taxonomy |
| `build/output/step3c-definition-authoring-workbook.xlsx` | Semantic-intake workbook (6 sheets, 503 rows). Step 3c closed 2026-09-21: 498/503 approved (see the working record's decision log) |
| `build/scripts/step3c-workbook-validate.py` | Mechanical review gate. Synced v2026-09-19b (`ptc-closed` is blocked-only) |
| `step3c-reviewer-instructions.md` | Locked reviewer guide (v2026-09-19b) |
| `step3c-parked-tree-changes.md` | Structural moves accepted in review and deferred to a later JSON/TTL pass |

## Standing conventions

- **Source of truth:** `../business_process/downstream_process_map.json`.
  The ontology models those processes; APQC is a consistency reference.
- **URI base:** `https://w3id.org/mpc/ontology/`, a placeholder: not registered with w3id.org and not hosted, because the domain may change (the decision of 2026-10-14).
- **License:** this folder's contents are proprietary, all rights reserved.
  APQC-sourced material is used under the APQC/IBM license terms —
  attribution travels with every distribution (see `../reference/README.md`).
- **HTML pages:** each reading document here (this README, `MODULES.md`, the module READMEs and the others
  `scripts/build_docs_html.py` lists) has an `.html` page beside it, generated from the Markdown, and the
  decision records are one page, `../domain/decisions/decisions.html`. Edit the Markdown, then run
  `python3 scripts/build_docs_html.py` from the repo root; `scripts/check.sh` fails while a page is stale.

## Status

**The ontology is closed** (the decision of 2026-10-23, 2026-10-23). *2026-10-26:* **the ontology is done** (the decision of 2026-10-26): MPC-P11 and MPC-P12 are accepted and released, the deferred qSKOS fixes are released, and what stays open is the business's points in `business-closeout.md`, the next releases' small fixes, the items parked for other reasons, and usage and integration, a separate, later task. Every item that
waited on the decision owner is answered (the decisions of 2026-10-23 to 2026-10-23), the six
close-out releases are built and tagged, the projection's list of release
gaps is empty, and the competency regression is green. Steps 0 to 12 are done or stand as recorded, each with its listed
exceptions (the decision of 2026-10-22). Phase E closed on 2026-10-22.

- **Releases:** 51 packages under `releases/`, listed in
  `releases/catalog.ttl` (the decision of 2026-10-22). The newest of each module:
  `core` 2.4.0 (the decision of 2026-10-26), organization 2.2.0 (the decision of 2026-10-18, amendment of 2026-10-28), ref-mpc 1.3.0 (the decision of 2026-10-27), kpi 1.3.0 (the decision of 2026-10-28), party 2.1.0
  (the decision of 2026-10-25, amendment of 2026-10-28),
  value-stream 1.2.0 (the decision of 2026-10-26), data-product 1.2.0
  (the decision of 2026-10-25), system 1.5.0 (the decision of 2026-10-27), lane 1.1.0 (the decision of 2026-10-26), market-data 1.1.0 (the decision of 2026-10-25), and
  integration 2.5.0 (the decision of 2026-10-25, amendment of 2026-10-28), and technical-graph 1.0.0 (the decision of 2026-11-02). *2026-10-25:* system 1.1.0, party 1.2.0 and integration
  2.1.0 carry the systems' definitions from item G and the qSKOS top-concept fixes (the decision of 2026-10-25); item F's
  five releases carry the pricing measures' bindings, prices, platform tables and lineage (the decision of 2026-10-25, the decision of 2026-10-25). *2026-10-26:* system 1.3.0, party 1.3.0 and integration 2.3.0 carry the internal systems' descriptions, drafted from the repository (the decision of 2026-10-26). Lane 1.1.0, organization 2.1.0 and value-stream 1.2.0 carry the deferred qSKOS top-concept fixes (the decision of 2026-10-25, item 5; the decision of 2026-10-26). core 2.4.0 renames the 25 processes that shared seven names (MPC-P12) and carries core's qSKOS fixes (the decision of 2026-10-25, the decision of 2026-10-26). System 1.4.0 and party 1.4.0 carry MPC-P11, which the subject matter expert accepted, and party's shape message without an apostrophe (the decision of 2026-10-26). *2026-10-27:* party 2.0.0 (a major the subject matter expert approved), system 1.5.0 and integration 2.4.0 carry the subject matter expert's customer inputs of that day (the decision of 2026-10-27). ref-mpc 1.3.0 adds MPC's brands Marathon, ARCO and Tesoro, which the subject matter expert confirmed as brand values later that day (the decision of 2026-10-27, amendment of 2026-10-27). *2026-10-28:* organization 2.2.0 carries the decision owner's close-out answers: PSM expanded as Process Safety Management, and the Crude RFC reading and Business Planning and Analysis's definition confirmed (the decision of 2026-10-18, amendment of 2026-10-28). Party 2.1.0 defines Drop Tank, GasBuddy and the DTN File Server from their vendors' own published words (Drop Tank's from a 2018 press release) and notes the decision owner's belief that Polaris is bought; integration 2.5.0 tiers the three new sources (the decision of 2026-10-25, amendment of 2026-10-28).
- **Checks:** every package conforms to its own shapes (the decision of 2026-10-22);
  the competency regression has 43 questions answerable, 0 partial,
  0 waiting and 1 parked (Q17, the decision of 2026-10-23) (*2026-11-02:* 49 answerable, with questions 45 to 50 of the
  technical-graph module answered on its example graph, the decision of 2026-11-02; *2026-11-02:* 54 answerable, with questions 51 to 55 of the logical-model module answered on its made-up example model, the decision of 2026-11-02); the Neo4j projection of every released package passes,
  with no rule gap listed (16 before value-stream 1.1.0, 14 before party
  1.1.0, 6 before kpi 1.1.1, 5 before integration 2.0.0)
  (the decision of 2026-10-13). *2026-11-02:* the skill's checker lists one release exception, `tg:designedAs` with no range,
  which technical-graph 1.0.0 leaves out on purpose (`projection/skill-run/epm-config.json`).
- **Held rows:** 462, each held with its reason: 51 Phase 1 rows and 411
  outside Phase 1 (`python3 scripts/epm_facts.py counts`). PTC-001-B is
  held by design.
- **Decided by the subject matter expert on 2026-10-23:** Q17 is parked until
  the ontology is first shared with business consumers (the decision of 2026-10-23;
  *2026-11-02:* the follow-up release may be cut and shared with it still open, listed in `OPEN-ITEMS.md`);
  MPC-P10 is accepted (the decision of 2026-10-23); product values from MPC's FY2025
  Form 10-K, and six releases that carry these and close the 16 projection
  gaps, are approved (the decision of 2026-10-23). `core` 2.3.0, `value-stream` 1.1.0,
  `data-product` 1.1.0, `party` 1.1.0, `kpi` 1.1.1 and `integration` 2.0.0
  are released (the decisions of 2026-10-23 to 2026-10-23). The projection guideline moved
  into the `ontology-to-lpg` skill (the decision of 2026-10-23).
  Phase F, the `ontology` skill, was approved on 2026-10-22
  (the decision of 2026-10-22) and is done: a change to the skills folder,
  merged on 2026-10-23.
- **Open after closure, with the business:** every point only the business
  can settle is in `business-closeout.md`, with the record each answer goes
  to: Q17, Market Data's accountable group, the four codes and TID Nbr, the
  product list, Forecaster, Crude RFC, PSM, four working role definitions
  and 33 measure populations. They are settled when the ontology is first
  shared with business consumers (*2026-11-02:* the follow-up release may
  be cut and shared with Q17 still open, the decision of 2026-10-23). *2026-10-28:* the decision owner worked
  through the package: points 3 and 4 are closed, point 5 is narrowed to the
  PIDX family letters, and points 17 and 18 (Dealer Master) are added
  (the decision of 2026-10-23, amendment of 2026-10-28). Organization 2.2.0 closes
  points 7 (Crude RFC) and 8 (PSM) and settles one of point 9's four
  definitions (the decision of 2026-10-18, amendment of 2026-10-28). Party 2.1.0
  narrows point 11 to Federal Health and what MPC sends the four systems,
  and notes point 15's answer (the decision of 2026-10-25, amendment of 2026-10-28).
- **Open after closure, apart from the ontology:** the store tests are a
  separate, later task: load the ontology into Apache Jena and into a
  Databricks Delta triple table, project it to a local Neo4j and to Aura, then
  rebuild both from the Databricks store and check that no data is lost;
  OntoBricks follows, to link Unity Catalog metric views to the processes
  (the decision of 2026-10-23).
