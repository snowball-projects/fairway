"""Finite private HTTP smoke test using synthetic Chicago inputs.

Run only against an already authorized private router. This starts and stops a
local loopback API within the command; it does not deploy anything or configure
the router. Output contains counts/timings, never submitted coordinates.
"""

import argparse
import http.client
import json
import threading
from pathlib import Path
from time import monotonic
from urllib.request import ProxyHandler, build_opener

from fairway.national_api import APIConfig, NoRedirect
from fairway.national_server import RANKING_PATH, PrivateHTTPServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router", default="http://127.0.0.1:8003")
    parser.add_argument("--dataset", default="us-261011-operator-declared")
    args = parser.parse_args()
    import fairway

    catalog = (
        Path(fairway.__file__).with_name("static") / "data" / "public-courses.json"
    )
    config = APIConfig(args.router, str(catalog), args.dataset)
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def router_status():
        with opener.open(
            config.endpoint.rstrip("/") + "/status", timeout=5
        ) as response:
            assert response.status == 200
            raw = response.read(65537)
            assert len(raw) <= 65536
            document = json.loads(raw)
            return document.get("version"), document.get("has_tiles")

    before = router_status()
    server = PrivateHTTPServer(("127.0.0.1", 0), config)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}
    )
    thread.start()
    summaries = []
    try:
        for objective in ("maximum", "combined"):
            raw = json.dumps(
                {
                    "origins": [[41.90, -87.66], [42.06, -87.88]],
                    "objective": objective,
                    "holes": [9, 18],
                }
            ).encode()
            client = http.client.HTTPConnection(*server.server_address, timeout=35)
            started = monotonic()
            try:
                client.request(
                    "POST",
                    RANKING_PATH,
                    body=raw,
                    headers={"Content-Type": "application/json"},
                )
                response = client.getresponse()
                result = json.loads(response.read())
                status = response.status
            finally:
                client.close()
            metadata = result.get("metadata", {})
            summaries.append(
                {
                    "objective": objective,
                    "http_status": status,
                    "elapsed_seconds": round(monotonic() - started, 3),
                    "ranked_facilities": len(result.get("facilities", [])),
                    "provider_requests": metadata.get("provider_requests"),
                    "matrix_cells": metadata.get("matrix_cells"),
                    "evaluated_candidates": metadata.get("area_search", {}).get(
                        "evaluated_candidates"
                    ),
                    "approximate": metadata.get("approximate"),
                    "traffic_basis": metadata.get("traffic_basis"),
                    "catalog_facility_count": metadata.get("catalog_facility_count"),
                    "error_code": result.get("error", {}).get("code"),
                }
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    after = router_status()
    print(
        json.dumps(
            {
                "router_version": before[0],
                "router_has_tiles": before[1],
                "router_status_unchanged": before == after,
                "cases": summaries,
            },
            indent=2,
        )
    )
    return (
        0
        if all(row["http_status"] == 200 for row in summaries) and before == after
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
