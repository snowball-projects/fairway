import io
import json
import logging
from dataclasses import replace
from hashlib import sha256

import networkx as nx
import pytest
from modo import CompactRoadGraph

from fairway import app
from fairway.courses import Course


def request(
    path="/",
    method="GET",
    payload=None,
    *,
    raw_body=None,
    content_length="auto",
    content_type="auto",
    include_headers=False,
):
    body = (
        raw_body
        if raw_body is not None
        else json.dumps(payload).encode()
        if payload is not None
        else b""
    )
    status = None
    headers = None

    def start_response(value, response_headers):
        nonlocal headers, status
        status = value
        headers = dict(response_headers)

    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "wsgi.input": io.BytesIO(body),
    }
    if content_length == "auto":
        environ["CONTENT_LENGTH"] = str(len(body))
    elif content_length is not None:
        environ["CONTENT_LENGTH"] = str(content_length)
    if content_type == "auto" and method == "POST":
        environ["CONTENT_TYPE"] = "application/json"
    elif content_type is not None and content_type != "auto":
        environ["CONTENT_TYPE"] = content_type
    result = b"".join(app.application(environ, start_response))
    return (status, result, headers) if include_headers else (status, result)


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


def course(identifier, name, coordinate, holes):
    return Course(
        identifier,
        name,
        "1 Test Way, Chicago, IL",
        coordinate,
        holes,
        "public",
        f"https://example.com/{identifier}",
        "cpd-columbus",
        "openstreetmap-2026-08-30",
        f"node/{identifier}",
    )


@pytest.fixture
def ranked_courses(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())
    monkeypatch.setattr(app, "_graph_sha256", app.SNAPSHOT_METADATA.sha256)
    monkeypatch.setattr(
        app,
        "COURSES",
        (
            course("combined", "Combined Course", (41.89, -87.78), 9),
            course("balanced", "Balanced Course", (41.89, -87.77), 18),
        ),
    )


def test_serves_course_ranking_interface():
    status, body = request()
    assert status == "200 OK"
    assert b"fairway" in body
    assert b"Choose the course that works for the whole group" in body
    assert b"Shortest longest drive" in body
    assert b"Lowest combined drive" in body
    assert b'id="results"' in body
    assert b'id="results-panel"' in body
    assert b'class="results-panel" aria-labelledby="results-title" hidden' in body
    assert b'id="map"' in body
    assert b'id="map-key" class="map-key" hidden' in body
    assert b'id="filter-toggle"' in body
    assert b'aria-controls="filter-popover"' in body
    assert b'aria-haspopup="dialog"' in body
    assert b"Order by" in body
    assert b"Holes" in body
    assert b"Service policy" in body
    assert b"Built by AI agents" in body
    assert b"Address suggestions use Photon" not in body
    assert b'class="eyebrow"' not in body
    assert b"Results will appear here" not in body
    assert b"meeting region" not in body.lower()
    assert b"tee-time availability" in body
    assert (
        b'href="https://snowball-projects.github.io/licensing/#how-snowball-is-built"'
        in body
    )
    controls = body.split(b'<aside class="controls"', 1)[1].split(b"</aside>", 1)[0]
    assert b'name="objective"' not in controls
    assert b'name="holes"' not in controls

    status, body = request("/app.js")
    assert status == "200 OK"
    assert b'fetch("/api/config")' in body
    assert b'fetch("/api/rankings"' in body
    assert b"courseMarkers" in body
    assert b"drawCourseMarkers" in body
    assert b"drawCatalog" not in body
    assert b"setResultsVisible(true)" in body
    assert b"preserveResults: true" in body
    assert b'event.key !== "Tab"' in body
    assert b'querySelectorAll("input:checked")' in body
    assert b'view.results.querySelector(".course-focus")' in body
    assert b"COLORS" in body
    assert b"looksLikeCoordinateInput(query)" in body
    assert b'element.setAttribute("aria-label", label)' in body
    assert b'element.setAttribute("title", label)' in body
    assert b"`${course.name}, rank ${rank}`" in body
    assert b"`Golfer ${state.rows.indexOf(row) + 1}`" in body
    assert b'row.input.setAttribute("role", "combobox")' in body
    assert b'row.suggestions.setAttribute("role", "listbox")' in body
    assert b'row.input.setAttribute("aria-activedescendant"' in body
    assert b'event.key === "ArrowDown"' in body
    assert b'event.key === "ArrowUp"' in body
    assert b'event.key === "Enter"' in body
    assert b'event.key === "Escape"' in body
    assert b"setTimeout(() => row.suggestions.replaceChildren(), 180)" not in body

    status, body = request("/styles.css")
    assert status == "200 OK"
    assert b"grid-template-columns" in body
    assert b".app-shell.has-results" in body
    assert b"[hidden]" in body
    assert b".filter-popover" in body
    assert b".filter-icon span:nth-child(3)" in body
    assert b'.status[data-error="true"]' in body
    assert b".course-card" in body
    assert b".origin-pin" in body
    assert b"@media (max-width: 960px)" in body
    assert b"min-height: 40rem" not in body


