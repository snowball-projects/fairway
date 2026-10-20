# Offline planning transport proposal

Status: reserved frontend/backend contract only. NO endpoint or session service
is implemented, installed or exposed by this document. The current national
server rejects every Origin header and is unchanged. Source adapters must keep
fixtureOnly/offline guards until a separate transport/authentication review clears
a real binding. No CORS relaxation, public ingress or new credentials are implied.

## Required dependencies and authorization

The finite library bridge is fairway-provider-bridge at
 d96714a8278a368016ba2bcf7e1d570c5588ba64, based on admission2dcf537 and frozen
e8d66be. Its catalog source is independently reviewed b047da5 with both modules
and migrations001..003. It cannot read schema4 catalogs. The next native catalog
reader must pin a named owner source commit such as af27fe88298f83ce0f78eed2a3139777bec9764d
with catalog_store.py, catalog_sources.py and SQL001..004 together; the owner
supplies query_courses/query_facilities and source/round qualification. This is a
separate dependency refresh, not an API-owned migration or moving-copy strategy.

Before any real browser binding, trusted private ingress must authenticate a
caller and supply an authorization decision. Same-origin is a browser boundary,
not authentication. An opaque session ID is only a locator, never authorization;
all reads must bind to the same trusted caller as creation. Offline tests inject
literal authorization success/failure. No API caller may configure provider URLs,
paths, SQL, engine identity or journal directory. Anonymous/public access is not
an acceptable default; no accounts or identifying telemetry are required here.
The exact private ingress/caller mechanism remains an explicit review blocker.
Do not claim a tunnel alone protects the machine.

## Reserved paths and fields

These names agree with the frontend proposal. All schemas require strict bounded
query/body parsing, no duplicate/unknown fields and structured sanitized errors.
No response or error includes filesystem paths, provider URLs or credentials.

| Method/path | Proposed contract |
| --- | --- |
| GET /api/v1/catalog/courses | DB-owned paged course DTO, filters, revision, total, has_more and deduplicated qualified destinations; access=all broad browse and nonmember preliminary planner policy remain explicit. |
| GET /api/v1/catalog/facilities | DB-owned paged map/facility context including empty inventories; no fabricated courses, round layouts or entrance certification. |
| POST /api/v1/preparations | Exactly generation, origins[{id,coordinate}], objective, radius_km, access_policy, round_holes, using PreparationRequest validation and4096-byte limit. |
| GET /api/v1/preparations/{session_id}/events | after=cursor; bounded event list plus authoritative state and terminal evidence. |
| GET /api/v1/preparations/{session_id}/snapshot | expected_snapshot_sequence, limit, offset and expected catalog_revision/generation/request_key; immutable e8-shaped course page. |

Catalog pages use limit1..1000 and nonnegative offset, preserving owner totals and
has_more. expected_revision is required after page1; mismatch is409
catalog_revision_changed with no provider work. Filter parsing must use the
owner's documented native fields, with no second catalog authority or static
fallback. JSON course/facility fixture files are transport examples only.

A proposed successful preparation creation response includes session_id,
request_key, generation, catalog_revision, cursor and operation_started. The
server captures the exact request and operator provider policy for all event and
snapshot reads. UI-local generations cannot mutate an accepted request. Duplicate
creation must not be used as a retry/continuation mechanism.

Events bind session/generation/request_key/catalog_revision and strictly monotonic
cursor. The bridge side-channel can drop frames, so progress is informational and
snapshots/final state are authoritative. Proposed retention is at most256 events
per logical preparation; stale cursors return409 cursor_expired and point to the
current immutable snapshot. Long polling is capped15s with one poll per session;
o missed frame implies new routing work. These are proposed transport bounds,
not an implemented retention service.

Snapshots require a server-held immutable sequence token. All page reads bind
generation, request_key, catalog_revision AND snapshot_sequence, not row counts.
Mismatch returns409 snapshot_changed; discard mixed pages and restart reads only.
Course rows retain DB facts, canonical arrival, separate qualified routing_target,
per-origin pending/unreachable/complete states and nullable scores. Fully missing
or partially prepared vectors have no group score; zero is not missing. Separate
course IDs may share routing target aliases and facility map identities. An
area's Point geometry has approximate search qualification and original objective;
the course-selection radius never supplies an area extent.

Only a trusted terminal derived from unchanged Calculator evidence may state
fairway_reservation_cleared=true. native_admission_released remains false because
native admission/cancellation/reclamation was not proven. Observer loss, browser
abort, edits, generation changes, cursor expiry and snapshot errors cannot clear
admission or acknowledge provider completion. No DELETE/cancel-provider route is
reserved.

## Work bounds, errors and unresolved continuation

Current bridge is ONE finite operation:32 total upstream HTTP dispatches,4096
matrix cells,256 distinct coordinates including MODO search targets, one absolute
30s deadline, course batches at most8 targets, one shared durable engine reservation.
All origin-neighborhood/area/course phases inherit the same counters. At most4096
course rows are materialized; larger selections fail visibly while catalog paging
still works.24 is never a display/pool cap. Budget-limited outcomes remain visible,
pending/unscored, preparation_limited=true and ranking_complete=false.

A future session store needs explicit memory/session retention limits and ownership
cleanup rules; an expired view must NEVER clear an unresolved durable reservation.
One active computation and one coalesced latest UI generation are proposed, but
must be wired to trusted terminal evidence before replacement. The bridge contains
no cross-request routing cache, server queue or continuation controller.

Busy/rate errors may report retryable=true and Retry-After:10 only when the server
can PROVE no operation started for that rejected request. It must retain ownership
of any earlier operation. UI retries remain explicit. Unknown upstream outcome,
deadline, worker failure and durability-unconfirmed errors do not carry automatic
retry permission. operation_started:false alone cannot override an unknown global
engine journal. Authentication failures,409 catalog/snapshot/cursor conflicts and
body/filter errors never dispatch routing work. Provider text is always sanitized.

There is NO continuation endpoint or automatic reset in this proposal. A full pool
larger than the current operation's envelope cannot be drained by silently issuing
new POSTs or resetting32/4096/256. Full-pool draining needs separately reviewed
logical-operation accounting, stable catalog/target identity, finite overall bounds
and trusted release between chunks. Session reuse similarly needs an explicit
provider/source policy key, exact origin/target coordinates and IDs, finite cache
bound, pruning and no stale vectors under changed requests. These remain blockers
to a real complete automatic planner, not hidden caps or completed features.

## Offline acceptance tests for the next source slice

Fake-fetch/fake-authorizer tests should verify native course/facility DTO preservation,
changed-revision rejection, caller/session separation, generation/request/hash/token
binding across pages, bounded cursors, partial pool visibility, no static fallback,
provisional-progress invalidation on failure, no cancellation release and no
provider dispatch from reads/errors. No browser, real provider, geocoder, Spark,
container, service exposure, credentials or deployment is required or authorized.
