"""Native5 browse DTOs. Operational facts come only from explicit SQL columns."""

import math
from contextlib import closing

from .catalog_native import BOOLEANS, DOMAINS, connect
from .catalog_native_common import distance_km, require


def _booleans(record):
    row = dict(record)
    for key in BOOLEANS & row.keys():
        if row[key] is not None:
            row[key] = bool(row[key])
    return row


def read_optional(db, **subject):
    """Exact subject only: never inherit facility facts into course assertions."""
    require(
        len(subject) == 1
        and next(iter(subject))
        in {"facility_id", "course_id", "component_id", "round_id"},
        "choose one exact optional subject",
    )
    column, identifier = next(iter(subject.items()))
    require(isinstance(identifier, str) and identifier, "subject ID required")
    result = {table: [] for table in DOMAINS}
    for table in DOMAINS:
        columns = {r["name"] for r in db.execute("PRAGMA table_info(" + table + ")")}
        if column not in columns:
            continue
        result[table] = [
            _booleans(row)
            for row in db.execute(
                "SELECT x.*,s.license AS source_license,s.attribution AS source_attribution FROM "
                + table
                + "_facts x LEFT JOIN source s ON s.id=x.source_id WHERE x."
                + column
                + "=? ORDER BY x.id",
                (identifier,),
            )
        ]
    for event in result["architecture_event"]:
        event["credits"] = [
            dict(r)
            for r in db.execute(
                "SELECT c.id,c.role,p.id AS party_id,p.name,p.party_kind FROM architecture_credit c JOIN design_party p ON p.id=c.party_id WHERE c.event_id=? ORDER BY c.id",
                (event["id"],),
            )
        ]
    return result


def _address(record, *, scope):
    fields = {
        name: record["address_" + name]
        for name in (
            "text",
            "purpose",
            "street_line1",
            "street_line2",
            "city",
            "region",
            "postal_code",
            "country",
        )
    }
    return (
        fields | {"scope": scope}
        if any(v is not None for v in fields.values())
        else None
    )


def _map(record):
    return (
        {
            "latitude": record["latitude"],
            "longitude": record["longitude"],
            "kind": record["location_kind"],
        }
        if record["latitude"] is not None
        else None
    )


def _rounds(db, *, facility_id=None, course_id=None):
    if course_id is None:
        clause, args = "r.facility_id=?", [facility_id]
    else:
        clause, args = (
            """r.course_id=? OR EXISTS(SELECT 1 FROM round_component m
            LEFT JOIN component p ON p.id=m.component_id
            WHERE m.round_id=r.id AND coalesce(m.course_id,p.course_id)=?)""",
            [course_id, course_id],
        )
    result = []
    for record in db.execute(
        "SELECT r.* FROM round_option r WHERE " + clause + " ORDER BY r.id", args
    ):
        row = dict(record)
        row["scope"] = "facility" if row["facility_id"] else "course"
        row["members"] = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM round_component WHERE round_id=? ORDER BY ordinal,id",
                (row["id"],),
            )
        ]
        row["tee_sets"] = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM tee_set WHERE round_id=? ORDER BY id", (row["id"],)
            )
        ]
        row["optional"] = read_optional(db, round_id=row["id"])
        result.append(row)
    return result


def _eligibility(course):
    # Preserve the reviewed preliminary public-play policy without rewriting
    # a nullable booking fact or claiming an affiliation-only offer is ordinary.
    if course["nonmember_bookable"] is not None:
        return course["nonmember_bookable"], "explicit_nonmember_fact"
    if course["access"] == "public":
        return True, "accepted_public_play_with_qualification"
    return (None if course["access"] is None else False), "unknown_or_nonpublic_access"


