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

1. Add public courses only after verifying access, holes, address, official
   link, and a drivable destination point.
2. Publish a new immutable catalog identifier and retain the old catalog for
   reproducibility.
3. Build dated regional road snapshots from OpenStreetMap extracts with a
   supported core and routing halo.
4. Select one snapshot that contains all origins and candidate destinations.
   State borders and arbitrary search radii must not become routing borders.
5. Measure request latency, process memory, artifact size, failure rate, and
   hosted cost before adding a graph cache or external routing service.

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
