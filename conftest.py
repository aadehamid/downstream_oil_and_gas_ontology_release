"""The two groups of this release's tests. scripts/check.sh runs everything that proves the ontology is valid, and leaves
out the tests listed in scripts/pinned-tests.txt, which compare this tree with the release as shipped.
scripts/check-pinned.sh sets EPM_PINNED_ONLY and runs only those.

A test listed in scripts/pending-tests.txt is skipped in both groups, with the reason that file gives.
"""
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def pending():
    """The test IDs in scripts/pending-tests.txt: tests that wait for a change still to come."""
    path = os.path.join(HERE, "scripts", "pending-tests.txt")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def pinned():
    with open(os.path.join(HERE, "scripts", "pinned-tests.txt"), encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def pytest_collection_modifyitems(config, items):
    listed, only = pinned(), bool(os.environ.get("EPM_PINNED_ONLY"))
    waiting = pending()
    keep, drop = [], []
    for item in items:
        if item.nodeid.split("[")[0] in waiting:
            item.add_marker(pytest.mark.skip(reason="listed in scripts/pending-tests.txt: it reads the removed demo folder"))
        name = getattr(item, "originalname", None) or item.name
        key = os.path.relpath(str(item.fspath), HERE).replace(os.sep, "/") + "::" + name
        (keep if (key in listed) == only else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
