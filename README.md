# fairway

fairway explores golf facilities and helps a group find nearby courses. Software by
snowball; catalog and third-party data retain their separate licenses.

## Local public release candidate

This branch prepares a SQLite-derived national catalog and the reviewed Courses
interface for GitHub Pages. It has **not been published**. The 758 baseline contains
7,387 facilities and 3,641 retained course records, with explicit unknowns, component
identities, access qualifications and dated source evidence. Typed operational
optional fields are being finalized with the writer; 758 is not a claim that all
historical prose or optional facts have been normalized.

The map, facility/city/state search, single Courses drawer and its keyboard/drag
controls are independent of routing. Plan a Round commits an address only on Enter
or blur, fits origin pins, and selects courses within the chosen straight-line radius
of at least one origin. Manual coordinates stay local. **Driving-time comparison is
unavailable** in this public release path. There is no Rank Courses button, private
routing transport, MODO request or fake completion.

SQLite is the sole maintained authority. The browser loads an immutable generated
native DTO projection bound by SHA256, revision and release identity. No full SQLite,
SQL recovery, private source controls or credentials enter the Pages artifact.
See [data](data/README.md), [public seam](PUBLIC-758-EXPORT-CONTRACT.md),
[actual 758 schema](docs/catalog/SCHEMA758.md) and [service policy](SERVICE.md).

## Build and verify locally

Python 3.12+ and Node are required. Existing locked app dependencies are installed with
`uv sync --extra test --locked`. The static Pages build itself uses Python stdlib:

```sh
python scripts/build_pages.py --check
python scripts/build_pages.py --output /tmp/fairway-pages --commit <git-commit>
node --test tests/*.test.mjs
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m pytest
uv build
```

The writer regenerates the public transport from a closed private SQLite release;
see data/README.md. Do not edit generated JSON/gzip or choose an implicit database.
The source export is 36.6MB raw /4.76MB gzip; fresh desktop/mobile browser acceptance
and payload performance remain release gates. Offline unit tests do not substitute
for those checks.

## Existing calculation API

`src/fairway/app.py` and its bounded eight-course Chicago snapshot remain separate
and unchanged. Pages does not contact that API. Existing private provider keys and
`render.yaml` are not altered by the public catalog work. To run that existing API,
fetch its verified snapshot with `scripts/fetch_snapshot.py`, then run
`gunicorn fairway.app:application`. This does not enable national browser routing.

## License

Original software is MIT. OpenStreetMap-derived data remains subject to ODbL and
attribution. Public catalog source licenses, policies and scopes travel with the
native transport and appear under Sources and qualifications. Leaflet is BSD-2-Clause;
Census geometry is public domain. See LICENSE and THIRD-PARTY-NOTICES.md.
