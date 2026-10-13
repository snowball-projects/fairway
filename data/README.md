# Data

fairway uses a small immutable course catalog and an optional, separately
versioned compact road graph for static routing. TomTom mode uses external
travel-time estimates while keeping the same bounded catalog. Application
source is MIT-licensed. OpenStreetMap-derived data remains subject to the Open
Database License 1.0; TomTom results remain subject to its service terms.

## Road snapshot

`src/fairway/data/snapshots.json` binds a snapshot identifier to its artifact
file, release URL, checksum, cost profile, supported core, and graph bounds.

`chicago-static-v1.npz` is a compact road graph built from OpenStreetMap data.
It is distributed as a GitHub release artifact and is not tracked in source.

- Snapshot: `chicago-static-v1`
- Cost profile: `static-free-flow-seconds-v1`
- Created: August 23, 2026 with OSMnx 2.1.1
- Supported core: 41.8600077 to 42.1699662 latitude,
  -88.1299989 to -87.6112705 longitude
- Graph bounds: 41.8500077 to 42.1799662 latitude,
  -88.1399989 to -87.6012705 longitude. The supported core stays 0.01
  degrees inside the graph on every side so accepted inputs are not on a hard
  extraction edge. This minimum halo does not prove that every ideal route
  outside the extract was retained.
- Graph: 63,413 vertices, 169,189 directed source edges, and 166,843 stored
  minimum-cost edges after parallel-edge compaction
- Artifact: 2,603,992 bytes
- SHA-256: `c095461796adda233387c66f5b32c433c0d8a76d184902daf848fed1a3f2d39c`
- Source: OpenStreetMap contributors
- Data license: Open Database License 1.0

The original GraphML checksum, extraction query, and road filter were not
retained, so v1 cannot be reproduced byte for byte. Future builds refuse
undocumented or invalid edge data and emit a checksummed build record:

```sh
uv run --locked python scripts/build_snapshot.py local-chicago.graphml \
  data/chicago-static-v2.npz \
  --source-url https://example.org/pinned-source \
  --source-date 2026-08-31 \
  --extraction 'documented region or query' \
  --road-filter 'documented OSM road filter' \
  --generator 'OSMnx 2.1.1 with documented command'
```

Replace the example values with the exact immutable source and commands used.
The builder requires a directed graph and a finite, positive `travel_time` on
every edge. Validate a release artifact and its course matrix with
`scripts/validate_snapshot.py` before publishing it.

The builder stages and rolls back the artifact and build record on ordinary
write failures, but two filesystem renames are not power-loss atomic. Published
snapshots must use a new immutable identifier and files; never rebuild over a
released pair in place.

## Course catalog

The generated `src/fairway/data/course-catalog.json` contains eight public courses whose
reviewed routing points fall inside the road snapshot's supported core: three
operated by Chicago Park District Golf and five by Forest Preserve Golf. It
includes four 9-hole and four 18-hole courses. The reviewed foundation below generates this bounded projection.

Names, public access, street addresses, hole counts, and official course links
were checked against the operator page identified by each course's
`facts_source` on August 30, 2026. No description, rating, price, availability,
or booking inventory was copied.

Routing points were reviewed against OpenStreetMap clubhouse or published
address objects on August 30, 2026. Each item records its OSM object in
`routing_reference`. These points identify where the routing model ends. They
do not describe the course polygon and may still become stale when an entrance
or road changes.

This is not a complete directory of courses in the road coverage. It excludes
private clubs, facilities whose public access or hole count was not confirmed,
and courses beyond the current road core. In particular, the current snapshot
cannot honestly route to the Chicago Park District courses south of its core.
Unknown or unverified fields are omitted instead of inferred.

To update reviewed ranking facts in the foundation:

1. Verify each fact against an owner or operator page.
2. Review a drivable clubhouse, entrance, or published-address point in
   OpenStreetMap and record its object reference.
3. Confirm the point is inside the selected road snapshot's supported core.
4. Run the catalog and ranking tests against the actual snapshot.
5. Publish a new catalog identifier and `as_of` date rather than mutating a
   previously released artifact silently.

Every ranking includes the catalog file's SHA-256 digest, binding the result to
the exact local file.

