"""Native5 catalog transactions and SQL-only browse DTOs.

No schema upgrade, legacy payload reader or automatic authority selection lives
here. Reviewed retained single-course identity additions use the same batch
transaction and evidence ledger, with guarded accepted SQLite references.
Guarded corrections to existing typed rows preserve their retained envelopes;
they never provide new extraction permission or add held-source records.
"""

import fcntl
import gzip
import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .catalog_native_common import (
    digest,
    encoded,
    local_path,
    require,
    valid_date,
    valid_url,
)
from .catalog_sources import ensure_source_allowed, resource_identity

SCHEMA = Path(__file__).with_name("catalog_schema") / "native5.sql"
DOMAINS = (
    "physical_characteristics",
    "amenity_observation",
    "practice_observation",
    "service_observation",
    "policy_observation",
    "operating_period",
    "accessibility_observation",
    "price_observation",
    "architecture_event",
    "quality_rating",
)
CORE = {
    "facility",
    "course",
    "component",
    "round_option",
    "round_component",
    "tee_set",
    "alias",
}
PREFIX = {
    "facility": "f",
    "course": "c",
    "component": "p",
    "round_option": "r",
    "round_component": "l",
    "tee_set": "t",
    "alias": "a",
}
TABLES = (
    CORE | set(DOMAINS) | {"source_observation", "design_party", "architecture_credit"}
)
# Booleans are explicit native schema fields, not name/text classifiers.
BOOLEANS = set(
    re.findall(
        r"\b(\w+)\s+INTEGER(?:\s+NOT NULL)?(?:\s+DEFAULT 0)?\s+CHECK\(\1 IN \(0,1\)\)",
        SCHEMA.read_text(),
    )
)
DATES = {
    "collected_on",
    "observed_on",
    "effective_from",
    "effective_to",
    "date_from",
    "date_to",
    "rated_on",
    "source_information_as_of",
    "website_checked_on",
}
SUBJECT_KEYS = {"facility_id", "course_id", "round_id", "component_id"}


def connect(path, *, readonly=True):
    db = sqlite3.connect(
        local_path(path).as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
        uri=True,
        timeout=0,
    )
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        if readonly:
            db.execute("PRAGMA query_only=ON")
        require(
            db.execute("SELECT max(version) FROM schema_migration").fetchone()[0] == 5,
            "native5 database required; no automatic migration",
        )
        return db
    except Exception:
        db.close()
        raise


def create(path):
    """Create only a new empty native5 file; never mutate an earlier schema."""
    path = local_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb"):
        pass
    db = sqlite3.connect(path)
    try:
        db.executescript(SCHEMA.read_text())
        db.execute("INSERT INTO schema_migration VALUES(5,'native typed catalog')")
        db.execute("INSERT INTO catalog_state VALUES(1,0)")
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
        db = connect(path, readonly=False)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
        finally:
            db.rollback()
            db.close()


def check(db):
    integrity = [r[0] for r in db.execute("PRAGMA integrity_check")]
    foreign_keys = [list(r) for r in db.execute("PRAGMA foreign_key_check")]
    require(
        integrity == ["ok"] and not foreign_keys,
        "database integrity/foreign key failure",
    )
    for table in TABLES:
        numeric = [
            r["name"]
            for r in db.execute("PRAGMA table_info(" + table + ")")
            if r["type"] == "REAL"
        ]
        for column in numeric:
            require(
                not db.execute(
                    "SELECT 1 FROM " + table + " WHERE abs(" + column + ")>? LIMIT 1",
                    (1.7976931348623157e308,),
                ).fetchone(),
                "nonfinite native numeric value",
            )
    for view in (
        "round_scope_violation",
        "optional_scope_violation",
        "price_bundle_scope_violation",
        "observation_reference_violation",
    ):
        require(
            not db.execute("SELECT 1 FROM " + view + " LIMIT 1").fetchone(),
            "native scope violation: " + view,
        )
    require(
        not db.execute("""SELECT f.id FROM facility f JOIN course c ON c.facility_id=f.id
        WHERE f.inventory_complete=1 AND f.physical_holes IS NOT NULL
        AND c.identity_status!='component' GROUP BY f.id
        HAVING count(c.physical_holes)=count(*) AND sum(c.physical_holes)!=f.physical_holes""").fetchone(),
        "complete physical inventory does not match facility holes",
    )
    return {
        "integrity_check": integrity,
        "foreign_key_check": foreign_keys,
        "scope_violations": 0,
    }


