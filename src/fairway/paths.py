"""Stable packaged metadata and replaceable local artifact paths."""

import os
from pathlib import Path

PACKAGE_DATA = Path(__file__).with_name("data")
SNAPSHOT_CATALOG_PATH = PACKAGE_DATA / "snapshots.json"
COURSE_CATALOG_PATH = PACKAGE_DATA / "course-catalog-v1.json"
REPOSITORY_DATA = Path(__file__).resolve().parents[2] / "data"


def graph_path(filename, catalog_path=SNAPSHOT_CATALOG_PATH):
    """Return an explicit, repository-local, or per-user snapshot path."""
    configured = os.environ.get("FAIRWAY_GRAPH")
    if configured:
        return Path(configured)
    catalog_path = Path(catalog_path)
    if catalog_path.resolve() != SNAPSHOT_CATALOG_PATH.resolve():
        return catalog_path.parent / filename
    if (REPOSITORY_DATA / "README.md").is_file():
        return REPOSITORY_DATA / filename
    configured_cache = os.environ.get("XDG_CACHE_HOME")
    cache_root = Path(configured_cache) if configured_cache else Path.home() / ".cache"
    if not cache_root.is_absolute():
        cache_root = Path.home() / ".cache"
    cache_root /= "fairway"
    return cache_root / filename
