"""Synthetic bounded router fixture. No road files, network calls or shell work."""

import json
import math
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, address, mode="normal"):
        if mode not in {"normal", "hold-first", "slow-stream"}:
            raise ValueError("unknown fixture mode")
        self.mode = mode
        self.stop_requested = False
        self.slots = threading.BoundedSemaphore(4)
        self.lock = threading.Lock()
        self.started = 0
        self.completed = 0
        self.active = 0
        self.disconnected = 0
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        request.settimeout(3)
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass

    def service_actions(self):
        if self.stop_requested:
            raise StopRequested


class StopRequested(Exception):
    pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def respond(self, status, document):
        raw = json.dumps(document, separators=(",", ":")).encode()
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path != "/status":
            self.respond(404, {"error": "unknown fixture route"})
            return
        with self.server.lock:
            snapshot = {
                "fixture_only": True,
                "mode": self.server.mode,
                "started_jobs": self.server.started,
                "completed_jobs": self.server.completed,
                "active_jobs": self.server.active,
                "disconnected_jobs": self.server.disconnected,
            }
        self.respond(200, snapshot)

    def do_POST(self):
        if self.path not in {"/locate", "/sources_to_targets"}:
            self.respond(404, {"error": "unknown fixture route"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 65536:
            self.respond(413, {"error": "fixture body limit"})
            return
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        with self.server.lock:
            if self.server.started >= 64:
                self.respond(503, {"error": "fixture request budget"})
                return
            self.server.started += 1
            sequence = self.server.started
            self.server.active += 1
        try:
            if self.path == "/locate":
                points = payload["locations"]
                if not 1 <= len(points) <= 128:
                    raise ValueError("fixture locate dimensions")
                result = [
                    {
                        "edges": [
                            {"correlated_lat": p["lat"], "correlated_lon": p["lon"]}
                        ]
                    }
                    for p in points
                ]
            else:
                sources, targets = payload["sources"], payload["targets"]
                if not 1 <= len(sources) <= 8 or not 1 <= len(targets) <= 40:
                    raise ValueError("fixture matrix dimensions")
                result = {
                    "sources_to_targets": [
                        [
                            {
                                "time": math.hypot(
                                    a["lat"] - b["lat"], a["lon"] - b["lon"]
                                )
                                * 3600,
                                "begin_lat": a["lat"],
                                "begin_lon": a["lon"],
                                "end_lat": b["lat"],
                                "end_lon": b["lon"],
                            }
                            for b in targets
                        ]
                        for a in sources
                    ]
                }
            if self.server.mode == "hold-first" and sequence == 1:
                time.sleep(2)
            if self.server.mode == "slow-stream" and self.path == "/locate":
                self.slow_stream(result)
            else:
                self.respond(200, result)
        except (TimeoutError, BrokenPipeError, ConnectionResetError):
            with self.server.lock:
                self.server.disconnected += 1
        finally:
            with self.server.lock:
                self.server.active -= 1
                self.server.completed += 1

    def slow_stream(self, document):
        """Keep read calls alive; intentionally continue fake work after disconnect."""
        raw = json.dumps(document).encode()
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        disconnected = False
        for index in range(35):
            if not disconnected:
                try:
                    self.wfile.write(raw[index : index + 1])
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    disconnected = True
                    with self.server.lock:
                        self.server.disconnected += 1
            time.sleep(1)
        if not disconnected:
            self.wfile.write(raw[35:])


def main():
    server = FixtureServer(("0.0.0.0", 8002), os.environ.get("FIXTURE_MODE", "normal"))

    def stop(signum, frame):
        server.stop_requested = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.1)
    except StopRequested:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
