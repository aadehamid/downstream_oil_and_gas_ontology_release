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
//
// The query has five parts. Three read the KPI Store graph, one reads the governance graph, and the last joins
// their results on values, because no relationship runs from one graph to the other.
//
// Part 1, KPI Store graph. Each table that copies a system, with the system's code, the table's name and the
// layers of the tables built from it, as one list (by_name) that the last part searches.
CALL () {
  USE graph.byName($bpa_graph)
  OPTIONAL MATCH (replica:{{label:platform_table.node}})-[:{{relationship:platform_table.copies_system}}]->(s:{{label:ontology_system.node}})
  // The tables built from the replica, through at most 6 steps of lineage. The bound keeps the search finite; a
  // table more than 6 steps away is not found.
  OPTIONAL MATCH (built:{{label:platform_table.node}})-[:{{relationship:platform_table.derived_from}}*1..6]->(replica)
  OPTIONAL MATCH (built)-[:{{relationship:platform_table.in_layer}}]->(l:{{label:layer.node}})
  WITH replica, toLower(s.{{property:ontology_system.code}}) AS code,
       split(toLower(replica.{{property:platform_table.full_name}}), '.')[-1] AS table_name,
       collect(DISTINCT l.{{property:layer.code}}) AS built_layers
  // A row with no replica table, which the optional match gives when the graph holds none, adds nothing to the
  // list: collect leaves out null.
  WITH collect(CASE WHEN replica IS NULL THEN null ELSE {
         // A replica table's name may start with its system's code. The governance graph may leave it out.
         keys: [code + '.' + table_name,
                code + '.' + CASE WHEN table_name STARTS WITH code + '_'
                                  THEN substring(table_name, size(code) + 1) ELSE table_name END],
         layers: ['replica'] + built_layers} END) AS by_name
  RETURN by_name
}
// Part 2, KPI Store graph. The codes of the systems the ontology holds, for the in_kpi_store column.
CALL () {
  USE graph.byName($bpa_graph)
  MATCH (s:{{label:ontology_system.node}})
  RETURN collect(DISTINCT toLower(s.{{property:ontology_system.code}})) AS ontology_codes
}
//#if replaces tech.object tech.name tech.designed_as
// Part 3, KPI Store graph, kept only when the mapping names the technical graph's roles. Each link from a Databricks table to
// the Synapse table it replaces, with the layer of the Databricks table's design, as one list (by_link).
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
// The mapping names no technical graph roles, so no table is found by a link. The names alone answer.
WITH by_name, ontology_codes, [] AS by_link
//#endif
// Part 4, governance graph. Each system, or the one asked for, with the qualified names of the tables it holds.
CALL (by_name, by_link, ontology_codes) {
  USE graph.byName($governance_graph)
  MATCH (g:{{label:system.node}})
  WHERE $system = '' OR toLower(g.{{property:system.code}}) = toLower($system)
  OPTIONAL MATCH (g)-[{{path:system_to_table}}]->(t:{{label:table.node}})
  WITH DISTINCT g.{{property:system.code}} AS system, t.{{property:table.qualified_name}} AS qualified_name
  RETURN system, collect(qualified_name) AS held
}
// Part 5, the join. One row per table. A system with no table gets one empty row, so it still shows, with 0 tables.
UNWIND CASE WHEN size(held) = 0 THEN [null] ELSE held END AS qualified_name
// linked holds the layers a link gives this table, found by its qualified name in lower case.
// named holds the layers the name gives: the system's code and the table's own name must be one of a replica's keys.
WITH system, ontology_codes, qualified_name,
     [link IN by_link WHERE link.key = toLower(qualified_name) | link.layer] AS linked,
     reduce(layers = [], found IN [entry IN by_name
                                   WHERE toLower(system) + '.' + toLower(split(qualified_name, '.')[-1]) IN entry.keys
                                   | entry.layers] | layers + found) AS named
WITH system, ontology_codes, qualified_name, linked, linked + named AS layers
// count() passes over the empty row, and each sum counts a table once per layer it has a counterpart in.
RETURN system,
       toLower(system) IN ontology_codes AS in_kpi_store,
       count(qualified_name) AS tables,
       sum(CASE WHEN 'replica' IN layers THEN 1 ELSE 0 END) AS replica,
       sum(CASE WHEN 'silver' IN layers THEN 1 ELSE 0 END) AS silver,
       sum(CASE WHEN 'gold' IN layers THEN 1 ELSE 0 END) AS gold,
       sum(CASE WHEN size(linked) > 0 THEN 1 ELSE 0 END) AS by_link
ORDER BY system
