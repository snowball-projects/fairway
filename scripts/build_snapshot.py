"""Compile and document one strictly validated static road snapshot."""

import json
import sys
from argparse import ArgumentParser
from datetime import date
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

import networkx as nx
import numpy as np
import scipy
from modo import CompactRoadGraph
from modo import __version__ as modo_version

from fairway.snapshots import is_https_url


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def _temporary(parent, name):
    with NamedTemporaryFile(dir=parent, prefix=f".{name}.", delete=False) as output:
        return Path(output.name)


def _write_metadata(path, build_record):
    path.write_text(
        json.dumps(build_record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _publish_pair(staged_artifact, artifact, staged_metadata, metadata):
    pairs = ((staged_artifact, artifact), (staged_metadata, metadata))
    backups = {}
    published = []
    try:
        for _staged, target in pairs:
            if target.exists():
                backup = _temporary(target.parent, target.name)
                backup.unlink()
                target.replace(backup)
                backups[target] = backup
        for staged, target in pairs:
            staged.replace(target)
            published.append(target)
    except Exception:
        for target in published:
            target.unlink(missing_ok=True)
        for target, backup in backups.items():
            backup.replace(target)
        raise
    else:
        for backup in backups.values():
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                pass


def validate_graph(graph):
    """Require the exact graph semantics fairway publishes."""
    if not graph.is_directed() or graph.number_of_nodes() == 0:
        raise ValueError("source must be a nonempty directed graph")
    if graph.number_of_edges() == 0:
        raise ValueError("source must contain directed road edges")
    for _start, _end, data in graph.edges(data=True):
        if "travel_time" not in data or isinstance(data["travel_time"], bool):
            raise ValueError("every source edge must declare travel_time")
        try:
            travel_time = float(data["travel_time"])
        except (OverflowError, TypeError, ValueError) as error:
            raise ValueError(
                "every source edge travel_time must be a finite positive number"
            ) from error
        if not isfinite(travel_time) or travel_time <= 0:
            raise ValueError(
                "every source edge travel_time must be a finite positive number"
            )


def package_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def graph_bounds(graph):
    coordinates = []
    for _vertex, attributes in graph.nodes(data=True):
        try:
            latitude = float(attributes["y"])
            longitude = float(attributes["x"])
        except (KeyError, OverflowError, TypeError, ValueError) as error:
            raise ValueError(
                "every source vertex must declare numeric x and y coordinates"
            ) from error
        if (
            not isfinite(latitude)
            or not isfinite(longitude)
            or abs(latitude) > 90
            or abs(longitude) > 180
        ):
            raise ValueError("source vertex coordinates are out of range")
        coordinates.append((latitude, longitude))
    latitudes, longitudes = zip(*coordinates, strict=True)
    return [min(latitudes), min(longitudes), max(latitudes), max(longitudes)]


def build_snapshot(
    source,
    destination,
    *,
    source_url,
    source_date,
    extraction,
    road_filter,
    generator,
    cost_profile,
    metadata=None,
):
    source = Path(source)
    destination = Path(destination)
    metadata_path = (
        Path(metadata)
        if metadata is not None
        else destination.with_name(f"{destination.name}.build.json")
    )
    if len({source.resolve(), destination.resolve(), metadata_path.resolve()}) != 3:
        raise ValueError("source, destination, and metadata must be different files")
    if not is_https_url(source_url):
        raise ValueError("source URL must be HTTPS without credentials")
    try:
        date.fromisoformat(source_date)
    except ValueError as error:
        raise ValueError("source date must use YYYY-MM-DD") from error
    for label, value in (
        ("extraction", extraction),
        ("road filter", road_filter),
        ("generator", generator),
        ("cost profile", cost_profile),
    ):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"{label} must be nonempty and trimmed")

    source_sha256 = digest(source)
    graph = nx.read_graphml(source)
    validate_graph(graph)
    bounds = graph_bounds(graph)
    compact = CompactRoadGraph.from_networkx(graph, weight="travel_time")
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    if any(
        path.exists() and not path.is_file() for path in (destination, metadata_path)
    ):
        raise ValueError("destination and metadata must be files")
    staged_artifact = None
    staged_metadata = None
    try:
        staged_artifact = _temporary(destination.parent, destination.name)
        staged_metadata = _temporary(metadata_path.parent, metadata_path.name)
        compact.save(staged_artifact)
        build_record = {
            "schema_version": 1,
            "artifact": {
                "file": destination.name,
                "sha256": digest(staged_artifact),
                "bytes": staged_artifact.stat().st_size,
            },
            "cost_profile": cost_profile,
            "graph": {
                "directed": True,
                "vertices": graph.number_of_nodes(),
                "source_edges": graph.number_of_edges(),
                "stored_edges": compact._matrix.nnz,
                "bounds": bounds,
                "minimum_travel_time_seconds": float(compact._matrix.data.min()),
                "maximum_travel_time_seconds": float(compact._matrix.data.max()),
            },
            "source": {
                "file": source.name,
                "sha256": source_sha256,
                "url": source_url,
                "as_of": source_date,
                "extraction": extraction,
                "road_filter": road_filter,
                "generator": generator,
            },
            "tool_versions": {
                "python": ".".join(map(str, sys.version_info[:3])),
                "networkx": package_version("networkx"),
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "modo": modo_version,
            },
        }
        _write_metadata(staged_metadata, build_record)
        if digest(source) != source_sha256:
            raise RuntimeError("source changed while the snapshot was being built")
        _publish_pair(
            staged_artifact,
            destination,
            staged_metadata,
            metadata_path,
        )
        return build_record
    finally:
        if staged_artifact is not None:
            staged_artifact.unlink(missing_ok=True)
        if staged_metadata is not None:
            staged_metadata.unlink(missing_ok=True)


def parser():
    result = ArgumentParser()
    result.add_argument("source", type=Path)
    result.add_argument("destination", type=Path)
    result.add_argument("--source-url", required=True)
    result.add_argument("--source-date", required=True)
    result.add_argument("--extraction", required=True)
    result.add_argument("--road-filter", required=True)
    result.add_argument("--generator", required=True)
    result.add_argument("--cost-profile", default="static-free-flow-seconds-v1")
    result.add_argument("--metadata", type=Path)
    return result


def main():
    args = parser().parse_args()
    build_snapshot(
        args.source,
        args.destination,
        source_url=args.source_url,
        source_date=args.source_date,
        extraction=args.extraction,
        road_filter=args.road_filter,
        generator=args.generator,
        cost_profile=args.cost_profile,
        metadata=args.metadata,
    )


if __name__ == "__main__":
    main()
