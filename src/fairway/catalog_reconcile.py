"""Apply reviewed ID-to-ID catalog decisions, with a reversible fact receipt."""

import copy
import hashlib

from .open_catalog import encoded
from .rebuild_catalog import enrich_record, new_record

ACTIONS = {"merge_facility", "remove_component", "course", "match_course"}
INVENTORY_FIELDS = (
    "name",
    "physical_holes",
    "identity_status",
    "access",
    "nonmember_bookable",
)
FACILITY_SCALARS = {
    "access",
    "booking_url",
    "contact_url",
    "country",
    "county",
    "name",
    "operating_status",
    "ownership",
    "physical_holes",
    "setting",
    "state",
    "website",
    "website_checked_on",
    "website_status",
}
WITHHOLDABLE_COURSE_FIELDS = {
    "website",
    "website_status",
    "website_checked_on",
    "address",
    "address_city",
    "address_country",
    "address_postal_code",
    "address_purpose",
    "address_region",
    "address_street_line1",
    "address_street_line2",
    "address_text",
    "booking_url",
    "contact_url",
}


def _sha(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def _without_receipt(value):
    value = dict(value)
    if "rebuild" in value:
        value["rebuild"] = dict(value["rebuild"])
        if "preservation" in value["rebuild"]:
            preservation = dict(value["rebuild"]["preservation"])
            preservation.pop("reconciliation", None)
            value["rebuild"]["preservation"] = preservation
    return value


def _catalog_sha(value):
    return _sha(_without_receipt(value))


def _index(rows, key):
    result = {}
    for row in rows:
        identifier = row.get(key)
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ValueError("Duplicate or missing catalog identity: " + key)
        result[identifier] = row
    return result


def _decisions(value, plan):
    decisions = plan.get("decisions") if isinstance(plan, dict) else plan
    if not isinstance(decisions, list):
        raise TypeError("Reconciliation plan requires explicit decisions")
    facilities = _index(value["facilities"], "facility_id")
    courses = _index(value["courses"], "course_id")
    sources = set()
    for decision in decisions:
        if not isinstance(decision, dict) or decision.get("action") not in ACTIONS:
            raise ValueError("Unknown reconciliation action")
        for key in ("source_id", "target_facility_id", "rule", "reason"):
            if not isinstance(decision.get(key), str) or not decision[key].strip():
                raise ValueError("Missing reconciliation decision: " + key)
        if not decision.get("evidence"):
            raise ValueError("Missing reconciliation evidence")
        source_id, target_id = decision["source_id"], decision["target_facility_id"]
        if source_id in sources:
            raise ValueError("Repeated reconciliation source: " + source_id)
        sources.add(source_id)
        if source_id not in facilities or target_id not in facilities:
            raise ValueError("Unknown reconciliation facility")
        if source_id == target_id:
            raise ValueError("Reconciliation source cannot target itself")
        source = facilities[source_id]
        if any(row.get("facility_id") == source_id for row in courses.values()):
            raise ValueError(
                "Reconciliation source has actual course rows: " + source_id
            )
        if decision.get("source_sha256") not in (None, _sha(source)):
            raise ValueError("Reconciliation source digest changed: " + source_id)
        action, course_id = decision["action"], decision.get("target_course_id")
        if action in {"course", "match_course"}:
            if not isinstance(source.get("osm"), dict):
                raise ValueError("Course decision requires an explicit source OSM row")
            if action == "match_course" and not course_id:
                raise ValueError("match_course requires an existing target_course_id")
            if (
                course_id is not None
                and course_id not in courses
                and not (action == "course" and course_id == source_id)
            ):
                raise ValueError("Unknown target course: " + str(course_id))
            course = courses.get(course_id or source_id)
            if course and course.get("facility_id") not in (None, target_id):
                raise ValueError("Target course belongs to another facility")
            if not course and not courses:
                raise ValueError(
                    "Creating a course requires an existing course template"
                )
        elif course_id is not None:
            raise ValueError("Facility/component decision cannot target a course")
        withheld = decision.get("withheld_course_fields")
        if withheld is not None:
            if action != "course" or courses.get(course_id or source_id):
                raise ValueError("Withheld course fields require a new course")
            if (
                not isinstance(withheld, dict)
                or not isinstance(withheld.get("fields"), list)
                or not withheld["fields"]
                or not all(isinstance(field, str) for field in withheld["fields"])
                or len(set(withheld["fields"])) != len(withheld["fields"])
                or not set(withheld["fields"]) <= WITHHOLDABLE_COURSE_FIELDS
                or not isinstance(withheld.get("reason"), str)
                or not withheld["reason"].strip()
            ):
                raise ValueError(
                    "Withheld course fields require explicit fields and reason"
                )
    # Flattening is a plan author's responsibility. This also rejects cycles and
    # prevents the execution order from silently changing a reviewed decision.
    if any(row["target_facility_id"] in sources for row in decisions):
        raise ValueError(
            "Reconciliation targets cannot also be sources (chain or cycle)"
        )
    return decisions


def _facility_refs(value, mapping):
    """Rewrite facility-typed references, never source IDs or free text."""
    if isinstance(value, list):
        return [_facility_refs(row, mapping) for row in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        typed = key == "facility_id"
        typed |= (
            key == "destination_id"
            and value.get("arrival") is None
            and value.get("arrival_latitude") is None
        )
        typed |= key == "entity_id" and value.get("entity_type") == "facility"
        typed |= key == "id" and value.get("scope") == "facility_estimate"
        result[key] = (
            mapping.get(item, item)
            if typed and isinstance(item, str)
            else _facility_refs(item, mapping)
        )
    return result


def _append_unique(rows, additions):
    seen = {_sha(row) for row in rows}
    for row in additions:
        digest = _sha(row)
        if digest not in seen:
            rows.append(copy.deepcopy(row))
            seen.add(digest)


def _append_optional(target, source):
    for domain, rows in source.get("optional", {}).items():
        current = target.setdefault("optional", {}).setdefault(domain, [])
        by_id = {row["id"]: row for row in current}
        for row in rows:
            if row["id"] in by_id and by_id[row["id"]] != row:
                raise ValueError(
                    "Conflicting immutable optional identity: " + row["id"]
                )
            if row["id"] not in by_id:
                current.append(copy.deepcopy(row))
                by_id[row["id"]] = row


def _attach_osm(target, source, source_id):
    observation = source.get("osm")
    if not observation:
        return
    if target.get("osm") is None:
        target["osm"] = copy.deepcopy(observation)
        target["osm_identity"] = source.get("osm_identity") or source_id
    # A second geometry never displaces the pinned primary observation. Its
    # complete dictionary is in the source_snapshot, and this citation links it.
    citation = {
        "fields": ["osm"],
        "source_kind": "reconciled_osm_observation",
        "source_url": observation.get("source_url"),
        "checked_on": observation.get("checked_on"),
        "license": "ODbL-1.0",
        "credit": observation.get("credit", "OpenStreetMap contributors"),
        "original_source_id": source_id,
        "qualification": "Explicit reviewed identity decision. The complete original OSM observation and source row remain in rebuild.preservation.reconciliation; display positions do not establish an entrance or bookability.",
    }
    _append_unique(target.setdefault("fact_sources", []), [citation])
    _append_unique(target.setdefault("wikidata", []), source.get("wikidata", []))


def _alias(value, kind, identifier, name):
    if not name:
        return
    rows = value["relationships"]["alias"]
    key = kind + "_id"
    if any(row[key] == identifier and row["name"] == name for row in rows):
        return
    rows.append(
        {
            "id": "reconciliation-alias-" + _sha([kind, identifier, name])[:24],
            "facility_id": identifier if kind == "facility" else None,
            "course_id": identifier if kind == "course" else None,
            "name": name,
        }
    )


def _merge_facility(value, target, source, source_id):
    conflicts = []
    prefer_source = bool(source.get("released_id")) and not target.get("released_id")
    fields = FACILITY_SCALARS | {key for key in source if key.startswith("address_")}
    old_name = target.get("name")
    for field in sorted(fields):
        incoming, existing = source.get(field), target.get(field)
        if incoming is None or incoming == "" or isinstance(incoming, (dict, list)):
            continue
        if existing is not None and existing != incoming:
            conflicts.append(
                {
                    "field": field,
                    "source_value": copy.deepcopy(incoming),
                    "target_value": copy.deepcopy(existing),
                    "selected": "source" if prefer_source else "target",
                }
            )
        if existing is None or prefer_source:
            target[field] = copy.deepcopy(incoming)
    if source.get("address") and (target.get("address") is None or prefer_source):
        target["address"] = copy.deepcopy(source["address"])
    if source.get("map_location") and target.get("map_location") is None:
        target["map_location"] = copy.deepcopy(source["map_location"])
        for field in ("latitude", "longitude", "location_kind"):
            if target.get(field) is None:
                target[field] = source.get(field)
    _append_unique(
        target.setdefault("fact_sources", []), source.get("fact_sources", [])
    )
    _append_optional(target, source)
    _attach_osm(target, source, source_id)
    for name in (old_name, source.get("name")):
        if name != target.get("name"):
            _alias(value, "facility", target["facility_id"], name)
    return conflicts


def _archive_relations(value, source_id):
    """A facility observation cannot be relabeled as a course/component fact."""
    relationships = value["relationships"]
    rounds = {
        row["id"]
        for row in relationships["round_option"]
        if row.get("facility_id") == source_id
    }
    for kind, rows in relationships.items():
        relationships[kind] = [
            row
            for row in rows
            if row.get("facility_id") != source_id
            and row.get("round_id") not in rounds
            and not (kind == "round_option" and row["id"] in rounds)
        ]
    value["provenance"]["intake"] = [
        row
        for row in value["provenance"].get("intake", [])
        if not (
            row.get("entity_type") == "facility" and row.get("entity_id") == source_id
        )
    ]


def _refresh(value, facility_ids, course_ids):
    facilities = {row["facility_id"]: row for row in value["facilities"]}
    courses = {row["course_id"]: row for row in value["courses"]}
    relationships = value["relationships"]
    # Optional arrays belong to the existing canonical child identity, not its
    # new parent DTO. Keep the observation envelope and exact subject untouched.
    children = {}
    for row in [*facilities.values(), *courses.values()]:
        for kind in ("components", "round_options"):
            for child in row.get(kind, []):
                children[child["id"]] = child
    parts = {row["id"]: row for row in relationships["component"]}

    def child(row):
        result = copy.deepcopy(row)
        previous = children.get(row["id"], {})
        result["optional"] = copy.deepcopy(
            previous.get(
                "optional",
                {key: [] for key in next(iter(courses.values()))["optional"]},
            )
        )
        return result

    def rounds(facility_id=None, course_id=None):
        result = []
        for row in relationships["round_option"]:
            members = [
                r
                for r in relationships["round_component"]
                if r["round_id"] == row["id"]
            ]
            owners = {row.get("course_id")} | {
                r.get("course_id")
                or parts.get(r.get("component_id"), {}).get("course_id")
                for r in members
            }
            if (facility_id is not None and row.get("facility_id") == facility_id) or (
                course_id is not None and course_id in owners
            ):
                view = child(row)
                view["scope"] = (
                    "facility" if row["facility_id"] is not None else "course"
                )
                view["members"] = copy.deepcopy(members)
                view["tee_sets"] = [
                    copy.deepcopy(r)
                    for r in relationships["tee_set"]
                    if r.get("round_id") == row["id"]
                ]
                result.append(view)
        return result

    for identifier in facility_ids & facilities.keys():
        facility = facilities[identifier]
        own = sorted(
            [row for row in courses.values() if row.get("facility_id") == identifier],
            key=lambda row: row["course_id"],
        )
        facility["course_ids"] = [row["course_id"] for row in own]
        facility["course_count"] = len(own)
        facility["course_inventory"] = [
            {"course_id": row["course_id"]}
            | {key: row.get(key) for key in INVENTORY_FIELDS}
            for row in own
        ]
        facility["documented_course_ids"] = [
            row["course_id"]
            for row in own
            if row.get("identity_status") == "operator_defined"
        ]
        facility["documented_course_count"] = len(facility["documented_course_ids"])
        facility["aliases"] = [
            copy.deepcopy(row)
            for row in relationships["alias"]
            if row.get("facility_id") == identifier
        ]
        facility["round_options"] = rounds(facility_id=identifier)
        course_ids.update(row["course_id"] for row in own)
    for identifier in course_ids:
        course = courses[identifier]
        facility = facilities[course["facility_id"]]
        for field in (
            "name",
            "access",
            "operating_status",
            "physical_holes",
            "website",
        ):
            course["facility_" + field] = facility.get(field)
        for field, address_field in (
            ("state", "address_region"),
            ("country", "address_country"),
        ):
            own_address = course.get("address_mode") in {"own", "override"}
            course[field] = (
                course[address_field]
                if facility.get(field) is None
                and own_address
                and course.get(address_field) is not None
                else facility.get(field)
            )
        for field in ("county", "inventory_complete"):
            course[field] = facility.get(field)
        if course.get("address_mode") == "inherit":
            course["address"] = copy.deepcopy(facility.get("address"))
        if not course.get("osm"):
            course["map_location"] = copy.deepcopy(facility.get("map_location"))
        course["components"] = [
            child(row)
            for row in relationships["component"]
            if row["course_id"] == identifier
        ]
        course["round_options"] = rounds(course_id=identifier)
        course["tee_sets"] = [
            copy.deepcopy(row)
            for row in relationships["tee_set"]
            if row.get("course_id") == identifier
        ]
        course["aliases"] = [
            copy.deepcopy(row)
            for row in relationships["alias"]
            if row.get("course_id") == identifier
        ]
    for rows in relationships.values():
        rows.sort(key=lambda row: row["id"])


def _receipt(before, after, plan, decisions):
    snapshots, hashes = {}, {}
    for kind, key in (("facilities", "facility_id"), ("courses", "course_id")):
        old, new = _index(before[kind], key), _index(after[kind], key)
        changed = {
            identifier
            for identifier in old.keys() | new.keys()
            if old.get(identifier) != new.get(identifier)
        }
        snapshots[kind] = [
            {"index": index, "row": copy.deepcopy(row), "sha256": _sha(row)}
            for index, row in enumerate(before[kind])
            if row[key] in changed
        ]
        hashes[kind] = {
            identifier: _sha(new[identifier]) if identifier in new else None
            for identifier in sorted(changed)
        }
    metadata = {
        key: {"value": copy.deepcopy(before[key]), "sha256": _sha(before[key])}
        for key in before
        if key not in {"facilities", "courses", "rebuild"}
        and before[key] != after.get(key)
    }
    return {
        "format_version": 1,
        "plan": copy.deepcopy(plan),
        "plan_sha256": _sha(plan),
        "decisions": decisions,
        "decisions_sha256": _sha(decisions),
        "before_sha256": _catalog_sha(before),
        "after_sha256": _catalog_sha(after),
        "before": {
            "rows": snapshots,
            "metadata": metadata,
            "rebuild": {
                "value": copy.deepcopy(before.get("rebuild")),
                "sha256": _sha(before.get("rebuild")),
            },
        },
        "after": {
            "rows": hashes,
            "metadata": {key: _sha(after[key]) for key in metadata},
        },
    }


def apply_reconciliation(value, plan):
    """Return a deep copy after explicit reviewed decisions, with no matching."""
    if value.get("rebuild", {}).get("preservation", {}).get("reconciliation"):
        raise ValueError("Catalog already has a reconciliation receipt")
    decisions = _decisions(value, plan)
    result = copy.deepcopy(value)
    result["revision"] = value["revision"] + 1
    merged = {
        row["source_id"]: row["target_facility_id"]
        for row in decisions
        if row["action"] == "merge_facility"
    }
    # Rewrite operational views only; the old preservation receipts are immutable.
    for key in result:
        if key != "rebuild":
            result[key] = _facility_refs(result[key], merged)
    original_facilities = _index(value["facilities"], "facility_id")
    result["facilities"] = [
        row
        for index, row in enumerate(result["facilities"])
        if value["facilities"][index]["facility_id"]
        not in {d["source_id"] for d in decisions}
    ]
    facilities = _index(result["facilities"], "facility_id")
    courses = _index(result["courses"], "course_id")
    applied, course_ids = [], set()
    for decision in decisions:
        source_id, target_id = decision["source_id"], decision["target_facility_id"]
        source = copy.deepcopy(original_facilities[source_id])
        entry = copy.deepcopy(decision) | {
            "source_snapshot": copy.deepcopy(source),
            "source_snapshot_sha256": _sha(source),
            "conflicts": [],
        }
        if decision["action"] == "merge_facility":
            source = _facility_refs(source, {source_id: target_id})
            entry["conflicts"] = _merge_facility(
                result, facilities[target_id], source, source_id
            )
        else:
            _archive_relations(result, source_id)
            if decision["action"] in {"course", "match_course"}:
                course_id = decision.get("target_course_id") or source_id
                if course_id not in courses:
                    row = new_record(
                        source["osm"], next(iter(courses.values())), "courses"
                    )
                    row.update(
                        course_id=course_id,
                        facility_id=target_id,
                        released_id=None,
                        catalog_origin="osm",
                        osm=None,
                        osm_identity=None,
                        osm_identity_candidates=[],
                        wikidata=[],
                    )
                    entry["filled_fields"] = enrich_record(row, source["osm"])
                    withheld = decision.get("withheld_course_fields")
                    if withheld:
                        for field in withheld["fields"]:
                            if field in row:
                                row[field] = None
                        for citation in row["fact_sources"]:
                            citation["fields"] = [
                                field
                                for field in citation["fields"]
                                if field not in withheld["fields"]
                            ]
                        entry["withheld_course_fields_applied"] = copy.deepcopy(
                            withheld
                        )
                    courses[course_id] = row
                    result["courses"].append(row)
                else:
                    entry["filled_fields"] = enrich_record(
                        courses[course_id], source["osm"]
                    )
                course = courses[course_id]
                course["facility_id"] = target_id
                _attach_osm(course, source, source_id)
                if source.get("name") != course.get("name"):
                    _alias(result, "course", course_id, source.get("name"))
                course_ids.add(course_id)
                entry["applied_course_id"] = course_id
            else:
                entry["archival_scope"] = "component"
        applied.append(entry)
    removed = {row["source_id"] for row in decisions}
    # Facility estimates cannot become course arrivals or parent estimates.
    result["destinations"] = [
        row
        for row in result.get("destinations", [])
        if not (row.get("scope") == "facility_estimate" and row.get("id") in removed)
    ]
    # A merged duplicate estimate may have a different coordinate fact. Prefer
    # the target's original operational estimate and archive every original row.
    destinations = {}
    for row in result["destinations"]:
        key = (row.get("scope"), row.get("id"))
        if key not in destinations or row in value.get("destinations", []):
            destinations[key] = row
    result["destinations"] = list(destinations.values())
    _refresh(result, {row["target_facility_id"] for row in decisions}, course_ids)
    remaining_destinations = {row["id"] for row in result["destinations"]}
    for course in result["courses"]:
        if (
            course.get("destination_id") in removed
            and course["destination_id"] not in remaining_destinations
        ):
            course["destination_id"] = None
    counts = result.setdefault("rebuild", {}).setdefault("counts", {})
    for kind in ("facilities", "courses"):
        counts[kind] = len(result[kind])
        if "unnamed_" + kind in counts:
            counts["unnamed_" + kind] = sum(
                row.get("name") is None for row in result[kind]
            )
    result["rebuild"]["qualification"] = (
        "Exact stored identity build followed by frozen, reviewed ID-to-ID "
        "facility and course reconciliation. Unresolved identity and scope "
        "conflicts remain separate. Original rows, source observations, "
        "licenses and disagreements remain in preservation receipts. "
        "No entrance or bookability inference."
    )
    preservation = result["rebuild"].setdefault("preservation", {})
    preservation["reconciliation"] = _receipt(value, result, plan, applied)
    return result


def restore_before_reconciliation(value):
    """Verify the receipt and reconstruct the baseline for assert_preserved."""
    receipt = value.get("rebuild", {}).get("preservation", {}).get("reconciliation")
    if not receipt or receipt.get("format_version") != 1:
        raise ValueError("Missing reconciliation receipt")
    if _sha(receipt["plan"]) != receipt["plan_sha256"]:
        raise ValueError("Reconciliation plan digest changed")
    if _sha(receipt["decisions"]) != receipt["decisions_sha256"]:
        raise ValueError("Reconciliation decisions digest changed")
    if _catalog_sha(value) != receipt["after_sha256"]:
        raise ValueError("Reconciled catalog after digest changed")
    result = copy.deepcopy(value)
    for kind, key in (("facilities", "facility_id"), ("courses", "course_id")):
        rows = _index(result[kind], key)
        for identifier, expected in receipt["after"]["rows"][kind].items():
            actual = _sha(rows[identifier]) if identifier in rows else None
            if actual != expected:
                raise ValueError("Reconciled row after digest changed: " + identifier)
            rows.pop(identifier, None)
        result[kind] = [row for row in result[kind] if row[key] in rows]
        for snapshot in receipt["before"]["rows"][kind]:
            if _sha(snapshot["row"]) != snapshot["sha256"]:
                raise ValueError("Reconciliation before row digest changed")
            result[kind].insert(snapshot["index"], copy.deepcopy(snapshot["row"]))
    for key, snapshot in receipt["before"]["metadata"].items():
        if _sha(value.get(key)) != receipt["after"]["metadata"][key]:
            raise ValueError("Reconciliation after metadata digest changed: " + key)
        if _sha(snapshot["value"]) != snapshot["sha256"]:
            raise ValueError("Reconciliation before metadata digest changed: " + key)
        result[key] = copy.deepcopy(snapshot["value"])
    original_rebuild = receipt["before"]["rebuild"]
    if _sha(original_rebuild["value"]) != original_rebuild["sha256"]:
        raise ValueError("Reconciliation before rebuild digest changed")
    if original_rebuild["value"] is None:
        result.pop("rebuild", None)
    else:
        result["rebuild"] = copy.deepcopy(original_rebuild["value"])
    for entry in receipt["decisions"]:
        if _sha(entry["source_snapshot"]) != entry["source_snapshot_sha256"]:
            raise ValueError("Reconciliation source snapshot digest changed")
    if _catalog_sha(result) != receipt["before_sha256"]:
        raise ValueError("Reconciliation reconstructed baseline digest changed")
    return result
