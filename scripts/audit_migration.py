"""One-time accounting against the frozen Git snapshot. No catalog writes."""

import hashlib
import json
import subprocess
from pathlib import Path

import catalog


def assert_original_courses(original, current, persisted_ids):
    assert len(persisted_ids) == len(original), "preserved course count differs"
    assert len(set(persisted_ids)) == len(persisted_ids), (
        "duplicate persisted course ID"
    )
    by_id = {course["id"]: course for course in current}
    assert len(by_id) == len(current), "duplicate current course ID"
    assert set(persisted_ids) <= set(by_id), "original course ID missing or changed"
    for old_course, course_id in zip(original, persisted_ids, strict=True):
        assert old_course == {k: by_id[course_id][k] for k in ["name", "holes"]}


def main():
    root = Path(__file__).resolve().parents[1]

    v = catalog.read(root / "data/catalog.json")
    accounting = json.loads((root / "data/migration-accounting.json").read_text())
    ids = accounting["original_facility_ids"]
    assert len(ids) == accounting["original_facilities"]
    assert (
        sum(len(row["course_ids"]) for row in ids)
        == accounting["preserved_original_courses"]
    )
    by = {f["id"]: f for f in v["facilities"]}
    rename = {
        "holes": "physical_holes",
        "course_details_complete": "inventory_complete",
        "facility_grouping": "grouping",
        "coordinates": "map_location",
        "source_note": "notes.source",
        "access_note": "notes.access",
    }

    def frozen(path):
        return json.loads(
            subprocess.check_output(["git", "show", "3006606:" + path], cwd=root)
        )

    def refs(s):
        return catalog.joined_notes(v, s)

    old = frozen("data/public-courses.json")
    for r, m in zip(old["facilities"], ids, strict=True):
        f = by[m["id"]]
        q = v["research"][f["id"]]
        assert (
            m["original_sha256"]
            == hashlib.sha256(
                json.dumps(
                    r, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
        )
        for k in ["name", "state", "county", "website"]:
            assert f[k] == r[k]
        assert (f["address"]["text"] if f["address"] else None) == r["address"]
        assert (
            q["reported_main_holes"]
            if r["name"] == "Winagamie Golf Course"
            else f["physical_holes"]
        ) == r["holes"]
        assert f["inventory_complete"] == r["course_details_complete"]
        assert q["grouping"] == r["facility_grouping"]
        assert_original_courses(r["courses"], f["courses"], m["course_ids"])
        assert [v["sources"][s] for s in q["listed_sources"]] == r["sources"]
        for k in ["source_note", "access_note"]:
            if k in r:
                assert refs(q["notes"][k.split("_")[0]]) == r[k]
        if "website_source" in r:
            if r["website_source"] is None:
                assert q["unknown_sources"]["website"] is None
            else:
                assert any(
                    s["fields"] == ["website"]
                    and v["sources"][s["source"]] == r["website_source"]
                    and s["observed_on"] is None
                    for s in q["support"]
                )
        if r["coordinates"]:
            c = r["coordinates"]
            assert f["map_location"] == {
                k: c[k] for k in ["latitude", "longitude", "kind"]
            }
            assert any(
                s["fields"] == ["map_location"]
                and v["sources"][s["source"]] == c["source"]
                and s["observed_on"] == c["observed_on"]
                for s in q["support"]
            )
        else:
            assert f["map_location"] is None
        if "county_evidence" in r:
            e = r["county_evidence"]
            assert q["county_match"] == {
                k: x for k, x in e.items() if k not in ["source", "observed_on"]
            }
            assert any(
                s["fields"] == ["county"]
                and v["sources"][s["source"]] == e["source"]
                and s["observed_on"] == e["observed_on"]
                for s in q["support"]
            )
        for e in r.get("evidence", []):
            assert any(
                s["fields"] == [rename.get(k, k) for k in e["fields"]]
                and v["sources"][s["source"]] == e["source"]
                and s["observed_on"] == e.get("observed_on")
                and refs(s.get("note")) == e.get("note")
                for s in q["support"]
            )
    for k, x in old.items():
        if k not in ["facilities", "coverage", "county_checklist", "schema_version"]:
            assert v["metadata"][k] == x
    assert v["county_checklist"] == old["county_checklist"]
    for name, section in [
        ("data/catalog-additions.json", "history"),
        ("data/research-progress.json", "progress"),
    ]:
        o = frozen(name)
        generated = catalog.exports(v)[Path(name).name]
        assert len(o.get("batches", o.get("recent_batches"))) == len(
            generated.get("batches", generated.get("recent_batches"))
        )
        for a, b in zip(
            o.get("batches", o.get("recent_batches")),
            generated.get("batches", generated.get("recent_batches")),
            strict=True,
        ):
            for k, x in a.items():
                if k == "added_facilities":
                    assert x == [
                        {k: y for k, y in z.items() if k != "id"} for z in b[k]
                    ]
                else:
                    assert x == b[k], (k, x, b[k])
        for k, x in o.items():
            if k not in [
                "schema_version",
                "batches",
                "recent_batches",
                "current_facility_count",
            ]:
                assert generated[k] == x
    ranking = frozen("src/fairway/data/course-catalog-v1.json")
    newranking = catalog.exports(v)["course-catalog.json"]
    ranking_map = []
    for a, b in zip(ranking["courses"], newranking["courses"], strict=True):
        for k, x in a.items():
            if k not in ["id", "facts_source", "routing_source"]:
                assert b[k] == x
            elif k != "id":
                assert v["sources"][b[k]] == next(
                    s["url"] for s in ranking["sources"] if s["id"] == x
                )
        ranking_map.append(
            {
                "original_id": a["id"],
                "facility_id": b["facility_id"],
                "course_id": b["id"],
            }
        )
    assert ranking_map == accounting["bounded_catalog_ids"], "bounded ID map changed"
    print(
        "All original facts, explicit nulls, sources, notes, evidence, geography and history accounted for."
    )


if __name__ == "__main__":
    main()
