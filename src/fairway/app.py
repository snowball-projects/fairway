"""Small WSGI application for fairway."""

import json
import logging
import mimetypes
import os
from datetime import UTC
from hashlib import sha256
from importlib.metadata import version
from math import ceil, isfinite
from pathlib import Path
from re import fullmatch
from threading import BoundedSemaphore, Lock
from time import monotonic

import networkx as nx
from modo import CompactRoadGraph

from .course_index import CourseDistanceIndex
from .courses import load_course_catalog
from .matrix import (
    MAX_SNAP_DISTANCE_KILOMETERS,
    DestinationFailure,
    MatrixMetadata,
    MatrixProviderUnavailable,
    OutsideRoadCoverage,
    StaticModoMatrix,
    TrafficBasis,
    validate_road_snapshot,
)
from .paths import (
    COURSE_CATALOG_PATH as DEFAULT_COURSE_CATALOG_PATH,
)
from .paths import (
    SNAPSHOT_CATALOG_PATH,
    graph_path,
)
from .scoring import SCORE_RESOLUTION_MILLISECONDS, canonical_milliseconds
from .snapshots import load_catalog
from .tomtom import DEFAULT_DAILY_CELL_LIMIT, TomTomMatrix


def _environment(name, default=None):
    value = os.environ.get(name)
    return default if value in (None, "") else value


def _configure_live_matrix():
    key = _environment("TOMTOM_API_KEY")
    provider = _environment("FAIRWAY_MATRIX_PROVIDER", "tomtom" if key else "static")
    if provider == "static":
        return None
    if provider != "tomtom":
        raise RuntimeError("FAIRWAY_MATRIX_PROVIDER must be 'static' or 'tomtom'")
    try:
        limit = int(
            _environment("FAIRWAY_TOMTOM_DAILY_CELLS", DEFAULT_DAILY_CELL_LIMIT)
        )
        return TomTomMatrix(key, daily_cell_limit=limit)
    except (TypeError, ValueError):
        raise RuntimeError(
            "TomTom requires a key and a valid daily cell limit"
        ) from None


_live_matrix = _configure_live_matrix()
STATIC = Path(__file__).with_name("static")
ROAD_CATALOG_PATH = Path(_environment("FAIRWAY_CATALOG", str(SNAPSHOT_CATALOG_PATH)))
ROAD_CATALOG = load_catalog(ROAD_CATALOG_PATH)
SNAPSHOT = _environment("FAIRWAY_SNAPSHOT", "chicago-static-v1")
try:
    SNAPSHOT_METADATA = next(
        item for item in ROAD_CATALOG if item.identifier == SNAPSHOT
    )
except StopIteration as error:
    raise RuntimeError(f"unknown configured road snapshot: {SNAPSHOT}") from error
COST_PROFILE = SNAPSHOT_METADATA.cost_profile
GRAPH_PATH = str(graph_path(SNAPSHOT_METADATA.file, ROAD_CATALOG_PATH))
COURSE_CATALOG_PATH = Path(
    _environment("FAIRWAY_COURSE_CATALOG", str(DEFAULT_COURSE_CATALOG_PATH))
)
COURSE_CATALOG = load_course_catalog(COURSE_CATALOG_PATH)
COURSES = COURSE_CATALOG.courses
if any(
    not SNAPSHOT_METADATA.contains([course.routing_coordinate]) for course in COURSES
):
    raise RuntimeError("configured course catalog exceeds the road snapshot core")

MAX_REQUEST_BYTES = 32_768
MAX_ORIGINS = 8
COURSE_INDEX_PATH = _environment("FAIRWAY_COURSE_INDEX")
COURSE_INDEX_SHA256 = _environment("FAIRWAY_COURSE_INDEX_SHA256")
if bool(COURSE_INDEX_PATH) != bool(COURSE_INDEX_SHA256) or (
    COURSE_INDEX_SHA256 is not None
    and fullmatch(r"[0-9a-f]{64}", COURSE_INDEX_SHA256) is None
):
    raise RuntimeError(
        "FAIRWAY_COURSE_INDEX and its valid SHA-256 must be configured together"
    )
CONTENT_SECURITY_POLICY = "default-src 'self'; base-uri 'none'; connect-src 'self' https://photon.komoot.io; font-src 'self'; form-action 'none'; frame-ancestors 'none'; frame-src 'none'; img-src 'self' data: https://tile.openstreetmap.org; object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; worker-src 'none'"
SECURITY_HEADERS = (
    ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    (
        "Permissions-Policy",
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    ),
    # OpenStreetMap's tile policy requires a Referer identifying the app.
    # Send only the origin, never the full URL or its query.
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Strict-Transport-Security", "max-age=31536000"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
)
LOGGER = logging.getLogger(__name__)
_graph = None
_graph_sha256 = None
_course_distance_index = None
_compute_gate = BoundedSemaphore(1)


