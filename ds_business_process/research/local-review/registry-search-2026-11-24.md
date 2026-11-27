# Step 0 registry searches, run from this Mac, 2026-11-24

All 32 searches ran (4 registries × 8 terms). Full lists, up to 25 names per row, are in ~/dsbp-local-review/registry-search.md on this Mac.

**Skill-gap rows from this step** (external-ontologies.md, "The registries to search"):
1. **LOV:** the API path the skill documents (`/dataset/lov/api`) returns 404. The working path is `/dataset/api/v2/vocabulary/search?q=` and `/dataset/api/v2/term/search?q=`. The vocabulary search pages showed no result list for 7 of 8 terms, even where the API had hits, so the page search the skill tells us to record is unreliable. The "downstream" term page returned HTTP 500.
2. **BARTOC:** the skill's `/api/` hint is incomplete. `/api/voc?search=` ignores the term (all 8 responses were byte-identical), and the site search page errored. The working call is `/api/voc/suggest?search=<term>&limit=100`; `/api/voc/search?query=` agreed for "petroleum".
3. **Open Knowledge Graphs:** the site search runs in the browser. The API `api.openknowledgegraphs.com/ontologies?q=` works but reported a degraded text-only mode (semantic search paused). The full listing (`openknowledgegraphs.com/data/ontologies.ttl`) was too large to fetch. Rerun it when semantic search is back.
4. **DBpedia Archivo:** no keyword search, and `/list` failed twice. The root URL redirected to the list (2010 ontologies), which I filtered by name and IRI.
5. **The skill should say:** substring hits ("RACI" matching "racing", "oil and gas" matching "and") are not hits, and multi-word queries need an exact-phrase check.

