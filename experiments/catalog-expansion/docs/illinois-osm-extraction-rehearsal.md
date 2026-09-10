# Illinois OSM extraction rehearsal

## Result

The 2026-08-02 rehearsal completed the state-scale development-time path from a
dated Illinois `.osm.pbf` extract through source-derived JSONL and the existing
Fairway generator. It emitted 635 logical courses, retained usable shortlist
coordinates for all 635, and produced byte-identical catalogs on two runs. It
did not change or connect to Fairway runtime behavior.

## Source and tool

- Provider: [Geofabrik Illinois downloads](https://download.geofabrik.de/north-america/us/illinois.html).
- Fixed source URL: `https://download.geofabrik.de/north-america/us/illinois-260731.osm.pbf`.
- Download date: 2026-08-02.
- OSM snapshot timestamp: `2026-07-31T20:21:56Z`.
- Size: 355,527,045 bytes (339.06 MiB).
- Published and verified MD5: `954f0368dd9a67482dcea63424368621`.
- SHA-256: `9bd2077e068643b326fa24456eade721e0b419ab89374945026865a0ef6c8ecb`.
- Tool: [Osmium Tool](https://osmcode.org/osmium-tool/) 1.19.1 with
  libosmium 2.23.1, installed from conda-forge into the ignored rehearsal
  directory.

Osmium was selected because it is a standard, maintained, replaceable OSM CLI
with native PBF decoding, tag filters, recursive reference inclusion, source
identity and tag preservation, relation members and roles, source metadata,
and source-preserving OSM XML conversion. Fairway depends only on those generic
capabilities. Another CLI can replace Osmium if it supplies the same filtered
objects and references in a source-preserving representation; neither the
generator nor its input contract depends on Osmium commands or file formats.

The tool and its native libraries are local rehearsal prerequisites, not npm or
runtime dependencies.

## Reproduction

Prerequisites are PowerShell 5.1 or later, Node.js and npm as required by this
repository, and Osmium Tool 1.19.1 or a compatible release. This rehearsal used
a portable Micromamba executable and the following local environment:

```powershell
.\.local\illinois-osm-rehearsal\tools\micromamba.exe create --yes `
  --root-prefix .\.local\illinois-osm-rehearsal\micromamba-root `
  --prefix .\.local\illinois-osm-rehearsal\osmium-env `
  --channel conda-forge osmium-tool=1.19.1
```

Acquire and verify the fixed extract under the ignored `.local/` directory:

```powershell
curl.exe -L --fail --retry 3 `
  -o .local\illinois-osm-rehearsal\illinois-260731.osm.pbf `
  https://download.geofabrik.de/north-america/us/illinois-260731.osm.pbf
curl.exe -L --fail --retry 3 `
  -o .local\illinois-osm-rehearsal\illinois-260731.osm.pbf.md5 `
  https://download.geofabrik.de/north-america/us/illinois-260731.osm.pbf.md5
Get-FileHash -Algorithm MD5 `
  .local\illinois-osm-rehearsal\illinois-260731.osm.pbf
```

Run the direct development-only extraction adapter:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\extract-illinois-osm-golf-courses.ps1 `
  -InputPbf .\.local\illinois-osm-rehearsal\illinois-260731.osm.pbf `
  -OutputJsonl .\.local\illinois-osm-rehearsal\illinois-golf-courses.jsonl `
  -OsmiumPath .\.local\illinois-osm-rehearsal\osmium-env\Library\bin\osmium.exe
```

Generate twice and compare the actual bytes:

```powershell
npm run generate:golf-course-catalog -- `
  .local\illinois-osm-rehearsal\illinois-golf-courses.jsonl `
  .local\illinois-osm-rehearsal\illinois-catalog-first.json
npm run generate:golf-course-catalog -- `
  .local\illinois-osm-rehearsal\illinois-golf-courses.jsonl `
  .local\illinois-osm-rehearsal\illinois-catalog-second.json
& "$env:SystemRoot\System32\fc.exe" /b `
  .local\illinois-osm-rehearsal\illinois-catalog-first.json `
  .local\illinois-osm-rehearsal\illinois-catalog-second.json
```

## Exact extraction boundary

The script asks Osmium for `nwr/leisure=golf_course` and leaves its default
recursive reference inclusion enabled. Osmium decodes the PBF, retains full
matching node, way, and relation objects, includes the nodes and ways required
by matching geometry, preserves tags, IDs, relation memberships, and member
roles, and converts that narrow result to OSM XML.

The PowerShell adapter streams the source representation and emits one Fairway
JSONL row per directly tagged course object. Node coordinates remain source
node coordinates. Ways and relations receive the center of the axis-aligned
bounding box of their referenced source geometry and are marked `center`; this
is an approximate representative coordinate, not an arrival point. Direct tags
and relation member roles are copied without interpretation.

The extraction does not classify access or format, normalize metadata, select
an arrival point, or infer logical-course identity. The existing Fairway
generator continues to own those decisions.

Osmium does not perform a geometry-containment join. No clubhouse, main
entrance, parking, or parking-entrance object was a topological member of the
filtered Illinois course objects, so the JSONL honestly contains empty
`contained` arrays. No database or custom geographic engine was added to fill
that gap.

## Measurements

| Measurement | Result |
| --- | ---: |
| Raw Illinois PBF | 355,527,045 bytes |
| Narrow filtered PBF | 299,694 bytes |
| Source-preserving XML | 3,155,863 bytes |
| Source-derived JSONL | 228,718 bytes |
| Extraction duration | 9,763.4 ms |
| Extraction peak working set | 2,075,508,736 bytes (1.93 GiB) |
| PowerShell adapter peak working set | 145,108,992 bytes (138.39 MiB) |
| Source course objects | 636: 18 nodes, 532 ways, 86 relations |
| Contained or associated evidence objects emitted | 0 |
| Logical courses emitted | 635 |
| Structural duplicates folded | 1 |
| Exact-name pairs within 1 km deliberately retained | 11 pairwise cases |
| Malformed or non-course rows skipped | 0 |
| Invalid metadata values | 4 |
| Conflicting metadata fields | 2 |
| Generated catalog | 246,010 bytes (240.24 KiB) |
| Generator durations | 29.0 ms and 27.7 ms |
| Generator peak working set | 72,257,536 bytes (68.91 MiB) |

The extraction peak belongs to Osmium's reference-following filter pass; the
streaming adapter remained substantially smaller. Peak values are the maximum
polled working set of the relevant process, not an aggregate across processes.

## Metadata coverage

Unknown rates use the 635 emitted logical courses as the denominator.

| Field | Unknown | Rate |
| --- | ---: | ---: |
| Name | 73 | 11.5% |
| Holes | 625 | 98.4% |
| Par | 630 | 99.2% |
| Access | 628 | 98.9% |
| Format | 635 | 100.0% |
| Operator | 559 | 88.0% |
| Website | 361 | 56.9% |
| Address | 327 | 51.5% |

Known hole values were one 3-hole, three 9-hole, and six 18-hole records. Known
par values were 34, 35, 71, and two 72 records. Access normalized only from
direct evidence: one public and six private records; 628 remained unknown. No
recognized explicit course-format evidence was present.

The four invalid values were `golf:course=driving_range`,
`golf:course=18_holes`, and two unsupported `ownership=government` access
values. The two conflicts were the differently spelled relation/outer-way names
for Orchard Valley and the two different valid URLs on Palatine Hills Golf
Course. There were no conflicting holes or par values.

## Representative cases

- `osm:node/3095981624`, Carthage Golf Club, retained an exact node coordinate.
- `osm:way/39875542`, Country Club of Peoria Golf Course, retained approximate
  geometry-derived coordinates plus direct 18-hole and par-72 evidence.
- `osm:relation/13764464`, Tri-City Country Club, retained its multipolygon
  identity and member roles, with direct 9-hole and par-35 evidence.
- Multipolygon relation `7881067` folded its tagged outer way `478328355` and
  retained both OSM identities. Their conflicting `Orchard Valley` / `Orchard
  Vally` names correctly produced an unknown name instead of choosing one.
- `osm:way/1017136209` is one of 73 unnamed results and remained usable through
  an approximate geometry-derived coordinate.
- The `Nettle Creek County Club` node and three nearby `Nettle Creek Country
  Club` ways stayed separate because no explicit supported structure says they
  are one logical course. The 11-pair possible-duplicate measurement is an
  audit heuristic, not a new merge rule.
- Sunset Valley normalized to public only from `access=yes`; Westmoreland
  normalized to private only from `access=private`. Names and operators did not
  infer access.
- `golf:course=driving_range` was preserved as source evidence but did not
  become a recognized Fairway format. No speculative format rule was added.
- A George W. Dunne course relation and nearby course way are also tagged
  `amenity=parking`. Because those are course objects rather than contained
  evidence objects, the generator did not promote their generic parking tag to
  an arrival candidate.

There were no real clubhouse or main-entrance arrival candidates to inspect in
the generated catalog. The existing focused generator test still verifies that
source-derived clubhouse, entrance, and generic parking evidence remains
unverified when the input supplies it, but the Illinois run did not validate a
state-scale containment join.

## Limitations and contract result

The existing course input shape represented all Illinois course nodes, ways,
multipolygon relations, direct tags, member roles, structural folding evidence,
and representative coordinates without a generator change.

The current `contained` field cannot honestly distinguish geometry containment
from some other explicit association. A future extractor that can produce both
must first define source provenance for that distinction. This rehearsal did
not change the contract because Osmium alone supplied neither relationship for
Illinois evidence objects, and adding a geographic database or custom
containment engine would exceed this slice.

All 635 emitted courses have a stable ID and finite, in-range latitude and
longitude. Zero records lack the minimum inputs required by the current
meeting-region shortlisting prototype. Eighteen coordinates are exact nodes;
617 are approximate bounding-box centers.

## Validation and local artifacts

- Byte comparison: no differences; both catalogs have SHA-256
  `2d30b31c596fa16ebe024ad40eb72b1f2f4bcae1d712b904f7f55207cd354637`.
- Focused generator tests: 7 passed.
- Full repository suite: 76 passed.
- Runtime files under `src/fairway/`: unchanged.

The raw PBF, published checksum, narrow PBF, exported XML, source JSONL, two
catalogs, Micromamba executable, Osmium environment, and package cache remain
under `.local/illinois-osm-rehearsal/`. `.local/` is ignored, so none is part of
the repository change.
