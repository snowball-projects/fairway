"""Actual stdio/HTTP integration with local processes; Docker is never invoked.

The adapter preserves production peer/nonce arguments, redirects only the fixed
socket to a temporary loopback server, and mocks OCI facts explicitly. Independent
PID/start-time checks use the production read-only probe against local /proc.
These tests establish protocol behavior, not container networking or isolation.
"""

import importlib.util
import json
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import test_review_controller as review_tests
from test_national_server import running_server

from fairway.national_api import APIError

REAL_POPEN = subprocess.Popen


def real_run(argv, *, input=None, capture_output=False, timeout=3, check=False):
    with REAL_POPEN(
        argv,
        stdin=subprocess.PIPE if input is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as process:
        stdout, stderr = process.communicate(input, timeout=timeout)
        if check and process.returncode:
            raise AssertionError("local read-only probe failed")
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


FIXTURE = review_tests.FIXTURE
attach = review_tests.attach


@pytest.fixture
def controller(tmp_path, monkeypatch):
    return review_tests.controller.__wrapped__(tmp_path, monkeypatch)


def load_client():
    spec = importlib.util.spec_from_file_location(
        "namespace_fixture", FIXTURE / "namespace_client.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_for(check):
    end = time.monotonic() + 3
    while not check():
        assert time.monotonic() < end, "local fixture deadline"
        time.sleep(0.01)


@pytest.fixture
def local_adapter(controller, monkeypatch):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    review.container(m.API, m.NETWORK, "512m")
    review.container(m.ROUTER, m.NETWORK, "256m")
    review.begin_phase()
    launches = []
    address = [None]
    transform = [lambda source: source]
    document = review.document

    def local_document(*args, **kwargs):
        if args[0] == "exec" and "same=p.joinpath" in args[8]:
            result = real_run(
                [sys.executable, "-I", "-B", "-c", args[8], *args[9:]],
                capture_output=True,
                timeout=2,
                check=True,
            )
            return json.loads(result.stdout)
        return document(*args, **kwargs)

    def launch(argv, **kwargs):
        assert argv[: len(review.command)] == review.command
        args = argv[len(review.command) :]
        assert args[:4] == ["exec", "--interactive", "--user", "65532:65532"]
        assert args[4] in {
            review.resource_id("container", m.API),
            review.resource_id("container", m.ROUTER),
        }
        assert args[5:13] == [
            "/usr/bin/timeout",
            "--signal=TERM",
            "--kill-after=1s",
            "90s",
            "python",
            "-I",
            "-B",
            "-c",
        ]
        peer, nonce, duration = args[-3:]
        assert peer in {"127.0.0.1", "172.30.0.2"} and address[0] is not None
        memory = 512 if args[4] == review.resource_id("container", m.API) else 256
        facts = {
            "uid": 65532,
            "cap_eff": "0000000000000000",
            "no_new_privs": "1",
            "seccomp": "2",
            "limits": {
                "memory.max": str(memory * 1024**2),
                "cpu.max": "100000 100000",
                "pids.max": "64",
            },
        }
        wrapper = f"""import socket
ns={{'__name__':'local_fixture'}}
exec({args[13]!r},ns)
ns['isolation_facts']=lambda:{facts!r}
original=socket.create_connection
def redirect(target,*a,**kw):
 assert target==({peer!r},8081), 'unexpected target'
 return original({address[0]!r},*a,**kw)
socket.create_connection=redirect
ns['main']()
"""
        process = REAL_POPEN(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                transform[0](wrapper),
                peer,
                nonce,
                duration,
            ],
            **kwargs,
        )
        launches.append(process)
        return process

    monkeypatch.setattr(review, "document", local_document)
    monkeypatch.setattr(subprocess, "Popen", launch)
    try:
        yield m, review, fake, address, launches, transform
    finally:
        for client in review.clients:
            client.detach()
        for process in launches:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)


class HeldCalculator:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = threading.Event()
        self.release = threading.Event()

    def close(self):
        self.release.set()

    def run(self, request):
        if not self.lock.acquire(blocking=False):
            raise APIError(503, "busy", "Held fixture.", retryable=True)
        try:
            self.active.set()
            assert self.release.wait(3)
            return 200, {"fixture": True}
        finally:
            self.lock.release()


