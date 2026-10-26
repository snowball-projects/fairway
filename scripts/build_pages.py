"""Build static browsing directly from the maintained plain CSV catalog."""

import argparse
import hashlib
import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fairway.open_catalog import transport

MAX_CATALOG_BYTES = 64 * 1024 * 1024
MAX_INITIAL_MAP_BYTES = 4 * 1024 * 1024
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


# Explicit shared scan policy: no engine-dependent whitespace, casefold or boundary.
_SCAN_SPACE = r"\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_URL_BOUNDARY = r"\x00-\x2f\x3a-\x40\x5b-\x5e\x60\x7b-\x7f“”‘’«»"


def _validation_scan(text):
    text = re.sub(f"[{_SCAN_SPACE}]", " ", text)
    return re.sub(r"[A-Z]", lambda match: match[0].lower(), text)


_HTTP_TOKEN = rf"""(^|[{_URL_BOUNDARY}])(https?://[^ <>"'`“”‘’«»]+)"""
_CREDENTIAL_URL_KEYS = frozenset(
    [
        "access_token",
        "access-token",
        "api_key",
        "api-key",
        "apikey",
        "authorization",
        "client_secret",
        "client-secret",
        "credential",
        "password",
        "passwd",
        "secret",
        "token",
    ]
)


def _credential_syntax(text):
    # No URL extraction or reconstruction: conservatively hold explicit syntax.
    for view in (text, re.sub(r"[\t\n\r]", "", text)):
        scan = _validation_scan(view)
        scan = re.sub(
            r"%([0-9a-f]{2})",
            lambda m: (
                chr(int(m[1], 16))
                if chr(int(m[1], 16))
                in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._~-"
                else m[0]
            ),
            scan,
        )
        scan = _validation_scan(scan)
        if re.search(r"https?:[/\\]*[^/\\?#]*(?:@|%40)", scan):
            return True
        keys = "|".join(re.escape(key) for key in _CREDENTIAL_URL_KEYS)
        if re.search(rf"(?:^|[^a-z0-9_])(?:{keys}) *=", scan):
            return True
    return False


def _without_http_links(text):
    return re.sub(_HTTP_TOKEN, r"\1", _validation_scan(text))


# Canonical public text roles; private/provenance objects never gain this role.
_PRIVATE_KEYS = frozenset(
    [
        "access_token",
        "api_key",
        "authorization",
        "capture_path",
        "controls_reference",
        "credential",
        "fact_groups",
        "local_path",
        "password",
        "payload",
        "retained_document",
        "retained_evidence",
        "retained_pointer",
        "secret",
    ]
)
_PRIVATE_KEYS |= _CREDENTIAL_URL_KEYS
_PUBLIC_LICENSE_FIELDS = frozenset(
    [
        "applies_to",
        "attribution",
        "changes",
        "collected_on",
        "kind",
        "license",
        "license_url",
        "policy_capture_sha256",
        "policy_url",
        "scope",
        "source",
        "source_id",
        "source_url",
    ]
)
_PUBLIC_DOMAIN_TEXT = {
    kind: frozenset(fields.split())
    for kind, fields in {
        "accessibility_observation": "qualification",
        "amenity_observation": "qualification",
        "architecture_event": "event_kind project_state qualification target_area",
        "operating_period": "aerification_method affected_area maintenance_kind period_kind qualification",
        "physical_characteristics": "elevation_unit fairway_grass_name greens_grass_name landscape playing_surface qualification rough_grass_name tee_grass_name terrain",
        "policy_observation": "arrival_access_condition audience cancellation_charge_basis cancellation_charge_currency qualification season",
        "practice_observation": "driving_range_details driving_range_length_unit putting_green_details qualification range_technology_name",
        "price_observation": "amount_kind audience billing_basis conditions currency fee_kind product_name qualification residency residency_area_name season",
        "quality_rating": "dimension issuer_name qualification",
        "service_observation": "pro_shop_details qualification rental_details",
    }.items()
}
_CORE_TEXT = frozenset(
    [
        "access_qualification",
        "address_city",
        "address_postal_code",
        "address_region",
        "address_street_line1",
        "address_street_line2",
        "address_text",
        "arrival_reference",
        "booking_conditions",
        "country",
        "county",
        "description",
        "facility_name",
        "location_note",
        "name",
        "rated_category",
        "state",
    ]
)
_CHILD_ROWS = frozenset(
    ["aliases", "components", "course_inventory", "round_options", "tee_sets"]
)
_POSIX_PATH = r"""(?:^|[ "'`(\[={:;,<>|!?“”‘’«»])/+[^ /]"""
_EXPLICIT_PATH = r"file://|[a-zİıſK]:[\\/]|\\{2}"
_PATH_END = "[ /\\\\?&#;=,:'\"`()<>\\[\\]{}|!?“”‘’«»]"
_LOCAL_ROOT = (
    r"""(?:^|[ "'`(\[={:;,<>|!?“”‘’«»])/+"""
    r"(?:home|users|root|tmp|var|private|mnt|media|volumes|workspace|workspaces|task|tasks|"
    r"srv|opt|etc|usr|proc|sys|dev|run)"
    rf"(?=$|{_PATH_END}|\.+(?=$|{_PATH_END}))"
)
_PRIVATE_COMPONENT = (
    r"(?:[/\\?&#;=]|%2f)(?:private|secret|evidence|capture|retained|recovery)"
    rf"(?=$|[-._]|{_PATH_END})"
)
_PRIVATE_DECLARATION = (
    r"(?:^|[^a-z0-9_])(?:private +(?:copy|file|capture|path|directory|folder)|"
    r"local +(?:copy|file|directory|folder)|evidence +(?:copy|file|directory|folder)|"
    r"capture +(?:file|path)|capture *:|recovery +(?:sql|dump|file))(?=$|[^a-z0-9_])"
)


