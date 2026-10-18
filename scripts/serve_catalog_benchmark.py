"""Loopback-only, precompressed HTTP benchmark server, including conditional cache."""

import argparse
import gzip
import hashlib
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    # Compress before timing, so server gzip work never masquerades as latency.
    assets = {}
    for path in args.root.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            packed = gzip.compress(raw, mtime=0)
            assets["/" + path.relative_to(args.root).as_posix()] = (
                packed,
                hashlib.sha256(raw).hexdigest(),
                mimetypes.guess_type(path)[0] or "application/octet-stream",
            )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            path = unquote(url.path)
            if path.endswith("/"):
                path += "index.html"
            if path not in assets:
                self.send_error(404)
                return
            packed, checksum, content_type = assets[path]
            etag = '"' + checksum + '"'
            self.send_response(
                304 if self.headers.get("If-None-Match") == etag else 200
            )
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "public, max-age=600")
            self.send_header("Content-Type", content_type)
            # The probe fetches the identical encoded representation separately,
            # then times gzip, UTF-8, SHA, parse and validation in isolation.
            if url.query != "gzip-bytes":
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(packed)))
            self.end_headers()
            if self.headers.get("If-None-Match") != etag:
                self.wfile.write(packed)

    print(
        f"Precompressed {len(assets)} assets; http://127.0.0.1:{args.port}", flush=True
    )
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
