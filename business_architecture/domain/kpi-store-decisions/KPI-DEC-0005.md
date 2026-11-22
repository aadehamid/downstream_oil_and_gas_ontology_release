# KPI-DEC-0005: The load comments only the tables it creates, and the property shapes with no type wait until after 1.2

| Field | Value |
|---|---|
| Status | Decided (the owner, 2026-11-22) |
| Date | 2026-11-22 |
| Source | The owner's words of 2026-11-22, saved in `answers/2026-11-22-kpi-store-1.2-questions.md` |

## Question

The night run under KPI-DEC-0003 left two questions for the owner, each with a recommendation. Both are saved in full
in the answers file.

## Context

The agent wrote this section. It is not the owner's words.

Step 9 of KPI-DEC-0002 (Q23) wrote the Neo4j Ontology Graph Specification and made the load comment the tables it
creates in Databricks, from the ontology's definitions. Two things were left out of it:
- **The client's own tables.** The load's safety gate refuses any write outside the KPI Store's schemas, so the
  client's gold tables and metric views get no comments, even where the ontology has a definition that fits them.
- **114 property shapes.** They name no datatype and no class, so the specification lists them under "left out"
  instead of guessing a type. Covering them would mean changing the ontology-to-lpg skill.

## Decision

**The owner's answer:**

> agreed with your recommendation on 1 and 2.

This accepts each recommendation:

1. The load does not comment the client's own gold tables and metric views. It comments only the four tables it
   creates, and its safety gate stays as it is: the KPI Store writes inside its own schemas only.
2. The 114 property shapes with no datatype or class stay under "left out" in the specification for 1.2. Covering
   them is work for after 1.2.

## Alternatives considered

- **Comment the client's own tables too.** Not chosen: "agreed with your recommendation on 1 and 2". It would need the
  load to write outside the KPI Store's schemas.
- **Give the 114 shapes a type in 1.2.** Not chosen: "agreed with your recommendation on 1 and 2". It would change the
  ontology-to-lpg skill within this release.

## The owner's recorded words

Saved in `answers/2026-11-22-kpi-store-1.2-questions.md`: the quote in the Decision section above, word for word, and
the two questions as the agent asked them.

## Evidence

- The owner's words of 2026-11-22 (the answers file). Tier: the owner's recorded decision.
