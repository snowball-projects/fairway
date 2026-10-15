"""Local SQLite catalog commands. No public server or network calls."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fairway.catalog_store import (
    apply_batch,
    check,
    clear_source,
    connect,
    digest,
    inventory,
    query_courses,
    query_facilities,
    restore,
    row,
    snapshot,
    summary,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
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
    lookup = sub.add_parser("row")
    lookup.add_argument("entity")
    lookup.add_argument("id")
    listing = sub.add_parser("courses")
    listing.add_argument("--state")
    listing.add_argument("--access")
    listing.add_argument("--style")
    listing.add_argument("--holes", type=int)
    listing.add_argument("--round-holes", type=int)
    listing.add_argument("--bbox", nargs=4, type=float)
    listing.add_argument("--center", nargs=2, type=float)
    listing.add_argument("--radius-km", type=float)
    listing.add_argument("--plan", action="store_true")
    listing.add_argument("--confirmed-identities", action="store_true")
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--offset", type=int, default=0)
    facilities = sub.add_parser("facilities")
    for field in ("state", "country", "county", "access", "search"):
        facilities.add_argument("--" + field)
    facilities.add_argument("--bbox", nargs=4, type=float)
    facilities.add_argument("--center", nargs=2, type=float)
    facilities.add_argument("--radius-km", type=float)
    facilities.add_argument("--limit", type=int, default=100)
    facilities.add_argument("--offset", type=int, default=0)
    save = sub.add_parser("snapshot")
    save.add_argument("output", type=Path)
    load = sub.add_parser("restore")
    load.add_argument("input", type=Path)
    args = parser.parse_args()
    if args.command == "import":
        result = apply_batch(
            args.db, json.loads(args.batch.read_text()), apply=args.apply
        )
        args.report.write_text(summary(result))
        args.report.with_suffix(args.report.suffix + ".json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
    elif args.command == "clear-source":
        result = clear_source(
            args.db,
            args.source_id,
            args.expected,
            args.controls_reference,
            args.collected_on,
        )
    elif args.command == "row":
        with connect(args.db, readonly=True) as db:
            found = (
                dict(
                    db.execute("SELECT * FROM source WHERE id=?", (args.id,)).fetchone()
                )
                if args.entity == "source"
                else row(db, args.entity, args.id)
            )
            result = {"row": found, "digest": digest(found) if found else None}
    elif args.command == "check":
        with connect(args.db, readonly=True) as db:
            result = check(db) | inventory(db)
    elif args.command == "courses":
        result = query_courses(
            args.db,
            state=args.state,
            access=args.access,
            style=args.style,
            holes=args.holes,
            round_holes=args.round_holes,
            bbox=args.bbox,
            center=args.center,
            radius_km=args.radius_km,
            plan=args.plan,
            include_review=not args.confirmed_identities,
            limit=args.limit,
            offset=args.offset,
        )
    elif args.command == "facilities":
        result = query_facilities(
            args.db,
            state=args.state,
            country=args.country,
            county=args.county,
            access=args.access,
            search=args.search,
            bbox=args.bbox,
            center=args.center,
            radius_km=args.radius_km,
            limit=args.limit,
            offset=args.offset,
        )
    elif args.command == "snapshot":
        result = snapshot(args.db, args.output)
    else:
        restore(args.input, args.db)
        result = {"restored": str(args.db)}
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result.get("state") in {"rejected", "conflicted"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
