"""Shared scalar validation and local-storage guards for the native5 path.

These are version-independent guards. No legacy schema, JSON catalog adapter,
reader, importer or automatic migration is imported by native5 production code.
"""

import json
import math
import re
from datetime import date
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return sha256(encoded(value).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_date(value):
    require(
        isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
        "date must be YYYY-MM-DD",
    )
    date.fromisoformat(value)


def valid_url(value):
    require(isinstance(value, str), "URL must be text")
    parsed = urlsplit(value)
    require(
        parsed.scheme in {"https", "http"}
        and parsed.hostname
        and not (parsed.username or parsed.password),
        "invalid source/link URL",
    )


def local_path(path):
    """Refuse known network filesystems; operationally only the integrator owns this path."""
    path = Path(path).resolve()
    mounts = Path("/proc/mounts")
    if mounts.exists():
        entries = [line.split() for line in mounts.read_text().splitlines()]
        matches = [
            row
            for row in entries
            if path.is_relative_to(Path(row[1].replace("\\040", " ")))
        ]
        if matches:
            nearest = max(matches, key=lambda row: len(row[1]))
            require(
                nearest[2]
                not in {
                    "nfs",
                    "nfs4",
                    "cifs",
                    "smbfs",
                    "sshfs",
                    "fuse.sshfs",
                    "9p",
                    "ceph",
                    "glusterfs",
                },
                "catalog must be on local storage",
            )
    return path


def distance_km(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    hav = (
        math.sin((b - a) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(hav)))
