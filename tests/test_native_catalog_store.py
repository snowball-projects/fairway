"""Meaningful local migration, transaction and query regressions without network."""

import copy
import json

import pytest

from fairway import catalog_store as store


def identifier(prefix, number):
    return f"{prefix}-00000000-0000-4000-8000-{number:012d}"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "catalog.sqlite"
    store.create(path)
    with store.writer(path) as connection:
        connection.execute(
            "INSERT INTO source VALUES ('operator','https://operator.example/course',NULL,NULL,'permitted')"
        )
        connection.execute(
            "INSERT INTO source VALUES ('retained','https://retained.example/course',NULL,NULL,'retained_only')"
        )
        store.put(
            connection,
            "facility",
            {
                "id": identifier("f", 1),
                "name": "Two courses",
                "physical_holes": 36,
                "inventory_complete": True,
                "latitude": 40.0,
                "longitude": -90.0,
                "location_kind": "property_point",
                "address_text": "1 Shared Street",
            },
        )
        for i, access, name in [(1, "public", "North"), (2, "private", "South")]:
            store.put(
                connection,
                "course",
                {
                    "id": identifier("c", i),
                    "facility_id": identifier("f", 1),
                    "name": name,
                    "physical_holes": 18,
                    "access": access,
                },
            )
        store.put(
            connection,
            "facility",
            {
                "id": identifier("f", 2),
                "name": "Unknown inventory",
                "physical_holes": 72,
                "inventory_complete": False,
            },
        )
        store.put(
            connection,
            "facility",
            {
                "id": identifier("f", 3),
                "name": "Documented 27",
                "physical_holes": 27,
                "inventory_complete": True,
                "latitude": 40.0,
                "longitude": 179.9,
                "location_kind": "address_range_estimate",
            },
        )
        store.put(
            connection,
            "course",
            {
                "id": identifier("c", 3),
                "facility_id": identifier("f", 3),
                "name": None,
                "physical_holes": 27,
                "access": "unknown",
            },
        )
        connection.commit()
    return path


def change(path, entity="course", number=1, values=None):
    with store.connect(path, readonly=True) as connection:
        before = store.row(connection, entity, identifier(store.PREFIX[entity], number))
    return {
        "entity": entity,
        "id": identifier(store.PREFIX[entity], number),
        "expected": store.digest(before) if before else None,
        "values": values or {"nonmember_bookable": True},
        "evidence": {
            "source_id": "operator",
            "collected_on": "2026-10-14",
            "status": "extracted",
        },
    }


def batch(*changes):
    return {"batch_id": "pilot-01", "sources": [], "changes": list(changes)}


def test_preview_atomic_apply_idempotence_and_changed_batch(db):
    proposal = batch(change(db))
    assert store.apply_batch(db, proposal)["state"] == "preview"
    assert all(
        c["nonmember_bookable"] is None
        for c in store.query_courses(db, plan=True)["courses"]
    )
    result = store.apply_batch(db, proposal, apply=True)
    assert result["state"] == "applied" and result["distinct_facilities"] == 1
    assert (
        store.query_courses(db, plan=True)["courses"][0]["nonmember_bookable"] is True
    )
    assert store.apply_batch(db, proposal, apply=True)["state"] == "already_applied"
    proposal["changes"][0]["values"]["nonmember_bookable"] = False
    with pytest.raises(ValueError, match="reused"):
        store.apply_batch(db, proposal, apply=True)


def test_stale_rows_roll_back_entire_batch(db):
    first = change(db, number=1)
    stale = change(db, number=2)
    stale["expected"] = "stale"
    report = store.apply_batch(db, batch(first, stale), apply=True)
    assert report["state"] == "conflicted"
    assert all(
        c["nonmember_bookable"] is None
        for c in store.query_courses(db, plan=True)["courses"]
    )
    with store.connect(db, readonly=True) as connection:
        assert (
            connection.execute("SELECT count(*) FROM import_batch").fetchone()[0] == 0
        )
        assert (
            connection.execute("SELECT count(*) FROM intake_evidence").fetchone()[0]
            == 0
        )


