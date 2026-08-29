"""Measure one fairway road snapshot with a repeatable origin set."""

import json
from argparse import ArgumentParser
from pathlib import Path
from time import perf_counter

from modo import CompactRoadGraph


def coordinate(value):
    try:
        latitude, longitude = map(float, value.split(","))
    except ValueError as error:
        raise ValueError("origins must use latitude,longitude") from error
    return latitude, longitude


parser = ArgumentParser()
parser.add_argument("--memory-bounded", action="store_true")
parser.add_argument("snapshot", type=Path)
parser.add_argument("origins", nargs="+", type=coordinate)
args = parser.parse_args()

started = perf_counter()
road = CompactRoadGraph.load(args.snapshot)
loaded = perf_counter()
analysis = road.analyze_coordinates(
    args.origins, retain_distances=not args.memory_bounded
)
routed = perf_counter()
total = analysis.optimize("total", 60)
maximum = analysis.optimize("maximum", 60)
finished = perf_counter()

print(
    json.dumps(
        {
            "snapshot_bytes": args.snapshot.stat().st_size,
            "origins": len(args.origins),
            "memory_bounded": args.memory_bounded,
            "load_seconds": loaded - started,
            "snap_and_route_seconds": routed - loaded,
            "two_objectives_seconds": finished - routed,
            "total_region_vertices": len(total.region),
            "maximum_region_vertices": len(maximum.region),
        },
        sort_keys=True,
    )
)
