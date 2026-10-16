# Catalog release 818

This immutable native5/format2 export was generated from the sole writer's reviewed
closed revision818. SQLite remains the maintained authority; these JSON/gzip bytes
are generated public build inputs. The private database, recovery SQL, evidence
bodies, review packets and source-control records are not published.

- Closed binary/release key: `867ba77cfe0f995375f8d747c2c1779abdc03b92c610aa2cbf0b7fe328786013`.
- JSON: `c253d381fbf148bcf7e6f60cdb601a3f68fc1f0c26b2c7303204d0d64eb77c8b`, 34,274,761 bytes.
- Gzip: `92dfbf73f73c7a7667b8349339d4493b40139479379fe45f4ff4d544adcc88fa`, 3,610,325 bytes.
- Manifest: `02d96720e901e9dfdc54c8924d4fb2135b80bf0b2825bc5fc643e071a2648b15`.
- Inventory: 7,430 facilities, 3,813 course records, 2,251 shared destinations,
  588 rounds and 2,700 tee sets.
- Typed observations: 4,826 distinct domain rows, including 2,115 dated price
  observations. Prices preserve every recorded condition and are not current quotes.
- Native map contexts: 4,640 facilities on the map; 2,790 not yet mapped.

The final reconciliation cohorts recover 57 actual course identities at 57 existing
facilities, with zero new facilities in those cohorts. They preserve unknown access,
booking and arrival facts and do not promote inventory completeness. Emerald Hill
now links its reviewed actual 18-hole course; its unknown access and booking values
remain unknown. These cohorts follow other reviewed research since release768, so
their 57 rows are not the entire 768-to-818 inventory delta. Later pending proposals
are excluded from this release.

The complete release768-to-818 change adds 35 facilities and 119 course records:
57 reconciled identities and 62 from reviewed discovery and inventory enrichment.
It also adds 1,765 typed domain rows and 57 architecture credits. Those counts do not
mean every record has complete optional facts or that any unknown is now confirmed.

All 8,286 legacy public note IDs remain IDs only. Facility, course, component,
round, tee and source scopes stay separate; empty observations and NULL cells retain
their unknown semantics. No raw evidence or inferred facility-to-course facts fill
missing typed fields. Existing public source licenses and attribution remain on the
generated Data credits page. Routing and the separate private API test release are
unchanged.