class _TokenBucket:
    """Small identifier-free process-global request budget."""

    def __init__(self, capacity, refill_per_second, clock=monotonic):
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        if (
            not isfinite(self.capacity)
            or self.capacity < 1
            or not isfinite(self.refill_per_second)
            or self.refill_per_second <= 0
        ):
            raise ValueError("token bucket values must be finite and positive")
        self.tokens = float(capacity)
        self.updated = clock()
        self.clock = clock
        self.lock = Lock()

    def consume(self):
        with self.lock:
            now = self.clock()
            self.tokens = min(
                self.capacity,
                self.tokens + max(0.0, now - self.updated) * self.refill_per_second,
            )
            self.updated = now
            if self.tokens >= 1:
                self.tokens -= 1
                return 0
            return max(1, ceil((1 - self.tokens) / self.refill_per_second))


_ranking_tokens = _TokenBucket(capacity=12, refill_per_second=0.5)


class _UnprocessableRequest(Exception):
    """A valid request that the current road snapshot cannot calculate."""


class _BadRequest(Exception):
    """A request whose JSON or input values are invalid."""


class _PayloadTooLarge(Exception):
    """A request body that exceeds the hosted-service byte limit."""


class _UnsupportedMediaType(Exception):
    """A ranking request that is not JSON."""


class _ServiceBusy(Exception):
    """The bounded local calculation slot is already occupied."""


class _RateLimited(Exception):
    """The identifier-free global calculation budget is exhausted."""

    def __init__(self, retry_after):
        super().__init__("fairway's calculation limit was reached; try again shortly")
        self.retry_after = retry_after


def _digest_source(source):
    digest = sha256()
    while chunk := source.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _road():
    global _graph, _graph_sha256
    if _graph is None:
        with Path(GRAPH_PATH).open("rb") as source:
            _graph_sha256 = _digest_source(source)
            if _graph_sha256 != SNAPSHOT_METADATA.sha256:
                _graph_sha256 = None
                raise RuntimeError("road snapshot checksum does not match")
            source.seek(0)
            road = CompactRoadGraph.load(source)
        validate_road_snapshot(road)
        _graph = road
    return _graph


def _course_index(road):
    global _course_distance_index
    if COURSE_INDEX_PATH is None:
        return None
    if _course_distance_index is None:
        with Path(COURSE_INDEX_PATH).open("rb") as source:
            if _digest_source(source) != COURSE_INDEX_SHA256:
                raise RuntimeError("course distance index checksum does not match")
            source.seek(0)
            course_distance_index = CourseDistanceIndex.load(
                source,
                road_snapshot_sha256=SNAPSHOT_METADATA.sha256,
                course_catalog_sha256=COURSE_CATALOG.sha256,
                vertex_count=len(road._vertices),
                expected_course_ids=(course.identifier for course in COURSES),
            )
        course_vertices = road.nearest_vertices(
            course.routing_coordinate for course in COURSES
        )
        _course_distance_index = course_distance_index.validate_against(
            road, course_vertices
        )
    return _course_distance_index


def _matrix_provider():
    """Return the configured provider without silently changing its model."""
    if _live_matrix is not None:
        return _live_matrix
    road = _road()
    if _graph_sha256 is None:
        raise RuntimeError("road snapshot was not checksum-verified")
    course_index = _course_index(road)
    metadata = MatrixMetadata(
        provider="modo-static",
        traffic_basis=TrafficBasis.UNAWARE,
        provenance=(
            ("road_snapshot", SNAPSHOT),
            ("road_snapshot_sha256", _graph_sha256),
            ("cost_profile", COST_PROFILE),
            ("modo", version("modo")),
            (
                "course_index_sha256",
                COURSE_INDEX_SHA256 if course_index is not None else None,
            ),
        ),
    )
    return StaticModoMatrix(
        road,
        MAX_SNAP_DISTANCE_KILOMETERS,
        course_index=course_index,
        metadata=metadata,
    )


def _timestamp(value):
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _matrix_provenance(metadata):
    result = {
        "matrix_provider": metadata.provider,
        "matrix_strategy": metadata.strategy,
        "traffic_basis": metadata.traffic_basis.value,
        "departure_mode": (
            metadata.departure.mode.value if metadata.departure is not None else None
        ),
        "departure_time": _timestamp(metadata.departure_time),
        "matrix_calculated_at": _timestamp(metadata.calculated_at),
        "traffic_data_as_of": _timestamp(metadata.traffic_data_as_of),
    }
    for key, value in metadata.provenance:
        if key in result:
            raise RuntimeError(f"matrix provenance uses reserved key: {key}")
        result[key] = value
    return result


