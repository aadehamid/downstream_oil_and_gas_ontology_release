# Policies

Recorded 2026-11-24, by the ontology skill's Step 1 (`references/foundations.md`). Requirements file: `requirements.yaml`.

Rows 5, 6, 8 and 10 carry 1.2's policy over unchanged, as the owner confirmed (DSBP-DEC-0036). Step 1 closes only when no row says ASSUMED.

| # | Policy | Choice | Reason | Decided by |
|---|---|---|---|---|
| 1 | Competency questions | Locked list in `competency-questions.md`, drafted from 1.2's 55 locked questions with company names taken out and industry questions added | The acceptance test (Step 11) | ASSUMED, not yet answered (Q-CQ: the owner locks the list) |
| 2 | Data scope | Concepts, definitions, relationships, typical measures and typical RACI by generic role. No event records, observed values, company instances or company extensions | Records belong in consumers' systems; the reference must stay company-agnostic | DSBP-DEC-0033; the project's safeguards (company extensions and instances out of scope) |
| 3 | Evidence order | 1. standards and sector bodies, which drive the design; 2. public disclosures of 3 or more independent companies, which validate it; 3. sector-specific sources such as government agencies and price-reporting agencies; 4. generic frameworks, such as APQC, as a crosswalk only. Private company material may show what exists and is never cited | The reference must hold for the industry, not for one company | DSBP-DEC-0002, 0005, 0032 |
| 4 | URI policy | Base `https://w3id.org/ds-bp/`, a placeholder that is not registered until hosting is approved. Processes are `…/ontology/process/DSBP-P-000123`, an ID that says nothing about place. Old IRIs and codes live only in the migration map | A rename or a move changes no IRI | DSBP-DEC-0003, 0031 |
| 5 | Language | Primary `en`; every language-text literal tagged; one `skos:prefLabel` per language; a `skos:definition` on every concept | Tagged and untagged literals are different RDF terms | DSBP-DEC-0036 |
| 6 | Version | Semantic versioning per module and per release; deprecate, never delete | Consumers pin versions | DSBP-DEC-0036 |
| 7 | Licence | Open: CC BY 4.0, with the APQC/IBM notice kept | An industry reference is meant to be reused | DSBP-DEC-0009 |
| 8 | Modules | The 12 modules of 1.2 (`core`, `data-product`, `integration`, `kpi`, `lane`, `logical-model`, `market-data`, `organization`, `party`, `system`, `technical-graph`, `value-stream`), with 1.2's one-way dependencies and no cycle. `ref-mpc` stays in 1.2 only | A cycle blocks releasing a module alone | DSBP-DEC-0010 for the list; DSBP-DEC-0036 for the dependencies |
| 9 | Consumers | No active consumer of DS_Business_Process yet; 1.2's consumers stay on 1.2 | Release rules depend on it; only the owner can state it | ASSUMED, not yet answered (Q-P2) |
| 10 | Target formats | RDF plus a property-graph projection (Neo4j), with Rule 4 option 4a, qualified-relation nodes | The release loads into Neo4j and Fuseki (done line 11); the validator is pySHACL, which does not read RDF 1.2 reifiers | DSBP-DEC-0036 |

## Questions for the owner

- **Q-P1.** Answered: carry them over (DSBP-DEC-0036).
- **Q-P2.** Confirm that DS_Business_Process has no active consumer yet, so its first release is 1.0.0 with no migration duty to consumers.
- **Q-CQ.** Lock the competency questions once they are drafted.
