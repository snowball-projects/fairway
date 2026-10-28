"""Source identity, privacy and geometry checks for the independent backbone."""

import gzip
import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "backbone", Path(__file__).resolve().parents[1] / "scripts/build_backbone.py"
)
backbone = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backbone)


def test_contact_fields_and_embedded_values_are_excluded():
    tags = backbone.source_tags(
        {
            "name": "Test course",
            "phone": "+1 212-555-0123",
            "email": "person@example.test",
            "operator": "Unrelated private person",
            "designer": "Approved designer",
            "golf:holes": "18",
            "fee": "yes",
            "access": "customers",
            "website": "mailto:person@example.test",
            "alt_name": "Booking 212-555-0123 person@example.test",
        }
    )
    assert set(tags) == {"name", "designer", "alt_name", "golf:holes", "fee", "access"}
    assert tags["designer"] == "Approved designer"
    assert tags["alt_name"] == "Booking [contact removed] [contact removed]"


def test_structured_claims_keep_dates_and_sources_without_unrelated_properties():
    claim = {
        "id": "Q1$claim",
        "rank": "normal",
        "mainsnak": {"snaktype": "novalue"},
        "qualifiers": {"P580": [{"date": "known"}], "P123": ["unrelated"]},
        "references": [
            {"snaks": {"P854": [{"url": "https://example.test"}], "P123": []}}
        ],
    }
    projected = backbone.claim_projection(claim)
    assert projected["value"] is None
    assert projected["snaktype"] == "novalue"
    assert projected["qualifiers"] == {"P580": [{"date": "known"}]}
    assert projected["references"] == [{"P854": [{"url": "https://example.test"}]}]


def test_extract_keeps_feature_identity_and_null_geometry(tmp_path):
    pytest.importorskip("osmium")
    pytest.importorskip("shapely")
    source = tmp_path / "tiny.osm"
    source.write_text("""<osm version="0.6">
<node id="1" version="1" timestamp="2026-10-20T00:00:00Z" lat="40" lon="-75"><tag k="leisure" v="golf_course"/><tag k="name" v="Shared name"/><tag k="wikidata" v="Q123"/><tag k="phone" v="212-555-0123"/></node>
<node id="2" version="1" timestamp="2026-10-20T00:00:00Z" lat="40.01" lon="-75"/>
<node id="3" version="1" timestamp="2026-10-20T00:00:00Z" lat="40.01" lon="-74.99"/>
<node id="4" version="1" timestamp="2026-10-20T00:00:00Z" lat="40" lon="-74.99"/>
<way id="10" version="2" timestamp="2026-10-21T00:00:00Z"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="leisure" v="golf_course"/><tag k="name" v="Shared name"/><tag k="wikidata" v="Q123"/></way>
<way id="11" version="1" timestamp="2026-10-20T00:00:00Z"><nd ref="2"/><nd ref="3"/><tag k="golf" v="course"/><tag k="name" v="Unclosed course"/></way>
<way id="12" version="1" timestamp="2026-10-20T00:00:00Z"><nd ref="1"/><nd ref="2"/><nd ref="999"/><nd ref="1"/><tag k="leisure" v="golf_course"/></way>
<relation id="20" version="3" timestamp="2026-10-22T00:00:00Z"><member type="way" ref="10" role=""/><member type="way" ref="11" role=""/><tag k="type" v="site"/><tag k="leisure" v="golf_course"/></relation>
</osm>""")
    args = Namespace(
        pbf=source,
        work=tmp_path / "work",
        md5=backbone.hash_file(source)[1],
        source_url="https://example.test/tiny.osm",
        source_date="2026-10-25T21:21:21Z",
        checked_on="2026-10-26",
    )
    backbone.extract(args)
    records = json.loads((args.work / "osm-features.json").read_text())
    rows = {row["feature_id"]: row for row in records}
    assert set(rows) == {
        "osm/node/1",
        "osm/way/10",
        "osm/way/11",
        "osm/way/12",
        "osm/relation/20",
    }
    assert rows["osm/node/1"]["wikidata_ids"] == rows["osm/way/10"]["wikidata_ids"]
    assert rows["osm/way/10"]["position_kind"] == "derived_inside_source_polygon"
    lon, lat = rows["osm/way/10"]["position"]
    assert -75 < lon < -74.99 and 40 < lat < 40.01
    assert rows["osm/way/11"]["position"] is None
    assert rows["osm/way/12"]["position"] is None
    assert rows["osm/relation/20"]["member_feature_ids"] == ["osm/way/10", "osm/way/11"]
    assert rows["osm/node/1"]["osm_last_edit"] == "2026-10-20T00:00:00Z"
    assert rows["osm/node/1"]["checked_on"] == "2026-10-26"
    assert "phone" not in rows["osm/node/1"]["tags"]
    assert all(row["arrival"] is None for row in records)


