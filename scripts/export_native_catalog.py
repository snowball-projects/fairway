"""Build static native reader transport from a pinned closed SQLite release."""

import argparse
import json
from pathlib import Path

from fairway.catalog_export import export_native_transport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            export_native_transport(
                args.db,
                args.output,
                expected_sha256=args.sha256,
                revision=args.revision,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
