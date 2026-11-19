"""Tests for scripts/rehearsal_workspace.py, without Databricks: every statement of create names only the two
practice catalogs, and drop refuses any other catalog."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rehearsal_workspace as rw  # noqa: E402

PRACTICE = {"kpi_reh_idp_sbx", "kpi_reh_synapse_dev"}
# A name with a catalog: three dotted parts, outside quotes. The metric views' YAML names its sources the same way.
FULL_NAME = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b")


def test_create_names_only_the_two_practice_catalogs():
    plan = rw.create_statements()
    assert [name for kind, name, _ in plan if kind == "catalog"] == ["kpi_reh_synapse_dev", "kpi_reh_idp_sbx"]
    named = set()
    for kind, name, statement in plan:
        assert name.split(".")[0] in PRACTICE, name
        named |= set(FULL_NAME.findall(statement))
    assert named == PRACTICE


def test_create_makes_63_objects_with_the_planted_column():
    plan = rw.create_statements()
    assert sum(kind in ("schema", "table", "view") for kind, _, _ in plan) == 63
    summary = [s for k, n, s in plan if n.endswith(".mips_mpr_executive_summary_fact") and n.startswith("kpi_reh_idp_sbx.")]
    assert "AS ChangeValue" in summary[0] and "AS Change_Value_Amount" in summary[1]


def test_drop_names_only_a_practice_catalog():
    assert rw.drop_statement("kpi_reh_idp_sbx") == "DROP CATALOG IF EXISTS kpi_reh_idp_sbx CASCADE"
    for other in ("idp_sbx", "workspace", "samples", "epm_release_validate_1", "synapse_dev"):
        with pytest.raises(SystemExit):
            rw.drop_statement(other)