def test_actual_dispatcher_adapter_startup_contention_overload_and_finish(
    local_adapter,
):
    m, review, _, address, launches, _ = local_adapter
    calculator = HeldCalculator()
    with running_server(calculator) as (server, _):
        address[0] = server.server_address
        review.open_client(m.API)
        assert review.request()[0] == 200
        review.finish_client()
        review.open_client(m.ROUTER)
        review.start_http_worker()
        assert calculator.active.wait(2)
        assert review.request("/api/national/rankings", m.BODY)[::2] == (503, "10")
        calculator.release.set()
        assert review.http_worker_result()["status"] == 200
        assert review.request("/api/national/rankings", m.BODY)[0] == 200
        review.client.exchange("idle-open")
        assert review.request()[0] == 503
        review.client.exchange("idle-close")
        review.finish_client()
    assert review.attempts == 5
    assert all(p.poll() == 0 for p in launches)
    assert all(c.finished for c in review.clients)
    assert not review.client_failure


def test_selected_disconnect_leaves_other_socket_and_observer_alive(local_adapter):
    m, review, _, address, launches, _ = local_adapter
    calculator = HeldCalculator()
    with running_server(calculator) as (server, _):
        address[0] = server.server_address
        client = review.open_client(m.ROUTER)
        first = review.allocate_attempt()
        second = review.allocate_attempt()
        client.exchange("begin", attempt=first)
        assert calculator.active.wait(2)
        client.exchange("begin", attempt=second)
        client.exchange("close", attempt=first)
        assert client.pending == {second} and launches[-1].poll() is None
        assert client.exchange("collect", attempt=second)["status"] == 503
        assert not calculator.release.is_set()
        review.finish_client()
        calculator.release.set()
    assert not review.client_failure and review.clients[-1].finished


