"""Reviewed course identities must not invent public access, tees or layouts."""

from pathlib import Path

import pytest

from fairway.open_catalog import load_source

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def catalog():
    _, rows = load_source(ROOT)
    return {r["facility_id"]: r for r in rows["facilities"]}, rows["courses"]


def test_colorado_uses_existing_properties_and_keeps_private_play_qualified(catalog):
    facilities, courses = catalog
    expected = {
        "osm/way/1531443170": 1,
        "osm/way/225518003": 1,
        "osm/way/35447207": 1,
        "osm/way/130458219": 1,
        "osm/relation/11372288": 1,
        "osm/relation/6930436": 2,
    }
    for fid, count in expected.items():
        facility = facilities[fid]
        layouts = [c for c in courses if c["facility_id"] == fid]
        assert len(layouts) == facility["documented_course_count"] == count
        assert facility["access"] == "private"
        assert facility["osm"]["feature_id"] == fid
        assert all(c["identity_status"] == "operator_defined" for c in layouts)
        assert all(c["arrival"] is None for c in layouts)
        assert facility["inventory_complete"] is False
        if fid != "osm/way/225518003":
            assert all(c["nonmember_bookable"] is None for c in layouts)
            assert all(c["plan_eligible"] is False for c in layouts)
        for course in layouts:
            assert any(
                s["source_kind"] == "official_site"
                and s["checked_on"] == "2026-11-02"
                and s["license"] is None
                for s in course["fact_sources"]
            )


def test_north_has_a_separate_site_and_extra_hole_outside_ordinary_round(catalog):
    facilities, courses = catalog
    north = facilities["f-ffa2ceb2-5438-4242-acc8-dbfdb4c6fa30"]
    main = facilities["osm/way/225518003"]
    assert north["address_street_line1"] == "15268 Allen Ranch Road"
    assert main["address_street_line1"] == "1880 Weiskopf Point"
    assert north["map_location"] is None and north["osm_identity"] is None
    course = next(c for c in courses if c["facility_id"] == north["facility_id"])
    assert course["physical_holes"] == north["physical_holes"] == 19
    assert [r["round_holes"] for r in course["round_options"]] == [18]
    assert len(north["course_ids"]) == 1
    ordinary = course["round_options"][0]
    assert len(ordinary["tee_sets"]) == 8
    assert all(
        tee["round_id"] == ordinary["id"]
        and tee["course_id"] is None
        and tee["par"] == 72
        and tee["yardage_unit"] is None
        and tee["rated_category"] is None
        and tee["slope"] is None
        for tee in ordinary["tee_sets"]
    )
    assert (
        next(t for t in ordinary["tee_sets"] if t["name"] == "Gold")["yardage"] == 7166
    )
    main_course = next(c for c in courses if c["facility_id"] == main["facility_id"])
    assert len(main_course["tee_sets"]) == 9
    assert any(
        citation["checked_on"] == "2026-10-15"
        and citation["source_url"].endswith("CFHN-SC.pdf")
        and citation["license"] is None
        for citation in course["fact_sources"]
    )
    for fid in (north["facility_id"], main["facility_id"]):
        layout = next(c for c in courses if c["facility_id"] == fid)
        assert layout["access"] == "private"
        assert layout["nonmember_bookable"] is True
        assert "resort guests" in layout["booking_conditions"]
        assert layout["optional"]["policy_observation"][0]["resort_stay_required"]
    assert not north["optional"]["practice_observation"]


def test_boulder_family_yardage_is_not_an_extra_physical_course(catalog):
    facilities, courses = catalog
    fid = "osm/relation/6930436"
    layouts = [c for c in courses if c["facility_id"] == fid]
    assert {(c["name"], c["physical_holes"]) for c in layouts} == {
        ("Championship Course", 18),
        ("Les Fowler Par 3 Course", 9),
    }
    assert facilities[fid]["physical_holes"] is None
    assert all(c["tee_sets"] == [] for c in layouts)
    assert next(c for c in layouts if c["physical_holes"] == 9)["style"] == "par_3"


def test_held_design_is_senior_and_monterey_totals_stay_uninvented(catalog):
    _, courses = catalog
    madeline = next(
        c for c in courses if c["course_id"] == "c-6b43cbe8-bd26-4606-be84-83e31a6e2115"
    )
    events = madeline["optional"]["architecture_event"]
    assert len(events) == 1 and events[0]["event_year"] is None
    credit = events[0]["credits"][0]
    assert credit["name"] == "Robert Trent Jones Sr."
    assert credit["party_id"] == "dp-0d496361-eb42-56ab-8051-e964102d5661"
    assert madeline["tee_sets"][0]["yardage"] == 6026
    assert madeline["tee_sets"][0]["par"] is None
    assert "prior arrangement" in madeline["booking_conditions"]
    monterey = next(
        c for c in courses if c["course_id"] == "c-a7ae369a-21ec-4192-a4b0-5462f8ed083f"
    )
    assert monterey["physical_holes"] == 9
    assert monterey["tee_sets"] == [] and monterey["style"] is None
    assert not monterey["optional"]["architecture_event"]


def test_dated_tee_totals_are_not_attributed_to_current_html(catalog):
    _, courses = catalog
    for cid, pdf_name, field in (
        ("c-23979c7b-4850-5879-8111-d506f2334c28", "CFHC-SC.pdf", "tee_sets"),
        (
            "c-e9309768-5dc6-502a-a121-1b47cf95f00d",
            "CFHN-SC.pdf",
            "round_options.tee_sets",
        ),
    ):
        course = next(c for c in courses if c["course_id"] == cid)
        html = [c for c in course["fact_sources"] if c["checked_on"] == "2026-11-02"]
        assert all(
            "tee_sets" not in field and field != "round_options"
            for citation in html
            for field in citation["fields"]
        )
        pdf = next(
            c for c in course["fact_sources"] if c["source_url"].endswith(pdf_name)
        )
        assert pdf["checked_on"] == "2026-10-15"
        assert pdf["fields"] == [field]
        if field == "round_options.tee_sets":
            assert any("round_options.round_holes" in c["fields"] for c in html)


def test_rebuild_date_does_not_change_the_pinned_osm_snapshot(catalog):
    metadata, _ = load_source(ROOT)
    assert metadata["rebuild"]["rebuilt_on"] == "2026-11-02"
    assert metadata["rebuild"]["osm_extract"]["data_through"] == "2026-10-25T21:21:21Z"
    _, courses = catalog
    greeley = next(
        c for c in courses if c["course_id"] == "c-ee4941f7-d369-54e4-bad1-67a18d7260f9"
    )
    expansion = next(
        e
        for e in greeley["optional"]["architecture_event"]
        if e["event_kind"] == "expansion"
    )
    assert expansion["source_url"] == "https://www.greeleycc.org/club/story"
    assert expansion["event_year"] is None
