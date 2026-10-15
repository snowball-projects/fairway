-- PROPOSED complete native5 layout; build NEW EMPTY database only.
-- Existing v4 core relationships retained. Operational unknown access becomes NULL.
PRAGMA foreign_keys=ON;
CREATE TABLE alias (
 id TEXT PRIMARY KEY, facility_id TEXT REFERENCES facility(id), course_id TEXT REFERENCES course(id), name TEXT NOT NULL,
 CHECK((facility_id IS NULL) != (course_id IS NULL))
) STRICT;

CREATE TABLE catalog_state(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL) STRICT;

CREATE TABLE component (
 id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES course(id), name TEXT NOT NULL,
 physical_holes INTEGER CHECK(physical_holes > 0)
) STRICT;

CREATE TABLE "course" (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facility(id),
 name TEXT CHECK(name IS NULL OR length(trim(name)) > 0), physical_holes INTEGER CHECK(physical_holes > 0),
 access TEXT CHECK(access IN ('public','private','restricted')),
 nonmember_bookable INTEGER CHECK(nonmember_bookable IN (0,1)), booking_conditions TEXT CHECK(booking_conditions IS NULL OR length(booking_conditions)<=4000),
 style TEXT CHECK(style IN ('regulation','executive','par_3','pitch_and_putt','putting')),
 game_kind TEXT CHECK(game_kind IN ('golf','obstacle_minigolf')),
 identity_status TEXT NOT NULL DEFAULT 'needs_review' CHECK(identity_status IN ('operator_defined','needs_review','component')),
 operating_status TEXT CHECK(operating_status IN ('open','partially_open','temporarily_closed','seasonally_closed','permanently_closed','planned','under_renovation')), website TEXT, booking_url TEXT, contact_url TEXT,
 address_text TEXT,address_street_line1 TEXT CHECK(address_street_line1 IS NULL OR (length(trim(address_street_line1))>0 AND length(address_street_line1)<=512)),address_street_line2 TEXT CHECK(address_street_line2 IS NULL OR (length(trim(address_street_line2))>0 AND length(address_street_line2)<=512)),address_city TEXT CHECK(address_city IS NULL OR (length(trim(address_city))>0 AND length(address_city)<=255)),address_region TEXT CHECK(address_region IS NULL OR (length(trim(address_region))>0 AND length(address_region)<=128)),address_postal_code TEXT CHECK(address_postal_code IS NULL OR (length(trim(address_postal_code))>0 AND length(address_postal_code)<=32)),address_country TEXT CHECK(address_country IS NULL OR address_country GLOB '[A-Z][A-Z]'), address_purpose TEXT CHECK(address_purpose IN ('clubhouse','contact','course','mailing','published_unspecified')),
 address_mode TEXT NOT NULL DEFAULT 'inherit' CHECK(address_mode IN ('inherit','override','suppress')),
 arrival_latitude REAL CHECK(arrival_latitude BETWEEN -90 AND 90),
 arrival_longitude REAL CHECK(arrival_longitude BETWEEN -180 AND 180),
 arrival_kind TEXT CHECK(arrival_kind IN ('reviewed_osm_point','verified_entrance')), arrival_reference TEXT,
 location_note TEXT,
 CHECK((arrival_latitude IS NULL) = (arrival_longitude IS NULL)),
 CHECK(arrival_latitude IS NULL OR (arrival_kind IS NOT NULL AND arrival_reference IS NOT NULL AND length(trim(arrival_reference,char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)))>0))
,CHECK(address_mode='override' OR (address_text IS NULL AND address_purpose IS NULL AND address_street_line1 IS NULL AND address_street_line2 IS NULL AND address_city IS NULL AND address_region IS NULL AND address_postal_code IS NULL AND address_country IS NULL))) STRICT;

CREATE TABLE facility (
 id TEXT PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name)) > 0),
 state TEXT, country TEXT NOT NULL DEFAULT 'US', county TEXT,
 address_text TEXT,address_street_line1 TEXT CHECK(address_street_line1 IS NULL OR (length(trim(address_street_line1))>0 AND length(address_street_line1)<=512)),address_street_line2 TEXT CHECK(address_street_line2 IS NULL OR (length(trim(address_street_line2))>0 AND length(address_street_line2)<=512)),address_city TEXT CHECK(address_city IS NULL OR (length(trim(address_city))>0 AND length(address_city)<=255)),address_region TEXT CHECK(address_region IS NULL OR (length(trim(address_region))>0 AND length(address_region)<=128)),address_postal_code TEXT CHECK(address_postal_code IS NULL OR (length(trim(address_postal_code))>0 AND length(address_postal_code)<=32)),address_country TEXT CHECK(address_country IS NULL OR address_country GLOB '[A-Z][A-Z]'), address_purpose TEXT CHECK(address_purpose IN ('clubhouse','contact','course','mailing','published_unspecified')),
 physical_holes INTEGER CHECK(physical_holes > 0),
 inventory_complete INTEGER CHECK(inventory_complete IN (0,1)),
 access TEXT CHECK(access IN ('public','private','restricted')),
 ownership TEXT CHECK(ownership IN ('municipal','county','state','federal','tribal','private','nonprofit','other_documented')), setting TEXT CHECK(setting IN ('parkland','links','desert','mountain','coastal','urban','rural','mixed')), operating_status TEXT CHECK(operating_status IN ('open','partially_open','temporarily_closed','seasonally_closed','permanently_closed','planned','under_renovation')),
 website TEXT, booking_url TEXT, contact_url TEXT,
 latitude REAL CHECK(latitude BETWEEN -90 AND 90),
 longitude REAL CHECK(longitude BETWEEN -180 AND 180), location_kind TEXT CHECK(location_kind IN ('property_point','reviewed_osm_point','verified_entrance','address_range_estimate')),
 website_status TEXT CHECK(website_status IN ('found','not_checked','unreachable','redirected')), website_checked_on TEXT,
 CHECK((latitude IS NULL) = (longitude IS NULL)),
 CHECK(latitude IS NULL OR location_kind IS NOT NULL)
) STRICT;

