#!/usr/bin/env bash
set -euo pipefail

python -m pip install uv==0.12.15
python scripts/publish_research_map.py
uv sync --locked --no-dev
.venv/bin/python scripts/fetch_snapshot.py
