# Catalog release candidate 758

The migration is complete. SQLite contains the entire accepted PR17 dataset and
all integrated, independently reviewed research through revision 758. Catalog
browsing can ship independently of routing. This document describes a local
release candidate; it does not claim publication or backend deployment.

The frozen data commit is `ab38722743eb05073a6637f78f8f5318ce5be896`, with
independent confirmation recorded at `185b7bd046d4cb138fed1ddc926e1d5d28dd2fbb`.
The native schema is version 4. The reviewed writer is `510f878`; the native
readers remain compatible with the separately reviewed `4f3db754` reader.

## Completeness and unpublished changes

The live Pages deployment and remote main were verified at
`f011e4b8330577613f781a6cc3e32b0a2915beb6`. Its generated catalog SHA256 is
`a555f6c6564ecc10df1420268674423ddce3c5f6acc0f03ccb470fc7ef5e8258`.

| Measure | Live release | Candidate 758 |
| --- | ---: | ---: |
| Facilities | 7,189 | 7,387 |
| Stored course records | 2,969 | 3,641 |
| Documented round options | 0 | 439 |
| Named tee records | 0 | 2,224 |
| Optional sourced fact groups | 0 | 4,794 |

There are **198 genuinely added facility records**, separate from **672 new
course records**. Of the latter, 664 are operator-defined identities, six are
documented components and two remain explicitly `needs_review`. There are 573
new course records at 525 previously listed facilities, and 99 at 86 new
facilities. These counts must not be advertised as 672 newly discovered golf
properties or 672 independently bookable courses.

There are 832 enhanced existing facility scopes, giving 1,030 distinct added or
enhanced scopes when the 198 new facilities are included. This includes new
inventory, optional facts and core changes. Existing core changes affect 65
facility rows and 124 legacy course rows in fields comparable to the live
schema. Another measure, 197 existing courses have facts in the new native core
fields or an explicitly reviewed identity; these measures overlap.

The earlier accepted PR17 checkpoint adds 15 of the 198 facilities. Relative to
that checkpoint, integrated research adds 183 facilities and 672 course records.
All original **7,204 facility IDs and 2,969 course IDs** survive. The exact
archived input, all **8,286 notes**, **17,208 original source IDs/URLs**, licenses,
history, support records, explicit null dates and eight canonical arrivals are
preserved. Every current facility and course row reconstructs exactly from the
accepted migration plus its recorded transactional changes.

There are no arithmetic course splits in the migration. Existing uncertain
identities remain qualified: the candidate contains 843 `operator_defined`,
2,784 `needs_review` and 14 `component` course records. A separate component
table has 27 documented component records. Empty inventories at 4,303 facilities
remain empty, with no synthetic course cards. Physical holes, scoring rounds,
loop components and tee scopes remain separate.

Compared with the live release, 22 missing core map locations were filled and
two existing points changed in accepted PR17. Later research has not promoted
additional core map points or arrivals. One missing core address was filled;
198 new facilities include 145 addresses and no core map points. Another 401
optional location-related groups at 400 facilities retain qualified published
links, coordinates or viewport information. They are not verified entrances.
Unlocated facilities remain searchable/listable and cannot silently gain a pin.

Native core relationships and eleven sparse optional modules cover integrated
access, operations, prices, architecture, turf, mobility, amenities, practice,
services, accessibility and overview facts. Source URLs, collection/observation
dates, extracted/confirmed status and conflict flags remain attached. Unknown
values remain null. Quality scores/ranking badges are not introduced.

FL43's 159 proposed additions are **not in SQLite or this candidate**. Its narrow
identity/unit review passed, but intake remains paused for the release freeze.
Original research transports and evidence are preserved for later intake.

## Reproduction and authority

`data/catalog-research-snapshot.sql.gz` is the portable complete SQLite backup,
SHA256 `ca5ea3ed2c9f7b669dc6c95305e0112d976c5090649ba0a7bd9b72c34dd03852`.
Its uncompressed SQL SHA256 is
`335a8ca7133435df979064615042cad04c0a376844160991974644447b42f2c5`.
Restore it to a new local file with `scripts/sqlite_catalog.py restore`.
The `catalog-snapshot.sql.gz` migration baseline and archived PR17 input remain
immutable recovery/evidence artifacts, not competing editable catalogs.

The closed candidate is 27,267,072 bytes, SHA256
`52ba61ecf5cc89dc5ee7212ec4a284dc3d3ccadf56f6171a108d770d27cf3fa9`.
It uses DELETE journaling, has no WAL/SHM/journal sidecars and is owner-read-only.
Its SQL replay exactly matches the trusted recovery backup. Integrity is `ok`,
foreign-key violations are zero, and the writer was unchanged by preparation.

Generate static native read transport from that closed file:

```sh
PYTHONPATH=src python scripts/export_native_catalog.py \
  --db /private/release/catalog.sqlite \
  --sha256 52ba61ecf5cc89dc5ee7212ec4a284dc3d3ccadf56f6171a108d770d27cf3fa9 \
  --revision 758 --output /new/generated/catalog
```

The output directory must be new. `manifest.json` binds revision, binary release
identity, counts and hashes of `catalog.json` and its deterministic gzip form.
The payload contains existing native facility/course/destination DTOs, all
documented relationships, public provenance and required attribution. It does
not recreate the retired schema-3 catalog. Change facts through controlled
SQLite intake, then regenerate; never edit generated JSON.

The complete database contains retained audit/control documents and original
evidence. Keep it private as the build authority. The public exporter omits
those documents and internal license-control file pointers while preserving
public license, policy URL, attribution and scope. It refuses checksum/revision
changes, sidecars, existing output, or leaked local evidence paths.

The remaining release work is frontend static-adapter/build integration,
independent review of the new exporter/public projection and the assembled UI,
then the parent's publication decision. No routing service, browser SQLite
engine, persistent backend or source-policy relaxation is needed for browsing.
The old eight-course routing projection remains a frozen unrelated runtime
fixture; it must not become the public catalog authority or be regenerated as
an independently maintained catalog.
