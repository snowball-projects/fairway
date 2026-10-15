# Native5 production preparation

This is a reversible local source candidate. It does not adopt the proposed
schema, replace revision758, publish data, refresh API/UI consumers or perform
routing. The native5 SQL resource is byte-identical to reviewed DDL SHA256
`ab852cff6180dba03c4d7f780b2aded18ea962ed0664808887698c9cd78a34c6`.
There are no new columns or constraints in this source slice.

## One clean native path

`catalog_native.py` creates only new empty native5 databases and provides guarded
transactions, scoped source admission, checks and portable snapshot/recovery.
`catalog_native_read.py` reads explicit native5 columns and SQL observation views.
`catalog_native_export.py` emits public read transport version2/schema5.
`catalog_native_common.py` contains only version-independent scalar/storage guards;
`catalog_sources.py` retains the independently reviewed resource/hold logic.
No production module imports the old reader, importer, mapper or legacy catalog.

All commands require an explicit database path. Earlier schemas are rejected;
there is no in-place automatic upgrade and no runtime old-schema adapter. The
reviewed one-time mapping remains a separate preparation and is not complete.
Raw retained groups/notes/support and source controls remain in SQLite as evidence,
but do not fill missing operational fields or drive a runtime classifier.

## Intake and sources

The transport envelope is exactly `batch_id`, `sources`, `changes`. Each change
contains exactly `entity`, `id`, `expected`, `values`, `evidence`. Additions require
`expected:null`; updates require the digest of the complete stored native row.
IDs and subject parents cannot move. Batches are transactional, idempotent under
their exact ID/content, and source/row/report/revision writes roll back together.
Preview never commits. A rejected/conflicted report describes staged differences,
not applied facts. Generated text reports distinguish these states explicitly.

New sources use the existing exact ID/URL/license/attribution/controls-reference
shape. Registered resource aliases cannot acquire alternate identities. Existing
sources need same-ID scoped clearance. Blocked and held resources cannot be
cleared through this command; no permission is inferred from a retained citation.

Core, party and source-observation changes use primary
`{source_id,collected_on,status}` evidence. New source observations must have
`origin:new_extraction` and matching source/date/status. Their source must be
currently permitted and outside retained holds. Typed domain records reference
`{observation_id}`; credits reference their event's observation. Exact claim dates,
status, conflict, qualification, license/attribution and subject scope travel with
the typed row. Optional columns are not mandatory enrichment fields.

New held-source promotions are not ordinary intake. A correction of an already
typed retained domain row may use the separate preservation-only evidence shape:
`{origin:retained_normalization,observation_id,observation_digest,review_reference}`.
It requires the complete existing-row guard, the unchanged existing retained
envelope and its full digest, and a saved correction review reference. It cannot
add records, move subjects, replace source envelopes, create retained envelopes,
clear sources or invent claim dates. Original NULL source/date/status context and
holds remain in place. This path does not parse retained JSON into runtime facts.
Semantic correctness still requires the sole writer's reviewed source comparison.

Source observations are immutable through this importer. A newly sourced claim
uses a new observation. Raw fact-group mutations are not a native5 catalog API.
Quality-rating population remains explicitly deferred. Booleans require JSON
true/false/null, numeric fields require finite JSON numbers, integer counts remain
integers, and exact CHECK/foreign-key/scope constraints enforce the reviewed DDL.

## Read contract

Use `query_facilities(path,...)` or `query_courses(path,...)` from
`catalog_native_read`. Limits are1..1000; offset is nonnegative. Count, rows,
children, observations and revision share one read transaction. Queries support
literal escaped text/alias search, state/country/county/access, physical-hole,
bbox including the antimeridian, and center/radius filters. Course queries also
support style, documented round length, planning and explicit identity filters.
Course-only filters cannot silently alter facility semantics. NUL search rejects.

