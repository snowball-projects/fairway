"""Convert local Census 2025 20m boundary ZIPs to review-map SVG paths.

Build-only dependency: pyshp==3.1.6. No downloads or catalog writes.
"""

import argparse
import hashlib
import io
import json
import math
import zipfile
from itertools import pairwise
from pathlib import Path

import shapefile


def project(longitude, latitude, state):
    if state == "AK":
        longitude = longitude if longitude < 0 else longitude - 360
        return (longitude + 180) * 4.5 + 25, (72 - latitude) * 6 + 435
    if state == "HI":
        return (longitude + 161) * 19 + 250, (23 - latitude) * 19 + 490
    # Spherical Albers equal-area, parallels 29.5 and 45.5 degrees.
    phi = math.radians(latitude)
    n = (math.sin(math.radians(29.5)) + math.sin(math.radians(45.5))) / 2
    c = math.cos(math.radians(29.5)) ** 2 + 2 * n * math.sin(math.radians(29.5))
    rho = math.sqrt(c - 2 * n * math.sin(phi)) / n
    rho0 = math.sqrt(c - 2 * n * math.sin(math.radians(38))) / n
    theta = n * math.radians(longitude + 96)
    return 510 + 1100 * rho * math.sin(theta), 270 + 1100 * (
        rho * math.cos(theta) - rho0
    )


def convert(path, county):
    archive = zipfile.ZipFile(path)
    reader = shapefile.Reader(
        shp=io.BytesIO(
            archive.read(next(n for n in archive.namelist() if n.endswith(".shp")))
        ),
        dbf=io.BytesIO(
            archive.read(next(n for n in archive.namelist() if n.endswith(".dbf")))
        ),
    )
    result = []
    for item in reader.iterShapeRecords():
        record = item.record.as_dict()
        state = record["STUSPS"]
        if state == "PR":
            continue
        points = [project(x, y, state) for x, y in item.shape.points]
        parts = list(item.shape.parts) + [len(points)]
        d = "".join(
            "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in points[a:b]) + "Z"
            for a, b in pairwise(parts)
        )
        xs, ys = zip(*points)
        result.append(
            {
                "id": record["GEOID"] if county else state,
                "state": state,
                "name": record["NAMELSAD"] if county else record["NAME"],
                "d": d,
                "bounds": [
                    round(min(xs), 1),
                    round(min(ys), 1),
                    round(max(xs), 1),
                    round(max(ys), 1),
                ],
            }
        )
    return sorted(result, key=lambda item: item["id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("counties", type=Path)
    parser.add_argument("states", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = {
        "vintage": 2025,
        "scale": "1:20,000,000",
        "viewBox": [0, 0, 1000, 600],
        "sources": [
            {
                "url": f"https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_{kind}_20m.zip",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for kind, path in [("county", args.counties), ("state", args.states)]
        ],
        "counties": convert(args.counties, True),
        "states": convert(args.states, False),
    }
    args.output.write_text(json.dumps(data, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
