"""Build public native catalog browsing from immutable SQLite-generated transport."""

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    "index.html",
    "app.js",
    "styles.css",
    "catalog-read.mjs",
    "public-catalog.mjs",
    "public-planning.mjs",
    "optional-schema.mjs",
    "optional-facts.mjs",
    "map-geometry.mjs",
    "courses-drawer.mjs",
    "facility-dots.mjs",
    "origin-rows.mjs",
    "leaflet.js",
    "leaflet.css",
    "favicon.png",
    "icon.png",
    "LEAFLET-LICENSE.txt",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def public_projection(value):
    """Reject retained bodies and private path tokens before writing a public asset."""
    forbidden = {
        "fact_groups",
        "payload",
        "retained_pointer",
        "retained_document",
        "retained_evidence",
        "controls_reference",
        "capture_path",
        "local_path",
    }

    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if key in forbidden:
                    raise ValueError("raw evidence in public transport")
                visit(key)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            scan = re.sub(r"\bhttps?://[^\s<>\"'`]+", "", item, flags=re.IGNORECASE)
            if re.search(
                r"""(?:^|[\s"'`(\[={:;,<>|!?“”‘’«»])/+[^\s/]|file://|\b[A-Za-z]:[\\/]|\\{2}""",
                scan,
                re.IGNORECASE,
            ):
                raise ValueError("private path in public transport")

    visit(value)
    for note in value.get("provenance", {}).get("notes", []):
        if (
            not isinstance(note, dict)
            or set(note) != {"id"}
            or not isinstance(note["id"], str)
            or not note["id"]
        ):
            raise ValueError("public notes contain IDs only")


def native_transport(root, review_fixture=False):
    if review_fixture:
        raw = (root / "tests/fixtures/native5-ui/transport.json").read_bytes()
        if (
            digest(raw)
            != "af80563e815aaedda424b24eeeb42b985e6edd8b746306a8804fca6bc3454bef"
        ):
            raise ValueError("frozen native5 review fixture changed")
        value = json.loads(raw)
        public_projection(value)
        return {
            **{
                k: value[k]
                for k in (
                    "format_version",
                    "schema",
                    "revision",
                    "catalog_release_key",
                    "qualification",
                    "authority",
                )
            },
            "counts": {
                k: len(value[k]) for k in ("facilities", "courses", "destinations")
            },
            "files": {"catalog.json": {"sha256": digest(raw), "bytes": len(raw)}},
        }, raw
    source = root / "data/catalog-release"
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("format_version") != 2 or manifest.get("schema") != 5:
        raise ValueError("unsupported native catalog manifest")
    packed = (source / "catalog.json.gz").read_bytes()
    item = manifest["files"]["catalog.json.gz"]
    if len(packed) != item["bytes"] or digest(packed) != item["sha256"]:
        raise ValueError("generated compressed catalog changed")
    raw = gzip.decompress(packed)
    item = manifest["files"]["catalog.json"]
    if (
        len(raw) != item["bytes"]
        or len(raw) > 64 * 1024 * 1024
        or digest(raw) != item["sha256"]
    ):
        raise ValueError("generated catalog changed")
    value = json.loads(raw)
    public_projection(value)
    for key in ("format_version", "revision", "schema", "catalog_release_key"):
        if value[key] != manifest[key]:
            raise ValueError("native release identity mismatch")
    for kind, identity in (
        ("facilities", "facility_id"),
        ("courses", "course_id"),
        ("destinations", "id"),
    ):
        rows = value[kind]
        if len(rows) != manifest["counts"][kind] or len(
            {r[identity] for r in rows}
        ) != len(rows):
            raise ValueError("native identity or count mismatch")
    facilities = {r["facility_id"] for r in value["facilities"]}
    if any(c["facility_id"] not in facilities for c in value["courses"]):
        raise ValueError("orphan native course")
    return manifest, raw


def build(root, output, commit, review_fixture=False):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Pages output must be new or empty")
    manifest, raw = native_transport(root, review_fixture)
    payloads = {
        name: (root / "src/fairway/static" / name).read_bytes() for name in ASSETS
    }
    payloads["research-map/boundaries.json"] = (
        root / "docs/research-map/boundaries.json"
    ).read_bytes()
    item = manifest["files"]["catalog.json"]
    name = f"native-catalog-{item['sha256']}.json"
    payloads["data/" + name] = raw
    public = {**manifest, "files": {"catalog.json": {**item, "path": name}}}
    payloads["data/catalog-release.json"] = (
        json.dumps(public, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    # Retire the old coverage application; its URL leads to the same native catalog UI.
    payloads["research-map/index.html"] = (
        b'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=../"><title>fairway catalog</title><a href="../">Open the fairway catalog</a>'
    )
    policy = "default-src 'self'; base-uri 'none'; connect-src 'self' https://photon.komoot.io; img-src 'self' data: https://tile.openstreetmap.org; font-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'none'; object-src 'none'"
    html = (
        payloads["index.html"]
        .decode()
        .replace(
            '<meta charset="utf-8" />',
            '<meta charset="utf-8" />\n    <meta http-equiv="Content-Security-Policy" content="'
            + policy
            + '" />',
        )
    )
    if review_fixture:
        html = html.replace(
            "<body>",
            '<body><p class="review-fixture-banner">REVIEW FIXTURE: synthetic records; not an adopted or published catalog.</p>',
        )
    payloads["index.html"] = html.encode()
    deployment = {
        "commit": commit,
        "revision": manifest["revision"],
        "catalog_release_key": manifest["catalog_release_key"],
        "catalog_sha256": item["sha256"],
        "counts": manifest["counts"],
        "review_fixture": review_fixture,
    }
    payloads["deployment.json"] = (
        json.dumps(deployment, sort_keys=True) + "\n"
    ).encode()
    payloads[".nojekyll"] = b""
    for relative, body in payloads.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    return {
        **deployment,
        "assets": len(payloads),
        "output_sha256": {n: digest(b) for n, b in sorted(payloads.items())},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--review-fixture",
        action="store_true",
        help="Build only the pinned synthetic native5 review fixture",
    )
    parser.add_argument("--commit", default="validation")
    args = parser.parse_args()
    if args.check:
        manifest, _ = native_transport(ROOT, args.review_fixture)
        print(json.dumps(manifest, sort_keys=True))
    elif args.output is not None:
        print(
            json.dumps(
                build(ROOT, args.output, args.commit, args.review_fixture),
                sort_keys=True,
            )
        )
    else:
        parser.error("--output or --check is required")


if __name__ == "__main__":
    main()
