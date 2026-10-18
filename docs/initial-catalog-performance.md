# Initial catalog map performance

Measured October 18, 2026 against catalog981, complete JSON SHA-256
`68cceb68dd19e255a552a85c6dec0a8cf3904ef817b2aca92a401517fc7e7d65`.
Baseline software: `3afdb3a`; the subsequently merged CI-only changes do not affect
these browser assets. This is local benchmark evidence, not a hosted acceptance
or a promise of 200 ms on arbitrary devices or networks.

The original initial path fetched county/state geometry, then the manifest and
whole catalog, then decoded, parsed, validated and drew pins. Complete optional
observation validation was the largest CPU stage. The new path checks a generated
map/search index and draws the same facility pins first. Course views request the
complete catalog only when opened. Full course validation is unchanged.

## Conditions and results

Chromium 153.0.8010.12, headless Playwright, Chromium sandbox enabled, isolated
profiles on Omarchy, Intel i7-11800H / 16 GiB RAM. Desktop: unthrottled CPU,
1440×1000, loopback HTTP. Mobile simulation: the same host with 4× CPU slowdown,
10 Mbps download / 5 Mbps upload and 40 ms latency, 390×844, DPR 3. This is not a
measurement from a physical phone. No other test/build workload ran during the
final measurement. CPU scheduling and thermal variation remain uncontrolled.

Each condition has one cold navigation after clearing HTTP cache and three warm
reloads in the same context. Values below are cold samples and warm medians,
rounded to milliseconds. The mutable manifest is revalidated on every navigation.
Content-hashed bodies now use `force-cache` but still undergo length/hash checks.
Recorded resource timing confirms zero transferred index bytes on warm reloads;
the baseline's `no-cache` fetches retransferred the whole catalog in this server.
No persistent application cache or stored user state was introduced.

| First useful pins | Baseline | Initial map |
| --- | ---: | ---: |
| Desktop, cold | 1,107 ms | 177 ms |
| Desktop, warm median (3) | 1,028 ms | 95 ms |
| Mobile simulation, cold | 7,510 ms | 1,055 ms |
| Mobile simulation, warm median (3) | 6,808 ms | 355 ms |

The first-pins measurement ends after two animation frames following the verified
model's draw call; it is an upper bound on the first completed canvas paint, not a
browser-native paint metric. External map tiles and Photon are blocked in the
benchmark so their network/availability cannot masquerade as catalog time. The
application source, map renderer and public external-service behavior are intact.
Tile/background completion is outside this isolated milestone.

The first useful payload shrinks from 36,961,062 decoded / 3,924,451 gzip bytes to
1,029,823 decoded / 386,122 gzip bytes, including the existing state geometry.
The preceding 1,125,884 decoded / 313,402 gzip county/state fetch is removed from
the initial path. Published output still retains its existing URL.

The independent stage probe downloads the identical gzip representation through a
separate benchmark URL, then measures in-memory browser gzip decompression,
UTF-8 decoding, SHA-256, JSON parsing and the actual respective validator. These
are medians of four probes and are not additive explanations of first-pins time:
streaming, HTTP decompression and cache work overlap differently in the real path.
The separate download probe uses `no-cache`; its warm transfer behavior is recorded
in raw results rather than assumed to be a cache hit.

| Stage | Desktop full | Desktop map | Mobile full | Mobile map |
| --- | ---: | ---: | ---: | ---: |
| Response/header wait | 2.2 ms | 1.5 ms | 44.3 ms | 43.5 ms |
| Encoded body download | 78.9 ms | 7.7 ms | 3,423.8 ms | 338.3 ms |
| Gzip decode | 68.3 ms | 4.2 ms | 255.9 ms | 17.2 ms |
| UTF-8 decode | 70.8 ms | 1.8 ms | 245.8 ms | 7.2 ms |
| SHA-256 | 34.7 ms | 0.9 ms | 135.4 ms | 3.9 ms |
| JSON parse | 58.9 ms | 2.6 ms | 246.2 ms | 10.7 ms |
| Validation/model | 642.6 ms | 2.4 ms | 2,541.5 ms | 9.2 ms |

The 200 ms goal is achieved for these desktop samples. Constrained mobile remains
above it, especially cold. The full course-detail cost is deferred, not removed:
a first course view still downloads/parses/validates the complete catalog and can
take seconds on this constrained connection. There is no partial/fake course list
while loading. Pin drawing, facility/city/state search and the four catalog counts
are useful before that request. Counts remain 7,430 facilities, 4,682 courses,
4,640 on-map facilities and 2,790 not yet mapped.

