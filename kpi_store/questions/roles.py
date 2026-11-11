"""The roles the question templates need, with what each one means and the names to try first.

A role is a slot in a template: "the node that stands for a source system", "the property that holds a table's
qualified name". The candidates are first guesses only. Discovery matches them to a graph's real schema, and a
person confirms the result.

This module holds the list and nothing else: it reads and writes no file and no graph. The templates name these
roles in their placeholders, `discover.py` proposes a value for each, `mapping.py` checks each against the live
schema, and `render.py` replaces each placeholder with its confirmed value. A new question that needs a new
label, property or relationship type adds a role here first.

A role's name reads <thing>.<aspect>: `system.node` is the label, `system.code` a property on that label.
"""
from __future__ import annotations

from dataclasses import dataclass

# The two graphs. "bpa" is the KPI Store graph, as in the bpa_alias connection setting.
GOVERNANCE = "governance"
BPA = "bpa"
GRAPHS = (GOVERNANCE, BPA)

# The four kinds of role. A path is one or more relationship types followed for a bounded number of steps.
LABEL = "label"
PROPERTY = "property"
RELATIONSHIP = "relationship"
PATH = "path"


@dataclass(frozen=True)
class Role:
    """One slot a template can name. A required role must have a value before any question runs. An optional
    role may have none, and a template then leaves out the part that needs it."""
    name: str
    graph: str
    kind: str
    meaning: str
    candidates: tuple[str, ...]
    required: bool = True
    on: str = ""                  # a property's label role
    start: str = ""               # a relationship's or path's start label role
    ends: tuple[str, ...] = ()    # the label roles a relationship or path may end at


# Short forms for the three shapes of role, so the list below reads one role per entry. The candidates are in
# order of preference: discovery scores the first one highest.
def _label(name, graph, meaning, *candidates, required=True):
    return Role(name, graph, LABEL, meaning, candidates, required)


def _prop(name, graph, on, meaning, *candidates, required=True):
    return Role(name, graph, PROPERTY, meaning, candidates, required, on=on)


def _rel(name, graph, start, ends, meaning, *candidates, required=True, kind=RELATIONSHIP):
    return Role(name, graph, kind, meaning, candidates, required, start=start, ends=tuple(ends))


