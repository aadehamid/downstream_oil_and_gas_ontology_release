// title: KPIs that rest on SOX-relevant or confidential systems
// param: terms | default ["sox", "confidential"] | Words that mark a policy or a class as sensitive. Case is ignored.
// needs-any: policy.applies_to system.classification table.classification
// language-tagged: kpi
//
// The governance graph says which systems are sensitive: a policy whose name holds one of the terms covers the
// system or one of its tables, or the system's or a table's class holds one of the terms. The KPI Store graph
// gives every KPI whose chain reaches a replica of such a system. One row per KPI, metric view and system.
//
// Part 1, governance graph. Each system with its tables, then the reasons that make it sensitive. Each of the
// three sources of a reason is kept only when the governance graph has it, and the header asks for at least one.
CALL () {
  USE graph.byName($governance_graph)
  MATCH (g:{{label:system.node}})
  OPTIONAL MATCH (g)-[{{path:system_to_table}}]->(t:{{label:table.node}})
  WITH DISTINCT g, t ORDER BY t.{{property:table.qualified_name}}
  WITH g, collect(t) AS tables
//#if policy.node policy.name policy.applies_to
  // Source 1, a policy. It counts when its name holds one of the terms and it covers the system or one of its tables.
  OPTIONAL MATCH (p:{{label:policy.node}})-[:{{relationship:policy.applies_to}}]->(covered)
  WHERE (covered = g OR covered IN tables)
    AND any(term IN $terms WHERE toLower(toString(p.{{property:policy.name}})) CONTAINS toLower(term))
  WITH DISTINCT g, tables,
       'policy ' + p.{{property:policy.name}} + ' on '
       + CASE WHEN covered = g THEN 'the system'
              ELSE 'table ' + covered.{{property:table.qualified_name}} END AS reason
  ORDER BY reason
  WITH g, tables, collect(reason) AS reasons
//#else
  WITH g, tables, [] AS reasons
//#endif
//#if system.classification
  // Source 2, the system's own class, when it holds one of the terms.
  WITH g, tables, reasons
       + CASE WHEN any(term IN $terms
                       WHERE toLower(toString(g.{{property:system.classification}})) CONTAINS toLower(term))
              THEN ['class ' + toString(g.{{property:system.classification}}) + ' on the system']
              ELSE [] END AS reasons
//#endif
//#if table.classification
  // Source 3, the class of each of the system's tables, when it holds one of the terms.
  WITH g, reasons
       + [t IN tables
          WHERE any(term IN $terms
                    WHERE toLower(toString(t.{{property:table.classification}})) CONTAINS toLower(term))
          | 'class ' + toString(t.{{property:table.classification}}) + ' on table '
            + t.{{property:table.qualified_name}}] AS reasons
//#endif
  // Only a system with at least one reason goes on to the second part.
  WITH g, reasons WHERE size(reasons) > 0
  RETURN collect({code: toLower(g.{{property:system.code}}), system: g.{{property:system.code}},
                  reasons: reasons}) AS sensitive
}
// Part 2, KPI Store graph. For each sensitive system, the system with the same code in lower case, and every KPI
// served by a metric view whose lineage reaches a replica of it. 0 steps covers a view that reads a replica
// directly, and 6 bounds the search.
CALL (sensitive) {
  USE graph.byName($bpa_graph)
  UNWIND sensitive AS found
  MATCH (s:{{label:ontology_system.node}})
  WHERE toLower(s.{{property:ontology_system.code}}) = found.code
  MATCH (m:{{label:measure.node}})<-[:{{relationship:platform_table.serves_measure}}]-(mv:{{label:platform_table.node}})
        -[:{{relationship:platform_table.derived_from}}*0..6]->(:{{label:platform_table.node}})
        -[:{{relationship:platform_table.copies_system}}]->(s)
  RETURN DISTINCT m.{{property:measure.code}} AS kpi_code,
         m.{{property:measure.name}} AS kpi,
         mv.{{property:platform_table.full_name}} AS metric_view,
         s.{{property:ontology_system.code}} AS system_code,
         found.system AS governance_system,
         found.reasons AS reasons
}
RETURN kpi_code, kpi, metric_view, system_code, governance_system, reasons
ORDER BY kpi_code, metric_view, system_code
