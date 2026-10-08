"""WebSocket connection and channel management.

Provides :class:`WebSocketHub`, which tracks connected clients and routes
channel broadcasts to them, plus :func:`attach_event_bus`, which bridges the
in-process :class:`~ist.core.events.EventBus` to WebSocket subscribers.
"""

import asyncio
from typing import Any

from fastapi import WebSocket

from ist.core.events import Event, EventBus, EventType
from ist.core.logging import get_logger

logger = get_logger(__name__)


class WebSocketHub:
    """Tracks WebSocket connections and dispatches channel broadcasts.

    Each connection may subscribe to any number of named channels.
    Broadcasts are delivered only to connections subscribed to the channel.
    """

    def __init__(self) -> None:
        self._channels: dict[WebSocket, set[str]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self._channels)

    def channels(self, websocket: WebSocket) -> set[str]:
        """Channels a connection is subscribed to."""
        return set(self._channels.get(websocket, set()))

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new connection."""
        self._loop = asyncio.get_running_loop()
        await websocket.accept()
        self._channels[websocket] = set()

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection."""
        self._channels.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, channel: str) -> None:
        """Subscribe a connection to a channel."""
        if websocket in self._channels:
            self._channels[websocket].add(channel)

    def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        """Unsubscribe a connection from a channel."""
        if websocket in self._channels:
            self._channels[websocket].discard(channel)

    def subscribers(self, channel: str) -> list[WebSocket]:
        """List connections subscribed to a channel."""
        return [
            ws for ws, channels in self._channels.items() if channel in channels
        ]

    async def broadcast(self, channel: str, message: dict[str, Any]) -> int:
        """Send ``message`` to every connection subscribed to ``channel``.

        Returns the number of successful deliveries. Connections that fail
        to receive are dropped.
        """
        delivered = 0
        for websocket in self.subscribers(channel):
            try:
                await websocket.send_json(message)
                delivered += 1
            except Exception as exc:
                logger.debug(
                    "WebSocket send failed, dropping connection", error=str(exc),
                )
                self.disconnect(websocket)
        return delivered

    def schedule_broadcast(self, channel: str, message: dict[str, Any]) -> None:
        """Thread-safe broadcast from synchronous (possibly foreign) callers."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is loop:
            loop.create_task(self.broadcast(channel, message))
        else:
            asyncio.run_coroutine_threadsafe(
                self.broadcast(channel, message), loop,
            )


def attach_event_bus(hub: WebSocketHub, event_bus: EventBus) -> None:
    """Bridge ``event_bus`` events to WebSocket channel subscribers.

    Each event is published to a channel named after the event type (lower
    case). Events carrying a ``symbol`` are additionally published to the
    ``market:<symbol>`` channel.
    """

    def _handler(event: Event) -> None:
        payload = {
            "type": "event",
            "event": event.event_type.name.lower(),
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload,
            "source": event.source,
        }
        hub.schedule_broadcast(event.event_type.name.lower(), payload)

        symbol = (event.payload or {}).get("symbol")
        if symbol:
            hub.schedule_broadcast(f"market:{symbol}", payload)

    for event_type in EventType:
        event_bus.subscribe(event_type, _handler)
