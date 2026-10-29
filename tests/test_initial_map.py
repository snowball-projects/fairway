"""The early map must preserve the release's identities and map semantics."""

import gzip
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "map_builder", ROOT / "scripts/build_pages.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


def test_map_is_exact_reproducible_projection_of_complete_released_catalog():
    # No second complete build: exercise the projection against the actual release.
    value = json.loads(
        gzip.decompress((ROOT / "data/catalog-release/catalog.json.gz").read_bytes())
    )
    manifest = json.loads((ROOT / "data/catalog-release/manifest.json").read_bytes())
    states = json.loads((ROOT / "data/map-boundaries.json").read_bytes())["states"]
    before = json.dumps(value, sort_keys=True)
    raw = pages.initial_map_bytes(value, manifest, states)
    assert raw == pages.initial_map_bytes(value, manifest, states)
    index = json.loads(raw)
    assert index["catalog_sha256"] == manifest["files"]["catalog.json"]["sha256"]
    assert index["catalog_release_key"] == value["catalog_release_key"]
    assert index["revision"] == manifest["revision"] == value["revision"]
    assert index["counts"] == manifest["counts"]
    assert index["states"] == states
    assert len(index["facilities"]) == manifest["counts"]["facilities"]
    course_counts = Counter(c["facility_id"] for c in value["courses"])
    for row, facility in zip(index["facilities"], value["facilities"], strict=True):
        identity, name, state, city, point, holes, courses, access = row
        assert (identity, name, state, city) == (
            facility["facility_id"],
            facility["name"],
            facility["state"],
            (facility["address"] or {}).get("city"),
        )
        assert holes == facility["physical_holes"]
        assert access == facility["access"]
        assert courses == course_counts[identity]
        expected = facility["map_location"]
        assert point == (
            [expected["latitude"], expected["longitude"], expected["kind"]]
            if expected is not None
            else None
        )
    assert len(raw) < 4 * 1024 * 1024
    assert len(gzip.compress(raw)) < 1024 * 1024
    assert json.dumps(value, sort_keys=True) == before
    assert set(index) == {
        "map_format",
        "revision",
        "catalog_release_key",
        "catalog_sha256",
        "counts",
        "states",
        "facilities",
        "courses",
    }
