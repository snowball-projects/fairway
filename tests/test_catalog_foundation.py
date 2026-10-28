"""Native publication preserves legacy identities, unknowns and course scope."""

import gzip
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def catalog():
    return json.loads(
        gzip.decompress((ROOT / "data/catalog-release/catalog.json.gz").read_bytes())
    )


def test_legacy_ids_mixed_access_and_nulls_survive(catalog):
    lake = next(f for f in catalog["facilities"] if f["name"] == "Lake of Isles")
    assert lake["released_id"] == "f-f6463598-f26c-404e-9584-2abace25109d"
    assert lake["facility_id"] == lake["osm_identity"]
    assert lake["physical_holes"] == 36
    courses = {
        c["name"]: c
        for c in catalog["courses"]
        if c["facility_id"] == lake["facility_id"]
    }
    assert (
        courses["North"]["access"] == "public"
        and courses["South"]["access"] == "private"
    )
    win = next(f for f in catalog["facilities"] if f["name"] == "Winagamie Golf Course")
    assert win["physical_holes"] is None and win["inventory_complete"] is False
    twigs = next(
        c
        for c in catalog["courses"]
        if c["facility_id"] == win["facility_id"] and c["name"] == "TWIGS"
    )
    assert (
        twigs["physical_holes"] is None
        and twigs["access"] is None
        and twigs["arrival"] is None
    )


def test_native_inventory_never_promotes_components_or_private_booking(catalog):
    blackhawk = next(
        f
        for f in catalog["facilities"]
        if f["name"] == "Blackhawk Country Club" and f["state"] == "CA"
    )
    courses = [
        c for c in catalog["courses"] if c["facility_id"] == blackhawk["facility_id"]
    ]
    assert blackhawk["physical_holes"] == 36 and len(courses) == 2
    assert {c["name"] for c in courses} == {"Lakeside Course", "Falls Course"}
    assert all(
        c["identity_status"] == "operator_defined"
        and c["access"] == "private"
        and c["nonmember_bookable"] is None
        and not c["tee_sets"]
        for c in courses
    )
    assert sum(c["identity_status"] == "component" for c in catalog["courses"]) == 17


def test_all_native_relationships_and_public_evidence_are_preserved(catalog):
    assert (
        sum(len(f["course_ids"]) for f in catalog["facilities"]) == 4951
        and len(catalog["courses"]) == 4985
    )
    assert len(catalog["provenance"]["notes"]) == 8286
    assert all(set(note) == {"id"} for note in catalog["provenance"]["notes"])
    assert len(catalog["provenance"]["sources"]) == 19030
    assert len(catalog["provenance"]["intake"]) == 15186
    assert sum(c["arrival"] is not None for c in catalog["courses"]) == 8
    assert (
        not {"retained_document", "source_hold", "source_hold_scope"} & catalog.keys()
    )
    assert all("controls_reference" not in item for item in catalog["source_licenses"])


