"""Build the release package of a module other than core (Step 10; the decision of 2026-10-05, the decision of 2026-10-13).

    python3 build_module.py organization            # build, validate, print the figures
    python3 build_module.py organization --write    # write releases/organization/<version>/
    python3 build_module.py organization --verify   # fail unless the written package equals a fresh build

The package holds the module's Turtle and JSON-LD, its shapes, a DCAT record, its changelog and a
manifest with each file's SHA-256, the shape of the core 1.0.0 package (the decision of 2026-10-13). A release
candidate (a stage such as "rc.1") carries no issued date: a module's first release is a major, and
a major needs the subject matter expert's approval (module policy, 2026-09-18). An issued release names where their
approval is recorded; the tests check that the words are there.
"""
import argparse
import hashlib
import json
import os
import re
import sys

from pyshacl import validate
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, XSD

import newest

HERE = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY = os.path.join(HERE, "..")
MODULES_NS = "https://w3id.org/mpc/ontology/modules/"
DCAT = Namespace("http://www.w3.org/ns/dcat#")

# One entry per module. Paths are relative to business_architecture/ontology/.
MODULES = {
    "organization": {
        "title": "MPC Organization Module",
        "description": "Roles, RACI responsibility assignments and control between legal entities (Step 5).",
        # 2.0.0 carries the decision owner's role answers: three roles deprecated, their assignments moved
        # (the decision of 2026-10-18). Each earlier package stays on disk as released; test_build_module.py
        # checks it is untouched.
        # 2.1.0 is a minor release a subject matter expert approved: the RACI levels stated as top concepts both ways;
        # it requires core 2.3.0, the current release (the decision of 2026-10-25, item 5; the decision of 2026-10-26).
        # 2.2.0 is a minor release a subject matter expert approved: the decision owner's close-out answers of 2026-10-28,
        # PSM expanded as Process Safety Management, the Crude RFC reading and Business Planning and Analysis's
        # definition confirmed; it still requires core 2.3.0 (the decision of 2026-10-18, amendment of 2026-10-28).
        "version": "2.2.0", "stage": None, "approver": "a subject matter expert reviewing the documents", "issued": "2026-10-28",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "Approved as described"),
        "parts": ["organization/vocabulary.ttl", "organization/roles.ttl", "organization/assignments.ttl"],
        "shapes": ["organization/shapes.ttl"],
        "depends_on": ["core"],
        "decisions": ["the decision of 2026-10-13", "the decision of 2026-10-13", "the decision of 2026-10-13", "the decision of 2026-10-18", "the decision of 2026-10-25",
                      "the decision of 2026-10-26"],
    },
    "ref-mpc": {
        "title": "MPC Reference Instances: Marathon Petroleum Corporation",
        "description": "Public reference facts about MPC and MPLX, each with a source and an as-of date (Step 5).",
        # 1.1.0 requires organization 2.0.0; its own content is unchanged (the decision of 2026-10-18).
        # 1.2.0 adds MPC and MPLX as parties in the party module's terms, moved from party/, and requires
        # party 1.0.0; the subject matter expert approved it on its own (the decision of 2026-10-22, the decision of 2026-10-22).
        # 1.3.0 is a minor release a subject matter expert approved and the words of a subject matter expert reviewing the documents: MPC's brands Marathon,
        # ARCO and Tesoro as party:Brand individuals; it requires organization 2.1.0 and party 2.0.0, the current
        # releases (the decision of 2026-10-27, amendment of 2026-10-27).
        "version": "1.3.0", "stage": None,
        "approver": "a subject matter expert reviewing the documents",
        "issued": "2026-10-27",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)",
                     "yes those can be brand values. Others I cannot answer."),
        "parts": ["ref-mpc/ref-mpc.ttl", "ref-mpc/reference-parties.ttl", "ref-mpc/reference-brands.ttl"],
        # Its own shapes, then the released shapes of organization and party (the decision of 2026-10-23). resolve()
        # reads each from that module's newest package, whatever version the path names.
        "shapes": ["ref-mpc/shapes.ttl", "releases/organization/2.1.0/shapes.ttl", "releases/party/2.0.0/shapes.ttl"],
        "depends_on": ["organization", "party"],
        "decisions": ["the decision of 2026-10-05", "the decision of 2026-10-13", "the decision of 2026-10-21", "the decision of 2026-10-22", "the decision of 2026-10-22",
                      "the decision of 2026-10-27"],
    },
    "kpi": {
        "title": "MPC KPI Module",
        "description": "Measure definitions, classified by kind, with the planning personas who use them and the core processes they inform (Step 7). Definitions only, never values.",
        # 1.0.0 was the module's first release, a major approved by the decision owner (the decision of 2026-10-18).
        # 1.0.1 is a patch: the planner list's source names VCO DSV (the decision of 2026-10-18).
        # 1.1.0 is a minor approved with the release plan: the eight measure populations join the package,
        # the measure shape is closed, and it requires core 2.2.0 (the decision of 2026-10-22).
        # 1.1.1 is a patch approved with the close-out releases: pop:populationEvidence gains rdfs:range xsd:string,
        # closing its projection gap; it requires core 2.3.0, the current release (the decision of 2026-10-23, the decision of 2026-10-23).
        # 1.2.0 is a minor of item F's release plan, which the subject matter expert approved: KPI-0001 on Crack Spreads
        # Pricing, Additional Market Prices narrowed to renewables and NGLs, the duplicate alias dropped, top
        # concepts both ways; it requires core 2.3.0 (the decision of 2026-10-25, the decision of 2026-10-25, the decision of 2026-10-25).
        # 1.3.0 is a minor release a subject matter expert approved: a KPI or OPM identifier on every measure but the
        # trackers, reports and non-measures, the scheme a subject matter expert reviewing the documents chose; it still requires core 2.3.0
        # (the decision of 2026-10-28).
        "version": "1.3.0", "stage": None, "approver": "a subject matter expert reviewing the documents", "issued": "2026-10-28",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "Approved as described"),
        "parts": ["kpi/vocabulary.ttl", "kpi/measures.ttl", "population/vocabulary.ttl", "population/population.ttl"],
        "shapes": ["kpi/shapes.ttl"],
        "depends_on": ["core"],
        "decisions": ["the decision of 2026-10-18", "the decision of 2026-10-18", "the decision of 2026-10-18", "the decision of 2026-10-19", "the decision of 2026-10-22",
                      "the decision of 2026-10-23", "the decision of 2026-10-23", "the decision of 2026-10-25", "the decision of 2026-10-25", "the decision of 2026-10-25",
                      "the decision of 2026-10-28"],
    },
    "party": {
        "title": "MPC Party Module",
        "description": "The Customer domain's concepts: parties, the roles they hold for a period, accounts, agreements and sites; the customer's systems, data flow and attributes; and the customer lifecycle linked to core processes (Steps 5 to 7). Definitions only, never records.",
        # 1.0.0 is the module's first release, a major approved by the decision owner (the decision of 2026-10-22).
        # The reference parties are reference instances of real companies, which the playbook's module policy
        # puts in their own module, so they are not part of this package. Since 2026-10-22 they are in
        # ref-mpc/reference-parties.ttl (the decision of 2026-10-22).
        # 1.1.0 is a minor approved with the close-out releases: the products from MPC's FY2025 Form 10-K with their
        # OEO mappings and PIDX families, the onboarding stage's link to CM 1.3.7.1.7, and the eight projection
        # fixes; it requires core 2.3.0 (the decision of 2026-10-23, the decision of 2026-10-23, the decision of 2026-10-23).
        # 1.2.0 is a minor the subject matter expert approved: 18 customer systems defined, each citing its source;
        # SAP S/4HANA matched to the system module's SAP; every code list's top concepts stated both ways
        # (the decision of 2026-10-25, the decision of 2026-10-25).
        # 1.3.0 is a minor release a subject matter expert approved: the 20 internal customer systems' descriptions,
        # drafted from the repository; it requires system 1.3.0 (the decision of 2026-10-26).
        # 1.4.0 is a minor release a subject matter expert approved: seven more customer systems matched to the system
        # module's, which gains them with MPC-P11, and one shape message reworded without an apostrophe (the ontology
        # skill's SHACL rule 19); it requires core 2.4.0, which its build now reads, and system 1.4.0 (the decision of 2026-10-26, the decision of 2026-10-26).
        # 2.0.0 is a major the subject matter expert approved: the customer inputs of 2026-10-27 correct Dealer Master's role and
        # definition, two data flows, a sourcing note and the prospect system stage, and deprecate the sourcing that says
        # jobbers start in Dealer Master; they add the sub-jobber role, the dealer classes, the classes of trade, eight
        # systems and 13 flows; it requires system 1.5.0 (the decision of 2026-10-27).
        # 2.1.0 is a minor release a subject matter expert approved: the decision owner's close-out answers of 2026-10-28,
        # Drop Tank, GasBuddy and DTN defined from their vendors' own published words (Drop Tank's from a 2018 press release, its site being gone) and a note on Polaris; it still requires core
        # 2.4.0 and system 1.5.0 (the decision of 2026-10-25, amendment of 2026-10-28).
        "version": "2.1.0", "stage": None, "approver": "a subject matter expert reviewing the documents", "issued": "2026-10-28",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "Approved as described"),
        "parts": ["party/vocabulary.ttl", "party/code-lists.ttl", "party/systems.ttl", "party/lifecycle.ttl"],
        "shapes": ["party/shapes.ttl"],
        # Since 1.2.0 it also requires system 1.1.0, whose systems its five skos:exactMatch links name
        # (the decision of 2026-10-25; the earlier packages name four of them without requiring system). 1.4.0 names twelve
        # and requires system 1.4.0 (the decision of 2026-10-26). 2.0.0 names twenty and requires system 1.5.0 (the decision of 2026-10-27).
        "depends_on": ["core", "system"],
        "decisions": ["the decision of 2026-10-21", "the decision of 2026-10-21", "the decision of 2026-10-21", "the decision of 2026-10-21",
                      "the decision of 2026-10-21", "the decision of 2026-10-21", "the decision of 2026-10-22", "the decision of 2026-10-23", "the decision of 2026-10-23",
                      "the decision of 2026-10-23", "the decision of 2026-10-25", "the decision of 2026-10-25", "the decision of 2026-10-26",
                      "the decision of 2026-10-26", "the decision of 2026-10-27"],
    },
    # The Step 7 modules' first releases, majors the subject matter expert approved with the release plan
    # (the decision of 2026-10-22). Each requires core 2.2.0, the release that holds every process they link.
    "data-product": {
        "title": "MPC Data Product Module",
        "description": "The data products of the portfolio, the product lines and segments that group them, and the processes that produce them; and the pricing tables and views on the data platform, foundational or derived, with their lineage and the Genie agents that use them (Step 7). Definitions only, never data values; mapped to DCAT, not imported.",
        # 1.1.0 is a minor approved with the close-out releases: the Customer Master data product, produced by
        # CM 1.3.7.1.1 (MPC-P10.3); it requires core 2.3.0 (the decision of 2026-10-23, the decision of 2026-10-23, the decision of 2026-10-23).
        # 1.2.0 is a minor of item F's release plan, which the subject matter expert approved: the pricing platform tables,
        # the data product kinds, their lineage and the Genie agents; the four line labels and top concepts both ways.
        # It requires core 2.3.0, and kpi 1.2.0 and system 1.2.0, whose measures and systems it links (the decision of 2026-10-25,
        # 0098, 0100).
        "version": "1.2.0", "stage": None, "issued": "2026-10-25",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "Approve the plan (Recommended)"),
        "parts": ["data-product/vocabulary.ttl", "data-product/data-products.ttl", "data-product/pricing.ttl"],
        "shapes": ["data-product/shapes.ttl"],
        "depends_on": ["core", "kpi", "system"],
        "decisions": ["the decision of 2026-10-05", "the decision of 2026-10-19", "the decision of 2026-10-19", "the decision of 2026-10-22", "the decision of 2026-10-23",
                      "the decision of 2026-10-23", "the decision of 2026-10-23", "the decision of 2026-10-25", "the decision of 2026-10-25", "the decision of 2026-10-25"],
    },
    "value-stream": {
        "title": "MPC Value Stream Module",
        "description": "The Commercial Hydrocarbon Lifecycle and Order to Cash value streams: their stages, capabilities and value-stream processes, which realize core processes, produce and consume data products and carry cited measure links (Step 7).",
        # 1.1.0 is a minor the subject matter expert approved with the close-out releases: the Order to Cash credit
        # review realizes CM 1.3.7.4.2 (MPC-P10.2), and vs:produces and vs:consumes gain rdfs:range skos:Concept;
        # it requires the current core, data-product and kpi releases (the decision of 2026-10-23, the decision of 2026-10-23, the decision of 2026-10-23).
        # 1.2.0 is a minor release a subject matter expert approved: the measure relationships stated as top concepts both
        # ways; it requires the current core, data-product and kpi releases (the decision of 2026-10-25, item 5; the decision of 2026-10-26).
        "version": "1.2.0", "stage": None, "approver": "a subject matter expert reviewing the documents", "issued": "2026-10-26",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "Approved as described"),
        "parts": ["value-stream/vocabulary.ttl", "value-stream/value-streams.ttl"],
        "shapes": ["value-stream/shapes.ttl"],
        "depends_on": ["core", "data-product", "kpi"],
        "decisions": ["the decision of 2026-10-19", "the decision of 2026-10-22", "the decision of 2026-10-23", "the decision of 2026-10-23", "the decision of 2026-10-23",
                      "the decision of 2026-10-25", "the decision of 2026-10-26"],
    },
    "system": {
        "title": "MPC System Module",
        "description": "The systems, office tools and working documents the process map names, with their kind, definitions and the processes that use them, and the systems the pricing assets name (Step 7).",
        # 1.1.0 is a minor the subject matter expert approved: 15 systems defined from their vendors' own descriptions
        # or the decision owner's, full names as preferred labels, both code lists' members as top concepts both
        # ways; it requires core 2.3.0 (the decision of 2026-10-25, the decision of 2026-10-25).
        # 1.2.0 is a minor of item F's release plan, which the subject matter expert approved: MIPS and Databricks, which the
        # process map does not name, and MPR's definition, from the subject matter expert's pricing assets (the decision of 2026-10-25).
        # 1.3.0 is a minor release a subject matter expert approved (the decision of 2026-10-12, amendment of 2026-10-25, evening):
        # the 14 internal systems' descriptions, drafted from the repository (the decision of 2026-10-26).
        # 1.4.0 is a minor release a subject matter expert approved: the seven systems and 21 links of MPC-P11, which
        # the subject matter expert accepted; it requires core 2.4.0, the current release (the decision of 2026-10-26, the decision of 2026-10-26).
        # 1.5.0 is a minor release a subject matter expert approved, with the decision owner's alignment with the plan: eight
        # systems the customer inputs of 2026-10-27 name and the process map does not, and notes on TMR and Bridger
        # Insight (the decision of 2026-10-27).
        "version": "1.5.0", "stage": None, "approver": "a subject matter expert reviewing the documents", "issued": "2026-10-27",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)",
                     "I am aligned with all your recommendation in the input plan."),
        "parts": ["system/vocabulary.ttl", "system/systems.ttl"],
        "shapes": ["system/shapes.ttl"],
        "depends_on": ["core"],
        "decisions": ["the decision of 2026-10-19", "the decision of 2026-10-22", "the decision of 2026-10-25", "the decision of 2026-10-25", "the decision of 2026-10-25",
                      "the decision of 2026-10-26", "the decision of 2026-10-26", "the decision of 2026-10-27"],
    },
    "lane": {
        "title": "MPC Lane Module",
        "description": "The four office lanes as a code list, and the processes the process map places in them (Step 7).",
        # 1.1.0 is a minor release a subject matter expert approved: the four lanes stated as top concepts both ways, and a
        # shape message reworded without an apostrophe (ontology skill, SHACL rule 19); it requires core 2.3.0, then
        # the current release, which build_lanes.py then read (the decision of 2026-10-25, item 5; the decision of 2026-10-26). Since then
        # build_lanes.py reads core 2.4.0 (2026-10-30); this entry records lane 1.1.0 as issued.
        "version": "1.1.0", "stage": None, "approver": "a subject matter expert reviewing the documents", "issued": "2026-10-26",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "Approved as described"),
        "parts": ["lane/vocabulary.ttl", "lane/lanes.ttl"],
        "shapes": ["lane/shapes.ttl"],
        "depends_on": ["core"],
        "decisions": ["the decision of 2026-10-19", "the decision of 2026-10-22", "the decision of 2026-10-25", "the decision of 2026-10-26"],
    },
    "market-data": {
        "title": "MPC Market Data Module",
        "description": "The published series of the crack-spreads measure, from MPC Economics' definition first, with their benchmarks, regions, legs and RIN treatment; the prices the decision owner's pricing views report for the other pricing measures; and where each measure's complete list of series is (Step 7). Definitions only, never prices.",
        # 1.1.0 is a minor of item F's release plan, which the subject matter expert approved: the pricing views' prices for
        # each pricing measure, the columns that list every series, two NYMEX cracks, top concepts both ways; it
        # requires kpi 1.2.0 (the decision of 2026-10-25, the decision of 2026-10-25, the decision of 2026-10-25).
        "version": "1.1.0", "stage": None, "issued": "2026-10-25",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "Approve the plan (Recommended)"),
        "parts": ["market-data/vocabulary.ttl", "market-data/market-data.ttl"],
        "shapes": ["market-data/shapes.ttl"],
        "depends_on": ["kpi"],
        "decisions": ["the decision of 2026-10-18", "the decision of 2026-10-19", "the decision of 2026-10-20", "the decision of 2026-10-22", "the decision of 2026-10-25",
                      "the decision of 2026-10-25", "the decision of 2026-10-25"],
    },
    # The follow-up release's new module. 1.0.0 is its first release, a major the subject matter expert approved
    # (the decision of 2026-11-02, amendment of 2026-11-02, later). Its example graph is test data and never joins the package
    # (the ontology skill's new-module rule 9).
    # 1.1.0 is a minor decided under the delegation of KPI-DEC-0001: tg:replaces, tg:builtBy and the builder classes,
    # for a technical graph built from a live platform.
    "technical-graph": {
        "title": "MPC Technical Graph Module",
        "description": "The kinds of thing a technical graph records about a data platform as built: hosts, source databases, tables, views, metric views, pipeline steps, the jobs and pipelines that build data objects, quality checks and agents, and the links between them, among them the data object on an earlier platform that a data object replaces; each built thing points to its design in data-product, the measure it computes in kpi and the system it copies from in system. Definitions only, never the graph's records.",
        "version": "1.1.0", "stage": None,
        "approver": "The build's agent, delegated under KPI-DEC-0001", "issued": "2026-11-11",
        "approval": ("../domain/kpi-store-decisions/KPI-DEC-0001.md", "Decide anything inside the plan yourself and log it."),
        "parts": ["technical-graph/vocabulary.ttl"],
        "shapes": ["technical-graph/shapes.ttl"],
        "depends_on": ["data-product", "kpi", "system"],
        "decisions": ["the decision of 2026-11-02", "KPI-DEC-0001"],
    },
    # The integration package's first release, a major the subject matter expert approved with the release plan
    # (the decision of 2026-10-22). It packages three small vocabularies, each keeping its own namespace; the package
    # IRI names the release only. The population statements ship in kpi 1.1.0, and the APQC element list
    # stays a reference file (the decision of 2026-10-22).
    "integration": {
        "title": "MPC Integration Vocabularies",
        "description": "The rules that tie the modules together: which placing properties certify and which give context (placement), the evidence tier of every cited source (authority), and what a consumer may bind, answer and must refuse (consumer). Each vocabulary keeps its own namespace (Steps 7, 9 and 11).",
        # 2.0.0 is a major the subject matter expert approved: the five projection fixes (ranges for plc:placementKind and
        # con:reliesOn, whose definition narrows from property or class to property, which makes it a major;
        # cardinality for plc:placementKind, auth:rank and auth:evidenceTier, in two new shape files packaged with
        # consumer's), and it requires the current releases (the decision of 2026-10-23, the decision of 2026-10-23).
        # 2.1.0 is a minor the subject matter expert approved: the 27 sources of the systems' definitions in their tiers,
        # the three code lists' members as top concepts both ways; it requires the new system and party releases
        # (the decision of 2026-10-25, the decision of 2026-10-25).
        # 2.2.0 is a minor of item F's release plan, which the subject matter expert approved: the consumer rule for a value
        # quoted through the bound metric view, eight more sources tiered; it requires the new releases (the decision of 2026-10-25,
        # 0100).
        # 2.3.0 is a minor release a subject matter expert approved: two more sources in tier 1, the sources of the
        # internal systems' descriptions; it requires the new system and party releases (the decision of 2026-10-26).
        # 2.4.0 is a minor release a subject matter expert approved, with the decision owner's alignment with the plan: the
        # customer inputs of 2026-10-27 in tier 1; it requires the current releases (the decision of 2026-10-27).
        # 2.5.0 is a minor release a subject matter expert approved: the three public sources (two vendor pages, a press release) that define Drop Tank, GasBuddy
        # and DTN in party 2.1.0, in tier 4; it requires the current releases, organization 2.2.0 and party 2.1.0
        # among them (the decision of 2026-10-25, amendment of 2026-10-28).
        "version": "2.5.0", "stage": None, "approver": "a subject matter expert reviewing the documents", "issued": "2026-10-28",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "Approved as described"),
        "parts": ["placement/vocabulary.ttl", "authority/vocabulary.ttl", "authority/source-tiers.ttl",
                  "consumer/vocabulary.ttl"],
        "shapes": ["consumer/shapes.ttl", "placement/shapes.ttl", "authority/shapes.ttl"],
        "own_shapes": 3,  # all three shape files are the package's own; the package's shapes.ttl holds them merged
        "depends_on": ["core", "organization", "kpi", "data-product", "value-stream", "system", "lane", "market-data",
                       "party"],
        "decisions": ["the decision of 2026-10-19", "the decision of 2026-10-19", "the decision of 2026-10-19", "the decision of 2026-10-22", "the decision of 2026-10-23",
                      "the decision of 2026-10-23", "the decision of 2026-10-25", "the decision of 2026-10-25", "the decision of 2026-10-25", "the decision of 2026-10-26",
                      "the decision of 2026-10-27"],
    },
    # Its first release, a major the subject matter expert approved (the decision of 2026-11-02). Each model's two
    # graphs ship as they are (graphs); augment lists the two files the models were built from, each with its SHA-256.
    "logical-model": {
        "title": "MPC Logical Model Module",
        "description": "Logical data models exported from ER Studio Data Architect, each kept as two graphs: ER Studio's export as it is, in ER Studio's own namespace, and a layer of annotations that links its entities to the party, system and data-product modules. This package holds the module's vocabulary; each model's two graphs ship beside it.",
        "version": "1.0.0", "stage": None, "approver": "The decision owner", "issued": "2026-11-03",
        "approval": ("(the review comments of a subject matter expert reviewing the documents)", "I approve logical-model 1.0.0,"),
        "parts": ["logical-model/vocabulary.ttl"],
        "shapes": ["logical-model/shapes.ttl"],
        "graphs": ["logical-model/models/customer-logical-model.erstudio.ttl", "logical-model/models/customer-logical-model.layer.ttl"],
        "augment": [{"path": "customer-logical-model.ttl", "sha256": "967fedabfad83f21ce9b20413fb471eb4998220fc3c267b9437f7df4b15259be"}, {"path": "customer-logical-model.links.csv", "sha256": "65b811c9dd9f2ebee98037c89872688c613cc1c95517b00a29cb3256a1ee4cc7"}],
        "depends_on": ["party", "system", "data-product"],
        "decisions": ["the decision of 2026-11-02"],
    },
}


