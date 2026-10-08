"""Prepare public review assets for fairway's existing static file handler.

Copies only public catalog/status inputs and the reviewed browser assets.
Run before packaging/installing the application; source inputs are not changed.
"""

import argparse
import json
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("index.html", "styles.css", "app.mjs", "model.mjs", "boundaries.json")


def publish(root, output):
    catalog = (root / "data/public-courses.json").read_bytes()
    progress = (root / "data/research-progress.json").read_bytes()
    catalog_data, progress_data = json.loads(catalog), json.loads(progress)
    if not isinstance(catalog_data.get("facilities"), list) or not isinstance(
        catalog_data.get("county_checklist"), list
    ):
        raise TypeError("unsupported public catalog")
    if progress_data.get("schema_version") != 1:
        raise ValueError("unsupported public progress snapshot")
    payloads = {
        Path("research-map") / name: (root / "docs/research-map" / name).read_bytes()
        for name in ASSETS
    }
    payloads[Path("research-map/index.html")] = payloads[
        Path("research-map/index.html")
    ].replace(b"../../src/fairway/static/favicon.png", b"/favicon.png")
    payloads[Path("data/public-courses.json")] = catalog
    payloads[Path("data/research-progress.json")] = progress
    payloads[Path("research-map/publication.json")] = (
        json.dumps(
            {
                "catalog_sha256": sha256(catalog).hexdigest(),
                "progress_sha256": sha256(progress).hexdigest(),
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
        "progress_sha256": sha256(progress).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "src/fairway/static")
    args = parser.parse_args()
    print(json.dumps(publish(ROOT, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
