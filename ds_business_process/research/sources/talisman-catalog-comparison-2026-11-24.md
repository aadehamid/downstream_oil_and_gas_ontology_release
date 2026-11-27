# Ontology Pipeline resource catalogue: comparison with the ontology skill and the DSBP survey

Source: J. Talisman, "Ontology Pipeline Resource Catalog", Intentional Arrangement (Substack), 18 October 2026; full text supplied by the owner on 2026-11-24 (kept privately in `talisman-resource-catalog-2026-10-18.md`, not for the repo). The catalogue is a pointer list: anything we adopt is cited to its own publisher, never to the catalogue, and none of its wording is copied.

## How it was compared

Each of the 263 entries in its standards, guidelines, schemas, vocabularies, registries and tools sections was matched by name against every file of the `ontology` skill (personal-agent-skills `skills/data/ontology`). 78 are already named there, including ANSI/NISO Z39.19, ISO 25964, RDF 1.2 and qSKOS. Most of the other 185 are domain vocabularies for libraries, health, agriculture or media, which no downstream oil and gas build needs. The ones that matter are below.

## Gaps for the skill (all industries)

| Gap | Entries | Why it matters | Gap-log row |
|---|---|---|---|
| Ontology quality scanners | OOPS! (OntOlogy Pitfall Scanner), FOOPS! and O'FAIRe (FAIR checks), SKOS Play, Skosify, SKOS-Utils | The skill names qSKOS only; these find common modelling pitfalls and FAIR gaps that our own checks don't | SG-15 |
| SKOS extensions | XKOS (statistical classifications, levels and correspondence tables), ISO-THES, SKOS-XL (labels as resources), OntoLex-Lemon | XKOS fits code lists and classification levels; SKOS-XL fits labels that need their own provenance | SG-16 |
| Graph canonicalization | W3C RDF Dataset Canonicalization (RDFC-1.0), 2024 | Gives a deterministic form for regression diffs and release checksums | SG-17 |
| Alignment evaluation | LogMap and the Ontology Alignment Evaluation Initiative | A way to propose and score mappings before they become SSSOM rows | SG-18 |
| Cross-industry vocabularies to check in every Step 0 | NAICS and ISIC, SDMX, IFRS Accounting Taxonomy, UNSPSC, GS1 Global Product Classification, ESCO, ITIL and TOGAF, PKO (Procedural Knowledge Ontology), DCAT-AP and ADMS, CSV on the Web | These recur in any industry: statistics, accounts, products, occupations, IT services, procedures, catalogues, tables | SG-19 |
| Registries | Research Data Alliance Metadata Standards Directory, LOD Cloud, BioPortal (life sciences), W3C SKOS Datasets wiki | More places for the Step 0 registry search | SG-08 (updated) |

## Leads for DS_Business_Process (added to the survey register as "to survey")

| Module | Lead | Use |
|---|---|---|
| KPI | SDMX and W3C Data Cube | Statistical measure and dimension structure for market and reported figures |
| KPI, finance | IFRS Accounting Taxonomy | Financial line items that refining-margin components decompose into |
| Products, procurement | UNSPSC, GS1 Global Product Classification | Product and purchased-goods codes |
| Organization and roles | ESCO | Occupation codes as a public basis for generic roles |
| Processes | PKO | Procedure and step structure, beside APQC and BPMN |
| IT and systems | ITIL, TOGAF content metamodel | Service and application vocabulary for the system module |

Licences for all of these are still to be read in full before any treatment is chosen.

Not relevant here: library cataloguing rules (AACR2, RDA, MARC), cultural-heritage, life-science and media vocabularies, AI taxonomies and agent-memory tools. The author's own SKOS editor is free only for small organizations, so it is not adopted as tooling.
