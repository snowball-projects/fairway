"""Review-only controller. Docker mutations require explicit --execute approval."""

import argparse
import hashlib
import ipaddress
import json
import os
import platform
import re
import select
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.dont_write_bytecode = True
import namespace_client as client_module

ROOT = Path(__file__).resolve().parent
NETWORK = "fairway-safety-review"
CANARY = "fairway-safety-canary-review"
API = "fairway-safety-api-review"
ROUTER = "fairway-safety-router-review"
PREP = "fairway-safety-prepare-review"
BASE = (
    "docker.io/library/python:3.12.14-slim-bookworm@sha256:"
    "eb5be8e5b4d0a159c237946bbdd06356dda5d19c30fc4f7843e8046d3a590333"
)
NATIVE_NAMES = {"modo-native-review-build", "modo-native-review-router"}
LIVE = ("valhalla-us-261011", "valhalla-illinois")
LABEL = "fairway.safety.run=review"
PORT = client_module.PORT
PREPARATION_SECONDS = 180
COPY_SECONDS = 30
COPY_RESERVE_SECONDS = COPY_SECONDS + 5
BODY = json.dumps(
    {
        "origins": [[41.90, -87.66], [42.06, -87.88]],
        "objective": "maximum",
        "holes": [9, 18],
    }
).encode()
WORKERS = """import glob,json
n=0
for p in glob.glob('/proc/[0-9]*/cmdline'):
 try:
  a=open(p,'rb').read().split(b'\\0')
  n += b'--multiprocessing-fork' in a
 except OSError: pass
print(json.dumps(n))
"""
STATUS = """import json,urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:8002/status',timeout=2) as r:
 print(r.read(4096).decode())
"""
ISOLATION = """import errno,json,os,sys
assert os.getuid()==int(sys.argv[1])
status=dict(line.split(':',1) for line in open('/proc/self/status') if ':' in line)
assert status['CapEff'].strip()=='0000000000000000'
assert status['NoNewPrivs'].strip()=='1' and status['Seccomp'].strip()=='2'
try:
 with open('/tmp/fairway-fixture-write-denied','w'): pass
except OSError as e: assert e.errno==errno.EROFS
else: raise AssertionError('root filesystem writable')
limits={p:open('/sys/fs/cgroup/'+p).read().strip() for p in
        ('memory.max','cpu.max','pids.max')}
print(json.dumps(limits))
"""


def validate_work_directory(path):
    if path is None or not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("work directory must be an absolute new path")
    if not path.parent.is_dir() or path.parent.resolve() != path.parent:
        raise ValueError("work directory parent must exist without symlink components")
    if path.is_relative_to(ROOT) or ROOT.is_relative_to(path):
        raise ValueError("work directory must be outside the immutable bundle")
    if any(c in str(path) + str(ROOT) for c in ",\n\r"):
        raise ValueError("mount paths cannot contain commas or line breaks")
    return path


def file_hash(path):
    assert path.is_file() and not path.is_symlink()
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_tree(root, *, make_readable=False):
    assert root.is_dir() and not root.is_symlink()
    total, count = 0, 0
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        assert not path.is_symlink(), "installed code links forbidden"
        if path.is_dir():
            if make_readable:
                path.chmod(0o755)
            continue
        assert path.is_file(), "installed code special files forbidden"
        total += path.stat().st_size
        count += 1
        assert count <= 20000 and total <= 512 * 1024**2, "installed code copy budget"
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        digest.update(bytes.fromhex(file_hash(path)))
        if make_readable:
            path.chmod(0o644)
    assert count, "empty installed code tree"
    if make_readable:
        root.chmod(0o755)
    return digest.hexdigest()


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}), flush=True)


def diagnostic_stderr(raw):
    """Defensive preview only: scan 8 KiB, retain at most 4 KiB UTF-8."""
    raw = raw or b""
    clipped_input = len(raw) > 8192
    if isinstance(raw, str):
        raw = raw[:8192].encode("utf-8", "replace")
    clipped_input = clipped_input or len(raw) > 8192
    preview = raw[:8192].decode("utf-8", "replace")
    preview = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e]", "?", preview)
    preview = re.sub(
        r"(?is)-----BEGIN[^\n]*PRIVATE KEY-----.*", "[redacted key]", preview
    )
    preview = re.sub(
        r"(?im)\b([\w-]*(?:password|passwd|token|secret|credential|key|authorization)[\w-]*)[\"']?\s*[:=][^\n]*",
        r"\1=[redacted]",
        preview,
    )
    preview = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [redacted]", preview)
    preview = re.sub(r"(?i)(?:https?|tcp|ssh)://[^\s\"']+", "[url]", preview)
    # Paths may contain spaces and live outside familiar home/tmp roots. URL
    # data was removed above; conservatively suppress every remaining line
    # with POSIX/Windows path syntax instead of guessing its final component.
    preview = "\n".join(
        "[private-path]" if "/" in line or "\\" in line else line
        for line in preview.split("\n")
    )
    preview = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", preview)
    encoded = preview.encode("utf-8")
    return encoded[:4096].decode("utf-8", "ignore"), clipped_input or len(
        encoded
    ) > 4096


def verify_bundle():
    # CLI verification must not create an unlisted __pycache__ in the bundle.
    sys.dont_write_bytecode = True
    from bundle_integrity import verify

    return verify(ROOT)


absolute_watchdog = client_module.absolute_watchdog
remaining_seconds = client_module.remaining_seconds
http = client_module.http
socket = client_module.socket
ReviewHTTPResponse = client_module.ReviewHTTPResponse
request = client_module.request


