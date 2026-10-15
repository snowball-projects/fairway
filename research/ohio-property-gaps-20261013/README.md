# Ohio existing-facility property gaps

This batch reconciles three existing facilities on main
`f011e4b8330577613f781a6cc3e32b0a2915beb6`, after PR13's nine hole totals and
PR14's thirteen additions. It adds three property browse points and explicit
operator-public access, and corrects Beavercreek's published ZIP45324 to45431.
It adds no facilities, hole totals, nested course records or routing arrivals.

The ID-scoped review is
`../../data/review-batches/ohio-property-gaps-03-20261013.json`. Complete selected
ODbL geometry, versions, tags, identity decisions and point derivation are in
`../../data/source-layers/ohio-property-gaps-03-20261011.json`. The retained input
SHA256 matches committed Ohio provenance; new hash serialization is explicit.
Upstream geometry hashes retain their original unspecified serialization.
Shapely 2.1.2 unions the selected areas, derives PointOnSurface and checks strict
containment after eight-decimal rounding. No proximity-only, fuzzy-only,
address-range, map-viewport or entrance inference is used.

`semantic-delta-main-f011e4b.json` records every changed facility key and appended
provenance value. `preservation-main-f011e4b.json` checks every current-main
facility and unrelated canonical field, all thirteen addition IDs, all nine hole
totals, existing named/numeric registry entries, nested courses, arrivals,
Maryland records, ranking bytes and progress. One license entry and a factual
correction-history entry are appended without rewriting prior entries.

`returned-evidence-excerpts.json` contains short verbatim transcriptions from the
earlier native official-page results, with returned URL/line/crawl-vintage data.
Operator reads preceded the robots attempts. All three robots reads were
inaccessible without HTTP status or rules; no retry, alternate source route or
subsequent operator request occurred. These excerpts are not raw HTML, original
HTTP responses or complete exported response buffers, which were not retained.
Exact acquisition times and successful-page HTTP statuses are not invented.
Independent and parent review accepted the factual scoped delta while preserving
these limitations; no source-wide permission or live availability is established.

The accepted complete review archive remains in Library as
`libfile_6a951cb980008191b3b4cbb0edcd3575`, version1, SHA256
`d19e49c29e629abb6e060331bac5f95693e5b50cd1a455126ca94e63b8f45e5b`.
Its original review baseline was `3fe8f486cce87ec1e38524c7e49c732ed368d05e` and
head `b2c1ec2f1f54130f74d61fb5633da5c661379340`; reconciliation preserves its
accepted factual rows and source geometry. Its self-contained Git bundle and
full baseline/head catalogs permit independent whole-catalog comparison. No
operator source was refetched while applying the accepted delta to current main.
