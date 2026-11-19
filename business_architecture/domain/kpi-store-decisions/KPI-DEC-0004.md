# KPI-DEC-0004: A new KPI's change file is KGCL lines plus a facts table, approval records keep signers' names, and KGCL stays the one change format

| Field | Value |
|---|---|
| Status | Decided (the owner, 2026-11-19) |
| Date | 2026-11-19 |
| Source | The owner's words of 2026-11-19, saved in `answers/2026-11-19-kpi-store-1.2-morning.md` |

## Question

The night run under KPI-DEC-0003 left five questions for the owner, each with a recommendation worded so that "yes"
accepts it. The owner then asked whether a second change format should sit beside KGCL. Both are saved in full in
the answers file.

## Context

The agent wrote this section. It is not the owner's words.

KPI-DEC-0002 chose KGCL as the change file. Building the new-KPI path showed that KGCL cannot carry the text facts a
new KPI needs: on kgcl-schema 0.7.0, a quoted text object in `create edge` renders without its quotes, and `change
annotation` does not parse. Two decisions the agent had made under the delegation (signers' names in the approval
records, and the apostrophe rule) were also put to the owner, with two smaller questions: who rehearses the handout,
and removing the old 1.1 folder from the client laptop.

## Decision

**The owner's answer to the five questions:**

> Yes to all

This accepts each recommendation:

1. A new KPI's proposal holds `change.kgcl` for everything KGCL can say, and `facts.csv` (measure, property, value)
   for the text facts KGCL cannot write. Apply writes both, and the round trip checks both.
2. Approval records (`approvals/<change>.json`, sign-off files next to the ontology and not part of it) keep each
   signer's name. The ontology records roles and never a person's name.
3. A straight apostrophe (`'`) from a table value is written as a curly apostrophe (`’`) in a KGCL line, and apply
   turns it back into `'`, so the tables keep their text. Text that already holds a real `’` is refused.
4. The handout's rehearser (Q25 of KPI-DEC-0002) is the teammate who tested the KPI intake form.
5. The owner removes the old 1.1 folder from the client laptop.

**The owner's answer on a second format**, after the agent recommended one path:

> ok go ahead, keep working on the plan

So KGCL, with the facts table for a new KPI, stays the one change format. No second format is built.

## Alternatives considered

- **A format of KPI Store's own instead of KGCL.** Not chosen: "Yes to all" accepted KGCL plus a facts table.
- **An extended KGCL that writes text facts.** Not chosen: "Yes to all" accepted KGCL plus a facts table, and the
  official parser would refuse the lines.
- **Roles only in approval records.** Not chosen: "Yes to all".
- **Refuse any value that holds an apostrophe.** Not chosen: "Yes to all".
- **A second change format beside KGCL.** Not chosen: "ok go ahead, keep working on the plan", after the agent's
  answer that one path is simpler.

## The owner's recorded words

Saved in `answers/2026-11-19-kpi-store-1.2-morning.md`: every quote in the Decision section above, word for word, and
the owner's question about a second format.

## Evidence

- The owner's words of 2026-11-19 (the answers file). Tier: the owner's recorded decision.
- The agent's test of kgcl-schema 0.7.0, described in the Context section and in the answers file.
