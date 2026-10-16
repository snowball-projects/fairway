# Catalog release 850

This native5/format2 projection comes from the sole writer's selected, independently
reviewed closed revision 850. SQLite remains the maintained authority. The private
database, recovery SQL, retained evidence and controls are not public build inputs.

- Closed binary/release key: `f179842e702c687c3395770a344fe4ba9bf3ac42062c5c5c8759c5aba50cd092`.
- JSON: `045eac20f43257c7ddcae6b705a570b1ffacd2efedc4d0592ff0c9455257d352`, 35,322,639 bytes.
- Gzip: `96ec27eff005b2e334d4fa24ff726248996e7e7a54edcf63e30b41a4964e720b`, 3,720,142 bytes.
- Manifest: `b079eb4c70090cdf16cbed7298cda56fec7ea78e977372e7d7bd1238bf14885e`.
- Inventory: 7,430 facilities, 4,234 courses, 2,610 shared destinations,
  588 rounds and 2,700 tee sets.
- Preserved observations: 4,826 typed domain rows, including 2,115 dated prices
  with their recorded conditions, and 8,286 note IDs without note bodies.
- Map context remains 4,640 facilities on the map and 2,790 not yet mapped.

Compared with release 845, five complete reviewed batches add 103 supported course
identities at 93 existing facilities. No facilities are added and no old business
rows, source-policy cells or private controls are changed. All 4,131 earlier course
DTOs remain exact. All 540 scoped holds remain preserved. Later intake is excluded.

The 103 retained ledger entries preserve unknown historical collection dates.
Primary source references are recorded for 28 additions and remain unknown for 75.
Unknown course names, hole counts, access and nonmember booking remain unknown.
Reconciliation does not promote inventory completeness, style or canonical arrivals.
Course inventory remains separate from components, scoring rounds and tee sets;
property points remain qualified map context.

This update changes generated data and release identity documentation/tests only.
All runtime code, the native schema and exporter, browser validation and performance
reuse, pin selection, course pills, filters, labels, Pages and Data credits generation
remain unchanged from the published PR27 merge. Source qualifications and all 22
public credit notices are retained. Public driving-time comparison and the separate
API test catalog remain unchanged.
