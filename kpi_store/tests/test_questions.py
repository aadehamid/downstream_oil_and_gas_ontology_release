"""The cross-graph questions without a server: discovery, the mapping, the drift check, rendering and refusal.

The schema is a made-up one (fixtures/questions/schema.json). Every expected value is written by hand.
"""
import copy
import csv
import datetime as dt
import io
import json
import os
from pathlib import Path

import pytest

from kpi_store.questions import connection as C
from kpi_store.questions import discover as D
from kpi_store.questions import mapping as M
from kpi_store.questions import render as T
from kpi_store.questions import roles as R
from kpi_store.questions import run

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "questions"
GRAPHS = {"governance": "composite.gov", "bpa": "composite.kpi"}
PASSWORD = "not-a-real-password-7f3a"


def fixture_rows():
    with (FIXTURES / "schema.json").open(encoding="utf-8") as f:
        return json.load(f)


def schemas(rows=None):
    rows = rows or fixture_rows()
    answers = {D.LABELS_QUERY: "labels", D.PROPERTIES_QUERY: "properties", D.RELATIONSHIPS_QUERY: "relationships"}
    return {graph: D.read_schema(lambda query, graph=graph: rows[graph][answers[query]]) for graph in R.GRAPHS}


def confirmed():
    return M.load(FIXTURES / "mapping.json")


def set_value(mapping, role, value):
    """A copy of the mapping with one role changed and confirmed again, as a person who edited the file would."""
    changed = copy.deepcopy(mapping)
    changed["roles"][role]["value"] = value
    changed["digest"] = M.digest(changed)
    return changed


class FakeReader:
    """Answers the three schema queries from the fixture and every other query with the rows it was given."""

    def __init__(self, rows=None, answer=None, columns=None):
        self.rows, self.answer, self.last_columns, self.asked = rows or fixture_rows(), answer or [], columns, []

    def read(self, query, params=None):
        self.asked.append((query, params))
        prefix = "USE graph.byName($graph) "
        if query.startswith(prefix):
            graph = {name: key for key, name in GRAPHS.items()}[params["graph"]]
            kind = {D.LABELS_QUERY: "labels", D.PROPERTIES_QUERY: "properties",
                    D.RELATIONSHIPS_QUERY: "relationships"}[query[len(prefix):]]
            return self.rows[graph][kind]
        return self.answer

    def close(self):
        pass


# ---------- roles ----------

def test_the_role_list():
    assert len(R.ROLES) == 39
    assert [r.name for r in R.ROLES if r.graph == "governance" and r.required] == [
        "system.node", "system.code", "table.node", "table.qualified_name", "system_to_table"]
    assert R.role("replaces").required is False and R.role("replaces").candidates == ("REPLACES",)
    assert R.role("platform_table.copies_system").candidates == ("dp_copiesSystem",)
    assert all(r.meaning.endswith(".") and r.candidates for r in R.ROLES)
    with pytest.raises(KeyError):
        R.role("no.such.role")


# ---------- discovery ----------

def test_read_schema_from_three_queries():
    schema = schemas()["governance"]
    assert schema.labels["DataSystem"] == 4 and schema.labels["Table"] == 8
    assert schema.properties["DataSystem"] == {"name", "systemId", "ingestionMethod", "refreshFrequency", "madeUp"}
    assert ("Policy", "APPLIES_TO", "DataSystem") in schema.relationships
    assert schema.types_between("Schema", ["Table"]) == ["CONTAINS"]


def test_proposal_on_the_made_up_graphs():
    proposal = D.propose(schemas())
    values = {name: entry["value"] for name, entry in proposal["roles"].items()}
    assert proposal["confirmed"] is False and proposal["digest"] == ""
    assert values["system.node"] == "DataSystem" and values["system.code"] == "name"
    assert values["table.node"] == "Table" and values["table.qualified_name"] == "qualifiedName"
    assert values["system_to_table"] == {"types": ["CONTAINS"], "max_hops": 2}
    assert values["policy.applies_to"] == "APPLIES_TO" and values["table.derived_from"] == "DERIVED_FROM"
    assert values["table.classification"] == "classification"
    assert values["system.classification"] is None
    assert proposal["roles"]["system.classification"]["confidence"] == 0.0
    assert proposal["roles"]["system.classification"]["alternatives"] == [
        "ingestionMethod", "madeUp", "name", "refreshFrequency", "systemId"]
    assert values["measure.node"] == "kpi_MeasureDefinition" and values["measure.code"] == "skos_notation"
    assert values["platform_table.full_name"] == "dp_fullName"
    assert values["platform_table.derived_from"] == "prov_wasDerivedFrom"
    assert values["platform_table.in_layer"] == "dp_layer" and values["layer.node"] == "skos_Concept"
    assert values["ontology_system.node"] == "sys_System"
    assert values["platform_table.part_of"] == "dcterms_isPartOf"
    assert values["tech.checks"] == "CHECKS" and values["replaces"] == "REPLACES"
    assert all(proposal["roles"][name]["confidence"] == 1.0 for name in values if values[name] is not None)


