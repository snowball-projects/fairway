# fairway

fairway is a minimal dashboard for comparing two modo meeting regions. One
minimizes total driving time; the other minimizes the longest driving time. Add
two or more origins, inspect both regions, and click any map point to compare
individual and combined driving times.

[Built by AI agents](https://snowball-projects.github.io/licensing/#how-snowball-is-built)

The initial release covers the Chicago-area static road snapshot. It does not
yet account for live or historical traffic, depart-at, or arrive-by times.

## Run locally

Python 3.11 or newer is required.

```sh
python -m pip install -e '.[test]'
python scripts/fetch_snapshot.py
gunicorn fairway.app:application
```

Open `http://127.0.0.1:8000`. Address suggestions come from the public Photon
demo service. Coordinates can also be entered as `latitude, longitude`.

## Architecture

One Python process serves the browser files and JSON API. It loads one immutable
compact road snapshot, asks modo to calculate both exact vertex regions from a
shared shortest-path analysis, and keeps only a small bounded set of temporary
analyses in memory. Nothing is written to a database.

The road snapshot is a separately versioned release artifact rather than source
code. Every result identifies its snapshot, cost profile, and modo version.
`data/snapshots.json` binds each published artifact to its checksum, supported
core, graph bounds, and cost profile. `FAIRWAY_SNAPSHOT` selects one catalog
entry for the current process.

## License

fairway is a snowball project licensed under the [Apache License 2.0](LICENSE).
Its OpenStreetMap-derived road snapshot is separately available under the Open
Database License. See [data/README.md](data/README.md). The locally served
Leaflet stylesheet remains under BSD-2-Clause; see
[LEAFLET-LICENSE.txt](src/fairway/static/LEAFLET-LICENSE.txt).

See [NOTICE](NOTICE) for attribution, [CONTRIBUTING.md](CONTRIBUTING.md) before
submitting work, the official [hosted-service policy](SERVICE.md), and
snowball's [licensing and identity
policy](https://snowball-projects.github.io/licensing/).
