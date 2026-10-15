"""Typed release transport must expose honest scopes without raw fallback."""

import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from test_catalog_native5 import batch, change, ident, typed
from test_catalog_native5 import db as base_db

from fairway import catalog_native as native
from fairway import catalog_native_export as export
from fairway import catalog_native_read as read


def test_packaged_layout_is_the_exact_reviewed_proposal():
    assert hashlib.sha256(native.SCHEMA.read_bytes()).hexdigest() == (
        "ab852cff6180dba03c4d7f780b2aded18ea962ed0664808887698c9cd78a34c6"
    )


def test_pinned_synthetic_transport_has_explicit_version_and_no_raw_fallback():
    fixture = Path(__file__).parent / "fixtures/native5-production/transport.json"
    value = json.loads(fixture.read_text())
    assert value["format_version"] == 2
    assert value["schema"] == 5
    assert len(value["facilities"]) == 3
    assert len(value["courses"]) == 3
    assert any(row["access"] is None for row in value["courses"])
    export._public(value)


@pytest.mark.parametrize(
    "private_path",
    [
        "/var/tmp/fairway/private-controls.json",
        "/mnt/research/private-capture.html",
        "/opt/fairway/private-proof.json",
        "/etc/private-proof.json",
        "/private-proof.json",
        "D:\\Research\\private-proof.json",
        "D:/Research/private-proof.json",
        "\\\\server\\share\\private-proof.json",
        "FILE:///var/tmp/private-proof.json",
        "`/mnt/research/proof.html`",
        "Private capture:/var/tmp/private.json",
        "Private capture;/opt/proof.json",
        "«/srv/research/private-proof.json»",
        "///var/tmp/private-proof.json",
    ],
)
def test_private_paths_in_operational_text_reject_export(db, tmp_path, private_path):
    with native.writer(db) as con:
        con.execute(
            "UPDATE course SET location_note=? WHERE id=?",
            ("Private capture: " + private_path, ident("c", 1)),
        )
        con.commit()
    output = tmp_path / "must-not-publish"
    with pytest.raises(ValueError, match="local evidence path"):
        export.export_transport(
            db,
            output,
            expected_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),
            revision=1,
        )
    assert not output.exists()


def test_private_note_bodies_stay_sqlite_only_without_text_rewriting(db):
    note = (
        "Private capture: /mnt/research/proof.html; original source wording /rates.html"
    )
    with native.writer(db) as con:
        con.execute("INSERT INTO note VALUES('retained-private',?)", (note,))
        con.commit()
    value = export.build_transport(
        db, expected_sha256=hashlib.sha256(db.read_bytes()).hexdigest(), revision=1
    )
    assert value["provenance"]["notes"] == [{"id": "retained-private"}]
    assert note not in json.dumps(value)
    with native.connect(db) as con:
        assert con.execute("SELECT text FROM note").fetchone()[0] == note


def test_path_guard_preserves_normal_urls_and_operational_slash_text():
    export._public(
        {
            "qualification": "Range / chipping area; 9/18 holes",
            "url": "https://example.test/var/tmp/proof",
            "linked_qualification": "See HTTPS://example.test:8443/golf/?route=/course; ordinary 9/18 play",
            "actual_retained_tee_name": "Cinn./Quicks.",
            "actual_retained_discount": "Senior60+/junior17under discounts.",
            "actual_retained_rate_scope": "Weekend(Fri-Sun)/Holidays 08:00-15:00",
        }
    )
    with pytest.raises(ValueError, match="local evidence path"):
        export._public({"/mnt/private/proof.json": "key also stays private"})


@pytest.fixture
def db(tmp_path):
    return base_db.__wrapped__(tmp_path)