def test_confidence_falls_with_a_weaker_match():
    rows = fixture_rows()
    for row in rows["governance"]["properties"]:
        if row["label"] == "DataSystem" and row["key"] == "name":
            row["key"] = "code"                                  # the second candidate
    for kind in ("labels", "properties"):
        for row in rows["governance"][kind]:
            if row["label"] == "Table":
                row["label"] = "TABLE"                           # the first candidate in another case
    for row in rows["governance"]["relationships"]:
        row["start"], row["end"] = (("TABLE" if x == "Table" else x) for x in (row["start"], row["end"]))
        if row["type"] == "APPLIES_TO":
            row["type"] = "GOVERNS"                              # no candidate, but the only type there is
    roles = D.propose(schemas(rows))["roles"]
    assert (roles["system.code"]["value"], roles["system.code"]["confidence"]) == ("code", 0.9)
    assert (roles["table.node"]["value"], roles["table.node"]["confidence"]) == ("TABLE", 0.7)
    assert (roles["policy.applies_to"]["value"], roles["policy.applies_to"]["confidence"]) == ("GOVERNS", 0.5)


def test_a_missing_required_role_has_no_value_and_lists_the_choices():
    rows = fixture_rows()
    rows["governance"]["labels"] = [r for r in rows["governance"]["labels"] if r["label"] != "DataSystem"]
    roles = D.propose(schemas(rows))["roles"]
    assert roles["system.node"]["value"] is None and roles["system.node"]["confidence"] == 0.0
    assert "Server" in roles["system.node"]["alternatives"] and "Table" in roles["system.node"]["alternatives"]
    assert roles["system.code"]["value"] is None and roles["system_to_table"]["value"] is None


def test_the_path_follows_other_relationship_types_with_less_confidence():
    rows = fixture_rows()
    for row in rows["governance"]["relationships"]:
        if row["type"] == "CONTAINS" and row["start"] == "DataSystem":
            row["type"] = "OWNS"
    entry = D.propose(schemas(rows))["roles"]["system_to_table"]
    assert entry["value"] == {"types": ["CONTAINS", "OWNS"], "max_hops": 2} and entry["confidence"] == 0.6


# ---------- the mapping and the drift check ----------

def test_the_fixture_mapping_is_confirmed_and_fits():
    mapping = confirmed()
    assert M.is_confirmed(mapping)
    assert M.drift(mapping, schemas()) == []
    assert {n: e["value"] for n, e in D.propose(schemas())["roles"].items()} == {
        n: e["value"] for n, e in mapping["roles"].items()}


def test_an_edit_after_confirmation_needs_a_new_confirmation():
    mapping = confirmed()
    mapping["roles"]["system.code"]["value"] = "systemId"
    assert not M.is_confirmed(mapping)
    with pytest.raises(M.MappingError, match="changed after it was confirmed"):
        M.require_confirmed(mapping)
    with pytest.raises(M.MappingError, match="not confirmed"):
        M.require_confirmed(D.propose(schemas()))


def test_confirm_stamps_and_refuses_a_mapping_that_does_not_fit():
    proposal = D.propose(schemas())
    done = M.confirm(proposal, schemas(), now=dt.datetime(2026, 11, 11, 9, 30, tzinfo=dt.timezone.utc))
    assert done["confirmed"] is True and done["confirmed_at"] == "2026-11-11T09:30:00Z"
    assert M.is_confirmed(done) and proposal["confirmed"] is False
    proposal["roles"]["table.qualified_name"]["value"] = "noSuchProperty"
    with pytest.raises(M.MappingError, match="role table.qualified_name: property noSuchProperty"):
        M.confirm(proposal, schemas())


def drop(rows, graph, kind, **match):
    rows[graph][kind] = [r for r in rows[graph][kind] if any(r[k] != v for k, v in match.items())]
    return rows


