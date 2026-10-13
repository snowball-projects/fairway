import http.client
import json
import socket
import threading
import time
from contextlib import contextmanager

import pytest
from test_national_api import BODY, CONFIG

from fairway.national_api import Calculator
from fairway.national_server import RANKING_PATH, PrivateHTTPServer


class FakeCalculator:
    def __init__(self):
        self.calls = []

    def close(self):
        pass

    def run(self, request):
        self.calls.append(request)
        return 200, {"fixture": True}


@contextmanager
def running_server(calculator=None):
    calculator = calculator or FakeCalculator()
    server = PrivateHTTPServer(("127.0.0.1", 0), CONFIG, calculator=calculator)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}
    )
    thread.start()
    try:
        yield server, calculator
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def request(server, method="POST", path=RANKING_PATH, *, body=None, headers=None):
    connection = http.client.HTTPConnection(*server.server_address, timeout=8)
    raw = json.dumps(BODY).encode() if body is None else body
    connection.request(
        method,
        path,
        body=raw if method == "POST" else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), json.loads(response.read())
    connection.close()
    return result


def raw_request(server, raw):
    with socket.create_connection(server.server_address, timeout=8) as connection:
        connection.sendall(raw)
        connection.shutdown(socket.SHUT_WR)
        result = b""
        while chunk := connection.recv(65536):
            result += chunk
        return result


def test_http_valid_request_health_and_privacy_headers():
    with running_server() as (server, calculator):
        status, headers, result = request(server)
        assert status == 200
        assert result == {"fixture": True}
        assert len(calculator.calls) == 1
        assert headers["Cache-Control"] == "no-store"
        assert headers["Connection"] == "close"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert not any(k.startswith("Access-Control") for k in headers)
        assert request(server, "GET", "/health")[0] == 200
        assert len(calculator.calls) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/route",
        "/sources_to_targets",
        "/status",
        "/admin",
        "/docker",
        "/ssh",
        "/etc/passwd",
        "/../data/catalog.json",
        "/api/rankings",
        RANKING_PATH + "?endpoint=http://evil",
        "http://evil/api/national/rankings",
    ],
)
def test_no_provider_filesystem_admin_or_public_api_passthrough(path):
    with running_server() as (server, calculator):
        status, _, _ = request(server, path=path)
        assert status == 404
        assert not calculator.calls


@pytest.mark.parametrize(
    "origin",
    [
        "https://snowball-projects.github.io",
        "null",
        "http://localhost",
        "https://evil.example",
    ],
)
def test_browser_origins_and_preflight_are_closed(origin):
    with running_server() as (server, calculator):
        assert request(server, headers={"Origin": origin})[0] == 403
        assert request(server, "OPTIONS", headers={"Origin": origin})[0] == 403
        assert not calculator.calls


@pytest.mark.parametrize(
    "method", ["GET", "HEAD", "OPTIONS", "PUT", "DELETE", "PATCH", "CONNECT", "TRACE"]
)
def test_calculation_only_allows_post(method):
    with running_server() as (server, calculator):
        # HEAD intentionally has no parsed body in http.client.
        connection = http.client.HTTPConnection(*server.server_address, timeout=8)
        connection.request(method, RANKING_PATH)
        response = connection.getresponse()
        assert response.status == 405
        connection.close()
        assert not calculator.calls


@pytest.mark.parametrize(
    ("extra", "status"),
    [
        (b"Content-Length: 10\r\nContent-Length: 10\r\n", 411),
        (b"Transfer-Encoding: chunked\r\nContent-Length: 10\r\n", 400),
        (b"Content-Encoding: gzip\r\nContent-Length: 10\r\n", 400),
        (b"Content-Length: 5000\r\n", 413),
        (b"Content-Length: -1\r\n", 411),
        (b"Content-Length: 999999999999999\r\n", 411),
        (b"", 411),
        (b"Content-Length: 10\r\nContent-Type: text/plain\r\n", 415),
        (b"Content-Length: 10\r\nExpect: 100-continue\r\n", 417),
        (b"Content-Length: 10\r\nX-Pad: " + b"x" * 8200 + b"\r\n", 431),
    ],
)
def test_http_framing_and_header_limits(extra, status):
    with running_server() as (server, calculator):
        raw = (
            b"POST /api/national/rankings HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
            + extra
            + b"\r\n{}"
        )
        result = raw_request(server, raw)
        assert result.startswith(f"HTTP/1.1 {status} ".encode())
        assert not calculator.calls
        assert b"<html" not in result


def test_rate_limit_over_http_has_retry_after():
    with running_server() as (server, calculator):
        for _ in range(4):
            assert request(server)[0] == 200
        status, headers, result = request(server)
        assert status == 429
        assert headers["Retry-After"] == "10"
        assert result["error"]["retryable"] is True
        assert len(calculator.calls) == 4


