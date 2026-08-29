"""Small WSGI application for fairway."""

import json
import logging
import mimetypes
import os
import secrets
from collections import OrderedDict
from importlib.metadata import version
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path

import networkx as nx
from modo import CompactRoadGraph

from .snapshots import load_catalog

STATIC = Path(__file__).with_name("static")
CATALOG_PATH = Path(os.environ.get("FAIRWAY_CATALOG", "data/snapshots.json"))
CATALOG = load_catalog(CATALOG_PATH)
SNAPSHOT = os.environ.get("FAIRWAY_SNAPSHOT", "chicago-static-v1")
try:
    SNAPSHOT_METADATA = next(item for item in CATALOG if item.identifier == SNAPSHOT)
except StopIteration as error:
    raise RuntimeError(f"unknown configured road snapshot: {SNAPSHOT}") from error
COST_PROFILE = SNAPSHOT_METADATA.cost_profile
GRAPH_PATH = os.environ.get(
    "FAIRWAY_GRAPH", str(CATALOG_PATH.parent / SNAPSHOT_METADATA.file)
)
MAX_REQUEST_BYTES = 32_768
MAX_ORIGINS = 32
MAX_TOLERANCE_SECONDS = 300
MAX_REGION_POINTS = 5_000
MAX_SNAP_DISTANCE_KILOMETERS = 5
MAX_ANALYSES = 8
LOGGER = logging.getLogger(__name__)
_graph = None
_analyses = OrderedDict()


class _UnprocessableRequest(Exception):
    """A valid request that the current road snapshot cannot calculate."""


class _BadRequest(Exception):
    """A request whose JSON or input values are invalid."""


class _PayloadTooLarge(Exception):
    """A request body that exceeds the hosted-service byte limit."""


def _road():
    global _graph
    if _graph is None:
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
    if not isinstance(value, (list, tuple)):
        raise _BadRequest("coordinates must be a list of latitude, longitude pairs")
    if any(not isinstance(point, (list, tuple)) or len(point) != 2 for point in value):
        raise _BadRequest("coordinates must contain latitude, longitude pairs")
    try:
        points = tuple(
            (float(latitude), float(longitude)) for latitude, longitude in value
        )
    except (OverflowError, TypeError, ValueError) as error:
        raise _BadRequest(
            "coordinates must contain latitude, longitude pairs"
        ) from error
    if any(
        not isfinite(latitude)
        or not isfinite(longitude)
        or abs(latitude) > 90
        or abs(longitude) > 180
        for latitude, longitude in points
    ):
        raise _BadRequest("coordinates are out of range")
    return points


def _distance_kilometers(first, second):
    first_latitude, first_longitude = map(radians, first)
    second_latitude, second_longitude = map(radians, second)
    latitude_delta = second_latitude - first_latitude
    longitude_delta = second_longitude - first_longitude
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude) * cos(second_latitude) * sin(longitude_delta / 2) ** 2
    )
    return 12_742.0176 * asin(sqrt(min(1, haversine)))


def _snap_coordinates(road, coordinates):
    vertices = road.nearest_vertices(coordinates)
    snapped = road.coordinates(vertices)
    if any(
        _distance_kilometers(point, match) > MAX_SNAP_DISTANCE_KILOMETERS
        for point, match in zip(coordinates, snapped, strict=True)
    ):
        raise _UnprocessableRequest(
            "A coordinate is too far from a road in fairway's current snapshot."
        )
    return vertices, snapped


def _tolerance(value):
    try:
        tolerance = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise _BadRequest("tolerance_seconds must be a nonnegative number") from error
    if not isfinite(tolerance) or tolerance < 0:
        raise _BadRequest("tolerance_seconds must be a nonnegative number")
    if tolerance > MAX_TOLERANCE_SECONDS:
        raise _UnprocessableRequest(
            "Region tolerance cannot exceed 5 minutes on the hosted service."
        )
    return tolerance


