import hashlib
import json
from pathlib import Path

import networkx as nx
import numpy as np
import pytest
from modo import CompactRoadGraph

import scripts.build_course_index as build_course_index_module
from fairway.course_index import CourseDistanceIndex

ROAD_SHA = "a" * 64
CATALOG_SHA = "b" * 64


def save(path, distances=None):
    CourseDistanceIndex.save(
        path,
        road_snapshot_sha256=ROAD_SHA,
        course_catalog_sha256=CATALOG_SHA,
        course_ids=("first", "second"),
        distances=(
            np.array([[1, 2, np.inf], [4, 5, 6]], dtype=np.float64)
            if distances is None
            else distances
        ),
    )


def build_inputs(tmp_path):
    graph_path = tmp_path / "roads.npz"
    graph = nx.DiGraph()
    graph.add_node("a", y=0, x=0)
    graph.add_node("b", y=0, x=1)
    graph.add_edge("a", "b", travel_time=12.5)
    graph.add_edge("b", "a", travel_time=13.5)
    CompactRoadGraph.from_networkx(graph).save(graph_path)
    graph_sha256 = hashlib.sha256(graph_path.read_bytes()).hexdigest()

    snapshots = tmp_path / "snapshots.json"
    snapshots.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshots": [
                    {
                        "id": "test-roads-v1",
                        "file": graph_path.name,
                        "url": "https://example.test/roads.npz",
                        "sha256": graph_sha256,
                        "cost_profile": "static-test-v1",
                        "core_bounds": [-0.5, -0.5, 0.5, 1.5],
                        "graph_bounds": [-1, -1, 1, 2],
                    }
                ],
            }
        )
    )
    courses = tmp_path / "courses.json"
    courses.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "test-courses-v1",
                "title": "Test courses",
                "as_of": "2026-08-31",
                "description": "A synthetic catalog for builder tests.",
                "sources": [
                    {
                        "id": "course-source",
                        "url": "https://example.test/course",
                    },
                    {
                        "id": "openstreetmap",
                        "url": "https://www.openstreetmap.org/copyright",
                    },
                ],
                "courses": [
                    {
                        "id": "test-course",
                        "name": "Test Course",
                        "address": "1 Test Road",
                        "routing_coordinate": [0, 1],
                        "holes": 9,
                        "access": "public",
                        "website": "https://example.test/course",
                        "facts_source": "course-source",
                        "routing_source": "openstreetmap",
                        "routing_reference": "way/1",
                    }
                ],
            }
        )
    )
    return graph_path, snapshots, courses


def test_course_distance_index_round_trips_exact_float64(tmp_path):
    path = tmp_path / "courses.npz"
    save(path)

    index = CourseDistanceIndex.load(
        path,
        road_snapshot_sha256=ROAD_SHA,
        course_catalog_sha256=CATALOG_SHA,
        vertex_count=3,
        expected_course_ids=("first", "second"),
    )
    assert index.distances.flags.writeable is False

    class Road:
        def __init__(self):
            self._indices = {"a": 0, "b": 1, "c": 2}

    assert index.lookup(("second", "first"), ("b", "a"), Road()) == (
        (5.0, 4.0),
        (2.0, 1.0),
    )


def test_course_distance_index_rejects_wrong_data_binding(tmp_path):
    path = tmp_path / "courses.npz"
    save(path)

    with pytest.raises(ValueError, match="does not match active data"):
        CourseDistanceIndex.load(
            path,
            road_snapshot_sha256="c" * 64,
            course_catalog_sha256=CATALOG_SHA,
            vertex_count=3,
        )

    with pytest.raises(ValueError, match="does not match active data"):
        CourseDistanceIndex.load(
            path,
            road_snapshot_sha256=ROAD_SHA,
            course_catalog_sha256=CATALOG_SHA,
            vertex_count=3,
            expected_course_ids=("first",),
        )


def test_course_distance_index_rejects_lossy_float32(tmp_path):
    path = tmp_path / "courses.npz"
    with pytest.raises(ValueError, match="float64"):
        save(path, np.ones((2, 3), dtype=np.float32))


