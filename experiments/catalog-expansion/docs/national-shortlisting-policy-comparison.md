# Exact-budget national shortlisting policy comparison

## Result

The 2026-08-03 offline comparison evaluated five deterministic policies at
exact route budgets of 40, 60, 80, and 100 across the same 26 national
shortlisting scenarios and both canonical ranking modes. It selected columns
only from the 29 already-cached routed matrix batches and made zero public
network requests.

No tested policy met all provisional acceptance gates. Exact budgeting is
solved by the prototype, but shortlist quality is not. The strongest combined
result was Policy E at 100 candidates: 88.5% reference-winner inclusion for
minimum maximum journey and 92.3% for minimum total journey. Its remaining
maximum-mode regret reached 20.681 minutes and its remaining total-mode regret
reached 11.768 minutes per origin, both above their gates.

Policy E at 80 is the smallest balanced diagnostic point: it included 88.5%
of winners in both modes. Moving to 100 recovered one additional
minimum-total winner and raised that mode to 92.3%, but did not improve
minimum-maximum winner inclusion. Neither budget is suitable for runtime
integration.

The two-anchor plus global-safety-net architecture remains directionally
useful, and origin-relative and radial sources each recovered winners the
four-source baseline missed. Allocation changes alone cannot repair the
remaining failures: several missed winners rank below 100 in none of the
tested source orders. The next slice should first test whether larger exact
route budgets recover the remaining winners while remaining within one
practical matrix request. New directional or road-aware candidate sources
should be considered only if larger budgets remain insufficient or impose
unacceptable latency or provider load.

## Fixed inputs and cache integrity

| Input | SHA-256 |
| --- | --- |
| National catalog | `ff0fd7efbb21e8e6edd4e99bc59acd7eb000272346e9ec7db4e961d352c3ad77` |
| Scenario fixture | `189e91154d5f18876e61cec783a85082127fb172e70b2c033ef2f3ab30bce6c1` |
| Committed benchmark summary | `70e3c33bd796e3ca9eed98775abcac56eae21ad42f299e46d95caaa77cb6506c` |
| Exact-budget comparison summary | `a80742a2dfeb808dfcecbd01451490478b0d03ee65f552da177caa3feae62bc7` |

The catalog contains 16,166 eligible courses. The corpus contains 26
scenarios and 104 origins in total: three two-origin, one three-origin, 17
four-origin, three five-origin, and two six-origin groups. All 520
scenario-policy-budget shortlists found every selected ID in the corresponding
cached routed matrix. The comparison has no routing mode and cannot backfill a
missing matrix column through a provider request.

Two consecutive comparison runs emitted byte-identical
`comparison-summary.json` output. Generated summaries, detailed candidate
provenance, scenario observations, and run timing remain ignored under
`.local/national-shortlisting-policy-comparison/`.

## Existing and exact-budget mechanics

The current runtime-independent shortlisting prototype expands fixed radii
around both anchors until each nominal local target is reached. Every course
inside the final radius is admitted, including radius ties, so a local pool
can exceed its target. Local entries inherit stable catalog-ID order. Each
global pool is sorted by its Haversine objective, the other objective, and
stable ID, then truncated. The four pools are deduplicated by ID and the final
union is sorted by ID. There is no final exact-budget truncation or backfill.

The comparison keeps the same geographic concepts but gives each one a full,
deterministic order:

* `LT`: distance from the minimum-total anchor, then total, maximum, and ID;
* `LM`: distance from the minimum-maximum anchor, then maximum, total, and ID;
* `GT`: global total Haversine, then maximum and ID;
* `GM`: global maximum Haversine, then total and ID;
* `O`: round-robin nearest-course coverage across canonically ordered origins;
* `R`: the benchmark's deterministic 30-degree sector and logarithmic-ring
  coverage around the minimum-maximum anchor.

Every policy assigns an integer quota to each 20-candidate tranche. New quota
prefixes are admitted in the listed source order, duplicate IDs are retained
as provenance but consume no final slot, and a fixed source cycle backfills
the unused capacity. Source-order ties and all within-source ties end in stable
candidate ID. Each larger budget extends the prior sequence rather than
rebuilding it.

