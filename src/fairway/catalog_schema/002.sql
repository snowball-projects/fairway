-- Forward SQLite migration. The frozen v1 snapshot is not edited.
PRAGMA foreign_keys=OFF;
BEGIN IMMEDIATE;
CREATE TABLE course_v2 (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facility(id),
 name TEXT CHECK(name IS NULL OR length(trim(name)) > 0), physical_holes INTEGER CHECK(physical_holes > 0),
 access TEXT NOT NULL DEFAULT 'unknown' CHECK(access IN ('public','private','restricted','unknown')),
 nonmember_bookable INTEGER CHECK(nonmember_bookable IN (0,1)), booking_conditions TEXT,
 style TEXT CHECK(style IN ('regulation','executive','par_3','pitch_and_putt','putting')),
 game_kind TEXT CHECK(game_kind IN ('golf','obstacle_minigolf')),
 identity_status TEXT NOT NULL DEFAULT 'needs_review' CHECK(identity_status IN ('operator_defined','needs_review','component')),
 operating_status TEXT, website TEXT, booking_url TEXT, contact_url TEXT,
 address_text TEXT, address_purpose TEXT,
 address_mode TEXT NOT NULL DEFAULT 'inherit' CHECK(address_mode IN ('inherit','override','suppress')),
 arrival_latitude REAL CHECK(arrival_latitude BETWEEN -90 AND 90),
 arrival_longitude REAL CHECK(arrival_longitude BETWEEN -180 AND 180),
 arrival_kind TEXT CHECK(arrival_kind IN ('reviewed_osm_point','verified_entrance')), arrival_reference TEXT,
 location_note TEXT,
 CHECK((arrival_latitude IS NULL) = (arrival_longitude IS NULL)),
 CHECK(arrival_latitude IS NULL OR (arrival_kind IS NOT NULL AND arrival_reference IS NOT NULL AND length(trim(arrival_reference))>0))
) STRICT;
INSERT INTO course_v2 SELECT * FROM course;
DROP TABLE course;
ALTER TABLE course_v2 RENAME TO course;
CREATE INDEX course_facility ON course(facility_id);
CREATE INDEX course_filter ON course(access,style,physical_holes);
CREATE TABLE source_hold_scope (
 id TEXT PRIMARY KEY,
 scope_kind TEXT NOT NULL CHECK(scope_kind IN ('publisher','host','resource')),
 scope_key TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload))
) STRICT;
CREATE INDEX source_hold_scope_key ON source_hold_scope(scope_kind,scope_key);
INSERT INTO schema_migration VALUES (2,'scoped source holds and required canonical arrival reference');
COMMIT;
PRAGMA foreign_keys=ON;