def _json(start_response, status, value, extra_headers=()):
    body = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            *SECURITY_HEADERS,
            *extra_headers,
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
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise _BadRequest("request body must be valid UTF-8 JSON") from error
    if not isinstance(request, dict):
        raise _BadRequest("JSON body must be an object")
    return request


def _coordinates(value):
    if not isinstance(value, list):
        raise _BadRequest("origins must be a list")
    if any(
        not isinstance(point, list)
        or len(point) != 2
        or any(type(coordinate) not in {int, float} for coordinate in point)
        for point in value
    ):
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
    if not isinstance(value, str) or value not in {"combined", "maximum"}:
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


def _validate_matrix_contract(matrix, origins, candidates):
    expected_origins = tuple(origins)
    expected_ids = tuple(course.identifier for course in candidates)
    expected_destinations = tuple(course.routing_coordinate for course in candidates)
    if matrix.origin_coordinates != expected_origins:
        raise RuntimeError("matrix provider changed origin identity or order")
    if matrix.destination_ids != expected_ids:
        raise RuntimeError("matrix provider changed destination identity or order")
    if tuple(item.coordinate for item in matrix.destinations) != expected_destinations:
        raise RuntimeError("matrix provider changed destination coordinates or order")
    return matrix


def _config(start_response):
    return _json(
        start_response,
        "200 OK",
        {
            "core_bounds": list(SNAPSHOT_METADATA.core_bounds),
            "max_origins": MAX_ORIGINS,
            "course_catalog": {
                "title": COURSE_CATALOG.title,
                "as_of": COURSE_CATALOG.as_of,
            },
            "routing": {
                "provider": "tomtom-matrix-v2"
                if _live_matrix is not None
                else "modo-static",
                "description": (
                    "Drive times use TomTom's live and historical traffic for leaving "
                    "now. Confirmed coordinates are sent from fairway to TomTom."
                    if _live_matrix is not None
                    else "Drive times use one static road snapshot without traffic. "
                    "Confirmed coordinates stay within the fairway service."
                ),
            },
        },
    )


def _rankings(environ, start_response):
    content_type = environ.get("CONTENT_TYPE", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise _UnsupportedMediaType("content type must be application/json")
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
    if not _compute_gate.acquire(blocking=False):
        raise _ServiceBusy("fairway is already calculating another ranking")
    try:
        retry_after = _ranking_tokens.consume()
        if retry_after:
            raise _RateLimited(retry_after)
        try:
            provider = _matrix_provider()
            matrix = provider.calculate(
                origins,
                (course.routing_coordinate for course in candidates),
                (course.identifier for course in candidates),
                departure=None,
            )
            _validate_matrix_contract(matrix, origins, candidates)
        except OutsideRoadCoverage as error:
            raise _UnprocessableRequest(
                f"Golfer {error.point_index + 1} is more than "
                f"{error.limit_kilometers:g} km from a modeled road."
            ) from error
        except nx.NetworkXNoPath as error:
            raise _UnprocessableRequest(
                "These origins have no reachable road route."
            ) from error
    finally:
        _compute_gate.release()

    ranked = []
    unranked = []
    for course, destination in zip(candidates, matrix.destinations, strict=True):
        if isinstance(destination, DestinationFailure):
            unranked.append(
                {
                    "id": course.identifier,
                    "name": course.name,
                    "reason": destination.reason,
                }
            )
            continue
        travel_times_milliseconds = canonical_milliseconds(
            destination.travel_times_seconds
        )
        combined_milliseconds = sum(travel_times_milliseconds)
        maximum_milliseconds = max(travel_times_milliseconds)
        item = _course(course)
        item.update(
            {
                "road_coordinate": (
                    list(destination.road_coordinate)
                    if destination.road_coordinate is not None
                    else None
                ),
                "snap_distance_kilometers": destination.snap_distance_kilometers,
                "travel_times_seconds": [
                    value / 1000 for value in travel_times_milliseconds
                ],
                "combined_seconds": combined_milliseconds / 1000,
                "maximum_seconds": maximum_milliseconds / 1000,
                "_combined_milliseconds": combined_milliseconds,
                "_maximum_milliseconds": maximum_milliseconds,
            }
        )
        ranked.append(item)
    if not ranked:
        raise _UnprocessableRequest(
            "No selected course is reachable from every golfer on the current roads."
        )
    primary = (
        "_combined_milliseconds" if objective == "combined" else "_maximum_milliseconds"
    )
    secondary = (
        "_maximum_milliseconds" if objective == "combined" else "_combined_milliseconds"
    )
    ranked.sort(
        key=lambda item: (
            item[primary],
            item[secondary],
            item["name"],
            item["id"],
        )
    )
    for rank, item in enumerate(ranked, 1):
        del item["_combined_milliseconds"]
        del item["_maximum_milliseconds"]
        item["rank"] = rank
    provenance = {
        "course_catalog": COURSE_CATALOG.identifier,
        "course_catalog_as_of": COURSE_CATALOG.as_of,
        "course_catalog_sha256": COURSE_CATALOG.sha256,
        "score_resolution_seconds": SCORE_RESOLUTION_MILLISECONDS / 1000,
    }
    matrix_provenance = _matrix_provenance(matrix.metadata)
    overlap = provenance.keys() & matrix_provenance.keys()
    if overlap:
        raise RuntimeError(
            f"matrix provenance conflicts with fairway provenance: {sorted(overlap)}"
        )
    provenance.update(matrix_provenance)
    return _json(
        start_response,
        "200 OK",
        {
            "objective": objective,
            "holes": sorted(holes),
            "origin_road_coordinates": [
                list(coordinate) if coordinate is not None else None
                for coordinate in matrix.origin_road_coordinates
            ],
            "origin_snap_distances_kilometers": list(
                matrix.origin_snap_distances_kilometers
            ),
            "courses": ranked,
            "unranked_courses": unranked,
            "provenance": provenance,
        },
    )


def _static(start_response, path):
    name = "index.html" if path == "/" else path.removeprefix("/")
    try:
        file = (STATIC / name).resolve()
        valid = file.is_relative_to(STATIC.resolve()) and file.is_file()
    except (OSError, RuntimeError, ValueError):
        valid = False
    if not valid:
        return _json(start_response, "404 Not Found", {"error": "not found"})
    body = file.read_bytes()
    content_type = mimetypes.guess_type(file)[0] or "application/octet-stream"
    if content_type.startswith("text/") or content_type in {
        "application/javascript",
        "application/json",
    }:
        content_type += "; charset=utf-8"
    start_response(
        "200 OK",
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-cache"),
            *SECURITY_HEADERS,
        ],
    )
    return [body]


