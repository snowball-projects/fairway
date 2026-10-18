# Proportionate verification

CI selects additive scopes from the complete changed-path diff. It always checks
the generated catalog, complete browser contract and browser behavior. Changes to
CI itself, unknown paths, an unavailable/empty diff, or tests alone select full
integration. Renames retain both the removed and added paths.

| Change | Python 3.12 and 3.13 | Distribution checks | Real legacy road/index check |
| --- | --- | --- | --- |
| Catalog only | Catalog foundation and retained factual assertions | Not selected | Not selected |
| Runtime | All remaining Python behavior tests | Wheel CLI and extracted-source Python/Node tests on 3.13 | Once on 3.13 when road/API/index inputs change |
| Packaging | All remaining Python behavior tests | Wheel CLI and extracted-source Python/Node tests on both versions | When road inputs also change |
| Dependencies | All remaining Python behavior tests | Both versions | Once on 3.13 |
| CI, unknown, test-only or uncertain diff | All remaining Python behavior tests | Both versions; also experiment tests | Once on 3.13 |

Runtime includes every `src/fairway/**` path and `scripts/build_pages.py`, including
catalog writers, readers, exporters, schema, loader, renderer and planning code.
Packaging includes `MANIFEST.in`, README and license files. `pyproject.toml` and
`uv.lock` select the dependency scope. Mixed changes accumulate requirements.
Experiments retain their separate suite when their paths or CI selection change.

The catalog-only allowlist is deliberately narrow: generated
`data/catalog-release/**`, `data/README.md`, `docs/catalog/RELEASE*.md`,
`CHANGELOG.md`, `tests/test_catalog_foundation.py` and `tests/test_kansas_delta.py`.
At least one generated artifact must change. A loader test, another test file or
an unknown path makes the change broader. Catalog owners should extend the
dedicated factual assertions when a release changes fields, NULLs or
qualifications; runtime test files cannot silently take this shortcut.

## Production integration runs once

`catalog` runs the two `catalog_integration` tests in `test_build_pages.py`.
Their shared module fixture builds the entire real committed release twice,
compares every output byte, and retains manifest/gzip/raw identity, counts,
default-production selection, deployed-commit identity and complete public
license-notice assertions. The separate browser contract checks every native
relationship, provenance record and optional binding. The full Node suite also
includes current factual/NULL regression assertions and loader/cancellation tests.

The remaining Python tests run on both supported versions for broader changes.
They retain small-fixture publication, hostile public-boundary, bounded gzip,
API/provider, SQL/export and index regressions. Wheel checks compare every package
code/data byte with the checkout before the installed CLI smoke. Extracted-source checks first compare code, scripts, tests
and generated catalog bytes with the checkout, then rerun the behavior tests from
their own locked installation and run Node against packaged assets and fixtures.
The two complete production-build tests already passed in `catalog`;
they are excluded from these repeated runs, not removed from verification.
Running `python -m pytest` locally still includes them.

CI does not call `scripts/build.sh` again after `catalog`: it installs locked
dependencies and fetches the verified legacy road snapshot only for the API tests
that use it. The standalone build script retains its publication-before-install
contract. The final `validate_snapshot.py --course-index ...` already validates
the real graph and baseline matrix, then exhaustively checks the rebuilt index;
the preceding duplicate graph-only invocation is unnecessary.

## Status and release boundaries

The existing `catalog`, `verify`, `verify-python-3.12` and `catalog-experiment`
names remain. The two `verify` checks always execute, report their selected scope
and fail if `catalog` failed or was cancelled. For catalog-only changes they
actually run the factual tests rather than imply that API/package suites ran.
Pages requires successful catalog and verification results. No branch-protection,
ruleset, permission or release-approval setting is changed.

This matters because a conditional or dependency skip can otherwise satisfy a
required check without running it. GitHub recommends `always()` plus a dependency
result check for this case. See [GitHub's required-check guidance](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).

Public CI does not replace the catalog writer's preservation, recovery,
current-guard, hold or admission checks. Root review/authorized merge and
postmerge Pages/live acceptance remain separate. This change edits no catalog
artifact or database and does not enable driving times.

## Measurement

Recent successful runs before this change:

| Run | Total elapsed | Catalog | Longest Python job | Its checkout Python / source archive |
| --- | --- | --- | --- | --- |
| [981 PR, 39095166075](https://github.com/snowball-projects/fairway/actions/runs/39095166075) | 18m 35s | 2m 28s | 16m 01s | 6m 15s / 7m 50s |
| [981 main, 39096361490](https://github.com/snowball-projects/fairway/actions/runs/39096361490) | 20m 41s | 3m 18s | 15m 28s | 5m 55s / 7m 37s |

These are executed historical runs, not results for this patch. Runners differ:
for the same 981 main run, its Python jobs took 15m 28s and 12m 12s.
A local baseline on Python 3.12 took 154.43s for 2,056 tests; 130.11s was spent
in the two tests performing three complete real-release builds. The shared fixture
now needs only two builds, and CI executes that integration once. An unfiltered
local run after this change took 111.55s, including the new scope regressions;
the remaining behavior suite took 24.09s. These same-host measurements do not
predict shared-runner scheduling. The PR records
fresh measured results; no fixed speedup or lower test-count target is promised.

Useful local commands:

```sh
python scripts/ci_scope.py --base BASE --head HEAD
uv run --locked python -m pytest --strict-markers tests/test_ci_scope.py
uv run --locked python -m pytest --strict-markers tests/test_build_pages.py -m catalog_integration
uv run --locked python -m pytest --strict-markers -m 'not catalog_integration'
node --test tests/*.test.mjs
```
