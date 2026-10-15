"""Explicit-path native5 maintenance. No automatic upgrade, service or publication."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fairway import catalog_native as native
from fairway.catalog_native_export import export_transport
from fairway.catalog_native_read import query_courses, query_facilities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create")
    sub.add_parser("check")
    intake = sub.add_parser("import")
    intake.add_argument("batch", type=Path)
    intake.add_argument("--apply", action="store_true")
    intake.add_argument("--report", type=Path, required=True)
    clear = sub.add_parser("clear-source")
    clear.add_argument("source_id")
    clear.add_argument("--expected", required=True)
    clear.add_argument("--controls-reference", required=True)
    clear.add_argument("--collected-on", required=True)
    for command in ("courses", "facilities"):
        listing = sub.add_parser(command)
        for field in ("state", "country", "county", "access", "search"):
            listing.add_argument("--" + field)
        listing.add_argument("--holes", type=int)
        listing.add_argument("--bbox", type=float, nargs=4)
        listing.add_argument("--center", type=float, nargs=2)
        listing.add_argument("--radius-km", type=float)
        listing.add_argument("--limit", type=int, default=100)
        listing.add_argument("--offset", type=int, default=0)
        if command == "courses":
            listing.add_argument("--style")
            listing.add_argument("--round-holes", type=int)
            listing.add_argument("--plan", action="store_true")
    for command in ("snapshot", "restore", "export"):
        action = sub.add_parser(command)
        action.add_argument("path", type=Path)
        if command != "snapshot":
            action.add_argument("--sha256", required=True)
        if command == "export":
            action.add_argument("--revision", type=int, required=True)
    args = parser.parse_args()
    if args.command == "create":
        native.create(args.db)
        result = {"state": "created", "schema": 5}
    elif args.command == "check":
        db = native.connect(args.db)
        try:
            db.execute("BEGIN")
            result = native.check(db)
        finally:
            db.close()
    elif args.command == "import":
        result = native.apply_batch(
            args.db, json.loads(args.batch.read_text()), apply=args.apply
        )
        args.report.write_text(native.summary(result))
        args.report.with_suffix(args.report.suffix + ".json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
    elif args.command == "clear-source":
        result = native.clear_source(
            args.db,
            args.source_id,
            expected=args.expected,
            controls_reference=args.controls_reference,
            collected_on=args.collected_on,
        )
    elif args.command in {"courses", "facilities"}:
        values = vars(args).copy()
        for field in ("db", "command"):
            values.pop(field)
        result = (query_courses if args.command == "courses" else query_facilities)(
            args.db, **values
        )
    elif args.command == "snapshot":
        result = native.snapshot(args.db, args.path)
    elif args.command == "restore":
        result = native.restore(args.path, args.db, expected_sha256=args.sha256)
    else:
        result = export_transport(
            args.db, args.path, expected_sha256=args.sha256, revision=args.revision
        )
    print(json.dumps(result, indent=2, allow_nan=False))
    if result.get("state") in {"rejected", "conflicted"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