@pytest.mark.parametrize("change, expected", [
    (lambda r: drop(r, "governance", "labels", label="Policy"),
     "role policy.node: label Policy no longer exists in the governance graph"),
    (lambda r: drop(r, "governance", "properties", label="Table", key="qualifiedName"),
     "role table.qualified_name: property qualifiedName is no longer on label Table in the governance graph"),
    (lambda r: drop(r, "governance", "relationships", type="APPLIES_TO"),
     "role policy.applies_to: relationship type APPLIES_TO no longer runs from Policy to DataSystem or Table "
     "in the governance graph"),
    (lambda r: drop(r, "governance", "relationships", type="CONTAINS"),
     "role system_to_table: relationship type CONTAINS no longer exists in the governance graph"),
    # A node with two labels gives the schema two rows, so both go.
    (lambda r: drop(drop(r, "governance", "relationships", type="CONTAINS", start="Schema"),
                    "governance", "relationships", type="CONTAINS", start="Legacy"),
     "role system_to_table: no path of CONTAINS leads from DataSystem to Table in the governance graph in 2 steps"),
    (lambda r: drop(r, "bpa", "properties", label="dp_PlatformTable", key="dp_fullName"),
     "role platform_table.full_name: property dp_fullName is no longer on label dp_PlatformTable in the bpa graph"),
    (lambda r: drop(r, "bpa", "relationships", type="REPLACES"),
     "role replaces: relationship type REPLACES no longer runs from Tech to Tech in the bpa graph"),
])
def test_drift_names_the_role(change, expected):
    assert M.drift(confirmed(), schemas(change(fixture_rows()))) == [expected]


def test_drift_reports_a_required_role_with_no_value_and_a_role_the_file_lacks():
    mapping = set_value(confirmed(), "system.code", None)
    assert M.drift(mapping, schemas()) == ["role system.code: required, and nothing plays it"]
    del mapping["roles"]["replaces"]
    assert "role replaces: not in the mapping; run discover again" in M.drift(mapping, schemas())


def test_save_and_load(tmp_path):
    M.save(tmp_path / "m.json", confirmed())
    assert M.load(tmp_path / "m.json") == confirmed()
    assert b"\r" not in (tmp_path / "m.json").read_bytes()
    (tmp_path / "bad.json").write_text('{"format": 2, "roles": {}}', encoding="utf-8", newline="\n")
    with pytest.raises(M.MappingError, match="not a role mapping of format 1"):
        M.load(tmp_path / "bad.json")


# ---------- rendering ----------

SMALL = """// title: Tables of one system
// param: system | required | The system's code.
// param: limit | default 3 | How many.
CALL () {
  USE graph.byName($governance_graph)
  MATCH (g:{{label:system.node}})-[{{path:system_to_table}}]->(t:{{label:table.node}})
  WHERE g.{{property:system.code}} = $system
//#if policy.applies_to
  OPTIONAL MATCH (p)-[:{{relationship:policy.applies_to}}]->(t)
//#else
  WITH g, t, null AS p
//#endif
  RETURN t.{{property:table.qualified_name}} AS name LIMIT $limit
}
RETURN name
"""


def test_render_quotes_names_and_keeps_values_as_parameters():
    rendered = T.render_text("small", SMALL, confirmed(), schemas(), {"system": "x' OR 1=1 //"}, GRAPHS)
    assert rendered.query == """// title: Tables of one system
// param: system | required | The system's code.
// param: limit | default 3 | How many.
CALL () {
  USE graph.byName($governance_graph)
  MATCH (g:`DataSystem`)-[:`CONTAINS`*1..2]->(t:`Table`)
  WHERE g.`name` = $system
  OPTIONAL MATCH (p)-[:`APPLIES_TO`]->(t)
  RETURN t.`qualifiedName` AS name LIMIT $limit
}
RETURN name
"""
    assert rendered.params == {"system": "x' OR 1=1 //", "limit": 3,
                               "governance_graph": "composite.gov", "bpa_graph": "composite.kpi"}
    assert rendered.title == "Tables of one system"
    assert rendered.roles == ("system.node", "system_to_table", "table.node", "system.code", "policy.applies_to",
                              "table.qualified_name")


def test_render_takes_the_else_part_when_an_optional_role_has_no_value():
    mapping = set_value(confirmed(), "policy.applies_to", None)
    query = T.render_text("small", SMALL, mapping, schemas(), {"system": "MIPS"}, GRAPHS).query
    assert "  WITH g, t, null AS p\n" in query and "APPLIES_TO" not in query and "OPTIONAL MATCH" not in query


def test_render_doubles_a_backtick_inside_a_name():
    rows = fixture_rows()
    hostile = "Table`) DETACH DELETE (n"
    for kind in ("labels", "properties"):
        for row in rows["governance"][kind]:
            if row["label"] == "Table":
                row["label"] = hostile
    for row in rows["governance"]["relationships"]:
        row["start"], row["end"] = ((hostile if x == "Table" else x) for x in (row["start"], row["end"]))
    mapping = set_value(confirmed(), "table.node", hostile)
    query = T.render_text("small", SMALL, mapping, schemas(rows), {"system": "MIPS"}, GRAPHS).query
    assert "(t:`Table``) DETACH DELETE (n`)" in query


