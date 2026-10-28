# fairway

A static golf catalog with map browsing, search, course facts and nearby selection.
Driving-time comparison is unavailable. Drive-time ideas come from [modo](https://github.com/adelevski/modo).

Python 3.12+ and Node 24+:

```sh
uv sync --extra test --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m pytest
node --check src/fairway/static/app.js
node --check src/fairway/static/leaflet.js
node --test --test-isolation=none tests/*.test.mjs
python3 scripts/build_pages.py --check
python3 scripts/build_pages.py --output /tmp/fairway-pages
uv build
```

Serve the new output directory with `python3 -m http.server --directory /tmp/fairway-pages`.
GitHub Pages publishes from main. One maintained CSV catalog contains 16,174
facility records and 4,991 course records, rebuilt from the pinned 2026-10-25 US
OSM extract and released facts, with reviewed identity decisions and source receipts. Wikidata facts
use explicit links. Sources, dates, licenses and unknowns remain in the plain files.
The 3,103 new unnamed OSM facility polygons stay in pinned `data/catalog-inputs/`
snapshots, outside this public catalog. The remaining 97 unnamed OSM facilities
are 94 source points and three unassembled geometries; released unnamed courses stay.
`python3 scripts/export_catalog.py` regenerates GeoJSON and browser projections.
Property points do not establish entrances or independently bookable layouts.

The fairway course catalog is © OpenStreetMap contributors, licensed under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Data we create from scratch is [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

Software is MIT. Contents keep their source licenses and attribution; the site's Data credits lists them.
Leaflet is BSD-2-Clause.
See [third-party notices](THIRD-PARTY-NOTICES.md).

See [data terms](data/catalog/LICENSE.txt) and scoped licenses in metadata.json.
