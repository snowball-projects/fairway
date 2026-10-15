"""Prepare a guarded ID-scoped proposal; never write the receiving catalog."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def apply(repo, delta_path, output, expected_current_sha256):
    source = repo / "data/catalog.json"
    raw = source.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_current_sha256, (
        "Receiving source changed; inspect/reconcile before preparing a proposal"
    )
    assert output.resolve() != source.resolve(), "Output cannot be canonical"
    if output.exists():
        assert not output.samefile(source), "Output cannot alias canonical"
    before = json.loads(raw)
    delta = json.loads(delta_path.read_bytes())
    candidate = copy.deepcopy(before)
    spec = importlib.util.spec_from_file_location(
        "catalog", repo / "scripts/catalog.py"
    )
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    contract.validate(before)
    facilities = {f["id"]: f for f in candidate["facilities"]}
    assert delta["facility_count"] == len(delta["changes"]) == 17
    assert len({r["facility_id"] for r in delta["changes"]}) == 17
    assert not any(
        license_entry["source_url"] == delta["source_license_to_append"]["source_url"]
        for license_entry in candidate["metadata"]["source_licenses"]
    ), "Cohort license already present; do not apply twice"

    def note(key, value):
        old = candidate["notes"].get(key)
        assert old is None or old == value, f"Note namespace conflict: {key}"
        candidate["notes"][key] = value
        return key

    def source_key(url):
        for key, value in candidate["sources"].items():
            if value == url:
                return key
        key = "s-ohio-next20-" + hashlib.sha256(url.encode()).hexdigest()[:16]
        assert key not in candidate["sources"], f"Source namespace conflict: {key}"
        candidate["sources"][key] = url
        return key

    for row in delta["changes"]:
        fid = row["facility_id"]
        facility = facilities[fid]
        assert all(
            facility[key] == value for key, value in row["identity_guard"].items()
        ), f"Identity changed: {fid}"
        assert set(row["changes"]) <= {"map_location", "public_access"}
        for key, change in row["changes"].items():
            if change.get("before_present") is False:
                assert key not in facility, f"Target field already present: {fid}/{key}"
            else:
                assert facility[key] == change["before"], (
                    f"Target field changed: {fid}/{key}"
                )
            facility[key] = copy.deepcopy(change["after"])
        research = candidate["research"][fid]
        location_note = note(
            "n-ohio-next20-" + fid[2:] + "-location", row["location_qualification"]
        )
        source_note = note(
            "n-ohio-next20-" + fid[2:] + "-source", row["source_qualification"]
        )
        for field, key in [("location", location_note), ("source", source_note)]:
            fragments = research["notes"].setdefault(field, [])
            assert key not in fragments
            fragments.append(key)

        def list_source(url, facility_research=research):
            key = source_key(url)
            if key not in facility_research["listed_sources"]:
                facility_research["listed_sources"].append(key)
            return key

        geometry_source = list_source(row["geometry_evidence"]["url"])
        list_source(row["geometry_evidence"]["osm_url"])
        research["support"].append(
            {
                "fields": ["map_location"],
                "source": geometry_source,
                "observed_on": "2026-10-13",
                "note": [location_note],
            }
        )
        for evidence in row["official_evidence"]:
            fields = evidence["fields"]
            assert "public_access" not in fields or "public_access" in row["changes"]
            research["support"].append(
                {
                    "fields": fields,
                    "source": list_source(evidence["url"]),
                    "observed_on": evidence["observed_on"],
                    "note": [source_note],
                }
            )
    candidate["metadata"]["source_licenses"].append(
        copy.deepcopy(delta["source_license_to_append"])
    )
    contract.validate(candidate)
    touched = {r["facility_id"] for r in delta["changes"]}
    old_facilities = {f["id"]: f for f in before["facilities"]}
    allowed = {r["facility_id"]: set(r["changes"]) for r in delta["changes"]}
    for fid, facility in facilities.items():
        for key in set(facility) | set(old_facilities[fid]):
            if key not in allowed.get(fid, set()):
                assert facility.get(key) == old_facilities[fid].get(key)
        if fid not in touched:
            assert facility == old_facilities[fid]
            assert candidate["research"][fid] == before["research"][fid]
    for key in ["history", "progress", "county_checklist"]:
        assert candidate[key] == before[key]
    for table in ["sources", "notes"]:
        assert all(
            candidate[table][key] == value for key, value in before[table].items()
        )
    assert source.read_bytes() == raw, "Receiving source changed while preparing"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(contract.encoded(candidate))
    return {
        "expected_current_sha256": expected_current_sha256,
        "proposal_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "facilities_updated": len(touched),
        "output": str(output),
        "receiving_catalog_unchanged": True,
        "history_progress_county_checklist_unchanged": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument(
        "--delta",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "data/review-batches/ohio-next20-20261013.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-current-sha256", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            apply(args.repo, args.delta, args.output, args.expected_current_sha256),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
