# Peer hierarchy findings: how downstream companies name and place their business areas

Access date for every source: 2026-11-24. Evidence rows: `peer-hierarchy-evidence.csv` (181 rows, 30 distinct sources), in this folder.

## Summary

I read primary sources for 19 companies: 9 independent refiners (Valero, MPC, Phillips 66, HF Sinclair, PBF, Delek, CVR, Par Pacific, Calumet), 4 integrated majors (ExxonMobil, Chevron, Shell, bp), 3 midstream companies (MPLX, Plains, Kinder Morgan) and 3 marketers (Sunoco, Global Partners, World Kinect). I also read APQC PCF Downstream Petroleum 7.2.2 and the EIA glossary as standards. The sources were mainly FY2025 10-Ks and 20-Fs, with some company web pages and reports. Across them, the downstream value chain splits the same way:
- **Supply and trading** (often called "Commercial")
- **Refining**
- **Logistics or Midstream**
- **Marketing**, with retail split out where the company runs stores
- **Renewables**, a separate segment at 6 companies
- **Corporate**, which holds the enabling functions

The baseline's two L0s hold up. So do these L1s: Refining, Midstream, and a Commercial L1 that holds planning, supply and trading, and marketing.

Four baseline placements have no support:
- No company puts IT under Commercial.
- No company has a "Shared Services" business area.
- "Supply Chain Mgmt." means procurement of goods and services when it is an enabling function. The hydrocarbon supply chain sits with supply and trading.
- "Terminal Loading" sits with terminals and midstream, not with marketing.

The evidence splits on one question: where planning and optimization go. Three companies put optimization with supply and trading or Commercial (PBF, Phillips 66, Shell). MPC has a standalone "Value Chain Optimization" executive. APQC puts planning under Deliver Physical Products and production scheduling under Produce. The recommendations below follow the rule "3 or more independent companies, or a standard".

A caution on the evidence: segment notes describe reporting structure. Executive titles and company pages describe how the work is organized. Where the two differ, the findings say so.

## Method

- Item 1 (Business), segment lists, MD&A segment descriptions and executive officer lists, read with Firecrawl `filings/sections` and direct-quote scrapes of the EDGAR documents. Where the scraper read only the first part of a long 10-K, I targeted the passage instead.
- Company web pages for org evidence that filings do not carry: the HF Sinclair leadership page, a Phillips 66 Commercial job page, the supplier pages of Valero, Phillips 66 and Chevron, and two MPC responsibility reports.
- APQC workbook: the local copy, read with openpyxl. EIA glossary: eia.gov pages R, D and W.
- Every row in the CSV carries a verbatim quote of 40 words or fewer and a source you can open. My reading of a source is in the `note` column. Where it is interpretation, it is marked "Inference".
- Executive rows record titles only, without the person's name.

## Findings by baseline node

Counts are companies, not rows. "Support" means the company uses the same or an equivalent name in the same place.

### L0 Downstream Operations / L0 Enabling Functions

- **Support for the split: 6 companies and APQC.** The 6 companies separate the operating businesses from a corporate unit:
  - Calumet: "Corporate segment"
  - Par Pacific: "Corporate and Other"
  - ExxonMobil: "Corporate and Financing … general administrative support functions"
  - Phillips 66: Corporate holds "enterprise information technology assets"
  - Chevron: the parent "provides administrative, financial, management and technology support"
  - World Kinect: corporate expenses are allocated to segments

  APQC also separates operating categories (1.0 to 6.0) from support categories (7.0 to 13.0).
- **Names used:** companies say "Corporate". None says "Enabling Functions". "Downstream" is the integrated majors' word (Chevron "Downstream operations"). Independents just list their segments.
- **Recommendation: keep both L0s.** The names are fine for a company-agnostic model. If an industry word is wanted, "Corporate" is the term that 5 or more companies use.

### L1 Commercial & Marketing (CM 1)

- **Commercial as an executive function separate from refining: 5 companies.**
  - MPC: "Chief Commercial Officer"
  - Phillips 66: "Executive Vice President, Marketing and Commercial"
  - HF Sinclair: "Executive Vice President, Commercial"
  - PBF: "Senior Vice President, Supply, Trading and Optimization"
  - Valero: "Senior Vice President Product Supply, Trading and Wholesale"
