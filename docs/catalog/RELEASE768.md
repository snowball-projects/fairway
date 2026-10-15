# Catalog release 768

This immutable native5/format2 projection comes from the reviewed closed SQLite
release. SQLite remains the maintained authority; generated files are copied
byte-exact and are never hand edited.

| Item | SHA-256 |
| --- | --- |
| Closed SQLite release | `53c1bf95a165b1869de5fd1dfe743d0ce5b75b8a8f81537f452f431d9139ea4a` |
| Raw JSON | `d231a7c4f3081ffe2984931249909d6319723b9e1066bebe94e855950b88b6f0` |
| Deterministic gzip | `a853f9245dd55e4cc372606601eecb95b57f3728d5df2ee81b6468763fbad428` |
| Source export manifest | `5b58bbf395f1caf94c7789ec89f89a6bba688e5d417cbca6fbcd939010736101` |

The projection contains 7,395 facilities, 3,694 course records and 2,179 qualified
destinations. Raw JSON is 29,661,623 bytes; gzip is 3,099,375 bytes. Browser memory
and validation use the complete decoded projection.

Compared with release 760, the reviewed cohort adds 8 facilities and 12 physical
courses in Nebraska and enriches Bethpage State Park and Airway Meadows across 6
existing course scopes. The new facilities are Sand Hills, Dismal River, CapRock
Ranch, Lost Rail, Firethorn, Omaha Country Club, Happy Hollow and Champions Run.
A completed research pass does not mean every optional column is known.

There are 4,640 native map-context facilities and 2,755 without qualified map context.
The additions do not invent map points or course arrivals. The 8 existing qualified
course arrivals remain unchanged. Source evidence exposes 8,286 note IDs only,
18,455 public source records and 9,853 intake records; typed observations total 3,061.
Facility, course, component and round scopes remain distinct. Unknown names,
amounts, currencies, dates, units, booking facts and architecture roles remain
unknown; dated prices are not current quotes.

Exporter, Pages assembly and browser validation recognize bounded `/ea` notation
only within explicit per-person price conditions. Validation scans a temporary
representation; emitted conditions stay byte-exact. Shared acceptance/rejection
cases cover all three guards, including path suffixes, other fields and keys,
and extra private paths. There is no general slash-path exemption.

Only the generated manifest/gzip are build inputs. No populated database, recovery
SQL, retained payloads or private research controls are public assets. Existing
API/routing fixtures and admission state are unchanged; public planning remains
catalog-only with driving times unavailable.
