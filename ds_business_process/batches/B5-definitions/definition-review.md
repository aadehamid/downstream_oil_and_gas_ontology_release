# Definition review: batch B5, 2026-11-28

Step 3's definition review for every concept that batch B5 changes, one row for each row of `changes.csv`. The rules are the ontology skill's `references/quality.md`, "Definition quality bar". Each cell is P (passes), F (fails; Notes say what fixes it) or n/a. The texts are the ones on the core that `build_candidate.py` makes. B3's review (`../B3-structure/definition-review.md`) found the failures this batch fixes.

Reviewer: the modeller (Claude), with the independent reviewer named in the pull request. Check script result: `check_taxonomy.py` on the core reports only the failures in `taxonomy-known.csv` (`test_build_candidate.py`, `test_the_core_fails_check_taxonomy_only_where_listed`). Checks V4 and V6 pass on it.

Stated once here, not repeated in Notes:
- **Point 8, provenance, fails on every row.** No concept has `dcterms:dateAccepted` or a `dcterms:creator` role yet, so each is still a candidate. The fix is the release batch (Step 10).
- **Point 7, evidence.** Every new or rewritten definition cites public sources only, listed in `sources.csv` with a title, publisher, version or issue date, web address and access date (check V6). Every changed concept loses the private Step 3c workbook as a source (DSBP-DEC-0002). Where a row keeps 1.2's definition, 1.2's other sources stand; four such concepts cited only the workbook and now cite nothing, so they fail point 7 until a later batch sources 1.2's unchanged definitions (listed in `../../BUILD-STATUS.md`).
- **Point 4, bounded.** A test (`test_every_scope_note_that_names_a_process_is_named_back`) checks that every scope note this batch writes, when it names another process, is named back in that process's scope note, unless the two are parent and child.

