import io
import json

import networkx as nx
from modo import CompactRoadGraph

from fairway import app


def request(path="/", method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    status = None

    def start_response(value, _headers):
        nonlocal status
        status = value

    result = b"".join(app.application({
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }, start_response))
    return status, result


def test_serves_dashboard():
    status, body = request()
    assert status == "200 OK"
    assert b"fairway" in body
    assert b'href="/leaflet.css"' in body
    assert b"service policy" in body

    status, body = request("/leaflet.css")
    assert status == "200 OK"
    assert b".leaflet-tile" in body


def test_rejects_too_few_origins():
    status, body = request("/api/evaluations", "POST", {"origins": [[1, 2]]})
    assert status == "400 Bad Request"
    assert b"provide between 2 and 32 origins" in body


def test_calculates_both_regions_and_selected_point(monkeypatch):
    graph = nx.DiGraph()
    graph.add_node("a", y=0, x=0)
    graph.add_node("b", y=0, x=10)
    graph.add_node("x", y=1, x=2)
    graph.add_edge("a", "x", travel_time=1)
    graph.add_edge("b", "x", travel_time=9)
    monkeypatch.setattr(app, "_graph", CompactRoadGraph.from_networkx(graph))
    app._analyses.clear()

    status, body = request("/api/evaluations", "POST", {
        "origins": [[0, 0], [0, 10]], "tolerance_seconds": 60})
    result = json.loads(body)
    assert status == "200 OK"
    assert result["total"]["region"] == [[1.0, 2.0]]
    assert result["maximum"]["region"] == [[1.0, 2.0]]

    status, body = request(
        f"/api/evaluations/{result['id']}/travel-times", "POST",
        {"coordinate": [1, 2]})
    assert status == "200 OK"
    assert json.loads(body)["travel_times_seconds"] == [1.0, 9.0]


def test_unknown_route_is_not_found():
    assert request("/missing")[0] == "404 Not Found"
