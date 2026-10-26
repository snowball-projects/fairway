"""Complete public transport builds preserve bounded price notation and unknowns."""

import copy
import gzip
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from fairway.catalog_native_export import _public

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "notation_pages", ROOT / "scripts/build_pages.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)
CASES = json.loads(
    (
        ROOT / "tests/fixtures/native5-ui/public-boundary-legacy-decisions.json"
    ).read_text()
)["complete_transport_fixture"]["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_complete_notation_transport_build_and_unknowns(tmp_path, case):
    value = json.loads((ROOT / "tests/fixtures/native5-ui/transport.json").read_bytes())
    changed = []

    def update(item):
        if isinstance(item, list):
            for child in item:
                update(child)
        elif isinstance(item, dict):
            if item.get("id") == "n-00000000-0000-4000-8000-000000000004":
                item.update(
                    observation_id="o-00000000-0000-4000-8000-000000000991",
                    historical=True,
                    billing_basis=None,
                    currency=None,
                    quantity=None,
                )
                item[case["field"]] = case["text"]
                changed.append(item)
            for child in item.values():
                update(child)

    update(value)
    assert changed
    before = copy.deepcopy(value)
    accept = case["accept"]
    if accept:
        _public(value)
    else:
        with pytest.raises(ValueError):
            _public(value)
    raw = json.dumps(value, ensure_ascii=False).encode()
    packed = gzip.compress(raw, mtime=0)
    source = tmp_path / "source"
    data = source / "data/catalog-release"
    data.mkdir(parents=True)
    manifest = {
        k: value[k]
        for k in ("format_version", "schema", "revision", "catalog_release_key")
    }
    manifest["counts"] = {
        k: len(value[k]) for k in ("facilities", "courses", "destinations")
    }
    manifest["files"] = {
        name: {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
        for name, body in (("catalog.json", raw), ("catalog.json.gz", packed))
    }
    (data / "manifest.json").write_text(json.dumps(manifest))
    (data / "catalog.json.gz").write_bytes(packed)
    shutil.copytree(ROOT / "src/fairway/static", source / "src/fairway/static")
    shutil.copyfile(
        ROOT / "data/map-boundaries.json", source / "data/map-boundaries.json"
    )
    out = tmp_path / "site"
    if accept:
        assert pages.build(source, out, "b" * 40)["assets"] == 36
        assert "Data credits" in (out / "credits.html").read_text()
        assert (
            out / ("data/native-catalog-" + hashlib.sha256(raw).hexdigest() + ".json")
        ).read_bytes() == raw
        assert case["text"].encode() in raw
        assert all(
            r["billing_basis"] is r["currency"] is r["quantity"] is None
            for r in changed
        )
    else:
        with pytest.raises(ValueError):
            pages.build(source, out, "b" * 40)
        assert not out.exists()
    assert value == before