def test_sets_security_and_cache_headers_on_every_response_kind():
    status, _body, headers = request(include_headers=True)
    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-cache"
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Content-Security-Policy"] == app.CONTENT_SECURITY_POLICY
    assert "https://unpkg.com" in headers["Content-Security-Policy"]
    assert "https://tile.openstreetmap.org" in headers["Content-Security-Policy"]
    assert "https://photon.komoot.io" in headers["Content-Security-Policy"]
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Strict-Transport-Security"] == "max-age=31536000"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"

    status, _body, headers = request("/api/config", include_headers=True)
    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["Content-Security-Policy"] == app.CONTENT_SECURITY_POLICY

    status, _body, headers = request("/missing", include_headers=True)
    assert status == "404 Not Found"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Security-Policy"] == app.CONTENT_SECURITY_POLICY


def test_known_routes_enforce_methods_and_support_head(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())
    monkeypatch.setattr(app, "_graph_sha256", app.SNAPSHOT_METADATA.sha256)

    status, body, headers = request("/", "HEAD", include_headers=True)
    assert status == "200 OK"
    assert body == b""
    assert int(headers["Content-Length"]) > 0

    status, body, headers = request("/api/rankings", "HEAD", include_headers=True)
    assert status == "405 Method Not Allowed"
    assert body == b""
    assert int(headers["Content-Length"]) > 0
    assert headers["Allow"] == "POST"

    for path, method, allowed in (
        ("/health", "POST", "GET, HEAD"),
        ("/api/config", "POST", "GET, HEAD"),
        ("/api/rankings", "GET", "POST"),
    ):
        status, _body, headers = request(path, method, include_headers=True)
        assert status == "405 Method Not Allowed"
        assert headers["Allow"] == allowed


@pytest.mark.parametrize(
    "content_type", [None, "text/plain", "application/x-www-form-urlencoded"]
)
def test_rankings_require_json_content_type(content_type):
    status, body = request(
        "/api/rankings", "POST", raw_body=b"{}", content_type=content_type
    )
    assert status == "415 Unsupported Media Type"
    assert b"content type must be application/json" in body


def test_rankings_accept_json_content_type_parameters(ranked_courses):
    status, _body = request(
        "/api/rankings",
        "POST",
        {"origins": [[41.88, -87.80], [41.88, -87.70]]},
        content_type="application/json; charset=utf-8",
    )
    assert status == "200 OK"


def test_config_exposes_bounded_catalog_and_provenance():
    status, body = request("/api/config")
    result = json.loads(body)
    assert status == "200 OK"
    assert result["snapshot"] == "chicago-static-v1"
    assert result["max_origins"] == 8
    assert result["course_catalog"]["id"] == "chicago-public-courses-v1"
    assert result["course_catalog"]["as_of"] == "2026-08-30"
    assert len(result["course_catalog"]["sha256"]) == 64
    assert len(result["courses"]) == 8
    assert {course["holes"] for course in result["courses"]} == {9, 18}
    assert {course["access"] for course in result["courses"]} == {"public"}
    assert all(
        course["facts_source"].startswith("https://") for course in result["courses"]
    )
    assert all(
        course["routing_source"].startswith("https://www.openstreetmap.org/")
        for course in result["courses"]
    )


