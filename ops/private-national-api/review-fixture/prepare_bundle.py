"""Prepare a verified local review bundle; no downloads, installs or Docker calls."""

import argparse
import hashlib
import json
import re
import shutil
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FILES = (
    "Dockerfile.api",
    "Dockerfile.fixture",
    "fixture_router.py",
    "run_review.py",
    "bundle_integrity.py",
    "runtime-requirements.arm64.txt",
)
MAX_WHEEL_BYTES = 128 * 1024 * 1024


def verified(path, expected):
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("expected SHA256 must contain 64 lowercase hexadecimal digits")
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_WHEEL_BYTES:
        raise ValueError(f"missing, linked or oversized wheel: {path.name}")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"wheel checksum mismatch: {path.name}")
    return path


def prepare(output, dependencies, fairway, fairway_hash, modo, modo_hash):
    if not output.is_absolute() or output.exists():
        raise ValueError("output must be an absolute path to a new directory")
    if not output.parent.is_dir():
        raise ValueError("output parent must already exist")
    # Exact official filenames/hashes come from the repository lock, not an index.
    lock = tomllib.loads((REPO / "uv.lock").read_text())
    selected = []
    manifest = {"schema_version": 1, "dependencies": {}, "applications": {}}
    for line in (HERE / "runtime-requirements.arm64.txt").read_text().splitlines():
        match = re.fullmatch(r"([a-z]+)==([0-9.]+) --hash=sha256:([0-9a-f]{64})", line)
        if match is None:
            raise ValueError("invalid offline requirement")
        name, version, digest = match.groups()
        package = next(
            p for p in lock["package"] if p["name"] == name and p["version"] == version
        )
        wheel = next(w for w in package["wheels"] if w["hash"] == f"sha256:{digest}")
        filename = Path(urlsplit(wheel["url"]).path).name
        if not filename.endswith(".whl"):
            raise ValueError("lock entry is not a wheel")
        selected.append(verified(dependencies / filename, digest))
        manifest["dependencies"][name] = {
            "filename": filename,
            "version": version,
            "sha256": digest,
        }
    versions = {p["name"]: p["version"] for p in lock["package"]}
    for path, name, digest in (
        (fairway, "fairway", fairway_hash),
        (modo, "modo", modo_hash),
    ):
        if path.name != f"{name}-{versions[name]}-py3-none-any.whl":
            raise ValueError(f"expected the locked {name} wheel filename")
        selected.append(verified(path, digest))
        manifest["applications"][name] = {
            "filename": path.name,
            "version": versions[name],
            "sha256": digest,
        }
    # Verify everything before creating output; never remove an existing directory.
    output.mkdir(mode=0o700)
    try:
        (output / "wheels").mkdir()
        for path in selected:
            shutil.copyfile(path, output / "wheels" / path.name)
        for filename in FILES:
            shutil.copyfile(HERE / filename, output / filename)
        shutil.copyfile(
            REPO / "docs/disposable-container-test.md", output / "README.md"
        )
        (output / "wheel-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        (output / "application-requirements.txt").write_text(
            "".join(
                f"wheels/{manifest['applications'][name]['filename']} "
                f"--hash=sha256:{manifest['applications'][name]['sha256']}\n"
                for name in sorted(manifest["applications"])
            )
        )
        (output / ".dockerignore").write_text(
            "*\n!Dockerfile.api\n!Dockerfile.fixture\n!fixture_router.py\n"
            "!runtime-requirements.arm64.txt\n!application-requirements.txt\n"
            "!wheel-manifest.json\n!SHA256SUMS\n!bundle_integrity.py\n!wheels/\n!wheels/*.whl\n"
        )
        paths = sorted(p for p in output.rglob("*") if p.is_file())
        lines = []
        for path in paths:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            lines.append(f"{digest}  {path.relative_to(output)}\n")
        (output / "SHA256SUMS").write_text("".join(lines))
        from bundle_integrity import verify

        verify(output)
    except Exception:
        shutil.rmtree(output)
        raise
    return {
        "output": str(output),
        "wheels": len(selected),
        "docker_calls": 0,
        "network_calls": 0,
        "image_builds": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dependency-wheels", type=Path, required=True)
    parser.add_argument("--fairway-wheel", type=Path, required=True)
    parser.add_argument("--fairway-sha256", required=True)
    parser.add_argument("--modo-wheel", type=Path, required=True)
    parser.add_argument("--modo-sha256", required=True)
    args = parser.parse_args()
    try:
        result = prepare(
            args.output,
            args.dependency_wheels,
            args.fairway_wheel,
            args.fairway_sha256,
            args.modo_wheel,
            args.modo_sha256,
        )
    except (OSError, ValueError, StopIteration) as error:
        parser.error(str(error) or "wheel entry does not match the committed lock")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