## Policies and quotas

The quota columns use `LT/LM/GT/GM/O/R`. Every row sums exactly to `K` before
deduplication. Overflow orders are fixed for every scenario and budget.

| Policy | Purpose | Overflow order |
| --- | --- | --- |
| A | Exact-budget current four-source design | LT, LM, GT, GM |
| B | Deeper balanced global objectives | GT, GM, LT, LM |
| C | Four-source balance plus origin coverage | O, GT, GM, LT, LM |
| D | Four-source balance plus radial coverage | R, GT, GM, LT, LM |
| E | Both anchors, both globals, origin, and radial coverage | O, R, GT, GM, LT, LM |

| Policy | K | LT | LM | GT | GM | O | R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 40 | 10 | 10 | 10 | 10 | 0 | 0 |
| A | 60 | 15 | 15 | 15 | 15 | 0 | 0 |
| A | 80 | 20 | 20 | 20 | 20 | 0 | 0 |
| A | 100 | 25 | 25 | 25 | 25 | 0 | 0 |
| B | 40 | 4 | 4 | 16 | 16 | 0 | 0 |
| B | 60 | 6 | 6 | 24 | 24 | 0 | 0 |
| B | 80 | 8 | 8 | 32 | 32 | 0 | 0 |
| B | 100 | 10 | 10 | 40 | 40 | 0 | 0 |
| C | 40 | 4 | 4 | 8 | 8 | 16 | 0 |
| C | 60 | 6 | 6 | 12 | 12 | 24 | 0 |
| C | 80 | 8 | 8 | 16 | 16 | 32 | 0 |
| C | 100 | 10 | 10 | 20 | 20 | 40 | 0 |
| D | 40 | 4 | 4 | 8 | 8 | 0 | 16 |
| D | 60 | 6 | 6 | 12 | 12 | 0 | 24 |
| D | 80 | 8 | 8 | 16 | 16 | 0 | 32 |
| D | 100 | 10 | 10 | 20 | 20 | 0 | 40 |
| E | 40 | 2 | 2 | 8 | 8 | 10 | 10 |
| E | 60 | 3 | 3 | 12 | 12 | 15 | 15 |
| E | 80 | 4 | 4 | 16 | 16 | 20 | 20 |
| E | 100 | 5 | 5 | 20 | 20 | 25 | 25 |

## Exact-budget and source-allocation results

Every actual-size minimum, median, and maximum equals `K`. The contribution
column reports first-admission source counts after ID deduplication, aggregated
over 26 scenarios in `LT/LM/GT/GM/O/R` order. Unused quota, duplicate slots
avoided, and backfill count are equal by construction; the final column shows
their per-scenario median/p90/maximum.

| Policy | K | Actual min/median/max | Contributions after deduplication | Unused = backfill = duplicates median/p90/max |
| --- | ---: | ---: | ---: | ---: |
| A | 40 | 40/40/40 | 330/273/217/220/0/0 | 23/28/30 |
| A | 60 | 60/60/60 | 463/402/350/345/0/0 | 34/43/45 |
| A | 80 | 80/80/80 | 593/534/481/472/0/0 | 48/56/60 |
| A | 100 | 100/100/100 | 724/663/613/600/0/0 | 59/72/75 |
| B | 40 | 40/40/40 | 187/160/378/315/0/0 | 17/23/24 |
| B | 60 | 60/60/60 | 292/261/531/476/0/0 | 26/34/36 |
| B | 80 | 80/80/80 | 407/375/674/624/0/0 | 37/45/48 |
| B | 100 | 100/100/100 | 529/494/815/762/0/0 | 49/57/60 |
| C | 40 | 40/40/40 | 147/123/193/183/394/0 | 14/23/24 |
| C | 60 | 60/60/60 | 228/198/298/277/559/0 | 24/35/36 |
| C | 80 | 80/80/80 | 313/282/399/376/710/0 | 31/47/48 |
| C | 100 | 100/100/100 | 405/371/500/477/847/0 | 40/59/60 |
| D | 40 | 40/40/40 | 160/130/199/184/0/367 | 17/20/23 |
| D | 60 | 60/60/60 | 239/206/293/267/0/555 | 26/30/34 |
| D | 80 | 80/80/80 | 315/281/379/349/0/756 | 34/39/42 |
| D | 100 | 100/100/100 | 392/357/462/429/0/960 | 41/49/50 |
| E | 40 | 40/40/40 | 101/87/197/171/272/212 | 15/23/25 |
| E | 60 | 60/60/60 | 168/151/284/250/383/324 | 23/35/38 |
| E | 80 | 80/80/80 | 239/221/368/331/492/429 | 31/46/48 |
| E | 100 | 100/100/100 | 312/292/452/410/596/538 | 38/57/60 |

