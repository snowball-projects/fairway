"""Fetch and verify fairway's immutable road snapshot."""

import os
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, build_opener

from .paths import SNAPSHOT_CATALOG_PATH, graph_path
from .snapshots import is_https_url, load_catalog

MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_CHUNK_BYTES = 64 * 1024
MAX_REDIRECTS = 5
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


_OPENER = build_opener(_NoRedirectHandler())


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def _redirect_target(current_url, headers):
    location = headers.get("Location") or headers.get("URI")
    try:
        target = urljoin(current_url, location)
    except (TypeError, ValueError) as error:
        raise RuntimeError("road snapshot redirect is invalid") from error
    if not is_https_url(target):
        raise RuntimeError("road snapshot redirected outside HTTPS")
    return target


def _open_snapshot(url, deadline):
    for _redirect in range(MAX_REDIRECTS + 1):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise RuntimeError("road snapshot download timed out")
        try:
            return _OPENER.open(url, timeout=remaining)
        except HTTPError as error:
            try:
                if error.code not in REDIRECT_CODES:
                    raise RuntimeError(
                        f"road snapshot download failed with status {error.code}"
                    ) from error
                url = _redirect_target(url, error.headers)
            finally:
                error.close()
    raise RuntimeError("road snapshot has too many redirects")


def fetch(snapshot_id, destination=None, catalog_path=SNAPSHOT_CATALOG_PATH):
    catalog_path = Path(catalog_path)
    catalog = load_catalog(catalog_path)
    try:
        snapshot = next(item for item in catalog if item.identifier == snapshot_id)
    except StopIteration as error:
        raise ValueError(f"unknown road snapshot: {snapshot_id}") from error
    destination = Path(destination or graph_path(snapshot.file, catalog_path))
    if destination.resolve() == catalog_path.resolve():
        raise ValueError("snapshot destination must differ from its catalog")
    if destination.exists() and not destination.is_file():
        raise ValueError("snapshot destination must be a file")
    if destination.exists() and digest(destination) == snapshot.sha256:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        deadline = monotonic() + DOWNLOAD_TIMEOUT_SECONDS
        with (
            _open_snapshot(snapshot.url, deadline) as response,
            NamedTemporaryFile(dir=destination.parent, delete=False) as output,
        ):
            temporary = Path(output.name)
            if not is_https_url(response.geturl()):
                raise RuntimeError("road snapshot redirected outside HTTPS")
            declared_length = response.headers.get("Content-Length")
            if declared_length is not None:
                try:
                    declared_length = int(declared_length)
                except ValueError as error:
                    raise RuntimeError(
                        "road snapshot has an invalid content length"
                    ) from error
                if not 0 <= declared_length <= MAX_SNAPSHOT_BYTES:
                    raise RuntimeError("road snapshot exceeds the download limit")
            result = sha256()
            received = 0
            read = response.read1 if hasattr(response, "read1") else response.read
            while True:
                if monotonic() >= deadline:
                    raise RuntimeError("road snapshot download timed out")
                chunk = read(DOWNLOAD_CHUNK_BYTES)
                if monotonic() > deadline:
                    raise RuntimeError("road snapshot download timed out")
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_SNAPSHOT_BYTES:
                    raise RuntimeError("road snapshot exceeds the download limit")
                result.update(chunk)
                output.write(chunk)
            if declared_length is not None and received != declared_length:
                raise RuntimeError("road snapshot content length does not match")
        if result.hexdigest() != snapshot.sha256:
            raise RuntimeError("road snapshot checksum does not match")
        temporary.replace(destination)
        temporary = None
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "snapshot",
        nargs="?",
        default=os.environ.get("FAIRWAY_SNAPSHOT", "chicago-static-v1"),
    )
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--catalog", type=Path, default=SNAPSHOT_CATALOG_PATH)
    args = parser.parse_args()
    fetch(args.snapshot, args.destination, args.catalog)


if __name__ == "__main__":
    main()
