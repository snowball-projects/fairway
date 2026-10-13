"""Review-only controller. Docker mutations require explicit --execute approval."""

import argparse
import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

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
PORT = 18081
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


def verify_bundle():
    # CLI verification must not create an unlisted __pycache__ in the bundle.
    sys.dont_write_bytecode = True
    from bundle_integrity import verify

    return verify(ROOT)


@contextmanager
def absolute_watchdog(deadline):
    """Linux main-process alarm, independent of Docker and the API under test."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("absolute controller/request deadline")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def expire(signum, frame):
        raise TimeoutError("absolute controller/request deadline")

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(
        signal.ITIMER_REAL,
        min(remaining, previous_timer[0]) if previous_timer[0] else remaining,
    )
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            restored = previous_timer[0] - (time.monotonic() - started)
            if restored <= 0:
                raise TimeoutError("enclosing absolute deadline expired")
            signal.setitimer(signal.ITIMER_REAL, restored, previous_timer[1])


def remaining_seconds(deadline, ceiling):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("absolute controller/request deadline")
    return min(remaining, ceiling)


class ReviewHTTPResponse(http.client.HTTPResponse):
    """Stdlib framing with strict chunk terminators and bounded trailers."""

    # Same protocol guard as the native review's smoke parser; no native
    # cancellation or engine-evidence logic is imported into this controller.
    def _get_chunk_left(self):
        if self.chunk_left == 0:
            if self._safe_read(2) != b"\r\n":
                raise http.client.IncompleteRead(b"")
            self.chunk_left = None
        return super()._get_chunk_left()

    def _read_and_discard_trailer(self):
        for _ in range(32):
            line = self.fp.readline(8193)
            if line == b"\r\n":
                return
            if not line or not line.endswith(b"\r\n"):
                raise http.client.IncompleteRead(b"")
            if len(line) > 8192:
                raise http.client.HTTPException("review trailer line exceeds bound")
        raise http.client.HTTPException("review trailer count exceeds bound")


def request(path="/health", body=None, timeout=35, *, deadline=None):
    end = time.monotonic() + timeout
    if deadline is not None:
        end = min(end, deadline)
    remaining = remaining_seconds(end, timeout)
    with absolute_watchdog(end):
        client = http.client.HTTPConnection("127.0.0.1", PORT, timeout=remaining)
        response = None
        try:
            client.request(
                "GET" if body is None else "POST",
                path,
                body=body,
                headers={} if body is None else {"Content-Type": "application/json"},
            )
            # Keep the socket reference: getresponse may detach it from client
            # when a Connection: close response owns the remaining file handle.
            transport = client.sock
            transport.settimeout(remaining_seconds(end, timeout))
            client.response_class = ReviewHTTPResponse
            response = client.getresponse()
            raw = bytearray()
            # read1 closes HTTPResponse.fp at the last fixed-length byte. A
            # Connection: close transport can then also be closed; never touch
            # that saved socket once the parser has completed the response.
            while not response.isclosed():
                transport.settimeout(remaining_seconds(end, timeout))
                chunk = response.read1(min(65536, 1048577 - len(raw)))
                remaining_seconds(end, timeout)
                if not chunk:
                    break
                raw.extend(chunk)
                assert len(raw) <= 1048576, "response body exceeds 1 MiB"
            remaining_seconds(end, timeout)
            if response.length not in (None, 0):
                raise http.client.IncompleteRead(bytes(raw), response.length)
            if response.chunked and not response.isclosed():
                raise http.client.IncompleteRead(bytes(raw))
            body = json.loads(raw)
            remaining_seconds(end, timeout)
            return response.status, body, response.getheader("Retry-After")
        finally:
            try:
                if response is not None:
                    response.close()
            finally:
                client.close()


HTTP_WORKER = """import json,runpy,sys
module=runpy.run_path(sys.argv[1])
result=module['request']('/api/national/rankings',module['BODY'],deadline=float(sys.argv[2]))
print(json.dumps({'status':result[0]}),flush=True)
"""


def until(check, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(0.2)
    raise TimeoutError("fixture condition deadline")


class Review:
    def __init__(self, work_directory):
        self.work = validate_work_directory(work_directory)
        self.work_created = False
        self.http_worker = None
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
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("DOCKER_")}

    def request(self, path="/health", body=None, timeout=35):
        return request(path, body, timeout, deadline=self.deadline)

    def start_http_worker(self):
        assert self.http_worker is None
        remaining_seconds(self.deadline, 35)
        self.http_worker = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-c",
                HTTP_WORKER,
                str(ROOT / "run_review.py"),
                str(min(self.deadline, time.monotonic() + 35)),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def http_worker_result(self, timeout=25):
        assert self.http_worker is not None
        raw, _ = self.http_worker.communicate(
            timeout=remaining_seconds(self.deadline, timeout)
        )
        assert self.http_worker.returncode == 0 and len(raw) <= 256
        return json.loads(raw)["status"]

    def stop_http_worker(self):
        worker = self.http_worker
        if worker is None:
            return
        # Popen has no ThreadPoolExecutor's unbounded context/exit join. Even a
        # stalled client gets only two capped waits; retain an unreaped handle.
        if worker.poll() is None:
            worker.terminate()
        try:
            worker.wait(timeout=remaining_seconds(self.deadline, 0.5))
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=remaining_seconds(self.deadline, 0.5))
        self.http_worker = None

    def docker(self, *args, timeout=10, check=True):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("whole review deadline")
        result = subprocess.run(
            self.command + list(args),
            env=self.env,
            capture_output=True,
            text=True,
            timeout=min(timeout, remaining),
            check=False,
        )
        if check and result.returncode:
            # Never dump container/image environment or arbitrary daemon output.
            raise RuntimeError(f"Docker {args[0]} failed, status {result.returncode}")
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
        with socket.socket() as s:
            s.bind(("127.0.0.1", PORT))
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
        assert (host["PortBindings"] or {}) == (
            {"8081/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]}
            if name == API
            else {}
        )
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
        self.start_container(PREP, "none")
        self.check_container(PREP, "none", 1024, "0:0", ROOT, "/inputs")
        self.docker(
            "exec",
            self.resource_id("container", PREP),
            "python",
            "-c",
            "from pathlib import Path; Path('/out/allow-install').touch()",
        )
        end = time.monotonic() + 120
        while time.monotonic() < end:
            state = self.owned("container", PREP)["State"]
            assert state["Running"] and not state["OOMKilled"], "preparation failed"
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
            time.sleep(1)
        else:
            raise TimeoutError("offline preparation deadline")
        self.docker(
            "cp",
            self.resource_id("container", PREP) + ":/out/site",
            str(self.work / "site"),
            timeout=30,
        )
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
                "--publish",
                f"127.0.0.1:{PORT}:8081",
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
        self.container(ROUTER, NETWORK, "256m", mode)
        self.container(API, NETWORK, "512m")
        self.ready()
        until(lambda: self.status().get("fixture_only"), 3)

    def end_phase(self):
        self.remove_container(API)
        self.remove_container(ROUTER)

    def canary_and_busy(self):
        self.network(NETWORK)
        self.network(CANARY)
        self.container(ROUTER, CANARY, "256m", "hold-first")
        self.container(API, NETWORK, "512m")
        self.ready()
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
        self.start_http_worker()
        try:
            until(lambda: self.status()["active_jobs"] == 1, 10)
            second = self.request("/api/national/rankings", BODY)
            assert second[0] == 503 and second[2] == "10"
            assert self.http_worker_result() == 200
        finally:
            if time.monotonic() < self.deadline:
                self.stop_http_worker()
        assert self.request("/api/national/rankings", BODY)[0] == 200
        held = []
        try:
            for _ in range(8):
                s = socket.create_connection(("127.0.0.1", PORT), timeout=1)
                s.sendall(b"GET /health HTTP/1.1\r\n")
                held.append(s)
            time.sleep(0.2)
            assert self.request(timeout=2)[0] == 503
        finally:
            for s in held:
                s.close()
        emit("calculation-contention-and-connection-overload-passed")
        self.end_phase()

    def disconnect_deadline(self):
        self.start_phase("slow-stream")
        s = socket.create_connection(("127.0.0.1", PORT), timeout=2)
        raw = (
            b"POST /api/national/rankings HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Type: application/json\r\nContent-Length: "
            + str(len(BODY)).encode()
            + b"\r\n\r\n"
            + BODY
        )
        started = time.monotonic()
        try:
            s.sendall(raw)
            until(lambda: self.status()["active_jobs"] == 1, 10)
        finally:
            s.close()
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
        assert self.request("/api/national/rankings", BODY)[0] == 200
        emit("calculation-gate-recovered")
        self.end_phase()

    def interruption(self, abrupt):
        self.start_phase("slow-stream")
        s = socket.create_connection(("127.0.0.1", PORT), timeout=2)
        try:
            s.sendall(
                b"POST /api/national/rankings HTTP/1.1\r\nHost: localhost\r\n"
                b"Content-Type: application/json\r\nContent-Length: "
                + str(len(BODY)).encode()
                + b"\r\n\r\n"
                + BODY
            )
            until(lambda: self.status()["active_jobs"] == 1, 10)
            assert self.workers() == 1
            started = time.monotonic()
            self.owned("container", API)
            if abrupt:
                self.docker(
                    "kill", "--signal", "KILL", self.resource_id("container", API)
                )
            else:
                self.docker("stop", "--time", "3", self.resource_id("container", API))
            state = self.owned("container", API)["State"]
            assert not state["Running"] and not state["OOMKilled"]
            if not abrupt:
                assert state["ExitCode"] != 137
            emit(
                "api-container-interrupted",
                abrupt=abrupt,
                elapsed_seconds=round(time.monotonic() - started, 2),
                exit_code=state["ExitCode"],
            )
        finally:
            s.close()
        self.end_phase()

    def cleanup(self, *, deadline=None):
        # Separate 30-second reserve, including the local HTTP worker teardown.
        self.deadline = time.monotonic() + 30 if deadline is None else deadline
        failures = []
        try:
            self.stop_http_worker()
        except Exception:  # noqa: BLE001 - continue owned Docker cleanup within reserve
            failures.append("local HTTP worker could not be reaped")
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
            http_worker_pid=None if self.http_worker is None else self.http_worker.pid,
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
                "published_port": "127.0.0.1:18081",
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
                http_worker_pid=None
                if review.http_worker is None
                else review.http_worker.pid,
                remaining_resources=[
                    {"kind": k, "name": n, "id": review.ids.get((k, n))}
                    for k, n in review.created
                ],
            )
            raise


if __name__ == "__main__":
    main()
