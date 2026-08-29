"""Small WSGI application for fairway."""

import json
import mimetypes
import os
import secrets
from collections import OrderedDict
from importlib.metadata import version
from pathlib import Path

from modo import CompactRoadGraph

STATIC = Path(__file__).with_name("static")
SNAPSHOT = os.environ.get("FAIRWAY_SNAPSHOT", "chicago-static-v1")
COST_PROFILE = "static-free-flow-seconds-v1"
MAX_ANALYSES = 8
_graph = None
_analyses = OrderedDict()


def _road():
    global _graph
    if _graph is None:
        _graph = CompactRoadGraph.load(os.environ.get(
            "FAIRWAY_GRAPH", "data/chicago-static-v1.npz"))
    return _graph


def _json(start_response, status, value):
    body = json.dumps(value, separators=(",", ":")).encode()
    start_response(status, [("Content-Type", "application/json"),
                            ("Content-Length", str(len(body))),
                            ("Cache-Control", "no-store")])
    return [body]


def _body(environ):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    if length > 32_768:
        raise ValueError("request is too large")
    return json.loads(environ["wsgi.input"].read(length) or b"{}")


def _result(road, result):
    return {
        "optimum": list(result.coordinate),
        "objective_seconds": result.objective_seconds,
        "travel_times_seconds": list(result.travel_times_seconds),
        "region": [list(point) for point in road.coordinates(result.region)],
    }


def _evaluate(environ, start_response):
    request = _body(environ)
    origins = request.get("origins", [])
    if not 2 <= len(origins) <= 32:
        raise ValueError("provide between 2 and 32 origins")
    tolerance = request.get("tolerance_seconds", 60)
    road = _road()
    analysis = road.analyze_coordinates(origins)
    identifier = secrets.token_urlsafe(12)
    _analyses[identifier] = analysis
    while len(_analyses) > MAX_ANALYSES:
        _analyses.popitem(last=False)
    return _json(start_response, "200 OK", {
        "id": identifier,
        "origins": [list(point) for point in road.coordinates(
            analysis.origin_vertices)],
        "total": _result(road, analysis.optimize("total", tolerance)),
        "maximum": _result(road, analysis.optimize("maximum", tolerance)),
        "provenance": {"snapshot": SNAPSHOT, "cost_profile": COST_PROFILE,
                       "modo": version("modo")},
    })


def _travel_times(environ, start_response, identifier):
    analysis = _analyses.get(identifier)
    if analysis is None:
        return _json(start_response, "404 Not Found", {
            "error": "This temporary analysis has expired. Change an origin to recalculate."})
    coordinate = _body(environ).get("coordinate")
    result = analysis.travel_times_at_coordinate(coordinate)
    return _json(start_response, "200 OK", {
        "coordinate": list(result.coordinate),
        "travel_times_seconds": list(result.travel_times_seconds),
    })


def _static(start_response, path):
    name = "index.html" if path == "/" else path.removeprefix("/")
    file = STATIC / name
    if not file.is_file() or STATIC not in file.resolve().parents:
        return _json(start_response, "404 Not Found", {"error": "not found"})
    body = file.read_bytes()
    content_type = mimetypes.guess_type(file)[0] or "application/octet-stream"
    start_response("200 OK", [("Content-Type", content_type),
                              ("Content-Length", str(len(body)))])
    return [body]


def application(environ, start_response):
    """Serve the dashboard and its same-origin API."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    try:
        if path == "/health":
            _road()
            return _json(start_response, "200 OK", {"status": "ok"})
        if path == "/api/evaluations" and method == "POST":
            return _evaluate(environ, start_response)
        suffix = "/travel-times"
        if path.startswith("/api/evaluations/") and path.endswith(suffix) and method == "POST":
            return _travel_times(environ, start_response,
                                 path[len("/api/evaluations/"):-len(suffix)])
        if method == "GET":
            return _static(start_response, path)
        return _json(start_response, "405 Method Not Allowed", {"error": "method not allowed"})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return _json(start_response, "400 Bad Request", {"error": str(error)})
    except Exception:  # noqa: BLE001 - the public WSGI boundary must fail clearly
        return _json(start_response, "500 Internal Server Error", {
            "error": "fairway could not calculate this request"})
