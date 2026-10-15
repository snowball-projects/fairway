"""Native5 SQL-only release transport. This does not publish or adopt a catalog."""

import gzip
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from .catalog_native import check, connect
from .catalog_native_common import encoded, local_path, require
from .catalog_native_read import _course, _facility


def _identity(path, expected):
    path = local_path(path)
    require(
        path.is_file()
        and not any(Path(str(path) + s).exists() for s in ("-wal", "-shm", "-journal")),
        "closed release without sidecars required",
    )
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    require(checksum == expected, "closed release checksum differs")
    stat = path.stat()
    return checksum, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _license(value):
    # Only maintenance/control pointers are removed, never operational claims.
    if isinstance(value, dict):
        return {
            k: _license(v)
            for k, v in value.items()
            if k not in {"controls_reference", "capture_path", "local_path"}
        }
    if isinstance(value, list):
        return [_license(v) for v in value]
    return value


# Explicit shared scan policy: no engine-dependent whitespace, casefold or boundary.
_SCAN_SPACE = r"\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_URL_BOUNDARY = r"\x00-\x2f\x3a-\x40\x5b-\x5e\x60\x7b-\x7f“”‘’«»"


def _validation_scan(text):
    text = re.sub(f"[{_SCAN_SPACE}]", " ", text)
    return re.sub(r"[A-Z]", lambda match: match[0].lower(), text)


def _price_condition_scan(row):
    """Scan bounded ASCII financial notation; never rewrite emitted claims."""
    text = row["conditions"]
    if (
        row.get("billing_basis") != "per_person"
        or not {"id", "observation_id", "fee_kind", "amount_kind", "amount_min"}
        <= row.keys()
    ):
        return text
    text = _validation_scan(text)
    text = re.sub(
        r"""\A( *printed +["'`]?)\/ea(?=["'`]? +with *[0-9]+ *riders? +per +cart(?=$| |[.,;:!?)](?: |$)))""",
        r"\1each",
        text,
    )
    return re.sub(
        r"\A( *[$€£] *[0-9]+(?:[.,][0-9]{1,2})? +)/ea(?=$| |[.,;:!?)](?: |$))",
        r"\1each",
        text,
    )


def _without_http_links(text):
    return re.sub(
        rf"""(^|[{_URL_BOUNDARY}])https?://[^ <>"'`“”‘’«»]+""",
        r"\1",
        _validation_scan(text),
    )


def _has_private_path(text):
    return bool(
        re.search(
            r"""(?:^|[ "'`(\[={:;,<>|!?“”‘’«»])/+[^ /]|file://|[a-zİıſK]:[\\/]|\\{2}""",
            _without_http_links(text),
        )
    )


def _public(value):
    if isinstance(value, dict):
        require(
            not (
                {"controls_reference", "retained_pointer", "fact_groups"} & value.keys()
            ),
            "public transport contains private evidence/control material",
        )
        for key, child in value.items():
            _public(key)
            _public(
                _price_condition_scan(value)
                if key == "conditions" and isinstance(child, str)
                else child
            )
    elif isinstance(value, list):
        for child in value:
            _public(child)
    elif isinstance(value, str):
        require(
            not _has_private_path(value),
            "public transport contains a local evidence path",
        )


def build_transport(path, *, expected_sha256, revision):
    """One transaction covers both resources, all typed children and provenance."""
    before = _identity(path, expected_sha256)
    db = connect(path)
    try:
        db.execute("BEGIN")
        require(
            db.execute("SELECT revision FROM catalog_state").fetchone()[0] == revision,
            "unexpected release revision",
        )
        check(db)
        facilities = [
            _facility(db, row)
            for row in db.execute("SELECT * FROM facility ORDER BY name,id")
        ]
        courses, destinations = [], {}
        for row in db.execute(
            "SELECT c.* FROM course c JOIN facility f ON f.id=c.facility_id ORDER BY f.name,f.id,c.name,c.id"
        ):
            course, destination = _course(db, row)
            courses.append(course)
            if destination:
                old = destinations.setdefault(destination["id"], destination)
                require(old == destination, "inconsistent shared destination")
        relationships = {
            table: [
                dict(r) for r in db.execute("SELECT * FROM " + table + " ORDER BY id")
            ]
            for table in (
                "component",
                "round_option",
                "round_component",
                "tee_set",
                "alias",
            )
        }
        sources = [
            dict(r)
            for r in db.execute(
                "SELECT id,url,license,attribution FROM source ORDER BY id"
            )
        ]
        # Retained note bodies are private evidence, not typed operational text.
        # Keep stable references without guessing which free text is public-safe.
        notes = [dict(r) for r in db.execute("SELECT id FROM note ORDER BY id")]
        intake = [
            dict(r)
            for r in db.execute(
                "SELECT batch_id,entity_type,entity_id,source_id,collected_on,origin,status FROM intake_evidence ORDER BY batch_id,entity_type,entity_id"
            )
        ]
        licenses = [
            _license(json.loads(r[0]))
            for r in db.execute("SELECT payload FROM source_license ORDER BY id")
        ]
        value = {
            "format_version": 2,
            "schema": 5,
            "revision": revision,
            "catalog_release_key": expected_sha256,
            "facilities": facilities,
            "courses": courses,
            "destinations": list(destinations.values()),
            "relationships": relationships,
            "provenance": {"sources": sources, "notes": notes, "intake": intake},
            "source_licenses": licenses,
            "authority": "generated read-only transport; edit facts only in SQLite",
            "qualification": "Dated typed SQL observations; missing values remain null. Physical holes, components and round length differ. Facility estimates are not canonical arrivals. No live prices, booking availability or travel times. Retained raw claims are evidence, not standardized output.",
        }
    finally:
        db.close()
    require(
        before == _identity(path, expected_sha256),
        "closed release changed during export",
    )
    _public(value)
    return value


def export_transport(path, output, *, expected_sha256, revision):
    """Stage bytes first; publish the complete manifest last in a new directory.

    A process interrupted during file moves leaves no manifest and therefore no
    usable release. Ordinary failures remove only the newly created directory.
    """
    output = Path(output)
    require(not output.exists(), "generated output must not already exist")
    value = build_transport(path, expected_sha256=expected_sha256, revision=revision)
    raw = (encoded(value) + "\n").encode()
    compressed = bytearray(gzip.compress(raw, mtime=0))
    compressed[9] = 255
    files = {"catalog.json": raw, "catalog.json.gz": bytes(compressed)}
    manifest = {
        "format_version": 2,
        "schema": 5,
        "revision": revision,
        "catalog_release_key": expected_sha256,
        "authority": value["authority"],
        "qualification": value["qualification"],
        "counts": {k: len(value[k]) for k in ("facilities", "courses", "destinations")},
        "files": {
            k: {"bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()}
            for k, v in files.items()
        },
    }
    files["manifest.json"] = (encoded(manifest) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    with tempfile.TemporaryDirectory(
        prefix=".native5-export-", dir=output.parent
    ) as work:
        for name, body in files.items():
            with (Path(work) / name).open("xb") as file:
                file.write(body)
                file.flush()
                os.fsync(file.fileno())
        try:
            output.mkdir()
            created = True
            for name in files:  # manifest is deliberately last
                os.replace(Path(work) / name, output / name)
            directory = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except Exception:
            if created:
                shutil.rmtree(output)
            raise
    return manifest
