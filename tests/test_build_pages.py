"""Native publication binds immutable data and excludes private inputs."""

import gzip
import importlib.util
import json
import os
import re
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from struct import unpack
from urllib.parse import urljoin, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "pages_builder", ROOT / "scripts/build_pages.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


def test_native_pages_are_reproducible_public_only_and_leave_source_unchanged(tmp_path):
    source = ROOT / "data/catalog-release/catalog.json.gz"
    before = source.read_bytes()
    output = tmp_path / "one"
    one = pages.build(ROOT, output, "a" * 40, review_fixture=True)
    two = pages.build(ROOT, tmp_path / "two", "a" * 40, review_fixture=True)
    assert one == two
    manifest = json.loads((output / "data/catalog-release.json").read_text())
    item = manifest["files"]["browser-details.json"]
    raw = (output / "data" / item["path"]).read_bytes()
    assert len(raw) == item["bytes"] and sha256(raw).hexdigest() == item["sha256"]
    assert one["counts"] == {"facilities": 3, "courses": 3, "destinations": 2}
    html = (output / "index.html").read_text()
    assert f'src="./{one["ui_assets"]["app.js"]}"' in html
    assert "Content-Security-Policy" in html
    assert "photon.komoot.io" in html and "onrender.com" not in html
    assert (
        "data/catalog-release.json" in html
        and "REVIEW FIXTURE: synthetic records" in html
    )
    assert one["review_fixture"] is True
    assert one["assets"] == 40
    assert json.loads((output / "deployment.json").read_text())["commit"] == "a" * 40
    for name in [
        "catalog.mjs",
        "logical-plan.mjs",
        "assembly-plan.mjs",
        ".env",
        "tests",
        "research-map/publication.json",
    ]:
        assert not (output / name).exists()
    for suffix in ["*.sqlite", "*.sql", "*.gz", "*.npz"]:
        assert not list(output.rglob(suffix))
    assert (output / ".nojekyll").exists()
    assert source.read_bytes() == before
    with pytest.raises(ValueError, match="new or empty"):
        pages.build(ROOT, output, "b" * 40)
    for module in output.glob("*.mjs"):
        for dependency in re.findall(r"from\s+[\"\'](\./[^\"\']+)", module.read_text()):
            assert (module.parent / dependency).is_file(), (module.name, dependency)
    for dependency in re.findall(
        r"from\s+[\"\'](\./[^\"\']+)", (output / "app.js").read_text()
    ):
        assert (output / dependency).is_file(), dependency


def test_home_screen_assets_are_published_with_app_relative_urls(tmp_path):
    output = tmp_path / "site"
    pages.build(ROOT, output, "a" * 40, review_fixture=True)

    class Head(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = {}
            self.meta = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "link":
                self.links[attrs["rel"]] = attrs
            if tag == "meta" and "content" in attrs:
                self.meta[attrs.get("name", attrs.get("http-equiv"))] = attrs["content"]

    head = Head()
    head.feed((output / "index.html").read_text())
    base = "https://snowball-projects.github.io/fairway/"

    def published(href):
        assert href.startswith("./")
        url = urljoin(base, href)
        assert url.startswith(base)
        path = output / urlsplit(url).path.removeprefix("/fairway/")
        assert path.is_file(), url
        return path

    touch = head.links["apple-touch-icon"]
    assert touch["sizes"] == "180x180"
    assert head.meta["apple-mobile-web-app-title"] == "fairway"
    assert head.meta["apple-mobile-web-app-capable"] == "yes"
    manifest = json.loads(published(head.links["manifest"]["href"]).read_text())
    assert manifest["name"] == manifest["short_name"] == "fairway"
    assert manifest["display"] == "standalone"
    for key in ("start_url", "scope"):
        assert manifest[key] == "./"
        assert urljoin(base, manifest[key]) == base
    for key in ("theme_color", "background_color"):
        assert manifest[key] == head.meta["theme-color"] == "#f4f2e9"
    pngs = [(touch["href"], (180, 180))]
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    for icon in manifest["icons"]:
        assert icon["type"] == "image/png"
        pngs.append((icon["src"], tuple(map(int, icon["sizes"].split("x")))))
    for href, size in pngs:
        png = published(href).read_bytes()
        assert png[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        assert unpack(">II", png[16:24]) == size
        assert png[25] == 2  # Opaque RGB prevents a black iOS transparency fill.
    policy = dict(
        directive.strip().split(" ", 1)
        for directive in head.meta["Content-Security-Policy"].split(";")
    )
    for resource in ("manifest-src", "img-src"):
        assert "'self'" in policy.get(resource, policy["default-src"]).split()


@pytest.fixture(scope="module")
def production_pages(tmp_path_factory):
    root = tmp_path_factory.mktemp("production-pages")
    commit = os.environ.get("GITHUB_SHA", "c" * 40)
    one = pages.build(ROOT, root / "one", commit)
    two = pages.build(ROOT, root / "two", commit)
    assert one == two
    files = sorted(
        p.relative_to(root / "one") for p in (root / "one").rglob("*") if p.is_file()
    )
    assert files == sorted(
        p.relative_to(root / "two") for p in (root / "two").rglob("*") if p.is_file()
    )
    for path in files:
        assert (root / "one" / path).read_bytes() == (root / "two" / path).read_bytes()
    return root / "one", one, commit


@pytest.mark.catalog_integration
def test_default_build_uses_the_committed_real_release_without_fixture_fallback(
    production_pages,
):
    output, one, commit = production_pages
    manifest = json.loads((ROOT / "data/catalog-release/manifest.json").read_text())
    assert one["review_fixture"] is False
    assert one["revision"] == manifest["revision"]
    assert one["catalog_release_key"] == manifest["catalog_release_key"]
    assert one["catalog_sha256"] == manifest["files"]["catalog.json"]["sha256"]
    assert one["counts"] == manifest["counts"]
    assert "REVIEW FIXTURE" not in (output / "index.html").read_text()
    assert json.loads((output / "deployment.json").read_text())["commit"] == commit


def test_explicit_fixture_build_rejects_any_changed_literal(tmp_path):
    path = tmp_path / "tests/fixtures/native5-ui/transport.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(
        (ROOT / "tests/fixtures/native5-ui/transport.json").read_bytes() + b" "
    )
    with pytest.raises(ValueError, match="frozen native5 review fixture changed"):
        pages.build(tmp_path, tmp_path / "out", "candidate", review_fixture=True)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "token",
    [
        "/opt/private",
        "C:/private",
        r"C:\private",
        r"\\server\share",
        "file:///private",
        "context=/var/private",
    ],
)
def test_public_asset_rejects_private_path_tokens_in_values_and_keys(token):
    for value in ({"safe": token}, {token: "safe"}):
        with pytest.raises(ValueError, match="private path"):
            pages.public_projection(value)


