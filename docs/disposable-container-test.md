# Disposable private API test proposal, not executed

One practical path uses Spark's existing normal-user rootless Docker daemon:
prepare public Python code offline in one capped container, remove it, then run
the synthetic API/fixture pair with narrow read-only code mounts. The controller
has no pull, build, commit, import, image-removal or persistent-service path.
This namespace-client revision is an uncommitted local proposal based on reviewed
commit `a0aa503e47bc5881ca10ee033a4fb6977ac448d0`. It needs independent source
review and a fresh approval before acquisition, staging or execution. Local pipe
and temporary loopback HTTP tests exercise the actual client dispatcher and host
adapter with Docker policy mocked. No Spark staging, image pull, installer,
container, network or routing traffic was executed for this revision.

## Inputs and separate approval boundaries

The required official CPython Linux ARM64 base is:
`docker.io/library/python:3.12.14-slim-bookworm@sha256:eb5be8e5b4d0a159c237946bbdd06356dda5d19c30fc4f7843e8046d3a590333`.
It must already exist on the selected rootless daemon. Preflight checks its
architecture, OS and matching repository digest; all runs use `--pull=never`.
A cold download/pull, registry extraction and staging are separate operator
review actions, outside the installer cgroup. One later approval may cover these
explicit actions and finite execution together; none is implicitly authorized. No new daemon, cloud host,
credentials, sudo or daemon configuration is needed by this proposal.

Six dependency wheels are the exact ARM64/Python3.12 or universal wheels recorded
in `uv.lock` and `runtime-requirements.arm64.txt`. These are the only permitted
external wheel downloads, from the official package file URLs below:

