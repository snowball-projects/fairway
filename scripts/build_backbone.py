"""Rebuild the maintained golf catalog from one pinned US PBF and Wikidata.

No routing graph, travel times or network paths are computed.
"""

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AGENT = "fairway-backbone/1.0 (https://github.com/snowball-projects/fairway)"
TAGS = frozenset(
    [
        "name",
        "name:en",
        "official_name",
        "short_name",
        "alt_name",
        "leisure",
        "golf",
        "holes",
        "golf:holes",
        "par",
        "access",
        "fee",
        "website",
        "wikidata",
        "wikipedia",
        "architect",
        "designer",
        "addr:street",
        "addr:housenumber",
        "addr:city",
        "addr:state",
        "addr:postcode",
        "addr:country",
        "check_date",
        "check_date:holes",
        "check_date:access",
    ]
)
PROPERTIES = frozenset(
    [
        "P31",
        "P17",
        "P131",
        "P361",
        "P527",
        "P625",
        "P856",
        "P571",
        "P576",
        "P84",
        "P2046",
    ]
)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")
QUERY = "SELECT DISTINCT ?item WHERE { ?item wdt:P17 wd:Q30; wdt:P31/wdt:P279* wd:Q1048525. } ORDER BY ?item"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def clean_text(value):
    if value.lower().startswith(("mailto:", "tel:")):
        return None
    return PHONE.sub("[contact removed]", EMAIL.sub("[contact removed]", value))


def source_tags(tags):
    return {
        key: clean_text(value)
        for key, value in tags.items()
        if key in TAGS and clean_text(value) is not None
    }


def qids(value):
    return sorted(set(re.findall(r"\bQ[1-9][0-9]*\b", value or "")))


def request_json(url):
    request = Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=60) as response:
        body = response.read(32 * 1024 * 1024 + 1)
    if len(body) > 32 * 1024 * 1024:
        raise ValueError("Source response exceeds bounded request size")
    return json.loads(body)


def hash_file(path):
    sha = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            sha.update(block)
            md5.update(block)
    return sha.hexdigest(), md5.hexdigest()


def extract(args):
    import osmium
    from shapely.geometry import shape

    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    sha, md5 = hash_file(args.pbf)
    if md5 != args.md5:
        raise ValueError("PBF does not match the pinned publisher checksum")
    with osmium.io.Reader(str(args.pbf), osmium.osm.osm_entity_bits.NOTHING) as reader:
        header = reader.header()
        header_pin = {
            key: header.get(key)
            for key in [
                "generator",
                "timestamp",
                "osmosis_replication_timestamp",
                "osmosis_replication_sequence_number",
                "sorting",
            ]
            if header.get(key)
        }
    if (
        header_pin.get("osmosis_replication_timestamp")
        and header_pin["osmosis_replication_timestamp"] != args.source_date
    ):
        raise ValueError("PBF header does not match the pinned snapshot date")
    pin = {
        "url": args.source_url,
        "bytes": args.pbf.stat().st_size,
        "sha256": sha,
        "publisher_md5": md5,
        "data_through": args.source_date,
        "header": header_pin,
        "checked_on": args.checked_on,
        "license": "ODbL-1.0",
        "credit": "© OpenStreetMap contributors",
        "license_url": "https://www.openstreetmap.org/copyright",
    }
    records = {}
    thematic = work / "golf-with-references.osm.pbf"
    processor = osmium.FileProcessor(str(args.pbf)).with_filter(
        osmium.filter.TagFilter(("leisure", "golf_course"), ("golf", "course"))
    )
    with osmium.BackReferenceWriter(
        str(thematic), ref_src=str(args.pbf), relation_depth=3
    ) as writer:
        for obj in processor:
            kind = "node" if obj.is_node() else "way" if obj.is_way() else "relation"
            identity = f"osm/{kind}/{obj.id}"
            tags = source_tags(dict(obj.tags))
            records[identity] = {
                "feature_id": identity,
                "osm_type": kind,
                "osm_id": obj.id,
                "osm_version": obj.version,
                "osm_last_edit": obj.timestamp.isoformat().replace("+00:00", "Z"),
                "source_url": f"https://www.openstreetmap.org/api/0.6/{kind}/{obj.id}/{obj.version}",
                "checked_on": args.checked_on,
                "snapshot_date": args.source_date,
                "license": "ODbL-1.0",
                "credit": "© OpenStreetMap contributors",
                "name": tags.get("name") or tags.get("name:en"),
                "tags": tags,
                "wikidata_ids": qids(tags.get("wikidata")),
                "member_feature_ids": [
                    f"osm/{ {'n': 'node', 'w': 'way', 'r': 'relation'}[m.type] }/{m.ref}"
                    for m in obj.members
                ]
                if obj.is_relation()
                else [],
                "position": None,
                "position_kind": "unknown",
                "geometry_status": "not_assembled",
                "identity_scope": "source golf feature; facility/course decomposition unverified",
                "independent_booking": None,
                "arrival": None,
            }
            writer.add(obj)
    print("Filtered golf features:", len(records), flush=True)
    factory = osmium.geom.GeoJSONFactory()
    failures = Counter()
    for obj in osmium.FileProcessor(str(thematic)).with_locations().with_areas():
        if obj.is_node():
            row = records.get(f"osm/node/{obj.id}")
            if row and obj.location.valid():
                row["position"] = [obj.location.lon, obj.location.lat]
                row["position_kind"] = "source_node"
                row["geometry_status"] = "source_point"
        elif obj.is_area():
            kind = "way" if obj.from_way() else "relation"
            row = records.get(f"osm/{kind}/{obj.orig_id()}")
            if row:
                try:
                    geometry = shape(json.loads(factory.create_multipolygon(obj)))
                    if geometry.is_empty or not geometry.is_valid:
                        row["geometry_status"] = "invalid_source_polygon"
                        failures[row["geometry_status"]] += 1
                        continue
                    point = geometry.representative_point()
                    row["position"] = [point.x, point.y]
                    row["position_kind"] = "derived_inside_source_polygon"
                    row["geometry_status"] = "source_polygon"
                except (RuntimeError, ValueError):
                    row["geometry_status"] = "assembly_failed"
                    failures[row["geometry_status"]] += 1
    # Only explicit source relation membership is retained. Polygon containment,
    # matching names and shared QIDs never establish course/facility identity.
    for row in records.values():
        row["member_feature_ids"] = [
            x for x in row["member_feature_ids"] if x in records
        ]
    (work / "osm-features.json").write_text(encoded(list(records.values())) + "\n")
    (work / "osm-pin.json").write_text(encoded(pin) + "\n")
    print(
        encoded(
            {
                "features": len(records),
                "geometry": dict(
                    Counter(r["geometry_status"] for r in records.values())
                ),
                "failures": dict(failures),
                "thematic_bytes": thematic.stat().st_size,
            }
        ),
        flush=True,
    )


