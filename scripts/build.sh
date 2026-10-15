#!/usr/bin/env bash
set -euo pipefail

python -m pip install uv==0.12.15
# Validate the immutable SQLite-derived public artifact; never regenerate an old JSON catalog.
python scripts/build_pages.py --check
uv sync --locked --no-dev
.venv/bin/python scripts/fetch_snapshot.py
