# Road snapshot

`chicago-static-v1.npz` is an immutable compact road graph built from
OpenStreetMap data. It is distributed as a GitHub release artifact and is not
tracked in the source tree.

- Snapshot: `chicago-static-v1`
- Cost profile: `static-free-flow-seconds-v1`
- Created: 2026-08-23 with OSMnx 2.1.1
- Bounds: 41.8500077 to 42.1799662 latitude, -88.1399989 to -87.6012705 longitude
- Graph: 63,413 vertices and 169,189 directed source edges
- Artifact: 2,603,992 bytes
- SHA-256: `c095461796adda233387c66f5b32c433c0d8a76d184902daf848fed1a3f2d39c`
- Source: OpenStreetMap contributors
- Data license: Open Database License 1.0

Build it with:

```sh
python scripts/build_snapshot.py local-chicago.graphml data/chicago-static-v1.npz
```

Copyright OpenStreetMap contributors. OpenStreetMap data is available under the
[Open Database License](https://www.openstreetmap.org/copyright).
