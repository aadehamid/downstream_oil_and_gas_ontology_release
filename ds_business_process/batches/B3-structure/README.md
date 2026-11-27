# Batch B3: the process structure and the new IDs (expected results, for approval)

Status: waiting for approval under DSBP-DEC-0040 (Claude and Gemini Neon both agree; Codex breaks a tie, DSBP-DEC-0041). Nothing in the release changes until then. Once approved, the
change is made with `build_candidate.py` and checked with `check_expected.py` and the release checks.

## What changes

`expected-changes.csv` lists every change that round 2 decided (DSBP-DEC-0012 and 0016 to 0031), one row each:

| Kind | Count | What |
|---|---|---|
| Rename | 6 | Planning, Scheduling & Optimization; Supply & Trading; Midstream & Logistics; Procurement & Supply Chain (Goods and Services); Environment, Health & Safety; Legal & External Affairs. Each old label is kept as a prior preferred label. |
| Move | 4 | Refinery Planning and Optimization goes under Planning, Scheduling & Optimization, so it and its 23 descendants each go down one level. Terminal Loading goes to Terminal Services. Develop Strategic Business Plan goes to the new Strategy L1. Coordinate Site Business Risk Management goes to the new Enterprise Risk L1. |
| Exclude | 4 | Shared Services (DSBP-DEC-0018) and IT Services (DSBP-DEC-0017) leave the release; Process Excellence & IT is split into the new IT and Business Process Excellence (DSBP-DEC-0017); the emptied Refinery Performance and Risk Coordination is removed (DSBP-DEC-0027). All four are empty in 1.2 or emptied by this batch, and no relationship points at them. The migration map gives each one's reason and replacements, which is how an old 1.2 link finds its successor. |
| New | 8 | Information Technology; Business Process Excellence; Strategy & Business Development; Enterprise Risk Management; Lubricants & Specialties; Petrochemicals; Retail (under Marketing); Regulatory Reporting (under EHS). Each has a draft definition in the file for approval. |

**On every concept (DSBP-DEC-0031):** a new ID from `DSBP-P-000001` to `DSBP-P-000707`, numbered in the sorted order of the 1.2 IRIs; the 4 excluded concepts leave their numbers unused, so 703 are taken. The 8 new concepts take 000708 to 000715, in the file's order, and each joins its parent's concept scheme. `skos:notation` (the old code, such as "CM 1.1.4") moves to the migration map and leaves the concepts.

## What must not change

- Every concept not named in the file, and not a descendant of a moved one, keeps its parent, labels, definition and every other statement (check V3, with `skos:notation` the one predicate the ID rule removes everywhere).
- Every relationship between processes still holds under the new IDs (check V7).

## The tests, written first

`test_check_expected.py`, 13 tests:
- On the baseline under new IDs, with nothing else changed, the batch check fails, as it should before the change.
- On the candidate `build_candidate.py` makes, the batch check passes, and so do V2, V3 and V7. V4 finds only the two known missing definitions, which batch B5 adds.
- The batch check fails on candidates with one wrong change: a move not made, a rename not made, an old label not kept, a notation left behind, a wrong level, a new concept missing, and an exclusion with no reason in the map. V3 fails when an unlisted concept moves.

## Points for the decision owner when approving

1. **The draft definitions of the 8 new concepts.** They are in the file's last column. Each still needs a public source (check V6). Batch B5 adds the sources, from the APQC elements and the peer rows named in the evidence column.
2. **IT and Process Excellence (settled by the first delegated review, 2026-11-27).** An earlier draft deprecated three emptied concepts in place. DSBP-DEC-0017 says IT Services leaves and DSBP-DEC-0027 says the emptied Refining L2 is removed, so they are now excluded, as Shared Services is. Process Excellence & IT is excluded too, since it is split and has no children; renaming it to Information Technology would change its meaning without a record.
3. **Numbering.** IDs follow the sorted order of the old IRIs, so they are reproducible but not in tree order. Numbering in tree order would read better, but the numbers would then still hint at a place, which DSBP-DEC-0031 set out to avoid.
4. **Found while writing the file, not yet decided:** "Operational Accounting" sits under Marketing, which no research covered yet. CM 1.2.5 and 1.2.6 are still called "... Supply Chain Management"; the research suggests "Crude & Feedstock Supply" and "Refined Product Supply", so that "supply chain" means one thing only.
