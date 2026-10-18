"""Replay every frozen notation fixture with explicit prospective role decisions."""

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
    "price_scan_pages", ROOT / "scripts/build_pages.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)
LEGACY = json.loads(
    (
        ROOT / "tests/fixtures/native5-ui/public-boundary-legacy-decisions.json"
    ).read_text()
)
DECISIONS = {(r["fixture"], r["name"]): r for r in LEGACY["cases"]}
CASES = [
    dict(case, accept=DECISIONS[(name, case["name"])]["accept"])
    for name in (
        "per-each-guard.json",
        "per-each-unicode-policy.json",
        "public-url-termination.json",
        "public-price-notation.json",
    )
    for case in json.loads((ROOT / "tests/fixtures/native5-ui" / name).read_text())
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_financial_scan_decisions_match_export_and_preserve_all_text(case):
    for validate in (_public, pages.public_projection):
        value = copy.deepcopy(case["value"])
        before = copy.deepcopy(value)
        if case["accept"]:
            validate(value)
        else:
            with pytest.raises(ValueError):
                validate(value)
        assert value == before


@pytest.mark.parametrize(
    "field,conditions,accept",
    [
        ("conditions", "$25 /ea\u0085Dated only.", True),
        ("conditions", "Printed /ea\ufeffwith 2 riders per cart.", True),
        ("conditions", "$25 /ea then\u0085/private/evidence", False),
        ("conditions", "$25 /ea then\ufeff/private/evidence", False),
        ("qualification", "See “https://official.example”/private/evidence", False),
        ("qualification", "See ‘https://official.example’C:/private/evidence", False),
        ("qualification", r"See «https://official.example»\\server\private", False),
        (
            "qualification",
            "See “https://official.example/course” Dated source only.",
            True,
        ),
    ],
)
def test_normal_build_preserves_or_rejects_complete_unicode_transport(
    tmp_path, field, conditions, accept
):
    value = json.loads((ROOT / "tests/fixtures/native5-ui/transport.json").read_bytes())

    def update(item):
        if isinstance(item, list):
            for child in item:
                update(child)
        elif isinstance(item, dict):
            if (
                field == "conditions"
                and item.get("billing_basis") == "per_person"
                and "conditions" in item
            ) or (
                field == "qualification"
                and item.get("observation_id")
                == "o-00000000-0000-4000-8000-000000000001"
            ):
                item[field] = conditions
            for child in item.values():
                update(child)

    update(value)
    before = copy.deepcopy(value)
    if not accept:
        with pytest.raises(ValueError):
            _public(value)
    else:
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
    shutil.copytree(ROOT / "docs/research-map", source / "docs/research-map")
    out = tmp_path / "site"
    if accept:
        result = pages.build(source, out, "a" * 40)
        assert result["assets"] == 38
        assert "Data credits" in (out / "credits.html").read_text()
        assert (
            out / ("data/native-catalog-" + hashlib.sha256(raw).hexdigest() + ".json")
        ).read_bytes() == raw
        assert conditions.encode() in raw
    else:
        with pytest.raises(ValueError, match="private path"):
            pages.build(source, out, "a" * 40)
        assert not out.exists()
    assert value == before