The detailed ignored summary also retains unused-quota and backfill counts by
source, candidate-level source ranks, first-admission provenance, and the
legitimate shortfall reason field. No corpus scenario had a supply shortfall.

## Quality results

Percentages remain separate by ranking mode. Regret is in minutes. The
all-scenario regret median is zero for every row because a majority of
shortlists include the reference winner; `all p90/max` preserves the remaining
distribution. Miss-regret columns include only winner misses, matching the
previous benchmark. Minimum-total rows also show miss regret divided by the
scenario's origin count.

### Minimize maximum journey

| Policy | K | Winner | Full 3 | Avg 3 | Full 10 | Avg 10 | All regret p90/max | Miss regret median/p90/max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 40 | 76.9% | 76.9% | 80.8% | 57.7% | 75.4% | 14.106/55.045 | 10.641/55.045/55.045 |
| A | 60 | 80.8% | 80.8% | 85.9% | 65.4% | 83.5% | 14.106/42.964 | 14.106/42.964/42.964 |
| A | 80 | 84.6% | 84.6% | 89.7% | 76.9% | 88.1% | 14.106/37.524 | 14.106/37.524/37.524 |
| A | 100 | 84.6% | 84.6% | 89.7% | 80.8% | 88.8% | 14.106/32.005 | 14.106/32.005/32.005 |
| B | 40 | 76.9% | 76.9% | 79.5% | 53.8% | 74.2% | 26.855/55.045 | 9.950/55.045/55.045 |
| B | 60 | 80.8% | 76.9% | 83.3% | 65.4% | 82.7% | 17.826/37.524 | 17.826/37.524/37.524 |
| B | 80 | 84.6% | 84.6% | 89.7% | 73.1% | 87.7% | 14.106/37.524 | 14.106/37.524/37.524 |
| B | 100 | 84.6% | 84.6% | 89.7% | 80.8% | 88.8% | 14.106/32.005 | 14.106/32.005/32.005 |
| C | 40 | 76.9% | 65.4% | 73.1% | 42.3% | 67.3% | 26.269/27.872 | 21.516/27.872/27.872 |
| C | 60 | 76.9% | 76.9% | 79.5% | 57.7% | 75.8% | 14.726/27.872 | 10.641/27.872/27.872 |
| C | 80 | 84.6% | 80.8% | 87.2% | 65.4% | 83.1% | 14.106/25.204 | 14.106/25.204/25.204 |
| C | 100 | 84.6% | 84.6% | 88.5% | 73.1% | 86.2% | 14.106/21.744 | 14.106/21.744/21.744 |
| D | 40 | 84.6% | 69.2% | 76.9% | 42.3% | 72.7% | 17.826/44.644 | 17.826/44.644/44.644 |
| D | 60 | 84.6% | 76.9% | 83.3% | 61.5% | 80.0% | 14.106/44.644 | 14.106/44.644/44.644 |
| D | 80 | 88.5% | 84.6% | 91.0% | 69.2% | 86.2% | 14.106/42.964 | 15.933/42.964/42.964 |
| D | 100 | 88.5% | 84.6% | 91.0% | 69.2% | 87.3% | 14.106/37.524 | 15.933/37.524/37.524 |
| E | 40 | 84.6% | 65.4% | 75.6% | 42.3% | 67.7% | 17.826/44.022 | 17.826/44.022/44.022 |
| E | 60 | 84.6% | 76.9% | 80.8% | 53.8% | 76.5% | 17.826/22.870 | 17.826/22.870/22.870 |
| E | 80 | 88.5% | 80.8% | 88.5% | 61.5% | 84.2% | 14.106/21.744 | 20.681/21.744/21.744 |
| E | 100 | 88.5% | 84.6% | 91.0% | 73.1% | 87.3% | 14.106/20.681 | 15.933/20.681/20.681 |

