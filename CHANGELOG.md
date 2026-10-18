# Changes

## Unreleased software fixes

- Read public catalog responses incrementally with byte limits, cancellation and a 30-second network deadline. Verify checksums over the original response bytes.
- Bound Pages gzip expansion before parsing, including understated sizes and concatenated gzip members.
- Cancel Photon requests when origins are edited, removed or superseded, while retaining the ten-second lookup deadline.
- Document Pages publication, package/catalog/deployment identity and the separate unfinished private API. Exercise Python 3.12 and 3.13 in CI.
- Upgrade the bootstrap uv pin to 0.12.18 for GHSA-2cv4-cqwr-gwf7 (Windows wheel-extraction path traversal).
- Preserve public UI behavior and all catalog release bytes. Package remains 0.6.2 pending release-owner version coordination.

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
