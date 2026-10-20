"""Multi/partial retained identities guard complete baseline course inventory."""

import pytest
from test_retained_single_course_inventory import batch, ident, proposal, rows
from test_retained_single_course_inventory import db as single_db

from fairway import catalog_native as n
from fairway import catalog_native_read as read
from fairway.catalog_sources import retained_holds


@pytest.fixture
def db(tmp_path):
    path = single_db.__wrapped__(tmp_path)
    with n.writer(path) as d:
        d.execute("UPDATE facility SET physical_holes=27 WHERE id=?", (ident("f", 1),))
        d.execute(
            "UPDATE note SET text=? WHERE id='note1'",
            (
                "Accepted unnamed championship18 and separate Great 28 nine. Exact individual unknowns stay unknown; no arithmetic course split.",
            ),
        )
        d.commit()
    return path


def course(db, number, name, holes, facility=1):
    c = proposal(db, facility, named=False)
    c["id"] = ident("c", number)
    c["values"].update(name=name, physical_holes=holes)
    with n.connect(db) as d:
        c["evidence"]["course_inventory_digests"] = {
            r["id"]: n.digest(dict(r))
            for r in d.execute(
                "SELECT * FROM course WHERE facility_id=?", (ident("f", facility),)
            )
        }
    return c


def seed_course(db):
    with n.writer(db) as d:
        d.execute(
            "INSERT INTO course(id,facility_id,name,physical_holes) VALUES(?,?,?,?)",
            (ident("c", 99), ident("f", 1), "Already linked nine", 9),
        )
        d.commit()


@pytest.mark.parametrize(
    "identities",
    [
        [(None, 18), (None, 9)],
        [(None, 18), ("Great 28", 9)],
        [(None, None), ("Par 3", 9)],
        [("Crooked Cat", None), ("Panther Lake", None), ("Tooth", 9)],
        [(None, 9), (None, 9), (None, 9), (None, 3)],
    ],
)
def test_multi_identities_preview_apply_read_and_stale_guard_preserve_other_tables(
    db, identities
):
    changes = [
        course(db, i, name, holes) for i, (name, holes) in enumerate(identities, 10)
    ]
    b = batch(*changes)
    original = rows(db)
    assert n.apply_batch(db, b)["state"] == "preview" and rows(db) == original
    r = n.apply_batch(db, b, apply=True)
    assert r["state"] == "applied", r
    assert len(r["added"]) == len(changes) and not r["updated"]
    final = rows(db)
    for t in original:
        if t not in {"course", "citation", "catalog_state"}:
            assert final[t] == original[t], t
    stored = {r["id"]: r for r in final["course"]}
    for c in changes:
        row = stored[c["id"]]
        assert (
            row["name"] == c["values"]["name"]
            and row["physical_holes"] == c["values"]["physical_holes"]
        )
        assert all(
            row[k] is None
            for k in ["access", "nonmember_bookable", "style", "arrival_latitude"]
        )
    assert all(
        e["collected_on"] is None and e["entity_type"] == "course"
        for e in final["citation"]
    )
    assert (
        n.apply_batch(db, b, apply=True)["state"] == "conflicted" and rows(db) == final
    )
    assert len(read.query_courses(db, limit=100)["courses"]) == len(changes)


def test_missing_course_can_join_guarded_partial_inventory(db):
    seed_course(db)
    c = course(db, 10, None, 18)
    old = rows(db)
    r = n.apply_batch(db, batch(c), apply=True)
    assert r["state"] == "applied", r
    final = rows(db)
    assert old["course"][0] in final["course"] and len(final["course"]) == 2


@pytest.mark.parametrize(
    "mutation", ["omit", "stale", "extra", "not-object", "other-subject"]
)
def test_full_baseline_inventory_guard_rejects_omitted_stale_or_foreign_rows(
    db, mutation
):
    seed_course(db)
    c = course(db, 10, "Actual second course", 18)
    guard = c["evidence"]["course_inventory_digests"]
    if mutation == "omit":
        guard.clear()
    elif mutation == "stale":
        guard[ident("c", 99)] = "0" * 64
    elif mutation == "extra":
        guard[ident("c", 100)] = "0" * 64
    elif mutation == "not-object":
        c["evidence"]["course_inventory_digests"] = []
    else:
        c["values"]["facility_id"] = ident("f", 2)
    old = rows(db)
    assert (
        n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
        and rows(db) == old
    )


def test_second_add_cannot_declare_first_staged_add_as_preexisting(db):
    a, b = course(db, 10, None, 18), course(db, 11, "Great 28", 9)
    b["evidence"]["course_inventory_digests"] = {a["id"]: "0" * 64}
    old = rows(db)
    assert (
        n.apply_batch(db, batch(a, b), apply=True)["state"] == "rejected"
        and rows(db) == old
    )


def test_baseline_course_update_is_not_hidden_as_a_staged_addition(db):
    seed_course(db)
    with n.writer(db) as d:
        d.execute("UPDATE source SET intake_policy='permitted' WHERE id='retained'")
        d.commit()
    c = course(db, 10, None, 18)
    old = rows(db)
    update = {
        "entity": "course",
        "id": ident("c", 99),
        "expected": n.digest(old["course"][0]),
        "values": {"name": "Changed before retained addition"},
        "evidence": {
            "source_id": "retained",
            "collected_on": "2026-10-16",
            "status": "extracted",
        },
    }
    r = n.apply_batch(db, batch(update, c), apply=True)
    assert r[
        "state"
    ] == "rejected" and "complete pre-batch retained course inventory guard" in str(
        r
    ), r
    assert rows(db) == old