def seed_typed(db):
    payload = batch(
        "typed-scope-examples",
        change(
            "component",
            ident("p", 1),
            {
                "course_id": ident("c", 1),
                "name": "Documented North loop",
                "physical_holes": 9,
            },
        ),
        change(
            "round_option",
            ident("r", 1),
            {
                "facility_id": ident("f", 1),
                "name": "Documented paired 18",
                "round_holes": 18,
            },
        ),
        change(
            "round_component",
            ident("l", 1),
            {"round_id": ident("r", 1), "course_id": ident("c", 2), "ordinal": 0},
        ),
        change(
            "round_component",
            ident("l", 2),
            {"round_id": ident("r", 1), "component_id": ident("p", 1), "ordinal": 1},
        ),
        change(
            "tee_set",
            ident("t", 1),
            {
                "round_id": ident("r", 1),
                "name": "Blue",
                "yardage": None,
                "yardage_unit": None,
                "par": 71,
                "difficulty_rating": 70.1,
                "slope": 121,
                "rated_category": None,
            },
        ),
        typed(
            "amenity_observation",
            1,
            facility_id=ident("f", 1),
            restaurant_available=True,
        ),
        typed(
            "practice_observation",
            2,
            course_id=ident("c", 1),
            driving_range_available=None,
            driving_range_lighted=False,
            putting_green_count=2,
        ),
        typed(
            "physical_characteristics",
            3,
            component_id=ident("p", 1),
            greens_grass_name="Documented bentgrass",
        ),
        typed(
            "price_observation",
            4,
            round_id=ident("r", 1),
            fee_kind="green_fee",
            amount_kind="range",
            amount_min=25.0,
            amount_max=45.0,
            currency="USD",
            billing_basis="per_person",
            audience="adult",
            residency="nonresident",
            round_holes=18,
            weekday_mask=31,
            applies_on_holidays=False,
            cart_included=None,
            tax_included=None,
            historical=True,
            conditions="Dated weekdays only; affiliation and current availability unconfirmed.",
        ),
        typed(
            "policy_observation",
            5,
            course_id=ident("c", 2),
            ordinary_nonmember_allowed=False,
            club_affiliation_required=True,
            walk_in_play_allowed=None,
        ),
        typed(
            "architecture_event",
            6,
            component_id=ident("p", 1),
            event_kind="design",
            event_year=None,
        ),
        change(
            "design_party",
            ident("d", 1),
            {"name": "Synthetic Person", "party_kind": "person"},
        ),
        change(
            "design_party",
            ident("d", 2),
            {"name": "Synthetic Firm", "party_kind": "firm"},
        ),
        change(
            "architecture_credit",
            ident("k", 1),
            {"event_id": ident("n", 6), "party_id": ident("d", 1), "role": None},
            evidence={"observation_id": ident("o", 1)},
        ),
        change(
            "architecture_credit",
            ident("k", 2),
            {
                "event_id": ident("n", 6),
                "party_id": ident("d", 2),
                "role": "renovation",
            },
            evidence={"observation_id": ident("o", 1)},
        ),
    )
    result = native.apply_batch(db, payload, apply=True)
    assert result["state"] == "applied", result


def test_facility_course_component_round_scopes_and_unknowns(db):
    seed_typed(db)
    facility = next(
        r
        for r in read.query_facilities(db)["facilities"]
        if r["facility_id"] == ident("f", 1)
    )
    course = next(
        r for r in read.query_courses(db)["courses"] if r["course_id"] == ident("c", 1)
    )
    assert (
        facility["optional"]["amenity_observation"][0]["restaurant_available"] is True
    )
    assert course["optional"]["amenity_observation"] == []
    assert (
        course["optional"]["practice_observation"][0]["driving_range_available"] is None
    )
    part = course["components"][0]
    assert (
        part["optional"]["physical_characteristics"][0]["greens_grass_name"]
        == "Documented bentgrass"
    )
    event = part["optional"]["architecture_event"][0]
    assert event["event_year"] is None and len(event["credits"]) == 2
    assert event["credits"][0]["role"] is None
    assert course["optional"]["price_observation"] == []
    round_option = course["round_options"][0]
    assert len(round_option["members"]) == 2 and round_option["members"][0][
        "course_id"
    ] == ident("c", 2)
    assert (
        round_option["tee_sets"][0]["yardage"] is None
        and round_option["tee_sets"][0]["rated_category"] is None
    )
    price = round_option["optional"]["price_observation"][0]
    assert price["round_holes"] == 18 and price["billing_basis"] == "per_person"
    assert price["residency"] == "nonresident" and price["tax_included"] is None
    assert price["historical"] is True and price["conflict"] is True
    assert price["observed_on"] is None and price["effective_from"] is None
    assert read.query_courses(db, round_holes=18)["total"] == 2


def test_runtime_cannot_read_legacy_operational_payloads(db, monkeypatch):
    with native.writer(db) as con:
        con.execute(
            "INSERT INTO fact_group(id,facility_id,module,payload,source_id,collected_on,status) VALUES(?,?,'prices',?,'official','2026-10-15','extracted')",
            (
                ident("g", 1),
                ident("f", 1),
                '{"green_fee":99,"restaurant":true,"private_path":"/home/nas/secret"}',
            ),
        )
        con.commit()
    original = read.connect

    def forbid(path):
        con = original(path)

        def authorizer(action, table, *_):
            if action == sqlite3.SQLITE_READ and table in {
                "fact_group",
                "retained_evidence",
                "retained_document",
            }:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        con.set_authorizer(authorizer)
        return con

    monkeypatch.setattr(read, "connect", forbid)
    facility = next(
        r
        for r in read.query_facilities(db)["facilities"]
        if r["facility_id"] == ident("f", 1)
    )
    assert facility["optional"]["price_observation"] == []
    assert facility["optional"]["amenity_observation"] == []
    assert read.query_courses(db)["total"] == 3
    value = export.build_transport(
        db, expected_sha256=hashlib.sha256(db.read_bytes()).hexdigest(), revision=1
    )
    assert "fact_groups" not in json.dumps(
        value
    ) and "/home/nas/secret" not in json.dumps(value)


