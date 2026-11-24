# Goal: DS_Business_Process 1.0

Status: draft for Hamid's approval (2026-11-24). The done lines below take effect when he approves them in his own words, and that approval goes into `registers/decision-register.md` as DSBP-DEC-0014.

## The goal, in the owner's words

- "Let us make this a goal." (Hamid, 2026-11-24, project chat)
- The brief's aim, as he set it: a company-agnostic but industry-validated downstream oil and gas business process ontology, generalized from `kpi-store/1.2`, that keeps downstream specificity, preserves IDs and traceability, and cites high-quality public evidence.
- "basiacally we should migrate over all business areas in 1.2 and expand on them in this generic release" (Hamid, 2026-11-23)
- "Validation is very important. we must test that every chnages works this way it should. So before chnages we wotk out what the validation should be." (Hamid, 2026-11-23)

## Done means

Each line ends **Met**, with the command or file that shows it, run against the final release commit, or **Blocked**, with the open question that stops it. A line that is neither is not done.

1. **The baseline is untouched.** Branch `kpi-store/1.2` still points at `ddf6b68`, and check V1 passes (every 1.2 file matches the hash in its manifest).
2. **All nine release checks pass.** `dsbp_checks.py` prints `pass` for V1 to V9 and exits 0 on the release candidate, with no check skipped. The test file shows each check failing on a deliberately broken copy.
3. **Nothing is lost.** The migration map has exactly one row for each of the 707 baseline process IRIs, each with one status (retained, relabeled, modified, deprecated or excluded), and the counts add to 707 (check V2). The same holds for every term of the other 11 migrated modules, in that module's own map.
4. **No company is left in the reference layer.** Check V5 passes against `registers/company-terms.csv`, in every migrated module. No concept is an MPC-built system, an MPC org unit or an MPC role title. Exceptions: none. A company name may appear only in `skos:example` or in the migration map.
5. **All of 1.2 is migrated, not only the ontology.** Hamid: "when I say all of 1.2 i eant everything including the guides, playbooks, runbooks, viewer and so on." (2026-11-24). Every one of the 1,004 files tracked at `ddf6b68` has one row in `migration/files.csv`: migrated (with its new path) or excluded (with its reason). That covers the 12 ontology modules (`core`, `data-product`, `integration`, `kpi`, `lane`, `logical-model`, `market-data`, `organization`, `party`, `system`, `technical-graph`, `value-stream`), each with a manifest, conforming SHACL shapes and the new namespace; every script (the builders, checks, store loaders and everything under `scripts/`), as Hamid added: "and also the scripts of course" (2026-11-24); the KPI Store and intake pack; the README, handout, `HOW-TO-UPDATE` guide, best practices, playbooks and runbooks; the skills shipped with the release; and both viewers, rebuilt from the new release. Exclusions are allowed only for `ref-mpc` and MPC-only reference material, and Hamid approves the list of excluded rows. Every migrated text file passes check V5.
6. **Every L0 to L2 node has a decided place and name.** Each one has a row in the decision register with Hamid's recorded words, and an evidence row in `research/peer-hierarchy-evidence.csv` that cites a standard or 3 or more independent companies. That includes where supply chain sits.
7. **The thin areas are complete.** Refining, Midstream and logistics, Supply chain, Commercial, Finance, HR and every other area in the approved coverage table (`registers/coverage.md`) are marked complete in that table, and Hamid has approved the table. Every new concept has an evidence class other than "unsupported", and every claim of industry-wide practice cites a standard or 3 or more independent companies.
8. **Every source is logged.** Every new or changed definition cites a public source with title, publisher, URL, version and access date (check V6), and `registers/source-log.csv` lists every source used.
9. **The licence is stated.** Each module states CC BY 4.0 in `dcterms:rights`, and the release carries the APQC notice.
10. **The repository's checks pass.** `scripts/check.sh` exits 0 and CI is green on the final commit. The tests that need a live store also run, against Neo4j and Fuseki test servers started in Docker, and none of them is skipped. Databricks has no local stand-in, so its load stays an owner's step.
11. **The loads into the stores run with no issues.** Hamid: "the load to stores must also be tested to make sure they run. You can always delete what we have in the store when the testing is done." (2026-11-24). On fresh Neo4j and Fuseki test servers in Docker (a second Neo4j server stands in for Enterprise), the migrated loaders load the release, the sync check reports every store current, the questions return their expected answers, and the reset then empties every store. The saved log shows each step's exit status 0. Exception: Databricks, which has no local stand-in; its steps are proven only by the tests and a dry run.
12. **The runbook works as written.** Hamid: "when i get to the target environment i am able to run thensame thing by following the runbook and no issues." (2026-11-24). In a clean container that starts with only what the runbook's prerequisites list, every command is copied from the runbook in its order, nothing is typed that the runbook does not say, and every step ends as the runbook says it should. Any step that needed a fix is fixed in the runbook, and the rehearsal is rerun from the start. The rehearsal log is saved with the release. The same exception for Databricks applies.
13. **Hamid has approved the release.** The release pull request into `ds-business-process/1.0` has an independent review with every finding fixed or answered, and Hamid's approval. Every material change in it has an approved decision in the register with his recorded words. Nothing is merged without his approval.

## Owner's steps after the release

- Following the runbook in the target environment, including the first Databricks load, which no test here can stand in for.

## Target

This repository only: `aadehamid/downstream_oil_and_gas_ontology_release`, folder `ds_business_process/` on branch `ds-business-process/1.0`. Independent review runs on Mac-Studio-4 (decision of 2026-11-23).

## How decisions are made on the way

- **Grill-with-docs round 1** is Q1 to Q11 of the Phase 1 report, already answered.
- **Round 2** runs when the peer research comes back: one question per L0 to L2 node (keep, rename, move, split or merge), including supply chain.
- Each later batch starts with its expected-results file, which Hamid approves before the change is made.
