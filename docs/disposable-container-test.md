# Disposable private API test proposal, not executed

This replaces the earlier shared-Spark-build proposal. The controller now accepts
only two separately reviewed, already available SHA256 image IDs. It contains no
build, pull, import or image-removal path. No suitable images exist yet. Creation
of a bounded build host, image import, Spark staging and container execution all
remain separate review actions. No daemon changes, sudo or credentials are needed
by the proposed runtime test. No such action has been executed.

## Build resources, separate from runtime

Preferred path: an already approved disposable Linux arm64 build VM with hard host
limits of2 vCPUs,2GiB RAM, no swap, a dedicated4GiB writable disk and no personal
services/data/credentials. These whole-host bounds contain builder, pulls,
decompression and install work; a limit applied only to the Docker CLI does not.
No VM or paid service creation is authorized here. If that build environment is
unavailable, stop at this proposal. Do not build on Spark's shared daemon instead.

Use the digest-pinned official CPython arm64/v8 base:
`docker.io/library/python:3.12.14-slim-bookworm@sha256:eb5be8e5b4d0a159c237946bbdd06356dda5d19c30fc4f7843e8046d3a590333`.

The API image installs only these hash-locked wheel dependencies:
geographiclib2.1, gunicorn26.2.0, networkx3.6.1, NumPy2.5.2,
packaging26.3, SciPy1.18.1, plus local fairway0.6.2 and modo0.3.7.
modo source is exact merged257c680d6acf6917ac47df6521d44ab1b35f6d1a.
The fixture uses only Python stdlib. There is no apt install, compiler, road
artifact download, extra routing engine, SSH key or Docker socket in either image.
Build registry/PyPI access is confined to that isolated build host.

Current review wheel SHA256:
- fairway:633c2ecc39d5cddd6004bbf567e5bdd481439a060c62d1b0ae3f7f8b89d129c9
- modo:4e3a7f1240b83243bafa4a1d0782245457f6402f17772b4c647982b8d3795860

Inside the exact review bundle on that separately approved bounded build host:

```sh
sha256sum --check SHA256SUMS
# Build sequentially; outer client limit300s total. Whole-host limits also apply.
/usr/bin/timeout --signal=TERM --kill-after=5s 300s sh -eu -c '
  docker build --platform linux/arm64 --label fairway.safety.run=review \
    --label fairway.safety.input.sha256=633c2ecc39d5cddd6004bbf567e5bdd481439a060c62d1b0ae3f7f8b89d129c9 \
    -f Dockerfile.api -t fairway-safety-api:review .
  docker build --platform linux/arm64 --label fairway.safety.run=review \
    --label fairway.safety.input.sha256=d5c53953db64db7eb8ce3134dccad4514a21468ada9755722bbabc3ecb626439 \
    -f Dockerfile.fixture -t fairway-safety-router:review .
'
docker image inspect --format '{{.Id}} {{.Architecture}}' \
  fairway-safety-api:review fairway-safety-router:review
/usr/bin/timeout --signal=TERM --kill-after=5s 30s \
  docker save -o fairway-safety-images.tar \
  fairway-safety-api:review fairway-safety-router:review
sha256sum fairway-safety-images.tar
```

Client timeout alone does not establish cancellation of daemon build work. Stop
criteria are any build/space/time failure; retain evidence then stop/discard the
entire disposable build VM through its separately approved lifecycle, bounding
remaining processes and cache. Do not repair the failure with Spark builds or
broader privileges. No build host currently exists or has been approved.

Review the built image IDs, provenance and archive SHA before separately approving
import. Pre-existing reviewed images could eliminate the build step. No image IDs
are supplied here because images have not been built. Import/pull extraction on
Spark is not capped by runtime container flags; if accepting a separately bounded
import is unsuitable, run the whole test on the isolated CPU VM instead.

## Runtime resources and exact commands

Only Spark's existing normal-user rootless daemon. Read-only preflight checks
rootless security options, cgroupv2/systemd, controller delegation/effective files,
reserved name absence, unused loopback18081, >=4GiB free and the same filesystem as
DockerRootDir. Captures only live engine IDs/running state/networks/port bindings
for before/after equality; no HTTP requests, environment values or logs from them.

At most two test containers concurrently: API512MiB+fixture256MiB, each1 CPU/64tasks,
no swap beyond its memory ceiling, UID/GID65532, read-only rootfs, all caps dropped,
no-new-privileges, default seccomp, no mounts/volumes, core0,nofile256, restart=no,
logs disabled, init. Numeric libraries use one thread. Only published port is
`127.0.0.1:18081 -> 8081`. Both images independently expire after180s under GNU
timeout with TERM/KILL5s; total runtime controller540s +30s cleanup, outer600s.
Two calculation clients maximum; eight idle clients for admission only;
<=12 API requests/phase including up to8 startup health probes; each synthetic
fixture admits <=64 provider jobs and4 handlers. No live engine receives traffic.

The second internal bridge is solely an isolation canary. The same healthy fixture
starts there, unreachable from the API's first bridge. After a fixed socket check
of its disposable IP:8002, it joins the test bridge as valhalla, leaves the canary
bridge, and that empty bridge is removed. No third container is needed. A single
bridge would test only same-network behavior and could not supply this negative
control. Neither bridge attaches either live Valhalla or personal host services.

