"""Prepare public review assets for fairway's existing static file handler.

Copies only public catalog/status inputs and the reviewed browser assets.
Run before packaging/installing the application; source inputs are not changed.
"""

import argparse
import json
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    "index.html",
    "styles.css",
    "app.mjs",
    "model.mjs",
    "refresh.mjs",
    "boundaries.json",
)


def optional_snapshot(path, required):
    try:
        body = path.read_bytes()
        value = json.loads(body)
        if isinstance(value, dict) and all(
            value.get(key) == expected for key, expected in required.items()
        ):
            return body
    except (OSError, ValueError):
        pass
    return None


def publish(root, output):
    catalog = (root / "data/public-courses.json").read_bytes()
    progress = optional_snapshot(
        root / "data/research-progress.json", {"schema_version": 1}
    )
    catalog_data = json.loads(catalog)
    if not isinstance(catalog_data.get("facilities"), list) or not isinstance(
        catalog_data.get("county_checklist"), list
    ):
        raise TypeError("unsupported public catalog")
    payloads = {
        Path("research-map") / name: (root / "docs/research-map" / name).read_bytes()
        for name in ASSETS
    }
    payloads[Path("research-map/index.html")] = payloads[
        Path("research-map/index.html")
    ].replace(b"../../src/fairway/static/favicon.png", b"/favicon.png")
    payloads[Path("data/public-courses.json")] = catalog
    if progress is not None:
        payloads[Path("data/research-progress.json")] = progress
    additions = optional_snapshot(
        root / "data/catalog-additions.json",
        {
            "schema_version": 1,
            "time_basis": "git_commit_time",
            "count_unit": "provisional_facility_entry",
        },
    )
    if additions is not None:
        additions_data = json.loads(additions)
        if isinstance(additions_data.get("batches"), list):
            payloads[Path("data/catalog-additions.json")] = additions
        else:
            additions = None
    payloads[Path("research-map/publication.json")] = (
        json.dumps(
            {
                "catalog_sha256": sha256(catalog).hexdigest(),
                "progress_sha256": sha256(progress).hexdigest() if progress else None,
                "additions_sha256": sha256(additions).hexdigest()
                if additions
                else None,
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    # All inputs are read/validated before writing. Render builds in a fresh
    # release directory, so no running process can observe partial preparation.
    for relative, body in payloads.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
    return {
        "facilities": len(catalog_data["facilities"]),
        "catalog_sha256": sha256(catalog).hexdigest(),
        "progress_sha256": sha256(progress).hexdigest() if progress else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "src/fairway/static")
    args = parser.parse_args()
    print(json.dumps(publish(ROOT, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
