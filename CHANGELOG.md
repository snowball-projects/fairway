# Changes

## Catalog 981 (unreleased)

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
