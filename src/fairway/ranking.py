"""Provider-independent course ranking from one bounded travel-time matrix."""

from dataclasses import dataclass

from .courses import Course
from .matrix import DestinationFailure, DestinationTimes, MatrixResult
from .scoring import canonical_milliseconds


@dataclass(frozen=True)
class RankedCourse:
    course: Course
    destination: DestinationTimes
    travel_times_milliseconds: tuple[int, ...]
    combined_milliseconds: int
    maximum_milliseconds: int
    rank: int


@dataclass(frozen=True)
class UnrankedCourse:
    course: Course
    reason: str


@dataclass(frozen=True)
class CourseRanking:
    courses: tuple[RankedCourse, ...]
    unranked_courses: tuple[UnrankedCourse, ...]


def rank_course_matrix(courses, matrix: MatrixResult, objective: str) -> CourseRanking:
    """Validate and rank one complete, bounded course matrix."""
    courses = tuple(courses)
    if objective not in {"combined", "maximum"}:
        raise ValueError("objective must be 'combined' or 'maximum'")
    _validate_matrix_contract(matrix, courses)

    ranked = []
    unranked = []
    for course, destination in zip(courses, matrix.destinations, strict=True):
        if isinstance(destination, DestinationFailure):
            unranked.append(UnrankedCourse(course, destination.reason))
            continue
        travel_times = canonical_milliseconds(destination.travel_times_seconds)
        ranked.append(
            {
                "course": course,
                "destination": destination,
                "travel_times": travel_times,
                "combined": sum(travel_times),
                "maximum": max(travel_times),
            }
        )

    primary = objective
    secondary = "maximum" if objective == "combined" else "combined"
    ranked.sort(
        key=lambda item: (
            item[primary],
            item[secondary],
            item["course"].name,
            item["course"].identifier,
        )
    )
    return CourseRanking(
        tuple(
            RankedCourse(
                course=item["course"],
                destination=item["destination"],
                travel_times_milliseconds=item["travel_times"],
                combined_milliseconds=item["combined"],
                maximum_milliseconds=item["maximum"],
                rank=rank,
            )
            for rank, item in enumerate(ranked, 1)
        ),
        tuple(unranked),
    )


def _validate_matrix_contract(matrix, courses):
    expected_ids = tuple(course.identifier for course in courses)
    expected_destinations = tuple(course.routing_coordinate for course in courses)
    if matrix.destination_ids != expected_ids:
        raise RuntimeError("matrix provider changed destination identity or order")
    if tuple(item.coordinate for item in matrix.destinations) != expected_destinations:
        raise RuntimeError("matrix provider changed destination coordinates or order")
