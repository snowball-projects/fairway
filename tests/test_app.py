import io
import json
import logging

import networkx as nx
import pytest
from modo import CompactRoadGraph

from fairway import app


def request(
    path="/", method="GET", payload=None, *, raw_body=None, content_length="auto"
):
    body = (
        raw_body
        if raw_body is not None
        else json.dumps(payload).encode()
        if payload is not None
        else b""
    )
    status = None

    def start_response(value, _headers):
        nonlocal status
        status = value

    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "wsgi.input": io.BytesIO(body),
    }
    if content_length == "auto":
        environ["CONTENT_LENGTH"] = str(len(body))
    elif content_length is not None:
        environ["CONTENT_LENGTH"] = str(content_length)
    result = b"".join(app.application(environ, start_response))
    return status, result


@pytest.fixture(autouse=True)
def clear_analyses():
    app._analyses.clear()
    yield
    app._analyses.clear()


def road_graph():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    graph.add_node("x", y=41.89, x=-87.78)
    graph.add_node("y", y=41.89, x=-87.77)
    graph.add_edge("a", "x", travel_time=1)
    graph.add_edge("b", "x", travel_time=9)
    graph.add_edge("a", "y", travel_time=5)
    graph.add_edge("b", "y", travel_time=6)
    return CompactRoadGraph.from_networkx(graph)


def test_serves_dashboard():
    status, body = request()
    assert status == "200 OK"
    assert b"fairway" in body
    assert b'href="/leaflet.css"' in body
    assert b"Minimize total driving time" in body
    assert b"Minimize longest driving time" in body
    assert b"Service policy" in body
    assert b"Built by AI agents" in body
    assert b"Maintained by" not in body
    assert b'id="results"' not in body
    assert b'id="point-form"' not in body
    assert b'id="point-result"' not in body
    assert b'max="5"' in body
    assert b"Fairway" not in body
    assert b"Founder-directed" not in body
    assert b"Built entirely" not in body
    assert b"Written by AI agents" not in body
    assert (
        b'href="https://snowball-projects.github.io/licensing/#how-snowball-is-built"'
        in body
    )

    status, body = request("/leaflet.css")
    assert status == "200 OK"
    assert b".leaflet-tile" in body

    status, body = request("/app.js")
    assert status == "200 OK"
    assert b'fetch("/api/config")' in body
    assert b"bbox=${state.photonBbox}" in body
    assert b'fillColor: "#ed7b3a"' in body
    assert b"renderEvaluation" not in body

    status, body = request("/styles.css")
    assert status == "200 OK"
    assert b".legend .maximum { background: #ed7b3a; }" in body

    status, body = request("/api/config")
    config = json.loads(body)
    assert status == "200 OK"
    assert config["snapshot"] == "chicago-static-v1"
    assert config["core_bounds"] == [41.8500077, -88.1399989, 42.1799662, -87.6012705]


def test_rejects_too_few_origins():
    status, body = request("/api/evaluations", "POST", {"origins": [[1, 2]]})
    assert status == "400 Bad Request"
    assert b"provide between 2 and 32 origins" in body


@pytest.mark.parametrize(
    "origins",
    [
        {"first": [41.88, -87.80], "other": [41.88, -87.70]},
        ["41.88,-87.80", "41.88,-87.70"],
        [[41.88, -87.80, 1], [41.88, -87.70]],
    ],
)
def test_rejects_non_list_or_malformed_origin_coordinates(origins):
    status, body = request("/api/evaluations", "POST", {"origins": origins})
    assert status == "400 Bad Request"
    assert b"origins must be a list" in body or b"coordinates must contain" in body


