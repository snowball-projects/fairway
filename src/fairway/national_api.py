"""Private national calculation boundary, independent of the public WSGI app."""

import json
import multiprocessing
from dataclasses import dataclass
from math import isfinite
from threading import BoundedSemaphore, Lock
from time import monotonic
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from modo import (
    NationwideEstimator,
    RoutingCoverageError,
    RoutingProviderError,
    ValhallaHTTPProvider,
)
from modo.nationwide import LOWER_48_BOUNDS

from .facilities import load_facility_catalog
from .national import calculate_national_facility_ranking
from .national_modo import ModoMatrixProvider, ModoPromisingAreaProvider

MAX_BODY_BYTES = 4096
MAX_ORIGINS = 8
MAX_AREAS = 8
MAX_COURSES = 24
MAX_PROVIDER_REQUESTS = 32
MAX_MATRIX_CELLS = 4096
MAX_CANDIDATES = 256
MAX_RESPONSE_BYTES = 1024 * 1024
CALCULATION_SECONDS = 30


class APIError(Exception):
    def __init__(self, status, code, message, *, retryable=False):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)

    def document(self):
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        }


class WorkLimit(RoutingProviderError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RoutingProviderError("routing redirects are disabled")


@dataclass(frozen=True)
class APIConfig:
    # Operator configuration only. Never accepted in a request.
    endpoint: str
    catalog_path: str
    routing_dataset: str

    def __post_init__(self):
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "valhalla"}
            or parsed.port is None
            or not 1 <= parsed.port <= 65535
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("routing endpoint must be an approved private address")
        if (
            not isinstance(self.routing_dataset, str)
            or not 1 <= len(self.routing_dataset) <= 128
            or any(
                c not in "abcdefghijklmnopqrstuvwxyz0123456789-_."
                for c in self.routing_dataset
            )
        ):
            raise ValueError("a sanitized routing dataset identifier is required")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def parse_request(raw):
    if len(raw) > MAX_BODY_BYTES:
        raise APIError(413, "body_too_large", "JSON body exceeds 4096 bytes.")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object
        )
        if not isinstance(value, dict) or set(value) != {
            "origins",
            "objective",
            "holes",
        }:
            raise ValueError
        origins = value["origins"]
        if not isinstance(origins, list) or not 2 <= len(origins) <= MAX_ORIGINS:
            raise ValueError
        for point in origins:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(type(c) not in {float, int} or not isfinite(c) for c in point)
                or not -90 <= point[0] <= 90
                or not -180 <= point[1] <= 180
            ):
                raise ValueError
        if value["objective"] not in ("maximum", "combined"):
            raise ValueError
        holes = value["holes"]
        if (
            not isinstance(holes, list)
            or not 1 <= len(holes) <= 2
            or any(type(h) is not int or h not in {9, 18} for h in holes)
            or len(set(holes)) != len(holes)
        ):
            raise ValueError
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise APIError(
            400,
            "invalid_request",
            "Expected origins (2-8 coordinate pairs), objective (maximum or combined), "
            "and holes (9, 18, or both), with no extra fields.",
        ) from None
    origins = tuple(tuple(map(float, point)) for point in origins)
    if any(not LOWER_48_BOUNDS.contains(point) for point in origins):
        raise APIError(
            422, "outside_coverage", "Origins must be within lower-48 coverage."
        )
    return origins, value["objective"], tuple(holes)