# Every newest package names only the newest versions (the decision of 2026-10-31, "All links go through the latest
# release"): a module is built against the current version of each module it requires, and against core's newest
# package on disk.


def recorded_where(path):
    """The path a manifest names for where an approval is recorded, or None to leave the field out. Most sources name
    a subject matter expert's review comments, which is a sentence, not a path: the field then comes out (the
    decision of 2026-10-31, amendment: approval.file comes out). A file that is in the tree is always named."""
    return path if os.path.isfile(os.path.join(ONTOLOGY, path)) else None


def package_folder(module, version):
    """The released package's folder: releases/<module>/<version>/ for a newest package, or the history folder
    releases/previous/<module>/<version>/ for the one before it. None when the tree does not hold the package."""
    for folder in (os.path.join(ONTOLOGY, "releases", module, version),
                   os.path.join(ONTOLOGY, "releases", "previous", module, version)):
        if os.path.isfile(os.path.join(folder, "manifest.json")):
            return folder
    return None


def newest_on_disk(module):
    return newest.newest_version(module, ONTOLOGY)


def label(m):
    return m["version"] if m["stage"] is None else f"{m['version']}-{m['stage']}"


def dependencies(name):
    """Each dependency with the version this package is built against: core's newest package on disk, and the
    current version of every other module, so a package never names a release the tree does not hold."""
    return {d: newest_on_disk("core") if d == "core" else label(MODULES[d]) for d in MODULES[name]["depends_on"]}