def _row(db, table, identifier):
    require(table in TABLES, "unknown native entity type")
    found = db.execute(
        "SELECT * FROM " + table + " WHERE id=?", (identifier,)
    ).fetchone()
    return dict(found) if found else None


def _validate(db, table, values):
    require(isinstance(values, dict), "values must be an object")
    columns = {
        r["name"]: r["type"] for r in db.execute("PRAGMA table_info(" + table + ")")
    }
    require(set(values) <= columns.keys(), "unknown native fields")
    for key, value in values.items():
        if value is None:
            continue
        if key in BOOLEANS:
            require(type(value) is bool, key + " must be boolean or null")
        elif columns[key] == "INTEGER":
            require(type(value) is int, key + " must be integer or null")
        elif columns[key] == "REAL":
            require(
                type(value) in {float, int} and math.isfinite(value),
                key + " must be finite numeric or null",
            )
        else:
            require(
                isinstance(value, str) and value.strip() and "\x00" not in value,
                key + " must be nonblank text without NUL",
            )
        if key in DATES:
            valid_date(value)
        if key.endswith("_url") or key == "website":
            valid_url(value)


def _permitted_source(db, source_id):
    found = db.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
    require(
        found is not None and found["intake_policy"] == "permitted",
        "source is not permitted for new intake",
    )
    ensure_source_allowed(db, found["url"])
    return found