@pytest.mark.parametrize("abrupt", [False, True])
def test_real_api_stop_and_kill_observed_from_independent_client(
    local_adapter, tmp_path, abrupt
):
    m, review, fake, address, launches, _ = local_adapter
    marker = tmp_path / "active"
    source = f"""import sys,time
from pathlib import Path
sys.path.insert(0,{str(Path(__file__).resolve().parents[1] / "src")!r})
from fairway.national_api import APIConfig
from fairway.national_server import PrivateHTTPServer,serve_until_stopped
class Held:
 def close(self): pass
 def run(self,request):
  Path({str(marker)!r}).touch()
  while not server.stop_requested: time.sleep(.01)
  return 503,{{'error':{{'fixture':True}}}}
server=PrivateHTTPServer(('127.0.0.1',0),APIConfig('http://127.0.0.1:8003','unused','fixture'),calculator=Held())
print(server.server_address[1],flush=True)
serve_until_stopped(server)
"""
    api = REAL_POPEN(
        [sys.executable, "-I", "-B", "-c", source],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert select.select([api.stdout], [], [], 3)[0]
        address[0] = ("127.0.0.1", int(api.stdout.readline()))
        review.open_client(m.ROUTER)
        review.start_http_worker()
        wait_for(marker.exists)
        api.kill() if abrupt else api.terminate()
        assert api.wait(timeout=3) == (-9 if abrupt else 0)
        fake.objects[m.API]["State"]["Running"] = False
        assert launches[-1].poll() is None
        result = review.http_worker_result()
        assert result["outcome"] == "transport-error" or result.get("status") == 503
        review.finish_client()
        assert review.clients[-1].finished and not review.client_failure
    finally:
        if api.poll() is None:
            api.kill()
            api.wait(timeout=2)
        api.stdout.close()


@pytest.mark.parametrize(
    "mutation", ["peer", "incarnation", "ports", "missing-ports", "owner"]
)
def test_changed_peer_policy_blocks_request_without_replacement(
    local_adapter, mutation
):
    m, review, fake, address, launches, _ = local_adapter
    with running_server() as (server, _):
        address[0] = server.server_address
        review.open_client(m.ROUTER)
        row = fake.objects[m.API]
        if mutation == "peer":
            row["NetworkSettings"]["Networks"][m.NETWORK]["IPAddress"] = "172.30.0.8"
        elif mutation == "incarnation":
            row["State"]["StartedAt"] = "different-start"
        elif mutation == "ports":
            row["NetworkSettings"]["Ports"] = {
                "8081/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}]
            }
        elif mutation == "missing-ports":
            row["NetworkSettings"].pop("Ports")
        else:
            row["Config"]["Labels"]["fairway.safety.owner"] = "foreign"
        with pytest.raises(RuntimeError, match="inconclusive"):
            review.request()
        with pytest.raises(AssertionError):
            review.open_client(m.ROUTER)
        with pytest.raises(AssertionError):
            review.creation_gate("container", m.ROUTER)
        assert len(launches) == 1 and review.client_failure


@pytest.mark.parametrize("bad_finish", ["trailing", "nonzero", "remote-present"])
def test_finish_requires_eof_exit_and_independent_absence(
    local_adapter, monkeypatch, bad_finish
):
    m, review, _, address, _, transform = local_adapter
    if bad_finish == "trailing":
        transform[0] = lambda s: s + "\nprint('unexpected',flush=True)\n"
    elif bad_finish == "nonzero":
        transform[0] = lambda s: s + "\nraise SystemExit(2)\n"
    else:
        monkeypatch.setattr(review, "client_exited", lambda _: False)
    with running_server() as (server, _):
        address[0] = server.server_address
        review.open_client(m.ROUTER)
        with pytest.raises(RuntimeError, match="inconclusive"):
            review.finish_client()
    assert review.client_failure and not review.clients[-1].finished


def test_uncertain_launch_sticky_cleanup_retains_evidence(controller, monkeypatch):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    review.container(m.API, m.NETWORK, "512m")
    review.begin_phase()
    with pytest.raises(RuntimeError, match="inconclusive"):
        review.open_client(m.API)
    assert review.client_failure and len(review.clients) == 1
    with pytest.raises(AssertionError):
        review.open_client(m.API)
    with pytest.raises(RuntimeError, match="cleanup"):
        review.cleanup()
    assert review.work.exists() and not fake.objects


def test_phase_budget_never_resets_aggregate(controller):
    _, review = controller
    for phase in range(4):
        review.begin_phase()
        assert [review.allocate_attempt() for _ in range(12)] == list(
            range(phase * 12 + 1, phase * 12 + 13)
        )
        with pytest.raises(AssertionError):
            review.allocate_attempt()
    with pytest.raises(AssertionError):
        review.begin_phase()
    assert review.attempts == 48


@pytest.mark.parametrize(
    "command",
    [
        {"seq": 1, "op": "health", "attempt": 1, "host": "evil"},
        {"seq": 1, "op": "shell", "attempt": 1},
        {"seq": 1, "op": "health", "attempt": True},
        {"seq": 1, "op": "health", "attempt": 49},
        {"seq": 1, "op": "collect", "attempt": 1},
    ],
)
def test_closed_commands_before_network(command, monkeypatch):
    module = load_client()
    client = module.NamespaceClient("127.0.0.1", time.monotonic() + 2)
    monkeypatch.setattr(module, "request", lambda *a, **kw: pytest.fail("network call"))
    with pytest.raises((ValueError, KeyError)):
        client.handle(command)


def test_request_budget_counts_failed_attempts_and_rejects_reuse(monkeypatch):
    module = load_client()
    client = module.NamespaceClient("127.0.0.1", time.monotonic() + 2)
    monkeypatch.setattr(
        module,
        "request",
        lambda *a, **kw: (_ for _ in ()).throw(ConnectionRefusedError()),
    )
    for attempt in range(1, 13):
        assert (
            client.handle({"seq": attempt, "op": "health", "attempt": attempt})[
                "outcome"
            ]
            == "transport-error"
        )
    for attempt in [12, 13, 49]:
        with pytest.raises(ValueError):
            client.handle({"seq": 13, "op": "health", "attempt": attempt})
    assert client.attempts == 12


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b'{"seq":2,"op":"finish"}\n',
        b'{"seq":true,"op":"finish"}\n',
        b"\xff\n",
        b"{}\n{}\n",
        b"x" * 4097,
        b'{"seq":1',
    ],
)
def test_real_dispatcher_terminal_protocol_failures(tmp_path, raw):
    source = (FIXTURE / "namespace_client.py").read_text()
    wrapper = f"ns={{'__name__':'fixture'}};exec({source!r},ns);ns['isolation_facts']=lambda:{{}};ns['main']()"
    result = real_run(
        [sys.executable, "-I", "-B", "-c", wrapper, "127.0.0.1", "a" * 32, "1"],
        input=raw,
        capture_output=True,
        timeout=3,
    )
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == 1 and events[0]["event"] == "ready"
    assert events[-1]["event"] == "failed"
    assert "exception_type" in events[-1] and result.stderr == b""


