"""Prepare reviewed catalog exports and browser assets for static serving."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

import catalog as foundation

ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    "index.html",
    "styles.css",
    "app.mjs",
    "model.mjs",
    "refresh.mjs",
    "boundaries.json",
)


def publish(root, output):
    value = foundation.read(root / "data/catalog.json")
    generated = foundation.exports(value)
    payloads = {
        Path("research-map") / name: (root / "docs/research-map" / name).read_bytes()
        for name in ASSETS
    }
    payloads[Path("research-map/index.html")] = payloads[
        Path("research-map/index.html")
    ].replace(b"../../src/fairway/static/favicon.png", b"/favicon.png")
    for name, data in generated.items():
        if name != "course-catalog.json":
            payloads[Path("data") / name] = foundation.encoded(data)
    manifest = {
        key + "_sha256": sha256(payloads[Path("data") / name]).hexdigest()
        for key, name in [
            ("catalog", "public-courses.json"),
            ("progress", "research-progress.json"),
            ("additions", "catalog-additions.json"),
            ("metadata", "catalog-metadata.json"),
        ]
    }
    payloads[Path("research-map/publication.json")] = foundation.encoded(manifest)
    # Validate everything before writing; release preparation happens before serving.
    for relative, body in payloads.items():
        foundation.atomic_write(output / relative, body)
    foundation.atomic_write(
        root / "src/fairway/data/course-catalog.json",
        foundation.encoded(generated["course-catalog.json"]),
    )
    return {"facilities": len(value["facilities"]), **manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "src/fairway/static")
    args = parser.parse_args()
    print(json.dumps(publish(ROOT, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