def _retained_course_evidence(db, table, values, item, before):
    """Normalize an explicitly reviewed accepted single-course identity, not holes."""
    require(
        table == "course" and before is None,
        "retained inventory evidence only adds a missing course identity",
    )
    require(
        set(item)
        == {
            "origin",
            "facility_id",
            "facility_digest",
            "retained_evidence_digest",
            "source_digests",
            "note_digests",
            "support_indexes",
            "review_reference",
        },
        "invalid retained inventory evidence",
    )
    facility = _row(db, "facility", item["facility_id"])
    require(
        facility is not None
        and values.get("facility_id") == facility["id"]
        and digest(facility) == item["facility_digest"],
        "stale retained facility guard or different subject",
    )
    require(
        not db.execute(
            "SELECT 1 FROM course WHERE facility_id=?", (facility["id"],)
        ).fetchone(),
        "retained single-course reconciliation requires empty inventory",
    )
    require(
        values.get("name") in (None, facility["name"])
        and values.get("physical_holes") == facility["physical_holes"]
        and type(values.get("physical_holes")) is int
        and values["physical_holes"] > 0
        and values.get("identity_status") == "operator_defined"
        and values.get("game_kind") == "golf"
        and values.get("address_mode", "inherit") == "inherit"
        and all(
            v is None
            for k, v in values.items()
            if k
            not in {
                "id",
                "facility_id",
                "name",
                "physical_holes",
                "identity_status",
                "game_kind",
                "address_mode",
            }
        ),
        "retained reconciliation cannot invent layout names or promote other fields",
    )
    retained = db.execute(
        "SELECT * FROM retained_evidence WHERE facility_id=?", (facility["id"],)
    ).fetchone()
    require(
        retained is not None
        and digest(dict(retained)) == item["retained_evidence_digest"],
        "stale accepted retained evidence guard",
    )
    accepted = json.loads(retained["payload"])
    notes = item["note_digests"]
    allowed = {
        note
        for refs in (accepted.get("notes") or {}).values()
        if isinstance(refs, list)
        for note in refs
    }
    require(
        isinstance(notes, dict) and notes and notes.keys() <= allowed,
        "accepted course-definition notes required",
    )
    for identifier, expected in notes.items():
        found_note = db.execute(
            "SELECT * FROM note WHERE id=?", (identifier,)
        ).fetchone()
        note = dict(found_note) if found_note else None
        require(
            note is not None and digest(note) == expected, "stale retained note guard"
        )
    indexes = item["support_indexes"]
    supports = accepted.get("support", [])
    require(
        isinstance(indexes, list)
        and len(indexes) == len(set(indexes))
        and all(type(i) is int and 0 <= i < len(supports) for i in indexes),
        "invalid retained support indexes",
    )
    # Include every known hole/definition binding, so a caller cannot hide a
    # known held source by choosing only an unlinked note. Unbound accepted
    # notes still remain usable with explicitly unknown source/date context.
    relevant = [
        i
        for i, support in enumerate(supports)
        if "physical_holes" in support.get("fields", [])
        or set(notes).intersection(support.get("note") or [])
    ]
    require(indexes == relevant, "complete accepted inventory support required")
    selected = [supports[i] for i in indexes]
    source_ids = {support["source"] for support in selected if support.get("source")}
    require(
        isinstance(item["source_digests"], dict)
        and item["source_digests"].keys() == source_ids,
        "all known retained source guards required",
    )
    for source_id, expected in item["source_digests"].items():
        found = db.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
        source = dict(found) if found else None
        require(
            source is not None
            and digest(source) == expected
            and source_id in accepted.get("listed_sources", []),
            "stale or unrelated retained source",
        )
        require(source["intake_policy"] != "blocked", "retained source is blocked")
        ensure_source_allowed(db, source["url"])
    linked_notes = {
        note for support in selected for note in (support.get("note") or [])
    }
    primary_source = (
        next(iter(source_ids))
        if len(source_ids) == 1
        and notes.keys() <= linked_notes
        and all(support.get("source") in source_ids for support in selected)
        else None
    )
    require(
        isinstance(item["review_reference"], str) and item["review_reference"].strip(),
        "saved identity review required",
    )
    return {
        "source_id": primary_source,
        "collected_on": None,
        "status": "extracted",
        "origin": "retained_normalization",
        "payload": encoded(
            item | {"original_support": selected, "original_status": None}
        ),
    }


def _evidence(db, table, values, item, before=None):
    require(isinstance(item, dict), "evidence must be an object")
    if table == "course" and item.get("origin") == "retained_normalization":
        return _retained_course_evidence(db, table, values, item, before)
    if table in DOMAINS or table == "architecture_credit":
        require(
            set(item)
            == (
                {"origin", "observation_id", "observation_digest", "review_reference"}
                if item.get("origin") == "retained_normalization"
                else {"observation_id"}
            ),
            "invalid typed evidence envelope",
        )
        observation_id = values.get("observation_id")
        if table == "architecture_credit":
            event = _row(db, "architecture_event", values.get("event_id"))
            require(event is not None, "architecture event required")
            observation_id = event["observation_id"]
        require(
            observation_id == item["observation_id"],
            "evidence observation differs from fact",
        )
        observation = _row(db, "source_observation", observation_id)
        if item.get("origin") == "retained_normalization":
            require(
                set(item)
                == {
                    "origin",
                    "observation_id",
                    "observation_digest",
                    "review_reference",
                },
                "invalid preservation-only evidence",
            )
            require(
                before is not None and table in DOMAINS,
                "preservation-only intake only corrects existing typed observations",
            )
            require(
                before["observation_id"] == observation_id,
                "preservation-only correction cannot replace its source envelope",
            )
            require(
                observation is not None
                and observation["origin"]
                in {"retained_input", "retained_normalization"},
                "accepted retained observation required",
            )
            require(
                digest(observation) == item["observation_digest"],
                "stale retained observation guard",
            )
            require(
                isinstance(item["review_reference"], str)
                and item["review_reference"].strip(),
                "saved correction review reference required",
            )
            return {
                "source_id": observation["source_id"],
                "collected_on": observation["collected_on"],
                "status": observation["status"]
                if observation["status"] in {"extracted", "confirmed"}
                else "extracted",
                "origin": "retained_normalization",
                "payload": encoded(item | {"original_status": observation["status"]}),
            }
        require(
            set(item) == {"observation_id"},
            "typed facts require an observation reference",
        )
        require(
            observation is not None and observation["origin"] == "new_extraction",
            "ordinary intake cannot promote retained evidence; use reviewed one-time normalization",
        )
        item = {k: observation[k] for k in ("source_id", "collected_on", "status")}
    else:
        require(
            set(item) == {"source_id", "collected_on", "status"},
            "source/date/status evidence required",
        )
    valid_date(item["collected_on"])
    require(item["status"] in {"extracted", "confirmed"}, "invalid extraction status")
    _permitted_source(db, item["source_id"])
    if table == "source_observation":
        require(
            values.get("origin") == "new_extraction",
            "retained normalization belongs only in the one-time migration",
        )
        require(
            all(values.get(k) == item[k] for k in item),
            "source observation envelope differs from evidence",
        )
    return item | {"origin": "new_extraction", "payload": None}


