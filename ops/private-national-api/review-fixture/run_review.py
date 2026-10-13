"""Review-only controller. Docker mutations require explicit --execute approval."""

import argparse
import concurrent.futures
import hashlib
import http.client
import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NETWORK = "fairway-safety-review"
CANARY = "fairway-safety-canary-review"
API = "fairway-safety-api-review"
ROUTER = "fairway-safety-router-review"
IMAGES = ("fairway-safety-api:review", "fairway-safety-router:review")
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
ISOLATION = """import errno,json,os
assert os.getuid()==65532
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


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}), flush=True)


def verify_bundle():
    # CLI verification must not create an unlisted __pycache__ in the bundle.
    sys.dont_write_bytecode = True
    from bundle_integrity import verify

    return verify(ROOT)


def request(path="/health", body=None, timeout=35):
    client = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    try:
        client.request(
            "GET" if body is None else "POST",
            path,
            body=body,
            headers={} if body is None else {"Content-Type": "application/json"},
        )
        response = client.getresponse()
        raw = response.read(1048577)
        assert len(raw) <= 1048576
        return response.status, json.loads(raw), response.getheader("Retry-After")
    finally:
        client.close()


def until(check, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(0.2)
    raise TimeoutError("fixture condition deadline")


class Review:
    def __init__(self, images):
        self.images = images
        self.deadline = time.monotonic() + 540
        self.command = [
            "docker",
            "--host",
            f"unix:///run/user/{os.getuid()}/docker.sock",
        ]
        self.created = []
        self.baseline = None
        self.initial_bytes = None
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("DOCKER_")}

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
        info = self.document("info", "--format", "{{json .}}")
        assert "name=rootless" in info["SecurityOptions"]
        assert info["CgroupVersion"] == "2" and info["CgroupDriver"] == "systemd"
        for kind, names in (
            ("container", (API, ROUTER)),
            ("network", (NETWORK, CANARY)),
        ):
            for name in names:
                result = self.docker(kind, "inspect", name, check=False)
                assert result.returncode != 0, f"reserved {kind} already exists"
        with socket.socket() as s:
            s.bind(("127.0.0.1", PORT))
        manifest = json.loads((ROOT / "wheel-manifest.json").read_text())
        with (ROOT / "fixture_router.py").open("rb") as stream:
            fixture_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        for image, source_hash in zip(
            self.images,
            (manifest["applications"]["fairway"]["sha256"], fixture_hash),
            strict=True,
        ):
            row = self.document("image", "inspect", image)[0]
            assert row["Id"] == image and row["Architecture"] == "arm64"
            labels = row["Config"]["Labels"] or {}
            assert labels.get("fairway.safety.run") == "review"
            assert labels.get("fairway.safety.input.sha256") == source_hash
        self.baseline = self.live_snapshot()
        assert all(x["running"] for x in self.baseline)
        # Bundle must be staged on the same filesystem as DockerRootDir; otherwise
        # use explicit host-owner accounting before approving this controller.
        root_device = os.stat(info["DockerRootDir"]).st_dev
        assert root_device == ROOT.stat().st_dev
        self.initial_bytes = self.storage()
        assert self.initial_bytes >= 4 * 1024**3, "need at least 4 GiB free"

    def disk_budget(self):
        assert self.initial_bytes - self.storage() <= 2 * 1024**3, (
            "2 GiB added-space stop budget"
        )

    def network(self, name):
        self.created.append(("network", name))
        self.docker("network", "create", "--internal", "--label", LABEL, name)
        assert self.document("network", "inspect", name)[0]["Internal"]

    def container(self, name, image, network, memory, mode="normal"):
        args = [
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            LABEL,
            "--network",
            network,
            "--restart=no",
            "--init",
            "--user",
            "65532:65532",
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
        ]
        if name == API:
            args += ["--publish", f"127.0.0.1:{PORT}:8081"]
        else:
            args += ["--network-alias", "valhalla", "--env", f"FIXTURE_MODE={mode}"]
        self.created.append(("container", name))
        self.docker(*args, image)
        row = self.document("inspect", name)[0]
        host = row["HostConfig"]
        assert not row["Mounts"] and row["Config"]["User"] == "65532:65532"
        assert host["ReadonlyRootfs"] and not host["Privileged"]
        assert host["CapDrop"] == ["ALL"] and not host["CapAdd"]
        assert "no-new-privileges:true" in host["SecurityOpt"]
        assert host["RestartPolicy"]["Name"] == "no" and host["PidsLimit"] == 64
        assert set(row["NetworkSettings"]["Networks"]) == {network}
        assert host["PortBindings"] == (
            {"8081/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]}
            if name == API
            else {}
        )
        controls = self.document("exec", name, "python", "-c", ISOLATION)
        assert controls == {
            "memory.max": str((512 if name == API else 256) * 1024**2),
            "cpu.max": "100000 100000",
            "pids.max": "64",
        }
        emit("isolation-checked", component=name, effective_cgroups=controls)

    def remove_container(self, name):
        self.docker("stop", "--time", "3", name)
        self.docker("rm", name)
        self.created.remove(("container", name))

    def status(self):
        return self.document("exec", ROUTER, "python", "-c", STATUS)

    def workers(self):
        return self.document("exec", API, "python", "-c", WORKERS)

    def ready(self):
        def probe():
            try:
                return request(timeout=1)[0] == 200
            except OSError:
                return False

        for _ in range(8):
            if probe():
                return
            time.sleep(0.2)
        raise TimeoutError("API startup deadline / eight health requests")

    def start_phase(self, mode):
        self.container(ROUTER, self.images[1], NETWORK, "256m", mode)
        self.container(API, self.images[0], NETWORK, "512m")
        self.ready()
        until(lambda: self.status().get("fixture_only"), 3)

    def end_phase(self):
        self.remove_container(API)
        self.remove_container(ROUTER)

    def canary_and_busy(self):
        self.network(NETWORK)
        self.network(CANARY)
        self.container(ROUTER, self.images[1], CANARY, "256m", "hold-first")
        self.container(API, self.images[0], NETWORK, "512m")
        self.ready()
        until(lambda: self.status().get("fixture_only"), 3)
        ip = self.document("inspect", ROUTER)[0]["NetworkSettings"]["Networks"][CANARY][
            "IPAddress"
        ]
        probe = "import socket,sys\ns=socket.socket();s.settimeout(1)\ntry:s.connect((sys.argv[1],8002))\nexcept OSError:pass\nelse:raise AssertionError('cross-network reachable')\nfinally:s.close()"
        self.docker("exec", API, "python", "-c", probe, ip, timeout=3)
        emit("disposable-cross-network-canary-denied")
        self.docker("network", "connect", "--alias", "valhalla", NETWORK, ROUTER)
        self.docker("network", "disconnect", CANARY, ROUTER)
        self.docker("network", "rm", CANARY)
        self.created.remove(("network", CANARY))
        members = self.document("network", "inspect", NETWORK)[0]["Containers"]
        assert {x["Name"] for x in members.values()} == {API, ROUTER}
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(request, "/api/national/rankings", BODY)
            until(lambda: self.status()["active_jobs"] == 1, 10)
            second = request("/api/national/rankings", BODY)
            assert second[0] == 503 and second[2] == "10"
            assert first.result(timeout=25)[0] == 200
        assert request("/api/national/rankings", BODY)[0] == 200
        held = []
        try:
            for _ in range(8):
                s = socket.create_connection(("127.0.0.1", PORT), timeout=1)
                s.sendall(b"GET /health HTTP/1.1\r\n")
                held.append(s)
            time.sleep(0.2)
            assert request(timeout=2)[0] == 503
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
        self.container(ROUTER, self.images[1], NETWORK, "256m")
        assert request("/api/national/rankings", BODY)[0] == 200
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
            if abrupt:
                self.docker("kill", "--signal", "KILL", API)
            else:
                self.docker("stop", "--time", "3", API)
            state = self.document("inspect", API)[0]["State"]
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

    def cleanup(self):
        # Fresh deadline reserved for cleanup even after a command timeout.
        self.deadline = time.monotonic() + 30
        failures = []
        for kind, name in reversed(self.created):
            try:
                row = self.document(kind, "inspect", name)[0]
                labels = (
                    row.get("Config", {}).get("Labels")
                    if kind == "container"
                    else row.get("Labels")
                )
                assert labels and labels.get("fairway.safety.run") == "review"
                if kind == "container":
                    self.docker("stop", "--time", "3", name)
                self.docker(kind, "rm", name)
            except Exception:  # noqa: BLE001 - finish cleanup of other owned resources
                failures.append(name)
        if self.baseline is not None and self.live_snapshot() != self.baseline:
            failures.append("live routing snapshot changed; do not attempt repair")
        emit("cleanup", failed_resources=failures, prebuilt_images_retained=True)
        if failures:
            raise RuntimeError("cleanup or live-state verification failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--api-image-id")
    parser.add_argument("--fixture-image-id")
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
                "volumes": 0,
                "runtime_memory_mib": 768,
                "runtime_cpus": 2,
                "runtime_tasks": 128,
                "container_lifetime_seconds": 180,
                "whole_stage_seconds": 600,
            },
        )
        return
    if not all(
        re.fullmatch(r"sha256:[0-9a-f]{64}", value or "")
        for value in (args.api_image_id, args.fixture_image_id)
    ):
        parser.error(
            "execution requires two separately reviewed prebuilt SHA256 image IDs"
        )
    review = Review((args.api_image_id, args.fixture_image_id))

    def stop(signum, frame):
        raise InterruptedError("controller interrupted")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        review.preflight()
        review.canary_and_busy()
        review.disconnect_deadline()
        review.interruption(False)
        review.interruption(True)
        review.disk_budget()
        emit("fixture-stage-passed", native_valhalla_behavior_tested=False)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        review.cleanup()


if __name__ == "__main__":
    main()