CREATE TABLE fact_group (
 id TEXT PRIMARY KEY, facility_id TEXT REFERENCES facility(id), course_id TEXT REFERENCES course(id),
 module TEXT NOT NULL CHECK(module IN ('access','operations','prices','architecture','turf','mobility','amenities','practice','services','accessibility','overview')),
 payload TEXT NOT NULL CHECK(json_valid(payload)), source_id TEXT NOT NULL REFERENCES source(id),
 collected_on TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('extracted','confirmed')),
 observed_on TEXT, effective_from TEXT, effective_to TEXT,
 conflict INTEGER NOT NULL DEFAULT 0 CHECK(conflict IN (0,1)),
 CHECK((facility_id IS NULL) != (course_id IS NULL))
) STRICT;

CREATE TABLE import_batch (
 id TEXT PRIMARY KEY, digest TEXT NOT NULL, report TEXT NOT NULL CHECK(json_valid(report))
) STRICT;

CREATE TABLE intake_evidence (
 batch_id TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
 source_id TEXT REFERENCES source(id), collected_on TEXT,
 origin TEXT NOT NULL CHECK(origin IN ('new_extraction','retained_normalization')), payload TEXT CHECK(payload IS NULL OR json_valid(payload)),
 status TEXT NOT NULL CHECK(status IN ('extracted','confirmed')),
 PRIMARY KEY(batch_id,entity_type,entity_id)
) STRICT;

CREATE TABLE note(id TEXT PRIMARY KEY, text TEXT NOT NULL) STRICT;

CREATE TABLE retained_document (
 name TEXT PRIMARY KEY, payload TEXT NOT NULL CHECK(json_valid(payload))
) STRICT;

CREATE TABLE retained_evidence (
 facility_id TEXT PRIMARY KEY REFERENCES facility(id), payload TEXT NOT NULL CHECK(json_valid(payload))
) STRICT;

CREATE TABLE "round_component" (
 id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES round_option(id), ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 component_id TEXT REFERENCES component(id), course_id TEXT REFERENCES course(id),
 repetitions INTEGER NOT NULL DEFAULT 1 CHECK(repetitions>0),
 CHECK((component_id IS NULL)!=(course_id IS NULL)), UNIQUE(round_id,ordinal)
) STRICT;

CREATE TABLE "round_option" (
 id TEXT PRIMARY KEY, facility_id TEXT REFERENCES facility(id), course_id TEXT REFERENCES course(id),
 name TEXT NOT NULL, round_holes INTEGER NOT NULL CHECK(round_holes>0), description TEXT,
 CHECK((facility_id IS NULL)!=(course_id IS NULL))
) STRICT;

CREATE TABLE schema_migration(version INTEGER PRIMARY KEY, description TEXT NOT NULL) STRICT;

CREATE TABLE source (
 id TEXT PRIMARY KEY, url TEXT NOT NULL,
 license TEXT, attribution TEXT,
 intake_policy TEXT NOT NULL CHECK(intake_policy IN ('retained_only','permitted','blocked'))
) STRICT;

CREATE TABLE source_hold(domain TEXT PRIMARY KEY, reason TEXT NOT NULL) STRICT;

CREATE TABLE source_hold_scope (
 id TEXT PRIMARY KEY,
 scope_kind TEXT NOT NULL CHECK(scope_kind IN ('publisher','host','resource')),
 scope_key TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload))
) STRICT;

CREATE TABLE source_license(id INTEGER PRIMARY KEY, payload TEXT NOT NULL CHECK(json_valid(payload))) STRICT;

CREATE TABLE "tee_set" (
 id TEXT PRIMARY KEY, course_id TEXT REFERENCES course(id), round_id TEXT REFERENCES round_option(id),
 name TEXT NOT NULL, yardage REAL CHECK(yardage>0), yardage_unit TEXT CHECK(yardage_unit IN ('yards','metres')),
 par INTEGER CHECK(par>0), difficulty_rating REAL CHECK(difficulty_rating>0),
 slope INTEGER CHECK(slope BETWEEN 55 AND 155), rated_category TEXT,
 CHECK((course_id IS NULL)!=(round_id IS NULL)), CHECK(yardage IS NULL OR yardage_unit IS NOT NULL)
) STRICT;

CREATE INDEX course_facility ON course(facility_id);

CREATE INDEX course_filter ON course(access,style,physical_holes);

CREATE INDEX facility_location ON facility(latitude,longitude);

CREATE INDEX facility_region ON facility(country,state);

CREATE INDEX round_course ON round_option(course_id);

CREATE INDEX round_facility ON round_option(facility_id);

CREATE INDEX round_member_course ON round_component(course_id);

CREATE INDEX source_hold_scope_key ON source_hold_scope(scope_kind,scope_key);

CREATE INDEX tee_course ON tee_set(course_id);

CREATE INDEX tee_round ON tee_set(round_id);

CREATE VIEW round_scope_violation AS
 SELECT rc.id FROM round_component rc JOIN round_option r ON r.id=rc.round_id
 LEFT JOIN course parent ON parent.id=r.course_id
 LEFT JOIN course member ON member.id=rc.course_id
 LEFT JOIN component p ON p.id=rc.component_id LEFT JOIN course pc ON pc.id=p.course_id
 WHERE coalesce(member.facility_id,pc.facility_id)!=coalesce(r.facility_id,parent.facility_id)
 OR (r.course_id IS NOT NULL AND coalesce(rc.course_id,p.course_id)!=r.course_id);

CREATE TRIGGER component_parent_update AFTER UPDATE ON component BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;

CREATE TRIGGER course_parent_update AFTER UPDATE ON course BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;

CREATE TRIGGER round_member_insert AFTER INSERT ON round_component BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;

CREATE TRIGGER round_member_update AFTER UPDATE ON round_component BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;

CREATE TRIGGER round_parent_update AFTER UPDATE ON round_option BEGIN
 SELECT RAISE(ABORT,'round member must share its parent facility and course scope') WHERE EXISTS(SELECT 1 FROM round_scope_violation);
END;

