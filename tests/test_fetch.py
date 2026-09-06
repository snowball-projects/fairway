import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from fairway import fetch as fetch_module
from fairway import paths


def catalog(path, content):
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshots": [
                    {
                        "id": "test-roads-v1",
                        "file": "roads.npz",
                        "url": "https://example.test/roads.npz",
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "cost_profile": "static-test-v1",
                        "core_bounds": [-0.5, -0.5, 0.5, 0.5],
                        "graph_bounds": [-1, -1, 1, 1],
                    }
                ],
            }
        )
    )


class Response:
    def __init__(self, content, *, length=None, url="https://example.test/roads.npz"):
        self.content = content
        self.position = 0
        self.headers = {}
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def geturl(self):
        return self.url

    def read1(self, size):
        result = self.content[self.position : self.position + size]
        self.position += len(result)
        return result


class Opener:
    def __init__(self, response):
        self.response = response

    def open(self, url, timeout):
        assert url == "https://example.test/roads.npz"
        assert 0 < timeout <= fetch_module.DOWNLOAD_TIMEOUT_SECONDS
        return self.response


def test_fetches_and_verifies_snapshot_to_a_staged_file(tmp_path, monkeypatch):
    content = b"road snapshot"
    catalog_path = tmp_path / "snapshots.json"
    destination = tmp_path / "roads.npz"
    catalog(catalog_path, content)
    monkeypatch.setattr(
        fetch_module, "_OPENER", Opener(Response(content, length=len(content)))
    )

    assert fetch_module.fetch("test-roads-v1", destination, catalog_path) == destination
    assert destination.read_bytes() == content


def test_fetch_refuses_to_replace_its_catalog_or_a_resolving_alias(
    tmp_path, monkeypatch
):
    content = b"road snapshot"
    catalog_path = tmp_path / "snapshots.json"
    alias = tmp_path / "catalog-alias.json"
    catalog(catalog_path, content)
    alias.symlink_to(catalog_path)
    original = catalog_path.read_bytes()

    for destination in (catalog_path, alias):
        with pytest.raises(ValueError, match="must differ"):
            fetch_module.fetch("test-roads-v1", destination, catalog_path)
    assert catalog_path.read_bytes() == original


def test_fetch_rejects_mismatched_length_without_replacing_destination(
    tmp_path, monkeypatch
):
    content = b"road snapshot"
    catalog_path = tmp_path / "snapshots.json"
    destination = tmp_path / "roads.npz"
    catalog(catalog_path, content)
    destination.write_bytes(b"existing")
    monkeypatch.setattr(
        fetch_module, "_OPENER", Opener(Response(content, length=len(content) + 1))
    )

    with pytest.raises(RuntimeError, match="content length does not match"):
        fetch_module.fetch("test-roads-v1", destination, catalog_path)
    assert destination.read_bytes() == b"existing"


def test_fetch_enforces_a_total_download_deadline(tmp_path, monkeypatch):
    content = b"road snapshot"
    catalog_path = tmp_path / "snapshots.json"
    catalog(catalog_path, content)
    monkeypatch.setattr(fetch_module, "_OPENER", Opener(Response(content)))
    times = iter((0, 0, fetch_module.DOWNLOAD_TIMEOUT_SECONDS + 1))
    monkeypatch.setattr(fetch_module, "monotonic", lambda: next(times))

    with pytest.raises(RuntimeError, match="timed out"):
        fetch_module.fetch("test-roads-v1", tmp_path / "roads.npz", catalog_path)


def test_redirect_validation_rejects_every_non_https_hop():
    with pytest.raises(RuntimeError, match="outside HTTPS"):
        fetch_module._redirect_target(
            "https://example.test/roads.npz",
            {"Location": "http://cdn.example.test/roads.npz"},
        )


def test_redirects_close_without_reading_bodies_and_share_one_deadline(monkeypatch):
    class RedirectBody:
        closed = False

        def read(self):
            raise AssertionError("redirect bodies must not be read")

        def close(self):
            self.closed = True

    body = RedirectBody()
    redirect = HTTPError(
        "https://example.test/roads.npz",
        302,
        "Found",
        {"Location": "https://cdn.example.test/roads.npz"},
        body,
    )
    response = Response(b"road snapshot", url="https://cdn.example.test/roads.npz")

    class RedirectingOpener:
        def __init__(self):
            self.calls = []

        def open(self, url, timeout):
            self.calls.append((url, timeout))
            if len(self.calls) == 1:
                raise redirect
            return response

    opener = RedirectingOpener()
    monkeypatch.setattr(fetch_module, "_OPENER", opener)
    times = iter((1, 2))
    monkeypatch.setattr(fetch_module, "monotonic", lambda: next(times))

    assert (
        fetch_module._open_snapshot("https://example.test/roads.npz", deadline=10)
        is response
    )
    assert body.closed is True
    assert opener.calls == [
        ("https://example.test/roads.npz", 9),
        ("https://cdn.example.test/roads.npz", 8),
    ]


def test_graph_path_keeps_custom_catalogs_and_cache_roots_safe(tmp_path, monkeypatch):
    monkeypatch.delenv("FAIRWAY_GRAPH", raising=False)
    custom_catalog = tmp_path / "custom" / "snapshots.json"
    assert paths.graph_path("roads.npz", custom_catalog) == (
        custom_catalog.parent / "roads.npz"
    )

    monkeypatch.setattr(paths, "REPOSITORY_DATA", tmp_path / "missing")
    for configured in ("", "relative/cache"):
        monkeypatch.setenv("XDG_CACHE_HOME", configured)
        result = paths.graph_path("roads.npz")
        assert result == Path.home() / ".cache" / "fairway" / "roads.npz"
        assert result.is_absolute()
