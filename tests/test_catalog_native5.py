"""Native typed intake must preserve scope, uncertainty and transaction boundaries."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from fairway import catalog_native as native
from fairway import catalog_native_read as read
from fairway.catalog_store import digest


def ident(prefix, number):
    return f"{prefix}-00000000-0000-4000-8000-{number:012x}"


EVIDENCE = {
    "source_id": "official",
    "collected_on": "2026-10-15",
    "status": "extracted",
}


@pytest.mark.parametrize("column", ["yardage", "difficulty_rating"])
def test_integrity_gate_rejects_direct_nonfinite_tee_values(db, column):
    with native.writer(db) as con:
        con.execute(
            "INSERT INTO tee_set(id,course_id,name,yardage_unit,"
            + column
            + ") VALUES(?,?,?,'yards',?)",
            (ident("t", 987), ident("c", 1), "Invalid direct scalar", float("inf")),
        )
        with pytest.raises(ValueError, match="nonfinite"):
            native.check(con)


def change(table, identifier, values, *, evidence=None, expected=None):
    return {
        "entity": table,
        "id": identifier,
        "values": values,
        "expected": expected,
        "evidence": evidence or EVIDENCE.copy(),
    }


def batch(identifier, *changes, sources=None):
    return {"batch_id": identifier, "sources": sources or [], "changes": list(changes)}


def observation(number, **extra):
    return change(
        "source_observation",
        ident("o", number),
        EVIDENCE | {"origin": "new_extraction"} | extra,
    )


def typed(table, number, **values):
    return change(
        table,
        ident("n", number),
        {"observation_id": ident("o", 1)} | values,
        evidence={"observation_id": ident("o", 1)},
    )


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "native.sqlite"
    native.create(path)
    source = {
        "id": "official",
        "url": "https://official.example/golf/course",
        "license": "Scoped attribution",
        "attribution": "Operator",
        "controls_reference": "private-reviewed-controls.json#/golf",
    }
    result = native.apply_batch(
        path,
        batch(
            "fixture",
            change(
                "facility",
                ident("f", 1),
                {
                    "name": "Synthetic 100% Golf",
                    "state": "IL",
                    "physical_holes": 27,
                    "inventory_complete": True,
                    "latitude": 40.0,
                    "longitude": -88.0,
                    "location_kind": "property_point",
                    "address_text": "Recorded contact address",
                    "address_purpose": "contact",
                },
            ),
            change(
                "facility",
                ident("f", 2),
                {"name": "Empty inventory", "state": "CA", "physical_holes": 72},
            ),
            change(
                "facility",
                ident("f", 3),
                {
                    "name": "Antimeridian",
                    "state": "HI",
                    "latitude": 0.0,
                    "longitude": 179.5,
                    "location_kind": "address_range_estimate",
                },
            ),
            change(
                "course",
                ident("c", 1),
                {
                    "facility_id": ident("f", 1),
                    "name": None,
                    "physical_holes": 18,
                    "access": "public",
                    "nonmember_bookable": None,
                    "booking_conditions": "Public daily play; availability unknown.",
                },
            ),
            change(
                "course",
                ident("c", 2),
                {
                    "facility_id": ident("f", 1),
                    "name": "Private Nine",
                    "physical_holes": 9,
                    "access": "private",
                    "nonmember_bookable": False,
                    "booking_conditions": "Reciprocal affiliation only.",
                },
            ),
            change(
                "course",
                ident("c", 3),
                {
                    "facility_id": ident("f", 3),
                    "name": "Unknown",
                    "access": None,
                    "nonmember_bookable": None,
                },
            ),
            observation(
                1,
                observed_on=None,
                conflict=True,
                qualification="Exact dated source qualification; no present availability.",
            ),
            sources=[source],
        ),
        apply=True,
    )
    assert result["state"] == "applied", result
    return path


def state(path):
    with closing(native.connect(path)) as db:
        return list(db.iterdump())


def test_import_preview_apply_and_stale_row_conflict(db):
    payload = batch(
        "practice",
        typed(
            "practice_observation",
            1,
            facility_id=ident("f", 1),
            driving_range_available=None,
            driving_range_lighted=False,
            putting_green_count=2,
        ),
    )
    before = state(db)
    preview = native.apply_batch(db, payload)
    assert preview["state"] == "preview" and state(db) == before
    applied = native.apply_batch(db, payload, apply=True)
    assert applied["state"] == "applied" and applied["revision_after"] == 2
    after = state(db)
    assert native.apply_batch(db, payload, apply=True)["state"] == "conflicted"
    assert state(db) == after
    payload["changes"][0]["values"]["putting_green_count"] = 3
    assert native.apply_batch(db, payload, apply=True)["state"] == "conflicted"
    assert state(db) == after
    row = read.query_facilities(db)["facilities"][0]["optional"]["practice_observation"]
    assert row == []  # Sorted first is Antimeridian; no accidental inheritance.
    facility = next(
        x
        for x in read.query_facilities(db)["facilities"]
        if x["facility_id"] == ident("f", 1)
    )
    row = facility["optional"]["practice_observation"][0]
    assert (
        row["driving_range_available"] is None and row["driving_range_lighted"] is False
    )
    assert row["putting_green_count"] == 2 and type(row["putting_green_count"]) is int
    assert row["conflict"] is True and row["observed_on"] is None
    assert (
        row["source_license"] == "Scoped attribution"
        and row["source_attribution"] == "Operator"
    )
    assert (
        read.query_courses(db)["courses"][1]["optional"]["practice_observation"] == []
    )


@pytest.mark.parametrize(
    "table,field,value",
    [
        ("practice_observation", "putting_green_count", True),
        ("practice_observation", "putting_green_count", "2"),
        ("amenity_observation", "restaurant_available", 1),
        ("price_observation", "amount_min", "25"),
        ("price_observation", "amount_min", float("inf")),
        ("price_observation", "amount_min", float("nan")),
        ("price_observation", "course_rating", 70.0),
        ("price_observation", "currency", "usd"),
    ],
)
def test_rejected_types_unknown_keys_and_constraints_rollback(db, table, field, value):
    before = state(db)
    payload = batch(
        "invalid", typed(table, 10, facility_id=ident("f", 1), **{field: value})
    )
    assert native.apply_batch(db, payload, apply=True)["state"] == "rejected"
    assert state(db) == before


def test_late_stale_guard_rolls_back_every_earlier_change_and_source(db):
    with closing(native.connect(db)) as con:
        row = dict(
            con.execute("SELECT * FROM course WHERE id=?", (ident("c", 1),)).fetchone()
        )
    first = typed(
        "service_observation", 1, course_id=ident("c", 1), club_rental_available=True
    )
    stale = change("course", ident("c", 1), {"name": "Stale rename"}, expected="0" * 64)
    before = state(db)
    report = native.apply_batch(db, batch("stale", first, stale), apply=True)
    assert report["state"] == "conflicted" and state(db) == before
    payload = batch(
        "guarded",
        change(
            "course", ident("c", 1), {"name": "Documented title"}, expected=digest(row)
        ),
    )
    report = native.apply_batch(db, payload, apply=True)
    assert report["changed_fields"] == 1
    assert "name" in native.summary(report)


def test_cross_subject_source_envelope_parent_moves_and_retained_promotions_reject(db):
    before = state(db)
    bad = typed(
        "amenity_observation",
        1,
        facility_id=ident("f", 1),
        course_id=ident("c", 1),
        restaurant_available=True,
    )
    assert (
        native.apply_batch(db, batch("double-target", bad), apply=True)["state"]
        == "rejected"
    )
    bad = typed(
        "amenity_observation", 2, facility_id=ident("f", 1), restaurant_available=True
    )
    bad["evidence"]["observation_id"] = ident("o", 2)
    assert (
        native.apply_batch(db, batch("wrong-envelope", bad), apply=True)["state"]
        == "rejected"
    )
    with closing(native.connect(db)) as con:
        course = dict(
            con.execute("SELECT * FROM course WHERE id=?", (ident("c", 1),)).fetchone()
        )
    move = change(
        "course", ident("c", 1), {"facility_id": ident("f", 2)}, expected=digest(course)
    )
    assert (
        native.apply_batch(db, batch("move", move), apply=True)["state"] == "rejected"
    )
    retained = observation(2, origin="retained_normalization")
    assert (
        native.apply_batch(db, batch("retained", retained), apply=True)["state"]
        == "rejected"
    )
    assert state(db) == before


def test_source_observation_immutable_even_when_unused(db):
    with closing(native.connect(db)) as con:
        old = dict(con.execute("SELECT * FROM source_observation").fetchone())
    payload = batch(
        "rewrite-source",
        change(
            "source_observation",
            old["id"],
            {"qualification": "Rewritten"},
            expected=digest(old),
        ),
    )
    assert native.apply_batch(db, payload, apply=True)["state"] == "rejected"


@pytest.mark.parametrize(
    "alias",
    [
        "https://OFFICIAL.example/golf/course#same",
        "https://official.example:443/golf/./course",
        "https://official.example/golf/%63ourse",
    ],
)
def test_existing_resource_cannot_be_registered_under_an_alias(db, alias):
    source = {
        "id": "different",
        "url": alias,
        "license": None,
        "attribution": None,
        "controls_reference": "reviewed",
    }
    before = state(db)
    report = native.apply_batch(
        db,
        batch(
            "resource-alias",
            typed(
                "service_observation", 3, course_id=ident("c", 1), caddie_available=True
            ),
            sources=[source],
        ),
        apply=True,
    )
    assert report["state"] == "rejected" and state(db) == before


def test_current_hold_rejects_already_permitted_source_and_same_id_clearance(db):
    with native.writer(db) as con:
        con.execute(
            "INSERT INTO source_hold_scope VALUES('h','resource',?,'{}')",
            (
                __import__(
                    "fairway.catalog_sources", fromlist=["resource_identity"]
                ).resource_identity("https://official.example/golf/course", hold=True),
            ),
        )
        con.execute("UPDATE source SET intake_policy='retained_only'")
        con.commit()
    with closing(native.connect(db)) as con:
        source = dict(con.execute("SELECT * FROM source").fetchone())
    with pytest.raises(ValueError, match="hold"):
        native.clear_source(
            db,
            "official",
            expected=digest(source),
            controls_reference="scoped-reviewed-controls",
            collected_on="2026-10-15",
        )
    report = native.apply_batch(
        db,
        batch(
            "held",
            typed(
                "service_observation", 4, course_id=ident("c", 1), caddie_available=True
            ),
        ),
        apply=True,
    )
    assert report["state"] == "rejected"


def test_native_read_preserves_unknown_booking_address_and_destination_scope(db):
    page = read.query_courses(db)
    assert page["schema"] == 5 and page["total"] == 3 and page["has_more"] is False
    one = next(x for x in page["courses"] if x["course_id"] == ident("c", 1))
    two = next(x for x in page["courses"] if x["course_id"] == ident("c", 2))
    unknown = next(x for x in page["courses"] if x["course_id"] == ident("c", 3))
    assert one["name"] is None and one["nonmember_bookable"] is None
    assert (
        one["plan_eligible"] is True
        and one["planning_basis"] == "accepted_public_play_with_qualification"
    )
    assert (
        two["plan_eligible"] is False
        and two["booking_conditions"] == "Reciprocal affiliation only."
    )
    assert unknown["access"] is None and unknown["plan_eligible"] is None
    assert one["arrival"] is None and one["destination_id"] == two[
        "destination_id"
    ] == ident("f", 1)
    assert (
        one["map_location"]["kind"] == "property_point"
        and one["address"]["purpose"] == "contact"
    )
    assert len(page["destinations"]) == 2
    assert read.query_courses(db, plan=True)["total"] == 1
    assert read.query_courses(db, access="unknown")["total"] == 1
    assert (
        next(
            x
            for x in read.query_facilities(db)["facilities"]
            if x["facility_id"] == ident("f", 2)
        )["course_count"]
        == 0
    )


@pytest.mark.parametrize(
    "kwargs,total",
    [
        ({"search": "100%"}, 1),
        ({"search": "%"}, 1),
        ({"search": "_"}, 0),
        ({"search": "' OR 1=1 --"}, 0),
        ({"bbox": [-1, 179, 1, -179]}, 1),
        ({"center": [40, -88], "radius_km": 0}, 1),
        ({"access": "unknown"}, 3),
    ],
)
def test_parameterized_literal_and_spatial_facility_filters(db, kwargs, total):
    assert read.query_facilities(db, **kwargs)["total"] == total


@pytest.mark.parametrize(
    "kwargs",
    [
        {"search": "\x00anything"},
        {"search": "\x00"},
        {"limit": True},
        {"offset": -1},
        {"center": [True, 0], "radius_km": 10},
        {"bbox": [-91, 0, 10, 20]},
        {"holes": True},
    ],
)
def test_invalid_query_boundaries_reject(db, kwargs):
    with pytest.raises(ValueError):
        read.query_facilities(db, **kwargs)


def test_read_is_one_snapshot_including_count_children_and_revision(db, monkeypatch):
    with sqlite3.connect(db) as con:
        con.execute("PRAGMA journal_mode=WAL")
    real = read.connect
    written = False

    class SnapshotRace:
        def __init__(self, con):
            self.con = con

        def __getattr__(self, name):
            return getattr(self.con, name)

        def execute(self, sql, args=()):
            nonlocal written
            result = self.con.execute(sql, args)
            if sql.startswith("SELECT count(*)") and not written:
                written = True
                with native.writer(db) as writer:
                    writer.execute(
                        "UPDATE facility SET name='Changed concurrently' WHERE id=?",
                        (ident("f", 1),),
                    )
                    writer.execute("UPDATE catalog_state SET revision=revision+1")
                    writer.commit()
            return result

    monkeypatch.setattr(read, "connect", lambda path: SnapshotRace(real(path)))
    first = read.query_facilities(db)
    assert first["revision"] == 1
    assert any(x["name"] == "Synthetic 100% Golf" for x in first["facilities"])
    assert read.query_facilities(db)["revision"] == 2


def test_whole_native5_snapshot_roundtrip_and_wrong_hash_cleanup(db, tmp_path):
    snap = tmp_path / "recovery.sql.gz"
    proof = native.snapshot(db, snap)
    restored = tmp_path / "restored.sqlite"
    assert native.restore(snap, restored, expected_sha256=proof["sha256"])[
        "integrity_check"
    ] == ["ok"]
    assert state(restored) == state(db)
    again = tmp_path / "again.sql.gz"
    assert (
        native.snapshot(restored, again) == proof
        and again.read_bytes() == snap.read_bytes()
    )
    rejected = tmp_path / "rejected.sqlite"
    with pytest.raises(ValueError, match="checksum"):
        native.restore(snap, rejected, expected_sha256="0" * 64)
    assert not rejected.exists()


def test_real_native4_is_explicitly_rejected_without_migration(db, tmp_path):
    from fairway.catalog_store import create

    old = tmp_path / "old.sqlite"
    create(old)
    before = old.read_bytes()
    with pytest.raises(ValueError, match="native5"):
        native.connect(old)
    assert old.read_bytes() == before


def test_importer_does_not_accept_raw_fact_groups(db):
    payload = batch(
        "raw", change("fact_group", ident("g", 1), {"payload": {"restaurant": True}})
    )
    assert native.apply_batch(db, payload, apply=True)["state"] == "rejected"


def test_partial_arrival_update_validates_the_merged_native_row(db):
    def guarded(values):
        with closing(native.connect(db)) as con:
            row = dict(
                con.execute(
                    "SELECT * FROM course WHERE id=?", (ident("c", 1),)
                ).fetchone()
            )
        return change("course", ident("c", 1), values, expected=digest(row))

    invalid = guarded(
        {
            "arrival_latitude": 40.1,
            "arrival_longitude": -88.1,
            "arrival_kind": "verified_entrance",
        }
    )
    assert (
        native.apply_batch(db, batch("no-reference", invalid), apply=True)["state"]
        == "rejected"
    )
    initial = guarded(
        {
            "arrival_latitude": 40.1,
            "arrival_longitude": -88.1,
            "arrival_kind": "verified_entrance",
            "arrival_reference": "Synthetic documented entrance",
        }
    )
    assert (
        native.apply_batch(db, batch("arrival", initial), apply=True)["state"]
        == "applied"
    )
    assert (
        native.apply_batch(
            db,
            batch("partial-arrival", guarded({"arrival_latitude": 40.2})),
            apply=True,
        )["state"]
        == "applied"
    )
    row = next(
        r for r in read.query_courses(db)["courses"] if r["course_id"] == ident("c", 1)
    )
    assert row["arrival"]["latitude"] == 40.2
    assert row["arrival"]["reference"] == "Synthetic documented entrance"
    assert row["map_location"]["latitude"] == 40.0


def test_existing_retained_source_requires_same_id_clearance_and_keeps_metadata(db):
    with native.writer(db) as con:
        con.execute("UPDATE source SET intake_policy='retained_only'")
        con.commit()
    with closing(native.connect(db)) as con:
        before = dict(con.execute("SELECT * FROM source").fetchone())
    payload = batch(
        "permitted-after-review",
        typed(
            "service_observation", 21, course_id=ident("c", 1), caddie_available=True
        ),
    )
    assert native.apply_batch(db, payload, apply=True)["state"] == "rejected"
    native.clear_source(
        db,
        "official",
        expected=digest(before),
        controls_reference="saved-controls.json#/exact-resource",
        collected_on="2026-10-15",
    )
    with closing(native.connect(db)) as con:
        after = dict(con.execute("SELECT * FROM source").fetchone())
    assert after == before | {"intake_policy": "permitted"}
    assert native.apply_batch(db, payload, apply=True)["state"] == "applied"


def test_single_writer_lock_prevents_parallel_intake(db):
    before = state(db)
    with (
        native.writer(db),
        pytest.raises(ValueError, match="another integration writer"),
    ):
        native.apply_batch(
            db,
            batch(
                "parallel",
                typed(
                    "service_observation",
                    22,
                    course_id=ident("c", 1),
                    caddie_available=True,
                ),
            ),
            apply=True,
        )
    assert state(db) == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"style": "par_3"},
        {"plan": True},
        {"round_holes": 18},
        {"include_review": False},
    ],
)
def test_course_only_filters_do_not_silently_change_facility_semantics(db, kwargs):
    with pytest.raises(ValueError):
        read.query_facilities(db, **kwargs)


def test_cli_uses_explicit_native5_path_and_defaults_to_rollback(db, tmp_path):
    source = tmp_path / "batch.json"
    report = tmp_path / "report.txt"
    source.write_text(
        json.dumps(
            batch(
                "cli-preview",
                typed(
                    "service_observation",
                    23,
                    course_id=ident("c", 1),
                    caddie_available=True,
                ),
            )
        )
    )
    before = state(db)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/native5_catalog.py",
            "--db",
            str(db),
            "import",
            str(source),
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["state"] == "preview"
    assert "not committed" in report.read_text()
    assert state(db) == before


def test_extra_envelope_keys_reject(db):
    payload = batch(
        "extra",
        typed(
            "amenity_observation",
            1,
            facility_id=ident("f", 1),
            restaurant_available=True,
        ),
    )
    payload["changes"][0]["supporting_evidence"] = [EVIDENCE.copy()]
    assert native.apply_batch(db, payload, apply=True)["state"] == "rejected"


@pytest.mark.parametrize(
    "mode", ["valid", "new-row", "wrong-observation-guard", "missing-review"]
)
def test_native_preservation_only_correction_keeps_null_claim_source_date_and_holds(
    db, mode
):
    with native.writer(db) as con:
        con.execute(
            "INSERT INTO fact_group(id,facility_id,module,payload,source_id,collected_on,status) VALUES(?,?,'amenities','{\"restaurant\":true}','official','2026-10-15','extracted')",
            (ident("g", 1), ident("f", 1)),
        )
        con.execute(
            "UPDATE source_observation SET source_id=NULL,collected_on=NULL,status='retained',origin='retained_input',retained_group_id=?",
            (ident("g", 1),),
        )
        con.execute(
            "INSERT INTO amenity_observation(id,observation_id,facility_id,restaurant_available) VALUES(?,?,?,0)",
            (ident("n", 41), ident("o", 1), ident("f", 1)),
        )
        con.execute("UPDATE source SET intake_policy='blocked'")
        con.execute(
            "INSERT INTO source_hold VALUES('official.example','Retained hold stays in force')"
        )
        con.commit()
    with closing(native.connect(db)) as con:
        obs = dict(con.execute("SELECT * FROM source_observation").fetchone())
        old = dict(con.execute("SELECT * FROM amenity_observation").fetchone())
        source = dict(con.execute("SELECT * FROM source").fetchone())
    proof = {
        "origin": "retained_normalization",
        "observation_id": obs["id"],
        "observation_digest": digest(obs),
        "review_reference": "saved-exact-retained-correction.json",
    }
    target = change(
        "amenity_observation",
        old["id"],
        {"restaurant_available": True},
        expected=digest(old),
        evidence=proof,
    )
    if mode == "new-row":
        target = typed(
            "amenity_observation",
            42,
            facility_id=ident("f", 1),
            restaurant_available=True,
        )
        target["evidence"] = proof
    elif mode == "wrong-observation-guard":
        proof["observation_digest"] = "0" * 64
    elif mode == "missing-review":
        proof["review_reference"] = ""
    before = state(db)
    result = native.apply_batch(db, batch("preservation-only", target), apply=True)
    if mode != "valid":
        assert result["state"] == "rejected" and state(db) == before
        return
    assert result["state"] == "applied"
    with closing(native.connect(db)) as con:
        assert dict(con.execute("SELECT * FROM source_observation").fetchone()) == obs
        assert dict(con.execute("SELECT * FROM source").fetchone()) == source
        assert (
            con.execute(
                "SELECT count(*) FROM citation WHERE entity_type='amenity_observation'"
            ).fetchone()[0]
            == 0
        )
        assert con.execute("SELECT count(*) FROM source_hold").fetchone()[0] == 1
        assert native.check(con)["foreign_key_check"] == []


@pytest.mark.parametrize(
    "evidence",
    [
        {},
        {"observation_id": ident("o", 1), "unexpected": True},
        {"origin": "retained_normalization"},
    ],
)
def test_malformed_typed_evidence_rejects_cleanly(db, evidence):
    item = typed(
        "service_observation", 51, course_id=ident("c", 1), caddie_available=True
    )
    item["evidence"] = evidence
    assert (
        native.apply_batch(db, batch("malformed-evidence", item), apply=True)["state"]
        == "rejected"
    )
