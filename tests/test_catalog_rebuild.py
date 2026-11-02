"""Exact identity joins preserve released facts without inventing layouts."""

import copy
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from fairway.catalog_reconcile import restore_before_reconciliation
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
    baseline = restore_before_reconciliation(value)
    rows = {kind: baseline[kind] for kind in ("facilities", "courses")}
    receipts = metadata["rebuild"]["preservation"]["rows"]
    assert len(receipts) == 7430 + 4918
    osm = [
        r["osm_identity"] for group in rows.values() for r in group if r["osm_identity"]
    ]
    assert len(osm) == len(set(osm)) == 13413
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


@pytest.mark.parametrize(
    ("geometry", "course", "excluded"),
    [
        ("source_polygon", False, True),
        ("source_point", False, False),
        ("not_assembled", False, False),
        ("source_polygon", True, False),
    ],
)
def test_only_new_unnamed_facility_polygons_are_withheld(geometry, course, excluded):
    data = inputs()
    feature = data[2][1]
    feature.update(name=None, geometry_status=geometry)
    feature["tags"] = {"golf": "course"} if course else {}
    original = copy.deepcopy(data)
    value = rebuild(*data)
    ids = {r.get("course_id") or r["facility_id"] for k in data[1] for r in value[k]}
    assert (feature["feature_id"] not in ids) == excluded
    assert value["rebuild"]["counts"]["excluded_unnamed_osm_outlines"] == int(excluded)
    assert data == original  # The source observation, geometry and rights remain.
    assert_preserved(value)


def test_unnamed_released_match_and_unmatched_records_always_survive():
    data = inputs()
    for row in data[1]["facilities"]:
        row["name"] = None
    data[2][0].update(name=None, geometry_status="source_polygon")
    value = rebuild(*data)
    assert_preserved(value)
    matched = next(r for r in value["facilities"] if r["released_id"] == "f-old")
    assert matched["facility_id"] == "osm/way/1" and matched["name"] is None
    assert any(r["facility_id"] == "f-ambiguous" for r in value["facilities"])
    assert value["courses"][0]["facility_id"] == matched["facility_id"]


def test_naming_a_withheld_source_feature_restores_its_exact_identity():
    data = inputs()
    feature = data[2][1]
    feature.update(name=None, geometry_status="source_polygon")
    assert rebuild(*data)["rebuild"]["counts"]["excluded_unnamed_osm_outlines"] == 1
    feature["name"] = "Verified source name"
    value = rebuild(*data)
    row = next(
        r for r in value["facilities"] if r["facility_id"] == feature["feature_id"]
    )
    assert (
        row["name"] == feature["name"] and row["osm_identity"] == feature["feature_id"]
    )
    assert value["rebuild"]["counts"]["excluded_unnamed_osm_outlines"] == 0
    assert_preserved(value)


def test_pinned_inputs_retain_every_withheld_outline_without_a_second_catalog():
    metadata, rows = load_source(ROOT)
    baseline = restore_before_reconciliation(metadata | rows)
    rows = {kind: baseline[kind] for kind in ("facilities", "courses")}
    inputs = {}
    for name, pin in metadata["rebuild"]["build_inputs"].items():
        path = ROOT / "data/catalog-inputs" / name
        raw = (
            path.read_bytes()
            if path.exists()
            else gzip.decompress(path.with_suffix(path.suffix + ".gz").read_bytes())
        )
        assert len(raw) == pin["bytes"]
        assert hashlib.sha256(raw).hexdigest() == pin["sha256"]
        inputs[name] = json.loads(raw)
    features = {r["feature_id"]: r for r in inputs["osm-features.json"]}
    published = {
        r["osm_identity"] for group in rows.values() for r in group if r["osm_identity"]
    }
    excluded = set(features) - published
    assert len(features) == 16516 and len(excluded) == 3103
    assert all(
        not features[key]["name"]
        and features[key]["geometry_status"] == "source_polygon"
        and features[key]["tags"].get("golf") != "course"
        for key in excluded
    )
    assert Counter(
        r["osm"]["geometry_status"] for r in rows["facilities"] if not r["name"]
    ) == {"source_point": 94, "not_assembled": 3}
    assert sum(r["name"] is None for r in rows["courses"]) == 2437
    assert inputs["osm-pin.json"] == metadata["rebuild"]["osm_extract"]


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


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({}, None),
        ({"fee": "yes"}, None),
        ({"fee": "no"}, None),
        ({"access": "yes", "fee": "yes"}, "public"),
        ({"access": "public"}, "public"),
        ({"access": "private", "fee": "no"}, "private"),
        *[
            ({"access": value, "fee": "yes"}, "restricted")
            for value in (
                "no",
                "restricted",
                "customers",
                "permissive",
                "permit",
                "guests",
                "residents",
            )
        ],
        ({"access": "unknown"}, None),
        ({"access": "yes;private"}, None),
    ],
)
def test_osm_access_never_infers_permission_from_fees(tags, expected):
    from fairway.rebuild_catalog import osm_values

    assert osm_values(tags)["access"] == expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({}, None),
        ({"holes": "9"}, 9),
        ({"golf:holes": "18"}, 18),
        ({"holes": "18", "golf:holes": "18"}, 18),
        ({"holes": "9", "golf:holes": "18"}, None),
        ({"holes": "unknown", "golf:holes": "18"}, None),
        ({"holes": "18", "golf:holes": "0"}, None),
        *[
            ({"golf:holes": value}, None)
            for value in ("0", "-1", "9;18", "18.0", "eighteen", "９")
        ],
    ],
)
def test_osm_holes_require_positive_agreeing_integers(tags, expected):
    from fairway.rebuild_catalog import osm_values

    assert osm_values(tags)["physical_holes"] == expected


