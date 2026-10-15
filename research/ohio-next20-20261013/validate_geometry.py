"""Independently reproduce selected retained property points with Shapely2.1.2."""

import hashlib
import json
import sys
from pathlib import Path

from shapely.geometry import Point, shape


def validate(layer_path, delta_path):
    layer = json.loads(layer_path.read_bytes())
    delta = json.loads(delta_path.read_bytes())
    rows = {r["facility_id"]: r for r in delta["changes"]}
    assert len(rows) == len(layer["records"]) == 17
    selected_objects = set()
    selected_hashes = set()
    results = []
    for record in layer["records"]:
        osm = record["selected_feature"]["osm"]
        object_key = (osm["type"], osm["id"])
        assert object_key not in selected_objects
        selected_objects.add(object_key)
        encoded = json.dumps(
            osm["geometry"], sort_keys=True, separators=(",", ":")
        ).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        assert digest == osm["sorted_compact_geojson_sha256"]
        assert digest not in selected_hashes
        selected_hashes.add(digest)
        geometry = shape(osm["geometry"])
        assert geometry.is_valid and not geometry.is_empty
        point = geometry.representative_point()
        location = {
            "latitude": round(point.y, 8),
            "longitude": round(point.x, 8),
            "kind": "property_point",
        }
        assert geometry.contains(Point(location["longitude"], location["latitude"]))
        assert location == record["derived_map_location"]
        assert (
            location == rows[record["facility_id"]]["changes"]["map_location"]["after"]
        )
        assert record["original_map_location"] is None
        assert record["derivation"]["Census_coordinates_used_to_derive_point"] is False
        results.append(
            {
                "facility_id": record["facility_id"],
                "object": object_key,
                "geometry_valid": True,
                "independently_reproduced": True,
                "strict_contains_rounded_point": True,
            }
        )
    return {
        "selected_object_and_geometry_hash_uniqueness": True,
        "all_points_independently_reproduced": True,
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(validate(Path(sys.argv[1]), Path(sys.argv[2])), indent=2))