The stable facility/course IDs, honest nullable names, address inheritance,
override/suppression, separate map and canonical arrival, physical/round holes,
qualified facility estimate and shared destination aliases remain explicit.
NULL access means unconfirmed, never restricted. Empty facilities do not acquire
synthetic courses. Retained component/needs_review identities remain qualified.

Planning preserves the already reviewed policy: explicit ordinary-visitor true
qualifies; explicit false does not; public with unknown booking fact has the
separate preliminary `accepted_public_play_with_qualification` basis. The nullable
booking fact stays NULL. Nonpublic/unknown access does not become public, and
reciprocal-only qualifications never get classified by text. Availability is NULL.

Every `optional` object has all ten exact domain names, with arrays of SQL rows:
physical_characteristics, amenity_observation, practice_observation,
service_observation, policy_observation, operating_period,
accessibility_observation, price_observation, architecture_event, quality_rating.
An empty array means no recorded observation; NULL fields mean unknown. Facility
observations stay on the facility. Course observations stay on the course.
Documented components and rounds each carry their own observations. There is no
facility-to-course attribute inheritance. Architecture events contain all explicit
credits, including unknown roles/years. Multiple claims/conflicts are not reduced
to a first, cheapest or newest winner. Prices preserve the full recorded product,
amount-kind, currency/basis/unit, audience/residency, day/time/effective and
prerequisite qualifiers; no live/current-price sorting is invented.

The SQL views supply source_id/source_url, collection/observation/effective dates,
status/conflict/qualification and original source license/attribution. They do not
expose retained pointers or private source-control documents.

## Public transport and release boundaries

Version2 includes facilities, courses, deduplicated destinations, unchanged
component/round/member/tee/alias relationships, explicit SQL source registry and
note IDs, public intake metadata and preserved source-license metadata. Raw note
bodies remain private retained evidence in SQLite; they are not parsed, rewritten
or exposed as operational fields. Typed operational text remains unchanged. Source
intake decisions and private control/capture pointers are excluded. Raw groups,
retained payloads, correction proof bodies and arbitrary filesystem paths are not
public operational data. Absolute POSIX, drive-qualified Windows, UNC and file-URI
tokens in public values or keys cause export rejection rather than leakage.

Export requires a closed checksummed native5 file with no WAL/SHM/journal sidecars.
A single read transaction covers both resources and all children/provenance.
The file hash/inode/size/mtime are checked before and after. Output must be new;
staged bytes are fsynced, and the complete manifest is moved last. An interrupted
directory without its manifest is not a release; ordinary failure removes only
that newly created output. Gzip has a deterministic timestamp/OS header.

The frozen frontend version1/schema4 reader deliberately rejects this transport.
It needs a separate version2 successor and its own validation, especially NULL
access, typed rendering, empty arrays and exact subject scope. The existing API,
admission fix, providers, source schemas001..004, reviewed normalizers, authority758,
serving374/758 and public assets are unchanged. No automatic consumer fallback is
introduced. The synthetic fixture under tests/fixtures/native5-production is
non-authoritative and exercises all four subject scopes and honest unknowns.

## Local commands

Use `python scripts/native5_catalog.py --db /explicit/new.sqlite create`, then
`import batch.json --report report.txt` for a rollback preview. Only an explicit
`--apply` commits. `check`, `courses`, `facilities`, `clear-source`, `snapshot`,
`restore` and `export` use the same explicit path. Restore requires the expected
SHA256 of a trusted private SQL dump. Export requires its closed binary SHA256
and exact revision. None starts a service or performs publication.

## Remaining mapping work

`remaining-family-inventory.json` accounts for all eleven existing modules against
the frozen aac9d541 ledger. Root keys and nested cells are overlapping accounting
units, not a percent of all facts. The coordinator's13 exact alias/type rules cover
51 pre-guard root candidates and32 contextual cases; they are not implemented by
this source slice. Prices and architecture remain substantial separate families.
FL43/44 are also still proposed: typed optional binding, ordinary scoped controls,
current semantic/absence guards and actual transactional previews remain. No raw
payload retention is claimed to complete their standardization or adoption.
