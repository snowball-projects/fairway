# Contiguous-US OSM extraction rehearsal

## Result

The 2026-08-02 rehearsal completed the offline path from 49 fixed Geofabrik
OpenStreetMap extracts through source-derived JSONL and the existing Fairway
catalog generator. It covered the 48 contiguous states plus Washington, DC,
emitted 16,166 logical courses, retained shortlist-usable coordinates for all
16,166, and produced byte-identical catalogs. It did not connect the catalog to
Fairway runtime behavior.

The generator input contract did not change. The state extraction adapter
needed one narrow correction for clipped source geometry: relation memberships
can refer to objects absent from a state extract. The adapter now preserves
those memberships, counts missing references, and derives an approximate center
from available geometry. It still fails rather than inventing a coordinate when
no source geometry is available.

## Source scope and provenance

- Provider: [Geofabrik United States downloads](https://download.geofabrik.de/north-america/us.html).
- Included: the 48 contiguous states and the separately available District of
  Columbia extract; 49 jurisdictions total.
- Excluded: Alaska, Hawaii, Puerto Rico, and all other territories.
- Fixed source date: 2026-07-31.
- OSM snapshot timestamp: `2026-07-31T20:21:56Z` for all 49 PBF headers.
- Download date: 2026-08-02.
- URL base: `https://download.geofabrik.de/north-america/us/`; append the file
  in the table. Each checksum URL is the exact source URL plus `.md5`.
- Ordering: ordinal jurisdiction slug order exactly as tracked in
  `scripts/contiguous-us-osm-sources.json`.
- Canonical manifest fingerprint SHA-256:
  `cee4a8888f4665bdb755340a0535eeb5050c5fd240120a94857281d6d52233f4`.
- National snapshot identifier:
  `geofabrik-contiguous-us-2026-07-31-manifest-sha256-cee4a8888f4665bdb755340a0535eeb5050c5fd240120a94857281d6d52233f4`.
- All 49 published MD5 values matched both the manifest and downloaded bytes.
  Per-source SHA-256 values remain in ignored completion markers.

All rows below share the fixed date and snapshot timestamp above. Object counts
are directly tagged course nodes/ways/relations. Peak memory is the maximum
polled working set for that state's Osmium or adapter process, not an aggregate.

| Jurisdiction | Fixed file | MiB | Published and verified MD5 | Seconds | Peak GiB | Objects (n/w/r) |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| Alabama | `alabama-260731.osm.pbf` | 140.24 | `0343568366a6e837a291e8d233a178e9` | 4.991 | 1.19 | 201 (4/142/55) |
| Arizona | `arizona-260731.osm.pbf` | 286.26 | `f3ddab54423002dba5d1c4000b50808f` | 13.625 | 1.78 | 378 (12/172/194) |
| Arkansas | `arkansas-260731.osm.pbf` | 94.15 | `e535341d12bd77775301dea5c56a7428` | 3.088 | 0.81 | 144 (5/108/31) |
| California | `california-260731.osm.pbf` | 1,260.86 | `3536a74974b0d3d6ca6ea9f89fcd6701` | 32.481 | 2.10 | 997 (25/649/323) |
| Colorado | `colorado-260731.osm.pbf` | 359.41 | `a4644e32fb13fc10bd82cdf972b5418e` | 11.062 | 1.70 | 265 (6/190/69) |
| Connecticut | `connecticut-260731.osm.pbf` | 206.08 | `f704e07c9cfc9fa8158e4b28506b16cb` | 5.655 | 1.12 | 188 (1/155/32) |
| Delaware | `delaware-260731.osm.pbf` | 20.91 | `57c8bb95b9b6d53d5c5a1ce4b06c3566` | 1.532 | 0.54 | 47 (2/35/10) |
| District of Columbia | `district-of-columbia-260731.osm.pbf` | 19.94 | `098a353055f967a72b7ccb88c0108d48` | 0.929 | 0.19 | 7 (0/6/1) |
| Florida | `florida-260731.osm.pbf` | 623.22 | `c499d6d92191bfd83d800824760d24d8` | 55.850 | 2.10 | 2,052 (29/1,213/810) |
| Georgia | `georgia-260731.osm.pbf` | 338.15 | `7dca7b807118c51c16e6081e5605920d` | 10.648 | 1.58 | 420 (12/297/111) |
| Idaho | `idaho-260731.osm.pbf` | 121.45 | `7410f6e989bbd828606c384518f003bd` | 3.396 | 1.03 | 104 (1/69/34) |
| Illinois | `illinois-260731.osm.pbf` | 339.06 | `954f0368dd9a67482dcea63424368621` | 9.697 | 1.95 | 636 (18/532/86) |
| Indiana | `indiana-260731.osm.pbf` | 187.47 | `79e43bd758c0120529112110b776a05e` | 7.247 | 1.69 | 404 (6/325/73) |
| Iowa | `iowa-260731.osm.pbf` | 126.38 | `b0f688ffef541709aa13b551c43ad7be` | 4.336 | 1.56 | 399 (0/355/44) |
| Kansas | `kansas-260731.osm.pbf` | 109.10 | `3e2cf68c24703f5a6edffe7787790fd0` | 3.752 | 1.33 | 220 (5/177/38) |
| Kentucky | `kentucky-260731.osm.pbf` | 145.88 | `cbca7302bd16243868a9eb0cc96d97c3` | 4.075 | 1.27 | 234 (13/197/24) |
| Louisiana | `louisiana-260731.osm.pbf` | 138.65 | `1b59b6d5dfce2b1dcb1c4ead536bc969` | 3.388 | 0.84 | 121 (5/93/23) |
| Maine | `maine-260731.osm.pbf` | 86.22 | `15364fb9803c031f72b597557789b6b5` | 2.985 | 0.92 | 122 (1/103/18) |
| Maryland | `maryland-260731.osm.pbf` | 203.40 | `b7bc97615729e5c87fa903dadfc88219` | 6.093 | 1.45 | 203 (5/144/54) |
| Massachusetts | `massachusetts-260731.osm.pbf` | 294.64 | `2fff8b93c10a93db5f3e4fc136e8ba3c` | 11.942 | 1.65 | 359 (2/290/67) |
| Michigan | `michigan-260731.osm.pbf` | 295.93 | `500446f3209dacd636d0f084c6e47770` | 9.364 | 1.88 | 856 (11/758/87) |
| Minnesota | `minnesota-260731.osm.pbf` | 269.27 | `e9762a69a36b56fac88cf4888c8446ac` | 7.994 | 1.85 | 472 (12/393/67) |
| Mississippi | `mississippi-260731.osm.pbf` | 89.27 | `25a1b0c5931a4fb77861932a25513702` | 2.971 | 0.73 | 113 (4/87/22) |
| Missouri | `missouri-260731.osm.pbf` | 184.00 | `d53cec1962a4e97da9f27a12b7dbeebb` | 5.957 | 1.47 | 321 (10/253/58) |
| Montana | `montana-260731.osm.pbf` | 94.92 | `410b0c753cc2b04a400fc61adba08959` | 2.709 | 0.89 | 97 (1/76/20) |
| Nebraska | `nebraska-260731.osm.pbf` | 94.92 | `3e1f16fbd0bcfabc38ed3452bad225be` | 3.491 | 1.18 | 212 (1/178/33) |
| Nevada | `nevada-260731.osm.pbf` | 116.89 | `60e091e921c09a0f97b58f2b6319f59e` | 5.737 | 1.17 | 111 (3/48/60) |
| New Hampshire | `new-hampshire-260731.osm.pbf` | 67.47 | `1cf3f0d93b5b26f02865dcabc963871e` | 2.744 | 0.99 | 104 (8/84/12) |
| New Jersey | `new-jersey-260731.osm.pbf` | 154.87 | `5e1ada0beb37196c126c57cf7c811b06` | 6.059 | 1.52 | 326 (8/249/69) |
| New Mexico | `new-mexico-260731.osm.pbf` | 129.36 | `0fa892725b260dac0797d5b8b5068b1f` | 3.189 | 0.79 | 92 (1/76/15) |
| New York | `new-york-260731.osm.pbf` | 471.29 | `f255e883aaee39f4abe5a1040f328537` | 13.614 | 1.91 | 830 (11/755/64) |
| North Carolina | `north-carolina-260731.osm.pbf` | 406.54 | `47dde2990d41260af77cf000b6355193` | 13.859 | 1.68 | 484 (50/254/180) |
| North Dakota | `north-dakota-260731.osm.pbf` | 121.71 | `61aca19ab36d7c069adc006feb03c330` | 2.664 | 0.86 | 127 (0/119/8) |
| Ohio | `ohio-260731.osm.pbf` | 305.74 | `cb1d7d5b5809211297e7cfed0131dff0` | 10.182 | 1.97 | 695 (12/608/75) |
| Oklahoma | `oklahoma-260731.osm.pbf` | 159.70 | `2179767fc0b0652de2cc25535b16d9ab` | 3.751 | 1.19 | 168 (7/138/23) |
| Oregon | `oregon-260731.osm.pbf` | 240.36 | `691d096e059bc8ebe82cc27bd8c36bdf` | 5.060 | 1.44 | 197 (4/156/37) |
| Pennsylvania | `pennsylvania-260731.osm.pbf` | 327.55 | `05eb3df8cc2b2621c8d2a513a9ffca13` | 9.489 | 1.95 | 637 (38/538/61) |
| Rhode Island | `rhode-island-260731.osm.pbf` | 49.43 | `2aa7ceed40153a72951ef95ae68686b4` | 2.127 | 0.72 | 59 (0/44/15) |
| South Carolina | `south-carolina-260731.osm.pbf` | 154.51 | `e60a0c19dce9e2bc367da1f0f88ba800` | 8.851 | 1.65 | 338 (35/160/143) |
| South Dakota | `south-dakota-260731.osm.pbf` | 45.86 | `4bc752063aacb48bf6d53a4fdae56b30` | 2.042 | 0.91 | 106 (2/68/36) |
| Tennessee | `tennessee-260731.osm.pbf` | 178.22 | `87a13d87eba85ac9c9ad19abf2d09918` | 4.925 | 1.40 | 241 (11/182/48) |
| Texas | `texas-260731.osm.pbf` | 679.41 | `7a8bc823d7f09b3469abb0a9c122ec07` | 18.848 | 2.01 | 813 (26/592/195) |
| Utah | `utah-260731.osm.pbf` | 159.02 | `06327d836a98b69a2aa9285724c93cb8` | 4.967 | 1.28 | 123 (3/83/37) |
| Vermont | `vermont-260731.osm.pbf` | 43.56 | `d9480acd6217694fed4e313a57f229c0` | 1.653 | 0.62 | 61 (0/51/10) |
| Virginia | `virginia-260731.osm.pbf` | 406.24 | `390d4b0c466c2b3ab15649b21cd24d75` | 11.299 | 1.78 | 333 (6/224/103) |
| Washington | `washington-260731.osm.pbf` | 343.11 | `3ffa39a825f27af7ecdefc15576a62cb` | 8.216 | 1.76 | 274 (3/192/79) |
| West Virginia | `west-virginia-260731.osm.pbf` | 93.29 | `4f15bddd281c5c134d456626aaf5562c` | 2.845 | 0.70 | 126 (4/103/19) |
| Wisconsin | `wisconsin-260731.osm.pbf` | 277.66 | `499ab4d9df6a76dc7758aaed33fbb618` | 8.243 | 1.88 | 495 (8/401/86) |
| Wyoming | `wyoming-260731.osm.pbf` | 88.38 | `8038d1569ab8f0f818750da77a6e4e24` | 2.325 | 0.65 | 60 (4/44/12) |

## Preflight and execution

Before downloading, the manifest measured 11,691,605,431 compressed source
bytes (10.89 GiB). A 2% intermediate allowance plus 50 MiB for catalogs and
logs estimated 11,977,866,340 bytes (11.15 GiB) of retained working space. The
drive had 163,307,008,000 bytes (152.09 GiB) free. The final national artifact
directory used 11,867,229,378 bytes (11.05 GiB); the reused Osmium environment
adds 33,545,481 bytes (31.99 MiB).

The runner verifies that its artifact root is beneath ignored `.local/`, checks
manifest count, exclusions, unique slugs, fixed filenames, checksums, and
ordinal ordering, then processes one jurisdiction at a time. A completion
marker binds each finished JSONL to its source entry and JSONL SHA-256. Final
concatenation always walks manifest order and removes only per-state source
headers, not course rows.

The first attempt stopped after 46 seconds on Arizona's clipped relation
geometry. The corrected run reused the downloaded Alabama and Arizona PBFs,
downloaded the remaining 47, and completed in 1,103.9 seconds (18:23.9).
Including the failed attempt, observed empty-start wall time was about 1,149.9
seconds (19:09.9). A final replay reused all 49 completion markers and rebuilt
the combined input and two catalogs in 13.1 seconds.

Tools were Osmium Tool 1.19.1 with libosmium 2.23.1, curl 8.21.0, Windows
PowerShell 5.1.26100.8875, and Node.js 24.13.1. They remain development-only
local prerequisites.

## Extraction and generation measurements

| Measurement | Result |
| --- | ---: |
| Compressed PBF inputs | 11,691,605,431 bytes (10.89 GiB) |
| Recorded download time for 47 non-reused sources | 667.6 seconds |
| Summed state extraction duration | 381.9 seconds (6:21.9) |
| Extraction peak working set | 2,252,402,688 bytes (2.10 GiB) |
| Adapter-only peak working set | 246,018,048 bytes (234.62 MiB) |
| Narrow filtered PBFs | 11,461,651 bytes (10.93 MiB) |
| Source-preserving XML | 138,924,536 bytes (132.49 MiB) |
| State JSONL total | 6,393,301 bytes (6.10 MiB) |
| Combined deterministic JSONL | 6,386,355 bytes (6.09 MiB) |
| Source course representations | 16,372 |
| Nodes / ways / relations | 435 / 12,166 / 3,771 |
| Contained or associated evidence objects | 0 |
| Logical courses emitted | 16,166 |
| Repeated exact identities folded | 111 |
| Structural multipolygon folds | 95 |
| Total generator folds | 206 |
| Exact-name pairs within 1 km conservatively preserved | 262 |
| Invalid metadata values | 316 |
| Conflicting metadata fields | 42 |
| Skipped malformed or non-course rows | 0 |
| Final catalog | 6,140,500 bytes (5.86 MiB) |
| Gzip level-9 catalog measurement | 769,969 bytes (0.73 MiB) |
| Generator durations | 421.9 ms and 428.5 ms |
| Generator wall-clock durations | 555.5 ms and 529.1 ms |
| Generator peak working set | 207,351,808 bytes (197.75 MiB) |
| Byte-identical outputs | yes |
| Catalog SHA-256 | `ff0fd7efbb21e8e6edd4e99bc59acd7eb000272346e9ec7db4e961d352c3ad77` |

Florida, not California, had the slowest extraction at 55.85 seconds because
it had 2,052 directly tagged course objects. California supplied the largest
PBF and the peak working set. Download, checksum I/O, and Osmium filtering
dominated; the generator was negligible.

## Metadata and coordinate coverage

Unknown rates use 16,166 logical courses as the denominator.

| Field | Known | Unknown | Unknown rate |
| --- | ---: | ---: | ---: |
| Name | 12,904 | 3,262 | 20.2% |
| Holes | 1,347 | 14,819 | 91.7% |
| Par | 1,046 | 15,120 | 93.5% |
| Access | 469 | 15,697 | 97.1% |
| Format | 11 | 16,155 | 99.9% |
| Operator | 1,210 | 14,956 | 92.5% |
| Website | 6,968 | 9,198 | 56.9% |
| Address | 6,872 | 9,294 | 57.5% |

The 469 known access values were 37 public, 405 private, and 27 municipal.
Access is too sparse and contributor-biased for a national eligibility filter.
Holes, par, format, and operator are likewise too incomplete. Names, websites,
and addresses are useful when present; websites and addresses are plausible
optional presentation fields but should not become strict defaults.

There were 434 exact node coordinates and 15,732 approximate geometry centers.
All 16,166 records had finite, in-range coordinates; zero lacked the minimum
coordinate needed by current shortlisting. This establishes shortlist
readiness, not verified routing-arrival accuracy.

## Source irregularity and deduplication review

Thirteen state extracts contained clipped relation geometry: Arizona,
California, Maryland, Michigan, Minnesota, Missouri, Nebraska, Ohio, South
Carolina, South Dakota, Texas, Vermont, and Wisconsin. Across them, 20 course
objects referred to 113 missing geometry objects. The same generic behavior
handled every state. Every affected course retained enough source geometry for
a representative center; none was discarded.

The triggering example was `relation/3523875`, The Oasis - Canyons Course. The
Arizona extract retains the tagged relation and its members but only one of 12
member ways; Nevada contains the same exact relation identity with usable
geometry. Fairway retained both rows until generation, then its existing
exact-identity rule folded them.

The 111 repeated exact identities are 0.68% of source representations. Together
with 95 structural multipolygon folds, they reduced 16,372 rows to 16,166
logical courses. Boundary duplication did not materially inflate the catalog.
The 262 exact-name pairs within 1 km are an audit heuristic only. For example,
`node/10000107286` and `relation/20963164` are both Cedar Creek Golf Course and
0.491 km apart, but stayed separate because name and proximity do not prove
identity.

## Geographic sanity review

- Named node, way, and relation examples were exact node `10000107286` Cedar
  Creek Golf Course, approximate way `100010941` Diamond Bar Golf Course, and
  multipolygon relation `10040111` Spring Hollow Golf Club. Spring Hollow
  folded two explicitly tagged outer ways while preserving all three IDs.
- Dense metro samples included Liberty National Golf Club near New York,
  Monterey Park Golf Club near Los Angeles, The Green in Chicago, and Noonan
  Golf Facility in Atlanta. Rural samples included Hickory Swing Golf Course in
  Montana and Dunes Golf Course in South Dakota.
- Boundary identities included Green Island Hills Golf Course in
  Alabama/Georgia, Edgewood Tahoe Golf Course in California/Nevada, and The
  Oasis relation in Arizona/Nevada. They folded by identity, not place name.
- `node/10006297533` is one of 3,262 unnamed logical courses and retained an
  exact coordinate. Unnamed approximate relations and ways were also present.
- Direct evidence produced public Sun Village Golf Course, private Oak Hill
  Country Club, municipal Chicopee Country Club, and unknown Cedar Creek Golf
  Course. Names and operators did not supply those classifications.
- `golf:par=35 + 36 + 36` on JW Marriott Tucson Starr Pass remained invalid.
  The folded Indian Hills relation/outer-way pair supplied conflicting `Golf
  Course` and `Golf Club` names, so its logical name remained unknown.
- Approximate centers were widespread and explicitly marked. No contained
  clubhouse, entrance, or parking evidence was emitted because Osmium reference
  filtering does not establish geometry containment.

## Conclusions

1. The existing JSONL contract supports the contiguous United States without
   change. The adapter needed only generic tolerance and measurement for source
   references clipped from state PBFs.
2. No state required special-case behavior. Thirteen states exercised the same
   missing-reference path.
3. The generator remains deterministic at national scale. Two outputs were
   byte-identical, and a marker-reuse replay produced the same SHA-256.
4. The 5.86 MiB catalog, about 0.73 MiB gzip, is compact enough to evaluate as a
   static deployment asset.
5. All records are usable for geographic shortlisting. Most coordinates are
   approximate and still require later routing-destination validation.
6. Name has useful broad coverage. Website and address have enough coverage for
   optional, evidence-qualified presentation. Coordinate quality should remain
   visible.
7. Access, holes, par, format, and operator remain too incomplete or biased for
   strict national filtering. Unknown must remain first-class.
8. Boundary duplication did not materially affect output: 111 exact repeats
   were folded, only 0.68% of source rows.
9. The offline bottlenecks are the 10.89 GiB download, checksum I/O, and Osmium
   filtering at up to 2.10 GiB working set. Assembly and generation are small.
10. Another extraction rehearsal is not necessary before shortlist benchmarking.
    Verified arrivals and containment remain separate future data work but do
    not block the next roadmap slice.

## Reproduction and local artifacts

Preflight without downloads:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-contiguous-us-osm-golf-catalog.ps1 `
  -PreflightOnly
```

Run or resume the complete rehearsal with the Osmium environment documented by
the Illinois rehearsal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-contiguous-us-osm-golf-catalog.ps1
```

Raw PBFs, checksums, filtered PBFs, XML, state JSONL, completion markers,
combined JSONL, both catalogs, summaries, and temporary analysis remain under
`.local/contiguous-us-osm-rehearsal/`. The national catalog is not tracked.
