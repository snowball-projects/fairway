from dataclasses import replace

import pytest

from fairway.courses import Course
from fairway.matrix import (
    DestinationTimes,
    MatrixMetadata,
    MatrixResult,
    TrafficBasis,
)
from fairway.national import (
    MAX_AREA_RADIUS_KILOMETERS,
    AreaSearchMetadata,
    PromisingArea,
    PromisingAreas,
    calculate_national_ranking,
    shortlist_courses,
)

ORIGINS = ((47.6062, -122.3321), (40.7128, -74.0060))


def course(
    identifier,
    coordinate,
    *,
    name=None,
    access="public",
    destination_kind="verified_entrance",
    address_purpose="arrival",
    holes=18,
):
    return Course(
        identifier=identifier,
        name=name or identifier.title(),
        address="1 Test Way",
        routing_coordinate=coordinate,
        holes=holes,
        access=access,
        website="https://example.com/course",
        facts_source="operator",
        routing_source="osm",
        routing_reference="node/1",
        destination_kind=destination_kind,
        address_purpose=address_purpose,
        facility_identifier=f"facility-{identifier}",
    )


class Areas:
    def __init__(self, centers=((41.0, -96.0),), radius_kilometers=80):
        self.centers = centers
        self.radius_kilometers = radius_kilometers
        self.calls = []

    def find_promising_areas(self, origins, objective, *, limit):
        origins = tuple(origins)
        self.calls.append((origins, objective, limit))
        return PromisingAreas(
            origin_coordinates=origins,
            objective=objective,
            areas=tuple(
                PromisingArea(f"area-{index}", center, self.radius_kilometers)
                for index, center in enumerate(self.centers)
            ),
            metadata=AreaSearchMetadata(
                provider="modo-fixture",
                strategy="bounded-grid-fixture",
                provenance=(("approximation", True),),
            ),
        )


class Matrix:
    def __init__(self, times):
        self.times = times
        self.calls = []

    def calculate(self, origins, destinations, destination_ids, *, departure):
        origins = tuple(origins)
        destinations = tuple(destinations)
        destination_ids = tuple(destination_ids)
        self.calls.append((origins, destinations, destination_ids, departure))
        return MatrixResult(
            origin_coordinates=origins,
            origin_road_coordinates=(None,) * len(origins),
            origin_snap_distances_kilometers=(None,) * len(origins),
            destination_ids=destination_ids,
            destinations=tuple(
                DestinationTimes(destination, None, None, self.times[identifier])
                for destination, identifier in zip(
                    destinations, destination_ids, strict=True
                )
            ),
            metadata=MatrixMetadata(
                provider="national-matrix-fixture",
                traffic_basis=TrafficBasis.UNAWARE,
            ),
        )


@pytest.mark.parametrize(
    ("objective", "expected"),
    [("maximum", ("balanced", "combined")), ("combined", ("combined", "balanced"))],
)
def test_routes_only_bounded_spatial_shortlist_and_reuses_ranking(objective, expected):
    courses = (
        course(
            "property-center",
            (41.0, -96.0),
            destination_kind="osm_property_point",
            address_purpose="course",
        ),
        course("balanced", (41.01, -96.0), name="Balanced"),
        course("combined", (41.02, -96.0), name="Combined"),
        course("not-routed", (41.03, -96.0), name="Not routed"),
    )
    areas = Areas()
    matrix = Matrix(
        {
            "balanced": (5.0, 6.0),
            "combined": (1.0, 9.0),
            "not-routed": (1.0, 1.0),
        }
    )

    result = calculate_national_ranking(
        ORIGINS,
        objective,
        courses,
        areas,
        matrix,
        shortlist_limit=2,
    )

    assert areas.calls == [(ORIGINS, objective, 8)]
    assert tuple(item.identifier for item in result.shortlisted_courses) == (
        "balanced",
        "combined",
    )
    assert len(matrix.calls) == 1
    assert matrix.calls[0][0] == ORIGINS
    assert matrix.calls[0][2] == ("balanced", "combined")
    assert matrix.calls[0][3] is None
    assert tuple(item.course.identifier for item in result.ranking.courses) == expected


def test_shortlist_requires_explicit_reviewed_public_arrivals():
    area = PromisingArea("center", (41.0, -96.0), 80)
    eligible = course("eligible", (41.04, -96.0))
    courses = (
        course("private", (41.0, -96.0), access="private"),
        course(
            "property",
            (41.01, -96.0),
            destination_kind="reviewed_property_center",
        ),
        course(
            "estimate",
            (41.02, -96.0),
            destination_kind="reviewed_osm_point",
            address_purpose="estimate",
        ),
        course("wrong-holes", (41.03, -96.0), holes=9),
        eligible,
    )

    assert shortlist_courses(courses, (area,), holes=(18,), limit=5) == (eligible,)