def refresh_tags(args):
    """Recover whitelisted tags from the exact PBF without re-fetching Wikidata."""
    import gzip

    import osmium

    path = args.work / "osm-features.json"
    raw = (
        path.read_bytes()
        if path.exists()
        else gzip.decompress(path.with_suffix(".json.gz").read_bytes())
    )
    rows = json.loads(raw)
    pin = json.loads((args.work / "osm-pin.json").read_text())
    sha, md5 = hash_file(args.pbf)
    if (
        sha != pin["sha256"]
        or md5 != pin["publisher_md5"]
        or args.pbf.stat().st_size != pin["bytes"]
    ):
        raise ValueError("PBF differs from the pinned catalog input")
    by_id = {r["feature_id"]: r for r in rows}
    seen = set()
    for obj in osmium.FileProcessor(str(args.pbf)).with_filter(
        osmium.filter.TagFilter(("leisure", "golf_course"), ("golf", "course"))
    ):
        kind = "node" if obj.is_node() else "way" if obj.is_way() else "relation"
        key = f"osm/{kind}/{obj.id}"
        row = by_id[key]
        if row["osm_version"] != obj.version:
            raise ValueError("OSM feature version differs: " + key)
        # Preserve every existing observation, including approved privacy exclusions.
        tags = source_tags(dict(obj.tags))
        for tag in TAGS - {"wikidata"}:
            if tag in tags:
                if tag in row["tags"] and row["tags"][tag] != tags[tag]:
                    raise ValueError("OSM observation differs: " + key + " " + tag)
                row["tags"][tag] = tags[tag]
        seen.add(key)
    if seen != set(by_id):
        raise ValueError("OSM feature identities differ from pinned input")
    path.write_text(encoded(rows) + "\n")
    print("Refreshed pinned OSM tags:", len(rows))


def claim_projection(claim):
    # Structured claims and source references only; no page prose or media copies.
    return {
        "id": claim.get("id"),
        "rank": claim.get("rank"),
        "value": claim.get("mainsnak", {}).get("datavalue", {}).get("value"),
        "snaktype": claim.get("mainsnak", {}).get("snaktype"),
        "qualifiers": {
            key: values
            for key, values in claim.get("qualifiers", {}).items()
            if key in {"P580", "P582", "P585"}
        },
        "references": [
            {
                key: values
                for key, values in ref.get("snaks", {}).items()
                if key in {"P248", "P854", "P813"}
            }
            for ref in claim.get("references", [])
        ],
    }


def clean_structure(value):
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [clean_structure(x) for x in value]
    if isinstance(value, dict):
        return {key: clean_structure(x) for key, x in value.items()}
    return value