class BoundedRouter:
    """One request's modo provider, without coordinates retained across requests."""

    def __init__(self, endpoint, *, deadline, opener=None):
        self.deadline = deadline
        self.requests = 0
        self.cells = 0
        self.candidates = set()
        transport = opener or build_opener(ProxyHandler({}), NoRedirect()).open

        def bounded_open(request, timeout):
            remaining = self.deadline - monotonic()
            if remaining <= 0:
                raise WorkLimit("deadline exhausted")
            if self.requests >= MAX_PROVIDER_REQUESTS:
                raise WorkLimit("request budget exhausted")
            self.requests += 1
            response = transport(request, timeout=min(timeout, remaining))
            # modo's adapter reads up to 16 MiB; impose the narrower API policy.
            return LimitedResponse(response)

        self.provider = ValhallaHTTPProvider(
            endpoint, timeout_seconds=5, cache_size=0, opener=bounded_open
        )

    def filter_reachable(self, coordinates):
        coordinates = tuple(coordinates)
        if len(coordinates) > 128:
            raise WorkLimit("locate batch exhausted")
        return self.provider.filter_reachable(coordinates)

    def matrix(self, origins, targets):
        origins, targets = tuple(origins), tuple(targets)
        if len(origins) > MAX_ORIGINS or len(targets) > 40:
            raise WorkLimit("matrix dimensions exhausted")
        self.cells += len(origins) * len(targets)
        self.candidates.update(targets)
        if self.cells > MAX_MATRIX_CELLS or len(self.candidates) > MAX_CANDIDATES:
            raise WorkLimit("matrix work budget exhausted")
        return self.provider.matrix(origins, targets)


class LimitedResponse:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.response.close()

    def read(self, size):
        raw = self.response.read(min(size, MAX_RESPONSE_BYTES + 1))
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RoutingProviderError("routing response exceeds policy")
        return raw


def calculate(config, request, *, router=None):
    origins, objective, holes = request
    catalog = load_facility_catalog(config.catalog_path)
    router = router or BoundedRouter(
        config.endpoint, deadline=monotonic() + CALCULATION_SECONDS
    )
    estimator = NationwideEstimator(
        router,
        coarse_candidate_limit=81,
        refinement_rounds=2,
        finalists_per_round=6,
        matrix_target_limit=40,
    )
    result = calculate_national_facility_ranking(
        origins,
        objective,
        catalog.facilities,
        ModoPromisingAreaProvider(estimator, facility_radius_kilometers=25),
        ModoMatrixProvider(router),
        holes=holes,
        area_limit=MAX_AREAS,
        shortlist_limit=MAX_COURSES,
    )
    if not result.ranking.facilities:
        raise APIError(
            422,
            "no_routable_facilities",
            "No shortlisted facility is reachable by every origin.",
        )
    return {
        "schema_version": 2,
        "objective": objective,
        "facilities": [
            {
                "id": row.facility.identifier,
                "name": row.facility.name,
                "rank": row.rank,
                "state": row.facility.state,
                "physical_holes": row.facility.physical_holes,
                "public_layout_holes": row.facility.public_layout_holes,
                "inventory_complete": row.facility.inventory_complete,
                "coordinate_basis": row.facility.coordinate_basis,
                "layout_filter_status": row.facility.layout_filter_status(holes),
                "access_note": row.facility.access_note,
                "website": row.facility.website,
                "routing_coordinate": row.facility.routing_coordinate,
                "travel_times_milliseconds": row.travel_times_milliseconds,
                "combined_milliseconds": row.combined_milliseconds,
                "maximum_milliseconds": row.maximum_milliseconds,
            }
            for row in result.ranking.facilities
        ],
        "unranked_facilities": [
            {"id": row.facility.identifier, "reason": row.reason}
            for row in result.ranking.unranked_facilities
        ],
        "metadata": {
            "approximate": True,
            "global_optimum": False,
            "traffic_basis": "unaware",
            "departure": None,
            "area_search": dict(result.areas.metadata.provenance),
            "matrix_strategy": result.matrix.metadata.strategy,
            "routing_provider": "modo-valhalla",
            "routing_dataset": config.routing_dataset,
            "routing_dataset_identity": "operator-declared, not independently verified by API",
            "catalog_id": catalog.identifier,
            "catalog_sha256": catalog.sha256,
            "catalog_as_of": catalog.as_of,
            "catalog_facility_count": len(catalog.facilities),
            "shortlisted_facility_count": len(result.shortlisted_facilities),
            "catalog_complete": False,
            "result_unit": "golf-facility",
            "max_snap_distance_kilometers": 1,
            "snapped_coordinates_reported": False,
            "arrival_basis": "approximate drive to existing catalog point, not entrance directions",
            "layout_filter_basis": "single9/18 requires explicit public layout evidence; both admits unconfirmed inventories",
            "route_quality": "matrix does not classify ferries or private/cart-path approaches; access and timetables unverified",
            "provider_requests": router.requests,
            "matrix_cells": router.cells,
            "attribution": "Road data © OpenStreetMap contributors, ODbL 1.0",
        },
    }