def test_verifies_graph_checksum_before_load_and_provenance(monkeypatch, tmp_path):
    graph_path = tmp_path / "roads.npz"
    road_graph().save(graph_path)
    expected = sha256(graph_path.read_bytes()).hexdigest()
    monkeypatch.setattr(app, "GRAPH_PATH", str(graph_path))
    monkeypatch.setattr(
        app, "SNAPSHOT_METADATA", replace(app.SNAPSHOT_METADATA, sha256=expected)
    )
    monkeypatch.setattr(app, "_graph", None)
    monkeypatch.setattr(app, "_graph_sha256", None)
    monkeypatch.setattr(
        app,
        "COURSES",
        (
            course("combined", "Combined Course", (41.89, -87.78), 9),
            course("balanced", "Balanced Course", (41.89, -87.77), 18),
        ),
    )

    status, body = request(
        "/api/rankings",
        "POST",
        {"origins": [[41.88, -87.80], [41.88, -87.70]]},
    )
    result = json.loads(body)

    assert status == "200 OK"
    assert app._graph_sha256 == expected
    assert result["provenance"]["road_snapshot_sha256"] == expected


def test_rejects_graph_checksum_mismatch_before_load(monkeypatch, tmp_path):
    graph_path = tmp_path / "roads.npz"
    road_graph().save(graph_path)
    loaded = False

    def load(_path):
        nonlocal loaded
        loaded = True

    monkeypatch.setattr(app, "GRAPH_PATH", str(graph_path))
    monkeypatch.setattr(
        app, "SNAPSHOT_METADATA", replace(app.SNAPSHOT_METADATA, sha256="0" * 64)
    )
    monkeypatch.setattr(app, "_graph", None)
    monkeypatch.setattr(app, "_graph_sha256", None)
    monkeypatch.setattr(app.CompactRoadGraph, "load", load)

    with pytest.raises(RuntimeError, match="checksum does not match"):
        app._road()

    assert loaded is False
    assert app._graph is None
    assert app._graph_sha256 is None


def test_ranks_by_shortest_longest_drive(ranked_courses):
    status, body = request(
        "/api/rankings",
        "POST",
        {
            "origins": [[41.88, -87.80], [41.88, -87.70]],
            "objective": "maximum",
            "holes": [9, 18],
        },
    )
    result = json.loads(body)
    assert status == "200 OK"
    assert [course["id"] for course in result["courses"]] == [
        "balanced",
        "combined",
    ]
    assert result["courses"][0]["travel_times_seconds"] == [5.0, 6.0]
    assert result["courses"][0]["maximum_seconds"] == 6.0
    assert result["courses"][0]["combined_seconds"] == 11.0
    assert result["origin_road_coordinates"] == [
        [41.88, -87.8],
        [41.88, -87.7],
    ]
    assert result["provenance"]["course_catalog"] == "chicago-public-courses-v1"
    assert "id" not in result


def test_ranks_by_combined_drive_and_filters_holes(ranked_courses):
    status, body = request(
        "/api/rankings",
        "POST",
        {
            "origins": [[41.88, -87.80], [41.88, -87.70]],
            "objective": "combined",
            "holes": [9, 18],
        },
    )
    result = json.loads(body)
    assert status == "200 OK"
    assert [course["id"] for course in result["courses"]] == [
        "combined",
        "balanced",
    ]

    status, body = request(
        "/api/rankings",
        "POST",
        {
            "origins": [[41.88, -87.80], [41.88, -87.70]],
            "objective": "combined",
            "holes": [18],
        },
    )
    result = json.loads(body)
    assert status == "200 OK"
    assert [course["id"] for course in result["courses"]] == ["balanced"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"origins": [[41.88, -87.80]]}, b"provide between 2 and 8 origins"),
        (
            {"origins": [[41.88, -87.80], [41.88, -87.70]], "objective": "total"},
            b"objective must be 'combined' or 'maximum'",
        ),
        (
            {"origins": [[41.88, -87.80], [41.88, -87.70]], "holes": [12]},
            b"holes must be a nonempty list containing 9 or 18",
        ),
        (
            {"origins": [[41.88, -87.80], [41.88, -87.70]], "holes": []},
            b"holes must be a nonempty list containing 9 or 18",
        ),
    ],
)
def test_rejects_invalid_ranking_options(ranked_courses, payload, message):
    status, body = request("/api/rankings", "POST", payload)
    assert status == "400 Bad Request"
    assert message in body


