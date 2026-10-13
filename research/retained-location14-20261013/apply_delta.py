"""Prepare an offline, guarded location-only proposal without writing its source."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def apply(repo, delta_path, output, expected_current_sha256):
    source = repo / "data/catalog.json"
    raw = source.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_current_sha256
    assert output.resolve() != source.resolve()
    if output.exists():
        assert not output.samefile(source)
    before = json.loads(raw)
    candidate = copy.deepcopy(before)
    delta = json.loads(delta_path.read_bytes())
    spec = importlib.util.spec_from_file_location(
        "catalog", repo / "scripts/catalog.py"
    )
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    catalog.validate(before)
    facilities = {f["id"]: f for f in candidate["facilities"]}
    ids = {r["facility_id"] for r in delta["changes"]}
    assert len(ids) == len(delta["changes"]) == delta["accepted_count"] == 4
    assert not any(
        x["source_url"] == delta["source_license_to_append"]["source_url"]
        for x in candidate["metadata"]["source_licenses"]
    )

    def source_key(url):
        for key, value in candidate["sources"].items():
            if value == url:
                return key
        key = "s-retained-location14-" + hashlib.sha256(url.encode()).hexdigest()[:16]
        assert key not in candidate["sources"]
        candidate["sources"][key] = url
        return key

    for row in delta["changes"]:
        fid = row["facility_id"]
        facility = facilities[fid]
        assert facility == row["identity_guard"]
        assert set(row["changes"]) == {"map_location"}
        change = row["changes"]["map_location"]
        assert facility["map_location"] == change["before"]
        facility["map_location"] = copy.deepcopy(change["after"])
        note = "n-retained-location14-" + fid[2:] + "-location"
        assert note not in candidate["notes"]
        candidate["notes"][note] = row["location_qualification"]
        research = candidate["research"][fid]
        research["notes"].setdefault("location", []).append(note)
        for url in row["geometry_evidence"]["url"], row["geometry_evidence"]["osm_url"]:
            key = source_key(url)
            if key not in research["listed_sources"]:
                research["listed_sources"].append(key)
        research["support"].append(
            {
                "fields": ["map_location"],
                "source": source_key(row["geometry_evidence"]["url"]),
                "observed_on": "2026-10-13",
                "note": [note],
            }
        )
    candidate["metadata"]["source_licenses"].append(
        copy.deepcopy(delta["source_license_to_append"])
    )
    catalog.validate(candidate)
    for old in before["facilities"]:
        new = facilities[old["id"]]
        assert {k: v for k, v in old.items() if k != "map_location"} == {
            k: v for k, v in new.items() if k != "map_location"
        }
        if old["id"] not in ids:
            assert old == new
            assert before["research"][old["id"]] == candidate["research"][old["id"]]
    for key in "history", "progress", "county_checklist":
        assert before[key] == candidate[key]
    for table in "sources", "notes":
        assert all(candidate[table][k] == v for k, v in before[table].items())
    assert source.read_bytes() == raw
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(catalog.encoded(candidate))
    return {"proposal_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--delta", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-current-sha256", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            apply(args.repo, args.delta, args.output, args.expected_current_sha256)
        )
    )