| Registry | Date | Query terms (exact URL) | Hits (names), or "no hits" |
|---|---|---|---|
| LOV vocabs | 2026-11-24 | `https://lov.linkeddata.es/dataset/api/v2/vocabulary/search?q=petroleum` | no hits |
| LOV vocabs | 2026-11-24 | `https://lov.linkeddata.es/dataset/lov/vocabs?q=oil%20and%20gas` (page) | 2: sstim; oso (API: 524 single-word matches, none oil-and-gas) |
| LOV vocabs | 2026-11-24 | `.../api/v2/vocabulary/search?q=refinery&page_size=25` | no hits |
| LOV vocabs | 2026-11-24 | `.../api/v2/vocabulary/search?q=downstream&page_size=25` | no hits |
| LOV vocabs | 2026-11-24 | `.../api/v2/vocabulary/search?q=supply%20chain&page_size=25` | 6: mvco; psn; holy; dave; ioc; s4inma |
| LOV vocabs | 2026-11-24 | `.../api/v2/vocabulary/search?q=key%20performance%20indicator&page_size=25` | 15: mexperf; iso37120; sri; brk; brt; gci; bag; inno; npg; spectra; stories; music; bdi; gleif-L1; vir |
| LOV vocabs | 2026-11-24 | `.../api/v2/vocabulary/search?q=process%20classification&page_size=25` | 33 (first 25): pnc; acm; pep; spcm; rec54; ceon-process; ceon-processODP; citof; arco; tddial; tddm; elec; oae; cold; sw-quality; ioc; rov; shoah; pproc; decision; pso; pro; experts; seasbo; ludo |
| LOV vocabs | 2026-11-24 | `.../api/v2/vocabulary/search?q=RACI&page_size=25` | no hits |
| LOV terms | 2026-11-24 | `.../api/v2/term/search?q=petroleum&page_size=25` | 7: ceon-energy:Petroleum; lgdo:PetroleumWell; pext:PetroleumBasin; modsci:PetroleumGeology; km4c:Coke_and_petroleum_derivatives; km4c:Petroleum_and_natural_gas_extraction; km4c:Manufacture_of_refined_petroleum_products |
| LOV terms | 2026-11-24 | `.../api/v2/term/search?q=oil%20and%20gas&page_size=25` | 161, mostly matches on "and" (dbpedia-owl:oilSystem; dbpedia-owl:cargoGas; s4bldg:hasHotGasBypass; csp:and; odrl:and; sh:and…) |
| LOV terms | 2026-11-24 | `.../api/v2/term/search?q=refinery&page_size=25` | 1: holy:RefineryIndustrialProcessing |
| LOV terms | 2026-11-24 | `.../api/v2/term/search?q=downstream&page_size=25` | no hits (term page HTTP 500) |
| LOV terms | 2026-11-24 | `.../api/v2/term/search?q=supply%20chain&page_size=25` | 20: dbpedia-owl:chain; dbpedia-owl:supply; schema:supply; dpp:valueChainProcess; ofrd:powerSupply; lv:subjectChain… |
| LOV terms | 2026-11-24 | `.../api/v2/term/search?q=key%20performance%20indicator&page_size=25` | 116 (s4city:hasKPI; s4city:isKPIOf; s4city:KeyPerformanceIndicator; theatre:performance; opmo:key…) |
| LOV terms | 2026-11-24 | `.../api/v2/term/search?q=process%20classification&page_size=25` | 112 (vdpp:process; dbpedia-owl:classification; org:classification; pep:forProcess; okh:manufacturingProcess…) |
| LOV terms | 2026-11-24 | `.../api/v2/term/search?q=RACI&page_size=25` | 12 substring matches (racing, racial, racine); none is RACI |
| BARTOC | 2026-11-24 | `https://bartoc.org/api/voc/suggest?search=petroleum&limit=100` | 6: Petroleum Abstracts® Exploration and Production Thesaurus; Decimal System for Classifying Data Pertaining to the Petroleum Industry; Gale Industries Thesaurus; Vocabulary of Equipment, Transport and Tourism; Vocabulary of Oil and Gas; SNORRE |
| BARTOC | 2026-11-24 | `.../suggest?search=oil%20and%20gas&limit=100` | 1: Vocabulary of Oil and Gas |
| BARTOC | 2026-11-24 | `.../suggest?search=refinery&limit=100` | no hits |
| BARTOC | 2026-11-24 | `.../suggest?search=downstream&limit=100` | 2: MICE Industry Classification; Agriculture, Livestock and Food Industry Classification |
| BARTOC | 2026-11-24 | `.../suggest?search=supply%20chain&limit=100` | 4: Supply Chain Management Terms and Glossary; BISAC Subject Headings; Global Medical Device Nomenclature; ISNI International Standard Name Identifier |
| BARTOC | 2026-11-24 | `.../suggest?search=key%20performance%20indicator&limit=100` | no hits |
| BARTOC | 2026-11-24 | `.../suggest?search=process%20classification&limit=100` | 1: Process Classification Framework |
| BARTOC | 2026-11-24 | `.../suggest?search=RACI&limit=100` | 6 stem matches, none RACI (development cooperation, e-government, social security, race relations thesauri) |
| Open Knowledge Graphs | 2026-11-24 | `https://api.openknowledgegraphs.com/ontologies?q=petroleum&limit=100` | no hits (degraded text-only mode) |
| Open Knowledge Graphs | 2026-11-24 | `...?q=oil%20and%20gas&limit=100` | no hits |
| Open Knowledge Graphs | 2026-11-24 | `...?q=refinery&limit=100` | no hits |
| Open Knowledge Graphs | 2026-11-24 | `...?q=downstream&limit=100` | no hits |
| Open Knowledge Graphs | 2026-11-24 | `...?q=supply%20chain&limit=100` | 28 (Common Procurement Vocabulary; ECLASS; EPCIS; GS1 Core Business Vocabulary; GS1 Web Vocabulary; Harmonized System; Product Types Ontology; dpp: namespace…) |
| Open Knowledge Graphs | 2026-11-24 | `...?q=key%20performance%20indicator&limit=100` | no hits |
| Open Knowledge Graphs | 2026-11-24 | `...?q=process%20classification&limit=100` | 2: Semantics of Business Vocabulary and Business Rules; Whisky Ontology |
| Open Knowledge Graphs | 2026-11-24 | `...?q=RACI&limit=100` | 4 "racing" matches plus PGxO; none RACI |
| DBpedia Archivo | 2026-11-24 | `https://archivo.dbpedia.org/` (→ list of 2010), filter "petroleum" | no hits |
| DBpedia Archivo | 2026-11-24 | same, "oil and gas" | no hits (oil: lemon-model.net/oils; gas: countingas.owl) |
| DBpedia Archivo | 2026-11-24 | same, "refinery" | no hits |
| DBpedia Archivo | 2026-11-24 | same, "downstream" | no hits |
| DBpedia Archivo | 2026-11-24 | same, "supply chain" | no hits (supply: Product Supply Network Vocabulary; purl.org/supply-network/onto) |
| DBpedia Archivo | 2026-11-24 | same, "key performance indicator" | no hits ("kpi": energy.linkeddata.es/em-kpi/ontology) |
| DBpedia Archivo | 2026-11-24 | same, "process classification" | no hits (process: 10 incl. CEON process, A Process Model Ontology; classification: 5 incl. Thomson Reuters Business Classification) |
| DBpedia Archivo | 2026-11-24 | same, "RACI" | no hits |

**Leads worth assessing** (by name only):
- **Strongest:** BARTOC Process Classification Framework (node/502), Petroleum Abstracts® E&P Thesaurus (node/1083), Vocabulary of Oil and Gas (node/1527).
- **Other BARTOC:** Decimal System for Classifying Data Pertaining to the Petroleum Industry (node/1908), Gale Industries Thesaurus (node/18857), Supply Chain Management Terms and Glossary (node/17709).
- **LOV:** oso, sstim, ceon-energy, ceon-process, ceon-processODP, holy, km4c, s4inma, s4city (KeyPerformanceIndicator), psn, ioc, pep, dpp, org.
- **Archivo:** em-kpi, supply-network/onto, A Process Model Ontology, Thomson Reuters Business Classification.
- **OKG:** EPCIS, GS1 Core Business Vocabulary, GS1 Web Vocabulary, ECLASS, SBVR.

**Findings for the survey register:**
- No registry has a RACI vocabulary.
- No registry has a downstream (oil-and-gas sense) or refinery-process vocabulary.
- Open item: rerun Open Knowledge Graphs when its semantic search returns.

Packs 3, 4 and 5 follow.
