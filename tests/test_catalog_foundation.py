"""Safety regressions for identity, uncertain access and destination generation."""

import copy
import importlib.util
import json
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("foundation", ROOT / "scripts/catalog.py")
foundation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(foundation)


@pytest.fixture(scope="module")
def source():
    return foundation.read(ROOT / "data/catalog.json")


def named(value, name):
    return next(f for f in value["facilities"] if f["name"] == name)


def test_mixed_access_and_partial_inventory_survive_export(source):
    public = foundation.exports(source)["public-courses.json"]
    lake = named(public, "Lake of Isles")
    assert lake["physical_holes"] == 36
    assert [(c["name"], c["holes"], c["access"]) for c in lake["courses"]] == [
        ("North", 18, "public"),
        ("South", 18, "private"),
    ]
    assert "only on North" in lake["access_note"]
    winagamie = named(public, "Winagamie Golf Course")
    assert winagamie["physical_holes"] is None
    assert not winagamie["inventory_complete"]
    assert all(
        c["holes"] is None and c["access"] == "unknown" for c in winagamie["courses"]
    )
    assert source["research"][winagamie["id"]]["reported_main_holes"] == 27
    riverwood = named(public, "Riverwood National Golf Course")
    assert riverwood["physical_holes"] is None
    assert [c["holes"] for c in riverwood["courses"]] == [None, 18]
    assert "Separate clubhouse" in riverwood["courses"][1]["location_note"]
    assert not any("arrival" in c for c in riverwood["courses"])
    assert named(public, "Farmlinks Golf Club")["address"]["purpose"] == "mailing"


def test_exports_preserve_ids_after_corrections_and_reordering(source):
    original = foundation.exports(source)
    changed = copy.deepcopy(source)
    changed["facilities"].reverse()
    lake = named(changed, "Lake of Isles")
    lake["name"] = "Corrected name"
    lake["address"]["text"] = "Corrected address"
    lake["courses"].reverse()
    foundation.validate(changed)
    after = foundation.exports(changed)
    assert {f["id"] for f in after["public-courses.json"]["facilities"]} == {
        f["id"] for f in original["public-courses.json"]["facilities"]
    }
    assert {c["id"] for c in lake["courses"]} == {
        c["id"]
        for c in named(original["public-courses.json"], "Lake of Isles")["courses"]
    }
    assert foundation.exports(source) == original


def test_estimates_keep_exact_precision_and_never_become_routing_points(source):
    public = foundation.exports(source)["public-courses.json"]
    source_locations = {f["id"]: f["map_location"] for f in source["facilities"]}
    assert len(public["facilities"]) == len(source_locations)
    assert {
        f["id"]: f["map_location"] for f in public["facilities"]
    } == source_locations
    ranking_facilities = {
        c["facility_id"]
        for c in foundation.exports(source)["course-catalog.json"]["courses"]
    }
    assert all(
        f["map_location"]["kind"] == "address_range_estimate"
        for f in public["facilities"]
        if f["map_location"] and f["id"] not in ranking_facilities
    )
    changed = copy.deepcopy(source)
    candidate = changed["facilities"][-1]["courses"][0]
    candidate["arrival"]["kind"] = "address_range_estimate"
    with pytest.raises(ValueError, match="arrival"):
        foundation.validate(changed)


@pytest.mark.parametrize(
    "defect",
    [
        "missing_id",
        "duplicate_course",
        "dangling_source",
        "dangling_field",
        "unknown_access",
        "mailing_destination",
    ],
)
def test_invalid_proposals_do_not_pass_validation(source, defect):
    value = copy.deepcopy(source)
    if defect == "missing_id":
        del value["facilities"][0]["id"]
    elif defect == "duplicate_course":
        value["facilities"][-1]["courses"][0]["id"] = value["facilities"][-2][
            "courses"
        ][0]["id"]
    elif defect == "dangling_source":
        value["research"][value["facilities"][0]["id"]]["listed_sources"].append(
            "missing"
        )
    elif defect == "dangling_field":
        value["research"][value["facilities"][-1]["id"]]["support"][0]["fields"].append(
            "imaginary"
        )
    elif defect == "unknown_access":
        value["facilities"][-1]["courses"][0]["access"] = "unknown"
    elif defect == "mailing_destination":
        value["facilities"][-1]["address"]["purpose"] = "mailing"
    with pytest.raises(ValueError):
        foundation.validate(value)


