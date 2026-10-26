"""Plain catalog files are the maintained source; JSON and GeoJSON are projections."""

import csv
import gzip
import hashlib
import json
from pathlib import Path

NULL = r"\N"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_rows(path, rows):
    columns = list(rows[0]) if rows else []
    types = {}
    for field in columns:
        values = [r[field] for r in rows if r[field] is not None]
        types[field] = (
            "text" if values and all(isinstance(v, str) for v in values) else "json"
        )
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: NULL
                    if value is None
                    else value
                    if types[key] == "text"
                    else encoded(value)
                    for key, value in row.items()
                }
            )
    return types


def read_rows(path, types):
    csv.field_size_limit(64 * 1024 * 1024)
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return [
            {
                key: None
                if value == NULL
                else value
                if types[key] == "text"
                else json.loads(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(stream)
        ]


def write_source(root, value, fact_sources=None):
    """Write both complete row sets, preserving types, scopes and unknowns."""
    target = Path(root) / "data/catalog"
    target.mkdir(parents=True, exist_ok=True)
    metadata = {k: v for k, v in value.items() if k not in {"facilities", "courses"}}
    metadata["columns"] = {}
    for kind, identity in (("facilities", "facility_id"), ("courses", "course_id")):
        rows = [dict(row) for row in value[kind]]
        if fact_sources is not None:
            for row in rows:
                row["fact_sources"] = fact_sources[row[identity]]
        metadata["columns"][kind] = write_rows(target / (kind + ".csv"), rows)
    (target / "metadata.json").write_text(encoded(metadata) + "\n")


def load_source(root):
    target = Path(root) / "data/catalog"
    metadata = json.loads((target / "metadata.json").read_text())
    columns = metadata.pop("columns")
    rows = {
        kind: read_rows(target / (kind + ".csv"), columns[kind])
        for kind in ("facilities", "courses")
    }
    return metadata, rows


def transport(root):
    metadata, rows = load_source(root)
    for items in rows.values():
        for row in items:
            row.pop("fact_sources", None)
    value = metadata | rows
    target = Path(root) / "data/catalog"
    value["catalog_release_key"] = hashlib.sha256(
        b"".join(
            (target / name).read_bytes()
            for name in ("facilities.csv", "courses.csv", "metadata.json")
        )
    ).hexdigest()
    raw = (encoded(value) + "\n").encode()
    packed = bytearray(gzip.compress(raw, mtime=0))
    packed[9] = 255
    packed = bytes(packed)
    manifest = {
        key: value[key]
        for key in (
            "format_version",
            "schema",
            "revision",
            "catalog_release_key",
            "authority",
            "qualification",
        )
    }
    manifest["counts"] = {
        key: len(value[key]) for key in ("facilities", "courses", "destinations")
    }
    manifest["files"] = {
        name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        for name, body in (("catalog.json", raw), ("catalog.json.gz", packed))
    }
    return manifest, raw, packed


def geojson(rows, identity):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": row[identity],
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        row["map_location"]["longitude"],
                        row["map_location"]["latitude"],
                    ],
                }
                if row.get("map_location")
                else None,
                "properties": row,
            }
            for row in rows
        ],
    }


def derived_files(root):
    """Return deterministic projections; never read the old SQLite database."""
    _, rows = load_source(root)
    manifest, _, packed = transport(root)
    return {
        "data/catalog/facilities.geojson": (
            encoded(geojson(rows["facilities"], "facility_id")) + "\n"
        ).encode(),
        "data/catalog/courses.geojson": (
            encoded(geojson(rows["courses"], "course_id")) + "\n"
        ).encode(),
        "data/catalog-release/manifest.json": (encoded(manifest) + "\n").encode(),
        "data/catalog-release/catalog.json.gz": packed,
    }
