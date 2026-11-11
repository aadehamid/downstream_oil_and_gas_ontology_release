// title: From a KPI to its source systems: the full chain, with the quality result where one is recorded
// param: kpi | required | The measure's code (such as crude-prices) or its name. Case is ignored.
// param: sample | default 5 | How many of the governance system's tables to list.
// language-tagged: kpi system
//
// One row per chain from the measure to a replica table. The KPI Store graph gives the chain. The governance
// graph gives the system under the same code, how many tables it holds, and the table the replica copies.
//
// Part 1, KPI Store graph. The measure, by its code or by its name. A name ends in a language tag such as @en,
// so only the text before the @ is compared.
CALL () {
  USE graph.byName($bpa_graph)
  MATCH (m:{{label:measure.node}})
  WHERE toLower(m.{{property:measure.code}}) = toLower($kpi)
     OR toLower(split(m.{{property:measure.name}}, '@')[0]) = toLower($kpi)
  // The metric view that serves the measure, then each chain of lineage from it down to a replica table and the
  // system the replica copies. 0 steps covers a view that reads a replica directly, and 6 bounds the search.
  MATCH (mv:{{label:platform_table.node}})-[:{{relationship:platform_table.serves_measure}}]->(m)
  MATCH chain = (mv)-[:{{relationship:platform_table.derived_from}}*0..6]->(replica:{{label:platform_table.node}})
        -[:{{relationship:platform_table.copies_system}}]->(s:{{label:ontology_system.node}})
  // The chain's tables, each with its layer. The chain's last node is the system, so it is left out.
  WITH m, mv, replica, s,
       [n IN nodes(chain)[..-1] | {
         name: n.{{property:platform_table.full_name}},
         layer: head([(n)-[:{{relationship:platform_table.in_layer}}]->(l:{{label:layer.node}}) | l.{{property:layer.code}}])
       }] AS objects
  WITH DISTINCT m, mv, replica, s,
       [o IN objects WHERE o.layer = 'gold' | o.name] AS gold,
       [o IN objects WHERE o.layer = 'silver' | o.name] AS silver,
       [o IN objects | o.name] AS names
//#if tech.check tech.check_name tech.check_result tech.checks tech.object tech.designed_as
  // Kept only when the technical graph is loaded. The quality checks on any table of the chain: a check tests a
  // built object, and the built object points to its design. Sorting before collect fixes the list's order.
  OPTIONAL MATCH (qc:{{label:tech.check}})-[:{{relationship:tech.checks}}]->(:{{label:tech.object}})
                 -[:{{relationship:tech.designed_as}}]->(checked:{{label:platform_table.node}})
  WHERE checked.{{property:platform_table.full_name}} IN names
  WITH DISTINCT m, mv, replica, s, gold, silver, checked, qc
  ORDER BY checked.{{property:platform_table.full_name}}, qc.{{property:tech.check_name}}
  WITH m, mv, replica, s, gold, silver,
       collect({
         object: checked.{{property:platform_table.full_name}},
         check: qc.{{property:tech.check_name}},
         result: qc.{{property:tech.check_result}},
//#if tech.check_at
         checked_at: toString(qc.{{property:tech.check_at}})
//#else
         checked_at: null
//#endif
       }) AS checks
  // A chain with no check gives one entry of nulls from the optional match. It is removed here.
  WITH m, mv, replica, s, gold, silver, [c IN checks WHERE c.check IS NOT NULL] AS quality
//#else
  // No technical graph, so no quality result is recorded.
  WITH m, mv, replica, s, gold, silver, [] AS quality
//#endif
  WITH m, mv, replica, s, gold, silver, quality,
       toLower(s.{{property:ontology_system.code}}) AS code,
       split(toLower(replica.{{property:platform_table.full_name}}), '.')[-1] AS table_name
  RETURN m.{{property:measure.code}} AS kpi_code,
         m.{{property:measure.name}} AS kpi,
         mv.{{property:platform_table.full_name}} AS metric_view,
         gold, silver,
         replica.{{property:platform_table.full_name}} AS replica,
         s.{{property:ontology_system.code}} AS system_code,
         s.{{property:ontology_system.name}} AS system,
         quality,
         // A replica table's name may start with its system's code. The governance graph may leave it out.
         [code + '.' + table_name,
          code + '.' + CASE WHEN table_name STARTS WITH code + '_'
                            THEN substring(table_name, size(code) + 1) ELSE table_name END] AS table_keys
}
// Part 2, governance graph, once per row of part 1. The system with the same code, how many tables it holds, a
// sample of their names, and the table the replica copies, found by the keys built above.
CALL (system_code, table_keys) {
  USE graph.byName($governance_graph)
  OPTIONAL MATCH (g:{{label:system.node}})
  WHERE toLower(g.{{property:system.code}}) = toLower(system_code)
  OPTIONAL MATCH (g)-[{{path:system_to_table}}]->(t:{{label:table.node}})
  WITH DISTINCT g, t.{{property:table.qualified_name}} AS qualified_name
  ORDER BY qualified_name
  WITH g, collect(qualified_name) AS held
  RETURN g.{{property:system.code}} AS governance_system,
         size(held) AS governance_tables,
         held[..$sample] AS governance_table_sample,
         [q IN held WHERE toLower(g.{{property:system.code}}) + '.' + toLower(split(q, '.')[-1]) IN table_keys]
           AS governance_table
}
RETURN kpi_code, kpi, metric_view, gold, silver, replica, system_code, system, quality,
       governance_system, governance_tables, governance_table_sample, governance_table
ORDER BY metric_view, system_code, replica, gold, silver
