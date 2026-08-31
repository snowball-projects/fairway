"""Validated, versioned golf-course catalogs."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


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
        if value["schema_version"] != 1:
            raise ValueError
        date.fromisoformat(value["as_of"])
        sources = {item["id"]: item["url"] for item in value["sources"]}
        if len(sources) != len(value["sources"]):
            raise ValueError
        if any(not _url(url) for url in sources.values()):
            raise ValueError
        courses = tuple(_course(item, sources) for item in value["courses"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
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
    latitude, longitude = map(float, value["routing_coordinate"])
    if (
        not value["id"]
        or not value["name"]
        or not value["address"]
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or value["holes"] not in {9, 18}
        or value["access"] not in {"public", "private"}
        or not _url(value["website"])
        or value["facts_source"] not in sources
        or value["routing_source"] not in sources
        or not value["routing_reference"]
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


def _url(value):
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)
