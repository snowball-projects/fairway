"""Retained notation cases under the prospective public/private field boundary."""

from copy import deepcopy

import pytest
from test_catalog_native5 import EVIDENCE, change, ident
from test_catalog_native5 import db as base_db
from test_catalog_native5_export import seed_typed

from fairway import catalog_native as native
from fairway import catalog_native_export as export


@pytest.fixture
def db(tmp_path):
    return base_db.__wrapped__(tmp_path)


def price(column, text, **extra):
    return {
        "id": "n-00000000-0000-4000-8000-000000000001",
        "observation_id": "ob-00000000-0000-4000-8000-000000000001",
        "fee_kind": "range_balls",
        "amount_kind": "exact",
        "amount_min": 6.22,
        "billing_basis": None,
        "currency": None,
        column: text,
        **extra,
    }


def public_price(row):
    export._public({"facilities": [{"optional": {"price_observation": [row]}}]})


@pytest.mark.parametrize(
    "text",
    [
        "1 token /30 balls",
        "2 token /60 balls",
        "3 token /90 balls",
        "4 vouchers /120 shots",
        "1.5 credits /12.5 units",
    ],
)
def test_complete_measure_ratios_are_literal_product_names(text):
    row = price("product_name", text)
    before = deepcopy(row)
    public_price(row)
    assert row == before


@pytest.mark.parametrize(
    "text",
    [
        "Page explicitly titled 2025 Rates and Info /2025 RATES. All prices marked historical.",
        "Published 2024 Fees and Info /2024 FEES. Effective dates unknown.",
        "A 2023 Summer Tariff /2023 SUMMER TARIFF; historical publication.",
    ],
)
def test_repeated_historical_headings_are_prose_without_date_inference(text):
    row = price(
        "qualification", text, historical=True, effective_from=None, effective_to=None
    )
    before = deepcopy(row)
    public_price(row)
    assert row == before


@pytest.mark.parametrize(
    "suffix",
    ["/private.json", ".json", "%2fproof", "?proof", "#proof", "\\proof", ";private"],
)
def test_retained_ratio_suffixes_are_not_interpreted_as_quantity_or_private_origin(
    suffix,
):
    row = price("product_name", "1 token /30 balls" + suffix)
    if suffix in {"/private.json", ";private"}:
        with pytest.raises(ValueError):
            public_price(row)
    else:
        before = deepcopy(row)
        public_price(row)
        assert row == before


@pytest.mark.parametrize(
    "text",
    [
        "/30 balls",
        "/30",
        "1 token /30 balls /mnt/private",
        "capture: 1 token /30 balls",
        "1 token //30 balls",
        "1 token /30 balls.json",
        "2025 Rates /2025 RATES/private",
        "2025 Rates /2025 RATES.json",
        "2025 Rates /2025 RATES%2fprivate",
        "2025 Rates /2025 RATES?private",
        "2025 Rates /2025 RATES#private",
        "2025 Rates /2025 RATES; /mnt/private",
        "2025 Rates; capture: /2025 RATES.",
        "2025 Rates /2024 RATES.",
        "/2025 RATES",
        "/2025",
        "/unknown-root",
        "/ea",
        "/mnt/private",
        "/home/nas/private",
        "/var/tmp/proof",
        "file:///tmp/proof",
        "C:\\private\\proof",
        "\\\\server\\private",
    ],
)
def test_retained_unknown_slashes_and_recognizable_private_artifacts(text):
    rejected = {
        "1 token /30 balls /mnt/private",
        "2025 Rates /2025 RATES/private",
        "2025 Rates /2025 RATES%2fprivate",
        "2025 Rates /2025 RATES; /mnt/private",
        "2025 Rates /2025 RATES?private",
        "2025 Rates /2025 RATES#private",
        "2025 Rates; capture: /2025 RATES.",
        "capture: 1 token /30 balls",
        "/mnt/private",
        "/home/nas/private",
        "/var/tmp/proof",
        "file:///tmp/proof",
        "C:\\private\\proof",
        "\\\\server\\private",
    }
    row = price("qualification", text, historical=True)
    if text in rejected:
        with pytest.raises(ValueError):
            public_price(row)
    else:
        before = deepcopy(row)
        public_price(row)
        assert row == before