def test_course_distance_index_requires_bit_exact_active_reverse_rows():
    graph = nx.DiGraph()
    graph.add_node("a", y=0, x=0)
    graph.add_node("course", y=0, x=1)
    graph.add_edge("a", "course", travel_time=12.5)
    road = CompactRoadGraph.from_networkx(graph)
    distances = np.array([[12.5, 0.0]], dtype=np.float64)
    index = CourseDistanceIndex(ROAD_SHA, CATALOG_SHA, ("course",), distances)

    assert index.validate_against(road, ("course",)) is index
    changed = CourseDistanceIndex(
        ROAD_SHA,
        CATALOG_SHA,
        ("course",),
        np.array([[12.500000000000002, 0.0]], dtype=np.float64),
    )
    with pytest.raises(ValueError, match="do not match active routing"):
        changed.validate_against(road, ("course",))


def test_course_distance_index_rejects_object_archives(tmp_path):
    path = tmp_path / "courses.npz"
    np.savez(path, format_version=np.array(1), course_ids=np.array([object()]))
    with pytest.raises(ValueError, match="invalid course distance index"):
        CourseDistanceIndex.load(
            path,
            road_snapshot_sha256=ROAD_SHA,
            course_catalog_sha256=CATALOG_SHA,
            vertex_count=3,
        )


def test_build_course_index_writes_a_bound_float64_index(tmp_path):
    _graph, snapshots, courses = build_inputs(tmp_path)
    destination = tmp_path / "course-index.npz"

    result = build_course_index_module.build_course_index(
        destination,
        snapshot_id="test-roads-v1",
        snapshot_catalog=snapshots,
        course_catalog=courses,
    )

    assert result["courses"] == 1
    assert result["vertices"] == 2
    assert result["dtype"] == "float64"
    assert result["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()


@pytest.mark.parametrize("overlap", ["graph", "snapshots", "courses"])
def test_build_course_index_refuses_to_overwrite_inputs(tmp_path, overlap):
    graph, snapshots, courses = build_inputs(tmp_path)
    paths = {"graph": graph, "snapshots": snapshots, "courses": courses}
    destination = paths[overlap]
    original = destination.read_bytes()

    with pytest.raises(ValueError, match="must differ"):
        build_course_index_module.build_course_index(
            destination,
            snapshot_id="test-roads-v1",
            snapshot_catalog=snapshots,
            course_catalog=courses,
            graph_path=graph,
        )
    assert destination.read_bytes() == original


def test_build_course_index_rejects_a_graph_that_changes_during_build(
    tmp_path, monkeypatch
):
    graph, snapshots, courses = build_inputs(tmp_path)
    destination = tmp_path / "course-index.npz"
    destination.write_bytes(b"existing index")
    original_dijkstra = build_course_index_module.dijkstra

    def change_graph(*args, **kwargs):
        result = original_dijkstra(*args, **kwargs)
        graph.write_bytes(graph.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(build_course_index_module, "dijkstra", change_graph)
    with pytest.raises(RuntimeError, match="changed while the index was being built"):
        build_course_index_module.build_course_index(
            destination,
            snapshot_id="test-roads-v1",
            snapshot_catalog=snapshots,
            course_catalog=courses,
            graph_path=graph,
        )
    assert destination.read_bytes() == b"existing index"


def test_build_course_index_rejects_courses_over_one_kilometer_from_a_road(
    tmp_path,
):
    graph, snapshots, courses = build_inputs(tmp_path)
    value = json.loads(courses.read_text())
    value["courses"][0]["routing_coordinate"] = [0.4, 1.4]
    courses.write_text(json.dumps(value))
    destination = tmp_path / "course-index.npz"
    destination.write_bytes(b"existing index")

    with pytest.raises(ValueError, match="over 1 km"):
        build_course_index_module.build_course_index(
            destination,
            snapshot_id="test-roads-v1",
            snapshot_catalog=snapshots,
            course_catalog=courses,
            graph_path=graph,
        )
    assert destination.read_bytes() == b"existing index"


def test_build_course_index_stages_summary_before_publishing(tmp_path, monkeypatch):
    graph, snapshots, courses = build_inputs(tmp_path)
    destination = tmp_path / "course-index.npz"
    destination.write_bytes(b"existing index")
    original_digest = build_course_index_module.digest

    def fail_staged_digest(path):
        path = Path(path)
        if path.name.startswith(f".{destination.name}."):
            raise OSError("staged digest failed")
        return original_digest(path)

    monkeypatch.setattr(build_course_index_module, "digest", fail_staged_digest)
    with pytest.raises(OSError, match="staged digest failed"):
        build_course_index_module.build_course_index(
            destination,
            snapshot_id="test-roads-v1",
            snapshot_catalog=snapshots,
            course_catalog=courses,
            graph_path=graph,
        )
    assert destination.read_bytes() == b"existing index"
