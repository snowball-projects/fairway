# Local SQLite preparation DTO integration

The existing fairway Plan a Round and Courses panes now consume the API owner's frozen preparation DTO sequence from commit `e8d66be278af1425c15d972bf2c2563486d18c17`. Fixture SHA256 is `3ca7b31110b3b8b7cae88cabbfe60263ccf9a339481ffc4044db1a69c39d2dcd`. This replaces the earlier browser mock's planning selection, matrix cache and score calculation. The browser renders server-supplied outcomes, retains complete course identities and preserves canonical arrivals separately from qualified routing targets.

## Current behavior

Committed address resolution is a literal lookup of the two supplied labels, with no typing work or geocoder. First and second origin pins fit immediately. The first fixture supplies four separate course rows sharing two destinations. Adding the second origin clears comparable group scores until the supplied vectors complete. Two matrix cells for the first origin and two for the second serve all four aliases. Two facility map identities appear for the four course rows.

The distinct modo area stage remains visible as the supplied qualified Point. It has no claimed optimization extent or radius. Nearby course radius and area geometry remain separate. The second fixture completes its origin matrix before the area; rankings remain provisional until the area stage finishes. This ordering is supplied by the API fixture, not hard-coded as a universal provider guarantee.

The large-pool replay displays all 100 synthetic courses with 24 scored and 76 pending, then all 100 scored from the supplied completed snapshot. It does not route course25 onward in the browser. The API-owned fixture builder and controller produced these states; replaying them does not demonstrate real-provider throughput or a native full-pool continuation bridge.

Name, longest, combined and per-origin display sorts use the same completed vectors without changing the area objective. Unnamed rows show facility name prominently plus Course name not recorded; the underlying course name stays null and distinct c-UUIDs remain. Qualified nonmember eligibility is separate from nullable bookability and unknown availability. No metadata, course identity or booking fact is inferred. Ordinary browsing and Search This Area hide times and start no preparation.

Only the exact supplied maximum/20-mile/nonmember/all-round fixture requests are available. Other radius, objective, access or origin combinations produce a visible fixture-scope error instead of reusing unrelated values. Controls are retained to exercise invalidation and the future transport boundary. The source's ordinary map/browse still uses the frozen static baseline; production SQLite read cutover is separate. Generated DTO JSON is read-only test transport, not an editable catalog or SQLite browser engine.

## Consumer boundaries

`preparation-dto.mjs` validates request hash and ordered origins, generation, catalog revision and snapshot_sequence. A page collection rejects changed revisions, changed snapshot tokens, duplicate course IDs and inconsistent requests. Counts alone cannot identify a snapshot. Complete pools replace the current display only after every page has arrived. No course25 display cap exists.

Row validation preserves null names and canonical arrivals. Facility estimates require explicit scope and qualification and cannot become course arrivals. Integer millisecond vectors must match all current origins before comparable scores are accepted; supplied sums and maxima are checked. Missing, unreachable, unavailable destinations and errors retain distinct states. Known zero is valid.

`preparation-session.mjs` manages browser display generations with one active local fixture replay and one coalesced latest request. Stale frames do not paint newer inputs. Its adapter is explicitly fixture-only. Terminal evidence has basis literal-fixture-completion and native_admission_released=false. No browser event, cancellation, stale result or timer unlocks a native reservation. Uncertain completion blocks replacement. A real worker/admission bridge is not bound here.

`sqlite-preparation-adapter.mjs` replays exact frozen frames and snapshots. It has no provider, socket, database, fetch, geocoding, timing inference or score generator. The first-origin and group demonstration uses supplied frames; the large demonstration replays supplied 24/100 snapshots. Any wait is an artificial UI test delay, not a measured compute span. The 5 through 10 second target remains unmeasured.

## Review corrections and verification

The earlier frozen package remains Library `libfile_d75ad5a1b17c8191902f67f13c18db2a` version0, SHA256 `09b0c590f3bec89c3ffb203e26c929980f31c672854490f2d97a34a9f30ebba8`. Independent review found four P2 defects, now independently retested with no findings in separate correction package `libfile_b89ff7dc58888191a3b2c2a62a91163a` version0, SHA256 `9c0faadc44554afb1a2d91a9a42fb02b7931491ba736a90067773821d939ad05`.

Those corrections keep empty/blocked planning empty, protect both admitted mock windows, bind address lookup dedup/finalization to live controllers, and show terminal error/hold and retry instructions in the visible Courses sheet. The corrected legacy mock remains as a reviewed predecessor and regression fixture, not the new planning runtime. Its cache is not reused by the DTO consumer.

Run the current consumer checks with Node22 or newer:

```
node tests/preparation-api-fixture.test.mjs
node tests/preparation-dto.test.mjs
node tests/preparation-session.test.mjs
node --test tests/catalog-ui.test.mjs tests/research-map.test.mjs tests/research-refresh.test.mjs
```

The new `tests/preparation-browser.mjs` exercises the actual existing UI with the validated fixture adapter, blocks every non-loopback application request, and uses a virtual clock. It checks origin commits, complete-vector states, aliases, map dedup, point-area visibility, unsupported input invalidation,100-course display and mobile focus/overflow. The previous `plan-a-round-browser.mjs` applies to the frozen correction package's earlier mock, not this new adapter. No real routing, geocoding, Spark, publishing, push or deployment is included.
