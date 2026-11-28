# Where the build stands, by the ontology skill's steps

The build follows the `ontology` skill in personal-agent-skills (`skills/data/ontology/SKILL.md`), with its references, templates and scripts. For each module after `core`, `references/new-module.md` narrows the steps. Where the skill falls short, the gap goes in `registers/skill-gaps.csv` at the point we hit it, and the skill updates come from that log.

Status as of 2026-11-27. The owner's answers to the review pack of 2026-11-27 are DSBP-DEC-0044 to 0046, and to the follow-up decision card on Q-P2, DSBP-DEC-0047.

**Current step: Step 0, with Step 8 run early as the skill orders.** Open gate: the survey register is drafted and the registry searches are done; the APQC re-check and the remaining sources (OSDU, ISO 14224 and the leads in its findings) are still open.

| Step | What the build already has | What the skill still asks for | Gate |
|---|---|---|---|
| Intake | `foundations/requirements.yaml`, which passes `check_requirements.py` (2026-11-27); 61 competency questions locked, 9 held (DSBP-DEC-0044) | Lock or drop the 9 held questions | Done |
| 0. Reference framework and existing ontologies | Peer hierarchy research (`research/peer-hierarchy-findings.md` and its evidence CSV); APQC 7.x used as a crosswalk | `foundations/survey-register.md` drafted: IOF Core, Supply Chain, Production Planning and Maintenance (release 202603, MIT) read from the publisher's files; POSC Caesar and ISO 22400 read. The four registry searches ran on the owner's computer (2026-11-24). They have not ruled out a downstream or refinery vocabulary: one search failed (HTTP 500), one registry ran in degraded mode, and several hits are still to assess. Still open: those hits, the failed searches, the APQC re-check, and the further sources listed in its findings | Open |
| 8. Scope review | Round 2 decisions on every L0 to L2 node (DSBP-DEC-0012, 0016 to 0031); the coverage idea (done line 7); `foundations/scope-review.md`, approved with the line that places the H-10 work (DSBP-DEC-0046): 14 process areas and 4 module groups in, 6 out (3 process areas and 3 module groups), each out call with a boundary note and revival trigger | The evidence row for the H-10 placement, which also sets where crude gathering meets the Upstream fence, before a batch adds its processes | Approved |
| 1. The ten policies | 1.2's policies, changed by decisions on evidence order (0002), namespace (0003), IDs (0031), licence (0009) and the two layers (0033); `foundations/policies.md` with all 10 rows decided (DSBP-DEC-0036; Q-CQ by 0044, which locks 61 of the 70 questions in `foundations/competency-questions.md` and holds 9 until their evidence is cited; Q-P2 by 0047, no active consumers) | None | Done |
| 2. Identity | Neutral IDs decided (0031); check V2 tests the migration map's IDs | `identity-table.md`. V2 must also re-point all 640 Step 4 relationship facts, whose ends all carry old codes, and must find subtrees by parent links, not code prefixes (local-materials review, pack 4+5) | Open |
| 3. Taxonomy, classes and properties | Batch B3's expected-results file, approved by the owner (DSBP-DEC-0045); checks V3 to V7 | `definition-review.md`; `check_taxonomy.py` run beside our checks, both added to B3's expected results before its script runs | Approved, gate to add |
| 4 to 7. Relationships, organizations and roles, plans and runs, integration | 1.2's releases of the 12 modules, as the seed | Each module through `new-module.md`, completed from external evidence (0032), with the local-materials review and the market brief as leads | Not started |
| 9 to 12. SHACL, release, regression, projection | Checks V1 to V9 and the release tooling from 1.2 | The skill's scripts: `check_shapes.py`, `check_cardinality.py`, `check_code_lists.py`, `check_packages.py`, `build_package.py`, `build_catalog.py`, `run_regression.py`; then `ontology-to-lpg` for the stores | Not started |

## Next

1. Cite the evidence for the 9 held competency questions (59, 67, 70, 20, 22, 41, 42, 43 and 50) and lock each, delegated under DSBP-DEC-0040 and 0041. Question 20 is held, but 21, 23 and 25 ask about the same party roles; settle them with it. Q-P2 is answered: no active consumers (DSBP-DEC-0047). The vision is approved (`VISION.md`, DSBP-DEC-0043).
2. Finish Step 0: the APQC re-check (cross-industry and downstream petroleum 7.2.2), OSDU's reference-data lists, ISO 14224 and the leads in the survey register.
3. Bring batch B3 under Step 3's gate, the condition of its approval (DSBP-DEC-0045): add the definition review and `check_taxonomy.py` to its expected results, then run it. Add the evidence row for the H-10 placement, which also sets where crude gathering meets the Upstream fence (DSBP-DEC-0046).
4. Extend check V2 to the Step 4 facts before any migration runs.
5. Turn `registers/skill-gaps.csv` (20 rows) into a skills pull request, each change checked with Gemini (DSBP-DEC-0042).
