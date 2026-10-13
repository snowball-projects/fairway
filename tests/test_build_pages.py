"""The Pages artifact stays local to its project path and independent of routing."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "pages_builder", ROOT / "scripts/build_pages.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


def test_pages_build_preserves_source_and_uses_fresh_publication(tmp_path):
    source = (ROOT / "data/catalog.json").read_bytes()
    ranking = (ROOT / "src/fairway/data/course-catalog.json").read_bytes()
    output = tmp_path / "fairway"
    result = pages.build(ROOT, output, "a" * 40)
    assert (ROOT / "data/catalog.json").read_bytes() == source
    assert (ROOT / "src/fairway/data/course-catalog.json").read_bytes() == ranking
    html = (output / "index.html").read_text()
    assert 'src="./app.js"' in html
    assert (output / "origin-rows.mjs").is_file()
    assert 'href="./data/public-courses.json"' in html
    assert f'content="{pages.CALCULATION_ORIGIN}"' in html
    assert "Content-Security-Policy" in html
    assert json.loads((output / "deployment.json").read_text())["commit"] == "a" * 40
    assert (
        json.loads((output / "research-map/publication.json").read_text())[
            "catalog_sha256"
        ]
        == result["catalog_sha256"]
    )
    assert not list(output.rglob("*.npz"))
    assert not (output / ".env").exists()
    assert (
        "../data/public-courses.json"
        in (output / "research-map/index.html").read_text()
    )
    assert (output / ".nojekyll").exists()
    with pytest.raises(ValueError, match="new or empty"):
        pages.build(ROOT, output, "b" * 40)
