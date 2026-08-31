"""Replaceable travel-time matrix boundary."""

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt


class OutsideRoadCoverage(ValueError):
    """A supplied point is too far from the active road graph."""


@dataclass(frozen=True)
class DestinationTimes:
    coordinate: tuple[float, float]
    road_coordinate: tuple[float, float]
    travel_times_seconds: tuple[float, ...]


@dataclass(frozen=True)
class MatrixResult:
    origin_road_coordinates: tuple[tuple[float, float], ...]
    destinations: tuple[DestinationTimes, ...]


class StaticModoMatrix:
    """Calculate a bounded matrix from one immutable modo road graph."""

    def __init__(self, road, max_snap_distance_kilometers=5):
        self.road = road
        self.max_snap_distance_kilometers = max_snap_distance_kilometers

    def calculate(self, origins, destinations):
        origins = tuple(origins)
        destinations = tuple(destinations)
        points = origins + destinations
        vertices = self.road.nearest_vertices(points)
        road_points = self.road.coordinates(vertices)
        if any(
            distance_kilometers(point, road_point) > self.max_snap_distance_kilometers
            for point, road_point in zip(points, road_points, strict=True)
        ):
            raise OutsideRoadCoverage
        origin_vertices = vertices[: len(origins)]
        analysis = self.road.analyze_vertices(origin_vertices)
        results = tuple(
            DestinationTimes(
                coordinate,
                road_points[len(origins) + index],
                analysis.travel_times(vertex).travel_times_seconds,
            )
            for index, (coordinate, vertex) in enumerate(
                zip(destinations, vertices[len(origins) :], strict=True)
            )
        )
        return MatrixResult(road_points[: len(origins)], results)


def distance_kilometers(first, second):
    """Return great-circle distance between two latitude, longitude pairs."""
    first_latitude, first_longitude = map(radians, first)
    second_latitude, second_longitude = map(radians, second)
    latitude_delta = second_latitude - first_latitude
    longitude_delta = second_longitude - first_longitude
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude) * cos(second_latitude) * sin(longitude_delta / 2) ** 2
    )
    return 12_742.0176 * asin(sqrt(min(1, haversine)))
