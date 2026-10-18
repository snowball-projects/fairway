"""A cached deployment must not mix old modules with a newly loaded page."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "asset_builder", ROOT / "scripts/build_pages.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


def assets():
    return {
        name: (ROOT / "src/fairway/static" / name).read_bytes() for name in pages.ASSETS
    }


def test_page_and_every_module_dependency_use_integrity_named_files():
    payloads = assets()
    originals = dict(payloads)
    paths = pages.version_ui_assets(payloads)
    for name, target in paths.items():
        assert (
            target
            == f"{Path(name).stem}-{pages.digest(payloads[target])}{Path(name).suffix}"
        )
        assert payloads[name] == originals[name]  # Existing direct URLs remain usable.
        for dependency in re.findall(
            r"from\s+['\"]\./([^'\"]+)", payloads[target].decode()
        ):
            assert dependency in paths.values()
            assert dependency in payloads
    html = pages.version_ui_html(originals["index.html"].decode(), paths)
    for name in ["app.js", "leaflet.js", "styles.css", "leaflet.css"]:
        assert f"./{paths[name]}" in html
        assert f'./{name}"' not in html
    again = assets()
    assert pages.version_ui_assets(again) == paths
    assert again == payloads


def test_leaf_change_invalidates_its_complete_import_chain_only():
    before = assets()
    before_paths = pages.version_ui_assets(before)
    after = assets()
    after["optional-schema.mjs"] += b"\n// next software revision\n"
    after_paths = pages.version_ui_assets(after)
    for name in [
        "optional-schema.mjs",
        "optional-facts.mjs",
        "public-catalog.mjs",
        "app.js",
    ]:
        assert before_paths[name] != after_paths[name]
    for name in ["catalog-read.mjs", "courses-drawer.mjs", "leaflet.js", "styles.css"]:
        assert before_paths[name] == after_paths[name]


@pytest.mark.parametrize("dependency", ["missing.mjs", "public-catalog.mjs"])
def test_unpublished_or_cyclic_dependencies_cannot_form_a_partial_graph(dependency):
    payloads = assets()
    payloads["catalog-read.mjs"] += f"\nimport './{dependency}';\n".encode()
    with pytest.raises(ValueError, match="unknown or cyclic"):
        pages.version_ui_assets(payloads)
