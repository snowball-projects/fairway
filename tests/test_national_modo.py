from dataclasses import dataclass
from math import hypot

import pytest
from modo import NationwideEstimator, RoutingCoverageError, RoutingProviderError

from fairway.courses import Course
from fairway.national import calculate_national_ranking
from fairway.national_modo import ModoMatrixProvider, ModoPromisingAreaProvider


@dataclass(frozen=True)
class Candidate:
    identifier: str
    center: tuple[float, float]
    radius_kilometers: float
    travel_times_seconds: tuple[float, ...]
    resolution_kilometers: float


class Estimate:
    objective = "total"
    approximate = True
    method = "bounded fixture"
    evaluated_candidates = 31
    matrix_requests = 4
    final_resolution_km = 12.5

    def promising_candidates(self, *, limit, catchment_radius_kilometers):
        return (
            Candidate(
                "modo:first",
                (41.0, -96.0),
                catchment_radius_kilometers,
                (10.0, 20.0),
                12.5,
            ),
            Candidate(
                "modo:second",
                (42.0, -95.0),
                catchment_radius_kilometers,
                (11.0, 19.0),
                12.5,
            ),
        )[:limit]


class Estimator:
    def __init__(self):
        self.calls = []

    def estimate(self, origins, *, objective, tolerance_seconds):
        self.calls.append((origins, objective, tolerance_seconds))
        return Estimate()


def test_translates_combined_objective_and_modo_area_provenance():
    estimator = Estimator()
    provider = ModoPromisingAreaProvider(estimator, tolerance_seconds=600)
    origins = ((40.0, -100.0), (42.0, -90.0))

    result = provider.find_promising_areas(origins, "combined", limit=1)

    assert estimator.calls == [(origins, "total", 600.0)]
    assert result.origin_coordinates == origins
    assert result.objective == "combined"
    assert [
        (area.identifier, area.center, area.radius_kilometers) for area in result.areas
    ] == [("modo:first", (41.0, -96.0), 25.0)]
    assert result.metadata.provider == "modo-national"
    assert result.metadata.strategy == "bounded fixture"
    assert dict(result.metadata.provenance) == {
        "approximate": True,
        "evaluated_candidates": 31,
        "area_matrix_requests": 4,
        "final_resolution_kilometers": 12.5,
        "facility_radius_kilometers": 25.0,
        "tolerance_seconds": 600.0,
    }


def test_facility_catchment_is_separate_and_explicitly_bounded():
    provider = ModoPromisingAreaProvider(Estimator(), facility_radius_kilometers=40)

    result = provider.find_promising_areas(
        ((40.0, -100.0), (42.0, -90.0)), "combined", limit=1
    )

    assert result.areas[0].radius_kilometers == 40.0
    assert dict(result.metadata.provenance)["final_resolution_kilometers"] == 12.5
    with pytest.raises(ValueError, match="facility radius"):
        ModoPromisingAreaProvider(Estimator(), facility_radius_kilometers=161)


class Matrix:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def matrix(self, origins, destinations):
        self.calls.append((tuple(origins), tuple(destinations)))
        return self.rows


def test_transposes_modo_rows_into_fairway_destinations():
    modo = Matrix(((10.0, 30.0), (20.0, None)))
    provider = ModoMatrixProvider(modo)
    origins = ((40.0, -100.0), (42.0, -90.0))
    destinations = ((41.0, -96.0), (41.5, -95.5))

    result = provider.calculate(origins, destinations, ("first", "second"))

    assert modo.calls == [(origins, destinations)]
    assert result.destination_ids == ("first", "second")
    assert result.destinations[0].travel_times_seconds == (10.0, 20.0)
    assert result.destinations[1].reason == "unreachable"
    assert result.metadata.provider == "modo-valhalla"


def test_rejects_invalid_modo_matrix_dimensions():
    with pytest.raises(RuntimeError, match="matrix dimensions"):
        ModoMatrixProvider(Matrix(((1.0,),))).calculate(
            ((40.0, -100.0), (42.0, -90.0)),
            ((41.0, -96.0),),
            ("course",),
        )


