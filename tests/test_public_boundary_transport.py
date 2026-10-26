"""Credentials and path endpoints are enforced before any normal build output."""

import copy
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from test_public_price_scan import pages

from fairway.catalog_native_export import _public

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/native5-ui"
CREDENTIAL_DECISIONS = {
    c["name"]: c["accept"]
    for c in json.loads(
        (FIXTURE_ROOT / "public-boundary-conservative-decisions.json").read_text()
    )
}


def privacy_cases(rows):
    return [
        dict(c, accept=CREDENTIAL_DECISIONS.get(c.get("name"), c["accept"]))
        for c in rows
    ]


CASES = json.loads(
    (ROOT / "tests/fixtures/native5-ui/public-boundary-dto.json").read_text()
)
CASES += json.loads(
    (
        ROOT / "tests/fixtures/native5-ui/public-boundary-raw-url-controls.json"
    ).read_text()
)
CASES += json.loads((FIXTURE_ROOT / "public-boundary-scheme-userinfo.json").read_text())
CASES = privacy_cases(
    CASES
    + json.loads((FIXTURE_ROOT / "public-boundary-credential-syntax.json").read_text())
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["target"] + " " + c["text"])
def test_complete_credentials_and_path_boundary_normal_build(tmp_path, case):
    value = json.loads((ROOT / "tests/fixtures/native5-ui/transport.json").read_text())
    if case["target"] == "license":
        value["source_licenses"].append(
            {"source_url": case["text"], "license": "CC BY-SA"}
        )
    else:
        column = "website" if case["target"] == "website" else "booking_conditions"
        subject = value["courses"][0]["course_id"]

        def update(item):
            if isinstance(item, list):
                for child in item:
                    update(child)
            elif isinstance(item, dict):
                if item.get("course_id") == subject and column in item:
                    item[column] = case["text"]
                for child in item.values():
                    update(child)

        update(value)
    before = copy.deepcopy(value)
    if case["accept"]:
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
        for k in ["format_version", "schema", "revision", "catalog_release_key"]
    }
    manifest["counts"] = {
        k: len(value[k]) for k in ["facilities", "courses", "destinations"]
    }
    manifest["files"] = {
        name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        for name, body in [("catalog.json", raw), ("catalog.json.gz", packed)]
    }
    (data / "manifest.json").write_text(json.dumps(manifest))
    (data / "catalog.json.gz").write_bytes(packed)
    shutil.copytree(ROOT / "src/fairway/static", source / "src/fairway/static")
    shutil.copyfile(
        ROOT / "data/map-boundaries.json", source / "data/map-boundaries.json"
    )
    out = tmp_path / "site"
    if case["accept"]:
        assert pages.build(source, out, "0" * 40)["assets"] == 36
        assert "Data credits" in (out / "credits.html").read_text()
        assert (
            out / ("data/native-catalog-" + hashlib.sha256(raw).hexdigest() + ".json")
        ).read_bytes() == raw
        decoded = json.loads(raw)
        assert (
            decoded["source_licenses"][-1]["source_url"]
            if case["target"] == "license"
            else decoded["courses"][0][
                "website" if case["target"] == "website" else "booking_conditions"
            ]
        ) == case["text"]
    else:
        with pytest.raises(ValueError):
            pages.build(source, out, "0" * 40)
        assert not out.exists()
    assert value == before
