import json
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from test_national import ORIGINS, Areas, Matrix

from fairway.facilities import load_facility_catalog
from fairway.national import calculate_national_facility_ranking
from fairway.national_modo import ModoMatrixProvider

CATALOG = (
    Path(__file__).resolve().parents[1] / "src/fairway/static/data/public-courses.json"
)


def record(number, *, holes=18, layouts=(), access="public", kind="property_point"):
    return {
        "id": f"f-{UUID(int=number)}",
        "name": f"Facility {number}",
        "state": "NE",
        "physical_holes": holes,
        "inventory_complete": False,
        "website": None,
        "access_note": "Nonmembers subject to retained access conditions.",
        "public_access": access,
        "map_location": {"latitude": 41.0, "longitude": -96.0, "kind": kind},
        "courses": [{"holes": h, "access": a} for h, a in layouts],
    }


def catalog(tmp_path, *records):
    path = tmp_path / "public-courses.json"
    path.write_text(
        json.dumps(
            {"schema_version": 3, "updated_on": "2026-10-13", "facilities": records}
        )
    )
    return load_facility_catalog(path)


def ranking(candidates, holes=(9, 18), matrix=None):
    matrix = matrix or Matrix({f.identifier: (100, 200) for f in candidates})
    return calculate_national_facility_ranking(
        ORIGINS, "maximum", candidates, Areas(), matrix, holes=holes
    )


def public_map_ids(path=CATALOG):
    """Use the existing JavaScript map contract as an independent eligibility oracle."""
    script = """
      import { readFileSync } from 'node:fs';
      const { mapEligible } = await import(process.argv[1]);
      const data = JSON.parse(readFileSync(0, 'utf8'));
      console.log(JSON.stringify(data.facilities.filter(mapEligible).map(f => f.id)));
    """
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            script,
            (CATALOG.parent.parent / "catalog.mjs").as_uri(),
        ],
        input=path.read_text(),
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return set(json.loads(result.stdout))


def test_reuses_existing_catalog_pins_ids_and_layout_evidence():
    retained = json.loads(CATALOG.read_text())
    loaded = load_facility_catalog(CATALOG)
    originals = {f["id"]: f for f in retained["facilities"]}
    assert {f.identifier for f in loaded.facilities} == public_map_ids()
    assert len(loaded.facilities) == len({f.identifier for f in loaded.facilities})
    for candidate in loaded.facilities:
        source = originals[candidate.identifier]
        assert candidate.routing_coordinate == (
            source["map_location"]["latitude"],
            source["map_location"]["longitude"],
        )
        assert candidate.coordinate_basis == (
            "property_pin"
            if source["map_location"]["kind"] == "property_point"
            else source["map_location"]["kind"]
        )
        assert candidate.public_layout_holes == tuple(
            sorted(
                {
                    c["holes"]
                    for c in source["courses"]
                    if c["access"] == "public" and c["holes"] in (9, 18)
                }
            )
        )
        assert candidate.physical_holes == source["physical_holes"]
        assert candidate.website == source["website"]
        assert candidate.inventory_complete == source["inventory_complete"]
        assert candidate.access_note == source.get("access_note")


def test_new_hole_fact_admits_existing_pin_without_inventing_layout(tmp_path):
    unknown = record(1, holes=None)
    before = catalog(tmp_path, unknown, record(2))
    path = tmp_path / "public-courses.json"
    assert {f.identifier for f in before.facilities} == public_map_ids(path)
    known = {**unknown, "physical_holes": 9}
    after = catalog(tmp_path, known, record(2))
    assert {f.identifier for f in after.facilities} == public_map_ids(path)
    admitted = next(f for f in after.facilities if f.identifier == unknown["id"])
    assert len(after.facilities) == len(before.facilities) + 1
    assert admitted.routing_coordinate == (41.0, -96.0)
    assert admitted.public_layout_holes == ()
    assert admitted.layout_filter_status((9, 18)) == "unconfirmed"
    assert [
        r.facility.identifier for r in ranking(after.facilities).ranking.facilities
    ] == [unknown["id"], record(2)["id"]]