def test_existing_facility_course_roles_do_not_inherit_totals_or_offered_rounds(
    catalog,
):
    def courses(facility_id):
        current = next(
            f["facility_id"]
            for f in catalog["facilities"]
            if f["released_id"] == facility_id
        )
        return [c for c in catalog["courses"] if c["facility_id"] == current]

    heron = courses("f-bdb8f9c8-e82c-477d-9472-0af471020bb1")
    assert len(heron) == 1
    assert heron[0]["facility_physical_holes"] == 18
    assert heron[0]["name"] is None and heron[0]["physical_holes"] is None
    assert heron[0]["access"] is None and heron[0]["nonmember_bookable"] is None

    common = courses("f-21a4fe0c-9956-468d-b154-72ea65ca6277")
    assert sorted(c["physical_holes"] for c in common) == [9, 18]
    green_knoll = courses("f-cbbe0345-832e-429c-920a-89494396796f")
    assert sorted(c["physical_holes"] for c in green_knoll) == [9, 18]
    assert {c["name"] for c in green_knoll} == {None, "Pitch and Putt Course"}

    brighton = courses("f-003187f4-8960-444f-a278-7074245e13fc")
    assert {c["name"]: c["physical_holes"] for c in brighton} == {
        "White Birch": 18,
        "Blue Spruce": 18,
        "Red Pine": 9,
    }
    for fid, names in [
        (
            "f-0333909f-6f6d-42bc-bf0f-9c32121519c3",
            {"Thistle", "Pine Cone", "Foxglove"},
        ),
        ("f-040ec089-0f4b-4173-9969-8daf2ed6a718", {"North", "South", "West"}),
    ]:
        layouts = courses(fid)
        assert len(layouts) == 3 and {c["name"] for c in layouts} == names
        assert all(c["physical_holes"] == 9 for c in layouts)
        assert all(c["identity_status"] == "operator_defined" for c in layouts)

    pheasant = courses("f-0273cf4c-e3eb-43d5-9090-d686dc8d2c69")
    assert len(pheasant) == 1 and pheasant[0]["physical_holes"] == 18
    for fid in [
        "f-041e7d6d-1b2a-4ef7-adb1-fb38a41fd27d",  # Closed reconstruction context.
        "f-049e4cc4-43da-4945-91f5-dc8b53653b4f",  # Held card is not count evidence.
        "f-02c13ff2-5af6-41a7-9ac1-c67a48c1498f",  # Par/metrics are not a count.
    ]:
        records = courses(fid)
        assert len(records) == 1 and records[0]["physical_holes"] is None
        assert records[0]["operating_status"] is None
    assert all(
        c["inventory_complete"] is False for c in common + green_knoll + brighton
    )


def test_new_individual_identities_keep_partial_counts_and_round_boundaries(catalog):
    def courses(facility_id):
        current = next(
            f["facility_id"]
            for f in catalog["facilities"]
            if f["released_id"] == facility_id
        )
        return [c for c in catalog["courses"] if c["facility_id"] == current]

    legends = courses("f-08ab8d77-8ad8-4b41-aa42-97e71d70e21c")
    assert {c["name"]: c["physical_holes"] for c in legends} == {
        "EAST": 9,
        "SOUTH": 9,
        "NORTH": 9,
    }
    bangor = courses("f-062a1815-30b9-416e-8335-e91e08f5913d")
    assert {c["name"]: c["physical_holes"] for c in bangor} == {
        "Championship Course": None,
        "Kelly Nine": 9,
    }
    ocn = courses("f-0dcafd54-4360-4899-8c8a-9a24fc7702ab")
    assert {c["name"]: c["physical_holes"] for c in ocn} == {
        "Crooked Cat": None,
        "Panther Lake": None,
        "Tooth": 9,
    }
    greenville = courses("f-eccc1370-8ba5-4858-a608-8853b61a7a35")
    assert len(greenville) == 1
    assert greenville[0]["name"] is None
    assert greenville[0]["physical_holes"] is None
    assert greenville[0]["facility_physical_holes"] == 12
    five_waters = courses("f-07734373-1c22-4cfe-9cb8-dc662cb8e8a6")
    assert len(five_waters) == 2
    assert all(c["name"] is None for c in five_waters)
    assert {c["physical_holes"] for c in five_waters} == {9, None}
    for course in legends + bangor + ocn + greenville + five_waters:
        assert course["access"] is None
        assert course["nonmember_bookable"] is None
        assert course["style"] is None
        assert course["operating_status"] is None
        assert course["arrival"] is None
        assert course["inventory_complete"] is False


def test_reviewed_1089_keeps_short_courses_and_unknown_counts_distinct(catalog):
    def courses(facility_id):
        current = next(
            f["facility_id"]
            for f in catalog["facilities"]
            if f["released_id"] == facility_id
        )
        return [c for c in catalog["courses"] if c["facility_id"] == current]

    mid_vallee = courses("f-0ca2b774-f58c-4cc3-a1c6-a6fc86661d26")
    assert {c["name"]: c["physical_holes"] for c in mid_vallee} == {
        "Red Nine": 9,
        "White Nine": 9,
        "Blue Nine": 9,
    }
    randall = courses("f-0e0ffa09-a089-4635-8da5-cf071441ee6a")
    assert {c["name"]: c["physical_holes"] for c in randall} == {
        "Randall Oaks Golf Club": 18,
        "Acorn Course": 3,
        "The Links Learning Center": 4,
    }
    mount_ayr = courses("f-0d07895a-7d6c-4985-8043-70786a96236c")
    assert len(mount_ayr) == 1
    assert mount_ayr[0]["name"] is None
    assert mount_ayr[0]["physical_holes"] is None
    partials = []
    for fid in [
        "f-10e1344e-daea-4632-9954-7e89d04bb14c",  # Duke's tour is partial.
        "f-1108cc89-893b-4474-b991-26d8543f1935",  # Taos offers scoring rounds.
    ]:
        records = courses(fid)
        assert len(records) == 1
        assert records[0]["physical_holes"] is None
        partials.extend(records)
    for course in mid_vallee + randall + mount_ayr + partials:
        assert course["access"] is None
        assert course["nonmember_bookable"] is None
        assert course["style"] is None
        assert course["operating_status"] is None
        assert course["arrival"] is None
        assert course["inventory_complete"] is False


