# Release checks

`dsbp_checks.py` holds the checks that every DS_Business_Process change must pass (decision DSBP-DEC-0011). Each check returns a list of failures; none means it passed.

| ID | What it proves | How the tests show it can fail |
|---|---|---|
| V1 | Every KPI Store 1.2 release manifest in `../registers/baseline-manifests.csv` is present with its recorded SHA-256, and every file it lists still matches its hash | One byte changed in a copy; a manifest deleted; a manifest edited |
| V2 | Each baseline process has exactly one row in the migration map, with a known status, and each living concept has its own neutral new ID of the form `DSBP-P-000123` (DSBP-DEC-0031), is in the candidate, and its old IRI is gone; a row is `deprecated` exactly when the concept is `owl:deprecated`; an excluded concept has no new IRI and is gone | A dropped row, a duplicate row, an unknown status, an exclusion with no reason, an old code carried over, two concepts under one new ID, an old IRI left beside the new one, a deprecation the map does not record |
| V3 | Only concepts on the batch's approved list changed, were excluded or are new; any other named subject (a class, a property, the ontology header) whose statements changed is on the list too. The list may name old codes or new IDs. A move of a term to the new namespace is not a change. `--ignore` names predicates a batch changes everywhere by an approved rule, such as `skos:notation`. A blank node is compared by its content and how many times it occurs, so an edit inside one, or a second copy of one, is a change, and a new blank-node label is not. Blank nodes that nothing points at, such as an `owl:AllDisjointClasses` axiom, are compared together. A missing list file is an error, and a line that starts with `#`, indented or not, is a comment | A label changed outside the list; a class comment added; a note inside a blank node edited; a blank node doubled; an axiom added |
| V4 | No cycles; one parent below the top, and it is a process; one level, not negative, its parent's plus one; `skos:narrower`, where given, is the exact inverse of `skos:broader`; every level is an integer literal; every concept has one preferred label per language, none blank, and no other concept has the same label (one concept's label in two languages is not a clash); every live concept has one non-blank definition; SHACL shapes conform when given | A cycle, a second parent, a level jump, a level that is not an integer, a blank or doubled label, a duplicate label, a missing label, a deleted definition, a narrower link with no matching broader |
| V5 | No term from `../registers/company-terms.csv` appears in any literal of the candidate, on any subject and any property, the ontology header included, or in any IRI. An IRI is read in any letter case and split into words at marks and case changes, so `hasXpimsId` and `https://w3id.org/mpc/` are hits; a term of five letters or more is also found inside a run of letters, as in `marathonpetroleum.com`. Only a letter or digit joins a word, so `XPIMS_run` matches. `skos:example`, and a cited source's title, description, publisher, URL and IRI, may name a company, never a company-built system. The IRI is exempt only where it is cited (as the object of `dcterms:source`, the subject of any statement about the source, such as its record or its `rdf:type`, or a URL given as its identifier; the same IRI as the object of another statement is not exempt), and never when this project or its predecessor minted it, so a source named under `https://w3id.org/mpc`, with or without a path, still fails. An IRI the ontology models is never a cited source, even as the object of `dcterms:source`: one that is the subject of an OWL or SKOS statement or of a class or property axiom, or that has a type from OWL, SKOS or RDF Schema, such as a concept, class, property or ontology header. Nor is a subject that cites itself. No literal carries the predecessor's parked-tree-change codes, such as `PTC-001`, in any letter case, and none outside a cited source's record or an example carries a working file name ending in `.md`, `.xlsx`, `.xlsm`, `.csv`, `.json`, `.py`, `.ipynb`, `.docx` or `.pptx`. A web address is not read as a file name. A phrase in `../registers/company-terms-allowed.csv` (a generic meaning of the same letters, such as "days payable outstanding (DPO)") is not a hit. It reads one graph, so each migrated module is checked on its own | "XPIMS" put back into a label, an example, a class comment, the ontology header or an IRI, in any letter case; "PTC-001" or a working file name in a note |
| V6 | Every new or changed definition, on any subject, cites a public source with title, publisher, URL, version or issue date, and access date, none blank, and cites no internal source beside it (see "How a source is recorded" below). An IRI this project minted is not a URL. The internal workbook never counts, in any case or in the identifier; a `urn:` source IRI is internal, while a `urn:` identifier such as an ISBN is allowed | A missing access date; the workbook given as the source, alone or beside a public one; a new class with no source |
| V7 | The baseline's process-to-process statements (core properties and `skos:related`) still hold under the new IRIs, for approved concepts too. A statement may go only when one end is excluded or the batch lists it in `--removals` | One statement deleted |
| V8 | The HermiT reasoner finds the candidate consistent. `owl:imports` is left out, so the reasoner reads the candidate alone, and a file it cannot load is a failure, not a crash | Two disjoint classes sharing a member |
| V9 | The competency questions still return their expected answers | Not built yet; it comes with batch B1. Until then it counts as a failure unless `--skip V9` is given |

