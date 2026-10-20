# Proposed progressive contract, local mocks only

Current frontend: `/api/config`, `/api/rankings`, eight Chicago courses,
Photon typing suggestions and one final response. Current private national API:
strict `{origins, objective, holes}` POST `/api/national/rankings`, schema2
facilities, both integer-ms scores, one final response, no area geometry.
It rejects browser Origin and supplies no CORS integration. No endpoint/security
change is implemented here. Current `main` app.js matches the inspected baseline.

Keep the pipeline: **modo ideal area → nearby existing catalog facilities →
course matrix → complete fairway ranking**. Preserve objective-specific area
search; a catalog-first substitute is outside this work.

**Before Search:** preload public immutable assets/catalog once. Typing only
invalidates stale UI generations and origin confirmation. Enter or leaving the
box commits a complete valid origin. Prepare locally only after every box is
valid and committed; Enter then blur and unchanged canonical values deduplicate.
No typing timer, location transmission, geocoding or speculative routing.
Use one in-memory preparation key, 2–8 origins and a bounded candidate pool.
Search consumes prepared state and cannot itself perform preparation. Removing
a committed golfer can invalidate the group key; Search then stays disabled
with an explicit Enter/blur recommit prompt until the new group is prepared.

**Events:** proposed local envelope `{generation, sequence, type, ...payload}`.
A future adapter also binds an opaque operation ID, schema/catalog identity,
immutable origin order, objective and holes. This is not an implemented event
endpoint. Keep existing strict private request fields and admission limits.

| Event | Required interpretation |
| --- | --- |
| `area.ready` | Validated ordered area IDs/centers, approximation, objective, search resolution, separate facility catchment and modo duration. Draw immediately. |
| `candidates.ready` | Frozen canonical IDs/points, inventory/layout/access qualifications, catalog identity. Show nearby courses with pending times. |
| `matrix.batch` | Named destination vectors in original origin order; integer nonnegative milliseconds, null for pending, explicit unreachable/outside-coverage reasons. Update arrived times together. |
| `search.complete` | Every candidate has all-origin times or a terminal destination failure. Validate authoritative ranked/unranked IDs, both scores, metadata and stage timings. |
| `search.error` | Sanitized code/message/retryable. Provider failure revokes request-wide provisional rankings; retain area/catalog context visibly as error. |

Matrix batches are the delivery unit; per-cell streaming is not promised.
The existing provider may return all final course times in one batch. Never score
an incomplete origin vector or coerce missing/unreachable to zero. Valid zero
durations remain zero. Complete vectors can show provisional relative ranks;
the whole ranking becomes final only after completion. Reject changed IDs/cells,
invalid values, duplicate sequences and stale generations. Sort deterministically
by objective, other score, name, ID. Hold the whole row order during focus/pointer
interaction, continue updating values, then apply one new order on release.
Direct keyboard focus transfer between rows holds the destination before
releasing the source, so sorting cannot interrupt the focus handoff.

Both objectives can re-sort one complete shared matrix without routing again.
Disclose its original area-search objective. A different objective-specific area
requires another explicit Search; shared-matrix scores do not imply equal
candidate sets or equal results from independent area searches.

**Timing:** record local preparation; admission/startup; modo area calculation
(including its own matrices); area-visible time from Search; shortlist work;
candidates-visible time; final course-matrix dispatch-to-validation wall time;
integer scoring; complete-visible time. Measure transport/render separately where
possible. 30 seconds remains an API protection deadline, not a normal UX target.

Deterministic scenario: area 1.8 s, nearby courses 1.9 s, first batch 4.2 s,
partial second batch 5.7 s, final batch 7.2 s, final ranking 7.3 s. Injected modo
time 1.8 s and scoring 2 ms are mocks. These illustrate roughly 5–10 s complete
results with immediate responsiveness; they establish no live performance claim.

**API coordination:** keep reservation through area plus facility routing.
Progress events, stale generations, browser abort/disconnect and UI timeouts
cannot release it. Clearing requires trusted provider-completion evidence and
clean final worker exit/EOF. Unknown work stays blocked for operator
reconciliation; no automatic retry or TTL clear. Keep single-call/admission,
HTTP/deadline/request/cell limits. The separate safety task owns that fix.
Its proposed local tip is `aa903bcda84ced25e85cb2cafc64b8ab8c82ebfd`, not deployed.
`503 busy` and `429 rate_limited` are retryable with `Retry-After: 10`;
`503 upstream_outcome_unknown`, `503 worker_unavailable` and `504 deadline_exceeded`
are non-retryable and have no Retry-After. Unknown work requires operator
reconciliation. A future adapter must retain those sanitized code/boolean/header
distinctions and never automatically submit a replacement operation.
The mock routing-failure scenario explicitly supplies `retryable:true`; its
enabled **Retry mock search** action starts one new generation for unchanged
origins only when clicked. Unspecified/nonretryable failures disable the action.
`upstream_outcome_unknown` latches a separate UI block across edits, objective
changes and cancellation, even if incorrectly tagged retryable. Nothing in this
local state represents cleared backend admission or performs reconciliation.
Future event transport, area serialization, timings and browser auth/CORS need
separate review. No service, queue, dependency, catalog expansion, publication,
Spark call or live API call was added.
