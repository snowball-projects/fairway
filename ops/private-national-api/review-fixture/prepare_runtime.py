"""Fixed offline installer inside the disposable, capped preparation container."""

import os
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
from bundle_integrity import verify


def main():
    if not __debug__:
        raise RuntimeError("verification requires unoptimized Python")
    verify(Path("/inputs"))
    # The controller checks effective isolation before releasing this barrier.
    while not Path("/out/allow-install").exists():
        time.sleep(1)
    Path("/out/tmp").mkdir()
    Path("/out/site").mkdir()
    os.environ["TMPDIR"] = "/out/tmp"
    for requirement in (
        "runtime-requirements.arm64.txt",
        "application-requirements.txt",
    ):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--isolated",
                "--disable-pip-version-check",
                "install",
                "--target=/out/site",
                "--no-index",
                "--no-deps",
                "--no-cache-dir",
                "--no-compile",
                "--only-binary=:all:",
                "--require-hashes",
                "--find-links=/inputs/wheels",
                "-r",
                requirement,
            ],
            cwd="/inputs",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=120,
        )
    Path("/out/ready").touch()
    # Keep the bounded tmpfs alive for Docker copy; outer timeout is 180 seconds.
    time.sleep(180)


if __name__ == "__main__":
    main()
