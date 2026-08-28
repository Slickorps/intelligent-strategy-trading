"""Unit tests for the event system (Event, EventType, EventBus)."""

from datetime import datetime

import pytest

from ist.core.events import Event, EventBus, EventType


class TestEvent:
    def test_creation_with_timestamp(self) -> None:
        now = datetime.utcnow()
        event = Event(
            event_type=EventType.PRICE_UPDATE,
            timestamp=now,
            payload={"symbol": "EURUSD"},
            source="test",
        )
        assert event.event_type == EventType.PRICE_UPDATE
        assert event.timestamp == now
        assert event.payload == {"symbol": "EURUSD"}
        assert event.source == "test"

    def test_default_timestamp_and_payload(self) -> None:
        event = Event(event_type=EventType.BAR_CLOSE, timestamp=None)
        assert isinstance(event.timestamp, datetime)
        assert event.payload == {}
        assert event.source == ""

    def test_event_is_immutable(self) -> None:
        event = Event(
            event_type=EventType.PRICE_UPDATE,
            timestamp=datetime.utcnow(),
        )
        with pytest.raises(AttributeError):
            event.payload = {}  # type: ignore[misc]


class TestEventBus:
    @pytest.fixture
    def bus(self) -> EventBus:
        return EventBus()

    def test_subscribe_and_emit(self, bus) -> None:
        received: list[Event] = []
        bus.subscribe(EventType.PRICE_UPDATE, lambda e: received.append(e))

        event = bus.create_event(
            EventType.PRICE_UPDATE, {"symbol": "EURUSD"}, "src",
        )
        bus.emit(event)

        assert len(received) == 1
        assert received[0].payload["symbol"] == "EURUSD"
        assert received[0].source == "src"

    def test_emit_without_handlers_does_not_raise(self, bus) -> None:
        bus.emit(bus.create_event(EventType.PRICE_UPDATE, {}))

    def test_multiple_handlers_in_order(self, bus) -> None:
        received: list[int] = []
        bus.subscribe(EventType.SIGNAL_GENERATED, lambda e: received.append(1))
        bus.subscribe(EventType.SIGNAL_GENERATED, lambda e: received.append(2))

        bus.emit(bus.create_event(EventType.SIGNAL_GENERATED, {}))

        assert received == [1, 2]

    def test_unsubscribe_removes_handler(self, bus) -> None:
        received: list[Event] = []

        def handler(e: Event) -> None:
            received.append(e)

        bus.subscribe(EventType.BAR_CLOSE, handler)
        bus.unsubscribe(EventType.BAR_CLOSE, handler)
        bus.emit(bus.create_event(EventType.BAR_CLOSE, {}))

        assert received == []

    def test_unsubscribe_keeps_other_handlers(self, bus) -> None:
        received: list[str] = []
        bus.subscribe(EventType.ORDER_FILLED, lambda e: received.append("h1"))
        bus.subscribe(EventType.ORDER_FILLED, lambda e: received.append("h2"))

        h1 = bus._handlers[EventType.ORDER_FILLED][0]
        bus.unsubscribe(EventType.ORDER_FILLED, h1)
        bus.emit(bus.create_event(EventType.ORDER_FILLED, {}))

        assert received == ["h2"]

    def test_handler_exception_does_not_propagate(self, bus) -> None:
        def bad_handler(e: Event) -> None:
            raise RuntimeError("boom")

        received: list[Event] = []
        bus.subscribe(EventType.RISK_BREACH, bad_handler)
        bus.subscribe(EventType.RISK_BREACH, lambda e: received.append(e))

        # Should not raise; the error is logged and other handlers still run.
        bus.emit(bus.create_event(EventType.RISK_BREACH, {}))

        assert len(received) == 1

    def test_create_event_defaults(self, bus) -> None:
        event = bus.create_event(EventType.STRATEGY_STARTED, {"mode": "paper"})

        assert event.event_type == EventType.STRATEGY_STARTED
        assert event.source == ""
        assert event.payload == {"mode": "paper"}
        assert isinstance(event.timestamp, datetime)
