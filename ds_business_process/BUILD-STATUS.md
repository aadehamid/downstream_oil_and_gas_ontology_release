# Where the build stands, by the ontology skill's steps

The build follows the `ontology` skill in personal-agent-skills (`skills/data/ontology/SKILL.md`), with its references, templates and scripts. For each module after `core`, `references/new-module.md` narrows the steps. Where the skill falls short, the gap goes in `registers/skill-gaps.csv` at the point we hit it, and the skill updates come from that log.

Status as of 2026-11-24, 13:00 UTC.

**Current step: Step 0, with Step 8 run early as the skill orders.** Open gate: the survey register is drafted and the registry searches are done; the APQC re-check and the remaining sources (OSDU, ISO 14224 and the leads in its findings) are still open.

| Step | What the build already has | What the skill still asks for | Gate |
|---|---|---|---|
| Intake | `foundations/requirements.yaml`, which passes `check_requirements.py` (2026-11-24) | The owner locks the competency questions (Step 1) | Drafted |
| 0. Reference framework and existing ontologies | Peer hierarchy research (`research/peer-hierarchy-findings.md` and its evidence CSV); APQC 7.x used as a crosswalk | `foundations/survey-register.md` drafted: IOF Core, Supply Chain, Production Planning and Maintenance (release 202603, MIT) read from the publisher's files; POSC Caesar and ISO 22400 read. The four registry searches ran on the owner's computer (2026-11-24). They have not ruled out a downstream or refinery vocabulary: one search failed (HTTP 500), one registry ran in degraded mode, and several hits are still to assess. Still open: those hits, the failed searches, the APQC re-check, and the further sources listed in its findings | Open |
| 8. Scope review | Round 2 decisions on every L0 to L2 node (DSBP-DEC-0012, 0016 to 0031); the coverage idea (done line 7) | `foundations/scope-review.md` drafted: 14 process areas and 4 module groups in; 6 out (3 process areas and 3 module groups), each out call with a boundary note and revival trigger. Waits for the owner's review | Drafted |
| 1. The ten policies | 1.2's policies, changed by decisions on evidence order (0002), namespace (0003), IDs (0031), licence (0009) and the two layers (0033) | `foundations/policies.md`: 8 rows decided (Q-P1 answered, DSBP-DEC-0036); 2 ASSUMED, waiting on Q-CQ (lock `foundations/competency-questions.md`, 70 drafted: 1.2's 55 made company-neutral plus 15 new) and Q-P2 (no active consumers) | Open |
| 2. Identity | Neutral IDs decided (0031); check V2 tests the migration map's IDs | `identity-table.md`. V2 must also re-point all 640 Step 4 relationship facts, whose ends all carry old codes, and must find subtrees by parent links, not code prefixes (local-materials review, pack 4+5) | Open |
| 3. Taxonomy, classes and properties | Batch B3's expected-results file, waiting for the owner's approval; checks V3 to V7 | `definition-review.md`; `check_taxonomy.py` run beside our checks | Waiting on the owner |
| 4 to 7. Relationships, organizations and roles, plans and runs, integration | 1.2's releases of the 12 modules, as the seed | Each module through `new-module.md`, completed from external evidence (0032), with the local-materials review and the market brief as leads | Not started |
| 9 to 12. SHACL, release, regression, projection | Checks V1 to V9 and the release tooling from 1.2 | The skill's scripts: `check_shapes.py`, `check_cardinality.py`, `check_code_lists.py`, `check_packages.py`, `build_package.py`, `build_catalog.py`, `run_regression.py`; then `ontology-to-lpg` for the stores | Not started |

## Next

1. The owner reviews the drafts in `foundations/` and the local-materials packs in `research/local-review/`, and answers the open cards: Q-CQ (lock the 70 competency questions) and Q-P2 (no active consumers).
2. Finish Step 0: the APQC re-check, OSDU, ISO 14224 and the leads in the survey register.
3. Bring batch B3 under Step 3's gate: add the definition review and `check_taxonomy.py` to its expected results.
4. Extend check V2 to the Step 4 facts before any migration runs.
5. Turn `registers/skill-gaps.csv` (19 rows) into a skills pull request, with the owner's approval.
