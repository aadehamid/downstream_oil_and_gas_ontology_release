# DS_Business_Process

A company-agnostic, industry-validated business process ontology for downstream oil and gas. It is generalized from KPI Store 1.2 (branch `kpi-store/1.2`, commit `ddf6b68`), which stays unchanged as the baseline.

Status: the foundations (Steps 0, 1 and 8) are drafted, and batch B3, the first change to the process hierarchy, is built and waiting for its review. No release has been made yet. `BUILD-STATUS.md` has the detail.

- `GOAL.md`: what "done" means for release 1.0.
- `registers/decision-register.md`: every decision, with the owner's words.
- `registers/company-terms.csv`: the company terms that must not appear in the reference layer, and `company-terms-allowed.csv`, the generic phrases that share their letters.
- `registers/baseline-manifests.csv`: the KPI Store 1.2 release manifests that check V1 keeps unchanged.
- `validation/`: the release checks and their tests.
- `research/`: the peer hierarchy research (`peer-hierarchy-findings.md` and its evidence CSV, from public filings), the comparison of the Ontology Pipeline catalogue with the skill (`sources/`), and the registry searches of Step 0 (`local-review/`).

The plan and the baseline assessment were shared privately with the decision owner. What later work needs from them is in `registers/decision-register.md` and `foundations/`.