@pytest.mark.parametrize(
    "change", ["nonce", "sequence", "counts", "status", "isolation"]
)
def test_real_adapter_rejects_corrupted_event_identity(local_adapter, change):
    m, review, _, address, _, transform = local_adapter
    if change == "isolation":
        transform[0] = lambda s: s.replace("'pids.max': '64'", "'pids.max': '65'")
    else:
        inject = f"""
original_json=ns['json'].dumps
def corrupt(value,*a,**kw):
 if isinstance(value,dict) and value.get('event')=='reply':
  change={change!r}
  if change=='nonce': value['session']='b'*32
  elif change=='sequence': value['seq']+=1
  elif change=='counts': value['pending']=True
  elif change=='status': value['result']['status']=True
 return original_json(value,*a,**kw)
ns['json'].dumps=corrupt
"""
        transform[0] = lambda s: s.replace("ns['main']()", inject + "\nns['main']()")
    with running_server() as (server, _):
        address[0] = server.server_address
        with pytest.raises(RuntimeError, match="inconclusive"):
            review.open_client(m.ROUTER)
            review.request()
    assert review.client_failure and not review.clients[-1].finished


def test_client_incarnation_change_blocks_even_nonconnecting_finish(local_adapter):
    m, review, fake, address, _, _ = local_adapter
    with running_server() as (server, _):
        address[0] = server.server_address
        review.open_client(m.ROUTER)
        fake.objects[m.ROUTER]["State"]["StartedAt"] = "replacement"
        with pytest.raises(RuntimeError, match="inconclusive"):
            review.finish_client()
    assert review.client_failure


def test_two_outstanding_limit_and_pending_deadline(monkeypatch):
    module = load_client()
    client = module.NamespaceClient("127.0.0.1", time.monotonic() + 2)

    class Connection:
        def __init__(self):
            self.closed = False

        def request(self, *args):
            pass

        def close(self):
            self.closed = True

    connections = []

    def connect(seconds):
        connection = Connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(client, "connection", connect)
    client.handle({"seq": 1, "op": "begin", "attempt": 1})
    client.handle({"seq": 2, "op": "begin", "attempt": 2})
    with pytest.raises(ValueError, match="outstanding"):
        client.handle({"seq": 3, "op": "begin", "attempt": 3})
    with pytest.raises(ValueError, match="unfinished"):
        client.handle({"seq": 4, "op": "finish"})
    assert len(connections) == 2 and client.attempts == 3
    client.pending[1] = (connections[0], time.monotonic() - 1)
    with pytest.raises(TimeoutError):
        client.handle({"seq": 5, "op": "close", "attempt": 2})
    client.close_all()
    assert not client.pending and all(c.closed for c in connections)


