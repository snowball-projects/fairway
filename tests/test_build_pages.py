"""Native publication binds immutable data and excludes private inputs."""

import importlib.util
import json
import re
import shutil
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "pages_builder", ROOT / "scripts/build_pages.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


def test_native_pages_are_reproducible_public_only_and_leave_source_unchanged(tmp_path):
    source = ROOT / "data/catalog-release/catalog.json.gz"
    before = source.read_bytes()
    ranking = (ROOT / "src/fairway/data/course-catalog.json").read_bytes()
    output = tmp_path / "one"
    one = pages.build(ROOT, output, "a" * 40)
    two = pages.build(ROOT, tmp_path / "two", "a" * 40)
    assert one == two
    manifest = json.loads((output / "data/catalog-release.json").read_text())
    item = manifest["files"]["catalog.json"]
    raw = (output / "data" / item["path"]).read_bytes()
    assert len(raw) == item["bytes"] and sha256(raw).hexdigest() == item["sha256"]
    assert one["counts"] == {"facilities": 7387, "courses": 3641, "destinations": 2144}
    html = (output / "index.html").read_text()
    assert 'src="./app.js"' in html and "Content-Security-Policy" in html
    assert "photon.komoot.io" in html and "onrender.com" not in html
    assert "data/catalog-release.json" in html and "not uniformly normalized" in html
    assert json.loads((output / "deployment.json").read_text())["commit"] == "a" * 40
    for name in [
        "catalog.mjs",
        "logical-plan.mjs",
        "assembly-plan.mjs",
        ".env",
        "tests",
        "research-map/publication.json",
    ]:
        assert not (output / name).exists()
    for suffix in ["*.sqlite", "*.sql", "*.gz", "*.npz"]:
        assert not list(output.rglob(suffix))
    assert (output / ".nojekyll").exists()
    assert 'href="../"' in (output / "research-map/index.html").read_text()
    assert source.read_bytes() == before
    assert (ROOT / "src/fairway/data/course-catalog.json").read_bytes() == ranking
    with pytest.raises(ValueError, match="new or empty"):
        pages.build(ROOT, output, "b" * 40)
    for module in output.glob("*.mjs"):
        for dependency in re.findall(r"from\s+[\"\'](\./[^\"\']+)", module.read_text()):
            assert (module.parent / dependency).is_file(), (module.name, dependency)
    for dependency in re.findall(
        r"from\s+[\"\'](\./[^\"\']+)", (output / "app.js").read_text()
    ):
        assert (output / dependency).is_file(), dependency


@pytest.mark.parametrize(
    "defect", ["compressed", "uncompressed-hash", "revision", "counts"]
)
def test_corrupt_artifact_fails_before_output(tmp_path, defect):
    root = tmp_path / "source"
    source = root / "data/catalog-release"
    shutil.copytree(ROOT / "data/catalog-release", source)
    manifest = json.loads((source / "manifest.json").read_text())
    if defect == "compressed":
        with (source / "catalog.json.gz").open("ab") as stream:
            stream.write(b"changed")
    elif defect == "uncompressed-hash":
        manifest["files"]["catalog.json"]["sha256"] = "0" * 64
    elif defect == "revision":
        manifest["revision"] += 1
    else:
        manifest["counts"]["courses"] += 1
    (source / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "rejected"
    with pytest.raises(ValueError):
        pages.build(root, output, "rejected")
    assert not output.exists()
