"""Measure one fairway road snapshot and course matrix."""

import json
from argparse import ArgumentParser
from pathlib import Path
from time import perf_counter

from modo import CompactRoadGraph

from fairway.courses import load_course_catalog
from fairway.matrix import StaticModoMatrix


def coordinate(value):
    try:
        latitude, longitude = map(float, value.split(","))
    except ValueError as error:
        raise ValueError("origins must use latitude,longitude") from error
    return latitude, longitude


parser = ArgumentParser()
parser.add_argument("--courses", type=Path, default=Path("data/course-catalog-v1.json"))
parser.add_argument("snapshot", type=Path)
parser.add_argument("origins", nargs="+", type=coordinate)
args = parser.parse_args()

catalog = load_course_catalog(args.courses)
started = perf_counter()
road = CompactRoadGraph.load(args.snapshot)
loaded = perf_counter()
result = StaticModoMatrix(road).calculate(
    args.origins, (course.routing_coordinate for course in catalog.courses)
)
finished = perf_counter()

print(
    json.dumps(
        {
            "snapshot_bytes": args.snapshot.stat().st_size,
            "origins": len(args.origins),
            "courses": len(result.destinations),
            "load_seconds": loaded - started,
            "matrix_seconds": finished - loaded,
        },
        sort_keys=True,
    )
)