-- DRAFT for exact-layout approval. No data migration or canonical facts inserted.
CREATE TABLE source_observation (
 id TEXT PRIMARY KEY,
 source_id TEXT REFERENCES source(id),
 collected_on TEXT CHECK(collected_on IS NULL OR (length(collected_on)=10 AND date(collected_on,'+0 days') IS NOT NULL AND date(collected_on,'+0 days')=collected_on)),
 observed_on TEXT CHECK(observed_on IS NULL OR (length(observed_on)=10 AND date(observed_on,'+0 days') IS NOT NULL AND date(observed_on,'+0 days')=observed_on)),
 effective_from TEXT CHECK(effective_from IS NULL OR (date(effective_from,'+0 days') IS NOT NULL AND date(effective_from,'+0 days')=effective_from)),
 effective_to TEXT CHECK(effective_to IS NULL OR (date(effective_to,'+0 days') IS NOT NULL AND date(effective_to,'+0 days')=effective_to)),
 status TEXT NOT NULL CHECK(status IN ('retained','extracted','confirmed')),
 origin TEXT NOT NULL CHECK(origin IN ('retained_input','retained_normalization','new_extraction')),
 conflict INTEGER NOT NULL DEFAULT 0 CHECK(conflict IN (0,1)),
 qualification TEXT CHECK(qualification IS NULL OR (length(trim(qualification))>0 AND length(qualification)<=4000)),
 retained_group_id TEXT REFERENCES fact_group(id),
 retained_facility_id TEXT REFERENCES retained_evidence(facility_id),
 retained_pointer TEXT,
 CHECK(origin!='new_extraction' OR (source_id IS NOT NULL AND collected_on IS NOT NULL)),
 CHECK(origin NOT IN ('retained_input','retained_normalization') OR retained_group_id IS NOT NULL OR retained_facility_id IS NOT NULL),
 CHECK(retained_pointer IS NULL OR (length(trim(retained_pointer))>0 AND length(retained_pointer)<=2000)),
 CHECK(effective_from IS NULL OR effective_to IS NULL OR effective_from<=effective_to)
) STRICT;

CREATE TABLE physical_characteristics (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 component_id TEXT REFERENCES component(id),
 acreage REAL CHECK(acreage BETWEEN 1e-06 AND 1000000000000.0),
 acreage_approximate INTEGER CHECK(acreage_approximate IN (0,1)),
 landscape TEXT CHECK(landscape IN ('parkland','links','desert','mountain','coastal','urban','rural','mixed')),
 terrain TEXT CHECK(terrain IN ('flat','rolling','hilly','mixed')),
 water_features INTEGER CHECK(water_features IN (0,1)),
 wooded INTEGER CHECK(wooded IN (0,1)),
 playing_surface TEXT CHECK(playing_surface IN ('natural_grass','synthetic','mixed')),
 greens_grass_name TEXT CHECK(greens_grass_name IS NULL OR (length(trim(greens_grass_name))>0 AND length(greens_grass_name)<=512)),
 fairway_grass_name TEXT CHECK(fairway_grass_name IS NULL OR (length(trim(fairway_grass_name))>0 AND length(fairway_grass_name)<=512)),
 tee_grass_name TEXT CHECK(tee_grass_name IS NULL OR (length(trim(tee_grass_name))>0 AND length(tee_grass_name)<=512)),
 rough_grass_name TEXT CHECK(rough_grass_name IS NULL OR (length(trim(rough_grass_name))>0 AND length(rough_grass_name)<=512)),
 elevation REAL CHECK(elevation BETWEEN -500 AND 10000),
 elevation_unit TEXT CHECK(elevation_unit IN ('metres','feet')),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)+(component_id IS NOT NULL)=1),
 CHECK(elevation IS NULL OR elevation_unit IS NOT NULL)
) STRICT;

CREATE TABLE amenity_observation (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 clubhouse_available INTEGER CHECK(clubhouse_available IN (0,1)),
 restaurant_available INTEGER CHECK(restaurant_available IN (0,1)),
 bar_available INTEGER CHECK(bar_available IN (0,1)),
 snack_bar_available INTEGER CHECK(snack_bar_available IN (0,1)),
 lodging_available INTEGER CHECK(lodging_available IN (0,1)),
 casino_available INTEGER CHECK(casino_available IN (0,1)),
 spa_available INTEGER CHECK(spa_available IN (0,1)),
 pool_available INTEGER CHECK(pool_available IN (0,1)),
 locker_rooms_available INTEGER CHECK(locker_rooms_available IN (0,1)),
 showers_available INTEGER CHECK(showers_available IN (0,1)),
 restrooms_available INTEGER CHECK(restrooms_available IN (0,1)),
 drinking_water_available INTEGER CHECK(drinking_water_available IN (0,1)),
 tennis_available INTEGER CHECK(tennis_available IN (0,1)),
 pickleball_available INTEGER CHECK(pickleball_available IN (0,1)),
 banquet_space_available INTEGER CHECK(banquet_space_available IN (0,1)),
 parking_available INTEGER CHECK(parking_available IN (0,1)),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)=1)
) STRICT;

CREATE TABLE practice_observation (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 driving_range_available INTEGER CHECK(driving_range_available IN (0,1)),
 driving_range_station_count INTEGER CHECK(driving_range_station_count BETWEEN 0 AND 100000),
 driving_range_lighted INTEGER CHECK(driving_range_lighted IN (0,1)),
 driving_range_covered INTEGER CHECK(driving_range_covered IN (0,1)),
 driving_range_heated INTEGER CHECK(driving_range_heated IN (0,1)),
 driving_range_double_sided INTEGER CHECK(driving_range_double_sided IN (0,1)),
 driving_range_tier_count INTEGER CHECK(driving_range_tier_count BETWEEN 1 AND 20),
 range_grass_tees_available INTEGER CHECK(range_grass_tees_available IN (0,1)),
 range_mat_tees_available INTEGER CHECK(range_mat_tees_available IN (0,1)),
 driving_range_length REAL CHECK(driving_range_length BETWEEN 0 AND 1000000000000.0),
 driving_range_length_unit TEXT CHECK(driving_range_length_unit IN ('yards','metres')),
 putting_green_available INTEGER CHECK(putting_green_available IN (0,1)),
 putting_green_count INTEGER CHECK(putting_green_count BETWEEN 0 AND 100000),
 chipping_area_available INTEGER CHECK(chipping_area_available IN (0,1)),
 short_game_area_available INTEGER CHECK(short_game_area_available IN (0,1)),
 practice_bunker_available INTEGER CHECK(practice_bunker_available IN (0,1)),
 practice_bunker_count INTEGER CHECK(practice_bunker_count BETWEEN 0 AND 100000),
 indoor_simulator_available INTEGER CHECK(indoor_simulator_available IN (0,1)),
 indoor_simulator_count INTEGER CHECK(indoor_simulator_count BETWEEN 0 AND 100000),
 range_technology_name TEXT CHECK(range_technology_name IS NULL OR (length(trim(range_technology_name))>0 AND length(range_technology_name)<=512)),
 driving_range_details TEXT CHECK(driving_range_details IS NULL OR (length(trim(driving_range_details))>0 AND length(driving_range_details)<=2000)),
 putting_green_details TEXT CHECK(putting_green_details IS NULL OR (length(trim(putting_green_details))>0 AND length(putting_green_details)<=2000)),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)=1),
 CHECK(driving_range_length IS NULL OR driving_range_length_unit IS NOT NULL)
) STRICT;