Copyright OpenStreetMap contributors. OpenStreetMap data is available under the
[Open Database License](https://www.openstreetmap.org/copyright).

## Reviewed facility foundation

`data/catalog.json` is the single editable source of truth (schema 3). It owns
facility facts, nested physical courses, evidence, county research, correction
history and the bounded ranking selection. `scripts/catalog.py` is a standard
library command; it makes no source requests. Source and note tables deduplicate
repeated URLs and qualifications. Note references are ordered fragments whose
concatenation retains the original text exactly. This reduces retained facility
qualification text from 1,088,975 to 578,267 bytes without discarding conflicts.

Each facility has a persisted random `f-UUID`; each physical course has a
persisted random `c-UUID`. Mint an ID once with `mint-id` and retain it through
renames, address corrections and reordering. IDs are never derived during export.
Unnamed courses retain `name: null`; empty and partial inventories stay honest.
`physical_holes` is the whole-facility total when supported, including private
courses. `inventory_complete` does not assert access, current operation or
national completeness. Course `access` is public/private/restricted/unknown.
Source-list membership alone establishes neither field support nor course access.

An address is null or `{text, purpose}`. Purposes are `published_unspecified`,
`mailing`, `contact`, `course`, `clubhouse`, and `arrival`. Purpose is unknown
unless the retained evidence distinguishes it. A map location is independent
of arrival: all 1,931 migrated Census points remain `address_range_estimate`,
with unchanged numeric values and retained method/date/address-match evidence.
They are never routing destinations. A course may override a shared facility
address and may have an explicit `arrival` with latitude, longitude, kind and
source reference. Missing arrival stays missing; it never falls back to an
address, map estimate or another course's clubhouse.

Ranking exports require explicit public access, 9/18 holes, an applicable course,
clubhouse or arrival address, and a supported arrival. The eight existing Chicago
points remain `reviewed_osm_point`, identifying reviewed OSM clubhouses or
published-address objects as of August 30, 2026. They are not newly verified
entrances. `verified_entrance` requires actual retained verification. This change
does not expand road/ranking coverage. Changing these IDs invalidates any old
course index, which already checks destination IDs and the catalog digest.

`research` is keyed by facility ID. `listed_sources` retain unscoped source lists;
`support` records field paths, source IDs (or null for a retained qualification
without a field-scoped source), observed dates or null, and optional
shared notes. A field-specific date is retained only when originally recorded.
`courses.<course ID>.<field>` scopes an individual course. `county_match` retains
accepted match methods, addresses, FIPS and corroboration separately from facts.
Grouping review, source qualifications and unresolved reported totals live here.
Meaningful access qualifications also accompany the compact public records.

The validator in `scripts/catalog.py` is the schema contract: it checks required
facts, IDs, source/note links, field paths, coordinates, inventory sums when known,
history counts and ranking eligibility. It accepts only schema 3. Normal use:

```sh
python scripts/catalog.py validate
python scripts/catalog.py mint-id --kind facility
python scripts/catalog.py mint-id --kind course
python scripts/catalog.py export --output /tmp/fairway-catalog
# Review a full candidate document; guard against overwriting a changed source.
python scripts/catalog.py import --proposal /tmp/reviewed-catalog.json \
  --expected-sha256 <sha256-of-reviewed-current-source>
python scripts/publish_research_map.py
```

Import retains the reviewed file bytes and refuses to discard existing IDs unless
`--allow-removals` explicitly permits the reviewed change. Keep correction history
and qualifications when withdrawing a record.

Publication validates the source and generates the lean public catalog, accessible
`catalog-metadata.json` (sources, evidence, qualifications and reuse terms),
research progress, history, and `src/fairway/data/course-catalog.json`. The last
file is a committed generated ranking projection for application imports and
source installs. Never edit a projection independently. Run publication before
tests, packaging or deployment; `scripts/build.sh` does this before installation.
The public manifest hashes all snapshots. License/attribution information,
including Utah CC-BY-4.0 and OSM ODbL, remains in accompanying metadata.

### One-time migration accounting

The integrator confirmed checkpoint 26 frozen at
`300660608ba3c58fc997fa25ecc50ec9b4170eea`, public-catalog SHA-256
`8a7ac64ea4875fa60437adac63fa3063270e0851a361a4a241e4b69ee024c595`.
`data/migration-accounting.json` persists the exact ID assignment and per-record
original digest. `python scripts/audit_migration.py` checks this migration
against that Git snapshot; it is a one-time audit, not an old-schema importer.
Future facts may intentionally differ after review.

All 6,173 original facilities, 656 course entries, 1,931 estimates, 103 history
batches, 77 progress batches, county research, sources, qualifications, nulls and
correction notes are accounted for. Eight retained reviewed OSM points from the bounded catalog are also available
as labeled map points, giving 1,939 located facilities (1,931 estimates plus eight
reviewed routing points). The eight existing ranking facilities were
absent from the research catalog and are imported, giving 6,181 facilities.
Representing Lake of Isles' private South and Winagamie's unresolved TWIGS adds
two physical course records, giving 666. North is public, South private, and the
other 656 research-course access values remain unknown. Winagamie's whole-property
total becomes null; its reported 27-hole main facility remains in evidence.
Riverwood's separate clubhouse qualification and incomplete totals remain.
The 380 originally complete inventories and eight ranking inventories give 388.

History snapshots resolve to IDs only on an exact one-time name/state/address
match. Forty-five historical rows remain unlinked (`id: null`) rather than
being assigned a guessed current identity. Original names, dates, redactions,
counts and correction notes are retained. Historical totals predate the eight
bounded imports; `pre_migration_facility_count` explains that difference.
Withdrawn facilities remain excluded; recoverable pre-correction facts stay in
Git at their original revisions. No private controls or raw captures are imported.

### Existing ranking records preserved during migration

The frozen research catalog and bounded app catalog were separate inputs. The
following eight records occur in the frozen app catalog, with retained facts
review dates of August 30, 2026. Comparing the frozen Illinois research records
found no normalized name/address match or shared course-specific operator/source
host. Name-token checks likewise found no candidate except Indian Mounds/Indian
Oaks and Highland Springs, which have different towns, addresses and operators.
This does not certify national deduplication; it supports preserving these eight
existing app records in the single foundation without a guessed identity merge.
No operator or OSM source was re-requested and expansion remains paused.

| Existing record | Holes | Retained operator fact source | Retained OSM point |
| --- | ---: | --- | --- |
| Columbus Park | 9 | [Chicago Park District](https://columbuspark.cpdgolf.com/) | way/162517919 |
| Sydney R. Marovitz | 9 | [Chicago Park District](https://sydneymarovitz.cpdgolf.com/) | way/53582240 |
| Robert A. Black | 9 | [Chicago Park District](https://robertblack.cpdgolf.com/) | way/209952284 |
| Billy Caldwell | 9 | [Forest Preserve Golf](https://billycaldwell.forestpreservegolf.com/the-course/) | way/162836507 |
| Edgebrook | 18 | [Forest Preserve Golf](https://edgebrook.forestpreservegolf.com/the-course/) | way/677597973 |
| Chick Evans | 18 | [Forest Preserve Golf](https://chickevans.forestpreservegolf.com/the-course/) | way/202762135 |
| Indian Boundary | 18 | [Forest Preserve Golf](https://indianboundary.forestpreservegolf.com/) | way/163450051 |
| Highland Woods | 18 | [Forest Preserve Golf](https://highlandwoods.forestpreservegolf.com/the-course/) | way/29116340 |

Their course access is explicitly public based on the existing operator review,
not directory membership. Their physical single-course inventories and routing
coordinates preserve the existing app inputs exactly. They have no newly inferred
county. Map/routing precision is `reviewed_osm_point`: the original review covered
OSM clubhouses or published-address objects, and did not establish verified
entrances. The app keeps using these dated reviewed endpoints with an explicit
label; it does not guarantee a currently usable entrance or newly verified public
operation. Census estimates, mailing/contact addresses and unknown arrivals cannot
enter the ranking projection. The import is app-data preservation, not eight newly
researched public facilities or eight new navigation verifications.

Lake of Isles' retained owner qualification explicitly names North 18 public and
South 18 members-only. South is a nested private physical course, never a public
candidate; the whole-property 36 remains. Inventory completeness stays conservative.
The access support cites the retained qualification, with null field-scoped source
and date rather than inferring a missing per-field verification. Original owner
links and the October 10 review wording remain available in accompanying evidence.

Winagamie's owner qualification names TWIGS as an additional junior course but
does not establish its physical hole count or inclusion in the reported main 27.
TWIGS therefore has null holes and unknown access. Highlands, Woodlands and Pines
also retain null component counts; no divisions of 27, playing options, or junior
league round lengths become physical counts. Full-property holes are null and
inventory completeness remains false; reported main holes 27 stays in research.

The 45 unlinked history rows are 45 distinct retained name/state/address snapshots:
11 in the initial baseline and 34 in later batches. They remain included in the
original batch `facilities_added` totals and name lists, are not additional active
facilities, and are not redactions. The complete log totals still reconcile to
6,173 pre-migration facilities (6,185 added including baseline, less 12 removed).
Non-baseline pace remains 1,859 added and 12 removed. UI entries without an ID are
non-clickable and labeled **historical identity unlinked**, because an old spelling
or address may correspond to a corrected current facility. Recent-log display
limits remain 12 batches and 20 names per batch; the complete generated JSON
retains every row. The separate eight existing-app imports explain why current
catalog totals are 6,181 without changing or inventing a historical batch.

## Catalog browsing contract

The main map may use `map_location.kind: property_point` for a source-matched
point on the named golf property. Its identity/property-match qualification,
source URL and observed date stay in existing `research.support`; dated
`map_location` source support is required. An owner pin, official municipal map
or directly matched golf-property point may support browsing without surveying
an entrance. Geocoder estimates, viewport centers, nearby results and postcode
centroids alone do not. A property point cannot be a course `arrival`.

Optional facility `public_access` uses `public`, `private`, `restricted` or
`unknown`. `public` means at least one ordinarily public course; the facility's
physical-hole total can still include private components. Existing explicitly
public nested courses also establish public play when this facility field is
absent. No course rows are invented to make a public 27-hole facility browsable.

Main-map eligibility requires facility identity/name, known public play, a
positive physical-hole total and valid property/reviewed/entrance coordinates.
Website presence is optional. Census `address_range_estimate` points remain
unconfirmed estimates and are excluded from the main map. Browsing eligibility never
establishes routing eligibility or national discovery completeness.

Optional `website_status` is `not_checked`, `found` or `not_found`.
`website_checked_on` is a nullable ISO date. `found` requires a retained website
URL and dated check; `not_found` requires a dated check but means only that the
check did not find a website. `not_checked` has no check date. This status is
independent of map eligibility. Existing records with no recorded check remain
unchecked even when a website URL is populated.

## OSM property-match source layer

`data/source-layers/illinois-osm-property-matches-20261011.json` provides the
OpenStreetMap geometry and derived containment/identity evidence used for the
Illinois property qualifications. Copyright OpenStreetMap contributors; this
source layer and its derived matching results are offered under the
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
The source is the Geofabrik Illinois extract with OSM data through
2026-10-11T20:21:06Z. Object IDs, versions, timestamps, tags, geometry and the
unchanged pre-existing Census coordinates are included for reproducibility.

The canonical catalog links these results through its source and license
metadata. Numeric Census coordinates and independently sourced facility facts
retain their original provenance; the new property qualification depends on
OSM and is subject to ODbL. This does not establish an entrance, public access,
or current operation. The MIT software license does not license OSM data.
Keeping the evidence in a separate file does not by itself exempt a combined
or derivative database from ODbL obligations. Reusers must preserve applicable
source licenses and comply with ODbL when distributing OSM-derived databases.


`data/source-layers/illinois-osm-property-corrections-20261011.json` contains
60 further identity-matched golf polygons and derived interior property points,
also under ODbL-1.0. These replace off-property Census estimates for browsing;
the original coordinates remain in the source layer and prior catalog history.
The point derivation uses Shapely representative_point on complete valid
geometries, followed by strict containment after rounding. Namesakes, unresolved
feature duplication and the Nashville address conflict remain excluded.

`data/source-layers/illinois-osm-remaining80-properties-20261011.json` contains
65 additional identity-matched golf polygons and derived interior points from
the same Illinois extract, under ODbL-1.0. These fill previously null browse
locations; unchanged facility facts and original admission evidence remain
separate. Fourteen unmatched facilities and the insufficiently corroborated
Golfmohr spelling candidate remain unchanged.

The California property-point intake is reproducible in `source-layers/california-osm-properties-20261011.json`. It contains the selected OpenStreetMap golf polygons, versions, identity evidence and derived interior browse points, including the catalog's prior coordinate values. This layer and the resulting OSM-dependent point/location qualifications are under ODbL 1.0 with attribution to OpenStreetMap contributors. Independent facility facts retain their existing source provenance; separation into a companion file does not waive applicable combined-database obligations. Points indicate the matched property, not an entrance or a routing arrival. Source snapshot: 2026-10-11; intake: 2026-10-13.

The Florida property-point intake is reproducible in `source-layers/florida-osm-properties-20261011.json`, under the same ODbL source-layer and derived-point terms described above. It retains selected geometry, identity evidence and original coordinates; points identify golf properties for browsing, not entrances. Source snapshot: 2026-10-11; intake: 2026-10-13.

The Wisconsin property-point intake is reproducible in `source-layers/wisconsin-osm-properties-20261011.json`, under the same ODbL source-layer and derived-point terms described above. It retains selected geometry, identity evidence and original coordinates; points identify golf properties for browsing, not entrances. Source snapshot: 2026-10-11; intake: 2026-10-13.

The Ohio property-point intake is reproducible in `source-layers/ohio-osm-properties-20261011.json`, under the same ODbL source-layer and derived-point terms described above. It retains selected geometry, identity evidence and original coordinates; points identify golf properties for browsing, not entrances. Source snapshot: 2026-10-11; intake: 2026-10-13.

The Michigan property-point intake is reproducible in `source-layers/michigan-osm-properties-20261011.json`, under the same ODbL source-layer and derived-point terms described above. It retains selected geometry, identity evidence and original coordinates; points identify golf properties for browsing, not entrances. Source snapshot: 2026-10-11; intake: 2026-10-13.
