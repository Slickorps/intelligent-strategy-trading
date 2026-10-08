"""Unit tests for the WebSocket hub and EventBus bridge."""

import asyncio

import pytest

from ist.api.websocket_manager import WebSocketHub, attach_event_bus
from ist.core.events import EventBus, EventType


class FakeWebSocket:
    """Minimal WebSocket double recording sent messages."""

    def __init__(self, fail: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict] = []
        self._fail = fail

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        if self._fail:
            raise RuntimeError("connection lost")
        self.sent.append(message)


class TestWebSocketHub:
    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self) -> None:
        hub = WebSocketHub()
        ws = FakeWebSocket()

        await hub.connect(ws)

        assert ws.accepted is True
        assert hub.connection_count == 1

        hub.disconnect(ws)
        assert hub.connection_count == 0

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_and_channels(self) -> None:
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws)

        hub.subscribe(ws, "price_update")
        hub.subscribe(ws, "bar_close")
        assert hub.channels(ws) == {"price_update", "bar_close"}

        hub.unsubscribe(ws, "price_update")
        assert hub.channels(ws) == {"bar_close"}

    @pytest.mark.asyncio
    async def test_broadcast_only_to_subscribers(self) -> None:
        hub = WebSocketHub()
        subscribed = FakeWebSocket()
        other = FakeWebSocket()
        await hub.connect(subscribed)
        await hub.connect(other)
        hub.subscribe(subscribed, "price_update")

        delivered = await hub.broadcast("price_update", {"close": 1.1})

        assert delivered == 1
        assert subscribed.sent == [{"close": 1.1}]
        assert other.sent == []

    @pytest.mark.asyncio
    async def test_broadcast_drops_failing_connection(self) -> None:
        hub = WebSocketHub()
        broken = FakeWebSocket(fail=True)
        await hub.connect(broken)
        hub.subscribe(broken, "price_update")

        delivered = await hub.broadcast("price_update", {"close": 1.1})

        assert delivered == 0
        assert hub.connection_count == 0

    def test_schedule_broadcast_without_loop_is_noop(self) -> None:
        hub = WebSocketHub()
        # Never connected => no event loop captured.
        hub.schedule_broadcast("price_update", {"close": 1.1})


class TestEventBusBridge:
    def test_emit_without_loop_is_safe(self) -> None:
        hub = WebSocketHub()
        bus = EventBus()
        attach_event_bus(hub, bus)

        # No running loop and no captured hub loop: must not raise.
        bus.emit(
            bus.create_event(EventType.PRICE_UPDATE, {"symbol": "EURUSD"}),
        )

    @pytest.mark.asyncio
    async def test_events_broadcast_to_channel_and_market(self) -> None:
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws)
        hub.subscribe(ws, "price_update")
        hub.subscribe(ws, "market:EURUSD")

        bus = EventBus()
        attach_event_bus(hub, bus)

        bus.emit(
            bus.create_event(
                EventType.PRICE_UPDATE,
                {"symbol": "EURUSD", "close": 1.1234},
                "test",
            ),
        )
        await asyncio.sleep(0.05)

        events = [m for m in ws.sent if m.get("type") == "event"]
        channels_seen = {m["event"] for m in events}
        assert "price_update" in channels_seen
        # The market:EURUSD subscription also received the event.
        assert len([m for m in ws.sent if m["payload"].get("symbol") == "EURUSD"]) >= 1