def test_reviewed_1124_keeps_unnamed_nines_and_status_unknowns(catalog):
    def courses(facility_id):
        current = next(
            f["facility_id"]
            for f in catalog["facilities"]
            if f["released_id"] == facility_id
        )
        return [c for c in catalog["courses"] if c["facility_id"] == current]

    heron = courses("f-17991622-233c-4bc1-9b43-d0cbb77ca22b")
    assert {c["name"]: c["physical_holes"] for c in heron} == {
        "Oaks Course": 9,
        "Creek Course": 9,
        "Marsh Course": 9,
    }
    unnamed_nines = []
    for fid in [
        "f-16f6088a-9053-4495-b868-3db97b4a9130",  # Twin Oaks.
        "f-18521e40-c1ba-46da-9725-c11b68a1d1a3",  # Fellows Creek.
    ]:
        records = courses(fid)
        assert len(records) == 3
        assert all(c["name"] is None and c["physical_holes"] == 9 for c in records)
        unnamed_nines.extend(records)
    jester = courses("f-153f8613-a9e6-4a04-835f-31f1341430ab")
    assert len(jester) == 2
    assert sorted(c["physical_holes"] for c in jester) == [9, 18]
    assert all(c["name"] is None for c in jester)
    westwind = courses("f-1694333b-001e-4fb0-b8fd-65e08f9fad79")
    assert len(westwind) == 1
    assert westwind[0]["name"] is None
    assert westwind[0]["physical_holes"] is None
    for course in heron + unnamed_nines + jester + westwind:
        for field in [
            "access",
            "nonmember_bookable",
            "style",
            "operating_status",
            "arrival",
        ]:
            assert course[field] is None
        assert course["inventory_complete"] is False


def test_completion_1138_keeps_physical_identity_and_arrivals_separate(catalog):
    by_id = {c["course_id"]: c for c in catalog["courses"]}
    kinzua = by_id["c-1608bfb4-18bf-459f-8fa4-5608ade2ae6b"]
    assert kinzua["name"] == "Kinzua Hills Golf Club"
    assert kinzua["physical_holes"] == 6
    sunserra = by_id["c-38a1ebc1-0d53-40d5-ae4b-9dbe367a51c7"]
    assert sunserra["physical_holes"] == 9 and sunserra["style"] == "par_3"
    for cid in [
        "c-18ed1f25-2590-489d-b3aa-72a9563632ed",  # Tired Creek.
        "c-0b354fea-837a-4099-9b30-03965ed7db8e",  # Caswell Pines.
        "c-0f0b0bec-7173-403a-b3fb-e6385a3acf07",  # Space Coast.
    ]:
        course = by_id[cid]
        assert course["physical_holes"] == 18
        assert course["arrival"] is None and course["operating_status"] is None
        assert course["nonmember_bookable"] is None
        assert course["inventory_complete"] is False
    assert by_id["c-0b354fea-837a-4099-9b30-03965ed7db8e"]["access"] == "public"
    space = by_id["c-0f0b0bec-7173-403a-b3fb-e6385a3acf07"]
    assert space["map_location"]["kind"] == "address_range_estimate"


