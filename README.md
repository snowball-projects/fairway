# fairway

fairway helps a group choose a golf course by road travel time. Add two or more
golfer origins, filter the bounded public-course catalog by hole count, and rank
the remaining courses by either the shortest longest individual drive or the
lowest combined driving time. The map keeps each golfer's color consistent and
the ranked list shows every golfer's modeled time to every course.

[Built by AI agents](https://snowball-projects.github.io/licensing/#how-snowball-is-built)

The first catalog contains eight public 9- and 18-hole courses inside the
`chicago-static-v1` road snapshot. It is a reviewed, dated starting point, not a
complete Chicagoland course directory. Results use static road costs and do not
include traffic, prices, ratings, tee times, or availability.

## Run locally

Python 3.11 or newer is required.

```sh
python -m pip install uv==0.12.6
uv sync --extra test --locked
uv run --locked python scripts/fetch_snapshot.py
uv run --locked gunicorn fairway.app:application
```

Open `http://127.0.0.1:8000`. Address suggestions come from the public Photon
demo service. Coordinates can also be entered as `latitude, longitude`.

Run the project checks with:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
node --check src/fairway/static/app.js
uv run --locked python -m pytest
```

## Ranking

For each candidate course `c`, fairway calculates every golfer's static road
travel time `t_i(c)`. The two ranking choices are:

- shortest longest drive: `max_i t_i(c)`
- lowest combined drive: `sum_i t_i(c)`

Ties use the other score, then the course name. A ranking is only as current as
the named course catalog, routing points, road snapshot, and cost profile in its
provenance. See [data/README.md](data/README.md) for the v1 catalog boundary and
source method.

## Architecture

One Python process serves the browser files and JSON API. The browser sends
confirmed origin coordinates, the selected ranking, and the hole filter to
`POST /api/rankings`. The process loads one immutable compact road snapshot,
uses modo to build the origin-to-course travel-time matrix, ranks the catalog,
and returns the result without storing the request.

`StaticModoMatrix` is the narrow routing-provider boundary. Course discovery,
filter semantics, ranking, catalog provenance, and presentation remain owned by
fairway. No database or hosted modo service is required.

## License

fairway is a snowball project licensed under the [Apache License 2.0](LICENSE).
Its OpenStreetMap-derived road snapshot and course routing-point catalog are
separately available under the Open Database License. See
[data/README.md](data/README.md). The locally served Leaflet stylesheet remains
under BSD-2-Clause; see
[LEAFLET-LICENSE.txt](src/fairway/static/LEAFLET-LICENSE.txt).

See [NOTICE](NOTICE) for attribution, [CONTRIBUTING.md](CONTRIBUTING.md) before
submitting work, the official [hosted-service policy](SERVICE.md), and
snowball's [licensing and identity
policy](https://snowball-projects.github.io/licensing/).
