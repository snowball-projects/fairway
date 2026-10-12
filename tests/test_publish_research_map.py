"""All public projections must come from the same reviewed source."""

import importlib.util
import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from fairway import app

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import catalog as foundation

spec = importlib.util.spec_from_file_location(
    "publisher", ROOT / "scripts/publish_research_map.py"
)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def test_publication_generates_consistent_consumers_and_serves_existing_handler(
    tmp_path, monkeypatch
):
    original = (ROOT / "data/catalog.json").read_bytes()
    result = publisher.publish(ROOT, tmp_path)
    assert (ROOT / "data/catalog.json").read_bytes() == original
    expected = foundation.exports(foundation.read())
    for name, value in expected.items():
        path = (
            ROOT / "src/fairway/data"
            if name == "course-catalog.json"
            else tmp_path / "data"
        ) / name
        assert json.loads(path.read_bytes()) == value
    catalog_bytes = (tmp_path / "data/public-courses.json").read_bytes()
    assert result["catalog_sha256"] == sha256(catalog_bytes).hexdigest()
    assert len(catalog_bytes) < len(original) / 2
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
    assert b'href="../favicon.png"' in body
    assert "connect-src 'self'" in responses[0][1]["Content-Security-Policy"]
    responses.clear()
    body = b"".join(
        app.application(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/data/catalog-metadata.json"},
            lambda status, headers: responses.append((status, dict(headers))),
        )
    )
    assert responses[0][0] == "200 OK"
    assert json.loads(body)["metadata"]["source_licenses"]


def test_invalid_canonical_source_fails_before_publication(tmp_path):
    root = tmp_path / "source"
    (root / "data").mkdir(parents=True)
    (root / "data/catalog.json").write_text('{"schema_version":2}')
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="schema"):
        publisher.publish(root, output)
    assert not output.exists()