def test_osm_enrichment_fills_nulls_and_preserves_released_facts_and_citations():
    data = inputs()
    for row in data[1]["facilities"]:
        row.update(access=None, physical_holes=None)
    data[1]["facilities"][0]["access"] = "public"
    data[2][0]["tags"] = {"access": "private", "golf:holes": "18", "fee": "yes"}
    data[2][1]["tags"] = {"access": "customers", "holes": "9", "golf:holes": "18"}
    value = rebuild(*data)
    assert_preserved(value)
    rows = {r["facility_id"]: r for r in value["facilities"]}
    matched = rows["osm/way/1"]
    assert matched["access"] == "public"  # Contradictory source stays observable.
    assert matched["osm"]["tags"]["access"] == "private"
    assert matched["physical_holes"] == 18
    assert matched["fact_sources"][0] == data[1]["facilities"][0]["fact_sources"][0]
    citation = next(
        c for c in matched["fact_sources"] if c["fields"] == ["physical_holes"]
    )
    assert citation["source_url"] == data[2][0]["source_url"]
    assert citation["checked_on"] == "2026-10-26" and citation["license"] == "ODbL-1.0"
    assert rows["osm/way/2"]["access"] == "restricted"
    assert rows["osm/way/2"]["physical_holes"] is None
    assert rows["osm/way/2"]["osm"]["tags"]["golf:holes"] == "18"
    assert len(value["courses"]) == 2  # No new layouts or course identities.
    matched["physical_holes"] = 27
    with pytest.raises(ValueError, match="OSM enrichment changed"):
        assert_preserved(value)


def test_known_holes_win_over_osm_without_losing_the_disagreeing_observation():
    data = inputs()
    for row in data[1]["facilities"]:
        row.update(access=None, physical_holes=None)
    data[1]["facilities"][0]["physical_holes"] = 27
    data[2][0]["tags"] = {"holes": "18", "fee": "yes"}
    value = rebuild(*data)
    row = next(r for r in value["facilities"] if r["released_id"] == "f-old")
    assert row["physical_holes"] == 27 and row["access"] is None
    assert row["osm"]["tags"] == {"holes": "18", "fee": "yes"}
    assert_preserved(value)


@pytest.mark.parametrize("add_source", [False, True])
def test_reviewed_append_only_facts_keep_original_release_integrity(add_source):
    from fairway.rebuild_catalog import checksum

    data = inputs()
    for row in data[1]["facilities"]:
        row["optional"] = {"architecture_event": []}
    data[0]["relationships"] = {"round_option": []}
    value = rebuild(*data)
    original = copy.deepcopy(value)
    row = value["facilities"][0]
    observation = {"source_url": "https://owner.test/course", "event_kind": "design"}
    row["optional"]["architecture_event"] = [observation]
    new_sources = (
        [{"id": "owner", "url": "https://owner.test/course"}] if add_source else []
    )
    value["provenance"]["sources"].extend(new_sources)
    round_option = {"id": "new-round", "course_id": "c-layout", "round_holes": 18}
    value["relationships"]["round_option"].append(round_option)
    value["rebuild"]["reviewed_additions"] = {
        "optional": {
            row["facility_id"]: {
                "architecture_event": {"count": 1, "sha256": checksum([observation])}
            }
        },
        "sources": {"count": len(new_sources), "sha256": checksum(new_sources)},
        "relationships": {"round_option": {"new-round": checksum(round_option)}},
    }
    assert_preserved(value)
    assert value["rebuild"]["preservation"] == original["rebuild"]["preservation"]
    assert row["optional"]["architecture_event"] == [observation]
    damaged = copy.deepcopy(value)
    damaged["facilities"][0]["optional"]["architecture_event"][0]["event_kind"] = (
        "opening"
    )
    with pytest.raises(ValueError, match="Reviewed additions changed"):
        assert_preserved(damaged)
    damaged = copy.deepcopy(value)
    damaged["provenance"]["sources"][0]["url"] = "https://changed.test"
    with pytest.raises(ValueError, match="Released source/scope changed"):
        assert_preserved(damaged)
    damaged = copy.deepcopy(value)
    damaged["relationships"]["round_option"][0]["round_holes"] = 19
    with pytest.raises(ValueError, match="Reviewed relationship additions changed"):
        assert_preserved(damaged)


def test_reviewed_exclusion_survives_rebuilding_a_named_released_facility():
    from fairway.open_catalog import withhold_facilities

    data = inputs()
    exclusions = [{"facility_ids": ["f-old", "osm/way/1"]}]
    for name in ("Forest Ridge", "Changed source name"):
        data[2][0]["name"] = name
        rebuilt = rebuild(*data)
        public = withhold_facilities(rebuilt, exclusions)
        assert not any(r["facility_id"] == "osm/way/1" for r in public["facilities"])
        assert not any(r["course_id"] == "c-layout" for r in public["courses"])
        assert not any(r["id"] == "osm/way/1" for r in public["destinations"])
        # Rebuild and retention checks still see all original facts and source scope.
        assert_preserved(rebuilt)
        assert any(r["facility_id"] == "osm/way/1" for r in rebuilt["facilities"])
        assert any(r["facility_id"] == "f-ambiguous" for r in public["facilities"])
