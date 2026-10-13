"""Approximate facility candidates from the existing canonical browse projection."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite
from pathlib import Path
from re import fullmatch
from urllib.parse import urlsplit

from .matrix import DestinationFailure, MatrixResult
from .scoring import canonical_milliseconds

MAX_CATALOG_BYTES = 16 * 1024 * 1024
LOCATION_KINDS = {"property_point", "reviewed_osm_point", "verified_entrance"}


@dataclass(frozen=True)
class FacilityCandidate:
    identifier: str
    name: str
    state: str
    physical_holes: int
    routing_coordinate: tuple[float, float]
    coordinate_basis: str
    public_layout_holes: tuple[int, ...]
    inventory_complete: bool
    website: str | None
    access_note: str | None
    access: str = "public"

    def layout_filter_status(self, holes):
        return (
            "confirmed" if set(holes) & set(self.public_layout_holes) else "unconfirmed"
        )


@dataclass(frozen=True)
class FacilityCatalog:
    identifier: str
    as_of: str
    sha256: str
    facilities: tuple[FacilityCandidate, ...]


def load_facility_catalog(path):
    """Reuse the packaged public-courses.json export without changing its facts."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_CATALOG_BYTES + 1)
    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError("facility catalog exceeds size bound")
    try:
        document = json.loads(raw)
        if document["schema_version"] != 3 or not isinstance(
            document["facilities"], list
        ):
            raise ValueError
        date.fromisoformat(document["updated_on"])
        candidates = []
        identifiers = set()
        for item in document["facilities"]:
            fid = item["id"]
            if (
                not isinstance(fid, str)
                or not fullmatch(r"f-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", fid)
                or fid in identifiers
            ):
                raise ValueError
            identifiers.add(fid)
            layouts = item["courses"]
            if not isinstance(layouts, list) or item.get("public_access") not in {
                None,
                "public",
                "private",
                "restricted",
                "unknown",
            }:
                raise ValueError
            public_play = item.get("public_access") == "public" or (
                item.get("public_access") is None
                and any(c["access"] == "public" for c in layouts)
            )
            location = item["map_location"]
            if (
                not public_play
                or location is None
                or location["kind"] not in LOCATION_KINDS
            ):
                continue
            physical_holes = item["physical_holes"]
            if physical_holes is None:
                continue
            coordinate = (location["latitude"], location["longitude"])
            website, note = item["website"], item.get("access_note")
            if website is not None:
                if not isinstance(website, str):
                    raise ValueError
                parsed = urlsplit(website)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    raise ValueError
            if note is not None and not isinstance(note, str):
                raise ValueError
            if (
                type(physical_holes) is not int
                or physical_holes <= 0
                or not isinstance(item["name"], str)
                or not item["name"].strip()
                or not isinstance(item["state"], str)
                or not fullmatch("[A-Z]{2}", item["state"])
                or type(item["inventory_complete"]) is not bool
                or any(
                    type(c) not in {int, float} or not isfinite(c) for c in coordinate
                )
                or not -90 <= coordinate[0] <= 90
                or not -180 <= coordinate[1] <= 180
            ):
                raise ValueError
            candidates.append(
                FacilityCandidate(
                    fid,
                    item["name"],
                    item["state"],
                    physical_holes,
                    tuple(map(float, coordinate)),
                    "property_pin"
                    if location["kind"] == "property_point"
                    else location["kind"],
                    tuple(
                        sorted(
                            {
                                c["holes"]
                                for c in layouts
                                if c["access"] == "public"
                                and type(c["holes"]) is int
                                and c["holes"] in {9, 18}
                            }
                        )
                    ),
                    item["inventory_complete"],
                    item["website"],
                    item.get("access_note"),
                )
            )
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("invalid facility catalog") from error
    if not candidates:
        raise ValueError("no mapped public facilities")
    return FacilityCatalog(
        "public-facilities-v3",
        document["updated_on"],
        hashlib.sha256(raw).hexdigest(),
        tuple(candidates),
    )


@dataclass(frozen=True)
class RankedFacility:
    facility: FacilityCandidate
    travel_times_milliseconds: tuple[int, ...]
    combined_milliseconds: int
    maximum_milliseconds: int
    rank: int = 0


@dataclass(frozen=True)
class UnrankedFacility:
    facility: FacilityCandidate
    reason: str


@dataclass(frozen=True)
class FacilityRanking:
    facilities: tuple[RankedFacility, ...]
    unranked_facilities: tuple[UnrankedFacility, ...]


def rank_facility_matrix(facilities, matrix: MatrixResult, objective):
    facilities = tuple(facilities)
    if objective not in {"combined", "maximum"}:
        raise ValueError("unknown ranking objective")
    if matrix.destination_ids != tuple(f.identifier for f in facilities) or tuple(
        d.coordinate for d in matrix.destinations
    ) != tuple(f.routing_coordinate for f in facilities):
        raise RuntimeError(
            "matrix provider changed facility identity, coordinates or order"
        )
    ranked, unranked = [], []
    for facility, destination in zip(facilities, matrix.destinations, strict=True):
        if isinstance(destination, DestinationFailure):
            unranked.append(UnrankedFacility(facility, destination.reason))
            continue
        times = canonical_milliseconds(destination.travel_times_seconds)
        if len(times) != len(matrix.origin_coordinates):
            raise RuntimeError("matrix provider changed origin dimensions")
        ranked.append(RankedFacility(facility, times, sum(times), max(times)))
    primary = f"{objective}_milliseconds"
    secondary = (
        "maximum_milliseconds" if objective == "combined" else "combined_milliseconds"
    )
    ranked.sort(
        key=lambda r: (
            getattr(r, primary),
            getattr(r, secondary),
            r.facility.name,
            r.facility.identifier,
        )
    )
    return FacilityRanking(
        tuple(replace(r, rank=i) for i, r in enumerate(ranked, 1)), tuple(unranked)
    )
