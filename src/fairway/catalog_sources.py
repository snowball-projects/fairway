"""Canonical source identities and retained hold scopes. No source requests."""

import json
import re
from hashlib import sha256
from urllib.parse import urlsplit

LEGACY_HOLD_REASON = "Retained source-stop file; see source_stops document. Not permission for new enrichment."
HOST_PATTERN = re.compile(
    r"(?i)(?<![\w.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}(?![\w.-])"
)
URL_PATTERN = re.compile(r'https?://[^\s<>"\']+')


def canonical_host(value):
    if not isinstance(value, str) or not value:
        raise ValueError("missing source hostname")
    host = value.rstrip(".").encode("idna").decode("ascii").lower()
    if not host or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", part)
        for part in host.split(".")
    ):
        raise ValueError("invalid source hostname")
    return host


def canonical_percent(value):
    unreserved = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"

    def escape(match):
        character = chr(int(match[0][1:], 16))
        return character if character in unreserved else match[0].upper()

    return re.sub(r"%[0-9a-fA-F]{2}", escape, value)


def canonical_path(value):
    # RFC3986 dot segments preserve repeated slashes and reserved delimiters.
    pending = canonical_percent(value or "/")
    output = ""
    while pending:
        if pending.startswith("../"):
            pending = pending[3:]
        elif pending.startswith(("./", "/./")):
            pending = pending[2:]
        elif pending == "/.":
            pending = "/"
        elif pending.startswith("/../"):
            pending = pending[3:]
            output = output.rsplit("/", 1)[0]
        elif pending == "/..":
            pending = "/"
            output = output.rsplit("/", 1)[0]
        elif pending in {".", ".."}:
            pending = ""
        else:
            boundary = pending.find("/", 1 if pending.startswith("/") else 0)
            if boundary < 0:
                output += pending
                pending = ""
            else:
                output += pending[:boundary]
                pending = pending[boundary:]
    return output or "/"


def resource_identity(value, *, hold=False):
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("invalid source URL")
    host = canonical_host(parsed.hostname)
    port = parsed.port
    if port == ({"http": 80, "https": 443}[parsed.scheme.lower()]):
        port = None
    # Publisher-scoped holds cover ordinary www and protocol delivery aliases, while
    # preserving exact path/query boundaries. Registry identity preserves the scheme/host.
    if hold:
        host = host.removeprefix("www.")
    identity = [
        None if hold else parsed.scheme.lower(),
        host,
        port,
        canonical_path(parsed.path),
        canonical_percent(parsed.query),
    ]
    return json.dumps(identity, separators=(",", ":"))


def _host(value):
    return canonical_host(value).removeprefix("www.")


def retained_holds(controls):
    """Materialize structured host, publisher and exact-resource holds with provenance.

    Field meanings matter: a profile URL is not a publisher ban. The complete retained
    item remains attached to every scope; summaries do not replace original decisions.
    """
    found = {}

    def add(kind, value, path, item):
        key = (
            resource_identity(value, hold=True) if kind == "resource" else _host(value)
        )
        payload = {
            "control_path": path,
            "control": item,
            "scope_kind": kind,
            "original_scope": value,
        }
        identifier = sha256(
            json.dumps([kind, key, path], ensure_ascii=False).encode()
        ).hexdigest()
        found[identifier] = (
            identifier,
            kind,
            key,
            json.dumps(payload, sort_keys=True, ensure_ascii=False),
        )

    def text_scopes(value, path, item, kind="host"):
        if isinstance(value, list):
            for number, part in enumerate(value):
                text_scopes(part, f"{path}/{number}", item, kind)
        elif isinstance(value, str):
            urls = URL_PATTERN.findall(value)
            for url in urls:
                add("resource", url.rstrip(".,;)"), path, item)
            rest = URL_PATTERN.sub("", value)
            for host in HOST_PATTERN.findall(rest):
                add(kind, host, path, item)

    def visit(item, path):
        if isinstance(item, list):
            for number, part in enumerate(item):
                visit(part, f"{path}/{number}")
            return
        if not isinstance(item, dict):
            return
        kind = item.get("kind", "")
        scope_text = item.get("scope", "")
        profile = (
            "profile_specific" in kind
            or "no publisher-wide" in item.get("disposition", "").lower()
            or (
                isinstance(scope_text, str)
                and "no publisher-wide" in scope_text.lower()
            )
        )
        shared_government = (
            isinstance(scope_text, str) and "no statewide" in scope_text.lower()
        )
        for key, value in item.items():
            child = f"{path}/{key}"
            if key in {"domains", "ordinary_aliases"}:
                text_scopes(value, child, item, "publisher")
            elif key in {"host", "host_group", "publisher_group"}:
                if key == "host" and item.get("path"):
                    add("resource", "https://" + value + item["path"], child, item)
                else:
                    add("publisher", value, child, item)
            elif (
                key in {"url", "source_url", "control_url", "policy_url"}
                and isinstance(value, str)
                and value.startswith(("http://", "https://"))
            ):
                parsed = urlsplit(value)
                if profile or (
                    parsed.path not in {"", "/", "/robots.txt"}
                    and key == "url"
                    and "publisher" not in kind
                ):
                    add("resource", value, child, item)
                else:
                    add(
                        "host" if shared_government else "publisher",
                        parsed.hostname,
                        child,
                        item,
                    )
            elif key in {"targets", "scope", "restricted_or_unresolved_scope"}:
                text_scopes(value, child, item)
            elif key == "important_inherited_stop_groups" and isinstance(value, list):
                # Only the explicitly held initial clause; later clauses can name
                # independently permitted publishers and must not become holds.
                for number, clause in enumerate(value):
                    text_scopes(
                        clause.split(";", 1)[0], f"{child}/{number}", item, "publisher"
                    )
            elif key == "recent_exact_stops" and isinstance(value, dict):
                for scopes, reason in value.items():
                    text_scopes(
                        scopes, child + "/" + scopes, {"reason": reason}, "publisher"
                    )
            elif HOST_PATTERN.fullmatch(key):
                # Root domain-keyed stop records, never *.json filenames/paths.
                add("publisher", key, child, value)
                visit(value, child)
            else:
                visit(value, child)

    visit(controls, "")
    return list(found.values())


def install_holds(db, controls):
    db.execute("DELETE FROM source_hold WHERE reason=?", (LEGACY_HOLD_REASON,))
    db.execute("DELETE FROM source_hold_scope")
    db.executemany(
        "INSERT INTO source_hold_scope VALUES (?,?,?,?)", retained_holds(controls)
    )


def ensure_source_allowed(db, url):
    host = _host(urlsplit(url).hostname)
    for domain, reason in db.execute("SELECT domain,reason FROM source_hold"):
        normalized = _host(domain)
        if host == normalized or host.endswith("." + normalized):
            raise ValueError("publisher is on a retained source hold")
    target = resource_identity(url, hold=True)
    for kind, key in db.execute("SELECT scope_kind,scope_key FROM source_hold_scope"):
        if kind == "resource":
            parts = json.loads(key)
            parts[3] = canonical_path(parts[3])
            parts[4] = canonical_percent(parts[4])
            key = json.dumps(parts, separators=(",", ":"))
        if (
            (kind == "resource" and target == key)
            or (kind == "host" and host == key)
            or (kind == "publisher" and (host == key or host.endswith("." + key)))
        ):
            raise ValueError("source is on a retained scoped hold")
