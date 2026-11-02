"""Reviewed withholding covers every published projection, without losing sources."""

import copy
import gzip
import importlib.util
import json
from pathlib import Path

from fairway.open_catalog import (
    derived_files,
    load_public_source,
    load_source,
    transport,
    withhold_facilities,
)

ROOT = Path(__file__).resolve().parents[1]
FACILITY = "osm/relation/4498071"
COURSE = "c-77e7e09e-fa27-4501-b4a6-42f946fb50e1"


def test_forest_ridge_identity_sources_and_exact_public_losses():
    metadata, source = load_source(ROOT)
    public_metadata, public = load_public_source(ROOT)
    assert len(source["facilities"]) - len(public["facilities"]) == 1
    assert len(source["courses"]) - len(public["courses"]) == 1
    for kind, key, withheld in (
        ("facilities", "facility_id", FACILITY),
        ("courses", "course_id", COURSE),
    ):
        assert public[kind] == [r for r in source[kind] if r[key] != withheld]
    facility = next(r for r in source["facilities"] if r["facility_id"] == FACILITY)
    assert facility["address_text"] == "7501 E Kenosha St, Broken Arrow, OK 74014"
    assert facility["course_ids"] == [COURSE]
    assert facility["fact_sources"] and facility["osm"]  # Historical provenance stays.
    assert any(
        r["facility_id"] == "osm/relation/11895563" for r in public["facilities"]
    )
    assert public_metadata["relationships"] == metadata["relationships"]
    assert public_metadata["provenance"] == metadata["provenance"]
    assert public_metadata["destinations"] == [
        r for r in metadata["destinations"] if r["id"] != FACILITY
    ]
    exclusions = json.loads(
        (ROOT / "data/catalog-inputs/withheld-facilities.json").read_text()
    )
    assert len(exclusions) == 1
    entry = exclusions[0]
    assert entry["facility_ids"] == [FACILITY, facility["released_id"]]
    assert entry["conversion_date"] is None
    assert entry["first_verified_on"] == "2026-11-01"
    assert all(
        s["source_url"].startswith("https://") and s["checked_on"]
        for s in entry["sources"]
    )


def test_withholding_removes_child_relationships_without_mutating_source():
    value = {
        "facilities": [{"facility_id": "f-held"}, {"facility_id": "f-keep"}],
        "courses": [{"course_id": "c-held", "facility_id": "f-held"}],
        "destinations": [{"id": "f-held"}, {"id": "f-keep"}],
        "relationships": {
            "component": [{"id": "p-held", "course_id": "c-held"}],
            "round_option": [{"id": "r-held", "course_id": "c-held"}],
            "round_component": [
                {"id": "l-held", "component_id": "p-held", "round_id": "r-held"}
            ],
            "tee_set": [{"id": "t-held", "round_id": "r-held"}],
            "alias": [
                {"id": "a-held", "facility_id": "f-held"},
                {"id": "a-keep", "facility_id": "f-keep"},
            ],
        },
    }
    before = copy.deepcopy(value)
    public = withhold_facilities(value, [{"facility_ids": ["f-held"]}])
    assert value == before
    assert public["courses"] == []
    assert public["facilities"] == [{"facility_id": "f-keep"}]
    assert public["destinations"] == [{"id": "f-keep"}]
    assert public["relationships"] == {
        "component": [],
        "round_option": [],
        "round_component": [],
        "tee_set": [],
        "alias": [{"id": "a-keep", "facility_id": "f-keep"}],
    }


def test_regenerated_downloads_browser_details_and_map_omit_withheld_records():
    manifest, raw, _ = transport(ROOT)
    value = json.loads(raw)
    assert manifest["counts"] == {
        "facilities": 16180,
        "courses": 4992,
        "destinations": 2992,
    }
    assert value["rebuild"]["counts"]["facilities"] == 16180
    assert value["rebuild"]["counts"]["courses"] == 4992
    files = derived_files(ROOT)
    downloads = [
        json.loads(gzip.decompress(files["data/catalog-release/catalog.json.gz"]))
    ]
    for kind in ("facilities", "courses"):
        geojson = json.loads(files[f"data/catalog/{kind}.geojson"])
        assert len(geojson["features"]) == manifest["counts"][kind]
        downloads.append(geojson)
    spec = importlib.util.spec_from_file_location(
        "withholding_pages", ROOT / "scripts/build_pages.py"
    )
    pages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pages)
    downloads.extend(
        [
            json.loads(pages.browser_details_bytes(value)),
            json.loads(pages.initial_map_bytes(value, manifest, {})),
        ]
    )
    for download in downloads:
        # Intake receipts retain historical entity IDs, but cannot create records.
        records = {k: v for k, v in download.items() if k != "provenance"}
        serialized = json.dumps(records)
        assert not any(identity in serialized for identity in (FACILITY, COURSE))
