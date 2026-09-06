"""Exact precomputed origin-to-course distances for one immutable data pair."""

import json
from dataclasses import dataclass
from re import fullmatch

import numpy as np
from scipy.sparse.csgraph import dijkstra

_FORMAT_VERSION = 1


def _encoded(value):
    return np.frombuffer(value.encode(), dtype=np.uint8)


def _decoded(value, label):
    try:
        return value.tobytes().decode()
    except (AttributeError, UnicodeDecodeError) as error:
        raise ValueError(f"invalid course index {label}") from error


@dataclass(frozen=True)
class CourseDistanceIndex:
    """Exact distance rows bound to one road snapshot and course catalog."""

    road_snapshot_sha256: str
    course_catalog_sha256: str
    course_ids: tuple[str, ...]
    distances: np.ndarray

    @classmethod
    def load(
        cls,
        path,
        *,
        road_snapshot_sha256,
        course_catalog_sha256,
        vertex_count,
        expected_course_ids=None,
    ):
        """Load an index without permitting Python-object deserialization."""
        try:
            with np.load(path, allow_pickle=False) as archive:
                format_version = int(archive["format_version"])
                stored_road_sha256 = _decoded(
                    archive["road_snapshot_sha256"], "road snapshot checksum"
                )
                stored_catalog_sha256 = _decoded(
                    archive["course_catalog_sha256"], "course catalog checksum"
                )
                course_ids = tuple(
                    json.loads(_decoded(archive["course_ids"], "course identifiers"))
                )
                raw_distances = archive["distances"]
                if raw_distances.dtype != np.float64:
                    raise ValueError("course index distances must use float64")
                distances = np.array(raw_distances, dtype=np.float64)
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise ValueError("invalid course distance index") from error
        if format_version != _FORMAT_VERSION:
            raise ValueError("unsupported course distance index format")
        if (
            stored_road_sha256 != road_snapshot_sha256
            or stored_catalog_sha256 != course_catalog_sha256
            or (
                expected_course_ids is not None
                and course_ids != tuple(expected_course_ids)
            )
        ):
            raise ValueError("course distance index does not match active data")
        if (
            not course_ids
            or len(course_ids) != len(set(course_ids))
            or any(
                not isinstance(identifier, str)
                or fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", identifier) is None
                for identifier in course_ids
            )
            or distances.shape != (len(course_ids), vertex_count)
            or np.any(np.isnan(distances))
            or np.any(distances < 0)
        ):
            raise ValueError("invalid course distance index")
        distances.setflags(write=False)
        return cls(
            stored_road_sha256,
            stored_catalog_sha256,
            course_ids,
            distances,
        )

    def lookup(self, course_ids, origin_vertices, road):
        """Return per-origin travel times in requested course order."""
        rows = {identifier: index for index, identifier in enumerate(self.course_ids)}
        try:
            origin_indices = tuple(road._indices[vertex] for vertex in origin_vertices)
            course_rows = tuple(rows[identifier] for identifier in course_ids)
        except (AttributeError, KeyError) as error:
            raise ValueError(
                "course distance index cannot serve these inputs"
            ) from error
        return tuple(
            tuple(float(value) for value in self.distances[row, origin_indices])
            for row in course_rows
        )

    def validate_against(self, road, course_vertices):
        """Require bit-exact reverse rows for the active graph and courses."""
        try:
            indices = tuple(road._indices[vertex] for vertex in course_vertices)
            expected = np.atleast_2d(
                dijkstra(road._matrix.T, directed=True, indices=indices)
            ).astype(np.float64, copy=False)
        except (AttributeError, KeyError) as error:
            raise ValueError(
                "course distance index cannot validate against active data"
            ) from error
        if not np.array_equal(self.distances, expected):
            raise ValueError("course distance index values do not match active routing")
        return self

    @classmethod
    def save(
        cls,
        path,
        *,
        road_snapshot_sha256,
        course_catalog_sha256,
        course_ids,
        distances,
    ):
        """Write one compressed, exact float64 index."""
        course_ids = tuple(course_ids)
        distances = np.asarray(distances)
        if distances.dtype != np.float64:
            raise ValueError("course index distances must use float64")
        if (
            not course_ids
            or len(course_ids) != len(set(course_ids))
            or distances.ndim != 2
            or distances.shape[0] != len(course_ids)
            or np.any(np.isnan(distances))
            or np.any(distances < 0)
            or any(
                not isinstance(value, str) or fullmatch(r"[0-9a-f]{64}", value) is None
                for value in (road_snapshot_sha256, course_catalog_sha256)
            )
        ):
            raise ValueError("invalid course distance index data")
        with open(path, "wb") as output:
            np.savez_compressed(
                output,
                format_version=np.array(_FORMAT_VERSION, dtype=np.uint8),
                road_snapshot_sha256=_encoded(road_snapshot_sha256),
                course_catalog_sha256=_encoded(course_catalog_sha256),
                course_ids=_encoded(json.dumps(course_ids, separators=(",", ":"))),
                distances=distances,
            )