def test_render_refuses_a_name_the_schema_does_not_have():
    mapping = set_value(confirmed(), "system.code", "password")
    with pytest.raises(T.RenderError, match="role system.code: password is not in the governance graph's schema"):
        T.render_text("small", SMALL, mapping, schemas(), {"system": "MIPS"}, GRAPHS)
    mapping = set_value(confirmed(), "system_to_table", {"types": ["CONTAINS", "NOPE"], "max_hops": 2})
    with pytest.raises(T.RenderError, match="role system_to_table"):
        T.render_text("small", SMALL, mapping, schemas(), {"system": "MIPS"}, GRAPHS)
    mapping = set_value(confirmed(), "system_to_table", {"types": ["CONTAINS"], "max_hops": "2}]->() DELETE"})
    with pytest.raises(T.RenderError, match="role system_to_table"):
        T.render_text("small", SMALL, mapping, schemas(), {"system": "MIPS"}, GRAPHS)


def test_render_needs_a_confirmed_mapping():
    with pytest.raises(M.MappingError, match="not confirmed"):
        T.render_text("small", SMALL, D.propose(schemas()), schemas(), {"system": "MIPS"}, GRAPHS)
    edited = confirmed()
    edited["roles"]["table.node"]["value"] = "Column"
    with pytest.raises(M.MappingError, match="changed after it was confirmed"):
        T.render_text("small", SMALL, edited, schemas(), {"system": "MIPS"}, GRAPHS)


@pytest.mark.parametrize("text, message", [
    (SMALL.replace("$limit", "$limit + $extra"), "uses the parameter extra and does not declare it"),
    (SMALL.replace("{{label:table.node}}", "{{label:table.qualified_name}}"),
     "role table.qualified_name is a property, and the template uses it as a label"),
    (SMALL.replace("{{label:table.node}}", "{{label:no.such}}"), "no role named no.such"),
    (SMALL.replace("{{label:table.node}}", "{{ table node }}"), "is not a placeholder of the form"),
    (SMALL.replace("{{label:table.node}}", "{{label:policy.node}}").replace("//#else", "//#if x"), "no role named x"),
    (SMALL.replace("//#endif\n", ""), "an //#if has no //#endif"),
    (SMALL.replace("//#if policy.applies_to\n", ""), "//#else without //#if"),
    (SMALL.replace("//#else", "//#otherwise"), "is not //#if, //#else or //#endif"),
])
def test_render_refuses_a_broken_template(text, message):
    with pytest.raises(T.RenderError, match=message):
        T.render_text("small", text, confirmed(), schemas(), {"system": "MIPS"}, GRAPHS)


def test_render_refuses_a_parameter_the_question_does_not_have():
    with pytest.raises(T.RenderError, match="needs the parameter system"):
        T.render_text("small", SMALL, confirmed(), schemas(), {}, GRAPHS)
    with pytest.raises(T.RenderError, match="has no parameter colour"):
        T.render_text("small", SMALL, confirmed(), schemas(), {"system": "MIPS", "colour": "red"}, GRAPHS)


def test_render_refuses_a_required_role_with_no_value():
    mapping = set_value(confirmed(), "table.qualified_name", None)
    with pytest.raises(T.RenderError, match="role table.qualified_name: nothing plays it"):
        T.render_text("small", SMALL, mapping, schemas(), {"system": "MIPS"}, GRAPHS)


# ---------- read-only ----------

