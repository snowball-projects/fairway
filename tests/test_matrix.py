from datetime import UTC, datetime
from decimal import Decimal

import networkx as nx
import numpy as np
import pytest
from modo import CompactRoadGraph

import fairway.matrix as matrix_module
from fairway.course_index import CourseDistanceIndex
from fairway.matrix import (
    DepartureRequest,
    DestinationFailure,
    DestinationTimes,
    MatrixMetadata,
    MatrixProviderUnavailable,
    MatrixResult,
    OutsideRoadCoverage,
    StaticModoMatrix,
    TimeDependentMatrixUnsupported,
    TrafficBasis,
    distance_kilometers,
    validate_road_snapshot,
)
from fairway.scoring import canonical_milliseconds


def test_static_modo_matrix_returns_per_origin_destination_times():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    graph.add_node("x", y=41.89, x=-87.78)
    graph.add_node("y", y=41.89, x=-87.77)
    graph.add_edge("a", "x", travel_time=1)
    graph.add_edge("b", "x", travel_time=9)
    graph.add_edge("a", "y", travel_time=5)
    graph.add_edge("b", "y", travel_time=6)
    road = CompactRoadGraph.from_networkx(graph)

    result = StaticModoMatrix(road).calculate(
        [(41.88, -87.80), (41.88, -87.70)],
        [(41.89, -87.78), (41.89, -87.77)],
    )

    assert result.origin_road_coordinates == (
        (41.88, -87.8),
        (41.88, -87.7),
    )
    assert result.origin_coordinates == (
        (41.88, -87.8),
        (41.88, -87.7),
    )
    assert result.destination_ids is None
    assert [item.travel_times_seconds for item in result.destinations] == [
        (1.0, 9.0),
        (5.0, 6.0),
    ]
    assert result.origin_snap_distances_kilometers == (0.0, 0.0)
    assert result.metadata.provider == "modo-static"
    assert result.metadata.strategy == "sequential-dijkstra"
    assert result.metadata.traffic_basis is TrafficBasis.UNAWARE


def test_static_modo_matrix_runs_one_reverse_field_per_unique_destination(
    monkeypatch,
):
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    graph.add_node("x", y=41.89, x=-87.78)
    graph.add_node("y", y=41.89, x=-87.77)
    graph.add_edge("a", "x", travel_time=1)
    graph.add_edge("b", "x", travel_time=9)
    graph.add_edge("a", "y", travel_time=3)
    graph.add_edge("b", "y", travel_time=4)
    road = CompactRoadGraph.from_networkx(graph)
    calls = []
    original_dijkstra = matrix_module.dijkstra

    def recording_dijkstra(*args, **kwargs):
        calls.append(kwargs["indices"])
        return original_dijkstra(*args, **kwargs)

    monkeypatch.setattr(matrix_module, "dijkstra", recording_dijkstra)
    result = StaticModoMatrix(road).calculate(
        [(41.88, -87.80), (41.88, -87.80), (41.88, -87.70)],
        [(41.89, -87.78), (41.89, -87.78), (41.89, -87.77)],
    )

    assert calls == [road._indices["x"], road._indices["y"]]
    assert result.destinations[0].travel_times_seconds == (1.0, 1.0, 9.0)
    assert result.destinations[1].travel_times_seconds == (1.0, 1.0, 9.0)
    assert result.destinations[2].travel_times_seconds == (3.0, 3.0, 4.0)


def test_static_modo_matrix_marks_only_unreachable_destinations():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    graph.add_node("x", y=41.89, x=-87.78)
    graph.add_node("y", y=41.89, x=-87.77)
    graph.add_edge("a", "x", travel_time=1)
    graph.add_edge("b", "x", travel_time=2)
    road = CompactRoadGraph.from_networkx(graph)

    result = StaticModoMatrix(road).calculate(
        [(41.88, -87.80), (41.88, -87.70)],
        [(41.89, -87.78), (41.89, -87.77)],
    )

    assert result.destinations[0].travel_times_seconds == (1.0, 2.0)
    assert isinstance(result.destinations[1], DestinationFailure)
    assert result.destinations[1].reason == "unreachable"