### Minimize total journey

| Policy | K | Winner | Full 3 | Avg 3 | Full 10 | Avg 10 | All regret p90/max | Miss regret median/p90/max | Miss regret/origin median/p90/max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 40 | 80.8% | 69.2% | 79.5% | 46.2% | 75.0% | 34.345/73.095 | 34.345/73.095/73.095 | 8.586/24.365/24.365 |
| A | 60 | 84.6% | 73.1% | 80.8% | 61.5% | 79.6% | 34.345/47.072 | 34.345/47.072/47.072 | 8.586/13.988/13.988 |
| A | 80 | 84.6% | 76.9% | 82.1% | 69.2% | 81.9% | 21.801/47.072 | 21.801/47.072/47.072 | 6.939/11.768/11.768 |
| A | 100 | 84.6% | 76.9% | 82.1% | 76.9% | 83.1% | 14.627/43.321 | 14.627/43.321/43.321 | 4.876/10.830/10.830 |
| B | 40 | 80.8% | 69.2% | 79.5% | 46.2% | 75.4% | 34.345/73.095 | 34.345/73.095/73.095 | 8.586/24.365/24.365 |
| B | 60 | 84.6% | 73.1% | 80.8% | 65.4% | 80.8% | 27.758/43.321 | 27.758/43.321/43.321 | 6.939/13.988/13.988 |
| B | 80 | 84.6% | 76.9% | 82.1% | 69.2% | 81.9% | 21.801/43.321 | 21.801/43.321/43.321 | 6.396/10.830/10.830 |
| B | 100 | 84.6% | 76.9% | 82.1% | 73.1% | 82.7% | 14.627/41.302 | 14.627/41.302/41.302 | 4.734/10.326/10.326 |
| C | 40 | 80.8% | 73.1% | 80.8% | 38.5% | 72.3% | 10.658/106.573 | 10.658/106.573/106.573 | 2.665/26.643/26.643 |
| C | 60 | 88.5% | 76.9% | 85.9% | 53.8% | 80.8% | 3.980/47.072 | 34.345/47.072/47.072 | 8.586/11.768/11.768 |
| C | 80 | 92.3% | 80.8% | 87.2% | 65.4% | 85.0% | 0/47.072 | 34.345/47.072/47.072 | 8.586/11.768/11.768 |
| C | 100 | 92.3% | 80.8% | 87.2% | 69.2% | 86.2% | 0/47.072 | 27.758/47.072/47.072 | 6.939/11.768/11.768 |
| D | 40 | 76.9% | 69.2% | 78.2% | 38.5% | 71.5% | 20.999/49.286 | 13.495/49.286/49.286 | 3.374/13.988/13.988 |
| D | 60 | 80.8% | 69.2% | 80.8% | 57.7% | 78.8% | 7.633/47.072 | 7.633/47.072/47.072 | 1.908/13.988/13.988 |
| D | 80 | 84.6% | 73.1% | 82.1% | 61.5% | 80.8% | 7.633/47.072 | 7.633/47.072/47.072 | 1.908/13.988/13.988 |
| D | 100 | 84.6% | 76.9% | 83.3% | 69.2% | 81.9% | 7.633/43.321 | 7.633/43.321/43.321 | 1.908/10.990/10.990 |
| E | 40 | 80.8% | 69.2% | 78.2% | 30.8% | 70.4% | 10.658/106.307 | 10.658/106.307/106.307 | 2.665/26.577/26.577 |
| E | 60 | 84.6% | 76.9% | 84.6% | 53.8% | 79.2% | 7.633/47.072 | 7.633/47.072/47.072 | 1.908/11.768/11.768 |
| E | 80 | 88.5% | 80.8% | 87.2% | 65.4% | 83.5% | 3.495/47.072 | 7.633/47.072/47.072 | 1.908/11.768/11.768 |
| E | 100 | 92.3% | 80.8% | 88.5% | 69.2% | 85.4% | 0/47.072 | 3.495/47.072/47.072 | 0.874/11.768/11.768 |