CREATE TABLE service_observation (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 pro_shop_available INTEGER CHECK(pro_shop_available IN (0,1)),
 pro_shop_full_service INTEGER CHECK(pro_shop_full_service IN (0,1)),
 pro_shop_stocked INTEGER CHECK(pro_shop_stocked IN (0,1)),
 club_rental_available INTEGER CHECK(club_rental_available IN (0,1)),
 push_cart_rental_available INTEGER CHECK(push_cart_rental_available IN (0,1)),
 golf_cart_rental_available INTEGER CHECK(golf_cart_rental_available IN (0,1)),
 caddie_available INTEGER CHECK(caddie_available IN (0,1)),
 forecaddie_available INTEGER CHECK(forecaddie_available IN (0,1)),
 instruction_available INTEGER CHECK(instruction_available IN (0,1)),
 club_fitting_available INTEGER CHECK(club_fitting_available IN (0,1)),
 club_repair_available INTEGER CHECK(club_repair_available IN (0,1)),
 golf_academy_available INTEGER CHECK(golf_academy_available IN (0,1)),
 golf_learning_center_available INTEGER CHECK(golf_learning_center_available IN (0,1)),
 club_sales_available INTEGER CHECK(club_sales_available IN (0,1)),
 club_trade_ins_accepted INTEGER CHECK(club_trade_ins_accepted IN (0,1)),
 memberships_available INTEGER CHECK(memberships_available IN (0,1)),
 event_booking_available INTEGER CHECK(event_booking_available IN (0,1)),
 pro_shop_details TEXT CHECK(pro_shop_details IS NULL OR (length(trim(pro_shop_details))>0 AND length(pro_shop_details)<=2000)),
 rental_details TEXT CHECK(rental_details IS NULL OR (length(trim(rental_details))>0 AND length(rental_details)<=2000)),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)=1)
) STRICT;

CREATE TABLE policy_observation (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 round_id TEXT REFERENCES round_option(id),
 ordinary_nonmember_allowed INTEGER CHECK(ordinary_nonmember_allowed IN (0,1)),
 member_sponsor_required INTEGER CHECK(member_sponsor_required IN (0,1)),
 club_affiliation_required INTEGER CHECK(club_affiliation_required IN (0,1)),
 resort_stay_required INTEGER CHECK(resort_stay_required IN (0,1)),
 walk_in_play_allowed INTEGER CHECK(walk_in_play_allowed IN (0,1)),
 tee_time_reservations_accepted INTEGER CHECK(tee_time_reservations_accepted IN (0,1)),
 walking_allowed INTEGER CHECK(walking_allowed IN (0,1)),
 carts_required INTEGER CHECK(carts_required IN (0,1)),
 caddie_required INTEGER CHECK(caddie_required IN (0,1)),
 outside_food_allowed INTEGER CHECK(outside_food_allowed IN (0,1)),
 denim_allowed INTEGER CHECK(denim_allowed IN (0,1)),
 collared_shirt_required INTEGER CHECK(collared_shirt_required IN (0,1)),
 booking_window_days INTEGER CHECK(booking_window_days BETWEEN 0 AND 3650),
 booking_opens_minute_of_day INTEGER CHECK(booking_opens_minute_of_day BETWEEN 0 AND 1439),
 minimum_cancellation_notice_hours REAL CHECK(minimum_cancellation_notice_hours BETWEEN 0 AND 8760),
 minimum_player_age INTEGER CHECK(minimum_player_age BETWEEN 0 AND 120),
 minimum_cart_driver_age INTEGER CHECK(minimum_cart_driver_age BETWEEN 0 AND 120),
 arrival_access_condition TEXT CHECK(arrival_access_condition IN ('none','photo_id','visitor_pass','military_id','resort_check_in','member_sponsor','other_documented')),
 cancellation_charge_basis TEXT CHECK(cancellation_charge_basis IN ('fixed_amount','percent_of_booking','full_booking')),
 cancellation_charge_amount REAL CHECK(cancellation_charge_amount BETWEEN 0 AND 1000000000000.0),
 cancellation_charge_currency TEXT CHECK(cancellation_charge_currency IS NULL OR cancellation_charge_currency GLOB '[A-Z][A-Z][A-Z]'),
 cancellation_charge_percent REAL CHECK(cancellation_charge_percent BETWEEN 0 AND 100),
 weekday_mask INTEGER CHECK(weekday_mask BETWEEN 1 AND 127),
 applies_on_holidays INTEGER CHECK(applies_on_holidays IN (0,1)),
 start_minute_of_day INTEGER CHECK(start_minute_of_day BETWEEN 0 AND 1439),
 end_minute_of_day INTEGER CHECK(end_minute_of_day BETWEEN 0 AND 1439),
 ends_next_day INTEGER CHECK(ends_next_day IN (0,1)),
 season TEXT CHECK(season IN ('peak','off_peak','winter','summer','spring','autumn','other_documented')),
 audience TEXT CHECK(audience IN ('adult','junior','senior','student','military','veteran','member','nonmember','resort_guest','all_eligible')),
 minimum_group_size INTEGER CHECK(minimum_group_size BETWEEN 1 AND 1000000),
 maximum_group_size INTEGER CHECK(maximum_group_size BETWEEN 1 AND 1000000),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)+(round_id IS NOT NULL)=1),
 CHECK(minimum_group_size IS NULL OR maximum_group_size IS NULL OR minimum_group_size<=maximum_group_size),
 CHECK(start_minute_of_day IS NULL OR end_minute_of_day IS NULL OR (ends_next_day IS NOT NULL AND ((ends_next_day=0 AND end_minute_of_day>=start_minute_of_day) OR (ends_next_day=1 AND end_minute_of_day<=start_minute_of_day)))),
 CHECK(cancellation_charge_amount IS NULL OR (cancellation_charge_basis IS 'fixed_amount' AND cancellation_charge_currency IS NOT NULL)),
 CHECK(cancellation_charge_currency IS NULL OR cancellation_charge_basis IS 'fixed_amount'),
 CHECK(cancellation_charge_percent IS NULL OR cancellation_charge_basis IS 'percent_of_booking'),
 CHECK(cancellation_charge_basis IS NOT 'full_booking' OR (cancellation_charge_amount IS NULL AND cancellation_charge_percent IS NULL AND cancellation_charge_currency IS NULL))
) STRICT;

