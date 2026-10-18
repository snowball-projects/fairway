# Catalog release 1139

This native5/format2 transport selects exactly two admitted completion batches
after released 1124 and one bounded corrective batch. It is a fixed candidate, not a deployment claim. SQLite,
recovery SQL, source controls and retained evidence remain private. Later work and
32 candidate-only contexts are excluded.

- Closed binary/release key: `eb9bd861d0ea89dff89be024cb211893396887202ad9c1eef6b6a0f7f3a4690d`.
- JSON: `9c7699163015cb2397da764e3348adf370453ed8316d69f7819c00124caa57c7`, 37,783,729 bytes.
- Gzip: `f462044cd546cca54e764473ca81e75f253e5d04e10381dd9c880fa76f876501`, 4,013,881 bytes.
- Manifest: `d96c1bf4fbf02af142da185712ad3f962c78a13296ce6060de264e6e0536d3af`.
- Inventory: 7,430 facilities, 4,912 course records and 2,990 destinations.
- Typed inventory: 5,105 optional observations, 2,804 tee/category rows, 594 rounds
  and 2,219 prices. Provenance contains 18,996 source records, 14,816 intake
  projections and the same 8,286 note IDs without note bodies.

The two batches contain 129 reviewed native intents: 113 direct enhancements and
16 supporting source observations. Direct enhancements comprise three new course
identities, eighteen existing business-row updates, 91 typed observations and one
tee row. Provenance, private controls and receipts are not counted again as
features. There are no new facilities.

Tired Creek, Caswell Pines and Space Coast each have an explicit eighteen-hole
course identity. Caswell's public access is directly supported; the other two
retain unknown access. All three retain unknown nonmember bookability, style,
operating status and arrival. Firestone, Kinzua and Sunserra gain supported course
names and identity fields. Kinzua remains six physical holes played three times
for an eighteen-hole round. Sunserra remains nine physical holes with explicit
par-3 style. Carlsbad's existing Regulation course gains regulation style without
changing its separate par-3 course or creating an aggregate course.

Eleven facilities gain contact address components, totaling 48 cells. Existing
full-address text, all coordinates, arrival records and completeness flags remain
unchanged. Tired Creek's 39827/39828 ZIP conflict leaves the new postal component
unknown. Firestone's contradictory structured address and coordinates do not
become a reliable property point. Kinzua's PO box is not a physical address.
Space Coast's new course exposes its preexisting address-range estimate as one
additional derived destination; that unchanged estimate remains unsuitable for
UI map placement and is not an entrance or new coordinate.

Sundale's nonmember window, priority and after-10am conditions remain together.
Madeline requires prior arrangement or an advance tee time and retains island
travel context. Monterey retains weather-dependent operation, recommended tee
times and advance contact for cart staffing. Their explicit nonmember facts do
not establish live bookings, unconditional public access or property-entry
document requirements. Cart-driver qualifications remain cart qualifications.

New observations comprise nine practice, eight service, five amenity, four
physical-characteristic, five policy and sixty price rows. Each stays at its exact
facility or course scope. Prices retain their original age, weekday, holiday,
cart, time, round, product and conflict conditions. The retained-source correction fills 180 supported cells on those same sixty
prices: sixty exact printed amount forms, fifty-two fee classifications, fourteen
weekday masks, nineteen audiences, fifteen age bounds, six holiday flags, five
per-person billing bases and nine cart-inclusion flags. These cells are not new
features. Currency and unsupported classifications or billing bases remain unknown.
Merrill senior prices explicitly exclude holidays and weekends; its weekend and
holiday products include holidays but retain an unknown weekday mask because the
contract does not define mask/holiday OR semantics. Four literal pull-cart products
are not forced into the push_cart enum, and Madeline's Rider Fee is not assumed
to mean nonplaying rider. Source prose, amounts and observation dates stay exact. Cedar's twilight offer is relative
to sunset, not an invented fixed time. A dollar sign alone does not supply an ISO
currency. Madeline's named white tee has 6,026 yards and slope 119; par, rating and
rated category remain unknown. No quality ratings are introduced.

All prior native values and public projections outside the reviewed completion
changes and those 180 price cells remain exact. Existing
optional rows, relationships, licenses, note IDs, source records, intake records
and destinations are retained. Five derived inventory fields advance at nine
parents. The two original batches add 278 private storage rows, including 129 ledgers, two
receipts, twelve sources and twenty-four controls. The correction adds sixty
immutable correction ledgers and one receipt without adding facts or sources. Twelve exact source-workflow cells
advance under their original scoped reviews; all 540 native holds remain exact.
Unknown source terms and licenses remain unknown rather than reuse permission.

Empty documented inventories decrease from 3,168 to 3,165, which does not prove
that the remaining properties lack courses or that any facility is completely
reconciled. Reliable location coverage does not improve: 2,790 facilities remain
unfit for UI map placement, including 563 address-range estimates. Detail and
location enrichment remain incomplete. Unadmitted architecture, party mapping,
hours, complex-price and tee contexts are preserved separately, without importing
the sixty admitted prices a second time.

Runtime, native writer and exporter, PR42 cancellation, loader/privacy bounds,
initial-map derivation, content-hashed UI graph, CI, dependencies and software
version 0.6.3 remain unchanged. New exact manual review, required CI, actual
automatic review, root-authorized merge and postmerge Pages/hosted acceptance
remain separate gates.
