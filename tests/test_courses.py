import json

import pytest

from fairway.courses import load_course_catalog


def test_loads_published_course_catalog():
    catalog = load_course_catalog("data/course-catalog-v1.json")
    assert catalog.identifier == "chicago-public-courses-v1"
    assert catalog.as_of == "2026-08-30"
    assert len(catalog.sha256) == 64
    assert len(catalog.courses) == 8
    assert {course.holes for course in catalog.courses} == {9, 18}
    assert {course.access for course in catalog.courses} == {"public"}
    assert len({course.identifier for course in catalog.courses}) == 8
    assert all(course.routing_reference for course in catalog.courses)
    indian_boundary = next(
        course for course in catalog.courses if course.identifier == "indian-boundary"
    )
    assert indian_boundary.address == (
        "8600 W Forest Preserve Avenue, Chicago, IL 60634"
    )


def valid_catalog():
    return {
        "schema_version": 1,
        "id": "test-v1",
        "title": "Test courses",
        "as_of": "2026-08-30",
        "description": "Test catalog.",
        "sources": [
            {"id": "facts", "url": "https://example.com/facts"},
            {
                "id": "routing",
                "url": "https://www.openstreetmap.org/copyright",
            },
        ],
        "courses": [
            {
                "id": "one",
                "name": "Course One",
                "address": "1 Test Way",
                "routing_coordinate": [41.9, -87.7],
                "holes": 9,
                "access": "public",
                "website": "https://example.com/course",
                "facts_source": "facts",
                "routing_source": "routing",
                "routing_reference": "node/1",
            }
        ],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"as_of": "tomorrow"},
        {"courses": []},
        {"sources": [{"id": "facts", "url": "http://example.com"}]},
    ],
)
def test_rejects_invalid_catalog_roots(tmp_path, change):
    value = valid_catalog()
    value.update(change)
    path = tmp_path / "courses.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="invalid course catalog"):
        load_course_catalog(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("holes", 12),
        ("access", "unknown"),
        ("routing_coordinate", [91, 0]),
        ("website", "javascript:alert(1)"),
        ("website", "https://user@example.com/course"),
        ("facts_source", "missing"),
        ("routing_reference", ""),
        ("routing_reference", "node/not-a-number"),
        ("access", "private"),
    ],
)
def test_rejects_invalid_course_fields(tmp_path, field, value):
    catalog = valid_catalog()
    catalog["courses"][0][field] = value
    path = tmp_path / "courses.json"
    path.write_text(json.dumps(catalog))
    with pytest.raises(ValueError, match="invalid course catalog"):
        load_course_catalog(path)
