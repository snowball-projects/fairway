-- Nonblank references match documented Python Unicode whitespace handling.
PRAGMA foreign_keys=OFF;
BEGIN IMMEDIATE;
CREATE TABLE course_v3 (
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
 CHECK(arrival_latitude IS NULL OR (arrival_kind IS NOT NULL AND arrival_reference IS NOT NULL AND length(trim(arrival_reference,char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)))>0))
) STRICT;
INSERT INTO course_v3 SELECT * FROM course;
DROP TABLE course;
ALTER TABLE course_v3 RENAME TO course;
CREATE INDEX course_facility ON course(facility_id);
CREATE INDEX course_filter ON course(access,style,physical_holes);
INSERT INTO schema_migration VALUES (3,'canonical arrival references reject Unicode whitespace-only strings');
COMMIT;
PRAGMA foreign_keys=ON;