def _method_not_allowed(start_response, allow):
    return _json(
        start_response,
        "405 Method Not Allowed",
        {"error": "method not allowed"},
        (("Allow", allow),),
    )


def _application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    try:
        if path == "/health":
            if method not in {"GET", "HEAD"}:
                return _method_not_allowed(start_response, "GET, HEAD")
            _matrix_provider()
            return _json(
                start_response,
                "200 OK",
                {
                    "status": "ok",
                    "version": version("fairway"),
                    "matrix_provider": (
                        "tomtom-matrix-v2"
                        if _live_matrix is not None
                        else "modo-static"
                    ),
                },
            )
        if path == "/api/config":
            if method not in {"GET", "HEAD"}:
                return _method_not_allowed(start_response, "GET, HEAD")
            return _config(start_response)
        if path == "/api/rankings":
            if method != "POST":
                return _method_not_allowed(start_response, "POST")
            return _rankings(environ, start_response)
        if method in {"GET", "HEAD"}:
            return _static(start_response, path)
        return _method_not_allowed(start_response, "GET, HEAD")
    except _PayloadTooLarge as error:
        return _json(start_response, "413 Payload Too Large", {"error": str(error)})
    except _UnprocessableRequest as error:
        return _json(start_response, "422 Unprocessable Entity", {"error": str(error)})
    except _BadRequest as error:
        return _json(start_response, "400 Bad Request", {"error": str(error)})
    except _UnsupportedMediaType as error:
        return _json(
            start_response, "415 Unsupported Media Type", {"error": str(error)}
        )
    except _ServiceBusy as error:
        return _json(
            start_response,
            "503 Service Unavailable",
            {"error": str(error)},
            (("Retry-After", "1"),),
        )
    except MatrixProviderUnavailable as error:
        return _json(
            start_response,
            "503 Service Unavailable",
            {"error": str(error)},
            (("Retry-After", str(error.retry_after_seconds)),),
        )
    except _RateLimited as error:
        return _json(
            start_response,
            "429 Too Many Requests",
            {"error": str(error)},
            (("Retry-After", str(error.retry_after)),),
        )
    except Exception:
        LOGGER.exception("Unhandled fairway request failure: %r %r", method, path)
        return _json(
            start_response,
            "500 Internal Server Error",
            {"error": "fairway could not calculate this request"},
        )


def application(environ, start_response):
    """Serve fairway and its same-origin ranking API."""
    body = _application(environ, start_response)
    return [] if environ.get("REQUEST_METHOD", "GET") == "HEAD" else body
