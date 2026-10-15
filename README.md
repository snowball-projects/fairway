# fairway

fairway explores golf facilities and helps a group find nearby courses. Software by
snowball; catalog and third-party data retain their separate licenses.

## Isolated native5 consumer preparation

This branch prepares the version2/schema5 browser consumer from reviewed frontend
830bce4 using the writer's exact synthetic fixture. It has not adopted a new schema,
replaced the unchanged revision758/schema4 data or been published. See
[scope, pins, review build and remaining gates](docs/catalog/native5-ui/REVIEW.md).
Production layout confirmation, source review and approved real export are pending.

Facility, course, component and round optional observations remain independently
scoped. NULL values remain unconfirmed; prices are dated observations with all
recorded conditions, and tee difficulty is separate from deferred quality ratings.
Shared observation metadata and course-owned round scope are checked against the
pinned SQL contract. Public note provenance contains IDs only; retained evidence bodies remain private.

The existing map, single Courses drawer and committed-origin behavior remain.
**Driving-time comparison is unavailable** in this public path. No routing transport,
provider request, MODO request or fake completion is added.

## Build and verify locally

Python3.12+ and Node are required. The explicit synthetic review build uses stdlib
and writes only to a new output directory; it starts no server:

```sh
python scripts/build_pages.py --check --review-fixture
python scripts/build_pages.py --review-fixture --output /tmp/fairway-native5-review --commit COMMIT
node --test --test-isolation=none tests/*.test.mjs
PYTHONPATH=src:tests python -m pytest -q
```

Every review page carries a visible synthetic-fixture banner. The normal production
build intentionally rejects the retained v1 catalog before output. There is no
schema adapter or automatic fixture fallback. Do not edit generated transport or
replace the sole maintained SQLite authority. No raw SQLite/SQL/private controls
enter Pages. Desktop/mobile visual acceptance and real-payload performance remain
separate release gates.

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
