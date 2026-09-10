# National shortlisting routed benchmark

## Result

The 2026-08-02 offline benchmark routed 15,000 course candidates across 26
public, deterministic origin groups and compared the existing two-anchor plus
global-safety-net shortlist family with broad routed reference pools. The run
used 59,500 origin-destination cells in 29 openrouteservice matrix requests.

The broad architecture remains plausible: geographic scoring should shortlist
and real journey times should rank. However, the tested production
configuration family is not reliable enough for catalog-backed runtime
integration. Winner inclusion plateaued at 84.6% for both ranking modes at the
nominal 80 and 100 configurations. Nominal 100 still missed four of 26
reference winners under each objective, including every lowest-total winner in
the two continental scenarios.

The best measured quality/cost point in the current family is nominal 80,
whose actual shortlist had a median of 47 courses and ranged from 28 to 170.
It is a useful correction baseline, not an acceptable deployment default.
No tested configuration established a minimum acceptable runtime shortlist.

The next slice should correct how the local and global sources consume a fixed
route budget, then rerun this benchmark from the existing cached matrices.
Catalog-backed runtime integration should not proceed before that correction
is measured.

## Fixed inputs

* Catalog:
  `.local/contiguous-us-osm-rehearsal/contiguous-us-catalog-first.json`
* Catalog size: 6,140,500 bytes and 16,166 logical courses.
* Catalog SHA-256:
  `ff0fd7efbb21e8e6edd4e99bc59acd7eb000272346e9ec7db4e961d352c3ad77`
* Catalog snapshot:
  `geofabrik-contiguous-us-2026-07-31-manifest-sha256-cee4a8888f4665bdb755340a0535eeb5050c5fd240120a94857281d6d52233f4`
* Scenario fixture: `benchmark/national-shortlisting-scenarios.json`.
* Scenario fixture SHA-256:
  `189e91154d5f18876e61cec783a85082127fb172e70b2c033ef2f3ab30bce6c1`.
* Ranking: unchanged `rankDestinationsForAllModes`, including its existing
  missing-cell exclusion and lexicographic tie-break behavior.

The corpus has 26 scenarios: three two-origin, one three-origin, 17
four-origin, three five-origin, and two six-origin groups. Labels identify
public civic buildings and all coordinates are checked in directly; the
benchmark does not geocode and contains no personal location.

The fixture tags overlapping categories for review. It includes 12 multi-city,
nine state-border, seven coast, seven regional, six metropolitan, six rural,
six mountain, six obstructed, six north-south, five sparse-course, five bridge,
five dispersed, four lake, four river, four east-west, four asymmetric, three
objective-disagreement, three two-origin, two suburban, two continental, and
one near-coincident scenario. The complete labels, coordinates, and categories
remain concise in the fixture rather than being duplicated here.

## Provider preflight and routing

The run used the repository's existing `OpenRouteServiceMatrix` adapter with:

* provider endpoint: `https://api.heigit.org/openrouteservice`;
* profile: `driving-car`;
* metric: duration only;
* `resolve_locations: false`;
* no dynamic routing arguments;
* a 180-second request timeout;
* sequential requests at least 1.6 seconds apart;
* a conservative 3,000-cell request cap.

