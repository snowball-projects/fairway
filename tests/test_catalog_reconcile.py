"""Explicit reconciliation preserves evidence without widening fact scopes."""

import copy
import json
import subprocess
from pathlib import Path

import pytest

from fairway.catalog_reconcile import (
    apply_reconciliation,
    restore_before_reconciliation,
)
from fairway.open_catalog import load_source
from fairway.rebuild_catalog import blank, checksum

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def templates():
    _, rows = load_source(ROOT)
    return rows["facilities"][0], rows["courses"][0]


def osm(identifier, name="Source layout"):
    return {
        "feature_id": identifier,
        "name": name,
        "tags": {"golf": "course", "holes": "18", "access": "public"},
        "position": [-73.0, 41.0],
        "position_kind": "source point",
        "geometry_status": "source_point",
        "source_url": "https://www.openstreetmap.org/node/1",
        "checked_on": "2026-10-28",
        "credit": "OpenStreetMap contributors",
        "wikidata_ids": [],
    }


@pytest.fixture
def catalog(templates):
    facility_template, course_template = templates
    facilities = []
    for identifier, name in (("target", "Target club"), ("source", "Source layout")):
        row = blank(facility_template)
        row.update(
            facility_id=identifier,
            name=name,
            state="NY",
            country="US",
            course_count=0,
            documented_course_count=0,
            released_id=None,
            catalog_origin="osm",
            osm_identity=identifier,
            osm=osm(identifier, name),
        )
        facilities.append(row)
    course = blank(course_template)
    course.update(
        course_id="known-course",
        facility_id="target",
        facility_name="Target club",
        state="NY",
        country="US",
        name="Known course",
        physical_holes=9,
        nonmember_bookable=True,
        identity_status="operator_defined",
        released_id="released-course",
        plan_eligible=True,
        planning_basis="explicit_nonmember_fact",
    )
    facilities[0].update(
        course_ids=[course["course_id"]],
        course_count=1,
        documented_course_ids=[course["course_id"]],
        documented_course_count=1,
        course_inventory=[
            {
                key: course[key]
                for key in (
                    "course_id",
                    "name",
                    "physical_holes",
                    "identity_status",
                    "access",
                    "nonmember_bookable",
                )
            }
        ],
    )
    return {
        "revision": 8,
        "facilities": facilities,
        "courses": [course],
        "destinations": [
            {
                "id": "source",
                "scope": "facility_estimate",
                "latitude": 41,
                "longitude": -73,
            },
            {
                "id": "target",
                "scope": "facility_estimate",
                "latitude": 42,
                "longitude": -74,
            },
        ],
        "relationships": {
            key: []
            for key in (
                "alias",
                "component",
                "round_component",
                "round_option",
                "tee_set",
            )
        },
        "provenance": {
            "sources": [
                {
                    "id": "source",
                    "url": "https://example.test",
                    "license": "CC0-1.0",
                    "attribution": None,
                }
            ],
            "notes": [],
            "intake": [
                {
                    "entity_id": "source",
                    "entity_type": "facility",
                    "source_id": "source",
                }
            ],
        },
        "source_licenses": [{"source": "Original", "license": "CC0-1.0"}],
        "rebuild": {
            "counts": {"facilities": 2, "courses": 1},
            "preservation": {"rows": {}, "metadata": {}},
        },
    }


def decision(action, **values):
    return {
        "action": action,
        "source_id": "source",
        "target_facility_id": "target",
        "rule": "reviewed-explicit-identity",
        "reason": "Explicit source evidence supports this decision.",
        "evidence": [
            {"source_url": "https://example.test/decision", "checked_on": "2026-10-28"}
        ],
    } | values


def receipt(value):
    return value["rebuild"]["preservation"]["reconciliation"]


