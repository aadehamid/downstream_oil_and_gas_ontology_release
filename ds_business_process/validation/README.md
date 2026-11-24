# Release checks

`dsbp_checks.py` holds the checks that every DS_Business_Process change must pass (decision DSBP-DEC-0011). Each check returns a list of failures; none means it passed.

| ID | What it proves | How the tests show it can fail |
|---|---|---|
| V1 | Every KPI Store 1.2 file still matches the SHA-256 hash in its manifest | One byte changed in a copy |
| V2 | Each baseline process has exactly one row in the migration map, with a known status, and each living concept has its own neutral new ID of the form `DSBP-P-000123` (DSBP-DEC-0031) and is in the candidate; an excluded concept has no new IRI and is gone | A dropped row, a duplicate row, an unknown status, an exclusion with no reason, an old code carried over, two concepts under one new ID |
| V3 | Only concepts on the batch's approved list changed, were excluded or are new. The list may name old codes or new IDs. A move of a property to the new namespace is not a change. A missing list file is an error | A label changed outside the list |
| V4 | No cycles; one parent below the top, and it is a process; one level, not negative, its parent's plus one; unique preferred labels; every live concept has one non-blank definition; SHACL shapes conform when given | A cycle, a second parent, a level jump, a duplicate label, a deleted definition |
| V5 | No term from `../registers/company-terms.csv` appears in any reader-facing text, on any subject. `skos:example` may name a company, never a company-built system. It reads one graph, so each migrated module is checked on its own | "XPIMS" put back into a label, an example or a class comment |
| V6 | Every new or changed definition cites a public source with title, publisher, URL, version or issue date, and access date, none blank. An IRI this project minted is not a URL. The internal workbook never counts, in any case or in the identifier | A missing access date; the workbook given as the source |
| V7 | The baseline's process-to-process statements still hold under the new IRIs, for approved concepts too. A statement may go only when one end is excluded or the batch lists it in `--removals` | One statement deleted |
| V8 | The HermiT reasoner finds the candidate consistent | Two disjoint classes sharing a member |
| V9 | The competency questions still return their expected answers | Not built yet; it comes with batch B1 |

## Run them

From the repository root:

```bash skip reason="illustration: the angle brackets stand for your own files"
uv run --with rdflib --with pyshacl --with owlready2 python ds_business_process/validation/dsbp_checks.py \
    --candidate <candidate.ttl> --map <migration-map.csv> --approved <approved.txt> [--shapes <shapes.ttl>]
uv run --with rdflib --with pyshacl --with owlready2 --with pytest python -m pytest ds_business_process/validation
```

V8 needs Java for HermiT.

## What the baseline gives today

Renamed to the new IDs and otherwise unchanged (the tests' identity candidate), the baseline passes V1, V2, V3, V6, V7 and V8. It fails V4 on two live concepts with no definition (CM-1-1-3-5-3 and CM-1-1-4-6-1). It fails V5 on 343 mentions of company terms, mostly XPIMS (163), DPO (88) and MPC (62). V5 reads every subject and every reader-facing property, examples included. Those are the failures the batches are there to remove.

## Limits

- V5 reads the process concepts' text in RDF only. The check of every migrated text file (done line 5 of `../GOAL.md`) is still to be built.
- V5 finds only the terms in the register. A company reference written another way passes.
- V7 compares direct statements between processes in the core namespace.
