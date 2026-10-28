"""One maintained catalog, joined through stored OSM identities only."""

import copy
import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from .open_catalog import encoded, load_source, write_source

RELEASE = "b7481dc30fee1e9695571ecec797026ca1757fab"
RELEASE_SOURCE_KEY = "f47b895a5fc81e80ed9cbc0aa226c82683a3611464a89bfc7abb94a2f80c8160"


def checksum(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def identity(osm):
    kind, number = osm.get("type"), osm.get("id")
    if kind in {"node", "way", "relation"} and isinstance(number, int):
        return f"osm/{kind}/{number}"
    return None


def stored_bindings(root, facilities):
    """Read published ID-to-ID bindings. Names and geometry never enter the join."""
    layers = {}
    for path in (Path(root) / "data/source-layers").glob("*.json"):
        value = json.loads(path.read_text())
        by_id = defaultdict(list)
        for row in value.get("records", value.get("results", [])):
            fid = row.get("facility_id") or row.get("facility", {}).get("id")
            selected = row.get("selected_features") or (
                [row["selected_feature"]] if row.get("selected_feature") else []
            )
            if "matches" in row and row.get("status") == "supported":
                selected = row["matches"]
            for feature in selected:
                if key := identity(feature.get("osm", {})):
                    by_id[fid].append(key)
        layers[path.name] = by_id
    result = {}
    for row in facilities:
        candidates = set()
        if row.get("osm_identity"):
            candidates.add(row["osm_identity"])
        else:
            for citation in row["fact_sources"]:
                if "map_location" not in citation.get("fields", []):
                    continue
                filename = citation["source_url"].rsplit("/", 1)[-1]
                candidates.update(layers.get(filename, {}).get(row["facility_id"], []))
        result[row["facility_id"]] = sorted(candidates)
    return result


def rekey(value, mapping, field=None):
    """Rewrite typed references, never names, source IDs or narrative text."""
    references = {
        "facility_id",
        "course_id",
        "destination_id",
        "entity_id",
        "course_ids",
        "documented_course_ids",
    }
    if isinstance(value, dict):
        return {
            key: mapping.get(item, item)
            if key == "id"
            and value.get("scope") in {"facility_estimate", "course_arrival"}
            else rekey(item, mapping, key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [rekey(item, mapping, field) for item in value]
    return (
        mapping.get(value, value)
        if isinstance(value, str) and field in references
        else value
    )


def blank(template):
    row = {key: None for key in template}
    for key, value in template.items():
        if isinstance(value, list):
            row[key] = []
    row["optional"] = {key: [] for key in template["optional"]}
    return row


def source_facts(feature, wiki):
    osm = {key: value for key, value in feature.items() if key != "wikidata"}
    linked = [
        wiki["entities"][q] for q in feature["wikidata_ids"] if q in wiki["entities"]
    ]
    return osm, linked


# OSM access is legal access, not ownership or a booking promise. The catalog
# has three coarse values; exact restrictions and fee facts remain in osm.tags.
# https://wiki.openstreetmap.org/wiki/Key:access
# https://wiki.openstreetmap.org/wiki/Key:fee
OSM_ACCESS = {
    "yes": "public",
    "public": "public",
    "private": "private",
    "no": "restricted",
    "restricted": "restricted",
    "customers": "restricted",
    "permissive": "restricted",
    "permit": "restricted",
    "guests": "restricted",
    "residents": "restricted",
}


def osm_values(tags):
    """No fee-based access inference; disagreeing hole tags have no winner."""
    counts = [tags[k] for k in ("holes", "golf:holes") if tags.get(k)]
    valid = [int(v) if re.fullmatch(r"[0-9]+", v) else None for v in counts]
    holes = (
        valid[0]
        if valid and None not in valid and len(set(valid)) == 1 and valid[0] > 0
        else None
    )
    return {"access": OSM_ACCESS.get(tags.get("access")), "physical_holes": holes}


def enrich_record(row, feature):
    """Fill unknown scalar facts only. Keep known values and source disagreements."""
    filled = []
    for field, value in osm_values(feature["tags"]).items():
        if row.get(field) is None and value is not None:
            row[field] = value
            filled.append(field)
    if filled:
        row["fact_sources"].append(
            {
                "fields": filled,
                "source_kind": "osm_snapshot",
                "source_url": feature["source_url"],
                "checked_on": feature["checked_on"],
                "license": "ODbL-1.0",
                "credit": feature["credit"],
                "qualification": "OSM snapshot observation, not real-world verification. access=yes/public maps to public; private maps to private; no, restricted, customers, permissive, permit, guests and residents map to restricted. Exact access and fee tags remain in osm.tags; fee alone never establishes access. holes is used when present, otherwise golf:holes; both must agree as positive integers when present. Known released values take precedence; disagreements remain in osm.tags.",
            }
        )
    return filled


def new_record(feature, template, kind):
    row = blank(template)
    tags = feature["tags"]
    key = "facility_id" if kind == "facilities" else "course_id"
    row[key] = feature["feature_id"]
    row["name"] = feature["name"]
    row["state"] = tags.get("addr:state")
    row["country"] = tags.get("addr:country")
    row["website"] = (
        tags.get("website")
        if re.fullmatch(r"https?://[^\s]+", tags.get("website", ""))
        else None
    )
    if feature["position"]:
        lon, lat = feature["position"]
        row["map_location"] = {
            "latitude": lat,
            "longitude": lon,
            "kind": "property_point",
        }
        if kind == "facilities":
            row.update(latitude=lat, longitude=lon, location_kind="property_point")
    address = {
        "city": tags.get("addr:city"),
        "country": tags.get("addr:country"),
        "postal_code": tags.get("addr:postcode"),
        "purpose": "published_unspecified",
        "region": tags.get("addr:state"),
        "scope": "facility" if kind == "facilities" else "course",
        "street_line1": " ".join(
            filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")])
        )
        or None,
        "street_line2": None,
        "text": None,
    }
    if any(
        address[k] for k in ["city", "country", "postal_code", "region", "street_line1"]
    ):
        row["address"] = address
        for field in [
            "city",
            "country",
            "postal_code",
            "purpose",
            "region",
            "street_line1",
            "street_line2",
            "text",
        ]:
            row["address_" + field] = address[field]
    if kind == "facilities":
        row.update(
            course_count=0,
            documented_course_count=0,
            inventory_qualification="Course inventory unknown; OSM grounds do not establish individually bookable layouts.",
        )
    else:
        row.update(
            identity_status="osm_course_feature",
            plan_eligible=False,
            planning_basis="bookability_unconfirmed",
            address_mode="own",
        )
    row["fact_sources"] = [
        {
            "source_kind": "osm_snapshot",
            "source_url": feature["source_url"],
            "checked_on": feature["checked_on"],
            "license": "ODbL-1.0",
            "credit": feature["credit"],
            "fields": [
                k for k, v in row.items() if v is not None and k != "fact_sources"
            ],
            "qualification": "Source snapshot read date; real-world verification and entrance unknown. Inventory arrays describe documented records, not zero physical courses.",
        }
    ]
    return row


def rebuild(metadata, released, features, wiki, pin, bindings):
    metadata, released = copy.deepcopy(metadata), copy.deepcopy(released)
    identities = [row["feature_id"] for row in features]
    features = {row["feature_id"]: row for row in features}
    if len(features) != len(identities):
        raise ValueError("Duplicate OSM identity")
    owners = defaultdict(list)
    for old, candidates in bindings.items():
        if len(candidates) == 1 and candidates[0] in features:
            owners[candidates[0]].append(old)
    mapping = {old: osm for osm, ids in owners.items() if len(ids) == 1 for old in ids}
    # An aggregate footprint or competing stored bindings cannot equate records.
    value = rekey(metadata | released, mapping)
    indexes = {
        kind: {r[key]: r for r in value[kind]}
        for kind, key in [("facilities", "facility_id"), ("courses", "course_id")]
    }
    preservation = {"rows": {}, "metadata": {}}
    for key in ["destinations", "provenance", "relationships", "source_licenses"]:
        preservation["metadata"][key] = checksum(metadata[key])
    for kind, identity_key in [("facilities", "facility_id"), ("courses", "course_id")]:
        for original in released[kind]:
            old = original[identity_key]
            current = indexes[kind][mapping.get(old, old)]
            current.update(
                released_id=old,
                catalog_origin="matched_release" if old in mapping else "catalog_only",
                osm_identity=mapping.get(old),
                osm_identity_candidates=bindings.get(old, []),
                osm=None,
                wikidata=[],
            )
            preservation["rows"][old] = {
                "kind": kind,
                "record_id": current[identity_key],
                "sha256": checksum(original),
                "citation_count": len(original["fact_sources"]),
            }
    excluded_outlines = 0
    for key, feature in sorted(features.items()):
        if key in indexes["facilities"]:
            row = indexes["facilities"][key]
        elif key in indexes["courses"]:
            row = indexes["courses"][key]
        else:
            kind = (
                "courses" if feature["tags"].get("golf") == "course" else "facilities"
            )
            # Source observations remain in the pinned build inputs. Only new,
            # unnamed facility polygons are withheld; released facts always stay.
            if (
                kind == "facilities"
                and not feature["name"]
                and feature.get("geometry_status") == "source_polygon"
            ):
                excluded_outlines += 1
                continue
            row = new_record(feature, released[kind][0], kind)
            row.update(
                released_id=None,
                catalog_origin="osm",
                osm_identity=key,
                osm_identity_candidates=[],
            )
            value[kind].append(row)
            indexes[kind][key] = row
        filled = enrich_record(row, feature)
        if row["released_id"] and filled:
            preservation["rows"][row["released_id"]]["filled_fields"] = filled
        row["osm"], row["wikidata"] = source_facts(feature, wiki)
        row["fact_sources"].append(
            {
                "fields": ["osm", "osm_identity"],
                "source_kind": "osm_snapshot",
                "source_url": feature["source_url"],
                "checked_on": feature["checked_on"],
                "license": "ODbL-1.0",
                "credit": feature["credit"],
            }
        )
        for entity in row["wikidata"]:
            row["fact_sources"].append(
                {
                    "fields": ["wikidata"],
                    "source_kind": "explicit_wikidata_link",
                    "source_url": entity["source_url"],
                    "checked_on": entity["checked_on"],
                    "license": "CC0-1.0",
                }
            )
    for kind, identity_key in [("facilities", "facility_id"), ("courses", "course_id")]:
        value[kind].sort(key=lambda r: r[identity_key])
    value["revision"] = metadata["revision"] + 1
    value["authority"] = (
        "One maintained plain CSV catalog rebuilt from pinned OSM, released facts and explicitly linked Wikidata; GeoJSON/browser JSON are projections."
    )
    for name, license_id, url, scope in [
        (
            "OpenStreetMap contributors",
            "ODbL-1.0",
            "https://www.openstreetmap.org/copyright",
            "osm observations and derived property points",
        ),
        (
            "Wikidata",
            "CC0-1.0",
            "https://www.wikidata.org/wiki/Wikidata:Licensing",
            "explicitly linked structured claims",
        ),
    ]:
        value["source_licenses"].append(
            {
                "source": name,
                "license": license_id,
                "source_url": url,
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"
                if license_id == "CC0-1.0"
                else "https://opendatacommons.org/licenses/odbl/1-0/",
                "applies_to": scope,
            }
        )
    counts = {
        "matched_released_facilities": sum(
            r["facility_id"] in mapping for r in released["facilities"]
        ),
        "matched_released_courses": sum(
            r["course_id"] in mapping for r in released["courses"]
        ),
        "new_osm_features": len(features) - len(mapping) - excluded_outlines,
        "catalog_only_facilities": sum(
            r["facility_id"] not in mapping for r in released["facilities"]
        ),
        "catalog_only_courses": sum(
            r["course_id"] not in mapping for r in released["courses"]
        ),
        "input_osm_features": len(features),
        "excluded_unnamed_osm_outlines": excluded_outlines,
        "osm_features": len(features) - excluded_outlines,
        "facilities": len(value["facilities"]),
        "courses": len(value["courses"]),
        "unnamed_facilities": sum(r["name"] is None for r in value["facilities"]),
        "unnamed_courses": sum(r["name"] is None for r in value["courses"]),
    }
    value["rebuild"] = {
        "released_commit": RELEASE,
        "released_source_key": RELEASE_SOURCE_KEY,
        "osm_extract": pin,
        "public_catalog_policy": "New unnamed OSM facility polygons are retained in pinned build inputs only. Source points, unassembled geometry, course features and every released record remain eligible for the public catalog.",
        "map_geometry": "Pinned OSM display positions where available, otherwise the released location. Released coordinate facts remain unchanged in row fields; all display positions remain unverified as entrances.",
        "wikidata_status": wiki["status"],
        "wikidata_missing_entity_ids": wiki["missing_entity_ids"],
        "counts": counts,
        "preservation": preservation,
        "released_columns": {k: list(rows[0]) for k, rows in released.items()},
        "qualification": "Exact stored identity joins only. Multiple/absent identities remain separate catalog-only records. Facility footprint bindings do not identify individual course layouts. Missing names stay null; map labels use record kind and OSM identity. No entrance or bookability inference.",
    }
    assert_preserved(value)
    return value


def assert_preserved(value):
    if value.get("rebuild", {}).get("preservation", {}).get("reconciliation"):
        from .catalog_reconcile import restore_before_reconciliation

        value = restore_before_reconciliation(value)
    rebuild = value["rebuild"]
    inverse = {
        entry["record_id"]: old
        for old, entry in rebuild["preservation"]["rows"].items()
    }
    by_id = {
        r.get("course_id") or r["facility_id"]: r
        for kind in ["facilities", "courses"]
        for r in value[kind]
    }
    for old, receipt in rebuild["preservation"]["rows"].items():
        row = by_id[receipt["record_id"]]
        original = {k: row[k] for k in rebuild["released_columns"][receipt["kind"]]}
        original["fact_sources"] = original["fact_sources"][: receipt["citation_count"]]
        for field in receipt.get("filled_fields", []):
            if (
                field not in {"access", "physical_holes"}
                or row[field] != osm_values(row["osm"]["tags"])[field]
            ):
                raise ValueError("OSM enrichment changed: " + old)
            original[field] = None
        if checksum(rekey(original, inverse)) != receipt["sha256"]:
            raise ValueError("Released fact changed: " + old)
    for key, expected in rebuild["preservation"]["metadata"].items():
        data = value[key]
        if key == "source_licenses":
            data = data[:-2]
        if checksum(rekey(data, inverse)) != expected:
            raise ValueError("Released source/scope changed: " + key)


def build(root, work, released_root):
    source_key = hashlib.sha256(
        b"".join(
            (Path(released_root) / "data/catalog" / n).read_bytes()
            for n in ["facilities.csv", "courses.csv", "metadata.json"]
        )
    ).hexdigest()
    if source_key != RELEASE_SOURCE_KEY:
        raise ValueError("Released input differs from the pinned #56 catalog")
    metadata, released = load_source(released_root)
    inputs = {}
    input_pins = {}
    for name in ["osm-features.json", "wikidata.json", "osm-pin.json"]:
        path = Path(work) / name
        raw = (
            path.read_bytes()
            if path.exists()
            else gzip.decompress(path.with_suffix(path.suffix + ".gz").read_bytes())
        )
        inputs[name] = json.loads(raw)
        input_pins[name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    features = inputs["osm-features.json"]
    wiki = inputs["wikidata.json"]
    pin = inputs["osm-pin.json"]
    bindings = stored_bindings(released_root, released["facilities"])
    bindings.update(
        {
            r["course_id"]: [r["osm_identity"]] if r.get("osm_identity") else []
            for r in released["courses"]
        }
    )
    value = rebuild(metadata, released, features, wiki, pin, bindings)
    value["rebuild"]["build_inputs"] = input_pins
    decisions_path = Path(root) / "data/catalog-inputs/facility-reconciliation.json"
    if decisions_path.exists():
        from .catalog_reconcile import apply_reconciliation

        raw = decisions_path.read_bytes()
        value["rebuild"]["build_inputs"][decisions_path.name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        value = apply_reconciliation(value, json.loads(raw))
        assert_preserved(value)
    write_source(root, value)
    return value["rebuild"]["counts"]