def validate_optional(value, tmp_path):
    public = copy.deepcopy(value)
    public["rebuild"].pop("preservation")
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(public))
    script = """
import fs from 'node:fs';
import {validateScopedOptional} from './src/fairway/static/optional-facts.mjs';
validateScopedOptional(JSON.parse(fs.readFileSync(process.argv[1], 'utf8')));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def observation(templates, identifier="observation"):
    row = copy.deepcopy(templates[0]["optional"]["practice_observation"][0])
    row.update(
        id=identifier,
        observation_id=identifier,
        facility_id="source",
        course_id=None,
        source_id="source",
        source_url="https://example.test",
        source_license="CC0-1.0",
        source_attribution=None,
    )
    return row


def test_merge_preserves_conflicts_sources_and_exact_optional_scope(
    catalog, templates, tmp_path
):
    source, target = catalog["facilities"][1], catalog["facilities"][0]
    source.update(released_id="released-source", name="Released name", access="private")
    target["access"] = "public"
    source["optional"]["practice_observation"] = [observation(templates)]
    source["fact_sources"] = [
        {
            "source_id": "source",
            "fields": ["access"],
            "license": "CC-BY-4.0",
            "checked_on": None,
        }
    ]
    source["osm"]["name"] = "Raw OSM name"
    original = copy.deepcopy(catalog)
    result = apply_reconciliation(catalog, {"decisions": [decision("merge_facility")]})
    merged = result["facilities"][0]
    assert merged["name"] == "Released name"
    assert merged["access"] == "private"
    assert merged["osm"] == original["facilities"][0]["osm"]
    assert merged["optional"]["practice_observation"][0]["facility_id"] == "target"
    assert result["courses"][0]["optional"]["practice_observation"] == []
    assert source["fact_sources"][0] in merged["fact_sources"]
    assert result["provenance"]["sources"][0]["id"] == "source"
    assert result["provenance"]["intake"][0] == {
        "entity_id": "target",
        "entity_type": "facility",
        "source_id": "source",
    }
    assert result["destinations"] == [original["destinations"][1]]
    assert receipt(result)["decisions"][0]["source_snapshot"] == source
    assert {row["field"] for row in receipt(result)["decisions"][0]["conflicts"]} == {
        "access",
        "name",
    }
    assert result["courses"][0]["facility_name"] == "Released name"
    assert catalog == original
    assert restore_before_reconciliation(result) == original
    validate_optional(result, tmp_path)


def test_merge_keeps_known_released_target_and_fills_only_unknowns(catalog):
    target, source = catalog["facilities"]
    target.update(released_id="known-target", access="public", website=None)
    source.update(
        released_id="known-source",
        access="private",
        website="https://example.test/source",
    )
    result = apply_reconciliation(catalog, [decision("merge_facility")])
    assert result["facilities"][0]["access"] == "public"
    assert result["facilities"][0]["website"] == source["website"]
    assert all(
        row["selected"] == "target"
        for row in receipt(result)["decisions"][0]["conflicts"]
    )
    assert restore_before_reconciliation(result) == catalog


@pytest.mark.parametrize("action", ["course", "match_course"])
def test_course_reuses_existing_identity_and_keeps_known_facts(
    catalog, templates, tmp_path, action
):
    source = catalog["facilities"][1]
    source["physical_holes"] = 36
    source["optional"]["practice_observation"] = [observation(templates)]
    course = catalog["courses"][0]
    course["osm"] = osm("already-known-point", "Pinned primary name")
    course["osm_identity"] = "already-known-point"
    original_course = copy.deepcopy(course)
    result = apply_reconciliation(
        catalog, [decision(action, target_course_id="known-course")]
    )
    assert len(result["courses"]) == 1
    matched = result["courses"][0]
    for key in (
        "course_id",
        "released_id",
        "name",
        "physical_holes",
        "nonmember_bookable",
        "plan_eligible",
        "planning_basis",
        "osm",
        "osm_identity",
    ):
        assert matched[key] == original_course[key]
    assert matched["optional"] == original_course["optional"]
    assert matched["access"] == "public"
    assert matched["physical_holes"] == 9
    assert receipt(result)["decisions"][0]["filled_fields"] == ["access"]
    assert matched["arrival"] is None and matched["arrival_latitude"] is None
    assert matched["fact_sources"][-1]["original_source_id"] == "source"
    assert (
        receipt(result)["decisions"][0]["source_snapshot"]["optional"]
        == source["optional"]
    )
    assert restore_before_reconciliation(result) == catalog
    validate_optional(result, tmp_path)


@pytest.mark.parametrize("explicit_id", [False, True])
def test_course_creation_projects_explicit_osm_without_arrival_or_booking_assumptions(
    catalog, tmp_path, explicit_id
):
    source = catalog["facilities"][1]
    source.update(
        physical_holes=36, booking_url="https://example.test/facility-booking"
    )
    options = {"target_course_id": "source"} if explicit_id else {}
    result = apply_reconciliation(catalog, [decision("course", **options)])
    course = next(row for row in result["courses"] if row["course_id"] == "source")
    assert course["facility_id"] == "target"
    assert course["osm"] == source["osm"]
    assert course["name"] == source["osm"]["name"]
    assert course["physical_holes"] == 18
    assert course["access"] == "public"
    assert course["nonmember_bookable"] is None and course["booking_url"] is None
    assert course["arrival"] is None and course["arrival_latitude"] is None
    assert course["plan_eligible"] is False
    assert course["planning_basis"] == "bookability_unconfirmed"
    assert course["destination_id"] is None
    assert result["facilities"][0]["course_count"] == 2
    assert result["facilities"][0]["documented_course_ids"] == ["known-course"]
    assert restore_before_reconciliation(result) == catalog
    validate_optional(result, tmp_path)


@pytest.mark.parametrize("tags", [{}, {"fee": "yes", "holes": "18", "golf:holes": "9"}])
def test_new_course_does_not_infer_access_or_holes_from_facility_scalars(catalog, tags):
    source = catalog["facilities"][1]
    source.update(access="public", physical_holes=36)
    source["osm"]["tags"] = tags
    result = apply_reconciliation(catalog, [decision("course")])
    course = next(row for row in result["courses"] if row["course_id"] == "source")
    assert course["access"] is None
    assert course["physical_holes"] is None
    assert course["plan_eligible"] is False
    assert course["osm"] == source["osm"]
    assert restore_before_reconciliation(result) == catalog


def test_new_course_keeps_own_state_and_country_when_parent_is_unknown(
    catalog, tmp_path
):
    parent = catalog["facilities"][0]
    parent.update(state=None, country=None)
    source = catalog["facilities"][1]
    source["osm"]["tags"].update({"addr:state": "TX", "addr:country": "US"})
    result = apply_reconciliation(catalog, [decision("course")])
    course = next(row for row in result["courses"] if row["course_id"] == "source")
    assert course["state"] == course["address_region"] == "TX"
    assert course["country"] == course["address_country"] == "US"
    assert result["facilities"][0]["state"] is None
    assert result["facilities"][0]["country"] is None
    assert course["address"]["region"] == "TX"
    assert course["osm"] == source["osm"]
    assert restore_before_reconciliation(result) == catalog
    validate_optional(result, tmp_path)


def test_known_parent_geography_keeps_conflicting_own_address_scoped_to_course(
    catalog, tmp_path
):
    source = catalog["facilities"][1]
    source["osm"]["tags"].update({"addr:state": "TX", "addr:country": "CA"})
    result = apply_reconciliation(catalog, [decision("course")])
    course = next(row for row in result["courses"] if row["course_id"] == "source")
    assert course["state"] == result["facilities"][0]["state"] == "NY"
    assert course["country"] == result["facilities"][0]["country"] == "US"
    assert course["address_region"] == course["address"]["region"] == "TX"
    assert course["address_country"] == course["address"]["country"] == "CA"
    assert restore_before_reconciliation(result) == catalog
    validate_optional(result, tmp_path)


def test_course_known_osm_id_already_exists_and_does_not_create_duplicate(catalog):
    existing = catalog["courses"][0]
    existing.update(
        course_id="source",
        osm=osm("source"),
        osm_identity="source",
        destination_id="source",
        arrival={
            "latitude": 40,
            "longitude": -75,
            "kind": "entrance",
            "reference": "https://example.test/arrival",
        },
        arrival_latitude=40,
        arrival_longitude=-75,
    )
    arrival = {
        "id": "source",
        "scope": "course_arrival",
        "latitude": 40,
        "longitude": -75,
        "reference": "https://example.test/arrival",
        "precision": "entrance",
    }
    catalog["destinations"].append(arrival)
    result = apply_reconciliation(catalog, [decision("course")])
    assert len(result["courses"]) == 1
    assert result["courses"][0]["course_id"] == "source"
    assert result["courses"][0]["physical_holes"] == 9
    assert result["courses"][0]["destination_id"] == "source"
    assert arrival in result["destinations"]
    assert restore_before_reconciliation(result) == catalog


def test_match_fills_null_osm_with_exact_source_observation(catalog):
    source_osm = copy.deepcopy(catalog["facilities"][1]["osm"])
    result = apply_reconciliation(
        catalog, [decision("match_course", target_course_id="known-course")]
    )
    assert result["courses"][0]["osm"] == source_osm
    assert result["courses"][0]["osm_identity"] == "source"
    assert restore_before_reconciliation(result) == catalog


def test_reviewed_conflicting_fields_stay_unknown_on_new_course(catalog, tmp_path):
    source = catalog["facilities"][1]
    source["osm"]["tags"].update(
        website="https://example.test/unrelated",
        **{"addr:street": "Other Venue", "addr:city": "Other City"},
    )
    withholding = {
        "fields": [
            "website",
            "address",
            "address_street_line1",
            "address_city",
            "address_purpose",
        ],
        "reason": "Reviewed website and address refer to another venue.",
    }
    result = apply_reconciliation(
        catalog, [decision("course", withheld_course_fields=withholding)]
    )
    course = next(row for row in result["courses"] if row["course_id"] == "source")
    assert all(course[field] is None for field in withholding["fields"])
    assert course["address_mode"] == "own"
    assert course["osm"] == source["osm"]
    assert course["physical_holes"] == 18 and course["access"] == "public"
    assert receipt(result)["decisions"][0]["source_snapshot"] == source
    assert (
        receipt(result)["decisions"][0]["withheld_course_fields_applied"] == withholding
    )
    assert all(
        not set(citation["fields"]) & set(withholding["fields"])
        for citation in course["fact_sources"]
    )
    assert restore_before_reconciliation(result) == catalog
    validate_optional(result, tmp_path)


@pytest.mark.parametrize(
    "withholding",
    [
        {"fields": ["physical_holes"], "reason": "Invalid field"},
        {"fields": ["website"]},
        {"fields": [], "reason": "Empty"},
    ],
)
def test_withheld_fields_require_explicit_new_course_fields_and_reason(
    catalog, withholding
):
    with pytest.raises(ValueError, match="explicit fields and reason"):
        apply_reconciliation(
            catalog, [decision("course", withheld_course_fields=withholding)]
        )
    with pytest.raises(ValueError, match="require a new course"):
        apply_reconciliation(
            catalog,
            [
                decision(
                    "course",
                    target_course_id="known-course",
                    withheld_course_fields={
                        "fields": ["website"],
                        "reason": "Never alter existing facts",
                    },
                )
            ],
        )


def test_component_archive_never_leaks_scalars_or_optional_facts_to_parent(
    catalog, templates, tmp_path
):
    source = catalog["facilities"][1]
    source.update(physical_holes=6, access="private")
    source["optional"]["practice_observation"] = [observation(templates)]
    catalog["relationships"]["alias"] = [
        {
            "id": "source-alias",
            "facility_id": "source",
            "course_id": None,
            "name": "Other component name",
        }
    ]
    result = apply_reconciliation(catalog, [decision("remove_component")])
    assert result["facilities"][0]["physical_holes"] is None
    assert result["facilities"][0]["access"] is None
    assert result["facilities"][0]["optional"]["practice_observation"] == []
    assert result["relationships"]["component"] == []
    assert result["relationships"]["alias"] == []
    assert result["provenance"]["intake"] == []
    assert receipt(result)["decisions"][0]["archival_scope"] == "component"
    assert receipt(result)["decisions"][0]["source_snapshot"] == source
    assert restore_before_reconciliation(result) == catalog
    validate_optional(result, tmp_path)


def test_only_typed_facility_refs_are_redirected(catalog):
    catalog["facilities"][0]["name"] = "source"
    catalog["provenance"]["intake"].append(
        {"entity_id": "source", "entity_type": "course", "source_id": "source"}
    )
    result = apply_reconciliation(catalog, [decision("merge_facility")])
    assert result["facilities"][0]["name"] == "source"
    assert result["provenance"]["intake"][1]["entity_id"] == "source"
    assert result["provenance"]["sources"][0]["id"] == "source"
    assert restore_before_reconciliation(result) == catalog


@pytest.mark.parametrize(
    "change",
    ["after_row", "before_row", "before_metadata", "before_rebuild", "source_snapshot"],
)
def test_restore_checks_before_and_after_evidence_hashes(catalog, change):
    result = apply_reconciliation(catalog, [decision("remove_component")])
    proof = receipt(result)
    if change == "after_row":
        result["facilities"][0]["name"] = "Tampered operational row"
    elif change == "before_row":
        proof["before"]["rows"]["facilities"][0]["row"]["name"] = "Tampered original"
    elif change == "before_metadata":
        proof["before"]["metadata"]["destinations"]["value"][0]["latitude"] = 99
    elif change == "before_rebuild":
        proof["before"]["rebuild"]["value"]["counts"]["facilities"] = 999
    else:
        proof["decisions"][0]["source_snapshot"]["name"] = "Tampered source"
    with pytest.raises(ValueError, match="digest changed"):
        restore_before_reconciliation(result)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"action": "guess"}, "Unknown reconciliation action"),
        ({"source_id": "unknown"}, "Unknown reconciliation facility"),
        ({"target_facility_id": "source"}, "target itself"),
        ({"evidence": []}, "Missing reconciliation evidence"),
        ({"reason": ""}, "Missing reconciliation decision"),
        ({"source_sha256": "incorrect"}, "source digest changed"),
        ({"target_course_id": "known-course"}, "cannot target a course"),
    ],
)
def test_invalid_explicit_decisions_are_rejected_before_mutation(
    catalog, updates, message
):
    original = copy.deepcopy(catalog)
    with pytest.raises(ValueError, match=message):
        apply_reconciliation(catalog, [decision("merge_facility") | updates])
    assert catalog == original


def test_source_digest_and_invalid_course_targets(catalog):
    source = catalog["facilities"][1]
    result = apply_reconciliation(
        catalog, [decision("merge_facility", source_sha256=checksum(source))]
    )
    assert restore_before_reconciliation(result) == catalog
    with pytest.raises(ValueError, match="requires an existing target_course_id"):
        apply_reconciliation(catalog, [decision("match_course")])
    with pytest.raises(ValueError, match="Unknown target course"):
        apply_reconciliation(catalog, [decision("course", target_course_id="missing")])


def test_sources_with_actual_courses_chains_cycles_and_repeated_sources_are_rejected(
    catalog,
):
    with pytest.raises(ValueError, match="Repeated reconciliation source"):
        apply_reconciliation(
            catalog, [decision("merge_facility"), decision("remove_component")]
        )
    other = copy.deepcopy(catalog["facilities"][1])
    other["facility_id"] = "third"
    catalog["facilities"].append(other)
    with pytest.raises(ValueError, match="chain or cycle"):
        apply_reconciliation(
            catalog,
            [
                decision("merge_facility", target_facility_id="third"),
                decision("merge_facility", source_id="third"),
            ],
        )
    with pytest.raises(ValueError, match="chain or cycle"):
        apply_reconciliation(
            catalog,
            [
                decision("merge_facility", target_facility_id="third"),
                decision(
                    "merge_facility", source_id="third", target_facility_id="source"
                ),
            ],
        )
    catalog["courses"][0]["facility_id"] = "source"
    with pytest.raises(ValueError, match="actual course rows"):
        apply_reconciliation(catalog, [decision("remove_component")])


def test_second_application_is_rejected_and_unchanged_rows_are_verified(catalog):
    result = apply_reconciliation(catalog, [decision("remove_component")])
    with pytest.raises(ValueError, match="already has a reconciliation receipt"):
        apply_reconciliation(result, [])
    result["source_licenses"][0]["license"] = "changed"
    with pytest.raises(ValueError, match="after digest changed"):
        restore_before_reconciliation(result)