def test_shortlist_represents_multiple_promising_areas_before_filling_dense_one():
    west = course("west", (40.0, -120.0))
    west_second = course("west-second", (40.01, -120.0))
    east = course("east", (40.0, -75.0))

    shortlisted = shortlist_courses(
        (west, west_second, east),
        (
            PromisingArea("west-area", (40.0, -120.0), 80),
            PromisingArea("east-area", (40.0, -75.0), 80),
        ),
        limit=2,
    )

    assert shortlisted == (west, east)


def test_overlapping_areas_deduplicate_and_honor_course_cap():
    courses = tuple(
        course(f"course-{index}", (41.0 + index / 100, -96.0)) for index in range(5)
    )
    areas = (
        PromisingArea("first", (41.0, -96.0), 80),
        PromisingArea("second", (41.01, -96.0), 80),
    )

    shortlisted = shortlist_courses(courses, areas, limit=3)

    assert len(shortlisted) == 3
    assert len({item.identifier for item in shortlisted}) == 3


def test_spherical_longitude_prefilter_keeps_course_inside_exact_radius():
    inside = course("edge", (40.0, -95.988265))

    shortlisted = shortlist_courses(
        (inside,),
        (PromisingArea("area", (40.0, -96.0), 1),),
    )

    assert shortlisted == (inside,)


def test_distant_only_catalog_fails_without_matrix_call():
    matrix = Matrix({"chicago": (1.0, 1.0)})

    with pytest.raises(
        ValueError, match="reviewed routing arrival inside the promising areas"
    ):
        calculate_national_ranking(
            ORIGINS,
            "maximum",
            (course("chicago", (41.8781, -87.6298)),),
            Areas(centers=((34.0522, -118.2437),), radius_kilometers=40),
            matrix,
        )

    assert matrix.calls == []


@pytest.mark.parametrize("radius", [0, -1, float("inf"), 161])
def test_promising_area_radius_is_explicitly_bounded(radius):
    with pytest.raises(ValueError, match="promising area radius"):
        PromisingArea("area", (41.0, -96.0), radius)

    assert MAX_AREA_RADIUS_KILOMETERS == 160


@pytest.mark.parametrize("mismatch", ["origins", "objective", "too-many", "duplicate"])
def test_rejects_broken_area_provider_contract_before_routing(mismatch):
    class BrokenAreas(Areas):
        def find_promising_areas(self, origins, objective, *, limit):
            result = super().find_promising_areas(origins, objective, limit=limit)
            if mismatch == "origins":
                return replace(
                    result, origin_coordinates=result.origin_coordinates[::-1]
                )
            if mismatch == "objective":
                return replace(result, objective="combined")
            if mismatch == "too-many":
                return replace(
                    result,
                    areas=tuple(
                        PromisingArea(f"area-{index}", (41.0, -96.0), 80)
                        for index in range(limit + 1)
                    ),
                )
            return replace(result, areas=(result.areas[0], result.areas[0]))

    matrix = Matrix({"eligible": (1.0, 1.0)})

    with pytest.raises(RuntimeError):
        calculate_national_ranking(
            ORIGINS,
            "maximum",
            (course("eligible", (41.0, -96.0)),),
            BrokenAreas(),
            matrix,
        )

    assert matrix.calls == []


def test_rejects_matrix_that_changes_origin_identity():
    class BrokenMatrix(Matrix):
        def calculate(self, origins, destinations, destination_ids, *, departure):
            result = super().calculate(
                origins, destinations, destination_ids, departure=departure
            )
            return replace(result, origin_coordinates=result.origin_coordinates[::-1])

    with pytest.raises(RuntimeError, match="origin identity or order"):
        calculate_national_ranking(
            ORIGINS,
            "maximum",
            (course("eligible", (41.0, -96.0)),),
            Areas(),
            BrokenMatrix({"eligible": (1.0, 1.0)}),
        )


def test_normalizes_json_style_origin_lists_before_provider_contracts():
    areas = Areas()
    matrix = Matrix({"eligible": (1.0, 1.0)})

    result = calculate_national_ranking(
        [[47.6062, -122.3321], [40.7128, -74.0060]],
        "maximum",
        (course("eligible", (41.0, -96.0)),),
        areas,
        matrix,
    )

    assert result.matrix.origin_coordinates == ORIGINS
    assert areas.calls[0][0] == ORIGINS
    assert matrix.calls[0][0] == ORIGINS
