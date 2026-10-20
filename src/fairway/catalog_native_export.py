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
    # Only declared public scalar metadata crosses this boundary. Private
    # control pointers stay in SQLite; unknown extensions require review.
    require(isinstance(value, dict), "source-license object required")
    private = {"controls_reference", "capture_path", "local_path"}
    require(
        value.keys() <= _PUBLIC_LICENSE_FIELDS | private, "unknown source-license field"
    )
    result = {k: v for k, v in value.items() if k in _PUBLIC_LICENSE_FIELDS}
    require(
        all(v is None or isinstance(v, str) for v in result.values()),
        "source-license scalar required",
    )
    return result


# Explicit shared scan policy: no engine-dependent whitespace, casefold or boundary.
_SCAN_SPACE = r"\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_URL_BOUNDARY = r"\x00-\x2f\x3a-\x40\x5b-\x5e\x60\x7b-\x7f“”‘’«»"


def _validation_scan(text):
    text = re.sub(f"[{_SCAN_SPACE}]", " ", text)
    return re.sub(r"[A-Z]", lambda match: match[0].lower(), text)


_HTTP_TOKEN = rf"""(^|[{_URL_BOUNDARY}])(https?://[^ <>"'`“”‘’«»]+)"""
_CREDENTIAL_URL_KEYS = frozenset(
    [
        "access_token",
        "access-token",
        "api_key",
        "api-key",
        "apikey",
        "authorization",
        "client_secret",
        "client-secret",
        "credential",
        "password",
        "passwd",
        "secret",
        "token",
    ]
)


def _credential_syntax(text):
    # No URL extraction or reconstruction: conservatively hold explicit syntax.
    for view in (text, re.sub(r"[\t\n\r]", "", text)):
        scan = _validation_scan(view)
        scan = re.sub(
            r"%([0-9a-f]{2})",
            lambda m: (
                chr(int(m[1], 16))
                if chr(int(m[1], 16))
                in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._~-"
                else m[0]
            ),
            scan,
        )
        scan = _validation_scan(scan)
        if re.search(r"https?:[/\\]*[^/\\?#]*(?:@|%40)", scan):
            return True
        keys = "|".join(re.escape(key) for key in _CREDENTIAL_URL_KEYS)
        if re.search(rf"(?:^|[^a-z0-9_])(?:{keys}) *=", scan):
            return True
    return False


def _without_http_links(text):
    return re.sub(_HTTP_TOKEN, r"\1", _validation_scan(text))


# Canonical public text roles; private/provenance objects never gain this role.
_PRIVATE_KEYS = frozenset(
    [
        "access_token",
        "api_key",
        "authorization",
        "capture_path",
        "controls_reference",
        "credential",
        "fact_groups",
        "local_path",
        "password",
        "payload",
        "retained_document",
        "retained_evidence",
        "retained_pointer",
        "secret",
    ]
)
_PRIVATE_KEYS |= _CREDENTIAL_URL_KEYS
_PUBLIC_LICENSE_FIELDS = frozenset(
    [
        "applies_to",
        "attribution",
        "changes",
        "collected_on",
        "kind",
        "license",
        "license_url",
        "policy_capture_sha256",
        "policy_url",
        "scope",
        "source",
        "source_id",
        "source_url",
    ]
)
_PUBLIC_DOMAIN_TEXT = {
    kind: frozenset(fields.split())
    for kind, fields in {
        "accessibility_observation": "qualification",
        "amenity_observation": "qualification",
        "architecture_event": "event_kind project_state qualification target_area",
        "operating_period": "aerification_method affected_area maintenance_kind period_kind qualification",
        "physical_characteristics": "elevation_unit fairway_grass_name greens_grass_name landscape playing_surface qualification rough_grass_name tee_grass_name terrain",
        "policy_observation": "arrival_access_condition audience cancellation_charge_basis cancellation_charge_currency qualification season",
        "practice_observation": "driving_range_details driving_range_length_unit putting_green_details qualification range_technology_name",
        "price_observation": "amount_kind audience billing_basis conditions currency fee_kind product_name qualification residency residency_area_name season",
        "quality_rating": "dimension issuer_name qualification",
        "service_observation": "pro_shop_details qualification rental_details",
    }.items()
}
_CORE_TEXT = frozenset(
    [
        "access_qualification",
        "address_city",
        "address_postal_code",
        "address_region",
        "address_street_line1",
        "address_street_line2",
        "address_text",
        "arrival_reference",
        "booking_conditions",
        "country",
        "county",
        "description",
        "facility_name",
        "location_note",
        "name",
        "rated_category",
        "state",
    ]
)
_CHILD_ROWS = frozenset(
    ["aliases", "components", "course_inventory", "round_options", "tee_sets"]
)
_POSIX_PATH = r"""(?:^|[ "'`(\[={:;,<>|!?“”‘’«»])/+[^ /]"""
_EXPLICIT_PATH = r"file://|[a-zİıſK]:[\\/]|\\{2}"
_PATH_END = "[ /\\\\?&#;=,:'\"`()<>\\[\\]{}|!?“”‘’«»]"
_LOCAL_ROOT = (
    r"""(?:^|[ "'`(\[={:;,<>|!?“”‘’«»])/+"""
    r"(?:home|users|root|tmp|var|private|mnt|media|volumes|workspace|workspaces|task|tasks|"
    r"srv|opt|etc|usr|proc|sys|dev|run)"
    rf"(?=$|{_PATH_END}|\.+(?=$|{_PATH_END}))"
)
_PRIVATE_COMPONENT = (
    r"(?:[/\\?&#;=]|%2f)(?:private|secret|evidence|capture|retained|recovery)"
    rf"(?=$|[-._]|{_PATH_END})"
)
_PRIVATE_DECLARATION = (
    r"(?:^|[^a-z0-9_])(?:private +(?:copy|file|capture|path|directory|folder)|"
    r"local +(?:copy|file|directory|folder)|evidence +(?:copy|file|directory|folder)|"
    r"capture +(?:file|path)|capture *:|recovery +(?:sql|dump|file))(?=$|[^a-z0-9_])"
)


