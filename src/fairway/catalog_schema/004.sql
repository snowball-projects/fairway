-- Documented rounds may span retained course records at one facility.
PRAGMA foreign_keys=OFF;
BEGIN IMMEDIATE;
-- Never discard contradictory legacy double-parent tee or component relationships.
CREATE TEMP TABLE migration004_guard(n INTEGER CHECK(n=0));
INSERT INTO migration004_guard SELECT count(*) FROM tee_set t JOIN round_option r ON r.id=t.round_id WHERE t.course_id!=r.course_id;
INSERT INTO migration004_guard SELECT count(*) FROM round_component rc JOIN round_option r ON r.id=rc.round_id JOIN component p ON p.id=rc.component_id WHERE r.course_id!=p.course_id;
DROP TABLE migration004_guard;
CREATE TABLE round_option_v4 (
 id TEXT PRIMARY KEY, facility_id TEXT REFERENCES facility(id), course_id TEXT REFERENCES course(id),
 name TEXT NOT NULL, round_holes INTEGER NOT NULL CHECK(round_holes>0), description TEXT,
 CHECK((facility_id IS NULL)!=(course_id IS NULL))
) STRICT;
INSERT INTO round_option_v4 SELECT id,NULL,course_id,name,round_holes,description FROM round_option;
CREATE TABLE round_component_v4 (
 id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES round_option(id), ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 component_id TEXT REFERENCES component(id), course_id TEXT REFERENCES course(id),
 repetitions INTEGER NOT NULL DEFAULT 1 CHECK(repetitions>0),
 CHECK((component_id IS NULL)!=(course_id IS NULL)), UNIQUE(round_id,ordinal)
) STRICT;
INSERT INTO round_component_v4 SELECT id,round_id,ordinal,component_id,NULL,repetitions FROM round_component;
CREATE TABLE tee_set_v4 (
 id TEXT PRIMARY KEY, course_id TEXT REFERENCES course(id), round_id TEXT REFERENCES round_option(id),
 name TEXT NOT NULL, yardage REAL CHECK(yardage>0), yardage_unit TEXT CHECK(yardage_unit IN ('yards','metres')),
 par INTEGER CHECK(par>0), difficulty_rating REAL CHECK(difficulty_rating>0),
 slope INTEGER CHECK(slope BETWEEN 55 AND 155), rated_category TEXT,
 CHECK((course_id IS NULL)!=(round_id IS NULL)), CHECK(yardage IS NULL OR yardage_unit IS NOT NULL)
) STRICT;
INSERT INTO tee_set_v4 SELECT id,CASE WHEN round_id IS NULL THEN course_id ELSE NULL END,round_id,name,yardage,yardage_unit,par,difficulty_rating,slope,rated_category FROM tee_set;
DROP TABLE tee_set;
DROP TABLE round_component;
DROP TABLE round_option;
ALTER TABLE round_option_v4 RENAME TO round_option;
ALTER TABLE round_component_v4 RENAME TO round_component;
ALTER TABLE tee_set_v4 RENAME TO tee_set;
CREATE INDEX round_course ON round_option(course_id);
CREATE INDEX round_facility ON round_option(facility_id);
CREATE INDEX round_member_course ON round_component(course_id);
CREATE INDEX tee_course ON tee_set(course_id);
CREATE INDEX tee_round ON tee_set(round_id);
CREATE VIEW round_scope_violation AS
 SELECT rc.id FROM round_component rc JOIN round_option r ON r.id=rc.round_id
 LEFT JOIN course parent ON parent.id=r.course_id
 LEFT JOIN course member ON member.id=rc.course_id
 LEFT JOIN component p ON p.id=rc.component_id LEFT JOIN course pc ON pc.id=p.course_id
 WHERE coalesce(member.facility_id,pc.facility_id)!=coalesce(r.facility_id,parent.facility_id)
 OR (r.course_id IS NOT NULL AND coalesce(rc.course_id,p.course_id)!=r.course_id);
CREATE TRIGGER round_member_insert AFTER INSERT ON round_component BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;
CREATE TRIGGER round_member_update AFTER UPDATE ON round_component BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;
CREATE TRIGGER round_parent_update AFTER UPDATE ON round_option BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;
CREATE TRIGGER component_parent_update AFTER UPDATE ON component BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;
CREATE TRIGGER course_parent_update AFTER UPDATE ON course BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;
INSERT INTO schema_migration VALUES (4,'single-parent documented facility rounds, retained course members and round-scoped tees');
COMMIT;
PRAGMA foreign_keys=ON;
