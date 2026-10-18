"""Native publication binds immutable data and excludes private inputs."""

import gzip
import importlib.util
import json
import os
import re
from hashlib import sha256
from pathlib import Path

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
    ranking = (ROOT / "src/fairway/data/course-catalog.json").read_bytes()
    output = tmp_path / "one"
    one = pages.build(ROOT, output, "a" * 40, review_fixture=True)
    two = pages.build(ROOT, tmp_path / "two", "a" * 40, review_fixture=True)
    assert one == two
    manifest = json.loads((output / "data/catalog-release.json").read_text())
    item = manifest["files"]["catalog.json"]
    raw = (output / "data" / item["path"]).read_bytes()
    assert len(raw) == item["bytes"] and sha256(raw).hexdigest() == item["sha256"]
    assert one["counts"] == {"facilities": 3, "courses": 3, "destinations": 2}
    html = (output / "index.html").read_text()
    assert 'src="./app.js"' in html and "Content-Security-Policy" in html
    assert "photon.komoot.io" in html and "onrender.com" not in html
    assert (
        "data/catalog-release.json" in html
        and "REVIEW FIXTURE: synthetic records" in html
    )
    assert one["review_fixture"] is True
    assert one["assets"] == 24
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
    assert 'href="../"' in (output / "research-map/index.html").read_text()
    assert source.read_bytes() == before
    assert (ROOT / "src/fairway/data/course-catalog.json").read_bytes() == ranking
    with pytest.raises(ValueError, match="new or empty"):
        pages.build(ROOT, output, "b" * 40)
    for module in output.glob("*.mjs"):
        for dependency in re.findall(r"from\s+[\"\'](\./[^\"\']+)", module.read_text()):
            assert (module.parent / dependency).is_file(), (module.name, dependency)
    for dependency in re.findall(
        r"from\s+[\"\'](\./[^\"\']+)", (output / "app.js").read_text()
    ):
        assert (output / dependency).is_file(), dependency


@pytest.mark.parametrize(
    "defect", ["compressed", "uncompressed-hash", "revision", "counts"]
)
def test_corrupt_artifact_fails_before_output(tmp_path, defect):
    root = tmp_path / "source"
    source = root / "data/catalog-release"
    source.mkdir(parents=True)
    manifest, raw = pages.native_transport(ROOT, review_fixture=True)
    packed = gzip.compress(raw, mtime=0)
    (source / "catalog.json.gz").write_bytes(packed)
    manifest["files"]["catalog.json.gz"] = {
        "sha256": sha256(packed).hexdigest(),
        "bytes": len(packed),
    }
    if defect == "compressed":
        with (source / "catalog.json.gz").open("ab") as stream:
            stream.write(b"changed")
    elif defect == "uncompressed-hash":
        manifest["files"]["catalog.json"]["sha256"] = "0" * 64
    elif defect == "revision":
        manifest["revision"] += 1
    else:
        manifest["counts"]["courses"] += 1
    (source / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "rejected"
    with pytest.raises(ValueError):
        pages.build(root, output, "rejected")
    assert not output.exists()


def test_default_build_rejects_old_schema_before_output(tmp_path):
    root = tmp_path / "old-source"
    source = root / "data/catalog-release"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text(
        json.dumps({"format_version": 1, "schema": 4})
    )
    with pytest.raises(ValueError, match="unsupported native catalog manifest"):
        pages.build(root, tmp_path / "not-published", "candidate")
    assert not (tmp_path / "not-published").exists()


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


@pytest.mark.parametrize(
    "mode", ["oversize", "understated", "concatenated", "truncated", "packed"]
)
def test_bounded_gzip_rejects_before_output(tmp_path, monkeypatch, mode):
    root = tmp_path / "source"
    source = root / "data/catalog-release"
    source.mkdir(parents=True)
    manifest, _ = pages.native_transport(ROOT, review_fixture=True)
    monkeypatch.setattr(pages, "MAX_CATALOG_BYTES", 4096)
    raw = b"x" * 4096
    packed = gzip.compress(raw, mtime=0)
    declared = 4096
    if mode == "oversize":
        declared += 1
    elif mode == "understated":
        declared = 100
    elif mode == "concatenated":
        packed += gzip.compress(raw, mtime=0)
    elif mode == "truncated":
        packed = packed[:-8]
    else:
        monkeypatch.setattr(pages, "MAX_PACKED_BYTES", len(packed) - 1)
    manifest["files"] = {
        "catalog.json": {"bytes": declared, "sha256": sha256(raw).hexdigest()},
        "catalog.json.gz": {"bytes": len(packed), "sha256": sha256(packed).hexdigest()},
    }
    (source / "manifest.json").write_text(json.dumps(manifest))
    (source / "catalog.json.gz").write_bytes(packed)
    reads = []
    original = gzip.GzipFile.read

    def bounded_read(stream, size=-1):
        reads.append(size)
        assert 0 < size <= 4097
        return original(stream, size)

    monkeypatch.setattr(gzip.GzipFile, "read", bounded_read)
    output = tmp_path / "rejected"
    with pytest.raises((ValueError, EOFError)):
        pages.build(root, output, "rejected")
    assert not output.exists()
    assert reads == ([] if mode in {"oversize", "packed"} else [declared + 1])
