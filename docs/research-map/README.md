# Research coverage review page

A buildless, read-only page separate from the hosted ranking application.
Run from the repository root:

```sh
python scripts/publish_research_map.py
python -m http.server 8765 --bind 127.0.0.1 --directory src/fairway/static
```

Open `http://127.0.0.1:8765/research-map/index.html`. It reads
public JSON prepared from this checkout. It does not
contact external map services or change WSGI routes, ranking inputs or
catalog/checklist files. The page and public inputs are included in the source
archive for reproducibility.

The existing Render build validates `data/catalog.json` and generates all public
snapshots plus the bounded ranking catalog before installing the application.
The static handler serves `/research-map/index.html` and `/data/` using its existing
security headers. `publication.json` binds catalog, progress, history and accessible
source metadata to SHA-256 digests. No network requests or source writes occur.
Only schema 3 is supported. Invalid canonical data stops the build.

## Counts and limits

Facility and physical-course counts remain provisional. A facility hole total
includes private courses when supported, and never implies how many layouts exist.
Four fields are name, published address, county and physical holes; five adds
website. These describe record completeness, not national completeness. Unknown
holes, course access and inventories remain unknown. An inventory can be complete
without established course access. Cards distinguish physical holes from each
course's public/private/restricted/unknown access and show retained access conditions.

Addresses identify their supported purpose, including mailing/contact addresses.
Map estimates remain labeled as entrance-unverified, and never establish routing
destinations. The ranking app retains its eight separately reviewed OSM points;
this research map does not expand its routing coverage. Source qualifications and
reuse terms are accessible in `catalog-metadata.json` from the footer and cards.

Represented counties join only through exact state/county names. Null and unmatched
county records remain in state/region counts without invented coordinate joins.
Only explicit `searched_complete` counts as complete; all current searches remain
incomplete. Zero records are not evidence of no courses. No national remainder or
national progress percentage is claimed. Compilation and research-status dates
retain their original meanings and freshness warnings.

## Published updates and history

The visible page checks the same-origin publication manifest every 60 seconds.
Changed snapshots are verified before adoption. Hidden pages pause requests;
failures retain the working view and back off from two to ten minutes. Selection,
filters, zoom, focus and scroll survive refresh. Permanent facility IDs identify
new records and retain selection through renames and address corrections. New IDs
receive a 30-second highlight; the first snapshot is a baseline.

History and progress derive from the same reviewed source. Batches retain original
commit times, counts, corrections, redactions and historical identity snapshots.
Linked historical entries carry facility IDs; unmatched historical rows explicitly
retain null IDs and are labeled historical identity unlinked, without fuzzy joins.
An unlinked old address/name can belong to a corrected current facility; it is
not an assertion that the facility is absent. The initial
baseline is excluded from pace totals; recent batches remain independent of
geographic filters. Historical counts exclude the eight existing bounded ranking
facilities imported during migration, as explained in the log metadata and
[data foundation documentation](../../data/README.md).

Research focus remains a dated snapshot, not live worker activity. Stale or unknown
times lose the focus outline. The source-history audit remains in progress. A
successful build does not verify every facility or establish national completeness.

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
node --check docs/research-map/refresh.mjs
node --test tests/research-map.test.mjs tests/research-refresh.test.mjs
```

Also run the repository's Python lint, format, tests and build. Browser review
should exercise state/region/status/county filters, keyboard county selection,
marker toggle, reset, zero results, unavailable data and stale snapshots, plus
desktop/mobile layouts and an accessibility audit. Map data is also available
through labeled filters, a semantic county table and facility lists. SVG paths
are not thousands of keyboard tab stops. The page uses safe text DOM insertion
for catalog fields and validates outbound website URL protocols.

No runtime dependencies, external fonts, tiles, analytics or new backend.
The existing full catalog dominates payload size; compression is useful if a
separate static host is approved later. Nothing here enables deployment.

## Main catalog interface

The main Leaflet map now loads the same catalog before ranking. Local facility,
city and state search, optional estimates/counties, retractable desktop drawers
and mobile sheets share facility selection. State search fits retained Census
geometry inverted from this page's display projection; facility search fits
actual points, never invented property polygons. City search uses only catalog
addresses with an explicit city/state/ZIP pattern and fits those catalog points.
It makes no remote place-search requests or claims to be a complete city gazetteer.

The permanent Catalog progress modal shows derived On map / Not yet on map
counts under the contract in `data/README.md`, plus one commit-deduplicated activity
log in America/Chicago AM/PM time. Existing record completion and county discovery
remain separate. The old standalone page is retained as a secondary research
view; its legacy four/five metrics do not determine main-map eligibility.

No automatic geolocation, persistence, new tiles or new paid requests are added.
The current ranking API remains limited to its reviewed Chicago courses and road
coverage. Origins elsewhere may be entered, but the UI explains unsupported
routing before requesting a matrix. Lower-48 meeting-area optimization remains
a separate backend/data requirement, not a geographic-midpoint approximation.
