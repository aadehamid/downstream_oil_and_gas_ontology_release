#!/usr/bin/env bash
# The release's automated checks: every builder's --verify, the projection manifest, the competency regression,
# every test file, the module map and the coverage counts, the generated pages, and the stand-alone check. Run it
# from the release root before you change anything, and again after.
#
# Needs python3 and uv (https://docs.astral.sh/uv/) for the test dependencies.
#
# This script proves your copy is valid. It leaves out the tests in scripts/pinned-tests.txt, which ask whether your
# copy still equals the release as shipped. scripts/check-pinned.sh runs those, and you may ignore it after you change
# anything. When you add a module or a test, add it here too: HOW-TO-UPDATE.md says where.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
while IFS= read -r var; do unset "$var"; done < <(compgen -e | grep '^GIT_' || true)
export PYTHONDONTWRITEBYTECODE=1
run() { echo "--- $*"; "$@"; }
run_tests() {  # unittest exits 0 on zero tests; a test command must have run at least one
  echo "--- $*"; local out; out="$("$@" 2>&1)"; local rc=$?; printf '%s\n' "$out"
  [ "$rc" -eq 0 ] && grep -qE '^Ran [1-9][0-9]* tests? ' <<<"$out"
}
with_deps() { uv run -q --no-project --with pytest --with pytest-xdist --with rdflib --with pyshacl --with openpyxl --with jsonschema --with "markdown-it-py>=4,<5" --with pyyaml==6.0.3 --with sqlglot==30.31.0 --with pyoxigraph==0.5.13 --with neo4j "$@"; }

# Snapshot the tree, so a check that writes a file is caught.
snapshot() {
  python3 - <<'PY'
import hashlib, os
h = hashlib.sha256()
for root, dirs, files in os.walk("."):
    dirs[:] = sorted(d for d in dirs if d not in (".git", "__pycache__", ".venv", ".pytest_cache"))
    for f in sorted(files):
        p = os.path.join(root, f)
        h.update(p.encode() + b"\0")
        with open(p, "rb") as fh:
            h.update(hashlib.sha256(fh.read()).digest())
print(h.hexdigest())
PY
}
before="$(snapshot)"

ONT=business_architecture/ontology
# The core package and each module's package must equal a fresh build (the newest set).
CORE_BUILDER="$(cd $ONT/release && python3 -c 'import newest; print(newest.core_builder())')"
(cd $ONT/release && run with_deps python "$CORE_BUILDER.py" --verify)
(cd $ONT/release && run with_deps python build_module.py organization --verify)
(cd $ONT/release && run with_deps python build_module.py kpi --verify)
(cd $ONT/release && run with_deps python build_module.py system --verify)
(cd $ONT/release && run with_deps python build_module.py party --verify)
(cd $ONT/release && run with_deps python build_module.py ref-mpc --verify)
(cd $ONT/release && run with_deps python build_module.py data-product --verify)
(cd $ONT/release && run with_deps python build_module.py value-stream --verify)
(cd $ONT/release && run with_deps python build_module.py lane --verify)
(cd $ONT/release && run with_deps python build_module.py market-data --verify)
(cd $ONT/release && run with_deps python build_module.py integration --verify)
(cd $ONT/release && run with_deps python build_module.py technical-graph --verify)
(cd $ONT/release && run with_deps python build_module.py logical-model --verify)
# The logical models of this release must equal a fresh build from their exports and links files.
(cd $ONT/logical-model && run with_deps python build_logical_model.py --export models/customer-logical-model.erstudio.ttl --links models/customer-logical-model.links.csv --model customer-logical-model --title 'Customer logical model' --out models --verify)
(cd $ONT/release && run with_deps python build_catalog.py --verify)
# The competency questions the release can answer must still answer.
(cd $ONT/regression && run with_deps python run.py)
# Each module's source Turtle must equal a fresh build from its tables.
(cd $ONT/organization && run with_deps python build_roles.py --verify)
(cd $ONT/organization && run with_deps python build_assignments.py --verify)
(cd $ONT/kpi && run with_deps python build_measures.py --verify)
(cd $ONT/data-product && run with_deps python build_data_products.py --verify)
(cd $ONT/data-product && run with_deps python build_pricing.py --verify)
(cd $ONT/value-stream && run with_deps python build_value_streams.py --verify)
(cd $ONT/system && run with_deps python build_systems.py --verify)
(cd $ONT/lane && run with_deps python build_lanes.py --verify)
(cd $ONT/market-data && run with_deps python build_market_data.py --verify)
(cd $ONT/authority && run with_deps python build_source_tiers.py --verify)
(cd $ONT/apqc && run with_deps python build_apqc_elements.py --verify)
(cd $ONT/population && run with_deps python build_population.py --verify)
(cd $ONT/party && run with_deps python build_party.py --verify)
# The projection's checked, serialised inputs must match the manifest.
(cd $ONT/projection && run with_deps python pipeline.py build --verify)
# Every test file of the ontology and the scripts, in parallel (test_check_script.py checks the list is complete).
run with_deps python -m pytest -q -p no:cacheprovider --rootdir "$ROOT" --confcutdir "$ROOT" -n "${CHECK_WORKERS:-auto}" --maxprocesses=8 --dist load \
  business_architecture/business_process/test_business_process.py \
  business_architecture/ontology/apqc/test_apqc_elements.py \
  business_architecture/ontology/authority/test_source_tiers.py \
  business_architecture/ontology/build/scripts/test_relation_correct.py \
  business_architecture/ontology/build/scripts/test_scope_note_append.py \
  business_architecture/ontology/build/scripts/test_step3c_workbook_validate.py \
  business_architecture/ontology/consumer/test_consumer_rules.py \
  business_architecture/ontology/data-product/test_data_products.py \
  business_architecture/ontology/kpi/test_measures.py \
  business_architecture/ontology/lane/test_lanes.py \
  business_architecture/ontology/logical-model/test_logical_model.py \
  business_architecture/ontology/market-data/test_market_data.py \
  business_architecture/ontology/organization/test_assignments.py \
  business_architecture/ontology/organization/test_roles.py \
  business_architecture/ontology/organization/test_vocabulary.py \
  business_architecture/ontology/party/test_party.py \
  business_architecture/ontology/party/test_party_lifecycle.py \
  business_architecture/ontology/party/test_party_systems.py \
  business_architecture/ontology/placement/test_placement.py \
  business_architecture/ontology/population/test_population.py \
  business_architecture/ontology/projection/skill-run/test_skill_run.py \
  business_architecture/ontology/projection/test_empty_stores.py \
  business_architecture/ontology/projection/test_logical_models.py \
  business_architecture/ontology/projection/test_pipeline.py \
  business_architecture/ontology/projection/test_subgraph.py \
  business_architecture/ontology/projection/test_sync_stores.py \
  business_architecture/ontology/provenance/test_run_shapes.py \
  business_architecture/ontology/ref-mpc/test_ref_mpc.py \
  business_architecture/ontology/regression/test_run.py \
  business_architecture/ontology/release/test_build_catalog.py \
  business_architecture/ontology/release/test_build_core_2_4.py \
  business_architecture/ontology/release/test_build_module.py \
  business_architecture/ontology/release/test_dependents.py \
  business_architecture/ontology/release/test_frozen_sources.py \
  business_architecture/ontology/release/test_newest.py \
  business_architecture/ontology/release/test_next_version.py \
  business_architecture/ontology/system/test_systems.py \
  business_architecture/ontology/technical-graph/test_technical_graph.py \
  business_architecture/ontology/validation/test_all_module_shapes.py \
  business_architecture/ontology/validation/test_controlled_values.py \
  business_architecture/ontology/validation/test_release_package_shapes.py \
  business_architecture/ontology/value-stream/test_value_streams.py \
  business_architecture/ontology/viewer/test_viewer.py \
  kpi_store/tests/test_compare.py \
  kpi_store/tests/test_cut.py \
  kpi_store/tests/test_discovery.py \
  kpi_store/tests/test_load_databricks.py \
  kpi_store/tests/test_metric_view.py \
  kpi_store/tests/test_notebook.py \
  kpi_store/tests/test_ontology_view.py \
  kpi_store/tests/test_report.py \
  kpi_store/tests/test_settings.py \
  kpi_store/tests/test_tech_graph.py \
  kpi_store/tests/test_tech_graph_integration.py \
  kpi_store/tests/test_questions.py \
  kpi_store/tests/test_questions_integration.py \
  scripts/test_check_script.py \
  scripts/test_check_standalone.py \
  scripts/test_doc_snippets.py \
  scripts/test_docs_html.py \
  scripts/test_epm_facts.py \
  scripts/test_modules_guide.py \
  scripts/test_published_figures.py