def test_completion_1138_contacts_do_not_resolve_location_conflicts(catalog):
    facilities = {
        f["released_id"]: f
        for f in catalog["facilities"]
        if f["released_id"] is not None
    }
    tired = facilities["f-189e5a35-f1a3-44fa-bc45-73ba7f0ca5d8"]
    assert tired["address"]["street_line1"] == "1701 US-84"
    assert tired["address"]["purpose"] == "contact"
    assert tired["address"]["postal_code"] is None
    assert "39827" in tired["address"]["text"]
    assert tired["map_location"] is None
    firestone = facilities["f-000bc9d5-0b8f-4f35-a5f8-e07f8d499f23"]
    assert firestone["address"]["city"] == "Columbiana"
    assert firestone["address"]["postal_code"] == "44408"
    assert firestone["map_location"] is None


def test_completion_1138_booking_keeps_conditions_and_tee_unknowns(catalog):
    by_id = {c["course_id"]: c for c in catalog["courses"]}
    for cid, required in [
        ("c-bf4f83ad-c1dd-4529-bdad-b00a9b26257e", ["7 days", "14-day", "after 10am"]),
        (
            "c-6b43cbe8-bd26-4606-be84-83e31a6e2115",
            ["prior arrangement", "advance tee time", "ferry"],
        ),
        (
            "c-a7ae369a-21ec-4192-a4b0-5462f8ed083f",
            ["weather allows", "email ahead", "driver"],
        ),
    ]:
        course = by_id[cid]
        assert course["nonmember_bookable"] is True
        assert course["planning_basis"] == "explicit_nonmember_fact"
        assert course["booking_availability"] is None and course["arrival"] is None
        assert all(word in course["booking_conditions"] for word in required)
    madeline = by_id["c-6b43cbe8-bd26-4606-be84-83e31a6e2115"]
    white = next(
        t
        for t in madeline["tee_sets"]
        if t["id"] == "t-ad4ff0cd-38d6-5021-a17b-f03b9017faba"
    )
    assert white["name"] == "white" and white["yardage"] == 6026
    assert white["slope"] == 119 and white["yardage_unit"] == "yards"
    assert all(white[k] is None for k in ["par", "difficulty_rating", "rated_category"])


def test_completion_1138_prices_keep_relative_time_and_age_conditions(catalog):
    prices = {
        row["id"]: row
        for entity in catalog["facilities"] + catalog["courses"]
        for row in entity["optional"]["price_observation"]
    }
    twilight = prices["n-3e0eb819-8309-5802-93b1-ee8f446480fc"]
    assert twilight["amount_min"] == twilight["amount_max"] == 25
    assert twilight["cart_included"] is True
    assert "SUNSET" in twilight["conditions"]
    assert twilight["start_minute_of_day"] is None
    senior = prices["n-00565a92-6d27-516d-aed5-b136bb0b1e0c"]
    assert senior["minimum_age"] == 62 and senior["end_minute_of_day"] == 900
    assert senior["cart_included"] is False
    assert senior["applies_on_holidays"] is False
    assert senior["weekday_mask"] == 31
    assert "NOT tournaments, holidays or weekends" in senior["conditions"]
    assert "tournaments" in senior["conditions"]
    for price in [twilight, senior]:
        assert all(price[k] is None for k in ["currency", "billing_basis"])
        assert price["collected_on"] == "2026-10-18"
        assert price["amount_kind"] == "exact"
        assert price["fee_kind"] == "green_fee"


