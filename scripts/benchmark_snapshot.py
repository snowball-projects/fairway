"""Measure one fairway road snapshot and course matrix."""

import json
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from sys import platform
from time import perf_counter

from modo import CompactRoadGraph

from fairway.course_index import CourseDistanceIndex
from fairway.courses import load_course_catalog
from fairway.matrix import StaticModoMatrix
from fairway.paths import COURSE_CATALOG_PATH


def coordinate(value):
    try:
        latitude, longitude = map(float, value.split(","))
    except ValueError as error:
        raise ValueError("origins must use latitude,longitude") from error
    return latitude, longitude


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


parser = ArgumentParser()
parser.add_argument("--courses", type=Path, default=COURSE_CATALOG_PATH)
parser.add_argument("--course-index", type=Path)
parser.add_argument("--iterations", type=int, default=1)
parser.add_argument("snapshot", type=Path)
parser.add_argument("origins", nargs="+", type=coordinate)
args = parser.parse_args()
if args.iterations < 1:
    parser.error("--iterations must be positive")

catalog = load_course_catalog(args.courses)
destinations = tuple(course.routing_coordinate for course in catalog.courses)
destination_ids = tuple(course.identifier for course in catalog.courses)
started = perf_counter()
road = CompactRoadGraph.load(args.snapshot)
loaded = perf_counter()
course_index = (
    CourseDistanceIndex.load(
        args.course_index,
        road_snapshot_sha256=digest(args.snapshot),
        course_catalog_sha256=catalog.sha256,
        vertex_count=len(road._vertices),
        expected_course_ids=(course.identifier for course in catalog.courses),
    )
    if args.course_index
    else None
)
index_loaded = perf_counter()
if course_index is not None:
    course_index.validate_against(road, road.nearest_vertices(destinations))
prepared = perf_counter()
provider = StaticModoMatrix(road, course_index=course_index)
for _iteration in range(args.iterations):
    result = provider.calculate(args.origins, destinations, destination_ids)
finished = perf_counter()
peak_rss = getrusage(RUSAGE_SELF).ru_maxrss
if platform != "darwin":
    peak_rss *= 1024

print(
    json.dumps(
        {
            "snapshot_bytes": args.snapshot.stat().st_size,
            "origins": len(args.origins),
            "courses": len(result.destinations),
            "course_index_load_seconds": index_loaded - loaded,
            "course_index_validation_seconds": prepared - index_loaded,
            "iterations": args.iterations,
            "load_seconds": loaded - started,
            "matrix_seconds": finished - prepared,
            "matrix_seconds_per_iteration": (finished - prepared) / args.iterations,
            "peak_rss_bytes": peak_rss,
            "provider": (
                "precomputed-course-index" if course_index else "sequential-dijkstra"
            ),
        },
        sort_keys=True,
    )
)