def _course(db, record):
    card = _booleans(record)
    facility = dict(
        db.execute(
            "SELECT * FROM facility WHERE id=?", (card["facility_id"],)
        ).fetchone()
    )
    card["course_id"] = card.pop("id")
    card.update(
        {
            "facility_name": facility["name"],
            "state": facility["state"],
            "country": facility["country"],
            "county": facility["county"],
            "facility_access": facility["access"],
            "facility_operating_status": facility["operating_status"],
            "facility_physical_holes": facility["physical_holes"],
            "inventory_complete": bool(facility["inventory_complete"])
            if facility["inventory_complete"] is not None
            else None,
            "facility_website": facility["website"],
        }
    )
    card["map_location"] = _map(facility)
    card["address"] = (
        _address(facility, scope="facility")
        if card["address_mode"] == "inherit"
        else _address(card, scope="course")
        if card["address_mode"] == "override"
        else None
    )
    card["arrival"] = (
        {
            "latitude": card["arrival_latitude"],
            "longitude": card["arrival_longitude"],
            "kind": card["arrival_kind"],
            "reference": card["arrival_reference"],
        }
        if card["arrival_latitude"] is not None
        else None
    )
    destination = None
    if card["arrival"]:
        destination = {
            "id": card["course_id"],
            "latitude": card["arrival_latitude"],
            "longitude": card["arrival_longitude"],
            "precision": card["arrival_kind"],
            "reference": card["arrival_reference"],
            "scope": "course_arrival",
        }
    elif card["map_location"]:
        destination = {
            "id": card["facility_id"],
            "latitude": facility["latitude"],
            "longitude": facility["longitude"],
            "precision": facility["location_kind"],
            "scope": "facility_estimate",
            "qualification": "approximate planning estimate; does not establish an entrance",
        }
    card["destination_id"] = destination["id"] if destination else None
    card["plan_eligible"], card["planning_basis"] = _eligibility(card)
    card["booking_availability"] = None
    card["access_qualification"] = card["booking_conditions"]
    card["optional"] = read_optional(db, course_id=card["course_id"])
    card["round_options"] = _rounds(db, course_id=card["course_id"])
    card["tee_sets"] = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM tee_set WHERE course_id=? ORDER BY id", (card["course_id"],)
        )
    ]
    card["components"] = []
    for component in db.execute(
        "SELECT * FROM component WHERE course_id=? ORDER BY id", (card["course_id"],)
    ):
        part = dict(component)
        part["optional"] = read_optional(db, component_id=part["id"])
        card["components"].append(part)
    card["aliases"] = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM alias WHERE course_id=? ORDER BY id", (card["course_id"],)
        )
    ]
    return card, destination


def _facility(db, record):
    card = _booleans(record)
    card["facility_id"] = card.pop("id")
    card["map_location"] = _map(card)
    card["address"] = _address(card, scope="facility")
    card["optional"] = read_optional(db, facility_id=card["facility_id"])
    card["course_inventory"] = [
        _booleans(r)
        for r in db.execute(
            "SELECT id AS course_id,name,physical_holes,identity_status,access,nonmember_bookable FROM course WHERE facility_id=? ORDER BY id",
            (card["facility_id"],),
        )
    ]
    card["course_ids"] = [r["course_id"] for r in card["course_inventory"]]
    card["course_count"] = len(card["course_ids"])
    card["documented_course_ids"] = [
        r["course_id"]
        for r in card["course_inventory"]
        if r["identity_status"] == "operator_defined"
    ]
    card["documented_course_count"] = len(card["documented_course_ids"])
    card["round_options"] = _rounds(db, facility_id=card["facility_id"])
    card["aliases"] = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM alias WHERE facility_id=? ORDER BY id",
            (card["facility_id"],),
        )
    ]
    card["inventory_qualification"] = (
        "empty inventory does not establish zero physical courses; retained components are not independent course identities"
    )
    return card


def _filters(
    *,
    state=None,
    country=None,
    county=None,
    access=None,
    style=None,
    holes=None,
    search=None,
    bbox=None,
    center=None,
    radius_km=None,
    courses=False,
):
    require(courses or style is None, "style filter applies only to courses")
    clauses, args = [], []
    for column, value in (
        ("f.state", state),
        ("f.country", country),
        ("f.county", county),
        ("c.access" if courses else "f.access", access),
        ("c.style", style),
        ("c.physical_holes" if courses else "f.physical_holes", holes),
    ):
        if value is None:
            continue
        require(
            (type(value) is int and value > 0)
            if column.endswith("physical_holes")
            else (
                isinstance(value, str)
                and 0 < len(value.strip()) <= 256
                and "\x00" not in value
            ),
            "invalid native filter",
        )
        if value == "unknown" and column.endswith((".access", ".style")):
            clauses.append(column + " IS NULL")
        else:
            clauses.append(column + "=?")
            args.append(value)
    if search is not None:
        require(
            isinstance(search, str)
            and 0 < len(search.strip()) <= 256
            and "\x00" not in search,
            "invalid literal search",
        )
        literal = (
            "%"
            + search.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            + "%"
        )
        subject = "c" if courses else "f"
        alias_col = "course_id" if courses else "facility_id"
        clauses.append(
            "("
            + subject
            + ".name LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM alias a WHERE a."
            + alias_col
            + "="
            + subject
            + ".id AND a.name LIKE ? ESCAPE '\\'))"
        )
        args.extend([literal, literal])
    if bbox is not None:
        require(
            isinstance(bbox, (tuple, list))
            and len(bbox) == 4
            and all(type(n) in {int, float} and math.isfinite(n) for n in bbox),
            "invalid bounding box",
        )
        south, west, north, east = bbox
        require(
            -90 <= south <= north <= 90 and -180 <= west <= 180 and -180 <= east <= 180,
            "invalid bounding box",
        )
        clauses.append("f.latitude BETWEEN ? AND ?")
        args.extend([south, north])
        clauses.append(
            "f.longitude BETWEEN ? AND ?"
            if west <= east
            else "(f.longitude>=? OR f.longitude<=?)"
        )
        args.extend([west, east])
    if center is not None or radius_km is not None:
        require(
            isinstance(center, (tuple, list))
            and len(center) == 2
            and all(type(n) in {int, float} and math.isfinite(n) for n in center)
            and abs(center[0]) <= 90
            and abs(center[1]) <= 180
            and type(radius_km) in {int, float}
            and math.isfinite(radius_km)
            and 0 <= radius_km <= 20040,
            "invalid distance filter",
        )
        clauses.append(
            "f.latitude IS NOT NULL AND distance_km(?,?,f.latitude,f.longitude)<=?"
        )
        args.extend([*center, radius_km])
    return clauses, args