CREATE TABLE operating_period (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 period_kind TEXT CHECK(period_kind IN ('regular_hours','season','maintenance','closure','planned_reopening')),
 is_open INTEGER CHECK(is_open IN (0,1)),
 date_from TEXT CHECK(date_from IS NULL OR (length(date_from)=10 AND date(date_from,'+0 days') IS NOT NULL AND date(date_from,'+0 days')=date_from)),
 date_to TEXT CHECK(date_to IS NULL OR (length(date_to)=10 AND date(date_to,'+0 days') IS NOT NULL AND date(date_to,'+0 days')=date_to)),
 annual_start_month INTEGER CHECK(annual_start_month BETWEEN 1 AND 12),
 annual_start_day INTEGER CHECK(annual_start_day BETWEEN 1 AND 31),
 annual_end_month INTEGER CHECK(annual_end_month BETWEEN 1 AND 12),
 annual_end_day INTEGER CHECK(annual_end_day BETWEEN 1 AND 31),
 weekday_mask INTEGER CHECK(weekday_mask BETWEEN 1 AND 127),
 opens_minute_of_day INTEGER CHECK(opens_minute_of_day BETWEEN 0 AND 1439),
 closes_minute_of_day INTEGER CHECK(closes_minute_of_day BETWEEN 0 AND 1439),
 closes_next_day INTEGER CHECK(closes_next_day IN (0,1)),
 year_round INTEGER CHECK(year_round IN (0,1)),
 maintenance_kind TEXT CHECK(maintenance_kind IN ('aerification','topdressing','overseeding','mowing','turf_treatment','reconstruction','other_documented')),
 aerification_method TEXT CHECK(aerification_method IN ('hollow_tine','solid_tine','deep_tine','liquid','other_documented')),
 affected_hole_count INTEGER CHECK(affected_hole_count BETWEEN 1 AND 1000),
 affected_area TEXT CHECK(affected_area IN ('whole_facility','whole_course','selected_holes','greens','driving_range','clubhouse','other_documented')),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)=1),
 CHECK(date_from IS NULL OR date_to IS NULL OR date_from<=date_to),
 CHECK(annual_start_day IS NULL OR annual_start_month IS NOT NULL),
 CHECK(annual_end_day IS NULL OR annual_end_month IS NOT NULL),
 CHECK(annual_start_day IS NULL OR (annual_start_month IS NOT NULL AND date(printf('2000-%02d-%02d',annual_start_month,annual_start_day),'+0 days') IS NOT NULL AND date(printf('2000-%02d-%02d',annual_start_month,annual_start_day),'+0 days')=printf('2000-%02d-%02d',annual_start_month,annual_start_day))),
 CHECK(annual_end_day IS NULL OR (annual_end_month IS NOT NULL AND date(printf('2000-%02d-%02d',annual_end_month,annual_end_day),'+0 days') IS NOT NULL AND date(printf('2000-%02d-%02d',annual_end_month,annual_end_day),'+0 days')=printf('2000-%02d-%02d',annual_end_month,annual_end_day))),
 CHECK(opens_minute_of_day IS NULL OR closes_minute_of_day IS NULL OR (closes_next_day IS NOT NULL AND ((closes_next_day=0 AND closes_minute_of_day>=opens_minute_of_day) OR (closes_next_day=1 AND closes_minute_of_day<=opens_minute_of_day))))
) STRICT;

CREATE TABLE accessibility_observation (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 wheelchair_accessible_clubhouse INTEGER CHECK(wheelchair_accessible_clubhouse IN (0,1)),
 accessible_parking_available INTEGER CHECK(accessible_parking_available IN (0,1)),
 accessible_restroom_available INTEGER CHECK(accessible_restroom_available IN (0,1)),
 adaptive_cart_available INTEGER CHECK(adaptive_cart_available IN (0,1)),
 accessible_cart_available INTEGER CHECK(accessible_cart_available IN (0,1)),
 accessible_practice_area_available INTEGER CHECK(accessible_practice_area_available IN (0,1)),
 step_free_clubhouse_access INTEGER CHECK(step_free_clubhouse_access IN (0,1)),
 advance_notice_required_hours REAL CHECK(advance_notice_required_hours BETWEEN 0 AND 8760),
 advance_notice_recommended_hours REAL CHECK(advance_notice_recommended_hours BETWEEN 0 AND 8760),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)=1)
) STRICT;

