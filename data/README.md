# Data

fairway uses two immutable, separately versioned inputs: a compact road graph
and a small course catalog. Application source is Apache-2.0. OpenStreetMap
derived data remains subject to the Open Database License 1.0.

## Road snapshot

`snapshots.json` binds a snapshot identifier to its artifact file, release URL,
checksum, cost profile, supported core, and graph bounds.

`chicago-static-v1.npz` is a compact road graph built from OpenStreetMap data.
It is distributed as a GitHub release artifact and is not tracked in source.

- Snapshot: `chicago-static-v1`
- Cost profile: `static-free-flow-seconds-v1`
- Created: August 23, 2026 with OSMnx 2.1.1
- Supported core: 41.8500077 to 42.1799662 latitude,
  -88.1399989 to -87.6012705 longitude
- Graph: 63,413 vertices and 169,189 directed source edges
- Artifact: 2,603,992 bytes
- SHA-256: `c095461796adda233387c66f5b32c433c0d8a76d184902daf848fed1a3f2d39c`
- Source: OpenStreetMap contributors
- Data license: Open Database License 1.0

Build it from an OSMnx-style GraphML input with:

```sh
uv run --locked python scripts/build_snapshot.py local-chicago.graphml \
  data/chicago-static-v1.npz
```

## Course catalog

`course-catalog-v1.json` contains eight public courses whose reviewed routing
points fall inside the road snapshot's supported core: three operated by Chicago
Park District Golf and five by Forest Preserve Golf. It includes four 9-hole
and four 18-hole courses. The JSON file is the canonical list of entries and
sources.

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
