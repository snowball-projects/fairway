"""Bounded national candidate-area, course-shortlist, and ranking pipeline."""

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from .courses import Course
from .matrix import MatrixProvider, MatrixResult, distance_kilometers
from .ranking import CourseRanking, rank_course_matrix

MAX_PROMISING_AREAS = 8
MAX_ROUTED_COURSES = 24
ROUTING_DESTINATION_KINDS = frozenset({"reviewed_osm_point", "verified_entrance"})
ROUTING_ADDRESS_PURPOSES = frozenset({"course", "clubhouse", "arrival"})


@dataclass(frozen=True)
class PromisingArea:
    """One ordered coarse search result from an area provider such as modo."""

    identifier: str
    center: tuple[float, float]

    def __post_init__(self):
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("promising area identifier must be a nonempty string")
        _require_coordinate("promising area center", self.center)


@dataclass(frozen=True)
class AreaSearchMetadata:
    provider: str
    strategy: str
    provenance: tuple[tuple[str, str | int | float | bool | None], ...] = ()

    def __post_init__(self):
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("area provider must be a nonempty string")
        if not isinstance(self.strategy, str) or not self.strategy.strip():
            raise ValueError("area strategy must be a nonempty string")
        keys = [key for key, _value in self.provenance]
        if any(not isinstance(key, str) or not key for key in keys):
            raise ValueError("area provenance keys must be nonempty strings")
        if len(keys) != len(set(keys)):
            raise ValueError("area provenance keys must be unique")
        for _key, value in self.provenance:
            if type(value) not in {str, int, float, bool, type(None)} or (
                type(value) is float and not isfinite(value)
            ):
                raise ValueError("area provenance values must be finite JSON scalars")


@dataclass(frozen=True)
class PromisingAreas:
    origin_coordinates: tuple[tuple[float, float], ...]
    objective: str
    areas: tuple[PromisingArea, ...]
    metadata: AreaSearchMetadata


class PromisingAreaProvider(Protocol):
    """Structural boundary for modo's bounded coarse-to-fine area search."""

    def find_promising_areas(
        self,
        origins,
        objective: str,
        *,
        limit: int,
    ) -> PromisingAreas: ...


@dataclass(frozen=True)
class NationalRanking:
    areas: PromisingAreas
    shortlisted_courses: tuple[Course, ...]
    matrix: MatrixResult
    ranking: CourseRanking


def shortlist_courses(courses, areas, *, holes=(9, 18), limit=MAX_ROUTED_COURSES):
    """Select actual reviewed arrivals near promising area centers."""
    areas = tuple(areas)
    holes = frozenset(holes)
    _require_limit("course shortlist", limit, MAX_ROUTED_COURSES)
    if not areas:
        raise ValueError("at least one promising area is required")
    if not holes or not holes <= {9, 18}:
        raise ValueError("holes must contain 9, 18, or both")

    eligible = tuple(
        course
        for course in courses
        if course.holes in holes and _has_reviewed_arrival(course)
    )
    nearest_by_area = tuple(
        sorted(
            eligible,
            key=lambda course: (
                distance_kilometers(course.routing_coordinate, area.center),
                course.name,
                course.identifier,
            ),
        )
        for area in areas
    )
    selected = []
    selected_ids = set()
    for rank in range(len(eligible)):
        for nearest in nearest_by_area:
            course = nearest[rank]
            if course.identifier in selected_ids:
                continue
            selected.append(course)
            selected_ids.add(course.identifier)
            if len(selected) == limit:
                return tuple(selected)
    return tuple(selected)


def calculate_national_ranking(
    origins,
    objective,
    courses,
    area_provider: PromisingAreaProvider,
    matrix_provider: MatrixProvider,
    *,
    holes=(9, 18),
    area_limit=MAX_PROMISING_AREAS,
    shortlist_limit=MAX_ROUTED_COURSES,
):
    """Run one bounded area search, one spatial shortlist, and one route matrix."""
    origins = tuple(origins)
    if not 2 <= len(origins) <= 8:
        raise ValueError("provide between 2 and 8 origins")
    for origin in origins:
        _require_coordinate("origin", origin)
    if objective not in {"combined", "maximum"}:
        raise ValueError("objective must be 'combined' or 'maximum'")
    _require_limit("promising area", area_limit, MAX_PROMISING_AREAS)
    _require_limit("course shortlist", shortlist_limit, MAX_ROUTED_COURSES)

    areas = area_provider.find_promising_areas(origins, objective, limit=area_limit)
    _validate_area_contract(areas, origins, objective, area_limit)
    shortlist = shortlist_courses(
        courses, areas.areas, holes=holes, limit=shortlist_limit
    )
    if not shortlist:
        raise ValueError("no eligible public course has a reviewed routing arrival")

    matrix = matrix_provider.calculate(
        origins,
        (course.routing_coordinate for course in shortlist),
        (course.identifier for course in shortlist),
        departure=None,
    )
    if matrix.origin_coordinates != origins:
        raise RuntimeError("matrix provider changed origin identity or order")
    ranking = rank_course_matrix(shortlist, matrix, objective)
    return NationalRanking(areas, shortlist, matrix, ranking)


def _has_reviewed_arrival(course):
    return (
        course.access == "public"
        and course.destination_kind in ROUTING_DESTINATION_KINDS
        and course.address_purpose in ROUTING_ADDRESS_PURPOSES
    )


def _validate_area_contract(result, origins, objective, limit):
    if not isinstance(result, PromisingAreas):
        raise TypeError("area provider must return PromisingAreas")
    if result.origin_coordinates != origins:
        raise RuntimeError("area provider changed origin identity or order")
    if result.objective != objective:
        raise RuntimeError("area provider changed the ranking objective")
    if not isinstance(result.metadata, AreaSearchMetadata):
        raise TypeError("area provider metadata must be AreaSearchMetadata")
    if not result.areas:
        raise RuntimeError("area provider returned no promising areas")
    if len(result.areas) > limit:
        raise RuntimeError("area provider exceeded the requested area limit")
    if any(not isinstance(area, PromisingArea) for area in result.areas):
        raise TypeError("area provider returned an invalid promising area")
    identifiers = tuple(area.identifier for area in result.areas)
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("area provider returned duplicate area identifiers")


def _require_coordinate(name, value):
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


def _require_limit(name, value, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} limit must be between 1 and {maximum}")
