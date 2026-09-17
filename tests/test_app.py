import io
import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256

import networkx as nx
import pytest
from modo import CompactRoadGraph

from fairway import app
from fairway.courses import Course
from fairway.matrix import (
    DepartureRequest,
    DestinationTimes,
    MatrixMetadata,
    MatrixProviderUnavailable,
    MatrixResult,
    TrafficBasis,
)
from fairway.scoring import travel_time_milliseconds


@pytest.fixture(autouse=True)
def reset_ranking_budget(monkeypatch):
    monkeypatch.setattr(
        app, "_ranking_tokens", app._TokenBucket(12, 0.5, clock=lambda: 0)
    )


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
    assert b'<script src="/leaflet.js" defer></script>' in body
    assert b"https://unpkg.com" not in body
    assert b"Address suggestions use Photon" not in body
    assert b'class="eyebrow"' not in body
    assert b"Results will appear here" not in body
    assert b"meeting region" not in body.lower()
    assert b"tee-time availability" in body
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
    assert b"Updating golfer origins..." in body
    assert b"Nearest-road adjustment:" in body
    assert b"rankingBasis(result.provenance)" in body
    assert b'"traffic-unaware": "without traffic"' in body
    assert b'live: "with live traffic"' in body
    assert b"current static road snapshot" not in body
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

    status, body = request("/leaflet.js")
    assert status == "200 OK"
    assert b"Leaflet 1.9.4" in body[:200]


def test_sets_security_and_cache_headers_on_every_response_kind():
    status, _body, headers = request(include_headers=True)
    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-cache"
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Content-Security-Policy"] == app.CONTENT_SECURITY_POLICY
    assert "https://unpkg.com" not in headers["Content-Security-Policy"]
    assert "https://tile.openstreetmap.org" in headers["Content-Security-Policy"]
    assert "https://photon.komoot.io" in headers["Content-Security-Policy"]
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
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


def test_overlong_static_path_is_not_a_server_error():
    status, body = request("/" + ("x" * 300))

    assert status == "404 Not Found"
    assert json.loads(body) == {"error": "not found"}


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
    assert result["max_origins"] == 8
    assert result["course_catalog"]["as_of"] == "2026-08-30"
    assert set(result) == {"core_bounds", "max_origins", "course_catalog", "routing"}
    assert result["routing"]["provider"] == "modo-static"


def test_tomtom_configuration_is_server_only_and_static_is_explicit(monkeypatch):
    monkeypatch.setenv("TOMTOM_API_KEY", "private-key")
    monkeypatch.delenv("FAIRWAY_MATRIX_PROVIDER", raising=False)
    monkeypatch.delenv("FAIRWAY_TOMTOM_DAILY_CELLS", raising=False)
    provider = app._configure_live_matrix()
    monkeypatch.setattr(app, "_live_matrix", provider)
    status, body = request("/api/config")
    assert status == "200 OK"
    assert json.loads(body)["routing"]["provider"] == "tomtom-matrix-v2"
    assert b"TomTom" in body
    assert b"private-key" not in body
    # Health checks inspect configuration without making billed API calls.
    status, body = request("/health")
    assert status == "200 OK"
    assert json.loads(body)["matrix_provider"] == "tomtom-matrix-v2"
    monkeypatch.setenv("FAIRWAY_MATRIX_PROVIDER", "static")
    assert app._configure_live_matrix() is None


@pytest.mark.parametrize("provider, key", [("tomtom", ""), ("typo", "private-key")])
def test_invalid_provider_configuration_fails_at_startup(monkeypatch, provider, key):
    monkeypatch.setenv("FAIRWAY_MATRIX_PROVIDER", provider)
    monkeypatch.setenv("TOMTOM_API_KEY", key)
    with pytest.raises(RuntimeError):
        app._configure_live_matrix()


def test_empty_optional_environment_values_use_their_defaults(monkeypatch):
    monkeypatch.setenv("FAIRWAY_COURSE_INDEX", "")
    assert app._environment("FAIRWAY_COURSE_INDEX") is None
    assert app._environment("FAIRWAY_COURSE_INDEX", "default") == "default"


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


