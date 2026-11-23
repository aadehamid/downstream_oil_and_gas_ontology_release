#!/usr/bin/env bash
# Is the release's zip the same whether the release folder is a plain folder or is kept in Git?
#
# The runbook tells the reader to unpack the zip and put the folder in Git before any change. In a plain folder the
# runner zips every file except caches; in a Git folder it zips the files Git tracks. This script proves on the real
# release that both give one zip: it builds the zip from this tree, unpacks it, builds it again from the unpacked
# folder, runs the runbook's Git commands there, and builds it a third time. The three SHA-256 values and the three
# file counts must be equal. It writes only under a temporary folder. The test job runs it on Linux and on Windows.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
while IFS= read -r var; do unset "$var"; done < <(compgen -e | grep '^GIT_' || true)
export PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8
# uv starts a Python of its own choice for "uv run", and it prefers one it installed itself, whatever its version.
# The release's code on this machine needs Python 3.11 or later, so uv is told so here. A --python option on a
# command line still wins, as in scripts/check-notebook-side.sh.
export UV_PYTHON="${UV_PYTHON:->=3.11}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
build() {  # <release folder> <zip to write>: prints "<sha256> <files>"
  uv run -q --no-project --with rdflib==7.6.0 --with pyyaml==6.0.3 python -c \
    'import sys; from kpi_store import runner; print(*runner.build_zip(sys.argv[1], sys.argv[2]))' "$1" "$2"
}
from_tree="$(build "$ROOT" "$WORK/tree.zip")"
mkdir "$WORK/release"
uv run -q --no-project python -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$WORK/tree.zip" "$WORK/release"
plain="$(build "$WORK/release" "$WORK/plain.zip")"
# The runbook's commands, in the unpacked folder.
git -C "$WORK/release" init -q
git -C "$WORK/release" config user.name "KPI Store operator"
git -C "$WORK/release" config user.email "kpi-store@example.invalid"
git -C "$WORK/release" add -A
git -C "$WORK/release" commit -q -m "KPI Store 1.2 as shipped"
[ -z "$(git -C "$WORK/release" status --porcelain)" ] || { echo "Git still shows a change after the first commit:"; git -C "$WORK/release" status --short | head; exit 1; }
in_git="$(build "$WORK/release" "$WORK/git.zip")"
echo "this tree:           $from_tree"
echo "unpacked, plain:     $plain"
echo "unpacked, in Git:    $in_git"
[ "$from_tree" = "$plain" ] && [ "$plain" = "$in_git" ] || { echo "the zips differ"; exit 1; }
echo "one zip from the plain folder and from the Git folder"