def test_new_duplicate_identity_and_source_are_rolled_back(db):
    proposal = change(
        db,
        entity="facility",
        number=4,
        values={
            "name": "Two courses",
            "physical_holes": 36,
            "address_text": "1 Shared Street",
        },
    )
    transport = batch(proposal)
    transport["sources"] = [
        {
            "id": "new",
            "url": "https://new.example/course",
            "license": None,
            "attribution": None,
            "controls_reference": "local permitted-control review",
        }
    ]
    report = store.apply_batch(db, transport, apply=True)
    assert (
        report["state"] == "conflicted"
        and "duplicate" in report["conflicts"][0]["reason"]
    )
    with store.connect(db, readonly=True) as connection:
        assert (
            connection.execute("SELECT count(*) FROM source WHERE id='new'").fetchone()[
                0
            ]
            == 0
        )
        assert store.row(connection, "facility", identifier("f", 4)) is None


@pytest.mark.parametrize(
    "values",
    [
        {"physical_holes": 0},
        {"physical_holes": True},
        {"nonmember_bookable": 0},
        {"unexpected": "field"},
        {"style": "mini_golf"},
        {"arrival_latitude": 91},
        {"website": "javascript:alert(1)"},
    ],
)
def test_basic_validation_and_unknown_not_zero(db, values):
    assert (
        store.apply_batch(db, batch(change(db, values=values)), apply=True)["state"]
        == "rejected"
    )
    assert store.check(store.connect(db, readonly=True))["integrity_check"] == ["ok"]


def test_foreign_references_and_parent_moves_refused(db):
    new = change(
        db, number=4, values={"facility_id": identifier("f", 999), "physical_holes": 18}
    )
    assert store.apply_batch(db, batch(new), apply=True)["state"] == "rejected"
    move = change(db, values={"facility_id": identifier("f", 2)})
    assert store.apply_batch(db, batch(move), apply=True)["state"] == "rejected"


def test_retained_sources_and_holds_cannot_be_reused(db):
    proposal = batch(change(db))
    proposal["changes"][0]["evidence"]["source_id"] = "retained"
    assert store.apply_batch(db, proposal, apply=True)["state"] == "rejected"
    with store.writer(db) as connection:
        connection.execute(
            "INSERT INTO source_hold VALUES ('blocked.example','publisher hold')"
        )
        connection.commit()
    proposal = batch(change(db))
    proposal["sources"] = [
        {
            "id": "bypass",
            "url": "https://www.blocked.example/alternate",
            "license": None,
            "attribution": None,
            "controls_reference": "not a permission bypass",
        }
    ]
    assert store.apply_batch(db, proposal, apply=True)["state"] == "rejected"
    with store.connect(db, readonly=True) as connection:
        source = dict(
            connection.execute("SELECT * FROM source WHERE id='retained'").fetchone()
        )
    result = store.clear_source(
        db,
        "retained",
        store.digest(source),
        "exact scoped current controls",
        "2026-10-14",
    )
    assert result["url"] == source["url"]
    proposal = batch(change(db))
    proposal["changes"][0]["evidence"]["source_id"] = "retained"
    assert store.apply_batch(db, proposal, apply=True)["state"] == "applied"


def test_optional_price_dates_basis_and_preliminary_provenance(db):
    proposal = change(
        db,
        entity="fact_group",
        number=1,
        values={
            "course_id": identifier("c", 1),
            "module": "prices",
            "payload": {
                "amount": 0,
                "currency": "USD",
                "basis": "green_fee_18_nonmember",
            },
            "observed_on": "2026-10-13",
        },
    )
    result = store.apply_batch(db, batch(proposal), apply=True)
    assert result["state"] == "applied"
    with store.connect(db, readonly=True) as connection:
        fact = store.row(connection, "fact_group", proposal["id"])
        assert (
            fact["status"] == "extracted"
            and fact["collected_on"] == "2026-10-14"
            and fact["observed_on"] == "2026-10-13"
        )
        assert json.loads(fact["payload"])["amount"] == 0
    for missing in ("observed_on", "payload"):
        bad = copy.deepcopy(proposal)
        bad["id"] = identifier("g", 2)
        bad["values"].pop(missing)
        assert (
            store.apply_batch(
                db,
                {"batch_id": "bad-" + missing, "sources": [], "changes": [bad]},
                apply=True,
            )["state"]
            == "rejected"
        )