@pytest.mark.parametrize(
    "column", ["qualification", "conditions", "location_note", "source_attribution"]
)
def test_retained_ratio_in_operational_versus_noncanonical_fields(column):
    row = price(column, "1 token /30 balls")
    if column in {"qualification", "conditions"}:
        public_price(row)
    else:
        with pytest.raises(ValueError):
            public_price(row)


@pytest.mark.parametrize("column", ["product_name", "conditions", "location_note"])
def test_retained_heading_uses_field_role_without_history_inference(column):
    row = price(column, "2025 Rates /2025 RATES.", historical=True)
    if column in {"product_name", "conditions"}:
        public_price(row)
    else:
        with pytest.raises(ValueError):
            public_price(row)


@pytest.mark.parametrize("historical", [None, False])
def test_unknown_or_false_history_does_not_authorize_heading(historical):
    with pytest.raises(ValueError):
        export._public(
            price("qualification", "2025 Rates /2025 RATES.", historical=historical)
        )


@pytest.mark.parametrize(
    "key",
    [
        "/30 balls",
        "/2025 RATES",
        "/ea",
        "controls_reference",
        "retained_pointer",
        "fact_groups",
    ],
)
def test_private_keys_or_provenance_never_receive_exceptions(key):
    row = price("product_name", "1 token /30 balls")
    row[key] = "private"
    with pytest.raises(ValueError):
        public_price(row)


@pytest.mark.parametrize(
    "row",
    [
        {"product_name": "1 token /30 balls"},
        {"qualification": "2025 Rates /2025 RATES.", "historical": True},
    ],
)
def test_unstructured_metadata_does_not_receive_price_exception(row):
    with pytest.raises(ValueError):
        export._public(row)


def test_export_preserves_numeric_slash_products_and_historical_qualification(db):
    import hashlib

    seed_typed(db)
    with native.writer(db) as con:
        con.execute(
            "UPDATE price_observation SET product_name=?,historical=1,billing_basis=NULL,quantity=NULL,currency=NULL WHERE id=?",
            ("1 token /30 balls", ident("n", 4)),
        )
        observation = dict(
            con.execute(
                "SELECT * FROM source_observation WHERE id=(SELECT observation_id FROM price_observation WHERE id=?)",
                (ident("n", 4),),
            ).fetchone()
        )
        observation.update(
            id=ident("o", 99),
            qualification="Page explicitly titled 2025 Rates and Info /2025 RATES. Historical.",
        )
        columns = list(observation)
        con.execute(
            "INSERT INTO source_observation("
            + ",".join(columns)
            + ") VALUES("
            + ",".join("?" for _ in columns)
            + ")",
            list(observation.values()),
        )
        con.execute(
            "UPDATE price_observation SET observation_id=? WHERE id=?",
            (observation["id"], ident("n", 4)),
        )
        con.commit()
    before = db.read_bytes()
    data = export.build_transport(
        db, expected_sha256=hashlib.sha256(before).hexdigest(), revision=2
    )
    found = []

    def walk(v):
        if isinstance(v, dict):
            if v.get("id") == ident("n", 4) and "product_name" in v:
                found.append(v)
            for child in v.values():
                walk(child)
        elif isinstance(v, list):
            for child in v:
                walk(child)

    walk(data)
    assert found
    assert all(
        r["product_name"] == "1 token /30 balls"
        and "/2025 RATES" in r["qualification"]
        and r["currency"] is r["quantity"] is r["billing_basis"] is None
        for r in found
    )
    assert db.read_bytes() == before


@pytest.mark.parametrize("prefix", ["source_licenses", "provenance", "relationships"])
def test_price_shaped_metadata_does_not_grant_itself_notation(prefix):
    row = price("product_name", "1 token /30 balls")
    with pytest.raises(ValueError):
        export._public({prefix: [{"optional": {"price_observation": [row]}}]})


@pytest.mark.parametrize(
    "key", ["access_token", "authorization", "credential", "capture_path"]
)
def test_credential_or_evidence_fields_are_never_reclassified_as_price_prose(key):
    with pytest.raises(ValueError):
        export._public({key: "2025 Rates /2025 RATES."})