- **Marketing under the same executive as supply and trading:** Phillips 66 and Valero say so. MPC is Inference: the CCO's scope is not stated.
- **Marketing as a separate reporting segment from refining:** Phillips 66 (M&S), HF Sinclair (Marketing) and Shell (Marketing).
- **Marketing inside the refining segment:** MPC (Refining & Marketing), Valero, PBF, Delek, CVR ("refining and marketing"), Chevron (Downstream) and ExxonMobil (Energy Products, which covers "refining, logistics, trading, and marketing").
- **Recommendation: keep the L1, and consider renaming it "Commercial".**
  - "Commercial" is used by 3 companies: MPC, Phillips 66 and HF Sinclair.
  - Holding marketing under it is supported at the org level by 3 companies (Phillips 66, Valero and, as Inference, MPC). It matches APQC 3.0 Market and Sell, which holds both 3.5 sales and 3.6 trading.
  - Keep "& Marketing" if the owner wants marketing visible at L1. Either name is defensible.

#### L2 CM 1.1 Planning & Scheduling

- **Under Commercial: 3 companies.**
  - PBF: optimization is in "Supply, Trading and Optimization".
  - Phillips 66: the Commercial organization does "asset optimization", and its roles include "scheduler", "logistics coordinator" and "marine operations and chartering".
  - Shell: "trading and optimisation of crude oil, oil products and petrochemicals" sits in Chemicals and Products, with the refineries and the trading.
- **Standalone: 1 company.** MPC has a "Senior Vice President Value Chain Optimization".
- **Standard: APQC** places 4.1 "Plan for and align supply chain resources" under 4.0 Deliver Physical Products. That L2 covers demand, supply network, master production schedule, distribution requirements and commodity values. APQC places 4.3.1 "Schedule production" under 4.3 Produce.
- **Recommendation: keep it under Commercial, and rename it "Planning, Scheduling & Optimization".** The placement meets the 3-company rule. The rename names the optimization work that PBF, Phillips 66, Shell and MPC all name. MPC's standalone function is the dissent. Record it as a valid alternative (a separate L1 "Value Chain Optimization") rather than the default.

#### L2 CM 1.2 Supply And Trading

- **Support: 6 companies and APQC.**
  - PBF: "Supply, Trading and Optimization".
  - Valero: "Product Supply, Trading and Wholesale".
  - Shell: "trading and optimisation".
  - ExxonMobil: "trading" in Energy Products.
  - MPC: its Canadian subsidiary's "business purpose is to trade and supply crude oil and other petroleum products as needed for and related to the MPC refining system".
  - Plains: "merchant activities include the purchase of crude oil supply".
  - APQC: 3.6 Trade commodity products and 3.7 Manage commodity positions, under 3.0 Market and Sell.
- **Placement of crude supply:** in filings, crude and feedstock supply appears as a sub-heading under the refining segment. Examples are Valero "Feedstock Supply", MPC "Crude Oil Supply" and HF Sinclair "Crude Oil and Feedstock Supplies". At the org level it sits with Commercial: Phillips 66 "sourcing advantaged feedstocks to our refineries", plus PBF and Valero. This is the reporting-versus-organization gap noted in the summary.
- **Recommendation: keep it.** Rename it "Supply & Trading", which is the companies' wording. CM 1.2.5 to 1.2.7, the hydrocarbon supply chain, stay here. See the supply chain section.

#### L2 CM 1.3 Marketing

- **Support: 9 companies.** Valero, MPC, Phillips 66, HF Sinclair, Delek, CVR, Sunoco, Global Partners and Shell use "marketing" or an equivalent sales term. The channels they name are wholesale, rack, branded, unbranded, jobber, dealer, commission agent and commercial or end user. EIA defines rack, DTW, reseller and retailer, and APQC has 3.5.3 "Manage wholesale/rack accounts".
- **Retail as a separate unit: 6 companies.**
  - Par Pacific: a Retail segment.
  - Shell: Mobility, under Marketing.
  - Global Partners: GDSO.
  - Sunoco: inside Fuel Distribution.
  - Chevron: counts "Service Station Employees".
  - World Kinect: "cardlock and retail activities".
  - MPC and Delek sold their retail businesses.
- **Recommendation: keep it.** Add an optional L2 or L3 "Retail" under this node so that the model stays company-agnostic. 6 companies run retail; MPC does not, so the node can stay empty for MPC. "Wholesale" and "branded" are the commonest channel words, so use them in the L3 names.

#### L2 CM 1.4 IT Services