CREATE TABLE price_observation (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 round_id TEXT REFERENCES round_option(id),
 fee_kind TEXT CHECK(fee_kind IN ('green_fee','golf_cart','push_cart','club_rental','nonplayer_rider','range_balls','practice_pass','instruction','booking_fee','membership','event','other_documented')),
 amount_min REAL CHECK(amount_min BETWEEN 0 AND 1000000000000.0),
 amount_max REAL CHECK(amount_max BETWEEN 0 AND 1000000000000.0),
 amount_kind TEXT CHECK(amount_kind IN ('exact','range','starting_at','discount')),
 currency TEXT CHECK(currency IS NULL OR currency GLOB '[A-Z][A-Z][A-Z]'),
 billing_basis TEXT CHECK(billing_basis IN ('per_person','per_cart','per_round','per_bucket','per_ball','per_hour','per_day','per_month','per_year','per_event')),
 round_holes INTEGER CHECK(round_holes BETWEEN 1 AND 1000),
 quantity INTEGER CHECK(quantity BETWEEN 1 AND 1000000),
 audience TEXT CHECK(audience IN ('adult','junior','senior','student','military','veteran','member','nonmember','resort_guest','all_eligible')),
 residency TEXT CHECK(residency IN ('resident','nonresident','all_eligible')),
 residency_area_name TEXT CHECK(residency_area_name IS NULL OR (length(trim(residency_area_name))>0 AND length(residency_area_name)<=512)),
 minimum_age INTEGER CHECK(minimum_age BETWEEN 0 AND 120),
 maximum_age INTEGER CHECK(maximum_age BETWEEN 0 AND 120),
 weekday_mask INTEGER CHECK(weekday_mask BETWEEN 1 AND 127),
 applies_on_holidays INTEGER CHECK(applies_on_holidays IN (0,1)),
 start_minute_of_day INTEGER CHECK(start_minute_of_day BETWEEN 0 AND 1439),
 end_minute_of_day INTEGER CHECK(end_minute_of_day BETWEEN 0 AND 1439),
 ends_next_day INTEGER CHECK(ends_next_day IN (0,1)),
 season TEXT CHECK(season IN ('peak','off_peak','winter','summer','spring','autumn','other_documented')),
 cart_included INTEGER CHECK(cart_included IN (0,1)),
 tax_included INTEGER CHECK(tax_included IN (0,1)),
 practice_included INTEGER CHECK(practice_included IN (0,1)),
 resort_stay_required INTEGER CHECK(resort_stay_required IN (0,1)),
 member_sponsor_required INTEGER CHECK(member_sponsor_required IN (0,1)),
 club_affiliation_required INTEGER CHECK(club_affiliation_required IN (0,1)),
 discount_percent REAL CHECK(discount_percent BETWEEN 0 AND 100),
 historical INTEGER CHECK(historical IN (0,1)),
 dynamic_pricing INTEGER CHECK(dynamic_pricing IN (0,1)),
 unconditional INTEGER CHECK(unconditional IN (0,1)),
 source_information_as_of TEXT CHECK(source_information_as_of IS NULL OR (length(source_information_as_of)=10 AND date(source_information_as_of,'+0 days') IS NOT NULL AND date(source_information_as_of,'+0 days')=source_information_as_of)),
 minimum_group_size INTEGER CHECK(minimum_group_size BETWEEN 1 AND 1000000),
 maximum_group_size INTEGER CHECK(maximum_group_size BETWEEN 1 AND 1000000),
 minimum_advance_purchase_days REAL CHECK(minimum_advance_purchase_days BETWEEN 0 AND 3650),
 maximum_advance_purchase_days REAL CHECK(maximum_advance_purchase_days BETWEEN 0 AND 3650),
 prepayment_required INTEGER CHECK(prepayment_required IN (0,1)),
 second_round_required INTEGER CHECK(second_round_required IN (0,1)),
 same_day_second_round_required INTEGER CHECK(same_day_second_round_required IN (0,1)),
 qualifying_prior_round_id TEXT REFERENCES round_option(id),
 product_name TEXT CHECK(product_name IS NULL OR (length(trim(product_name))>0 AND length(product_name)<=512)),
 conditions TEXT CHECK(conditions IS NULL OR (length(trim(conditions))>0 AND length(conditions)<=4000)),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)+(round_id IS NOT NULL)=1),
 CHECK(amount_min IS NULL OR amount_max IS NULL OR amount_min<=amount_max),
 CHECK(amount_kind!='exact' OR (amount_min IS NOT NULL AND amount_max IS NOT NULL AND amount_min=amount_max)),
 CHECK(minimum_age IS NULL OR maximum_age IS NULL OR minimum_age<=maximum_age),
 CHECK(start_minute_of_day IS NULL OR end_minute_of_day IS NULL OR (ends_next_day IS NOT NULL AND ((ends_next_day=0 AND end_minute_of_day>=start_minute_of_day) OR (ends_next_day=1 AND end_minute_of_day<=start_minute_of_day)))),
 CHECK(minimum_group_size IS NULL OR maximum_group_size IS NULL OR minimum_group_size<=maximum_group_size),
 CHECK(minimum_advance_purchase_days IS NULL OR maximum_advance_purchase_days IS NULL OR minimum_advance_purchase_days<=maximum_advance_purchase_days),
 CHECK(same_day_second_round_required IS NOT 1 OR second_round_required IS 1)
) STRICT;

CREATE TABLE design_party (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL CHECK(length(trim(name))>0 AND length(name)<=255),
 party_kind TEXT CHECK(party_kind IN ('person','firm'))
) STRICT;

CREATE TABLE architecture_event (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 component_id TEXT REFERENCES component(id),
 event_kind TEXT CHECK(event_kind IN ('design','opening','redesign','renovation','restoration','expansion','founding','construction')),
 project_state TEXT CHECK(project_state IN ('planned','in_progress','completed','cancelled')),
 target_area TEXT CHECK(target_area IN ('whole_facility','whole_course','nine_hole_component','greens','tees','fairways','clubhouse','practice_area')),
 event_year INTEGER CHECK(event_year BETWEEN 1 AND 9999),
 event_month INTEGER CHECK(event_month BETWEEN 1 AND 12),
 event_day INTEGER CHECK(event_day BETWEEN 1 AND 31),
 year_end INTEGER CHECK(year_end BETWEEN 1 AND 9999),
 physical_holes_before INTEGER CHECK(physical_holes_before BETWEEN 1 AND 1000),
 physical_holes_after INTEGER CHECK(physical_holes_after BETWEEN 1 AND 1000),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)+(component_id IS NOT NULL)=1),
 CHECK(event_month IS NULL OR event_year IS NOT NULL),
 CHECK(event_day IS NULL OR event_month IS NOT NULL),
 CHECK(year_end IS NULL OR event_year IS NULL OR event_year<=year_end),
 CHECK(event_day IS NULL OR date(printf('%04d-%02d-%02d',event_year,event_month,event_day),'+0 days')=printf('%04d-%02d-%02d',event_year,event_month,event_day))
) STRICT;