def _facility(db, table, values):
    if table == "facility":
        return values["id"]
    if values.get("facility_id"):
        return values["facility_id"]
    for key, parent in (
        ("course_id", "course"),
        ("component_id", "component"),
        ("round_id", "round_option"),
        ("event_id", "architecture_event"),
    ):
        if values.get(key):
            found = _row(db, parent, values[key])
            require(found is not None, "missing subject parent")
            return _facility(db, parent, found)
    return None


def _new_sources(db, sources):
    require(isinstance(sources, list), "sources must be an array")
    identities = {resource_identity(r[0]) for r in db.execute("SELECT url FROM source")}
    for source in sources:
        require(
            isinstance(source, dict)
            and set(source)
            == {"id", "url", "license", "attribution", "controls_reference"},
            "invalid source declaration",
        )
        require(
            isinstance(source["id"], str)
            and 0 < len(source["id"].strip()) <= 200
            and "\x00" not in source["id"],
            "invalid source ID",
        )
        valid_url(source["url"])
        require(
            not any(ord(char) < 32 or ord(char) == 127 for char in source["url"]),
            "source URL contains control characters",
        )
        ensure_source_allowed(db, source["url"])
        require(
            all(
                source[k] is None or isinstance(source[k], str)
                for k in ("license", "attribution")
            ),
            "invalid license/attribution",
        )
        require(
            isinstance(source["controls_reference"], str)
            and source["controls_reference"].strip(),
            "saved scoped controls reference required",
        )
        key = resource_identity(source["url"])
        require(
            key not in identities
            and not db.execute(
                "SELECT 1 FROM source WHERE id=?", (source["id"],)
            ).fetchone(),
            "source ID/resource already registered; use same-ID clearance",
        )
        identities.add(key)
        db.execute(
            "INSERT INTO source VALUES(?,?,?,?,?)",
            (
                source["id"],
                source["url"],
                source["license"],
                source["attribution"],
                "permitted",
            ),
        )
        db.execute(
            "INSERT INTO retained_document VALUES(?,?)",
            (
                "source-control:" + source["id"],
                encoded({"reference": source["controls_reference"]}),
            ),
        )