@pytest.mark.parametrize("clause, named", [
    ("CREATE (:X)", "CREATE"), ("MERGE (:X)", "MERGE"), ("MATCH (n) SET n.x = 1", "SET"),
    ("MATCH (n) set n.x = 1", "SET"), ("MATCH (n) DELETE n", "DELETE"), ("MATCH (n) DETACH DELETE n", "DETACH"),
    ("MATCH (n) REMOVE n.x", "REMOVE"), ("DROP DATABASE x", "DROP"), ("FOREACH (x IN [1] | CREATE (:X))", "FOREACH"),
    ("LOAD CSV FROM 'file:///x' AS row RETURN row", "LOAD"), ("INSERT (:X)", "INSERT"),
    ("CALL db.createLabel('X')", "calls a procedure"), ("CALL apoc.periodic.iterate('a', 'b', {})", "calls a procedure"),
    ("CALL `db.createLabel`('X')", "calls a procedure"), ("CALL `db`.`createLabel`('X')", "calls a procedure"),
    ("CALL db.x()", "calls a procedure"), ("call  \n db.x()", "calls a procedure"),
    ("CALL db.labels() YIELD label RETURN label", "calls a procedure"), ("CALL db.labels", "calls a procedure"),
    ("CALL `p`() { MATCH (n) RETURN n }", "calls a procedure"), ("OPTIONAL CALL db.x()", "calls a procedure"),
    ("CALL (name) db.x()", "calls a procedure"), ("CALL /* a note */ db.x()", "calls a procedure"),
    ("CALL`dbms`.`components`()", "calls a procedure"), ("CALL`db`.`createLabel`('X')", "calls a procedure"),
    ("call`db.x`()", "calls a procedure"), ("CALL/**/db.x()", "calls a procedure"),
    ("CALL/**/`db`.`x`()", "calls a procedure"), ("MATCH (n) WHERE true CALL\tdb.x()", "calls a procedure"),
    # What sits in the parentheses of a subquery is an import list: nothing, a star, or variable names.
    ("CALL ('x') { RETURN 1 AS one }", "calls a procedure"), ("CALL (1 + 1) { RETURN 1 AS one }", "calls a procedure"),
    ("CALL (name.size) { RETURN 1 AS one }", "calls a procedure"), ("CALL (name,) { RETURN 1 AS one }", "calls a procedure"),
    ("CALL (`name`) { RETURN 1 AS one }", "calls a procedure"), ("CALL (*, name) { RETURN 1 AS one }", "calls a procedure"),
    ("CALL (name) (name) { RETURN 1 AS one }", "calls a procedure"), ("CALL {{label:table.node}}", "calls a procedure"),
    ("CALL", "calls a procedure"), ("CALL (name", "calls a procedure"),
    ("CALL () { MATCH (n) RETURN n } IN TRANSACTIONS", "opens its own transactions"),
    ("CALL () { MATCH (n) RETURN n } IN 2 CONCURRENT TRANSACTIONS", "opens its own transactions"),
])
def test_a_template_with_a_write_clause_is_refused(clause, named):
    text = SMALL.replace("RETURN name\n", f"WITH name {clause}\nRETURN name\n")
    with pytest.raises(T.RenderError, match="refused: .*" + named):
        T.render_text("small", text, confirmed(), schemas(), {"system": "MIPS"}, GRAPHS)


def test_a_write_word_inside_a_comment_a_string_or_a_name_is_not_a_clause():
    text = SMALL.replace("RETURN name\n", "// we never CREATE or DELETE here\n"
                         "WITH name, 'SET' AS word, $system AS start_value, 1 AS `MERGE`\n"
                         "WHERE name STARTS WITH 'M' OR name ENDS WITH \"DROP\"\nRETURN name\n")
    assert "STARTS WITH" in T.render_text("small", text, confirmed(), schemas(), {"system": "MIPS"}, GRAPHS).query


@pytest.mark.parametrize("subquery", [
    "CALL { MATCH (n) RETURN count(n) AS found }", "CALL () { MATCH (n) RETURN count(n) AS found }",
    "CALL (name) { RETURN size(name) AS found }", "call  \n ( name , name2 )\n{ RETURN 1 AS found }",
    "CALL (*) { RETURN 1 AS found }", "CALL // a note\n () { RETURN 1 AS found }",
    "WITH 'CALL db.x()' AS `CALL db.y()` RETURN 1 AS found",
    "CALL(){ RETURN 1 AS found }", "CALL(name,name2){ RETURN 1 AS found }", "CALL/**/{ RETURN 1 AS found }",
    "CALL ( /* none */ ) { RETURN 1 AS found }",
    # The letters alone are not the keyword: inside a name, as part of a longer word, or as a property.
    "MATCH (n:`CALL`) RETURN count(n) AS found", "WITH name AS recall, name AS callsign RETURN 1 AS found",
    "MATCH (n) WHERE n.callsign = 'x' OR n.call = 1 OR n.`CALL` = 2 RETURN count(n) AS found",
    "WITH $call AS x, $CALL AS y RETURN 1 AS found",
    # A name may hold letters outside ASCII; it is still one word.
    "WITH name AS na\u00efve CALL (na\u00efve) { RETURN size(na\u00efve) AS found }",
])
def test_the_two_subquery_forms_are_allowed(subquery):
    text = SMALL.replace("RETURN name\n", f"WITH name, name AS name2 {subquery}\nRETURN name\n")
    if "$call" in subquery:
        text = text.replace("// param: limit", "// param: call | default 1 | x\n// param: CALL | default 1 | x\n"
                                              "// param: limit")
    assert T.render_text("small", text, confirmed(), schemas(), {"system": "MIPS"}, GRAPHS).query.count("found") == 1


# ---------- the four questions ----------

@pytest.mark.parametrize("question, params", [("q1", {}), ("q4", {"system": "mips"}), ("q6", {"kpi": "crude-prices"}),
                                              ("q7", {})])
