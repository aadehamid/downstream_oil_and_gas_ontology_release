# KPI-DEC-0001: KPI Store 1.1 is a stand-alone release for one platform, built under a recorded delegation

| Field | Value |
|---|---|
| Status | Decided (the owner, 2026-11-11) |
| Date | 2026-11-11 |
| Source | The owner's written instruction of 2026-11-11, saved in `answers/2026-11-11-kpi-store-1.1.md` |

## Question

None was asked. The owner gave the instruction in their own words on 2026-11-11.

## Context

KPI Store 1.1 carries the whole ontology and targets one platform: Databricks, then Apache Jena Fuseki on Windows,
then Neo4j Enterprise. Before the Databricks load, it compares the ontology with the workspace. If the two differ
on structure, the load stops and writes a report. A person clears the report, a cut tool turns the cleared report
into a correction version, and Databricks loads that version. This record fixes the rules the build follows and
the decisions the owner delegated. The agent wrote this section.

### The agent's plan (not the owner's words)

1. Build the parts in this order: this record; the stand-alone clean-up and its guard in `scripts/check.sh`; the
   Databricks load and the loop with its runner; the cut tool; the Fuseki and Neo4j loads; the technical graph;
   the sync check; the cross-graph questions; a rehearsal on Databricks Free; the documents and both step-by-step
   guides; the guide tests; the cut and the zip.
2. Every module, skill, viewer, guide and script of the ontology goes in. The demo does not. The AuraDB copy, the
   Docker stores and the token connector leave with their tests, and no other document names them.
3. Keep a guard in `scripts/check.sh`: a deny list for references to anything outside this release, and an allow
   list for public sources and licences.
4. Each change is a pull request into the release branch. The owner's recorded words set the merge rule: a pull
   request merges when `check.sh` and CI pass and every review finding is fixed or answered. The agent adds how it
   meets that rule; this part is the agent's text, with no recorded words behind it: before each push,
   `scripts/check.sh` passes and one independent reviewer, a different model from the author, reads the change.
5. Number this release's decision records `KPI-DEC-0001` onward, in this folder. A decision the agent makes under
   the delegation below is recorded as "Decided (delegated under KPI-DEC-0001)" where its question lives.
6. Record each ontology correction with a discovery-run record in the repo: what changed, why, who cleared it and
   when. A correction version carries a marker, for example `1.2.1-correction.1`.
7. State the write limits in the runbook. The notebook writes only to `idp_sbx.kpi_store` and
   `idp_sbx.tech_graph`, and reads only the catalogs named in `kpi_store.toml`. The Neo4j load writes only to
   `businessprocessarchitecturegraph`.
8. Open items that wait on the owner: the first run on the sandbox and the run on the owner's Windows machine,
   both from the zip and the runbook. Open item that waits on the owner or the Genie space's creator: whether
   Benchmark Prices gets its own measure.
9. This record amends no earlier record. It is the first in this release.

## Decision

**The owner's answer:** "Build KPI Store 1.1 overnight, up to a tested zip."

"The cut release must stand alone. It refers to nothing outside itself except public sources and licences."

"Remove the AuraDB copy, the Docker stores and the token connector, with their tests."

"Client inputs never go in the repo. Tests use made-up fixtures with the real shapes. The demo's data may be used for tests and the Free rehearsal, but the demo is not in the package."

"Ontology changes only through the loop. Each correction cites a discovery-run record kept in the repo."

"Decide anything inside the plan yourself and log it. Anything that would change the plan goes in the morning log as a question; work around it and don't stop."

"Merge a PR when check.sh and CI pass and every review finding is fixed or answered."

**The option that answer chose (the agent's text, as asked; not the owner's words):** None.

## Alternatives considered

- **Keep the demo in the package.** Not chosen: "the demo is not in the package".
- **Edit the ontology by hand when discovery finds a difference.** Not chosen: "Ontology changes only through the
  loop."
- **Wait for the owner on each choice inside the plan.** Not chosen: "Decide anything inside the plan yourself and
  log it."

## The owner's recorded words

Saved in `answers/2026-11-11-kpi-store-1.1.md`: every quote in the Decision section above, word for word.

The agent's text, not the owner's words: the owner can reverse any decision made under this delegation.

## Evidence

- The owner's instruction of 2026-11-11 (the answers file). Tier: the owner's recorded decision.
- `scripts/check.sh` in this release: the check every change passes before it is pushed.
