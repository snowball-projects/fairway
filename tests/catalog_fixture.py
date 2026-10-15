"""Synthetic SQLite fixture retained from reviewed writer1d3d841. No live inputs."""

import pytest

from fairway import catalog_store as store


def identifier(prefix, number):
    return f"{prefix}-00000000-0000-4000-8000-{number:012d}"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "catalog.sqlite"
    store.create(path)
    with store.writer(path) as connection:
        connection.execute(
            "INSERT INTO source VALUES ('operator','https://operator.example/course',NULL,NULL,'permitted')"
        )
        connection.execute(
            "INSERT INTO source VALUES ('retained','https://retained.example/course',NULL,NULL,'retained_only')"
        )
        store.put(
            connection,
            "facility",
            {
                "id": identifier("f", 1),
                "name": "Two courses",
                "physical_holes": 36,
                "inventory_complete": True,
                "latitude": 40.0,
                "longitude": -90.0,
                "location_kind": "property_point",
                "address_text": "1 Shared Street",
            },
        )
        for i, access, name in [(1, "public", "North"), (2, "private", "South")]:
            store.put(
                connection,
                "course",
                {
                    "id": identifier("c", i),
                    "facility_id": identifier("f", 1),
                    "name": name,
                    "physical_holes": 18,
                    "access": access,
                },
            )
        store.put(
            connection,
            "facility",
            {
                "id": identifier("f", 2),
                "name": "Unknown inventory",
                "physical_holes": 72,
                "inventory_complete": False,
            },
        )
        store.put(
            connection,
            "facility",
            {
                "id": identifier("f", 3),
                "name": "Documented 27",
                "physical_holes": 27,
                "inventory_complete": True,
                "latitude": 40.0,
                "longitude": 179.9,
                "location_kind": "address_range_estimate",
            },
        )
        store.put(
            connection,
            "course",
            {
                "id": identifier("c", 3),
                "facility_id": identifier("f", 3),
                "name": None,
                "physical_holes": 27,
                "access": "unknown",
            },
        )
        connection.commit()
    return path