CREATE TABLE architecture_credit (
 id TEXT PRIMARY KEY,
 event_id TEXT NOT NULL REFERENCES architecture_event(id),
 party_id TEXT NOT NULL REFERENCES design_party(id),
 role TEXT CHECK(role IN ('original_design','redesign','renovation','restoration','expansion')),
 UNIQUE(event_id,party_id,role)
) STRICT;
CREATE UNIQUE INDEX architecture_unknown_role_once ON architecture_credit(event_id,party_id) WHERE role IS NULL;

CREATE TABLE quality_rating (
 id TEXT PRIMARY KEY,
 observation_id TEXT NOT NULL REFERENCES source_observation(id),
 facility_id TEXT REFERENCES facility(id),
 course_id TEXT REFERENCES course(id),
 issuer_name TEXT NOT NULL CHECK(issuer_name IS NULL OR (length(trim(issuer_name))>0 AND length(issuer_name)<=512)),
 score REAL CHECK(score BETWEEN -1000000000.0 AND 1000000000.0),
 scale_min REAL CHECK(scale_min BETWEEN -1000000000.0 AND 1000000000.0),
 scale_max REAL CHECK(scale_max BETWEEN -1000000000.0 AND 1000000000.0),
 rated_on TEXT CHECK(rated_on IS NULL OR (length(rated_on)=10 AND date(rated_on,'+0 days') IS NOT NULL AND date(rated_on,'+0 days')=rated_on)),
 dimension TEXT CHECK(dimension IN ('overall','conditioning','design','value','service','practice')),
 CHECK((facility_id IS NOT NULL)+(course_id IS NOT NULL)=1),
 CHECK(score IS NULL OR (scale_min IS NOT NULL AND scale_max IS NOT NULL AND scale_min<scale_max AND score BETWEEN scale_min AND scale_max))
) STRICT;

CREATE VIEW optional_subject_scope AS
SELECT x.id,x.observation_id,x.facility_id,coalesce(x.course_id,p.course_id) AS course_id,NULL AS round_id FROM physical_characteristics x LEFT JOIN component p ON p.id=x.component_id
UNION ALL
SELECT id,observation_id,facility_id,course_id,NULL AS round_id FROM amenity_observation
UNION ALL
SELECT id,observation_id,facility_id,course_id,NULL AS round_id FROM practice_observation
UNION ALL
SELECT id,observation_id,facility_id,course_id,NULL AS round_id FROM service_observation
UNION ALL
SELECT id,observation_id,facility_id,course_id,round_id FROM policy_observation
UNION ALL
SELECT id,observation_id,facility_id,course_id,NULL AS round_id FROM operating_period
UNION ALL
SELECT id,observation_id,facility_id,course_id,NULL AS round_id FROM accessibility_observation
UNION ALL
SELECT id,observation_id,facility_id,course_id,round_id FROM price_observation
UNION ALL
SELECT x.id,x.observation_id,x.facility_id,coalesce(x.course_id,p.course_id) AS course_id,NULL AS round_id FROM architecture_event x LEFT JOIN component p ON p.id=x.component_id
UNION ALL
SELECT id,observation_id,facility_id,course_id,NULL AS round_id FROM quality_rating;
CREATE VIEW optional_scope_violation AS
SELECT x.id FROM optional_subject_scope x JOIN source_observation o ON o.id=x.observation_id
LEFT JOIN fact_group g ON g.id=o.retained_group_id
LEFT JOIN course c ON c.id=x.course_id LEFT JOIN round_option r ON r.id=x.round_id
LEFT JOIN course rc ON rc.id=r.course_id
WHERE (o.retained_facility_id IS NOT NULL AND
       coalesce(x.facility_id,c.facility_id,r.facility_id,rc.facility_id)!=o.retained_facility_id)
 OR (g.id IS NOT NULL AND (
  coalesce(x.facility_id,c.facility_id,r.facility_id,rc.facility_id)!=coalesce(g.facility_id,(SELECT facility_id FROM course WHERE id=g.course_id))
  OR (g.course_id IS NOT NULL AND (
   (x.course_id IS NOT NULL AND x.course_id!=g.course_id)
   OR (x.course_id IS NULL AND x.round_id IS NULL)
   OR (x.round_id IS NOT NULL AND (r.course_id IS NULL OR r.course_id!=g.course_id)
       AND NOT EXISTS(SELECT 1 FROM round_component member LEFT JOIN component part ON part.id=member.component_id
          WHERE member.round_id=x.round_id AND coalesce(member.course_id,part.course_id)=g.course_id))
  ))
 ));
CREATE VIEW price_bundle_scope_violation AS
SELECT p.id FROM price_observation p
LEFT JOIN course c ON c.id=p.course_id LEFT JOIN round_option own_round ON own_round.id=p.round_id
LEFT JOIN course own_course ON own_course.id=own_round.course_id
JOIN round_option prior_round ON prior_round.id=p.qualifying_prior_round_id
LEFT JOIN course prior_course ON prior_course.id=prior_round.course_id
WHERE coalesce(p.facility_id,c.facility_id,own_round.facility_id,own_course.facility_id)!=coalesce(prior_round.facility_id,prior_course.facility_id);
CREATE VIEW observation_reference_violation AS
SELECT o.id FROM source_observation o JOIN fact_group g ON g.id=o.retained_group_id
LEFT JOIN course c ON c.id=g.course_id
WHERE o.retained_facility_id IS NOT NULL AND o.retained_facility_id!=coalesce(g.facility_id,c.facility_id);
CREATE TRIGGER source_observation_insert AFTER INSERT ON source_observation BEGIN
 SELECT RAISE(ABORT,'retained observation references different facilities') WHERE EXISTS(SELECT 1 FROM observation_reference_violation);