def test_body_deadline_and_header_deadline_release_connections(monkeypatch):
    import fairway.national_server as transport

    monkeypatch.setattr(transport, "BODY_SECONDS", 0.15)
    monkeypatch.setattr(transport, "HEADER_SECONDS", 0.15)
    with running_server() as (server, calculator):
        for raw in [
            b"POST /api/national/rankings HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 300\r\n\r\n{",
            b"GET /health HTTP/1.1\r\nHost:",
        ]:
            with socket.create_connection(
                server.server_address, timeout=2
            ) as connection:
                connection.sendall(raw)
                started = time.monotonic()
                assert connection.recv(4096) == b""
                assert time.monotonic() - started < 1
        assert request(server, "GET", "/health")[0] == 200
        assert not calculator.calls


def test_connection_overload_rejected_without_spawning_handler():
    with running_server() as (server, calculator):
        assert all(server.slots.acquire(blocking=False) for _ in range(8))
        status, headers, result = request(server)
        assert status == 503
        assert headers["Retry-After"] == "10"
        assert result["error"]["code"] == "busy"
        for _ in range(8):
            server.slots.release()
        assert not calculator.calls


@pytest.mark.parametrize(
    "mode, expected", [("valid", 200), ("outage", 502), ("malformed", 502)]
)
def test_full_http_to_real_modo_adapter_with_local_fixture_router(mode, expected):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from math import hypot

    from fairway.national_api import APIConfig

    calls = []

    class RouterHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            document = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(self.path)
            if mode != "valid":
                raw = (
                    b'{"error":"private coordinate /home/operator SECRET","error_code":199}'
                    if mode == "outage"
                    else b'{"bad":"private endpoint SECRET"}'
                )
                self.send_response(500 if mode == "outage" else 200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if self.path == "/locate":
                result = [
                    {
                        "edges": [
                            {
                                "correlated_lat": point["lat"],
                                "correlated_lon": point["lon"],
                            }
                        ]
                    }
                    for point in document["locations"]
                ]
            elif self.path == "/sources_to_targets":
                result = {
                    "sources_to_targets": [
                        [
                            {
                                "time": hypot(a["lat"] - b["lat"], a["lon"] - b["lon"])
                                * 3600,
                                "begin_lat": a["lat"],
                                "begin_lon": a["lon"],
                                "end_lat": b["lat"],
                                "end_lon": b["lon"],
                            }
                            for b in document["targets"]
                        ]
                        for a in document["sources"]
                    ]
                }
            else:
                self.send_error(404)
                return
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    router = ThreadingHTTPServer(("127.0.0.1", 0), RouterHandler)
    thread = threading.Thread(
        target=router.serve_forever, kwargs={"poll_interval": 0.01}
    )
    thread.start()
    config = APIConfig(
        f"http://127.0.0.1:{router.server_port}",
        CONFIG.catalog_path,
        "synthetic-fixture-v1",
    )
    try:
        with running_server(Calculator(config)) as (server, _):
            status, _, result = request(server)
            assert status == expected
            if mode != "valid":
                assert result["error"]["code"] == "routing_unavailable"
                assert "facilities" not in result
                assert "SECRET" not in json.dumps(result)
                assert "/home/operator" not in json.dumps(result)
                assert len(calls) == 1
                return
            assert result["facilities"]
            assert result["metadata"]["routing_dataset"] == "synthetic-fixture-v1"
            assert result["metadata"]["provider_requests"] == len(calls)
            assert set(calls) == {"/locate", "/sources_to_targets"}
            assert len(calls) <= 32
    finally:
        router.shutdown()
        router.server_close()
        thread.join()


@pytest.mark.parametrize(
    "encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"]
)
def test_http_rejects_non_utf8_json_before_calculation(encoding):
    with running_server() as (server, calculator):
        status, _, result = request(server, body=json.dumps(BODY).encode(encoding))
        assert status == 400
        assert result["error"]["code"] == "invalid_request"
        assert not calculator.calls


def shutdown_test_worker(connection, config, request):
    import os
    import signal
    from pathlib import Path

    if config.routing_dataset == "ignore-term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(config.catalog_path).write_text(str(os.getpid()))
    time.sleep(60)


