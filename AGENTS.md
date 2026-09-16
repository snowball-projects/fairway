# fairway

An independent group golf-course chooser. It accepts two or more golfer origins
and ranks a bounded course catalog by either the longest individual drive or
combined driving time. It does not calculate or display an optimal midpoint or
meeting region.

## Scope and sources

- Read `README.md` for setup, `SERVICE.md` for hosted behavior and limits, and
  `data/README.md` before changing course facts, routing points or road data.
- Read the [snowball principles](https://snowball-projects.github.io/principles/)
  before public claims or architecture, data, operations and product-direction
  decisions. Do not duplicate or rewrite that policy here.
- Inspect `git status` and the relevant diff before editing. Preserve unrelated
  and unfinished work.
- Keep ranking inputs trustworthy and reproducible. The official catalog,
  supported filters, source links, routing points and update method are
  canonical in `data/README.md`.
- Keep travel-time providers replaceable. TomTom supplies optional leave-now
  matrices; modo supplies the static OpenStreetMap fallback. Do not make
  fairway depend on a hosted modo interface or silently switch providers after
  an error.

## Development and verification

Use Python 3.11+ and the committed `uv.lock`:

```sh
python -m pip install uv==0.12.6
uv sync --extra test --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
node --check src/fairway/static/app.js
node --check src/fairway/static/leaflet.js
uv run --locked python -m pytest
uv build
```

- To run the application, fetch the verified snapshot with
  `uv run --locked python scripts/fetch_snapshot.py`, then run
  `uv run --locked gunicorn fairway.app:application` and open port 8000.
- For routing, catalog or index changes, also run
  `uv run --locked python scripts/validate_snapshot.py`; validate a rebuilt
  index with its `--course-index` option. Use `docs/scaling.md` for the build
  and benchmark procedure.
- Add regression coverage for changed behavior or a demonstrated defect. Do not
  keep tests that merely repeat implementation details. Check browser behavior
  and accessibility when changing the interface.

## Implementation boundaries

- `src/fairway/app.py` owns the stateless WSGI API and request limits;
  `static/` owns the browser interface; `courses.py` and packaged `data/` own
  catalog validation and provenance. `matrix.py` is the routing-provider
  boundary, `tomtom.py` owns bounded external requests, and `course_index.py`
  is the optional offline acceleration path.
- Preserve complete origin and destination identity checks, deterministic
  millisecond scoring in `scoring.py`, honest provider metadata, and explicit
  failure for provider outages. An outage must not become a partial ranking.
- Keep road artifacts external and checksummed. Preserve ODbL attribution,
  source provenance, bounded downloads and atomic replacement. Do not rebuild
  or expand datasets merely to run ordinary application tests.

## Data and privacy

- Keep the service stateless, private by default, and free of accounts,
  analytics, advertising, behavioral tracking and personalized results.
- Keep `.env` and real credentials untracked. Document variable names in
  `.env.example`; never print keys, place them in browser assets, or include
  request coordinates or provider URLs containing keys in logs.
- External provider work must have bounded requests, timeouts and truthful
  privacy copy.
- Do not claim live traffic, prices, ratings, tee times or availability without
  a lawful, reliable source. Outbound links to official course sites are
  enough.

## Publication

- `render.yaml` is the deployment source. Verify the release's installed wheel,
  the extracted source archive's locked installation and tests, CI, hosted
  `/health`, and a bounded ranking smoke test before describing it as deployed.
- Report any checks that could not run and why.

## Stewardship

- Write `fairway`, `modo` and `snowball` in lowercase in visible copy. Credit
  software to snowball; Nas Delevski is its founder and final product direction
  remains with him. Treat snowball projects as peers.
- Original software is MIT. Preserve third-party licenses and notices. Treat
  OpenStreetMap-derived road and course data as separately licensed under ODbL
  and preserve its attribution.
- Do not add AI-builder labels or production-method badges to public copy.
- Prefer the smallest reliable design and never use em dashes.
- `CLAUDE.md` imports this file. Keep operational detail in docs rather than
  duplicating agent instructions.
