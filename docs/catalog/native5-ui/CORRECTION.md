# Three independent consumer findings corrected

This successor preserves rejected candidateb3ab9528e8433b4d3a40d5985796f262af41e935
and its frozen packet. The correction changes only optional-facts.mjs, targeted
JavaScript regressions and these review notes. Writer203fcd4, SQL, exactaf80563
fixture, runtime/data/config and all existing public UI behavior remain unchanged.
It does not adopt a schema or real export.

The source_observation SQL status is nonnullable retained/extracted/confirmed.
The consumer now accepts retained and rejects missing/null/unknown statuses.
A retained row can still have NULL source/date fields; its qualification/conflict
and recorded status are preserved. No retained body or raw field is interpreted.

Every row with one observation_id now shares an exact public source envelope:
source ID, URL, license, attribution, collected/observed/effective dates, status,
conflict and qualification. Equality is checked across all domains and subjects,
including repeated shared-round views. Two independent typed rows can share an
observation without sharing operational values, but cannot silently change its
provenance or suppress its conflict warning.

The round_scope_violation SQL rule also binds a course-owned round to that exact
course or its components. Same-facility membership alone is insufficient. The
consumer applies both conditions. Facility-owned documented combinations remain
valid across courses; valid course-owned component rounds also remain valid.

Targeted positive and negative tests include all exact statuses, NULL retained
source/date context, every public shared-envelope field, consistent alternate
source binding, valid course-owned components and same-facility foreign course or
component membership. Existing independent reproductions are replayed separately,
and test sensitivity is measured against the unchanged rejectedb3ab source.

Author source:273Python/133JavaScript pass. The frozen correction packet records
extracted builds/replay and test evidence. Independent correction retest is required;
these author results do not clear the findings. Nas layout confirmation, remaining
mapping, approved real export, browser/mobile/performance acceptance and publication
remain separately gated. No browser/listener/provider/native/Spark or publication
operation is introduced.