# The bundled skills' own checks, each with the dependencies its own check names (the list is written at the cut from
# one table, the same one the cut's skills-tests row runs). A test command that found no test is a failure.
(cd skills/ontology/scripts && run_tests uv run -q --no-project --with rdflib --with pyyaml --with pyshacl python3 -m unittest discover -q -p 'test_*.py')
(cd skills/ontology && run uv run -q --no-project --with pyyaml python3 scripts/check_sssom.py templates/mappings.sssom.tsv)
(cd skills/ontology-to-lpg/scripts && run_tests uv run -q --no-project --with rdflib --with pyshacl --with mcp-neo4j-data-modeling==0.8.2 python3 -m unittest -q test_projection test_engine_gate test_modeling test_explore test_run_projection test_release_record)
(cd skills/rdf-store/scripts && run_tests uv run -q --no-project --with pyoxigraph python3 -m unittest -q test_rdf_store)
(cd skills && run_tests uv run -q --no-project --with 'markdown-it-py>=4,<5' python3 scripts/test_playbook_html.py)
# The module map and the coverage counts run from the release folders.
run with_deps python scripts/epm_facts.py counts >/dev/null
run with_deps python scripts/epm_facts.py modules >/dev/null
run with_deps python scripts/epm_facts.py coverage >/dev/null
# The generated pages must equal a fresh build of their Markdown.
run with_deps python scripts/build_docs_html.py --check
# Every code block in the Markdown documents is run, compared, parsed or skipped for a stated reason, and the last
# line counts them. scripts/DOC-SNIPPETS.md explains the tags. The cut adds --strict --all-contexts.
run with_deps python scripts/doc_snippets.py check
# The tree refers to nothing outside itself. scripts/standalone-pending.txt lists the paths not yet clean.
run python3 scripts/check_standalone.py

# The last load's report. A stale report means the stores are behind the packages, not that the ontology is invalid.
if ! EPM_PINNED_ONLY=1 with_deps python -m pytest -q -p no:cacheprovider --rootdir "$ROOT" --confcutdir "$ROOT" business_architecture/ontology/projection/test_pipeline.py \
    -k test_the_step_5_report_describes_the_current_inputs_and_passed >/dev/null 2>&1; then
  echo "note: projection-report.json describes an earlier build. Project into Neo4j again when you want the stores current (HOW-TO-UPDATE.md)."
fi

after="$(snapshot)"
if [ "$before" != "$after" ]; then
  echo "the checks changed the tree; they must only read it" >&2
  exit 1
fi
echo "all checks passed"
