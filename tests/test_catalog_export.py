"""Static publication must preserve native unknowns and reject moving inputs."""

import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest
from catalog_fixture import db as base_db
from catalog_fixture import identifier

from fairway import catalog_export as export
from fairway import catalog_store as store


@pytest.fixture
def db(tmp_path):
    return base_db.__wrapped__(tmp_path)


def test_export_preserves_empty_facilities_unknowns_and_shared_targets(db, tmp_path):
    before = export.file_digest(db)
    output = tmp_path / "generated"
    manifest = export.export_native_transport(
        db, output, expected_sha256=before, revision=0
    )
    value = json.loads((output / "catalog.json").read_bytes())
    assert value["facilities"] == store.query_facilities(db)["facilities"]
    assert value["courses"] == store.query_courses(db)["courses"]
    assert value["destinations"] == store.query_courses(db)["destinations"]
    assert len(value["facilities"]) == 3 and len(value["courses"]) == 3
    unknown = next(c for c in value["courses"] if c["course_id"] == identifier("c", 3))
    assert unknown["name"] is None and unknown["nonmember_bookable"] is None
    assert unknown["arrival"] is None and unknown["round_options"] == []
    assert not any(c["facility_id"] == identifier("f", 2) for c in value["courses"])
    siblings = [c for c in value["courses"] if c["facility_id"] == identifier("f", 1)]
    assert len(siblings) == 2 and len({c["destination_id"] for c in siblings}) == 1
    assert manifest["catalog_release_key"] == before == export.file_digest(db)
    assert (
        gzip.decompress((output / "catalog.json.gz").read_bytes())
        == (output / "catalog.json").read_bytes()
    )
    assert manifest["files"]["catalog.json"]["sha256"] == export.file_digest(
        output / "catalog.json"
    )


def test_export_public_provenance_omits_private_control_documents(db, tmp_path):
    with store.writer(db) as con:
        con.execute("INSERT INTO note VALUES ('n1','Accepted dated qualification.')")
        con.execute(
            "INSERT INTO retained_evidence VALUES (?,?)",
            (
                identifier("f", 1),
                store.encoded(
                    {
                        "listed_sources": ["retained"],
                        "notes": {"access": ["n1"], "location": None},
                        "support": [
                            {
                                "fields": ["access"],
                                "source": "retained",
                                "observed_on": None,
                            }
                        ],
                    }
                ),
            ),
        )
        con.execute(
            "INSERT INTO retained_document VALUES ('private-proof','\"/home/nas/private-capture\"')"
        )
        con.execute(
            "INSERT INTO source_license(payload) VALUES (?)",
            (
                store.encoded(
                    {
                        "license": "CC-BY-SA-3.0",
                        "policy_url": "https://city.example/license",
                        "scope": "City-owned content only",
                        "controls_reference": "/home/nas/private-controls.json",
                    }
                ),
            ),
        )
        con.commit()
    value = export.build_native_transport(
        db, expected_sha256=export.file_digest(db), revision=0
    )
    provenance = value["provenance"]["retained"][0]
    assert provenance["support"][0]["source_url"] == "https://retained.example/course"
    assert provenance["support"][0]["observed_on"] is None
    assert provenance["notes"]["access"] == ["Accepted dated qualification."]
    assert provenance["notes"]["location"] is None
    assert provenance["support"][0]["notes"] is None
    assert "private-capture" not in store.encoded(value)
    assert value["source_licenses"] == [
        {
            "license": "CC-BY-SA-3.0",
            "policy_url": "https://city.example/license",
            "scope": "City-owned content only",
        }
    ]
    assert "private-controls" not in store.encoded(value)


@pytest.mark.parametrize("boundary", ["hash", "revision", "sidecar"])
def test_export_rejects_unbound_or_open_inputs_without_output(db, tmp_path, boundary):
    checksum, revision = export.file_digest(db), 0
    if boundary == "hash":
        checksum = "0" * 64
    elif boundary == "revision":
        revision = 1
    else:
        db.with_name(db.name + "-wal").write_bytes(b"not a closed release")
    output = tmp_path / "rejected"
    with pytest.raises(ValueError):
        export.export_native_transport(
            db, output, expected_sha256=checksum, revision=revision
        )
    assert not output.exists()


def test_same_revision_changed_binary_during_export_is_rejected(
    db, tmp_path, monkeypatch
):
    original = export.query_courses

    def racing_read(*args, **kwargs):
        page = original(*args, **kwargs)
        with store.writer(db) as con:
            con.execute(
                "UPDATE facility SET name='Changed release' WHERE id=?",
                (identifier("f", 1),),
            )
            con.commit()
        return page

    monkeypatch.setattr(export, "query_courses", racing_read)
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="checksum differs"):
        export.export_native_transport(
            db, output, expected_sha256=export.file_digest(db), revision=0
        )
    assert not output.exists()


def test_export_is_reproducible_and_refuses_existing_output(db, tmp_path):
    checksum = export.file_digest(db)
    for folder in ("one", "two"):
        export.export_native_transport(
            db, tmp_path / folder, expected_sha256=checksum, revision=0
        )
    for name in ("catalog.json", "catalog.json.gz", "manifest.json"):
        assert (tmp_path / "one" / name).read_bytes() == (
            tmp_path / "two" / name
        ).read_bytes()
    with pytest.raises(ValueError, match="must not already exist"):
        export.export_native_transport(
            db, tmp_path / "one", expected_sha256=checksum, revision=0
        )


def test_catalog_commands_require_explicit_database_instead_of_old_checkpoint():
    script = Path(__file__).resolve().parents[1] / "scripts/sqlite_catalog.py"
    result = subprocess.run(
        [sys.executable, str(script), "check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "--db" in result.stderr
