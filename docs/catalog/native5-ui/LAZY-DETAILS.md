# Deferred course details

This separate successor starts from independently clearedb7cf977529b8745d74dcad52d89a9ff51fd9ba85.
That checkout, its reviewed ZIP and the disposable actual725 export audit remain
frozen. No schema, authority, catalog, source qualification, server, routing,
provider, security/config or publication changes are made.

The actual heavy card built2251 elements because courseMetadata constructed its
whole body, including every typed observation field, before its native outer
Course details section opened. Optional observation sections were collapsed but
already existed as nodes. Ordinary browsing did not need those hidden fields.

The minimal change leaves the same details element and summary in place. A native
toggle listener fills the existing body on its first open. Closing before a toggle
is delivered does not populate it. Further toggle events and close/reopen reuse
all children rather than reconstructing them. No click/key handler overrides the
native summary behavior, no asynchronous data fetch is introduced, and the full
validated source object remains intact. The existing rendering body and markup
are unchanged after expansion. This defers the course detail body as one requested
section; nested detail sections retain their current behavior. Facility details
are unchanged.

Regression coverage checks no optional reads or construction while closed, no
construction on closed toggle, first-open exact qualified content, isolated cards,
unchanged source data, the same summary/focus targets, retained children and no
additional work on repeated open/close. Existing source/qualification, drawer and
origin tests remain. The synthetic fixture bytes are unchanged.

Actual frozen725 comparison uses JSON SHA
a20172da2d72a35f615818f29c2ceb429e7f5b86a9a19aa1b0f3daa825d3c5c4
through copied cleared validators, without altering either source/data baseline.
All3641 fully expanded card DOM structures matchb7 exactly and reopen creates no
new nodes. The heaviest collapsed card drops2251 to23 constructed elements;
closed-card maximum is24. National name-order first60 drops3040 to1428 elements.
This is host-only fakeDOM evidence, not browser layout/paint/mobile acceptance.
The28.1MB JSON load and synchronous catalog validation remain separate concerns.

Author affected suite:136 JavaScript tests pass. Full Python/build/package and
independent review evidence is recorded in the separate frozen review packet.
Product/schema approval, real export adoption, fresh browser/mobile acceptance,
real-payload performance and release/publication checks remain separately gated.
