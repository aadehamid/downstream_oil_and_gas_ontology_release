# DS_Business_Process

A company-agnostic, industry-validated business process ontology for downstream oil and gas. It is generalized from KPI Store 1.2 (branch `kpi-store/1.2`, commit `ddf6b68`), which stays unchanged as the baseline.

Status: the policies and competency questions (Step 1) and the scope review (Step 8) are decided, Step 0 is drafted, and batch B3, the first change to the process hierarchy, is built and approved; it runs once its Step 3 gate is added (DSBP-DEC-0045). No release has been made yet. `BUILD-STATUS.md` has the detail.

- `GOAL.md`: what "done" means for release 1.0.
- `registers/decision-register.md`: every decision, with the owner's words.
- `registers/company-terms.csv`: the company terms that must not appear in the reference layer, and `company-terms-allowed.csv`, the generic phrases that share their letters.
- `registers/baseline-manifests.csv`: the KPI Store 1.2 release manifests that check V1 keeps unchanged.
- `validation/`: the release checks and their tests.

The plan and the baseline assessment were shared privately with the decision owner. What later work needs from them is in `registers/decision-register.md` and `foundations/`.

The working research that the decisions and batch files cite under `research/` (the peer hierarchy findings and their evidence table, the registry searches of Step 0, and the catalogue comparison) is kept in the project's working files, outside this public repository, because it discusses the internal structure of the 1.2 baseline. Its public evidence enters the release only as source records on the concepts, which check V6 reads. A company-neutral evidence table for the hierarchy comes with batch B5.
