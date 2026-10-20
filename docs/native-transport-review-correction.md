# Separate native transport review correction

Base: frozen local review ZIP6e1a7667129b22d93580a629fc69e188d1fc7cea936ccb1d8a858fc387a00427,
40-source manifest009c18e1c90febb91c14bb4e6e784a4e6c79392ff30698027536f01e61168566.
The original ZIP, source worktree, native query/preparation fixture bytes and
source-only Library item remain unchanged. This correction lives in a separate
worktree, fairway-native-correction.

Four independent P2 findings are corrected before observer/UI publication:

- Snapshot restart tokens must be nonnegative safe integers at least as new as
  the currently bound token, including successive restarts. Event token67 cannot
  restart at17;67 to68 to67 also fails. Rejection occurs before an older snapshot
  is read or painted, with no additional POST or admission release.
- Fake terminal evidence is validated before onRead or the final snapshot GET.
  Invalid native_admission_released, reservation clear or evidence basis never
  reaches the observer. A valid terminal followed by observer failure retains
  observer_failed/unknown semantics. This is still an offline fake seam, never
  real native completion proof.
- The current comparable-price helper chooses the latest eligible observation
  set before checking its conflict flags. A newer conflicting fee returns null,
  without resurrecting an older scalar. An unrelated basis/course does not
  suppress another comparison. Price sorting remains deferred in the UI; no
  price data or source facts were added.
- Sources and qualifications opens the current native revision/qualification
  context and supplied scoped source observations. No retired static exports
  are linked in the footer, progress dialog or noscript copy. History/downloads
  missing from the native interface are visibly unavailable. All-access native
  map copy replaces the retired public-only map requirement.

Exact regressions are in private-transport.test.mjs, catalog-read-native.test.mjs
and native-catalog-browser.mjs. The supplied reviewer transport and price probes
were rerun with path changes only: rollback/bad terminal produce zero observer
calls and one POST each; conflicting fee is null. Browser provenance checks click
the actual footer control, inspect native revision21 qualification and unavailable
history, and verify no old export requests or static fallback links. Existing
progressive and all four prior DTO rejection flows remain covered.

76 full JavaScript tests and61 packaged consumer tests are expected in this
correction; results are recorded in the correction package. Source and packaged
native/progressive/rejection harnesses use loopback only, with external/API calls
blocked. Screenshots remain local evidence, excluded from Library copies.

Real binding, browser authorization, server ownership/snapshot assembly, catalog
dependency cutover, continuation accounting and measured performance remain
pending separate work. No publishing/push/PR/Spark/provider/geocoder call, API or
catalog source edit, source clearance, new metadata research or dependency change
is included. The independently reviewed original remains available for exact
comparison, including its known findings; only the new correction is proposed
for independent retest.
