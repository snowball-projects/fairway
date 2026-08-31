"""Small WSGI application for fairway."""

import json
import logging
import mimetypes
import os
from hashlib import sha256
from importlib.metadata import version
from math import isfinite
from pathlib import Path

import networkx as nx
from modo import CompactRoadGraph

from .courses import load_course_catalog
from .matrix import OutsideRoadCoverage, StaticModoMatrix
from .snapshots import load_catalog

STATIC = Path(__file__).with_name("static")
ROAD_CATALOG_PATH = Path(os.environ.get("FAIRWAY_CATALOG", "data/snapshots.json"))
ROAD_CATALOG = load_catalog(ROAD_CATALOG_PATH)
SNAPSHOT = os.environ.get("FAIRWAY_SNAPSHOT", "chicago-static-v1")
try:
    SNAPSHOT_METADATA = next(
        item for item in ROAD_CATALOG if item.identifier == SNAPSHOT
    )
except StopIteration as error:
    raise RuntimeError(f"unknown configured road snapshot: {SNAPSHOT}") from error
COST_PROFILE = SNAPSHOT_METADATA.cost_profile
GRAPH_PATH = os.environ.get(
    "FAIRWAY_GRAPH", str(ROAD_CATALOG_PATH.parent / SNAPSHOT_METADATA.file)
)
COURSE_CATALOG_PATH = Path(
    os.environ.get("FAIRWAY_COURSE_CATALOG", "data/course-catalog-v1.json")
)
COURSE_CATALOG = load_course_catalog(COURSE_CATALOG_PATH)
COURSES = COURSE_CATALOG.courses
if any(
    not SNAPSHOT_METADATA.contains([course.routing_coordinate]) for course in COURSES
):
    raise RuntimeError("configured course catalog exceeds the road snapshot core")

MAX_REQUEST_BYTES = 32_768
MAX_ORIGINS = 8
MAX_SNAP_DISTANCE_KILOMETERS = 5
LOGGER = logging.getLogger(__name__)
_graph = None
_graph_sha256 = None


class _UnprocessableRequest(Exception):
    """A valid request that the current road snapshot cannot calculate."""


class _BadRequest(Exception):
    """A request whose JSON or input values are invalid."""


class _PayloadTooLarge(Exception):
    """A request body that exceeds the hosted-service byte limit."""


def _road():
    global _graph, _graph_sha256
    if _graph is None:
        digest = sha256()
        with Path(GRAPH_PATH).open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        _graph_sha256 = digest.hexdigest()
        if _graph_sha256 != SNAPSHOT_METADATA.sha256:
            _graph_sha256 = None
            raise RuntimeError("road snapshot checksum does not match")
        _graph = CompactRoadGraph.load(GRAPH_PATH)
    return _graph


