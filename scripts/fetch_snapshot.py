"""Fetch and verify fairway's immutable road snapshot."""

import os
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from fairway.snapshots import is_https_url, load_catalog

MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


parser = ArgumentParser()
parser.add_argument(
    "snapshot",
    nargs="?",
    default=os.environ.get("FAIRWAY_SNAPSHOT", "chicago-static-v1"),
)
args = parser.parse_args()
catalog = load_catalog("data/snapshots.json")
try:
    snapshot = next(item for item in catalog if item.identifier == args.snapshot)
except StopIteration as error:
    raise SystemExit(f"unknown road snapshot: {args.snapshot}") from error

destination = Path("data") / snapshot.file
if destination.exists() and digest(destination) == snapshot.sha256:
    raise SystemExit

destination.parent.mkdir(parents=True, exist_ok=True)
temporary = None
try:
    # load_catalog permits only HTTPS snapshot URLs.
    with (
        urlopen(  # nosec B310
            snapshot.url, timeout=DOWNLOAD_TIMEOUT_SECONDS
        ) as response,
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
        while chunk := response.read(1024 * 1024):
            received += len(chunk)
            if received > MAX_SNAPSHOT_BYTES:
                raise RuntimeError("road snapshot exceeds the download limit")
            result.update(chunk)
            output.write(chunk)
    if result.hexdigest() != snapshot.sha256:
        raise RuntimeError("road snapshot checksum does not match")
    temporary.replace(destination)
finally:
    if temporary is not None:
        temporary.unlink(missing_ok=True)
