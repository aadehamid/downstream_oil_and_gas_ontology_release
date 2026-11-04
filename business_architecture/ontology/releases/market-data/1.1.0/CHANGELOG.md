# market-data changelog

## 1.1.0 (2026-10-25)

A minor release: it adds classes, properties, prices, series and enumerations, renames one scheme's label, and removes no IRI. Approved by the decision owner with item F's release plan ("Approve the plan (Recommended)", saved in (the review comments of a subject matter expert reviewing the documents); the decision of 2026-10-25, the decision of 2026-10-25).

- [minor] **Market prices.** `mkt:MarketPrice`, `mkt:priceOf` and `mkt:reportedAs` name the prices the decision owner's pricing views report for the other pricing measures: 8 for Gasoline Market Pricing, 9 for Distillate Market Pricing, 15 for Crude Market Pricing (10 differentials and the benchmark view's 5 instruments) and 12 for Additional Market Prices (10 renewables, 2 NGLs). Four reuse a benchmark of the same name and market: LA CARBOB, USGC CBOB, USGC ULSD and NYMEX WTI (MPR 747) (the decision of 2026-10-25, item 4).
- [minor] **Where every series is listed.** `mkt:SeriesEnumeration` names, for each pricing measure, the view and the columns that list its complete set: for the crack spreads, the distinct `Price_Master_ID` of the crack-spread view, named by `Price_Master_Name` and grouped by `MIPS_Groups_Text` (127 series in 44 groups on 2026-10-25) (the decision of 2026-10-25, item 5).
- [minor] **Two NYMEX cracks,** Price Masters 44934 and 44935, with their legs unstated.
- [minor] **Top concepts** (the decision of 2026-10-25, item 5) for `mkt:Series`, `mkt:RefiningRegions`, `mkt:MarketRegions` and `mkt:BenchmarkKind`, stated both ways.
- [minor] **The series scheme's label and definition** now name the market prices it holds: `mkt:Series` is "market series and prices" (it was "benchmark series"), with a change note; the IRI is unchanged (the decision of 2026-10-25).
- It requires kpi 1.2.0.

### Known gaps

- **Completeness of series.** Only the named series carry definitions; the rest are known only through the views' columns, which the enumerations name (the decision of 2026-10-25, Known gaps).
- **The 40 new market prices' definitions are built from the agents' filters,** which name each price and its group, not from a source's own words; each says so in an editorial note.

## 1.0.0 (2026-10-22)

The module's first release, a major. Approved by the decision owner with the release plan ("release plan approved", saved in (the review comments of a subject matter expert reviewing the documents); the decision of 2026-10-22). It holds the 13 published series of the kpi module's crack-spreads measure, with MPC Economics' definition as the primary source: six regional ex-RIN 3-2-1 series, the NYMEX 3-2-1, two MPC-weighted blends and MPC's four 10-K cracks, with their 24 benchmarks and regions (the decision of 2026-10-19, the decision of 2026-10-20). Definitions only, never prices. It requires kpi 1.0.1.

*Share release, 2026-11-04:* in this release the newest package is built against kpi 1.3.0, the newest package of each module it requires (its `manifest.json` says so). The notes above that name kpi 1.2.0 describe the pins at the time of the original release.
