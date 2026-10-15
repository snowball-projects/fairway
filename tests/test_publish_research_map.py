"""Retired writers fail before creating old-schema public outputs."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["catalog.py", "publish_research_map.py"])
def test_legacy_publisher_is_retired_without_fallback(tmp_path, name):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and "retired" in result.stderr
    assert list(tmp_path.iterdir()) == []
    assert not (ROOT / "data/catalog.json").exists()
