import json
import multiprocessing
import time
from math import hypot
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

import pytest
from modo import RoutingProviderError

from fairway.national_api import (
    MAX_BODY_BYTES,
    MAX_CANDIDATES,
    MAX_MATRIX_CELLS,
    MAX_PROVIDER_REQUESTS,
    APIConfig,
    APIError,
    BoundedRouter,
    Calculator,
    LimitedResponse,
    NoRedirect,
    RateBudget,
    WorkLimit,
    calculate,
    parse_request,
)

CATALOG = (
    Path(__file__).resolve().parents[1] / "src/fairway/static/data/public-courses.json"
)
CONFIG = APIConfig("http://127.0.0.1:8003", str(CATALOG), "fixture-roads-v1")
BODY = {
    "origins": [[41.9, -88.0], [42.0, -87.7]],
    "objective": "maximum",
    "holes": [9, 18],
}


class PlaneRouter:
    requests = 0
    cells = 0

    def filter_reachable(self, points):
        self.requests += 1
        return (True,) * len(points)

    def matrix(self, origins, targets):
        self.requests += 1
        self.cells += len(origins) * len(targets)
        return tuple(
            tuple(hypot(a[0] - b[0], a[1] - b[1]) * 3600 for b in targets)
            for a in origins
        )


@pytest.mark.parametrize("objective", ["combined", "maximum"])
def test_real_modo_estimator_shortlist_and_canonical_ranking(objective):
    request = parse_request(json.dumps({**BODY, "objective": objective}).encode())
    result = calculate(CONFIG, request, router=PlaneRouter())
    assert result["facilities"]
    assert len(result["facilities"]) <= 24
    assert all(
        len(row["travel_times_milliseconds"]) == 2 for row in result["facilities"]
    )
    assert all(
        row["combined_milliseconds"] == sum(row["travel_times_milliseconds"])
        for row in result["facilities"]
    )
    metadata = result["metadata"]
    assert metadata["approximate"] is True
    assert metadata["global_optimum"] is False
    assert metadata["traffic_basis"] == "unaware"
    assert metadata["catalog_complete"] is False
    assert metadata["catalog_facility_count"] == 4428
    assert len(metadata["catalog_sha256"]) == 64
    assert metadata["area_search"]["approximate"] is True
    assert "127.0.0.1" not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        {"origins": [[True, -88], [42, -87]]},
        {"origins": [[float("nan"), -88], [42, -87]]},
        {"origins": [[float("inf"), -88], [42, -87]]},
        {"origins": [[41, -88]]},
        {"origins": [[41, -88]] * 9},
        {"origins": [[91, -88], [42, -87]]},
        {"origins": [[41, -88, 0], [42, -87]]},
        {"origins": ["41,-88", [42, -87]]},
        {"objective": "total"},
        {"objective": {}},
        {"holes": [True]},
        {"holes": [9.0]},
        {"holes": [9, 9]},
        {"holes": []},
        {"holes": [27]},
        {"provider_url": "http://169.254.169.254"},
        {"destinations": [[41, -88]]},
        {"catalog_path": "/etc/passwd"},
        {"command": "id"},
        {"departure": "now"},
        {"area_limit": 1000},
        {"shortlist_limit": 1000},
    ],
)
def test_rejects_invalid_or_capability_expanding_inputs(change):
    with pytest.raises(APIError) as error:
        parse_request(json.dumps({**BODY, **change}).encode())
    assert error.value.status == 400


@pytest.mark.parametrize(
    "raw",
    [b"[]", b"null", b"{}", b"\xff", b"{", b"[" * 1500, b'{"origins":[],"origins":[]}'],
)
def test_json_errors_are_structured(raw):
    with pytest.raises(APIError) as error:
        parse_request(raw)
    assert error.value.code == "invalid_request"


def test_rejects_size_and_non_lower48_coverage():
    with pytest.raises(APIError) as error:
        parse_request(b" " * (MAX_BODY_BYTES + 1))
    assert error.value.status == 413
    with pytest.raises(APIError) as error:
        parse_request(json.dumps({**BODY, "origins": [[0, 0], [42, -87]]}).encode())
    assert error.value.code == "outside_coverage"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com:8003",
        "http://169.254.169.254:8003",
        "http://127.0.0.1:8003/route",
        "http://user:pass@valhalla:8002",
        "http://valhalla:8002?x=1",
        "file:///etc/passwd",
    ],
)
def test_configuration_rejects_remote_and_credential_urls(endpoint):
    with pytest.raises(ValueError):
        APIConfig(endpoint, str(CATALOG), "roads")


def test_deadline_and_work_budgets_stop_provider_calls():
    calls = []

    def unavailable(request, timeout):
        calls.append(request)
        raise URLError("private url and coordinate details")

    router = BoundedRouter(
        CONFIG.endpoint, deadline=time.monotonic() + 10, opener=unavailable
    )
    for _ in range(MAX_PROVIDER_REQUESTS):
        with pytest.raises(RoutingProviderError):
            router.filter_reachable(((41.9, -87.9),))
    with pytest.raises(WorkLimit):
        router.filter_reachable(((41.9, -87.9),))
    assert len(calls) == MAX_PROVIDER_REQUESTS
    router.cells = MAX_MATRIX_CELLS
    with pytest.raises(WorkLimit):
        router.matrix(((41, -88),), ((42, -87),))
    router.cells = 0
    router.candidates = {(41.0, -100 + n / 1000) for n in range(MAX_CANDIDATES)}
    with pytest.raises(WorkLimit):
        router.matrix(((41, -88),), ((42, -87),))
    expired = BoundedRouter(CONFIG.endpoint, deadline=0, opener=unavailable)
    with pytest.raises(WorkLimit):
        expired.filter_reachable(((41, -88),))
    assert len(calls) == MAX_PROVIDER_REQUESTS


