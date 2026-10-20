# Local immutable planning interface

This is source and an offline fixture contract, not an installed HTTP service.
`PlanningInterface` has no WSGI route, listening socket or browser adapter.
Authorization defaults to denial and `ContinuationExecutor` defaults to disabled.
The existing national HTTP endpoint and its Origin rejection are unchanged.
The corrected frontend consumer is the separate `7bb203ef...` review artifact;
its fake-only guard must remain. This slice does not authorize real binding.

## Dependency and authority

The six-file manifest `catalog-dependency-pin.json` pins catalog reader
`4f3db754079c274ca677027c3b0879af9eebb837`, including schemas 001 through 004 and
`catalog_sources.py`. The independently cleared reader is separate from research
revision 21/38 facts. No research database or source clearance is copied here.
Course and facility queries call that native reader and preserve its DTOs,
nullable facts, source qualifications, round scopes and empty inventories.
There is no second JSON authority or static fallback.

The catalog is operator-selected, never a caller path. It must be an immutable,
read-only, checkpointed release in a deployed process. A release key is a startup
SHA-256 of catalog bytes, not a credential. Startup reads at most 128 MiB plus one probe byte with a
1 MiB buffer and verifies the file did not change during fingerprinting. Active
WAL sidecars are not release assets; promotion must checkpoint and close writers.
An atomic file replacement
is refused even when the revision is unchanged. Native read transactions bind
rows, totals and revision; checks before/after reads bind the file release.
Trusted in-place edits that fail to advance revision are outside this contract.
Release promotion must restart/rebind readers deliberately.

## Reserved paths and exact fields

These paths are proposed mappings to local methods. None is registered:

| Method/path | Local source boundary | Fields |
| --- | --- | --- |
| GET `/api/v1/catalog/courses` | `catalog_page("courses")` | native allowlisted filters; `limit`, `offset`, `expected_revision`, `expected_release_key` |
| GET `/api/v1/catalog/facilities` | `catalog_page("facilities")` | native allowlisted filters; same page/release binding |
| POST `/api/v1/preparations` | `create(raw)` | strict JSON body below; trusted caller context outside the body |
| GET `/api/v1/preparations/{session_id}/events` | `events(...)` | **`generation`, `request_key`, `after`, `limit`** |
| GET `/api/v1/preparations/{session_id}/snapshot` | `snapshot(...)` | **`expected_snapshot_sequence`, `expected_generation`, `expected_request_key`, `expected_catalog_revision`, `expected_catalog_release_key`, `limit`, `offset`** |

The future snapshot HTTP adapter maps `expected_generation` to the local
`generation` argument, likewise request key, catalog revision and release key.
It must reject duplicate/unknown parameters and parse bounded types explicitly.
There is no DELETE/cancel, worker-dispatch, journal-initialize or retry endpoint.
`dispatch` and `retry_predispatch` are trusted host orchestration methods only.
No read starts provider work; a separately reviewed host scheduler is required.

Body, at most 4096 UTF-8 bytes, with exactly these fields:

```json
{"generation":1,"origins":[{"id":"o0","coordinate":[41.0,-88.0]}],"objective":"maximum","radius_km":32.18688,"access_policy":"nonmember","round_holes":null}
```

Use the exact origin object shape in the typed fixture request (the parser uses
`id` and `coordinate`). Coordinates are finite points in the lower 48; 1 through
8 origins, unique bounded IDs, generation 1 through 2147483647, objective
`maximum` or `combined`, radius greater than zero and at most 160 km, supported
access policy, round holes null/9/18. Origins `[]` is the explicit clear input
with the same five other fields. No geocoding, provider URL or shell input exists.

A trusted authorization callback maps transport context to a private caller
identity. No credential format, token, cookie, CORS exception or public login is
chosen here. With no callback every operation fails closed. The sole logical
slot belongs to one caller; session IDs are non-secret locators, not access
tokens. Foreign reads return unavailable. A second caller cannot obtain a new
slot while that owner exists.

The same authorized caller POSTs updates and clear to the same path. The server
always reuses its existing `session_id` and ledger; there is no caller-selected
ID, replacement session or reset flag. Exactly repeated input is acknowledged
without work. Changed input requires a strictly newer generation. The response
always identifies the existing session, current generation, exact request key,
catalog revision/release, snapshot sequence and cursor. A future multi-session
service would need a separately reviewed allocation/quota design.

`operation_started: true` means **logical preparation admission**, not provider
dispatch. `upstream_started` is false before any completed dispatch, true after
known accounted work, or null while active/uncertain. `engine_unknown` is true
for blocked unknown work and otherwise null: absence of current global journal
proof must not become false or a retry grant. `operation_active` describes a held
chunk. These fields must not be substituted for each other.

## Immutable pages and progress

Every published complete view gets a strictly increasing `snapshot_sequence`.
Rows, areas, request, revision, release key and counts are immutable for that
sequence even when another origin's cells change without changing counts.
All pages bind generation, request key, revision, release key and sequence.
Retained older pages for the **same current input** can finish consistently;
superseded input is refused by the interface. Four snapshots and 16 MiB total
are retained, each full view at most 8 MiB. Course pool at most 4096. Pages have
1 through 1000 rows and at most 4 MiB; a page limit means use a smaller GET,
never create new work. Catalog responses also have a 4 MiB bound.

Catalog pagination requires both expected revision and release key after page
zero. Bind that same pair across **both** course and facility resources and
preparation views. A new reader with another release key cannot legitimize old
pages merely because its numeric revision matches.

