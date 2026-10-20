# Draft existing interface progressive planning review

This describes the earlier frozen mock review. The next local slice is specified in sqlite-dto-frontend.md and uses the validated API-owned preparation DTO; its planning runtime replaces the browser selection/cache/scoring described below. The original and corrected review artifacts remain unchanged.

The local prototype extends the existing fairway map and Plan a Round pane. Committing an address with Enter or blur places its pin, fits all current pins, opens Courses, and prepares nearby course driving times. Two or more origins also start the distinct modo meeting-area stage. Typing performs no geocoding or routing. This is a review implementation with deterministic mock transport, not a release or measured routing benchmark.

## Existing frontend and national API differences

Baseline is `9086c6318de6c6cc7b141fc87bde5d4f11d4b219`. The published frontend uses Photon and `/api/config` plus `/api/rankings` for the small Chicago catalog. The private national API accepts strict `{origins, objective, holes}` with 2 through 8 lower48 origins and returns one final JSON response. It does not expose a meeting area, neighborhood query, preparation session, progress stream or single-origin ranking. Its browser Origin rejection and admission protections remain intact. No endpoint was repointed and no backend file was edited here.

The local API owner is developing separate SQLite reads and deterministic preparation from admission commit `2dcf53775566d45131fb47b42fac45a71f5dd976`. Proposed stages below are interface requirements; they are not capabilities of the published API. UI cancellation, stale generations and network disconnects never prove provider completion or release an upstream reservation.

## Acceptance behavior

- Enter and blur deduplicate the same committed origin. Incomplete text starts no work; address resolution must yield a valid coordinate. Editing invalidates scores and stale generations immediately. The local fixture resolver recognizes only the listed test addresses.
- First origin fits its pin and shows nearby retained course records. A complete single-driver value can rank that course. Additional origins fit all current pins and remove final group scores until each course has every required origin time.
- Radius choices are 10, 20 and 25 miles. Default 20 is provisional. Candidate pool is the deduplicated union of all current origin regions and only the latest modo area, never historic regions. Every matching locatable course remains visible; 24 is only a routing window.
- Nearby cards show pending times immediately. A modo area event appears on the existing map before its course matrix completes. Router output arrives in batches; per-cell streaming is not assumed. Missing, unreachable and outside-road-coverage cells do not become zero.
- Longest and combined integer-millisecond scores require complete vectors. Both can be computed from the same completed candidate matrix. This does not make objective-specific modo area searches equivalent. Name, combined, longest and per-origin display sorts remain separate from the modo objective. Ranking is provisional while pool members remain unscored.
- Course order stays stable during pointer or keyboard interaction, including direct Tab handoff between cards. Scores update in place. A focused row leaving the current region stays temporarily marked outside the region, then disappears after interaction ends.
- One Courses pane has a filter and sort menu. Browse and Search This Area show no driving times and start no routing. Browse includes all access; the current baseline mock planning view approximates eligibility using public components. The SQLite cutover must consume the derived qualified plan_eligible decision instead.
- State is geography. Holes uses documented course records, never a facility aggregate split. No 27-hole round assertion. Style and unsupported access classifications remain unavailable until sourced fields exist. Private and Restricted are selectable. Retained records explicitly show course identity unconfirmed; broad browsing has no mandatory verification gate.

## Local event contract and timing definitions

Each committed generation binds origin IDs and coordinates, modo objective, radius, hole/access selection, catalog revision and provider policy. One adapter operation is active; one latest generation can wait. No keystroke timer, automatic retry loop or general queue exists. Page-memory matrix reuse requires compatible origin and destination identity, coordinates and policy; catalog changes invalidate cached values.

| Event or boundary | Required meaning |
| --- | --- |
| origin committed | Valid confirmed coordinate, not raw input; local pin and neighborhood selection can render immediately |
| area ready | Current generation, objective and revision; distinct modo centers/geometry and qualification; latest area replaces prior area |
| matrix batch | Bound origin IDs and route-target IDs; integer milliseconds or explicit unreachable/coverage reason; preserve course aliases |
| operation terminal | Server/adapter supplies trusted completion or explicit admission hold; progress or UI abort cannot supply this proof |
| retryable error | Explicit user retry only, respecting backend Retry-After and admission status |
| unknown outcome | Block dependent work and retries until authoritative reconciliation; editing or elapsed time cannot clear the hold |

