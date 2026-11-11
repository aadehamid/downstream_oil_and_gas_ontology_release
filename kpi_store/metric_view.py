"""Parses a metric view's definition and finds the table names inside SQL.

Databricks returns a metric view's definition from DESCRIBE TABLE EXTENDED <view> AS JSON. Its view_text is YAML
(version 1.1): a source that is a table name or a SQL query, optional joins and filter, dimensions, and measures
with an expression each. Needs pyyaml and sqlglot.

Where it sits: kpi_store.discovery calls parse_describe_json for every metric view it finds, and the comparison
then checks the view's tables against the sources the ontology names. The Gate of kpi_store.load_databricks uses
cte_references to decide which names in a statement are real tables. This module reads text only: it sends
nothing to Databricks, writes nothing and has no command.

pyyaml and sqlglot are loaded inside the functions that use them, so loading this module needs neither package.
"""
import json
import re
from dataclasses import dataclass, field

# A source that is a table name: one to three parts with dots between them, each with or without backticks. A
# source that does not match is taken as a SQL query.
TABLE_NAME = re.compile(r"^`?[\w$]+`?(\.`?[\w$]+`?){0,2}$")
# MEASURE(name) inside a measure's expression: a measure built on another measure. Group 1 is that measure's name.
MEASURE_REF = re.compile(r"\bMEASURE\s*\(\s*`?([\w$]+)`?\s*\)", re.IGNORECASE)


class MetricViewError(Exception):
    """A metric view's definition could not be read."""


@dataclass
class MetricView:
    """One metric view as its definition describes it."""
    name: str                                         # the view's full name, as Databricks spells it
    source: str = ""                                  # the source as written: a table name or a SQL query
    source_is_sql: bool = False
    tables: list = field(default_factory=list)        # every table the view reads, full names in lower case
    filter: str = ""
    dimensions: list = field(default_factory=list)    # [{"name", "expr"}]
    measures: list = field(default_factory=list)      # [{"name", "expr", "measure_refs", "display_name", ...}]
    measure_columns: list = field(default_factory=list)  # the column names DESCRIBE marks is_measure
    from_name: str = ""                               # table property metric_view.from.name

    def reads_column(self, column):
        """True when a measure, a dimension or the filter names the column. Case is ignored."""
        # The column as a whole word: Amount must not be found inside Amount_USD.
        word = re.compile(rf"(?<![\w$]){re.escape(column)}(?![\w$])", re.IGNORECASE)
        texts = [d.get("expr", "") for d in self.dimensions] + [m.get("expr", "") for m in self.measures] + [self.filter]
        return any(word.search(t or "") for t in texts)


def qualify(name, catalog=None, schema=None):
    """A table name as catalog.schema.name in lower case, without backticks. A shorter name takes the view's own
    catalog and schema, as Databricks resolves it."""
    parts = [p.strip("`") for p in name.strip().split(".")]
    parts = [catalog, schema][: 3 - len(parts)] + parts if len(parts) < 3 else parts
    if len(parts) != 3 or not all(parts):
        raise MetricViewError(f"cannot give {name!r} a catalog and a schema")
    return ".".join(parts).lower()


def cte_references(tree):
    """The table nodes of a parsed statement that name a WITH clause's query and not a table, as a set of id().

    A bare name is such a reference only where the WITH clause that defines it is in scope. The same bare name
    outside that scope is a real table, which Databricks would look up in the session's schema. Names compare
    without case, as Databricks compares them. A statement whose scopes cannot be built gives an empty set, so
    every bare name in it counts as a table."""
    from sqlglot import exp
    from sqlglot.errors import SqlglotError
    from sqlglot.optimizer.scope import traverse_scope
    queries = [tree] if isinstance(tree, exp.Query) else [q for q in tree.find_all(exp.Query) if not q.find_ancestor(exp.Query)]
    found = set()
    try:
        for query in queries:
            for scope in traverse_scope(query):
                in_scope = {name.lower() for name in scope.cte_sources}
                found |= {id(t) for t in scope.tables if not t.db and t.name.lower() in in_scope}
    except SqlglotError:
        return set()
    return found


