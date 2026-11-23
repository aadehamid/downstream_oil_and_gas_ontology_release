#!/usr/bin/env bash
# Optional. Does this tree still equal KPI Store 1.1 as it was shipped? It runs only the tests in scripts/pinned-tests.txt.
# On the release as shipped they pass. After your first change some are expected to fail, which says your copy has
# moved on and nothing more. Run scripts/check.sh to see whether your copy is valid.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
while IFS= read -r var; do unset "$var"; done < <(compgen -e | grep '^GIT_' || true)
export PYTHONDONTWRITEBYTECODE=1 EPM_PINNED_ONLY=1
# uv prefers a Python it installed itself, whatever its version; the release needs 3.11 or later here.
export UV_PYTHON="${UV_PYTHON:->=3.11}"
files="$(grep -v '^#' scripts/pinned-tests.txt | cut -d: -f1 | sort -u)"
# shellcheck disable=SC2086
uv run -q --no-project --with pytest==9.2.0 --with rdflib==7.6.0 --with pyshacl==0.40.2 --with owlrl==7.6.2 --with openpyxl==3.1.5 --with jsonschema==4.26.0 --with pyoxigraph==0.5.13 --with markdown-it-py==4.3.0 \
  python -m pytest -q -p no:cacheprovider --rootdir "$ROOT" --confcutdir "$ROOT" $files
