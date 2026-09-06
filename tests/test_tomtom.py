import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from fairway import tomtom
from fairway.matrix import (
    DepartureRequest,
    DestinationFailure,
    MatrixProviderUnavailable,
    TrafficBasis,
)

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)
ORIGINS = ((41.88, -87.80), (41.88, -87.70))
DESTINATIONS = ((41.89, -87.78), (41.89, -87.77))


def response():
    return {
        "data": [
            {
                "originIndex": origin,
                "destinationIndex": destination,
                "routeSummary": {
                    "travelTimeInSeconds": 100 * (destination + 1) + origin,
                    "departureTime": (NOW + timedelta(seconds=origin)).isoformat(),
                },
            }
            for destination in (1, 0)
            for origin in (1, 0)
        ],
        "statistics": {"totalCount": 4, "successes": 4, "failures": 0},
    }


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(tomtom, "_utcnow", lambda: NOW)


def calculate(monkeypatch, value):
    monkeypatch.setattr(tomtom, "_post_matrix", lambda key, payload: value)
    return tomtom.TomTomMatrix("private-key").calculate(
        ORIGINS, DESTINATIONS, ("first", "second")
    )


def test_preserves_matrix_identity_and_honest_provider_timing(monkeypatch):
    posted = []

    def post(key, payload):
        posted.append((key, payload))
        return response()

    monkeypatch.setattr(tomtom, "_post_matrix", post)
    provider = tomtom.TomTomMatrix("private-key")
    result = provider.calculate(ORIGINS, DESTINATIONS, ("first", "second"))
    assert result.origin_coordinates == ORIGINS
    assert result.destination_ids == ("first", "second")
    assert [item.travel_times_seconds for item in result.destinations] == [
        (100, 101),
        (200, 201),
    ]
    assert result.origin_road_coordinates == (None, None)
    assert all(item.road_coordinate is None for item in result.destinations)
    assert result.metadata.traffic_basis is TrafficBasis.BLENDED
    assert result.metadata.traffic_data_as_of is None
    assert result.metadata.departure_time == NOW
    assert (
        dict(result.metadata.provenance)["latest_departure_time"]
        == (NOW + timedelta(seconds=1)).isoformat()
    )
    assert posted[0][1]["options"] == {
        "departAt": "now",
        "traffic": "live",
        "routeType": "fastest",
        "travelMode": "car",
    }
    assert "private-key" not in repr(provider)
    assert "private-key" not in repr(result)


@pytest.mark.parametrize(
    "problem",
    [
        "missing-cell",
        "duplicate-cell",
        "out-of-range-cell",
        "bool-index",
        "negative-time",
        "bool-time",
        "missing-offset",
        "stale-departure",
        "future-departure",
        "wrong-total",
        "wrong-failures",
        "error-cell",
        "invalid-root",
    ],
)
def test_rejects_invalid_or_partial_provider_results(monkeypatch, problem):
    value = response()
    cell = value["data"][0]
    if problem == "missing-cell":
        value["data"].pop()
    elif problem == "duplicate-cell":
        value["data"][0] = deepcopy(value["data"][1])
    elif problem == "out-of-range-cell":
        cell["originIndex"] = 2
    elif problem == "bool-index":
        cell["originIndex"] = True
    elif problem == "negative-time":
        cell["routeSummary"]["travelTimeInSeconds"] = -1
    elif problem == "bool-time":
        cell["routeSummary"]["travelTimeInSeconds"] = True
    elif problem == "missing-offset":
        cell["routeSummary"]["departureTime"] = "2026-09-06T12:00:00"
    elif problem == "stale-departure":
        cell["routeSummary"]["departureTime"] = (NOW - timedelta(days=1)).isoformat()
    elif problem == "future-departure":
        cell["routeSummary"]["departureTime"] = (NOW + timedelta(days=1)).isoformat()
    elif problem == "wrong-total":
        value["statistics"]["totalCount"] = 5
    elif problem == "wrong-failures":
        value["statistics"].update(successes=3, failures=1)
    elif problem == "error-cell":
        cell["detailedError"] = {"code": "CELL_TIMEOUT", "message": "private-key"}
        cell.pop("routeSummary")
    elif problem == "invalid-root":
        value = []
    with pytest.raises(MatrixProviderUnavailable) as captured:
        calculate(monkeypatch, value)
    assert "private-key" not in str(captured.value)
    assert captured.value.__suppress_context__


