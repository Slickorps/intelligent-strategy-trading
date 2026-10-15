"""Integration tests for the visual strategy editor."""

from fastapi.testclient import TestClient

from ist.api.main import create_app
from ist.core import config


def test_node_types_endpoint() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/strategies/node-types")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    types = {entry["type"] for entry in body["data"]}
    assert "IndicatorNode" in types
    assert "ActionNode" in types
    assert "RiskNode" in types

    indicator = next(e for e in body["data"] if e["type"] == "IndicatorNode")
    assert any(p["name"] == "indicator" for p in indicator["params"])


def test_editor_page_served() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/editor")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Visual Strategy Editor" in response.text


def test_editor_static_assets_served() -> None:
    app = create_app()
    with TestClient(app) as client:
        js = client.get("/static/editor.js")
        css = client.get("/static/editor.css")

    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]


def test_editor_exempt_but_api_protected(monkeypatch) -> None:
    monkeypatch.setattr(
        config, "_settings", config.Settings(api_key="secret-key"),
    )
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/editor").status_code == 200
        assert client.get("/static/editor.js").status_code == 200
        assert client.get("/strategies/node-types").status_code == 401
        authed = client.get(
            "/strategies/node-types", headers={"X-API-Key": "secret-key"},
        )

    assert authed.status_code == 200


def test_editor_payload_round_trip() -> None:
    app = create_app()
    payload = {
        "name": "Editor Strategy",
        "nodes": [
            {
                "id": "node1",
                "type": "DataSourceNode",
                "params": {"symbol": "EURUSD"},
                "position": {"x": 10, "y": 20},
            },
            {
                "id": "node2",
                "type": "ActionNode",
                "params": {"action": "buy"},
                "position": {"x": 240, "y": 20},
            },
        ],
        "connections": [{"from": "node1", "to": "node2"}],
    }

    with TestClient(app) as client:
        created = client.post("/strategies", json=payload)
        assert created.status_code == 201
        strategy_id = created.json()["data"]["id"]

        flow = client.get(f"/strategies/{strategy_id}/flowchart")

    assert flow.status_code == 200
    data = flow.json()["data"]
    assert data["is_valid"] is True
    positions = {n["id"]: n.get("position") for n in data["nodes"]}
    assert positions["node1"] == {"x": 10, "y": 20}
    assert data["connections"][0]["from"] == "node1"
    assert data["connections"][0]["to"] == "node2"

