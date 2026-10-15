"""Exporter and Pages accept the same bounded financial notation without rewriting it."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from fairway.catalog_native_export import _public

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "price_scan_pages", ROOT / "scripts/build_pages.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)
CASES = json.loads((ROOT / "tests/fixtures/native5-ui/per-each-guard.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_financial_scan_decisions_match_export_and_preserve_all_text(case):
    for validate in (_public, pages.public_projection):
        value = copy.deepcopy(case["value"])
        before = copy.deepcopy(value)
        if case["accept"]:
            validate(value)
        else:
            with pytest.raises(ValueError):
                validate(value)
        assert value == before
