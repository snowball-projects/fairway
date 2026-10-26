"""Regenerate public GeoJSON and browser projections from the maintained CSV files."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fairway.open_catalog import derived_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    for name, body in derived_files(root).items():
        path = root / name
        if args.check:
            if path.read_bytes() != body:
                raise SystemExit("Regeneration required: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
    print(
        "Catalog projections match CSV sources."
        if args.check
        else "Catalog projections regenerated."
    )


if __name__ == "__main__":
    main()