def _query(
    path,
    *,
    courses,
    limit,
    offset,
    round_holes=None,
    plan=False,
    include_review=True,
    **filters,
):
    require(
        type(limit) is int
        and 1 <= limit <= 1000
        and type(offset) is int
        and offset >= 0,
        "invalid pagination",
    )
    require(
        type(plan) is bool and type(include_review) is bool,
        "invalid planning/review flag",
    )
    require(
        courses or (not plan and include_review and round_holes is None),
        "course-only filters cannot select facilities",
    )
    clauses, args = _filters(courses=courses, **filters)
    if plan:
        clauses.append(
            "(c.nonmember_bookable=1 OR (c.nonmember_bookable IS NULL AND c.access='public'))"
        )
    if not include_review:
        clauses.append("c.identity_status='operator_defined'")
    if round_holes is not None:
        require(type(round_holes) is int and round_holes > 0, "invalid round length")
        clauses.append("""EXISTS(SELECT 1 FROM round_option r WHERE r.round_holes=? AND
            (r.course_id=c.id OR EXISTS(SELECT 1 FROM round_component m LEFT JOIN component p ON p.id=m.component_id
            WHERE m.round_id=r.id AND coalesce(m.course_id,p.course_id)=c.id)))""")
        args.append(round_holes)
    subject = "c" if courses else "f"
    sql = (
        "SELECT "
        + subject
        + ".* FROM facility f"
        + (" JOIN course c ON c.facility_id=f.id" if courses else "")
    )
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    with closing(connect(path)) as db:
        try:
            db.create_function("distance_km", 4, distance_km, deterministic=True)
            db.execute("BEGIN")
            total = db.execute("SELECT count(*) FROM (" + sql + ")", args).fetchone()[0]
            records = db.execute(
                sql
                + " ORDER BY f.name,f.id"
                + (",c.name,c.id" if courses else "")
                + " LIMIT ? OFFSET ?",
                args + [limit, offset],
            ).fetchall()
            rows, destinations = [], {}
            for record in records:
                if courses:
                    card, destination = _course(db, record)
                    if destination:
                        destinations[destination["id"]] = destination
                else:
                    card = _facility(db, record)
                if filters.get("center") is not None:
                    loc = card["map_location"]
                    card["distance_km"] = distance_km(
                        *filters["center"], loc["latitude"], loc["longitude"]
                    )
                rows.append(card)
            result = {
                "schema": 5,
                "revision": db.execute(
                    "SELECT revision FROM catalog_state WHERE id=1"
                ).fetchone()[0],
                "courses" if courses else "facilities": rows,
                "limit": limit,
                "offset": offset,
                "total": total,
                "has_more": offset + len(rows) < total,
                "qualification": "dated typed facts; unknowns remain null; physical holes differ from round length; no live booking availability",
            }
            if courses:
                result["destinations"] = list(destinations.values())
            return result
        finally:
            db.close()


def query_courses(
    path,
    *,
    limit=100,
    offset=0,
    round_holes=None,
    plan=False,
    include_review=True,
    **filters,
):
    return _query(
        path,
        courses=True,
        limit=limit,
        offset=offset,
        round_holes=round_holes,
        plan=plan,
        include_review=include_review,
        **filters,
    )


def query_facilities(path, *, limit=100, offset=0, **filters):
    return _query(path, courses=False, limit=limit, offset=offset, **filters)
