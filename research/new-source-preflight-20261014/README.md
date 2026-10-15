# New-source intake review, October 14, 2026

The resumed bounded review clears **no new course cohort**. It makes six direct
control/discovery requests and admits no facility facts or dataset records.
The catalog remains 7,200 facilities and 4,460 eligible dots, with 35 distinct
accepted batch IDs. Catalog, history, progress, prior evidence, ranking inputs
and green-dot UI remain unchanged from `5e65fbd`.

MassGIS was selected because an official protected/recreational open-space
inventory is published. Historical exact MassGIS references were OSM import
attributions, not a publisher clearance or observed access hold. The first
request to `https://www.mass.gov/robots.txt` returned HTTP 403 with a forbidden
response. Intake stopped before metadata or data access. Do not retry through
`mass.gov`, `gis.data.mass.gov`, MassGIS's ArcGIS host, a browser transport or a
cached fact source. This is an observed intake denial; no general legal ban or
retraction of standing independent OSM facts is inferred.

Mass Golf was considered separately. Recovered controls contain the earlier
course-openings-list HTTP 403 and abandoned GolfNations anonymous API HTTP 401.
No direct request or fact admission was made. Initial search discovery preceded
recovery of that hold and supplies no accepted facts. These are independent of
MassGIS's new stop and remain active. New York Parks also stays excluded under
its existing publisher/alias hold.

The independent Connecticut GIS portal returned HTTP 200 robots permitting
the discovery route and declaring wildcard `Crawl-delay: 60`. Five direct
Connecticut control/discovery requests used one conservative pacing group,
with at least 60 seconds from completion to the next start. The actual linked
State Privacy Policy was read. The actual linked `/pages/terms-of-use` returned
a complete HTTP 200 application shell and embedded site configuration, but no
governing Terms of Use body or dataset-specific reuse license. Site
`licenseInfo: null` establishes neither permission nor prohibition. No API
query, dataset download, course profile, credential or new fact was used.
Further portal intake is paused while governing policy/reuse scope remains
unconfirmed; do not use an alternate delivery route to recover missing facts.
This is not a statewide legal ban on Connecticut agencies.

`request-audit.json` retains all six direct request identities, UTC times,
statuses, byte lengths, hashes and forward completion gaps. Each publisher's
final gap is null. Raw bodies and normalized response headers remain private;
no raw publisher text is committed. `new-stops.json` records the new scopes,
and `outcome.json` records the unchanged catalog hash and decision needed.

The concrete next-source plan is a publisher-provided maintained golf inventory
from the Connecticut GIS Office, with stable facility IDs, explicit public or
nonmember play classification, facility/course distinctions, observation dates
and written reuse/attribution terms. Public land access or geometry alone is
insufficient. Start with at most 20 records after a suitable licensed file is
provided, deduplicate against the current catalog, and retain the established
acceptance checks. Human authorization to contact the publisher, or provision
of an independently authorized export, is needed for that route. No external
message is part of this review. The practical 100-facility target never lowers
evidence standards; PR #17 remains open, draft and unmerged.
