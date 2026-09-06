# Geographic and catalog scaling

fairway ranks a finite destination catalog. Its fallback static provider
calculates one reverse shortest-path field per unique snapped destination and
retains only the requested origin columns. Peak request memory is one distance
vector rather than a course-by-vertex matrix. Work is bounded by the selected
catalog courses, not the number of origins.

For a fixed catalog, `scripts/build_course_index.py` can instead calculate one
reverse shortest-path row per course offline. The compressed float64 index is
bound to the road and course SHA-256 values. Runtime requests then perform
float64 shortest-path lookups, with no shortest-path calculation. Float32 is
intentionally rejected. Forward and reverse traversal can accumulate the same
edge costs in a different order, so the fallback deliberately uses the same
reverse traversal as the index builder. Index loading recomputes every course
row and requires bit-exact equality across the full graph. fairway then rounds
each individual time to the nearest millisecond, with exact halves rounded up,
before calculating or ordering scores. This makes output precision explicit;
provider equivalence does not depend on rounding.

The index grows with courses times graph vertices. It suits a small regional
catalog, not a national one: thousands of courses over a lower-48 graph would
be prohibitively large. National coverage still needs a tiled routing engine,
bounded regional catalogs, or another indexed many-to-many design.

## Current boundary

The initial `chicago-static-v1` graph contains 63,413 vertices in a 2.60 MB
artifact. The official service accepts at most eight origins and evaluates at
most eight catalog courses. The course catalog is loaded once; static mode also
loads the road snapshot once. Every ranking request remains stateless.

Exactness is limited to the graph vertices, edge costs, and routing points named
in the result provenance. Static free-flow costs are a model, not observed
traffic. More courses would not repair incomplete roads, stale entrances, or an
unsuitable cost profile.

## Reversible expansion

The next safe unit is an immutable regional bundle: one road snapshot with an
inner supported core and routing halo, plus one reviewed course catalog whose
destinations lie inside that core. Claim only bundles that have been built,
benchmarked, deployed, and returned in result provenance.

1. Pin the OpenStreetMap extract, region geometry, road filter, cost profile,
   tool versions, and checksums.
2. Verify every course's public access, holes, address, official link, and
   drivable destination point.
3. Publish new immutable road and course identifiers while retaining prior
   versions for reproducibility.
4. Measure artifact size, cold loading, peak memory, worst-case latency, and
   hosted cost before deployment.

Reject inputs outside one active bundle. Cross-region ranking requires prebuilt
partition and boundary routing; runtime road downloads and larger course lists
alone are not coverage.

Private courses, live tee times, prices, and ratings are separate data
decisions. They must not enter the catalog merely because a routing provider can
return a matrix for them.

## Provider decision gate

`MatrixProvider` is intentionally narrow: origins and destination coordinates
go in, matched road points, per-origin times, and provider metadata come out.
Results echo requested origins and destination identifiers so fairway can fail
closed if an adapter changes matrix identity, dimensions, or ordering.
Only unreachable and outside-coverage destinations are valid partial results;
timeouts, quotas, and provider outages fail the request with a retryable error.
The contract represents leave-now and depart-at requests. `StaticModoMatrix`
rejects both and labels its results traffic-unaware. `TomTomMatrix` supports
leave-now only. Provider configuration, cost controls, timing semantics, and
recovery are canonical in [README.md](../README.md#tomtom-configuration).
Another provider can use a self-hosted routing engine or a lawful external
matrix API without moving course discovery or ranking semantics out of fairway.

Before adding another provider or expanding its scope, record:

- matrix limits for origins and destinations
- cost per interactive ranking and at expected monthly usage
- traffic coverage and the meaning of departure times
- privacy, retention, attribution, caching, and derived-data restrictions
- latency, timeout, partial-result, and provider-outage behavior
- a local or alternate-provider recovery path

Traffic-aware ranking requires an explicit label and an operator-selectable
static fallback. Provider outages must not silently change the ranking model.

Run the repeatable local matrix benchmark with:

```sh
uv run --locked python scripts/benchmark_snapshot.py data/chicago-static-v1.npz \
  41.8781,-87.6298 42.0334,-88.0834 42.0451,-87.6877
```

Build and benchmark the optional float64 index with:

```sh
uv run --locked python scripts/build_course_index.py /tmp/fairway-courses.npz
uv run --locked python scripts/benchmark_snapshot.py \
  --course-index /tmp/fairway-courses.npz data/chicago-static-v1.npz \
  41.8781,-87.6298 42.0334,-88.0834 42.0451,-87.6877
```

A deployment must set both `FAIRWAY_COURSE_INDEX` and
`FAIRWAY_COURSE_INDEX_SHA256`. A mismatched artifact fails closed.

## Free-first rollout

Keep the current regional service and optional course index while they fit a
measured free instance. For broader coverage, prefer independently publishable
regional bundles over a national course-by-vertex index. They preserve current
ranking semantics, keep failure boundaries small, and can share modo's static
browser-tile experiment only as a traffic-unaware fallback.

TomTom is the bounded external option for this catalog. Its matrix endpoint does
not expand course coverage or establish new course facts. Keep the static
provider restartable, and measure actual usage before changing limits or adding
another routing service. A national graph, fresh traffic feed, and larger
catalog remain separate data and operations decisions.

## Chicago experiment

On August 31, 2026, the float64 index for eight courses and 63,413 vertices
built to 3,808,836 compressed bytes. Exhaustive validation matched all 507,304
course-by-vertex cells bit-for-bit.

On the development machine, the reverse-field fallback averaged 58.1 ms for
two origins and 54.4 ms for eight; indexed lookups averaged 0.08-0.09 ms per
warm request after a roughly 16 ms one-time load and 68 ms exhaustive check.
These are local measurements, not hosting guarantees; rerun the checked-in
benchmark on every candidate graph and runtime.