def _operational_text_path(path):
    if len(path) == 4 and path[0] == "relationships":
        return (
            path[1] in {"component", "round_option", "tee_set", "alias"}
            and type(path[2]) is int
            and path[3] in _CORE_TEXT
        )
    if (
        len(path) < 3
        or path[0] not in {"facilities", "courses"}
        or type(path[1]) is not int
    ):
        return False
    parents, field = path[2:-1], path[-1]
    while len(parents) >= 2 and parents[0] in _CHILD_ROWS and type(parents[1]) is int:
        parents = parents[2:]
    if not parents:
        return field in _CORE_TEXT
    if parents == ("address",):
        return field in {
            "text",
            "street_line1",
            "street_line2",
            "city",
            "region",
            "postal_code",
            "country",
        }
    if parents == ("arrival",):
        return field == "reference"
    if (
        len(parents) >= 3
        and parents[0] == "optional"
        and parents[1] in _PUBLIC_DOMAIN_TEXT
        and type(parents[2]) is int
    ):
        if len(parents) == 3:
            return field in _PUBLIC_DOMAIN_TEXT[parents[1]]
        return (
            len(parents) == 5
            and parents[1] == "architecture_event"
            and parents[3] == "credits"
            and type(parents[4]) is int
            and field == "name"
        )
    return False


def _has_private_path(text, *, operational=False):
    if _credential_syntax(text):
        return True
    scan = _without_http_links(text)
    if re.search(_EXPLICIT_PATH, scan):
        return True
    if not operational:
        return bool(re.search(_POSIX_PATH, scan))
    # Ordinary slash notation belongs to the public fact, not a filesystem
    # classifier. Still reject recognizable local artifacts or explicit evidence.
    return bool(
        re.search(_LOCAL_ROOT, scan)
        or (re.search(_POSIX_PATH, scan) and re.search(_PRIVATE_COMPONENT, scan))
        or (re.search(_POSIX_PATH, scan) and re.search(_PRIVATE_DECLARATION, scan))
    )


def _projection_record(value, path):
    if (
        len(path) == 2
        and path[0] == "source_licenses"
        and type(path[1]) is int
        and (
            not isinstance(value, dict)
            or not value.keys() <= _PUBLIC_LICENSE_FIELDS
            or any(v is not None and not isinstance(v, str) for v in value.values())
        )
    ):
        raise ValueError("unknown or nonpublic source-license material")
    if (
        len(path) == 3
        and path[:2] == ("provenance", "notes")
        and type(path[2]) is int
        and (
            not isinstance(value, dict)
            or set(value) != {"id"}
            or not isinstance(value["id"], str)
            or not value["id"]
        )
    ):
        raise ValueError("public notes contain IDs only")


def _public(value, *, _path=()):
    _projection_record(value, _path)
    if isinstance(value, dict):
        for key, child in value.items():
            require(
                isinstance(key, str) and _validation_scan(key) not in _PRIVATE_KEYS,
                "public transport contains private evidence/control material",
            )
            _public(key)
            _public(child, _path=(*_path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _public(child, _path=(*_path, index))
    elif isinstance(value, str):
        require(
            "\0" not in value
            and not _has_private_path(
                value,
                operational=_operational_text_path(_path),
            ),
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
        citations = [
            dict(r)
            for r in db.execute(
                "SELECT entity_type,entity_id,source_id,collected_on,status FROM citation ORDER BY entity_type,entity_id,source_id,collected_on,status"
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
            "provenance": {"sources": sources, "notes": notes, "citations": citations},
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
