import json

import networkx as nx
import pytest
from modo import CompactRoadGraph

import scripts.build_snapshot as build_snapshot_module
from scripts.build_snapshot import build_snapshot, validate_graph


def valid_graph():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.89, x=-87.78)
    graph.add_edge("a", "b", travel_time=12.5)
    return graph


def test_build_snapshot_validates_and_records_reproducible_inputs(tmp_path):
    source = tmp_path / "roads.graphml"
    destination = tmp_path / "roads.npz"
    nx.write_graphml(valid_graph(), source)

    result = build_snapshot(
        source,
        destination,
        source_url="https://example.test/roads.graphml",
        source_date="2026-08-30",
        extraction="bbox: 41.8,-87.9,42.0,-87.6",
        road_filter="drive service roads included",
        generator="OSMnx 2.1.1 export command",
        cost_profile="static-test-v1",
    )

    assert result["source"]["sha256"]
    assert result["artifact"]["sha256"]
    assert result["graph"] == {
        "directed": True,
        "vertices": 2,
        "source_edges": 1,
        "stored_edges": 1,
        "bounds": [41.88, -87.8, 41.89, -87.78],
        "minimum_travel_time_seconds": 12.5,
        "maximum_travel_time_seconds": 12.5,
    }
    assert json.loads((tmp_path / "roads.npz.build.json").read_text()) == result
    loaded = CompactRoadGraph.load(destination)
    assert loaded.analyze_vertices(("a",)).travel_times("b").travel_times_seconds == (
        12.5,
    )


@pytest.mark.parametrize("travel_time", [None, 0, -1, float("inf"), "invalid", True])
def test_build_snapshot_rejects_missing_or_invalid_travel_time(travel_time):
    graph = valid_graph()
    if travel_time is None:
        del graph["a"]["b"]["travel_time"]
    else:
        graph["a"]["b"]["travel_time"] = travel_time
    with pytest.raises(ValueError, match="travel_time"):
        validate_graph(graph)


def test_build_snapshot_rejects_undirected_graph():
    with pytest.raises(ValueError, match="directed"):
        validate_graph(valid_graph().to_undirected())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_url", "http://example.test/roads", "HTTPS"),
        ("source_date", "today", "YYYY-MM-DD"),
        ("extraction", "", "extraction"),
    ],
)
def test_build_snapshot_requires_source_provenance(tmp_path, field, value, message):
    source = tmp_path / "roads.graphml"
    nx.write_graphml(valid_graph(), source)
    arguments = {
        "source_url": "https://example.test/roads.graphml",
        "source_date": "2026-08-30",
        "extraction": "test bounds",
        "road_filter": "test roads",
        "generator": "test generator",
        "cost_profile": "static-test-v1",
    }
    arguments[field] = value
    with pytest.raises(ValueError, match=message):
        build_snapshot(source, tmp_path / "roads.npz", **arguments)


def test_build_snapshot_rejects_overlapping_paths(tmp_path):
    source = tmp_path / "roads.graphml"
    destination = tmp_path / "roads.npz"
    nx.write_graphml(valid_graph(), source)
    arguments = {
        "source_url": "https://example.test/roads.graphml",
        "source_date": "2026-08-30",
        "extraction": "test bounds",
        "road_filter": "test roads",
        "generator": "test generator",
        "cost_profile": "static-test-v1",
    }
    with pytest.raises(ValueError, match="different files"):
        build_snapshot(source, source, **arguments)
    with pytest.raises(ValueError, match="different files"):
        build_snapshot(source, destination, metadata=source, **arguments)


def test_build_snapshot_rejects_a_source_that_changes_during_build(
    tmp_path, monkeypatch
):
    source = tmp_path / "roads.graphml"
    destination = tmp_path / "roads.npz"
    nx.write_graphml(valid_graph(), source)
    destination.write_bytes(b"previous artifact")
    original_read_graphml = nx.read_graphml

    def changing_read_graphml(path):
        graph = original_read_graphml(path)
        source.write_text(source.read_text() + "\n")
        return graph

    monkeypatch.setattr("scripts.build_snapshot.nx.read_graphml", changing_read_graphml)
    with pytest.raises(RuntimeError, match="source changed"):
        build_snapshot(
            source,
            destination,
            source_url="https://example.test/roads.graphml",
            source_date="2026-08-30",
            extraction="test bounds",
            road_filter="test roads",
            generator="test generator",
            cost_profile="static-test-v1",
        )
    assert destination.read_bytes() == b"previous artifact"


