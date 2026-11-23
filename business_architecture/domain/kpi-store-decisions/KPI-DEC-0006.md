# KPI-DEC-0006: The handout stays in the release, an agent skill drives a change, the zip gets a dry run, a 1.1 copy moves to 1.2 by a new run, and the upgrade takes content the copy left as shipped

| Field | Value |
|---|---|
| Status | Decided (the owner, 2026-11-22 and 2026-11-23) |
| Date | 2026-11-23 |
| Source | The owner's words, saved in `answers/2026-11-23-kpi-store-1.2-changes.md` |

## Question

During the night run under KPI-DEC-0003, the agent asked the owner four questions that changed the plan of
KPI-DEC-0002. The answers file saves each question as the owner received it and the owner's words.

## Context

The agent wrote this section. It is not the owner's words.

- **The handout's copy.** The plan of 2026-11-18 sent a generated copy of the handout to a training folder outside
  the release.
- **The skill.** The people who change the ontology have never built one. The release's commands refuse rather than
  guess, and the apply order of forms that wait on each other is easy to get wrong.
- **The dry run.** Every check so far ran from a Git checkout. Nobody had unpacked a 1.2 zip and run it.
- **The move from 1.1.** A 1.1 copy that the runner has loaded holds correction versions that the cut committed.
  1.2 changed the format of the source tables. The upgrade command first ships in 1.2. In a test on 2026-11-23, it
  refused a 1.1 copy with one correction: it kept the copy's version of every content file the new release changes,
  so 1.2's builders read 1.1 tables and stopped. A fresh 1.2 copy refuses a discovery report of 1.1, so a 1.1 copy's
  corrections are made again from a new report.

## Decision

1. The handout's only home is the release. No copy goes to the training folder.
2. An agent skill drives a change from a filled form through the release's own commands. Its master is
   in the owner's skills repository, and the release ships a copy of its files, unchanged.
3. Before the night run closes, the 1.2 zip gets a dry run: built, unpacked into an empty folder, checked, and run.
4. a. The handout tells a 1.1 user how to move to 1.2: rename the old folder, unpack 1.2 under the same name, and run
   the runner, deciding the new report's rows again.
   b. Before the close, a CI job rehearses that move: it loads 1.1 into the stores, moves to 1.2 and runs the runner.
   c. The upgrade command changes its rule for content in 1.2. A content file the copy left as shipped takes the new
   version. A table that both the copy and the new release changed, whose columns the new release changes, stops the
   upgrade, with a message that says to make the change again in the new format.

This narrows KPI-DEC-0002, Q2, under which the copy is the master of the ontology's content: the copy stays the
master of every content file it changed.

## Consequences

- The upgrade's rule in `HOW-TO-UPDATE.md`, "Upgrade the tools from a newer release", and in `kpi_store/upgrade.py`
  changes with item 4c, in the same change as this record.
- Items 2, 3, 4a and 4b each land in a change of their own.
