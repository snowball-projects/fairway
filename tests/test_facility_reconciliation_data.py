"""The reviewed data decisions keep layout identities and source scope intact."""

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from fairway.catalog_reconcile import (
    apply_reconciliation,
    restore_before_reconciliation,
)
from fairway.open_catalog import load_source
from fairway.rebuild_catalog import checksum

ROOT = Path(__file__).resolve().parents[1]
BETH = "f-0129c277-d9de-4db0-b203-0d560081c668"


@pytest.fixture(scope="module")
def data():
    metadata, rows = load_source(ROOT)
    value = metadata | rows
    baseline = restore_before_reconciliation(value)
    plan = json.loads(
        (ROOT / "data/catalog-inputs/facility-reconciliation.json").read_text()
    )
    return value, baseline, plan


def test_frozen_decisions_only_remove_zero_actual_course_facilities(data):
    value, baseline, plan = data
    before = {r["facility_id"]: r for r in baseline["facilities"]}
    counts = Counter(c["facility_id"] for c in baseline["courses"])
    decisions = plan["decisions"]
    assert Counter(d["rule"] for d in decisions) == {
        "a": 54,
        "b": 29,
        "c": 46,
        "d": 10,
        "e": 14,
        "bethpage": 1,
    }
    assert len(decisions) == len({d["source_id"] for d in decisions}) == 154
    for decision in decisions:
        source = decision["source_id"]
        assert counts[source] == 0
        assert checksum(before[source]) == decision["source_sha256"]
    assert len(value["facilities"]) == 16180
    assert len(value["courses"]) == 4985
    receipt = value["rebuild"]["preservation"]["reconciliation"]
    assert receipt["plan"] == plan
    assert receipt["plan_sha256"] == checksum(plan)


def test_reviewed_plan_reproduces_the_entire_published_catalog(data):
    value, baseline, plan = data
    assert apply_reconciliation(baseline, plan) == value


def test_existing_courses_and_point_match_targets_keep_their_identities(data):
    value, baseline, plan = data
    before = {c["course_id"]: c for c in baseline["courses"]}
    after = {c["course_id"]: c for c in value["courses"]}
    assert before.keys() <= after.keys()
    course_decisions = [d for d in plan["decisions"] if d["rule"] == "c"]
    assert sum(d["target_course_id"] in before for d in course_decisions) == 13
    assert sum(d["target_course_id"] not in before for d in course_decisions) == 33
    for d in plan["decisions"]:
        if d["rule"] not in {"c", "e"}:
            continue
        course = after[d["target_course_id"]]
        assert course["facility_id"] == d["target_facility_id"]
        if course["course_id"] in before:
            original = before[course["course_id"]]
            for field in (
                "name",
                "released_id",
                "nonmember_bookable",
                "arrival",
                "arrival_kind",
                "arrival_latitude",
                "arrival_longitude",
            ):
                assert course[field] == original[field]
            for field in ("access", "physical_holes"):
                if original[field] is not None:
                    assert course[field] == original[field]
        else:
            assert course["course_id"] == d["source_id"]
            assert course["plan_eligible"] is False
            assert course["nonmember_bookable"] is None
            assert course["arrival"] is None
    points = [d for d in plan["decisions"] if d["rule"] == "e"]
    assert len(points) == 14
    assert all(d["source_id"].startswith("osm/node/") for d in points)
    assert all(d["distance_km"] <= 2 for d in points)


def test_bethpage_is_one_facility_with_the_same_five_course_ids(data):
    value, baseline, _ = data
    facilities = {f["facility_id"]: f for f in value["facilities"]}
    original = next(f for f in baseline["facilities"] if f["facility_id"] == BETH)
    assert facilities[BETH]["course_ids"] == sorted(original["course_ids"])
    assert len(facilities[BETH]["course_ids"]) == 5
    assert "osm/way/29468839" not in facilities
    assert "osm/node/2854158382" not in facilities
    assert [
        f["facility_id"]
        for f in value["facilities"]
        if "bethpage" in (f["name"] or "").lower()
    ] == [BETH]
    assert {c["name"] for c in value["courses"] if c["facility_id"] == BETH} == {
        "Black Course",
        "Red Course",
        "Yellow Course",
        "Blue Course",
        "Green Course",
    }


