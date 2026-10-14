"""Guarded addition replay; no network or new identifiers."""

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import catalog


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    delta = json.loads(Path(__file__).with_name("delta.json").read_text())
    raw = args.catalog.read_bytes()
    if hashlib.sha256(raw).hexdigest() != delta["base_catalog_sha256"]:
        raise ValueError("Catalog guard mismatch; review changed source before replay")
    before = catalog.read(args.catalog)
    after = copy.deepcopy(before)
    for facility in delta["added_facilities"]:
        for old in before["facilities"]:
            address = normalized((facility["address"] or {}).get("text"))
            if old["id"] == facility["id"] or (
                old["state"] == facility["state"]
                and (
                    normalized(old["name"]) == normalized(facility["name"])
                    or (
                        address
                        and normalized((old["address"] or {}).get("text")) == address
                    )
                )
            ):
                raise ValueError("Potential duplicate requires identity review")
        after["facilities"].append(copy.deepcopy(facility))
    for key in ["sources", "notes", "research"]:
        if before[key].keys() & delta[key].keys():
            raise ValueError("Evidence registry collision")
        after[key].update(copy.deepcopy(delta[key]))
    catalog.validate(after)
    if after["facilities"][: len(before["facilities"])] != before["facilities"]:
        raise ValueError("Existing facility changed")
    for key in ["sources", "notes", "research"]:
        if any(after[key][k] != v for k, v in before[key].items()):
            raise ValueError("Existing evidence changed")
    for key in ["metadata", "history", "progress", "county_checklist"]:
        if after[key] != before[key]:
            raise ValueError("Unrelated catalog value changed")
    args.output.write_bytes(catalog.encoded(after))
    print(
        json.dumps(
            {
                "facilities_added": len(delta["added_facilities"]),
                "preserved_facilities": len(before["facilities"]),
                "candidate_facilities": len(after["facilities"]),
                "candidate_sha256": hashlib.sha256(
                    args.output.read_bytes()
                ).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