- **Support for IT under Commercial: 0 companies.** Everywhere it appears, IT sits with corporate:
  - MPC: "Chief Digital Officer", a corporate executive.
  - Phillips 66: "enterprise information technology assets" in Corporate.
  - Valero: "information services personnel", a separate group.
  - World Kinect: a CIO.
  - Chevron: the parent provides "technology support".
  - HF Sinclair: "President, Growth, Technology & Transformation".
  - APQC: 8.0 Manage Information Technology, a support category.
- **Recommendation: move it to Enabling Functions as "Information Technology".** It is empty, so nothing below it moves.

### L1 Midstream (MS 1)

- **Name "Midstream": 3 companies** (MPC, Phillips 66, HF Sinclair).
- **Name "Logistics": 4 companies.** PBF, Delek and Par Pacific use "Logistics", and MPLX uses "Crude Oil and Products Logistics".
- **Logistics as its own segment: 10 companies.** MPC, Phillips 66, HF Sinclair, PBF, Delek, Par Pacific, Sunoco ("Pipeline Systems" and "Terminals"), MPLX, Plains and Kinder Morgan.
- **Logistics inside another segment:**
  - CVR: "crude gathering and logistics" in the Petroleum segment.
  - Global Partners: logistics in Wholesale.
  - Shell: "the pipeline business" in Chemicals and Products.
  - Chevron and ExxonMobil: inside Downstream or Energy Products.
- **Recommendation: keep the L1.** Both names pass the rule. "Midstream & Logistics" would cover both wordings. Note that for an integrated refiner without a logistics affiliate, this L1 holds internal logistics, not a services business.

#### L2 MS 1.1 to 1.4 (Pipeline, Terminal, Marine, Storage services)

- **Support: 5 midstream companies.**
  - MPLX: "Transportation Services Agreements, Storage Services Agreements, Terminal Services Agreements and Fuels Distribution Services Agreement"; marine is listed in the agreements table.
  - Phillips 66: "transportation, terminaling and storage services".
  - Plains: "gathering and transporting … terminalling, storage".
  - Kinder Morgan: terminals, including "Jones Act-qualified product tankers".
  - PBF: "receiving, handling, storage and transferring".
- **Recommendation: keep all four.**
  - Kinder Morgan files marine under Terminals. That is a single company, so not enough to merge Marine into Terminals.
  - Consider an optional "Fuels Distribution Services" L2. Its only source is MPLX, so it does not meet the rule.

### L1 Refining (RF 1)

- **Support: 11 companies name refining as a segment, a sub-unit or an executive function**, and EIA defines "Refiner" and "Refinery". They are MPC, Valero, Phillips 66, HF Sinclair, PBF, Delek, CVR ("refining and marketing" in Petroleum), Par Pacific, Sunoco ("Refinery"), Chevron ("refining crude oil" in Downstream) and ExxonMobil ("refining" in Energy Products).
  - Executive titles: "Executive Vice President Refining" (MPC), "Executive Vice President, Refining" (Phillips 66), "Senior Vice President, Head of Refining" (PBF). Valero and HF Sinclair use operations titles instead: Valero's "Executive Vice President and Chief Operating Officer" and HF Sinclair's "Senior Vice President, Operations". "Operations" is the alternative name, used by 2 companies.
- **Recommendation: keep "Refining".**

#### L2 RF 1.1 Refinery Performance and Risk Coordination; RF 1.2 Refinery Asset Reliability and Turnaround Coordination

- **Turnarounds named as refining activities: 5 companies** (MPC, PBF, Phillips 66, Delek, CVR).
  - Delek defines a turnaround as "A periodic shutdown of refinery process units to perform routine maintenance".
  - APQC puts maintenance in 10.3 "Maintain productive assets".
- **Recommendation: keep both L2s.** RF 1.2 is well supported. RF 1.1 holds one L3, coded CM 1.1.4.6.3 (site business risk). It is MPC-specific, and I found no peer evidence for it either way, so leave it to the owner.

#### Odd L3 placements under Refining: CM 1.1.4 Refinery Planning and Optimization; CM 1.1.7 Refinery Production Planning and Scheduling

- **CM 1.1.4 (planning and optimization):** 3 companies put optimization with Commercial (PBF, Phillips 66, Shell). None puts refinery planning under the refining executive.
  - **Recommendation: move it back under CM 1.1 Planning, Scheduling & Optimization.** Its code already says CM.
- **CM 1.1.7 (production planning and scheduling):** APQC 4.3.1 "Schedule production" sits under Produce, with refining. On the other side, Phillips 66 lists "scheduler" as a Commercial role, but that is one company, and the role is probably hydrocarbon scheduling rather than unit scheduling (Inference).
  - **Recommendation: keep it under Refining, on the strength of the standard, and recode it RF.** Its Energy & Utility Management L3 fits there too.
