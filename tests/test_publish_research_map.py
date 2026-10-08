"""Verify publication uses only public snapshots and existing static serving."""

import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest

from fairway import app

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "publish_research_map", ROOT / "scripts/publish_research_map.py"
)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def test_publication_preserves_inputs_and_serves_under_existing_handler(
    tmp_path, monkeypatch
):
    before = {
        name: (ROOT / "data" / name).read_bytes()
        for name in ("public-courses.json", "research-progress.json")
    }
    result = publisher.publish(ROOT, tmp_path)
    for name, data in before.items():
        assert (ROOT / "data" / name).read_bytes() == data
        assert (tmp_path / "data" / name).read_bytes() == data
    assert result["catalog_sha256"] == sha256(before["public-courses.json"]).hexdigest()
    assert not (tmp_path / "research-map/README.md").exists()
    monkeypatch.setattr(app, "STATIC", tmp_path)
    responses = []
    body = b"".join(
        app.application(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/research-map/index.html"},
            lambda status, headers: responses.append((status, dict(headers))),
        )
    )
    assert responses[0][0] == "200 OK"
    assert b'href="/favicon.png"' in body
    assert "connect-src 'self'" in responses[0][1]["Content-Security-Policy"]
    responses.clear()
    body = b"".join(
        app.application(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/data/research-progress.json"},
            lambda status, headers: responses.append((status, dict(headers))),
        )
    )
    assert responses[0][0] == "200 OK"
    assert json.loads(body)["schema_version"] == 1


@pytest.mark.parametrize("status", [None, "not JSON", '{"schema_version":2}'])
def test_optional_status_failure_does_not_block_catalog_publication(tmp_path, status):
    root = tmp_path / "source"
    (root / "data").mkdir(parents=True)
    (root / "data/public-courses.json").write_text(
        '{"facilities":[],"county_checklist":[]}'
    )
    (root / "docs/research-map").mkdir(parents=True)
    for name in publisher.ASSETS:
        (root / "docs/research-map" / name).write_bytes(
            (ROOT / "docs/research-map" / name).read_bytes()
        )
    if status is not None:
        (root / "data/research-progress.json").write_text(status)
    output = tmp_path / "output"
    result = publisher.publish(root, output)
    assert result["progress_sha256"] is None
    assert (output / "data/public-courses.json").is_file()
    assert not (output / "data/research-progress.json").exists()


def test_optional_additions_log_is_published_unchanged_with_its_hash(tmp_path):
    root = tmp_path / "source"
    (root / "data").mkdir(parents=True)
    (root / "docs/research-map").mkdir(parents=True)
    (root / "data/public-courses.json").write_text(
        '{"facilities":[],"county_checklist":[]}'
    )
    (root / "data/research-progress.json").write_text('{"schema_version":1}')
    for name in publisher.ASSETS:
        (root / "docs/research-map" / name).write_bytes(
            (ROOT / "docs/research-map" / name).read_bytes()
        )
    log = {
        "schema_version": 1,
        "time_basis": "git_commit_time",
        "count_unit": "provisional_facility_entry",
        "history_complete_from": None,
        "batches": [],
    }
    body = json.dumps(log).encode()
    (root / "data/catalog-additions.json").write_bytes(body)
    output = tmp_path / "output"
    publisher.publish(root, output)
    assert (output / "data/catalog-additions.json").read_bytes() == body
    assert (root / "data/catalog-additions.json").read_bytes() == body
    manifest = json.loads((output / "research-map/publication.json").read_bytes())
    assert manifest["additions_sha256"] == sha256(body).hexdigest()
    assert (output / "research-map/refresh.mjs").is_file()
