"""Rootless controller regressions with mocked Docker and in-memory HTTP parsers."""

import hashlib
import importlib.util
import io
import json
import subprocess
import traceback
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

FIXTURE = (
    Path(__file__).resolve().parents[1] / "ops/private-national-api/review-fixture"
)


@pytest.fixture
def controller(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "controller", FIXTURE / "run_review.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "fixture_router.py").write_text("# public synthetic fixture\n")
    (bundle / "SHA256SUMS").write_text("reviewed source manifest\n")
    monkeypatch.setattr(module, "ROOT", bundle)
    # A real subprocess or HTTP request is a test failure, even on failure paths.
    monkeypatch.setattr(
        subprocess, "run", Mock(side_effect=AssertionError("external call"))
    )
    module.request_impl = module.request
    monkeypatch.setattr(
        module, "request", Mock(side_effect=AssertionError("HTTP call"))
    )
    monkeypatch.setattr(
        subprocess, "Popen", Mock(side_effect=AssertionError("external process"))
    )
    review = module.Review(tmp_path / "prepared")
    return module, review


class FakeDocker:
    """Small stateful daemon model, inspecting the actual generated run arguments."""

    def __init__(self, module, review):
        self.m, self.review = module, review
        self.calls, self.objects = [], {}
        self.native_running = False
        self.native_name = False
        self.unsafe = None
        self.prep_failed = False

    def __call__(self, *args, timeout=10, check=True):
        self.calls.append(args)
        stdout, code = "", 0
        names = {row["Id"]: name for name, row in self.objects.items()}
        name_at_end = names.get(args[-1], args[-1])
        if args[0] == "ps":
            if "--quiet" in args:
                stdout = "native-id" if self.native_running else ""
            else:
                stdout = "modo-native-review-build" if self.native_name else ""
        elif args[:2] == ("network", "create"):
            self.objects[args[-1]] = {
                "Labels": {
                    "fairway.safety.run": "review",
                    "fairway.safety.owner": self.review.token,
                },
                "Internal": True,
                "Name": args[-1],
                "Driver": "bridge",
                "Id": hashlib.sha256(args[-1].encode()).hexdigest(),
                "Containers": {},
            }
            stdout = self.objects[args[-1]]["Id"]
        elif args[0] == "create":
            value = lambda flag: args[args.index(flag) + 1]
            name = value("--name")
            memory = {"1g": 1024, "512m": 512, "256m": 256}[value("--memory")]
            mount = dict(
                x.split("=", 1) for x in value("--mount").split(",") if "=" in x
            )
            host = {
                "ReadonlyRootfs": True,
                "Privileged": False,
                "CapDrop": ["ALL"],
                "CapAdd": [],
                "SecurityOpt": ["no-new-privileges:true"],
                "RestartPolicy": {"Name": "no"},
                "PidsLimit": 64,
                "Memory": memory * 1024**2,
                "MemorySwap": memory * 1024**2,
                "NanoCpus": 1_000_000_000,
                "LogConfig": {"Type": value("--log-driver")},
                "Init": True,
                "Devices": [],
                "Tmpfs": {},
                "PortBindings": {},
                "NetworkMode": value("--network"),
            }
            if name == self.m.API:
                host["PortBindings"] = {
                    "8081/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}]
                }
            if name == self.m.PREP:
                host["Tmpfs"] = {"/out": value("--tmpfs").split(":", 1)[1]}
            network_name = names.get(value("--network"), value("--network"))
            row = {
                "Id": hashlib.sha256(name.encode()).hexdigest(),
                "Name": "/" + name,
                "Config": {
                    "User": value("--user"),
                    "Labels": {
                        "fairway.safety.run": "review",
                        "fairway.safety.owner": self.review.token,
                    },
                },
                "HostConfig": host,
                "Mounts": [
                    {
                        "Type": "bind",
                        "Source": mount["src"],
                        "Destination": mount["dst"],
                        "RW": False,
                    }
                ],
                "NetworkSettings": {"Networks": {network_name: {"NetworkID": ""}}},
                "State": {
                    "Running": False,
                    "OOMKilled": self.prep_failed,
                },
            }
            if self.unsafe == "writable-mount":
                row["Mounts"][0]["RW"] = True
            if self.unsafe == "extra-mount":
                row["Mounts"].append({"Type": "volume"})
            if self.unsafe == "swap":
                host["MemorySwap"] = -1
            if self.unsafe == "privileged":
                host["Privileged"] = True
            self.objects[name] = row
            stdout = row["Id"]
        elif args[0] == "start":
            row = self.objects[name_at_end]
            row["State"]["Running"] = not self.prep_failed
            for network in row["NetworkSettings"]["Networks"]:
                if network != "none":
                    bridge = self.objects[network]
                    row["NetworkSettings"]["Networks"][network]["NetworkID"] = bridge[
                        "Id"
                    ]
                    bridge["Containers"][row["Id"]] = {"Name": name_at_end}
        elif args[0] == "inspect" or args[1:2] == ("inspect",):
            name = name_at_end
            if name in self.objects:
                stdout = json.dumps([self.objects[name]])
            else:
                code = 1
        elif args[0] == "exec":
            if self.m.ISOLATION in args:
                container_name = names.get(args[1], args[1])
                mib = (
                    1024
                    if container_name == self.m.PREP
                    else 512
                    if container_name == self.m.API
                    else 256
                )
                stdout = json.dumps(
                    {
                        "memory.max": str(mib * 1024**2),
                        "cpu.max": "100000 100000",
                        "pids.max": "64",
                    }
                )
            elif "/out/ready" in args[-1]:
                code = 0
        elif args[0] == "cp":
            target = Path(args[-1])
            target.mkdir()
            (target / "module.py").write_text("# installed public wheel code\n")
        elif args[0] == "stop":
            self.objects[name_at_end]["State"]["Running"] = False
        elif args[0] == "rm" or args[1:2] == ("rm",):
            row = self.objects.pop(name_at_end)
            for other in self.objects.values():
                if "Containers" in other:
                    other["Containers"].pop(row["Id"], None)
        else:
            raise AssertionError(f"unmodeled Docker action {args[:2]}")
        if check and code:
            raise RuntimeError("mock Docker failure")
        return subprocess.CompletedProcess(args, code, stdout, "")


def attach(module, review, monkeypatch):
    fake = FakeDocker(module, review)
    monkeypatch.setattr(review, "docker", fake)
    return fake


def test_sequential_preparation_then_readonly_runtime_and_owned_cleanup(
    controller, monkeypatch
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    assert m.PREP not in fake.objects
    receipt = json.loads((review.work / "receipt.json").read_text())
    assert (
        receipt["preparation_removed"]
        and receipt["installed_tree_sha256"] == review.site_digest
    )
    review.network(m.NETWORK)
    review.container(m.ROUTER, m.NETWORK, "256m")
    review.container(m.API, m.NETWORK, "512m")
    runs = [a for a in fake.calls if a[0] == "create"]
    assert len(runs) == 3
    for args in runs:
        assert "--pull=never" in args and m.BASE in args
        assert (
            args.count("--mount") == 1 and "readonly" in args[args.index("--mount") + 1]
        )
        assert "--read-only" in args and args[args.index("--cpus") + 1] == "1"
        assert args[args.index("--pids-limit") + 1] == "64"
        assert args[args.index("--entrypoint") + 1] == "/usr/bin/timeout"
        assert "180s" in args
        assert args[args.index("--log-driver") + 1] == "none"
        assert "--log-opt" not in args
        assert not any(x in args for x in ("run", "build", "pull", "commit", "load"))
    prep = runs[0]
    assert prep[prep.index("--network") + 1] == "none"
    assert prep[prep.index("--user") + 1] == "0:0"
    assert prep[prep.index("--tmpfs") + 1] == "/out:rw,size=512m,mode=0755"
    isolated = next(
        i for i, a in enumerate(fake.calls) if a[0] == "exec" and m.ISOLATION in a
    )
    barrier = next(
        i
        for i, a in enumerate(fake.calls)
        if a[0] == "exec" and "/out/allow-install" in a[-1]
    )
    removed = next(
        i
        for i, a in enumerate(fake.calls)
        if a[:2] == ("rm", review.resource_id("container", m.PREP))
    )
    network = next(
        i for i, a in enumerate(fake.calls) if a[:2] == ("network", "create")
    )
    assert isolated < barrier < removed < network
    review.cleanup()
    assert not fake.objects and not review.work.exists()


@pytest.mark.parametrize(
    "unsafe", ["writable-mount", "extra-mount", "swap", "privileged"]
)
def test_preparation_isolation_failure_never_releases_installer(
    controller, monkeypatch, unsafe
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    fake.unsafe = unsafe
    with pytest.raises(AssertionError):
        review.prepare()
    assert not any(a[0] == "exec" and "/out/allow-install" in a[-1] for a in fake.calls)
    review.cleanup()
    assert not fake.objects


@pytest.mark.parametrize("guard", ["running", "name"])
def test_native_guard_checked_again_before_creation(controller, monkeypatch, guard):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.native_absent()
    fake.native_running = guard == "running"
    fake.native_name = guard == "name"
    with pytest.raises(AssertionError, match="native review"):
        review.network(m.NETWORK)
    assert not review.created and not any(
        a[:2] == ("network", "create") for a in fake.calls
    )


def test_failed_installer_cannot_start_runtime(controller, monkeypatch):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    fake.prep_failed = True
    with pytest.raises(AssertionError, match="preparation failed"):
        review.prepare()
    with pytest.raises(AssertionError):
        review.container(m.API, m.NETWORK, "512m")
    assert not any(m.API in a for a in fake.calls)
    review.cleanup()


def test_changed_installed_tree_denies_runtime_before_docker(controller, monkeypatch):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    (review.work / "site/module.py").write_text("changed code")
    before = len(fake.calls)
    with pytest.raises(AssertionError):
        review.container(m.API, m.NETWORK, "512m")
    assert len(fake.calls) == before
    review.cleanup()


def test_cleanup_never_removes_replaced_object_and_retains_code(
    controller, monkeypatch
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    fake.objects[m.NETWORK]["Labels"]["fairway.safety.owner"] = "another-invocation"
    before = len(fake.calls)
    with pytest.raises(RuntimeError, match="cleanup"):
        review.cleanup()
    assert not any(a[:2] == ("network", "rm") for a in fake.calls[before:])
    assert review.work.exists() and m.NETWORK in fake.objects


@pytest.mark.parametrize(
    "path_kind", ["existing", "relative", "in-bundle", "comma", "symlink-parent"]
)
def test_invalid_work_directory_fails_without_external_action(
    controller, tmp_path, path_kind
):
    m, _ = controller
    path = tmp_path / "new"
    if path_kind == "existing":
        path.mkdir()
    elif path_kind == "relative":
        path = Path("relative")
    elif path_kind == "in-bundle":
        path = m.ROOT / "new"
    elif path_kind == "comma":
        path = tmp_path / "bad,mount"
    else:
        link = tmp_path / "linked"
        link.symlink_to(m.ROOT, target_is_directory=True)
        path = link / "new"
    with pytest.raises(ValueError):
        m.Review(path)


def test_installed_tree_rejects_links_and_records_content(controller):
    m, review = controller
    tree = review.work
    tree.mkdir()
    (tree / "module.py").write_text("first")
    initial = m.checked_tree(tree, make_readable=True)
    (tree / "module.py").write_text("second")
    assert m.checked_tree(tree) != initial
    (tree / "linked.py").symlink_to(tree / "module.py")
    with pytest.raises(AssertionError, match="links"):
        m.checked_tree(tree)


@pytest.mark.parametrize("barrier_open", [False, True])
def test_fixed_installer_waits_for_verified_isolation_and_uses_only_offline_wheels(
    controller, tmp_path, monkeypatch, barrier_open
):
    monkeypatch.syspath_prepend(str(FIXTURE))
    spec = importlib.util.spec_from_file_location(
        "installer", FIXTURE / "prepare_runtime.py"
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    inputs, output = tmp_path / "inputs", tmp_path / "out"
    inputs.mkdir()
    output.mkdir()
    if barrier_open:
        (output / "allow-install").touch()
    original = Path
    monkeypatch.setattr(
        installer,
        "Path",
        lambda path: original(
            str(path).replace("/inputs", str(inputs), 1).replace("/out", str(output), 1)
        ),
    )
    verified = Mock()
    monkeypatch.setattr(installer, "verify", verified)
    pip = Mock()
    monkeypatch.setattr(installer.subprocess, "run", pip)
    # Stop at the first sleep, either waiting for the gate or after successful pip.
    monkeypatch.setattr(
        installer.time, "sleep", Mock(side_effect=InterruptedError("test stop"))
    )
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    with pytest.raises(InterruptedError):
        installer.main()
    verified.assert_called_once_with(inputs)
    assert pip.call_count == (2 if barrier_open else 0)
    if barrier_open:
        assert (output / "ready").is_file()
        for call in pip.call_args_list:
            args = call.args[0]
            assert {
                "--isolated",
                "--no-index",
                "--no-deps",
                "--require-hashes",
                "--no-compile",
                "--no-cache-dir",
                "--only-binary=:all:",
            }.issubset(args)
            assert (
                "--find-links=/inputs/wheels" in args and "--target=/out/site" in args
            )
            assert not any(value.startswith("http") for value in args)
            assert call.kwargs["timeout"] == 120
    else:
        assert not (output / "site").exists()


def test_default_mode_verifies_inputs_without_external_calls(controller, monkeypatch):
    m, _ = controller
    monkeypatch.setattr(m, "verify_bundle", Mock())
    monkeypatch.setattr("sys.argv", ["run_review.py"])
    m.main()
    m.verify_bundle.assert_called_once()
    m.request.assert_not_called()
    subprocess.run.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        "missing-base",
        "wrong-digest",
        "wrong-arch",
        "oversized-base",
        "not-rootless",
        "wrong-cgroup",
    ],
)
def test_preflight_fails_closed_without_creating_or_fetching_resources(
    controller, monkeypatch, failure
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    monkeypatch.setattr(m.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(m.os, "getuid", lambda: 1000)
    monkeypatch.setattr(m.socket, "socket", MagicMock())
    info = {
        "SecurityOptions": ["name=rootless"],
        "CgroupVersion": "2",
        "CgroupDriver": "systemd",
    }
    image = {
        "Architecture": "arm64",
        "Os": "linux",
        "RepoDigests": [m.BASE],
        "Size": 1024**2,
    }
    if failure == "not-rootless":
        info["SecurityOptions"] = []
    elif failure == "wrong-cgroup":
        info["CgroupVersion"] = "1"
    elif failure == "wrong-digest":
        image["RepoDigests"] = ["python@sha256:" + "0" * 64]
    elif failure == "wrong-arch":
        image["Architecture"] = "amd64"
    elif failure == "oversized-base":
        image["Size"] = 1024**3 + 1

    def document(*args):
        if args[0] == "info":
            return info
        if args[:2] == ("image", "inspect"):
            if failure == "missing-base":
                raise RuntimeError("base absent")
            return [image]
        raise AssertionError("unexpected preflight action")

    monkeypatch.setattr(review, "document", document)
    with pytest.raises((RuntimeError, AssertionError)):
        review.preflight()
    assert not review.created and not review.work.exists()
    assert all(a[0] in {"ps", "container", "network"} for a in fake.calls)
    assert not any(
        "create" in a or a[0] in {"create", "run", "pull", "build", "load"}
        for a in fake.calls
    )


@pytest.mark.parametrize("delayed_visible", [False, True])
@pytest.mark.parametrize("kind", ["network", "container"])
def test_timed_out_create_reconciles_delayed_owned_object_or_retains_unknown(
    controller, monkeypatch, delayed_visible, capsys, kind
):
    m, review = controller
    fake = FakeDocker(m, review)
    hidden, lookups = False, 0
    resource_name = m.NETWORK if kind == "network" else m.PREP

    def delayed(*args, **kwargs):
        nonlocal hidden, lookups
        if args[:2] == ("network", "create") or args[0] == "create":
            fake(*args, **kwargs)
            hidden = True
            raise subprocess.TimeoutExpired("docker network create", 10)
        if hidden and args[:2] == (kind, "inspect") and args[-1] == resource_name:
            lookups += 1
            if not delayed_visible or lookups < 3:
                if kwargs.get("check", True):
                    raise RuntimeError("object not yet visible")
                return subprocess.CompletedProcess(args, 1, "", "")
            hidden = False
        return fake(*args, **kwargs)

    monkeypatch.setattr(review, "docker", delayed)
    monkeypatch.setattr(m.time, "sleep", Mock())
    with pytest.raises(subprocess.TimeoutExpired):
        review.network(m.NETWORK) if kind == "network" else review.prepare()
    assert (kind, resource_name) in review.uncertain_creates
    if delayed_visible:
        review.cleanup()
        assert lookups == 3 and not review.uncertain_creates and not fake.objects
    else:
        with pytest.raises(RuntimeError, match="cleanup"):
            review.cleanup()
        assert lookups == 6 and fake.objects
        outcome = json.loads(capsys.readouterr().out.splitlines()[-1])
        assert outcome["uncertain_creations"] == [
            {"kind": kind, "name": resource_name, "id": None}
        ]
        assert "creation outcome unknown" in outcome["failed_resources"][0]
        assert not any(a[1:2] == ("rm",) for a in fake.calls)
        if kind == "container":
            assert review.work.exists()


@pytest.mark.parametrize("change", ["replacement-id", "other-owner", "intruder"])
def test_replaced_or_contaminated_bridge_refused_before_container_creation(
    controller, monkeypatch, change
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    bridge = fake.objects[m.NETWORK]
    if change == "replacement-id":
        bridge["Id"] = "9" * 64
        bridge["Labels"]["fairway.safety.owner"] = "another-owner"
    elif change == "other-owner":
        bridge["Labels"]["fairway.safety.owner"] = "another-owner"
    else:
        bridge["Containers"]["9" * 64] = {"Name": "intruder"}
    before = len(fake.calls)
    with pytest.raises((AssertionError, RuntimeError)):
        review.container(m.API, m.NETWORK, "512m")
    assert not any(a[0] in {"create", "start"} for a in fake.calls[before:])
    assert any(
        a[-1] == review.resource_id("network", m.NETWORK) for a in fake.calls[before:]
    )


def test_bridge_owner_change_between_create_and_start_is_refused(
    controller, monkeypatch
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    original = review.docker

    def replaced(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == "create" and m.API in args:
            fake.objects[m.NETWORK]["Labels"]["fairway.safety.owner"] = "another-owner"
        return result

    monkeypatch.setattr(review, "docker", replaced)
    before = len(fake.calls)
    with pytest.raises(AssertionError, match="ownership"):
        review.container(m.API, m.NETWORK, "512m")
    assert not any(a[0] == "start" for a in fake.calls[before:])


def test_wrong_pending_network_id_refused_before_start(controller, monkeypatch):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    original = review.docker

    def wrong_endpoint(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == "create" and m.API in args:
            fake.objects[m.API]["NetworkSettings"]["Networks"][m.NETWORK][
                "NetworkID"
            ] = "9" * 64
        return result

    monkeypatch.setattr(review, "docker", wrong_endpoint)
    before = len(fake.calls)
    with pytest.raises(AssertionError):
        review.container(m.API, m.NETWORK, "512m")
    assert not any(a[0] == "start" for a in fake.calls[before:])


def test_reused_fixed_name_drops_previous_phase_id_before_uncertain_create(
    controller, monkeypatch
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    review.container(m.ROUTER, m.NETWORK, "256m")
    review.remove_container(m.ROUTER)
    old_id = review.resource_id("container", m.ROUTER)
    original = review.docker

    def late_create(*args, **kwargs):
        if args[0] == "create":
            raise subprocess.TimeoutExpired("docker create", 10)
        return original(*args, **kwargs)

    monkeypatch.setattr(review, "docker", late_create)
    with pytest.raises(subprocess.TimeoutExpired):
        review.container(m.ROUTER, m.NETWORK, "256m")
    assert ("container", m.ROUTER) not in review.ids
    assert ("container", m.ROUTER) in review.uncertain_creates
    before = len(fake.calls)
    with pytest.raises(RuntimeError):
        review.owned("container", m.ROUTER)
    assert fake.calls[before][-1] == m.ROUTER and fake.calls[before][-1] != old_id


def test_expired_http_clock_opens_no_socket(controller, monkeypatch):
    m, _ = controller
    connection = Mock()
    monkeypatch.setattr(m.http.client, "HTTPConnection", connection)
    monkeypatch.setattr(m.time, "monotonic", lambda: 100.0)
    with pytest.raises(TimeoutError, match="deadline"):
        m.request_impl(deadline=99.0)
    connection.assert_not_called()


def test_slow_body_trickle_obeys_absolute_deadline_and_closes(controller, monkeypatch):
    m, _ = controller
    clock = [100.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(m, "absolute_watchdog", lambda deadline: nullcontext())
    client, response = Mock(), Mock()
    client.getresponse.return_value = response
    response.isclosed.return_value = False
    response.length = None
    response.chunked = False
    constructor = Mock(return_value=client)
    monkeypatch.setattr(m.http.client, "HTTPConnection", constructor)

    def read1(cap):
        assert cap <= 65536
        clock[0] += 0.2
        return b" "  # never EOF; each read completes before inactivity timeout

    response.read1.side_effect = read1
    with pytest.raises(TimeoutError, match="deadline"):
        m.request_impl(timeout=35, deadline=100.5)
    assert response.read1.call_count == 3
    assert client.sock.settimeout.call_args_list[-1].args[0] < 0.11
    client.close.assert_called_once()


def test_http_body_size_cap_is_enforced_incrementally(controller, monkeypatch):
    m, _ = controller
    monkeypatch.setattr(m, "absolute_watchdog", lambda deadline: nullcontext())
    client, response = Mock(), Mock()
    client.getresponse.return_value = response
    response.isclosed.return_value = False
    response.length = None
    response.chunked = False
    monkeypatch.setattr(m.http.client, "HTTPConnection", Mock(return_value=client))
    response.read1.side_effect = lambda cap: b"x" * cap
    with pytest.raises(AssertionError, match="1 MiB"):
        m.request_impl()
    assert response.read1.call_count == 17
    assert response.read1.call_args.args == (1,)
    client.close.assert_called_once()


def test_independent_alarm_interrupts_slow_headers_without_api_timers(
    controller, monkeypatch
):
    m, _ = controller
    client = Mock()
    # No network: emulate a parser held by continuous slow headers.
    client.getresponse.side_effect = lambda: m.time.sleep(0.2)
    monkeypatch.setattr(m.http.client, "HTTPConnection", Mock(return_value=client))
    started = m.time.monotonic()
    with pytest.raises(TimeoutError, match="deadline"):
        m.request_impl(timeout=0.02)
    assert m.time.monotonic() - started < 0.15
    client.close.assert_called_once()


def test_nested_watchdog_keeps_earlier_controller_deadline(controller):
    m, _ = controller
    before = m.signal.getitimer(m.signal.ITIMER_REAL)
    handler = m.signal.getsignal(m.signal.SIGALRM)
    with (
        pytest.raises(TimeoutError, match="deadline"),
        m.absolute_watchdog(m.time.monotonic() + 0.02),
        m.absolute_watchdog(m.time.monotonic() + 0.2),
    ):
        m.time.sleep(0.1)
    assert m.signal.getitimer(m.signal.ITIMER_REAL) == before
    assert m.signal.getsignal(m.signal.SIGALRM) == handler


def test_worker_timeout_gets_terminate_kill_and_only_bounded_waits(controller):
    _, review = controller
    worker = Mock(pid=321)
    worker.poll.return_value = None
    worker.wait.side_effect = [subprocess.TimeoutExpired("client", 0.5), 0]
    review.http_worker = worker
    review.stop_http_worker()
    worker.terminate.assert_called_once()
    worker.kill.assert_called_once()
    assert worker.wait.call_count == 2
    assert all(0 < call.kwargs["timeout"] <= 0.5 for call in worker.wait.call_args_list)
    assert review.http_worker is None


def test_unreaped_client_is_reported_but_docker_cleanup_still_runs(
    controller, monkeypatch, capsys
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.network(m.NETWORK)
    worker = Mock(pid=321)
    worker.poll.return_value = None
    worker.wait.side_effect = subprocess.TimeoutExpired("client", 0.5)
    review.http_worker = worker
    with pytest.raises(RuntimeError, match="cleanup"):
        review.cleanup()
    assert not fake.objects and review.http_worker is worker
    assert worker.wait.call_count == 2
    event = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert event["http_worker_pid"] == 321
    assert "local HTTP worker could not be reaped" in event["failed_resources"]


def test_expired_controller_clock_starts_no_client_and_no_wait(controller, monkeypatch):
    m, review = controller
    monkeypatch.setattr(m.time, "monotonic", lambda: review.deadline + 1)
    with pytest.raises(TimeoutError):
        review.start_http_worker()
    subprocess.Popen.assert_not_called()
    worker = Mock(pid=321)
    worker.poll.return_value = None
    review.http_worker = worker
    with pytest.raises(TimeoutError):
        review.stop_http_worker()
    worker.wait.assert_not_called()


def test_contention_client_is_fixed_loopback_helper_with_finite_result_wait(
    controller, monkeypatch
):
    m, review = controller
    worker = Mock(pid=321, returncode=0)
    worker.communicate.return_value = (b'{"status":200}\n', None)
    popen = Mock(return_value=worker)
    monkeypatch.setattr(subprocess, "Popen", popen)
    review.start_http_worker()
    args = popen.call_args.args[0]
    assert args[:4] == [m.sys.executable, "-B", "-c", m.HTTP_WORKER]
    assert args[4] == str(m.ROOT / "run_review.py")
    assert (
        "--execute" not in args
        and popen.call_args.kwargs["stderr"] == subprocess.DEVNULL
    )
    assert review.http_worker_result() == 200
    assert 0 < worker.communicate.call_args.kwargs["timeout"] <= 25


def test_controller_alarm_preserves_fresh_cleanup_reserve(controller, monkeypatch):
    m, review = controller
    review.deadline = m.time.monotonic() + 0.02
    monkeypatch.setattr(m, "verify_bundle", Mock())
    monkeypatch.setattr(m, "Review", lambda path: review)
    monkeypatch.setattr(
        "sys.argv", ["run_review.py", "--execute", "--work-directory", str(review.work)]
    )
    monkeypatch.setattr(review, "preflight", lambda: m.time.sleep(0.2))
    observed = []

    def cleanup(*, deadline):
        observed.append(
            (deadline - m.time.monotonic(), m.signal.getitimer(m.signal.ITIMER_REAL)[0])
        )

    monkeypatch.setattr(review, "cleanup", cleanup)
    handlers = {
        sig: m.signal.getsignal(sig) for sig in (m.signal.SIGTERM, m.signal.SIGINT)
    }
    try:
        with pytest.raises(TimeoutError, match="deadline"):
            m.main()
    finally:
        for sig, handler in handlers.items():
            m.signal.signal(sig, handler)
    assert len(observed) == 1 and all(29 < seconds <= 30 for seconds in observed[0])
    assert m.signal.getitimer(m.signal.ITIMER_REAL)[0] == 0


def test_expired_cleanup_clock_never_claims_success_or_removes_output(
    controller, monkeypatch, capsys
):
    m, review = controller
    review.work.mkdir()
    review.work_created = True
    expired = m.time.monotonic() - 1
    with pytest.raises(RuntimeError, match="cleanup"):
        review.cleanup(deadline=expired)
    assert review.work.exists()
    event = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert (
        "cleanup deadline expired; completion unconfirmed" in event["failed_resources"]
    )
    assert event["prepared_directory_retained"] is True


class MemoryHTTPStream(io.BytesIO):
    """Real response parser input with controllable read1, never a socket."""

    def __init__(self, payload, transport, read_hook=None):
        super().__init__(payload)
        self.transport = transport
        self.read_hook = read_hook
        self.close_calls = 0
        self.readline_hook = None

    def readline(self, size=-1):
        if self.readline_hook is not None:
            return self.readline_hook(self, size)
        return super().readline(size)

    def read1(self, size=-1):
        if self.read_hook is not None:
            return self.read_hook(self, size)
        return super().read1(size)

    def close(self):
        self.close_calls += 1
        self.transport.file_closed = True
        super().close()


class MemoryHTTPTransport:
    """Models a detached Connection:close socket's remaining file lifetime."""

    def __init__(self, payload, read_hook=None):
        self.file_closed = False
        self.timeouts, self.closed_timeout_calls = [], 0
        self.stream = MemoryHTTPStream(payload, self, read_hook)
        self.close_calls = 0
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def makefile(self, mode):
        assert mode == "rb"
        return self.stream

    def settimeout(self, value):
        if self.file_closed:
            self.closed_timeout_calls += 1
            raise OSError(9, "Bad file descriptor")
        self.timeouts.append(value)

    def close(self):
        # HTTPConnection may close its reference while HTTPResponse.fp lives.
        self.close_calls += 1


def memory_http_client(module, monkeypatch, payload, read_hook=None):
    """Use actual HTTPConnection and HTTPResponse, replace only connect transport."""
    connection_class = module.http.client.HTTPConnection
    transport = MemoryHTTPTransport(payload, read_hook)
    responses = []

    class MemoryConnection(connection_class):
        @property
        def response_class(self):
            def factory(*args, **kwargs):
                response = self.parser_class(*args, **kwargs)
                response.close = Mock(wraps=response.close)
                responses.append(response)
                return response

            return factory

        @response_class.setter
        def response_class(self, parser_class):
            self.parser_class = parser_class

    client = MemoryConnection("127.0.0.1", module.PORT)
    client.parser_class = module.http.client.HTTPResponse
    client.connect = lambda: setattr(client, "sock", transport)
    monkeypatch.setattr(module.http.client, "HTTPConnection", Mock(return_value=client))
    return client, transport, responses


@pytest.mark.parametrize("connection_close", [False, True])
def test_real_parser_fixed_length_closes_without_touching_dead_transport(
    controller, monkeypatch, connection_close
):
    m, _ = controller
    body = b'{"ok":true}'
    headers = b"Connection: close\r\n" if connection_close else b""
    payload = (
        b"HTTP/1.1 200 OK\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n"
        + headers
        + b"Retry-After: 10\r\n\r\n"
        + body
    )
    client, transport, responses = memory_http_client(m, monkeypatch, payload)
    assert m.request_impl() == (200, {"ok": True}, "10")
    assert transport.closed_timeout_calls == 0 and transport.file_closed
    assert client.sock is None
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize("body", [b'{"ok":true}', b"", b'{"ok":'])
def test_real_parser_overstated_content_length_is_not_accepted_as_json(
    controller, monkeypatch, body
):
    m, _ = controller
    payload = (
        b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "
        + str(len(body) + 3).encode()
        + b"\r\n\r\n"
        + body
    )
    _, transport, responses = memory_http_client(m, monkeypatch, payload)
    with pytest.raises(m.http.client.IncompleteRead) as failure:
        m.request_impl()
    assert failure.value.expected == 3 and failure.value.partial == body
    assert transport.closed_timeout_calls == 0 and transport.file_closed
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize("body", [b"", b"{invalid}"])
def test_real_parser_zero_length_and_json_errors_close_response(
    controller, monkeypatch, body
):
    m, _ = controller
    payload = (
        b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    _, transport, responses = memory_http_client(m, monkeypatch, payload)
    with pytest.raises(json.JSONDecodeError):
        m.request_impl()
    assert transport.closed_timeout_calls == 0 and transport.file_closed
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize("connection_close", [False, True])
def test_real_parser_complete_chunked_response_is_read_through_framing(
    controller, monkeypatch, connection_close
):
    m, _ = controller
    header = b"Connection: close\r\n" if connection_close else b""
    # Deliberately use correct framing for split JSON, not Mock.read1 chunks.
    payload = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        + header
        + b'\r\n5\r\n{"ok"\r\n6\r\n:true}\r\n0\r\n\r\n'
    )
    _, transport, responses = memory_http_client(m, monkeypatch, payload)
    assert m.request_impl()[:2] == (200, {"ok": True})
    assert transport.closed_timeout_calls == 0 and transport.file_closed
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize(
    "framed",
    [b'B\r\n{"ok":true}', b'B\r\n{"ok":true}\r\n', b'C\r\n{"ok":true}\r\n0\r\n\r\n'],
)
def test_real_parser_truncated_chunked_json_cannot_be_accepted(
    controller, monkeypatch, framed
):
    m, _ = controller
    payload = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        + framed
    )
    _, transport, responses = memory_http_client(m, monkeypatch, payload)
    with pytest.raises(m.http.client.IncompleteRead):
        m.request_impl()
    assert transport.closed_timeout_calls == 0 and transport.file_closed
    assert responses[0].close.call_count >= 1


def test_real_parser_slow_read_is_stopped_by_independent_alarm_and_closed(
    controller, monkeypatch
):
    m, _ = controller
    payload = (
        b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{"ok":true}'
    )

    def slow(stream, size):
        m.time.sleep(0.2)
        return super(MemoryHTTPStream, stream).read1(size)

    _, transport, responses = memory_http_client(m, monkeypatch, payload, slow)
    with pytest.raises(TimeoutError, match="deadline"):
        m.request_impl(timeout=0.02)
    assert transport.file_closed
    assert responses[0].close.call_count >= 1


def test_real_parser_read_error_closes_response(controller, monkeypatch):
    m, _ = controller
    payload = (
        b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{"ok":true}'
    )

    def broken(stream, size):
        raise OSError("synthetic read failure")

    _, transport, responses = memory_http_client(m, monkeypatch, payload, broken)
    with pytest.raises(OSError, match="synthetic read"):
        m.request_impl()
    assert transport.file_closed
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize("declared_length", [None, 20])
def test_real_parser_timer_generated_eof_is_deadline_failure_even_after_valid_json(
    controller, monkeypatch, declared_length
):
    m, _ = controller
    clock = [100.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(m, "absolute_watchdog", lambda deadline: nullcontext())
    length = b"" if declared_length is None else b"Content-Length: 20\r\n"
    payload = b"HTTP/1.1 200 OK\r\nConnection: close\r\n" + length + b'\r\n{"ok":true}'

    def timer_eof(stream, size):
        if stream.tell() == len(payload):
            clock[0] = 101.0
            return b""  # timer-induced shutdown, not successful completed JSON
        return super(MemoryHTTPStream, stream).read1(size)

    _, transport, responses = memory_http_client(m, monkeypatch, payload, timer_eof)
    with pytest.raises(TimeoutError, match="deadline"):
        m.request_impl(deadline=100.5)
    assert transport.file_closed
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize(
    "framed",
    [
        b'B\r\n{"ok":true}XX0\r\n\r\n',  # stdlib normally discards invalid CRLF
        b'B\r\n{"ok":true}\r\n0\r\n',  # EOF is not the final trailer terminator
        b'B\r\n{"ok":true}\r\n0\r\nX: value\r\n',
    ],
)
def test_real_parser_chunk_terminators_and_trailer_eof_are_strict(
    controller, monkeypatch, framed
):
    m, _ = controller
    payload = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        + framed
    )
    _, transport, responses = memory_http_client(m, monkeypatch, payload)
    with pytest.raises(m.http.client.IncompleteRead):
        m.request_impl()
    assert transport.file_closed and transport.closed_timeout_calls == 0
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize(
    "trailers", [b"X: " + b"x" * 8192 + b"\r\n", b"X: value\r\n" * 32]
)
def test_real_parser_chunked_trailers_have_finite_byte_and_count_caps(
    controller, monkeypatch, trailers
):
    m, _ = controller
    payload = (
        b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\nB\r\n{"ok":true}\r\n0\r\n'
        + trailers
        + b"\r\n"
    )
    _, transport, responses = memory_http_client(m, monkeypatch, payload)
    with pytest.raises(m.http.client.HTTPException):
        m.request_impl()
    assert transport.file_closed and responses[0].close.call_count >= 1


@pytest.mark.parametrize("stage", ["headers", "chunk-size", "trailers"])
def test_real_parser_absolute_alarm_closes_during_slow_line_parsing(
    controller, monkeypatch, stage
):
    m, _ = controller
    headers = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
    )
    chunks = b'B\r\n{"ok":true}\r\n0\r\n'
    payload = headers + chunks + b"\r\n"
    positions = {
        "headers": 0,
        "chunk-size": len(headers),
        "trailers": len(headers + chunks),
    }
    _, transport, responses = memory_http_client(m, monkeypatch, payload)

    def slow_line(stream, size):
        if stream.tell() == positions[stage]:
            m.time.sleep(0.2)
        return super(MemoryHTTPStream, stream).readline(size)

    transport.stream.readline_hook = slow_line
    with pytest.raises(TimeoutError, match="deadline"):
        m.request_impl(timeout=0.02)
    assert transport.file_closed
    assert responses[0].close.call_count >= 1


def test_real_parser_malformed_status_closes_response_before_getresponse_returns(
    controller, monkeypatch
):
    m, _ = controller
    _, transport, responses = memory_http_client(
        m, monkeypatch, b"invalid status\r\n\r\n"
    )
    with pytest.raises(m.http.client.BadStatusLine):
        m.request_impl()
    assert transport.file_closed
    assert responses[0].close.call_count >= 1


def test_real_parser_expiry_during_json_processing_is_rejected_and_closed(
    controller, monkeypatch
):
    m, _ = controller
    clock = [100.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(m, "absolute_watchdog", lambda deadline: nullcontext())
    payload = (
        b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{"ok":true}'
    )
    _, transport, responses = memory_http_client(m, monkeypatch, payload)
    original = m.json.loads

    def delayed_json(raw):
        result = original(raw)
        clock[0] = 101.0
        return result

    monkeypatch.setattr(m.json, "loads", delayed_json)
    with pytest.raises(TimeoutError, match="deadline"):
        m.request_impl(deadline=100.5)
    assert transport.file_closed and transport.closed_timeout_calls == 0
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize("version", [b"HTTP/1.0", b"HTTP/1.1"])
def test_real_parser_valid_close_delimited_eof_without_declared_length(
    controller, monkeypatch, version
):
    m, _ = controller
    _, transport, responses = memory_http_client(
        m, monkeypatch, version + b' 200 OK\r\nConnection: close\r\n\r\n{"ok":true}'
    )
    assert m.request_impl()[:2] == (200, {"ok": True})
    assert transport.file_closed and transport.closed_timeout_calls == 0
    assert responses[0].close.call_count >= 1


@pytest.mark.parametrize("length", [1048576, 1048577])
def test_real_parser_body_cap_and_completed_file_lifetime(
    controller, monkeypatch, length
):
    m, _ = controller
    body = b'"' + b"x" * (length - 2) + b'"'
    payload = (
        b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "
        + str(length).encode()
        + b"\r\n\r\n"
        + body
    )
    _, transport, responses = memory_http_client(m, monkeypatch, payload)
    if length == 1048576:
        result = m.request_impl()
        assert result[0] == 200 and len(result[1]) == length - 2
    else:
        with pytest.raises(AssertionError, match="1 MiB"):
            m.request_impl()
    assert transport.file_closed and transport.closed_timeout_calls == 0
    assert responses[0].close.call_count >= 1


def test_connection_close_still_runs_when_explicit_response_close_raises(
    controller, monkeypatch
):
    m, _ = controller
    client, _, responses = memory_http_client(
        m,
        monkeypatch,
        b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 11\r\n\r\n{"ok":true}',
    )
    original = client.getresponse

    def parsed():
        response = original()
        response.close = Mock(side_effect=OSError("synthetic close failure"))
        return response

    client.getresponse = parsed
    close = Mock(wraps=client.close)
    client.close = close
    with pytest.raises(OSError, match="synthetic close"):
        m.request_impl()
    assert responses[0].close.call_count >= 1
    assert close.call_count >= 2  # detachment plus request finally, despite close error


@pytest.mark.parametrize("checked", [False, True])
def test_docker_failure_record_keeps_only_allowed_bounded_fields(
    controller, monkeypatch, capsys, checked
):
    m, review = controller
    identifier = "a" * 64
    review.ids[("container", m.API)] = identifier
    review.cleanup_mode = True
    result = subprocess.CompletedProcess(
        [],
        1,
        "NEVER_PRINT_STDOUT_ENV",
        "compression cannot be enabled when max file count is 1",
    )
    monkeypatch.setattr(subprocess, "run", Mock(return_value=result))
    args = ("start", identifier, "/home/nas/private-marker", "password=NEVER_ARGV")
    if checked:
        with pytest.raises(RuntimeError, match="Docker command failed"):
            review.docker(*args, timeout=4)
    else:
        assert review.docker(*args, timeout=4, check=False) is result
    event = json.loads(capsys.readouterr().out)
    assert event["operation"] == ["start"] and event["resources"] == [identifier]
    assert event["returncode"] == 1 and event["timeout_seconds"] == 4
    assert event["cleanup"] is True and event["checked"] is checked
    assert event["stderr_preview"] == result.stderr
    assert not any(
        value in json.dumps(event)
        for value in ("NEVER_PRINT_STDOUT_ENV", "NEVER_ARGV", "private-marker")
    )


def test_timeout_partial_stderr_is_redacted_without_resolving_create_uncertainty(
    controller, monkeypatch, capsys
):
    m, review = controller
    failure = subprocess.TimeoutExpired(
        "SECRET_ARGV",
        2,
        output=b"SECRET_STDOUT",
        stderr=b"token=SECRET_TOKEN\nstart failed\xff",
    )
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=failure))
    with pytest.raises(TimeoutError) as raised:
        review.create_resource("container", m.PREP, ["create", "--name", m.PREP])
    assert "SECRET" not in str(raised.value)
    assert ("container", m.PREP) in review.uncertain_creates
    event = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert event["exception_type"] == "TimeoutExpired" and event["resources"] == [
        m.PREP
    ]
    assert event["returncode"] is None
    assert "start failed" in event["stderr_preview"]
    assert not any(
        value in json.dumps(event)
        for value in ("SECRET_TOKEN", "SECRET_STDOUT", "SECRET_ARGV")
    )
    assert review.ids == {}  # Diagnostics do not confirm a timed-out creation.


@pytest.mark.parametrize(
    "payload",
    [
        "界" * 10000,
        b"x" * 10000,
        "\x1b\x00\r\x7f\u202e" + "z" * 5000,
        "TOKEN=" + "x" * 10000,
    ],
)
def test_stderr_scan_utf8_retention_truncation_and_controls(controller, payload):
    m, _ = controller
    preview, clipped = m.diagnostic_stderr(payload)
    assert len(preview.encode("utf-8")) <= 4096 and clipped
    assert not any(char in preview for char in ("\x1b", "\x00", "\r", "\x7f", "\u202e"))


def test_stderr_redacts_named_secrets_private_paths_url_data_and_key_block(controller):
    m, _ = controller
    payload = """failed /home/person/private-folder
API_KEY=fake-api-credential
Authorization: Bearer fake-bearer-credential
PASSWORD=fake-password
HTTPS://user:fake-url-credential@example.invalid/path?token=fake-query
ssh://person@example.invalid/private
C:\\Users\\person\\private-folder
-----BEGIN PRIVATE KEY-----
synthetic-fixture-only-no-key-material
-----END PRIVATE KEY-----
"""
    preview, _ = m.diagnostic_stderr(payload)
    assert (
        "[private-path]" in preview
        and "[url]" in preview
        and "[redacted key]" in preview
    )
    assert not any(
        value in preview
        for value in (
            "private-folder",
            "fake-api",
            "fake-bearer",
            "fake-password",
            "fake-url",
            "fake-query",
            "synthetic-fixture-only",
        )
    )


def test_unknown_operation_and_copy_failure_never_publish_args_or_stdout(
    controller, monkeypatch, capsys
):
    m, review = controller
    review.failed_command(
        ("SECRET_COMMAND", "SECRET_ARG", "password=value"),
        1,
        checked=False,
        stderr="generic failure",
    )
    event = json.loads(capsys.readouterr().out)
    assert event["operation"] == ["unknown"] and event["resources"] == []
    assert "SECRET" not in json.dumps(event)
    identifier = "b" * 64
    review.ids[("container", m.PREP)] = identifier
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                [], 1, "SECRET_STDOUT", "copy failed /tmp/private-output"
            )
        ),
    )
    with pytest.raises(RuntimeError):
        review.docker("cp", identifier + ":/out/site", "/tmp/private-output")
    event = json.loads(capsys.readouterr().out)
    assert event["operation"] == ["cp"] and event["resources"] == [identifier]
    assert "private-output" not in event[
        "stderr_preview"
    ] and "SECRET_STDOUT" not in json.dumps(event)
    assert subprocess.run.call_args.kwargs["capture_output"] is True


def test_docker_oserror_does_not_reproduce_private_filename_or_raw_message(
    controller, monkeypatch, capsys
):
    m, review = controller
    failure = OSError("SECRET_ERROR /home/user/privatefile")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=failure))
    with pytest.raises(RuntimeError, match="invocation failed") as raised:
        review.docker("start", m.API)
    event = json.loads(capsys.readouterr().out)
    assert event["exception_type"] == "OSError"
    assert "SECRET" not in str(raised.value) and "privatefile" not in str(raised.value)
    assert "SECRET" not in json.dumps(event) and "privatefile" not in json.dumps(event)


@pytest.mark.parametrize("stage", ["generation", "write"])
@pytest.mark.parametrize("original", ["timeout", "oserror", "interrupt", "exit"])
@pytest.mark.parametrize("diagnostic", ["pipe", "space", "alarm", "interrupt", "exit"])
def test_diagnostic_failure_traceback_never_restores_raw_subprocess_context(
    controller, monkeypatch, stage, original, diagnostic
):
    m, review = controller
    original_errors = {
        "timeout": subprocess.TimeoutExpired("SECRET_ARGV", 2, stderr=b"partial"),
        "oserror": OSError(28, "SECRET_MESSAGE", "/srv/SECRET_FILENAME"),
        "interrupt": KeyboardInterrupt("SECRET_INTERRUPT"),
        "exit": SystemExit("SECRET_EXIT"),
    }
    diagnostic_errors = {
        "pipe": BrokenPipeError("SECRET_DIAGNOSTIC"),
        "space": OSError(28, "SECRET_DIAGNOSTIC", "/srv/SECRET_LOGFILE"),
        "alarm": TimeoutError("SECRET_DIAGNOSTIC"),
        "interrupt": KeyboardInterrupt("SECRET_DIAGNOSTIC"),
        "exit": SystemExit("SECRET_DIAGNOSTIC"),
    }
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=original_errors[original]))
    target = "diagnostic_stderr" if stage == "generation" else "emit"
    monkeypatch.setattr(m, target, Mock(side_effect=diagnostic_errors[diagnostic]))
    expected = {
        "timeout": TimeoutError,
        "oserror": RuntimeError,
        "interrupt": KeyboardInterrupt,
        "exit": InterruptedError,
    }[original]
    if diagnostic in {"alarm", "interrupt", "exit"}:
        expected = {
            "alarm": TimeoutError,
            "interrupt": KeyboardInterrupt,
            "exit": InterruptedError,
        }[diagnostic]
    args = ("start", m.API, "SECRET_ARGV")
    with pytest.raises(expected) as raised:
        review.docker(*args)
    formatted = "".join(traceback.format_exception(raised.value))
    assert "SECRET" not in formatted
    assert raised.value.__suppress_context__


def test_failed_diagnostic_during_create_keeps_uncertainty_and_owned_cleanup(
    controller, monkeypatch, capsys
):
    m, review = controller
    fake = attach(m, review, monkeypatch)
    review.prepare()
    review.network(m.NETWORK)
    saved_emit = m.emit

    def broken_record(event, **fields):
        if event == "docker-command-failed":
            raise BrokenPipeError("SECRET_LOG_FAILURE")
        saved_emit(event, **fields)

    monkeypatch.setattr(m, "emit", broken_record)
    monkeypatch.setattr(review, "docker", m.Review.docker.__get__(review))
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(side_effect=subprocess.TimeoutExpired("SECRET_ARGV", 1)),
    )
    with pytest.raises(TimeoutError):
        review.create_resource("container", m.API, ["create", "--name", m.API])
    assert ("container", m.API) in review.uncertain_creates
    # A late owned create is reconciled during cleanup, never assumed absent.
    fake(
        *review.run_arguments(
            m.API, review.resource_id("network", m.NETWORK), "512m", "65532:65532"
        ),
        "--mount",
        f"type=bind,src={review.work / 'site'},dst=/opt/prepared,readonly",
    )
    monkeypatch.setattr(review, "docker", fake)
    review.cleanup()
    assert not fake.objects and not review.uncertain_creates and not review.created
    assert "SECRET" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "path",
    [
        "/home/alice/Private Client/record.txt",
        "/srv/private-client/record.txt",
        "C:\\Private Client\\record.txt",
    ],
)
def test_path_bearing_stderr_suppresses_complete_path_line(controller, path):
    m, _ = controller
    preview, _ = m.diagnostic_stderr(f"invalid mount source: {path}\ncopy failed")
    assert preview == "[private-path]\ncopy failed"
    assert "record.txt" not in preview and "Client" not in preview


