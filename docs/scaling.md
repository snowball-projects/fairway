# Geographic scaling

fairway should support lower-48 road calculations without weakening modo's exact
road-vertex semantics or making a national graph a permanent application
dependency.

## Current boundary

The initial Chicago snapshot contains 63,413 vertices and 166,843 compact
directed arcs in a 2.60 MB artifact. On the reference development machine it
loads in about 0.05 seconds. A three-origin shortest-path analysis takes about
0.06 seconds, and a 32-origin analysis takes about 0.39 seconds. Scanning both
objectives takes about 0.002 seconds and 0.007 seconds for those cases after the
compact engine's vectorized August 2026 changes. These are single-run
measurements, not service guarantees.

The current algorithm performs one complete shortest-path search per origin.
Its retained travel-time matrix grows with the number of origins multiplied by
the number of road vertices. A single detailed lower-48 graph would therefore
conflict with the small-process deployment before it conflicts with geographic
coordinates or state boundaries.

## Reversible first expansion

1. Build immutable regional road snapshots offline from dated OpenStreetMap
   extracts using pinned tools and cost rules.
2. Give every snapshot a supported core and a larger graph halo. Select the
   smallest core containing every origin. State borders are not routing borders.
3. Publish source timestamps, source and artifact checksums, tool versions,
   bounds, observed and imputed speed counts, vertex and arc counts, and known
   limits with each artifact.
4. Load one selected graph into the existing Python process. Add a graph cache
   only if measured traffic shows that repeated switching warrants it.
5. Start with a Great Lakes corridor whose supported core includes Milwaukee,
   Chicago, and Peoria, then test denser and larger regions before producing the
   rest of the catalog.

`data/snapshots.json` is the versioned catalog. A result remains exact only over
the graph and cost profile named in its provenance. A request that fits no
published core must fail clearly.

## National decision gate

New York, Miami, Seattle, and Los Angeles in one request require a true national
routing field. Regional snapshots cannot answer that request, and joining their
answers would not preserve shortest paths.

Before adding another runtime, benchmark an exact lower-48 prototype for
artifact size, build time, cold load, nearest-road lookup, 2-, 4-, 8-, and
32-origin routing, both objective scans, selected-point evaluation, and peak
resident memory. `scripts/benchmark_snapshot.py` records the runtime measures
that apply to the current compact engine.

```sh
python scripts/benchmark_snapshot.py data/chicago-static-v1.npz \
  41.8781,-87.6298 42.0334,-88.0834 42.0451,-87.6877
python scripts/benchmark_snapshot.py --memory-bounded \
  data/chicago-static-v1.npz 41.8781,-87.6298 42.0334,-88.0834 \
  42.0451,-87.6877
```

A routing engine is compatible only if modo can obtain the complete per-origin
travel-time field needed for its region. Point-to-point and bounded matrix APIs
are not drop-in replacements. If the compact prototype misses its measured
resource budget, a native shortest-path-tree runtime is justified. Changing the
result to sampled candidates or a straight-line approximation is a separate
product decision and must be labeled as such.
