# OpenStreetMap golf-course metadata audit

Generated from the cached sample dated 2026-08-02T19:37:36.172Z. Percentages use **OSM leisure=golf_course objects** as the denominator.

## Measured sample

The audit reads the retained JSON Lines sample incrementally. The capture query records each `leisure=golf_course` object and, for course areas, contained layout relations, clubhouses, entrances, and parking objects. It does not download a national extract or affect runtime discovery.

| Region | Courses | Name | Holes | Par | Access evidence | Website | Address |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Chicago metropolitan area | 25 | 25 | 0 | 0 | 3 | 8 | 13 |
| New York metropolitan area | 6 | 6 | 0 | 0 | 2 | 5 | 5 |
| Phoenix metropolitan area | 57 | 53 | 42 | 42 | 6 | 41 | 42 |
| North Carolina Triangle | 26 | 23 | 1 | 0 | 1 | 13 | 11 |

Total: 114 course objects, 0 layout relations, and 152 routing-target objects. 4 objects share a normalized name. These are object counts, not deduplicated facilities.

The imbalance is material to aggregate percentages: Phoenix supplies 42 of 43 objects with holes evidence and all 42 objects with par evidence. The sample still exposes useful tag shapes and failure modes, but its percentages must not be generalized to the United States.

## Measured metadata coverage

| Field | Evidence | Normalizable | Ambiguous or unusable | Unknown | Card | Filter |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Course name | 107 (93.9%) | 107 (93.9%) | 0 | 7 | supported | not suitable |
| Holes | 43 (37.7%) | 42 (36.8%) | 1 | 72 | conditional | later, with Unknown |
| Par | 42 (36.8%) | 36 (31.6%) | 6 | 78 | conditional | defer |
| Access / municipal evidence | 12 (10.5%) | 9 (7.9%) | 3 | 105 | conditional | later, with Unknown |
| Course format / type | 43 (37.7%) | 1 (0.9%) | 42 | 113 | defer | defer |
| Operator | 12 (10.5%) | 12 (10.5%) | 0 | 102 | conditional | not suitable |
| Website | 67 (58.8%) | 67 (58.8%) | 0 | 47 | conditional | not suitable |
| Address fields | 71 (62.3%) | 69 (60.5%) | 2 | 45 | conditional | not suitable |
| Contained clubhouse candidate | 23 (20.2%) | 20 (17.5%) | 3 | 94 | not suitable | not suitable |
| Contained entrance candidate | 6 (5.3%) | 1 (0.9%) | 5 | 113 | not suitable | not suitable |
| Contained parking candidate | 58 (50.9%) | 0 (0.0%) | 58 | 114 | not suitable | not suitable |
| Geometry-derived fallback | 114 (100.0%) | 114 (100.0%) | 0 | 0 | not suitable | not suitable |

Unknown means that no single usable normalized value is available. Conflicting or unusable evidence is therefore both ambiguous and unknown.

## Observed tags and values