def test_static_modo_matrix_uses_exact_course_index_when_available():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    graph.add_node("x", y=41.89, x=-87.78)
    road = CompactRoadGraph.from_networkx(graph)

    class Index:
        def lookup(self, course_ids, origin_vertices, received_road):
            assert course_ids == ("course",)
            assert origin_vertices == ("a", "b")
            assert received_road is road
            return ((12.25, 34.5),)

    def fail(_origins):
        raise AssertionError("Dijkstra fallback must not run")

    road.analyze_vertices = fail
    result = StaticModoMatrix(road, course_index=Index()).calculate(
        [(41.88, -87.80), (41.88, -87.70)],
        [(41.89, -87.78)],
        ["course"],
    )

    assert result.destinations[0].travel_times_seconds == (12.25, 34.5)
    assert result.destination_ids == ("course",)
    assert result.metadata.strategy == "precomputed-course-index"


def test_static_modo_matrix_refuses_time_dependent_requests():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    road = CompactRoadGraph.from_networkx(graph)

    with pytest.raises(TimeDependentMatrixUnsupported, match="does not support"):
        StaticModoMatrix(road).calculate(
            [(41.88, -87.80)],
            [(41.88, -87.80)],
            departure=DepartureRequest.leave_now(),
        )


def test_matrix_metadata_requires_explicit_aware_traffic_timing():
    departure_time = datetime(2026, 9, 4, 15, tzinfo=UTC)
    metadata = MatrixMetadata(
        provider="synthetic-traffic",
        traffic_basis=TrafficBasis.BLENDED,
        departure=DepartureRequest.depart_at(departure_time),
        departure_time=departure_time,
        calculated_at=datetime(2026, 9, 4, 14, 59, tzinfo=UTC),
    )

    assert metadata.departure.mode.value == "depart-at"
    with pytest.raises(ValueError, match="UTC offset"):
        DepartureRequest.depart_at(
            datetime(2026, 9, 4, 15, tzinfo=UTC).replace(tzinfo=None)
        )
    with pytest.raises(ValueError, match="requires departure and calculation times"):
        MatrixMetadata(
            provider="synthetic-traffic",
            traffic_basis=TrafficBasis.LIVE,
        )
    with pytest.raises(ValueError, match="must match the depart-at request"):
        MatrixMetadata(
            provider="synthetic-traffic",
            traffic_basis=TrafficBasis.PREDICTED,
            departure=DepartureRequest.depart_at(departure_time),
            departure_time=datetime(2026, 9, 4, 16, tzinfo=UTC),
            calculated_at=datetime(2026, 9, 4, 14, 59, tzinfo=UTC),
        )


def test_matrix_result_requires_one_travel_time_per_origin():
    metadata = MatrixMetadata("synthetic-static", TrafficBasis.UNAWARE)

    with pytest.raises(ValueError, match="equal length"):
        MatrixResult(
            ((0, 0), (0, 1)),
            (None, None),
            (None,),
            None,
            (),
            metadata,
        )
    with pytest.raises(ValueError, match="identifiers and results"):
        MatrixResult(((0, 0),), (None,), (None,), ("missing",), (), metadata)
    with pytest.raises(ValueError, match="one travel time per origin"):
        MatrixResult(
            ((0, 0), (0, 1)),
            (None, None),
            (None, None),
            None,
            (DestinationTimes((0, 0), None, None, (1.0,)),),
            metadata,
        )


def test_destination_failure_rejects_provider_outages_as_omissions():
    with pytest.raises(ValueError, match="unsupported destination failure reason"):
        DestinationFailure((0, 0), None, None, "provider-timeout")


def test_matrix_provider_unavailable_has_a_bounded_retry_delay():
    error = MatrixProviderUnavailable(45)

    assert error.retry_after_seconds == 45
    assert str(error) == "fairway's travel-time provider is temporarily unavailable"
    for value in (True, 0, 3601, 1.5):
        with pytest.raises(ValueError, match="between 1 and 3600 seconds"):
            MatrixProviderUnavailable(value)


@pytest.mark.parametrize("travel_time", [-1.0, float("inf"), float("nan"), None])
def test_matrix_result_rejects_invalid_travel_times(travel_time):
    with pytest.raises(ValueError, match="travel time must be finite and nonnegative"):
        MatrixResult(
            ((0, 0),),
            (None,),
            (None,),
            None,
            (DestinationTimes((0, 0), None, None, (travel_time,)),),
            MatrixMetadata("synthetic-static", TrafficBasis.UNAWARE),
        )


@pytest.mark.parametrize(
    "snap_distance", [-1.0, float("inf"), float("nan"), Decimal("0.1")]
)
def test_matrix_result_rejects_invalid_optional_snap_distances(snap_distance):
    metadata = MatrixMetadata("synthetic-static", TrafficBasis.UNAWARE)

    with pytest.raises(ValueError, match="origin snap distance"):
        MatrixResult(((0, 0),), (None,), (snap_distance,), None, (), metadata)
    with pytest.raises(ValueError, match="destination snap distance"):
        MatrixResult(
            ((0, 0),),
            (None,),
            (None,),
            None,
            (DestinationFailure((0, 0), None, snap_distance, "outside-road-coverage"),),
            metadata,
        )