def until(check, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(0.2)
    raise TimeoutError("fixture condition deadline")


class ExecClient:
    """One fixed client in an owned namespace; ambiguous lifecycle is fatal."""

    def __init__(self, owner, component):
        self.owner, self.component = owner, component
        self.cid = owner.resource_id("container", component)
        api, self.peer = owner.client_peer(component)
        self.started_at = owner.owned("container", component)["State"]["StartedAt"]
        self.api_id = api["Id"]
        self.api_started_at = api["State"]["StartedAt"]
        self.token = uuid.uuid4().hex
        self.sequence = 0
        self.buffer = bytearray()
        self.bytes = 0
        self.events = 0
        self.pid = self.start_ticks = None
        self.process = None
        self.finished = False
        self.failed = False
        self.pending = set()
        self.idle = 0
        self.idle_used = False
        self.end = min(owner.deadline, time.monotonic() + 90)
        owner.clients.append(self)  # Intent before Popen: unknown exec stays owned.
        try:
            owner.validate_client(self, True)
            source = (ROOT / "namespace_client.py").read_text()
            self.process = subprocess.Popen(
                owner.command
                + [
                    "exec",
                    "--interactive",
                    "--user",
                    "65532:65532",
                    self.cid,
                    "/usr/bin/timeout",
                    "--signal=TERM",
                    "--kill-after=1s",
                    "90s",
                    "python",
                    "-I",
                    "-B",
                    "-c",
                    source,
                    self.peer,
                    self.token,
                    str(remaining_seconds(self.end, 90)),
                ],
                env=owner.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
            event = self.read("ready", min(self.end, time.monotonic() + 5))
            assert set(event) == {
                "event",
                "session",
                "seq",
                "pid",
                "start_ticks",
                "peer",
                "port",
                "isolation",
            }
            assert type(event["pid"]) is int and event["pid"] > 0
            assert (
                isinstance(event["start_ticks"], str) and event["start_ticks"].isdigit()
            )
            assert event["peer"] == self.peer and event["port"] == 8081
            assert event["isolation"] == {
                "uid": 65532,
                "cap_eff": "0000000000000000",
                "no_new_privs": "1",
                "seccomp": "2",
                "limits": {
                    "memory.max": str((512 if component == API else 256) * 1024**2),
                    "cpu.max": "100000 100000",
                    "pids.max": "64",
                },
            }
            self.pid, self.start_ticks = event["pid"], event["start_ticks"]
            assert owner.client_alive(self), "remote exec identity unconfirmed"
        except (Exception, KeyboardInterrupt, SystemExit) as error:  # noqa: BLE001 - incomplete exec/protocol evidence always fails closed
            self.abort(error)

    def abort(self, error):
        self.failed = True
        self.owner.client_failure = True
        if isinstance(error, KeyboardInterrupt):
            raise KeyboardInterrupt from None
        if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
            raise TimeoutError("namespace exec outcome inconclusive") from None
        if isinstance(error, (InterruptedError, SystemExit)):
            raise InterruptedError(
                "namespace exec interrupted; outcome inconclusive"
            ) from None
        raise RuntimeError("namespace exec outcome inconclusive") from None

    def read(self, expected, deadline):
        while b"\n" not in self.buffer:
            remaining = remaining_seconds(min(deadline, self.owner.deadline), 0.1)
            if select.select([self.process.stdout], [], [], remaining)[0]:
                raw = os.read(self.process.stdout.fileno(), 4096)
                if not raw:
                    raise ValueError("exec EOF before lifecycle evidence")
                self.bytes += len(raw)
                self.buffer.extend(raw)
                if self.bytes > 65536 or len(self.buffer) > 4096:
                    raise ValueError("exec output budget")
        line, _, rest = self.buffer.partition(b"\n")
        if rest:
            raise ValueError("unsolicited exec events")
        self.buffer.clear()
        self.events += 1
        if self.events > 64:
            raise ValueError("exec event budget")
        event = json.loads(line.decode("utf-8"))
        if (
            not isinstance(event, dict)
            or event.get("event") != expected
            or event.get("session") != self.token
            or type(event.get("seq")) is not int
            or event["seq"] != self.sequence
        ):
            raise ValueError("exec event identity")
        return event

    def exchange(self, op, **fields):
        try:
            assert (
                not self.failed and not self.finished and not self.owner.client_failure
            )
            self.owner.validate_client(
                self, op in {"health", "ranking", "begin", "idle-open"}
            )
            if op in {"collect", "close"}:
                assert fields.get("attempt") in self.pending
            if op == "finish":
                assert not self.pending and not self.idle
            if op == "idle-open":
                assert not self.idle_used
                self.idle_used = True
            self.sequence += 1
            assert self.sequence < 64
            raw = (
                json.dumps({"seq": self.sequence, "op": op, **fields}) + "\n"
            ).encode()
            assert len(raw) <= 4096
            end = min(self.end, self.owner.deadline, time.monotonic() + 35)
            cursor = 0
            while cursor < len(raw):
                if select.select(
                    [], [self.process.stdin], [], remaining_seconds(end, 0.1)
                )[1]:
                    cursor += os.write(self.process.stdin.fileno(), raw[cursor:])
            event = self.read("finished" if op == "finish" else "reply", end)
            if op == "finish":
                assert set(event) == {"event", "session", "seq", "pending", "idle"}
                assert type(event["pending"]) is type(event["idle"]) is int
                assert event["pending"] == event["idle"] == 0
                self.process.stdin.close()
                self.process.wait(timeout=remaining_seconds(end, 2))
                assert self.process.returncode == 0
                while not select.select(
                    [self.process.stdout], [], [], remaining_seconds(end, 0.1)
                )[0]:
                    pass
                assert os.read(self.process.stdout.fileno(), 4096) == b"", (
                    "exec trailing output or missing EOF"
                )
                assert self.owner.client_exited(self), (
                    "remote exec termination unconfirmed"
                )
                self.finished = True
                self.process.stdout.close()
                return None
            assert set(event) == {
                "event",
                "session",
                "seq",
                "result",
                "pending",
                "idle",
            }
            assert type(event["pending"]) is int and 0 <= event["pending"] <= 2
            assert type(event["idle"]) is int and event["idle"] in {0, 8}
            result = event["result"]
            assert isinstance(result, dict)
            outcomes = {
                "response": {"outcome", "status", "retry_after"},
                "transport-error": {"outcome", "exception_type"},
                "begun": {"outcome", "attempt"},
                "closed": {"outcome", "attempt"},
                "idle-open": {"outcome", "count"},
                "idle-closed": {"outcome"},
            }
            allowed = {
                "health": {"response", "transport-error"},
                "ranking": {"response", "transport-error"},
                "begin": {"begun"},
                "collect": {"response", "transport-error"},
                "close": {"closed"},
                "idle-open": {"idle-open"},
                "idle-close": {"idle-closed"},
            }
            assert (
                result.get("outcome") in allowed[op]
                and set(result) == outcomes[result["outcome"]]
            )
            if result["outcome"] == "response":
                assert type(result["status"]) is int and 100 <= result["status"] <= 599
                assert result["retry_after"] is None or (
                    isinstance(result["retry_after"], str)
                    and result["retry_after"].isdigit()
                    and len(result["retry_after"]) <= 4
                )
            elif result["outcome"] == "transport-error":
                assert result["exception_type"] in {
                    "OSError",
                    "TimeoutError",
                    "ConnectionRefusedError",
                    "ConnectionResetError",
                    "RemoteDisconnected",
                    "IncompleteRead",
                    "HTTPException",
                    "JSONDecodeError",
                    "UnicodeDecodeError",
                    "ValueError",
                }
            elif result["outcome"] in {"begun", "closed"}:
                assert type(result["attempt"]) is int
                assert result["attempt"] == fields["attempt"]
            elif result["outcome"] == "idle-open":
                assert result["count"] == 8
            if op == "begin":
                self.pending.add(fields["attempt"])
            elif op in {"collect", "close"}:
                self.pending.remove(fields["attempt"])
            elif op == "idle-open":
                self.idle = 8
            elif op == "idle-close":
                self.idle = 0
            assert event["pending"] == len(self.pending) and event["idle"] == self.idle
            return result
        except (Exception, KeyboardInterrupt, SystemExit) as error:  # noqa: BLE001 - incomplete exec/protocol evidence always fails closed
            self.abort(error)

    def detach(self):
        # Local CLI termination is not remote termination evidence.
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=remaining_seconds(self.owner.deadline, 0.5))
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=remaining_seconds(self.owner.deadline, 0.5))
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe is not None:
                pipe.close()


