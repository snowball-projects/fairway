# fairway

fairway's [hosted interface](https://fairway-n29h.onrender.com) ranks a bounded
public-course catalog for two or more golfer origins. It can minimize either the
longest individual drive or the group's combined driving time, and reports every
golfer's modeled time to each course.

The current catalog contains eight public 9- and 18-hole courses in a bounded
Chicago region. It is dated and incomplete. The interface identifies its
travel-time provider: TomTom with live and historical traffic for leaving now,
or a local static modo road snapshot without traffic. Prices, ratings, and
live tee-time availability are not included.

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

The wheel contains the application, browser assets, and immutable metadata.
The separately licensed road artifact remains external; the installed
`fairway-fetch-snapshot` command downloads and verifies it in the user's cache.

Run the project checks with:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
node --check src/fairway/static/app.js
node --check src/fairway/static/leaflet.js
uv run --locked python -m pytest
uv build
```

Release both the wheel and source archive. The source archive includes the
lockfile, maintenance scripts, tests, and operating documentation. CI extracts
it into a separate directory, installs its locked dependencies, and runs its
tests so validation does not depend on files from the original checkout.

## App icon

Keep the full-resolution artwork in `docs/icon.png` and use the same artwork
on snowball's project card. The header and touch icon share one small PNG;
the browser tab uses a 32-pixel version. After replacing the source, regenerate
both with macOS's built-in image tool (or equivalent PNG resizing):

```sh
sips -z 180 180 docs/icon.png --out src/fairway/static/icon.png
sips -z 32 32 docs/icon.png --out src/fairway/static/favicon.png
```

## TomTom configuration

Put a fairway-specific Matrix Routing v2 key in the ignored `.env` file using
the names in `.env.example`, then start with:

```sh
uv run --locked --env-file .env gunicorn --workers 1 --threads 4 fairway.app:application
```

The presence of `TOMTOM_API_KEY` selects TomTom. Set `FAIRWAY_MATRIX_PROVIDER=static`
to explicitly use local routing, or `tomtom` to require the key at startup.
The key is used only by the server. Confirmed coordinates go to TomTom for one
synchronous matrix; the app does not cache them. A failed provider request
returns a retryable error without switching to static results. `/api/config`
describes the active provider; `/health` checks local readiness without billing
an external request.

The adapter sends at most 100 cells in one request (64 with today's catalog),
uses a 20-second deadline and 1 MiB response limit, and never retries or follows
redirects. `FAIRWAY_TOMTOM_DAILY_CELLS` defaults to **80 submitted cells per UTC
day per process**, including failed attempts; `0` pauses external calculations.
Keep one worker. Restarts reset this identifier-free guard, and extra replicas
each have a separate budget. Configure the provider account's own quota or
spending controls; this application guard is not a billing cap.

TomTom's [billing formula](https://docs.tomtom.com/matrix-routing-v2-api/documentation/discounted-transaction-billing)
charges 16 transactions for a 2-by-8 ranking and 40 for an 8-by-8 ranking.
The [pricing page](https://docs.tomtom.com/pricing) lists 2,500 monthly free
transactions as checked September 6, 2026. Quotas belong to the account, and
other usage can consume them. Check current terms and account limits before
raising the guard. Use `render.yaml` for deployment and put the key in Render's
secret environment settings; never commit it to the blueprint.

## Ranking

For each candidate course `c`, fairway calculates every golfer's modeled road
travel time `t_i(c)`. The two ranking choices are:

- shortest longest drive: `max_i t_i(c)`
- lowest combined drive: `sum_i t_i(c)`

Each modeled time is rounded to the nearest millisecond, with exact halves
rounded up, before either score is calculated. Ties use the other score, then
the course name and stable identifier. A ranking is only as current as the
named course catalog, routing points, provider, and timing or static cost
profile in its provenance. See
[data/README.md](data/README.md) for the v1 catalog boundary and source method.

## Architecture

One Python process serves the browser files and JSON API. The browser sends
confirmed origin coordinates, the ranking method, and the hole filter to
`POST /api/rankings`. The process requests a bounded TomTom matrix or uses modo
with one immutable road snapshot, ranks the catalog, and returns the result
without storing the request.

The static matrix implementation holds one reverse destination-distance field
at a time.
An optional checksummed, float64 course index can move the same shortest-path
model to an offline build and reduce each request to bounded lookups. See
[docs/scaling.md](docs/scaling.md).

`MatrixProvider` is the narrow routing-provider boundary. Its results carry the
provider, traffic basis, departure semantics, and available freshness times.
The response must echo the requested origins and destination identifiers in
order; fairway rejects mismatched matrices before ranking them.
Only unreachable or out-of-coverage destinations may be omitted. Provider
outages produce a retryable service error instead of a partial ranking.
`StaticModoMatrix` identifies itself as traffic-unaware and rejects
time-dependent requests. `TomTomMatrix` uses the provider's leave-now mode,
which resolves departure separately for each cell. Provenance records the
earliest and latest returned departure times and the response calculation
time; traffic-data freshness remains unknown. Course discovery, filter
semantics, ranking, catalog provenance, and presentation remain owned by
fairway. No database or hosted modo service is required.

## Research

The isolated [catalog expansion experiment](https://github.com/snowball-projects/fairway/tree/main/experiments/catalog-expansion)
preserves earlier OSM catalog-generation and candidate-selection research.
It is not used by the hosted app; its historical benchmark did not establish
a production-ready national shortlist.

## License

fairway's snowball-owned software is licensed under the [MIT License](LICENSE).
The OpenStreetMap-derived road snapshot and course routing-point catalog remain
under the Open Database License; see [data/README.md](data/README.md). The local
Leaflet JavaScript and stylesheet remain under BSD-2-Clause; see
[LEAFLET-LICENSE.txt](src/fairway/static/LEAFLET-LICENSE.txt).

See [NOTICE](NOTICE) for attribution, [CONTRIBUTING.md](CONTRIBUTING.md) before
submitting work, the official [hosted-service policy](SERVICE.md), and
snowball's [licensing and identity
policy](https://snowball-projects.github.io/about/#licensing).