def test_each_question_renders_with_no_placeholder_left(question, params):
    rendered = T.render(question, confirmed(), schemas(), params, GRAPHS)
    assert "{{" not in rendered.query and "//#" not in rendered.query
    # Each graph is named only through a parameter, and both graphs take part.
    assert "USE graph.byName($bpa_graph)" in rendered.query
    assert "USE graph.byName($governance_graph)" in rendered.query
    assert rendered.query.count("USE ") == rendered.query.count("USE graph.byName($")
    assert "enterpriseknowledgegraph" not in rendered.query and "composite" not in rendered.query
    assert "`DataSystem`" in rendered.query and "`sys_System`" in rendered.query


def test_question_defaults():
    assert T.render("q7", confirmed(), schemas(), {}, GRAPHS).params["terms"] == ["sox", "confidential"]
    assert T.render("q1", confirmed(), schemas(), {}, GRAPHS).params["system"] == ""
    assert T.render("q6", confirmed(), schemas(), {"kpi": "x"}, GRAPHS).params["sample"] == 5
    assert T.render("q6", confirmed(), schemas(), {"kpi": "x"}, GRAPHS).language_tagged == ("kpi", "system")
    with pytest.raises(T.RenderError, match="needs the parameter system"):
        T.render("q4", confirmed(), schemas(), {}, GRAPHS)
    with pytest.raises(T.RenderError, match="no question named q9"):
        T.render("q9", confirmed(), schemas(), {}, GRAPHS)


def test_question_1_uses_the_replaces_link_and_falls_back_to_names_without_it():
    with_link = T.render("q1", confirmed(), schemas(), {}, GRAPHS).query
    assert "-[:`REPLACES`]->(old:`Tech`)" in with_link and "[] AS by_link" not in with_link
    without = T.render("q1", set_value(confirmed(), "replaces", None), schemas(), {}, GRAPHS).query
    assert "REPLACES" not in without and "WITH by_name, ontology_codes, [] AS by_link\n" in without
    assert "entry.keys" in without                      # the name matching stays


def test_question_6_leaves_the_quality_part_out_without_the_technical_graph():
    without = T.render("q6", set_value(confirmed(), "tech.checks", None), schemas(), {"kpi": "x"}, GRAPHS).query
    assert "QualityCheck" not in without and "[] AS quality" in without
    assert "`QualityCheck`" in T.render("q6", confirmed(), schemas(), {"kpi": "x"}, GRAPHS).query


def test_question_7_needs_a_policy_or_a_class():
    mapping = confirmed()
    for role in ("policy.applies_to", "table.classification"):
        mapping = set_value(mapping, role, None)
    with pytest.raises(T.RenderError, match="question q7 needs one of the roles policy.applies_to, "
                                            "system.classification, table.classification"):
        T.render("q7", mapping, schemas(), {}, GRAPHS)
    only_class = T.render("q7", set_value(confirmed(), "policy.applies_to", None), schemas(), {}, GRAPHS).query
    assert "`Policy`" not in only_class and "t.`classification`" in only_class


# ---------- connection settings ----------

def settings_file(folder, **changes):
    values = {"uri": "bolt://127.0.0.1:17999", "user": "reader", "password": PASSWORD, "composite": "composite",
              "governance_alias": "gov", "bpa_alias": "kpi", **changes}
    path = folder / "questions.toml"
    path.write_text("[neo4j]\n" + "".join(f'{k} = "{v}"\n' for k, v in values.items() if v is not None),
                    encoding="utf-8", newline="\n")
    return path


def test_settings_from_a_file_and_from_the_environment(tmp_path):
    connection = C.read(settings_file(tmp_path), environ={})
    assert (connection.uri, connection.user, connection.password) == ("bolt://127.0.0.1:17999", "reader", PASSWORD)
    assert connection.graphs == GRAPHS
    assert PASSWORD not in repr(connection) and PASSWORD not in str(connection)
    over = C.read(settings_file(tmp_path), environ={"KPI_STORE_NEO4J_USER": "other", "KPI_STORE_NEO4J_BPA_ALIAS": "b2"})
    assert over.user == "other" and over.graphs["bpa"] == "composite.b2"
    only_env = C.read(None, environ={"KPI_STORE_NEO4J_" + k.upper(): "v" for k in C.KEYS})
    assert only_env.composite == "v"


def test_settings_that_are_missing_or_wrong_stop(tmp_path):
    with pytest.raises(C.SettingsError, match="lack password, bpa_alias"):
        C.read(settings_file(tmp_path, password=None, bpa_alias=None), environ={})
    with pytest.raises(C.SettingsError, match="no settings file"):
        C.read(tmp_path / "absent.toml", environ={})
    with pytest.raises(C.SettingsError, match="composite is not a database name"):
        C.read(settings_file(tmp_path, composite="a.b; DROP"), environ={})
    with pytest.raises(C.SettingsError, match="must be outside the release folder"):
        C.read(FIXTURES / "questions.toml", environ={})
    with pytest.raises(C.SettingsError, match="the mapping file must be outside the release folder"):
        C.outside_release(FIXTURES / "mapping.json", "the mapping file")


