# Catalog expansion experiment

Preserved research from `adelevski/midpoint-tool` at
`49e8320a67a2d1839504911877a734f253e6f19e`, July–August 2026.
This is an offline starting point for expanding fairway's course catalog and
measuring candidate selection. It is not used by the app or included in its
Python distributions. The live catalog, ranking and provider contracts remain
in the main [README](../../README.md) and [data notes](../../data/README.md).

## Run the retained checks

Use Node.js 22.18 or newer. No npm dependencies or installation are needed.
Run commands from this directory because fixtures and artifact paths are relative:

```sh
cd experiments/catalog-expansion
npm test
mkdir -p .local
npm run generate:golf-course-catalog -- audit/golf-course-catalog/bounded-sample.jsonl .local/bounded-catalog.json
```

Tests use synthetic fixtures and make no external provider requests. The
PowerShell runner tests check its manifest and structural safeguards; they do
not execute Windows extraction or download national data. CI runs these checks
separately from the Python app.

## What is preserved

- Deterministic OSM JSONL normalization, conservative identity/multipolygon
  deduplication, explicit unknown metadata and coordinate provenance.
- A fixed 49-jurisdiction source manifest and Windows PowerShell/Osmium
  extraction tooling, including restart markers and clipped relation handling.
- Two geographic search anchors, local/global/origin/radial candidate sources,
  exact route budgets, nested candidate expansion and historical ranking logic.
- Twenty-six public-origin scenarios and cache-aware benchmark, policy
  comparison and larger-budget evidence-audit tools.
- Supporting tests, small fixtures and historical findings. `provenance.json`
  records each imported file's original SHA-256; the initial extraction is
  byte-for-byte. Update that record with an explicit change description if
  adapting the research later, rather than claiming modified files are originals.

The old web app, geocoding/discovery stack, Leaflet dependency and product-policy
files were not imported. The remaining openrouteservice adapter is a direct
benchmark dependency, not fairway's production routing provider.

## Findings and limits

The [extraction report](docs/contiguous-us-osm-extraction-rehearsal.md) records
16,166 logical courses in a 5.86 MiB JSON catalog. Most locations are approximate
geometry centers; those records are not verified public courses or validated
vehicle arrival points. The [generator contract](docs/golf-course-catalog-generator.md)
and [metadata audit](audit/osm-course-metadata/REPORT.md) explain those limits.

The [policy comparison](docs/national-shortlisting-policy-comparison.md) failed
its quality gates: even Policy E at 100 destinations included only 88.5% of
maximum-objective and 92.3% of total-objective reference winners. Larger-budget
code is preserved, but there is no retained successful run establishing a
production budget. Reference winners were drawn from broad sampled pools, not
an exhaustive national search.

The historical ranker uses minutes and its original tie breaks. It is retained
to reproduce those experiments; it must not replace fairway's current
millisecond scoring. Geographic anchors shortlist destinations, not exact road
meeting regions. No claim of current provider prices, quotas or availability
should be inferred from the historical reports.

## Recovering or rebuilding evidence

Generated evidence was ignored in the original repository and is absent here.
Before discarding a Windows checkout, look for these directories under `.local/`:

- `contiguous-us-osm-rehearsal/`: catalog and source completion markers.
- `national-shortlisting-benchmark/`: summary and the 29 cached matrix batches.
- `national-shortlisting-policy-comparison/`: comparison summary.
- `national-shortlisting-budget-sensitivity/`: later evidence/sensitivity output.

Use the hashes in the reports to identify matching artifacts. Some reports call
summaries “committed”; their named `.local/` paths were actually ignored. Without
those inputs, full replay is unavailable. Keep recovered data ignored and
separate from source; do not copy `.env`, credentials or bulk extracts here.

The benchmark's default mode replays caches. Its explicit `--route` option can
send origin/destination coordinates to openrouteservice, and the PowerShell
runner can download large extracts. Those are manual research operations:
verify current data/provider terms and an explicit request/storage budget first.
Do not enable network fallback in the cache-only policy or sensitivity tools.
Historical fixed extracts may no longer be available. A new snapshot requires
new hashes and fresh benchmark results, not claims of identical replay.

## Next steps

Recover matching evidence if convenient; otherwise plan a bounded fresh run.
Compare candidate recall, missed-winner travel-time penalty, matrix size and
cost before choosing a larger budget or new heuristics. Keep unknown access and
arrival quality visible. Do not integrate the old catalog or candidate policy
into the app merely because the tooling runs.

A separate useful UI idea from the predecessor is switching objectives using
one complete returned matrix in page memory. A future implementation should
reuse only the same origins, catalog, filter and provider observation, preserve
current scoring/tie rules, label the observation and offer explicit refresh.
This extraction does not implement that behavior.

## Licensing

Original software is covered by fairway's [MIT license](../../LICENSE).
OpenStreetMap-derived fixtures and any regenerated catalogs remain separately
subject to ODbL and OpenStreetMap attribution; see [NOTICE](../../NOTICE).
Provider-derived routing evidence has its own applicable terms. Historical
reports record experiments, not current service policies or licensing grants.
