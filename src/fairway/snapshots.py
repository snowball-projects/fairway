"""Immutable road snapshot catalog."""

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from re import fullmatch
from urllib.parse import urlparse


@dataclass(frozen=True)
class Snapshot:
    identifier: str
    file: str
    url: str
    sha256: str
    cost_profile: str
    core_bounds: tuple[float, float, float, float]
    graph_bounds: tuple[float, float, float, float]

    def contains(self, coordinates):
        """Return whether every latitude, longitude pair is in the supported core."""
        south, west, north, east = self.core_bounds
        return all(
            south <= latitude <= north and west <= longitude <= east
            for latitude, longitude in coordinates
        )


def load_catalog(path):
    """Load and validate a versioned snapshot catalog."""
    try:
        value = json.loads(Path(path).read_text())
        if value["schema_version"] != 1 or not isinstance(value["snapshots"], list):
            raise ValueError
        snapshots = tuple(_snapshot(item) for item in value["snapshots"])
    except (
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError("invalid road snapshot catalog") from error
    if not snapshots or len({item.identifier for item in snapshots}) != len(snapshots):
        raise ValueError("invalid road snapshot catalog")
    return snapshots


def select_snapshot(snapshots, coordinates):
    """Select the smallest supported core containing every coordinate."""
    matches = [item for item in snapshots if item.contains(coordinates)]
    if not matches:
        return None
    return min(matches, key=lambda item: (_area(item.core_bounds), item.identifier))


def _snapshot(value):
    bounds = _bounds(value["core_bounds"])
    graph_bounds = _bounds(value["graph_bounds"])
    if (
        not isinstance(value["id"], str)
        or not value["id"]
        or not isinstance(value["file"], str)
        or not value["file"]
        or not isinstance(value["cost_profile"], str)
        or not value["cost_profile"]
        or bounds[0] > bounds[2]
        or bounds[1] > bounds[3]
        or graph_bounds[0] > bounds[0]
        or graph_bounds[1] > bounds[1]
        or graph_bounds[2] < bounds[2]
        or graph_bounds[3] < bounds[3]
        or Path(value["file"]).name != value["file"]
        or not is_https_url(value["url"])
        or not isinstance(value["sha256"], str)
        or fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
    ):
        raise ValueError
    return Snapshot(
        value["id"],
        value["file"],
        value["url"],
        value["sha256"],
        value["cost_profile"],
        bounds,
        graph_bounds,
    )


def _area(bounds):
    south, west, north, east = bounds
    return (north - south) * (east - west)


def _bounds(value):
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(type(item) not in {int, float} for item in value)
    ):
        raise ValueError
    bounds = tuple(map(float, value))
    if (
        not all(map(isfinite, bounds))
        or not -90 <= bounds[0] <= 90
        or not -180 <= bounds[1] <= 180
        or not -90 <= bounds[2] <= 90
        or not -180 <= bounds[3] <= 180
    ):
        raise ValueError
    return bounds


def is_https_url(value):
    """Return whether a URL uses HTTPS without credentials or control characters."""
    if not isinstance(value, str) or any(
        character.isspace() or ord(character) == 127 for character in value
    ):
        return False
    try:
        parsed = urlparse(value)
        _port = parsed.port  # Validate a declared port before accepting the URL.
        return (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False
