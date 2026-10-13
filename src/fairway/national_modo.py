"""Thin adapters from modo's private nationwide library to fairway contracts."""

from math import isfinite

from modo import RoutingCoverageError

from .matrix import (
    DestinationFailure,
    DestinationTimes,
    MatrixMetadata,
    MatrixResult,
    TimeDependentMatrixUnsupported,
    TrafficBasis,
)
from .national import (
    MAX_AREA_RADIUS_KILOMETERS,
    AreaSearchMetadata,
    PromisingArea,
    PromisingAreas,
)

MODO_OBJECTIVES = {"maximum": "maximum", "combined": "total"}
DEFAULT_FACILITY_RADIUS_KILOMETERS = 25


class ModoPromisingAreaProvider:
    """Translate a modo NationwideEstimator without hosting modo as a service."""

    def __init__(
        self,
        estimator,
        *,
        tolerance_seconds=900,
        facility_radius_kilometers=DEFAULT_FACILITY_RADIUS_KILOMETERS,
    ):
        if (
            type(tolerance_seconds) not in {int, float}
            or not isfinite(tolerance_seconds)
            or tolerance_seconds < 0
        ):
            raise ValueError("area tolerance must be finite and nonnegative")
        if (
            type(facility_radius_kilometers) not in {int, float}
            or not isfinite(facility_radius_kilometers)
            or not 0 < facility_radius_kilometers <= MAX_AREA_RADIUS_KILOMETERS
        ):
            raise ValueError(
                "facility radius must be positive and no greater than "
                f"{MAX_AREA_RADIUS_KILOMETERS} km"
            )
        self.estimator = estimator
        self.tolerance_seconds = float(tolerance_seconds)
        self.facility_radius_kilometers = float(facility_radius_kilometers)

    def find_promising_areas(self, origins, objective, *, limit):
        origins = tuple(origins)
        try:
            modo_objective = MODO_OBJECTIVES[objective]
        except KeyError as error:
            raise ValueError("objective must be 'combined' or 'maximum'") from error
        result = self.estimator.estimate(
            origins,
            objective=modo_objective,
            tolerance_seconds=self.tolerance_seconds,
        )
        if result.objective != modo_objective:
            raise RuntimeError("modo changed the area-search objective")
        if result.approximate is not True:
            raise RuntimeError("modo area search must identify itself as approximate")
        candidates = tuple(
            result.promising_candidates(
                limit=limit,
                catchment_radius_kilometers=self.facility_radius_kilometers,
            )
        )
        for candidate in candidates:
            times = tuple(candidate.travel_times_seconds)
            if len(times) != len(origins) or any(
                type(value) not in {int, float} or not isfinite(value) or value < 0
                for value in times
            ):
                raise RuntimeError("modo returned invalid candidate travel times")
            if (
                type(candidate.resolution_kilometers) not in {int, float}
                or not isfinite(candidate.resolution_kilometers)
                or candidate.resolution_kilometers <= 0
            ):
                raise RuntimeError("modo returned invalid optimization resolution")
            if candidate.radius_kilometers != self.facility_radius_kilometers:
                raise RuntimeError("modo changed the requested facility radius")
        return PromisingAreas(
            origin_coordinates=origins,
            objective=objective,
            areas=tuple(
                PromisingArea(
                    candidate.identifier,
                    tuple(candidate.center),
                    candidate.radius_kilometers,
                )
                for candidate in candidates
            ),
            metadata=AreaSearchMetadata(
                provider="modo-national",
                strategy=result.method,
                provenance=(
                    ("approximate", True),
                    ("evaluated_candidates", result.evaluated_candidates),
                    ("area_matrix_requests", result.matrix_requests),
                    ("final_resolution_kilometers", result.final_resolution_km),
                    (
                        "facility_radius_kilometers",
                        self.facility_radius_kilometers,
                    ),
                    ("tolerance_seconds", self.tolerance_seconds),
                ),
            ),
        )


class ModoMatrixProvider:
    """Translate modo's routing provider matrix into fairway's matrix model."""

    def __init__(self, provider):
        self.provider = provider

    def calculate(self, origins, destinations, destination_ids=None, *, departure=None):
        if departure is not None:
            raise TimeDependentMatrixUnsupported(
                "the private modo Valhalla adapter is traffic-unaware"
            )
        origins = tuple(origins)
        destinations = tuple(destinations)
        if destination_ids is None:
            destination_ids = tuple(str(index) for index in range(len(destinations)))
        else:
            destination_ids = tuple(destination_ids)
        if len(destination_ids) != len(destinations):
            raise ValueError("destination identifiers must match destinations")

        isolated = False
        try:
            results = _destination_results(self.provider, origins, destinations)
        except RoutingCoverageError:
            _validate_origins(self.provider, origins)
            isolated = True
            results = _isolate_destinations(self.provider, origins, destinations)

        return MatrixResult(
            origin_coordinates=origins,
            origin_road_coordinates=(None,) * len(origins),
            origin_snap_distances_kilometers=(None,) * len(origins),
            destination_ids=destination_ids,
            destinations=tuple(results),
            metadata=MatrixMetadata(
                provider="modo-valhalla",
                strategy=(
                    "bounded-destination-isolation"
                    if isolated
                    else "bounded-sources-to-targets"
                ),
                traffic_basis=TrafficBasis.UNAWARE,
            ),
        )


def _matrix_rows(provider, origins, destinations):
    rows = tuple(tuple(row) for row in provider.matrix(origins, destinations))
    if len(rows) != len(origins) or any(len(row) != len(destinations) for row in rows):
        raise RuntimeError("modo returned invalid matrix dimensions")
    return rows


def _destination_results(provider, origins, destinations):
    rows = _matrix_rows(provider, origins, destinations)
    results = []
    for destination_index, destination in enumerate(destinations):
        values = tuple(row[destination_index] for row in rows)
        if any(value is None for value in values):
            results.append(DestinationFailure(destination, None, None, "unreachable"))
            continue
        times = tuple(float(value) for value in values)
        if any(not isfinite(value) or value < 0 for value in times):
            raise RuntimeError("modo returned invalid matrix travel times")
        results.append(DestinationTimes(destination, None, None, times))
    return tuple(results)


def _validate_origins(provider, origins):
    for index, origin in enumerate(origins):
        rows = _matrix_rows(provider, (origin,), (origin,))
        value = rows[0][0]
        if value is None:
            raise RoutingCoverageError(f"origin {index} has no usable road location")
        try:
            value = float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError("modo returned invalid matrix travel times") from error
        if not isfinite(value) or value < 0:
            raise RuntimeError("modo returned invalid matrix travel times")


def _isolate_destinations(provider, origins, destinations):
    results = []

    def evaluate(batch):
        try:
            results.extend(_destination_results(provider, origins, batch))
        except RoutingCoverageError:
            if len(batch) == 1:
                results.append(
                    DestinationFailure(batch[0], None, None, "outside-road-coverage")
                )
                return
            middle = len(batch) // 2
            evaluate(batch[:middle])
            evaluate(batch[middle:])

    middle = len(destinations) // 2
    if middle:
        evaluate(destinations[:middle])
        evaluate(destinations[middle:])
    else:
        evaluate(destinations)
    return tuple(results)
