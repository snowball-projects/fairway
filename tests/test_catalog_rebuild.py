"""Exact identity joins preserve released facts without inventing layouts."""

import copy
import json
from pathlib import Path

import pytest

from fairway.open_catalog import load_source
from fairway.rebuild_catalog import assert_preserved, rebuild, stored_bindings

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    metadata = {
        "revision": 7,
        "destinations": [{"id": "f-old", "scope": "facility_estimate"}],
        "provenance": {
            "sources": [
                {"id": "source", "url": "https://example.test", "license": "CC-BY-4.0"}
            ]
        },
        "relationships": {},
        "source_licenses": [{"source": "Original", "license": "CC-BY-4.0"}],
    }
    citation = {
        "fields": ["name"],
        "source_url": "https://example.test",
        "checked_on": None,
        "license": "CC-BY-4.0",
    }
    facilities = [
        {
            "facility_id": fid,
            "name": name,
            "optional": {},
            "course_ids": ["c-layout"] if fid == "f-old" else [],
            "fact_sources": [copy.deepcopy(citation)],
        }
        for fid, name in [("f-old", "Original name"), ("f-ambiguous", "Shared name")]
    ]
    courses = [
        {
            "course_id": "c-layout",
            "facility_id": "f-old",
            "name": "Known layout",
            "nonmember_bookable": None,
            "optional": {},
            "fact_sources": [copy.deepcopy(citation)],
        }
    ]
    features = [
        {
            "feature_id": f"osm/way/{n}",
            "tags": {"golf": "course"} if n == 3 else {},
            "name": "Shared name",
            "position": [1, 2],
            "source_url": f"https://www.openstreetmap.org/way/{n}",
            "checked_on": "2026-10-26",
            "credit": "OpenStreetMap contributors",
            "wikidata_ids": [],
        }
        for n in range(1, 5)
    ]
    wiki = {"entities": {}, "status": "entity_reads_complete", "missing_entity_ids": []}
    bindings = {"f-old": ["osm/way/1"], "f-ambiguous": ["osm/way/2", "osm/way/4"]}
    return (
        metadata,
        {"facilities": facilities, "courses": courses},
        features,
        wiki,
        {},
        bindings,
    )


def test_exact_identity_carries_all_facts_and_keeps_course_scope():
    data = inputs()
    value = rebuild(*data)
    assert_preserved(value)
    rows = {f["facility_id"]: f for f in value["facilities"]}
    matched = rows["osm/way/1"]
    assert matched["name"] == "Original name"
    assert matched["osm"]["name"] == "Shared name"
    assert matched["fact_sources"][0]["checked_on"] is None
    assert matched["fact_sources"][0]["license"] == "CC-BY-4.0"
    layout = next(c for c in value["courses"] if c["course_id"] == "c-layout")
    assert layout["facility_id"] == "osm/way/1" and layout["name"] == "Known layout"
    assert value["destinations"][0]["id"] == "osm/way/1"
    assert value["source_licenses"][0] == data[0]["source_licenses"][0]
    assert "f-ambiguous" in rows
    assert rows["osm/way/2"]["released_id"] is None
    standalone = next(c for c in value["courses"] if c["course_id"] == "osm/way/3")
    assert (
        standalone["facility_id"] is None and standalone["nonmember_bookable"] is None
    )
    assert standalone["plan_eligible"] is False
    assert len(value["courses"]) == 2  # No layout inferred for three OSM grounds.
    assert data[1]["facilities"][0]["facility_id"] == "f-old"  # Input untouched.


def test_names_never_enter_the_join_and_competing_ids_are_not_merged():
    data = inputs()
    value = rebuild(*data)
    data[1]["facilities"][0]["name"] = "Entirely different released name"
    data[2][0]["name"] = "Entirely different OSM name"
    other = rebuild(*data)
    assert value["rebuild"]["counts"] == other["rebuild"]["counts"]
    assert other["rebuild"]["counts"]["matched_released_facilities"] == 1
    assert other["rebuild"]["counts"]["catalog_only_facilities"] == 1
    data[5]["f-ambiguous"] = ["osm/way/1"]
    collision = rebuild(*data)
    assert collision["rebuild"]["counts"]["matched_released_facilities"] == 0


def test_fact_loss_and_duplicate_osm_identity_are_rejected():
    data = inputs()
    value = rebuild(*data)
    next(f for f in value["facilities"] if f["released_id"] == "f-old")["name"] = (
        "Lost fact"
    )
    with pytest.raises(ValueError, match="Released fact changed"):
        assert_preserved(value)
    data[2].append(data[2][0])
    with pytest.raises(ValueError, match="Duplicate OSM"):
        rebuild(*data)


def test_published_bindings_use_only_record_id_and_stored_osm_identity(tmp_path):
    path = tmp_path / "data/source-layers"
    path.mkdir(parents=True)
    (path / "binding.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "facility_id": "f-old",
                        "name": "Ignored",
                        "selected_feature": {"osm": {"type": "way", "id": 1}},
                    }
                ]
            }
        )
    )
    rows = [
        {
            "facility_id": "f-old",
            "name": "Different",
            "fact_sources": [
                {
                    "fields": ["map_location"],
                    "source_url": "https://example.test/binding.json",
                }
            ],
        }
    ]
    assert stored_bindings(tmp_path, rows) == {"f-old": ["osm/way/1"]}


def test_every_released_fact_and_source_scope_survives_in_the_single_catalog():
    metadata, rows = load_source(ROOT)
    value = metadata | rows
    assert_preserved(value)
    receipts = metadata["rebuild"]["preservation"]["rows"]
    assert len(receipts) == 7430 + 4918
    osm = [
        r["osm_identity"] for group in rows.values() for r in group if r["osm_identity"]
    ]
    assert len(osm) == len(set(osm)) == 16516
    assert sum(r["released_id"] is not None for r in rows["facilities"]) == 7430
    assert sum(r["released_id"] is not None for r in rows["courses"]) == 4918
    assert not (ROOT / "data/backbone").exists()


def test_identity_rekeying_never_rewrites_names_or_source_identifiers():
    data = inputs()
    data[1]["facilities"][0]["name"] = "f-old"
    data[0]["provenance"]["sources"][0]["id"] = "f-old"
    value = rebuild(*data)
    row = next(f for f in value["facilities"] if f["facility_id"] == "osm/way/1")
    assert row["name"] == "f-old"
    assert value["provenance"]["sources"][0]["id"] == "f-old"
    assert_preserved(value)


def test_an_explicit_course_identity_keeps_its_scope_and_layout_facts():
    data = inputs()
    data[5]["c-layout"] = ["osm/way/3"]
    value = rebuild(*data)
    course = next(c for c in value["courses"] if c["course_id"] == "osm/way/3")
    assert course["name"] == "Known layout" and course["released_id"] == "c-layout"
    assert course["facility_id"] == "osm/way/1"
    assert value["rebuild"]["counts"]["matched_released_courses"] == 1
    assert len(value["courses"]) == 1
    assert_preserved(value)
