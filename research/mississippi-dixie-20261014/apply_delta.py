"""Create a validated proposal from the reviewed, guarded addition delta.

Makes no source requests. History/progress belong to the integration owner.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    delta = json.loads(Path(__file__).with_name("delta.json").read_text())
    raw = args.source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.expected_sha256:
        raise SystemExit("Source changed; review the current catalog before applying")
    before = json.loads(raw)
    candidate = copy.deepcopy(before)
    ids = {row["id"] for row in before["facilities"]}
    for row in delta["added_facilities"]:
        if row["id"] in ids:
            raise SystemExit("Addition ID already exists")
        if any(
            row["state"] == existing["state"]
            and (
                row["name"].casefold() == existing["name"].casefold()
                or row["website"] == existing.get("website")
                or row["address"] == existing.get("address")
            )
            for existing in before["facilities"]
        ):
            raise SystemExit("Possible existing identity requires review")
        candidate["facilities"].append(row)
    for key in ["sources", "notes", "research"]:
        if set(candidate[key]) & set(delta[key]):
            raise SystemExit(f"Registry collision: {key}")
        candidate[key].update(delta[key])
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "catalog", root / "scripts/catalog.py"
    )
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    catalog.validate(candidate)
    for row in before["facilities"]:
        assert row == next(x for x in candidate["facilities"] if x["id"] == row["id"])
        assert before["research"].get(row["id"]) == candidate["research"].get(row["id"])
    for key in ["metadata", "county_checklist", "history", "progress"]:
        assert before[key] == candidate[key]
    if args.output.resolve() == args.source.resolve():
        raise SystemExit(
            "Write a separate proposal; use catalog import for integration"
        )
    args.output.write_bytes(catalog.encoded(candidate))
    print(
        f"Validated proposal: {len(before['facilities'])} -> {len(candidate['facilities'])}"
    )


if __name__ == "__main__":
    main()
