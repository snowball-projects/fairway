"""Validate/import the reviewed catalog and generate fairway's read models.

Standard library only. No source requests, identity guessing, or geocoding.
"""

import argparse
import copy
import json
import math
import os
import re
import tempfile
import uuid
from datetime import date
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/catalog.json"
VERSION = 3
STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "DC",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
}
KINDS = {
    "address_range_estimate",
    "property_point",
    "reviewed_osm_point",
    "verified_entrance",
}
PURPOSES = {
    "published_unspecified",
    "mailing",
    "contact",
    "course",
    "clubhouse",
    "arrival",
}


def identifier(value, prefix):
    return isinstance(value, str) and re.fullmatch(
        prefix + r"-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value
    )


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def url(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not (parsed.username or parsed.password)
    )


def location(value, arrival=False):
    if value is None:
        return
    require(isinstance(value, dict), "invalid location")
    for key, limit in [("latitude", 90), ("longitude", 180)]:
        number = value.get(key)
        require(
            type(number) in {float, int}
            and math.isfinite(number)
            and abs(number) <= limit,
            "invalid location coordinate",
        )
    require(value.get("kind") in KINDS, "unknown location precision")
    if arrival:
        require(
            value["kind"] in {"reviewed_osm_point", "verified_entrance"},
            "browse point is not an arrival",
        )
        require(text(value.get("reference")), "arrival needs a retained reference")


def ranking_support(supports, course_id):
    """Resolve the same evidence contract for validation and export.

    The primary facts link supports public access. Its scope remains in metadata;
    a source link does not independently certify other fields.
    """
    facts = next(
        (
            s
            for s in supports
            if s["source"] is not None
            and (
                "courses" in s["fields"] or f"courses.{course_id}.access" in s["fields"]
            )
        ),
        None,
    )
    routing = next(
        (
            s
            for s in supports
            if s["source"] is not None and f"courses.{course_id}.arrival" in s["fields"]
        ),
        None,
    )
    require(facts is not None, "ranking access lacks a scoped source")
    require(routing is not None, "ranking arrival lacks a scoped source")
    return facts, routing


