"""Build exact reverse shortest-path rows for a fixed fairway course catalog."""

import json
import platform
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import scipy
from modo import CompactRoadGraph
from modo import __version__ as modo_version
from scipy.sparse.csgraph import dijkstra

from fairway.course_index import CourseDistanceIndex
from fairway.courses import load_course_catalog
from fairway.matrix import (
    MAX_SNAP_DISTANCE_KILOMETERS,
    distance_kilometers,
    validate_road_snapshot,
)
from fairway.paths import (
    COURSE_CATALOG_PATH,
    SNAPSHOT_CATALOG_PATH,
)
from fairway.paths import (
    graph_path as default_graph_path,
)
from fairway.snapshots import load_catalog


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def build_course_index(
    destination,
    *,
    snapshot_id,
    snapshot_catalog,
    course_catalog,
    graph_path=None,
):
    destination = Path(destination)
    snapshot_catalog = Path(snapshot_catalog)
    course_catalog = Path(course_catalog)
    snapshots = load_catalog(snapshot_catalog)
    try:
        snapshot = next(item for item in snapshots if item.identifier == snapshot_id)
    except StopIteration as error:
        raise ValueError(f"unknown road snapshot: {snapshot_id}") from error
    graph_path = Path(graph_path or default_graph_path(snapshot.file, snapshot_catalog))
    if (
        len(
            {
                destination.resolve(),
                snapshot_catalog.resolve(),
                course_catalog.resolve(),
                graph_path.resolve(),
            }
        )
        != 4
    ):
        raise ValueError(
            "destination, graph, snapshot catalog, and course catalog must differ"
        )
    if digest(graph_path) != snapshot.sha256:
        raise ValueError("road snapshot checksum does not match its catalog")
    catalog = load_course_catalog(course_catalog)
    coordinates = tuple(course.routing_coordinate for course in catalog.courses)
    if not snapshot.contains(coordinates):
        raise ValueError("course catalog exceeds the road snapshot core")

    road = CompactRoadGraph.load(graph_path)
    validate_road_snapshot(road)
    course_vertices = road.nearest_vertices(coordinates)
    course_road_coordinates = road.coordinates(course_vertices)
    if any(
        distance_kilometers(course, road_point) > MAX_SNAP_DISTANCE_KILOMETERS
        for course, road_point in zip(coordinates, course_road_coordinates, strict=True)
    ):
        raise ValueError(
            "course catalog contains a point over "
            f"{MAX_SNAP_DISTANCE_KILOMETERS:g} km from a road"
        )
    course_indices = [road._indices[vertex] for vertex in course_vertices]
    distances = np.atleast_2d(
        dijkstra(
            road._matrix.T,
            directed=True,
            indices=course_indices,
        )
    ).astype(np.float64, copy=False)

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not destination.is_file():
        raise ValueError("destination must be a file")
    temporary = None
    try:
        with NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as output:
            temporary = Path(output.name)
        CourseDistanceIndex.save(
            temporary,
            road_snapshot_sha256=snapshot.sha256,
            course_catalog_sha256=catalog.sha256,
            course_ids=(course.identifier for course in catalog.courses),
            distances=distances,
        )
        result = {
            "file": destination.name,
            "sha256": digest(temporary),
            "bytes": temporary.stat().st_size,
            "snapshot": snapshot.identifier,
            "snapshot_sha256": snapshot.sha256,
            "course_catalog": catalog.identifier,
            "course_catalog_sha256": catalog.sha256,
            "courses": len(catalog.courses),
            "vertices": distances.shape[1],
            "dtype": str(distances.dtype),
            "tool_versions": {
                "python": platform.python_version(),
                "modo": modo_version,
                "numpy": np.__version__,
                "scipy": scipy.__version__,
            },
        }
        if digest(graph_path) != snapshot.sha256:
            raise RuntimeError("road snapshot changed while the index was being built")
        temporary.replace(destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


def main():
    parser = ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--snapshot", default="chicago-static-v1")
    parser.add_argument("--snapshot-catalog", type=Path, default=SNAPSHOT_CATALOG_PATH)
    parser.add_argument("--course-catalog", type=Path, default=COURSE_CATALOG_PATH)
    parser.add_argument("--graph", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            build_course_index(
                args.destination,
                snapshot_id=args.snapshot,
                snapshot_catalog=args.snapshot_catalog,
                course_catalog=args.course_catalog,
                graph_path=args.graph,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