@pytest.mark.parametrize(
    ("field", "coordinate"),
    [
        ("origin coordinate", "00"),
        ("origin coordinate", ("41", "-87")),
        ("origin coordinate", (True, 0)),
        ("origin road coordinate", (float("nan"), 0)),
        ("destination road coordinate", (0, float("inf"))),
        ("destination coordinate", (91, 0)),
    ],
)
def test_matrix_result_rejects_invalid_coordinates(field, coordinate):
    origin_coordinate = coordinate if field == "origin coordinate" else (0, 0)
    destination_coordinate = coordinate if field == "destination coordinate" else (0, 0)
    destination_road_coordinate = (
        coordinate if field == "destination road coordinate" else None
    )
    origin_road_coordinate = coordinate if field == "origin road coordinate" else None

    with pytest.raises(ValueError, match=field):
        MatrixResult(
            (origin_coordinate,),
            (origin_road_coordinate,),
            (None,),
            ("course",),
            (
                DestinationTimes(
                    destination_coordinate,
                    destination_road_coordinate,
                    None,
                    (1.0,),
                ),
            ),
            MatrixMetadata("synthetic-static", TrafficBasis.UNAWARE),
        )


def test_reverse_fallback_matches_index_at_a_rounding_boundary():
    first = 38.687880225382735
    second = 8.83218919985173
    third = 25.22543057476554
    forward_sum = (first + second) + third
    graph = nx.DiGraph()
    graph.add_node("origin", y=0, x=0)
    graph.add_node("one", y=0, x=1)
    graph.add_node("two", y=0, x=2)
    graph.add_node("zeta", y=0, x=3)
    graph.add_node("alpha", y=1, x=0)
    graph.add_edge("origin", "one", travel_time=first)
    graph.add_edge("one", "two", travel_time=second)
    graph.add_edge("two", "zeta", travel_time=third)
    graph.add_edge("origin", "alpha", travel_time=forward_sum)
    road = CompactRoadGraph.from_networkx(graph)
    origins = ((0, 0), (0, 0))
    destinations = ((0, 3), (1, 0))

    fallback = StaticModoMatrix(road).calculate(origins, destinations)
    course_vertices = road.nearest_vertices(destinations)
    rows = np.atleast_2d(
        matrix_module.dijkstra(
            road._matrix.T,
            directed=True,
            indices=[road._indices[vertex] for vertex in course_vertices],
        )
    ).astype(np.float64, copy=False)
    index = CourseDistanceIndex("a" * 64, "b" * 64, ("zeta", "alpha"), rows)
    indexed = StaticModoMatrix(road, course_index=index).calculate(
        origins, destinations, ("zeta", "alpha")
    )

    assert [item.travel_times_seconds for item in fallback.destinations] == [
        item.travel_times_seconds for item in indexed.destinations
    ]
    assert canonical_milliseconds(fallback.destinations[0].travel_times_seconds) == (
        72745,
        72745,
    )
    forward = (
        road.analyze_vertices(("origin",)).travel_times("zeta").travel_times_seconds[0]
    )
    assert canonical_milliseconds((forward,)) == (72746,)


def test_static_modo_matrix_rejects_distant_points():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    road = CompactRoadGraph.from_networkx(graph)
    with pytest.raises(OutsideRoadCoverage):
        StaticModoMatrix(road, 1).calculate([(40.71, -74.0)], [(41.88, -87.80)])


def test_distance_uses_kilometers():
    assert distance_kilometers((41.88, -87.80), (41.88, -87.80)) == 0
    assert 80 < distance_kilometers((41.88, -87.80), (42.88, -87.80)) < 130


def test_validate_road_snapshot_requires_directed_positive_weights():
    directed = nx.DiGraph()
    directed.add_node("a", y=0, x=0)
    directed.add_node("b", y=0, x=1)
    directed.add_edge("a", "b", travel_time=1)
    validate_road_snapshot(CompactRoadGraph.from_networkx(directed))

    undirected = directed.to_undirected()
    with pytest.raises(ValueError, match="directed graph"):
        validate_road_snapshot(CompactRoadGraph.from_networkx(undirected))

    directed["a"]["b"]["travel_time"] = 0
    with pytest.raises(ValueError, match="finite and positive"):
        validate_road_snapshot(CompactRoadGraph.from_networkx(directed))