def validate(value):
    """The small schema contract, including cross-record and evidence checks."""
    require(value.get("schema_version") == VERSION, "unsupported catalog schema")
    for key in ["metadata", "sources", "notes", "research", "history", "progress"]:
        require(isinstance(value.get(key), dict), f"missing {key}")
    require(isinstance(value.get("facilities"), list), "missing facilities")
    require(isinstance(value.get("county_checklist"), list), "missing counties")
    require(all(url(u) for u in value["sources"].values()), "invalid source URL")
    require(
        all(isinstance(n, str) for n in value["notes"].values()), "invalid shared note"
    )
    facility_ids, course_ids = set(), set()
    course_records = {}
    for facility in value["facilities"]:
        require(
            {
                "id",
                "name",
                "state",
                "county",
                "address",
                "physical_holes",
                "inventory_complete",
                "website",
                "map_location",
                "courses",
            }
            <= set(facility),
            "missing facility fields",
        )
        fid = facility.get("id")
        require(
            identifier(fid, "f") and fid not in facility_ids,
            "duplicate/invalid facility ID",
        )
        facility_ids.add(fid)
        require(text(facility.get("name")), f"{fid}: missing name")
        require(
            facility.get("state") in STATES,
            f"{fid}: invalid state",
        )
        require(
            facility.get("county") is None or text(facility["county"]), "invalid county"
        )
        address = facility.get("address")
        require(
            address is None
            or (
                isinstance(address, dict)
                and text(address.get("text"))
                and address.get("purpose") in PURPOSES
            ),
            f"{fid}: invalid address purpose",
        )
        require(
            facility.get("website") is None or url(facility["website"]),
            "invalid website",
        )
        require(
            facility.get("public_access", "unknown")
            in {"public", "private", "restricted", "unknown"},
            "invalid facility public access",
        )
        website_status = facility.get("website_status", "not_checked")
        checked_on = facility.get("website_checked_on")
        require(
            website_status in {"not_checked", "found", "not_found"},
            "invalid website status",
        )
        require(
            (website_status == "not_checked" and checked_on is None)
            or (website_status != "not_checked" and isinstance(checked_on, str)),
            "website check needs its date",
        )
        if checked_on is not None:
            require(
                date.fromisoformat(checked_on).isoformat() == checked_on,
                "invalid website check date",
            )
        require(
            website_status != "found" or facility.get("website") is not None,
            "found website needs its URL",
        )
        holes = facility.get("physical_holes")
        require(
            holes is None or type(holes) is int and holes > 0, "invalid physical holes"
        )
        require(
            type(facility.get("inventory_complete")) is bool, "invalid inventory flag"
        )
        location(facility.get("map_location"))
        require(isinstance(facility.get("courses"), list), "missing course inventory")
        for course in facility["courses"]:
            require(
                {"id", "name", "holes", "access"} <= set(course),
                "missing course fields",
            )
            cid = course.get("id")
            require(
                identifier(cid, "c") and cid not in course_ids,
                "duplicate/invalid course ID",
            )
            course_ids.add(cid)
            course_records[cid] = (facility, course)
            require(
                course.get("name") is None or text(course["name"]),
                "invalid course name",
            )
            require(
                course.get("holes") is None
                or type(course["holes"]) is int
                and course["holes"] > 0,
                "invalid course holes",
            )
            require(
                course.get("access") in {"public", "private", "restricted", "unknown"},
                "invalid course access",
            )
            location(course.get("arrival"), arrival=True)
            if "address" in course:
                require(
                    course["address"] is None
                    or (
                        text(course["address"].get("text"))
                        and course["address"].get("purpose") in PURPOSES
                    ),
                    "invalid course address override",
                )
        if facility["inventory_complete"]:
            require(bool(facility["courses"]), "complete inventory cannot be empty")
            known = [c["holes"] for c in facility["courses"]]
            if holes is not None and all(h is not None for h in known):
                require(
                    sum(known) == holes, f"{fid}: physical inventory total conflicts"
                )
    require(set(value["research"]) == facility_ids, "research/facility IDs disagree")

    def note_refs(refs):
        require(
            refs is None
            or isinstance(refs, list)
            and all(n in value["notes"] for n in refs),
            "dangling note reference",
        )

    by_facility = {f["id"]: f for f in value["facilities"]}
    for fid, evidence in value["research"].items():
        require(
            evidence.get("grouping") in {"verified", "unreviewed"}, "invalid grouping"
        )
        require(
            all(s in value["sources"] for s in evidence["listed_sources"]),
            "dangling source",
        )
        for refs in evidence["notes"].values():
            note_refs(refs)
        facility = by_facility[fid]
        if (facility.get("map_location") or {}).get("kind") == "property_point":
            require(
                any(
                    "map_location" in support.get("fields", [])
                    and support.get("source") is not None
                    and support.get("observed_on") is not None
                    for support in evidence.get("support", [])
                ),
                "property point needs dated source support",
            )
        fields = set(facility) | {"grouping", "notes.source", "notes.access"}
        fields |= {
            f"courses.{c['id']}.{field}"
            for c in facility["courses"]
            for field in ["arrival", "access", "holes", "name", "address"]
        }
        for support in evidence["support"]:
            require(
                support["source"] in value["sources"]
                or support["source"] is None
                and bool(support.get("note")),
                "dangling support source",
            )
            require(
                bool(support["fields"]) and set(support["fields"]) <= fields,
                f"{fid}: invalid field support",
            )
            observed = support.get("observed_on")
            require(
                observed is None
                or isinstance(observed, str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", observed),
                "invalid observed date",
            )
            if observed is not None:
                date.fromisoformat(observed)
            if "note" in support:
                note_refs(support["note"])
        for course in facility["courses"]:
            if course.get("arrival"):
                require(
                    any(
                        f"courses.{course['id']}.arrival" in s["fields"]
                        for s in evidence["support"]
                    ),
                    "arrival lacks specific support",
                )
            if course["access"] != "unknown":
                require(
                    any(
                        "courses" in s["fields"]
                        or f"courses.{course['id']}.access" in s["fields"]
                        for s in evidence["support"]
                    ),
                    "course access lacks support",
                )
    county_ids = set()
    for county in value["county_checklist"]:
        require(
            re.fullmatch(r"\d{5}", county["fips"]) and county["fips"] not in county_ids,
            "invalid/duplicate county",
        )
        county_ids.add(county["fips"])
    commits = set()
    for batch in value["history"]["batches"]:
        require(
            re.fullmatch(r"[0-9a-f]{40}", batch["commit"])
            and batch["commit"] not in commits,
            "invalid/duplicate history commit",
        )
        commits.add(batch["commit"])
        require(
            batch["facilities_added"]
            == len(batch["added_facilities"]) + batch.get("redacted_entries", 0),
            "history counts disagree",
        )
        for row in batch["added_facilities"]:
            require(
                row.get("id") is None or row["id"] in facility_ids,
                "dangling historical facility",
            )
        if "correction_note" in batch:
            note_refs(batch["correction_note"])
    require(
        set(value["progress"]["report_commits"]) <= commits, "dangling progress commit"
    )
    ranking = value["metadata"]["ranking"]
    require(
        len(ranking["course_ids"]) == len(set(ranking["course_ids"])),
        "duplicate ranking course",
    )
    for cid in ranking["course_ids"]:
        require(cid in course_records, "dangling ranking course")
        facility, course = course_records[cid]
        ranking_support(value["research"][facility["id"]]["support"], cid)
        require(
            course["access"] == "public" and course["holes"] in {9, 18},
            "ineligible ranking course",
        )
        require(course.get("arrival") is not None, "ranking destination unknown")
        address = course.get("address", facility["address"])
        require(
            address is not None
            and address["purpose"] in {"course", "clubhouse", "arrival"},
            "ranking address is not a course location",
        )
    return value


def read(path=SOURCE):
    return validate(json.loads(Path(path).read_text()))


def joined_notes(value, refs):
    return None if refs is None else "".join(value["notes"][n] for n in refs)


def coverage(value):
    facilities = value["facilities"]
    county_keys = {(c["state"], c["name"]) for c in value["county_checklist"]}
    return {
        "national_complete": False,
        "complete_essentials": sum(
            all(
                f[k] is not None
                for k in ["name", "address", "county", "physical_holes"]
            )
            for f in facilities
        ),
        "complete_with_website": sum(
            all(
                f[k] is not None
                for k in ["name", "address", "county", "physical_holes", "website"]
            )
            for f in facilities
        ),
        "counties_represented": len(
            {(f["state"], f["county"]) for f in facilities} & county_keys
        ),
        "state_facility_entry_counts": {
            state: sum(f["state"] == state for f in facilities)
            for state in sorted({f["state"] for f in facilities})
        },
        "facility_entry_count": len(facilities),
        "course_entry_count": sum(len(f["courses"]) for f in facilities),
        "public_course_entry_count": sum(
            c["access"] == "public" for f in facilities for c in f["courses"]
        ),
        "unknown_access_course_entry_count": sum(
            c["access"] == "unknown" for f in facilities for c in f["courses"]
        ),
        "facilities_with_coordinates": sum(
            f["map_location"] is not None for f in facilities
        ),
        "facilities_with_unresolved_course_details": sum(
            not f["inventory_complete"] for f in facilities
        ),
        "missing_fields": {
            k: sum(f[k] is None for f in facilities)
            for k in ["address", "county", "physical_holes", "website", "map_location"]
        },
    }


def exports(value):
    """Derive all consumers together. IDs are copied, never regenerated."""
    public = {
        "schema_version": VERSION,
        "updated_on": value["metadata"]["updated_on"],
        "coverage": coverage(value),
        "metadata_url": "catalog-metadata.json",
        "county_checklist": [
            {
                k: c[k]
                for k in ["state", "fips", "name", "search_status", "searched_on"]
                if k in c
            }
            for c in value["county_checklist"]
        ],
        "facilities": [
            {
                **f,
                "access_note": joined_notes(
                    value, value["research"][f["id"]]["notes"].get("access")
                ),
            }
            for f in value["facilities"]
        ],
    }
    metadata = {
        "schema_version": VERSION,
        "metadata": value["metadata"],
        "sources": value["sources"],
        "notes": value["notes"],
        "research": value["research"],
        "county_checklist": value["county_checklist"],
    }
    history = copy.deepcopy(value["history"])
    history["schema_version"] = VERSION
    history["current_facility_count"] = len(value["facilities"])
    for batch in history["batches"]:
        if "correction_note" in batch:
            batch["correction_note"] = joined_notes(value, batch["correction_note"])
    by_commit = {b["commit"]: b for b in history["batches"]}
    progress = {k: v for k, v in value["progress"].items() if k != "report_commits"}
    progress["schema_version"] = VERSION
    progress["coverage"] = coverage(value)
    progress["recent_batches"] = [
        {**by_commit[c], "published_at": by_commit[c].get("reported_at")}
        for c in value["progress"]["report_commits"]
    ]
    ranking = {
        k: v for k, v in value["metadata"]["ranking"].items() if k != "course_ids"
    }
    ranking.update(
        schema_version=VERSION,
        sources=[{"id": k, "url": u} for k, u in value["sources"].items()],
        courses=[],
    )
    by_course = {c["id"]: (f, c) for f in value["facilities"] for c in f["courses"]}
    used_sources = set()
    for cid in value["metadata"]["ranking"]["course_ids"]:
        facility, course = by_course[cid]
        supports = value["research"][facility["id"]]["support"]
        facts, routing = ranking_support(supports, cid)
        used_sources.update([facts["source"], routing["source"]])
        address = course.get("address", facility["address"])
        ranking["courses"].append(
            {
                "id": cid,
                "facility_id": facility["id"],
                "name": facility["name"] if course["name"] is None else course["name"],
                "address": address["text"],
                "address_purpose": address["purpose"],
                "routing_coordinate": [
                    course["arrival"]["latitude"],
                    course["arrival"]["longitude"],
                ],
                "destination_kind": course["arrival"]["kind"],
                "holes": course["holes"],
                "access": course["access"],
                "website": facility["website"],
                "facts_source": facts["source"],
                "routing_source": routing["source"],
                "routing_reference": course["arrival"]["reference"],
            }
        )
    ranking["sources"] = [s for s in ranking["sources"] if s["id"] in used_sources]
    return {
        "public-courses.json": public,
        "catalog-metadata.json": metadata,
        "research-progress.json": progress,
        "catalog-additions.json": history,
        "course-catalog.json": ranking,
    }


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()


def atomic_write(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staged = tempfile.mkstemp(dir=path.parent, prefix=".catalog-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
        os.replace(staged, path)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)


def export(value, output):
    for name, data in exports(value).items():
        atomic_write(Path(output) / name, encoded(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "export", "import", "mint-id"])
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=ROOT / "src/fairway/static/data")
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument(
        "--allow-removals",
        action="store_true",
        help="Explicitly permit reviewed removal of existing IDs",
    )
    parser.add_argument("--kind", choices=["facility", "course"])
    args = parser.parse_args()
    if args.command == "mint-id":
        parser.error("--kind is required") if not args.kind else None
        print(("f" if args.kind == "facility" else "c") + "-" + str(uuid.uuid4()))
        return
    if args.command == "import":
        require(
            args.proposal is not None and args.expected_sha256 is not None,
            "import requires --proposal and --expected-sha256",
        )
        reviewed = args.proposal.read_bytes()
        candidate = validate(json.loads(reviewed))
        current = read(args.source)
        if not args.allow_removals:

            def ids(document):
                return {f["id"] for f in document["facilities"]} | {
                    c["id"] for f in document["facilities"] for c in f["courses"]
                }

            require(
                ids(current) <= ids(candidate),
                "existing IDs removed; retain identity or explicitly review removals",
            )
        require(
            sha256(args.source.read_bytes()).hexdigest() == args.expected_sha256,
            "source changed since review",
        )
        atomic_write(args.source, reviewed)
    value = read(args.source)
    if args.command == "export":
        export(value, args.output)
    print(json.dumps(coverage(value), sort_keys=True))


if __name__ == "__main__":
    main()