def selection_snapshot(national, linked, query_url, checked_on):
    """Keep the successful query's facts even when entity detail reads must wait."""
    return {
        "checked_on": checked_on,
        "license": "CC0-1.0",
        "license_url": "https://www.wikidata.org/wiki/Wikidata:Licensing",
        "query": QUERY,
        "query_url": query_url,
        "national_query_count": len(national),
        "linked_osm_count": len(linked),
        "status": "selection_only",
        "missing_entity_ids": [],
        "entities": {
            qid: {
                "id": qid,
                "lastrevid": None,
                "modified": None,
                "label": None,
                "source_url": query_url,
                "checked_on": checked_on,
                "from_national_query": True,
                "claims": {},
                "qualification": "Query membership only; entity details and revision unknown.",
            }
            for qid in sorted(national)
        },
        "excluded_human_targets": [],
    }


def enrich(args):
    rows = json.loads((args.work / "osm-features.json").read_text())
    linked = {qid for row in rows for qid in row["wikidata_ids"]}
    query_url = "https://query.wikidata.org/sparql?" + urlencode(
        {"query": QUERY, "format": "json"}
    )
    query = request_json(query_url)
    national = {
        row["item"]["value"].rsplit("/", 1)[-1] for row in query["results"]["bindings"]
    }
    identities = sorted(linked | national)
    snapshot = selection_snapshot(national, linked, query_url, args.checked_on)
    for start in range(0, len(identities), 50):
        group = identities[start : start + 50]
        url = "https://www.wikidata.org/w/api.php?" + urlencode(
            {
                "action": "wbgetentities",
                "format": "json",
                "ids": "|".join(group),
                "props": "labels|claims|info",
                "languages": "en",
                "maxlag": 5,
            }
        )
        response = request_json(url)
        if "error" in response:
            snapshot["blocked_reason"] = response["error"].get("code", "unknown")
            break
        for qid, entity in response["entities"].items():
            if "missing" in entity:
                snapshot["missing_entity_ids"].append(qid)
                if qid in snapshot["entities"]:
                    snapshot["entities"][qid]["entity_status"] = "missing_at_read"
                continue
            kinds = {
                c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                for c in entity.get("claims", {}).get("P31", [])
            }
            if "Q5" in kinds:
                snapshot["excluded_human_targets"].append(qid)
                snapshot["entities"].pop(qid, None)
                continue
            snapshot["entities"][qid] = {
                "id": qid,
                "lastrevid": entity.get("lastrevid"),
                "modified": entity.get("modified"),
                "label": entity.get("labels", {}).get("en", {}).get("value"),
                "source_url": f"https://www.wikidata.org/w/index.php?title={qid}&oldid={entity['lastrevid']}",
                "checked_on": args.checked_on,
                "from_national_query": qid in national,
                "claims": {
                    key: [claim_projection(c) for c in claims]
                    for key, claims in entity.get("claims", {}).items()
                    if key in PROPERTIES
                },
            }
        print(
            f"Wikidata items: {min(start + 50, len(identities))}/{len(identities)}",
            flush=True,
        )
        time.sleep(0.25)
    else:
        snapshot["status"] = "entity_reads_complete"
    # Human targets are omitted from public files, including their IDs/labels.
    excluded = set(snapshot.pop("excluded_human_targets"))
    snapshot["excluded_human_target_count"] = len(excluded)
    for row in rows:
        row["wikidata_ids"] = [
            qid for qid in row["wikidata_ids"] if qid not in excluded
        ]
        if excluded & set(qids(row["tags"].get("wikidata"))):
            row["tags"].pop("wikidata", None)
    (args.work / "osm-features.json").write_text(encoded(rows) + "\n")
    (args.work / "wikidata.json").write_text(encoded(clean_structure(snapshot)) + "\n")
    if snapshot.get("blocked_reason"):
        raise ValueError("Wikidata source error: " + snapshot["blocked_reason"])


def publish_files(args):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from fairway.rebuild_catalog import build

    print(json.dumps(build(args.output, args.work, args.released_root), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["extract", "refresh-tags", "enrich", "write"])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--pbf", type=Path)
    parser.add_argument("--md5")
    parser.add_argument("--source-url")
    parser.add_argument("--source-date")
    parser.add_argument("--checked-on", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--output", type=Path, default=Path("."))
    parser.add_argument("--released-root", type=Path)
    args = parser.parse_args()
    if args.stage == "extract":
        if not all([args.pbf, args.md5, args.source_url, args.source_date]):
            parser.error(
                "extract requires --pbf, --md5, --source-url and --source-date"
            )
        extract(args)
    elif args.stage == "refresh-tags":
        if not args.pbf:
            parser.error("refresh-tags requires --pbf")
        refresh_tags(args)
    elif args.stage == "enrich":
        enrich(args)
    else:
        if not args.released_root:
            parser.error(
                "write requires --released-root with the pinned released catalog"
            )
        publish_files(args)


if __name__ == "__main__":
    main()