def test_component_removal_does_not_create_courses_or_infer_parent_holes(data):
    value, baseline, plan = data
    receipt = value["rebuild"]["preservation"]["reconciliation"]
    archived = {d["source_id"]: d for d in receipt["decisions"]}
    courses = {c["course_id"] for c in value["courses"]}
    before = {f["facility_id"]: f for f in baseline["facilities"]}
    after = {f["facility_id"]: f for f in value["facilities"]}
    for d in plan["decisions"]:
        if d["rule"] != "b":
            continue
        assert d["source_id"] not in courses
        assert archived[d["source_id"]]["archival_scope"] == "component"
        assert archived[d["source_id"]]["source_snapshot"] == before[d["source_id"]]
        parent = d["target_facility_id"]
        assert after[parent]["physical_holes"] == before[parent]["physical_holes"]
    # A playable putting layout is kept as a course, not discarded as a green.
    assert "osm/way/183815258" in courses


def test_partial_rule_is_only_the_ten_reviewed_same_name_way_relation_pairs(data):
    _, baseline, plan = data
    before = {f["facility_id"]: f for f in baseline["facilities"]}
    for d in plan["decisions"]:
        if d["rule"] != "d":
            continue
        assert d["source_id"].startswith("osm/way/")
        assert d["target_facility_id"].startswith("osm/relation/")
        assert before[d["source_id"]]["name"] == before[d["target_facility_id"]]["name"]
        assert not d["geometry"]["source_covered_by_target"]
        assert 0 < d["geometry"]["source_fraction_in_target"] < 1
        assert 0 < d["geometry"]["target_fraction_in_source"] < 1


def test_held_identities_and_distinct_sibling_layouts_remain_separate(data):
    value, baseline, plan = data
    after = {f["facility_id"]: f for f in value["facilities"]}
    before = {f["facility_id"]: f for f in baseline["facilities"]}
    assert len(plan["held"]) == 14
    for held in plan["held"]:
        assert after[held["source_id"]] == before[held["source_id"]]
    courses = {c["course_id"]: c for c in value["courses"]}
    for ids in (("osm/way/231394152", "osm/way/231528197"),):
        assert all(i in courses for i in ids)
        assert courses[ids[0]]["facility_id"] == courses[ids[1]]["facility_id"]


def test_cypress_conflicting_address_and_site_stay_raw(data):
    value, baseline, plan = data
    decision = next(
        d for d in plan["decisions"] if d["source_id"] == "osm/way/96656326"
    )
    course = next(
        c for c in value["courses"] if c["course_id"] == decision["target_course_id"]
    )
    assert course["facility_id"] == "osm/relation/5462846"
    for field in decision["withheld_course_fields"]["fields"]:
        assert course[field] is None
    original = next(
        f for f in baseline["facilities"] if f["facility_id"] == decision["source_id"]
    )
    assert course["osm"] == original["osm"]
    assert "cypresscreek" in course["osm"]["tags"]["website"]


def test_evidence_uses_actual_osm_identities_not_catalog_only_ids(data):
    _, _, plan = data
    for item in [*plan["decisions"], *plan["held"]]:
        for url in item["evidence"]:
            parsed = urlsplit(url)
            assert parsed.scheme in {"http", "https"}
            if parsed.hostname in {"openstreetmap.org", "www.openstreetmap.org"}:
                assert re.fullmatch(
                    r"/(?:api/0\.6/)?(?:node|way|relation)/[1-9][0-9]*(?:/[1-9][0-9]*)?",
                    parsed.path,
                ), url
