# Step 8: scope review

Reviewed 2026-11-24 against the purpose in `requirements.yaml`. Approved by the owner on 2026-11-27 with the line that places the H-10 work (DSBP-DEC-0046). The calls rest on the round 2 decisions and on DSBP-DEC-0008 and 0032 (complete every downstream area). "In" means the area is part of the reference; an area a given company does not run stays in the reference and that company leaves it empty.

## Process areas (L1, after round 2)

| Candidate area | Call (in / out) | Hook or reason | Boundary note (out only) | Revival trigger (out only) |
|---|---|---|---|---|
| Refining | in | CQ1, CQ2; a thin area to complete (DSBP-DEC-0008) | | |
| Commercial & Marketing, with Planning, Scheduling & Optimization; Supply & Trading; Marketing, including Retail | in | CQ1 to CQ4; DSBP-DEC-0016, 0020, 0024, 0028 | | |
| Midstream & Logistics | in | DSBP-DEC-0025; Terminal Loading moved here (0021) | | |
| Lubricants & Specialties | in | DSBP-DEC-0030 | | |
| Petrochemicals | in | DSBP-DEC-0030 | | |
| Finance | in | DSBP-DEC-0008 | | |
| Human Resources | in | DSBP-DEC-0008 | | |
| Procurement & Supply Chain (Goods and Services) | in | DSBP-DEC-0012 | | |
| Information Technology | in | DSBP-DEC-0017 | | |
| Business Process Excellence | in | DSBP-DEC-0017 | | |
| Legal & External Affairs | in | DSBP-DEC-0029 | | |
| Environment, Health & Safety, with regulatory reporting | in | DSBP-DEC-0019 | | |
| Strategy & Business Development | in | DSBP-DEC-0026 | | |
| Enterprise Risk Management | in | DSBP-DEC-0027 | | |
| Downstream-adjacent work from the vision (H-10): crude gathering and NGL fractionation under Midstream & Logistics; power trading under Supply & Trading | in | `../VISION.md`; DSBP-DEC-0043 (H-10) and 0046. The placement, and where crude gathering meets the Upstream fence, need an evidence row (a standard, or the public disclosures of 3 or more independent companies) before a batch adds these processes | | |
| Shared Services | out | None of the companies in the peer research names it as a process area; two of them (PBF and Chevron) use it for how work is delivered (DSBP-DEC-0018) | Work delivered by a shared-services centre sits under the process area it serves, such as Finance or HR; nothing depends on a Shared Services node | A standard or 3 or more independent companies that name shared services as a process area |
| Renewable fuels as its own area | out | Decided as a product line, not a process area (DSBP-DEC-0023). Six companies report a renewables segment; that the same Commercial and Refining processes run it is an inference, not a verified fact | Renewable feedstocks and products are named inside the Commercial and Refining processes | Evidence that renewable fuels run on processes the existing areas cannot hold |
| Upstream (exploration and production) | out | Not downstream; the purpose names downstream only | Crude enters the reference at crude gathering under Midstream & Logistics, or at crude supply under Supply & Trading. Where gathering meets this fence is set with the H-10 evidence row | A decision to extend the reference upstream |

## Companion modules (DSBP-DEC-0010)

| Candidate area | Call (in / out) | Hook or reason | Boundary note (out only) | Revival trigger (out only) |
|---|---|---|---|---|
| KPI and measures | in | CQ2; DSBP-DEC-0033 | | |
| Organization: roles and RACI | in | CQ3; DSBP-DEC-0033 | | |
| System categories, with off-the-shelf products as examples | in | CQ4; DSBP-DEC-0034 | | |
| Data products, logical model, technical graph, integration, lane, market data, party, value stream | in | DSBP-DEC-0010; each gets its competency questions at its module review | | |
| The predecessor's real-organization reference module | out | Company instances are out of scope (policy 2) | It stays in 1.2 only; a company specialization may add its own `ref-<organization>` module later | A company specialization |
| Company extensions and instances | out | Policy 2; the project's safeguards | A company specialization holds them | The first company specialization |
| Event records and measure values | out | "Define, don't record" (policy 2) | They stay in consumers' systems | None: a standing rule |