class Review:
    def __init__(self, work_directory):
        self.work = validate_work_directory(work_directory)
        self.work_created = False
        self.client = None
        self.clients = []
        self.client_failure = False
        self.pending_attempt = None
        self.phase = 0
        self.phase_attempts = 0
        self.attempts = 0
        self.idle_used = False
        self.site_digest = None
        self.token = uuid.uuid4().hex
        self.deadline = time.monotonic() + 540
        self.command = [
            "docker",
            "--host",
            f"unix:///run/user/{os.getuid()}/docker.sock",
        ]
        self.created = []
        self.ids = {}
        self.members = {}
        self.uncertain_creates = set()
        self.baseline = None
        self.initial_bytes = None
        self.cleanup_mode = False
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("DOCKER_")}

    def begin_phase(self):
        assert self.client is None and not self.client_failure and self.phase < 4
        self.phase += 1
        self.phase_attempts = 0

    def allocate_attempt(self):
        assert (
            not self.client_failure
            and self.phase > 0
            and self.phase_attempts < 12
            and self.attempts < 48
        )
        self.phase_attempts += 1
        self.attempts += 1
        return self.attempts

    def no_publication(self, row):
        host, network = row["HostConfig"], row["NetworkSettings"]
        bindings = host["PortBindings"]
        assert bindings is None or isinstance(bindings, dict)
        assert not bindings and host["PublishAllPorts"] is False, (
            "requested host publication forbidden"
        )
        ports = network["Ports"]
        assert ports is None or isinstance(ports, dict)
        assert all(
            isinstance(key, str)
            and re.fullmatch(r"[0-9]+/(?:tcp|udp|sctp)", key)
            and (value is None or value == [])
            for key, value in (ports or {}).items()
        ), "effective host publication forbidden"

    def client_peer(self, component):
        assert component in {API, ROUTER} and not self.client_failure
        api = self.owned("container", API)
        self.no_publication(api)
        assert api["State"]["Running"] and not api["State"]["OOMKilled"]
        assert isinstance(api["State"]["StartedAt"], str) and api["State"]["StartedAt"]
        self.network_row(NETWORK, self.members[NETWORK])
        assert set(api["NetworkSettings"]["Networks"]) == {NETWORK}
        assert api["NetworkSettings"]["Networks"][NETWORK][
            "NetworkID"
        ] == self.resource_id("network", NETWORK)
        if component == API:
            return api, "127.0.0.1"
        assert self.members[NETWORK] == {API, ROUTER}
        peer = api["NetworkSettings"]["Networks"][NETWORK]["IPAddress"]
        address = ipaddress.IPv4Address(peer)
        assert (
            address.is_private
            and not address.is_loopback
            and not address.is_unspecified
            and not address.is_multicast
        )
        return api, str(address)

    def validate_client(self, client, connecting):
        row = self.owned("container", client.component)
        assert (
            row["Id"] == client.cid
            and row["State"]["Running"]
            and not row["State"]["OOMKilled"]
            and row["State"]["StartedAt"] == client.started_at
        )
        self.no_publication(row)
        assert row["Config"]["User"] == "65532:65532"
        assert set(row["NetworkSettings"]["Networks"]) == {NETWORK}
        assert row["NetworkSettings"]["Networks"][NETWORK][
            "NetworkID"
        ] == self.resource_id("network", NETWORK)
        api = self.owned("container", API)
        assert (
            api["Id"] == client.api_id
            and api["State"]["StartedAt"] == client.api_started_at
        ), "API incarnation changed"
        if connecting:
            checked, peer = self.client_peer(client.component)
            assert checked["Id"] == client.api_id and peer == client.peer, (
                "peer endpoint changed"
            )
        else:
            bridge = self.owned("network", NETWORK)
            assert bridge["Internal"] and bridge["Driver"] == "bridge"
            members = set(bridge.get("Containers") or {})
            assert client.cid in members and members <= {
                self.resource_id("container", n) for n in self.members[NETWORK]
            }

    def client_process_state(self, client, alive):
        code = """import json,sys
from pathlib import Path
p=Path('/proc')/sys.argv[1]
try:
 same=p.joinpath('stat').read_text().rsplit(')',1)[1].split()[19]==sys.argv[2]
 present=same and sys.argv[3].encode() in p.joinpath('cmdline').read_bytes().split(b'\\0')
except FileNotFoundError: same=present=False
print(json.dumps(present if sys.argv[4]=='alive' else not same))
"""
        return (
            self.document(
                "exec",
                "--user",
                "65532:65532",
                client.cid,
                "python",
                "-I",
                "-B",
                "-c",
                code,
                str(client.pid),
                client.start_ticks,
                client.token,
                "alive" if alive else "exited",
            )
            is True
        )

    def client_alive(self, client):
        return self.client_process_state(client, True)

    def client_exited(self, client):
        return self.client_process_state(client, False)

    def open_client(self, component):
        assert self.client is None and not self.client_failure
        self.client = ExecClient(self, component)
        return self.client

    def finish_client(self):
        if self.client is not None:
            self.client.exchange("finish")
            self.client = None

    def request(self, path="/health", body=None, timeout=35):
        assert path in {"/health", "/api/national/rankings"} and body in (None, BODY)
        attempt = self.allocate_attempt()
        result = self.client.exchange(
            "health" if path == "/health" else "ranking", attempt=attempt
        )
        if result["outcome"] == "transport-error":
            if (
                path == "/health"
                and result["exception_type"] == "ConnectionRefusedError"
            ):
                return 0, None, None
            raise RuntimeError("namespace HTTP request failed")
        assert result["outcome"] == "response"
        return result["status"], None, result["retry_after"]

    def start_http_worker(self):
        assert self.pending_attempt is None
        attempt = self.allocate_attempt()
        result = self.client.exchange("begin", attempt=attempt)
        assert result["outcome"] == "begun"
        self.pending_attempt = attempt

    def http_worker_result(self, timeout=25):
        assert self.pending_attempt is not None
        result = self.client.exchange("collect", attempt=self.pending_attempt)
        self.pending_attempt = None
        return result

    def stop_http_worker(self):
        if self.pending_attempt is not None:
            result = self.client.exchange("close", attempt=self.pending_attempt)
            assert result["outcome"] == "closed"
            self.pending_attempt = None

    def failed_command(
        self,
        args,
        timeout,
        *,
        checked,
        returncode=None,
        exception_type=None,
        stderr=None,
    ):
        # Field values are constants or confirmed IDs, never full argv/stdout.
        groups = {
            "container": {"inspect", "rm"},
            "network": {"create", "inspect", "connect", "disconnect", "rm"},
            "image": {"inspect"},
            "system": {"df"},
        }
        singles = {
            "info",
            "ps",
            "inspect",
            "create",
            "start",
            "stop",
            "rm",
            "kill",
            "exec",
            "cp",
        }
        operation = args[:1] if args[0] in singles else ("unknown",)
        if len(args) > 1 and args[1] in groups.get(args[0], set()):
            operation = args[:2]
        known = {PREP, API, ROUTER, NETWORK, CANARY} | set(self.ids.values())
        resources = list(
            dict.fromkeys(
                arg.split(":", 1)[0] for arg in args if arg.split(":", 1)[0] in known
            )
        )
        preview, clipped = diagnostic_stderr(stderr)
        emit(
            "docker-command-failed",
            operation=operation,
            resources=resources[:4],
            timeout_seconds=timeout,
            returncode=returncode,
            exception_type=exception_type,
            checked=checked,
            cleanup=self.cleanup_mode,
            stderr_preview=preview,
            stderr_truncated=clipped,
        )

    def record_failure(self, *args, failure=None, **fields):
        # Called after leaving the original subprocess exception handler. A
        # formatter/output failure must never expose its message or context.
        try:
            self.failed_command(*args, **fields)
        except KeyboardInterrupt:
            raise KeyboardInterrupt from None
        except (TimeoutError, subprocess.TimeoutExpired):
            raise TimeoutError("Docker diagnostic deadline expired") from None
        except (InterruptedError, SystemExit):
            raise InterruptedError("Docker diagnostic recording interrupted") from None
        except Exception:  # noqa: BLE001 - fail closed without arbitrary diagnostic text
            raise failure or RuntimeError(
                "Docker diagnostic recording failed"
            ) from None

    def docker(self, *args, timeout=10, check=True):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("whole review deadline")
        timeout = min(timeout, remaining)
        failure = None
        exception_type = None
        stderr = None
        try:
            # communicate drains both pipes, including cp failures. This limits
            # persisted diagnostics, not total CLI capture/daemon resource use.
            result = subprocess.run(
                self.command + list(args),
                env=self.env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (
            OSError,
            subprocess.SubprocessError,
            KeyboardInterrupt,
            SystemExit,
        ) as error:
            # No redaction or output while a raw exception is active. Retain
            # its category/partial stderr only; Python clears error on exit.
            exception_type = type(error).__name__
            stderr = getattr(error, "stderr", None)
            if isinstance(error, KeyboardInterrupt):
                failure = KeyboardInterrupt()
            elif isinstance(error, (subprocess.TimeoutExpired, TimeoutError)):
                failure = TimeoutError("Docker command deadline expired")
            elif isinstance(error, (InterruptedError, SystemExit)):
                failure = InterruptedError("Docker command interrupted")
            else:
                failure = RuntimeError("Docker command invocation failed")
        if failure is not None:
            self.record_failure(
                args,
                timeout,
                checked=check,
                failure=failure,
                exception_type=exception_type,
                stderr=stderr,
            )
            raise failure from None
        if result.returncode:
            self.record_failure(
                args,
                timeout,
                checked=check,
                returncode=result.returncode,
                stderr=result.stderr,
            )
        if check and result.returncode:
            # Never dump container/image environment or arbitrary daemon output.
            raise RuntimeError(f"Docker command failed, status {result.returncode}")
        return result

    def document(self, *args):
        return json.loads(self.docker(*args).stdout)

    def live_snapshot(self):
        data = self.document("inspect", *LIVE)
        return [
            {
                "id": x["Id"],
                "running": x["State"]["Running"],
                "networks": x["NetworkSettings"]["Networks"],
                "ports": x["HostConfig"]["PortBindings"],
            }
            for x in data
        ]

    def storage(self):
        # Daemon-reported image/container/build-cache bytes, not a hard disk quota.
        rows = self.docker("system", "df", "--format", "{{json .}}").stdout.splitlines()
        # The precise machine-readable df API is not available from this CLI.
        # Filesystem free-space delta is the stop criterion for this proposal.
        assert rows
        return os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize

    def preflight(self):
        assert os.getuid() != 0 and platform.machine() == "aarch64"
        self.native_absent()
        info = self.document("info", "--format", "{{json .}}")
        assert "name=rootless" in info["SecurityOptions"]
        assert info["CgroupVersion"] == "2" and info["CgroupDriver"] == "systemd"
        for kind, names in (
            ("container", (PREP, API, ROUTER)),
            ("network", (NETWORK, CANARY)),
        ):
            for name in names:
                result = self.docker(kind, "inspect", name, check=False)
                assert result.returncode != 0, f"reserved {kind} already exists"
        row = self.document("image", "inspect", BASE)[0]
        assert row["Architecture"] == "arm64" and row["Os"] == "linux"
        digest = BASE.split("@", 1)[1]
        assert any(x.endswith("@" + digest) for x in row.get("RepoDigests", []))
        assert 0 < row["Size"] <= 1024**3, "base image exceeds 1 GiB reported size"
        # Inspect only; the controller never pulls, builds, imports or commits.
        self.baseline = self.live_snapshot()
        assert all(x["running"] for x in self.baseline)
        # Bundle must be staged on the same filesystem as DockerRootDir; otherwise
        # use explicit host-owner accounting before approving this controller.
        root_device = os.stat(info["DockerRootDir"]).st_dev
        assert root_device == ROOT.stat().st_dev == self.work.parent.stat().st_dev
        self.initial_bytes = self.storage()
        assert self.initial_bytes >= 4 * 1024**3, "need at least 4 GiB free"

    def disk_budget(self):
        assert self.initial_bytes - self.storage() <= 2 * 1024**3, (
            "2 GiB added-space stop budget"
        )

    def native_absent(self):
        assert not self.docker(
            "ps", "--quiet", "--filter", "label=modo.native.review"
        ).stdout.strip(), "native review is running"
        names = self.docker("ps", "--all", "--format", "{{.Names}}").stdout.splitlines()
        assert not NATIVE_NAMES.intersection(names), "native review objects remain"

    def creation_gate(self, kind, name):
        assert not self.client_failure, "prior namespace exec outcome inconclusive"
        self.native_absent()
        assert self.docker(kind, "inspect", name, check=False).returncode != 0, (
            "reserved object already exists"
        )

    def resource_id(self, kind, name):
        return self.ids[(kind, name)]

    def owned(self, kind, name):
        known_id = self.ids.get((kind, name))
        row = self.document(kind, "inspect", known_id or name)[0]
        assert re.fullmatch(r"[0-9a-f]{64}", row["Id"]), "full resource ID required"
        assert known_id is None or row["Id"] == known_id, "resource identity changed"
        labels = row["Config"]["Labels"] if kind == "container" else row["Labels"]
        assert labels and labels.get("fairway.safety.run") == "review"
        assert labels.get("fairway.safety.owner") == self.token, "ownership changed"
        return row

    def create_resource(self, kind, name, arguments):
        key = (kind, name)
        # Fixed names are reused by sequential phases. An uncertain new create
        # must be reconciled by its intent name, not a removed phase's old ID.
        self.ids.pop(key, None)
        self.created.append(key)
        # Client timeout is not proof the daemon abandoned creation. Only a
        # returned full ID and subsequent ownership verification resolve intent.
        self.uncertain_creates.add(key)
        emit("resource-create-intent", kind=kind, name=name, owner_token=self.token)
        result = self.docker(*arguments)
        identifier = result.stdout.strip()
        assert re.fullmatch(r"[0-9a-f]{64}", identifier), "creation requires full ID"
        self.ids[key] = identifier
        self.owned(kind, name)
        self.uncertain_creates.remove(key)
        emit(
            "resource-created",
            kind=kind,
            name=name,
            id=identifier,
            owner_token=self.token,
        )

    def network_row(self, name, allowed):
        row = self.owned("network", name)
        assert row["Name"] == name and row["Internal"] and row["Driver"] == "bridge"
        members = row.get("Containers") or {}
        allowed_ids = {self.resource_id("container", n) for n in allowed}
        assert set(members) == allowed_ids, "unexpected or missing bridge member"
        for identifier in members:
            member_name = next(
                n for n in allowed if self.resource_id("container", n) == identifier
            )
            self.owned("container", member_name)
        return row

    def network(self, name):
        self.creation_gate("network", name)
        self.create_resource(
            "network",
            name,
            [
                "network",
                "create",
                "--internal",
                "--label",
                LABEL,
                "--label",
                "fairway.safety.owner=" + self.token,
                name,
            ],
        )
        self.network_row(name, set())
        self.members[name] = set()

    def start_container(self, name, network):
        identifier = self.resource_id("container", name)
        row = self.owned("container", name)
        assert not row["State"]["Running"]
        if network == "none":
            assert row["HostConfig"]["NetworkMode"] == "none"
        else:
            allowed = self.members[network].copy()
            bridge = self.network_row(network, allowed)
            # Created Docker containers may have an empty endpoint NetworkID
            # until start. The configured NetworkMode must already be the full
            # pinned ID, never a mutable name; any populated endpoint must agree.
            assert row["HostConfig"]["NetworkMode"] == bridge["Id"]
            endpoints = row["NetworkSettings"]["Networks"]
            assert len(endpoints) == 1
            assert next(iter(endpoints)) in {network, bridge["Id"]}
            assert all(
                x.get("NetworkID", "") in {"", bridge["Id"]} for x in endpoints.values()
            )
        self.native_absent()
        self.docker("start", identifier)
        if network != "none":
            row = self.owned("container", name)
            endpoints = row["NetworkSettings"]["Networks"]
            assert set(endpoints) == {network}
            assert endpoints[network]["NetworkID"] == self.resource_id(
                "network", network
            )
            bridge = self.network_row(network, allowed | {name})
            assert identifier in (bridge.get("Containers") or {})
            self.members[network].add(name)

    def run_arguments(self, name, network, memory, user):
        return [
            "create",
            "--pull=never",
            "--name",
            name,
            "--label",
            LABEL,
            "--label",
            "fairway.safety.owner=" + self.token,
            "--network",
            network,
            "--restart=no",
            "--init",
            "--user",
            user,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            memory,
            "--memory-swap",
            memory,
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--ulimit",
            "core=0",
            "--ulimit",
            "nofile=256:256",
            "--log-driver",
            "none",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONUNBUFFERED=1",
            "--env",
            "OPENBLAS_NUM_THREADS=1",
            "--env",
            "OMP_NUM_THREADS=1",
            "--env",
            "MKL_NUM_THREADS=1",
            "--env",
            "NUMEXPR_NUM_THREADS=1",
            "--env",
            "BLIS_NUM_THREADS=1",
            "--entrypoint",
            "/usr/bin/timeout",
        ]

    def check_container(self, name, network, memory_mib, user, source, destination):
        row = self.owned("container", name)
        host = row["HostConfig"]
        assert row["Config"]["User"] == user
        assert host["ReadonlyRootfs"] and not host["Privileged"]
        assert host["CapDrop"] == ["ALL"] and not host["CapAdd"]
        assert "no-new-privileges:true" in host["SecurityOpt"]
        assert host["RestartPolicy"]["Name"] == "no" and host["PidsLimit"] == 64
        assert host["Memory"] == host["MemorySwap"] == memory_mib * 1024**2
        assert host["NanoCpus"] == 1_000_000_000
        assert host["LogConfig"]["Type"] == "none"
        assert host["Init"] and not host.get("Devices")
        assert set(row["NetworkSettings"]["Networks"]) == {network}
        if network != "none":
            assert row["NetworkSettings"]["Networks"][network][
                "NetworkID"
            ] == self.resource_id("network", network)
        self.no_publication(row)
        binds = [x for x in row["Mounts"] if x["Type"] == "bind"]
        assert len(binds) == 1 and binds[0]["Source"] == str(source)
        assert binds[0]["Destination"] == destination and not binds[0]["RW"]
        if name == PREP:
            assert host["Tmpfs"] == {"/out": "rw,size=512m,mode=0755"}
            assert all(
                x["Type"] == "bind"
                or (x["Type"] == "tmpfs" and x["Destination"] == "/out")
                for x in row["Mounts"]
            )
        else:
            assert len(row["Mounts"]) == 1 and not host.get("Tmpfs")
        controls = self.document(
            "exec",
            self.resource_id("container", name),
            "python",
            "-c",
            ISOLATION,
            user.split(":")[0],
        )
        assert controls == {
            "memory.max": str(memory_mib * 1024**2),
            "cpu.max": "100000 100000",
            "pids.max": "64",
        }
        emit("isolation-checked", component=name, effective_cgroups=controls)

    def prepare(self):
        previous_deadline = self.deadline
        deadline = min(previous_deadline, time.monotonic() + PREPARATION_SECONDS)
        try:
            self.deadline = deadline
            with absolute_watchdog(deadline):
                self.prepare_with_deadline(deadline)
        finally:
            self.deadline = previous_deadline

    def prepare_with_deadline(self, deadline):
        # Validate before creating host output or daemon objects. This is public
        # code, not a routing dataset; the copied tree is capped and checked.
        validate_work_directory(self.work)
        self.work.mkdir(mode=0o700)
        self.work_created = True
        self.creation_gate("container", PREP)
        args = self.run_arguments(PREP, "none", "1g", "0:0")
        args += [
            "--mount",
            f"type=bind,src={ROOT},dst=/inputs,readonly",
            "--tmpfs",
            "/out:rw,size=512m,mode=0755",
            "--workdir",
            "/inputs",
            BASE,
            "--signal=TERM",
            "--kill-after=5s",
            "180s",
            "python",
            "/inputs/prepare_runtime.py",
        ]
        self.create_resource("container", PREP, args)
        try:
            # One stage budget begins before creation, hence no later than the
            # container timer. Checks/install cannot consume the copy reserve.
            self.deadline = deadline - COPY_RESERVE_SECONDS
            with absolute_watchdog(self.deadline):
                self.start_container(PREP, "none")
                self.check_container(PREP, "none", 1024, "0:0", ROOT, "/inputs")
                self.docker(
                    "exec",
                    self.resource_id("container", PREP),
                    "python",
                    "-c",
                    "from pathlib import Path; Path('/out/allow-install').touch()",
                )
                self.deadline = min(self.deadline, time.monotonic() + 120)
                with absolute_watchdog(self.deadline):
                    while time.monotonic() < self.deadline:
                        state = self.owned("container", PREP)["State"]
                        assert state["Running"] and not state["OOMKilled"], (
                            "preparation failed"
                        )
                        ready = self.docker(
                            "exec",
                            self.resource_id("container", PREP),
                            "python",
                            "-c",
                            "from pathlib import Path; raise SystemExit(not Path('/out/ready').is_file())",
                            check=False,
                        )
                        if ready.returncode == 0:
                            break
                        time.sleep(min(1, remaining_seconds(self.deadline, 1)))
                    else:
                        raise TimeoutError("offline preparation deadline")
        finally:
            self.deadline = deadline
        state = self.owned("container", PREP)["State"]
        assert state["Running"] and not state["OOMKilled"], "preparation failed"
        if deadline - time.monotonic() < COPY_RESERVE_SECONDS:
            raise TimeoutError("insufficient preparation copy reserve")
        # A 30s copy must finish at least 5s before the conservative lifetime
        # deadline. The daemon's actual live-tmpfs copy behavior remains untested.
        with absolute_watchdog(deadline - 5):
            self.docker(
                "cp",
                self.resource_id("container", PREP) + ":/out/site",
                str(self.work / "site"),
                timeout=COPY_SECONDS,
            )
            remaining_seconds(deadline - 5, 1)
        self.site_digest = checked_tree(self.work / "site", make_readable=True)
        if self.initial_bytes is not None:
            self.disk_budget()
        fixture = self.work / "fixture_router.py"
        shutil.copyfile(ROOT / "fixture_router.py", fixture)
        fixture.chmod(0o644)
        # Required ordering: preparation must be removed before runtime begins.
        self.remove_container(PREP)
        assert self.docker("container", "inspect", PREP, check=False).returncode != 0
        receipt = {
            "input_manifest_sha256": file_hash(ROOT / "SHA256SUMS"),
            "installed_tree_sha256": self.site_digest,
            "fixture_sha256": file_hash(fixture),
            "preparation_removed": True,
        }
        (self.work / "receipt.json").write_text(json.dumps(receipt) + "\n")
        emit("offline-preparation-passed", **receipt)

    def container(self, name, network, memory, mode="normal"):
        assert self.site_digest and ("container", PREP) not in self.created
        assert checked_tree(self.work / "site") == self.site_digest
        assert file_hash(self.work / "fixture_router.py") == file_hash(
            ROOT / "fixture_router.py"
        )
        self.creation_gate("container", name)
        self.network_row(network, self.members[network])
        args = self.run_arguments(
            name, self.resource_id("network", network), memory, "65532:65532"
        )
        if name == API:
            source, destination = self.work / "site", "/opt/prepared"
            args += [
                "--env",
                "PYTHONPATH=/opt/prepared",
                "--env",
                "FAIRWAY_NATIONAL_BIND=0.0.0.0",
                "--env",
                "FAIRWAY_NATIONAL_ROUTER=http://valhalla:8002",
                "--env",
                "FAIRWAY_NATIONAL_DATASET=synthetic-fixture-only",
            ]
            program = ["python", "-m", "fairway.national_server"]
        else:
            assert name == ROUTER and mode in {"normal", "hold-first", "slow-stream"}
            source, destination = (
                self.work / "fixture_router.py",
                "/opt/fixture_router.py",
            )
            args += ["--network-alias", "valhalla", "--env", f"FIXTURE_MODE={mode}"]
            program = ["python", destination]
        args += [
            "--mount",
            f"type=bind,src={source},dst={destination},readonly",
            BASE,
            "--signal=TERM",
            "--kill-after=5s",
            "180s",
            *program,
        ]
        self.create_resource("container", name, args)
        self.start_container(name, network)
        self.check_container(
            name,
            network,
            512 if name == API else 256,
            "65532:65532",
            source,
            destination,
        )

    def remove_container(self, name):
        self.owned("container", name)
        self.docker("stop", "--time", "3", self.resource_id("container", name))
        self.owned("container", name)
        self.docker("rm", self.resource_id("container", name))
        self.created.remove(("container", name))
        for members in self.members.values():
            members.discard(name)

    def status(self):
        return self.document(
            "exec", self.resource_id("container", ROUTER), "python", "-c", STATUS
        )

    def workers(self):
        return self.document(
            "exec", self.resource_id("container", API), "python", "-c", WORKERS
        )

    def ready(self):
        def probe():
            try:
                return self.request(timeout=1)[0] == 200
            except TimeoutError:
                raise
            except OSError:
                return False

        for _ in range(8):
            if probe():
                return
            time.sleep(0.2)
        raise TimeoutError("API startup deadline / eight health requests")

    def start_phase(self, mode):
        self.begin_phase()
        self.container(ROUTER, NETWORK, "256m", mode)
        self.container(API, NETWORK, "512m")
        self.open_client(API)
        self.ready()
        self.finish_client()
        self.open_client(ROUTER)
        until(lambda: self.status().get("fixture_only"), 3)

    def end_phase(self):
        self.finish_client()
        self.remove_container(API)
        self.remove_container(ROUTER)

    def canary_and_busy(self):
        self.begin_phase()
        self.network(NETWORK)
        self.network(CANARY)
        self.container(ROUTER, CANARY, "256m", "hold-first")
        self.container(API, NETWORK, "512m")
        self.open_client(API)
        self.ready()
        self.finish_client()
        until(lambda: self.status().get("fixture_only"), 3)
        ip = self.owned("container", ROUTER)["NetworkSettings"]["Networks"][CANARY][
            "IPAddress"
        ]
        probe = "import socket,sys\ns=socket.socket();s.settimeout(1)\ntry:s.connect((sys.argv[1],8002))\nexcept OSError:pass\nelse:raise AssertionError('cross-network reachable')\nfinally:s.close()"
        self.docker(
            "exec",
            self.resource_id("container", API),
            "python",
            "-c",
            probe,
            ip,
            timeout=3,
        )
        emit("disposable-cross-network-canary-denied")
        self.network_row(NETWORK, {API})
        self.network_row(CANARY, {ROUTER})
        self.docker(
            "network",
            "connect",
            "--alias",
            "valhalla",
            self.resource_id("network", NETWORK),
            self.resource_id("container", ROUTER),
        )
        self.network_row(NETWORK, {API, ROUTER})
        self.network_row(CANARY, {ROUTER})
        self.members[NETWORK].add(ROUTER)
        self.owned("container", ROUTER)
        self.docker(
            "network",
            "disconnect",
            self.resource_id("network", CANARY),
            self.resource_id("container", ROUTER),
        )
        self.members[CANARY].discard(ROUTER)
        assert not self.network_row(CANARY, set()).get("Containers")
        self.owned("network", CANARY)
        self.docker("network", "rm", self.resource_id("network", CANARY))
        self.created.remove(("network", CANARY))
        self.members.pop(CANARY)
        row = self.owned("container", ROUTER)
        assert set(row["NetworkSettings"]["Networks"]) == {NETWORK}
        assert row["NetworkSettings"]["Networks"][NETWORK][
            "NetworkID"
        ] == self.resource_id("network", NETWORK)
        members = self.network_row(NETWORK, {API, ROUTER})["Containers"]
        assert {x["Name"] for x in members.values()} == {API, ROUTER}
        self.open_client(ROUTER)
        self.start_http_worker()
        try:
            until(lambda: self.status()["active_jobs"] == 1, 10)
            second = self.request("/api/national/rankings", BODY)
            assert second[0] == 503 and second[2] == "10"
            assert self.http_worker_result()["status"] == 200
        finally:
            if time.monotonic() < self.deadline:
                self.stop_http_worker()
        assert self.request("/api/national/rankings", BODY)[0] == 200
        assert not self.idle_used
        self.idle_used = True
        assert self.client.exchange("idle-open")["count"] == 8
        assert self.request(timeout=2)[0] == 503
        assert self.client.exchange("idle-close")["outcome"] == "idle-closed"
        emit("calculation-contention-and-connection-overload-passed")
        self.end_phase()

    def disconnect_deadline(self):
        self.start_phase("slow-stream")
        started = time.monotonic()
        self.start_http_worker()
        until(lambda: self.status()["active_jobs"] == 1, 10)
        self.stop_http_worker()
        self.finish_client()
        assert self.workers() == 1
        until(lambda: self.workers() == 0, 32)
        elapsed = time.monotonic() - started
        assert elapsed <= 33 and self.status()["active_jobs"] == 1
        emit(
            "disconnected-child-reaped",
            elapsed_seconds=round(elapsed, 2),
            synthetic_upstream_job_still_active=True,
        )
        self.remove_container(ROUTER)
        self.container(ROUTER, NETWORK, "256m")
        self.open_client(ROUTER)
        assert self.request("/api/national/rankings", BODY)[0] == 200
        emit("calculation-gate-recovered")
        self.end_phase()

    def interruption(self, abrupt):
        self.start_phase("slow-stream")
        self.start_http_worker()
        until(lambda: self.status()["active_jobs"] == 1, 10)
        assert self.workers() == 1
        started = time.monotonic()
        self.owned("container", API)
        if abrupt:
            self.docker("kill", "--signal", "KILL", self.resource_id("container", API))
        else:
            self.docker("stop", "--time", "3", self.resource_id("container", API))
        state = self.owned("container", API)["State"]
        assert not state["Running"] and not state["OOMKilled"]
        if not abrupt:
            assert state["ExitCode"] != 137
        result = self.http_worker_result()
        assert result["outcome"] == "transport-error" or result.get("status") in {
            503,
            504,
        }
        self.finish_client()  # Independent fixture observer survives API exit.
        emit(
            "api-container-interrupted",
            abrupt=abrupt,
            elapsed_seconds=round(time.monotonic() - started, 2),
            exit_code=state["ExitCode"],
        )
        self.end_phase()

    def cleanup(self, *, deadline=None):
        # Separate 30-second reserve, including namespace CLI teardown.
        self.cleanup_mode = True
        self.deadline = time.monotonic() + 30 if deadline is None else deadline
        failures = (
            ["namespace exec outcome inconclusive"] if self.client_failure else []
        )
        try:
            if self.client is not None and not self.client_failure:
                self.stop_http_worker()
                self.finish_client()
        except Exception:  # noqa: BLE001 - continue owned Docker cleanup within reserve
            failures.append("namespace client lifecycle unconfirmed")
        for client in self.clients:
            try:
                client.detach()
            except Exception:  # noqa: BLE001 - remote cleanup remains mandatory
                failures.append("namespace client CLI unreaped")
        # Bounded reconciliation can discover a delayed create, but repeated
        # absence never turns an uncertain create into confirmed cleanup.
        for key in list(self.uncertain_creates):
            kind, name = key
            for attempt in range(6):
                if time.monotonic() >= self.deadline:
                    break
                try:
                    row = self.owned(kind, name)
                    self.ids[key] = row["Id"]
                    self.uncertain_creates.remove(key)
                    break
                except Exception:  # noqa: BLE001 - retain unknown outcome
                    if attempt < 5 and self.deadline - time.monotonic() >= 1:
                        time.sleep(1)
            if key in self.uncertain_creates:
                failures.append(name + ": creation outcome unknown")
        for kind, name in list(reversed(self.created)):
            if (kind, name) in self.uncertain_creates:
                continue
            try:
                self.owned(kind, name)
                identifier = self.resource_id(kind, name)
                if kind == "container":
                    self.docker("stop", "--time", "3", identifier)
                self.owned(kind, name)
                self.docker(kind, "rm", identifier)
                assert (
                    self.docker(kind, "inspect", identifier, check=False).returncode
                    != 0
                )
                self.created.remove((kind, name))
            except Exception:  # noqa: BLE001 - finish cleanup of other owned resources
                failures.append(name)
        if self.baseline is not None:
            try:
                if self.live_snapshot() != self.baseline:
                    failures.append(
                        "live routing snapshot changed; do not attempt repair"
                    )
            except Exception:  # noqa: BLE001 - never report uncertain cleanup as success
                failures.append("live routing snapshot could not be verified")
        if time.monotonic() >= self.deadline:
            failures.append("cleanup deadline expired; completion unconfirmed")
        if not failures and self.work_created:
            shutil.rmtree(self.work)
            self.work_created = False
        emit(
            "cleanup",
            failed_resources=failures,
            base_image_retained=True,
            prepared_directory_retained=self.work_created,
            uncertain_creations=[
                {"kind": k, "name": n, "id": self.ids.get((k, n))}
                for k, n in sorted(self.uncertain_creates)
            ],
            namespace_exec_inconclusive=self.client_failure,
            namespace_clients=[
                {"container_id": c.cid, "pid": c.pid, "finished": c.finished}
                for c in self.clients
            ],
            remaining_resources=[
                {"kind": k, "name": n, "id": self.ids.get((k, n))}
                for k, n in self.created
            ],
        )
        if failures:
            raise RuntimeError("cleanup or live-state verification failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--work-directory", type=Path)
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError(
            "run without Python optimization; verification guards required"
        )
    verify_bundle()
    if not args.execute:
        emit(
            "review-only",
            docker_calls=0,
            container_tests_executed=False,
            resources={
                "containers_max": 2,
                "internal_bridges_max": 2,
                "published_ports": 0,
                "persistent_volumes": 0,
                "readonly_code_mounts_per_container": 1,
                "preparation_memory_mib": 1024,
                "preparation_tmpfs_mib": 512,
                "preparation_cpus": 1,
                "preparation_tasks": 64,
                "runtime_memory_mib": 768,
                "runtime_cpus": 2,
                "runtime_tasks": 128,
                "container_lifetime_seconds": 180,
                "whole_stage_seconds": 600,
            },
        )
        return
    if args.work_directory is None:
        parser.error(
            "execution requires a new absolute --work-directory outside the bundle"
        )
    review = Review(args.work_directory)

    def stop(signum, frame):
        raise InterruptedError("controller interrupted")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        with absolute_watchdog(review.deadline):
            emit(
                "execution-started",
                owner_token=review.token,
                base_image=BASE,
                work_directory=str(review.work),
            )
            review.preflight()
            review.prepare()
            review.canary_and_busy()
            review.disconnect_deadline()
            review.interruption(False)
            review.interruption(True)
            review.disk_budget()
            emit("fixture-stage-passed", native_valhalla_behavior_tested=False)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        cleanup_deadline = time.monotonic() + 30
        try:
            with absolute_watchdog(cleanup_deadline):
                review.cleanup(deadline=cleanup_deadline)
        except TimeoutError:
            emit(
                "cleanup-deadline-expired",
                confirmed_cleanup=False,
                owner_token=review.token,
                namespace_exec_inconclusive=review.client_failure,
                remaining_resources=[
                    {"kind": k, "name": n, "id": review.ids.get((k, n))}
                    for k, n in review.created
                ],
            )
            raise


if __name__ == "__main__":
    main()