def tables_in_sql(sql, catalog=None, schema=None):
    """The tables a SQL query reads, sorted, as full names in lower case. A name a WITH clause defines is not a table
    where that clause is in scope (cte_references)."""
    import sqlglot
    from sqlglot import exp
    try:
        tree = sqlglot.parse_one(sql, read="databricks")
    except sqlglot.errors.SqlglotError as err:
        raise MetricViewError(f"cannot parse the SQL: {str(err).splitlines()[0]}") from None
    defined = cte_references(tree)
    found = set()
    for table in tree.find_all(exp.Table):
        if not table.name or id(table) in defined:
            continue
        found.add(qualify(".".join(p for p in (table.catalog, table.db, table.name) if p), catalog, schema))
    return sorted(found)


def columns_in_sql(expression):
    """[(table qualifier or "", column name)] of the columns a SQL expression names, in lower case."""
    import sqlglot
    from sqlglot import exp
    try:
        tree = sqlglot.parse_one(expression, read="databricks")
    except sqlglot.errors.SqlglotError:
        return []
    return sorted({(c.table.lower(), c.name.lower()) for c in tree.find_all(exp.Column) if c.name})


def _joins(items, out):
    """Collects the source of every join into out, through the joins nested inside a join."""
    for item in items or []:
        if isinstance(item, dict):
            if item.get("source"):
                out.append(str(item["source"]))
            _joins(item.get("joins"), out)   # a snowflake join nests its own joins


def parse_yaml(view_text, name, catalog=None, schema=None):
    """A MetricView from the YAML definition. The view's catalog and schema complete any shorter table name."""
    import yaml
    try:
        doc = yaml.safe_load(view_text)
    except yaml.YAMLError as err:
        raise MetricViewError(f"{name}: the definition is not valid YAML: {str(err).splitlines()[0]}") from None
    if not isinstance(doc, dict) or not doc.get("source"):
        raise MetricViewError(f"{name}: the definition names no source")
    view = MetricView(name=name, source=str(doc["source"]).strip(), filter=str(doc.get("filter") or ""))
    view.source_is_sql = not TABLE_NAME.match(view.source)
    sources = []
    _joins(doc.get("joins"), sources)
    tables = set()
    for source in [view.source] + sources:
        if TABLE_NAME.match(source.strip()):
            tables.add(qualify(source, catalog, schema))
        else:
            tables.update(tables_in_sql(source, catalog, schema))
    view.tables = sorted(tables)
    for d in doc.get("dimensions") or []:
        view.dimensions.append({"name": str(d.get("name", "")), "expr": str(d.get("expr", ""))})
    for m in doc.get("measures") or []:
        expr = str(m.get("expr", ""))
        measure = {"name": str(m.get("name", "")), "expr": expr, "measure_refs": MEASURE_REF.findall(expr)}
        for key in ("display_name", "synonyms", "format", "comment"):
            if key in m:
                measure[key] = m[key]
        view.measures.append(measure)
    return view


def parse_describe_json(text):
    """A MetricView from the JSON that DESCRIBE TABLE EXTENDED <view> AS JSON returns."""
    try:
        doc = json.loads(text)
    except (TypeError, ValueError):
        raise MetricViewError("the DESCRIBE result is not JSON") from None
    catalog, schema, table = doc.get("catalog_name"), doc.get("schema_name"), doc.get("table_name")
    # Some answers give the schema as the last part of a namespace list, not as schema_name.
    if not schema and isinstance(doc.get("namespace"), list) and doc["namespace"]:
        schema = doc["namespace"][-1]
    name = ".".join(str(p) for p in (catalog, schema, table) if p)
    if not doc.get("view_text"):
        raise MetricViewError(f"{name}: the DESCRIBE result holds no view_text")
    view = parse_yaml(doc["view_text"], name, catalog, schema)
    view.measure_columns = [str(c.get("name")) for c in doc.get("columns") or [] if c.get("is_measure")]
    view.from_name = str((doc.get("table_properties") or {}).get("metric_view.from.name", ""))
    return view
