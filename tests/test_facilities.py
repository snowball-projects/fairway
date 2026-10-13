import json
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


def test_reuses_existing_catalog_pins_ids_and_layout_evidence():
    retained = json.loads(CATALOG.read_text())
    loaded = load_facility_catalog(CATALOG)
    originals = {f["id"]: f for f in retained["facilities"]}
    assert len(loaded.facilities) == 4428
    assert sum(bool(f.public_layout_holes) for f in loaded.facilities) == 1318
    assert sum(f.coordinate_basis == "property_pin" for f in loaded.facilities) == 4420
    for candidate in loaded.facilities:
        source = originals[candidate.identifier]
        assert candidate.routing_coordinate == (
            source["map_location"]["latitude"],
            source["map_location"]["longitude"],
        )
        assert candidate.physical_holes == source["physical_holes"]
        assert candidate.access_note == source.get("access_note")


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
