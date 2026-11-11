"""Cross-graph questions: query templates that join the KPI Store graph to a governance graph.

Both graphs are members of one Neo4j composite database. A query cannot follow a relationship from one member
to the other, so each question joins on values: a system code, or a table's qualified name.

The governance graph belongs to its owner and its labels can change. So no template names a label, a property
or a relationship type. A template names roles (`roles.py`). `discover.py` reads each graph's schema and
proposes which label, property or relationship type plays each role. A person confirms that mapping once
(`mapping.py`). Every later run checks the mapping against the live schema before it asks anything, and
`render.py` builds a query only from a confirmed mapping. `run.py` is the command line.
"""
