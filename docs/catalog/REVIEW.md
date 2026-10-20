# Independent catalog review

The website's complete catalog is already available in this repository. A reviewer
can inspect and validate its public facts without the private SQLite database,
retained captures or a database migration. Work in a cloud checkout; no always-on
server, credentials or new service is required.

## Start here

- `data/catalog-release/manifest.json` pins revision 1163, schema 5, format 2,
  database release key, facility/course/destination counts and raw/gzip hashes.
- `data/catalog-release/catalog.json.gz` is the complete JSON consumed by the
  website, including facts, relationships, scoped observations and public
  source/license metadata. Decompress with `gzip -dc` or Python's standard `gzip`
  module. JSON is generated output, not an editing authority.
- [Public contract](../../PUBLIC-CATALOG-CONTRACT.md), [data authority](../../data/README.md),
  [service behavior](../../SERVICE.md) and [release accounting](RELEASE1163.md)
  explain scope, unknowns, source notices and public routing limits.

## Trace the implementation

| Concern | Entry points |
| --- | --- |
| SQLite layout and integrity | `src/fairway/catalog_schema/native5.sql`, `catalog_native.py` |
| Import preview, row guards, transaction and source checks | `catalog_native.py`, `catalog_sources.py`, `scripts/native5_catalog.py` |
| SQL-to-public projection and redaction | `catalog_native_read.py`, `catalog_native_export.py` |
| Static assembly, checksums and content-hashed assets | `scripts/build_pages.py` |
| Complete browser validation and reads | `src/fairway/static/public-catalog.mjs`, `optional-facts.mjs`, `catalog-read.mjs` |
| Regression and preservation coverage | `tests/test_catalog_native5*.py`, `test_retained_*inventory.py`, `test_build_pages.py`, `tests/*.test.mjs` |

Python module paths in the table are under `src/fairway/` unless shown otherwise.
The schema in this draft contains the proposed `citation` table rather than the
old ledger tables. Revision 1163 still contains its historical `provenance.intake`
array; no user-facing function consumes those entries. The draft exporter emits
only core citation bindings alongside existing sources and IDs-only notes. Source
URLs, collection dates, statuses and license meaning remain available. The draft
browser accepts revision 1163 and does not require or retain its unused ledger.

## Reproduce checks

With Python 3.12+, Node 24+ and locked test dependencies installed:

```sh
uv sync --extra test --locked
python scripts/build_pages.py --check
node --test --test-isolation=none tests/*.test.mjs
uv run --locked python -m pytest --strict-markers
python scripts/build_pages.py --output /tmp/fairway-review
```

The builder validates manifest identity, hashes, bounds and counts. Python
integration tests build the real release twice and compare every byte. Browser
tests validate the complete public contract and factual regressions. SQLite
import/export tests use synthetic databases to exercise source binding, NULLs,
transactions, invalid inputs and private-material rejection. The separate legacy
API tests use its existing verified road snapshot; see [verification](../verification.md).

## What the public artifact cannot prove

It shows exactly what the website receives. It cannot establish that every source
claim was transcribed correctly, that every private SQLite fact was exported, or
that retained private material was classified correctly. The manifest's source-DB
hash identifies a file but does not make that file available. Testing an export
against the actual populated source database and verifying migration preservation
require that database or the owner's supervised evidence. Those are additional
checks, not prerequisites for independent review of the public artifact and code.

This draft changes no production artifact, publishes no dataset and enables no
feature, merge or deployment.