def _result(road, result):
    return {
        "optimum": list(result.coordinate),
        "objective_seconds": result.objective_seconds,
        "travel_times_seconds": list(result.travel_times_seconds),
        "region": [
            {
                "coordinate": list(road.coordinate(vertex)),
                "excess_seconds": excess,
            }
            for vertex, excess in result.region_excess_seconds.items()
        ],
    }


def _evaluate(environ, start_response):
    request = _body(environ)
    origins = request.get("origins", [])
    if not isinstance(origins, list):
        raise _BadRequest("origins must be a list")
    origin_count = len(origins)
    if not 2 <= origin_count <= MAX_ORIGINS:
        raise _BadRequest(f"provide between 2 and {MAX_ORIGINS} origins")
    coordinates = _coordinates(origins)
    tolerance = _tolerance(request.get("tolerance_seconds", 60))
    road = _road()
    origin_vertices, snapped_origins = _snap_coordinates(road, coordinates)
    try:
        analysis = road.analyze_vertices(origin_vertices)
    except nx.NetworkXNoPath as error:
        raise _UnprocessableRequest(
            "These origins have no mutually reachable road location."
        ) from error
    total = analysis.optimize("total", tolerance)
    maximum = analysis.optimize("maximum", tolerance)
    region_points = len(total.region_excess_seconds) + len(
        maximum.region_excess_seconds
    )
    if region_points > MAX_REGION_POINTS:
        raise _UnprocessableRequest(
            "This tolerance produces too many region points. Use a smaller tolerance."
        )
    identifier = secrets.token_urlsafe(12)
    response = _json(
        start_response,
        "200 OK",
        {
            "id": identifier,
            "origins": [list(point) for point in snapped_origins],
            "total": _result(road, total),
            "maximum": _result(road, maximum),
            "provenance": {
                "snapshot": SNAPSHOT,
                "snapshot_sha256": SNAPSHOT_METADATA.sha256,
                "cost_profile": COST_PROFILE,
                "core_bounds": list(SNAPSHOT_METADATA.core_bounds),
                "graph_bounds": list(SNAPSHOT_METADATA.graph_bounds),
                "modo": version("modo"),
            },
        },
    )
    _analyses[identifier] = analysis
    while len(_analyses) > MAX_ANALYSES:
        _analyses.popitem(last=False)
    return response


def _travel_times(environ, start_response, identifier):
    analysis = _analyses.get(identifier)
    if analysis is None:
        return _json(
            start_response,
            "404 Not Found",
            {
                "error": "This temporary analysis has expired. Change an origin to recalculate."
            },
        )
    coordinate = _coordinates([_body(environ).get("coordinate")])
    vertices, _snapped = _snap_coordinates(_road(), coordinate)
    try:
        result = analysis.travel_times(vertices[0])
    except nx.NetworkXNoPath as error:
        raise _UnprocessableRequest(
            "That point is not reachable from every origin."
        ) from error
    return _json(
        start_response,
        "200 OK",
        {
            "coordinate": list(result.coordinate),
            "travel_times_seconds": list(result.travel_times_seconds),
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
    """Serve the dashboard and its same-origin API."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    try:
        if path == "/health":
            _road()
            return _json(start_response, "200 OK", {"status": "ok"})
        if path == "/api/config" and method == "GET":
            return _json(
                start_response,
                "200 OK",
                {
                    "snapshot": SNAPSHOT,
                    "cost_profile": COST_PROFILE,
                    "core_bounds": list(SNAPSHOT_METADATA.core_bounds),
                    "graph_bounds": list(SNAPSHOT_METADATA.graph_bounds),
                },
            )
        if path == "/api/evaluations" and method == "POST":
            return _evaluate(environ, start_response)
        suffix = "/travel-times"
        if (
            path.startswith("/api/evaluations/")
            and path.endswith(suffix)
            and method == "POST"
        ):
            return _travel_times(
                environ, start_response, path[len("/api/evaluations/") : -len(suffix)]
            )
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