def test_all_access_course_cards_shared_pins_and_no_synthetic_courses(db):
    result = store.query_courses(db)
    assert len(result["courses"]) == 3 and result["total"] == 3
    north, south = [
        c for c in result["courses"] if c["facility_id"] == identifier("f", 1)
    ]
    assert {north["access"], south["access"]} == {"public", "private"}
    assert north["course_id"] != south["course_id"]
    assert north["destination_id"] == south["destination_id"] == identifier("f", 1)
    assert (
        north["arrival"] is None and north["map_location"]["kind"] == "property_point"
    )
    assert len(result["destinations"]) == 2
    assert not store.query_courses(db, round_holes=27)["courses"]
    assert store.query_courses(db, holes=27)["courses"][0]["name"] is None
    assert all(
        c["nonmember_bookable"] is None
        for c in store.query_courses(db, plan=True)["courses"]
    )
    assert not store.query_courses(db, include_review=False)["courses"]


def test_spatial_bbox_distance_antimeridian_and_pagination(db):
    assert len(store.query_courses(db, bbox=[39, -91, 41, -89])["courses"]) == 2
    assert len(store.query_courses(db, center=[40, -90], radius_km=1)["courses"]) == 2
    assert len(store.query_courses(db, bbox=[39, 170, 41, -170])["courses"]) == 1
    assert (
        len(store.query_courses(db, center=[40, -179.9], radius_km=30)["courses"]) == 1
    )
    pages = [store.query_courses(db, limit=1, offset=n) for n in range(3)]
    assert pages[0]["has_more"] and not pages[-1]["has_more"]
    assert len({p["courses"][0]["course_id"] for p in pages}) == 3
    assert {p["revision"] for p in pages} == {0}
    assert {p["total"] for p in pages} == {3}
    with pytest.raises(ValueError):
        store.query_courses(db, limit=0)


def test_complete_inventory_rejects_inconsistent_physical_update(db):
    assert (
        store.apply_batch(
            db, batch(change(db, values={"physical_holes": 9})), apply=True
        )["state"]
        == "rejected"
    )
    assert len(store.query_courses(db, holes=18)["courses"]) == 2


def test_one_writer_and_portable_snapshot_round_trip(db, tmp_path):
    with store.writer(db), pytest.raises(ValueError, match="writer"):
        store.apply_batch(db, batch(change(db)), apply=True)
    first, second = tmp_path / "first.sql.gz", tmp_path / "second.sql.gz"
    assert store.snapshot(db, first) == store.snapshot(db, second)
    restored = tmp_path / "restored.sqlite"
    store.restore(first, restored)
    assert store.query_courses(db) == store.query_courses(restored)
    with store.connect(restored, readonly=True) as connection:
        assert store.check(connection) == {
            "integrity_check": ["ok"],
            "foreign_key_check": [],
        }
    with pytest.raises(FileExistsError):
        store.restore(first, restored)


def test_course_address_suppression_and_read_transaction(db, monkeypatch):
    real = store.connect
    traces = []

    def recording(path, **kwargs):
        connection = real(path, **kwargs)
        connection.set_trace_callback(traces.append)
        return connection

    monkeypatch.setattr(store, "connect", recording)
    assert store.query_courses(db)["courses"][-1]["address"]["scope"] == "facility"
    assert "BEGIN" in traces
    assert traces.index("BEGIN") < next(
        i for i, s in enumerate(traces) if s.startswith("SELECT count(*) FROM (")
    )
    assert (
        store.apply_batch(
            db, batch(change(db, values={"address_mode": "suppress"})), apply=True
        )["state"]
        == "applied"
    )
    assert (
        next(
            c
            for c in store.query_courses(db)["courses"]
            if c["course_id"] == identifier("c", 1)
        )["address"]
        is None
    )


