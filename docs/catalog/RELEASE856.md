# Catalog release 856

This native5/format2 projection comes from the sole writer's selected, independently
reviewed closed revision 856. SQLite remains the maintained authority. The private
database, recovery SQL, retained evidence and controls are not public build inputs.

- Closed binary/release key: `c02070da6b113c431cd463cfb85d0ff7bcfd0524ab8706af9c756a10c754b6ef`.
- JSON: `d13bc28d5f8c076a1c46ff5a325bff922a1166571ed1a15cde6ebe632c68d594`, 35,554,455 bytes.
- Gzip: `17667b41b428dddb400aeeb47b3df7361fe6ce2bf954a92143098772475920a6`, 3,742,946 bytes.
- Manifest: `4aadd9a0a396273257296454d8c1222ac9ed401f3b27015bb298e939924cfbf0`.
- Inventory: 7,430 facilities, 4,336 courses, 2,640 shared destinations,
  588 rounds and 2,700 tee sets.
- Preserved observations: 4,826 typed domain rows, including 2,115 price observations
  with their recorded conditions, and 8,286 note IDs without note bodies.
- Map context remains 4,640 facilities on the map and 2,790 not yet mapped.

Compared with release 850, six complete reviewed batches add 102 supported course
identities at 98 existing facilities. No facilities are added and no old business
rows, source-policy cells or private controls are changed. All 4,234 earlier course
DTOs remain exact. All 540 scoped holds remain preserved. Later intake is excluded.

The 102 retained ledger entries preserve unknown historical collection dates.
Primary source references are recorded for 9 additions and remain unknown for 93.
Three new course names remain unknown; individual hole totals retain their exact
recorded values or NULL. Access and nonmember booking are not inferred.
Reconciliation does not promote inventory completeness, style or canonical arrivals.
Course inventory remains separate from components, scoring rounds and tee sets;
property points remain qualified map context.

This update changes generated data and release identity documentation/tests only.
All runtime code, the native schema and exporter, browser validation and performance
reuse, pin selection, course pills, filters, labels, Pages and Data credits generation
remain unchanged from the published PR28 merge. Source qualifications and all 22
public credit notices are retained. Public driving-time comparison and the separate
API test catalog remain unchanged.