@pytest.mark.parametrize("ignore_term", [False, True])
def test_sigterm_server_parent_stops_and_reaps_calculation_child(tmp_path, ignore_term):
    import os
    import subprocess
    import sys
    from pathlib import Path

    worker_pid_path = tmp_path / "worker.pid"
    launcher = tmp_path / "serve.py"
    launcher.write_text("""
import sys
from fairway.national_api import APIConfig, Calculator
from fairway.national_server import PrivateHTTPServer, serve_until_stopped
from test_national_server import shutdown_test_worker
if __name__ == '__main__':
    config = APIConfig('http://127.0.0.1:8003', sys.argv[1], sys.argv[2])
    server = PrivateHTTPServer(('127.0.0.1', 0), config, calculator=Calculator(config, timeout=30, worker=shutdown_test_worker))
    print(server.server_port, flush=True)
    serve_until_stopped(server)
""")
    parent = subprocess.Popen(
        [
            sys.executable,
            str(launcher),
            str(worker_pid_path),
            "ignore-term" if ignore_term else "normal-term",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent)},
    )
    child_pid = None
    client = None
    try:
        import select

        ready, _, _ = select.select([parent.stdout], [], [], 5)
        assert ready, "server did not start"
        port = int(parent.stdout.readline())
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        client.request(
            "POST",
            RANKING_PATH,
            body=json.dumps(BODY).encode(),
            headers={"Content-Type": "application/json"},
        )
        deadline = time.monotonic() + 5
        while not worker_pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert worker_pid_path.exists(), "calculation child did not start"
        child_pid = int(worker_pid_path.read_text())
        os.kill(child_pid, 0)
        started = time.monotonic()
        parent.terminate()
        assert parent.wait(timeout=3) == 0
        assert time.monotonic() - started < 2
        # A zombie also answers kill(pid, 0). ESRCH proves the parent reaped it.
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if client is not None:
            client.close()
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        if child_pid is not None:
            try:
                os.kill(child_pid, 9)
            except ProcessLookupError:
                pass
        parent.stdout.close()
        parent.stderr.close()


def controlled_fixture_worker(connection, config, request):
    import os
    from pathlib import Path

    root = Path(config.catalog_path)
    (root / "worker.pid").write_text(str(os.getpid()))
    deadline = time.monotonic() + 4
    while not (root / "release").exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    connection.send((200, {"fixture": True}))
    connection.close()


def test_real_http_calculation_contention_is_immediate_and_recovers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from fairway.national_api import APIConfig

    config = APIConfig(CONFIG.endpoint, str(tmp_path), "controlled-fixture")
    calculator = Calculator(config, timeout=6, worker=controlled_fixture_worker)
    with (
        running_server(calculator) as (server, _),
        ThreadPoolExecutor(max_workers=1) as clients,
    ):
        first = clients.submit(request, server)
        try:
            deadline = time.monotonic() + 3
            while (
                not (tmp_path / "worker.pid").exists() and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert (tmp_path / "worker.pid").exists()
            started = time.monotonic()
            status, headers, body = request(server)
            assert status == 503
            assert body["error"]["code"] == "busy"
            assert headers["Retry-After"] == "10"
            assert time.monotonic() - started < 1
        finally:
            (tmp_path / "release").touch()
        assert first.result(timeout=5)[0] == 200
        assert request(server)[0] == 200
        assert calculator.active_process is None


def interrupted_fixture_worker(connection, config, request):
    import os
    from pathlib import Path

    Path(config.catalog_path).write_text(str(os.getpid()))
    time.sleep(60)


def test_disconnected_client_still_has_bounded_child_lifetime_and_gate_recovery(
    tmp_path,
):
    import os

    from test_national_api import successful_worker

    from fairway.national_api import APIConfig

    pid_file = tmp_path / "worker.pid"
    config = APIConfig(CONFIG.endpoint, str(pid_file), "disconnect-fixture")
    calculator = Calculator(config, timeout=1.5, worker=interrupted_fixture_worker)
    with running_server(calculator) as (server, _):
        client = http.client.HTTPConnection(*server.server_address, timeout=3)
        client.request(
            "POST",
            RANKING_PATH,
            body=json.dumps(BODY).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            deadline = time.monotonic() + 3
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert pid_file.exists()
            child_pid = int(pid_file.read_text())
            client.close()
            deadline = time.monotonic() + 3
            while calculator.active_process is not None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert calculator.active_process is None
            with pytest.raises(ProcessLookupError):
                os.kill(child_pid, 0)
            calculator.worker = successful_worker
            calculator.timeout = 5
            assert request(server)[0] == 200
        finally:
            client.close()


def test_eight_stalled_connections_reject_ninth_without_more_handlers(monkeypatch):
    from fairway.national_server import Handler

    entered = 0
    lock = threading.Lock()
    all_entered = threading.Event()
    original = Handler.handle_one_request

    def counted(handler):
        nonlocal entered
        with lock:
            entered += 1
            if entered == 8:
                all_entered.set()
        return original(handler)

    monkeypatch.setattr(Handler, "handle_one_request", counted)
    with running_server() as (server, calculator):
        idle = []
        try:
            for _ in range(8):
                client = socket.create_connection(server.server_address, timeout=3)
                client.sendall(b"G")
                idle.append(client)
            assert all_entered.wait(timeout=3)
            status, _, body = request(server, method="GET", path="/health")
            assert status == 503
            assert body["error"]["code"] == "busy"
            assert entered == 8
            assert not calculator.calls
        finally:
            for client in idle:
                client.close()