def test_hashes_and_loads_the_same_open_graph_file(monkeypatch, tmp_path):
    graph_path = tmp_path / "roads.npz"
    replacement = tmp_path / "replacement.npz"
    road_graph().save(graph_path)
    replacement.write_bytes(b"replaced after verification")
    expected = sha256(graph_path.read_bytes()).hexdigest()
    original_load = app.CompactRoadGraph.load

    def replace_then_load(source):
        replacement.replace(graph_path)
        return original_load(source)

    monkeypatch.setattr(app, "GRAPH_PATH", str(graph_path))
    monkeypatch.setattr(
        app, "SNAPSHOT_METADATA", replace(app.SNAPSHOT_METADATA, sha256=expected)
    )
    monkeypatch.setattr(app, "_graph", None)
    monkeypatch.setattr(app, "_graph_sha256", None)
    monkeypatch.setattr(app.CompactRoadGraph, "load", replace_then_load)

    assert app._road().analyze_vertices(("a",)).travel_times(
        "x"
    ).travel_times_seconds == (1.0,)
    assert graph_path.read_bytes() == b"replaced after verification"


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
    assert result["origin_snap_distances_kilometers"] == [0.0, 0.0]
    assert result["unranked_courses"] == []
    assert result["provenance"]["course_catalog"] == "chicago-public-courses-v1"
    assert result["provenance"]["matrix_provider"] == "modo-static"
    assert result["provenance"]["matrix_strategy"] == "sequential-dijkstra"
    assert result["provenance"]["traffic_basis"] == "traffic-unaware"
    assert result["provenance"]["departure_mode"] is None
    assert result["provenance"]["departure_time"] is None
    assert result["provenance"]["matrix_calculated_at"] is None
    assert result["provenance"]["traffic_data_as_of"] is None
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


def test_ranking_uses_provider_stable_half_up_millisecond_scores(monkeypatch):
    monkeypatch.setattr(app, "_graph", road_graph())
    monkeypatch.setattr(app, "_graph_sha256", app.SNAPSHOT_METADATA.sha256)
    monkeypatch.setattr(
        app,
        "COURSES",
        (
            course("z", "Same Course", (41.89, -87.78), 9),
            course("a", "Same Course", (41.89, -87.77), 9),
        ),
    )

    class Matrix:
        def calculate(self, origins, destinations, destination_ids, *, departure):
            assert departure is None
            origins = tuple(origins)
            destinations = tuple(destinations)
            destination_ids = tuple(destination_ids)
            assert destination_ids == ("z", "a")
            return MatrixResult(
                origin_coordinates=origins,
                origin_road_coordinates=origins,
                origin_snap_distances_kilometers=(0.0, 0.0),
                destination_ids=destination_ids,
                destinations=(
                    DestinationTimes(
                        destinations[0], destinations[0], 0.0, (60.599999999999994,) * 2
                    ),
                    DestinationTimes(
                        destinations[1], destinations[1], 0.0, (60.6,) * 2
                    ),
                ),
                metadata=MatrixMetadata(
                    provider="synthetic-static",
                    traffic_basis=TrafficBasis.UNAWARE,
                ),
            )

    monkeypatch.setattr(app, "_matrix_provider", Matrix)
    status, body = request(
        "/api/rankings",
        "POST",
        {"origins": [[41.88, -87.80], [41.88, -87.70]]},
    )
    result = json.loads(body)

    assert status == "200 OK"
    assert [item["id"] for item in result["courses"]] == ["a", "z"]
    assert all(
        item["travel_times_seconds"] == [60.6, 60.6]
        and item["combined_seconds"] == 121.2
        for item in result["courses"]
    )
    assert result["provenance"]["score_resolution_seconds"] == 0.001
    assert travel_time_milliseconds(1.2345) == 1235
    assert travel_time_milliseconds(1.2344) == 1234


