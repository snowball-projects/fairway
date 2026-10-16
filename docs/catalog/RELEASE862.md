# Catalog release 862

This native5/format2 projection comes from the sole writer's selected closed
revision 862. SQLite remains the maintained authority. The private database,
recovery SQL, retained evidence and controls are not public build inputs.

- Closed binary/release key: `51e8bdcd5a86f57a9c72e816e8db21c96436e1f61cda1faefaac851f7d91bd07`.
- JSON: `690071903e8e92f8746008c8927399a94152e889f08bd7e1144c117857473140`, 35,785,323 bytes.
- Gzip: `3332f404c4719e3231369ce4f42e82ec5411cda6e5bf11bcbde0a6fbcc17898f`, 3,766,047 bytes.
- Manifest: `1e857801579dda1422dab2fdc69eae72660d375b54f579e95370e7578098c214`.
- Inventory: 7,430 facilities, 4,437 courses, 2,676 shared destinations,
  588 rounds and 2,700 tee sets.
- Preserved observations: 4,826 typed domain rows, including 2,115 price observations
  with their recorded conditions, and 8,286 note IDs without note bodies.
- Map context remains 4,640 facilities on the map and 2,790 not yet mapped.

Compared with release 856, six complete reviewed batches add 101 supported course
identities at 96 existing facilities. No facilities are added and no old business
rows, source-policy cells or private controls are changed. All 4,336 earlier course
DTOs remain exact. All 540 scoped holds remain preserved. Later intake is excluded.

The 101 retained ledger entries preserve unknown historical collection dates.
Primary source references are recorded for 31 additions and remain unknown for 70.
Eight new course names remain unknown; individual hole totals retain their exact
recorded values or NULL. Access and nonmember booking are not inferred.
Reconciliation does not promote inventory completeness, style or canonical arrivals.
Course inventory remains separate from components, scoring rounds and tee sets;
property points remain qualified map context.

This update changes generated data and release identity documentation/tests only.
All runtime code, the native schema and exporter, browser validation and performance
reuse, pin selection, course pills, filters, labels, Pages and Data credits generation
remain unchanged from the published PR29 merge. Source qualifications and all 22
public credit notices are retained. Public driving-time comparison and the separate
API test catalog remain unchanged.
