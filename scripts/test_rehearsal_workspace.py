"""Tests for scripts/rehearsal_workspace.py, without Databricks: every statement of create names only the two
practice catalogs, and drop sends exactly the two DROP statements and refuses any other catalog."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rehearsal_workspace as rw  # noqa: E402

PRACTICE = {"kpi_reh_idp_sbx", "kpi_reh_synapse_dev"}
NAME = r"[A-Za-z_][A-Za-z0-9_]*"
FULL_NAME = re.compile(rf"\b({NAME})\.{NAME}\.{NAME}\b")         # catalog.schema.object
CREATED = re.compile(rf"\bCREATE (?:CATALOG|SCHEMA) ({NAME})\b")  # the catalog a CREATE CATALOG or SCHEMA names
READ = re.compile(rf"\b(?:FROM|JOIN|source:) +({NAME}(?:\.{NAME})*)")
CTE = re.compile(rf"\b({NAME}) AS \(")                            # a name a WITH clause declares


def test_every_statement_of_create_names_only_a_practice_catalog():
    plan = rw.create_statements()
    assert [name for kind, name, _ in plan if kind == "catalog"] == ["kpi_reh_synapse_dev", "kpi_reh_idp_sbx"]
    for kind, name, statement in plan:
        assert name.split(".")[0] in PRACTICE, name
        assert set(FULL_NAME.findall(statement)) <= PRACTICE, statement
        assert set(CREATED.findall(statement)) <= PRACTICE, statement
        assert "IF NOT EXISTS" not in statement, statement
        assert not re.search(r"`|\bUSE\b|\bDROP\b", statement), statement   # the keywords are written in capitals
        local = set(CTE.findall(statement))
        for ref in READ.findall(statement):
            assert ref in local or (ref.count(".") == 2 and ref.split(".")[0] in PRACTICE), (ref, statement)


def test_create_makes_63_objects_with_the_planted_column():
    plan = rw.create_statements()
    assert sum(kind in ("schema", "table", "view") for kind, _, _ in plan) == 63
    summary = [(k, s) for k, n, s in plan if n == "kpi_reh_idp_sbx.gold_commercial_core.mips_mpr_executive_summary_fact"]
    assert [k for k, _ in summary][:2] == ["table", "replace"]
    assert "AS ChangeValue" in summary[0][1] and "AS Change_Value_Amount" in summary[1][1]


def test_drop_refuses_any_other_catalog():
    assert set(rw.CATALOGS) == PRACTICE
    for catalog in PRACTICE:
        assert rw.drop_statement(catalog) == f"DROP CATALOG IF EXISTS {catalog} CASCADE"
    for other in ("idp_sbx", "workspace", "samples", "epm_release_validate_1", "synapse_dev", "KPI_REH_IDP_SBX",
                  "kpi_reh_idp_sbx; DROP CATALOG idp_sbx"):
        with pytest.raises(SystemExit):
            rw.drop_statement(other)


def test_drop_sends_exactly_the_two_drop_statements(monkeypatch):
    sent = []
    monkeypatch.setattr(rw, "runner", lambda profile: sent.append)
    assert rw.main(["drop"]) == 0
    assert sorted(sent) == sorted(f"DROP CATALOG IF EXISTS {c} CASCADE" for c in PRACTICE)


def test_a_failed_drop_ends_with_a_plain_message(monkeypatch):
    def fail(statement):
        raise RuntimeError("the statement ended as FAILED")
    monkeypatch.setattr(rw, "runner", lambda profile: fail)
    with pytest.raises(SystemExit, match="drop kpi_reh_idp_sbx: the statement ended as FAILED"):
        rw.main(["drop"])