def resolve(path):
    """A path under releases/<module>/<version>/ names that module's newest package instead: the tree may not
    hold the version the path was written with."""
    m = re.match(r"releases/([a-z-]+)/(\d+\.\d+\.\d+)/(.*)", path)
    if m and m.group(1) in MODULES:
        return f"releases/{m.group(1)}/{label(MODULES[m.group(1)])}/{m.group(3)}"
    return path


def parse(paths):
    g = Graph()
    for p in paths:
        g.parse(os.path.join(ONTOLOGY, resolve(p)))
    return g


def build(name):
    m = MODULES[name]
    iri, lab = URIRef(MODULES_NS + name), label(m)
    g = parse(m["parts"])
    for prefix, ns in (("dcterms", DCTERMS), ("owl", OWL)):
        g.bind(prefix, ns)
    # The ontology header names the version; the module refers to others by IRI and imports none.
    g.remove((iri, None, None))
    g.add((iri, RDF.type, OWL.Ontology))
    g.add((iri, DCTERMS.title, Literal(m["title"], lang="en")))
    g.add((iri, DCTERMS.description, Literal(m["description"], lang="en")))
    g.add((iri, OWL.versionInfo, Literal(lab)))
    g.add((iri, OWL.versionIRI, URIRef(f"{iri}/{lab}")))
    for dep, version in sorted(dependencies(name).items()):
        g.add((iri, DCTERMS.requires, URIRef(f"{MODULES_NS}{dep}/{version}")))
    if m["issued"]:
        # Issued and modified dates on every release, both the issue date at the cut (playbook
        # Step 10; build_core.py does the same for core).
        g.add((iri, DCTERMS.issued, Literal(m["issued"], datatype=XSD.date)))
        g.add((iri, DCTERMS.modified, Literal(m["issued"], datatype=XSD.date)))
    return g


