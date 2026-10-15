-- SQLite is authoritative. NULL means unknown, including booleans and dates.
PRAGMA foreign_keys = ON;
CREATE TABLE schema_migration(version INTEGER PRIMARY KEY, description TEXT NOT NULL) STRICT;
INSERT INTO schema_migration VALUES (1, 'local normalized catalog');
CREATE TABLE facility (
 id TEXT PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name)) > 0),
 state TEXT, country TEXT NOT NULL DEFAULT 'US', county TEXT,
 address_text TEXT, address_purpose TEXT,
 physical_holes INTEGER CHECK(physical_holes > 0),
 inventory_complete INTEGER CHECK(inventory_complete IN (0,1)),
 access TEXT DEFAULT 'unknown' CHECK(access IN ('public','private','restricted','unknown')),
 ownership TEXT, setting TEXT, operating_status TEXT,
 website TEXT, booking_url TEXT, contact_url TEXT,
 latitude REAL CHECK(latitude BETWEEN -90 AND 90),
 longitude REAL CHECK(longitude BETWEEN -180 AND 180), location_kind TEXT,
 website_status TEXT, website_checked_on TEXT,
 CHECK((latitude IS NULL) = (longitude IS NULL)),
 CHECK(latitude IS NULL OR location_kind IS NOT NULL)
) STRICT;
CREATE INDEX facility_location ON facility(latitude,longitude);
CREATE INDEX facility_region ON facility(country,state);
CREATE TABLE course (
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
 CHECK(arrival_latitude IS NULL OR (arrival_kind IS NOT NULL AND length(arrival_reference)>0))
) STRICT;
CREATE INDEX course_facility ON course(facility_id);
CREATE INDEX course_filter ON course(access,style,physical_holes);
CREATE TABLE component (
 id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES course(id), name TEXT NOT NULL,
 physical_holes INTEGER CHECK(physical_holes > 0)
) STRICT;
CREATE TABLE round_option (
 id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES course(id), name TEXT NOT NULL,
 round_holes INTEGER NOT NULL CHECK(round_holes > 0), description TEXT
) STRICT;
CREATE TABLE round_component (
 id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES round_option(id), ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
 component_id TEXT NOT NULL REFERENCES component(id), repetitions INTEGER NOT NULL DEFAULT 1 CHECK(repetitions > 0),
 UNIQUE(round_id,ordinal)
) STRICT;
CREATE TABLE tee_set (
 id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES course(id), round_id TEXT REFERENCES round_option(id),
 name TEXT NOT NULL, yardage REAL CHECK(yardage > 0), yardage_unit TEXT CHECK(yardage_unit IN ('yards','metres')),
 par INTEGER CHECK(par > 0), difficulty_rating REAL CHECK(difficulty_rating > 0),
 slope INTEGER CHECK(slope BETWEEN 55 AND 155), rated_category TEXT,
 CHECK(yardage IS NULL OR yardage_unit IS NOT NULL)
) STRICT;
CREATE TABLE alias (
 id TEXT PRIMARY KEY, facility_id TEXT REFERENCES facility(id), course_id TEXT REFERENCES course(id), name TEXT NOT NULL,
 CHECK((facility_id IS NULL) != (course_id IS NULL))
) STRICT;
CREATE TABLE source (
 id TEXT PRIMARY KEY, url TEXT NOT NULL,
 license TEXT, attribution TEXT,
 intake_policy TEXT NOT NULL CHECK(intake_policy IN ('retained_only','permitted','blocked'))
) STRICT;
-- Original reuse terms remain intact, including applicability and adaptations.
CREATE TABLE source_license(id INTEGER PRIMARY KEY, payload TEXT NOT NULL CHECK(json_valid(payload))) STRICT;
CREATE TABLE source_hold(domain TEXT PRIMARY KEY, reason TEXT NOT NULL) STRICT;
CREATE TABLE note(id TEXT PRIMARY KEY, text TEXT NOT NULL) STRICT;
CREATE TABLE retained_evidence (
 facility_id TEXT PRIMARY KEY REFERENCES facility(id), payload TEXT NOT NULL CHECK(json_valid(payload))
) STRICT;
CREATE TABLE retained_document (
 name TEXT PRIMARY KEY, payload TEXT NOT NULL CHECK(json_valid(payload))
) STRICT;
-- Small optional groups; evolving details are sparse JSON inside SQLite.
CREATE TABLE fact_group (
 id TEXT PRIMARY KEY, facility_id TEXT REFERENCES facility(id), course_id TEXT REFERENCES course(id),
 module TEXT NOT NULL CHECK(module IN ('access','operations','prices','architecture','turf','mobility','amenities','practice','services','accessibility','overview')),
 payload TEXT NOT NULL CHECK(json_valid(payload)), source_id TEXT NOT NULL REFERENCES source(id),
 collected_on TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('extracted','confirmed')),
 observed_on TEXT, effective_from TEXT, effective_to TEXT,
 conflict INTEGER NOT NULL DEFAULT 0 CHECK(conflict IN (0,1)),
 CHECK((facility_id IS NULL) != (course_id IS NULL))
) STRICT;
-- Group-level provenance for changed core, round and tee records, without a mandatory per-field workflow.
CREATE TABLE intake_evidence (
 batch_id TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
 source_id TEXT REFERENCES source(id), collected_on TEXT,
 origin TEXT NOT NULL CHECK(origin IN ('new_extraction','retained_normalization')), payload TEXT CHECK(payload IS NULL OR json_valid(payload)),
 status TEXT NOT NULL CHECK(status IN ('extracted','confirmed')),
 PRIMARY KEY(batch_id,entity_type,entity_id)
) STRICT;
CREATE TABLE import_batch (
 id TEXT PRIMARY KEY, digest TEXT NOT NULL, report TEXT NOT NULL CHECK(json_valid(report))
) STRICT;
CREATE TABLE catalog_state(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL) STRICT;
INSERT INTO catalog_state VALUES (1,0);
