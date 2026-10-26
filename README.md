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
GitHub Pages publishes from main. The committed catalog projection contains 7,430
facilities and 4,918 courses at revision 1163; the maintained SQLite stays private.
Facts retain source dates, qualifications and unknown values. Prices are dated
observations. Facility locations do not establish course entrances.

Software is MIT. Data keeps its source licenses and attribution, including
OpenStreetMap under ODbL; the site's Data credits lists them. Leaflet is BSD-2-Clause.
See [third-party notices](THIRD-PARTY-NOTICES.md).