def test_documented_round_components_tees_and_aliases_do_not_mint_cards(db):
    changes = [
        change(
            db,
            entity="component",
            number=1,
            values={
                "course_id": identifier("c", 3),
                "name": "Published loop",
                "physical_holes": 9,
            },
        ),
        change(
            db,
            entity="round_option",
            number=1,
            values={
                "course_id": identifier("c", 3),
                "name": "Published repeat nine",
                "round_holes": 18,
            },
        ),
        change(
            db,
            entity="round_component",
            number=1,
            values={
                "round_id": identifier("r", 1),
                "component_id": identifier("p", 1),
                "ordinal": 0,
                "repetitions": 2,
            },
        ),
        change(
            db,
            entity="tee_set",
            number=1,
            values={
                "round_id": identifier("r", 1),
                "name": "Forward",
                "yardage": 4200,
                "yardage_unit": "yards",
                "par": 68,
                "difficulty_rating": 62.4,
                "slope": 102,
                "rated_category": "women",
            },
        ),
        change(
            db,
            entity="alias",
            number=1,
            values={"course_id": identifier("c", 3), "name": "Operator short name"},
        ),
    ]
    report = store.apply_batch(db, batch(*changes), apply=True)
    assert report["state"] == "applied" and report["distinct_facilities"] == 1
    result = store.query_courses(db, round_holes=18)
    assert len(result["courses"]) == 1 and result["courses"][0]["physical_holes"] == 27
    assert len(store.query_courses(db)["courses"]) == 3
    with store.connect(db, readonly=True) as connection:
        assert store.check(connection)["foreign_key_check"] == []
    bad = change(
        db,
        entity="tee_set",
        number=2,
        values={
            "course_id": identifier("c", 1),
            "round_id": identifier("r", 1),
            "name": "Wrong course",
        },
    )
    assert (
        store.apply_batch(
            db, {"batch_id": "bad-tee", "sources": [], "changes": [bad]}, apply=True
        )["state"]
        == "rejected"
    )


def test_retained_normalization_preserves_null_provenance_without_source_clearance(db):
    with store.writer(db) as connection:
        connection.execute(
            "INSERT INTO note VALUES ('old-note','Accepted members-only condition.')"
        )
        connection.execute(
            "INSERT INTO retained_evidence VALUES (?,?)",
            (
                identifier("f", 1),
                store.encoded(
                    {
                        "notes": {"access": ["old-note"]},
                        "support": [
                            {"fields": ["courses"], "source": None, "observed_on": None}
                        ],
                    }
                ),
            ),
        )
        connection.commit()
    proposal = change(
        db,
        values={
            "nonmember_bookable": False,
            "booking_conditions": "Accepted members-only condition.",
        },
    )
    proposal["evidence"] = {
        "origin": "retained_normalization",
        "facility_id": identifier("f", 1),
        "note_ids": ["old-note"],
        "support_indexes": [0],
    }
    result = store.apply_batch(db, batch(proposal), apply=True)
    assert result["state"] == "applied"
    with store.connect(db, readonly=True) as connection:
        saved = dict(connection.execute("SELECT * FROM intake_evidence").fetchone())
        assert saved["source_id"] is None and saved["collected_on"] is None
        assert (
            json.loads(saved["payload"])["original_support"][0]["observed_on"] is None
        )
        assert (
            connection.execute(
                "SELECT intake_policy FROM source WHERE id='retained'"
            ).fetchone()[0]
            == "retained_only"
        )
    assert not store.query_courses(db, plan=True)["courses"]
    bad = copy.deepcopy(proposal)
    bad["id"] = identifier("c", 2)
    bad["expected"] = change(db, number=2)["expected"]
    bad["evidence"]["note_ids"] = ["invented-note"]
    assert (
        store.apply_batch(
            db,
            {"batch_id": "bad-retained", "sources": [], "changes": [bad]},
            apply=True,
        )["state"]
        == "rejected"
    )


def test_reciprocal_private_play_is_not_ordinary_nonmember_eligibility(db):
    condition = "Reciprocal guests must belong to another private club and arrange play through their golf professional; ordinary public access is excluded."
    update = change(
        db,
        number=2,
        values={
            "access": "private",
            "nonmember_bookable": False,
            "booking_conditions": condition,
        },
    )
    assert store.apply_batch(db, batch(update), apply=True)["state"] == "applied"
    assert identifier("c", 2) not in {
        c["course_id"] for c in store.query_courses(db, plan=True)["courses"]
    }
    private = store.query_courses(db, access="private")["courses"]
    assert len(private) == 1 and private[0]["course_id"] == identifier("c", 2)
    assert private[0]["booking_conditions"] == condition
    assert (
        private[0]["nonmember_bookable"] is False
        and private[0]["plan_eligible"] is False
    )
    restricted = change(db, number=2, values={"access": "restricted"})
    assert (
        store.apply_batch(
            db,
            {
                "batch_id": "restricted-reciprocal",
                "sources": [],
                "changes": [restricted],
            },
            apply=True,
        )["state"]
        == "applied"
    )
    result = store.query_courses(db, access="restricted")["courses"]
    assert len(result) == 1 and result[0]["booking_conditions"] == condition
    assert store.query_courses(db, access="restricted", plan=True)["total"] == 0