def _json(start_response, status, value):
    body = json.dumps(value, separators=(",", ":")).encode()
    start_response(
        status,
        [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def _body(environ):
    declared_length = environ.get("CONTENT_LENGTH")
    if declared_length in (None, ""):
        body = environ["wsgi.input"].read(MAX_REQUEST_BYTES + 1)
    else:
        try:
            length = int(declared_length)
        except (TypeError, ValueError) as error:
            raise _BadRequest("invalid content length") from error
        if length < 0:
            raise _BadRequest("invalid content length")
        if length > MAX_REQUEST_BYTES:
            raise _PayloadTooLarge("request is too large")
        body = environ["wsgi.input"].read(length)
        if len(body) != length:
            raise _BadRequest("request body is shorter than content length")
    if len(body) > MAX_REQUEST_BYTES:
        raise _PayloadTooLarge("request is too large")
    try:
        request = json.loads(body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise _BadRequest("request body must be valid UTF-8 JSON") from error
    if not isinstance(request, dict):
        raise _BadRequest("JSON body must be an object")
    return request


def _coordinates(value):
    if not isinstance(value, list):
        raise _BadRequest("origins must be a list")
    if any(not isinstance(point, (list, tuple)) or len(point) != 2 for point in value):
        raise _BadRequest("origins must contain latitude, longitude pairs")
    try:
        points = tuple(
            (float(latitude), float(longitude)) for latitude, longitude in value
        )
    except (OverflowError, TypeError, ValueError) as error:
        raise _BadRequest("origins must contain latitude, longitude pairs") from error
    if any(
        not isfinite(latitude)
        or not isfinite(longitude)
        or abs(latitude) > 90
        or abs(longitude) > 180
        for latitude, longitude in points
    ):
        raise _BadRequest("origin coordinates are out of range")
    return points


def _objective(value):
    if value not in {"combined", "maximum"}:
        raise _BadRequest("objective must be 'combined' or 'maximum'")
    return value


def _holes(value):
    if not isinstance(value, list) or not value:
        raise _BadRequest("holes must be a nonempty list containing 9 or 18")
    if any(type(item) is not int or item not in {9, 18} for item in value):
        raise _BadRequest("holes must be a nonempty list containing 9 or 18")
    return frozenset(value)


def _course(course):
    return {
        "id": course.identifier,
        "name": course.name,
        "address": course.address,
        "coordinate": list(course.routing_coordinate),
        "holes": course.holes,
        "access": course.access,
        "website": course.website,
        "facts_source": COURSE_CATALOG.sources[course.facts_source],
        "routing_source": (f"https://www.openstreetmap.org/{course.routing_reference}"),
    }


def _config(start_response):
    return _json(
        start_response,
        "200 OK",
        {
            "snapshot": SNAPSHOT,
            "cost_profile": COST_PROFILE,
            "core_bounds": list(SNAPSHOT_METADATA.core_bounds),
            "graph_bounds": list(SNAPSHOT_METADATA.graph_bounds),
            "max_origins": MAX_ORIGINS,
            "course_catalog": {
                "id": COURSE_CATALOG.identifier,
                "title": COURSE_CATALOG.title,
                "as_of": COURSE_CATALOG.as_of,
                "description": COURSE_CATALOG.description,
                "sha256": COURSE_CATALOG.sha256,
                "sources": [
                    {"id": identifier, "url": url}
                    for identifier, url in COURSE_CATALOG.sources.items()
                ],
            },
            "courses": [_course(course) for course in COURSES],
        },
    )


def _rankings(environ, start_response):
    request = _body(environ)
    origins = _coordinates(request.get("origins", []))
    if not 2 <= len(origins) <= MAX_ORIGINS:
        raise _BadRequest(f"provide between 2 and {MAX_ORIGINS} origins")
    if not SNAPSHOT_METADATA.contains(origins):
        raise _UnprocessableRequest(
            "An origin is outside fairway's current road coverage."
        )
    objective = _objective(request.get("objective", "maximum"))
    holes = _holes(request.get("holes", [9, 18]))
    candidates = tuple(course for course in COURSES if course.holes in holes)
    try:
        road = _road()
        if _graph_sha256 is None:
            raise RuntimeError("road snapshot was not checksum-verified")
        matrix = StaticModoMatrix(road, MAX_SNAP_DISTANCE_KILOMETERS).calculate(
            origins, (course.routing_coordinate for course in candidates)
        )
    except OutsideRoadCoverage as error:
        raise _UnprocessableRequest(
            "An origin is too far from a road in fairway's current snapshot."
        ) from error
    except nx.NetworkXNoPath as error:
        raise _UnprocessableRequest(
            "These origins and courses have no mutually reachable road route."
        ) from error

    ranked = []
    for course, destination in zip(candidates, matrix.destinations, strict=True):
        travel_times = tuple(map(float, destination.travel_times_seconds))
        item = _course(course)
        item.update(
            {
                "road_coordinate": list(destination.road_coordinate),
                "travel_times_seconds": list(travel_times),
                "combined_seconds": sum(travel_times),
                "maximum_seconds": max(travel_times),
            }
        )
        ranked.append(item)
    primary = "combined_seconds" if objective == "combined" else "maximum_seconds"
    secondary = "maximum_seconds" if objective == "combined" else "combined_seconds"
    ranked.sort(key=lambda item: (item[primary], item[secondary], item["name"]))
    for rank, item in enumerate(ranked, 1):
        item["rank"] = rank
    return _json(
        start_response,
        "200 OK",
        {
            "objective": objective,
            "holes": sorted(holes),
            "origin_road_coordinates": [
                list(coordinate) for coordinate in matrix.origin_road_coordinates
            ],
            "courses": ranked,
            "provenance": {
                "course_catalog": COURSE_CATALOG.identifier,
                "course_catalog_as_of": COURSE_CATALOG.as_of,
                "course_catalog_sha256": COURSE_CATALOG.sha256,
                "road_snapshot": SNAPSHOT,
                "road_snapshot_sha256": _graph_sha256,
                "cost_profile": COST_PROFILE,
                "modo": version("modo"),
            },
        },
    )


def _static(start_response, path):
    name = "index.html" if path == "/" else path.removeprefix("/")
    file = STATIC / name
    if not file.is_file() or STATIC not in file.resolve().parents:
        return _json(start_response, "404 Not Found", {"error": "not found"})
    body = file.read_bytes()
    content_type = mimetypes.guess_type(file)[0] or "application/octet-stream"
    start_response(
        "200 OK", [("Content-Type", content_type), ("Content-Length", str(len(body)))]
    )
    return [body]


def application(environ, start_response):
    """Serve fairway and its same-origin ranking API."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    try:
        if path == "/health":
            _road()
            return _json(start_response, "200 OK", {"status": "ok"})
        if path == "/api/config" and method == "GET":
            return _config(start_response)
        if path == "/api/rankings" and method == "POST":
            return _rankings(environ, start_response)
        if method == "GET":
            return _static(start_response, path)
        return _json(
            start_response, "405 Method Not Allowed", {"error": "method not allowed"}
        )
    except _PayloadTooLarge as error:
        return _json(start_response, "413 Payload Too Large", {"error": str(error)})
    except _UnprocessableRequest as error:
        return _json(start_response, "422 Unprocessable Entity", {"error": str(error)})
    except _BadRequest as error:
        return _json(start_response, "400 Bad Request", {"error": str(error)})
    except Exception:
        LOGGER.exception("Unhandled fairway request failure: %s %s", method, path)
        return _json(
            start_response,
            "500 Internal Server Error",
            {"error": "fairway could not calculate this request"},
        )