def released_requires(dep, version):
    """What a released package requires, read from its own manifest on disk, never from this builder's
    current table: a later release of that module must not change what an earlier package loads."""
    folder = package_folder(dep, version)
    if folder is None:
        raise FileNotFoundError(f"{dep} {version} is not on disk (releases/ or releases/previous/)")
    with open(os.path.join(folder, "manifest.json")) as f:
        return json.load(f).get("depends_on") or {}


def current_requires(dep, version):
    """What a package of the newest set requires: the builder's own table (dependencies), and nothing for core,
    which depends on no module. Read in place of the manifests, because the newest packages are rebuilt in some
    order and a manifest not yet rebuilt may still name a version the tree does not hold."""
    return dependencies(dep) if dep in MODULES else {}


def released_closure(name):
    """Every released package this module's check loads: its dependencies at the versions it names,
    and theirs, down to core. Where two paths name different versions of one module, the highest is loaded,
    so a graph never holds two releases of one module. The requirements come from the builder's table
    (current_requires), never a manifest."""
    return closure(dependencies(name), current_requires)


def closure(depends_on, requires=None):
    """The released packages that the given dependencies load, by the rule of released_closure. A
    written package's closure starts from its own manifest: closure(released_requires(name, version)).
    It settles on the highest release of each module reachable from the given requirements through the
    chosen releases' own requirements (`requires`, each chosen release's manifest unless told otherwise), so a
    release that loses to a higher one adds nothing (the fixed point of the ontology skill's
    check_packages.closure, a change to the skills folder)."""
    def key(version):
        return tuple(map(int, version.split(".")))
    requires = requires or released_requires  # looked up when called, so a test may stand in for the manifests
    chosen = {}
    for _ in range(1000):
        want = {}
        for deps in [dict(depends_on)] + [requires(dep, version) for dep, version in chosen.items()]:
            for dep, version in deps.items():
                if dep not in want or key(version) > key(want[dep]):
                    want[dep] = version
        if want == chosen:
            return chosen
        chosen = want
    raise ValueError("the dependency closure does not settle")