def apply_batch(path, batch, *, apply=False):
    """Atomic guarded native5 intake; preview rolls back sources and every row."""
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
        isinstance(batch["changes"], list) and batch["changes"],
        "nonempty changes required",
    )
    report = {
        "batch_id": batch["batch_id"],
        "digest": digest(batch),
        "state": "preview",
        "committed": False,
        "added": [],
        "updated": [],
        "conflicts": [],
        "flags": [],
    }
    with writer(path) as db:
        previous = db.execute(
            "SELECT digest,report FROM import_batch WHERE id=?", (batch["batch_id"],)
        ).fetchone()
        if previous:
            require(
                previous["digest"] == report["digest"],
                "batch ID reused with different contents",
            )
            return json.loads(previous["report"]) | {"state": "already_applied"}
        try:
            _new_sources(db, batch["sources"])
            report["source_ids_added"] = [s["id"] for s in batch["sources"]]
            seen, facilities = set(), set()
            for change in batch["changes"]:
                require(
                    isinstance(change, dict)
                    and set(change)
                    == {"entity", "id", "expected", "values", "evidence"},
                    "invalid change envelope",
                )
                table, identifier = change["entity"], change["id"]
                require(
                    table in TABLES,
                    "unknown native entity type; retained payloads are not writable catalog fields",
                )
                require(
                    table != "quality_rating",
                    "quality-rating population remains deferred",
                )
                require(
                    isinstance(identifier, str)
                    and re.fullmatch(
                        r"[a-z][a-z0-9_]{0,31}-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
                        identifier,
                    ),
                    "stable UUID entity ID required",
                )
                require(
                    table not in PREFIX or identifier.startswith(PREFIX[table] + "-"),
                    "incorrect core entity ID prefix",
                )
                require((table, identifier) not in seen, "duplicate entity in batch")
                seen.add((table, identifier))
                before = _row(db, table, identifier)
                if change["expected"] != (digest(before) if before else None):
                    report["conflicts"].append(
                        {
                            "entity": table,
                            "id": identifier,
                            "reason": "stale row or addition collision",
                            "current_digest": digest(before) if before else None,
                        }
                    )
                    continue
                require("id" not in change["values"], "identity cannot be changed")
                require(
                    not before or table != "source_observation",
                    "source envelopes are immutable; add a new observation",
                )
                _validate(db, table, change["values"])
                values = (before or {}) | change["values"] | {"id": identifier}
                if before:
                    require(
                        all(
                            k not in change["values"]
                            or change["values"][k] == before[k]
                            for k in SUBJECT_KEYS | {"event_id", "party_id"}
                            if k in before
                        ),
                        "subject identity cannot be moved",
                    )
                envelope = _evidence(db, table, values, change["evidence"], before)
                if before:
                    columns = list(change["values"])
                    if columns:
                        db.execute(
                            "UPDATE "
                            + table
                            + " SET "
                            + ",".join(k + "=?" for k in columns)
                            + " WHERE id=?",
                            [values[k] for k in columns] + [identifier],
                        )
                else:
                    columns = list(values)
                    db.execute(
                        "INSERT INTO "
                        + table
                        + "("
                        + ",".join(columns)
                        + ") VALUES("
                        + ",".join("?" for _ in columns)
                        + ")",
                        list(values.values()),
                    )
                after = _row(db, table, identifier)
                facility = _facility(db, table, after)
                if facility:
                    facilities.add(facility)
                if before != after:
                    report["updated" if before else "added"].append(
                        {
                            "entity": table,
                            "id": identifier,
                            "facility_id": facility,
                            "before": before,
                            "after": after,
                        }
                    )
                if not before and table in {"facility", "course"} and after.get("name"):
                    clause, args = (
                        (
                            "country IS ? AND state IS ? AND address_text IS ?",
                            [after["country"], after["state"], after["address_text"]],
                        )
                        if table == "facility"
                        else ("facility_id=?", [after["facility_id"]])
                    )
                    duplicates = [
                        r[0]
                        for r in db.execute(
                            "SELECT id FROM "
                            + table
                            + " WHERE id!=? AND lower(trim(name))=lower(trim(?)) AND "
                            + clause,
                            [identifier, after["name"], *args],
                        )
                    ]
                    if duplicates:
                        report["conflicts"].append(
                            {
                                "entity": table,
                                "id": identifier,
                                "reason": "possible duplicate identity",
                                "candidates": duplicates,
                            }
                        )
                db.execute(
                    "INSERT INTO intake_evidence VALUES(?,?,?,?,?,?,?,?)",
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
            report["checks"] = check(db)
            report["distinct_facilities"] = len(facilities)
            report["changed_fields"] = sum(
                sum(item["before"].get(k) != v for k, v in item["after"].items())
                for item in report["updated"]
            )
            report["revision_before"] = db.execute(
                "SELECT revision FROM catalog_state"
            ).fetchone()[0]
            if report["conflicts"]:
                report["state"] = "conflicted"
            elif apply:
                report["state"] = "applied"
                report["committed"] = True
                report["revision_after"] = report["revision_before"] + 1
                db.execute("UPDATE catalog_state SET revision=revision+1 WHERE id=1")
                db.execute(
                    "INSERT INTO import_batch VALUES(?,?,?)",
                    (batch["batch_id"], report["digest"], encoded(report)),
                )
                db.commit()
            return report
        except (ValueError, sqlite3.Error, TypeError) as error:
            report["state"] = "rejected"
            report["conflicts"].append({"reason": str(error)})
            return report


def clear_source(path, source_id, *, expected, controls_reference, collected_on):
    """Same-ID scoped clearance; never clears a blocked or held resource."""
    valid_date(collected_on)
    require(
        isinstance(controls_reference, str) and controls_reference.strip(),
        "saved scoped controls reference required",
    )
    with writer(path) as db:
        found = db.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
        require(found is not None, "unknown source")
        before = dict(found)
        require(digest(before) == expected, "stale source guard")
        ensure_source_allowed(db, before["url"])
        require(
            before["intake_policy"] == "retained_only",
            "only retained_only sources can be cleared here",
        )
        db.execute(
            "UPDATE source SET intake_policy='permitted' WHERE id=?", (source_id,)
        )
        proof = {
            "source_id": source_id,
            "before": before,
            "controls_reference": controls_reference,
            "collected_on": collected_on,
        }
        db.execute(
            "INSERT INTO retained_document VALUES(?,?)",
            ("native5-source-clearance:" + digest(proof), encoded(proof)),
        )
        db.execute("UPDATE catalog_state SET revision=revision+1 WHERE id=1")
        db.commit()
        return proof | {"state": "cleared"}


def summary(report):
    """Generated review text reports actual stored differences, not proposals."""
    label = "Committed" if report.get("committed") else "Staged only, not committed"
    lines = [
        f"{report['batch_id']}: {report['state']}",
        f"{label}: additions {len(report['added'])}; updates {len(report['updated'])}; existing fields changed {report.get('changed_fields', 0)}.",
    ]
    for kind in ("added", "updated"):
        for change in report[kind]:
            fields = [
                k
                for k, v in change["after"].items()
                if change["before"] is None or change["before"].get(k) != v
            ]
            lines.append(
                f"{kind}: {change['entity']} {change['id']} ({', '.join(fields)})"
            )
    for conflict in report["conflicts"]:
        lines.append("conflict: " + encoded(conflict))
    return "\n".join(lines) + "\n"


def snapshot(path, output):
    """Whole native5 SQL recovery snapshot from one read transaction."""
    db = connect(path)
    try:
        db.execute("BEGIN")
        check(db)
        body = ("\n".join(db.iterdump()) + "\n").encode()
        compressed = bytearray(gzip.compress(body, mtime=0))
        compressed[9] = 255
        with Path(output).open("xb") as file:
            file.write(compressed)
        return {
            "sha256": hashlib.sha256(compressed).hexdigest(),
            "uncompressed_sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(compressed),
        }
    finally:
        db.close()


def restore(snapshot_path, output, *, expected_sha256):
    """Execute an explicitly trusted checksummed native5 private SQL snapshot."""
    raw = Path(snapshot_path).read_bytes()
    require(
        hashlib.sha256(raw).hexdigest() == expected_sha256, "snapshot checksum differs"
    )
    output = local_path(output)
    with output.open("xb"):
        pass
    db = sqlite3.connect(output)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(gzip.decompress(raw).decode())
        require(
            db.execute("SELECT max(version) FROM schema_migration").fetchone()[0] == 5,
            "native5 snapshot required",
        )
        db.execute("PRAGMA foreign_keys=ON")
        result = check(db)
        db.commit()
        return result
    except Exception:
        db.close()
        output.unlink()
        raise
    finally:
        db.close()