def test_public_asset_rejects_note_bodies_and_retained_payload():
    pages.public_projection({"provenance": {"notes": [{"id": "note-id"}]}})
    for value in (
        {"provenance": {"notes": [{"id": "note-id", "text": "body"}]}},
        {"fact_groups": []},
    ):
        with pytest.raises(ValueError):
            pages.public_projection(value)


@pytest.mark.parametrize(
    "prefix",
    [":", ";", ",", "<", ">", "|", "!", "?", "“", "”", "‘", "’", "«", "»", "`"],
)
def test_public_asset_rejects_punctuation_prefixed_paths(prefix):
    with pytest.raises(ValueError, match="private path"):
        pages.public_projection({"safe": "label" + prefix + "/private/evidence"})


def test_public_asset_preserves_urls_and_slash_compound_text():
    for text in [
        "clubhouse/range",
        "https://official.example/path?next=/course",
        "Source: https://official.example/golf/course; practice/range",
    ]:
        pages.public_projection({"safe": text})
    with pytest.raises(ValueError, match="private path"):
        pages.public_projection(
            {"safe": "https://official.example/path then:/private/evidence"}
        )


def test_generated_credits_keep_public_license_notices_and_escape_markup():
    records = [
        {
            "source": "Source <one>",
            "attribution": "Author & team",
            "license": "CC-BY-4.0",
            "source_url": "https://official.example/?a=1&b=2",
            "changes": "Adapted property points",
            "applies_to": "Selected records",
        },
        {
            "attribution": "City of Moorhead",
            "license": "CC-BY-SA-3.0-Unported",
            "policy_url": "https://official.example/policy",
            "scope": "City-owned facts",
        },
        {"source": "Unsafe link", "source_url": "javascript:alert(1)"},
    ]
    before = json.dumps(records)
    html = pages.credits_html(records, "default-src 'self'").decode()
    assert "Source &lt;one&gt;" in html and "Author &amp; team" in html
    assert 'href="https://creativecommons.org/licenses/by/4.0/"' in html
    assert 'href="https://creativecommons.org/licenses/by-sa/3.0/"' in html
    assert "Adapted property points" in html and "Selected records" in html
    assert "City-owned facts" in html and "https://official.example/policy" in html
    assert 'href="javascript:' not in html and "<script" not in html
    assert json.dumps(records) == before


@pytest.mark.catalog_integration
def test_production_credits_preserve_all_public_license_notices(production_pages):
    output, result, _commit = production_pages
    actual = (output / "credits.html").read_text()
    public = json.loads(
        gzip.decompress((ROOT / "data/catalog-release/catalog.json.gz").read_bytes())
    )
    for record in public["source_licenses"]:
        for key in (
            "source",
            "attribution",
            "license",
            "changes",
            "applies_to",
            "scope",
        ):
            if record.get(key):
                from html import escape

                assert escape(record[key]) in actual
    assert (
        result["output_sha256"]["credits.html"]
        == sha256((output / "credits.html").read_bytes()).hexdigest()
    )
    assert 'href="./credits.html"' in (output / "app.js").read_text()


def test_browser_details_keep_display_facts_without_duplicate_transport_material():
    value = json.loads((ROOT / "tests/fixtures/native5-ui/transport.json").read_bytes())
    before = json.dumps(value, sort_keys=True)
    details = json.loads(pages.browser_details_bytes(value))
    assert set(details) == {
        "revision",
        "catalog_release_key",
        "facilities",
        "courses",
        "destinations",
    }
    for original, actual in zip(value["courses"], details["courses"], strict=True):
        assert actual["course_id"] == original["course_id"]
        assert actual["facility_id"] == original["facility_id"]
        assert actual["access"] == original["access"]
        assert actual.get("nonmember_bookable") == original["nonmember_bookable"]
        assert actual.get("plan_eligible") == original["plan_eligible"]
        for removed in (
            "address_text",
            "address_region",
            "arrival_latitude",
            "aliases",
            "inventory_qualification",
        ):
            assert removed not in actual
    main = next(c for c in details["courses"] if c.get("plan_eligible"))
    assert main["optional"]["practice_observation"][0]["driving_range_lighted"] is False
    price = main["round_options"][0]["optional"]["price_observation"][0]
    original_price = next(c for c in value["courses"] if c["plan_eligible"])[
        "round_options"
    ][0]["optional"]["price_observation"][0]
    assert price["conditions"] == original_price["conditions"]
    assert price["qualification"] == original_price["qualification"]
    assert price["historical"] is True
    assert "observation_id" not in price and "source_id" not in price
    assert json.dumps(value, sort_keys=True) == before