def test_typed_public_export_and_deterministic_recovery_files(db, tmp_path):
    seed_typed(db)
    checksum = hashlib.sha256(db.read_bytes()).hexdigest()
    output = tmp_path / "export"
    manifest = export.export_transport(db, output, expected_sha256=checksum, revision=2)
    body = (output / "catalog.json").read_bytes()
    value = json.loads(body)
    assert manifest["format_version"] == 2 and manifest["schema"] == 5
    assert value["catalog_release_key"] == checksum
    assert value["facilities"] == read.query_facilities(db)["facilities"]
    assert value["courses"] == read.query_courses(db)["courses"]
    assert len(value["relationships"]["round_component"]) == 2
    assert value["provenance"]["sources"][0]["attribution"] == "Operator"
    assert "intake_policy" not in json.dumps(value)
    assert "controls_reference" not in json.dumps(value)
    assert "retained_pointer" not in json.dumps(value)
    assert "fact_groups" not in json.dumps(value)
    assert gzip.decompress((output / "catalog.json.gz").read_bytes()) == body
    assert (
        hashlib.sha256(body).hexdigest() == manifest["files"]["catalog.json"]["sha256"]
    )
    other = tmp_path / "export-again"
    assert (
        export.export_transport(db, other, expected_sha256=checksum, revision=2)
        == manifest
    )
    assert (other / "catalog.json.gz").read_bytes() == (
        output / "catalog.json.gz"
    ).read_bytes()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == checksum


@pytest.mark.parametrize(
    "boundary",
    ["hash", "revision", "sidecar", "existing-output", "private-qualification"],
)
def test_rejected_export_creates_no_public_artifact(db, tmp_path, boundary):
    seed_typed(db)
    checksum = hashlib.sha256(db.read_bytes()).hexdigest()
    revision = 2
    output = tmp_path / "rejected"
    if boundary == "hash":
        checksum = "0" * 64
    elif boundary == "revision":
        revision += 1
    elif boundary == "sidecar":
        db.with_name(db.name + "-wal").write_bytes(b"unclosed")
    elif boundary == "existing-output":
        output.mkdir()
        (output / "sentinel").write_text("preserve")
    else:
        with native.writer(db) as con:
            con.execute(
                "UPDATE course SET location_note='/home/nas/private-capture' WHERE id=?",
                (ident("c", 1),),
            )
            con.commit()
        checksum = hashlib.sha256(db.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        export.export_transport(db, output, expected_sha256=checksum, revision=revision)
    if boundary == "existing-output":
        assert (output / "sentinel").read_text() == "preserve"
    else:
        assert not output.exists()


def test_export_file_move_failure_removes_only_its_new_output(
    db, tmp_path, monkeypatch
):
    output = tmp_path / "failed"

    def fail(*_):
        raise OSError("simulated disk error")

    monkeypatch.setattr(export.os, "replace", fail)
    with pytest.raises(OSError, match="disk error"):
        export.export_transport(
            db,
            output,
            expected_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),
            revision=1,
        )
    assert not output.exists()


def test_wrong_facility_qualified_prior_round_rejects_without_partial_commit(db):
    payload = batch(
        "cross-facility-prior",
        change(
            "round_option",
            ident("r", 99),
            {
                "facility_id": ident("f", 2),
                "name": "Different facility",
                "round_holes": 18,
            },
        ),
        typed(
            "price_observation",
            99,
            course_id=ident("c", 1),
            qualifying_prior_round_id=ident("r", 99),
            second_round_required=True,
        ),
    )
    before = db.read_bytes()
    assert native.apply_batch(db, payload, apply=True)["state"] == "rejected"
    assert db.read_bytes() == before


def test_quality_population_remains_deferred(db):
    payload = batch(
        "quality",
        typed(
            "quality_rating",
            1,
            course_id=ident("c", 1),
            issuer_name="Unapproved",
            score=4.0,
            scale_min=0.0,
            scale_max=5.0,
        ),
    )
    assert native.apply_batch(db, payload, apply=True)["state"] == "rejected"
    assert all(
        not r["optional"]["quality_rating"] for r in read.query_courses(db)["courses"]
    )
