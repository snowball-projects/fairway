"""Explicit field boundaries and concrete privacy threats; no golf prose parser."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from test_catalog_native5 import db as base_db
from test_catalog_native5 import ident
from test_catalog_native5_export import seed_typed
from test_public_price_scan import pages

from fairway import catalog_native as native
from fairway import catalog_native_export as export


@pytest.fixture
def db(tmp_path):
    return base_db.__wrapped__(tmp_path)


FIXTURES = Path(__file__).parent / "fixtures/native5-ui"
FIXTURE_ROOT = FIXTURES
CREDENTIAL_DECISIONS = {
    c["name"]: c["accept"]
    for c in json.loads(
        (FIXTURE_ROOT / "public-boundary-conservative-decisions.json").read_text()
    )
}


def privacy_cases(rows):
    return [
        dict(c, accept=CREDENTIAL_DECISIONS.get(c["name"], c["accept"])) for c in rows
    ]


CASES = json.loads((FIXTURES / "public-boundary.json").read_text()) + json.loads(
    (FIXTURES / "public-boundary-credential-path.json").read_text()
)
CASES += json.loads((FIXTURES / "public-boundary-raw-url-controls.json").read_text())
CASES += json.loads((FIXTURE_ROOT / "public-boundary-scheme-userinfo.json").read_text())
CASES = privacy_cases(
    CASES
    + json.loads((FIXTURE_ROOT / "public-boundary-credential-syntax.json").read_text())
)
ACTUAL = json.loads((FIXTURES / "public-boundary-802.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_explicit_public_boundary_across_python_validators(case):
    for validate in (export._public, pages.public_projection):
        value = copy.deepcopy(case["value"])
        before = copy.deepcopy(value)
        if case["accept"]:
            validate(value)
        else:
            with pytest.raises(ValueError):
                validate(value)
        assert value == before


def test_all_original_normative_fixtures_are_retained_byte_exact():
    ledger = json.loads(
        (FIXTURES / "public-boundary-legacy-decisions.json").read_text()
    )
    for name, expected in ledger["fixtures"].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == expected
    assert (
        hashlib.sha256(
            (FIXTURES / ledger["complete_transport_fixture"]["name"]).read_bytes()
        ).hexdigest()
        == ledger["complete_transport_fixture"]["sha256"]
    )
    assert len(ledger["cases"]) == 508
    assert sum(c["accept"] != c["original_accept"] for c in ledger["cases"]) == 123


@pytest.mark.parametrize(
    "case", ACTUAL["occurrences"], ids=lambda c: c["id"] + "-" + c["field"]
)
def test_all_sixteen_actual_802_occurrences_preserve_full_typed_row(case):
    assert case["context"][case["field"]] == case["text"]
    before = copy.deepcopy(case["context"])
    # Both the original absolute DTO location and a compact canonical projection.
    export._public(case["text"], _path=tuple(case["path"]))
    value = {"facilities": [{"optional": {"price_observation": [case["context"]]}}]}
    export._public(value)
    pages.public_projection(value)
    assert value["facilities"][0]["optional"]["price_observation"][0] == before


def test_private_license_controls_and_note_bodies_stay_sqlite_only(db):
    secret = "/unusual-secret-root/proof.json"
    payload = {
        "license": "CC BY-SA 4.0",
        "source_url": "https://example.test/fees/",
        "attribution": "Operator",
        "controls_reference": secret,
        "capture_path": secret,
        "local_path": secret,
    }
    with native.writer(db) as con:
        con.execute(
            "INSERT INTO source_license(payload) VALUES(?)", (json.dumps(payload),)
        )
        con.execute("INSERT INTO note VALUES('private-body',?)", (secret,))
        con.commit()
    before = db.read_bytes()
    value = export.build_transport(
        db, expected_sha256=hashlib.sha256(before).hexdigest(), revision=1
    )
    assert value["source_licenses"] == [
        {
            k: v
            for k, v in payload.items()
            if k in {"license", "source_url", "attribution"}
        }
    ]
    assert value["provenance"]["notes"] == [{"id": "private-body"}]
    assert secret not in json.dumps(value)
    with native.connect(db) as con:
        assert (
            json.loads(con.execute("SELECT payload FROM source_license").fetchone()[0])
            == payload
        )
        assert con.execute("SELECT text FROM note").fetchone()[0] == secret
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown": "innocent"},
        {"license": {"raw": "innocent"}},
        {"access_token": "innocent"},
    ],
)
def test_unknown_license_material_rejects_before_any_release_artifact(
    db, tmp_path, payload
):
    with native.writer(db) as con:
        con.execute(
            "INSERT INTO source_license(payload) VALUES(?)", (json.dumps(payload),)
        )
        con.commit()
    before = db.read_bytes()
    out = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        export.export_transport(
            db, out, expected_sha256=hashlib.sha256(before).hexdigest(), revision=1
        )
    assert not out.exists() and db.read_bytes() == before


@pytest.mark.parametrize(
    "text",
    [
        "Private copy of 2025 RATES is at /2025 RATES.",
        "Local file named 2024 FEES was saved at /2024 FEES.",
        "Evidence directory 2023 SCANS is located at /2023 SCANS.",
    ],
)
def test_actual_native_export_rejects_private_declaration_with_arbitrary_root(
    db, tmp_path, text
):
    seed_typed(db)
    with native.writer(db) as con:
        con.execute(
            "UPDATE price_observation SET conditions=? WHERE id=?",
            (text, ident("n", 4)),
        )
        con.commit()
    before = db.read_bytes()
    out = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        export.export_transport(
            db, out, expected_sha256=hashlib.sha256(before).hexdigest(), revision=2
        )
    assert not out.exists() and db.read_bytes() == before


@pytest.mark.parametrize(
    "text,license_field,accept",
    [
        ("https://review-user:TEST_ONLY_PASSWORD@operator.example/fees", True, False),
        ("https://operator.example/fees?api_key=TEST_ONLY_KEY", True, False),
        ("https://operator.example/fees?access_token=TEST_ONLY_TOKEN", True, False),
        ("https://operator.example/fees?client_secret=TEST_ONLY_SECRET", True, False),
        ("https://operator.example/fees?%61pi%5fkey=TEST_ONLY_KEY", True, False),
        ("https://operator.example/fees?q=public&year=2026", True, True),
        ("https://operator.example/fees?key=x", True, True),
        ("Files kept in /tmp for review.", False, False),
        ("See /home, then continue.", False, False),
        ("See /unusual/evidence for details.", False, False),
        ("See /home-page for public information.", False, True),
        ("Fees/private/resort", False, True),
    ],
)
def test_real_native_url_credentials_and_path_terminators(
    db, tmp_path, text, license_field, accept
):
    with native.writer(db) as con:
        if license_field:
            con.execute(
                "INSERT INTO source_license(payload) VALUES(?)",
                (json.dumps({"source_url": text, "license": "CC BY-SA"}),),
            )
        else:
            con.execute(
                "UPDATE course SET booking_conditions=? WHERE id=?",
                (text, ident("c", 1)),
            )
        con.commit()
    before = db.read_bytes()
    out = tmp_path / "release"
    if accept:
        export.export_transport(
            db, out, expected_sha256=hashlib.sha256(before).hexdigest(), revision=1
        )
        result = json.loads((out / "catalog.json").read_bytes())
        assert text in str(result)
        pages.public_projection(result)
    else:
        with pytest.raises(ValueError):
            export.export_transport(
                db, out, expected_sha256=hashlib.sha256(before).hexdigest(), revision=1
            )
        assert not out.exists()
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "case",
    privacy_cases(
        json.loads((FIXTURES / "public-boundary-raw-url-controls.json").read_text())
        + json.loads((FIXTURES / "public-boundary-credential-syntax.json").read_text())
        + json.loads((FIXTURES / "public-boundary-scheme-userinfo.json").read_text())
    ),
    ids=lambda c: c["name"],
)
def test_raw_url_controls_never_hide_native_credential_output(db, tmp_path, case):
    with native.writer(db) as con:
        if case["target"] == "license":
            con.execute(
                "INSERT INTO source_license(payload) VALUES(?)",
                (json.dumps({"source_url": case["text"], "license": "CC BY-SA"}),),
            )
        else:
            column = "website" if case["target"] == "website" else "booking_conditions"
            con.execute(
                f"UPDATE course SET {column}=? WHERE id=?",
                (case["text"], ident("c", 1)),
            )
        con.commit()
    before = db.read_bytes()
    out = tmp_path / "release"
    if case["accept"]:
        export.export_transport(
            db, out, expected_sha256=hashlib.sha256(before).hexdigest(), revision=1
        )
        result = json.loads((out / "catalog.json").read_text())
        if case["target"] == "license":
            assert result["source_licenses"][0]["source_url"] == case["text"]
        else:
            assert any(
                c["website" if case["target"] == "website" else "booking_conditions"]
                == case["text"]
                for c in result["courses"]
            )
    else:
        with pytest.raises(ValueError):
            export.export_transport(
                db, out, expected_sha256=hashlib.sha256(before).hexdigest(), revision=1
            )
        assert not out.exists()
    assert db.read_bytes() == before
