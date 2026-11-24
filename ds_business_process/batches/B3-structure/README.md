# Batch B3: the process structure and the new IDs (expected results, for approval)

Status: waiting for the decision owner's approval. Nothing in the release changes until then. Once approved, the
change is made with `build_candidate.py` and checked with `check_expected.py` and the release checks.

## What changes

`expected-changes.csv` lists every change that round 2 decided (DSBP-DEC-0012 and 0016 to 0031), one row each:

| Kind | Count | What |
|---|---|---|
| Rename | 6 | Planning, Scheduling & Optimization; Supply & Trading; Midstream & Logistics; Procurement & Supply Chain (Goods and Services); Environment, Health & Safety; Legal & External Affairs. Each old label is kept as a prior preferred label. |
| Move | 4 | Refinery Planning and Optimization goes under Planning, Scheduling & Optimization, so it and its 23 descendants each go down one level. Terminal Loading goes to Terminal Services. Develop Strategic Business Plan goes to the new Strategy L1. Coordinate Site Business Risk Management goes to the new Enterprise Risk L1. |
| Deprecate | 3 | IT Services and Process Excellence & IT, replaced by the new IT and Business Process Excellence. Refinery Performance and Risk Coordination, emptied by the move and replaced by Enterprise Risk Management. Each stays as a deprecated concept so old links still resolve. |
| Exclude | 1 | Shared Services, which leaves the release. The migration map gives the reason. |
| New | 8 | Information Technology; Business Process Excellence; Strategy & Business Development; Enterprise Risk Management; Lubricants & Specialties; Petrochemicals; Retail (under Marketing); Regulatory Reporting (under EHS). Each has a draft definition in the file for approval. |

**On every concept (DSBP-DEC-0031):** a new ID `DSBP-P-000001` to `DSBP-P-000707`, numbered in the sorted order of the 1.2 IRIs. The 8 new concepts take 000708 to 000715, in the file's order. `skos:notation` (the old code, such as "CM 1.1.4") moves to the migration map and leaves the concepts.

## What must not change

- Every concept not named in the file, and not a descendant of a moved one, keeps its parent, labels, definition and every other statement (check V3, with `skos:notation` the one predicate the ID rule removes everywhere).
- Every relationship between processes still holds under the new IDs (check V7).

## The tests, written first

`test_check_expected.py`, 13 tests:
- On the baseline under new IDs, with nothing else changed, the batch check fails, as it should before the change.
- On the candidate `build_candidate.py` makes, the batch check passes, and so do V2, V3 and V7. V4 finds only the two known missing definitions, which batch B5 adds.
- The batch check fails on candidates with one wrong change: a move not made, a rename not made, an old label not kept, a deprecation missing, a notation left behind, a wrong level, a new concept missing, and an exclusion with no reason in the map. V3 fails when an unlisted concept moves.

## Points for the decision owner when approving

1. **The draft definitions of the 8 new concepts.** They are in the file's last column. Each still needs a public source (check V6). Batch B5 adds the sources, from the APQC elements and the peer rows named in the evidence column.
2. **IT and Process Excellence: deprecate and replace, or rename?** The file deprecates both old concepts and adds two new ones, because the split changes what each means. Renaming Process Excellence & IT to Information Technology would keep one link, but its meaning would change without a record.
3. **Numbering.** IDs follow the sorted order of the old IRIs, so they are reproducible but not in tree order. Numbering in tree order would read better, but the numbers would then still hint at a place, which DSBP-DEC-0031 set out to avoid.
4. **Found while writing the file, not yet decided:** "Operational Accounting" sits under Marketing, which no research covered yet. CM 1.2.5 and 1.2.6 are still called "... Supply Chain Management"; the research suggests "Crude & Feedstock Supply" and "Refined Product Supply", so that "supply chain" means one thing only.