## Run them

From the repository root:

```bash skip reason="illustration: the angle brackets stand for your own files"
uv run --with rdflib --with pyshacl --with owlready2 python ds_business_process/validation/dsbp_checks.py \
    --candidate <candidate.ttl> --map <migration-map.csv> --approved <approved.txt> [--shapes <shapes.ttl>]
uv run --with rdflib --with pyshacl --with owlready2 --with pytest python -m pytest ds_business_process/validation
```

V8 needs Java for HermiT. Without a working Java, `scripts/check.sh` still runs every test, but the V8 tests that need the reasoner are skipped, and pytest's summary counts them as skipped. Install a Java runtime to run them.

## How a source is recorded

A definition cites its source with `dcterms:source`. The source is its own subject, with these statements:

| What | Property | Example |
|---|---|---|
| Title | `dcterms:title` | "Petroleum Supply Annual, Volume 1" |
| Publisher | `dcterms:publisher` | "U.S. Energy Information Administration" |
| URL | `dcterms:identifier`, a web address (or the source's own IRI, when that is one) | `https://www.eia.gov/petroleum/supply/annual/volume1/` |
| Version or issue date | `dcterms:hasVersion` or `dcterms:issued` | "2025" |
| Access date | `dsbp:accessDate` (`https://w3id.org/ds-bp/ontology/accessDate`), an `xsd:date` | "2026-11-27"^^xsd:date |

V6 accepts an access date written as a real calendar date, `YYYY-MM-DD`, typed as `xsd:date` or not; any other text, such as "last week" or 2026-02-31, is no access date.

Dublin Core has no term for the day a reader opened a source, so this project defines `dsbp:accessDate`. The release's ontology header declares it as an `owl:DatatypeProperty` with the range `xsd:date` when the first sourced batch (B5) lands. V6 reads it under that IRI only.

## What the baseline gives today

Renamed to the new IDs and otherwise unchanged (the tests' identity candidate), the baseline passes V1, V2, V3, V6, V7 and V8. It fails V4 on two live concepts with no definition (CM-1-1-3-5-3 and CM-1-1-4-6-1). It fails V5 1,458 times: 343 literals that name company terms, mostly XPIMS (163), DPO (88) and MPC (62); 49 literals that carry the predecessor's working trace, such as `PTC-001` and `step4-decisions.md`; and 1,066 IRIs that still sit under the predecessor's namespace `https://w3id.org/mpc/` (its module properties and classes, facts, sequences and sources), which must move to `https://w3id.org/ds-bp/` or leave before release. V5 reads every literal on every subject, examples included. V9 is not built, so the command fails until it is, unless it is skipped. Those are the failures the batches are there to remove.

## Limits

- V5 reads the RDF only. The check of every migrated text file (done line 5 of `../GOAL.md`) is still to be built.
- V5 finds only the terms in the register. A company reference written another way passes.
- V7 compares direct statements between processes, in the core namespace and `skos:related`.
- V3 compares a blank node through the named subject that points at it. Blank nodes that no named subject reaches are compared as a group, by content and count, a detached loop of them included; one whose every statement is on an ignored property is left out. A blank node that two statements share is compared as two copies of its content, so sharing one blank node and using two equal ones look the same.