@pytest.mark.parametrize(
    "problem", ["blocked", "held", "stale-source", "missing-support", "bad-note"]
)
def test_source_or_note_failure_rolls_back_full_multi_batch(db, problem):
    if problem == "blocked":
        with n.writer(db) as d:
            d.execute("UPDATE source SET intake_policy='blocked' WHERE id='retained'")
            d.commit()
    if problem == "held":
        with n.writer(db) as d:
            d.executemany(
                "INSERT INTO source_hold_scope VALUES(?,?,?,?)",
                retained_holds(
                    {
                        "url": "https://owner.example/golf",
                        "reason": "exact resource hold",
                    }
                ),
            )
            d.commit()
    a, b = course(db, 10, None, 18), course(db, 11, "Great 28", 9)
    if problem == "stale-source":
        b["evidence"]["source_digests"]["retained"] = "0" * 64
    if problem == "missing-support":
        b["evidence"]["support_indexes"] = [1]
    if problem == "bad-note":
        b["evidence"]["note_digests"]["note1"] = "0" * 64
    old = rows(db)
    assert (
        n.apply_batch(db, batch(a, b), apply=True)["state"] == "rejected"
        and rows(db) == old
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("access", "public"),
        ("nonmember_bookable", True),
        ("style", "regulation"),
        ("arrival_latitude", 40.0),
        ("identity_status", "component"),
        ("game_kind", "obstacle_minigolf"),
        ("operating_status", "open"),
    ],
)
def test_multi_identity_cannot_promote_unrelated_fields(db, field, value):
    c = course(db, 10, None, 18)
    c["values"][field] = value
    old = rows(db)
    assert (
        n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
        and rows(db) == old
    )


@pytest.mark.parametrize("holes", [True, 0, -1, 9.5])
def test_holes_remain_positive_integer_or_unknown(db, holes):
    c = course(db, 10, None, holes)
    old = rows(db)
    assert (
        n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
        and rows(db) == old
    )


def test_no_existing_row_update_or_user_supplied_staging_context(db):
    seed_course(db)
    c = course(db, 99, None, 18)
    old = rows(db)
    c["expected"] = n.digest(old["course"][0])
    assert n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
    c = course(db, 10, None, 18)
    c["evidence"]["staged_courses"] = [ident("c", 99)]
    assert (
        n.apply_batch(db, batch(c), apply=True)["state"] == "rejected"
        and rows(db) == old
    )


@pytest.mark.parametrize(
    "position, refreshed",
    [(0, False), (0, True), (1, False), (1, True), (2, False), (2, True)],
)
def test_same_true_prebatch_inventory_is_required_before_between_and_after_additions(
    db, position, refreshed
):
    seed_course(db)
    with n.writer(db) as d:
        d.execute("UPDATE source SET intake_policy='permitted' WHERE id='retained'")
        d.commit()
    first, second = course(db, 10, None, 18), course(db, 11, "Great 28", 9)
    original = rows(db)
    existing = original["course"][0]
    changed = existing | {"name": "Interleaved guarded ordinary update"}
    update = {
        "entity": "course",
        "id": existing["id"],
        "expected": n.digest(existing),
        "values": {"name": changed["name"]},
        "evidence": {
            "source_id": "retained",
            "collected_on": "2026-10-16",
            "status": "extracted",
        },
    }
    if refreshed:
        # Updating caller guards cannot redefine the true pre-batch snapshot.
        if position == 0:
            first["evidence"]["course_inventory_digests"] = {
                existing["id"]: n.digest(changed)
            }
        second["evidence"]["course_inventory_digests"] = {
            existing["id"]: n.digest(changed)
        }
    changes = [first, second]
    changes.insert(position, update)
    r = n.apply_batch(db, batch(*changes), apply=True)
    assert r["state"] == "rejected", r
    assert rows(db) == original


def test_guarded_course_update_at_unrelated_facility_is_not_a_global_ban(db):
    seed_course(db)
    with n.writer(db) as d:
        d.execute("UPDATE source SET intake_policy='permitted' WHERE id='retained'")
        d.execute(
            "INSERT INTO course(id,facility_id,name,physical_holes) VALUES(?,?,?,?)",
            (ident("c", 98), ident("f", 2), "Separate facility course", 18),
        )
        d.commit()
    c = course(db, 10, None, 18)
    old = rows(db)
    separate = next(r for r in old["course"] if r["id"] == ident("c", 98))
    update = {
        "entity": "course",
        "id": separate["id"],
        "expected": n.digest(separate),
        "values": {"name": "Explicit separately sourced name"},
        "evidence": {
            "source_id": "retained",
            "collected_on": "2026-10-16",
            "status": "extracted",
        },
    }
    r = n.apply_batch(db, batch(c, update), apply=True)
    assert r["state"] == "applied", r
    current = rows(db)
    assert next(x for x in current["course"] if x["id"] == ident("c", 99)) == next(
        x for x in old["course"] if x["id"] == ident("c", 99)
    )
