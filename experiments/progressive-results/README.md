# Progressive fairway, local review prototype

Built in a separate worktree from `9086c6318de6c6cc7b141fc87bde5d4f11d4b219`.
This experiment retains the distinct visible modo ideal-area stage. No API,
router, geocoder, tiles, analytics, persistent query storage or new dependency is
connected. It does not replace the existing frontend or private API. These files
are outside `src/fairway/static`, so the existing Pages build does not copy them.

From the repository root, serve local assets:

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/experiments/progressive-results/`. Enter synthetic
coordinates `41.90, -88.00` and `42.10, -87.75`, confirming each with Enter or
Tab, then Search. The six facility records are exact copies from the pinned
existing catalog. Their names, IDs, points and facts are real catalog records;
the area and every driving time are synthetic. Other valid lower-48 coordinate
pairs use the same fixed mock area and times, not a geographical calculation.
All layouts are selected; no new 9/18-hole evidence is inferred from physical
totals. Eight golfer boxes and 24 candidates are lifecycle limits; this fixture
uses six candidates, at most 48 distinct course cells. A later API controls its
own narrower work budget independently of frontend limits.

The map uses the repository's vendored Leaflet with a local grid background.
It is a coordinate schematic, without geographical tiles. Existing property
pins do not certify entrances or routes. Course buttons center their point.
Keyboard focus and pointer interaction hold the whole list order while values
continue updating. Leaving the row releases one sort update. The status names
pending, provisional, final and error states. Matrix cells displayed before all
origins are available never supply a score. Genuine unreachable destinations
remain unranked. A provider outage revokes provisional scores across the request.

## Verified frontend/API differences

Read-only GitHub inspection confirmed current `main` `app.js` blob
`f7acaa2cd8ad8a4669284c497784d89934279409`, exactly matching this baseline's
frontend. PR15 was still draft at `86f54e561426e7499f6f96679a766d23ccffef63`.
PR17 is an independent catalog draft; none of its data files were imported or
edited. Existing frontend behavior was confirmed from the actual source and
build script, not by calling the live calculation service.

| Existing browser frontend | Private national prototype | Progressive design implication |
| --- | --- | --- |
| Pages builds `src/fairway/static`; map uses OSM tiles and catalog snapshots | No static/browser endpoints | Separate local experiment; no production wiring |
| `/api/config` sets Chicago bounds/provider; `/api/rankings` returns `courses` | `/health` and `/api/national/rankings`; schema2 `facilities` | Requires an explicit versioned adapter, not endpoint substitution |
| Photon suggestions start after a 300 ms typing pause | Accepts only 2–8 finite lower-48 coordinate pairs | Latest correction replaces typing pauses with Enter/blur commits in this prototype |
| Origin-aware public Chicago calculation endpoint | Rejects every browser Origin; no CORS/authentication integration | Preserve rejection; browser transport/security needs separate review |
| Final JSON ranking; second/minute UI formatting | Final JSON with integer ms vectors, both scores, unranked facilities and metadata | Progressive events are proposed only; final API remains unchanged |
| No ideal region calculation/display | `national.py` calls area provider, shortlist, then matrix; `national_modo.py` translates modo candidates | Expose validated area geometry before matrix; preserve existing order |
| Course map and catalog browsing share frontend state | Facility routing targets and layout/provenance qualifications | Reuse catalog IDs and existing qualifications; do not invent course rows |

The API response records `metadata.area_search` counters and resolution, but
does not serialize area centers/radii or per-stage wall times. Its estimator
maps fairway `combined` to modo `total`. The 25 km facility catchment is separate
from estimator search resolution. Neither area nor final ranking is a certified
global optimum. This prototype's amber center represents an approximate ideal
area, not a new optimum claim. If modo later supplies several promising areas,
display them with stable IDs and distinguish the leading area from alternatives.

## Entry preparation and lifecycle

Latest user correction supersedes timer debounce. `input` only invalidates the
generation and displayed results. It launches no preparation, geocoding,
routing, timer or process. Enter (except IME composition) or blur commits one
valid complete value. The group prepares once every box is committed, with 2–8
valid origins; incomplete added boxes block Search. Canonical coordinates form
an in-memory group key. Enter followed by blur, whitespace/decimal-equivalent
inputs and unchanged submissions deduplicate. A single most recent prepared
key/result is kept in page memory; this is bounded, not a query-history cache.
Search consumes that preparation and has no commit/preparation loop. After
removing a committed golfer, the changed group key requires an Enter/blur
recommit, with Search disabled and an explicit prompt until then.

At page load, preload the public immutable catalog, reusable IDs/local index
and UI assets once. Committed valid origins can perform cheap local validation,
coverage checks and request preparation. This fixture prepares an ID map.
No speculative engine work occurs before Search. In production, version/hash-key
only public catalog/index state across requests. Origin-specific caches or
speculative modo work require separate privacy/admission review; do not assume
preloading means routing each keystroke. Address geocoding remains deliberately
absent here. A future address flow needs a committed query, explicit confirmed
result and equivalent invalidation, bounds and deduplication.

Search starts one generation. Edits, added/removed golfers and in-flight
objective changes invalidate it immediately and cancel mock timers. Late old
events and duplicate sequence numbers are ignored. A completed matrix can
produce both objective rankings locally, with ties broken by the other score,
name and ID, matching the existing Python ranking policy. The UI explicitly
states that changing the objective reorders the same candidates from the
original area objective. Search new meeting area runs the newly selected
objective's separate area search. This is not equivalence to two independent
objective-specific area searches. No silent catalog-first substitution occurs.

Explicitly retryable mock routing failures enable **Retry mock search**, which
starts one fresh generation even for unchanged origins. No automatic retry runs.
Unspecified/nonretryable errors disable the action. `upstream_outcome_unknown`
sets a separate persistent page-memory block across edits, objectives and
cancellation; an incorrect retryable tag cannot override it. This represents a
UI refusal, not backend admission clearing or operator reconciliation.
Direct row-to-row keyboard focus transfer holds the destination before releasing
the source, preventing an intermediate sort from disrupting the next focus target.

## Proposed interface/event contract

This is a local callback envelope, not an installed endpoint, SSE/queue service,
new request schema or permission to relax Origin policy. Preserve the current
private wire request exactly: `origins`, `objective`, `holes`. The client-local
generation is separate from a future opaque server operation identity and from
the engine identity. Bind events to one accepted immutable origin order,
objective, holes, catalog ID/hash/date and shortlisted destination identities.
Do not send the raw coordinate key or retain it in logs. A later adapter must
validate external messages more deeply than this deterministic fixture consumer.

All mock envelopes have `{generation, sequence, type, ...payload}`, with a
strictly increasing sequence within a generation. A future transport needs an
opaque operation ID plus negotiated schema version, explicit finite event/byte
limits and an authoritative final result. No resuming/retrying engine work on
reconnect is proposed.

| Event | Payload / meaning |
| --- | --- |
| `area.ready` | Validated ordered `areas: [{id, center:[lat,lon], facility_radius_kilometers, resolution_kilometers}]`, modo `duration_ms`; area-search objective and truthful approximation metadata are bound to the operation |
| `candidates.ready` | Frozen bounded canonical facilities, stable IDs, points, basis, public layout/physical inventory/access qualifications, catalog identity; reveal map points/list immediately, without driving scores |
| `matrix.batch` | Named destinations with integer-ms `times` vectors in frozen origin order, each cell finite/nonnegative or `null` pending, optional terminal `unreachable` / `outside-road-coverage` reason; response may represent destination or origin-row slices of a completed provider batch |
| `search.complete` | Only after every destination has an all-origin vector or explicit terminal destination failure; authoritative final ranked/unranked IDs, both scores and existing metadata in a future adapter, plus distinct stage timings |
| `search.error` | Sanitized structured error `{code,message,retryable}`; revoke request-wide provisional ranking after provider failure; preserve useful area/catalog context with explicit error |

Router times arrive as matrix batches. Individual time cells may appear together
after one batch response, not as promised per-cell streaming. The current final
24-target route matrix may produce all course times at once. Area and candidates
still provide useful earlier stages. The mock deliberately includes an origin-row
slice to test pending times; this does not imply the current provider streams it.
More splitting can increase request count/latency, so no new batching strategy
is imposed on the API. Established cells cannot change within an operation;
unknown destination IDs, duplicates, invalid durations, changed established
times or incomplete final matrices fail clearly. Nulls and failures never become
zero. Zero is accepted only as a validated actual duration. Scores use integer
milliseconds before display rounding. Complete vectors can have provisional
relative ranks while candidates remain pending; the list is globally final only
after the authoritative complete event.

## Timing definitions

| Measurement | Start → end / interpretation |
| --- | --- |
| Local preparation | Committed valid group → local catalog/index/request preparation done; no engine time |
| Admission wait | Search accepted by ingress → worker allowed to start; current busy rejection is not successful wait time and no queue exists |
| modo calculation | Area provider entry → validated area results; includes its locate/matrix/refinement work, excludes facility matrix |
| Area visible | Search click → area drawn in UI; includes transport/admission/startup and render |
| Shortlist | Area validated → bounded canonical facility shortlist ready; measure index work separately if significant |
| Courses visible | Search click → nearby candidates painted without times |
| Course routing | Final facility matrix dispatch → all required batches validated; includes isolation if needed; separate from modo's area matrices |
| Scoring | Complete canonical matrix → validated comparable integer scores and order |
| Complete visible | Search click → final comparable ranking painted; includes all stages/transport, not just routing |

The UI reports real browser elapsed mock wall time, not engine performance.
Its simplified course-matrix clock starts on `candidates.ready` and includes
delivery plus mock scoring; a real adapter must supply dispatch/validation/scoring
measurements separately. Mock modo/scoring numbers are injected labeled values.
Deterministic unit clock: area 1.8 s, candidates 1.9 s, first batch 4.2 s,
second 5.7 s, last 7.2 s, final 7.3 s; course window 5.4 s, injected scoring 2 ms.
These are scenarios for the requested roughly 5–10 s full-ranking tolerance,
not observed live latency or guaranteed targets. UI responds immediately;
modeled useful area appears well before completion. Use browser performance
marks at actual paint boundaries in a future integrated measurement.

## API coordination and preserved boundaries

Coordination was explicitly authorized with API task
`01a135a6-e21b-773f-b0be-d4ac419820c6`. It confirmed unchanged strict request and
single final schema2 response, no progressive stream and no area geometry.
Its handoff describes proposed local tip `aa903bcda84ced25e85cb2cafc64b8ab8c82ebfd`
and functional admission commit `ebe4ccc43cf906269a5abe08b9fcdf49811c51ed`, neither
deployed nor incorporated here. Retryable 503 `busy` and 429 `rate_limited` have
Retry-After 10. Non-retryable 503 `upstream_outcome_unknown`, 503
`worker_unavailable` and 504 `deadline_exceeded` have no Retry-After. Preserve
these distinctions in a later adapter without automatic resubmission.
The admission fix is independent, outside this worktree and frozen namespace
artifacts. No safety-fix source was duplicated here.

Reserve upstream admission for the entire modo-area-plus-facility operation.
UI progress, input replacement, abort/disconnect, completion of one matrix
batch and elapsed UI timeout are not proof of upstream reclamation. Only the
API's trusted ordered provider completion evidence and clean final worker
exit/EOF permit reservation clearing. Unknown upstream outcomes remain blocked
for operator reconciliation. Future public progress messages must never be
confused with that trusted internal evidence. Keep one outstanding provider
call/admission policy and all current request/time/cell budgets until separately
reviewed. There is no automatic retry, polling loop, queue, new service or slot
increase in this prototype. 429/503/504 UI handling must preserve Retry-After and
explicit user-driven resubmission; unknown outcome does not auto-retry.

Browser Origin rejection/auth/CORS, a hardened event transport, progress IPC
bounded by existing worker/response deadlines, authoritative area serialization,
actual per-stage measurements, native upstream cancellation/capacity and live
performance remain future integration work. They are not blockers for this
mock-only design deliverable. Existing source holds, immutable catalog facts,
road attribution and privacy policies remain intact.

## Local verification

```sh
node tests/progressive-results.test.mjs
node --test tests/catalog-ui.test.mjs tests/research-map.test.mjs tests/research-refresh.test.mjs
node --check experiments/progressive-results/ui.mjs
node --check experiments/progressive-results/model.mjs
node --check experiments/progressive-results/mock.mjs
git diff --check
```

The browser check uses an already installed Playwright and Chromium. Set
`PLAYWRIGHT_MODULE` to its existing `index.mjs` if it is outside normal resolution;
`REVIEW_OUTPUT` selects the screenshot/receipt directory. It blocks all browser
URLs outside this loopback origin. No installation is required by the prototype.
`browser-check.mjs` covers commit/dedup, no typing actions, early area/candidates,
partial rows, focus stability, both objectives, stale edits, failure, added
incomplete golfer and mobile overflow. Run it with the local asset server only.
It also verifies unchanged-origin explicit recovery, no automatic retry,
direct row-to-row keyboard focus and removal followed by a rejected submit.

The portable lifecycle suite now includes the small independently extracted
`tests/fixtures/progressive-catalog-pinned.json`, so all 15 tests run without the
full catalog. It records selected IDs, repository/path, exact source commit,
full catalog SHA256 and Git blob. Records were extracted locally with
`git show 9086c6318de6c6cc7b141fc87bde5d4f11d4b219:data/catalog.json`, then selected
in the recorded ID order. The full catalog digest is
`8541ba73b8ad87d425ef0347819db737ccea7ab8490d8e2e0fd090b390fd9a4a` and Git blob
`b31b4e636936c26a8cf83650b91393fc7b265006`. The test compares all six exact
records and identities against this pinned extract; when the full source
catalog is present, it additionally verifies its whole-file digest and records.

The three existing JS suites require ignored generated static catalog/map assets.
In this worktree those were generated from the pinned canonical source using
`publish(..., write_ranking=False)`. No tracked catalog, routing input, frontend
or operational file changed. The initial missing-generated-assets check was
resolved, then all three suites passed. No Python/backend code changed, so the
unrelated national/safety suite and routing snapshots were not rerun.

Portable review archive includes these sources, a baseline patch, the existing
Leaflet/origin-row assets needed for local playback, screenshots, receipts and
hashes. It does not include catalog expansion files, frozen API bundles or
credentials. No commit, PR, push, merge, publication, deployment, live API call,
Spark request or load test was performed.
