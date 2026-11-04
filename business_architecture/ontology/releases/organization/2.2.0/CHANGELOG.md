# organization changelog

## 2.2.0 (2026-10-28)

A minor release: it changes statements on three roles and removes no IRI. Approved by a subject matter expert. It carries the decision owner's close-out answers of 2026-10-28 (the decision of 2026-10-18, amendment of 2026-10-28; saved in (the review comments of a subject matter expert reviewing the documents).

- [minor] **PSM expanded.** `role:psm` takes the preferred label Process Safety Management, and "PSM" becomes an alternative label, as 2.0.0 did for the other acronyms (close-out point 8).
- [minor] **Crude RFC confirmed.** Crude Refinery Feedstock Coordinator's editorial note says the subject matter expert confirmed the reading of RFC; it is no longer a contextual reading pending confirmation (close-out point 7).
- [minor] **Business Planning and Analysis's definition confirmed.** Its editorial note says the subject matter expert confirmed the definition. The other three working definitions stay open with their managers (close-out point 9).
- It still requires core 2.3.0. `ref-mpc` 1.3.0 and `integration` 2.4.0 still require organization 2.1.0, which stays released as it is.

## 2.1.0 (2026-10-26)

A minor release: it adds statements and removes no IRI. Approved by a subject matter expert.

- [minor] **Top concepts both ways.** Each of the four RACI levels states `skos:topConceptOf orgm:RaciLevel`, and the scheme states `skos:hasTopConcept` for each. The code list is flat, so every level is a top concept; this fixes the qSKOS finding "Omitted Top Concepts" (the decision of 2026-10-25, item 5).
- It requires core 2.3.0, the current release (2.0.0 required core 2.1.0). `ref-mpc` 1.2.0 still requires organization 2.0.0, which stays released as it is.

## 2.0.0 (2026-10-18)

Major. Approved by the subject matter expert on 2026-10-18 ("Yes, approve 2.0.0 (Recommended)", saved in (the review comments of a subject matter expert reviewing the documents). It carries their answers to the role questions (the decision of 2026-10-18).

- Deprecated, never deleted: `role:rcvo-advisor` (replaced by `role:rvco-advisor`; "RCVO Advisor" becomes a hidden label, a misspelling), `role:refinery-technical-service-representative` (replaced by `role:refinery-technical-representative`) and `role:vp-clean-products-crude-trading-ngls-asphalt-petchem` (replaced by `role:vp-clean-products-rvco-crude-trading-ngls-asphalt-petchem`). Each keeps its triples and gains `owl:deprecated true` and `dcterms:isReplacedBy`. 60 roles, 57 live.
- Breaking: the three assignments that named a deprecated role now name its successor. They keep their IRIs and source text. 940 assignments, as before.
- Expanded names: ten roles take an expanded preferred label, with the source spelling kept as an alternative label: nine from the acronym answers (Refinery Value Chain Optimization Advisor, VP Refinery Value Chain Optimization, Continual Commercial Improvement Director, Clean Products Manager, Clean Products Value Chain Scheduler, Global Feedstocks Value Chain Manager, Economics and Planning Manager and Supervisor, Business Planning and Analysis), and Crude RFC, which becomes Crude Refinery Feedstock Coordinator and stays its own role.
- Added: definitions on four roles, and an editorial note with the evidence and its status on each answered role. Forecaster and PSM stay unresolved, each with its open question.
- Depends on `core` 2.1.0 by IRI, the current `core` release (1.0.0 depended on `core` 1.0.0). `ref-mpc` 1.1.0 requires this release.

## 1.0.0 (2026-10-13)

Approved by the subject matter expert on 2026-10-13 ("aprove now", saved in (the review comments of a subject matter expert reviewing the documents). The release is 1.0.0-rc.1 with the issued and modified dates set (2026-10-13) and the stage removed; nothing else changed. the decision of 2026-10-13.

## 1.0.0-rc.1 (release candidate, not issued)

The first release candidate of the `organization` module. A module's first release is a major, so 1.0.0 is issued only when the decision owner approves it (module policy, 2026-09-18; the decision of 2026-10-13).

- The vocabulary and shapes: `orgm:ResponsibilityAssignment`, the RACI level list and `orgm:ControlRelationship` (the decision of 2026-10-13).
- 60 roles from the role register (the decision of 2026-10-13).
- 940 RACI assignments on 153 processes, one per source entry and role (the decision of 2026-10-13).
- Depends on `core` 1.0.0 by IRI; imports nothing.

*Share release, 2026-11-04:* in this release the newest package is built against core 2.4.0, the newest package of each module it requires (its `manifest.json` says so). The notes above that name core 2.3.0 describe the pins at the time of the original release.
