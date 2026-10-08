# Research coverage review page

A buildless, read-only page separate from the hosted ranking application.
Run from the repository root:

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/docs/research-map/`. It reads
`data/public-courses.json` from this checkout on each page load. It does not
poll, publish updates, contact external map services or change Render, the
WSGI routes, ranking inputs or catalog/checklist files. The wheel is unchanged;
the page and its inputs are included in the source archive for reproducibility.

## Counts and limits

- Facility entry counts remain provisional. Nested `courses` are counted
  directly; a facility hole total never implies layouts.
- Four fields are name, address, county and holes. Five adds website. These
  describe record completeness, not national completeness.
- Represented means at least one catalog facility joins to the county through
  retained FIPS evidence or an exact state/county name. Unmatched records stay
  in state/region totals and are not assigned a county by coordinates.
- `searched_incomplete` is searched and explicitly unconfirmed. Only an
  explicit future `searched_complete` checklist status counts as confirmed
  complete. The current catalog has no confirmed counties. Unknown statuses
  stay unknown. A county with zero facilities is not evidence of no courses.
- Coordinates must be finite and within latitude/longitude limits. Only
  located records receive markers. `address_range_estimate` markers are
  explicitly unverified as entrances. Other kinds retain their uncertainty;
  only an explicit `verified_entrance` kind is labeled a verified entrance.
- Unlocated records remain in county/state counts and facility lists. Missing
  fields and unsearched counties are known work; national facility remainder
  is unknown, with no national progress percentage.
- `updated_on` is the compilation date, not fresh verification of every row.
  Snapshots older than two UTC days are labeled stale. Missing catalog data
  fails visibly and disables filters.

Research focus and recent additions currently show unavailable states. The
catalog does not publish current tasks or facility addition timestamps. A
separate public snapshot contract must be coordinated before enabling those
panels. Do not infer current activity from source notes, array order, county
search dates or compilation dates, and do not expose researcher notes/prompts.

## Geography

`boundaries.json` contains SVG paths derived from Census Bureau 2025 county and
state cartographic boundaries, small-scale 1:20,000,000. All 3,144 checklist
county equivalents match by FIPS. Puerto Rico is outside the catalog scope.
Lower 48 coordinates use a spherical Albers equal-area projection (parallels
29.5 and 45.5, central meridian -96). Alaska and Hawaii use labeled insets at
different scales. Rounded paths are thematic display geometry, not survey or
routing boundaries. Zooming does not make these generalized boundaries exact.

Input ZIP URLs and SHA-256 digests are in the generated file. To reproduce it,
download the exact Census files named there, verify their digests and run:

```sh
# Isolated build tool only; not an application/runtime dependency.
python -m pip install pyshp==3.1.6
python scripts/build_research_map.py counties.zip states.zip docs/research-map/boundaries.json
```

The conversion script performs no network calls or catalog writes. Census
boundaries are public domain; existing catalog source licenses remain applicable.

## Review checks

```sh
node --check docs/research-map/app.mjs
node --check docs/research-map/model.mjs
node --test tests/research-map.test.mjs
```

Also run the repository's Python lint, format, tests and build. Browser review
should exercise state/region/status/county filters, keyboard county selection,
marker toggle, reset, zero results, unavailable data and stale snapshots, plus
desktop/mobile layouts and an accessibility audit. Map data is also available
through labeled filters, a semantic county table and facility lists. SVG paths
are not thousands of keyboard tab stops. The page uses safe text DOM insertion
for catalog fields and validates outbound website URL protocols.

No runtime dependencies, external fonts, tiles, analytics, backend or polling.
The existing full catalog dominates payload size; compression is useful if a
separate static host is approved later. Nothing here enables deployment.
