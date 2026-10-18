"""Native publication preserves legacy identities, unknowns and course scope."""

import gzip
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def catalog():
    return json.loads(
        gzip.decompress((ROOT / "data/catalog-release/catalog.json.gz").read_bytes())
    )


def test_legacy_ids_mixed_access_and_nulls_survive(catalog):
    lake = next(f for f in catalog["facilities"] if f["name"] == "Lake of Isles")
    assert lake["facility_id"] == "f-f6463598-f26c-404e-9584-2abace25109d"
    assert lake["physical_holes"] == 36
    courses = {
        c["name"]: c
        for c in catalog["courses"]
        if c["facility_id"] == lake["facility_id"]
    }
    assert (
        courses["North"]["access"] == "public"
        and courses["South"]["access"] == "private"
    )
    win = next(f for f in catalog["facilities"] if f["name"] == "Winagamie Golf Course")
    assert win["physical_holes"] is None and win["inventory_complete"] is False
    twigs = next(
        c
        for c in catalog["courses"]
        if c["facility_id"] == win["facility_id"] and c["name"] == "TWIGS"
    )
    assert (
        twigs["physical_holes"] is None
        and twigs["access"] is None
        and twigs["arrival"] is None
    )


def test_native_inventory_never_promotes_components_or_private_booking(catalog):
    blackhawk = next(
        f
        for f in catalog["facilities"]
        if f["name"] == "Blackhawk Country Club" and f["state"] == "CA"
    )
    courses = [
        c for c in catalog["courses"] if c["facility_id"] == blackhawk["facility_id"]
    ]
    assert blackhawk["physical_holes"] == 36 and len(courses) == 2
    assert {c["name"] for c in courses} == {"Lakeside Course", "Falls Course"}
    assert all(
        c["identity_status"] == "operator_defined"
        and c["access"] == "private"
        and c["nonmember_bookable"] is None
        and not c["tee_sets"]
        for c in courses
    )
    assert sum(c["identity_status"] == "component" for c in catalog["courses"]) == 17


def test_all_native_relationships_and_public_evidence_are_preserved(catalog):
    assert (
        sum(len(f["course_ids"]) for f in catalog["facilities"])
        == len(catalog["courses"])
        == 4747
    )
    assert len(catalog["provenance"]["notes"]) == 8286
    assert all(set(note) == {"id"} for note in catalog["provenance"]["notes"])
    assert len(catalog["provenance"]["sources"]) == 18930
    assert len(catalog["provenance"]["intake"]) == 14465
    assert sum(c["arrival"] is not None for c in catalog["courses"]) == 8
    assert (
        not {"retained_document", "source_hold", "source_hold_scope"} & catalog.keys()
    )
    assert all("controls_reference" not in item for item in catalog["source_licenses"])


def test_existing_facility_course_roles_do_not_inherit_totals_or_offered_rounds(
    catalog,
):
    def courses(facility_id):
        return [c for c in catalog["courses"] if c["facility_id"] == facility_id]

    heron = courses("f-bdb8f9c8-e82c-477d-9472-0af471020bb1")
    assert len(heron) == 1
    assert heron[0]["facility_physical_holes"] == 18
    assert heron[0]["name"] is None and heron[0]["physical_holes"] is None
    assert heron[0]["access"] is None and heron[0]["nonmember_bookable"] is None

    common = courses("f-21a4fe0c-9956-468d-b154-72ea65ca6277")
    assert sorted(c["physical_holes"] for c in common) == [9, 18]
    green_knoll = courses("f-cbbe0345-832e-429c-920a-89494396796f")
    assert sorted(c["physical_holes"] for c in green_knoll) == [9, 18]
    assert {c["name"] for c in green_knoll} == {None, "Pitch and Putt Course"}

    brighton = courses("f-003187f4-8960-444f-a278-7074245e13fc")
    assert {c["name"]: c["physical_holes"] for c in brighton} == {
        "White Birch": 18,
        "Blue Spruce": 18,
        "Red Pine": 9,
    }
    for fid, names in [
        (
            "f-0333909f-6f6d-42bc-bf0f-9c32121519c3",
            {"Thistle", "Pine Cone", "Foxglove"},
        ),
        ("f-040ec089-0f4b-4173-9969-8daf2ed6a718", {"North", "South", "West"}),
    ]:
        layouts = courses(fid)
        assert len(layouts) == 3 and {c["name"] for c in layouts} == names
        assert all(c["physical_holes"] == 9 for c in layouts)
        assert all(c["identity_status"] == "operator_defined" for c in layouts)

    pheasant = courses("f-0273cf4c-e3eb-43d5-9090-d686dc8d2c69")
    assert len(pheasant) == 1 and pheasant[0]["physical_holes"] == 18
    for fid in [
        "f-041e7d6d-1b2a-4ef7-adb1-fb38a41fd27d",  # Closed reconstruction context.
        "f-049e4cc4-43da-4945-91f5-dc8b53653b4f",  # Held card is not count evidence.
        "f-02c13ff2-5af6-41a7-9ac1-c67a48c1498f",  # Par/metrics are not a count.
    ]:
        records = courses(fid)
        assert len(records) == 1 and records[0]["physical_holes"] is None
        assert records[0]["operating_status"] is None
    assert all(
        c["inventory_complete"] is False for c in common + green_knoll + brighton
    )
