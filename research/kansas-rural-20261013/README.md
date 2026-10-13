# Kansas rural public-golf additions, October 13, 2026

Three net-new public facilities and three unnamed physical nine-hole courses are proposed against `3fe8f486cce87ec1e38524c7e49c732ed368d05e` (7,176 facilities). No existing facility facts, property dots, arrivals, county assignments, ranking selection or UI are changed. After application: 7,179 facilities; mapped count remains 4,428.

| Facility | Physical course | Published address | Primary admission evidence |
| --- | --- | --- | --- |
| Caney Golf Club | One unnamed nine-hole course | 1567 County Road 2000, Caney, Kansas 67333 | [Operator nonmember play](https://caneygolf.com/stay-%26-play); [physical statistics](https://caneygolf.com/course-statistics) |
| Ness County Golf Club | One unnamed nine-hole course | Null; only Highway 283 about four miles north of Ness City is stated | [Official Ness County Chamber recreation page](https://www.nesscountychamber.com/recreation.html), expressly public nine-hole golf |
| Cimarron Golf Club | One unnamed nine-hole course | 812 Golf Course Rd., Cimarron, KS 67835 | [Operator nonmember rates](https://cimarrongolfclub.com/fees/); [official state physical inventory](https://www.travelks.com/listing/cimarron-golf-club/6233/) |

Caney's [homepage](https://caneygolf.com/) closes golf to the public on Tuesdays and allows event exceptions. This specific qualification is retained despite a second page saying daily opening. Its eighteen-hole route uses two tee loops on nine physical holes. County and map/arrival coordinates are null throughout. Page publication dates are unknown; October 13 is the observation date, not a guarantee of current operation.

`delta.json` is portable. Persisted facility/course UUIDs must be preserved. Sources and notes use batch-specific identifiers to avoid collisions with parallel workers. `apply_delta.py` prepares a schema-validated candidate document, preserves all existing records, deduplicates source URLs, and refuses exact name/address/ID collisions. The parent must review similar names/aliases and the provenance before importing into its newer baseline.

```sh
python research/kansas-rural-20261013/apply_delta.py --output /tmp/reviewed-kansas-catalog.json
# Review the proposal and use the expected_current_sha256 printed above.
python scripts/catalog.py import --proposal /tmp/reviewed-kansas-catalog.json --expected-sha256 <printed-current-sha256>
python scripts/publish_research_map.py
```

Both successfully materialized historical archives were screened. Relevant control/hold/stop/ledger/scope and embedded Kansas source notes were reviewed before collection. The follow-up complete host/alias occurrence scan and raw source captures remain outside the repository in the private handoff directory. `source-review.json` retains concise decisions, qualifications, the exact new stop, and archive checksums. `capture-manifest.json` records direct-read URLs, start/completion times, statuses and response SHA-256 hashes. No raw page prose, source imagery, scorecard artwork or third-party coordinates is published.

Current robots and linked policies were inspected; applicable Kansas Tourism two-second and Crazy Horse three-second delays were honored from completion to next request start. Every source read was bounded, with no automatic redirect following. No observed direct-request pacing exceptions. No new paid services, credentials, accounts, checkout actions, deployed changes or pushes.

No explicit open reuse license was located for these admitted operator/Chamber/state facts. Website copyright is not relicensed as MIT. Only independently written minimal fact summaries and necessary source citations are proposed. Kansas Tourism's current linked conditions contain no identified restriction on this scoped bare-fact use; account/payment terms and reCAPTCHA terms retain their actual scopes.

The automatic approval reviewer rejected Belleville homepage collection after its robots endpoint returned 404, because missing source controls were not clearance. No homepage request or substitute alias/cache intake followed. That source stays stopped. All prior MCG, Classic5, Pennsylvania redirect-batch, PGA, canceled LeRoy, and applicable Kansas source stops remain respected.

Council Grove and Cimarron Valley remain unconfirmed for ordinary nonmember admission; no blanket publication hold is inferred. Ellis has current independent state public/nine-hole evidence but matches an unlinked initial historical row absent from the active catalog, so it is withheld from the net-new count pending identity/restoration review. Other excluded discoveries are recorded in `source-review.json`.

Next useful Kansas work: bounded review of the unlinked Ellis, Baxter Springs and Wedgewood historical identities, using existing historical artifacts before any fresh source collection. These are restoration questions, not an assured new-facility cohort. For fresh expansion, another under-covered state is likely more fruitful than repeatedly querying these extensively reviewed Kansas access ambiguities.

Validation completed: catalog validation/publication; 226 Python tests; three JavaScript test files; app/Leaflet syntax; Ruff checks and format; source/wheel packaging; and existing Chicago snapshot validation. All 7,176 existing facility objects and research records, county checklist and ranking metadata are unchanged. The ranking projection SHA-256 remains `c017b830b398d9476a0791882c7e193bb691476eab1a8f43359892eaf9ff3180`. Exact results and source-pacing assertions are in `validation.json`.

Replay resolves the evidence commit locally with Git and uses its actual committer timestamp for committed_at; reported_at stays the invocation/report time. The batch is prepended to recent reports and records zero existing-facility updates. Import the verified component bundle or pass another actual reviewed evidence commit before replay. Regression tests cover all three public-history contracts, including the exported projection.
