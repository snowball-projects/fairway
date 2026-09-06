"""Validate one published fairway road snapshot and its course catalog."""

import json
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path

from modo import CompactRoadGraph

from fairway.course_index import CourseDistanceIndex
from fairway.courses import load_course_catalog
from fairway.matrix import (
    MAX_SNAP_DISTANCE_KILOMETERS,
    DestinationFailure,
    StaticModoMatrix,
    validate_road_snapshot,
)
from fairway.paths import (
    COURSE_CATALOG_PATH,
    SNAPSHOT_CATALOG_PATH,
)
from fairway.paths import (
    graph_path as default_graph_path,
)
from fairway.scoring import canonical_milliseconds
from fairway.snapshots import load_catalog


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def ranking_order(courses, destinations, objective):
    other = "combined" if objective == "maximum" else "maximum"
    scores = []
    for course, destination in zip(courses, destinations, strict=True):
        if isinstance(destination, DestinationFailure):
            continue
        values = canonical_milliseconds(destination.travel_times_seconds)
        score = {"combined": sum(values), "maximum": max(values)}
        scores.append((score[objective], score[other], course.name, course.identifier))
    return tuple(item[3] for item in sorted(scores))


def compare_results(courses, fallback, indexed):
    pairs = tuple(zip(fallback.destinations, indexed.destinations, strict=True))
    if any(
        isinstance(first, DestinationFailure) != isinstance(second, DestinationFailure)
        for first, second in pairs
    ):
        raise ValueError("course index reachability differs from fallback")
    if any(
        canonical_milliseconds(first.travel_times_seconds)
        != canonical_milliseconds(second.travel_times_seconds)
        for first, second in pairs
        if not isinstance(first, DestinationFailure)
    ):
        raise ValueError("course index changes a canonical millisecond travel time")
    differences = [
        abs(first_time - second_time)
        for first, second in pairs
        if not isinstance(first, DestinationFailure)
        for first_time, second_time in zip(
            first.travel_times_seconds,
            second.travel_times_seconds,
            strict=True,
        )
    ]
    for objective in ("combined", "maximum"):
        if ranking_order(courses, fallback.destinations, objective) != ranking_order(
            courses, indexed.destinations, objective
        ):
            raise ValueError("course index changes a ranking")
    return max(differences, default=0.0)


def validate(
    snapshot_id,
    catalog_path,
    course_catalog_path,
    graph_path=None,
    course_index_path=None,
):
    snapshots = load_catalog(catalog_path)
    try:
        snapshot = next(item for item in snapshots if item.identifier == snapshot_id)
    except StopIteration as error:
        raise ValueError(f"unknown road snapshot: {snapshot_id}") from error
    graph_path = Path(graph_path or default_graph_path(snapshot.file, catalog_path))
    if digest(graph_path) != snapshot.sha256:
        raise ValueError("road snapshot checksum does not match its catalog")
    road = CompactRoadGraph.load(graph_path)
    validate_road_snapshot(road)
    actual_graph_bounds = (
        float(road._coordinates[:, 0].min()),
        float(road._coordinates[:, 1].min()),
        float(road._coordinates[:, 0].max()),
        float(road._coordinates[:, 1].max()),
    )
    if any(
        abs(actual - documented) > 1e-7
        for actual, documented in zip(
            actual_graph_bounds, snapshot.graph_bounds, strict=True
        )
    ):
        raise ValueError("road snapshot bounds do not match its catalog")
    course_catalog = load_course_catalog(course_catalog_path)
    courses = course_catalog.courses
    coordinates = tuple(course.routing_coordinate for course in courses)
    if not snapshot.contains(coordinates):
        raise ValueError("course catalog exceeds the snapshot core")
    south, west, north, east = snapshot.core_bounds
    graph_south, graph_west, graph_north, graph_east = snapshot.graph_bounds
    if not (
        graph_south < south
        and graph_west < west
        and graph_north > north
        and graph_east > east
    ):
        raise ValueError("snapshot core must have a road-graph halo on every side")
    result = StaticModoMatrix(
        road, max_snap_distance_kilometers=MAX_SNAP_DISTANCE_KILOMETERS
    ).calculate(
        coordinates,
        coordinates,
        (course.identifier for course in courses),
    )
    failures = [
        item.reason
        for item in result.destinations
        if isinstance(item, DestinationFailure)
    ]
    if failures:
        raise ValueError(f"course matrix smoke test failed: {', '.join(failures)}")
    summary = {
        "snapshot": snapshot.identifier,
        "vertices": len(road._vertices),
        "edges": road._matrix.nnz,
        "courses": len(courses),
        "maximum_course_snap_kilometers": max(
            item.snap_distance_kilometers for item in result.destinations
        ),
    }
    if course_index_path is not None:
        course_index = CourseDistanceIndex.load(
            course_index_path,
            road_snapshot_sha256=snapshot.sha256,
            course_catalog_sha256=course_catalog.sha256,
            vertex_count=len(road._vertices),
            expected_course_ids=(course.identifier for course in courses),
        )
        course_vertices = road.nearest_vertices(coordinates)
        course_index.validate_against(road, course_vertices)
        indexed = StaticModoMatrix(
            road,
            max_snap_distance_kilometers=MAX_SNAP_DISTANCE_KILOMETERS,
            course_index=course_index,
        ).calculate(
            coordinates,
            coordinates,
            (course.identifier for course in courses),
        )
        maximum_difference = compare_results(courses, result, indexed)
        if maximum_difference > 1e-9:
            raise ValueError("course index differs from float64 fallback")
        summary["course_index_max_abs_difference_seconds"] = maximum_difference
        summary["course_index_exhaustive_cells"] = course_index.distances.size
    return summary


def main():
    parser = ArgumentParser()
    parser.add_argument("--snapshot", default="chicago-static-v1")
    parser.add_argument("--catalog", type=Path, default=SNAPSHOT_CATALOG_PATH)
    parser.add_argument("--courses", type=Path, default=COURSE_CATALOG_PATH)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--course-index", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            validate(
                args.snapshot,
                args.catalog,
                args.courses,
                graph_path=args.graph,
                course_index_path=args.course_index,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