ROLES = (
    # The governance graph. The candidates are the names its model gives; discovery confirms or replaces them.
    _label("system.node", GOVERNANCE, "A node that stands for one source system.",
           "DataSystem", "System", "SourceSystem"),
    _prop("system.code", GOVERNANCE, "system.node",
          "The system's short code. It equals a KPI Store system's code when case is ignored.",
          "name", "code", "systemCode"),
    _label("table.node", GOVERNANCE, "A node that stands for one table.", "Table"),
    _prop("table.qualified_name", GOVERNANCE, "table.node", "The table's name with its schema: schema.table.",
          "qualifiedName", "fullName", "name"),
    _prop("table.layer", GOVERNANCE, "table.node", "The layer the table is in, as the governance graph names it.",
          "layer", required=False),
    _rel("system_to_table", GOVERNANCE, "system.node", ["table.node"],
         "The relationship types that lead from a system to the tables it holds, in at most a few steps.",
         "HOSTS", "CONTAINS", kind=PATH),
    _rel("table.derived_from", GOVERNANCE, "table.node", ["table.node"],
         "From a table to a table it is built from.", "DERIVED_FROM", required=False),
    _label("policy.node", GOVERNANCE, "A node that stands for one policy, such as a SOX or confidentiality rule.",
           "Policy", required=False),
    _prop("policy.name", GOVERNANCE, "policy.node", "The policy's name.",
          "name", "policyName", "title", required=False),
    _rel("policy.applies_to", GOVERNANCE, "policy.node", ["system.node", "table.node"],
         "From a policy to a system or a table it covers.", "APPLIES_TO", required=False),
    _prop("system.classification", GOVERNANCE, "system.node", "The system's sensitivity class, where it has one.",
          "classification", "dataClassification", "sensitivity", "confidentiality", required=False),
    _prop("table.classification", GOVERNANCE, "table.node", "The table's sensitivity class, where it has one.",
          "classification", "dataClassification", "sensitivity", "confidentiality", required=False),

    # The KPI Store graph. The candidates are the names the property-graph projection writes: the fixed prefix,
    # one underscore, the local name.
    _label("measure.node", BPA, "A measure definition of the kpi module. A KPI is one of these.",
           "kpi_MeasureDefinition"),
    _prop("measure.code", BPA, "measure.node", "The measure's code.", "skos_notation"),
    _prop("measure.name", BPA, "measure.node", "The measure's name.", "skos_prefLabel"),
    _label("platform_table.node", BPA, "A table or view on the data platform, as designed.", "dp_PlatformTable"),
    _prop("platform_table.full_name", BPA, "platform_table.node", "Catalog, schema and name.", "dp_fullName"),
    _rel("platform_table.serves_measure", BPA, "platform_table.node", ["measure.node"],
         "From a metric view to a measure whose values it gives.", "dp_servesMeasure"),
    _rel("platform_table.derived_from", BPA, "platform_table.node", ["platform_table.node"],
         "From a table or view to a table it is built from.", "prov_wasDerivedFrom"),
    _label("layer.node", BPA, "A value of the layer code list: replica, silver, gold or metric view.",
           "skos_Concept"),
    _prop("layer.code", BPA, "layer.node", "The layer's code.", "skos_notation"),
    _rel("platform_table.in_layer", BPA, "platform_table.node", ["layer.node"],
         "From a table or view to its layer.", "dp_layer"),
    _label("ontology_system.node", BPA, "A system of the system module.", "sys_System"),
    _prop("ontology_system.code", BPA, "ontology_system.node", "The system's code, in lower case.",
          "skos_notation"),
    _prop("ontology_system.name", BPA, "ontology_system.node", "The system's name.", "skos_prefLabel"),
    _rel("platform_table.copies_system", BPA, "platform_table.node", ["ontology_system.node"],
         "From a replica table to the system whose records it copies.", "dp_copiesSystem"),
    _label("data_product.node", BPA, "A data product of the portfolio.", "dp_DataProduct"),
    _prop("data_product.code", BPA, "data_product.node", "The data product's code.", "skos_notation"),
    _prop("data_product.name", BPA, "data_product.node", "The data product's name.", "skos_prefLabel"),
    _rel("platform_table.part_of", BPA, "platform_table.node", ["data_product.node"],
         "From a table or view to the data product it is part of.", "dcterms_isPartOf"),

    # The technical graph, in the KPI Store graph. Optional: a question leaves the part out when it is absent.
    _label("tech.object", BPA, "A thing the technical graph records as built.", "Tech", required=False),
    _prop("tech.name", BPA, "tech.object", "The built thing's name on its platform.", "name", required=False),
    _rel("tech.designed_as", BPA, "tech.object", ["platform_table.node"],
         "From a built table or view to its design.", "DESIGNED_AS", required=False),
    _label("tech.check", BPA, "A quality check, as last run.", "QualityCheck", required=False),
    _prop("tech.check_name", BPA, "tech.check", "The check's name.", "name", required=False),
    _prop("tech.check_result", BPA, "tech.check", "What the check found: pass, fail or differs.",
          "result", required=False),
    _prop("tech.check_at", BPA, "tech.check", "When the check last ran.", "checkedAt", required=False),
    _rel("tech.checks", BPA, "tech.check", ["tech.object"],
         "From a quality check to a thing it tests.", "CHECKS", required=False),
    _rel("replaces", BPA, "tech.object", ["tech.object"],
         "From a Databricks table to the Synapse table it replaces.", "REPLACES", required=False),
)

BY_NAME = {role.name: role for role in ROLES}
# A second role with the same name would replace the first in BY_NAME without a word, so the import stops here.
assert len(BY_NAME) == len(ROLES), "two roles share a name"


def role(name: str) -> Role:
    """The role with this name. Raises KeyError with a readable message for a name no role has."""
    if name not in BY_NAME:
        raise KeyError(f"no role named {name}")
    return BY_NAME[name]