def _operational_text_path(path):
    if len(path) == 4 and path[0] == "relationships":
        return (
            path[1] in {"component", "round_option", "tee_set", "alias"}
            and type(path[2]) is int
            and path[3] in _CORE_TEXT
        )
    if (
        len(path) < 3
        or path[0] not in {"facilities", "courses"}
        or type(path[1]) is not int
    ):
        return False
    parents, field = path[2:-1], path[-1]
    while len(parents) >= 2 and parents[0] in _CHILD_ROWS and type(parents[1]) is int:
        parents = parents[2:]
    if not parents:
        return field in _CORE_TEXT
    if parents == ("address",):
        return field in {
            "text",
            "street_line1",
            "street_line2",
            "city",
            "region",
            "postal_code",
            "country",
        }
    if parents == ("arrival",):
        return field == "reference"
    if (
        len(parents) >= 3
        and parents[0] == "optional"
        and parents[1] in _PUBLIC_DOMAIN_TEXT
        and type(parents[2]) is int
    ):
        if len(parents) == 3:
            return field in _PUBLIC_DOMAIN_TEXT[parents[1]]
        return (
            len(parents) == 5
            and parents[1] == "architecture_event"
            and parents[3] == "credits"
            and type(parents[4]) is int
            and field == "name"
        )
    return False


def _has_private_path(text, *, operational=False):
    if _credential_syntax(text):
        return True
    scan = _without_http_links(text)
    if re.search(_EXPLICIT_PATH, scan):
        return True
    if not operational:
        return bool(re.search(_POSIX_PATH, scan))
    # Ordinary slash notation belongs to the public fact, not a filesystem
    # classifier. Still reject recognizable local artifacts or explicit evidence.
    return bool(
        re.search(_LOCAL_ROOT, scan)
        or (re.search(_POSIX_PATH, scan) and re.search(_PRIVATE_COMPONENT, scan))
        or (re.search(_POSIX_PATH, scan) and re.search(_PRIVATE_DECLARATION, scan))
    )


def _projection_record(value, path):
    if (
        len(path) == 2
        and path[0] == "source_licenses"
        and type(path[1]) is int
        and (
            not isinstance(value, dict)
            or not value.keys() <= _PUBLIC_LICENSE_FIELDS
            or any(v is not None and not isinstance(v, str) for v in value.values())
        )
    ):
        raise ValueError("unknown or nonpublic source-license material")
    if (
        len(path) == 3
        and path[:2] == ("provenance", "notes")
        and type(path[2]) is int
        and (
            not isinstance(value, dict)
            or set(value) != {"id"}
            or not isinstance(value["id"], str)
            or not value["id"]
        )
    ):
        raise ValueError("public notes contain IDs only")


def public_projection(value):
    """Validate explicit public roles; never rewrite stored operational text."""

    def visit(item, path=()):
        _projection_record(item, path)
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or _validation_scan(key) in _PRIVATE_KEYS:
                    raise ValueError("raw evidence in public transport")
                visit(key)
                visit(child, (*path, key))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, (*path, index))
        elif isinstance(item, str) and (
            "\0" in item
            or _has_private_path(
                item,
                operational=_operational_text_path(path),
            )
        ):
            raise ValueError("private path in public transport")

    visit(value)


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
    manifest, raw, _ = transport(root)
    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError("catalog exceeds browser size limit")
    public_projection(json.loads(raw))
    return manifest, raw


def credits_html(licenses, policy):
    """Keep public attribution accessible without adding catalog UI prose."""
    license_urls = {
        "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
        "CC-BY-SA-3.0-Unported": "https://creativecommons.org/licenses/by-sa/3.0/",
        "ODbL-1.0": "https://opendatacommons.org/licenses/odbl/1-0/",
    }

    def value_html(value, url=None):
        text = escape(str(value))
        if isinstance(url, str) and re.match(r"https?://[^\s]+\Z", url):
            return f'<a href="{escape(url, quote=True)}" rel="noreferrer">{text}</a>'
        return text

    sections = []
    for record in licenses:
        title = record.get("source") or record.get("attribution") or "Data source"
        fields = []
        for key in (
            "attribution",
            "license",
            "source_url",
            "policy_url",
            "changes",
            "applies_to",
            "scope",
            "copyright_notice",
            "disclaimer_notice",
        ):
            value = record.get(key)
            if value is None:
                continue
            url = (
                record.get("license_url") or license_urls.get(value)
                if key == "license"
                else value
                if key.endswith("_url")
                else None
            )
            fields.append(
                f"<dt>{escape(key.replace('_', ' ').title())}</dt><dd>{value_html(value, url)}</dd>"
            )
        sections.append(
            f"<section><h2>{escape(title)}</h2><dl>{''.join(fields)}</dl></section>"
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{escape(policy, quote=True)}">'
        '<title>Data credits · fairway</title><link rel="stylesheet" href="./styles.css">'
        '<body class="credits-page"><main><a href="./">fairway</a><h1>Data credits</h1>'
        + "".join(sections)
        + "</main></body></html>"
    ).encode()


