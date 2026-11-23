#!/usr/bin/env bash
# The notebook's side of the KPI Store on an older Python. The notebook and the modules it reaches run in
# Databricks, on whatever Python the compute has. Serverless compute of environment version 1 has Python 3.10, and
# the first real run met it there. scripts/check.sh runs these same tests on the Python of your machine, which is
# 3.11 or later. This script runs them on Python 3.10, or on the version you name:
#
#     bash scripts/check-notebook-side.sh          # Python 3.10
#     bash scripts/check-notebook-side.sh 3.11
#
# uv fetches that Python when the machine has none, so the first run needs the network. The test job runs this
# script on Linux and on Windows. The packages are the six of the notebook's first cell, at its versions, and the
# test tools.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
while IFS= read -r var; do unset "$var"; done < <(compgen -e | grep '^GIT_' || true)
export PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8
VERSION="${1:-3.10}"
echo "--- the notebook's side on Python $VERSION"
uv run -q --python "$VERSION" --no-project --with pytest==9.2.0 --with pytest-xdist==3.8.0 --with pyshacl==0.40.2 --with owlrl==7.6.2 \
  --with databricks-sdk==0.164.0 --with pyoxigraph==0.5.13 --with rdflib==7.6.0 --with sqlglot==30.31.0 --with pyyaml==6.0.3 --with tomli==2.2.1 \
  python -m pytest -q -p no:cacheprovider --rootdir "$ROOT" --confcutdir "$ROOT" -n "${CHECK_WORKERS:-auto}" --maxprocesses=8 \
  kpi_store/tests/test_notebook.py \
  kpi_store/tests/test_settings.py \
  kpi_store/tests/test_load_databricks.py \
  kpi_store/tests/test_discovery.py \
  kpi_store/tests/test_compare.py \
  kpi_store/tests/test_report.py \
  kpi_store/tests/test_tech_graph.py \
  kpi_store/tests/test_metric_view.py \
  kpi_store/tests/test_ontology_view.py
uv run -q --python "$VERSION" --no-project python -c 'import sys; print("the notebook side passed on Python " + ".".join(map(str, sys.version_info[:3])))'
