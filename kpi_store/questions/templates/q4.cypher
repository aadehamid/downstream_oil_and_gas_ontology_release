// title: The impact of a late source system: the tables, data products and KPIs that depend on it, on both graphs
// param: system | required | The system's code, such as mips. Case is ignored.
// language-tagged: label
//
// One row per thing that depends on the system. The KPI Store graph gives the replica tables that copy the
// system and everything built from them. The governance graph gives the tables the system holds and, where it
// records lineage, the tables built from those.
CALL () {
  USE graph.byName($bpa_graph)
  OPTIONAL MATCH (s:{{label:ontology_system.node}})
  WHERE toLower(s.{{property:ontology_system.code}}) = toLower($system)
  OPTIONAL MATCH (replica:{{label:platform_table.node}})-[:{{relationship:platform_table.copies_system}}]->(s)
  OPTIONAL MATCH (built:{{label:platform_table.node}})-[:{{relationship:platform_table.derived_from}}*1..6]->(replica)
  OPTIONAL MATCH (built)-[:{{relationship:platform_table.in_layer}}]->(l:{{label:layer.node}})
  OPTIONAL MATCH (built)-[:{{relationship:platform_table.part_of}}]->(p:{{label:data_product.node}})
  OPTIONAL MATCH (built)-[:{{relationship:platform_table.serves_measure}}]->(m:{{label:measure.node}})
  WITH collect(DISTINCT {kind: 'replica table', name: replica.{{property:platform_table.full_name}},
                         label: null, layer: 'replica'})
     + collect(DISTINCT {kind: CASE l.{{property:layer.code}} WHEN 'metric-view' THEN 'metric view'
                                    ELSE l.{{property:layer.code}} + ' table' END,
                         name: built.{{property:platform_table.full_name}},
                         label: null, layer: l.{{property:layer.code}}})
     + collect(DISTINCT {kind: 'data product', name: p.{{property:data_product.code}},
                         label: p.{{property:data_product.name}}, layer: null})
     + collect(DISTINCT {kind: 'kpi', name: m.{{property:measure.code}},
                         label: m.{{property:measure.name}}, layer: null}) AS things
  RETURN [thing IN things WHERE thing.name IS NOT NULL | thing {.*, graph: 'kpi store'}] AS in_kpi_store
}
CALL () {
  USE graph.byName($governance_graph)
  OPTIONAL MATCH (g:{{label:system.node}})
  WHERE toLower(g.{{property:system.code}}) = toLower($system)
  OPTIONAL MATCH (g)-[{{path:system_to_table}}]->(t:{{label:table.node}})
//#if table.derived_from
  OPTIONAL MATCH (built:{{label:table.node}})-[:{{relationship:table.derived_from}}*1..6]->(t)
//#if table.layer
  WITH collect(DISTINCT {kind: 'table', name: t.{{property:table.qualified_name}}, label: null,
                         layer: t.{{property:table.layer}}})
     + collect(DISTINCT {kind: 'derived table', name: built.{{property:table.qualified_name}}, label: null,
                         layer: built.{{property:table.layer}}}) AS things
//#else
  WITH collect(DISTINCT {kind: 'table', name: t.{{property:table.qualified_name}}, label: null, layer: null})
     + collect(DISTINCT {kind: 'derived table', name: built.{{property:table.qualified_name}}, label: null,
                         layer: null}) AS things
//#endif
//#else
//#if table.layer
  WITH collect(DISTINCT {kind: 'table', name: t.{{property:table.qualified_name}}, label: null,
                         layer: t.{{property:table.layer}}}) AS things
//#else
  WITH collect(DISTINCT {kind: 'table', name: t.{{property:table.qualified_name}}, label: null, layer: null})
       AS things
//#endif
//#endif
  RETURN [thing IN things WHERE thing.name IS NOT NULL | thing {.*, graph: 'governance'}] AS in_governance
}
UNWIND in_kpi_store + in_governance AS thing
RETURN thing.graph AS graph, thing.kind AS kind, thing.name AS name, thing.label AS label, thing.layer AS layer
ORDER BY graph DESC, CASE kind WHEN 'replica table' THEN 1 WHEN 'silver table' THEN 2 WHEN 'gold table' THEN 3
                               WHEN 'metric view' THEN 4 WHEN 'data product' THEN 5 WHEN 'kpi' THEN 6
                               WHEN 'table' THEN 7 ELSE 8 END, name
