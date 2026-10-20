# Local SQLite preparation slice

This is an in-process deterministic seam, not a new endpoint, browser transport,
real MODO run or native admission release. Signed-off2dcf537 and its artifacts
remain unchanged. The separate existing browser and private national HTTP APIs
are not repointed. No compatibility fallback to JSON is added to the read adapter.

The reader reuses unchanged catalog-owner module/schema from
c9e7561c2a354168c335b333dfd5651d249b0ede. Schema/import/source-clearance ownership
stays there; this checkout integrates those dependency bytes only, plus packaging
the SQL schema. SQLite is the catalog authority; fixture JSON is transport only.
The fixture builder seeds synthetic SQLite rather than treating JSON as a catalog.

## Read and preparation interface

`SQLiteCourseCatalog.page` browses all access by default, limit1000/offset, returning
the DB-owned total/has_more/revision/cards/deduplicated destinations. `select`
unions ALL current origin regions plus ONLY the latest matching meeting regions,
deduplicating course IDs and rejecting revision changes between pages/regions.
It does not select24 courses. Its materialization safety ceiling is4096 courses,
64 pages and16 regions; exceeding it raises a visible selection error while
independent paged browsing remains available. Nothing silently drops later rows.

Planning defaults to the owner's nonmember policy: explicit booking true, or
preliminary explicit public access when booking is null; explicit false wins.
Nullable actual booking/availability and planning_basis/qualification remain
unchanged. Private/restricted courses can be requested explicitly. Unknown names,
needs_review identities and empty inventories are not manufactured or treated as
certified courses. Single round filters use documented round_options, not totals.

`DeterministicPreparation.update` receives typed Origin(id,coordinate) values,
objective maximum/combined, radius_km, access_policy and optional round_holes9/18.
Enter followed by blur with identical input deduplicates. Input removal/edit,
radius and objective changes replace the pending generation; an active operation
remains owned until fixture completion. Current origin neighborhoods appear first;
after one new-origin batch, two-or-more origins schedule the fixture area, then
route the full current pool in batches. No obsolete meeting-area union grows.

`FixtureProvider` supplies literal millisecond/null cells and area points.
Non-fixture providers are rejected. There is one active operation, not native
concurrency. `complete_active` is a trusted fixture callback, never a frontend
acknowledgement or socket-abort release. Loss/timeout retains its active operation
and blocks automatic replacement across edits. A real binding must use reviewed
worker completion/exit/EOF and durable reservation; this slice cannot provide it.

Routing batches use at most8 unique target coordinates and newest missing origin
first. Aliased destinations and separate course outcomes share point-level cells
while retaining their own canonical arrival/scope/precision. Pre-area and post-area
work share32 simulated attempts,4096 cells,256 distinct points and one inherited
30s deadline per generation. Superseded active work retains its original budget.
Commit admission also uses the existing identifier-free rate budget. Fixture
requests are not actual HTTP attempts or throughput measurements.

Cache is session-memory only, max4096 cells keyed fixture-policy identity, exact
origin identity/coordinate and target coordinate. Inactive origins and obsolete
targets are pruned; event memory is capped256 entries. No coordinates are logged,
persisted to catalog state or shared across controllers. No cache expiry clears
unknown operation ownership. The cache bound is distinct from the course pool.

## DTO and pagination binding

Events include generation, sequence, snapshot_sequence, catalog_revision,
request and SHA256 request_key, type and payload. Request binds ordered origin
IDs/coordinates, objective, radius, access policy and round preference. This is
a local contract, not an extension to the strict national POST.

- courses.ready: current region IDs/course count/target count; read a snapshot.
- area.ready: area IDs/centers and Point geometry with synthetic qualification.
  The course-neighborhood radius is NOT a MODO extent or optimization resolution.
- matrix.batch: complete fixture batch cells keyed origin and point, with
  destination aliases. Null fixture cells mean explicitly unreachable.
- operation.terminal: fixture_complete and evidence basis literal-fixture-
  completion; native_admission_released is explicitly false.
- planning.snapshot: complete paged-state envelope in the generated fixture.
- preparation.limited/error: visible exhaustion or nonretryable unknown outcome.

Snapshot has course rows containing the untouched course DTO, separately qualified
routing_target, ordered travel_times_milliseconds and origin_statuses, status,
nullable combined/maximum scores. Missing/unreachable is never zero; known zero
stays zero. Scores require every current origin. It returns total, has_more,
prepared/pending counts and ranking_complete; one batch is not the whole ranking.
Unknown outcomes revoke scores, retain catalog context and cannot be retried.

All pages must bind generation, catalog_revision, request_key AND
snapshot_sequence. Counts are not snapshot identities: cells can change while
all courses remain pending. `snapshot(expected_snapshot_sequence=...)` rejects
changed state; consumers must discard mixed pages and restart the whole read.
Sequence increases for cache/selection/operation state changes, including
compatible stale-operation cells. This controller is single-threaded; no concurrent
HTTP read/scheduler implementation is claimed.

## Fixtures and validation

`tests/fixtures/sqlite-preparation-sequence.json` is generated by
`scripts/build_preparation_fixture.py`. It binds exact frontend-supplied retained
test points/labels; this builder performs no geocoding. Course IDs/data, route
times and area geometry are synthetic. It provides one-origin then two-origin
ordered event/snapshot frames plus100-course states with24scored/76pending and
all100complete after bounded fixture batches. Larger pools can exceed this
controller's work envelope; all such rows remain visible and unscored. A future
real full-pool drain requires reviewed continuation/accounting, not hidden caps
or automatically resetting the same request's budget.

Tests use actual temporary SQLite plus literal providers, and regeneration is
checked with socket creation forbidden. Source/unit evidence does not establish
live latency, capacity, snapping, entrance verification or native cancellation.
Default real-provider binding and browser transport remain subsequent slices.