The controller uses these exact resource commands (for review, not execution).
`API_IMAGE` and `FIXTURE_IMAGE` must be the separately reviewed SHA256 IDs;
placeholders are not executable approvals:

```sh
D=(docker --host "unix:///run/user/$(id -u)/docker.sock")
"${D[@]}" network create --internal --label fairway.safety.run=review fairway-safety-review
"${D[@]}" network create --internal --label fairway.safety.run=review fairway-safety-canary-review
"${D[@]}" run --detach --name fairway-safety-router-review \
  --label fairway.safety.run=review --network fairway-safety-canary-review \
  --network-alias valhalla --env FIXTURE_MODE=hold-first \
  --restart=no --init --user 65532:65532 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 256m --memory-swap 256m \
  --cpus 1 --pids-limit 64 --ulimit core=0 --ulimit nofile=256:256 \
  --log-driver none "$FIXTURE_IMAGE"
"${D[@]}" run --detach --name fairway-safety-api-review \
  --label fairway.safety.run=review --network fairway-safety-review \
  --publish 127.0.0.1:18081:8081 \
  --restart=no --init --user 65532:65532 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 512m --memory-swap 512m \
  --cpus 1 --pids-limit 64 --ulimit core=0 --ulimit nofile=256:256 \
  --log-driver none "$API_IMAGE"
# Verify the fixture is healthy; then API exec probes ONLY its disposable IP:8002.
"${D[@]}" network connect --alias valhalla fairway-safety-review fairway-safety-router-review
"${D[@]}" network disconnect fairway-safety-canary-review fairway-safety-router-review
"${D[@]}" network rm fairway-safety-canary-review
# Other phases recreate ONLY these owned containers, on fairway-safety-review.
# Fixture modes are normal or slow-stream; API arguments remain identical.
```

Entrypoints are fixed in the digest-pinned Dockerfiles:

```sh
/usr/bin/timeout --signal=TERM --kill-after=5s 180s fairway-national-api
/usr/bin/timeout --signal=TERM --kill-after=5s 180s python /opt/fixture/fixture_router.py
```

Run the reviewed controller, only after separate approval and image availability:

```sh
sha256sum --check SHA256SUMS
python3 run_review.py  # hash verification and scope; zero Docker calls
/usr/bin/timeout --signal=TERM --kill-after=5s 600s \
  python3 run_review.py --execute \
  --api-image-id "$API_IMAGE" --fixture-image-id "$FIXTURE_IMAGE" > review-events.jsonl 2>&1
```

The controller verifies image IDs/architecture/input labels, exact mount/network
membership and port bindings, UID65532, CapEff0, NoNewPrivs1, Seccomp2 and failed
rootfs write. Reads effective memory.max/cpu.max/pids.max. Never probes production
8002/8003, port11000, host gateway or Internet. Cross-bridge denial is selected-path
evidence, not proof every host service is unreachable or a kernel exploit cannot
escape. Rootless, internal bridging and tunnel absence are not complete host security.

Finite behavioral cases: held first calculation/immediate second503/recovery;
eight held connections/ninth503; disconnected client and local child reaped at30s
while deliberate35s synthetic upstream work continues; gate recovery; active-worker
SIGTERM then abrupt container kill. These do not prove native Valhalla queue,
cancellation, capacity, ferry/access suitability or authentication.

Cleanup and independent check (fixed names only, after verifying ownership labels):

```sh
"${D[@]}" stop --time 3 fairway-safety-api-review fairway-safety-router-review
"${D[@]}" rm fairway-safety-api-review fairway-safety-router-review
"${D[@]}" network rm fairway-safety-review
# If still present from an interrupted earlier phase, remove ONLY the owned empty canary.
"${D[@]}" network rm fairway-safety-canary-review
"${D[@]}" container inspect fairway-safety-api-review fairway-safety-router-review
"${D[@]}" network inspect fairway-safety-review fairway-safety-canary-review
# Expected: test names absent. Also compare live engines' metadata to preflight.
```

The Python cleanup handles normal already-removed resources, checks ownership and
reports failures. Lost controller/SSH may leave stopped owned objects after180s;
report/reconcile exact objects, never prune or expand daemon permissions. Prebuilt
images are retained; runtime creates no builder cache. If imported images need
later removal, separately review exact newly imported IDs and remove without
force only after confirming no users. Shared layers remain referenced if used by
others. No shared Docker/system/builder/network prune. Build-host cache is removed
by disposing that independently approved host. Remove the exact staged temporary
bundle after retaining evidence; no wildcard filesystem cleanup.

No image build/import, staging, Spark network/container creation or execution has
occurred. Five local checks cover default/missing-ID no-Docker guards, altered
bundle denial, actual current-wheel synthetic calculator compatibility and fixture
route/body bounds. Existing API343 tests and installed-runtime142 checks pass.
Chicago road snapshot validation was attempted but could not run: local artifact
absent; no download/rebuild. No current live-router smoke/overload test. Sideline is
one paused/uninstalled proposal, excluded from this runtime. No public exposure,
persistent service, credentials, DNS/firewall changes, Render retirement or merge.