Define `origin_resolution_ms` from committed address to confirmed coordinate. Define `local_first_courses_ms` from confirmed origin to the neighborhood paint. Define `modo_area_compute_ms` within the server from admitted area search to its result, separately from its queue/admission delay and browser `area_visible_ms`. Define `fairway_matrix_ms` from admitted first course-window request through all required batch results, excluding modo compute; report window count and cells. Define `fairway_scoring_ms` after complete vectors arrive, and `full_pool_rank_visible_ms` through the final comparable pool paint. Stage spans may overlap and must not be added blindly. Use monotonic spans within each process; do not subtract unrelated clocks. The requested 5 through 10 seconds is a target for full search completion, not an observed result. Mock waits are 40 ms address resolution, 400 ms per matrix chunk and 1200 ms for the area stage; browser tests use a virtual clock.

## SQLite course read contract

The data owner's `docs/catalog/QUERY-CONTRACT.md` defines clean JSON transport from authoritative SQLite. No database engine belongs in the browser. Query responses contain revision, total/has_more, limit/offset, course rows and deduplicated destinations. Course rows carry course_id/facility_id, nullable name, physical_holes, round_options, access, nullable nonmember_bookable, identity_status, map_location, canonical arrival and destination_id. Address explicitly records scope or suppression. Map location and arrival are distinct.

Browse includes retained needs_review rows without certifying independent playable rounds. The latest `--plan` contract accepts explicit nonmember_bookable=true, or retained explicit public course access when that fact is unknown, preserving access_qualification and planning_basis. Explicit nonmember_bookable=false wins; facility labels cannot promote components. Preliminary eligibility does not assert booking availability. The nullable booking fact remains unknown unless sourced. Physical 9/18 filters and documented round-length filters must stay separate. Empty inventories yield no synthetic courses. Optional metadata stays absent/null; price, quality and publisher badges are not inferred.

Read every page for each current spatial region, merge course_id across regions, retain all matched courses for display, then deduplicate destination_id for routing. Shared qualified facility estimates retain separate course outcomes and canonical arrival=null. A course arrival target does not move the facility map identity. A changed revision invalidates mixed-page results. Fixture JSON is generated test transport, not a second editable catalog.

## Remaining integration gaps

The actual UI still reads the unchanged baseline static map catalog for this review. Production SQLite transport and qualified preliminary eligibility are not wired. Frozen baseline fixture projection is local scaffolding, not a compatibility migration. The API owner will supply paged pool and clean route DTOs; cutover removes this scaffolding rather than retaining dual authority. Refreshing fixtures has confirmed nullable booking facts remain unknown while plan_eligible can be true through accepted public-play evidence.

The current controller routes at most 24 course targets before the area and 24 after it, retaining all remaining cards as pending. It does not automatically drain further windows; full-pool scheduling and destination alias dedup require the coordinated API controller. The mock's possible 48 targets are separate windows, not one matrix. Real requests must share the existing global envelope of 32 upstream attempts, 4096 cells and 256 targets including modo, preserve trusted admission and bound concurrent work. Do not claim a full ranking when work exceeds a safe request budget. The preview currently materializes planning rows; larger pools need pagination or virtualization without dropping pool members.

## Review and checks

Changed source: existing app.js/index.html/styles.css plus planning-session.mjs. Tests cover lifecycle, exact zero/missing/unreachable values, stale and retry holds, broad display beyond the routing window, explicit access, course identities and canonical-versus-estimated arrivals. Browser checks exercise the actual existing layout, pin fits, first-origin opening, separate modo area, radius, sort/focus handoff, natural removal, no browse routing and mobile focus/overflow.

The portable ZIP contains a source patch, exact source hashes, fixtures, test output and screenshots. Its preview is a copied existing index with a mock bootstrap and self-only network policy. Serve the extracted package on loopback and open the existing index path in PREVIEW.txt. All browser application requests in the test harness are loopback only; no Photon, OSM tile, live API, Spark or user-location transmission occurs. The repository source without that bootstrap retains the original committed-address Photon fallback and OSM map path and is not the offline review entry point. No new repository authority, service, dependency, PR, push, deployment or publication is included.
