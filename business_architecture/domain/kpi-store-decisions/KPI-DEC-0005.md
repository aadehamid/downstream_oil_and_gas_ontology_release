# KPI-DEC-0005: The client's own tables get no comments, the 114 untyped property shapes wait until after 1.2, and the release is KPI Store 1.2 in a folder with no version

| Field | Value |
|---|---|
| Status | Decided (the owner, 2026-11-22) |
| Date | 2026-11-22 |
| Source | The owner's words of 2026-11-22, saved in `answers/2026-11-22-kpi-store-1.2-questions.md` |

## Question

The agent's update of the night run under KPI-DEC-0003 listed three questions:

1. Should the load add comments to the client's own gold tables and metric views? My recommendation is no.
2. Should the 114 untyped property shapes be left until after 1.2? My recommendation is yes.
3. At release time, how should the version be named? `release.json` and the doc paths still say 1.1.

The owner answered the first two, asked for the agent's view on the third, and then answered it. All of it is saved
in the answers file.

## Context

The agent wrote this section. It is not the owner's words.

- **The client's own tables.** Step 9 of KPI-DEC-0002 (Q23) made the load comment the four tables it creates in
  Databricks, from the ontology's definitions. The load's safety gate refuses any write outside the KPI Store's
  schemas, so the client's gold tables and metric views get no comments.
- **The 114 property shapes.** They name no datatype and no class, so the Neo4j Ontology Graph Specification lists
  them under "left out". Covering them would mean changing the ontology-to-lpg skill.
- **The name.** `release.json` says "KPI Store 1.1", and the guides and the runbook name the release folder
  `kpi-store-1.1`. The upgrade command (step 10) refuses a release older than the copy and changes nothing for the
  same one.

## Decision

**The owner's answer to questions 1 and 2:**

> agreed with your recommendation on 1 and 2.

This accepts both recommendations:

1. The load does not add comments to the client's own gold tables and metric views.
2. The 114 untyped property shapes are left until after 1.2.

**The owner's answer to question 3**, after the agent's view (quoted in the answers file):

> yes to both, go ahead with 3

This accepts both parts of the agent's view:

3. The release is named KPI Store 1.2, as the last change before it is cut: in `release.json`, in the zip's name,
   `kpi-store-1.2.zip`, and in the release line the forms and pages show.
4. The guides stop putting the version in the release folder's name, in a change of its own before the cut. An
   upgrade keeps the folder the client has. The records of 1.1 keep their name: KPI-DEC-0001, the saved answers,
   the 1.1 shipping notes and the tests that check them.

## Alternatives considered

- **Comment the client's own gold tables and metric views too.** Not chosen: "agreed with your recommendation on 1
  and 2."
- **Cover the 114 untyped property shapes in 1.2.** Not chosen: "agreed with your recommendation on 1 and 2."
- **Keep the name KPI Store 1.1.** Not chosen: "yes to both, go ahead with 3".
- **A folder named for each release, such as `kpi-store-1.2`.** Not chosen: "yes to both, go ahead with 3".

## The owner's recorded words

Saved in `answers/2026-11-22-kpi-store-1.2-questions.md`: every quote in the Decision section above, word for word,
the three questions as the agent asked them, the owner's question on the third and the agent's answer.

## Evidence

- The owner's words of 2026-11-22 (the answers file). Tier: the owner's recorded decision.
