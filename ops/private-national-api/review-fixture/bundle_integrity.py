"""Exact local bundle and wheel verification, shared by preparation and review."""

import argparse
import hashlib
import json
import re
from pathlib import Path

DEPENDENCIES = {"geographiclib", "gunicorn", "networkx", "numpy", "packaging", "scipy"}
APPLICATIONS = {"fairway", "modo"}
FIXED_FILES = {
    "prepare_runtime.py",
    "fixture_router.py",
    "namespace_client.py",
    "run_review.py",
    "bundle_integrity.py",
    "runtime-requirements.arm64.txt",
    "application-requirements.txt",
    "wheel-manifest.json",
    "README.md",
}
MAX_WHEEL_BYTES = 128 * 1024 * 1024
MAX_BUNDLE_BYTES = 256 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def small_text(path):
    require(
        path.is_file() and not path.is_symlink() and path.stat().st_size <= 16384,
        "missing, linked or oversized manifest",
    )
    return path.read_text()


def wheel_entries(root):
    document = json.loads(small_text(root / "wheel-manifest.json"))
    require(
        set(document) == {"schema_version", "dependencies", "applications"}
        and document["schema_version"] == 1,
        "invalid wheel manifest",
    )
    result = {}
    for section, projects in (
        ("dependencies", DEPENDENCIES),
        ("applications", APPLICATIONS),
    ):
        entries = document[section]
        require(
            isinstance(entries, dict) and set(entries) == projects,
            "unexpected wheel projects",
        )
        for project, entry in entries.items():
            require(
                isinstance(entry, dict)
                and set(entry) == {"filename", "version", "sha256"},
                "invalid wheel entry",
            )
            version, name, digest = entry["version"], entry["filename"], entry["sha256"]
            require(
                isinstance(version, str) and re.fullmatch(r"[0-9.]+", version),
                "invalid version",
            )
            require(
                isinstance(name, str)
                and re.fullmatch(r"[A-Za-z0-9._-]+\.whl", name)
                and name.startswith(f"{project}-{version}-"),
                "invalid wheel filename",
            )
            require(
                isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                "invalid hash",
            )
            require(name not in result, "duplicate wheel")
            result[name] = digest
    runtime = "".join(
        f"{name}=={document['dependencies'][name]['version']} "
        f"--hash=sha256:{document['dependencies'][name]['sha256']}\n"
        for name in sorted(DEPENDENCIES)
    )
    actual_runtime = small_text(root / "runtime-requirements.arm64.txt")
    require(
        sorted(actual_runtime.splitlines()) == sorted(runtime.splitlines()),
        "runtime requirements do not match the six pinned wheels",
    )
    application = "".join(
        f"wheels/{document['applications'][name]['filename']} "
        f"--hash=sha256:{document['applications'][name]['sha256']}\n"
        for name in sorted(APPLICATIONS)
    )
    require(
        small_text(root / "application-requirements.txt") == application,
        "application requirements must name exactly two local hash-locked wheels",
    )
    return result


def verify(root):
    root = Path(root)
    wheels = wheel_entries(root)
    expected = FIXED_FILES | {f"wheels/{name}" for name in wheels}
    checksums = {}
    for line in small_text(root / "SHA256SUMS").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._/-]+)", line)
        require(match is not None, "invalid checksum entry")
        digest, name = match.groups()
        require(
            name in expected and name not in checksums,
            "unlisted or duplicate checksum entry",
        )
        checksums[name] = digest
    require(
        set(checksums) == expected, "checksum manifest must list the exact bundle files"
    )
    wanted = expected
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "bundle links are forbidden")
        name = str(path.relative_to(root))
        if path.is_dir():
            require(name == "wheels", "unexpected bundle directory")
        else:
            require(path.is_file(), "bundle special files are forbidden")
            actual.add(name)
    require(actual == wanted | {"SHA256SUMS"}, "extra or missing bundle files")
    require(
        sum((root / name).stat().st_size for name in actual) <= MAX_BUNDLE_BYTES,
        "aggregate bundle exceeds the 256 MiB input budget",
    )
    for name in wanted:
        path = root / name
        require(
            path.stat().st_size <= MAX_WHEEL_BYTES, "bundle file exceeds size limit"
        )
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        require(digest == checksums[name], "bundle checksum mismatch")
        if name.startswith("wheels/"):
            require(
                digest == wheels[path.name], "wheel hash disagrees with requirement"
            )
    return {"files": len(actual), "wheels": len(wheels)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parent)))


if __name__ == "__main__":
    main()
