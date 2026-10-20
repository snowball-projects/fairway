# Unfinished offline planning handoff

This draft extracts the latest local logical-session consumer from the five
overlapping DTO/planning/transport worktrees. Its base is the PR15 source at
95701a1, not current production main. It does not connect a real API, replace
Pages, change source data or prove real routing/cancellation behavior.

The selected slice includes the later preparation DTO/session validation,
native browse/price corrections, reserved private transport, logical session
transport and controller, and their existing tests and bounded fixtures. Earlier
whole-interface copies are superseded by this slice and are not duplicated here.
Original worktrees remain intact. The separate progressive-results experiment
and unmapped-course facts dialog have their own draft branches.

The fixture protocol, caller authorization and completion attestations are fake
test seams. They are not server authentication, native ownership or trustworthy
engine-stop evidence. Fixture catalog windows are historical examples, not an
editable data authority or the current catalog. No credentials or source capture
bodies are included.

Start with docs/immutable-planning-contract.md and
docs/native-transport-review-correction.md. Other copied design notes describe
their original review chronology; old release and branch identities in them are
historical. Contributors must reconcile this design with current main and the
new editable dataset before any integration or deployment.

Run the supplied Node unit tests for catalog-read-native, planning-session,
preparation-dto, preparation-session, preparation-api-fixture, private-transport,
logical-transport and logical-planning-session. Browser scripts are supplied but
were not executed as part of this migration. No feature completion is claimed.