@pytest.mark.parametrize(
    "field,text",
    [
        ("product_name", "1 token /30 balls/private.json"),
        ("product_name", "1 token /30 balls; /mnt/private.json"),
        ("qualification", "2025 Rates /2025 RATES.json"),
        ("qualification", "2025 Rates /2025 RATES. Evidence: /tmp/private.json"),
    ],
)
def test_actual_export_rejects_paths_and_leaves_no_output(db, tmp_path, field, text):
    import hashlib

    seed_typed(db)
    with native.writer(db) as con:
        if field == "product_name":
            con.execute(
                "UPDATE price_observation SET product_name=? WHERE id=?",
                (text, ident("n", 4)),
            )
        else:
            observation = dict(
                con.execute(
                    "SELECT * FROM source_observation WHERE id=(SELECT observation_id FROM price_observation WHERE id=?)",
                    (ident("n", 4),),
                ).fetchone()
            )
            observation.update(id=ident("o", 98), qualification=text)
            columns = list(observation)
            con.execute(
                "INSERT INTO source_observation("
                + ",".join(columns)
                + ") VALUES("
                + ",".join("?" for _ in columns)
                + ")",
                list(observation.values()),
            )
            con.execute(
                "UPDATE price_observation SET observation_id=?,historical=1 WHERE id=?",
                (observation["id"], ident("n", 4)),
            )
        con.commit()
    before = db.read_bytes()
    output = tmp_path / "must-not-export"
    if text == "2025 Rates /2025 RATES.json":
        result = export.build_transport(
            db, expected_sha256=hashlib.sha256(before).hexdigest(), revision=2
        )
        assert text in str(result)
    else:
        with pytest.raises(ValueError):
            export.export_transport(
                db,
                output,
                expected_sha256=hashlib.sha256(before).hexdigest(),
                revision=2,
            )
        assert not output.exists()
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "column,text,extra",
    [
        ("product_name", "1 token /30 balls", {}),
        ("qualification", "2025 Rates /2025 RATES.", {"historical": True}),
    ],
)
def test_license_payload_cannot_spoof_real_price_projection(
    db, tmp_path, column, text, extra
):
    import hashlib
    import json

    seed_typed(db)
    with native.writer(db) as con:
        payload = {
            "facilities": [
                {"optional": {"price_observation": [price(column, text, **extra)]}}
            ]
        }
        con.execute(
            "INSERT INTO source_license(payload) VALUES(?)", (json.dumps(payload),)
        )
        con.commit()
    output = tmp_path / "must-not-export"
    with pytest.raises(ValueError):
        export.export_transport(
            db,
            output,
            expected_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),
            revision=2,
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "text",
    [
        "Private copy of 2025 RATES is at /2025 RATES.",
        "Local file named 2024 FEES was saved at /2024 FEES.",
        "Evidence directory 2023 SCANS is located at /2023 SCANS.",
        "2025 RATES IS AT /2025 RATES.",
        "2025 Rates and Info was saved at /2025 RATES.",
        "2025 Rates with Info /2025 RATES.",
        "2025 Rates and lower case prose /2025 RATES.",
    ],
)
def test_retained_locator_cases_reject_explicit_private_origin(text):
    row = price("qualification", text, historical=True)
    if text.startswith(("Private copy", "Local file", "Evidence directory")):
        with pytest.raises(ValueError):
            public_price(row)
    else:
        before = deepcopy(row)
        public_price(row)
        assert row == before


def test_real_native_intake_with_explicit_local_root_must_fail_export(db, tmp_path):
    import hashlib

    seed_typed(db)
    text = "Private copy of 2025 RATES is at /2025 RATES."
    oid = ident("o", 991)
    result = native.apply_batch(
        db,
        {
            "batch_id": "independent-private-root-caption",
            "sources": [],
            "changes": [
                change(
                    "source_observation",
                    oid,
                    EVIDENCE
                    | {
                        "origin": "new_extraction",
                        "qualification": text,
                    },
                ),
                change(
                    "price_observation",
                    ident("n", 991),
                    {
                        "observation_id": oid,
                        "course_id": ident("c", 1),
                        "fee_kind": "green_fee",
                        "amount_kind": "exact",
                        "amount_min": 10,
                        "amount_max": 10,
                        "historical": True,
                    },
                    evidence={"observation_id": oid},
                ),
            ],
        },
        apply=True,
    )
    assert result["state"] == "applied"
    before = db.read_bytes()
    output = tmp_path / "private-root-must-not-export"
    with pytest.raises(ValueError):
        export.export_transport(
            db, output, expected_sha256=hashlib.sha256(before).hexdigest(), revision=3
        )
    assert db.read_bytes() == before and not output.exists()