def test_a_differently_cased_spelling_of_the_release_folder_is_refused():
    respelled = Path(str(C.RELEASE_ROOT).swapcase())
    if str(respelled) == str(C.RELEASE_ROOT) or not respelled.exists():
        pytest.skip("this file system tells upper case from lower case, so the other spelling is another folder")
    for inside in (respelled / "mapping.json", respelled / "kpi_store" / "no-such-folder" / "mapping.json", respelled):
        with pytest.raises(C.SettingsError, match="must be outside the release folder"):
            C.outside_release(inside, "the mapping file")


def test_a_relative_path_into_the_release_folder_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(C.RELEASE_ROOT / "kpi_store")
    for inside in (Path("mapping.json"), Path("../answers/q1.json"), Path("."), Path("..")):
        with pytest.raises(C.SettingsError, match="must be outside the release folder"):
            C.outside_release(inside, "the mapping file")
    monkeypatch.chdir(tmp_path)
    assert C.outside_release(Path("mapping.json"), "the mapping file") == (tmp_path / "mapping.json").resolve()


def test_a_link_into_the_release_folder_is_refused(tmp_path):
    link = tmp_path / "elsewhere"
    try:
        os.symlink(C.RELEASE_ROOT, link, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"this account cannot make a link: {type(error).__name__}")
    for inside in (link / "mapping.json", link / "kpi_store" / "tests" / "mapping.json", link):
        with pytest.raises(C.SettingsError, match="must be outside the release folder"):
            C.outside_release(inside, "the mapping file")


# ---------- asking and the command line ----------

def test_ask_stops_on_drift_before_the_question_runs():
    reader = FakeReader(rows=drop(fixture_rows(), "governance", "properties", label="DataSystem", key="name"))
    with pytest.raises(M.MappingError, match="role system.code: property name is no longer on label DataSystem"):
        run.ask(reader, "q4", confirmed(), GRAPHS, {"system": "mips"})
    assert len(reader.asked) == 6 and all(q.startswith("USE graph.byName($graph) MATCH") for q, _ in reader.asked)


def test_ask_returns_rows_without_language_tags_and_sends_values_as_parameters():
    rows = [{"graph": "kpi store", "kind": "kpi", "name": "made-up-kpi", "label": "Made-up KPI@en", "layer": None},
            {"graph": "governance", "kind": "table", "name": "a@b.c", "label": None, "layer": "Operational"}]
    reader = FakeReader(answer=rows, columns=["graph", "kind", "name", "label", "layer"])
    answer = run.ask(reader, "q4", confirmed(), GRAPHS, {"system": "MIPS"},
                     now=dt.datetime(2026, 11, 11, 8, 0, tzinfo=dt.timezone.utc))
    assert answer["rows"][0]["label"] == "Made-up KPI" and answer["rows"][1]["name"] == "a@b.c"
    assert answer["columns"] == ["graph", "kind", "name", "label", "layer"]
    assert answer["params"] == {"system": "MIPS"} and answer["asked_at"] == "2026-11-11T08:00:00Z"
    query, params = reader.asked[-1]
    assert params == {"system": "MIPS", "governance_graph": "composite.gov", "bpa_graph": "composite.kpi"}
    assert "MIPS" not in query and "composite" not in query


def test_plain_values():
    assert run.plain({"at": dt.datetime(2026, 11, 1, 6, 0), "n": [1, 2.5, None, True]}) == {
        "at": "2026-11-01T06:00:00", "n": [1, 2.5, None, True]}


def test_write_answer_as_json_and_csv(tmp_path):
    answer = {"question": "q7", "title": "t", "params": {}, "asked_at": "2026-11-11T08:00:00Z",
              "columns": ["kpi", "tables", "reasons", "ok", "note"],
              "rows": [{"kpi": "Prix é", "tables": 3, "reasons": ["a", "b, c"], "ok": True, "note": None}]}
    json_path, csv_path = run.write_answer(answer, tmp_path / "out")
    assert json.loads(json_path.read_text(encoding="utf-8")) == answer
    assert csv_path.read_bytes() == 'kpi,tables,reasons,ok,note\nPrix é,3,"[""a"", ""b, c""]",true,\n'.encode("utf-8")
    assert list(csv.reader(io.StringIO(csv_path.read_text(encoding="utf-8"))))[1][2] == '["a", "b, c"]'


