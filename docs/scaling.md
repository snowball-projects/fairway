# Geographic and catalog scaling

fairway ranks a finite destination catalog. Its static provider calculates one
shortest-path field per golfer and reads each course vertex from those fields.
The result is exact over the named graph.

## Current boundary

The initial `chicago-static-v1` graph contains 63,413 vertices in a 2.60 MB
artifact. The official service accepts at most eight origins and evaluates at
most eight catalog courses. The course catalog and road snapshot are loaded
once, while every ranking request remains stateless.

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

`StaticModoMatrix` is intentionally narrow: origins and destination coordinates
go in, snapped road points and per-origin times come out. A future provider can
use a self-hosted routing engine or a lawful external matrix API without moving
course discovery or ranking semantics out of fairway.

Before replacing the static provider, record:

- matrix limits for origins and destinations
- cost per interactive ranking and at expected monthly usage
- traffic coverage and the meaning of departure times
- privacy, retention, attribution, caching, and derived-data restrictions
- latency, timeout, partial-result, and provider-outage behavior
- a local or alternate-provider recovery path

Traffic-aware ranking would require an explicit label and a static fallback; it
must not silently replace the current model.

Run the repeatable local matrix benchmark with:

```sh
uv run --locked python scripts/benchmark_snapshot.py data/chicago-static-v1.npz \
  41.8781,-87.6298 42.0334,-88.0834 42.0451,-87.6877
```
