# Research coverage review page

A buildless, read-only page separate from the hosted ranking application.
Run from the repository root:

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/docs/research-map/`. It reads
`data/public-courses.json` from this checkout on each page load. It does not
poll, contact external map services or change WSGI routes, ranking inputs or
catalog/checklist files. The page and public inputs are included in the source
archive for reproducibility.

The existing Render build runs `scripts/publish_research_map.py` before the
locked installation. This copies the reviewed browser files and exact public
catalog/status bytes into generated, ignored static directories, also included
in the wheel. The existing static handler serves `/research-map/index.html`
and `/data/` JSON, using its existing security headers; no route or CSP change
is needed. `publication.json` binds the served inputs to their SHA-256 digests.
The script requires the published progress sidecar and performs no network
calls or source-data writes. No hosting migration or additional service is used.
Data remains a deployment snapshot until the next existing Render build.

## Counts and limits

- Facility entry counts remain provisional. Nested `courses` are counted
  directly; a facility hole total never implies layouts.
- Four fields are name, address, county and holes. Five adds website. These
  describe record completeness, not national completeness.
- Represented means at least one catalog facility joins to the county through
  an exact state/county name. Null and unmatched county records stay
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

Research focus and recent additions independently load the public
`data/research-progress.json` version 1 sidecar on page load. Missing or
unsupported sidecars show unavailable without breaking the catalog view.
`updated_at` is the UTC snapshot time; snapshots older than two days, with
unknown times or implausibly future times are labeled stale. Stale region
status remains labeled as a historical snapshot and loses the focus outline.
There is no polling or claim of live researcher activity.

The agreed contract is `schema_version`, `updated_at`, `catalog_commit`,
`active_regions` (`state`, `county_fips` or null, `stage`, `note`) and
`recent_batches` (`published_at`, `commit`, `facilities_added`,
`facilities_updated`, `added_facilities` with `name`, `state`, `address`). The
page only displays valid US regions, the stages discovery/verification/review/
queued, explicit nonnegative integer counts and times. It omits `note` and
unknown extra fields. Missing counts stay unknown. Batch totals are explicitly
all-region totals and are not altered by geographic filters.

Addition identities are exact name/state/address tuples; no invented facility
IDs, fuzzy matches or additions inferred from array order. An addition absent
from the loaded catalog remains labeled absent. Catalog and status snapshots
can refer to different revisions; the status catalog commit is linked
separately without claiming that it matches the loaded catalog. Only valid
40-character commit hashes receive change links. The page does not write,
package a substitute sidecar or publish status data.

## Geography

`boundaries.json` contains SVG paths derived from Census Bureau 2025 county and
state cartographic boundaries, small-scale 1:20,000,000. All 3,144 checklist
county equivalents match by FIPS. Puerto Rico is outside the catalog scope.
Future unmatched shapes are hatched and labeled unknown, never zero. Checklist
counties without geometry stay in the table and counts, with an explicit
unmapped warning and a boundary-unavailable label in their detail panel.
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
