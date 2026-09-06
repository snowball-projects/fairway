"""Replaceable travel-time matrix boundary."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Protocol

import numpy as np
from scipy.sparse.csgraph import dijkstra

MAX_SNAP_DISTANCE_KILOMETERS = 1
OMITTABLE_DESTINATION_FAILURES = frozenset({"outside-road-coverage", "unreachable"})


class OutsideRoadCoverage(ValueError):
    """A supplied point is too far from the active road graph."""

    def __init__(self, point_kind, point_index, distance_kilometers, limit_kilometers):
        super().__init__(
            f"{point_kind} {point_index + 1} is {distance_kilometers:.3f} km "
            f"from a modeled road; the limit is {limit_kilometers:g} km"
        )
        self.point_kind = point_kind
        self.point_index = point_index
        self.distance_kilometers = distance_kilometers
        self.limit_kilometers = limit_kilometers


class TimeDependentMatrixUnsupported(ValueError):
    """A provider cannot calculate the requested departure semantics."""


class MatrixProviderUnavailable(RuntimeError):
    """A provider cannot safely return a complete matrix right now."""

    def __init__(self, retry_after_seconds=60):
        if type(retry_after_seconds) is not int or not 1 <= retry_after_seconds <= 3600:
            raise ValueError("provider retry delay must be between 1 and 3600 seconds")
        super().__init__("fairway's travel-time provider is temporarily unavailable")
        self.retry_after_seconds = retry_after_seconds


class DepartureMode(str, Enum):
    """Supported time-dependent matrix request modes."""

    LEAVE_NOW = "leave-now"
    DEPART_AT = "depart-at"


class TrafficBasis(str, Enum):
    """Traffic information represented by a provider result."""

    UNAWARE = "traffic-unaware"
    LIVE = "live"
    HISTORICAL = "historical"
    PREDICTED = "predicted"
    BLENDED = "blended"


def _require_aware_timestamp(name, value):
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} must include a UTC offset")


def _require_nonnegative_finite(name, value, *, optional=False):
    if optional and value is None:
        return
    valid = type(value) in {int, float} and isfinite(value) and value >= 0
    if not valid:
        raise ValueError(f"{name} must be finite and nonnegative")


def _require_coordinate(name, value, *, optional=False):
    if optional and value is None:
        return
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(type(coordinate) not in {int, float} for coordinate in value)
    ):
        raise ValueError(f"{name} must be a latitude, longitude pair")
    latitude, longitude = value
    if (
        not isfinite(latitude)
        or not isfinite(longitude)
        or abs(latitude) > 90
        or abs(longitude) > 180
    ):
        raise ValueError(f"{name} must be a finite latitude, longitude pair")


@dataclass(frozen=True)
class DepartureRequest:
    """An explicit leave-now or scheduled-departure request."""

    mode: DepartureMode
    at: datetime | None = None

    def __post_init__(self):
        if not isinstance(self.mode, DepartureMode):
            raise TypeError("departure mode must be a DepartureMode")
        _require_aware_timestamp("departure time", self.at)
        if self.mode is DepartureMode.LEAVE_NOW and self.at is not None:
            raise ValueError("leave-now must not include a departure time")
        if self.mode is DepartureMode.DEPART_AT and self.at is None:
            raise ValueError("depart-at requires a departure time")

    @classmethod
    def leave_now(cls):
        return cls(DepartureMode.LEAVE_NOW)

    @classmethod
    def depart_at(cls, at):
        return cls(DepartureMode.DEPART_AT, at)


@dataclass(frozen=True)
class MatrixMetadata:
    """Provider and timing facts needed to describe one matrix honestly."""

    provider: str
    traffic_basis: TrafficBasis
    strategy: str | None = None
    departure: DepartureRequest | None = None
    departure_time: datetime | None = None
    calculated_at: datetime | None = None
    traffic_data_as_of: datetime | None = None
    provenance: tuple[tuple[str, str | int | float | bool | None], ...] = ()

    def __post_init__(self):
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("matrix provider must be a nonempty string")
        if not isinstance(self.traffic_basis, TrafficBasis):
            raise TypeError("traffic basis must be a TrafficBasis")
        if self.strategy is not None and (
            not isinstance(self.strategy, str) or not self.strategy.strip()
        ):
            raise ValueError("matrix strategy must be a nonempty string")
        if self.departure is not None and not isinstance(
            self.departure, DepartureRequest
        ):
            raise TypeError("departure must be a DepartureRequest")
        for name, value in (
            ("resolved departure time", self.departure_time),
            ("matrix calculation time", self.calculated_at),
            ("traffic data time", self.traffic_data_as_of),
        ):
            _require_aware_timestamp(name, value)
        if self.traffic_basis is TrafficBasis.UNAWARE:
            if any(
                value is not None
                for value in (
                    self.departure,
                    self.departure_time,
                    self.traffic_data_as_of,
                )
            ):
                raise ValueError(
                    "traffic-unaware metadata must not claim traffic or departure time"
                )
        elif any(
            value is None
            for value in (self.departure, self.departure_time, self.calculated_at)
        ):
            raise ValueError(
                "traffic-aware metadata requires departure and calculation times"
            )
        if (
            self.departure is not None
            and self.departure.mode is DepartureMode.DEPART_AT
            and self.departure_time != self.departure.at
        ):
            raise ValueError("resolved departure time must match the depart-at request")
        keys = [key for key, _value in self.provenance]
        if any(not isinstance(key, str) or not key for key in keys):
            raise ValueError("matrix provenance keys must be nonempty strings")
        if len(keys) != len(set(keys)):
            raise ValueError("matrix provenance keys must be unique")
        for _key, value in self.provenance:
            if type(value) not in {str, int, float, bool, type(None)} or (
                type(value) is float and not isfinite(value)
            ):
                raise ValueError("matrix provenance values must be finite JSON scalars")


@dataclass(frozen=True)
class DestinationTimes:
    coordinate: tuple[float, float]
    road_coordinate: tuple[float, float] | None
    snap_distance_kilometers: float | None
    travel_times_seconds: tuple[float, ...]


@dataclass(frozen=True)
class DestinationFailure:
    coordinate: tuple[float, float]
    road_coordinate: tuple[float, float] | None
    snap_distance_kilometers: float | None
    reason: str

    def __post_init__(self):
        if self.reason not in OMITTABLE_DESTINATION_FAILURES:
            raise ValueError("unsupported destination failure reason")


@dataclass(frozen=True)
class MatrixResult:
    origin_coordinates: tuple[tuple[float, float], ...]
    origin_road_coordinates: tuple[tuple[float, float] | None, ...]
    origin_snap_distances_kilometers: tuple[float | None, ...]
    destination_ids: tuple[str, ...] | None
    destinations: tuple[DestinationTimes | DestinationFailure, ...]
    metadata: MatrixMetadata

    def __post_init__(self):
        origin_count = len(self.origin_coordinates)
        if (
            len(self.origin_road_coordinates) != origin_count
            or len(self.origin_snap_distances_kilometers) != origin_count
        ):
            raise ValueError(
                "origin coordinates, road coordinates, and snap distances must "
                "have equal length"
            )
        for coordinate in self.origin_coordinates:
            _require_coordinate("origin coordinate", coordinate)
        for coordinate in self.origin_road_coordinates:
            _require_coordinate("origin road coordinate", coordinate, optional=True)
        if self.destination_ids is not None:
            if len(self.destination_ids) != len(self.destinations):
                raise ValueError(
                    "destination identifiers and results must have equal length"
                )
            if any(
                not isinstance(identifier, str) or not identifier
                for identifier in self.destination_ids
            ):
                raise ValueError("destination identifiers must be nonempty strings")
        for distance in self.origin_snap_distances_kilometers:
            _require_nonnegative_finite("origin snap distance", distance, optional=True)
        for destination in self.destinations:
            if not isinstance(destination, (DestinationTimes, DestinationFailure)):
                raise TypeError("matrix destinations must contain destination results")
            _require_nonnegative_finite(
                "destination snap distance",
                destination.snap_distance_kilometers,
                optional=True,
            )
            _require_coordinate("destination coordinate", destination.coordinate)
            _require_coordinate(
                "destination road coordinate",
                destination.road_coordinate,
                optional=True,
            )
            if isinstance(destination, DestinationTimes):
                if len(destination.travel_times_seconds) != origin_count:
                    raise ValueError(
                        "each destination must have one travel time per origin"
                    )
                for travel_time in destination.travel_times_seconds:
                    _require_nonnegative_finite("travel time", travel_time)
        if not isinstance(self.metadata, MatrixMetadata):
            raise TypeError("matrix metadata must be MatrixMetadata")


class MatrixProvider(Protocol):
    """Structural interface implemented by static and traffic-aware matrices."""

    def calculate(
        self,
        origins,
        destinations,
        destination_ids=None,
        *,
        departure: DepartureRequest | None = None,
    ) -> MatrixResult: ...


class StaticModoMatrix:
    """Calculate a bounded matrix from one immutable modo road graph."""

    def __init__(
        self,
        road,
        max_snap_distance_kilometers=MAX_SNAP_DISTANCE_KILOMETERS,
        course_index=None,
        metadata=None,
    ):
        self.road = road
        self.max_snap_distance_kilometers = max_snap_distance_kilometers
        self.course_index = course_index
        self.metadata = (
            metadata
            if metadata is not None
            else MatrixMetadata(
                provider="modo-static", traffic_basis=TrafficBasis.UNAWARE
            )
        )
        if not isinstance(self.metadata, MatrixMetadata):
            raise TypeError("StaticModoMatrix metadata must be MatrixMetadata")
        if self.metadata.traffic_basis is not TrafficBasis.UNAWARE:
            raise ValueError("StaticModoMatrix metadata must be traffic-unaware")

    def calculate(self, origins, destinations, destination_ids=None, *, departure=None):
        if departure is not None:
            raise TimeDependentMatrixUnsupported(
                "the static modo fallback does not support departure times or traffic"
            )
        origins = tuple(origins)
        destinations = tuple(destinations)
        if destination_ids is not None:
            destination_ids = tuple(destination_ids)
            if len(destination_ids) != len(destinations):
                raise ValueError("destination identifiers must match destinations")
        points = origins + destinations
        vertices = self.road.nearest_vertices(points)
        road_points = self.road.coordinates(vertices)
        snap_distances = tuple(
            distance_kilometers(point, road_point)
            for point, road_point in zip(points, road_points, strict=True)
        )
        origin_snap_distances = snap_distances[: len(origins)]
        for index, distance in enumerate(origin_snap_distances):
            if distance > self.max_snap_distance_kilometers:
                raise OutsideRoadCoverage(
                    "origin", index, distance, self.max_snap_distance_kilometers
                )

        origin_vertices = vertices[: len(origins)]
        destination_vertices = vertices[len(origins) :]
        use_course_index = self.course_index is not None and destination_ids is not None
        if use_course_index:
            destination_times = self.course_index.lookup(
                destination_ids, origin_vertices, self.road
            )
        else:
            origin_indices = tuple(
                self.road._indices[origin] for origin in origin_vertices
            )
            times_by_destination = {}
            for destination in dict.fromkeys(destination_vertices):
                distances = np.atleast_1d(
                    dijkstra(
                        self.road._matrix.T,
                        directed=True,
                        indices=self.road._indices[destination],
                    )
                )
                times_by_destination[destination] = tuple(
                    float(distances[index]) for index in origin_indices
                )
            destination_times = tuple(
                times_by_destination[destination]
                for destination in destination_vertices
            )

        destination_snap_distances = snap_distances[len(origins) :]
        results = []
        for index, (coordinate, vertex) in enumerate(
            zip(destinations, destination_vertices, strict=True)
        ):
            road_coordinate = road_points[len(origins) + index]
            snap_distance = destination_snap_distances[index]
            if snap_distance > self.max_snap_distance_kilometers:
                results.append(
                    DestinationFailure(
                        coordinate,
                        road_coordinate,
                        snap_distance,
                        "outside-road-coverage",
                    )
                )
                continue
            travel_times = destination_times[index]
            if any(
                value is None or not isfinite(float(value)) for value in travel_times
            ):
                results.append(
                    DestinationFailure(
                        coordinate, road_coordinate, snap_distance, "unreachable"
                    )
                )
                continue
            results.append(
                DestinationTimes(
                    coordinate,
                    road_coordinate,
                    snap_distance,
                    tuple(float(value) for value in travel_times),
                )
            )
        return MatrixResult(
            origin_coordinates=origins,
            origin_road_coordinates=road_points[: len(origins)],
            origin_snap_distances_kilometers=origin_snap_distances,
            destination_ids=destination_ids,
            destinations=tuple(results),
            metadata=replace(
                self.metadata,
                strategy=(
                    "precomputed-course-index"
                    if use_course_index
                    else "sequential-dijkstra"
                ),
            ),
        )


def validate_road_snapshot(road):
    """Reject snapshots that cannot represent directed positive travel time."""
    try:
        directed = road._directed
        matrix = road._matrix
    except AttributeError as error:
        raise ValueError("unsupported modo road snapshot implementation") from error
    if (
        directed is not True
        or matrix.shape[0] == 0
        or matrix.shape[0] != matrix.shape[1]
    ):
        raise ValueError("road snapshot must contain a nonempty directed graph")
    if matrix.nnz == 0 or any(
        not isfinite(float(value)) or float(value) <= 0 for value in matrix.data
    ):
        raise ValueError("road snapshot travel times must be finite and positive")


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
