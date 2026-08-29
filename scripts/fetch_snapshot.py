"""Fetch and verify fairway's immutable road snapshot."""

from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

NAME = "chicago-static-v1.npz"
URL = "https://github.com/snowball-projects/fairway/releases/download/chicago-static-v1/" + NAME
CHECKSUM = "c095461796adda233387c66f5b32c433c0d8a76d184902daf848fed1a3f2d39c"
destination = Path("data") / NAME

if destination.exists() and sha256(destination.read_bytes()).hexdigest() == CHECKSUM:
    raise SystemExit

destination.parent.mkdir(exist_ok=True)
with urlopen(URL) as response:
    content = response.read()
if sha256(content).hexdigest() != CHECKSUM:
    raise RuntimeError("road snapshot checksum does not match")
destination.write_bytes(content)
