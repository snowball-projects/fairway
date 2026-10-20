"""Accepted inventory recovery uses native batches without source clearance."""

import copy
import json

import pytest

from fairway import catalog_native as n
from fairway import catalog_native_read as read
from fairway.catalog_sources import retained_holds


def ident(prefix, number):
    return f"{prefix}-00000000-0000-4000-8000-{number:012x}"


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "retained.sqlite"
    n.create(p)
    with n.writer(p) as d:
        d.execute(
            "INSERT INTO source VALUES('retained','https://owner.example/golf',NULL,NULL,'retained_only')"
        )
        for i in (1, 2):
            fid, nid = ident("f", i), "note" + str(i)
            d.execute(
                "INSERT INTO facility(id,name,state,physical_holes,access) VALUES(?,?,'IL',18,'public')",
                (fid, "Actual Course " + str(i)),
            )
            d.execute(
                "INSERT INTO note VALUES(?,?)",
                (
                    nid,
                    "Accepted explicit one18-hole golf course, separatepractice facilities.",
                ),
            )
            d.execute(
                "INSERT INTO retained_evidence VALUES(?,?)",
                (
                    fid,
                    n.encoded(
                        {
                            "listed_sources": ["retained"],
                            "notes": {"source": [nid]},
                            "support": [
                                {
                                    "fields": ["physical_holes"],
                                    "source": "retained",
                                    "observed_on": "2026-10-12",
                                },
                                {
                                    "fields": ["notes.source"],
                                    "source": "retained",
                                    "observed_on": None,
                                    "note": [nid],
                                },
                            ],
                        }
                    ),
                ),
            )
        d.commit()
    return p


def proposal(db, number=1, *, named=True):
    with n.connect(db) as d:
        f = dict(
            d.execute(
                "SELECT * FROM facility WHERE id=?", (ident("f", number),)
            ).fetchone()
        )
        r = dict(
            d.execute(
                "SELECT * FROM retained_evidence WHERE facility_id=?", (f["id"],)
            ).fetchone()
        )
        s = dict(d.execute("SELECT * FROM source WHERE id='retained'").fetchone())
        note = dict(
            d.execute(
                "SELECT * FROM note WHERE id=?", ("note" + str(number),)
            ).fetchone()
        )
    return {
        "entity": "course",
        "id": ident("c", number),
        "expected": None,
        "values": {
            "facility_id": f["id"],
            "name": f["name"] if named else None,
            "physical_holes": 18,
            "identity_status": "operator_defined",
            "game_kind": "golf",
            "address_mode": "inherit",
        },
        "evidence": {
            "origin": "retained_normalization",
            "facility_id": f["id"],
            "facility_digest": n.digest(f),
            "retained_evidence_digest": n.digest(r),
            "source_digests": {s["id"]: n.digest(s)},
            "note_digests": {note["id"]: n.digest(note)},
            "support_indexes": [0, 1],
            "review_reference": "reviewed-inventory.json#/course-" + str(number),
        },
    }


def batch(*items):
    return {"batch_id": "retained-identity-test", "sources": [], "changes": list(items)}


def rows(db):
    with n.connect(db) as d:
        return {
            r[0]: [dict(x) for x in d.execute("SELECT * FROM " + r[0])]
            for r in d.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        }


@pytest.mark.parametrize("named", [True, False])
def test_preview_apply_read_and_stale_guard_preserve_accepted_envelope(db, named):
    original = rows(db)
    b = batch(proposal(db, named=named))
    assert n.apply_batch(db, b)["state"] == "preview"
    assert rows(db) == original
    r = n.apply_batch(db, b, apply=True)
    assert r["state"] == "applied" and len(r["added"]) == 1 and r["updated"] == []
    final = rows(db)
    assert final["source"] == original["source"]  # never cleared
    assert final["retained_evidence"] == original["retained_evidence"]
    assert (
        final["facility"] == original["facility"] and final["note"] == original["note"]
    )
    e = final["citation"][0]
    assert (
        e["entity_type"] == "course"
        and e["source_id"] == "retained"
        and e["collected_on"] is None
    )
    c = final["course"][0]
    assert c["name"] == ("Actual Course 1" if named else None)
    assert (
        c["access"] is None
        and c["nonmember_bookable"] is None
        and c["arrival_latitude"] is None
    )
    assert (
        n.apply_batch(db, b, apply=True)["state"] == "conflicted" and rows(db) == final
    )
    result = read.query_courses(db, limit=10)
    assert len(result["courses"]) == 1 and result["courses"][0]["name"] == c["name"]
    bad = copy.deepcopy(b)
    bad["changes"][0]["values"]["name"] = None if named else "Actual Course 1"
    assert n.apply_batch(db, bad, apply=True)["state"] == "conflicted"
    assert rows(db) == final


