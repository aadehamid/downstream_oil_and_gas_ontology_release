"""Cross-graph questions: query templates that join the KPI Store graph to a governance graph.

Both graphs are members of one Neo4j composite database. A query cannot follow a relationship from one member
to the other, so each question joins on values: a system code, or a table's qualified name.

The governance graph belongs to its owner and its labels can change. So no template names a label, a property
or a relationship type. A template names roles (`roles.py`). `discover.py` reads each graph's schema and
proposes which label, property or relationship type plays each role. A person confirms that mapping once
(`mapping.py`). Every later run checks the mapping against the live schema before it asks anything, and
`render.py` builds a query only from a confirmed mapping. `run.py` is the command line.

Where this sits in the run: the questions come after the stores are loaded. The runner's `enterprise` step copies
the KPI Store graph, with the technical graph, to the Neo4j Enterprise database, and that database is one member of
the composite. The runner asks no question. A person asks one with `run.py`.

The questions, each a template in `templates/`:
  q1  migration progress by system and layer
  q4  the impact of a late source system
  q6  from a KPI to its source systems, with the quality result where one is recorded
  q7  KPIs that rest on SOX-relevant or confidential systems

The package reads both graphs and writes to neither. It writes two kinds of file, both outside the release
folder: the mapping file and the answers.

The files, in the order a run uses them:
  connection.py  where the composite database is
  roles.py       the roles the templates name
  discover.py    reads a schema and proposes the mapping
  mapping.py     the mapping file, its confirmation and the drift check
  render.py      turns a template and a confirmed mapping into a query
  run.py         the command line: discover, confirm, check, ask
"""