@pytest.mark.parametrize("holes", [(9,), (18,)])
def test_single_layout_filter_does_not_infer_layouts_from_total(tmp_path, holes):
    candidates = catalog(
        tmp_path,
        record(1, holes=holes[0]),
        record(2, holes=36, layouts=((holes[0], "public"),)),
        record(3, layouts=((holes[0], "private"),)),
    ).facilities
    result = ranking(candidates, holes)
    assert [r.facility.identifier for r in result.ranking.facilities] == [
        candidates[1].identifier
    ]
    assert (
        result.ranking.facilities[0].facility.layout_filter_status(holes) == "confirmed"
    )


def test_default_includes_unknown_layouts_with_explicit_uncertainty(tmp_path):
    candidates = catalog(
        tmp_path, record(1), record(2, layouts=((18, "public"),))
    ).facilities
    result = ranking(candidates)
    statuses = {
        r.facility.identifier: r.facility.layout_filter_status((9, 18))
        for r in result.ranking.facilities
    }
    assert statuses == {
        candidates[0].identifier: "unconfirmed",
        candidates[1].identifier: "confirmed",
    }


def test_private_and_unqualified_estimates_do_not_enter_candidates(tmp_path):
    c = catalog(
        tmp_path,
        record(1),
        record(2, access="private", layouts=((18, "public"),)),
        record(3, kind="address_range_estimate"),
    )
    assert len(c.facilities) == 1


def test_one_matrix_target_per_property_even_with_multiple_public_layouts(tmp_path):
    c = catalog(tmp_path, record(1, holes=36, layouts=((18, "public"), (18, "public"))))
    matrix = Matrix({c.facilities[0].identifier: (100, 200)})
    result = ranking(c.facilities, matrix=matrix)
    assert len(matrix.calls[0][1]) == 1
    assert len(result.ranking.facilities) == 1


def test_one_unreachable_golfer_excludes_complete_facility_score(tmp_path):
    c = catalog(tmp_path, record(1), record(2))

    class Router:
        def matrix(self, origins, targets):
            return ((100, 101), (None, 102))

    result = ranking(c.facilities, matrix=ModoMatrixProvider(Router()))
    assert [r.facility.identifier for r in result.ranking.facilities] == [
        c.facilities[1].identifier
    ]
    assert result.ranking.unranked_facilities[0].reason == "unreachable"
    assert (
        result.ranking.unranked_facilities[0].facility.identifier
        == c.facilities[0].identifier
    )


@pytest.mark.parametrize("change", ["origin", "ids", "coordinates"])
def test_provider_identity_changes_fail_whole_ranking(tmp_path, change):
    c = catalog(tmp_path, record(1))

    class WrongMatrix(Matrix):
        def calculate(self, *args, **kwargs):
            result = super().calculate(*args, **kwargs)
            if change == "origin":
                return replace(
                    result,
                    origin_coordinates=tuple(reversed(result.origin_coordinates)),
                )
            if change == "ids":
                return replace(result, destination_ids=("different",))
            return replace(
                result,
                destinations=(replace(result.destinations[0], coordinate=(40, -95)),),
            )

    with pytest.raises(RuntimeError):
        ranking(
            c.facilities, matrix=WrongMatrix({c.facilities[0].identifier: (100, 200)})
        )


def test_duplicate_catalog_ids_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        catalog(tmp_path, record(1), record(1))


def test_restricted_access_is_valid_but_never_enters_public_candidates(tmp_path):
    retained = catalog(
        tmp_path, record(1), record(2, access="restricted", layouts=((18, "public"),))
    )
    assert {f.identifier for f in retained.facilities} == {record(1)["id"]}
    assert {f.identifier for f in retained.facilities} == public_map_ids(
        tmp_path / "public-courses.json"
    )