def test_parse_params():
    assert run.parse_params(["kpi=crude-prices", "sample=2", 'terms=["sox"]', "note=a=b"]) == {
        "kpi": "crude-prices", "sample": 2, "terms": ["sox"], "note": "a=b"}
    with pytest.raises(T.RenderError, match="--param takes name=value"):
        run.parse_params(["kpi"])


def command(tmp_path, *argv, reader=None, typed="yes"):
    out = io.StringIO()
    code = run.main([*argv, "--settings", str(settings_file(tmp_path)), "--mapping", str(tmp_path / "mapping.json")],
                    out=out, reader_factory=lambda connection: reader or FakeReader(), confirm_input=lambda _: typed)
    return code, out.getvalue()


def test_the_command_line_from_discover_to_ask(tmp_path, monkeypatch):
    for key in C.KEYS:
        monkeypatch.delenv("KPI_STORE_NEO4J_" + key.upper(), raising=False)
    code, text = command(tmp_path, "ask", "q1", "--out", str(tmp_path / "answers"))
    assert code == 1 and "STOPPED: no mapping file at" in text and "run discover first" in text
    code, text = command(tmp_path, "discover")
    assert code == 0 and "system.node                      DataSystem  confidence 1.0" in text
    assert "system.classification            -  confidence 0.0  (optional, absent)" in text
    code, text = command(tmp_path, "check")
    assert code == 1 and "STOPPED: the role mapping is not confirmed" in text
    code, text = command(tmp_path, "ask", "q1", "--out", str(tmp_path / "answers"))
    assert code == 1 and "STOPPED: the role mapping is not confirmed" in text
    code, text = command(tmp_path, "confirm", typed="no")
    assert code == 1 and "not confirmed" in text and not M.is_confirmed(M.load(tmp_path / "mapping.json"))
    code, text = command(tmp_path, "confirm")
    assert code == 0 and M.is_confirmed(M.load(tmp_path / "mapping.json"))
    code, text = command(tmp_path, "discover")
    assert code == 1 and "pass --replace" in text
    code, text = command(tmp_path, "check")
    assert code == 0 and "the mapping still fits both graphs (39 roles checked)" in text
    reader = FakeReader(answer=[{"system": "MIPS", "tables": 3}], columns=["system", "tables"])
    code, text = command(tmp_path, "ask", "q1", "--out", str(tmp_path / "answers"), reader=reader)
    assert code == 0 and text.startswith("q1: 1 rows; wrote ")
    assert (tmp_path / "answers" / "q1.csv").read_text(encoding="utf-8") == "system,tables\nMIPS,3\n"
    drifted = FakeReader(rows=drop(fixture_rows(), "governance", "labels", label="Table"))
    code, text = command(tmp_path, "check", reader=drifted)
    assert code == 1 and "role table.node: label Table no longer exists in the governance graph" in text


def test_the_command_line_never_prints_the_password_and_keeps_files_out_of_the_release(tmp_path, monkeypatch):
    for key in C.KEYS:
        monkeypatch.delenv("KPI_STORE_NEO4J_" + key.upper(), raising=False)
    shown = "".join(command(tmp_path, *argv)[1] for argv in (
        ["discover"], ["confirm", "--yes"], ["check"], ["ask", "q1", "--out", str(tmp_path / "answers")]))
    assert "confirmed " in shown and PASSWORD not in shown
    assert PASSWORD not in (tmp_path / "mapping.json").read_text(encoding="utf-8")
    out = io.StringIO()
    code = run.main(["discover", "--settings", str(settings_file(tmp_path)), "--mapping", str(FIXTURES / "new.json")],
                    out=out, reader_factory=lambda connection: FakeReader())
    assert code == 1 and "the mapping file must be outside the release folder" in out.getvalue()
    assert not (FIXTURES / "new.json").exists()


def test_answers_are_never_written_inside_the_release(tmp_path, monkeypatch):
    for key in C.KEYS:
        monkeypatch.delenv("KPI_STORE_NEO4J_" + key.upper(), raising=False)
    assert command(tmp_path, "discover")[0] == 0 and command(tmp_path, "confirm", "--yes")[0] == 0
    monkeypatch.chdir(C.RELEASE_ROOT)
    for out_args in ([], ["--out", "."], ["--out", str(FIXTURES / "answers")]):      # no --out means this folder
        reader = FakeReader(answer=[{"system": "MIPS"}], columns=["system"])
        code, text = command(tmp_path, "ask", "q1", *out_args, reader=reader)
        assert code == 1 and "the folder for the answers (--out) must be outside the release folder" in text
        assert reader.asked == []                                                    # stopped before any query
    assert not (C.RELEASE_ROOT / "q1.json").exists() and not (C.RELEASE_ROOT / "q1.csv").exists()
    assert not (FIXTURES / "answers").exists()