@pytest.mark.parametrize(
    "mode", ["success", "late-copy", "early-exit", "short-outer", "late-result"]
)
def test_preparation_uses_shared_lifetime_and_refuses_unsafe_copy(
    controller, monkeypatch, mode
):
    m, review = controller
    clock = [100.0]
    original_deadline = 130.0 if mode == "short-outer" else 640.0
    review.deadline = original_deadline
    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])
    watchdogs = []

    def watchdog(deadline):
        watchdogs.append(deadline)
        if deadline <= clock[0]:
            raise TimeoutError("absolute test deadline")
        return nullcontext()

    monkeypatch.setattr(m, "absolute_watchdog", watchdog)
    fake = attach(m, review, monkeypatch)
    seen_ready = False
    observed = []

    def docker(*args, **kwargs):
        nonlocal seen_ready
        observed.append((args, review.deadline))
        if args[0] == "exec" and "/out/ready" in args[-1]:
            seen_ready = True
            if mode in {"late-copy", "early-exit"}:
                # Ready shortly before the reserved boundary; the subsequent
                # owned-state lookup spends another two seconds of that budget.
                clock[0] = 244.0
        elif seen_ready and args[:2] == ("container", "inspect"):
            clock[0] += 2
            if mode == "early-exit":
                fake.objects[m.PREP]["State"]["Running"] = False
        if args[0] == "cp" and mode == "late-result":
            clock[0] = 276.0
        return fake(*args, **kwargs)

    monkeypatch.setattr(review, "docker", docker)
    if mode == "success":
        review.prepare()
        assert review.site_digest and (review.work / "receipt.json").is_file()
    else:
        expected = AssertionError if mode == "early-exit" else TimeoutError
        with pytest.raises(expected):
            review.prepare()
        assert not review.site_digest and not (review.work / "receipt.json").exists()
        assert any(args[0] == "cp" for args, _ in observed) == (mode == "late-result")
    assert review.deadline == original_deadline  # Restore outer work/cleanup budget.
    assert watchdogs[0] == min(original_deadline, 280.0)
    assert min(original_deadline, 280.0) - 35 in watchdogs
    if mode == "success":
        assert 275.0 in watchdogs
        cp = next(row for row in observed if row[0][0] == "cp")
        assert cp[1] == 280.0
    monkeypatch.setattr(review, "docker", fake)
    review.cleanup()
    assert not fake.objects and not review.created


def test_unchecked_failure_with_broken_diagnostic_write_aborts_safely(
    controller, monkeypatch
):
    m, review = controller
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess([], 1, "SECRET_STDOUT", "failed")
        ),
    )
    monkeypatch.setattr(m, "emit", Mock(side_effect=OSError(28, "SECRET_LOG_FAILURE")))
    with pytest.raises(RuntimeError, match="diagnostic recording failed") as raised:
        review.docker("start", m.API, check=False)
    assert "SECRET" not in "".join(traceback.format_exception(raised.value))