def test_corrected_prices_structure_source_qualifiers_without_defaulting_unknowns(
    catalog,
):
    prices = {
        row["id"]: row
        for subject in catalog["facilities"] + catalog["courses"]
        for row in subject["optional"]["price_observation"]
    }
    holiday = prices["n-fc31ef43-3cf2-5e11-a457-4bc003f07f44"]
    assert holiday["applies_on_holidays"] is True
    assert holiday["weekday_mask"] is None
    assert holiday["cart_included"] is False
    junior = prices["n-cf5e21c0-65c8-5190-a56d-f2f100b94bd8"]
    assert (junior["audience"], junior["minimum_age"], junior["maximum_age"]) == (
        "junior",
        7,
        17,
    )
    assert junior["weekday_mask"] == 31 and junior["applies_on_holidays"] is None
    cart = prices["n-bae45594-1b08-5323-a9cc-00467a1f594a"]
    assert (cart["fee_kind"], cart["billing_basis"], cart["amount_kind"]) == (
        "golf_cart",
        "per_person",
        "exact",
    )
    member = prices["n-f9840f40-1195-5542-84c8-48252844f75f"]
    assert member["fee_kind"] == "membership" and member["audience"] == "senior"
    assert member["minimum_age"] is None and member["billing_basis"] is None
    balls = prices["n-85c38733-36cd-599a-966c-cea1c2dcf9b5"]
    assert balls["fee_kind"] == "range_balls" and balls["amount_min"] == 50
    assert balls["quantity"] is None and balls["billing_basis"] is None
    ride = prices["n-bd0d83ba-3491-5f32-b098-2535bc378473"]
    assert (
        ride["audience"],
        ride["minimum_age"],
        ride["maximum_age"],
        ride["cart_included"],
    ) == ("junior", 13, 17, True)
    free = prices["n-1f6170f8-8d1d-5402-b732-0bde2c35772e"]
    assert free["amount_min"] == 0 and free["amount_kind"] == "exact"
    assert free["maximum_age"] == 11 and free["minimum_age"] is None
    for pid in [
        "n-9fc92641-57da-52ee-b9d5-40e57aff4ffb",  # Pull cart, not push_cart.
        "n-30ccaa96-1faf-594e-bff8-4a4eaefea682",  # Rider not explicitly nonplayer.
        "n-a71b6b48-6f32-55e7-abf6-b1467a2b8cee",  # Range product/unit unspecified.
    ]:
        assert prices[pid]["fee_kind"] is None
        assert prices[pid]["currency"] is None
        assert prices[pid]["amount_kind"] == "exact"


def test_completion_1163_preserves_partial_course_identity_and_round_scope(catalog):
    courses = {c["course_id"]: c for c in catalog["courses"]}
    sunny = courses["c-f81503ee-99c6-4cf2-aec3-e546c0fab1b6"]
    assert sunny["name"] is None
    assert (sunny["physical_holes"], sunny["access"], sunny["style"]) == (
        18,
        "public",
        "executive",
    )
    creek = courses["c-30a36de0-6ce2-45de-81ad-7c1741f1a03d"]
    assert creek["physical_holes"] is None and creek["access"] == "public"
    assert creek["map_location"]["kind"] == "address_range_estimate"
    shadow = courses["c-1462934a-55c8-4dbb-b26e-dce443eb5897"]
    assert shadow["physical_holes"] == 18
    assert {r["round_holes"] for r in shadow["round_options"]} == {9, 18}
    assert all(r["course_id"] == shadow["course_id"] for r in shadow["round_options"])
    assert all(
        c["arrival"] is None and c["nonmember_bookable"] is None
        for c in [sunny, creek, shadow]
    )


def test_completion_1163_property_context_does_not_create_arrivals(catalog):
    by_id = {
        f["released_id"]: f
        for f in catalog["facilities"]
        if f["released_id"] is not None
    }
    for fid, latitude, longitude in [
        ("f-005bd2e9-b3fd-46f8-9ecf-8b0df5e7d3e5", 29.69799, -95.137051),
        ("f-1b4feacc-0a88-4f73-b4ad-c1ba810ef8a2", 41.5493657, -75.9201033),
        (
            "f-01fbe6d3-8c81-47eb-a8c0-65f0fe831639",
            46.01814113649568,
            -83.68948710012675,
        ),
    ]:
        facility = by_id[fid]
        assert facility["map_location"] == {
            "latitude": latitude,
            "longitude": longitude,
            "kind": "property_point",
        }
        assert all(
            c["arrival"] is None
            for c in catalog["courses"]
            if c["facility_id"] == facility["facility_id"]
        )
    lee = next(
        c
        for c in catalog["courses"]
        if c["course_id"] == "c-a7a18a66-ed3e-464f-883a-24ab02810dc8"
    )
    assert (
        lee["location_note"]
        == "Mine Rd is the old entrance and does not provide access to the golf course."
    )
    assert lee["arrival"] is None


