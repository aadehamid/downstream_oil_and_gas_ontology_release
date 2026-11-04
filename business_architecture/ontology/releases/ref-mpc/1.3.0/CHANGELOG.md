# ref-mpc changelog

## 1.3.0 (2026-10-27)

Minor: it only adds. Approved by a subject matter expert, on the subject matter expert's answer ("yes those can be brand values. Others I cannot answer.", saved in (the review comments of a subject matter expert reviewing the documents); the decision of 2026-10-27, amendment of 2026-10-27).

- [minor] **MPC's brands.** Marathon, ARCO and Tesoro join the module as individuals of `party:Brand` (`reference-brands.ttl`), on this module's IRIs (`ref-mpc/brand/marathon`, `ref-mpc/brand/arco`, `ref-mpc/brand/tesoro`). Each has a plain-word definition, cites the subject matter expert's customer inputs of 2026-10-27 and MPC's FY2025 Form 10-K, and holds as of 2026-10-27. Who owns or licenses each brand is not stated.
- [minor] **A brand shape.** Each brand has one English name, one English definition, a source and a date.
- It requires organization 2.1.0 and party 2.0.0, the current releases, in place of organization 2.0.0 and party 1.0.0. No released IRI changes.
- Known gaps, open with the business, because the decision owner cannot answer them: how Dealer Master's billing customer number relates to the SAP customer number, and whether Dealer Master's fuel volumes reach the Enterprise Data Lake. This release closes the third gap the party 2.0.0 changelog lists, the brands; that package is left as built.

## 1.2.0 (2026-10-22)

Minor. Approved by the decision owner ("Approve ref-mpc 1.2.0 (Recommended)", saved in (the review comments of a subject matter expert reviewing the documents); the decision of 2026-10-22). MPC and MPLX as parties, in the `party` module's terms, join the module (`reference-parties.ttl`, moved from `party/`; the decision of 2026-10-21, the decision of 2026-10-22): MPC holds the Throughput Holder and Payer roles and MPLX the Carrier and Vendor roles under MPLX's fee-based services agreements, each held since 2012-10-31 and sourced to MPLX's FY2025 Form 10-K. The roles and the agreement are on this module's namespace. No released IRI changes. It requires organization 2.0.0, as 1.1.0 did, and party 1.0.0; the parties conform to the party module's shapes.

## 1.1.0 (2026-10-19)

Minor. Approved by the decision owner ("Approve the ref-mpc release too if needed", and "You have my approval to keep going and release things as needed. while I am out", saved in (the review comments of a subject matter expert reviewing the documents) and (the review comments of a subject matter expert reviewing the documents). The module now requires organization 2.0.0 in place of 1.0.0 (the decision of 2026-10-18). Its facts, shapes and IRIs are unchanged: it uses only the control relationship, which organization 2.0.0 keeps as it was.

## 1.0.0 (2026-10-13)

Approved by the subject matter expert on 2026-10-13 ("aprove now", saved in (the review comments of a subject matter expert reviewing the documents). The release is 1.0.0-rc.1 with the issued and modified dates set (2026-10-13) and the stage removed, and its requirement moved from organization 1.0.0-rc.1 to organization 1.0.0, released the same day; nothing else changed. the decision of 2026-10-13.

## 1.0.0-rc.1 (release candidate, not issued)

The first release candidate of the `ref-mpc` module. A module's first release is a major, so 1.0.0 is issued only when the decision owner approves it (module policy, 2026-09-18; the decision of 2026-10-13).

- MPC and MPLX with their LEIs, MPC's control of MPLX, MPC's three reportable segments and its 13 refineries, from the FY2025 Form 10-K and GLEIF (the decision of 2026-10-05, the decision of 2026-10-13).
- Depends on `organization` 1.0.0-rc.1 by IRI (the candidate it shipped with); imports nothing.

*Share release, 2026-11-04:* in this release the newest package is built against organization 2.2.0, party 2.1.0, the newest package of each module it requires (its `manifest.json` says so). The notes above that name organization 2.1.0, party 2.0.0 describe the pins at the time of the original release.
