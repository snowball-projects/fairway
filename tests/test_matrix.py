import networkx as nx
import pytest
from modo import CompactRoadGraph

from fairway.matrix import OutsideRoadCoverage, StaticModoMatrix, distance_kilometers


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
    assert [item.travel_times_seconds for item in result.destinations] == [
        (1.0, 9.0),
        (5.0, 6.0),
    ]


def test_static_modo_matrix_rejects_distant_points():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    road = CompactRoadGraph.from_networkx(graph)
    with pytest.raises(OutsideRoadCoverage):
        StaticModoMatrix(road, 1).calculate([(40.71, -74.0)], [(41.88, -87.80)])


def test_distance_uses_kilometers():
    assert distance_kilometers((41.88, -87.80), (41.88, -87.80)) == 0
    assert 80 < distance_kilometers((41.88, -87.80), (42.88, -87.80)) < 130
