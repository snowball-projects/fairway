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

## Build and verify locally

Python 3.12+ and Node are required. Building static assets starts no server and
needs no private SQLite database, provider credentials or network requests:

```sh
python scripts/build_pages.py --check
python scripts/build_pages.py --output /tmp/fairway-pages --commit COMMIT
node --test --test-isolation=none tests/*.test.mjs
PYTHONPATH=src:tests python -m pytest -q
```

The output directory must be new or empty. The builder validates compressed and
uncompressed hashes, release identity, public projection and row counts before
writing a hash-named JSON asset. The browser validates complete relationships and
scoped observations. CI checks both and compares two static builds byte for byte.
There is no legacy schema adapter or automatic fixture fallback.

For isolated regression work, `--review-fixture` selects the exact pinned synthetic
fixture and visibly labels every resulting page. It never substitutes for the
committed release in a normal build. Historical consumer preparation and source
clearances remain documented under `docs/catalog/native5-ui/`.

## Existing calculation API

`src/fairway/app.py` and its bounded eight-course Chicago snapshot remain separate.
Pages does not contact that API. Existing provider configuration and `render.yaml`
are unchanged. Running or testing that API does not enable national browser routing.

## License

Original software is MIT. OpenStreetMap-derived data remains subject to ODbL and
attribution. Public source licenses, policies and scopes travel with the native
transport. The map’s Data credits link opens their generated attribution, license,
source, scope and change notices. Leaflet is BSD-2-Clause;
Census geometry is public domain. See LICENSE and THIRD-PARTY-NOTICES.md.
