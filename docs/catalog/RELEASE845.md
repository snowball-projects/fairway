# Catalog release 845

This native5/format2 projection comes from the sole writer's selected, independently
reviewed closed revision 845. SQLite remains the maintained authority. The private
database, recovery SQL, retained evidence and controls are not public build inputs.

- Closed binary/release key: `610f0f8ea5edc8e28c0ce6edc44a43e741f6fb6eae0c36f27acd4e495ea71a5b`.
- JSON: `c1b2a42691074efc21320aff23fad8b8d78c6e34d33d43b95cd6dd0cfe1a792c`, 35,072,008 bytes.
- Gzip: `0074a78f23030ac6c5b582c9d57aed40522b931c78c50de64221b3e2ca70ff23`, 3,692,942 bytes.
- Manifest: `d58db9d14c6d33f22498b89fdef814f25b439690c6f74f0b00113dd4ba435893`.
- Inventory: 7,430 facilities, 4,131 courses, 2,538 shared destinations,
  588 rounds and 2,700 tee sets.
- Preserved observations: 4,826 typed domain rows, including 2,115 dated prices
  with their recorded conditions, and 8,286 note IDs without note bodies.
- Map context remains 4,640 facilities on the map and 2,790 not yet mapped.

Compared with release 840, five complete reviewed batches add 98 supported course
identities at 95 existing facilities. No facilities are added and no old business
rows, source-policy cells or private controls are changed. All 4,033 earlier course
DTOs remain exact. All 540 scoped holds remain preserved. Later intake is excluded.

The 98 retained ledger entries preserve unknown historical collection dates.
Primary source references are recorded for 26 additions and remain unknown for 72.
Unknown course names, hole counts, access and nonmember booking remain unknown.
Reconciliation does not promote inventory completeness, style or canonical arrivals.
Course inventory remains separate from components, scoring rounds and tee sets;
property points remain qualified map context.

This update changes generated data and release identity documentation/tests only.
All runtime code, the native schema and exporter, browser validation and performance
reuse, pin selection, course pills, filters, labels, Pages and Data credits generation
remain unchanged from the published PR26 merge. Source qualifications and all 22
public credit notices are retained. Public driving-time comparison and the separate
API test catalog remain unchanged.
