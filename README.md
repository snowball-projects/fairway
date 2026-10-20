# fairway

fairway explores golf facilities and helps a group find nearby courses. Software by
snowball; catalog and third-party data retain their separate licenses.

The public interface provides map browsing, search, a single adjustable Courses
drawer, radius selection and filters. Plan a Round fits the map around addresses
committed with Enter or blur and selects courses near the current origins.
**Driving-time comparison is unavailable.** This release connects no routing
transport, provider, modo or Spark calculation to the public interface.

The catalog comes from the sole writer's reviewed SQLite release. The browser reads
an immutable generated projection, with explicit facility, course, component and
round scopes. Unknown values remain unconfirmed. Prices are dated observations
with their recorded conditions, not current quotes. Tee difficulty is separate
from quality ratings, which are not supplied. Public note provenance contains IDs;
retained note bodies and private evidence stay outside browser assets.

See [catalog authority and release identity](data/README.md), the
[public contract](PUBLIC-CATALOG-CONTRACT.md), and [service policy](SERVICE.md).

For an independent review of the published data, code and verification limits,
start with the [reviewer map](docs/catalog/REVIEW.md). The public generated artifact
is sufficient to inspect the website's complete catalog without the private SQLite.

## Build and verify locally

Python 3.12+ and Node 24+ are required. CI runs the application checks on Python
3.12 and 3.13. Building static assets starts no server and
needs no private SQLite database, provider credentials or network requests:

```sh
python scripts/build_pages.py --check
python scripts/build_pages.py --output /tmp/fairway-pages --commit COMMIT
node --test --test-isolation=none tests/*.test.mjs
PYTHONPATH=src:tests python -m pytest -q
```

The output directory must be new or empty. The builder validates compressed and
uncompressed hashes, release identity, public projection and row counts before
writing a hash-named JSON asset. Decompression stops at the declared raw size
plus one sentinel byte, with a 64 MiB raw ceiling. The browser validates complete
relationships and scoped observations. CI checks both and compares two static builds byte for byte.
The builder also derives a hash-named initial map/search index from those same
verified bytes. It preserves facility identity, location, city/state search and
catalog counts. Opening Courses, Plan a Round or a pin loads the complete catalog
on demand; filters, course relationships and observations use its existing full
validation. The initial manifest stays pinned for that page, so a deployment
between map and detail requests cannot mix releases. Hash-named responses may use
the HTTP cache but always undergo checksum verification.

Pages entry points also use content-hashed JavaScript, module and stylesheet
filenames. The builder rewrites the complete static import graph and records it
in `deployment.json` as `ui_assets`, so reloading fresh HTML cannot reuse older
cached UI code. Original source URLs remain compatibility aliases.

The browser reads response streams with a 16 KiB manifest limit, 4 MiB initial-map
limit and 64 MiB complete-catalog limit. Each load has one 30-second deadline
covering its network requests and body reads.
Oversized, stalled or cancelled streams fail closed. There is no legacy schema
adapter or automatic fixture fallback.
See [measured initial-map performance](docs/initial-catalog-performance.md) for
conditions, timings and the deferred-detail tradeoff.

For isolated regression work, `--review-fixture` selects the exact pinned synthetic
fixture and visibly labels every resulting page. It never substitutes for the
committed release in a normal build. Historical consumer preparation and source
clearances remain documented under `docs/catalog/native5-ui/`.

## Existing calculation API

`src/fairway/app.py` and its bounded eight-course Chicago snapshot remain separate.
The unfinished private national API prototype (PR15) is separate work and has
not been adopted as a public routing service. Pages does not contact either API.
Existing provider configuration and `render.yaml` are unchanged. Running or testing that API does not enable national browser routing.

## Release identity

`.github/workflows/ci.yml` assembles and publishes Pages from main. Check its
`deployment.json` for the deployed software commit, catalog revision, release key,
and payload checksum. The Python package version (`0.6.3` in `pyproject.toml` and
`uv.lock`) identifies the separate software package, not a catalog revision or
proof of deployment. Unreleased software fixes are recorded in `CHANGELOG.md`;
version 0.6.3 is [released](https://github.com/snowball-projects/fairway/releases/tag/v0.6.3).
Catalog integration and release publication are coordinated with the release owner.

## License

Original software is MIT. OpenStreetMap-derived data remains subject to ODbL and
attribution. Public source licenses, policies and scopes travel with the native
transport. The map’s Data credits link opens their generated attribution, license,
source, scope and change notices. Leaflet is BSD-2-Clause;
Census geometry is public domain. See LICENSE and THIRD-PARTY-NOTICES.md.
