# Native5 catalog operations

Nas approved the exact native5 layout, functional preview and publication. This
runbook accompanies the reviewed source and generated version2/schema5 release.
SQLite is the sole editable catalog. Public JSON/gzip/manifest are generated
read transport only. Notes remain private SQLite bodies; public note IDs persist.

Use the adopted private native5 authority path recorded in the writer adoption
receipt. Do not pass an archived native4 database to the native5 command. The
command rejects older schemas. There is no schema adapter or automatic upgrade.

From the repository root, using local Python dependencies:

```
python scripts/native5_catalog.py --db /private/catalog.sqlite check
python scripts/native5_catalog.py --db /private/catalog.sqlite snapshot /private/new-snapshot.sql.gz
python scripts/native5_catalog.py --db /private/closed-release.sqlite export /private/new-generated-output --sha256 EXACT_BINARY_SHA256 --revision 760
```

The last command requires a closed, checksummed release with no WAL/SHM/journal
sidecars. It writes a new directory and places the manifest last. Publish only
its catalog.json, catalog.json.gz and manifest.json via the normal static build.
The earlier scripts/export_native_catalog.py is the retired schema4 transport;
it is not the native5 release command and must not be used for this release.
No mapping implementation, raw controls, research documents, SQL recovery files
or SQLite binary belongs in public source, static assets or Pages.

For subsequent edits, one integration writer backs up the selected native5
SQLite authority, checks current source scopes and complete row guards, previews
one exact batch, applies it transactionally, checks integrity/FKs/scopes, tests
idempotence, and creates a new portable SQL snapshot and human-readable report.
Research workers send proposals; they do not open/write the authority. Preserve
source license/attribution and scoped holds. Missing remains unknown. Observation
dates are distinct from collection dates. Schema changes need their own review.

Recovery uses only the private trusted SQL gzip and its independently pinned
SHA256: `python scripts/native5_catalog.py --db /private/new.sqlite restore
/private/snapshot.sql.gz --sha256 EXACT_SNAPSHOT_SHA256`. Restore refuses an
existing output. Run check and compare whole-table contents/snapshot bytes.
Public rollback selects a previously reviewed generated transport and its matching
consumer; it does not replay research batches or rewrite the writer authority.

This is the native5 source path. Historical native4 code remains only for frozen
recovery/history; it is not a compatibility fallback. API/provider/admission,
routing, deployment and authentication behavior are outside this catalog change.
