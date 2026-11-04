# lane changelog

## 1.1.0 (2026-10-26)

A minor release: it adds statements and rewords a shape message, and removes no IRI. Approved by a subject matter expert.

- [minor] **Top concepts both ways.** Each of the four lanes states `skos:topConceptOf lane:OfficeLanes`, and the scheme states `skos:hasTopConcept` for each. The code list is flat, so every lane is a top concept; this fixes the qSKOS finding "Omitted Top Concepts" (the decision of 2026-10-25, item 5).
- [patch] **A shape message without an apostrophe.** "A process's lane is one of the four office lanes." becomes "The lane of a process is one of the four office lanes.", because n10s writes `sh:message` into Cypher unescaped and a single quote breaks its validator (the `ontology` skill's SHACL rule 19, a change to the skills folder).
- It requires core 2.3.0, the current release (1.0.0 required core 2.2.0).

## 1.0.0 (2026-10-22)

The module's first release, a major. Approved by the decision owner with the release plan ("release plan approved", saved in (the review comments of a subject matter expert reviewing the documents); the decision of 2026-10-22). It holds the four office lanes as a code list and the seven processes the process map places in them; nothing is inherited down the tree (the decision of 2026-10-19). It requires core 2.2.0.

*Share release, 2026-11-04:* in this release the newest package is built against core 2.4.0, the newest package of each module it requires (its `manifest.json` says so). The notes above that name core 2.3.0 describe the pins at the time of the original release.