## Integrity and behavior

SQLite remains the sole authoring authority. `build_pages.py` verifies the same
writer-supplied gzip/raw release before generating the map from those exact bytes.
No generated release input, course fact, schema, routing provider or admission
logic changes. The new index is content-hashed, bounded to 4 MiB, deterministic and
bound to the complete catalog SHA, revision, release key and counts in one manifest.

The page pins that manifest for later detail requests. A deploy between requests
cannot substitute a newer manifest or combine releases. A missing immutable asset
fails explicitly; there is no cross-version retry. Cached corrupt bytes, wrong
release identities, malformed/oversized/truncated/stalled map responses and aborted
loads fail closed. A failed detail transfer leaves the map/search available and
can be retried explicitly against the same identity. The latest pending selection
wins; no course records appear before complete validation.
Pin clicks fit their already verified index coordinates immediately. Detail
completion does not fit again, and dismissing Courses cancels its pending
selection even if Plan a Round remains open.
The drawer opens before the synchronous initial fit so padding uses its real
dimensions. A subsequent pan or zoom cancels pending selection and follows the
new viewport. Initial-map failure offers page reload; only detail failure offers
the in-page retry.

Regression coverage exercises these paths and exact projection of every real
facility, including unmapped and address-estimate points. Existing complete
relationship, optional-scope, null, course-filter and planning checks are retained.
Actual desktop/mobile browser checks covered deferred Bethpage selection, all four
counts, course popups, state geometry search, interruption/retry, filter changes
while details load, no horizontal overflow and no script errors. Screenshots and
raw browser-flow receipts are local supporting evidence in the task workspace.
The Plan-open/Courses-dismissed case is exercised by the actual handler regression
and an actual browser flow. Disposable mutation probes also confirm that removing
checksum verification, manifest pinning, map revision checks or that dismissal
guard causes the corresponding regression to fail.
Browser regressions also confirm visible fitted points at 390 px and 900 px,
preserved pans during detail loading, no stale popup/course replay, and honest
initial-map failure recovery.

## Reproduce

Use the normal Python/Node versions and locked environment in `AGENTS.md`. Build
baseline and changed commits into different empty directories. Playwright is a
benchmark-only external tool; install/use it in a disposable environment, not an
application dependency. Choose its installed Chromium executable. The runner
requires the normal approved browser execution environment and keeps Chromium's
sandbox enabled; do not retry it inside a sandbox that forbids its sockets.

```sh
python scripts/build_pages.py --output /tmp/fairway-after --commit COMMIT
python scripts/serve_catalog_benchmark.py /tmp/fairway-after --port 8768
# In another terminal, with no other test/build work running:
PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs \
CHROMIUM_PATH=/path/to/chromium \
node scripts/benchmark_initial_catalog.mjs http://127.0.0.1:8768/ /tmp/after.json
```

Run the same server and runner on the baseline output. Both the separate stages
and each first-navigation resource's encoded/decoded/transfer sizes and timing are
recorded in JSON. Stop the two local servers after measurement. The benchmark
starts no routing server, changes no desktop settings and sends no origins.

## Deployment cache acceptance

The merged `1bdf05a` deployment passed its complete main CI and Pages publication.
Hosted catalog validation matched all 7,430 map-index rows against the complete
catalog981 payload, including its original checksum and relationship validation.
Fresh and same-version warm desktop/touch-mobile browsing passed counts, actual
mapped-pin selection, local search, deferred details and controlled error checks.
These hosted observations use the real network and live map tiles, without the
benchmark's CPU/network simulation; they are separate from the timing table above.

A pre-deployment cached browser did expose an adoption problem: normal reload
could retain unversioned `app.js` and `public-catalog.mjs` for the hosted
`max-age=600` period, then fetch the new manifest through the old complete-catalog
startup path. A controlled old-to-new server swap with the same cache policy
reproduced zero transferred script bytes, old script checksums and no initial-map
request. Catalog facts remained consistent; the new UI was not adopted.

The follow-up builder emits content-hashed JS/module/CSS copies and rewrites their
complete static import graph plus HTML references. Hashes include rewritten
dependency names, so a changed leaf invalidates every affected importer. Unchanged
assets retain their names; catalog-only changes need no UI redownload. Existing
source URLs remain aliases for compatibility, while normal pages use the hashed
graph. The mapping is recorded in deployment metadata. The catalog/index payloads,
their checksums and native schema are unchanged. Next hosted deployment acceptance
must still verify normal reload from the previously cached page.