def test_ranking_surfaces_traffic_provider_metadata_without_static_claims(
    monkeypatch,
):
    golfer_coordinates = ((41.88, -87.80), (41.88, -87.70))
    applied_departure = DepartureRequest.leave_now()
    departure_time = datetime(2026, 9, 4, 15, tzinfo=UTC)
    calculated_at = datetime(2026, 9, 4, 14, 59, 58, tzinfo=UTC)
    traffic_data_as_of = datetime(2026, 9, 4, 14, 59, tzinfo=UTC)
    monkeypatch.setattr(
        app,
        "COURSES",
        (course("traffic", "Traffic Course", (41.89, -87.78), 18),),
    )

    class SyntheticTrafficMatrix:
        def calculate(self, origins, destinations, destination_ids, *, departure):
            assert departure is None
            origins = tuple(origins)
            assert origins == golfer_coordinates
            destinations = tuple(destinations)
            destination_ids = tuple(destination_ids)
            assert destination_ids == ("traffic",)
            return MatrixResult(
                origin_coordinates=origins,
                origin_road_coordinates=(None, None),
                origin_snap_distances_kilometers=(None, None),
                destination_ids=destination_ids,
                destinations=(
                    DestinationTimes(destinations[0], None, None, (540.0, 600.0)),
                ),
                metadata=MatrixMetadata(
                    provider="synthetic-traffic",
                    strategy="deterministic-fixture",
                    traffic_basis=TrafficBasis.BLENDED,
                    departure=applied_departure,
                    departure_time=departure_time,
                    calculated_at=calculated_at,
                    traffic_data_as_of=traffic_data_as_of,
                    provenance=(("provider_profile", "driving-traffic"),),
                ),
            )

    monkeypatch.setattr(app, "_matrix_provider", SyntheticTrafficMatrix)
    status, body = request(
        "/api/rankings",
        "POST",
        {"origins": [list(coordinate) for coordinate in golfer_coordinates]},
    )
    result = json.loads(body)
    provenance = result["provenance"]

    assert status == "200 OK"
    assert result["origin_road_coordinates"] == [None, None]
    assert result["origin_snap_distances_kilometers"] == [None, None]
    assert result["courses"][0]["road_coordinate"] is None
    assert result["courses"][0]["snap_distance_kilometers"] is None
    assert provenance["matrix_provider"] == "synthetic-traffic"
    assert provenance["matrix_strategy"] == "deterministic-fixture"
    assert provenance["traffic_basis"] == "blended"
    assert provenance["departure_mode"] == "leave-now"
    assert provenance["departure_time"] == "2026-09-04T15:00:00Z"
    assert provenance["matrix_calculated_at"] == "2026-09-04T14:59:58Z"
    assert provenance["traffic_data_as_of"] == "2026-09-04T14:59:00Z"
    assert provenance["provider_profile"] == "driving-traffic"
    assert "road_snapshot" not in provenance
    assert "modo" not in provenance


@pytest.mark.parametrize("mismatch", ["origins", "identifiers", "coordinates"])
def test_rejects_mismatched_provider_matrix_contract(
    monkeypatch, ranked_courses, mismatch
):
    class MismatchedMatrix:
        def calculate(self, origins, destinations, destination_ids, *, departure):
            assert departure is None
            origins = tuple(origins)
            destinations = tuple(destinations)
            destination_ids = tuple(destination_ids)
            echoed_origins = origins[::-1] if mismatch == "origins" else origins
            echoed_ids = (
                destination_ids[::-1] if mismatch == "identifiers" else destination_ids
            )
            echoed_destinations = (
                destinations[::-1] if mismatch == "coordinates" else destinations
            )
            return MatrixResult(
                origin_coordinates=echoed_origins,
                origin_road_coordinates=(None,) * len(origins),
                origin_snap_distances_kilometers=(None,) * len(origins),
                destination_ids=echoed_ids,
                destinations=tuple(
                    DestinationTimes(coordinate, None, None, (1.0,) * len(origins))
                    for coordinate in echoed_destinations
                ),
                metadata=MatrixMetadata(
                    provider="mismatched-fixture",
                    traffic_basis=TrafficBasis.UNAWARE,
                ),
            )

    monkeypatch.setattr(app, "_matrix_provider", MismatchedMatrix)
    status, body = request(
        "/api/rankings",
        "POST",
        {"origins": [[41.88, -87.80], [41.88, -87.70]]},
    )

    assert status == "500 Internal Server Error"
    assert json.loads(body) == {"error": "fairway could not calculate this request"}