## Acceptance gates

No row reaches the required 95% winner inclusion in both modes. The
100-candidate rows show why raising the budget within these source orders does
not solve the problem.

| Policy | Maximum winner | Total winner | Maximum miss regret max | Total miss regret/origin max | Exact budget | All gates |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| A100 | 84.6% | 84.6% | 32.005 | 10.830 | yes | no |
| B100 | 84.6% | 84.6% | 32.005 | 10.326 | yes | no |
| C100 | 84.6% | 92.3% | 21.744 | 11.768 | yes | no |
| D100 | 88.5% | 84.6% | 37.524 | 10.990 | yes | no |
| E100 | 88.5% | 92.3% | 20.681 | 11.768 | yes | no |

The provisional gates remain unchanged. There is no selected deployment
configuration.

## Failure analysis and recoveries

At E100, Puget Sound includes both reference winners. Origin coverage recovers
the Lake Michigan and central north-south minimum-total winners that A100
misses. Radial coverage recovers the continental east-west minimum-maximum
winner. No winner-level degradation appears in the remaining ordinary
metropolitan and regional scenarios; all E100 misses are among the named
obstructed or continental focus cases.

The source-rank column below is `LT/LM/GT/GM/O/R`. These are complete-catalog
ranks under the tested deterministic orders, not routed ranks.

| Scenario | Mode | Missed winner | E100 winner | Regret | Per origin | Source ranks | Cause |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| Lake Michigan | maximum | South Gleason Park Course | Southshore Golf Learning Center | 20.681 | n/a | 412/355/405/279/478/809 | global-objective depth |
| Central north-south | maximum | Prairie Trails Golf Course | Twin Hills Golf & Country Club | 14.106 | n/a | 308/288/471/79/1202/1049 | quota competition at GM rank 79 |
| Continental corners | maximum | Rock Port Golf and Country Club | Junction City Golf Course | 15.933 | n/a | 299/294/430/163/11743/1643 | global-objective depth |
| Continental east-west | total | Des Moines Golf & Country Club | 5 by 80 Golf and Country Club | 3.495 | 0.874 | 3333/550/108/1523/7576/614 | global-objective depth |
| Continental corners | total | Sandy Meadows Golf Course | Syracuse Country Club | 47.072 | 11.768 | 139/186/330/237/9771/2346 | local-anchor depth |

Deduplication did not exclude any winner, every missed winner had complete
routing evidence, and every reference winner was inside its routed reference
pool. The misses are quota competition or source-order depth. Lake Michigan
maximum and both continental-corners winners rank beyond 100 in every useful
tested source, so no reallocation of a 100-slot budget among these same orders
can include them all.

At E100, first-admission provenance for the 23 recovered maximum winners is
`4/5/5/6/0/3`; for the 24 recovered total winners it is `7/0/8/2/4/3` in
`LT/LM/GT/GM/O/R` order. Origin coverage has measurable minimum-total value,
and radial coverage has measurable minimum-maximum value. Policy B's extra
global depth produces no winner-inclusion improvement over Policy A at any
tested budget, although it sometimes changes deeper top-ten coverage. No
source is universally useless, but global depth alone is a poor exchange for
capacity in this family.

## Operational volume

Matrix cells equal origins times actual shortlist size. Because every
shortlist is exact, operational volume is predictable.