The current [public API restrictions](https://openrouteservice.org/restrictions/)
allow 3,500 matrix pairs per request without dynamic arguments. The published
Standard plan lists 500 matrix requests per day and 40 per minute. The first
response confirmed a 500-request limit and 499 remaining; the lowest observed
remaining value after the run was 471. The run therefore consumed exactly 29
of the account's reported matrix-request quota. No request failed or retried.

The benchmark uses HeiGIT's current endpoint because the provider announced
that `api.openrouteservice.org` is deprecated and scheduled to shut off on
2026-08-24. The existing Fairway runtime default was deliberately not changed
in this offline slice. That configuration migration remains a separate
follow-up before future real-provider runtime work.

The provider's [terms](https://openrouteservice.org/terms-of-service/) require
attribution and license API results under CC BY 4.0. They do not state a cache
expiry for these results. Benchmark matrices are retained only as ignored,
local development evidence. They contain public fixture coordinates, catalog
course coordinates, durations, and provider metadata; no personal origins or
API key are written.

The public plan is listed as EUR 0. There is no authoritative per-request US
dollar price, so this report does not invent a dollar conversion or marginal
cost estimate.

### Volume and latency

| Measurement                                     |       Observed |
| ----------------------------------------------- | -------------: |
| Scenarios                                       |             26 |
| Routed candidate columns                        |         15,000 |
| Origin-destination cells                        |         59,500 |
| Provider requests                               |             29 |
| Direct provider latency, total                  | 30.090 seconds |
| Direct provider latency, median                 |  0.835 seconds |
| Direct provider latency, p90                    |  1.250 seconds |
| Direct provider latency, maximum                |  6.394 seconds |
| Complete live invocation after one cached probe | 51.138 seconds |
| Deterministic all-cache replay                  |  7.192 seconds |

Ordinary 500-candidate scenarios fit in one request. The three expanded
four-origin scenarios used `750 + 250` candidate batches, each capped at 3,000
cells. The expanded three-origin Lake Michigan scenario used one `3 x 1,000`
request. Across all scenarios, request shapes were:

| Candidate x cell shape         | Requests |
| ------------------------------ | -------: |
| 1,000 candidates / 3,000 cells |        1 |
| 750 / 3,000                    |        3 |
| 500 / 3,000                    |        2 |
| 500 / 2,500                    |        3 |
| 500 / 2,000                    |       14 |
| 500 / 1,000                    |        3 |
| 250 / 1,000                    |        3 |

## Shortlist configurations

All configurations use the existing shortlisting API and the same increasing
radius schedule from 1 km through 4,800 km. Counts scale as one small,
interpretable family rather than being tuned by scenario:

| Nominal target | Local target at each anchor | Global minimum-total | Global minimum-maximum |
| -------------: | --------------------------: | -------------------: | ---------------------: |
|             20 |                           6 |                    5 |                      5 |
|             30 |                           9 |                    8 |                      8 |
|             40 |                          12 |                   10 |                     10 |
|             60 |                          18 |                   15 |                     15 |
|             80 |                          24 |                   20 |                     20 |
|            100 |                          30 |                   25 |                     25 |

The API returns the union of both radius pools and both global pools. Radius
admission, overlap, and deduplication therefore make nominal target and actual
route count different. This is an important result rather than an adjustment
made after the fact.

| Nominal target | Actual minimum | Actual median | Actual mean | Actual maximum |
| -------------: | -------------: | ------------: | ----------: | -------------: |
|             20 |              6 |            14 |        17.6 |             37 |
|             30 |             10 |            19 |        24.2 |             53 |
|             40 |             14 |            26 |        30.0 |             68 |
|             60 |             21 |            40 |        49.8 |            151 |
|             80 |             28 |            47 |        58.5 |            170 |
|            100 |             32 |            60 |        73.8 |            170 |

The wide ranges, particularly the 151- and 170-course Lake Michigan pools,
show that the current parameter contract does not enforce a predictable route
budget.

## Routed reference pools

Each production shortlist is inserted into its scenario's reference pool so
every comparison selects columns from the same cached matrix. The remaining
reference capacity is filled by a balanced, deterministic union of:

1. generous expanding local pools around both existing anchors;
2. complete-catalog minimum-total Haversine order;
3. complete-catalog minimum-maximum Haversine order;
4. round-robin nearest-course coverage from every origin;
5. radial and distance-ring coverage around the minimum-maximum anchor.

This is not the current shortlisting algorithm with a larger `K`. The
origin-nearest and radial sources are independent protections against
asymmetry, geographic obstacles, and sparse supply. Across the 15,000 selected
columns, first admission came from the production union for 1,919, broad local
anchor pools for 1,401, minimum-total Haversine for 2,931, minimum-maximum
Haversine for 2,925, origin-nearest coverage for 2,914, and radial coverage for
2,910.

Twenty-two scenarios use 500 routed reference candidates. Puget Sound, Lake
Michigan, Colorado mountains, and continental corners use 1,000. Their nested
500, 750, and 1,000 prefixes are analyzed from the one 1,000-column matrix.

| Scenario and objective               | 500 to 750                                        | 750 to 1,000                                                 |
| ------------------------------------ | ------------------------------------------------- | ------------------------------------------------------------ |
| Puget Sound, both                    | winner, top 3, and top 10 stable                  | winner, top 3, and top 10 stable; no objective improvement   |
| Lake Michigan, minimum maximum       | winner changed; objective improved 1.010 min      | winner, top 3, and top 10 stable; no improvement             |
| Lake Michigan, minimum total         | winner, top 3, and top 10 stable                  | winner, top 3, and top 10 stable; no improvement             |
| Colorado mountains, both             | winner, top 3, and top 10 stable                  | winner, top 3, and top 10 stable; no improvement             |
| Continental corners, minimum maximum | winner changed; objective improved 15.933 min     | winner, top 3, and top 10 stable; no improvement             |
| Continental corners, minimum total   | winner stable; top 3 changed; top-10 overlap 8/10 | winner and top 3 stable; top-10 overlap 9/10; no improvement |

The adversarial winners and top threes stabilized by 750, and no winning
objective improved from 750 to 1,000. This establishes 750 as the observed
adversarial reference stabilization depth for this corpus.

It does not establish a production evaluation ceiling, a desired initial
request size, or proof of the national optimum. The practical production
evaluation ceiling remains unresolved until a corrected shortlist policy is
re-benchmarked for quality, latency, and provider cost. The 500-course ordinary
references were not independently expanded and remain less certain.

## Quality results

Regret distributions below include only scenarios whose shortlist missed the
reference winner. Maximum-objective regret is the difference in the winning
maximum journey. Total-objective regret is the difference in winning total
journey. All values are minutes.

### Minimize maximum driving time

| Nominal | Winner inclusion | Full top 3 | Avg. top-3 fraction | Full top 10 | Avg. top-10 fraction | Misses | Miss regret median / p90 / max |
| ------: | ---------------: | ---------: | ------------------: | ----------: | -------------------: | -----: | -----------------------------: |
|      20 |            69.2% |      50.0% |               65.4% |       11.5% |                54.6% |      8 |       17.588 / 68.323 / 68.323 |
|      30 |            76.9% |      61.5% |               73.1% |       19.2% |                64.2% |      6 |       17.826 / 68.323 / 68.323 |
|      40 |            80.8% |      65.4% |               78.2% |       42.3% |                71.5% |      5 |       25.204 / 68.323 / 68.323 |
|      60 |            84.6% |      76.9% |               84.6% |       61.5% |                78.5% |      4 |       14.106 / 37.524 / 37.524 |
|      80 |            84.6% |      80.8% |               85.9% |       61.5% |                81.2% |      4 |       14.106 / 37.524 / 37.524 |
|     100 |            84.6% |      80.8% |               87.2% |       73.1% |                83.5% |      4 |       14.106 / 37.524 / 37.524 |

### Minimize total driving time

| Nominal | Winner inclusion | Full top 3 | Avg. top-3 fraction | Full top 10 | Avg. top-10 fraction | Misses | Miss regret median / p90 / max |
| ------: | ---------------: | ---------: | ------------------: | ----------: | -------------------: | -----: | -----------------------------: |
|      20 |            69.2% |      53.8% |               64.1% |        7.7% |                54.2% |      8 |     10.053 / 106.573 / 106.573 |
|      30 |            73.1% |      53.8% |               67.9% |       23.1% |                63.8% |      7 |     10.053 / 106.573 / 106.573 |
|      40 |            76.9% |      61.5% |               74.4% |       30.8% |                68.1% |      6 |     10.053 / 106.573 / 106.573 |
|      60 |            80.8% |      65.4% |               78.2% |       50.0% |                76.9% |      5 |       14.627 / 47.072 / 47.072 |
|      80 |            84.6% |      73.1% |               82.1% |       61.5% |                80.0% |      4 |       14.627 / 47.072 / 47.072 |
|     100 |            84.6% |      73.1% |               82.1% |       69.2% |                82.3% |      4 |       12.804 / 20.999 / 20.999 |

Winner recall improves substantially through nominal 60 and, for total travel,
through nominal 80. Nominal 100 adds no winner recall. It improves maximum-mode
average top-three coverage by 1.3 points, full top-ten coverage by 11.6 points,
and total-mode full top-ten coverage by 7.7 points. That is useful depth but a
poor exchange for the larger, unpredictable route count when winner recall is
the gating concern.

## Failure review

At nominal 100, every missed reference winner is outside both production local
pools and both global pool limits. The issue is source coverage and budget
allocation, not ranking semantics or matrix reuse.

| Scenario              | Objective | Reference winner                | Actual shortlist | Cheap total / max rank | Anchor distance vs local radii (km) | Regret (min) |
| --------------------- | --------- | ------------------------------- | ---------------: | ---------------------: | ----------------------------------: | -----------: |
| Puget Sound           | maximum   | Belmor Park Golf & Country Club |               42 |                49 / 65 |                32.8, 34.1 vs 25, 25 |        9.950 |
| Lake Michigan         | maximum   | South Gleason Park Course       |              170 |              405 / 279 |             120.7, 122.0 vs 70, 100 |       37.524 |
| Lake Michigan         | total     | The Green                       |              170 |               57 / 200 |              84.4, 101.8 vs 70, 100 |       14.627 |
| Central north-south   | maximum   | Prairie Trails Golf Course      |              105 |               471 / 79 |             241.5, 226.1 vs 25, 100 |       14.106 |
| Central north-south   | total     | Brook Hollow Golf Club          |              105 |            283 / 2,345 |             726.7, 554.2 vs 25, 100 |        6.228 |
| Continental east-west | total     | Des Moines Golf & Country Club  |              120 |            108 / 1,523 |             514.2, 410.4 vs 25, 140 |       20.999 |
| Continental corners   | maximum   | Rock Port Golf and Country Club |              128 |              430 / 163 |            346.3, 301.2 vs 200, 140 |       15.933 |
| Continental corners   | total     | Sandy Meadows Golf Course       |              128 |              330 / 237 |            237.5, 256.3 vs 200, 140 |       12.804 |

The Lake Michigan maximum winner entered the broad reference only between 500
and 750. Its route advantage reflects the lake's road-network obstruction and
is poorly represented by the current cheap objectives. The continental-corners
maximum winner behaved similarly. The Green is an instructive allocation
failure: it was first in the generous broad local source and second in
origin-nearest coverage, but fell just outside both smaller production radii.

Puget Sound shows real disagreement between ranking modes: nominal 100 found
the minimum-total winner but missed the minimum-maximum winner. Continental
east-west did the reverse. The failure sets therefore cannot be repaired by
favoring only one canonical objective.

Strong nominal-20 cases included New York tri-state, Chesapeake Bay, both
St. Louis and Kansas City border groups, Four Corners, west Texas, Florida,
near-coincident Chicago, and the Dakotas. Each found both winners and both full
top threes despite actual pools from six to 24 candidates. Geographic density
alone did not predict success: sparse Four Corners and west Texas worked, while
Lake Michigan failed with 170 candidates.

The two continental scenarios recovered zero of two minimum-total winners even
at nominal 100; maximum-mode recovery was one of two. Continental groups do
require materially broader or better-diversified shortlisting than ordinary
groups under the current design.

Group-size results are too imbalanced to support a causal claim. All three
two-origin, all three five-origin, and both six-origin groups recovered both
winners at nominal 100. The 17 four-origin groups recovered 82.4% in each mode.
The only three-origin case was Lake Michigan and failed both modes. The
observed pattern follows geography and source coverage more clearly than origin
count.

## Duplicates and routing-coordinate quality

Exact normalized-name duplicates consumed 18 nominal-100 slots across ten
scenarios, with at most five in one scenario. Only one scenario had duplicate
name slots at nominal 20. None of the nominal-100 winner misses was displaced
near the cutoff by enough exact-name duplicates to explain the failure. Exact
names still do not prove duplicate identity; no catalog records are merged here.

The route matrices excluded 51 of 15,000 candidate columns (0.34%) because all
required cells for those destinations were null: 219 of 59,500 cells (0.37%).
Forty-nine excluded candidates used approximate geometry centers and two used
exact node coordinates. The reference pools contained 14,577 approximate and
423 exact coordinates, so this small sample does not show a materially higher
failure rate for approximate centers. No reference winner was excluded.

Representative unsnappable approximate centers included Windy Trails, Hat
Island Golf Club, Watermark Country Club, Ruby Hill Country Club, and several
military or island courses. The exact-node failures were one unnamed course and
Panther Valley Golf & Country Club. These are visible arrival-coordinate issues
worth retaining for the later destination-improvement slice, but they did not
drive shortlist recall in this benchmark.

## Conclusions and recommendations

1. **Initial quality/cost point:** nominal 80 is the best measured point in the
   current family. It reaches the maximum observed winner recall in both modes
   with a median 47 routed candidates. It is a benchmark baseline, not a safe
   runtime default.
2. **Minimum acceptable shortlist:** none of 20, 30, 40, 60, 80, or 100 is
   acceptable for runtime integration as currently constructed. The 84.6%
   winner plateau and continental failures are too material.
3. **Progressive tranche hypothesis:** a 20-candidate actual route tranche is a
   reasonable hypothesis for the next benchmark. The nominal 60-to-80 step
   produced the last winner-recall gain, while 80-to-100 only deepened top-ten
   coverage. This is not yet a runtime decision. A corrected API should make
   actual tranche size explicit and should test whether larger budgets extend
   smaller evaluated sets predictably.
4. **Reference stabilization depth:** the adversarial reference winners and top
   threes stabilized by 750 candidates, with no winning-objective improvement
   through 1,000. This is a property of the routed reference evidence, not a
   production evaluation ceiling. The practical production ceiling remains
   unresolved until the corrected policy is re-benchmarked for quality,
   latency, and provider cost. No tested production configuration at or below
   nominal 100 is sufficient.
5. **Design status:** two objective-specific anchors plus a global safety net
   remains a plausible architecture. The current radius/count mapping, pool
   composition, and budget allocation do not provide robust coverage or a
   predictable route budget. The benchmark does not yet establish which
   additional candidate sources belong in the final generic algorithm.
6. **Required correction:** before runtime integration, compare a small,
   scenario-independent family of exact-budget policies allocating candidates
   across local, minimum-total, minimum-maximum, origin-nearest, and radial
   sources. Do not tune by scenario or alter routed ranking semantics.
7. **Runtime integration:** do not proceed yet. Reuse the cached routed
   references to compare corrected policies, require materially better
   continental and obstructed-case recall, and verify that declared budgets
   equal actual routed candidate counts.
8. **Uncertainty:** the references are high-recall routed pools, not exhaustive
   national optima. Ordinary 500-course references were not expanded; one
   continental total top ten still changed by one course from 750 to 1,000;
   provider graphs and travel times can change; OSM course centers are mostly
   approximate; and the compact public corpus cannot represent every road or
   catalog irregularity.

## Reproduction and local artifacts

Preflight without provider access:

```powershell
npm run benchmark:national-shortlisting -- --preflight
```

Route only missing batches, then analyze:

```powershell
npm run benchmark:national-shortlisting -- --route
```

Replay entirely from cache:

```powershell
npm run benchmark:national-shortlisting
```

The checked replay used 29 cache hits, made zero provider requests, and emitted
a byte-identical `benchmark-summary.json` with SHA-256
`70e3c33bd796e3ca9eed98775abcac56eae21ad42f299e46d95caaa77cb6506c`.

Ignored `.local/national-shortlisting-benchmark/` contains 29 batch caches with
normalized matrices, raw provider JSON, quota headers, and measured latency;
`preflight.json`; `benchmark-summary.json`; and
`last-replay-observation.json`. The directory contains 32 files totaling about
10.37 MiB, including about 9.94 MiB of cache data. Interrupted runs reuse every
valid completed batch because each filename and payload are bound to a SHA-256
key over the catalog hash, scenario ID and public origins, ordered course IDs
and coordinates, provider endpoint, profile, metric, and relevant matrix
parameters.

Automated tests never enable `--route` and make no public network requests.
The benchmark does not change Fairway discovery, ranking, filtering, result
counts, browser behavior, or provider adapters.
