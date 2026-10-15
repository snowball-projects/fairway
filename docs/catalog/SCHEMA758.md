# Actual SQLite schema at revision 758

This is the implemented native version 4 schema, not a proposed schema. The
migrations are [001](../../src/fairway/catalog_schema/001.sql),
[002](../../src/fairway/catalog_schema/002.sql),
[003](../../src/fairway/catalog_schema/003.sql) and
[004](../../src/fairway/catalog_schema/004.sql). All tables are SQLite STRICT.

| Table | Key and relationships | Important typed columns |
| --- | --- | --- |
| `facility` | `id` primary key | Name, state/country/county, address/purpose, physical holes, inventory completeness, access, ownership, setting, operating status, website/booking/contact links, approximate coordinates/kind, website status/date |
| `course` | `id` PK, `facility_id` FK | Nullable name and physical holes; access; nullable ordinary-nonmember eligibility; booking conditions; style; game kind; identity status; status/links; address inheritance/override/suppression; canonical arrival and reference |
| `component` | `id` PK, `course_id` FK | Name, nullable physical holes |
| `round_option` | `id` PK, exactly one facility/course FK | Name, round holes, description |
| `round_component` | `id` PK, `round_id` FK, exactly one component/course FK | Unique ordinal per round, repetitions; same-facility membership enforced |
| `tee_set` | `id` PK, exactly one course/round FK | Name, distance and unit, par, difficulty rating, slope, rated category |
| `alias` | `id` PK, exactly one facility/course FK | Alternate name |

`NULL` means unknown, including boolean, dates, physical holes and units. False
inventory completeness is retained explicitly. Course access is one of
`public/private/restricted/unknown`; facility access may also be null. Styles
are `regulation/executive/par_3/pitch_and_putt/putting`. Obstacle mini golf is a
separate game kind. Identities are `operator_defined/needs_review/component`.
None of these enums establishes current tee-time availability.

Physical facility holes, course holes and round holes are distinct. A tee
belongs to a physical course or a documented scoring round. Distances require
a known yards/metres unit; unknown values stay null. Slope is constrained to
55–155, difficulty rating is a positive number, and rated category is nullable
text. Difficulty rating is not a quality/star rating.

## Optional facts are JSON modules, not fully typed attributes

`fact_group` has primary key `id`, exactly one facility/course FK, source FK,
typed module enum, collection date, extracted/confirmed status, optional observed
and effective dates, and a boolean conflict flag. Its `payload` is JSON-valid
text. The schema does **not** require uniform keys/types inside that JSON.

The eleven modules are access, operations, prices, architecture, turf, mobility,
amenities, practice, services, accessibility and overview. Price payloads can
hold currency, amount/ranges, fee basis, conditions and historical flags.
Architecture payloads hold designer/opening/renovation facts. Amenities contain
only documented claims. These are not separate price, amenity or architecture
tables with standardized columns. Missing keys do not mean false or zero.
Quality/star scores and publisher rankings are not implemented.

## Sources, observations and retained evidence

| Table | Stored data |
| --- | --- |
| `source` | `id` PK, URL, optional license/attribution, intake policy |
| `source_license` | Integer PK and JSON license/attribution/scope metadata |
| `intake_evidence` | Composite PK `(batch_id,entity_type,entity_id)`; source FK, collection date, status, origin and optional JSON preservation proof. Entity links are checked by intake, not polymorphic SQL FKs. |
| `source_hold_scope` | `id` PK, scope kind/key and JSON scoped access/control decision |
| `source_hold` | Historical domain-key hold table; current materialized scopes use `source_hold_scope` |
| `note` | `id` PK and original note text |
| `retained_evidence` | Facility FK/PK and original research/support JSON |
| `retained_document` | Name PK and JSON metadata, history, progress, checklist, migration and subsequent audit/control documents |
| `import_batch` | Stable batch ID PK, digest and JSON transactional report |
| `catalog_state`, `schema_migration` | Current revision and applied native schema versions |

Old and new records share the same canonical typed facility/course tables.
However, much legacy detail remains **only in notes and retained support JSON**.
New optional detail lives primarily in sparse module JSON. The complete dataset
has migrated without losing IDs, evidence or explicit nulls; this does not mean
every old narrative fact has been normalized into the same queryable optional
attribute shape as newly researched facts. Such semantic normalization remains
future work and must preserve original source/date/qualifications.

As a real example, Blackhawk Country Club, CA has a typed facility total of 36
and two sourced operator-defined course records: Lakeside Course 18 and Falls
Course 18. Both have private access and unknown ordinary-nonmember eligibility.
There are no tee rows for this facility, so none are fabricated. Other
facilities' named tees are stored in `tee_set` with their actual scoring scope.

Publication is on hold for the schema discussion. The complete reviewed SQLite
758 candidate and generated native transport remain frozen; no destructive
simplification or additional intake has occurred.
