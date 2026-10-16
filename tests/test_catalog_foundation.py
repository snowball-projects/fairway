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
        == 4131
    )
    assert len(catalog["provenance"]["notes"]) == 8286
    assert all(set(note) == {"id"} for note in catalog["provenance"]["notes"])
    assert len(catalog["provenance"]["sources"]) == 18855
    assert len(catalog["provenance"]["intake"]) == 13423
    assert sum(c["arrival"] is not None for c in catalog["courses"]) == 8
    assert (
        not {"retained_document", "source_hold", "source_hold_scope"} & catalog.keys()
    )
    assert all("controls_reference" not in item for item in catalog["source_licenses"])