def test_wikidata_matches_only_explicit_qids_and_keeps_unmatched_items(tmp_path):
    args = Namespace(work=tmp_path, checked_on="2026-10-26")
    rows = [
        {"wikidata_ids": ["Q123"], "tags": {"wikidata": "Q123"}},
        {"wikidata_ids": ["Q123"], "tags": {"wikidata": "Q123"}},
        {"wikidata_ids": ["Q5"], "tags": {"wikidata": "Q5"}},
        {"wikidata_ids": ["Q789"], "tags": {"wikidata": "Q789"}},
    ]
    (tmp_path / "osm-features.json").write_text(json.dumps(rows))
    calls = []

    def source(url):
        calls.append(url)
        if "sparql" in url:
            return {
                "results": {
                    "bindings": [
                        {"item": {"value": "http://www.wikidata.org/entity/Q456"}}
                    ]
                }
            }
        return {
            "entities": {
                "Q789": {"missing": ""},
                "Q123": {
                    "lastrevid": 10,
                    "labels": {"en": {"value": "Test course"}},
                    "claims": {},
                },
                "Q456": {"lastrevid": 20, "labels": {}, "claims": {}},
                "Q5": {
                    "lastrevid": 30,
                    "claims": {
                        "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]
                    },
                },
            }
        }

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(backbone, "request_json", source)
        patch.setattr(backbone.time, "sleep", lambda _: None)
        backbone.enrich(args)
    snapshot = json.loads((tmp_path / "wikidata.json").read_text())
    assert set(snapshot["entities"]) == {"Q123", "Q456"}
    assert snapshot["entities"]["Q456"]["from_national_query"] is True
    assert snapshot["entities"]["Q123"]["source_url"].endswith("oldid=10")
    assert snapshot["excluded_human_target_count"] == 1
    assert snapshot["missing_entity_ids"] == ["Q789"]
    changed = json.loads((tmp_path / "osm-features.json").read_text())
    assert changed[0]["wikidata_ids"] == changed[1]["wikidata_ids"] == ["Q123"]
    assert changed[2]["wikidata_ids"] == [] and changed[2]["tags"] == {}
    assert changed[3]["wikidata_ids"] == ["Q789"]
    assert len(calls) == 2


def test_source_backpressure_preserves_query_facts_without_inventing_details(tmp_path):
    args = Namespace(work=tmp_path, checked_on="2026-10-26")
    (tmp_path / "osm-features.json").write_text(
        json.dumps([{"wikidata_ids": ["Q123"], "tags": {"wikidata": "Q123"}}])
    )
    calls = []

    def source(url):
        calls.append(url)
        if "sparql" in url:
            return {
                "results": {
                    "bindings": [
                        {"item": {"value": "http://www.wikidata.org/entity/Q456"}}
                    ]
                }
            }
        return {"error": {"code": "maxlag"}}

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(backbone, "request_json", source)
        with pytest.raises(ValueError, match="maxlag"):
            backbone.enrich(args)
    snapshot = json.loads((tmp_path / "wikidata.json").read_text())
    assert snapshot["status"] == "selection_only"
    assert snapshot["blocked_reason"] == "maxlag"
    assert set(snapshot["entities"]) == {"Q456"}
    entity = snapshot["entities"]["Q456"]
    assert entity["lastrevid"] is None and entity["label"] is None
    assert entity["claims"] == {} and entity["checked_on"] == "2026-10-26"
    assert "query=" in entity["source_url"]
    assert len(calls) == 2


def test_refresh_tags_requires_exact_pin_and_retains_privacy_exclusions(tmp_path):
    pytest.importorskip("osmium")
    source = tmp_path / "tiny.osm"
    source.write_text(
        """<osm version="0.6"><node id="1" version="2" timestamp="2026-10-20T00:00:00Z" lat="40" lon="-75"><tag k="leisure" v="golf_course"/><tag k="golf:holes" v="18"/><tag k="wikidata" v="Q5"/><tag k="phone" v="212-555-0123"/></node></osm>"""
    )
    sha, md5 = backbone.hash_file(source)
    pin = {"sha256": sha, "publisher_md5": md5, "bytes": source.stat().st_size}
    (tmp_path / "osm-pin.json").write_text(json.dumps(pin))
    rows = [
        {
            "feature_id": "osm/node/1",
            "osm_version": 2,
            "tags": {"leisure": "golf_course"},
            "wikidata_ids": [],
        }
    ]
    path = tmp_path / "osm-features.json"
    path.with_suffix(".json.gz").write_bytes(
        gzip.compress(json.dumps(rows).encode(), mtime=0)
    )
    args = Namespace(pbf=source, work=tmp_path)
    backbone.refresh_tags(args)
    updated = json.loads(path.read_text())
    assert updated[0]["tags"] == {"leisure": "golf_course", "golf:holes": "18"}
    assert updated[0]["wikidata_ids"] == []
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="PBF differs"):
        backbone.refresh_tags(args)
    assert json.loads(path.read_text()) == updated