| K | 2 origins | 3 origins | 4 origins | 5 origins | 6 origins | Corpus cells | Increase |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 40 | 80 | 120 | 160 | 200 | 240 | 4,160 | n/a |
| 60 | 120 | 180 | 240 | 300 | 360 | 6,240 | 50.0% |
| 80 | 160 | 240 | 320 | 400 | 480 | 8,320 | 33.3% |
| 100 | 200 | 300 | 400 | 500 | 600 | 10,400 | 25.0% |

The corpus counts by group size are 3/1/17/3/2, respectively. Each additional
20-candidate tranche adds `20 x origin count` cells per scenario and 2,080
cells across this corpus. This analysis does not invent provider dollar costs
or infer live latency from cached evaluation.

## Progressive evaluation

All 390 `40 -> 60`, `60 -> 80`, and `80 -> 100` scenario-policy comparisons
are nested. No larger shortlist removes a previously selected ID. The fixed
20-candidate tranche therefore preserves balanced source allocation and is a
reasonable mechanical increment.

It is not yet a justified runtime tranche. Quality still fails at 100, and
live latency, provider request packing, provider cost, and a practical ceiling
remain unresolved. The earlier 750-candidate adversarial reference
stabilization depth remains reference evidence, not a production ceiling.

## Conclusions and next slice

1. No policy meets all primary gates, so no policy/budget is recommended for
   runtime integration.
2. E80 is the smallest balanced diagnostic point at 88.5% winner inclusion in
   both modes. E100 is the strongest measured diagnostic because it raises
   total-mode inclusion to 92.3%.
3. The 80-to-100 increase materially recovers one total-mode winner but does
   not improve maximum-mode winner inclusion.
4. Exact-budget outputs are stable and predictable: all 520 equal `K`, no
   shortlist exceeds `K`, and no supply shortfall occurs.
5. Every progressive comparison is nested; a 20-candidate tranche is
   mechanically sound but not yet a runtime decision.
6. Origin coverage recovers asymmetric minimum-total winners. Radial coverage
   recovers a continental minimum-maximum winner. Deeper global pools alone
   add no winner recall over the exact four-source baseline.
7. Lake Michigan maximum, central north-south maximum, and continental corners
   remain the important high-regret failures. Continental east-west total is
   a low-regret miss but still prevents the inclusion gate.
8. Two objective anchors plus global protection remains a suitable skeleton,
   but the current radial ordering is too coarse and the source orders do not
   expose several obstruction-sensitive winners within a 100-candidate budget.
9. The next bounded slice should remain benchmark-only and first test whether
   larger exact route budgets recover the remaining winners while remaining
   within one practical matrix request. The prior live benchmark successfully
   routed broad 500-candidate reference sets, so the next question is whether
   a larger exact budget is a simpler and more effective correction than more
   geographic heuristics. Assess result quality, matrix size, latency,
   provider constraints, and operating cost without claiming that a larger
   budget has already passed the gates. New directional or road-aware sources
   remain a fallback if larger budgets are insufficient or operationally
   unacceptable.
10. Do not copy this prototype into `src/core/` yet. Local/global ordering,
    stable deduplication, exact budgets, and nested tranche mechanics appear
    generic; golf-catalog eligibility, reference design, and the particular
    origin/radial heuristics remain Fairway benchmark concerns.
11. Catalog-backed runtime integration remains blocked and another benchmark
    is required after the larger-exact-budget test.
12. Reference pools are high-recall rather than exhaustive. Ordinary
    500-course pools were not expanded, one continental total top ten still
    changed between 750 and 1,000 in the prior benchmark, provider graphs can
    change, and mostly approximate OSM course centers remain an independent
    source of uncertainty.

The comparison does not modify runtime shortlisting, ranking, Fairway,
provider, server, or browser behavior.

## Reproduction

Run only after the committed benchmark summary and all 29 cache batches have
been verified:

```powershell
npm run benchmark:national-shortlisting-policies
```

The command reads the catalog, checked-in scenarios, committed benchmark
summary, and ignored cache. It has no routing flag or public-network path.
