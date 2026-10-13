"""Prepare a reviewed catalog proposal from the Kansas addition delta; no network."""

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import catalog


def identity(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-commit")
    args = parser.parse_args()
    delta = json.loads(Path(__file__).with_name("delta.json").read_text())
    before = catalog.read(args.catalog)
    proposal = copy.deepcopy(before)
    commit = args.evidence_commit or delta["evidence_commit"]
    if not commit or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("An actual reviewed evidence commit is required")
    if any(b["commit"] == commit for b in before["history"]["batches"]):
        raise ValueError("Evidence batch already present")
    existing_ids = {f["id"] for f in before["facilities"]}
    for f in delta["added_facilities"]:
        address = identity((f["address"] or {}).get("text"))
        for old in before["facilities"]:
            if old["state"] != f["state"]:
                continue
            same_address = address and address == identity(
                (old["address"] or {}).get("text")
            )
            if (
                old["id"] == f["id"]
                or identity(old["name"]) == identity(f["name"])
                or same_address
            ):
                raise ValueError(
                    f"Review possible duplicate: {f['name']} / {old['name']}"
                )
        if f["id"] in existing_ids:
            raise ValueError("Facility ID collision")
    remap = {}
    for key, url in delta["sources"].items():
        present = next((k for k, v in proposal["sources"].items() if v == url), None)
        if present:
            remap[key] = present
        else:
            if key in proposal["sources"]:
                raise ValueError("Source key collision")
            proposal["sources"][key] = url
            remap[key] = key
    for key, note in delta["notes"].items():
        if key in proposal["notes"] and proposal["notes"][key] != note:
            raise ValueError("Note key collision")
        proposal["notes"][key] = note
    for f in delta["added_facilities"]:
        proposal["facilities"].append(copy.deepcopy(f))
        evidence = copy.deepcopy(delta["research"][f["id"]])
        evidence["listed_sources"] = [remap[s] for s in evidence["listed_sources"]]
        for support in evidence["support"]:
            support["source"] = remap[support["source"]]
        proposal["research"][f["id"]] = evidence
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        commit_time = subprocess.check_output(
            ["git", "show", "-s", "--format=%cI", f"{commit}^{{commit}}"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError(
            "Resolve the reviewed evidence commit locally before replay"
        ) from error
    committed_at = (
        datetime.fromisoformat(commit_time)
        .astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    batch = {
        "commit": commit,
        "committed_at": committed_at,
        "reported_at": now,
        "initial_baseline": False,
        "facilities_added": len(delta["added_facilities"]),
        "facilities_removed": 0,
        "facilities_updated": 0,
        "redacted_entries": 0,
        "added_facilities": [
            {
                "id": f["id"],
                "name": f["name"],
                "state": f["state"],
                "address": (f["address"] or {}).get("text"),
            }
            for f in delta["added_facilities"]
        ],
    }
    proposal["history"]["batches"].append(batch)
    proposal["progress"]["report_commits"].insert(0, commit)
    proposal["progress"]["catalog_commit"] = commit
    proposal["progress"]["updated_at"] = now
    proposal["metadata"]["updated_on"] = max(
        before["metadata"]["updated_on"], delta["observed_on"]
    )
    catalog.validate(proposal)
    args.output.write_bytes(catalog.encoded(proposal))
    print(
        json.dumps(
            {
                "proposal": str(args.output),
                "facilities_added": len(delta["added_facilities"]),
                "expected_current_sha256": hashlib.sha256(
                    args.catalog.read_bytes()
                ).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
