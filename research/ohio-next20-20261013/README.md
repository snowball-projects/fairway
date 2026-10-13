# Ohio existing-facility reconciliation

The bounded20 existing-facility cohort produces17 worker-reviewed location
updates and16 explicit public-access updates. It resolves no whole-facility
hole total and adds no facility. Independent/parent integration review remains
with the canonical accumulating PR17 owner; this source-only commit does not
edit the canonical catalog or publish a new PR.

Reference base: `22f8d36cc217bf634b1c3dd848875e00cb418007`. Reference catalog
SHA256: `addd3acbbaa2799ed63f7124f8f36e6b5e7a446a03edbbb19336e0a532a4a2e6`.
The tested separate proposal SHA256 is
`eeb09c093e11284603572326e032f062d7849a648fefdf122f51ad7cf7c33314`.

On that base, applying the scoped delta would retain7193 facilities, increase
mapped facilities4440 to4456, reduce null-coordinate facilities2009 to1992,
and preserve357 unknown totals and565 estimates. Blacklick receives only an
independent licensed property point; its total remains unknown, so it remains
off map. Its existing dated nested public-course evidence is preserved, with no
new owner fact or facility access label.

The delta is `../../data/review-batches/ohio-next20-20261013.json`. Complete
selected ODbL geometry, element versions/tags, original automated flags,
identity decisions and independently reproduced rounded interior points are
in `../../data/source-layers/ohio-next20-properties-20261011.json`.
`county-context.json` records broad independent locality corroboration from
the existing Census2025 1:20,000,000 display outlines, with original source
URLs/checksums and the pinned projection code/file hashes. These generalized
outlines supply no coordinates or cadastral/survey claim. Exact distinguishing
names, compatible course/club identities, official profiles and county context
are considered together; county/proximity or fuzzy scores alone are insufficient.

Tanglewood's operator expressly identifies public golf, while the undated
association profile says Private. Both are retained; no change date or live
operating claim is invented. Reeves remains under its inherited Cincinnati
reuse hold. Twin Lakes' exact Mansfield property is identified, but its Semi
Private classification does not support unconditional Public admission.
Kennsington's missing alias/address binding remains unresolved. All three
facility objects and their research remain unchanged.

Current robots and linked applicable policies were screened before fact
admission. Requests were bounded, with no redirects/retries and at least ten
seconds between same-host reads. `source-controls.json` preserves results and
hashes. The linked Blacklick policy host declared ai-input=no, so no policy
request, alternate route or further owner collection followed; new owner content
is excluded. All previous explicit source holds persist. Raw bodies, normalized
header dictionaries/cookies, and protected prose remain private outside Git.
Original wire framing and duplicate-header fidelity were not captured. No open
license for independent official facts or source-wide permission is asserted.

Prepare a proposal against the owner's inspected fresh canonical source:

```sh
python research/ohio-next20-20261013/apply_delta.py \
  --repo . --output /tmp/ohio-next20-proposal.json \
  --expected-current-sha256 THE_INSPECTED_CURRENT_CATALOG_SHA256
```

The adapter makes no source requests, uses only existing facility UUIDs,
checks identities and before-values, allocates namespaced provenance without
overwriting existing entries, and never writes the receiving catalog. It
preserves all unrelated facilities/research, holes, course inventories,
addresses, counties, arrivals, history and progress. The owner must record its
actual reachable factual integration commit and UTC timestamp, with17 updated
facilities, then revalidate the actual combined head and report order.

Validation used a separate checkout containing the real proposal:229 Python
tests, all three JavaScript suites, schema/export/publication, the verified
63413-vertex/166843-edge/eight-course snapshot, and wheel/source builds passed.
Ruff lint/format passed. `geometry-validation.json` independently reproduces
all17 selected points and checks strict containment/unique objects and hashes.
`semantic-preservation.json` exhaustively preserves every unrelated object,
existing registry value, PR17's earlier seven facilities, history, progress,
county checklist, all physical totals, nested courses and arrivals. These are
candidate checks; canonical integration/history and exact-head CI remain the
owner's next step. Source research is paused at parent request.