def initial_map_bytes(value, manifest, states):
    # A reproducible map/search view, never a second catalog authority. Course
    # details still use the complete native projection and its browser validator.
    initial_map = {
        "map_format": 1,
        "revision": manifest["revision"],
        "catalog_release_key": manifest["catalog_release_key"],
        "catalog_sha256": manifest["files"]["catalog.json"]["sha256"],
        "counts": manifest["counts"],
        "facilities": [
            [
                f["facility_id"],
                f["name"],
                f["state"],
                (f.get("address") or {}).get("city"),
                [point["latitude"], point["longitude"], point["kind"]]
                if (point := f["map_location"]) is not None
                else None,
            ]
            for f in value["facilities"]
        ],
        # State geometry supports the existing state search/fitting behavior;
        # county geometry is not needed by this interface.
        "states": states,
    }
    raw = (
        json.dumps(
            initial_map, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode()
    if len(raw) > MAX_INITIAL_MAP_BYTES:
        raise ValueError("generated initial map too large")
    return raw


def version_ui_assets(payloads):
    """Publish one coherent content-addressed JS/module/CSS graph.

    Keep the existing source URLs as compatibility aliases. The page itself
    uses only hashed files, so fresh HTML cannot reuse older cached modules.
    """
    names = {name for name in ASSETS if Path(name).suffix in {".js", ".mjs", ".css"}}
    paths, compiling = {}, set()

    def compile_asset(name):
        if name in paths:
            return paths[name]
        if name not in names or name in compiling:
            raise ValueError("unknown or cyclic public UI module")
        compiling.add(name)
        body = payloads[name]
        if Path(name).suffix in {".js", ".mjs"}:

            def dependency(match):
                target = compile_asset(match[3][2:])
                return f"{match[1]}{match[2]}./{target}{match[2]}"

            body = re.sub(
                r"""(\bfrom\s+|\bimport\s*)(['"])(\./[^'"]+\.mjs)\2""",
                dependency,
                body.decode(),
            ).encode()
        path = Path(name)
        target = f"{path.stem}-{digest(body)}{path.suffix}"
        payloads[target] = body
        paths[name] = target
        compiling.remove(name)
        return target

    for name in sorted(names):
        compile_asset(name)
    return paths


def version_ui_html(html, paths):
    def reference(match):
        return f"{match[1]}./{paths[match[2]]}{match[3]}"

    return re.sub(
        r"""((?:src|href)=['"])\./([^/'"]+\.(?:js|css))(['"])""",
        reference,
        html,
    )


def build(root, output, commit, review_fixture=False):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Pages output must be new or empty")
    manifest, raw = native_transport(root, review_fixture)
    payloads = {
        name: (root / "src/fairway/static" / name).read_bytes() for name in ASSETS
    }
    ui_assets = version_ui_assets(payloads)
    item = manifest["files"]["catalog.json"]
    name = f"native-catalog-{item['sha256']}.json"
    payloads["data/" + name] = raw
    public = {**manifest, "files": {"catalog.json": {**item, "path": name}}}
    value = json.loads(raw)
    map_raw = initial_map_bytes(
        value,
        manifest,
        json.loads((root / "data/map-boundaries.json").read_bytes())["states"],
    )
    map_sha = digest(map_raw)
    map_name = f"initial-map-{map_sha}.json"
    payloads["data/" + map_name] = map_raw
    public["files"]["initial-map.json"] = {
        "path": map_name,
        "sha256": map_sha,
        "bytes": len(map_raw),
    }
    payloads["data/catalog-release.json"] = (
        json.dumps(public, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    policy = "default-src 'self'; base-uri 'none'; connect-src 'self' https://photon.komoot.io; img-src 'self' data: https://tile.openstreetmap.org; font-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'none'; object-src 'none'"
    payloads["credits.html"] = version_ui_html(
        credits_html(value["source_licenses"], policy).decode(), ui_assets
    ).encode()
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
    payloads["index.html"] = version_ui_html(html, ui_assets).encode()
    deployment = {
        "commit": commit,
        "revision": manifest["revision"],
        "catalog_release_key": manifest["catalog_release_key"],
        "catalog_sha256": item["sha256"],
        "counts": manifest["counts"],
        "review_fixture": review_fixture,
        "ui_assets": ui_assets,
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