| Wheel download | SHA256 |
| --- | --- |
| [geographiclib-2.1-py3-none-any.whl](https://files.pythonhosted.org/packages/31/b3/802576f2ea5dcb48501bb162e4c7b7b3ca5654a42b2c968ef98a797a4c79/geographiclib-2.1-py3-none-any.whl) | `e2a873b9b9e7fc38721ad73d5f4e6c9ed140d428a339970f505c07056997d40b` |
| [gunicorn-26.2.0-py3-none-any.whl](https://files.pythonhosted.org/packages/fe/85/7522a52e5e2f42faf1a129113ab63e548c42e103e9af395b7bfe65e403e2/gunicorn-26.2.0-py3-none-any.whl) | `bd249d0b3f7972f7432f0a6b6ff3b3ee2d129f70cd1ff6c09a9dd9e29a2b88e3` |
| [networkx-3.6.1-py3-none-any.whl](https://files.pythonhosted.org/packages/9e/c9/b2622292ea83fbb4ec318f5b9ab867d0a28ab43c5717bb85b0a5f6b3b0a4/networkx-3.6.1-py3-none-any.whl) | `d47fbf302e7d9cbbb9e2555a0d267983d2aa476bac30e90dfbe5669bd57f3762` |
| [numpy-2.5.2-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl](https://files.pythonhosted.org/packages/e5/21/4947e0e9d6c9fc2e2ff15b8949049ee44f63adb9cacc729ab8793f97e712/numpy-2.5.2-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl) | `8ee9c4eeb8454b3660a8b53493563c3e121c2fc94fbd72b848ef814ed7b676a9` |
| [packaging-26.3-py3-none-any.whl](https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl) | `d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c` |
| [scipy-1.18.1-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl](https://files.pythonhosted.org/packages/75/9a/2e71719f31eaefe0e3a1706c4a1ded94e664bfd95ffca2b219a671faee01/scipy-1.18.1-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl) | `3c085faa2cfa879c5141df483f836f4d691045a078224a670fa570fa01612d89` |

The other two wheels are local `fairway-0.6.2-py3-none-any.whl` and
`modo-0.3.7-py3-none-any.whl`. Build them from the reviewed fairway revision and
modo `865beb66c039babcc96d7c1511b29bbf95405acf`, as pinned by `uv.lock`.
Application wheel hashes are build outputs, not assumed to be reproducible bytes:
record and review their exact hashes before preparation. No historical hash is an
approval for a newly built wheel. Generate the existing canonical browse projection
before building fairway; no catalog, pins or public UI are edited by this test.

`prepare_bundle.py` takes an explicit new absolute directory and verified wheel
paths/hashes. It runs locally without downloads, installs, subprocesses or Docker.
The bundle contains exactly eight wheels, the fixed controller/installer/verifier, namespace client
and fixture source, the requirement/manifest files, README and SHA256SUMS.
It rejects changed hashes, missing/extra files, symlinks and unlisted wheel entries
before creating output. Both preparation and runtime controllers reject extra
files before any Docker call. The capped installer verifies the entire bundle
again before two offline hash-locked pip installations. Applications name exactly
two local wheel files; there is no wildcard or external application URL.

Review source hashes with `sha256sum` on the files under
`ops/private-national-api/review-fixture/` and this document at the exact local
revision under review. Generated `SHA256SUMS` covers those copied inputs plus the
exact eight wheels. Record its own hash separately; no self-referential hash is
claimed. A source change requires a fresh bundle and fresh review.

## Separate acquisition and staging bounds

Prefer already present artifacts when their exact recorded hashes, provenance,
platform and reviewed source identity match. Reuse is not inferred from a filename,
version or tag. No acquisition/staging command is executed by the controller.
If any bounded phase fails or its outcome is unknown, stop and report it; no
retry, next phase or extra workload follows automatically.

| Phase | Proposed finite time limit | Byte/storage stop limits | Enforcement and limits |
| --- | --- | --- | --- |
| Six dependency-wheel downloads on Omarchy, only if absent | 240s total client/process-group limit, TERM then KILL5s; no retries | 128MiB maximum per wheel; 256MiB maximum complete input bundle; watch the new download directory every5s and stop above256MiB | Verifier enforces per-file and aggregate caps before installation/staging acceptance. In-progress pip download bytes are monitored, not quota-enforced; its inactivity timeout is not the absolute limit. |
| Two local application-wheel builds, only if needed | 120s client/process-group limit per build; no Spark build | Same128MiB per-file/256MiB aggregate input caps | Record source and exact wheel hashes; local build/cache activity lies outside Spark installer caps. |
| One exact official Python base pull, only if missing | 180s client/process-group limit, TERM then KILL5s; no retry | At least4GiB free before pull; monitor free-space every5s, stop on >2GiB added or <2GiB free; installed image reported Size must be <=1GiB before execution | Existing-image <=1GiB Size/digest/platform gate is enforced by preflight. Pull/extraction CPU, RAM, network bytes and scratch usage are daemon work, outside installer cgroups. Space thresholds are monitored stop criteria, not quotas. Killing the CLI does not prove daemon cancellation. An uncertain/continuing pull blocks progression and requires owner review. If only enforced pull resource limits are acceptable, reuse an already present verified base and do not approve a cold Spark pull. |
| One verified public-bundle transfer and extraction into a new private Spark directory | 180s outer staging-client limit; transfer <=90s, extraction <=30s, verification <=30s; TERM/KILL5s; no retry | Verify archive <=256MiB before transfer; approved extracted bundle <=256MiB and exact regular-file inventory; monitor new stage/evidence/code directories every5s, stop above1280MiB total or16MiB evidence, with >=2GiB free | Local archive-size/hash checks and bundle byte/file/hash acceptance are enforced; in-progress remote copying, filesystem free-space and combined disk thresholds are monitored. Remote completion/cancellation is not inferred from an SSH/scp timeout. Retain unknown outcome and do not run the controller until verified completion. |

An acquisition approval must enumerate the exact fixed URLs/image digest,
archive/wheel hashes and new staging/output paths. Those paths must be on the
existing rootless daemon's filesystem. The approved archive's inventory must be
reviewed before extraction; it contains only the selected public files and eight
wheels, no links or special entries. No home/key/socket/live-engine mounts or
host installs are added. Use the existing key only through SSH, with strict known
host checking and no host-key update. CPU/RAM controls for the capped installer
apply only after these separately bounded phases complete. These monitored
thresholds can overshoot between checks; they do not secure or cap the Docker
daemon, and unresolved operations are never repaired by changing its settings.

The later download recipe must be wrapped in the240s outer limit above. The base
pull, if explicitly approved, is only `docker --host unix:///run/user/<UID>/docker.sock
pull --platform linux/arm64` for the exact digest above, wrapped in180s.
Never run an unbounded cold pull or staging copy to make the runtime recipe work.
The practical path remains the same existing rootless daemon with a verified
base and offline inputs, followed by the single capped preparation/runtime stage.

## Local bundle recipe

These are operator commands for later review, not authorization to download or
stage anything on Spark. Reuse the existing locked local development/build cache;
offline sync/build fails rather than fetching extra tools or backends. Use the locked versions/revisions after any reviewed
update, not substitute wheels or an unlocked dependency resolution.

```sh
# From the reviewed fairway checkout:
python scripts/publish_research_map.py
uv sync --extra test --locked --offline
/usr/bin/timeout --signal=TERM --kill-after=5s 120s \
  uv build --offline --out-dir /ABSOLUTE/fairway-artifacts
# In a separate checkout of the exact modo commit above:
/usr/bin/timeout --signal=TERM --kill-after=5s 120s \
  uv build --offline --out-dir /ABSOLUTE/modo-artifacts
# A separate approved download on Omarchy, only the six hash-pinned wheels:
/usr/bin/timeout --signal=TERM --kill-after=5s 240s \
  python -m pip download --index-url https://pypi.org/simple \
  --no-deps --require-hashes --only-binary=:all: \
  --platform manylinux_2_28_aarch64 --python-version 3.12 \
  --implementation cp --abi cp312 \
  -r ops/private-national-api/review-fixture/runtime-requirements.arm64.txt \
  --dest /ABSOLUTE/dependency-wheels
sha256sum /ABSOLUTE/fairway-artifacts/fairway-0.6.2-py3-none-any.whl \
  /ABSOLUTE/modo-artifacts/modo-0.3.7-py3-none-any.whl
python ops/private-national-api/review-fixture/prepare_bundle.py \
  --output /ABSOLUTE/new-review-bundle \
  --dependency-wheels /ABSOLUTE/dependency-wheels \
  --fairway-wheel /ABSOLUTE/fairway-artifacts/fairway-0.6.2-py3-none-any.whl \
  --fairway-sha256 REVIEWED_FAIRWAY_SHA256 \
  --modo-wheel /ABSOLUTE/modo-artifacts/modo-0.3.7-py3-none-any.whl \
  --modo-sha256 REVIEWED_MODO_SHA256
cd /ABSOLUTE/new-review-bundle
REVIEW_OUTPUT=$(mktemp -d ../fairway-review-output.XXXXXX)
REVIEW_OUTPUT=$(cd "$REVIEW_OUTPUT" && pwd -P)
export REVIEW_OUTPUT
sha256sum --check SHA256SUMS
sha256sum SHA256SUMS > "$REVIEW_OUTPUT/input-manifest.sha256"
python3 run_review.py > "$REVIEW_OUTPUT/preflight-events.jsonl" 2>&1
```

The last command verifies inputs and reports `docker_calls=0`; it is not an
executed Docker preflight. Keep the bundle immutable. All shell redirections,
logs, receipts and output directories stay outside it: redirection creates a
file before verification, and even an operator log inside the bundle is rejected.
The separate output parent must already exist on the DockerRootDir filesystem;
`--work-directory` must be a new absolute path without symlink components,
commas or line breaks, outside the bundle.

## Exact preparation and runtime effects

The fixed controller connects only to
`unix:///run/user/<ordinary UID>/docker.sock` and strips DOCKER_* overrides.
Read-only execution preflight verifies rootless/systemd/cgroupv2, all reserved
names absent, matching pinned base, <=1GiB reported base-image size, >=4GiB free and the same
filesystem for inputs, output and DockerRootDir. Before/after live-engine metadata
contains only IDs, running state, networks and port bindings. No environment,
logs, files or HTTP requests are read from those engines.

Preparation creates only `fairway-safety-prepare-review`: network=none, no ports,
1 CPU,1GiB memory with no extra swap,64 tasks,read-only rootfs,cap-drop ALL,
no-new-privileges,default seccomp,init,restart=no,logs disabled,core0,nofile256.
UID0 inside the rootless namespace maps to the ordinary host account; it is not
host root. Its one read-only bind is the verified public input bundle -> `/inputs`.
The only writable mount is `/out`, a512MiB tmpfs, with no persistent volume.
Fixed entrypoint is GNU timeout TERM/KILL5s after180s running
`python /inputs/prepare_runtime.py`. The installer waits at an explicit barrier
until the controller verifies actual cgroups, UID, CapEff0, NoNewPrivs1, Seccomp2,
failed `/tmp` rootfs write, network, mounts, ports and policy. It then installs the
six dependencies and two applications to `/out/site`, with no-index/no-deps,
only-binary,require-hashes,no-cache-dir,no-compile and isolated pip configuration.

The reviewed baseline gives the entire preparation stage one absolute
180s controller deadline recorded before creation, also capped by the outer
work deadline. Isolation/barrier checks and the at-most120s readiness wait end
at least35s before that deadline. After a fresh owned-state check, copying is
refused unless a full30s copy window plus5s reserve remains. Copying has its own
alarm ending5s before the stage deadline and rejects a late successful return.
The existing180s container timer is unchanged; installer post-ready sleep does
not extend it. Mocked tests cover late readiness, early exit, late copy return
and a shorter enclosing deadline; actual live-tmpfs archive behavior is unproved.

It copies only `/out/site` via Docker cp into its new mode0700 work directory,
rejects links/special files,
empty output or >20,000 files/>512MiB, hashes the tree and makes code readable
by runtime UID65532. Docker cp and host disk operations are outside the installer
cgroup; the tmpfs/copy bounds limit payload size, not all daemon CPU or memory.
It copies the public fixture source separately, removes the preparation container
and checks absence before any runtime bridge or container is created. Its receipt
records input-manifest, installed-tree and fixture SHA256, also emitted to the
external JSON log. Changed code blocks runtime before creation. The2GiB added-space
stop threshold is a measured free-space delta, not a filesystem quota.

Runtime creates at most two containers concurrently, each using the same pinned
base and180s timeout, UID/GID65532,read-only rootfs,all caps dropped,
no-new-privileges,default seccomp,init,restart=no,logs disabled,core0,nofile256,
1 CPU,64tasks and memory-swap equal to memory. Numeric libraries use one thread.

| Container | Memory | Only bind, always read-only | Command/environment |
| --- | --- | --- | --- |
| fairway-safety-api-review | 512MiB | work/site -> /opt/prepared | python -m fairway.national_server; PYTHONPATH=/opt/prepared; bind0.0.0.0; router http://valhalla:8002; dataset synthetic-fixture-only |
| fairway-safety-router-review | 256MiB | work/fixture_router.py -> /opt/fixture_router.py | python /opt/fixture_router.py; FIXTURE_MODE normal,hold-first,slow-stream |

No host ports are published. The controller verifies both requested
`HostConfig.PortBindings`/`PublishAllPorts` and realized `NetworkSettings.Ports`
as absent, before/after start and before connecting client commands. Missing
inspection fields are rejected; an exposed container port with no host mapping
is allowed. There is no host-network mode, external bridge or host proxy.
No SSH keys, home directories,
Docker socket, road tiles or live-engine data are mounted. No tmpfs is provided
to runtime. Creation returns full container and bridge IDs, checked with the exact owner
token. Every attachment, exec, stop and removal uses those recorded IDs.
Before Docker start, the bridge's pinned ID, name, internal/bridge policy,
owner token and exact permitted members must agree. Container NetworkMode must
already be that full bridge ID; populated endpoint NetworkIDs must agree.
Docker can leave a created container's endpoint NetworkID empty until start:
that pending case is accepted only with the full configured NetworkMode ID,
then actual endpoint NetworkID and exact bridge membership must match immediately
after start, before any HTTP probe. This reflects Docker's
[network-selection and startup handling](https://raw.githubusercontent.com/moby/moby/v28.5.1/daemon/container_operations.go),
not a claim of runtime verification on Spark. A replacement bridge, wrong owner,
foreign member or mismatching endpoint fails closed. It verifies exact binds,
ports and cgroup/UID/capability/rootfs state before behavioral checks.

Two internal bridges are `fairway-safety-review` and
`fairway-safety-canary-review`. The fixture initially starts on the canary;
API exec checks only that disposable fixture IP:8002 is unreachable. Then the
fixture joins the test bridge as valhalla, leaves the canary and the empty canary
is removed. No third container or live-router attachment is needed. This selected
cross-bridge check is not proof all host services are unreachable. Rootless,
internal bridges and tunnel absence do not fully secure the machine.

## Finite execution, only after approval

No execution is authorized by this document. After exact bundle/base/staging and
these effects receive approval, one reviewed command starts preparation and all
synthetic phases sequentially:

```sh
cd /ABSOLUTE/new-review-bundle
REVIEW_OUTPUT=$(mktemp -d ../fairway-review-output.XXXXXX)
REVIEW_OUTPUT=$(cd "$REVIEW_OUTPUT" && pwd -P)
export REVIEW_OUTPUT
sha256sum --check SHA256SUMS
/usr/bin/timeout --signal=TERM --kill-after=5s 600s \
  python3 run_review.py --execute \
  --work-directory "$REVIEW_OUTPUT/prepared-code" > "$REVIEW_OUTPUT/review-events.jsonl" 2>&1
```

An independent Linux SIGALRM watchdog stops controller work at its absolute540s
clock deadline and arms a separate30s cleanup reserve, within outer600s. Every
HTTP request uses the earlier of that deadline and its own timeout, including
headers and chunk framing, plus <=64KiB read1 chunks, deadline checks after each
read and JSON processing, and a1MiB body cap. Check parser completion before
touching the saved socket: read1 closes its file at the last fixed-length byte.
Remaining Content-Length bytes, incomplete chunks, invalid chunk CRLFs and missing
trailer terminators fail closed, even when the partial body is valid JSON. Chunk
trailers are capped at32 lines/8192 bytes per line. Explicitly close the response
on success/error/deadline paths and close the connection even if response close
itself fails. Timer-generated EOF does not override the absolute deadline. Continuous trickling cannot refresh the total allowance.
HTTP originates from a fixed Python client launched by one interactive Docker
exec in an already owned runtime container, as UID65532. It has no Docker
socket, key, new mount or arbitrary target/path/body command. Startup health
uses API namespace IPv4 loopback8081. After clean startup-client finish, one phase
observer runs in the existing synthetic fixture container and uses only the
inspected API IPv4 endpoint:8081 on the same owned internal bridge. Its container
ID, start time, exact bridge ID/membership, API full ID/start time and endpoint
are pinned and rechecked before connecting commands. This observer survives API
stop/kill; response/finish commands allow the stopped API to leave bridge
membership, but require the still-owned observer and no foreign member.

Both client and server probes independently report UID, capability/seccomp state
and the same actual cgroup limits. Client overhead shares the existing API
1CPU/512MiB/64-task or fixture1CPU/256MiB/64-task cap; it adds no separate
container budget and supports no capacity claim. Fixed source is passed through
exec stdin-independent argv, covered by the input manifest; no shell runs.

The closed protocol permits health, ranking, begin, collect, close, idle-open,
idle-close and finish. It permits no URLs, provider arguments or arbitrary code.
Each command/event has an exact schema, nonce and monotonically increasing
sequence. Input/output each cap at64KiB with4KiB frames including their newline. The
producer checks encoded UTF-8 frame and aggregate sizes before any write;
Retry-After is absent or one to four ASCII digits on both direct and collected
response paths. Every output write is nonblocking and bounded by the earliest
pending-request/session deadline, including readiness, replies and finish.
The dispatcher snapshots its command deadline before handling. Reply and error
writes use the earlier of that snapshot and the current deadline, so collecting
or closing the last pending socket cannot restore a later session allowance.
Direct health/ranking commands snapshot an additional1s/35s operation deadline
before handling; those totals include both HTTP work and protocol result delivery.
The handler watchdog and output writer retain that same command budget.
Failure closes held sockets before error reporting and retains that original
deadline; output rejection/uncertain partial write is terminal and forbids further
records. A partial frame, overflow,
wrong identity, unsolicited extra event or premature EOF is terminal. The host
allows at most63 commands and64 events including readiness per session. One
session is at most90s (GNU timeout TERM/KILL1s is an additional bound); request
headers/body/framing remain capped by the earlier absolute session/work deadline
and35s. Both direct and begun requests cap connection/send at2s (health retains
its earlier1s total); response reading restores only the remaining total budget. At most two calculation sockets
are outstanding; eight partial-header connections are opened only once in the
entire run and closed before finish. Pending/idle sockets retain their original
35s deadlines while the dispatcher waits for the next command.

The controller allocates attempt IDs before sending, never refunds a failed
attempt, and enforces <=12 API attempts per phase including <=8 startup health
probes, four phases and <=48 attempts across all sessions and fixture replacement.
The client independently permits <=12 attempts per session with increasing IDs
<=48. Startup requires an actual IPv4 HTTP200, rather than a TCP listener fact.
Cases are held first calculation/immediate second503/recovery; eight held
admission sockets/ninth503; selected client disconnect while intentional35s
synthetic upstream work continues, bounded API child reaping and gate recovery;
active-worker SIGTERM and abrupt API container kill with an independent observer.

Clean client finish requires acknowledgement, zero held sockets, CLI exit0,
clean output EOF and an independent /proc PID/start-time/nonce check showing
that exact client is absent. Uncertain launch/response/finish is a sticky
inconclusive failure: no replacement client, next phase or resource creation
follows. Cleanup may terminate/reap the local Docker CLI with two <=0.5s waits,
but this does not prove remote exec termination. The separately verified absence
of each owned whole-container full ID is the final remote cleanup boundary;
uncertain exec still fails the stage and retains evidence even after resources
are removed. There are no automatic retries after unknown outcomes.
Each runtime container retains its180s lifetime. Existing preparation180s,
work540s, cleanup30s and outer600s limits are unchanged.

Each recreated fixture permits <=64 provider
jobs/4 handlers, bounded bodies and origins/targets. No production8002/8003,
port11000, host gateway or Internet is probed.

These fixtures establish local process/HTTP behavior only. Native Valhalla queue,
HTTP-disconnect cancellation, reclaim latency, capacity and routing/access quality
remain unproved. The separate modo native proposal has its own controller, assets,
resource and request bounds and approval. Run stages strictly sequentially after
successful cleanup evidence. Fairway execution preflight and each creation gate
refuse running `modo.native.review` labelled containers or either fixed native
container name. The native controller reciprocally checks fairway's label and
three fixed container names. These checks are not an atomic cross-process lock;
the operator must not launch both stages concurrently.

## Cleanup, evidence and remaining limits

Every object carries `fairway.safety.run=review` and a unique invocation owner
token, recorded in the external `execution-started` JSON event. Each creation
intent is recorded before its command; acknowledged full IDs are recorded after
ownership verification. Cleanup checks both before removal, stops only tracked owned containers
with3s grace, removes only tracked containers/bridges and checks absence.
A timed-out create retains an uncertain intent: cleanup makes up to six bounded
lookups within its30s deadline to discover and remove a delayed owned object.
Repeated absence never proves the daemon abandoned creation. An unresolved
outcome fails cleanup, preserves the output directory and is reported with
kind/name/known ID in JSON. It blocks advancing to the native stage; later
operator reconciliation is required, without automated retries or workload growth.
Ownership mismatch, a failed cleanup or changed live metadata fails the stage;
there is no repair, force removal or prune. Only after successful cleanup and
live metadata equality is the exact invocation-created public-code directory
removed. Input bundle, pinned base image and external JSON evidence remain.
Failure retains the code directory for review. Receipt hashes survive in the
JSON log after successful code cleanup.

Lost controller/SSH can leave stopped owned objects after180s. Reconcile only
exact names with their recorded owner token, then verify absence and live-state
equality before the next stage. Preserve external evidence and retain/remove
only exact separately staged directories after review. No wildcard filesystem,
Docker/system/builder/network prune or image removal is part of this controller.

Local tests use fake wheel bytes and a mocked Docker model, including installer
barrier, exact policy/mount denial, preparation failure, content changes,
sequential ordering, native-stage conflict, delayed/unknown creates, bridge
replacement/foreign membership, pre-start endpoint ID denial, owner-token
cleanup refusal, expired clocks, slow body/header streams, nested alarms and preservation of the independent
cleanup reserve. Local integration uses the actual client dispatcher and host
adapter in Python pipes with temporary loopback HTTP, preserving fixed peer
arguments and explicitly mocking OCI facts. It covers startup, held calculation,
503/Retry-After, eight-slot admission, selected socket closure, actual API SIGTERM
and SIGKILL, protocol corruption, input byte budgets and independent PID checks.
Collect Retry-After overflow, encoded frame/aggregate output bounds, direct
connect/send overruns and actual full-pipe backpressure also have regressions.
Blocked readiness/reply/error output cannot retain sockets past their deadline;
error-reporting tests require closed sockets before the attempted error write.
Near-expiry collect and uncaught handler errors exercise normal and blocked
output after handler cleanup; all retain the original command deadline. Direct
health/ranking near-expiry result delivery, including full-pipe backpressure,
also retains its1s/35s operation deadline rather than the later session end.
Realized/requested mappings, missing fields, API/observer incarnation changes,
uncertain launches and missing finish/EOF/exit evidence stop progression. Framing and
lifecycle cases use actual stdlib HTTPConnection/HTTPResponse parsers over
BytesIO-backed transports that raise EBADF after file release, with no network.
They cover fixed-length/close/HTTP1.0, valid JSON with overstated length, empty/
invalid JSON, complete/malformed/truncated chunks and trailers, byte caps,
slow/error reads, timer-generated EOF and expiry during JSON processing.
No mocked success attests a real container's behavior. Chicago road validation
could not run because its local artifact is absent; no download/rebuild occurred.
Sideline remains one paused/uninstalled proposal, excluded from this runtime.
No public exposure, credentials, persistent service, DNS/firewall changes,
Render retirement, PR merge or live routing load occurs in this work.

## Reviewed baseline diagnostics

The reviewed baseline retains one bounded failed-command record: allowlisted
operation, fixed review names/confirmed full IDs, return code or exception type,
configured timeout, checked/cleanup context and redacted stderr preview only.
It scans at most8KiB and retains at most4KiB UTF-8. After credential/URL redaction,
every remaining line containing POSIX/Windows path syntax is suppressed entirely,
including paths with spaces or outside home/tmp roots. Credential assignments,
Bearer tokens/private-key blocks and control characters are removed defensively.
This is not a guarantee for arbitrary secret text. Full argv, environment, stdout
and raw exception messages are never persisted in these records.

Diagnostic generation/write occurs after leaving the original subprocess
exception handler. Failures during redaction or emission are converted to safe
messages with suppressed exception context. A failed diagnostic cannot restore
raw TimeoutExpired argv or an OSError filename through traceback chaining.
Deadline/interruption categories remain active; output failure fails closed and
keeps original deadline/interruption semantics. Tests format full exception
chains for generation/write failures, including broken pipe, ENOSPC and alarms.
Timeout partial stderr is recorded while the existing uncertain-create and exact
owner/ID cleanup guards remain in force. Checked and unchecked failures remain
distinguishable, and late owned creations are still reconciled during cleanup.

The existing subprocess.run/communicate path drains stdout and stderr together,
including Docker cp; no separate unconsumed stderr pipe is introduced. Preview
bounds limit persisted diagnostics, not total CLI capture or Docker daemon use.
These diagnostics are committed locally at `a0aa503`, separately from the
published PR15 head `86f54e5`. The namespace-client diff above remains uncommitted
and unreviewed. Earlier bundles retain their original identities and are paused;
a fresh18-file bundle (17 payload files plus SHA256SUMS) is needed after review. Runtime still uses log-driver
none without local-driver options, so native's max-file/compression conflict does
not apply; no daemon setting, log-driver switch or failed-stage retry is proposed.