@pytest.mark.parametrize(
    "guard", ["facility_digest", "retained_evidence_digest", "source_digests"]
)
def test_stale_guard_rejects_and_rolls_back_batched_additions(db, guard):
    good, bad = proposal(db, 1), proposal(db, 2)
    bad["evidence"][guard] = (
        {"retained": "0" * 64} if guard == "source_digests" else "0" * 64
    )
    old = rows(db)
    assert n.apply_batch(db, batch(good, bad), apply=True)["state"] == "rejected"
    assert rows(db) == old


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "Invented Layout"),
        ("physical_holes", 9),
        ("access", "public"),
        ("nonmember_bookable", True),
        ("style", "regulation"),
        ("arrival_latitude", 40.0),
        ("booking_conditions", "Inherited public offer"),
    ],
)
def test_no_facility_total_split_or_unrelated_field_promotion(db, field, value):
    c = proposal(db)
    c["values"][field] = value
    old = rows(db)
    assert n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
    assert rows(db) == old


@pytest.mark.parametrize(
    "mutation",
    [
        "no-notes",
        "foreign-note",
        "wrong-note",
        "wrong-support",
        "no-hole-support",
        "no-review",
        "source-not-listed",
    ],
)
def test_complete_accepted_course_definition_binding_required(db, mutation):
    c = proposal(db)
    if mutation == "no-notes":
        c["evidence"]["note_digests"] = {}
    if mutation == "foreign-note":
        c["evidence"]["note_digests"] = {
            "note2": c["evidence"]["note_digests"]["note1"]
        }
    if mutation == "wrong-note":
        c["evidence"]["note_digests"]["note1"] = "0" * 64
    if mutation == "wrong-support":
        c["evidence"]["support_indexes"] = [False, 1]
    if mutation == "no-hole-support":
        c["evidence"]["support_indexes"] = [1]
    if mutation == "no-review":
        c["evidence"]["review_reference"] = ""
    if mutation == "source-not-listed":
        with n.writer(db) as d:
            r = dict(
                d.execute(
                    "SELECT * FROM retained_evidence WHERE facility_id=?",
                    (ident("f", 1),),
                ).fetchone()
            )
            p = json.loads(r["payload"])
            p["listed_sources"] = []
            r["payload"] = n.encoded(p)
            d.execute(
                "UPDATE retained_evidence SET payload=? WHERE facility_id=?",
                (r["payload"], r["facility_id"]),
            )
            d.commit()
        c["evidence"]["retained_evidence_digest"] = n.digest(r)
    old = rows(db)
    assert n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
    assert rows(db) == old


def test_existing_inventory_and_held_source_stay_protected(db):
    c = proposal(db)
    with n.writer(db) as d:
        d.executemany(
            "INSERT INTO source_hold_scope VALUES(?,?,?,?)",
            retained_holds(
                {"url": "https://owner.example/golf", "reason": "exact held resource"}
            ),
        )
        d.commit()
    old = rows(db)
    assert (
        n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
        and rows(db) == old
    )


def test_second_course_and_existing_row_cannot_use_single_course_path(db):
    c = proposal(db)
    assert n.apply_batch(db, batch(c), apply=True)["state"] == "applied"
    old = rows(db)
    another = copy.deepcopy(c)
    another["id"] = ident("c", 9)
    assert (
        n.apply_batch(db, batch(another) | {"batch_id": "second"}, apply=True)["state"]
        == "rejected"
    )
    changed = copy.deepcopy(c)
    changed["expected"] = n.digest(old["course"][0])
    changed["values"]["name"] = None
    assert (
        n.apply_batch(db, batch(changed) | {"batch_id": "update"}, apply=True)["state"]
        == "rejected"
    )
    assert rows(db) == old


