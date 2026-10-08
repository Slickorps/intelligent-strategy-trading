"""Integration tests for the WebSocket real-time data endpoints."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ist.api.main import create_app
from ist.core import config
from ist.core.events import EventType


def test_events_subscribe_unsubscribe_and_ping() -> None:
    app = create_app()
    with TestClient(app) as client, client.websocket_connect("/ws/events") as ws:
        assert ws.receive_json() == {
            "type": "connected",
            "endpoint": "events",
        }

        ws.send_json({"action": "subscribe", "channels": ["price_update"]})
        assert ws.receive_json() == {
            "type": "subscribed",
            "channels": ["price_update"],
        }

        ws.send_json({"action": "unsubscribe", "channels": ["price_update"]})
        assert ws.receive_json() == {
            "type": "unsubscribed",
            "channels": ["price_update"],
        }

        ws.send_json({"action": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_events_unknown_action_returns_error() -> None:
    app = create_app()
    with TestClient(app) as client, client.websocket_connect("/ws/events") as ws:
        ws.receive_json()
        ws.send_json({"action": "bogus"})
        assert ws.receive_json()["type"] == "error"


def test_market_channel_subscribes() -> None:
    app = create_app()
    with TestClient(app) as client, client.websocket_connect("/ws/market/EURUSD") as ws:
        message = ws.receive_json()
        assert message["type"] == "subscribed"
        assert message["channel"] == "market:EURUSD"
        assert message["symbol"] == "EURUSD"


def test_market_channel_receives_emitted_event() -> None:
    app = create_app()
    with TestClient(app) as client, client.websocket_connect("/ws/market/EURUSD") as ws:
        assert ws.receive_json()["type"] == "subscribed"

        bus = app.state.event_bus
        bus.emit(
            bus.create_event(
                EventType.PRICE_UPDATE,
                {"symbol": "EURUSD", "close": 1.1234},
                "test",
            ),
        )

        message = ws.receive_json()
        assert message["type"] == "event"
        assert message["event"] == "price_update"
        assert message["payload"]["close"] == 1.1234


def test_ws_rejected_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        config, "_settings", config.Settings(api_key="secret-key"),
    )
    app = create_app()
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/market/EURUSD"),
    ):
        pass


def test_ws_accepted_with_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        config, "_settings", config.Settings(api_key="secret-key"),
    )
    app = create_app()
    with TestClient(app) as client, client.websocket_connect(
        "/ws/market/EURUSD?api_key=secret-key",
    ) as ws:
        assert ws.receive_json()["type"] == "subscribed"