END;
CREATE TRIGGER source_observation_update BEFORE UPDATE ON source_observation
 WHEN EXISTS(SELECT 1 FROM optional_subject_scope x WHERE x.observation_id=OLD.id) BEGIN
 SELECT RAISE(ABORT,'referenced source observation is immutable; create a new observation');
END;
CREATE TRIGGER source_observation_reference_update AFTER UPDATE ON source_observation BEGIN
 SELECT RAISE(ABORT,'retained observation references different facilities') WHERE EXISTS(SELECT 1 FROM observation_reference_violation);
 SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation);
END;
CREATE TRIGGER retained_group_used_update BEFORE UPDATE ON fact_group
 WHEN EXISTS(SELECT 1 FROM source_observation o WHERE o.retained_group_id=OLD.id) BEGIN
 SELECT RAISE(ABORT,'referenced retained source payload is immutable');
END;
CREATE TRIGGER retained_facility_used_update BEFORE UPDATE ON retained_evidence
 WHEN EXISTS(SELECT 1 FROM source_observation o WHERE o.retained_facility_id=OLD.facility_id) BEGIN
 SELECT RAISE(ABORT,'referenced retained facility evidence is immutable');
END;

CREATE INDEX physical_characteristics_subject ON physical_characteristics(facility_id,course_id,component_id);
CREATE TRIGGER physical_characteristics_insert AFTER INSERT ON physical_characteristics BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER physical_characteristics_update AFTER UPDATE ON physical_characteristics BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX amenity_observation_subject ON amenity_observation(facility_id,course_id);
CREATE TRIGGER amenity_observation_insert AFTER INSERT ON amenity_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER amenity_observation_update AFTER UPDATE ON amenity_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX practice_observation_subject ON practice_observation(facility_id,course_id);
CREATE TRIGGER practice_observation_insert AFTER INSERT ON practice_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER practice_observation_update AFTER UPDATE ON practice_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX service_observation_subject ON service_observation(facility_id,course_id);
CREATE TRIGGER service_observation_insert AFTER INSERT ON service_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER service_observation_update AFTER UPDATE ON service_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX policy_observation_subject ON policy_observation(facility_id,course_id,round_id);
CREATE TRIGGER policy_observation_insert AFTER INSERT ON policy_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER policy_observation_update AFTER UPDATE ON policy_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX operating_period_subject ON operating_period(facility_id,course_id);
CREATE TRIGGER operating_period_insert AFTER INSERT ON operating_period BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER operating_period_update AFTER UPDATE ON operating_period BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX accessibility_observation_subject ON accessibility_observation(facility_id,course_id);
CREATE TRIGGER accessibility_observation_insert AFTER INSERT ON accessibility_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER accessibility_observation_update AFTER UPDATE ON accessibility_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX price_observation_subject ON price_observation(facility_id,course_id,round_id);
CREATE TRIGGER price_observation_insert AFTER INSERT ON price_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER price_observation_update AFTER UPDATE ON price_observation BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX architecture_event_subject ON architecture_event(facility_id,course_id,component_id);
CREATE TRIGGER architecture_event_insert AFTER INSERT ON architecture_event BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER architecture_event_update AFTER UPDATE ON architecture_event BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE INDEX quality_rating_subject ON quality_rating(facility_id,course_id);
CREATE TRIGGER quality_rating_insert AFTER INSERT ON quality_rating BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;
CREATE TRIGGER quality_rating_update AFTER UPDATE ON quality_rating BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE TRIGGER optional_course_parent_update AFTER UPDATE OF facility_id ON course BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE TRIGGER optional_component_parent_update AFTER UPDATE OF course_id ON component BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE TRIGGER optional_round_option_parent_update AFTER UPDATE OF facility_id,course_id ON round_option BEGIN SELECT RAISE(ABORT,'optional observation must share source facility') WHERE EXISTS(SELECT 1 FROM optional_scope_violation); SELECT RAISE(ABORT,'qualifying prior round must share price facility') WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation); END;

CREATE VIEW physical_characteristics_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM physical_characteristics x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW amenity_observation_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM amenity_observation x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW practice_observation_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM practice_observation x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW service_observation_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM service_observation x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW policy_observation_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM policy_observation x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW operating_period_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM operating_period x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW accessibility_observation_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM accessibility_observation x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW price_observation_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM price_observation x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW architecture_event_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM architecture_event x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;

CREATE VIEW quality_rating_facts AS SELECT x.*,o.source_id,s.url AS source_url,o.collected_on,o.observed_on,o.effective_from,o.effective_to,o.status,o.conflict,o.qualification FROM quality_rating x JOIN source_observation o ON o.id=x.observation_id LEFT JOIN source s ON s.id=o.source_id;


-- Recheck source-course support whenever facility-round membership changes.
-- INSERT also covers SQLite INSERT OR REPLACE of an existing member row.
CREATE TRIGGER optional_round_component_membership_insert
AFTER INSERT ON round_component BEGIN
 SELECT RAISE(ABORT,'round membership must retain optional observation source support')
 WHERE EXISTS(SELECT 1 FROM optional_scope_violation);
 SELECT RAISE(ABORT,'qualifying prior round must share price facility')
 WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation);
END;
CREATE TRIGGER optional_round_component_membership_update
AFTER UPDATE ON round_component BEGIN
 SELECT RAISE(ABORT,'round membership must retain optional observation source support')
 WHERE EXISTS(SELECT 1 FROM optional_scope_violation);
 SELECT RAISE(ABORT,'qualifying prior round must share price facility')
 WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation);
END;
CREATE TRIGGER optional_round_component_membership_delete
AFTER DELETE ON round_component BEGIN
 SELECT RAISE(ABORT,'round membership must retain optional observation source support')
 WHERE EXISTS(SELECT 1 FROM optional_scope_violation);
 SELECT RAISE(ABORT,'qualifying prior round must share price facility')
 WHERE EXISTS(SELECT 1 FROM price_bundle_scope_violation);
END;