def test_provider_unavailability_is_a_retryable_service_failure(
    monkeypatch, ranked_courses
):
    class UnavailableMatrix:
        def calculate(self, origins, destinations, destination_ids, *, departure):
            raise MatrixProviderUnavailable(45)

    monkeypatch.setattr(app, "_matrix_provider", UnavailableMatrix)
    status, body, headers = request(
        "/api/rankings",
        "POST",
        {"origins": [[41.88, -87.80], [41.88, -87.70]]},
        include_headers=True,
    )

    assert status == "503 Service Unavailable"
    assert headers["Retry-After"] == "45"
    assert json.loads(body) == {
        "error": "fairway's travel-time provider is temporarily unavailable"
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"origins": [[41.88, -87.80]]}, b"provide between 2 and 8 origins"),
        (
            {"origins": [[41.88, -87.80], [41.88, -87.70]], "objective": "total"},
            b"objective must be 'combined' or 'maximum'",
        ),
        (
            {"origins": [[41.88, -87.80], [41.88, -87.70]], "objective": []},
            b"objective must be 'combined' or 'maximum'",
        ),
        (
            {"origins": [[41.88, -87.80], [41.88, -87.70]], "objective": {}},
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
    assert b"No selected course is reachable from every golfer" in body


def test_omits_only_unreachable_courses(monkeypatch):
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    graph.add_node("x", y=41.89, x=-87.78)
    graph.add_node("y", y=41.89, x=-87.77)
    graph.add_edge("a", "x", travel_time=1)
    graph.add_edge("b", "x", travel_time=2)
    monkeypatch.setattr(app, "_graph", CompactRoadGraph.from_networkx(graph))
    monkeypatch.setattr(app, "_graph_sha256", app.SNAPSHOT_METADATA.sha256)
    monkeypatch.setattr(
        app,
        "COURSES",
        (
            course("reachable", "Reachable", (41.89, -87.78), 9),
            course("unreachable", "Unreachable", (41.89, -87.77), 9),
        ),
    )

    status, body = request(
        "/api/rankings",
        "POST",
        {"origins": [[41.88, -87.80], [41.88, -87.70]]},
    )
    result = json.loads(body)

    assert status == "200 OK"
    assert [item["id"] for item in result["courses"]] == ["reachable"]
    assert result["unranked_courses"] == [
        {"id": "unreachable", "name": "Unreachable", "reason": "unreachable"}
    ]


def test_rejects_overlapping_compute_with_retry_hint(ranked_courses):
    tokens = app._ranking_tokens.tokens
    assert app._compute_gate.acquire(blocking=False)
    try:
        status, body, headers = request(
            "/api/rankings",
            "POST",
            {"origins": [[41.88, -87.80], [41.88, -87.70]]},
            include_headers=True,
        )
    finally:
        app._compute_gate.release()

    assert status == "503 Service Unavailable"
    assert headers["Retry-After"] == "1"
    assert b"already calculating" in body
    assert app._ranking_tokens.tokens == tokens


def test_identifier_free_ranking_budget_returns_retry_after(
    monkeypatch, ranked_courses
):
    now = [0.0]
    monkeypatch.setattr(
        app, "_ranking_tokens", app._TokenBucket(1, 0.5, clock=lambda: now[0])
    )
    payload = {"origins": [[41.88, -87.80], [41.88, -87.70]]}

    assert request("/api/rankings", "POST", payload)[0] == "200 OK"
    status, body, headers = request(
        "/api/rankings", "POST", payload, include_headers=True
    )

    assert status == "429 Too Many Requests"
    assert headers["Retry-After"] == "2"
    assert b"calculation limit was reached" in body
    now[0] = 2.0
    assert request("/api/rankings", "POST", payload)[0] == "200 OK"


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


def test_rejects_json_integer_over_the_interpreter_conversion_limit():
    raw_body = b'{"origins":' + (b"1" * 5_000) + b"}"
    status, body = request("/api/rankings", "POST", raw_body=raw_body)

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
