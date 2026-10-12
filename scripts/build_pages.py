"""Build independent static catalog browsing from the reviewed source."""

import argparse
import json
import shutil
from pathlib import Path

from publish_research_map import publish

ROOT = Path(__file__).resolve().parents[1]
CALCULATION_ORIGIN = "https://fairway-n29h.onrender.com"


def build(root, output, commit):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Pages output must be new or empty")
    # Validate source before creating output. No graph/runtime dependencies or secrets.
    import catalog

    catalog.read(root / "data/catalog.json")
    shutil.copytree(
        root / "src/fairway/static",
        output,
        ignore=shutil.ignore_patterns("data", "research-map", "__pycache__"),
        dirs_exist_ok=True,
    )
    publication = publish(root, output, write_ranking=False)
    index = output / "index.html"
    html = index.read_text().replace(
        '<meta name="fairway-calculation-origin" content="" />',
        f'<meta name="fairway-calculation-origin" content="{CALCULATION_ORIGIN}" />',
    )
    policy = (
        "default-src 'self'; base-uri 'none'; "
        f"connect-src 'self' https://photon.komoot.io {CALCULATION_ORIGIN}; "
        "img-src 'self' data: https://tile.openstreetmap.org; "
        "font-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "form-action 'none'; object-src 'none'"
    )
    html = html.replace(
        '<meta charset="utf-8" />',
        '<meta charset="utf-8" />\n'
        f'    <meta http-equiv="Content-Security-Policy" content="{policy}" />',
    )
    index.write_text(html)
    (output / ".nojekyll").write_text("")
    (output / "deployment.json").write_text(
        json.dumps({"commit": commit, "catalog_sha256": publication["catalog_sha256"]})
        + "\n"
    )
    return publication


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    print(json.dumps(build(ROOT, args.output, args.commit), sort_keys=True))


if __name__ == "__main__":
    main()
