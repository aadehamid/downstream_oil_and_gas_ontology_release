// title: Migration progress by system and layer: how many of each system's tables have a Databricks counterpart
// param: system | default "" | One system's code, or empty for every system. Case is ignored.
//
// One row per system of the governance graph: how many tables it holds and how many of them have a counterpart
// in the replica, silver and gold layers of the KPI Store.
//
// Two things give a table a counterpart, and either is enough. The first is a link: the technical graph
// records the Synapse table a Databricks table replaces, and the Databricks table's design gives the layer.
// The second is the name: a replica table that copies the same system and has the same table name, with every
// silver and gold table built from that replica. A graph with no such links answers from the names alone.
// The by_link column counts the tables a link found.
CALL () {
  USE graph.byName($bpa_graph)
  OPTIONAL MATCH (replica:{{label:platform_table.node}})-[:{{relationship:platform_table.copies_system}}]->(s:{{label:ontology_system.node}})
  OPTIONAL MATCH (built:{{label:platform_table.node}})-[:{{relationship:platform_table.derived_from}}*1..6]->(replica)
  OPTIONAL MATCH (built)-[:{{relationship:platform_table.in_layer}}]->(l:{{label:layer.node}})
  WITH replica, toLower(s.{{property:ontology_system.code}}) AS code,
       split(toLower(replica.{{property:platform_table.full_name}}), '.')[-1] AS table_name,
       collect(DISTINCT l.{{property:layer.code}}) AS built_layers
  WITH collect(CASE WHEN replica IS NULL THEN null ELSE {
         // A replica table's name may start with its system's code. The governance graph may leave it out.
         keys: [code + '.' + table_name,
                code + '.' + CASE WHEN table_name STARTS WITH code + '_'
                                  THEN substring(table_name, size(code) + 1) ELSE table_name END],
         layers: ['replica'] + built_layers} END) AS by_name
  RETURN by_name
}
CALL () {
  USE graph.byName($bpa_graph)
  MATCH (s:{{label:ontology_system.node}})
  RETURN collect(DISTINCT toLower(s.{{property:ontology_system.code}})) AS ontology_codes
}
//#if replaces tech.object tech.name tech.designed_as
CALL () {
  USE graph.byName($bpa_graph)
  OPTIONAL MATCH (new:{{label:tech.object}})-[:{{relationship:replaces}}]->(old:{{label:tech.object}}),
                 (new)-[:{{relationship:tech.designed_as}}]->(:{{label:platform_table.node}})
                 -[:{{relationship:platform_table.in_layer}}]->(l:{{label:layer.node}})
  WITH split(toLower(old.{{property:tech.name}}), '.') AS parts, l.{{property:layer.code}} AS layer
  // The governance graph names a table schema.table, so only the last two parts of the Synapse name count.
  RETURN collect(CASE WHEN layer IS NULL OR size(parts) < 2 THEN null
                      ELSE {key: parts[-2] + '.' + parts[-1], layer: layer} END) AS by_link
}
//#else
WITH by_name, ontology_codes, [] AS by_link
//#endif
CALL (by_name, by_link, ontology_codes) {
  USE graph.byName($governance_graph)
  MATCH (g:{{label:system.node}})
  WHERE $system = '' OR toLower(g.{{property:system.code}}) = toLower($system)
  OPTIONAL MATCH (g)-[{{path:system_to_table}}]->(t:{{label:table.node}})
  WITH DISTINCT g.{{property:system.code}} AS system, t.{{property:table.qualified_name}} AS qualified_name
  RETURN system, collect(qualified_name) AS held
}
UNWIND CASE WHEN size(held) = 0 THEN [null] ELSE held END AS qualified_name
WITH system, ontology_codes, qualified_name,
     [link IN by_link WHERE link.key = toLower(qualified_name) | link.layer] AS linked,
     reduce(layers = [], found IN [entry IN by_name
                                   WHERE toLower(system) + '.' + toLower(split(qualified_name, '.')[-1]) IN entry.keys
                                   | entry.layers] | layers + found) AS named
WITH system, ontology_codes, qualified_name, linked, linked + named AS layers
RETURN system,
       toLower(system) IN ontology_codes AS in_kpi_store,
       count(qualified_name) AS tables,
       sum(CASE WHEN 'replica' IN layers THEN 1 ELSE 0 END) AS replica,
       sum(CASE WHEN 'silver' IN layers THEN 1 ELSE 0 END) AS silver,
       sum(CASE WHEN 'gold' IN layers THEN 1 ELSE 0 END) AS gold,
       sum(CASE WHEN size(linked) > 0 THEN 1 ELSE 0 END) AS by_link
ORDER BY system