- **Course name:** tags `name` (107); leading values `name=Arizona Grand Golf Course` (2), `name=Mesquite Course` (2), `name=Aguila Golf Course` (1), `name=Ancala Country Club` (1), `name=Arizona Biltmore Estates Course` (1).
- **Holes:** tags `golf:course` (43); leading values `golf:course=18_hole` (29), `golf:course=9_hole` (6), `golf:course=27_hole` (4), `golf:course=36_hole` (3), `golf:course=pitch_and_putt` (1).
- **Par:** tags `golf:par` (42); leading values `golf:par=72` (14), `golf:par=71` (8), `golf:par=27` (2), `golf:par=30` (2), `golf:par=36 + 36 + 36` (2).
- **Access / municipal evidence:** tags `access` (9), `owner` (3), `ownership` (2); leading values `access=private` (7), `owner=Forest Preserve District of Cook County` (3), `access=yes` (2), `ownership=government` (2).
- **Course format / type:** tags `golf:course` (43); leading values `golf:course=18_hole` (29), `golf:course=9_hole` (6), `golf:course=27_hole` (4), `golf:course=36_hole` (3), `golf:course=pitch_and_putt` (1).
- **Operator:** tags `operator` (12); leading values `operator=Indigo Sports` (3), `operator=Arizona Grand Resort & Spa` (2), `operator=City of Phoenix` (2), `operator=Bally's` (1), `operator=Chicago Park District` (1).
- **Website:** tags `website` (66), `contact:website` (1); leading values `contact:website=http://www.clubcorp.com/Clubs/Lochmere-Golf-Club/Amenities/Golf` (1), `website=http://arizonagrandresort.com/arizona-golf-courses.php` (1), `website=http://bellairgolf.com/` (1), `website=http://dobsonranchgolfcourse.com/` (1), `website=http://www.golftempeaz.com/ken-mcdonald/` (1).
- **Address fields:** tags `addr:city` (69), `addr:housenumber` (69), `addr:postcode` (69), `addr:street` (69), `addr:state` (59), `addr:country` (33), `addr:full` (1), `addr:housename` (1), `addr:unit` (1); leading values `addr:state=AZ` (41), `addr:country=US` (33), `addr:city=Phoenix` (19), `addr:city=Scottsdale` (12), `addr:state=IL` (12).
- **Contained clubhouse candidate:** tags `golf` (31), `building` (29), `addr:city` (14), `addr:housenumber` (14), `addr:postcode` (14), `addr:state` (14), `addr:street` (14), `name` (14), `access` (5), `addr:country` (2), `website` (2), `addr:street:name` (1), `addr:street:prefix` (1), `addr:street:type` (1), `fee` (1), `operator` (1); leading values `golf=clubhouse` (31), `building=yes` (26), `addr:state=IL` (6), `addr:state=AZ` (5), `access=private` (3).
- **Contained entrance candidate:** tags `entrance` (11); leading values `entrance=main` (6), `entrance=service` (3), `entrance=exit` (1), `entrance=yes` (1).
- **Contained parking candidate:** tags `amenity` (110), `parking` (65), `access` (31), `surface` (27), `fee` (14), `operator` (6), `owner` (5), `ownership` (5), `operator:type` (1); leading values `amenity=parking` (108), `parking=surface` (60), `surface=asphalt` (27), `fee=no` (13), `access=private` (11).
- **Geometry-derived fallback:** tags `course_object` (114); leading values `course_object=way` (73), `course_object=relation` (34), `course_object=node` (7).

## Zero-layout investigation

The zero layout count is a real result for these bounds, not a parser failure. A focused Overpass search on 2026-08-02 found no `type=golf`, deprecated `route=golf`, or `golf:course:name` relations anywhere in the four sample boxes. As a control, the capture query's same `relation(area.courseArea)["type"="golf"]` expression returned both documented course layouts for OSM facility relation 10852837 in Kalmar, Sweden.

The `type=golf` relation scheme is proposed and was documented shortly before this snapshot. Zero in this small US sample therefore says nothing reliable about nationwide layout coverage. It only means the sampled facility objects carry the measured holes/par evidence directly and no associated layout records were available to clarify multi-course scope.

## Normalization recommendations

- Keep stable source identity, coordinates with approximation provenance, and nullable name, holes, par, access, format, operator, website, and structured address.
- Preserve optional layout records rather than forcing several layouts into one holes/par scalar.
- Normalize holes and par only from explicit numeric tags with unambiguous scope.
- Normalize public, private, or municipal only from explicit tags. Do not infer access or ownership from names or operator text.
- Preserve mapped clubhouse, entrance, and parking objects as candidates. Select none without later vehicle-access and routing validation.
- Keep unknown explicit for every incomplete intrinsic field.

## Product recommendations

Name is supported for course cards. Holes, par, access, operator, website, and address are conditional on source evidence. Course format is deferred: the sample supplied one explicit `pitch_and_putt` value and no reliable executive, full-length, or par-3 evidence.

Holes and access are structurally suitable for future intrinsic predicates only with an explicit **Unknown** choice. Their 36.8% and 7.9% sample normalization rates do not justify enabling filters before the generated catalog is measured. Intrinsic predicates run before routing; travel-time predicates run after routing.

Google and other external ratings remain deferred pending a separate product, licensing, cost, attribution, place-matching, and provider decision.

## Future catalog planning estimate

Plan provisionally for roughly 15,000–20,000 logical records, 10–25 MB of compact uncompressed JSON/JSONL, and 3–8 MB compressed. The record range is informed by the public [OpenGolf US 2026 OSM import plan](https://wiki.openstreetmap.org/wiki/Import/OpenGolf_US_2026), not by this sample and not by a measured contiguous-US catalog. Measure and replace these estimates when the catalog-generation slice exists.

## Limitations

- Exploratory metropolitan samples are neither random nor representative of nationwide or rural coverage.
- Counts are per OSM object, not deduplicated real-world facility.
- Phoenix supplies half the objects, so aggregate percentages are regionally skewed.
- Contained-target coverage requires an area feature and mapped internal objects; node courses cannot contain targets.
- No field is inferred from a course name.
