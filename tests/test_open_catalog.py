"""The portable catalog preserves identities, factual scope and privacy choices."""

import gzip
import json
import re
from pathlib import Path

from fairway.open_catalog import load_source, transport

ROOT = Path(__file__).resolve().parents[1]


def test_full_plain_rows_and_geojson_preserve_geometryless_records_and_relationships():
    _, rows = load_source(ROOT)
    assert {kind: len(items) for kind, items in rows.items()} == {
        "facilities": 16180,
        "courses": 4985,
    }
    for kind, key, missing in (
        ("facilities", "facility_id", None),
        ("courses", "course_id", None),
    ):
        geo = json.loads((ROOT / "data/catalog" / (kind + ".geojson")).read_bytes())
        assert [f["properties"] for f in geo["features"]] == rows[kind]
        assert any(f["geometry"] is None for f in geo["features"])
        assert [f["id"] for f in geo["features"]] == [r[key] for r in rows[kind]]
    facilities = {row["facility_id"]: row for row in rows["facilities"]}
    assert all(
        row["facility_id"] is None or row["facility_id"] in facilities
        for row in rows["courses"]
    )
    assert sum(len(f["course_ids"]) for f in facilities.values()) == 4951
    assert any(len(f["course_ids"]) > 1 for f in facilities.values())


def test_browser_projection_is_derived_from_csv_and_preserves_designer_credits():
    manifest, raw, _ = transport(ROOT)
    assert json.loads(raw) == json.loads(
        gzip.decompress((ROOT / "data/catalog-release/catalog.json.gz").read_bytes())
    )
    value = json.loads(raw)
    assert manifest["counts"]["courses"] == 4985
    parties = {}

    def visit(item):
        if isinstance(item, dict):
            if "party_id" in item and "name" in item:
                parties[item["party_id"]] = item["name"]
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    assert len(parties) == 753
    assert all(parties.values())
    assert "plain CSV" in value["authority"]


def test_known_dates_unknown_dates_contact_removal_and_scoped_licenses():
    metadata, rows = load_source(ROOT)
    citations = [c for items in rows.values() for r in items for c in r["fact_sources"]]
    assert citations and all(
        c["source_url"].startswith("https://") or c["source_url"].startswith("http://")
        for c in citations
    )
    assert any(c["checked_on"] is None for c in citations)
    assert any(c["checked_on"] is not None for c in citations)
    assert any(c.get("upstream_binding") == "unknown" for c in citations)
    assert {r["license"] for r in metadata["source_licenses"]} == {
        "ODbL-1.0",
        "CC-BY-4.0",
        "CC-BY-SA-3.0-Unported",
        "CC0-1.0",
    }
    email = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    phone = re.compile(
        r"(?<!\d)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)"
    )

    def visit(item, key=""):
        if isinstance(item, dict):
            for field, child in item.items():
                assert field.lower() not in {
                    "phone",
                    "email",
                    "telephone",
                    "fax",
                    "mobile",
                }
                visit(child, field)
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif isinstance(item, str) and not (key == "id" or key.endswith("_id")):
            assert not email.search(item), key
            assert not phone.search(item), key

    visit(metadata)
    visit(rows)


def test_cc_by_attributes_are_scoped_to_the_declared_ugrc_publisher():
    metadata, _ = load_source(ROOT)
    for source in metadata["provenance"]["sources"]:
        if source["license"] == "CC-BY-4.0":
            assert source["url"].startswith(
                (
                    "https://gis.utah.gov/",
                    "https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/GolfCourses/",
                )
            )