class IsolatingMatrix:
    def __init__(self, *, bad_destination=None, bad_origin=None, failure=None):
        self.bad_destination = bad_destination
        self.bad_origin = bad_origin
        self.failure = failure
        self.calls = []

    def matrix(self, origins, destinations):
        origins = tuple(origins)
        destinations = tuple(destinations)
        self.calls.append((origins, destinations))
        if self.failure is not None:
            raise self.failure
        if self.bad_origin in origins or self.bad_destination in destinations:
            raise RoutingCoverageError("fixture outside coverage")
        return tuple(
            tuple(
                float(origin_index + destination_index + 1)
                for destination_index, _ in enumerate(destinations)
            )
            for origin_index, _ in enumerate(origins)
        )


def test_isolates_bad_destination_without_losing_valid_venues():
    origins = ((40.0, -100.0), (42.0, -90.0))
    good = (41.0, -96.0)
    bad = (0.0, 0.0)
    modo = IsolatingMatrix(bad_destination=bad)

    result = ModoMatrixProvider(modo).calculate(origins, (good, bad), ("good", "bad"))

    assert result.destinations[0].travel_times_seconds == (1.0, 2.0)
    assert result.destinations[1].reason == "outside-road-coverage"
    assert result.metadata.strategy == "bounded-destination-isolation"
    assert modo.calls == [
        (origins, (good, bad)),
        ((origins[0],), (origins[0],)),
        ((origins[1],), (origins[1],)),
        (origins, (good,)),
        (origins, (bad,)),
    ]


def test_invalid_origin_coverage_failure_propagates():
    origins = ((40.0, -100.0), (0.0, 0.0))
    modo = IsolatingMatrix(bad_origin=origins[1])

    with pytest.raises(RoutingCoverageError, match="fixture outside coverage"):
        ModoMatrixProvider(modo).calculate(origins, ((41.0, -96.0),), ("course",))


def test_noncoverage_provider_failure_propagates_without_isolation():
    failure = RoutingProviderError("provider unavailable")
    modo = IsolatingMatrix(failure=failure)

    with pytest.raises(RoutingProviderError, match="provider unavailable"):
        ModoMatrixProvider(modo).calculate(
            ((40.0, -100.0), (42.0, -90.0)),
            ((41.0, -96.0), (41.5, -95.5)),
            ("first", "second"),
        )

    assert len(modo.calls) == 1


class PlaneMatrix:
    def __init__(self):
        self.calls = []

    def matrix(self, origins, destinations):
        origins = tuple(origins)
        destinations = tuple(destinations)
        self.calls.append((origins, destinations))
        return tuple(
            tuple(
                hypot(origin[0] - destination[0], origin[1] - destination[1]) * 3600
                for destination in destinations
            )
            for origin in origins
        )


def test_actual_modo_estimator_contract_runs_complete_fairway_pipeline():
    provider = PlaneMatrix()
    estimator = NationwideEstimator(
        provider,
        coarse_candidate_limit=25,
        refinement_rounds=2,
        matrix_target_limit=10,
    )
    course = Course(
        identifier="course",
        name="Reviewed Course",
        address="1 Test Way",
        routing_coordinate=(41.0, -88.0),
        holes=18,
        access="public",
        website="https://example.com/course",
        facts_source="operator",
        routing_source="osm",
        routing_reference="node/1",
        destination_kind="verified_entrance",
        address_purpose="arrival",
        facility_identifier="facility",
    )

    result = calculate_national_ranking(
        ((41.0, -90.0), (41.0, -86.0)),
        "maximum",
        (course,),
        ModoPromisingAreaProvider(estimator, facility_radius_kilometers=25),
        ModoMatrixProvider(provider),
    )

    assert result.shortlisted_courses == (course,)
    assert result.ranking.courses[0].course is course
    assert result.areas.metadata.provider == "modo-national"
    assert dict(result.areas.metadata.provenance)["approximate"] is True
    assert len(provider.calls) == (
        dict(result.areas.metadata.provenance)["area_matrix_requests"] + 1
    )
