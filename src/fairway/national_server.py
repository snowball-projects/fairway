"""Bounded loopback HTTP transport for private prototype review.

This is a separate entry point, not a replacement for fairway.app. It has no
static file, provider passthrough, or administration routes. Public deployment
requires a separately reviewed authentication and hardened ingress decision.
"""

import json
import os
import signal
import socket
from http.client import LineTooLong
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore, Timer

from .national_api import (
    MAX_BODY_BYTES,
    APIConfig,
    APIError,
    Calculator,
    RateBudget,
    parse_request,
)

MAX_CONNECTIONS = 8
CONNECTION_SECONDS = 40
BODY_SECONDS = 5
HEADER_SECONDS = 5
MAX_HEADER_BYTES = 8192
RANKING_PATH = "/api/national/rankings"


def _disconnect(connection):
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


class PrivateHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = True
    request_queue_size = 8

    def __init__(self, address, config, *, calculator=None):
        self.slots = BoundedSemaphore(MAX_CONNECTIONS)
        self.calculator = calculator or Calculator(config)
        self.rate_budget = RateBudget()
        self.catalog = config.catalog_path
        self.stop_requested = False
        super().__init__(address, Handler)

    def service_actions(self):
        if self.stop_requested:
            raise StopRequested

    def server_close(self):
        try:
            self.calculator.close()
        finally:
            super().server_close()

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            # No new thread and no request/body parsing under connection overload.
            body = json.dumps(
                APIError(
                    503, "busy", "Connection capacity exhausted.", retryable=True
                ).document()
            ).encode()
            try:
                request.settimeout(0.1)
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Type: application/json\r\nConnection: close\r\n"
                    b"Cache-Control: no-store\r\nRetry-After: 10\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode()
                    + body
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        timer = Timer(CONNECTION_SECONDS, _disconnect, (request,))
        timer.daemon = True
        timer.start()
        request.settimeout(BODY_SECONDS)
        try:
            super().process_request_thread(request, client_address)
        finally:
            timer.cancel()
            self.slots.release()

    def handle_error(self, request, client_address):
        # Base class logs exception tracebacks and client addresses. Keep neither.
        pass