def _worker(connection, config, request):
    try:
        result = (200, calculate(config, request))
    except APIError as error:
        result = error.status, error.document()
    except WorkLimit:
        result = (
            503,
            APIError(
                503,
                "work_limit",
                "Calculation exceeded its work budget.",
                retryable=True,
            ).document(),
        )
    except RoutingCoverageError:
        result = (
            422,
            APIError(
                422, "outside_coverage", "Origins have no usable shared road coverage."
            ).document(),
        )
    except RoutingProviderError:
        result = (
            502,
            APIError(
                502,
                "routing_unavailable",
                "Routing provider could not complete the calculation.",
                retryable=True,
            ).document(),
        )
    except ValueError:
        result = (
            422,
            APIError(
                422,
                "no_eligible_facilities",
                "No eligible public facility was found within the promising areas.",
            ).document(),
        )
    except Exception:  # noqa: BLE001 - final child boundary must sanitize faults
        # Never send provider messages, local paths, URLs, traceback or coordinates.
        result = (
            500,
            APIError(
                500, "calculation_failed", "Calculation failed its contract checks."
            ).document(),
        )
    try:
        connection.send(result)
    finally:
        connection.close()


class Calculator:
    """One tracked child, with bounded cleanup on deadlines and normal shutdown."""

    def __init__(self, config, *, timeout=CALCULATION_SECONDS, worker=_worker):
        self.config = config
        self.timeout = timeout
        self.worker = worker
        self.gate = BoundedSemaphore(1)
        self.lifecycle_lock = Lock()
        self.active_process = None
        self.closing = False

    def _stop_active_locked(self):
        process = self.active_process
        if process is None:
            return True
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=0.25)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            if process.is_alive():
                # Never admit more work after an unreaped worker. An external
                # supervisor must enforce whole-process-group termination.
                self.closing = True
                return False
        process.close()
        self.active_process = None
        return True

    def close(self):
        with self.lifecycle_lock:
            self.closing = True
            return self._stop_active_locked()

    def run(self, request):
        if not self.gate.acquire(blocking=False):
            raise APIError(
                503, "busy", "A calculation is already running.", retryable=True
            )
        receive = send = None
        deadline = monotonic() + self.timeout
        try:
            context = multiprocessing.get_context("spawn")
            receive, send = context.Pipe(duplex=False)
            with self.lifecycle_lock:
                if self.closing:
                    raise APIError(
                        503,
                        "shutting_down",
                        "Calculation service is stopping.",
                        retryable=True,
                    )
                process = context.Process(
                    target=self.worker, args=(send, self.config, request)
                )
                self.active_process = process
                process.start()
            send.close()
            if not receive.poll(max(0, deadline - monotonic())):
                raise APIError(
                    504,
                    "deadline_exceeded",
                    "Calculation exceeded 30 seconds.",
                    retryable=True,
                )
            try:
                return receive.recv()
            except EOFError:
                raise APIError(
                    503,
                    "worker_unavailable",
                    "Calculation worker exited.",
                    retryable=True,
                ) from None
        except OSError:
            raise APIError(
                503,
                "worker_unavailable",
                "Calculation worker could not start or communicate.",
                retryable=True,
            ) from None
        finally:
            if send is not None:
                send.close()
            if receive is not None:
                receive.close()
            with self.lifecycle_lock:
                self._stop_active_locked()
            self.gate.release()


class RateBudget:
    """Identifier-free process budget. Restart resets it; use one process."""

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.updated = clock()
        self.tokens = 4.0
        self.lock = Lock()

    def consume(self):
        with self.lock:
            now = self.clock()
            self.tokens = min(4, self.tokens + max(0, now - self.updated) / 10)
            self.updated = now
            if self.tokens < 1:
                raise APIError(
                    429,
                    "rate_limited",
                    "Calculation rate budget exhausted.",
                    retryable=True,
                )
            self.tokens -= 1