- The two together match where companies draw the line: commercial optimization goes to Commercial, and unit-level daily execution and scheduling stays with the refinery.

### L1 Renewables (not in the baseline)

- **Renewables as a separate segment: 6 companies.**
  - MPC: "Renewable Diesel".
  - Valero: "Renewable Diesel" and "Ethanol".
  - Phillips 66: "Renewable Fuels", which "includes the global activities to procure renewable feedstocks, manage certain regulatory credits, and market renewable fuels".
  - HF Sinclair and CVR: "Renewables".
  - Calumet: "Montana/Renewables".
- **Recommendation: add an L1 "Renewable Fuels" under Downstream Operations.** It can stay empty until processes are written. If renewables are run through the same commercial and refining processes (Inference for most of these companies), treat it as a product line rather than a process area. That is a judgement for the owner.

### Lubricants & Specialties; Chemicals (not in the baseline)

- **Lubricants and specialties as their own segment: 3 companies.**
  - HF Sinclair: "Lubricants & Specialties".
  - Calumet: "Specialty Products and Solutions" and "Performance Brands".
  - ExxonMobil: "Specialty Products".
- **Lubricants inside marketing or downstream: 3 companies.** Phillips 66 under M&S, Shell under Marketing, and Chevron in Downstream.
- **Chemicals as a segment: 4 companies.** Phillips 66 (CPChem), ExxonMobil (Chemical Products), Shell (within Chemicals and Products) and CVR (Nitrogen Fertilizer).
- **Recommendation: optional L1 extensions.** Neither applies to MPC, which does produce "NGLs and petrochemicals" in its refineries but has no segment for them. Keep them out of the core tree, and document them as extension points that meet the rule.

### L1 Enabling Functions, child by child

| Baseline L1 | Peer and standard evidence | Recommendation |
|---|---|---|
| Finance (with Financial Planning and Performance Management > Plan Budgets) | Finance titles at MPC (CFO, Controller, Treasury, IR), Phillips 66, PBF, Valero and HF Sinclair. APQC 9.0, with 9.1 "Perform planning and management accounting". | Keep. "Plan Budgets" under Finance matches APQC 9.1, so it is not an odd placement. APQC 3.3.2 "Establish marketing budgets" is the only reason to also show a marketing budget step under Marketing. |
| Human Resources | MPC "Chief Human Resources Officer…", PBF "Senior Vice President, Human Resources", HF Sinclair "Executive Vice President and Chief Human Resources Officer". APQC 7.0. | Keep. |
| Shared Services | 0 companies name it. PBF says G&A "services provided by PBF Holding to PBFX", and Chevron's parent provides support. Both describe a delivery model, not a process area. | Remove, or merge into the specific functions. It is empty. |
| Supply Chain Mgmt. | See the supply chain section below. | Keep, renamed "Procurement & Supply Chain (Goods and Services)". |
| Process Excellence & IT | MPC has separate "Chief Digital Officer" and "Chief Business Transformation Officer" roles. HF Sinclair combines "Growth, Technology & Transformation". APQC splits 8.0 IT from 13.1 "Manage business processes". | Split into "Information Technology" (taking CM 1.4) and "Business Process Excellence / Transformation". The standard and MPC support the split; HF Sinclair is the dissent. |
| Legal & Corp Comm | MPC: "Chief Legal Officer and Corporate Secretary", with communications under the HR chief. Phillips 66: "Government Affairs, General Counsel and Corporate Secretary". PBF and HF Sinclair: General Counsel. APQC 12.0 Manage External Relationships holds 12.4 legal, 12.5 public relations and 12.2 government relations. | Keep together, as APQC 12.0 groups them. The rename "Legal & External Affairs" would cover government affairs (Phillips 66) too. |
| EHS & Gov Reporting | MPC "Health, Environment, Safety and Security", HF Sinclair "Environmental, Health and Safety", APQC 13.7 "Manage environmental health and safety (EHS)". Government or regulatory reporting has no peer title; APQC 11.2 "Manage compliance" is the nearest standard. | Keep EHS as an L1, named "Environment, Health & Safety". Treat regulatory reporting as an L2 under it (Inference; no peer names it). |

## Where does supply chain go?

What "supply chain" covers, company by company (CSV areas "supply chain" and "procurement"):