@pytest.mark.parametrize(
    "origins",
    [
        {"first": [41.88, -87.80], "other": [41.88, -87.70]},
        ["41.88,-87.80", "41.88,-87.70"],
        [[41.88, -87.80, 1], [41.88, -87.70]],
        [[True, -87.80], [41.88, -87.70]],
        [["41.88", -87.80], [41.88, -87.70]],
    ],
)
def test_rejects_malformed_origin_coordinates(ranked_courses, origins):
    status, body = request("/api/rankings", "POST", {"origins": origins})
    assert status == "400 Bad Request"
    assert b"origins must" in body


def test_rejects_origins_outside_published_coverage(ranked_courses):
    status, body = request(
        "/api/rankings",
        "POST",
        {"origins": [[40.7128, -74.0060], [34.0522, -118.2437]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"outside fairway's current road coverage" in body


def test_rejects_unreachable_courses_with_clear_status(monkeypatch):
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    graph.add_node("x", y=41.89, x=-87.78)
    monkeypatch.setattr(app, "_graph", CompactRoadGraph.from_networkx(graph))
    monkeypatch.setattr(app, "_graph_sha256", app.SNAPSHOT_METADATA.sha256)
    monkeypatch.setattr(
        app,
        "COURSES",
        (course("course", "Course", (41.89, -87.78), 9),),
    )
    status, body = request(
        "/api/rankings",
        "POST",
        {"origins": [[41.88, -87.80], [41.88, -87.70]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"no mutually reachable road route" in body


def test_reads_body_without_content_length(ranked_courses):
    status, _body = request(
        "/api/rankings",
        "POST",
        {"origins": [[41.88, -87.80], [41.88, -87.70]]},
        content_length=None,
    )
    assert status == "200 OK"


@pytest.mark.parametrize("raw_body", [b"[]", b"null", b'"value"'])
def test_rejects_non_object_json_roots(raw_body):
    status, body = request("/api/rankings", "POST", raw_body=raw_body)
    assert status == "400 Bad Request"
    assert b"JSON body must be an object" in body


def test_rejects_invalid_utf8_json():
    status, body = request("/api/rankings", "POST", raw_body=b'{"origins":\xff}')
    assert status == "400 Bad Request"
    assert b"request body must be valid UTF-8 JSON" in body


def test_caps_declared_and_undeclared_request_bodies():
    status, body = request(
        "/api/rankings",
        "POST",
        raw_body=b"{}",
        content_length=app.MAX_REQUEST_BYTES + 1,
    )
    assert status == "413 Payload Too Large"
    assert b"request is too large" in body

    status, body = request(
        "/api/rankings",
        "POST",
        raw_body=b" " * (app.MAX_REQUEST_BYTES + 1),
        content_length=None,
    )
    assert status == "413 Payload Too Large"
    assert b"request is too large" in body


def test_rejects_truncated_declared_request_body():
    status, body = request("/api/rankings", "POST", raw_body=b"{}", content_length=3)
    assert status == "400 Bad Request"
    assert b"request body is shorter than content length" in body


def test_logs_unexpected_server_errors(monkeypatch, caplog):
    def fail():
        raise ValueError("corrupt snapshot")

    monkeypatch.setattr(app, "_road", fail)
    with caplog.at_level(logging.ERROR, logger="fairway.app"):
        status, body = request(
            "/api/rankings",
            "POST",
            {"origins": [[41.88, -87.80], [41.88, -87.70]]},
        )
    assert status == "500 Internal Server Error"
    assert b"fairway could not calculate this request" in body
    assert b"corrupt snapshot" not in body
    assert "Unhandled fairway request failure" in caplog.text


def test_unknown_route_is_not_found():
    assert request("/missing")[0] == "404 Not Found"
