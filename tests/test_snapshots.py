import json

import pytest

from fairway.snapshots import Snapshot, load_catalog, select_snapshot


def snapshot(identifier, bounds):
    return Snapshot(
        identifier,
        f"{identifier}.npz",
        "https://example.test/roads",
        "0" * 64,
        "static-test",
        bounds,
        bounds,
    )


def test_loads_published_catalog():
    catalog = load_catalog("data/snapshots.json")
    assert catalog[0].identifier == "chicago-static-v1"
    assert catalog[0].contains([(41.8781, -87.6298)])
    assert not catalog[0].contains([(43.0389, -87.9065)])


def test_selects_smallest_compatible_core_independent_of_order():
    regional = snapshot("regional", (40, -90, 44, -86))
    local = snapshot("local", (41, -89, 43, -87))
    origins = [(41.8, -87.7), (42.1, -88.0)]
    assert select_snapshot((regional, local), origins) == local
    assert select_snapshot((local, regional), origins) == local
    assert select_snapshot((local,), [(34.05, -118.24)]) is None


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"snapshots": []},
        {
            "snapshots": [
                {
                    "id": "bad",
                    "file": "../bad.npz",
                    "url": "https://example.test/bad",
                    "sha256": "short",
                    "cost_profile": "test",
                    "core_bounds": [0, 0, 1, 1],
                    "graph_bounds": [0, 0, 1, 1],
                }
            ]
        },
        {
            "snapshots": [
                {
                    "id": "bad",
                    "file": "bad.npz",
                    "url": "https://example.test:invalid/bad.npz",
                    "sha256": "0" * 64,
                    "cost_profile": "test",
                    "core_bounds": [0, 0, 1, 1],
                    "graph_bounds": [0, 0, 1, 1],
                }
            ]
        },
        {
            "snapshots": [
                {
                    "id": "bad",
                    "file": "bad.npz",
                    "url": "https://example.test /bad.npz",
                    "sha256": "0" * 64,
                    "cost_profile": "test",
                    "core_bounds": [0, 0, 1, 1],
                    "graph_bounds": [0, 0, 1, 1],
                }
            ]
        },
        {
            "snapshots": [
                {
                    "id": "bad",
                    "file": "bad.npz",
                    "url": "file:///tmp/bad.npz",
                    "sha256": "0" * 64,
                    "cost_profile": "test",
                    "core_bounds": [0, 0, 1, 1],
                    "graph_bounds": [0, 0, 1, 1],
                }
            ]
        },
        {
            "snapshots": [
                {
                    "id": "bad",
                    "file": "bad.npz",
                    "url": "custom://example.test/bad.npz",
                    "sha256": "0" * 64,
                    "cost_profile": "test",
                    "core_bounds": [0, 0, 1, 1],
                    "graph_bounds": [0, 0, 1, 1],
                }
            ]
        },
        {
            "snapshots": [
                {
                    "id": "bad",
                    "file": "bad.npz",
                    "url": "https://example.test/bad.npz",
                    "sha256": "g" * 64,
                    "cost_profile": "test",
                    "core_bounds": [0, 0, 1, 1],
                    "graph_bounds": [0, 0, 1, 1],
                }
            ]
        },
    ],
)
def test_rejects_invalid_catalog(tmp_path, change):
    value = {"schema_version": 1, "snapshots": []}
    value.update(change)
    path = tmp_path / "snapshots.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="invalid road snapshot catalog"):
        load_catalog(path)