def test_metadata_staging_failure_preserves_existing_pair(tmp_path, monkeypatch):
    source = tmp_path / "roads.graphml"
    destination = tmp_path / "roads.npz"
    metadata = tmp_path / "roads.build.json"
    nx.write_graphml(valid_graph(), source)
    destination.write_bytes(b"existing artifact")
    metadata.write_bytes(b"existing metadata")

    def fail(_path, _build_record):
        raise OSError("metadata write failed")

    monkeypatch.setattr(build_snapshot_module, "_write_metadata", fail)
    with pytest.raises(OSError, match="metadata write failed"):
        build_snapshot(
            source,
            destination,
            source_url="https://example.test/roads.graphml",
            source_date="2026-08-30",
            extraction="test bounds",
            road_filter="test roads",
            generator="test generator",
            cost_profile="static-test-v1",
            metadata=metadata,
        )
    assert destination.read_bytes() == b"existing artifact"
    assert metadata.read_bytes() == b"existing metadata"


def test_publish_failure_rolls_back_existing_pair(tmp_path, monkeypatch):
    artifact = tmp_path / "roads.npz"
    metadata = tmp_path / "roads.build.json"
    staged_artifact = tmp_path / "staged.npz"
    staged_metadata = tmp_path / "staged.build.json"
    artifact.write_bytes(b"existing artifact")
    metadata.write_bytes(b"existing metadata")
    staged_artifact.write_bytes(b"new artifact")
    staged_metadata.write_bytes(b"new metadata")
    replace = type(staged_metadata).replace

    def fail_metadata(self, target):
        if self == staged_metadata:
            raise OSError("metadata publish failed")
        return replace(self, target)

    monkeypatch.setattr(type(staged_metadata), "replace", fail_metadata)
    with pytest.raises(OSError, match="metadata publish failed"):
        build_snapshot_module._publish_pair(
            staged_artifact,
            artifact,
            staged_metadata,
            metadata,
        )
    assert artifact.read_bytes() == b"existing artifact"
    assert metadata.read_bytes() == b"existing metadata"


def test_second_staging_failure_cleans_the_first_temporary(tmp_path, monkeypatch):
    source = tmp_path / "roads.graphml"
    destination = tmp_path / "roads.npz"
    nx.write_graphml(valid_graph(), source)
    original_temporary = build_snapshot_module._temporary
    staged = []

    def fail_second(parent, name):
        if staged:
            raise OSError("second staging failed")
        result = original_temporary(parent, name)
        staged.append(result)
        return result

    monkeypatch.setattr(build_snapshot_module, "_temporary", fail_second)
    with pytest.raises(OSError, match="second staging failed"):
        build_snapshot(
            source,
            destination,
            source_url="https://example.test/roads.graphml",
            source_date="2026-08-30",
            extraction="test bounds",
            road_filter="test roads",
            generator="test generator",
            cost_profile="static-test-v1",
        )
    assert len(staged) == 1
    assert not staged[0].exists()
    assert not destination.exists()


def test_committed_pair_survives_backup_cleanup_failure(tmp_path, monkeypatch):
    artifact = tmp_path / "roads.npz"
    metadata = tmp_path / "roads.build.json"
    staged_artifact = tmp_path / "staged.npz"
    staged_metadata = tmp_path / "staged.build.json"
    artifact.write_bytes(b"existing artifact")
    metadata.write_bytes(b"existing metadata")
    staged_artifact.write_bytes(b"new artifact")
    staged_metadata.write_bytes(b"new metadata")
    original_temporary = build_snapshot_module._temporary
    original_unlink = type(artifact).unlink
    backups = []
    unlink_calls = {}

    def recording_temporary(parent, name):
        result = original_temporary(parent, name)
        backups.append(result)
        return result

    def fail_cleanup(self, *args, **kwargs):
        if self in backups:
            unlink_calls[self] = unlink_calls.get(self, 0) + 1
            if unlink_calls[self] > 1:
                raise OSError("backup cleanup failed")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(build_snapshot_module, "_temporary", recording_temporary)
    monkeypatch.setattr(type(artifact), "unlink", fail_cleanup)

    build_snapshot_module._publish_pair(
        staged_artifact,
        artifact,
        staged_metadata,
        metadata,
    )
    assert artifact.read_bytes() == b"new artifact"
    assert metadata.read_bytes() == b"new metadata"