@pytest.mark.parametrize(
    "field,value",
    [
        ("PortBindings", {"8081/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}]}),
        ("PublishAllPorts", True),
        ("PublishAllPorts", None),
    ],
)
def test_requested_publication_never_reaches_exec(
    controller, monkeypatch, field, value
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    review.container(m.API, m.NETWORK, "512m")
    fake.objects[m.API]["HostConfig"][field] = value
    with pytest.raises(AssertionError):
        review.open_client(m.API)
    subprocess.Popen.assert_not_called()


def test_actual_stdio_aggregate_input_budget_without_network():
    source = (FIXTURE / "namespace_client.py").read_text()
    wrapper = f"ns={{'__name__':'fixture'}};exec({source!r},ns);ns['isolation_facts']=lambda:{{}};ns['main']()"
    process = REAL_POPEN(
        [sys.executable, "-I", "-B", "-c", wrapper, "127.0.0.1", "a" * 32, "3"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def event():
        assert select.select([process.stdout], [], [], 2)[0]
        return json.loads(process.stdout.readline())

    try:
        assert event()["event"] == "ready"
        for sequence in range(1, 40):
            frame = json.dumps({"seq": sequence, "op": "idle-close"}).encode()
            process.stdin.write(frame + b" " * (2300 - len(frame)) + b"\n")
            process.stdin.flush()
            received = event()
            if sequence == 29:
                assert received["event"] == "failed"
                break
            assert received["event"] == "reply"
        assert process.wait(timeout=2) == 1
        assert process.stderr.read() == b""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize("op", ["health", "ranking", "collect"])
@pytest.mark.parametrize(
    "retry", [None, b"10", b"9999", b"10000", b"9" * 5000, b"now", b"", b"\xb2"]
)
def test_real_response_retry_header_validation_shared(
    controller, monkeypatch, op, retry
):
    m, _ = controller
    header = b"" if retry is None else b"Retry-After: " + retry + b"\r\n"
    connection, transport, responses = review_tests.memory_http_client(
        m,
        monkeypatch,
        b"HTTP/1.1 503 Busy\r\nContent-Length: 2\r\n" + header + b"\r\n{}",
    )
    client = m.client_module.NamespaceClient("127.0.0.1", time.monotonic() + 2)
    if op == "collect":
        client.handle({"seq": 1, "op": "begin", "attempt": 1})
        command = {"seq": 2, "op": "collect", "attempt": 1}
    else:
        command = {"seq": 1, "op": op, "attempt": 1}
    result = client.handle(command)
    if retry in (None, b"10", b"9999"):
        assert result == {
            "outcome": "response",
            "status": 503,
            "retry_after": None if retry is None else retry.decode(),
        }
    else:
        assert result == {"outcome": "transport-error", "exception_type": "ValueError"}
    assert not client.pending and connection.sock is None
    assert transport.file_closed and responses[0].close.call_count >= 1


@pytest.mark.parametrize("kind", ["frame", "aggregate", "encoded-frame"])
def test_emitter_rejects_bytes_before_write_and_stays_terminal(kind):
    import os

    module = load_client()
    read_fd, write_fd = os.pipe()
    emitter = module.ProtocolEmitter("a" * 32, write_fd)
    os.set_blocking(read_fd, False)
    try:
        if kind == "aggregate":
            total = 0
            for seq in range(1, 50):
                try:
                    emitter.emit(
                        "reply", seq, deadline=time.monotonic() + 1, padding="x" * 3000
                    )
                except ValueError:
                    break
                total += len(os.read(read_fd, 4096))
            assert 62000 < total <= 65536
        else:
            with pytest.raises(ValueError, match="output budget"):
                emitter.emit(
                    "reply",
                    1,
                    deadline=time.monotonic() + 1,
                    padding=("x" * 5000 if kind == "frame" else "\U0001f600" * 400),
                )
        assert emitter.failed
        with pytest.raises(ValueError, match="already failed"):
            emitter.emit("failed", 2, deadline=time.monotonic() + 1)
        with pytest.raises(BlockingIOError):
            os.read(read_fd, 4096)
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_direct_request_connect_send_cap_and_remaining_response_budget(
    controller, monkeypatch
):
    m, _ = controller
    clock = [100.0]
    from contextlib import nullcontext

    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        m.client_module, "absolute_watchdog", lambda deadline: nullcontext()
    )
    _, transport, _ = review_tests.memory_http_client(
        m, monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    )
    original = transport.sendall

    def send(data):
        clock[0] += 0.1
        original(data)

    monkeypatch.setattr(transport, "sendall", send)
    assert m.request_impl("/api/national/rankings", m.BODY)[0] == 200
    assert m.http.client.HTTPConnection.call_args.kwargs["timeout"] == 2
    assert all(0 < timeout < 35 for timeout in transport.timeouts)


def test_direct_send_alarm_prevents_response_read_after_send_overrun(
    controller, monkeypatch
):
    m, _ = controller
    monkeypatch.setattr(m.client_module, "CONNECT_SECONDS", 0.02)
    _, transport, responses = review_tests.memory_http_client(
        m, monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    )
    monkeypatch.setattr(transport, "sendall", lambda data: time.sleep(0.2))
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        m.request_impl("/api/national/rankings", m.BODY)
    assert time.monotonic() - started < 0.15
    assert responses == [] and transport.close_calls == 1


def test_blocked_emitter_expires_instead_of_blocking_on_full_pipe():
    import os

    module = load_client()
    read_fd, write_fd = os.pipe()
    emitter = module.ProtocolEmitter("a" * 32, write_fd)
    try:
        while True:
            try:
                os.write(write_fd, b"x" * 4096)
            except BlockingIOError:
                break
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            emitter.emit("reply", 1, deadline=started + 0.03)
        assert time.monotonic() - started < 0.2 and emitter.failed
    finally:
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize(
    "mode", ["blocked-reply", "blocked-error", "blocked-ready", "oversized-reply"]
)
def test_actual_dispatcher_output_failure_closes_socket_before_error_report(
    tmp_path, mode
):
    source = (FIXTURE / "namespace_client.py").read_text()
    marker = tmp_path / "closed"
    wrapper = f"""import os,time,json
from pathlib import Path
ns={{'__name__':'fixture'}}
exec({source!r},ns)
ns['isolation_facts']=lambda:{{}}
mode={mode!r}
marker=Path({str(marker)!r})
class Socket:
 def close(self): marker.touch()
class Client(ns['NamespaceClient']):
 def handle(self,cmd):
  self.pending[1]=(Socket(),time.monotonic()+.05)
  if mode=='blocked-error': raise ValueError('fixture failure')
  if mode=='oversized-reply': return {{'outcome':'fixture','padding':'x'*5000}}
  return {{'outcome':'begun','attempt':1}}
ns['NamespaceClient']=Client
original=ns['ProtocolEmitter'].emit
class Emitter(ns['ProtocolEmitter']):
 def emit(self,event,*a,**kw):
  if (mode=='blocked-ready' and event=='ready') or (mode=='blocked-reply' and event=='reply') or (mode=='blocked-error' and event=='failed'):
   if mode=='blocked-error': assert marker.exists(), 'reporting retained socket'
   while True:
    try: os.write(self.fd,b'x'*4096)
    except BlockingIOError: break
  return original(self,event,*a,**kw)
ns['ProtocolEmitter']=Emitter
ns['main']()
"""
    process = REAL_POPEN(
        [sys.executable, "-I", "-B", "-c", wrapper, "127.0.0.1", "a" * 32, ".3"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        if mode != "blocked-ready":
            assert select.select([process.stdout], [], [], 2)[0]
            assert json.loads(process.stdout.readline())["event"] == "ready"
            process.stdin.write(b'{"seq":1,"op":"begin","attempt":1}\n')
            process.stdin.flush()
        started = time.monotonic()
        assert process.wait(timeout=2) == 1
        assert time.monotonic() - started < 1
        if mode != "blocked-ready":
            assert marker.exists()
        assert process.stderr.read() == b""
        if mode == "oversized-reply":
            assert process.stdout.read() == b""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize(
    "mode", ["collect-normal", "collect-blocked", "error-normal", "error-blocked"]
)
def test_actual_dispatcher_retains_command_deadline_after_handler_cleanup(
    tmp_path, mode
):
    source = (FIXTURE / "namespace_client.py").read_text()
    records = tmp_path / "deadlines.jsonl"
    closed = tmp_path / "closed"
    wrapper = f"""import os,time,json
from pathlib import Path
ns={{'__name__':'fixture'}}
exec({source!r},ns)
ns['isolation_facts']=lambda:{{}}
mode={mode!r}
records=Path({str(records)!r})
closed=Path({str(closed)!r})
real_monotonic=time.monotonic
clock=[100.,real_monotonic()]
ns['time'].monotonic=lambda:clock[0]+real_monotonic()-clock[1]
class Connection:
 def close(self): closed.touch()
class Client(ns['NamespaceClient']):
 def __init__(self,*a):
  super().__init__(*a)
  self.deadline=190.
  self.pending[1]=(Connection(),135.)
def read_response(connection,end):
 assert end==135.
 clock[:]=[134.99,real_monotonic()]
 if mode.startswith('error'): raise RuntimeError('handler fixture')
 return 200,{{}},None
ns['NamespaceClient']=Client
ns['read_response']=read_response
original=ns['ProtocolEmitter'].emit
class Emitter(ns['ProtocolEmitter']):
 def emit(self,event,sequence,**kw):
  with records.open('a') as stream: stream.write(json.dumps({{'event':event,'deadline':kw['deadline']}})+'\\n')
  selected='failed' if mode.startswith('error') else 'reply'
  if event==selected:
   assert closed.exists(), 'handler did not close/remove pending connection'
   if mode.endswith('blocked'):
    while True:
     try: os.write(self.fd,b'x'*4096)
     except BlockingIOError: break
  return original(self,event,sequence,**kw)
ns['ProtocolEmitter']=Emitter
ns['main']()
"""
    process = REAL_POPEN(
        [sys.executable, "-I", "-B", "-c", wrapper, "127.0.0.1", "a" * 32, "90"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def event():
        assert select.select([process.stdout], [], [], 2)[0]
        return json.loads(process.stdout.readline())

    try:
        assert event()["event"] == "ready"
        process.stdin.write(b'{"seq":1,"op":"collect","attempt":1}\n')
        process.stdin.flush()
        if mode == "collect-normal":
            assert event()["result"]["status"] == 200
            process.stdin.write(b'{"seq":2,"op":"finish"}\n')
            process.stdin.flush()
            assert event()["event"] == "finished"
        elif mode == "error-normal":
            assert event()["event"] == "failed"
        started = time.monotonic()
        assert process.wait(timeout=2) == (0 if mode == "collect-normal" else 1)
        assert time.monotonic() - started < 0.5
        observed = [json.loads(line) for line in records.read_text().splitlines()]
        selected = "failed" if mode.startswith("error") else "reply"
        assert (
            next(row for row in observed if row["event"] == selected)["deadline"]
            == 135.0
        )
        assert closed.exists() and process.stderr.read() == b""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize("op", ["health", "ranking"])
@pytest.mark.parametrize("blocked", [False, True])
def test_actual_dispatcher_direct_operation_deadline_includes_result_delivery(
    tmp_path, op, blocked
):
    source = (FIXTURE / "namespace_client.py").read_text()
    records = tmp_path / "deadlines.jsonl"
    expected = 101.0 if op == "health" else 135.0
    wrapper = f"""import os,time,json
from pathlib import Path
ns={{'__name__':'fixture'}}
exec({source!r},ns)
ns['isolation_facts']=lambda:{{}}
records=Path({str(records)!r})
real_monotonic=time.monotonic
clock=[100.,real_monotonic(),False]
ns['time'].monotonic=lambda:clock[0]+(real_monotonic()-clock[1] if clock[2] else 0.)
def request(path,body=None,**kw):
 assert kw['timeout']=={1 if op == "health" else 35}
 clock[:]=[{expected!r}-.01,real_monotonic(),True]
 return 200,{{}},None
ns['request']=request
original=ns['ProtocolEmitter'].emit
class Emitter(ns['ProtocolEmitter']):
 def emit(self,event,sequence,**kw):
  with records.open('a') as stream: stream.write(json.dumps({{'event':event,'deadline':kw['deadline']}})+'\\n')
  if event=='reply' and {blocked!r}:
   while True:
    try: os.write(self.fd,b'x'*4096)
    except BlockingIOError: break
  return original(self,event,sequence,**kw)
ns['ProtocolEmitter']=Emitter
ns['main']()
"""
    process = REAL_POPEN(
        [sys.executable, "-I", "-B", "-c", wrapper, "127.0.0.1", "a" * 32, "90"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def event():
        assert select.select([process.stdout], [], [], 2)[0]
        return json.loads(process.stdout.readline())

    try:
        assert event()["event"] == "ready"
        process.stdin.write(
            (json.dumps({"seq": 1, "op": op, "attempt": 1}) + "\n").encode()
        )
        process.stdin.flush()
        if not blocked:
            assert event()["result"]["status"] == 200
            process.stdin.write(b'{"seq":2,"op":"finish"}\n')
            process.stdin.flush()
            assert event()["event"] == "finished"
        started = time.monotonic()
        assert process.wait(timeout=2) == (1 if blocked else 0)
        assert time.monotonic() - started < 0.5
        observed = [json.loads(line) for line in records.read_text().splitlines()]
        assert (
            next(row for row in observed if row["event"] == "reply")["deadline"]
            == expected
        )
        if blocked:
            assert (
                next(row for row in observed if row["event"] == "failed")["deadline"]
                == expected
            )
        assert process.stderr.read() == b""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()
