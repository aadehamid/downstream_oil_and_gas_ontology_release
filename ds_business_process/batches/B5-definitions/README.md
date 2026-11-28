# Batch B5: definitions, scope notes and public sources (applied)

Status: applied by script on top of batch B3 (DSBP-DEC-0053, delegated under DSBP-DEC-0040; decided when the independent review agrees). `build_candidate.py --out --map-out --approved-out` writes the working core, `../../ontology/core/core.ttl`, with `../../migration/core-process-map.csv` and the approved list `../../migration/core-approved.txt`. Tests fail when a committed file differs by one byte from a fresh run. This batch's test took that comparison over from B3's (DSBP-DEC-0050).

## What changes

`changes.csv` has one row per concept, with the decision behind each and the evidence, by source and section. `sources.csv` lists the public sources, each with a title, publisher, version or issue date, web address and access date (check V6).

| Kind | Count | What |
|---|---|---|
| Rewrite | 6 | The six renamed L1 areas B3's review failed: Planning, Scheduling & Optimization; Supply & Trading; Midstream & Logistics; Procurement & Supply Chain (Goods and Services); Legal & External Affairs; and Terminal Loading, rewritten as the lifting-control work at the terminal (DSBP-DEC-0049). |
| Add | 9 | A definition for Develop Strategic Business Plan, which 1.2 lacked, and sourced definitions and scope notes for the 8 concepts B3 added. |
| Scope note | 2 | Environment, Health & Safety and Terminal Services: new scope notes, without old names or old codes. |
| Reciprocal sentence | 6 | Terminal Operations Management, Allocate Finished Products, Allocate & Release Order, Manage Credit & Risk, Finance and Refining: one sentence naming back the concept whose new scope note names them (quality bar, point 4). |
| Sources | 2 | Coordinate Site Business Risk Management and Refinery Planning and Optimization: the private workbook replaced by public sources. |
| Exclude | 1 | Process Business Renewal Request, which 1.2 never defined and no public source names (DSBP-DEC-0052). |

On every changed concept, the private Step 3c workbook leaves as a source (DSBP-DEC-0002) and a change note names DSBP-DEC-0053 and the row's decision. The batch also declares `dsbp:accessDate` (`../../validation/README.md`), defined from ISO 690:2021.

Sources, by the evidence order of the industry-reference mode: standards and public bodies first (ISO 31000, ISO 690, the NIST Cybersecurity Framework 2.0, the EIA glossary, EPA's Greenhouse Gas Reporting Program, OSHA's recordkeeping rule), then the public filings and pages of independent companies (15 SEC filings, 3 company pages and 1 sustainability report). Each rewritten or new definition rests on a standard or on 3 or more companies, except Business Process Excellence, which rests on 2 (see below).

## What must not change

Every concept not in `changes.csv` keeps every statement (check V3), and every relationship between processes still holds (check V7).

## The tests, written first

`test_build_candidate.py`:
- On B3's core, V4 fails on the 2 missing definitions and V6 on the 8 unsourced new concepts. On this batch's core, V1 to V4 and V6 to V8 pass. V5 still fails, 1,454 times, on 1.2's namespace and editorial text, which later batches fix.
- V3 fails when a concept the batch does not list changes, and V6 when a cited source loses its access date.
- A change row with the wrong label, for a concept B3 lacks, or of an unknown kind is refused. Every source is cited and every cited source is listed, and each has the facts V6 asks for.
- Every scope note this batch writes that names another process is named back in that process's scope note, unless they are parent and child; a test proves the check catches a missing sentence.
- `check_taxonomy.py` fails only where `taxonomy-known.csv` says (B3's list without TX-2, the 2 missing definitions this batch adds), and a test proves the gate catches an untagged source fact.
- `definition-review.md` has a row for every row of `changes.csv`.

## Found on the way

- **The approved list shortened web addresses.** `read_approved` cut every line to its last path segment, so listing a source page such as `https://www.iso.org/standard/65694.html` would approve any IRI ending in `65694.html`. A full IRI now stays whole (`validation/test_dsbp_checks.py`, `test_an_approved_iri_approves_that_iri_only`).
- **The reasoner cannot read `xsd:date` as a range.** HermiT accepts only the OWL 2 datatype map, so `dsbp:accessDate` is an annotation property with no declared range, as check V8 showed.
- **Develop Strategic Business Plan still carries 1.2's implementation hold**, with a working trace check V5 finds. B3 made the move the hold waited for, and this batch gives it a definition. The batch that rewrites 1.2's editorial notes lifts the hold.
- **Business Process Excellence rests on two companies' disclosures**, with no standard behind it, one short of the 3 the industry-reference mode asks for. Its place was decided in round 2 (DSBP-DEC-0017); a third source is open in the definition review.
- **Four changed concepts keep 1.2 definitions with no public source**: Environment, Health & Safety; Terminal Services; Finance; Refining. They cited only the workbook. Their definitions are unchanged, so V6 does not test them, but the definition review marks point 7 open until a batch sources 1.2's unchanged definitions.