def test_no_unreferenced_source_or_permission_change(db):
    c = proposal(db)
    c["evidence"] = {
        "source_id": "retained",
        "collected_on": "2026-10-15",
        "status": "extracted",
    }
    old = rows(db)
    assert n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
    assert rows(db) == old


@pytest.mark.parametrize(
    "shape",
    [
        "note-only-support",
        "physical-only-support",
        "unbound-note",
        "unknown-source",
        "mixed-unknown-source",
    ],
)
def test_known_retained_claims_do_not_need_invented_binding_fields_or_dates(db, shape):
    with n.writer(db) as d:
        r = dict(
            d.execute(
                "SELECT * FROM retained_evidence WHERE facility_id=?", (ident("f", 1),)
            ).fetchone()
        )
        p = json.loads(r["payload"])
        if shape == "note-only-support":
            p["support"] = p["support"][1:]
        if shape == "physical-only-support":
            p["support"] = p["support"][:1]
        if shape == "unbound-note":
            p["support"] = []
        if shape == "mixed-unknown-source":
            p["support"][1]["source"] = None
        if shape == "unknown-source":
            p["support"] = p["support"][1:]
            p["support"][0]["source"] = None
        d.execute(
            "UPDATE retained_evidence SET payload=? WHERE facility_id=?",
            (n.encoded(p), r["facility_id"]),
        )
        d.commit()
    c = proposal(db)
    c["evidence"]["support_indexes"] = list(range(len(p["support"])))
    if shape in ("unbound-note", "unknown-source"):
        c["evidence"]["source_digests"] = {}
    before = rows(db)
    result = n.apply_batch(db, batch(c), apply=True)
    assert result["state"] == "applied", result
    final = rows(db)
    e = final["citation"][0]
    assert e["source_id"] == ("retained" if shape == "note-only-support" else None)
    assert e["collected_on"] is None and final["source"] == before["source"]
    assert final["retained_evidence"] == before["retained_evidence"]


def test_known_held_binding_cannot_be_hidden_by_omitting_its_support(db):
    c = proposal(db)
    c["evidence"]["support_indexes"] = []
    c["evidence"]["source_digests"] = {}
    with n.writer(db) as d:
        d.executemany(
            "INSERT INTO source_hold_scope VALUES(?,?,?,?)",
            retained_holds({"url": "https://owner.example/golf", "reason": "held"}),
        )
        d.commit()
    old = rows(db)
    assert (
        n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
        and rows(db) == old
    )


def test_missing_subject_rejects_without_partial_transaction(db):
    c = proposal(db)
    del c["values"]["facility_id"]
    old = rows(db)
    assert n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
    assert rows(db) == old


def test_blocked_source_policy_rolls_back_valid_first_subject(db):
    with n.writer(db) as d:
        d.execute(
            "INSERT INTO source VALUES('blocked','https://blocked.example/golf',NULL,NULL,'blocked')"
        )
        r = json.loads(
            d.execute(
                "SELECT payload FROM retained_evidence WHERE facility_id=?",
                (ident("f", 2),),
            ).fetchone()[0]
        )
        r["listed_sources"] = ["blocked"]
        for support in r["support"]:
            support["source"] = "blocked"
        d.execute(
            "UPDATE retained_evidence SET payload=? WHERE facility_id=?",
            (n.encoded(r), ident("f", 2)),
        )
        d.commit()
    good, blocked = proposal(db, 1), proposal(db, 2)
    with n.connect(db) as d:
        source = dict(d.execute("SELECT * FROM source WHERE id='blocked'").fetchone())
    blocked["evidence"]["source_digests"] = {"blocked": n.digest(source)}
    original = rows(db)
    result = n.apply_batch(db, batch(good, blocked), apply=True)
    assert result["state"] == "rejected"
    assert "retained source is blocked" in str(result)
    assert rows(db) == original