| Company | Meaning | Where it sits | Evidence |
|---|---|---|---|
| MPC | Both: goods and services procurement, and crude trading and supply | Procurement: "Procurement teams work with suppliers serving our refining, midstream and renewables businesses", which is shared across businesses. Crude: in the trading subsidiary. | 2025 Sustainability Report, "Responsible Supply Chain Management"; MCTS report: "primary supply chain activity is the purchase of Canadian crude oil" |
| Valero | Goods and services procurement | Serves "refining, renewables, and marketing operations", so it is enterprise-wide. The page metadata calls it supply chain management. | valero.com Suppliers page |
| Chevron | Goods and services procurement | The job category is "Procurement / Supply Chain Management" | careers.chevron.com |
| Phillips 66 | Both | Suppliers "through our procurement processes" across "the Phillips 66 supply chain", and Commercial "creating innovative supply chain solutions" for feedstocks | Supplier Diversity page; Commercial job page |
| Delek | Inputs to refine, manufacture, transport and sell | Risk-factor usage, no unit named | 10-K summary of risk factors |
| World Kinect | Fuel sourcing (SAF) | Inside the Aviation segment | 10-K Item 1 |
| APQC | All of it: 4.1 plan, 4.2 procure materials and services, 4.3 produce, 4.4 logistics | One L1, 4.0 Deliver Physical Products. Trading is separate, in 3.6 and 3.7. | APQC workbook |

Findings:
1. **When a company names "supply chain" as an organization, it means procurement of goods and services**, shared across the businesses. That is the case at MPC, Valero, Chevron and Phillips 66, so 4 companies support the baseline's enabling-function placement.
2. **The hydrocarbon supply chain is organized with supply and trading, not with procurement.** Crude and feedstock supply, product supply and distribution sit there at 4 companies: Phillips 66's Commercial sources feedstocks and employs schedulers and logistics coordinators, PBF has "Supply, Trading and Optimization", Valero has "Product Supply, Trading and Wholesale", and MPC's trading subsidiary trades and supplies crude. So the baseline is right to put CM 1.2.5 to 1.2.7 and CM 1.1.3 under Commercial.
3. **APQC's single "Deliver Physical Products" category is a classification, not an org model.** No company I read organizes procurement, hydrocarbon planning and logistics under one unit.

Recommendation:
- Keep the enabling L1, renamed **"Procurement & Supply Chain (Goods and Services)"**, or "Procurement" if a short name is wanted. That keeps the two meanings apart.
- Keep the hydrocarbon supply chain (CM 1.2.5 Crude/Feed Supply Chain, CM 1.2.6 Refined Product Supply Chain, CM 1.2.7 Products Distribution, CM 1.1.3 Distribution Planning) under Commercial.
- Map both to APQC 4.0 in the crosswalk column: procurement to 4.2, hydrocarbon planning to 4.1, distribution to 4.4.
- Optionally rename CM 1.2.5 and 1.2.6 from "Supply Chain Management" to "Supply" (for example "Crude & Feedstock Supply") so that the phrase "supply chain" lives in one place.

## Other odd L3 placements

- **CM 1.3.10 Terminal Loading (under Marketing):** terminal loading sits with terminals and midstream at 3 companies.
  - HF Sinclair: "our terminal loading racks" in midstream operations.
  - MPLX: Terminal Services Agreements.
  - Kinder Morgan: refined products terminals that "store fuels and offer blending services".
  - Recommendation: **move it to MS 1.2 Terminal Services.** Leave the customer-facing part, lifting authorization and BOL for the customer, under Order Management if the owner wants a marketing view (Inference).
- **CM 1.1.4.6 Commercial Development (under Planning & Scheduling):** Phillips 66 lists "business development and origination" as a Commercial role, and MPC has a "Chief Strategy Officer and Senior Vice President Business Development". That is 2 companies with different placements, which is below the rule. Keep it under Commercial, but at L2 level beside Supply & Trading rather than under planning. Flag it for the owner.
- **CM 1.2.4 Settlements & Accounting (under Supply And Trading):** APQC splits this work. 3.7.3 "Calculate trading profit and loss (mark to market)" sits under trading, while 9.2 revenue accounting and 9.6 accounts payable sit under Finance. I found no peer evidence. Keep it, and note the APQC split in the crosswalk.

## Activities named inside the thin areas (secondary scope)

