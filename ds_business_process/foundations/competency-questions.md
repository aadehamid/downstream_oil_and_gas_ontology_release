# Competency questions, draft

Status: drafted 2026-11-24 for the owner to lock (Step 1, policy 1). Nothing here is locked yet.

These are the acceptance test for DS_Business_Process: if the ontology cannot answer one, the ontology is incomplete, not the question. The Step 11 regression will run each as SPARQL.

Questions 1 to 55 carry over 1.2's 55 locked questions (`business_architecture/ontology/competency-questions.md` on `kpi-store/1.2`), with the same numbers. Where 1.2's wording named one company's systems, tools or data, the change is noted. Questions 56 to 70 are new, for an industry reference.

Before the list is locked, every list of values a question names (fields, categories, roles) needs a standard or 3 or more independent companies behind it, as any reference term does (DSBP-DEC-0002). Where a question names values without that evidence yet, it is marked *(Evidence needed)*. Questions 20, 22, 41 to 43 and 50 carry 1.2 assumptions (party-role functions, loading authorization, rules for agents), which need the same evidence before they are locked.

## I. Process structure
1. What are the child processes of process P, and what is its full path from the top?
2. Which processes are orphans: no parent, or no children where children are expected?

## II. Responsibility (RACI), by generic role
3. Which generic role is Accountable, Responsible, Consulted or Informed for process P? *(Changed: "who" becomes "which generic role", DSBP-DEC-0033.)*
4. Which processes have no Accountable role?
5. Which roles take part in process P?

## III. Systems and data products
6. Which system categories support process P, which off-the-shelf products are examples of each, and which processes depend on category S? *(Changed: 1.2 named one company's systems; DSBP-DEC-0034.)*
7. Which data products does process P produce or consume, and which data products have no owning process?
8. Which processes have no produced or consumed information object?

## IV. Lanes, capabilities, value streams
9. Which processes sit in each lane, and which lanes are thin?
10. Which processes realize capability C or take part in value stream V?

## V. Framework alignment
11. Which processes reference APQC element E, and which APQC elements have no counterpart?
12. Where does the reference deliberately depart from APQC, and why (boundary notes)?

## VI. Shared meaning
13. What is a concept, as against a named measure or a report?
14. Which concepts may become a number, and which must never become one?
15. When two teams use the same word, how do we tell whether they mean the same thing?
16. What is the official name, what are the aliases, and what is explicitly out?
17. Which role owns the meaning of a concept, and which only stewards its data? *(Changed: "who" becomes "which role".)*
18. When a definition changes, what stays the same (the identity) and what gets a new version?
- *Done when:* "Customer" cannot be classified as a measure at all, and "3-2-1 crack spread" is a measure of market nature that never carries the typical-KPI role (DSBP-DEC-0038, 0039).

## VII. Party
19. What is a party, and how is it different from a customer account?
20. Which roles can the same party hold at the same time (sold-to, bill-to, payer and so on)?
21. Are those roles permanent types or dated holds? Is ship-to a role or a location?
22. What is a loading-authorized party, and how is that different from an authorization object?
23. Where does credit sit: on the party, the account or the payer?
24. Can the same organization be a customer in one deal and a supplier or exchange counterparty in another, without a second "Customer" class?
25. Which concept should a customer-grained measure bind to (party, account, sold-to, payer or site), and why not the bare word "customer"?
26. Which questions about "who is the customer on this order?" must resolve to one role?
- *Done when:* five invented multi-role organizations can be described both ways, party to roles and role to party. *(Changed: 1.2 also described two real companies; real organizations are out of scope, policy 2.)*

## VIII. Measures
27. What is a named measure, as a concept, before anyone computes it?
28. Which population is in the measure, and which is out, in business words?
29. What is the grain of the measure?
30. Is a monthly average a second measure, or a way of asking for the same one?
31. When are two published series the same measure, and when two different ones?
32. What is the 3-2-1 crack spread not (a realized refinery margin, a capture rate, a segment result)?
33. Which process, decision or capability does a measure inform?
34. Which domain concepts does it quantify, without putting the formula's values in the ontology?
35. How does a measure catalogue row point at a measure, and what must exist before that pointer is filled?
36. If an assistant asks for "the crack", which measure is meant, and which nearby series are related but not it?

## IX. Process placement
37. Which process or capability does a concept or measure sit on?
38. Is that placement a certification, or only context?
39. What is affected upstream or downstream if a meaning changes?

## X. Publication and agents
40. Where is the official wording published for people, and what is only a copy?
41. What may a graph agent answer without reading a table or inventing a formula?
42. What must that agent refuse to do?
43. How does an analytics platform's assistant get the same definition without becoming a second ontology? *(Changed: 1.2 named one product.)*
44. If two sources disagree, which definition is authoritative, and how is that marked?

## XI. Technical graph
45. Where does this number come from?
46. Can I trust it today (last refresh, checks passed)?
47. What is affected if this table or system changes?
48. Is it built as designed?
49. Which role answers for it?
50. Which agent or report answers for this measure?

## XII. Logical models
51. Which logical entities hold data about a party concept?
52. Which source system category does each entity come from, and which entities does each feed?
53. Which attributes identify a customer in each system (primary and alternate keys)?
54. Which attributes stand for a business term, and which stand for none?
55. Which data product or platform table implements each entity, and which entities have none?
*(Changed: 1.2 named one modelling tool's export; the questions are asked of any exported logical model.)*

## XIII. Industry reference (new)
56. What is the one nature of measure M (observation, operational, financial, market, forecast, risk or data quality), what roles does it play (input, analysis, decision support, benchmark, typical KPI), and which public source anchors its nature? (DSBP-DEC-0039)
57. Which typical measures evaluate each process area, and which areas have none?
58. For a measure with the typical-KPI role, which components does the reference name (by component role, such as numerator and denominator), with which unit, grain and direction, and which items are left to the company layer (governed-KPI status, target, thresholds, owner, formula version, authoritative system)? (DSBP-DEC-0039)
59. Which inputs is data product D built from, and how does a public data-product standard (such as DPROD or ODPS) classify it? *(Evidence needed: the classes come from the standard once surveyed.)*
60. Which generic roles exist, which occupational standard or companies support each, and which processes have no RACI yet?
61. For a company title, which generic role does it map to? *(Answered by a company specialization, which the reference must make possible.)*
62. Which concepts rest on a standard, which on 3 or more independent companies, and which on fewer?
63. Which reference terms name a company, a brand, an internal system or a company role title? *(Must return none.)*
64. Which 1.2 IRI became which DS_Business_Process IRI, with which status (retained, relabeled, modified, deprecated or excluded)?
65. Which processes map to an external ontology term (IOF, APQC), and with which match?
66. Which areas in the coverage table are complete, which are thin, and on what evidence?
67. What must a market observation carry, and which standard or price-reporting agency methodology names each field? *(Evidence needed: 1.2's market-data module lists commodity, specification, location or hub, marker, observation date, delivery period, publication time, source and version, and status; each must be confirmed.)*
68. Which information objects does each process produce or consume, and which standard or company names each?
69. Which off-the-shelf products are examples of system category S, and which public page supports each?
70. Which risk categories does each Supply & Trading process manage, and which standard or company disclosures name each category? *(Evidence needed: a draft list of price, basis, crack, volume, quality, logistics, credit, liquidity, operational and regulatory risk is to be confirmed against filings' risk-factor sections.)*
