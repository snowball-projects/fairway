"""Accepted historical intake IDs remain present after retiring JSON replay."""

import gzip
import json
from pathlib import Path


def test_accepted_kansas_delta_is_preserved_in_native_catalog():
    root = Path(__file__).resolve().parents[1]
    delta = json.loads((root / "research/kansas-rural-20261013/delta.json").read_text())
    catalog = json.loads(
        gzip.decompress((root / "data/catalog-release/catalog.json.gz").read_bytes())
    )
    by_id = {f["facility_id"]: f for f in catalog["facilities"]}
    assert len(delta["added_facilities"]) == 3
    for old in delta["added_facilities"]:
        current = by_id[old["id"]]
        assert current["name"] == old["name"] and current["state"] == old["state"]
