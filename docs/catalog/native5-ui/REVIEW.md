# Native5 UI preparation

This isolated candidate starts at independently reviewed frontend
`830bce48610d829457d0f5cd24cac9c7ab9aa7e3`. It prepares a single version2/schema5
consumer using the frozen synthetic writer fixture, without adopting a new database
or replacing the unchanged revision758/schema4 transport in data/catalog-release.
Production schema adoption and publication still require Nas's layout confirmation,
independent source review and a frozen approved real export. No release is implied.

## Exact inputs

INPUT-PINS.json records writer base52a7c3f370580c8eafb71ee15ffa184cdb522226,
unchanged SQL SHA256 ab852cff6180dba03c4d7f780b2aded18ea962ed0664808887698c9cd78a34c6,
and synthetic transport SHA256
af80563e815aaedda424b24eeeb42b985e6edd8b746306a8804fca6bc3454bef.
The fixture remains byte-identical, 45,322 bytes, three facilities, three courses,
two shared destinations and six distinct optional observations. Its revision2 is
synthetic and is unrelated to the actual catalog revision758.

The public evidence correction203fcd46c8ea93f191bd0d33d9f5abfcd5209b63 is also
pinned: public provenance.notes contains exactly note IDs, never retained bodies.
SQLite retains original bodies privately. The fixture's empty notes array is
unchanged. BACKEND-CONTRACT.md is an exact copy of that corrected source contract.
Writer203fcd4 bounded source clearance is independently recorded in task11/native5-production-review/CLEARANCE-203fcd4.json. That source clearance does not adopt a schema or approve the remaining mapping/publication.

## Consumer behavior

The immutable loader requires format_version2/schema5, exact manifest release,
revision, counts, uncompressed bytes and SHA256, and a hash-named same-origin asset.
There is no v1 adapter, raw JSON alias interpretation or prose fallback. Standalone
CatalogRead tests retain v1 recovery-baseline checks independently of this strict
entry. Existing Python API, legacy SQLite reader/exporter and frozen data are
unchanged and are not advertised as a native5 backend.

optional-schema.mjs contains explicit column/type dictionaries for the ten pinned
SQL observation views and five relationship tables, rather than a generic attribute
framework. All ten domain arrays are required. Unknown columns, missing columns,
wrong types, mixed subjects, source binding drift, relationship drift, altered
shared-round copies and populated deferred quality ratings reject the catalog.
Facility, course, component and round observations remain separate. Architecture
credits preserve every party, nullable role/year and event. Dated prices retain all
recorded product, amount, currency, audience, residency, day/time, prerequisite,
conflict and qualification fields. There is no current-price sort or quote claim.
False range lighting never becomes absence of a range; empty lists and NULLs remain
unknown. Nullable access is displayed and filtered as unconfirmed. Preliminary
public-play eligibility keeps its NULL nonmember-booking fact and explicit qualifier.
Structured city fields support city search; addresses are never parsed for facts.

The UI renders canonical fields as textContent, with safe HTTP(S) source links,
source license/attribution and dated qualifications. It does not render raw retained
notes or private controls. Absolute POSIX, drive, UNC and file-URI tokens, including punctuation-prefixed paths, reject in
public keys and values. Complete HTTP(S) URL tokens are excluded from the validation
scan only; their emitted text and slash-compound words remain unchanged. Source registry data stays in the validated model; source
counts and per-observation provenance avoid eagerly creating thousands of registry
DOM nodes. The existing single Courses drawer, filters, committed origins and
coordinate selection remain. No routing implementation is added.

## Reproducible local review build

```
python scripts/build_pages.py --check --review-fixture
python scripts/build_pages.py --review-fixture --output /explicit/new/review-site --commit COMMIT
node --test --test-isolation=none tests/*.test.mjs
PYTHONPATH=src:tests python -m pytest -q
```

The explicit fixture switch verifies the literal pinned bytes and adds a persistent
visible synthetic-review banner and deployment.review_fixture:true. It creates only
23 allowlisted static files and starts no listener. The normal build deliberately
rejects the retained v1 release before writing output. Existing publication workflows
remain unmodified and cannot publish this candidate's old data by silently falling
back or selecting the fixture. Adopting an approved real native5 export remains a
separate reviewed change.

## Verification and limits

Author source checks:273 Python and114 JavaScript tests pass, including actual
committed-origin handler and course-details execution, all ten optional domain
arrays, four subject scopes, unknown/false behavior, shared rounds, architecture,
full price conditions, source drift, note-body rejection and absolute-path rejection.
Build tests verify deterministic fixture output, asset/import closure, content hashes,
private artifact exclusion, unchanged v1 data, corruption and old-schema rejection.
Source archive/wheel and independent review evidence are recorded alongside the
frozen review artifact, not asserted by this source note.

No fresh browser, display, listener, geocoder, router, provider, native, Spark, auth,
credential, security configuration, push, merge, deployment or publication action
was performed. Prior preview approval expired and its listener is cleaned up. This
source and DOM-fixture coverage does not establish visual/mobile/browser acceptance
or performance against a complete real native5 catalog. The real optional mapping
is still partial and separately reviewed; missing facts have not been invented.
