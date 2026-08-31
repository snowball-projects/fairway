"""Validated, versioned golf-course catalogs."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from re import fullmatch

from .snapshots import is_https_url


@dataclass(frozen=True)
class Course:
    identifier: str
    name: str
    address: str
    routing_coordinate: tuple[float, float]
    holes: int
    access: str
    website: str
    facts_source: str
    routing_source: str
    routing_reference: str


@dataclass(frozen=True)
class CourseCatalog:
    identifier: str
    title: str
    as_of: str
    description: str
    sources: dict[str, str]
    courses: tuple[Course, ...]
    sha256: str


def load_course_catalog(path):
    """Load and validate one immutable course-catalog JSON file."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
        if (
            value["schema_version"] != 1
            or not _slug(value["id"])
            or not _text(value["title"])
            or not _text(value["description"])
            or not isinstance(value["sources"], list)
            or not isinstance(value["courses"], list)
        ):
            raise ValueError
        date.fromisoformat(value["as_of"])
        sources = {item["id"]: item["url"] for item in value["sources"]}
        if len(sources) != len(value["sources"]):
            raise ValueError
        if any(not _slug(identifier) for identifier in sources) or any(
            not is_https_url(url) for url in sources.values()
        ):
            raise ValueError
        courses = tuple(_course(item, sources) for item in value["courses"])
    except (
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError("invalid course catalog") from error
    if not courses or len({course.identifier for course in courses}) != len(courses):
        raise ValueError("invalid course catalog")
    return CourseCatalog(
        value["id"],
        value["title"],
        value["as_of"],
        value["description"],
        sources,
        courses,
        hashlib.sha256(raw).hexdigest(),
    )


def _course(value, sources):
    coordinate = value["routing_coordinate"]
    if (
        not isinstance(coordinate, list)
        or len(coordinate) != 2
        or any(type(item) not in {int, float} for item in coordinate)
    ):
        raise ValueError
    latitude, longitude = map(float, coordinate)
    if (
        not _slug(value["id"])
        or not _text(value["name"])
        or not _text(value["address"])
        or not isfinite(latitude)
        or not isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or type(value["holes"]) is not int
        or value["holes"] not in {9, 18}
        or value["access"] != "public"
        or not is_https_url(value["website"])
        or value["facts_source"] not in sources
        or value["routing_source"] not in sources
        or sources[value["routing_source"]] != "https://www.openstreetmap.org/copyright"
        or not isinstance(value["routing_reference"], str)
        or fullmatch(r"(?:node|way|relation)/[1-9][0-9]*", value["routing_reference"])
        is None
    ):
        raise ValueError
    return Course(
        value["id"],
        value["name"],
        value["address"],
        (latitude, longitude),
        value["holes"],
        value["access"],
        value["website"],
        value["facts_source"],
        value["routing_source"],
        value["routing_reference"],
    )


def _slug(value):
    return isinstance(value, str) and fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", value)


def _text(value):
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(ord(character) < 32 for character in value)
    )
