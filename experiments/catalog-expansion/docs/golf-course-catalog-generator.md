# Golf-course catalog generator

This development-time script normalizes already filtered OSM-derived JSONL. It
does not parse `.osm.pbf` files or affect Fairway runtime discovery.

```powershell
npm run generate:golf-course-catalog -- input.jsonl catalog.json
```

## Extraction and input

The replaceable extraction boundary is:

```text
.osm.pbf
-> generic OSM filter/export
-> source-derived JSONL
-> Fairway catalog generator
```

An `osmium` filter/export pipeline or an equivalent GDAL/OGR workflow can own
PBF decoding, tag filtering, relation membership, containment, and representative
point calculation. It must not normalize metadata, select an arrival point, or
decide that nearby or similarly named objects are one course.

Blank lines are ignored. Exactly one source row supplies a stable snapshot ID:

```json
{"kind":"source","snapshot":"extract-id-2026-08-01-sha256-..."}
```

Every other row is a directly sourced possible course representation:

```json
{"kind":"course","course":{"type":"relation","id":123,"tags":{"leisure":"golf_course","type":"multipolygon","name":"Example Golf Course"},"coordinates":[41.1,-87.2],"coordinateSource":"center","members":[{"type":"way","id":124,"role":"outer"}]},"contained":[{"type":"node","id":125,"tags":{"entrance":"main"},"coordinates":[41.11,-87.21],"coordinateSource":"node"}]}
```

- OSM identities use `node`, `way`, or `relation` plus a positive integer ID.
- Tags are unmodified string pairs.
- Coordinates are `[latitude, longitude]`; `coordinateSource` is `node`,
  `center`, `centroid`, or `point_on_surface`.
- Optional `members` copy an OSM relation's object identities and roles.
- A clipped regional extract may retain a relation membership whose referenced
  object is absent. Extraction may derive the representative point from the
  available referenced geometry, but must preserve the full member list, count
  the missing source references, and fail rather than inventing a point when no
  source geometry is available.
- Optional `contained` objects are selected by source geometry containment, not
  by Fairway metadata semantics. They use the same identity, tags, and point
  fields and let Fairway recognize clubhouse, entrance, and parking evidence.

Non-`leisure=golf_course` course rows are counted and skipped. Malformed JSON,
identities, tags, points, coordinate sources, members, or containment fail with
a line-specific error.

## Output

The compact JSON document contains `schemaVersion`, the OpenStreetMap snapshot,
and stable-ID-sorted courses. Each course has:

- `id`, nullable `name`, `latitude`, and `longitude`;
- coordinate `source` and `approximate` status;
- nullable `holes`, `par`, explicit `format`, `operator`, `website`, and
  structured `address`;
- `access`: `public`, `private`, `municipal`, or `unknown`;
- zero or more unverified source-derived `arrivalCandidates`; and
- sorted OSM provenance identities.

Absent, invalid, or conflicting scalar evidence produces null, or `unknown` for
access. Conflict and invalid counts stay in the generation summary rather than
adding audit diagnostics to every runtime-oriented record.

## Normalization

- Text is trimmed, internal whitespace is collapsed, and Unicode is NFC.
  `name` is direct; `official_name` is only a fallback.
- Holes accept a positive one- or two-digit integer, optionally `<n>_hole`,
  from `holes`, `golf:holes`, or `golf:course`. Par accepts one positive integer
  from `par` or `golf:par`.
- Access uses only explicit supported `access`, `golf:access`, `golf:type`, or
  `ownership=municipal` values.
- Format uses recognized explicit `golf:format`, `course:type`, `golf:type`, or
  `golf:course` values: pitch-and-putt, par-3, executive, or full-length.
- Operator is direct. Website is one valid HTTP(S) URL. Address requires
  `addr:full` or both `addr:housenumber` and `addr:street`.
- Names and operator text never establish access, municipal status, or format.
- Node points are exact; all geometry-derived point types are approximate.
- Explicit clubhouses and `entrance=main` become unverified candidates. Parking
  and parking entrances remain unverified evidence. Service and exit entrances
  are not promoted. No authoritative arrival point is selected.

## Deduplication and determinism

Fairway folds repeated identical OSM identities. It also folds a tagged golf
course way into a tagged golf-course `type=multipolygon` relation when that way
is an explicit `outer` member. The relation becomes the stable identity and all
source identities remain in provenance.

No other relation type establishes equivalence. Names, proximity, operator, and
metadata overlap never merge records; uncertain possible duplicates stay
separate.

Input order, tag order, and relationship order do not affect output bytes.
There are no generation timestamps or machine paths in the catalog. The
snapshot ID is source provenance; duration, counters, and output size are
console-only measurements.
