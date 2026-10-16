# Catalog release 872

This native5/format2 projection comes from the sole writer's selected closed
revision 872. SQLite remains the maintained authority. The private database,
recovery SQL, retained evidence and controls are not public build inputs.

- Closed binary/release key: `d40ca0c712a44b4c5f753bcedf8ccb39067041874fdbda0f72e2c3c553198b32`.
- JSON: `a73c39bba30c97a4f34b206713ebf2e4c2872eeda986cd0f61efcafed5efcc4b`, 36,043,959 bytes.
- Gzip: `fe7ca9c21157640477a4e3a23ec4eba7d173ce9e354cb6042ac6afefbd27904f`, 3,793,064 bytes.
- Manifest: `a86b1012bff4675c046a60fa0de5b017b5825eebdf13e144510fc3031e04334a`.
- Inventory: 7,430 facilities, 4,544 courses, 2,747 shared destinations,
  588 rounds and 2,700 tee sets.
- Preserved observations: 4,826 typed domain rows, including 2,115 price observations
  with their recorded conditions, and 8,286 note IDs without note bodies.
- Map context remains 4,640 facilities on the map and 2,790 not yet mapped.

Compared with release 862, ten complete reviewed batches add 107 supported course
identities at 107 existing facilities. No facilities are added and no old business
rows, source-policy cells or private controls are changed. All 4,437 earlier course
DTOs remain exact. All 540 scoped holds remain preserved. Later intake is excluded.

The 107 retained ledger entries preserve unknown historical collection dates.
Primary source references are recorded for 18 additions and remain unknown for 89.
All added course names are recorded; individual hole totals retain their exact
recorded values or NULL. Access and nonmember booking are not inferred.
Reconciliation does not promote inventory completeness, style or canonical arrivals.
Course inventory remains separate from components, scoring rounds and tee sets;
property points remain qualified map context.

This update changes generated data and release identity documentation/tests only.
All runtime code, the native schema and exporter, browser validation and performance
reuse, pin selection, course pills, filters, labels, Pages and Data credits generation
remain unchanged from the published PR30 merge. Source qualifications and all 22
public credit notices are retained. Public driving-time comparison and the separate
API test catalog remain unchanged.
