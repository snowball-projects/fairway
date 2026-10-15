"""Deterministic public read transport derived from a closed SQLite release.

This module never imports facts or edits a catalog. The complete SQLite database,
its recovery dump and retained evidence remain the operational source and backup.
Only native reader DTOs and explicit public provenance are emitted for Pages.
"""

import gzip
import hashlib
import json
from pathlib import Path

from fairway.catalog_store import (
    check,
    connect,
    encoded,
    query_courses,
    query_facilities,
)


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _closed_identity(path, expected_sha256):
    path = Path(path).resolve()
    if not path.is_file() or any(
        Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ValueError("export requires a closed SQLite release without sidecars")
    actual = file_digest(path)
    if actual != expected_sha256:
        raise ValueError("SQLite release checksum differs")
    stat = path.stat()
    return actual, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _pages(path, reader, key, revision):
    rows, destinations = [], {}
    offset = 0
    while True:
        page = reader(path, limit=1000, offset=offset)
        if page["revision"] != revision:
            raise ValueError("catalog revision changed during export")
        rows.extend(page[key])
        for destination in page.get("destinations", []):
            previous = destinations.setdefault(destination["id"], destination)
            if previous != destination:
                raise ValueError("inconsistent shared destination")
        offset += len(page[key])
        if not page["has_more"]:
            if offset != page["total"]:
                raise ValueError("incomplete native export")
            break
        if not page[key]:
            raise ValueError("empty nonterminal native page")
    return rows, list(destinations.values())


def _public_provenance(db):
    """Whitelist public URLs, dates, qualifications and inherited attribution.

    Internal control decisions, retained documents, batch proofs, capture bodies
    and filesystem paths are deliberately not serialized wholesale.
    """
    sources = dict(db.execute("SELECT id,url FROM source"))
    notes = dict(db.execute("SELECT id,text FROM note"))
    retained = []
    for record in db.execute("SELECT * FROM retained_evidence ORDER BY facility_id"):
        payload = json.loads(record["payload"])
        support = []
        for claim in payload.get("support", []):
            support.append(
                {
                    "fields": claim.get("fields", []),
                    "source_url": sources.get(claim.get("source")),
                    "observed_on": claim.get("observed_on"),
                    "notes": (
                        [notes[n] for n in claim["note"]]
                        if claim.get("note") is not None
                        else None
                    ),
                    "status": "retained",
                }
            )
        retained.append(
            {
                "facility_id": record["facility_id"],
                "listed_source_urls": [
                    sources[s] for s in payload.get("listed_sources", [])
                ],
                "support": support,
                "notes": {
                    kind: [notes[n] for n in identifiers]
                    if identifiers is not None
                    else None
                    for kind, identifiers in payload.get("notes", {}).items()
                },
                "qualification": "accepted retained evidence; missing dates remain unknown",
            }
        )
    intake = []
    for row in db.execute(
        "SELECT * FROM intake_evidence ORDER BY entity_type,entity_id,batch_id"
    ):
        intake.append(
            {
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "source_url": sources.get(row["source_id"]),
                "collected_on": row["collected_on"],
                "status": row["status"],
                "origin": row["origin"],
            }
        )
    return {"retained": retained, "intake": intake}


def build_native_transport(path, *, expected_sha256, revision):
    """Read a pinned closed release, preserving native DTO values and unknowns."""
    path = Path(path).resolve()
    before = _closed_identity(path, expected_sha256)
    facilities, _ = _pages(path, query_facilities, "facilities", revision)
    courses, destinations = _pages(path, query_courses, "courses", revision)
    with connect(path, readonly=True) as db:
        db.execute("BEGIN")
        if db.execute("SELECT revision FROM catalog_state").fetchone()[0] != revision:
            raise ValueError("unexpected catalog revision")
        check(db)
        schema = db.execute("SELECT max(version) FROM schema_migration").fetchone()[0]
        relationships = {
            table: [
                dict(row)
                for row in db.execute("SELECT * FROM " + table + " ORDER BY id")
            ]
            for table in (
                "component",
                "round_option",
                "round_component",
                "tee_set",
                "alias",
            )
        }
        licenses = []
        for row in db.execute("SELECT payload FROM source_license ORDER BY id"):
            terms = json.loads(row[0])
            # The scoped license observation also keeps an internal audit-file
            # pointer. Its public policy URL, license, attribution, scope and
            # capture hash remain; the complete original stays in SQLite.
            terms.pop("controls_reference", None)
            licenses.append(terms)
        provenance = _public_provenance(db)
    if before != _closed_identity(path, expected_sha256):
        raise ValueError("closed release changed during export")
    value = {
        "format_version": 1,
        "revision": revision,
        "schema": schema,
        "catalog_release_key": expected_sha256,
        "facilities": facilities,
        "courses": courses,
        "destinations": destinations,
        "relationships": relationships,
        "provenance": provenance,
        "source_licenses": licenses,
        "qualification": (
            "Dated extracted and retained facts. Unknown inventories, identities, access, "
            "units, prices and current conditions remain unknown or explicitly qualified. "
            "Components are not independent courses; physical holes differ from round length. "
            "Facility map points are not verified entrances. No live booking or driving times."
        ),
        "authority": "generated read-only transport; change facts only in SQLite",
    }
    # Public modules must not accidentally carry private capture/control paths.
    raw = encoded(value)
    if any(marker in raw for marker in ("/home/nas/", '"/tmp/', "file://")):
        raise ValueError("public transport contains a local evidence path")
    return value


def export_native_transport(path, output, *, expected_sha256, revision):
    """Write a new immutable generated build directory; never overwrite output."""
    output = Path(output)
    if output.exists():
        raise ValueError("generated output must not already exist")
    value = build_native_transport(
        path, expected_sha256=expected_sha256, revision=revision
    )
    raw = (encoded(value) + "\n").encode()
    compressed = bytearray(gzip.compress(raw, mtime=0))
    compressed[9] = 255
    manifest = {
        "format_version": 1,
        "revision": revision,
        "schema": value["schema"],
        "catalog_release_key": expected_sha256,
        "authority": value["authority"],
        "counts": {
            key: len(value[key]) for key in ("facilities", "courses", "destinations")
        },
        "files": {
            "catalog.json": {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            },
            "catalog.json.gz": {
                "sha256": hashlib.sha256(compressed).hexdigest(),
                "bytes": len(compressed),
            },
        },
        "qualification": value["qualification"],
    }
    output.mkdir(parents=True)
    (output / "catalog.json").write_bytes(raw)
    (output / "catalog.json.gz").write_bytes(compressed)
    (output / "manifest.json").write_text(encoded(manifest) + "\n")
    return manifest
