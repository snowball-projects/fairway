# Changes

## Software updates after 0.6.3

- Keep the latest search choice when rapid selections overlap a normal map animation. Apply it after the older camera settles, and cancel queued choices when the user changes intent.
- Load the verified generated map/search index before complete course details. Preserve pinned catalog identity, counts and complete validation; defer course views until requested and respect current drawer and map selection intent.
- Publish a content-hashed Pages JavaScript/module/CSS graph so normal reload adopts changed UI software instead of older cached scripts. Keep source URL aliases and record the compiled asset mapping in deployment metadata.

## Catalog 1163 (unreleased)

- Complete four reviewed existing-record batches: six new course identities, eleven existing course updates and contact/location updates at twenty-seven facilities. Three qualified property points improve map context without establishing entrances, routes or arrivals.
- Add seventeen tee/category records, two rounds and 258 typed observations, including 192 qualified prices. Preserve literal rating categories, unreported units, dated windows, source-specific conflicts and all age, cart, day, time and round conditions. Dated prices are not current quotes.
- The existing batches contain 321 direct enhancements and 39 supporting source observations. A separate ten-intent copy correction appends three replacement source observations and rebinds seven rows to remove private workflow wording, preserving original immutable evidence and all factual qualifications. It adds no facts or features.
- Preserve all 540 native hold scopes, existing arrivals and inventory-complete flags. No new facility or API/runtime change is included. Software package version remains 0.6.3; prior catalog 1139 is released.

## Catalog 1139 (released)

- Add three reviewed eighteen-hole course identities and confirm three existing course names. Preserve Kinzua's six physical holes, Sunserra's nine-hole par-3 identity and all unknown operation and arrival fields.
- Fill contact address components at eleven existing facilities without replacing old full-address text or changing coordinates, arrivals or inventory completeness. Preserve unresolved ZIP and structured-address conflicts.
- Add 91 qualified typed observations, including 60 dated prices, and one named tee row. Structure directly supported amount forms, fee types, age, day, holiday, cart and per-person billing qualifiers. Keep ambiguous classifications, currency, billing units and tee metrics unknown.
- Record conditional nonmember booking at three courses and two supported style values. These remain subject to their recorded conditions and do not establish live availability or physical-entry requirements.
- Correct 180 previously omitted structured cells across the 60 new price observations using the same retained sources. These are corrections, not additional features; amounts, product labels, source dates and full conditions remain unchanged.
- The two admitted batches contain 113 direct enhancements and 16 supporting source observations, not 129 new features. Software and runtime remain unchanged at package version 0.6.3.

## Catalog 1124 (released)

- Document 57 reviewed course identities at 48 existing facilities. Add no facilities or optional observations, and preserve every prior course field.
- Preserve explicit named and unnamed nines, separate eighteen- and nine-hole courses, and partial identities. Eight counts and thirteen names remain unknown; every new record retains unknown access, bookability, style, operating status and arrival.
- Keep all 4,852 preceding complete course records and existing business facts, qualified observations, relationships and licenses. Empty documented inventories decrease from 3,216 to 3,168; factual reconciliation remains incomplete.
- Preserve the deployed selection cancellation, bounded catalog loader, derived initial map and content-hashed UI graph. Software package version remains 0.6.3.

## Catalog 1089 (released)

- Document 56 reviewed course identities at 52 existing facilities, with no new facilities, optional observations or changes to prior course fields.
- Preserve named nines and the distinct three-hole and four-hole courses without deriving identities from facility totals or offered rounds. Sixteen counts and one name remain unknown; access, bookability, style, operating status and arrival remain unknown on every new record.
- Preserve all 4,796 preceding complete course records and existing facility business facts, qualified observations, relationships, provenance and licenses. Empty documented inventories decrease from 3,268 to 3,216; factual reconciliation remains incomplete.
- Keep the deployed latest-selection fix, bounded loader, derived initial index and content-hashed UI graph unchanged. Software package version remains 0.6.3.

## Catalog 1046 (released)

- Link 49 reviewed course identities at 41 existing facilities. Add no facilities, optional observations, routing arrivals or existing course-field updates.
- Preserve individually named nines and short courses without splitting totals or offered rounds. Thirteen new counts and three names remain unknown; access, bookability, style and operating status remain unknown on every new record.
- Preserve all 4,747 preceding complete course records and existing facility business facts, qualified observations, relationships, provenance and licenses. Empty documented inventories decrease from 3,309 to 3,268; factual reconciliation remains incomplete.
- Keep the deployed latest-selection fix, bounded catalog loader, derived initial index and content-hashed asset graph unchanged. Software package version remains 0.6.3.

## Catalog 1019 (released)

- Link 65 documented course identities and confirm three existing identities across 59 existing facilities. Preserve unknown counts, names, access and operation; add no facilities or optional observations.
- Keep distinct named nines, main and short courses separate from offered rounds, facility totals and incomplete inventory.
- Clarify the empty-facility message when no course records are documented, with Emerald Hill, both Tiburon properties and explicit range-only controls covered.
- Preserve the bounded catalog loader, reviewed verification matrix, initial map index and versioned asset graph. Software package remains 0.6.3; catalog identity is separate.

## Catalog 981 (released)

- Retain 4,682 courses and 7,430 facilities while adding 68 domain/relationship records and five course location-note enhancements: 73 direct improvements. Five supporting source observations bring the reviewed packet to 78 actions; provenance and storage rows are not counted again as features.
- Preserve qualified tee categories and partial metrics, documentary range conflicts, dated instructional programmes and unknown currencies. Add no courses, routing coordinates or current-availability claims.
- Correct one Agave Teal category to the source-literal W and twelve authored product-name separators through the sole writer. These thirteen field corrections add no records or features.
- Preserve all released software 0.6.3 runtime fixes. Catalog revision and software version remain separate identities.

## 0.6.3 (released)

- Read public catalog responses incrementally into a bounded growing buffer, with byte limits, cancellation and a 30-second network deadline. Tiny or empty chunks cannot accumulate retained objects or starve the deadline. Verify checksums over the original response bytes and cancel late response bodies after abort.
- Bound Pages gzip expansion before parsing, including understated sizes and concatenated gzip members.
- Cancel Photon requests when origins are edited, removed or superseded, while retaining the ten-second lookup deadline.
- Document Pages publication, package/catalog/deployment identity and the separate unfinished private API. Exercise Python 3.12 and 3.13 in CI.
- Upgrade the bootstrap uv pin to 0.12.18 for GHSA-2cv4-cqwr-gwf7 (Windows wheel-extraction path traversal).
- Release software package 0.6.3 with the public UI and reviewed catalog 967 release bytes unchanged. Driving-time comparison remains unavailable in Pages.

## Public catalog release, October 15, 2026

- Replace the old catalog publication path with an immutable SQLite-derived native5 projection.
- Preserve facility, course, component, round, tee and source distinctions, including unknowns and dated typed optional observations.
- Unify browsing and committed-origin nearby selection in the adjustable Courses drawer.
- Construct Course details on first expansion while preserving all qualified content.
- Keep public driving-time calculation unavailable; no unfinished routing is activated.

## 0.3.1

- Simplify meeting regions.

## 0.3.0

- Clarify and grade meeting regions.
- Refine map result details.
- Credit snowball in the dashboard.
- Pin the modo dependency for this release.