def test_transport_does_not_follow_redirects_and_caps_response():
    with pytest.raises(RoutingProviderError):
        NoRedirect().redirect_request(
            Request(CONFIG.endpoint), None, 302, "", {}, "http://169.254.169.254/"
        )

    class Response:
        def read(self, size):
            return b"x" * size

        def close(self):
            pass

    with pytest.raises(RoutingProviderError):
        LimitedResponse(Response()).read(16 * 1024 * 1024)


def sleeping_worker(connection, config, request):
    time.sleep(60)


def successful_worker(connection, config, request):
    connection.send((200, {"ok": True}))
    connection.close()


def crashing_worker(connection, config, request):
    connection.close()


def test_hard_deadline_kills_child_and_releases_gate():
    calculator = Calculator(CONFIG, timeout=0.15, worker=sleeping_worker)
    before = set(multiprocessing.active_children())
    started = time.monotonic()
    with pytest.raises(APIError) as error:
        calculator.run(parse_request(json.dumps(BODY).encode()))
    assert error.value.status == 504
    assert time.monotonic() - started < 2
    assert set(multiprocessing.active_children()) == before
    calculator.worker = successful_worker
    calculator.timeout = 5
    assert calculator.run(None) == (200, {"ok": True})


def test_child_crash_is_service_error_and_releases_gate():
    calculator = Calculator(CONFIG, timeout=5, worker=crashing_worker)
    with pytest.raises(APIError) as error:
        calculator.run(None)
    assert error.value.code == "worker_unavailable"
    assert calculator.gate.acquire(blocking=False)


def test_concurrent_calculation_fails_immediately():
    calculator = Calculator(CONFIG)
    calculator.gate.acquire()
    with pytest.raises(APIError) as error:
        calculator.run(None)
    assert error.value.code == "busy"
    calculator.gate.release()


def test_rate_budget_refills_without_client_identifiers():
    clock = [0.0]
    budget = RateBudget(clock=lambda: clock[0])
    for _ in range(4):
        budget.consume()
    with pytest.raises(APIError) as error:
        budget.consume()
    assert error.value.status == 429
    clock[0] = 10
    budget.consume()


def test_worker_resource_creation_failure_releases_gate(monkeypatch):
    calculator = Calculator(CONFIG)

    class UnavailableContext:
        def Pipe(self, **kwargs):
            raise OSError("file descriptors exhausted")

    monkeypatch.setattr(multiprocessing, "get_context", lambda _: UnavailableContext())
    with pytest.raises(APIError) as error:
        calculator.run(None)
    assert error.value.status == 503
    assert error.value.code == "worker_unavailable"
    assert calculator.gate.acquire(blocking=False)


@pytest.mark.parametrize(
    "encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"]
)
def test_json_encoding_must_be_utf8(encoding):
    with pytest.raises(APIError) as error:
        parse_request(json.dumps(BODY).encode(encoding))
    assert error.value.status == 400
    assert error.value.code == "invalid_request"


def test_closed_calculator_cannot_start_new_work():
    calculator = Calculator(CONFIG, worker=successful_worker)
    assert calculator.close()
    assert calculator.close()
    with pytest.raises(APIError) as error:
        calculator.run(None)
    assert error.value.code == "shutting_down"
    assert calculator.active_process is None


def test_facility_response_labels_pin_layout_and_route_uncertainty():
    result = calculate(
        CONFIG, parse_request(json.dumps(BODY).encode()), router=PlaneRouter()
    )
    assert result["schema_version"] == 2
    assert "courses" not in result
    assert len({row["id"] for row in result["facilities"]}) == len(result["facilities"])
    assert any(
        row["coordinate_basis"] == "property_pin" for row in result["facilities"]
    )
    for row in result["facilities"]:
        assert row["id"].startswith("f-")
        assert row["layout_filter_status"] in {"confirmed", "unconfirmed"}
        assert "physical_holes" in row and "holes" not in row
        assert "access_note" in row
    metadata = result["metadata"]
    assert metadata["result_unit"] == "golf-facility"
    assert "entrance directions" in metadata["arrival_basis"]
    assert "ferries" in metadata["route_quality"]
    assert metadata["max_snap_distance_kilometers"] == 1


@pytest.mark.parametrize(
    "origins,state",
    [
        ([[33.45, -112.07], [33.60, -112.20]], "AZ"),
        ([[47.25, -122.45], [47.30, -122.35]], "WA"),
    ],
)
def test_national_facility_candidates_are_available_outside_chicago(origins, state):
    result = calculate(
        CONFIG,
        parse_request(json.dumps({**BODY, "origins": origins}).encode()),
        router=PlaneRouter(),
    )
    assert result["facilities"]
    assert all(row["state"] == state for row in result["facilities"])
    assert len(result["facilities"]) <= 24
    assert result["metadata"]["provider_requests"] <= MAX_PROVIDER_REQUESTS
    assert result["metadata"]["matrix_cells"] <= MAX_MATRIX_CELLS
