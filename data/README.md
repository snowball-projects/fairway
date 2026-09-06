# Data

fairway uses a small immutable course catalog and an optional, separately
versioned compact road graph for static routing. TomTom mode uses external
travel-time estimates while keeping the same bounded catalog. Application
source is Apache-2.0. OpenStreetMap-derived data remains subject to the Open
Database License 1.0; TomTom results remain subject to its service terms.

## Road snapshot

`src/fairway/data/snapshots.json` binds a snapshot identifier to its artifact
file, release URL, checksum, cost profile, supported core, and graph bounds.

`chicago-static-v1.npz` is a compact road graph built from OpenStreetMap data.
It is distributed as a GitHub release artifact and is not tracked in source.

- Snapshot: `chicago-static-v1`
- Cost profile: `static-free-flow-seconds-v1`
- Created: August 23, 2026 with OSMnx 2.1.1
- Supported core: 41.8600077 to 42.1699662 latitude,
  -88.1299989 to -87.6112705 longitude
- Graph bounds: 41.8500077 to 42.1799662 latitude,
  -88.1399989 to -87.6012705 longitude. The supported core stays 0.01
  degrees inside the graph on every side so accepted inputs are not on a hard
  extraction edge. This minimum halo does not prove that every ideal route
  outside the extract was retained.
- Graph: 63,413 vertices, 169,189 directed source edges, and 166,843 stored
  minimum-cost edges after parallel-edge compaction
- Artifact: 2,603,992 bytes
- SHA-256: `c095461796adda233387c66f5b32c433c0d8a76d184902daf848fed1a3f2d39c`
- Source: OpenStreetMap contributors
- Data license: Open Database License 1.0

The original GraphML checksum, extraction query, and road filter were not
retained, so v1 cannot be reproduced byte for byte. Future builds refuse
undocumented or invalid edge data and emit a checksummed build record:

```sh
uv run --locked python scripts/build_snapshot.py local-chicago.graphml \
  data/chicago-static-v2.npz \
  --source-url https://example.org/pinned-source \
  --source-date 2026-08-31 \
  --extraction 'documented region or query' \
  --road-filter 'documented OSM road filter' \
  --generator 'OSMnx 2.1.1 with documented command'
```

Replace the example values with the exact immutable source and commands used.
The builder requires a directed graph and a finite, positive `travel_time` on
every edge. Validate a release artifact and its course matrix with
`scripts/validate_snapshot.py` before publishing it.

The builder stages and rolls back the artifact and build record on ordinary
write failures, but two filesystem renames are not power-loss atomic. Published
snapshots must use a new immutable identifier and files; never rebuild over a
released pair in place.

## Course catalog

`src/fairway/data/course-catalog-v1.json` contains eight public courses whose
reviewed routing points fall inside the road snapshot's supported core: three
operated by Chicago Park District Golf and five by Forest Preserve Golf. It
includes four 9-hole and four 18-hole courses. The JSON file is the canonical
list of entries and sources.

Names, public access, street addresses, hole counts, and official course links
were checked against the operator page identified by each course's
`facts_source` on August 30, 2026. No description, rating, price, availability,
or booking inventory was copied.

Routing points were reviewed against OpenStreetMap clubhouse or published
address objects on August 30, 2026. Each item records its OSM object in
`routing_reference`. These points identify where the routing model ends. They
do not describe the course polygon and may still become stale when an entrance
or road changes.

This is not a complete directory of courses in the road coverage. It excludes
private clubs, facilities whose public access or hole count was not confirmed,
and courses beyond the current road core. In particular, the current snapshot
cannot honestly route to the Chicago Park District courses south of its core.
Unknown or unverified fields are omitted instead of inferred.

To update the catalog:

1. Verify each fact against an owner or operator page.
2. Review a drivable clubhouse, entrance, or published-address point in
   OpenStreetMap and record its object reference.
3. Confirm the point is inside the selected road snapshot's supported core.
4. Run the catalog and ranking tests against the actual snapshot.
5. Publish a new catalog identifier and `as_of` date rather than mutating a
   previously released artifact silently.

Every ranking includes the catalog file's SHA-256 digest, binding the result to
the exact local file.

Copyright OpenStreetMap contributors. OpenStreetMap data is available under the
[Open Database License](https://www.openstreetmap.org/copyright).