class HeaderReader:
    def __init__(self, stream, budget):
        self.stream = stream
        self.budget = budget

    def readline(self, size):
        raw = self.stream.readline(min(size, self.budget + 1))
        self.budget -= len(raw)
        if self.budget < 0:
            raise LineTooLong("headers")
        return raw


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fairway-private"
    sys_version = ""

    def handle_one_request(self):
        self.header_timer = Timer(HEADER_SECONDS, _disconnect, (self.connection,))
        self.header_timer.daemon = True
        self.header_timer.start()
        try:
            super().handle_one_request()
        finally:
            self.header_timer.cancel()

    def parse_request(self):
        if len(self.raw_requestline) > 2048:
            self.send_error(414)
            return False
        original = self.rfile
        self.rfile = HeaderReader(
            original, MAX_HEADER_BYTES - len(self.raw_requestline)
        )
        try:
            return super().parse_request()
        finally:
            self.rfile = original
            self.header_timer.cancel()

    def log_message(self, format, *args):
        pass

    def handle_expect_100(self):
        self.send_error(417)
        return False

    def send_error(self, code, message=None, explain=None):
        # Also sanitize protocol errors handled by BaseHTTPRequestHandler.
        self.respond(
            code, APIError(code, "http_error", "HTTP request rejected.").document()
        )

    def respond(self, status, document):
        raw = json.dumps(document, allow_nan=False, separators=(",", ":")).encode()
        self.close_connection = True
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status in {429, 503, 504}:
            self.send_header("Retry-After", "10")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.dispatch()

    do_POST = do_GET
    do_OPTIONS = do_GET
    do_HEAD = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET
    do_PATCH = do_GET
    do_CONNECT = do_GET
    do_TRACE = do_GET

    def dispatch(self):
        try:
            # Private CLI-only prototype. Origin is not an authentication check.
            # Reject browser cross-origin requests, including null and preflight.
            if self.headers.get_all("Origin"):
                raise APIError(
                    403,
                    "origin_denied",
                    "Browser origins are not enabled for this private prototype.",
                )
            if self.path not in {"/health", RANKING_PATH}:
                raise APIError(404, "not_found", "Unknown endpoint.")
            if self.command == "GET" and self.path == "/health":
                self.respond(
                    200,
                    {
                        "status": "ready",
                        "mode": "private-prototype",
                        "authentication": "network-boundary-required",
                    },
                )
                return
            if self.command != "POST" or self.path != RANKING_PATH:
                raise APIError(405, "method_not_allowed", "Method is not supported.")
            if self.headers.get_all("Transfer-Encoding") or self.headers.get_all(
                "Content-Encoding"
            ):
                raise APIError(
                    400,
                    "invalid_framing",
                    "Encoded or chunked request bodies are unsupported.",
                )
            lengths = self.headers.get_all("Content-Length", [])
            if (
                len(lengths) != 1
                or not lengths[0].isascii()
                or not lengths[0].isdigit()
                or len(lengths[0]) > 8
            ):
                raise APIError(
                    411, "length_required", "One bounded Content-Length is required."
                )
            length = int(lengths[0])
            if not 0 < length <= MAX_BODY_BYTES:
                raise APIError(
                    413, "body_too_large", "JSON body must contain 1-4096 bytes."
                )
            types = self.headers.get_all("Content-Type", [])
            if len(types) != 1 or types[0].lower() not in {
                "application/json",
                "application/json; charset=utf-8",
            }:
                raise APIError(
                    415, "unsupported_media_type", "Use application/json in UTF-8."
                )
            timer = Timer(BODY_SECONDS, _disconnect, (self.connection,))
            timer.daemon = True
            timer.start()
            try:
                raw = self.rfile.read(length)
            finally:
                timer.cancel()
            if len(raw) != length:
                raise APIError(400, "incomplete_body", "Request body was incomplete.")
            request = parse_request(raw)
            self.server.rate_budget.consume()
            status, result = self.server.calculator.run(request)
            self.respond(status, result)
        except APIError as error:
            self.respond(error.status, error.document())
        except (OSError, TimeoutError):
            # A disconnected client gets no response; computation remains bounded.
            self.close_connection = True
        except Exception:  # noqa: BLE001 - final HTTP boundary must sanitize faults
            self.respond(
                500,
                APIError(
                    500, "internal_error", "Request could not be completed."
                ).document(),
            )


class StopRequested(Exception):
    pass


def serve_until_stopped(server):
    # Signal handlers only set a flag. Cleanup runs in ordinary control flow,
    # never interrupting process creation or acquiring a lock in the handler.
    def request_stop(signum, frame):
        server.stop_requested = True

    previous = {
        number: signal.signal(number, request_stop)
        for number in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        server.serve_forever(poll_interval=0.1)
    except StopRequested:
        pass
    finally:
        try:
            server.server_close()
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)


def main():
    catalog_path = str(
        Path(__file__).with_name("static") / "data" / "public-courses.json"
    )
    config = APIConfig(
        endpoint=os.environ.get("FAIRWAY_NATIONAL_ROUTER", "http://127.0.0.1:8003"),
        catalog_path=catalog_path,
        routing_dataset=os.environ.get(
            "FAIRWAY_NATIONAL_DATASET", "us-261011-operator-declared"
        ),
    )
    from .facilities import load_facility_catalog

    load_facility_catalog(catalog_path)  # Fail startup before reporting readiness.
    bind = os.environ.get("FAIRWAY_NATIONAL_BIND", "127.0.0.1")
    if bind not in {"127.0.0.1", "0.0.0.0"}:
        raise ValueError("bind must be loopback or the isolated container interface")
    # 0.0.0.0 is only for the reviewed isolated-container proposal.
    serve_until_stopped(PrivateHTTPServer((bind, 8081), config))


if __name__ == "__main__":
    main()