def test_omits_only_courses_with_a_proven_unreachable_route(monkeypatch):
    value = response()
    cell = value["data"][0]
    cell.pop("routeSummary")
    cell["detailedError"] = {
        "code": "CELL_PROCESSING_ERROR",
        "innerError": {"code": "NO_ROUTE_FOUND"},
    }
    value["statistics"].update(successes=3, failures=1)
    result = calculate(monkeypatch, value)
    assert isinstance(result.destinations[1], DestinationFailure)
    assert result.destinations[1].reason == "unreachable"
    assert result.destinations[0].travel_times_seconds == (100, 101)


def test_cell_budget_counts_failed_attempts_and_resets_on_utc_day(monkeypatch):
    posted = []

    def unavailable(key, payload):
        posted.append(payload)
        raise MatrixProviderUnavailable()

    monkeypatch.setattr(tomtom, "_post_matrix", unavailable)
    provider = tomtom.TomTomMatrix("private-key", daily_cell_limit=4)
    for _attempt in range(2):
        with pytest.raises(MatrixProviderUnavailable):
            provider.calculate(ORIGINS, DESTINATIONS)
    assert len(posted) == 1
    monkeypatch.setattr(tomtom, "_utcnow", lambda: NOW + timedelta(days=1))
    with pytest.raises(MatrixProviderUnavailable):
        provider.calculate(ORIGINS, DESTINATIONS)
    assert len(posted) == 2


def test_concurrent_reservations_cannot_exceed_the_budget():
    provider = tomtom.TomTomMatrix("private-key", daily_cell_limit=8)

    def reserve(_attempt):
        try:
            provider._reserve(4)
            return True
        except MatrixProviderUnavailable:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(reserve, range(32))) == 2


def test_oversized_or_scheduled_requests_never_reach_the_provider(monkeypatch):
    def unexpected(*args):
        pytest.fail("an invalid request reached TomTom")

    monkeypatch.setattr(tomtom, "_post_matrix", unexpected)
    provider = tomtom.TomTomMatrix("private-key")
    with pytest.raises(ValueError, match="100 cells"):
        provider.calculate(ORIGINS * 6, DESTINATIONS * 5)
    with pytest.raises(ValueError, match="leave-now"):
        provider.calculate(
            ORIGINS,
            DESTINATIONS,
            departure=DepartureRequest.depart_at(NOW + timedelta(hours=1)),
        )


@pytest.mark.parametrize("status", [301, 403, 408, 429, 500, 503])
def test_http_errors_are_not_retried_redirected_or_exposed(monkeypatch, status):
    connection = fake_connection(monkeypatch, status=status)
    with pytest.raises(MatrixProviderUnavailable) as captured:
        tomtom._post_matrix("private-key", {})
    assert connection.closed
    assert connection.requests == 1
    assert "private-key" not in str(captured.value)
    assert not connection.response.reads


def fake_connection(monkeypatch, *, status=200, body=b"{}"):
    class Response:
        reads = 0

        def __init__(self):
            self.status = status
            self.stream = io.BytesIO(body)

        def read1(self, size):
            self.reads += 1
            return self.stream.read(size)

        def close(self):
            self.stream.close()

    class Connection:
        closed = False
        requests = 0

        def __init__(self):
            self.sock = self
            self.response = Response()

        def settimeout(self, value):
            assert 0 < value <= tomtom.REQUEST_TIMEOUT_SECONDS

        def request(self, method, path, *, body, headers):
            self.requests += 1
            assert method == "POST"
            assert path.startswith("/routing/matrix/2?key=")
            assert headers["Content-Type"] == "application/json"

        def getresponse(self):
            return self.response

        def close(self):
            self.closed = True

    connection = Connection()

    def connect(host, *, timeout):
        assert host == "api.tomtom.com"
        assert timeout == tomtom.REQUEST_TIMEOUT_SECONDS
        return connection

    monkeypatch.setattr(tomtom, "HTTPSConnection", connect)
    return connection


@pytest.mark.parametrize("body", [b"[]broken", b"x" * (tomtom.MAX_RESPONSE_BYTES + 1)])
def test_invalid_or_oversized_responses_fail_closed(monkeypatch, body):
    connection = fake_connection(monkeypatch, body=body)
    with pytest.raises(MatrixProviderUnavailable):
        tomtom._post_matrix("private-key", {})
    assert connection.closed


def test_successful_http_response(monkeypatch):
    fake_connection(monkeypatch, body=json.dumps(response()).encode())
    assert tomtom._post_matrix("private-key", {}) == response()


def test_slow_response_has_a_total_read_deadline(monkeypatch):
    connection = fake_connection(monkeypatch, body=b"{}")
    times = iter((0, 1, 2, 21))
    monkeypatch.setattr(tomtom, "monotonic", lambda: next(times))
    with pytest.raises(MatrixProviderUnavailable):
        tomtom._post_matrix("private-key", {})
    assert connection.closed
