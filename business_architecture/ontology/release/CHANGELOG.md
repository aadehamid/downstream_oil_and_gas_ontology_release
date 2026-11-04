# core changelog

## 1.0.0 (2026-10-13)

Approved by the subject matter expert on 2026-10-13: the release design (the decision of 2026-10-13), the conservation ledger, a fresh no-consumer attestation and the release.

The first release of the `core` module (the decision of 2026-10-05, built as the decision of 2026-10-13 decides).

- The process taxonomy, with every `intake:` field migrated to its `core` target. No `intake:` triple remains; `conservation.csv` records where each one went.
- The canonical relationship facts as direct triples on nine predicates. Their provenance (source rows, raw verbs, notes) is in `canonical-facts.csv`.
- The scoped sequences (the decision of 2026-10-12).
- Eight code lists: concept kind, APQC mapping decision, operating mode, cadence, planning level, and the three Q9 status lists.
- Cited sources and APQC elements are IRI resources; the release holds no blank nodes.
- The SHACL release slice (`release/shapes.ttl`) conforms.