def test_completion_1163_booking_retains_weekday_and_league_qualification(catalog):
    coyote = next(
        c
        for c in catalog["courses"]
        if c["course_id"] == "c-5f509a65-89e9-4560-b5f1-feeaac0c1775"
    )
    assert coyote["name"] == "Coyote Trails Golf Course"
    assert "closed Mondays and Tuesdays" in coyote["booking_conditions"]
    assert "exclusive to league participants" in coyote["booking_conditions"]
    assert "7:00 AM Wednesday through Sunday" in coyote["booking_conditions"]
    assert coyote["nonmember_bookable"] is None
    assert coyote["access_qualification"] == coyote["booking_conditions"]


def test_completion_1163_shadowbrook_price_scope_and_unknowns_survive(catalog):
    shadow = next(
        c
        for c in catalog["courses"]
        if c["course_id"] == "c-1462934a-55c8-4dbb-b26e-dce443eb5897"
    )
    direct = shadow["optional"]["price_observation"]
    round_prices = [
        p for r in shadow["round_options"] for p in r["optional"]["price_observation"]
    ]
    assert len(direct) == 4 and len(round_prices) == 16
    prices = direct + round_prices
    assert len({p["id"] for p in prices}) == 20
    assert {p["source_id"] for p in prices} == {"s5705"}
    assert all(
        p["currency"] is None
        and p["billing_basis"] is None
        and p["effective_from"] is None
        for p in prices
    )
    assert all(p["round_holes"] is None and p["cart_included"] is None for p in direct)
    assert all(p["round_holes"] in {9, 18} for p in round_prices)
    assert all(p["conditions"] and "2026" in p["conditions"] for p in prices)


def test_completion_1163_price_dates_and_tee_units_are_source_bound(catalog):
    golden = next(
        c
        for c in catalog["courses"]
        if c["course_id"] == "c-5d0e5d69-be73-4ce6-8430-02824918e9f1"
    )
    prices = golden["optional"]["price_observation"]
    assert len(prices) == 14
    assert all(
        p["observation_id"] == "o-6b2f0829-3f35-5d73-8ab3-f1f3fc651a37" for p in prices
    )
    assert all(
        p["effective_from"] == "2026-04-01" and p["currency"] is None for p in prices
    )
    tees = {t["name"]: t for t in golden["tee_sets"]}
    assert (tees["Blue"]["yardage"], tees["Blue"]["yardage_unit"]) == (6600, "yards")
    assert all(
        tees[name]["yardage"] is None and tees[name]["yardage_unit"] is None
        for name in ["White", "Gold", "Red"]
    )
    roosevelt = next(
        c
        for c in catalog["courses"]
        if c["course_id"] == "c-5117733b-e47c-4b08-9d0e-92ea0cc0e34e"
    )
    assert roosevelt["style"] == "executive"
    tees = [t for t in roosevelt["tee_sets"] if t["id"].startswith("t-")]
    assert len(tees) == 6 and {t["rated_category"] for t in tees} == {"M", "W"}
    assert all(t["par"] == 33 and t["yardage"] is None for t in tees)


def test_completion_1163_terra_copy_correction_preserves_conflicts(catalog):
    terra = next(
        f
        for f in catalog["facilities"]
        if f["released_id"] == "f-024a2471-acc3-4109-a2ab-0123d622e29c"
    )
    ids = {
        "n-0fa48260-9f21-5c39-8dd6-79adcfb376f5",
        "n-5a4c6ff3-17db-5807-81fd-adff91c83ef8",
        "n-352cd0b5-18aa-5c5b-a8d9-79748fcf0af7",
        "n-5688cabb-74c6-59f3-a75c-2d9947de109c",
        "n-67cce253-7b56-5d5f-8a95-9bd08955edc0",
        "n-7ed94af5-64e3-5f42-8c3b-f657b0c4dfc6",
        "n-1629e2a4-203b-5c6f-b015-7de3cb6cb7cc",
    }
    rows = [r for rows in terra["optional"].values() for r in rows if r["id"] in ids]
    assert len(rows) == 7 and len({r["observation_id"] for r in rows}) == 3
    for r in rows:
        assert "field-source-bindings.json" not in r["qualification"]
        assert (
            "individual fields remain bound to their respective source pages"
            in r["qualification"]
        )
        assert "pace4:10" in r["qualification"] and "4:30" in r["qualification"]
        assert "stateproof OR verbalassurance" in r["qualification"]
        assert r["collected_on"] == "2026-10-18" and r["effective_from"] is None
