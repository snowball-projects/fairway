"""Keep publication before installation and stop failed releases early."""

import os
import subprocess
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[1] / "scripts/build.sh"


@pytest.mark.parametrize("failed_step", ["", "publication", "installation"])
def test_build_orders_publication_and_stops_on_failure(tmp_path, failed_step):
    commands = tmp_path / "bin"
    commands.mkdir()
    python = commands / "python"
    python.write_text(
        '#!/bin/sh\ncase "$*" in\n'
        '  "-m pip "*) echo bootstrap >> "$BUILD_LOG" ;;\n'
        '  "scripts/publish_research_map.py")\n'
        '    echo publication >> "$BUILD_LOG"\n'
        '    [ "$FAILED_STEP" != publication ] ;;\n'
        "  *) exit 99 ;;\nesac\n"
    )
    uv = commands / "uv"
    uv.write_text(
        '#!/bin/sh\necho installation >> "$BUILD_LOG"\n'
        '[ "$FAILED_STEP" != installation ]\n'
    )
    fetch = tmp_path / ".venv/bin/python"
    fetch.parent.mkdir(parents=True)
    fetch.write_text('#!/bin/sh\necho snapshot >> "$BUILD_LOG"\n')
    for command in (python, uv, fetch):
        command.chmod(0o755)
    log = tmp_path / "build.log"
    result = subprocess.run(
        ["bash", str(BUILD)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{commands}:{os.environ['PATH']}",
            "BUILD_LOG": str(log),
            "FAILED_STEP": failed_step,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    steps = log.read_text().splitlines()
    assert steps[:2] == ["bootstrap", "publication"]
    if failed_step == "publication":
        assert "installation" not in steps
    else:
        assert steps[2] == "installation"
    assert ("snapshot" in steps) == (not failed_step)
    assert (result.returncode == 0) == (not failed_step)