Events are bounded snapshot headers: type `planning.snapshot`, cursor, sequence,
generation, exact request key, catalog revision and release key. The source
retains 256 headers and returns at most 64 per read, with `poll_after_ms: 250` as
a future client hint, not a long-poll implementation. Only current-generation
headers are returned. Reads require generation and request key, so delayed
polls cannot silently report new private/public-filter input. A cursor beyond
the session is invalid; an evicted cursor requires restarting reads.

The flat proposed error packet has `status`, `code`, sanitized `message`,
`retryable: false`, nullable `operation_started` and `engine_unknown`, `latest`
and `recovery`. Only an authenticated owner receives `latest`. Read conflicts
(`snapshot_changed`, expired snapshot mapped to that code, `generation_conflict`,
`cursor_expired`) return `recovery: "restart-current-reads"` and the current
session/generation/request/revision/release/sequence/cursor pointer. Restart
whole GET page reads only after validating that pointer against current UI
input; never infer compatibility from counts or automatically POST again.
Catalog release conflicts require discarding both browse resources and rebinding
a trusted release. Fatal/unknown errors revoke provisional display, retain held
ownership and give no automatic retry permission.

The wrapper deliberately grants **no** browser retry or Retry-After permission.
A proven local busy rejection can be retried explicitly by the trusted host
within the same ledger/deadline. A future browser predispatch retry requires
independent global-journal proof, `operation_started: false`, explicit
`engine_unknown: false` and a bounded Retry-After, and must still target the
same logical ownership. Those proof/transport semantics are not implemented.

## Work, logical terminal and continuation

One active chunk, one latest coalesced input and one ledger span all stages,
chunks, edits, clear and explicit trusted predispatch retry. Limits are 32 total
provider requests, 4096 cells, 256 distinct historical target coordinates,
8 origins, at most 8 course targets per work chunk, 40 estimator targets per
native matrix call, and one **30-second absolute deadline from session creation**.
MODO area work shares all limits. Historic dispatched targets remain charged
when their regions become obsolete. Counters and deadline never reset on a
continuation request or another generation. `remaining_milliseconds_at_snapshot`
is only the captured upper bound, not a lease or a new timeout; worker admission
always checks the original monotonic deadline.

The full current-origin plus latest-area course pool remains visible. Work
window 24 is not a display limit. Matrix aliases share a physical point without
merging course/arrival provenance. Only complete-current-origin vectors score.
Null/unreachable and pending remain distinct; known zero is valid. Limit
exhaustion is nonfatal `preparation_limited: true`, retaining completed provisional
vectors and all pending rows. Fatal errors mask old times and scores.
Areas are qualified Points, not invented circles or inferred extents.

A clean chunk receipt in a snapshot is not a logical terminal. Event response
`terminal` remains null while held work, more current tasks or area work remain.
At an actual stop it is:

```json
{"scope":"logical-plan","status":"complete","generation":1,"request_key":"...","snapshot_sequence":30,"catalog_revision":0,"catalog_release_key":"...","logical_operation_complete":true,"native_admission_released":false,"last_work_receipt":null}
```

Status is `complete`, `limited` or `cleared`. `last_work_receipt` is null when
no native work completed; otherwise it retains the work ID, its original
generation, `fairway_reservation_cleared` and trusted Calculator evidence basis.
That receipt can be from superseded work. It is not a new release claim for
the current UI, nor proof of engine cancellation/reclamation. Clear while held
revokes display and waits for actual trusted completion. Logical terminal lets
the browser stop polling that input; it does **not** free/reset the server slot,
budget or deadline. Later input from the same caller reuses them.

Calculator still requires ordered dispatch/completion acknowledgements, final
worker message, clean exit/EOF and durable journal clear. Unknown execution
holds the work and persistent engine reservation across worker/server restarts.
The new plan ledger itself is in memory: after restart old sessions are
unavailable, and consumers must not auto-create replacement plans. Multi-process
logical ownership, durable plan ledger/recovery and caller quotas remain blocked
deployment dependencies. No TTL/native reset is offered.

## Offline evidence and remaining gates

`scripts/build_plan_protocol_fixture.py` uses temporary synthetic SQLite and
the actual controller/Calculator/mode SDK over in-memory stdlib HTTP framing.
`tests/fixtures/plan-continuation/protocol.json` includes admitted/upstream-false,
held, clear/edit-held, stale-generation recovery, clean-chunk-without-terminal,
explicit trusted busy retry, 100-row partial/full, deadline-limited provisional,
Point-area and same-revision/different-release cases. Locators are normalized
offline aliases; snapshot clock metadata uses a disclosed test hook. There are
no sockets, geocoder calls or real native results. The fake-only frontend must
not remove its guard or accept the raw source receipt as production proof.

This 30-second session is a conservative finite-validation prototype, not a
production interaction lifetime. A longer interactive session would require
an explicit bounded deadline/aggregate-work policy and persistence review;
choosing that policy is parked. Remaining gates are independent source review,
real private caller authorization, host scheduling/session recovery, immutable
release promotion/rollback and read-only mount validation, exact shared-engine
connectivity and resource isolation, then separately approved private finite
validation. Any public connection needs its own authentication/abuse/ingress
review; a tunnel alone does not secure Spark. Do not run old deployment snippets
as though they expose this new interface.

Minimal portable proposal remains one nonroot API process with read-only root
and catalog release, narrow persistent RW engine journal, bounded tmpfs, fixed
CPU/memory/PID limits, no socket/key/home/admin mounts and an operator-owned
shared Valhalla endpoint. modo stays a pinned Python library, not a duplicate
HTTP service. Existing US/Illinois engines remain untouched. No Spark command,
image, network, service, credential, firewall/DNS, Render retirement or public
cutover is part of this source slice. Sideline freshness remains exactly one
separate planned/uninstalled/paused job, outside Fairway service configuration.
