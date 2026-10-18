"""The early map must preserve the release's identities and map semantics."""

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

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
    states = json.loads((ROOT / "docs/research-map/boundaries.json").read_bytes())[
        "states"
    ]
    before = json.dumps(value, sort_keys=True)
    raw = pages.initial_map_bytes(value, manifest, states)
    assert raw == pages.initial_map_bytes(value, manifest, states)
    index = json.loads(raw)
    assert index["catalog_sha256"] == manifest["files"]["catalog.json"]["sha256"]
    assert index["catalog_release_key"] == value["catalog_release_key"]
    assert index["revision"] == 981
    assert index["counts"] == manifest["counts"]
    assert index["states"] == states
    assert len(index["facilities"]) == 7430
    for row, facility in zip(index["facilities"], value["facilities"], strict=True):
        identity, name, state, city, point = row
        assert (identity, name, state, city) == (
            facility["facility_id"],
            facility["name"],
            facility["state"],
            (facility["address"] or {}).get("city"),
        )
        expected = facility["map_location"]
        assert point == (
            [expected["latitude"], expected["longitude"], expected["kind"]]
            if expected is not None
            else None
        )
    assert len(raw) < 4 * 1024 * 1024
    assert len(gzip.compress(raw)) < len(gzip.compress(json.dumps(value).encode())) / 8
    assert json.dumps(value, sort_keys=True) == before
    assert set(index) == {
        "map_format",
        "revision",
        "catalog_release_key",
        "catalog_sha256",
        "counts",
        "states",
        "facilities",
    }


def test_initial_map_cannot_publish_bytes_the_browser_would_reject():
    facility = {
        "facility_id": "f-large",
        "name": "x" * pages.MAX_INITIAL_MAP_BYTES,
        "state": None,
        "address": None,
        "map_location": None,
    }
    manifest = {
        "revision": 1,
        "catalog_release_key": "a" * 64,
        "files": {"catalog.json": {"sha256": "b" * 64}},
        "counts": {"facilities": 1, "courses": 0, "destinations": 0},
    }
    with pytest.raises(ValueError, match="initial map too large"):
        pages.initial_map_bytes({"facilities": [facility]}, manifest, [])