| Term | Kind | 1 Form for its kind | 2 Distinguishing | 3 Parent test | 4 Bounded | 5 Stable terms | 6 Park | 7 Evidence | 8 Provenance | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `DSBP-P-000002` Planning, Scheduling & Optimization (rewritten) | activity | P | P | P | P | P | P | P | F | Names the activity and its outcome. The scope note gives the line to Supply & Trading and Midstream & Logistics, and both name it back. "Backcasting" is gone. |
| `DSBP-P-000229` Supply & Trading (rewritten) | activity | P | P | P | P | P | P | P | F | Movements now belong to Midstream & Logistics (DSBP-DEC-0025); "primary & secondary distribution" is gone. The scope note names the three neighbours, and each names it back. |
| `DSBP-P-000682` Midstream & Logistics (rewritten) | activity | P | P | P | P | P | P | P | F | The one company's pipeline agreements and subsidiary are gone (check V5 no longer finds them in this concept). Crude gathering and NGL fractionation wait for their evidence row (DSBP-DEC-0046), as the scope note says. |
| `DSBP-P-000686` Procurement & Supply Chain (Goods and Services) (rewritten) | activity | P | P | P | P | P | P | P | F | Now the buying of goods and services only, as DSBP-DEC-0012 split it; crude and product supply go to Supply & Trading, which names it back. |
| `DSBP-P-000681` Legal & External Affairs (rewritten) | activity | P | P | P | P | P | P | P | F | Government relations and external affairs are in (DSBP-DEC-0029). The scope note's line to EHS is named back there. |
| `DSBP-P-000678` Environment, Health & Safety (scope note) | activity | P | P | P | P | P | P | F | F | The scope note no longer uses the old name of Legal & External Affairs and now names Enterprise Risk Management, both reciprocated. Its 1.2 definition cited only the workbook (point 7, open). |
| `DSBP-P-000427` Terminal Loading (rewritten) | activity | P | P | P | P | P | P | P | F | The lifting-control work of its four children (DSBP-DEC-0049): it enforces, at the rack, the allocation and credit decisions taken elsewhere. Each of the four neighbours its scope note names has a sentence naming it back. The "consist" grammar slip is gone. |
| `DSBP-P-000694` Terminal Services (scope note) | activity | P | P | P | P | P | P | F | F | The scope note is rewritten without 1.2's old codes. Its 1.2 definition has no source (point 7, open). |
| `DSBP-P-000395` Terminal Operations Management (reciprocal) | activity | P | P | P | P | P | P | P | F | Sentence added naming Terminal Loading. 1.2's definition and its public sources stand. |
| `DSBP-P-000021` Allocate Finished Products (reciprocal) | activity | P | P | P | P | P | P | P | F | As above. |
| `DSBP-P-000613` Allocate & Release Order (reciprocal) | activity | P | P | P | P | P | P | P | F | As above. |
| `DSBP-P-000618` Manage Credit & Risk (reciprocal) | activity | P | P | P | P | P | P | P | F | As above. |
| `DSBP-P-000144` Develop Strategic Business Plan (new definition) | activity | P | P | P | P | P | P | P | F | 1.2 had no definition (check V4 and B3's TX-2 found it); the gap is closed. The line to its parent is in the scope note. |
| `DSBP-P-000146` Coordinate Site Business Risk Management (sources) | activity | P | P | P | P | P | P | P | F | The workbook is dropped and ISO 31000 added; the scope note now names its parent, Enterprise Risk Management. |
| `DSBP-P-000128` Refinery Planning and Optimization (sources) | activity | P | P | P | P | P | P | P | F | The workbook is replaced by two refiners' 10-K descriptions of refinery planning. |
| `DSBP-P-000708` Information Technology (new) | activity | P | P | P | P | P | P | P | F | NIST CSF 2.0 and three peers. Lines to Business Process Excellence and Enterprise Risk Management, both named back. |
| `DSBP-P-000709` Business Process Excellence (new) | activity | P | P | P | P | P | P | F | F | The line to Information Technology is named back. Its sources are two companies' disclosures and no standard, one short of the 3 the industry-reference mode asks for; a third public source is open. |
| `DSBP-P-000710` Strategy & Business Development (new) | activity | P | P | P | P | P | P | P | F | Its child, Develop Strategic Business Plan, is named in the scope note. |
| `DSBP-P-000711` Enterprise Risk Management (new) | activity | P | P | P | P | P | P | P | F | ISO 31000. The scope note says how it differs from EHS and process safety and from cybersecurity, as B3's review asked; both name it back. |
| `DSBP-P-000712` Lubricants & Specialties (new) | activity | P | P | P | P | P | P | P | F | The line to Refining is named back there. "A company without this business leaves this area empty" is in the scope note, not the definition. |
| `DSBP-P-000713` Petrochemicals (new) | activity | P | P | P | P | P | P | P | F | As above. |
| `DSBP-P-000714` Retail (new) | activity | P | P | P | P | P | P | P | F | The pricing overlap B3's review found is settled: site pricing is here, reseller pricing stays with the other Marketing processes. |
| `DSBP-P-000715` Regulatory Reporting (new) | activity | P | P | P | P | P | P | P | F | Narrowed to EHS reports, as B3's review asked; Finance names it back. |
| `DSBP-P-000679` Finance (reciprocal) | activity | P | P | P | P | P | P | F | F | Sentence added naming Regulatory Reporting. Its 1.2 definition cited only the workbook (point 7, open). |
| `DSBP-P-000684` Refining (reciprocal) | activity | P | P | P | P | P | P | F | F | Sentence added naming Lubricants & Specialties and Petrochemicals. Its 1.2 definition cited only the workbook (point 7, open). |
| `DSBP-P-000103` Process Business Renewal Request (excluded) | activity | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Leaves the release (DSBP-DEC-0052): 1.2 never defined it, its owner never confirmed what it means, and no public source names such a process. The migration map gives the reason. |

`dsbp:accessDate`, the property this batch declares for the sources' access dates, is not a process and has no row: its definition cites ISO 690:2021, whose clause 7.7.4 is "Date of citation".