def test_minimal_course_location_override_wins_over_shared_contact(source):
    value = copy.deepcopy(source)
    facility = value["facilities"][-1]
    facility["address"]["purpose"] = "contact"
    facility["courses"][0]["address"] = {
        "text": "Separate clubhouse",
        "purpose": "clubhouse",
    }
    foundation.validate(value)
    exported = foundation.exports(value)["course-catalog.json"]["courses"][-1]
    assert exported["address"] == "Separate clubhouse"
    assert exported["address_purpose"] == "clubhouse"


def test_reviewed_import_rejects_stale_source_and_preserves_it(tmp_path, source):
    current = tmp_path / "catalog.json"
    proposal = tmp_path / "reviewed.json"
    body = foundation.encoded(source)
    current.write_bytes(body)
    proposal.write_bytes(body)
    result = subprocess.run(
        [
            "python",
            str(ROOT / "scripts/catalog.py"),
            "import",
            "--source",
            str(current),
            "--proposal",
            str(proposal),
            "--expected-sha256",
            "0" * 64,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "source changed since review" in result.stderr
    assert current.read_bytes() == body
    result = subprocess.run(
        [
            "python",
            str(ROOT / "scripts/catalog.py"),
            "import",
            "--source",
            str(current),
            "--proposal",
            str(proposal),
            "--expected-sha256",
            sha256(body).hexdigest(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(current.read_bytes()) == source


def test_import_refuses_accidental_facility_identity_replacement(tmp_path, source):
    current = tmp_path / "catalog.json"
    body = foundation.encoded(source)
    current.write_bytes(body)
    changed = copy.deepcopy(source)
    facility = changed["facilities"][-1]
    original_id = facility["id"]
    facility["id"] = "f-00000000-0000-4000-8000-000000000000"
    changed["research"][facility["id"]] = changed["research"].pop(original_id)
    foundation.validate(changed)
    proposal = tmp_path / "reviewed.json"
    proposal.write_bytes(foundation.encoded(changed))
    result = subprocess.run(
        [
            "python",
            str(ROOT / "scripts/catalog.py"),
            "import",
            "--source",
            str(current),
            "--proposal",
            str(proposal),
            "--expected-sha256",
            sha256(body).hexdigest(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "existing IDs removed" in result.stderr
    assert current.read_bytes() == body


def test_ranking_export_accepts_field_specific_course_support(source):
    value = copy.deepcopy(source)
    facility = value["facilities"][-1]
    cid = facility["courses"][0]["id"]
    supports = value["research"][facility["id"]]["support"]
    original = supports.pop(0)
    broad_fields = [field for field in original["fields"] if field != "courses"]
    supports.extend(
        [
            {**original, "fields": broad_fields},
            {**original, "fields": [f"courses.{cid}.holes", f"courses.{cid}.name"]},
            {**original, "fields": [f"courses.{cid}.access"]},
        ]
    )
    foundation.validate(value)
    exported = foundation.exports(value)["course-catalog.json"]["courses"][-1]
    assert exported["id"] == cid
    assert exported["facts_source"] == original["source"]
    assert exported["access"] == "public"
    assert supports[-1]["observed_on"] == original["observed_on"]


def test_ranking_validation_rejects_null_arrival_source_before_export(source):
    value = copy.deepcopy(source)
    facility = value["facilities"][-1]
    value["research"][facility["id"]]["support"][1]["source"] = None
    with pytest.raises(ValueError, match="arrival lacks a scoped source"):
        foundation.validate(value)