def test_calculates_both_regions_and_selected_point(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())

    status, body = request(
        "/api/evaluations",
        "POST",
        {
            "origins": [[41.8801, -87.8001], [41.8801, -87.7001]],
            "tolerance_seconds": 0.75,
        },
    )
    result = json.loads(body)
    assert status == "200 OK"
    assert result["origins"] == [[41.88, -87.8], [41.88, -87.7]]
    assert result["total"]["region"] == [
        {"coordinate": [41.89, -87.78], "excess_seconds": 0.0}
    ]
    assert result["maximum"]["region"] == [
        {"coordinate": [41.89, -87.77], "excess_seconds": 0.0}
    ]
    assert result["id"] in app._analyses

    status, body = request(
        f"/api/evaluations/{result['id']}/travel-times",
        "POST",
        {"coordinate": [41.8901, -87.7801]},
    )
    assert status == "200 OK"
    selected = json.loads(body)
    assert selected["coordinate"] == [41.89, -87.78]
    assert selected["travel_times_seconds"] == [1.0, 9.0]

    status, body = request(
        f"/api/evaluations/{result['id']}/travel-times",
        "POST",
        {"coordinate": {"latitude": 41.89, "longitude": -87.78}},
    )
    assert status == "400 Bad Request"
    assert b"coordinates must contain" in body

    status, body = request(
        f"/api/evaluations/{result['id']}/travel-times",
        "POST",
        {"coordinate": [40.7128, -74.0060]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"too far from a road" in body


def test_reads_body_without_content_length(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())
    status, _body = request(
        "/api/evaluations",
        "POST",
        {
            "origins": [[41.88, -87.80], [41.88, -87.70]],
        },
        content_length=None,
    )
    assert status == "200 OK"


@pytest.mark.parametrize("raw_body", [b"[]", b"null", b'"value"'])
def test_rejects_non_object_json_roots(raw_body):
    status, body = request("/api/evaluations", "POST", raw_body=raw_body)
    assert status == "400 Bad Request"
    assert b"JSON body must be an object" in body


def test_rejects_invalid_utf8_json():
    status, body = request("/api/evaluations", "POST", raw_body=b'{"origins":\xff}')
    assert status == "400 Bad Request"
    assert b"request body must be valid UTF-8 JSON" in body


def test_caps_declared_and_undeclared_request_bodies():
    status, body = request(
        "/api/evaluations",
        "POST",
        raw_body=b"{}",
        content_length=app.MAX_REQUEST_BYTES + 1,
    )
    assert status == "413 Payload Too Large"
    assert b"request is too large" in body

    status, body = request(
        "/api/evaluations",
        "POST",
        raw_body=b" " * (app.MAX_REQUEST_BYTES + 1),
        content_length=None,
    )
    assert status == "413 Payload Too Large"
    assert b"request is too large" in body


def test_rejects_truncated_declared_request_body():
    status, body = request("/api/evaluations", "POST", raw_body=b"{}", content_length=3)
    assert status == "400 Bad Request"
    assert b"request body is shorter than content length" in body


def test_rejects_coordinates_outside_snapshot(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())
    status, body = request(
        "/api/evaluations",
        "POST",
        {
            "origins": [[40.7128, -74.0060], [34.0522, -118.2437]],
        },
    )
    assert status == "422 Unprocessable Entity"
    assert b"too far from a road" in body


def test_rejects_coordinates_too_far_from_a_snapshot_road(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())
    status, body = request(
        "/api/evaluations",
        "POST",
        {
            "origins": [[41.88, -87.80], [42.17, -87.61]],
        },
    )
    assert status == "422 Unprocessable Entity"
    assert b"too far from a road" in body


def test_rejects_unreachable_origins_with_clear_status(monkeypatch):
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    monkeypatch.setattr(app, "_graph", CompactRoadGraph.from_networkx(graph))

    status, body = request(
        "/api/evaluations",
        "POST",
        {
            "origins": [[41.88, -87.80], [41.88, -87.70]],
        },
    )
    assert status == "422 Unprocessable Entity"
    assert b"no mutually reachable road location" in body
    assert not app._analyses


def test_failed_oversized_region_is_not_cached(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())
    monkeypatch.setattr(app, "MAX_REGION_POINTS", 1)

    status, body = request(
        "/api/evaluations",
        "POST",
        {
            "origins": [[41.88, -87.80], [41.88, -87.70]],
        },
    )
    assert status == "422 Unprocessable Entity"
    assert b"too many region points" in body
    assert not app._analyses


def test_rejects_tolerance_above_service_limit(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())
    status, body = request(
        "/api/evaluations",
        "POST",
        {
            "origins": [[41.88, -87.80], [41.88, -87.70]],
            "tolerance_seconds": app.MAX_TOLERANCE_SECONDS + 1,
        },
    )
    assert status == "422 Unprocessable Entity"
    assert b"cannot exceed 5 minutes" in body
    assert not app._analyses


def test_logs_unexpected_server_errors(monkeypatch, caplog):
    def fail():
        raise ValueError("corrupt snapshot")

    monkeypatch.setattr(app, "_road", fail)
    with caplog.at_level(logging.ERROR, logger="fairway.app"):
        status, body = request(
            "/api/evaluations",
            "POST",
            {
                "origins": [[41.88, -87.80], [41.88, -87.70]],
            },
        )
    assert status == "500 Internal Server Error"
    assert b"fairway could not calculate this request" in body
    assert b"corrupt snapshot" not in body
    assert "Unhandled fairway request failure" in caplog.text


def test_unknown_route_is_not_found():
    assert request("/missing")[0] == "404 Not Found"
