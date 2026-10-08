"""WebSocket endpoints for real-time data streaming."""

import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ist.api.websocket_manager import WebSocketHub
from ist.core.config import get_settings
from ist.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _hub(websocket: WebSocket) -> WebSocketHub:
    """Get the application-wide WebSocket hub."""
    return websocket.app.state.websocket_hub


def _authorized(websocket: WebSocket) -> bool:
    """Check the optional API key (query param or X-API-Key header)."""
    api_key = get_settings().api_key
    if not api_key:
        return True

    provided = (
        websocket.query_params.get("api_key")
        or websocket.headers.get("x-api-key")
    )
    return bool(provided) and secrets.compare_digest(provided, api_key)


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    """Stream internal events (subscribe to channels by event type).

    Client messages:
        {"action": "subscribe", "channels": ["price_update", ...]}
        {"action": "unsubscribe", "channels": [...]}
        {"action": "ping"}
    """
    if not _authorized(websocket):
        await websocket.close(code=1008)
        return

    hub = _hub(websocket)
    await hub.connect(websocket)
    await websocket.send_json({"type": "connected", "endpoint": "events"})

    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            channels = message.get("channels") or []

            if action == "subscribe":
                for channel in channels:
                    hub.subscribe(websocket, channel)
                await websocket.send_json(
                    {"type": "subscribed", "channels": channels},
                )
            elif action == "unsubscribe":
                for channel in channels:
                    hub.unsubscribe(websocket, channel)
                await websocket.send_json(
                    {"type": "unsubscribed", "channels": channels},
                )
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json(
                    {"type": "error", "message": "unknown action"},
                )
    except WebSocketDisconnect:
        hub.disconnect(websocket)
        logger.info("WebSocket events client disconnected")


@router.websocket("/ws/market/{symbol}")
async def websocket_market(websocket: WebSocket, symbol: str) -> None:
    """Stream real-time market data for a single symbol."""
    if not _authorized(websocket):
        await websocket.close(code=1008)
        return

    hub = _hub(websocket)
    channel = f"market:{symbol}"
    await hub.connect(websocket)
    hub.subscribe(websocket, channel)
    await websocket.send_json(
        {"type": "subscribed", "channel": channel, "symbol": symbol},
    )

    try:
        while True:
            message = await websocket.receive_json()
            if message.get("action") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        hub.disconnect(websocket)
        logger.info("WebSocket market client disconnected", symbol=symbol)
