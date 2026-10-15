"""Local SQLite catalog and single-writer intake. No HTTP, routing or geocoding."""

import fcntl
import gzip
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from .catalog_sources import ensure_source_allowed, install_holds, resource_identity

SCHEMA = Path(__file__).with_name("catalog_schema") / "001.sql"
TABLES = {
    "facility",
    "course",
    "component",
    "round_option",
    "round_component",
    "tee_set",
    "fact_group",
    "alias",
}
PREFIX = {
    "facility": "f",
    "course": "c",
    "component": "p",
    "round_option": "r",
    "tee_set": "t",
    "fact_group": "g",
    "round_component": "l",
    "alias": "a",
}
MODULES = {
    "access",
    "operations",
    "prices",
    "architecture",
    "turf",
    "mobility",
    "amenities",
    "practice",
    "services",
    "accessibility",
    "overview",
}
BOOLEANS = {"inventory_complete", "nonmember_bookable", "conflict"}
INTEGERS = {"physical_holes", "round_holes", "par", "slope", "repetitions"}
NUMBERS = {
    "latitude",
    "longitude",
    "arrival_latitude",
    "arrival_longitude",
    "yardage",
    "difficulty_rating",
}


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return sha256(encoded(value).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_date(value):
    require(
        isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
        "date must be YYYY-MM-DD",
    )
    date.fromisoformat(value)


def valid_url(value):
    require(isinstance(value, str), "URL must be text")
    parsed = urlsplit(value)
    require(
        parsed.scheme in {"https", "http"}
        and parsed.hostname
        and not (parsed.username or parsed.password),
        "invalid source/link URL",
    )


def local_path(path):
    """Refuse known network filesystems; operationally only the integrator owns this path."""
    path = Path(path).resolve()
    mounts = Path("/proc/mounts")
    if mounts.exists():
        entries = [line.split() for line in mounts.read_text().splitlines()]
        matches = [
            row
            for row in entries
            if path.is_relative_to(Path(row[1].replace("\\040", " ")))
        ]
        if matches:
            nearest = max(matches, key=lambda row: len(row[1]))
            require(
                nearest[2]
                not in {
                    "nfs",
                    "nfs4",
                    "cifs",
                    "smbfs",
                    "sshfs",
                    "fuse.sshfs",
                    "9p",
                    "ceph",
                    "glusterfs",
                },
                "catalog must be on local storage",
            )
    return path


def connect(path, *, readonly=False):
    path = local_path(path)
    connection = sqlite3.connect(
        path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True, timeout=0
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    if readonly:
        connection.execute("PRAGMA query_only=ON")
    require(
        connection.execute("SELECT max(version) FROM schema_migration").fetchone()[0]
        in {1, 2, 3, 4},
        "unsupported SQLite schema",
    )
    return connection


def migrate_sqlite(db):
    version = db.execute("SELECT max(version) FROM schema_migration").fetchone()[0]
    changed = False
    for number in (2, 3, 4):
        if version < number:
            db.executescript((SCHEMA.parent / f"{number:03}.sql").read_text())
            version = number
            changed = True
    if changed:
        found = db.execute(
            "SELECT payload FROM retained_document WHERE name='source_stops'"
        ).fetchone()
        install_holds(db, json.loads(found[0]) if found else {})
        db.commit()
    require(version == 4, "unsupported SQLite schema")


def create(path):
    path = local_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents replacing accepted data on a rerun.
    with path.open("xb"):
        pass
    db = sqlite3.connect(path)
    try:
        db.executescript(SCHEMA.read_text())
        migrate_sqlite(db)
        db.commit()
    except Exception:
        db.close()
        path.unlink()
        raise
    db.close()


@contextmanager
def writer(path):
    path = local_path(path)
    with Path(str(path) + ".writer.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another integration writer owns this catalog") from error
        db = connect(path)
        try:
            require(
                db.execute("SELECT max(version) FROM schema_migration").fetchone()[0]
                == 4,
                "restore a research copy with the native SQLite migration before writing",
            )
            db.execute("BEGIN IMMEDIATE")
            yield db
        finally:
            db.rollback()
            db.close()


def row(db, table, identifier):
    require(table in TABLES, "unknown entity type")
    found = db.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
    return dict(found) if found else None


def put(db, table, values):
    require(table in TABLES, "unknown entity type")
    columns = list(values)
    allowed = {item["name"] for item in db.execute(f"PRAGMA table_info({table})")}
    require(set(columns) <= allowed, "unknown core fields")
    sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
    db.execute(sql, [values[key] for key in columns])


def check(db):
    integrity = [r[0] for r in db.execute("PRAGMA integrity_check")]
    foreign_keys = [list(r) for r in db.execute("PRAGMA foreign_key_check")]
    require(
        integrity == ["ok"] and not foreign_keys,
        "database integrity/foreign key failure",
    )
    mismatches = db.execute("""SELECT f.id FROM facility f JOIN course c ON c.facility_id=f.id
        WHERE f.inventory_complete=1 AND f.physical_holes IS NOT NULL
        AND c.identity_status!='component'
        GROUP BY f.id HAVING count(c.physical_holes)=count(*) AND sum(c.physical_holes)!=f.physical_holes""").fetchall()
    require(not mismatches, "complete physical inventory does not match facility holes")
    version = db.execute("SELECT max(version) FROM schema_migration").fetchone()[0]
    if version >= 4:
        require(
            not db.execute("SELECT id FROM round_scope_violation").fetchone(),
            "round member must share its parent facility and course scope",
        )
    require(
        not db.execute("""SELECT t.id FROM tee_set t JOIN round_option r ON r.id=t.round_id
        WHERE t.course_id!=r.course_id""").fetchone(),
        "tee round belongs to another course",
    )
    require(
        not db.execute("""SELECT rc.round_id FROM round_component rc
        JOIN round_option r ON r.id=rc.round_id JOIN component p ON p.id=rc.component_id
        WHERE r.course_id!=p.course_id""").fetchone(),
        "round component belongs to another course",
    )
    require(
        not db.execute(
            "SELECT id FROM course WHERE arrival_latitude IS NOT NULL AND (arrival_longitude IS NULL OR arrival_kind IS NULL OR arrival_reference IS NULL OR length(trim(arrival_reference,char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)))=0)"
        ).fetchone(),
        "canonical arrival needs a nonempty reference",
    )
    return {"integrity_check": integrity, "foreign_key_check": foreign_keys}


def inventory(db):
    # Accounting for the frozen pre-cutover map rule; new browse includes all access.
    legacy_mapped = db.execute("""SELECT count(*) FROM facility f
        WHERE f.physical_holes>0 AND f.latitude IS NOT NULL
        AND f.location_kind IN ('property_point','reviewed_osm_point','verified_entrance')
        AND (f.access='public' OR (f.access IS NULL AND EXISTS(
        SELECT 1 FROM course c WHERE c.facility_id=f.id AND c.access='public')))""").fetchone()[
        0
    ]
    return {
        "accepted_map_eligible": legacy_mapped,
        "facilities": db.execute("SELECT count(*) FROM facility").fetchone()[0],
        "courses": db.execute("SELECT count(*) FROM course").fetchone()[0],
        "named_courses": db.execute("SELECT count(name) FROM course").fetchone()[0],
        "empty_inventories": db.execute(
            "SELECT count(*) FROM facility f WHERE NOT EXISTS(SELECT 1 FROM course c WHERE c.facility_id=f.id)"
        ).fetchone()[0],
        "non_null_arrivals": db.execute(
            "SELECT count(arrival_latitude) FROM course"
        ).fetchone()[0],
        "sources": db.execute("SELECT count(*) FROM source").fetchone()[0],
        "notes": db.execute("SELECT count(*) FROM note").fetchone()[0],
    }


def evidence(db, item, facility_id=None):
    require(isinstance(item, dict), "evidence must be an object")
    if item.get("origin") == "retained_normalization":
        require(
            set(item) == {"origin", "facility_id", "note_ids", "support_indexes"},
            "invalid retained-normalization evidence",
        )
        require(
            item["facility_id"] == facility_id,
            "retained evidence belongs to another facility",
        )
        found = db.execute(
            "SELECT payload FROM retained_evidence WHERE facility_id=?", (facility_id,)
        ).fetchone()
        require(found is not None, "no accepted retained evidence")
        accepted = json.loads(found[0])
        require(
            isinstance(item["note_ids"], list)
            and isinstance(item["support_indexes"], list)
            and (item["note_ids"] or item["support_indexes"]),
            "retained references required",
        )
        allowed = {
            n
            for refs in accepted.get("notes", {}).values()
            if isinstance(refs, list)
            for n in refs
        }
        for support in accepted.get("support", []):
            for key in ("notes", "note"):
                refs = support.get(key, [])
                allowed.update(refs if isinstance(refs, list) else [])
        require(
            all(isinstance(n, str) and n in allowed for n in item["note_ids"]),
            "note is not accepted facility evidence",
        )
        require(
            all(
                type(i) is int and 0 <= i < len(accepted.get("support", []))
                for i in item["support_indexes"]
            ),
            "invalid retained support index",
        )
        # Original source/date/null values stay in the referenced SQLite evidence. No invented collection date.
        payload = dict(item)
        payload["original_support"] = [
            accepted["support"][i] for i in item["support_indexes"]
        ]
        return {
            "source_id": None,
            "collected_on": None,
            "status": "extracted",
            "origin": "retained_normalization",
            "payload": encoded(payload),
        }
    require(
        set(item) == {"source_id", "collected_on", "status"},
        "source/date/status evidence required",
    )
    valid_date(item["collected_on"])
    require(item["status"] in {"extracted", "confirmed"}, "invalid extraction status")
    source = db.execute(
        "SELECT intake_policy FROM source WHERE id=?", (item["source_id"],)
    ).fetchone()
    require(
        source and source[0] == "permitted",
        "source is not cleared for new intake; retained evidence is not permission",
    )
    return item | {"origin": "new_extraction", "payload": None}


def validate_values(table, values, *, complete=True):
    require(isinstance(values, dict), "values must be an object")
    for key, value in values.items():
        if value is None:
            continue
        if key == "ordinal":
            require(
                type(value) is int and value >= 0,
                "ordinal must be a nonnegative integer",
            )
        elif key in BOOLEANS:
            require(type(value) is bool, f"{key} must be boolean or null")
        elif key in INTEGERS:
            require(
                type(value) is int and value > 0,
                f"{key} must be a positive integer or null",
            )
        elif key in NUMBERS:
            require(
                type(value) in {int, float} and math.isfinite(value),
                f"{key} must be finite numeric or null",
            )
        elif key == "payload":
            require(isinstance(value, dict), "module payload must be an object")
        else:
            require(
                isinstance(value, str) and value.strip(),
                f"{key} must be nonempty text or null",
            )
        if key.endswith("_url") or key == "website":
            valid_url(value)
        if key.endswith("_on") or key in {"effective_from", "effective_to"}:
            valid_date(value)
    if complete and table == "course" and values.get("arrival_latitude") is not None:
        require(
            values.get("arrival_longitude") is not None
            and values.get("arrival_kind")
            in {"reviewed_osm_point", "verified_entrance"}
            and isinstance(values.get("arrival_reference"), str)
            and values["arrival_reference"].strip(),
            "canonical arrival needs a nonempty reference",
        )
    if complete and table in {"round_option", "round_component", "tee_set"}:
        parents = {
            "round_option": ("facility_id", "course_id"),
            "round_component": ("component_id", "course_id"),
            "tee_set": ("course_id", "round_id"),
        }[table]
        require(
            sum(values.get(key) is not None for key in parents) == 1,
            f"{table} needs exactly one of {' or '.join(parents)}",
        )
    if table == "fact_group":
        require(
            values.get("module") in MODULES,
            "unknown optional module; quality rankings deferred",
        )
        if values["module"] == "prices":
            require(
                values.get("observed_on") is not None,
                "price observations need their own date",
            )
            payload = values.get("payload", {})
            require(
                {"currency", "basis"} <= payload.keys(),
                "prices need currency and rate basis",
            )
            require(
                isinstance(payload["currency"], str)
                and re.fullmatch("[A-Z]{3}", payload["currency"]),
                "invalid currency",
            )
            require(
                isinstance(payload["basis"], str) and payload["basis"].strip(),
                "invalid rate basis",
            )
            for key in ("amount", "minimum", "maximum"):
                if key in payload and payload[key] is not None:
                    require(
                        type(payload[key]) in {int, float}
                        and math.isfinite(payload[key])
                        and payload[key] >= 0,
                        "invalid price amount",
                    )


def facility_for(db, table, values):
    if table == "facility":
        return values["id"]
    if values.get("facility_id"):
        return values["facility_id"]
    if table == "round_component" or (table == "tee_set" and values.get("round_id")):
        parent = row(db, "round_option", values.get("round_id"))
        require(parent is not None, "missing round reference")
        return facility_for(db, "round_option", parent)
    else:
        course_id = values.get("course_id")
    require(course_id is not None, "entity needs a facility or course")
    parent = row(db, "course", course_id)
    require(parent is not None, "missing course reference")
    return parent["facility_id"]


def apply_batch(path, batch, *, apply=False):
    """All-or-nothing intake, reviewed row digests, idempotent IDs and durable summaries."""
    require(
        isinstance(batch, dict) and set(batch) == {"batch_id", "sources", "changes"},
        "invalid batch envelope",
    )
    require(
        isinstance(batch["batch_id"], str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", batch["batch_id"]),
        "invalid batch ID",
    )
    require(
        isinstance(batch["sources"], list)
        and isinstance(batch["changes"], list)
        and batch["changes"],
        "batch needs sources and changes arrays",
    )
    batch_digest = digest(batch)
    report = {
        "batch_id": batch["batch_id"],
        "digest": batch_digest,
        "state": "preview",
        "added": [],
        "updated": [],
        "conflicts": [],
        "flags": [],
    }
    with writer(path) as db:
        existing = db.execute(
            "SELECT digest,report FROM import_batch WHERE id=?", (batch["batch_id"],)
        ).fetchone()
        if existing:
            require(
                existing["digest"] == batch_digest,
                "batch ID reused with different contents",
            )
            return json.loads(existing["report"]) | {"state": "already_applied"}
        try:
            existing_resources = None
            for source in batch["sources"]:
                require(
                    isinstance(source, dict)
                    and set(source)
                    == {"id", "url", "license", "attribution", "controls_reference"},
                    "new source needs retained controls reference and license/attribution (nullable)",
                )
                require(
                    isinstance(source["id"], str) and source["id"].strip(),
                    "source ID must be nonempty text",
                )
                valid_url(source["url"])
                ensure_source_allowed(db, source["url"])
                require(
                    all(
                        source[k] is None or isinstance(source[k], str)
                        for k in ("license", "attribution")
                    ),
                    "license/attribution must be text or null",
                )
                require(
                    isinstance(source["controls_reference"], str)
                    and source["controls_reference"].strip(),
                    "missing source-control review reference",
                )
                if existing_resources is None:
                    existing_resources = {
                        resource_identity(r[0])
                        for r in db.execute("SELECT url FROM source")
                    }
                identity = resource_identity(source["url"])
                require(
                    db.execute(
                        "SELECT 1 FROM source WHERE id=?", (source["id"],)
                    ).fetchone()
                    is None
                    and identity not in existing_resources,
                    "source ID/resource already exists; integrator must clear existing policy separately",
                )
                existing_resources.add(identity)
                db.execute(
                    "INSERT INTO source VALUES (?,?,?,?,?)",
                    (
                        source["id"],
                        source["url"],
                        source["license"],
                        source["attribution"],
                        "permitted",
                    ),
                )
                # Store the reference inside the DB without creating a permission bypass for old sources.
                db.execute(
                    "INSERT INTO retained_document VALUES (?,?)",
                    (
                        "source-control:" + source["id"],
                        encoded({"reference": source["controls_reference"]}),
                    ),
                )
            seen, facilities = set(), set()
            for change in batch["changes"]:
                require(
                    isinstance(change, dict)
                    and set(change)
                    == {"entity", "id", "expected", "values", "evidence"},
                    "invalid change envelope",
                )
                table, identifier = change["entity"], change["id"]
                require(table in TABLES, "unknown entity type")
                require(
                    isinstance(identifier, str)
                    and re.fullmatch(
                        PREFIX[table] + r"-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
                        identifier,
                    ),
                    "invalid stable entity ID",
                )
                require((table, identifier) not in seen, "duplicate entity in batch")
                seen.add((table, identifier))
                before = row(db, table, identifier)
                if change["expected"] != (digest(before) if before else None):
                    report["conflicts"].append(
                        {
                            "entity": table,
                            "id": identifier,
                            "reason": "stale row or addition collides",
                            "current_digest": digest(before) if before else None,
                        }
                    )
                    continue
                retained = (
                    change["evidence"].get("origin") == "retained_normalization"
                    if isinstance(change["evidence"], dict)
                    else False
                )
                if retained:
                    require(
                        before is not None and table in {"facility", "course"},
                        "retained normalization only corrects existing core records",
                    )
                    require(
                        set(change["values"])
                        <= {
                            "nonmember_bookable",
                            "booking_conditions",
                            "style",
                            "identity_status",
                        },
                        "retained normalization cannot introduce unrelated/new facts",
                    )
                envelope = evidence(
                    db,
                    change["evidence"],
                    facility_for(db, table, before) if before else None,
                )
                require("id" not in change["values"], "identity cannot be changed")
                # Relations cannot be silently moved during a correction.
                if before:
                    require(
                        all(
                            key not in change["values"]
                            or change["values"][key] == before[key]
                            for key in (
                                "facility_id",
                                "course_id",
                                "round_id",
                                "component_id",
                            )
                            if key in before
                        ),
                        "parent identity cannot be changed",
                    )
                validate_values(
                    table, change["values"], complete=False
                ) if table != "fact_group" else None
                values = (before or {}) | change["values"] | {"id": identifier}
                for key in BOOLEANS & values.keys():
                    if key not in change["values"] and values[key] is not None:
                        values[key] = bool(values[key])
                if table == "fact_group":
                    values |= {
                        k: envelope[k] for k in ("source_id", "collected_on", "status")
                    }
                    if isinstance(values.get("payload"), str):
                        values["payload"] = json.loads(values["payload"])
                validate_values(table, values)
                if table == "fact_group":
                    values["payload"] = encoded(values["payload"])
                if before:
                    db.execute(
                        f"DELETE FROM {table} WHERE id=?", (identifier,)
                    ) if table == "fact_group" else None
                    if table != "fact_group":
                        columns = [k for k in change["values"]]
                        allowed = {
                            r["name"] for r in db.execute(f"PRAGMA table_info({table})")
                        }
                        require(set(columns) <= allowed, "unknown core fields")
                        if columns:
                            db.execute(
                                f"UPDATE {table} SET {','.join(k + '=?' for k in columns)} WHERE id=?",
                                [values[k] for k in columns] + [identifier],
                            )
                    else:
                        put(db, table, values)
                else:
                    put(db, table, values)
                after = row(db, table, identifier)
                facility_id = facility_for(db, table, after)
                if before != after:
                    facilities.add(facility_id)
                    report["updated" if before else "added"].append(
                        {
                            "entity": table,
                            "id": identifier,
                            "facility_id": facility_id,
                            "before": before,
                            "after": after,
                        }
                    )
                db.execute(
                    "INSERT INTO intake_evidence VALUES (?,?,?,?,?,?,?,?)",
                    (
                        batch["batch_id"],
                        table,
                        identifier,
                        envelope["source_id"],
                        envelope["collected_on"],
                        envelope["origin"],
                        envelope["payload"],
                        envelope["status"],
                    ),
                )
                if table == "facility" and before is None:
                    duplicates = db.execute(
                        "SELECT id FROM facility WHERE id!=? AND lower(trim(name))=lower(trim(?)) AND country=? AND state IS ? AND address_text IS ?",
                        (
                            identifier,
                            after["name"],
                            after["country"],
                            after["state"],
                            after["address_text"],
                        ),
                    ).fetchall()
                    if duplicates:
                        report["conflicts"].append(
                            {
                                "entity": table,
                                "id": identifier,
                                "reason": "possible duplicate identity",
                                "candidates": [r[0] for r in duplicates],
                            }
                        )
                if table == "course" and before is None and after["name"]:
                    duplicates = db.execute(
                        "SELECT id FROM course WHERE id!=? AND facility_id=? AND lower(trim(name))=lower(trim(?))",
                        (identifier, after["facility_id"], after["name"]),
                    ).fetchall()
                    if duplicates:
                        report["conflicts"].append(
                            {
                                "entity": table,
                                "id": identifier,
                                "reason": "possible duplicate course",
                                "candidates": [r[0] for r in duplicates],
                            }
                        )
            report["distinct_facilities"] = len(facilities)
            if len(facilities) < 100:
                report["flags"].append(
                    "small batch: combine roughly 100 distinct facility changes when practical; pilot/corrections may be smaller"
                )
            report["checks"] = check(db)
            if report["conflicts"]:
                report["state"] = "conflicted"
                return report
            if apply:
                report["state"] = "applied"
                db.execute(
                    "INSERT INTO import_batch VALUES (?,?,?)",
                    (batch["batch_id"], batch_digest, encoded(report)),
                )
                db.execute("UPDATE catalog_state SET revision=revision+1 WHERE id=1")
                db.commit()
            return report
        except (ValueError, sqlite3.Error, TypeError) as error:
            report["state"] = "rejected"
            report["conflicts"].append({"reason": str(error)})
            return report


def summary(report):
    lines = [
        f"# Catalog batch {report['batch_id']}",
        "",
        f"State: {report['state']}",
        f"Distinct facilities: {report.get('distinct_facilities', 0)}",
        f"Added: {len(report['added'])}; updated: {len(report['updated'])}; conflicts: {len(report['conflicts'])}",
        "",
    ]
    for action in ("added", "updated"):
        for item in report[action]:
            changes = {
                k: v
                for k, v in item["after"].items()
                if item["before"] is None or item["before"].get(k) != v
            }
            lines.append(
                f"- {action}: {item['entity']} {item['id']} (facility {item['facility_id']}): {encoded(changes)}"
            )
    for conflict in report["conflicts"]:
        lines.append("- CONFLICT: " + encoded(conflict))
    for flag in report["flags"]:
        lines.append("- Review: " + flag)
    return "\n".join(lines) + "\n"


def snapshot(path, output):
    """Portable whole-database SQL snapshot, deterministic gzip, one consistent read."""
    output = Path(output)
    db = connect(path, readonly=True)
    try:
        db.execute("BEGIN")
        check(db)
        body = ("\n".join(db.iterdump()) + "\n").encode()
        compressed = bytearray(gzip.compress(body, mtime=0))
        compressed[9] = 255  # Stable gzip OS header across supported Python versions.
        raw = bytes(compressed)
        with output.open("xb") as file:
            file.write(raw)
        return {
            "sha256": sha256(raw).hexdigest(),
            "uncompressed_sha256": sha256(body).hexdigest(),
            "bytes": len(raw),
        }
    finally:
        db.close()


def restore(snapshot_path, output):
    output = local_path(output)
    with output.open("xb"):
        pass
    db = sqlite3.connect(output)
    db.row_factory = sqlite3.Row
    try:
        # Only trusted private snapshots: SQL is executable input.
        db.executescript(gzip.decompress(Path(snapshot_path).read_bytes()).decode())
        db.execute("PRAGMA foreign_keys=ON")
        migrate_sqlite(db)
        check(db)
        db.commit()
    except Exception:
        db.close()
        output.unlink()
        raise
    db.close()


def distance_km(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    hav = (
        math.sin((b - a) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(hav)))


def query_courses(
    path,
    *,
    state=None,
    access=None,
    style=None,
    holes=None,
    round_holes=None,
    bbox=None,
    center=None,
    radius_km=None,
    plan=False,
    include_review=True,
    limit=100,
    offset=0,
):
    """JSON-ready course cards; routing destinations are deduplicated separately."""
    require(
        type(limit) is int
        and 1 <= limit <= 1000
        and type(offset) is int
        and offset >= 0,
        "invalid pagination",
    )
    require(
        (center is None) == (radius_km is None),
        "center and radius must be supplied together",
    )
    if center is not None:
        require(
            len(center) == 2
            and all(type(n) in {float, int} and math.isfinite(n) for n in center)
            and abs(center[0]) <= 90
            and abs(center[1]) <= 180
            and type(radius_km) in {float, int}
            and math.isfinite(radius_km)
            and 0 <= radius_km <= 20040,
            "invalid distance filter",
        )
    filters, params = [], []
    for column, value in [
        ("f.state", state),
        ("c.access", access),
        ("c.style", style),
        ("c.physical_holes", holes),
    ]:
        if value is not None:
            filters.append(column + "=?")
            params.append(value)
    if plan:
        filters.append(
            "(c.nonmember_bookable=1 OR (c.nonmember_bookable IS NULL AND c.access='public'))"
        )
    if not include_review:
        filters.append("c.identity_status='operator_defined'")
    if bbox is not None:
        require(
            len(bbox) == 4
            and all(type(n) in {float, int} and math.isfinite(n) for n in bbox),
            "invalid bounding box",
        )
        south, west, north, east = bbox
        require(
            -90 <= south <= north <= 90 and -180 <= west <= 180 and -180 <= east <= 180,
            "invalid bounding box",
        )
        filters.append("f.latitude BETWEEN ? AND ?")
        params += [south, north]
        filters.append(
            "f.longitude BETWEEN ? AND ?"
            if west <= east
            else "(f.longitude>=? OR f.longitude<=?)"
        )
        params += [west, east]
    db = connect(path, readonly=True)
    try:
        db.create_function("distance_km", 4, distance_km, deterministic=True)
        db.execute("BEGIN")
        version = db.execute("SELECT max(version) FROM schema_migration").fetchone()[0]
        round_membership = "r.course_id=c.id"
        if version >= 4:
            round_membership += """ OR (r.facility_id=c.facility_id AND EXISTS(
                SELECT 1 FROM round_component rc LEFT JOIN component p ON p.id=rc.component_id
                WHERE rc.round_id=r.id AND coalesce(rc.course_id,p.course_id)=c.id))"""
        if round_holes is not None:
            filters.append(
                "EXISTS(SELECT 1 FROM round_option r WHERE ("
                + round_membership
                + ") AND r.round_holes=?)"
            )
            params.append(round_holes)
        if center is not None:
            filters.append(
                "f.latitude IS NOT NULL AND distance_km(?,?,f.latitude,f.longitude)<=?"
            )
            params += [*center, radius_km]
        sql = """SELECT c.*, f.name AS facility_name,f.state,f.country,f.physical_holes AS facility_physical_holes,
            f.inventory_complete, f.latitude,f.longitude,f.location_kind,f.website AS facility_website,
            f.address_text AS facility_address_text,f.address_purpose AS facility_address_purpose
            FROM facility f JOIN course c ON c.facility_id=f.id"""
        if filters:
            sql += " WHERE " + " AND ".join(filters)
        count_sql = "SELECT count(*) FROM (" + sql + ")"
        total = db.execute(count_sql, params).fetchone()[0]
        sql += " ORDER BY f.name,f.id,c.name,c.id LIMIT ? OFFSET ?"
        cards, destinations = [], {}
        for record in db.execute(sql, params + [limit, offset]):
            card = dict(record)
            for boolean in ("nonmember_bookable", "inventory_complete"):
                if card[boolean] is not None:
                    card[boolean] = bool(card[boolean])
            destination = None
            if card["arrival_latitude"] is not None:
                destination = {
                    "id": card["id"],
                    "latitude": card["arrival_latitude"],
                    "longitude": card["arrival_longitude"],
                    "precision": card["arrival_kind"],
                    "reference": card["arrival_reference"],
                    "scope": "course_arrival",
                }
            elif card["latitude"] is not None:
                destination = {
                    "id": card["facility_id"],
                    "latitude": card["latitude"],
                    "longitude": card["longitude"],
                    "precision": card["location_kind"],
                    "scope": "facility_estimate",
                    "qualification": "approximate planning estimate; does not establish an entrance",
                }
            retained = db.execute(
                "SELECT payload FROM retained_evidence WHERE facility_id=?",
                (card["facility_id"],),
            ).fetchone()
            refs = (
                json.loads(retained[0]).get("notes", {}).get("access", [])
                if retained
                else []
            )
            card["access_qualification"] = (
                "".join(
                    db.execute("SELECT text FROM note WHERE id=?", (n,)).fetchone()[0]
                    for n in refs
                )
                if refs
                else None
            )
            card["plan_eligible"] = (
                bool(
                    card["nonmember_bookable"] is True
                    or (
                        card["nonmember_bookable"] is None
                        and card["access"] == "public"
                    )
                )
                if card["nonmember_bookable"] is not None or card["access"] != "unknown"
                else None
            )
            card["planning_basis"] = (
                "explicit_nonmember_fact"
                if card["nonmember_bookable"] is not None
                else "accepted_public_play_with_qualification"
                if card["access"] == "public"
                else "unknown_or_nonpublic_access"
            )
            card["booking_availability"] = None
            groups = []
            for group in db.execute(
                """SELECT g.*,s.url AS source_url FROM fact_group g JOIN source s ON s.id=g.source_id
                WHERE g.course_id=? OR g.facility_id=? ORDER BY g.id""",
                (card["id"], card["facility_id"]),
            ):
                value = dict(group)
                value["payload"] = json.loads(value["payload"])
                value["conflict"] = bool(value["conflict"])
                groups.append(value)
            card["fact_groups"] = groups
            card["map_location"] = (
                {
                    "latitude": card["latitude"],
                    "longitude": card["longitude"],
                    "kind": card["location_kind"],
                }
                if card["latitude"] is not None
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
            card["course_id"] = card.pop("id")
            card["address"] = (
                {
                    "text": card["facility_address_text"],
                    "purpose": card["facility_address_purpose"],
                    "scope": "facility",
                }
                if card["address_mode"] == "inherit"
                and card["facility_address_text"] is not None
                else {
                    "text": card["address_text"],
                    "purpose": card["address_purpose"],
                    "scope": "course",
                }
                if card["address_mode"] == "override"
                else None
            )
            round_rows = db.execute(
                "SELECT r.* FROM round_option r JOIN course c ON c.id=? WHERE ("
                + round_membership
                + ") ORDER BY r.id",
                (card["course_id"],),
            ).fetchall()
            card["round_options"] = []
            for r in round_rows:
                option = dict(r)
                option["scope"] = "facility" if option.get("facility_id") else "course"
                option["members"] = [
                    dict(member)
                    for member in db.execute(
                        "SELECT * FROM round_component WHERE round_id=? ORDER BY ordinal,id",
                        (r["id"],),
                    )
                ]
                option["tee_sets"] = [
                    dict(tee)
                    for tee in db.execute(
                        "SELECT * FROM tee_set WHERE round_id=? ORDER BY id", (r["id"],)
                    )
                ]
                card["round_options"].append(option)
            card["tee_sets"] = [
                dict(tee)
                for tee in db.execute(
                    "SELECT * FROM tee_set WHERE course_id=? AND round_id IS NULL ORDER BY id",
                    (card["course_id"],),
                )
            ]
            card["destination_id"] = destination["id"] if destination else None
            if destination:
                destinations[destination["id"]] = destination
            if center is not None:
                card["distance_km"] = distance_km(
                    *center, card["latitude"], card["longitude"]
                )
            cards.append(card)
        return {
            "revision": db.execute(
                "SELECT revision FROM catalog_state WHERE id=1"
            ).fetchone()[0],
            "courses": cards,
            "destinations": list(destinations.values()),
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(cards) < total,
            "qualification": "retained needs_review records are not certified independent course identities; physical holes are not round length",
        }
    finally:
        db.close()


def clear_source(path, source_id, expected, controls_reference, collected_on):
    """Integrator reviewed exact-source clearance, with optimistic guard and retained decision."""
    valid_date(collected_on)
    require(
        isinstance(controls_reference, str) and controls_reference.strip(),
        "specific current controls reference required",
    )
    with writer(path) as db:
        found = db.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
        require(found is not None, "source does not exist")
        current = dict(found)
        require(digest(current) == expected, "source changed since clearance review")
        require(
            current["intake_policy"] != "blocked",
            "blocked source cannot be cleared by this command",
        )
        ensure_source_allowed(db, current["url"])
        decision = {
            "source_id": source_id,
            "url": current["url"],
            "before": current,
            "controls_reference": controls_reference,
            "collected_on": collected_on,
            "policy": "permitted",
        }
        db.execute(
            "UPDATE source SET intake_policy='permitted' WHERE id=?", (source_id,)
        )
        db.execute(
            "INSERT INTO retained_document VALUES (?,?)",
            ("source-clearance:" + digest(decision), encoded(decision)),
        )
        db.execute("UPDATE catalog_state SET revision=revision+1")
        db.commit()
        return decision


def query_facilities(
    path,
    *,
    state=None,
    country=None,
    county=None,
    access=None,
    search=None,
    bbox=None,
    center=None,
    radius_km=None,
    limit=100,
    offset=0,
):
    """Facility map/context DTOs, including honest empty retained inventories."""
    require(type(limit) is int and 1 <= limit <= 1000, "limit must be 1..1000")
    require(type(offset) is int and offset >= 0, "offset must be nonnegative")
    filters, params = [], []
    for column, value in [
        ("state", state),
        ("country", country),
        ("county", county),
        ("access", access),
    ]:
        if value is not None:
            require(
                isinstance(value, str) and 0 < len(value.strip()) <= 256,
                "invalid facility filter",
            )
            if column == "access" and value == "unknown":
                filters.append("(f.access IS NULL OR f.access='unknown')")
            else:
                filters.append("f." + column + "=?")
                params.append(value)
    if search is not None:
        require(
            isinstance(search, str)
            and 0 < len(search.strip()) <= 256
            and "\x00" not in search,
            "search must be 1..256 characters without NUL",
        )
        literal = (
            search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        filters.append(
            "(f.name LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM alias a WHERE a.facility_id=f.id AND a.name LIKE ? ESCAPE '\\'))"
        )
        params.extend(["%" + literal + "%"] * 2)
    if bbox is not None:
        require(
            len(bbox) == 4
            and all(type(n) in {float, int} and math.isfinite(n) for n in bbox),
            "invalid bounding box",
        )
        south, west, north, east = bbox
        require(
            -90 <= south <= north <= 90 and -180 <= west <= 180 and -180 <= east <= 180,
            "invalid bounding box",
        )
        filters.append("f.latitude BETWEEN ? AND ?")
        params.extend([south, north])
        filters.append(
            "f.longitude BETWEEN ? AND ?"
            if west <= east
            else "(f.longitude>=? OR f.longitude<=?)"
        )
        params.extend([west, east])
    if center is not None or radius_km is not None:
        require(
            center is not None
            and len(center) == 2
            and all(type(n) in {float, int} and math.isfinite(n) for n in center)
            and abs(center[0]) <= 90
            and abs(center[1]) <= 180
            and type(radius_km) in {float, int}
            and math.isfinite(radius_km)
            and 0 <= radius_km <= 20040,
            "invalid distance filter",
        )
        filters.append(
            "f.latitude IS NOT NULL AND distance_km(?,?,f.latitude,f.longitude)<=?"
        )
        params.extend([*center, radius_km])
    db = connect(path, readonly=True)
    try:
        db.create_function("distance_km", 4, distance_km, deterministic=True)
        db.execute("BEGIN")
        sql = "SELECT f.* FROM facility f" + (
            " WHERE " + " AND ".join(filters) if filters else ""
        )
        total = db.execute("SELECT count(*) FROM (" + sql + ")", params).fetchone()[0]
        facilities = []
        for record in db.execute(
            sql + " ORDER BY f.name,f.id LIMIT ? OFFSET ?", params + [limit, offset]
        ):
            facility = dict(record)
            if facility["inventory_complete"] is not None:
                facility["inventory_complete"] = bool(facility["inventory_complete"])
            facility["facility_id"] = facility.pop("id")
            facility["map_location"] = (
                {
                    "latitude": facility["latitude"],
                    "longitude": facility["longitude"],
                    "kind": facility["location_kind"],
                }
                if facility["latitude"] is not None
                else None
            )
            facility["address"] = (
                {
                    "text": facility["address_text"],
                    "purpose": facility["address_purpose"],
                    "scope": "facility",
                }
                if facility["address_text"] is not None
                else None
            )
            courses = [
                dict(c)
                for c in db.execute(
                    "SELECT id AS course_id,name,physical_holes,identity_status,access,nonmember_bookable FROM course WHERE facility_id=? ORDER BY id",
                    (facility["facility_id"],),
                )
            ]
            for course in courses:
                if course["nonmember_bookable"] is not None:
                    course["nonmember_bookable"] = bool(course["nonmember_bookable"])
            facility["course_inventory"] = courses
            facility["course_ids"] = [c["course_id"] for c in courses]
            facility["course_count"] = len(courses)
            facility["documented_course_ids"] = [
                c["course_id"]
                for c in courses
                if c["identity_status"] == "operator_defined"
            ]
            facility["documented_course_count"] = len(facility["documented_course_ids"])
            facility["inventory_qualification"] = (
                "retained records are not necessarily independent bookable courses; empty inventory does not establish zero physical courses"
            )
            retained = db.execute(
                "SELECT payload FROM retained_evidence WHERE facility_id=?",
                (facility["facility_id"],),
            ).fetchone()
            note_ids = (
                json.loads(retained[0]).get("notes", {}).get("access", [])
                if retained
                else []
            )
            facility["access_qualification"] = (
                "".join(
                    db.execute("SELECT text FROM note WHERE id=?", (n,)).fetchone()[0]
                    for n in note_ids
                )
                if note_ids
                else None
            )
            facility["fact_groups"] = []
            for record in db.execute(
                "SELECT g.*,s.url AS source_url FROM fact_group g JOIN source s ON s.id=g.source_id WHERE g.facility_id=? ORDER BY g.id",
                (facility["facility_id"],),
            ):
                group = dict(record)
                group["payload"] = json.loads(group["payload"])
                group["conflict"] = bool(group["conflict"])
                facility["fact_groups"].append(group)
            if center is not None:
                facility["distance_km"] = distance_km(
                    *center, facility["latitude"], facility["longitude"]
                )
            facilities.append(facility)
        return {
            "revision": db.execute(
                "SELECT revision FROM catalog_state WHERE id=1"
            ).fetchone()[0],
            "facilities": facilities,
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(facilities) < total,
            "qualification": "facility map context includes unresolved and empty inventories; no synthetic course cards or routing entrances inferred",
        }
    finally:
        db.close()
