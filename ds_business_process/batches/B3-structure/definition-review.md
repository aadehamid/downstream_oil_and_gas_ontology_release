# Definition review: batch B3, 2026-11-27

Step 3's definition review for the concepts that B3 renames, moves or adds (DSBP-DEC-0045). The rules are the ontology skill's `references/quality.md`, "Definition quality bar". Each cell is P (passes), F (fails; the fix is in Notes) or n/a. The texts are the ones on the candidate that `build_candidate.py` makes. B3 changes structure and labels only, so a failing text stays as it is in B3. Its fix is the batch named in Notes, and no release is cut while an F stays open.

Reviewer: the modeller (Claude), with the independent reviewer named in the pull request. Check script result: `check_taxonomy.py` on the candidate reports only the failures in `taxonomy-known.csv` (`test_check_expected.py`, `test_the_candidate_fails_check_taxonomy_only_where_listed`).

Two points fail on every row, and a third on every new concept, so they are stated once here and not repeated in Notes:
- **Point 7, evidence.** The 1.2 texts cite the private Step 3c workbook (Coordinate Site Business Risk Management cites it beside its public sources), or nothing. A reference cites public sources only, checked at the cited item (DSBP-DEC-0002; checks V5 and V6). The fix is batch B5.
- **Point 8, provenance.** No concept has `dcterms:dateAccepted` or a `dcterms:creator` role yet, so every one is still a candidate. The fix is the release batch (Step 10), after the owner's approval of B5.
- **Point 4, bounded, on the 8 new concepts.** They have no scope note. B5 adds one with each definition.

A concept with no definition text is marked F on point 1 (there is no definition) and n/a on the points that test a text's content (2, 3, 5 and 6).

| Term | Kind | 1 Form for its kind | 2 Distinguishing | 3 Parent test | 4 Bounded | 5 Stable terms | 6 Park | 7 Evidence | 8 Provenance | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `DSBP-P-000002` Planning, Scheduling & Optimization (renamed) | activity | F | F | P | F | F | P | F | F | B5. The 1.2 text is in title case and lists contents ("Includes Processes Such As …") instead of naming the activity and its outcome. Its inventory management overlaps Supply & Trading and Midstream & Logistics. "Backcasting" is not defined. There is no scope note. |
| `DSBP-P-000229` Supply & Trading (renamed) | activity | F | F | P | F | F | P | F | F | B5. It lists contents in title case. "Planning & managing movements … primary & secondary distribution" overlaps Midstream & Logistics (DSBP-DEC-0025), and "primary & secondary distribution" is not defined. There is no scope note. |
| `DSBP-P-000682` Midstream & Logistics (renamed) | activity | F | P | P | F | P | P | F | F | B5. It names the activity but not its intended outcome. One scope note still describes one company's pipeline agreements and names its subsidiary, which a reference cannot carry (check V5). The H-10 work (crude gathering, NGL fractionation) is not in it yet (DSBP-DEC-0046). |
| `DSBP-P-000686` Procurement & Supply Chain (Goods and Services) (renamed) | activity | F | F | F | F | P | P | F | F | B5. The 1.2 text defines the whole downstream supply chain, but DSBP-DEC-0012 split crude and product supply away from it. It overlaps Supply & Trading and Planning, Scheduling & Optimization, and its scope note says the same, so the scope note is wrong too. |
| `DSBP-P-000678` Environment, Health & Safety (renamed) | activity | P | P | P | P | P | P | F | F | Its new child, Regulatory Reporting, is part of it, so the two don't overlap as siblings would. |
| `DSBP-P-000681` Legal & External Affairs (renamed) | activity | F | P | P | F | P | P | F | F | B5. It covers legal work and internal communications, but not the government relations and external affairs that the new name and DSBP-DEC-0029 put in it; its scope note's in-scope list leaves them out too. |
| `DSBP-P-000128` Refinery Planning and Optimization (moved) | activity | P | P | P | P | P | P | F | F | Planning the refinery's production is a way of carrying out Planning, Scheduling & Optimization, so the move passes the parent test. |
| `DSBP-P-000427` Terminal Loading (moved) | activity | F | P | F | F | P | P | F | F | B5, and a question for the decision log. The 1.2 text describes allocating product availability against customer credit and contract limits, and sending locks and unlocks. That is commercial allocation, not loading at a terminal, so under Terminal Services it fails the parent test. Either B5 rewrites it as the loading activity that DSBP-DEC-0021 moved, or the move is reopened. It has no scope note, and its grammar needs fixing ("consist"). |
| `DSBP-P-000144` Develop Strategic Business Plan (moved) | activity | F | n/a | n/a | F | n/a | n/a | F | F | B5. It has no definition in 1.2; check V4 and `taxonomy-known.csv` TX-2 find it. |
| `DSBP-P-000146` Coordinate Site Business Risk Management (moved) | activity | P | P | P | P | P | P | F | F | It cites public sources (APQC, EPA, OSHA) beside the private workbook; B5 drops the workbook and checks each claim at the cited item. Coordinating site risk is a way of carrying out Enterprise Risk Management. |
| `DSBP-P-000708` Information Technology (new) | activity | P | P | P | F | P | P | F | F | B5 adds the source (the peer rows of DSBP-DEC-0017) and a scope note. |
| `DSBP-P-000709` Business Process Excellence (new) | activity | P | P | P | F | P | P | F | F | B5, as above. |
| `DSBP-P-000710` Strategy & Business Development (new) | activity | P | P | P | F | P | P | F | F | B5, as above (DSBP-DEC-0026). |
| `DSBP-P-000711` Enterprise Risk Management (new) | activity | P | P | P | F | P | P | F | F | B5, as above (DSBP-DEC-0027). Its scope note should say how it differs from EHS and process safety. |
| `DSBP-P-000712` Lubricants & Specialties (new) | activity | P | P | P | F | P | P | F | F | B5, as above (DSBP-DEC-0030). |
| `DSBP-P-000713` Petrochemicals (new) | activity | P | P | P | F | P | P | F | F | B5, as above (DSBP-DEC-0030). |
| `DSBP-P-000714` Retail (new) | activity | P | F | P | F | P | P | F | F | B5. "Set prices and offers for consumers" overlaps Marketing's pricing processes. The scope note should say which pricing sits where. |
| `DSBP-P-000715` Regulatory Reporting (new) | activity | P | F | F | F | P | P | F | F | B5. "And other reports that regulators require" goes beyond EHS, its parent, and overlaps Finance, whose filings include financial and tax reports. Narrow it to EHS reporting. |

Open questions raised:
- **DSBP-Q-B3-1.** Is Terminal Loading, as 1.2 defines it, loading at a terminal or commercial allocation? This decides whether B5 rewrites its definition or the DSBP-DEC-0021 move is reopened. It is delegated under DSBP-DEC-0040 and 0041, and waits on the evidence B5 gathers.
