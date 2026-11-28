# Batch B3: the process structure and the new IDs (approved and applied)

Status: approved by the owner on 2026-11-27 (DSBP-DEC-0045), on the condition that the Step 3 definition review and `check_taxonomy.py` join these expected results before the script runs. Both have joined (see "The Step 3 gate" below). The change is made with `build_candidate.py` and checked with `check_expected.py`, `check_taxonomy.py` and the release checks. It is applied (DSBP-DEC-0050): `build_candidate.py --out --map-out --approved-out` writes the working core, `../../ontology/core/core.ttl`, with `../../migration/core-process-map.csv` and the approved list `../../migration/core-b3-approved.txt`, and tests fail when a committed file differs by one byte from a fresh run.

## What changes

`expected-changes.csv` lists every change that round 2 decided (DSBP-DEC-0012 and 0016 to 0031), one row each:

| Kind | Count | What |
|---|---|---|
| Rename | 6 | Planning, Scheduling & Optimization; Supply & Trading; Midstream & Logistics; Procurement & Supply Chain (Goods and Services); Environment, Health & Safety; Legal & External Affairs. Each old label is kept as a prior preferred label. |
| Move | 4 | Refinery Planning and Optimization goes under Planning, Scheduling & Optimization, so it and its 23 descendants each go down one level. Terminal Loading goes to Terminal Services. Develop Strategic Business Plan goes to the new Strategy L1. Coordinate Site Business Risk Management goes to the new Enterprise Risk L1. |
| Exclude | 5 | Shared Services (DSBP-DEC-0018) and IT Services (DSBP-DEC-0017) leave the release; Process Excellence & IT is split into the new IT and Business Process Excellence (DSBP-DEC-0017); the emptied Refinery Performance and Risk Coordination is removed (DSBP-DEC-0027); Commercial Development, already retired in 1.2 and emptied by this batch's move of its one child (Develop Strategic Business Plan), is excluded rather than kept as deprecated (H-7, DSBP-DEC-0043). All five are empty in 1.2 or emptied by this batch, and no relationship points at them. The migration map gives each one's reason and names each replacement by its new ID and label, such as "DSBP-P-000708 (Information Technology)", which is how an old 1.2 link finds its successor. |
| New | 8 | Information Technology; Business Process Excellence; Strategy & Business Development; Enterprise Risk Management; Lubricants & Specialties; Petrochemicals; Retail (under Marketing); Regulatory Reporting (under EHS). Each has a draft definition in the file. |

**On every concept (DSBP-DEC-0031):** a new ID from `DSBP-P-000001` to `DSBP-P-000707`, numbered in the sorted order of the 1.2 IRIs; the 5 excluded concepts leave their numbers unused, so 702 are taken. The 8 new concepts take 000708 to 000715, in the file's order, and each joins its parent's concept scheme. The old code, such as "CM 1.1.4", moves to the migration map, and each concept's one `skos:notation` becomes its neutral ID (DSBP-DEC-0048).

## What must not change

- Every concept not named in the file, and not a descendant of a moved one, keeps its parent, labels, definition and every other statement (check V3, with `skos:notation` the one predicate the ID rule changes everywhere, from the old code to the neutral ID).
- Every relationship between processes still holds under the new IDs (check V7).

## The tests, written first

`test_check_expected.py`:
- On the baseline under new IDs, with nothing else changed, the batch check fails, as it should before the change.
- On the candidate `build_candidate.py` makes, the batch check passes, and so do V2, V3 and V7. V4 finds only the two known missing definitions, which batch B5 adds.
- The batch check fails on candidates with one wrong change: a move not made, a rename not made, an old label not kept, an old code left as a notation, a wrong level, a new concept missing, and an exclusion with no reason in the map. V3 fails when an unlisted concept moves, and when an unchanged parent of a moved or renamed concept is edited; a parent is never approved for its child's change.
- A row of kind `unchanged` (the file has none now; the tests add one for CM-1-1-3) fails the check when that concept's label, parent or deprecation changes, and does not approve it for V3.
- Every migration-map note names a replacement by its new ID and label, never by the file's working key (`NEW:it`), and the retired Commercial Development is excluded, with no trace left in the candidate.

## The Step 3 gate (the condition of DSBP-DEC-0045)

- **`definition-review.md`** checks the definition of every concept this batch renames, moves or adds (18 rows) against the 8 points of the ontology skill's definition guide. A test fails if a changed concept has no row. Each failing point names the batch that fixes it, and the one question it raised, whether Terminal Loading's text fits its new parent, is DSBP-Q-B3-1, recorded under "Open questions" in the decision register and closed by DSBP-DEC-0049: it is the lifting-control work at the terminal, without physical loading, and batch B5 rewrites its definition.
- **`check_taxonomy.py`** (the copy in this repo's `skills/ontology/scripts/`) runs on the candidate. Its failures there are listed in `taxonomy-known.csv`, each with its count and the batch that fixes it: 46 core code-list values with no notation, the 2 missing definitions B5 adds, 3 core property domain or range issues, and 2 release-metadata values. The tests fail if the candidate fails anywhere else, if a listed count changes, or if a row has no fixing batch, and tests prove the gate catches a new failure and a changed count. A crash of the script fails the tests too.
- Before this gate, `check_taxonomy.py` found 756 concepts with no notation: the 710 process concepts, whose old codes the ID rule removed, and the 46 core code-list values (TX-1). DSBP-DEC-0048 makes each process concept's one notation its neutral ID. The SKOS Reference defines a notation as a string that identifies a concept within its scheme, `check_taxonomy.py` fails a concept with none, and the master copy of the ontology skill (personal-agent-skills) makes a generalizing build's notations its neutral IDs (Step 2, rule 2). This repo's older copy under `skills/ontology/` lacks that exception until it is refreshed.

## Points the owner approved (DSBP-DEC-0045)

1. **The draft definitions of the 8 new concepts.** They are in the file's last column. Each still needs a public source (check V6). Batch B5 adds the sources, from the APQC elements and the peer rows named in the evidence column. The Step 3 definition review, which joins this batch's gate, lists each such gap with B5 as its fix; no release is cut while one is open.
2. **IT and Process Excellence (settled by the first delegated review, 2026-11-27).** An earlier draft deprecated three emptied concepts in place. DSBP-DEC-0017 says IT Services leaves and DSBP-DEC-0027 says the emptied Refining L2 is removed, so they are now excluded, as Shared Services is. Process Excellence & IT is excluded too, since it is split and has no children; renaming it to Information Technology would change its meaning without a record.
3. **Numbering.** IDs follow the sorted order of the old IRIs, so they are reproducible but not in tree order. Numbering in tree order would read better, but the numbers would then still hint at a place, which DSBP-DEC-0031 set out to avoid.
4. **The renamed concepts keep their 1.2 definitions and scope notes for now.** This batch changes structure and labels only. Two of the old texts no longer match the new name: Procurement & Supply Chain (Goods and Services) is still defined as the whole downstream supply chain, though DSBP-DEC-0012 split supply away from it, and Legal & External Affairs does not yet name government relations, which DSBP-DEC-0029 puts in it. The other four renames need their texts checked against the new names too. Batch B5 rewrites all six, with public sources (check V6), and removes the company text in their scope notes (check V5). The definition review lists these too, and no release is cut while one is open.
5. **Found while writing the file, still undecided and left out of B3 (DSBP-DEC-0045):** "Operational Accounting" sits under Marketing, which no research covered yet. CM 1.2.5 and 1.2.6 are still called "... Supply Chain Management"; the research suggests "Crude & Feedstock Supply" and "Refined Product Supply", so that "supply chain" means one thing only.
