"""Bounded, server-side TomTom Matrix Routing v2 adapter."""

import json
from datetime import UTC, datetime
from http.client import HTTPException, HTTPSConnection
from threading import Lock
from time import monotonic
from urllib.parse import urlencode

from .matrix import (
    DepartureMode,
    DepartureRequest,
    DestinationFailure,
    DestinationTimes,
    MatrixMetadata,
    MatrixProviderUnavailable,
    MatrixResult,
    TrafficBasis,
    _require_coordinate,
)

MAX_MATRIX_CELLS = 100
MAX_RESPONSE_BYTES = 1_048_576
REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_DAILY_CELL_LIMIT = 80


def _utcnow():
    return datetime.now(UTC)


def _timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("provider departure time lacks a UTC offset")
    return result.astimezone(UTC)


def _post_matrix(key, payload):
    """Use one fixed HTTPS endpoint, with no redirects, retries, or URL logging."""
    deadline = monotonic() + REQUEST_TIMEOUT_SECONDS
    connection = HTTPSConnection("api.tomtom.com", timeout=REQUEST_TIMEOUT_SECONDS)
    response = None
    try:
        connection.request(
            "POST",
            "/routing/matrix/2?" + urlencode({"key": key}),
            body=json.dumps(payload, allow_nan=False).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError
        socket = connection.sock
        socket.settimeout(remaining)
        response = connection.getresponse()
        if response.status != 200:
            raise MatrixProviderUnavailable()
        received = bytearray()
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError
            # Retain the socket because Connection: close may detach it from
            # the connection while the response stream still owns it.
            socket.settimeout(remaining)
            chunk = response.read1(min(65_536, MAX_RESPONSE_BYTES + 1 - len(received)))
            if monotonic() > deadline:
                raise TimeoutError
            if not chunk:
                break
            received.extend(chunk)
            if len(received) > MAX_RESPONSE_BYTES:
                raise ValueError("provider response exceeds its size limit")
        return json.loads(received)
    except (HTTPException, OSError, TypeError, ValueError, RecursionError):
        # Provider messages and exception URLs may contain the API key or
        # coordinates. Discard their content, including chained tracebacks.
        raise MatrixProviderUnavailable() from None
    finally:
        if response is not None:
            response.close()
        connection.close()


class TomTomMatrix:
    """Leave-now car travel times with live and historical traffic.

    The cell budget is an identifier-free operational guard per process and UTC
    day. It is deliberately conservative and is not a provider billing cap.
    """

    def __init__(self, api_key, *, daily_cell_limit=DEFAULT_DAILY_CELL_LIMIT):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("TomTom requires TOMTOM_API_KEY")
        if type(daily_cell_limit) is not int or not 0 <= daily_cell_limit <= 100_000:
            raise ValueError("TomTom daily cell limit must be between 0 and 100000")
        self._api_key = api_key
        self.daily_cell_limit = daily_cell_limit
        self._budget_day = None
        self._used_cells = 0
        self._budget_lock = Lock()

    def _reserve(self, cells):
        today = _utcnow().date()
        with self._budget_lock:
            if self._budget_day != today:
                self._budget_day = today
                self._used_cells = 0
            if self._used_cells + cells > self.daily_cell_limit:
                raise MatrixProviderUnavailable(3600)
            # Count attempts, including timeouts: the provider may have billed
            # them even when a response never reaches this process.
            self._used_cells += cells

    def calculate(self, origins, destinations, destination_ids=None, *, departure=None):
        origins = tuple(tuple(point) for point in origins)
        destinations = tuple(tuple(point) for point in destinations)
        cells = len(origins) * len(destinations)
        if not 1 <= cells <= MAX_MATRIX_CELLS:
            raise ValueError("TomTom matrices require between 1 and 100 cells")
        for point in origins + destinations:
            _require_coordinate("matrix coordinate", point)
        if destination_ids is not None:
            destination_ids = tuple(destination_ids)
            if len(destination_ids) != len(destinations) or any(
                not isinstance(identifier, str) or not identifier
                for identifier in destination_ids
            ):
                raise ValueError("destination identifiers must match destinations")
        departure = departure or DepartureRequest.leave_now()
        if not isinstance(departure, DepartureRequest):
            raise TypeError("departure must be a DepartureRequest")
        if departure.mode is not DepartureMode.LEAVE_NOW:
            raise ValueError(
                "fairway's TomTom adapter supports leave-now requests only"
            )
        self._reserve(cells)
        submitted_at = _utcnow()
        payload = {
            "origins": [
                {"point": {"latitude": latitude, "longitude": longitude}}
                for latitude, longitude in origins
            ],
            "destinations": [
                {"point": {"latitude": latitude, "longitude": longitude}}
                for latitude, longitude in destinations
            ],
            "options": {
                "departAt": "now",
                "traffic": "live",
                "routeType": "fastest",
                "travelMode": "car",
            },
        }
        value = _post_matrix(self._api_key, payload)
        try:
            return self._result(
                value, origins, destinations, destination_ids, departure, submitted_at
            )
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            raise MatrixProviderUnavailable() from None

    def _result(
        self, value, origins, destinations, destination_ids, departure, submitted_at
    ):
        cells = len(origins) * len(destinations)
        data = value["data"]
        statistics = value["statistics"]
        if not isinstance(data, list) or len(data) != cells:
            raise ValueError("provider returned an incomplete matrix")
        if (
            any(
                type(statistics[name]) is not int or statistics[name] < 0
                for name in ("totalCount", "successes", "failures")
            )
            or statistics["totalCount"] != cells
            or statistics["successes"] + statistics["failures"] != cells
        ):
            raise ValueError("provider matrix statistics do not match")
        times = [[None] * len(origins) for _point in destinations]
        seen = set()
        unreachable = set()
        departures = []
        failures = 0
        for cell in data:
            origin = cell["originIndex"]
            destination = cell["destinationIndex"]
            if (
                type(origin) is not int
                or type(destination) is not int
                or not 0 <= origin < len(origins)
                or not 0 <= destination < len(destinations)
                or (origin, destination) in seen
            ):
                raise ValueError("provider matrix cell identity is invalid")
            seen.add((origin, destination))
            if "detailedError" in cell:
                failure = cell["detailedError"]
                if failure.get("code") == "CELL_PROCESSING_ERROR":
                    failure = failure.get("innerError", {})
                if failure.get("code") != "NO_ROUTE_FOUND" or "routeSummary" in cell:
                    raise ValueError("provider matrix cell failed")
                unreachable.add(destination)
                failures += 1
                continue
            summary = cell["routeSummary"]
            seconds = summary["travelTimeInSeconds"]
            if type(seconds) is not int or seconds < 0:
                raise ValueError("provider returned an invalid travel time")
            times[destination][origin] = seconds
            departures.append(_timestamp(summary["departureTime"]))
        if failures != statistics["failures"]:
            raise ValueError("provider failure count does not match")
        calculated_at = _utcnow()
        if departures and (
            (submitted_at - min(departures)).total_seconds() > 60
            or (max(departures) - calculated_at).total_seconds() > 60
        ):
            raise ValueError("provider leave-now departure times are inconsistent")
        return MatrixResult(
            origin_coordinates=origins,
            origin_road_coordinates=(None,) * len(origins),
            origin_snap_distances_kilometers=(None,) * len(origins),
            destination_ids=destination_ids,
            destinations=tuple(
                DestinationFailure(point, None, None, "unreachable")
                if index in unreachable
                else DestinationTimes(point, None, None, tuple(times[index]))
                for index, point in enumerate(destinations)
            ),
            metadata=MatrixMetadata(
                provider="tomtom-matrix-v2",
                strategy="synchronous-matrix",
                traffic_basis=TrafficBasis.BLENDED,
                departure=departure,
                departure_time=min(departures, default=submitted_at),
                calculated_at=calculated_at,
                provenance=(
                    ("tomtom_traffic", "live"),
                    ("travel_mode", "car"),
                    ("route_type", "fastest"),
                    ("departure_time_basis", "earliest-route-departure"),
                    (
                        "latest_departure_time",
                        max(departures).isoformat() if departures else None,
                    ),
                ),
            ),
        )