def validation_graph(name, g):
    """The data the module's shapes run over: the module, with the released packages of its closure."""
    data = Graph()
    data += g
    for dep, version in sorted(released_closure(name).items()):
        data.parse(os.path.join(ONTOLOGY, "releases", dep, version, f"{dep}.ttl"))
    return data


def check(name, g):
    """The module's shapes over the module, with the released packages it depends on loaded: core for
    the concepts a module refers to, the organization release for ref-mpc, and the released
    data-product and kpi packages for value-stream and market-data."""
    # advanced=True: SHACL-AF targets such as sh:SPARQLTarget run, as in every other check (the decision of 2026-10-23).
    data = validation_graph(name, g)
    for path in MODULES[name].get("graphs", []):  # a module's own graphs kept as files (graphs, below) are data for its shapes
        data.parse(os.path.join(ONTOLOGY, path))
    conforms, _, text = validate(data, shacl_graph=parse(MODULES[name]["shapes"]), advanced=True)
    return conforms, text


def jsonld(g):
    """JSON-LD with nodes, keys and values in a fixed order, so a rebuild is byte-identical (as for core)."""
    data = json.loads(g.serialize(format="json-ld"))
    nodes = data if isinstance(data, list) else data.get("@graph", [data])
    for node in nodes:
        for key, value in node.items():
            if isinstance(value, list):
                node[key] = sorted(value, key=lambda v: json.dumps(v, sort_keys=True))
    nodes.sort(key=lambda n: n.get("@id", ""))
    return json.dumps(nodes, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def catalog(name):
    m = MODULES[name]
    iri, lab = MODULES_NS + name, label(m)
    base = f"{iri}/releases/{lab}"
    g = Graph()
    g.bind("dcat", DCAT)
    g.bind("dcterms", DCTERMS)
    cat, dataset = URIRef("https://w3id.org/mpc/ontology/catalog"), URIRef(f"{iri}/{lab}")
    g.add((cat, RDF.type, DCAT.Catalog))
    g.add((cat, DCAT.dataset, dataset))
    g.add((dataset, RDF.type, DCAT.Dataset))
    g.add((dataset, DCTERMS.title, Literal(f"{m['title']} {lab}", lang="en")))
    g.add((dataset, DCTERMS.isVersionOf, URIRef(iri)))
    g.add((dataset, OWL.versionInfo, Literal(lab)))
    if m["issued"]:
        g.add((dataset, DCTERMS.issued, Literal(m["issued"], datatype=XSD.date)))
    for fname, media in ((f"{name}.ttl", "text/turtle"), (f"{name}.jsonld", "application/ld+json"),
                         ("shapes.ttl", "text/turtle"), *((os.path.basename(p), "text/turtle") for p in m.get("graphs", []))):
        dist = URIRef(f"{base}/{fname}")
        g.add((dataset, DCAT.distribution, dist))
        g.add((dist, RDF.type, DCAT.Distribution))
        g.add((dist, DCAT.downloadURL, dist))
        g.add((dist, DCAT.mediaType, Literal(media)))
    return g.serialize(format="turtle")


def package(name, g):
    m = MODULES[name]
    lab = label(m)
    # The package's own shape files lead the list (most modules have one); the rest belong to the modules it requires.
    shapes = parse(m["shapes"][:m.get("own_shapes", 1)])
    files = {f"{name}.ttl": g.serialize(format="turtle"), f"{name}.jsonld": jsonld(g),
             "shapes.ttl": shapes.serialize(format="turtle"), "catalog.ttl": catalog(name)}
    with open(os.path.join(ONTOLOGY, "releases", name, "CHANGELOG.md")) as f:
        files["CHANGELOG.md"] = f.read()
    # "graphs": files the package carries as they are, each in its own graph beside <name>.ttl, such as a logical model's
    # export and its annotation layer (the decision of 2026-11-02). Only the logical-model module has any.
    for path in m.get("graphs", []):
        with open(os.path.join(ONTOLOGY, path), encoding="utf-8") as f:
            files[os.path.basename(path)] = f.read()
    files["manifest.json"] = json.dumps({
        "module": name, "version": lab, "release_candidate": m["stage"] is not None,
        "ontology_iri": MODULES_NS + name, "version_iri": f"{MODULES_NS}{name}/{lab}",
        "depends_on": dependencies(name), "decisions": m["decisions"], "triples": len(g),
        "approved_by": None if m["stage"] else {"who": m.get("approver", "The decision owner"),
                                                 **({"recorded_in": where} if (where := recorded_where(m["approval"][0])) else {}),
                                                 "words": m["approval"][1]},
        # "augment": the files a module's models were built from, each with its SHA-256 (the decision of 2026-11-02);
        # only the logical-model module has it.
        **({"augment": m["augment"]} if m.get("augment") else {}),
        "files": {n: hashlib.sha256(t.encode()).hexdigest() for n, t in sorted(files.items())}}, indent=2) + "\n"
    return files


def release_dir(name):
    return os.path.join(ONTOLOGY, "releases", name, label(MODULES[name]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("module", choices=sorted(MODULES))
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--rebuild-released", action="store_true", help="overwrite a released package: a rebuild of the whole set")
    args = ap.parse_args()
    g = build(args.module)
    conforms, text = check(args.module, g)
    if not conforms:
        sys.exit(f"{args.module}: the shapes fail:\n{text}")
    files = package(args.module, g)
    out = release_dir(args.module)
    print(f"{args.module} {label(MODULES[args.module])}: {len(g)} triples; shapes conform")
    if args.verify:
        stale = [n for n, t in files.items()
                 if not os.path.exists(os.path.join(out, n)) or open(os.path.join(out, n)).read() != t]
        if stale:
            sys.exit(f"{args.module} release package is not current: {stale}")
        print("release package is current")
    if args.write:
        if MODULES[args.module]["stage"] is None:  # a candidate may change until it is released
            newest.refuse_overwrite(out, files, f"{args.module} {label(MODULES[args.module])}", args.rebuild_released)
        os.makedirs(out, exist_ok=True)
        for n, t in files.items():
            with open(os.path.join(out, n), "w") as f:
                f.write(t)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
