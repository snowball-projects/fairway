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


def test_missing_progress_prevents_publication_instead_of_inventing_status(tmp_path):
    root = tmp_path / "source"
    (root / "data").mkdir(parents=True)
    (root / "data/public-courses.json").write_text(
        '{"facilities":[],"county_checklist":[]}'
    )
    output = tmp_path / "output"
    with pytest.raises(FileNotFoundError):
        publisher.publish(root, output)
    assert not output.exists()