The CSV rows with `company_level` = "activity" carry the activities companies name. Examples:
- **Refining operations:** turnarounds (MPC, PBF, Phillips 66, Delek, CVR), and catalyst changes, inspection and repair (Delek's definition).
- **Midstream:** receiving, handling, storage and transferring (PBF); receipt, storage, throughput, blending and delivery (MPLX); pipeline and terminal preventive maintenance (HF Sinclair); operating affiliate pipelines under operating services agreements (MPLX); Jones Act tanker transport (Kinder Morgan).
- **Finance:** controller, treasury and investor relations (MPC).
- **HSE:** process safety event rate (Valero).
- **IT:** IT strategy, infrastructure, applications, data and cybersecurity (World Kinect's CIO).
- **Procurement:** category management, supplier selection and competitive bidding (MPC); chemicals, catalysts, equipment, maintenance materials and services (Valero).

Coverage of tax, HR activities and legal activities is thin. Filings name the functions but rarely the activities.

## Where companies disagree

1. **Planning and optimization placement:** Commercial (PBF, Phillips 66, Shell), standalone (MPC), or supply chain planning and production (APQC).
2. **Marketing with or without refining:** a separate segment (Phillips 66, HF Sinclair, Shell) or inside refining (MPC, Valero, PBF, Delek, CVR, Chevron, ExxonMobil). At the org level, 3 companies put marketing under the commercial executive.
3. **Midstream or Logistics as the name:** 3 companies against 4.
4. **Lubricants:** a segment (HF Sinclair, Calumet, ExxonMobil) or under marketing (Phillips 66, Shell).
5. **Technology:** combined with transformation (HF Sinclair) or separate (MPC, APQC).

## Limits

- **Segment structure is reporting structure.** Filings say how results are reported. Only MPC, MPLX, Valero and Calumet say they also manage that way ("organized and managed based upon…", "We manage our operations through…", "managed using the following reportable segments"). Org evidence comes from executive titles, which show only the top layer, and a few company pages.
- **Tool limits:** the scraper read only the first part of long filings. For Valero, Phillips 66, Plains, Kinder Morgan and HF Sinclair, Item 1 was not detected as a section. Some items were therefore not captured:
  - bp: the "customers & products" segment definition. bp's row is the table-of-contents heading only.
  - Kinder Morgan: the exact segment list.
  - CVR, Delek and HF Sinclair: executive officers, which are not in the 10-K or were not reachable. HF Sinclair's came from its leadership page.
- **Not covered:** proxy statements, investor-day decks and org charts. These could change the planning finding.
- **Web sources:** the job page and supplier pages are company-published but not filings. The Phillips 66 job page is dated 2026-11-09 and may be withdrawn.
- **Counting:** counts treat MPLX as independent of MPC for midstream questions, although MPC controls it. Without MPLX, the "Logistics" name has 3 companies.
- **Not read:** the APQC "Categories" sheet labels for the operating versus support grouping. I state that split from the numbering (1.0 to 6.0 against 7.0 to 13.0), which is my reading.

## 10% source check

I drew 18 of the 181 rows at random (Python `random.seed(20261124)`, rows 0, 11, 14, 19, 35, 41, 44, 63, 108, 112, 119, 125, 143, 145, 149, 155, 172 and 177). I re-opened each source and searched for the quote.

- **Confirmed verbatim: 16 of 18.**
  - Re-scraped: MPC segments; PBF rows 11, 14 and 108; HF Sinclair Refinery Operations; Global Partners Wholesale; Plains segments; Phillips 66 Chemicals; Delek wholesale and branded sales; EIA Retailer; HF Sinclair leadership title.
  - Found in the saved full section text: Phillips 66 "We do not produce any of our crude oil feedstocks." (Item 1A) and MPLX segments (Item 1).
  - Found in the workbook: APQC 4.1, 4.3.1 and 13.7, matched by PCF ID.
- **Corrected: 1 (row 44, Delek retail).** The first read gave the fragment "including the sale of our Retail Stores" from the forward-looking statements. The re-open did not return that fragment. It returned the divestiture table instead, so I replaced the quote with that verified text: "Sold 100% of the equity interests in four of Delek US' wholly-owned subsidiaries that owned and operated 249 retail fuel and convenience stores (the "Retail Stores")".
- **Not reconfirmed: 1 (row 177, Shell Lubricants).** The re-open query returned an empty answer. The quote was returned verbatim in the original scrape, inside the Marketing segment definition. Treat it as single-read until it is checked by hand in the Shell 20-F, Strategic Report segment table.
- **Side fix:** the check also corrected the section heading on the Plains rows to "Description of Segments and Associated Assets".
