> Historical revision758 preparation note. The current public contract is
> [PUBLIC-CATALOG-CONTRACT.md](PUBLIC-CATALOG-CONTRACT.md). Pins and pending gates
> below describe that earlier candidate, not the final release.

# Public native catalog seam (local candidate)

Public release branch derives from main f011e4 and accepted PR17 ancestry. UI behavior
is adapted from independently reviewed 0e95187; that prior clearance does not clear
this public adapter. Backend/private routing bytes are not adopted into Pages.

SQLite is the only maintained authority. This repository retains generated immutable
`data/catalog-release/{manifest.json,catalog.json.gz}` only. The private full database,
recovery SQL and retained documents are not copied to source packages or Pages.
Frozen writer 1d3d841 supplies the exporter and explicit-database CLI. It reads actual
native facility/course pages to completion and binds the closed file before/after.

The envelope is exactly `format_version:1`, `revision`, numeric native `schema`,
`catalog_release_key`, `facilities`, `courses`, `destinations`, `relationships`,
`provenance`, `source_licenses`, `qualification` and `authority`. The current baseline
is 758/schema 4 and release 52ba61ec..., JSON SHA feed468c... and gzip SHA 09366e1e....
Counts 7387/3641/2144, explicit nulls, shared targets and scoped evidence are retained.
The complete native shape is consumed directly; there is no schema 3 compatibility
projection. The browser verifies manifest hash/size/identity before constructing
CatalogRead and fails closed without retry or legacy fallback.

The Pages builder verifies immutable gzip+raw hashes, emits a hash-named JSON asset
and a small manifest under the project-relative `data/` directory. An explicit asset
allowlist excludes SQLite/SQL/private fixtures/credentials, private routing modules,
provider endpoint configuration and fake adapter witnesses. CI validates generated
bytes without accessing or reconstructing the private evidence-bearing database.

Plan a Round selects the full nearby course pool around the union of committed
origin neighborhoods in the browser. Radius and documented core filters apply.
Every driving time is unavailable. No MODO region, matrix, fake completion, native
admission or routing POST is used. Photon lookup is triggered only on Enter/blur;
manual coordinates remain local. OSM tiles and attribution use existing public hosts.

## Schema gate

Nas's exact-layout confirmation and the writer's relational optional-field migration
are pending. The consumer does not read sparse raw fact payload aliases into prices,
amenities or architecture. Raw observations currently expose source/date/scope only;
core typed tee values remain qualified. The final canonical optional DTO contract,
new immutable release identity, independent review and release tests must land before
publication. No push, merge or deployment has occurred from this candidate.
