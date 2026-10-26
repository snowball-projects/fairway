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
GitHub Pages publishes from main. One maintained CSV catalog contains 19,437
facility records and 4,952 course records, rebuilt from the pinned 2026-10-25 US
OSM extract and released facts joined by exact stored OSM identity. Wikidata facts
use explicit links. Sources, dates, licenses and unknowns remain in the plain files.
Unnamed records retain null names and use their OSM identity as the map label.
Property points do not establish entrances or independently bookable layouts.

Software is MIT. The database is ODbL; contents keep their source licenses and attribution, including
OpenStreetMap under ODbL; the site's Data credits lists them. Leaflet is BSD-2-Clause.
See [third-party notices](THIRD-PARTY-NOTICES.md).

See [data terms](data/catalog/LICENSE.txt) and scoped licenses in metadata.json.
