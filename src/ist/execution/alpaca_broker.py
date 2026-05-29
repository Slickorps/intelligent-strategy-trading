"""Alpaca broker adapter implementation.

Provides integration with Alpaca Trading API for stocks and crypto.
Supports both REST and WebSocket channels for real-time data.

Usage:
    adapter = AlpacaBrokerAdapter("api-key", "secret-key", paper=True)
    await adapter.connect()
    account = await adapter.get_account_info()
    order_result = await adapter.place_order(order)
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Optional

import httpx

from ist.core.logging import get_logger
from ist.execution.adapter import (
    AccountInfo,
    BrokerAdapter,
    BrokerFactory,
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

logger = get_logger(__name__)

ALPACA_LIVE = "https://api.alpaca.markets"
ALPACA_PAPER = "https://paper-api.alpaca.markets"
ALPACA_DATA_LIVE = "https://data.alpaca.markets"
ALPACA_DATA_PAPER = "https://data.sandbox.alpaca.markets"


class AlpacaBrokerAdapter(BrokerAdapter):
    """Alpaca Trading API adapter.

    Supports both REST order management and WebSocket streaming.
    Handles account authentication via API key and secret.

    Args:
        api_key: Alpaca API key ID
        secret_key: Alpaca secret key
        paper: Use paper trading (default True)
    """

    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        paper: bool = True,
    ) -> None:
        super().__init__("alpaca")
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self._client: Optional[httpx.AsyncClient] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._base_url = ALPACA_PAPER if paper else ALPACA_LIVE
        self._data_url = ALPACA_DATA_PAPER if paper else ALPACA_DATA_LIVE
        self._connection_params = {
            "paper": paper,
        }

    def _headers(self) -> dict[str, str]:
        """Get request headers with auth."""
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
        }

    async def connect(self) -> bool:
        """Establish connection to Alpaca API.

        Validates credentials by fetching account info.
        Sets up httpx async client for REST operations.

        Returns:
            True if authentication succeeded
        """
        if not self.api_key or not self.secret_key:
            self._last_error = "API key and secret key are required"
            logger.error(self._last_error)
            return False

        try:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers(),
                timeout=30.0,
            )

            # Validate by fetching account
            response = await self._client.get("/v2/account")
            response.raise_for_status()
            account_data = response.json()

            self._connected = True
            self._account_id = account_data.get("id", "")

            logger.info(
                f"Connected to Alpaca {'paper' if self.paper else 'live'}, "
                f"account={self._account_id}"
            )
            return True

        except httpx.HTTPStatusError as e:
            self._last_error = (
                f"Alpaca auth failed: {e.response.status_code} - "
                f"{e.response.text}"
            )
            logger.error(self._last_error)
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Alpaca connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Close REST client and WebSocket connection."""
        # Cancel WebSocket task first
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        # Close HTTP client
        if self._client:
            try:
                await self._client.aclose()
                self._connected = False
                logger.info("Disconnected from Alpaca")
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"Alpaca disconnect error: {e}")

    async def get_account_info(self) -> AccountInfo:
        """Get Alpaca account information.

        Fetches account details from Alpaca REST API.

        Returns:
            AccountInfo with cash, equity, buying power

        Raises:
            RuntimeError: If not connected
        """
        self._ensure_connected()

        try:
            response = await self._client.get("/v2/account")
            response.raise_for_status()
            data = response.json()

            return AccountInfo(
                account_id=self._account_id or "",
                cash=float(data.get("cash", 0.0)),
                equity=float(data.get("equity", 0.0)),
                buying_power=float(data.get("buying_power", 0.0)),
                margin_used=float(data.get("long_market_value", 0.0)),
                margin_available=float(data.get("buying_power", 0.0)),
                base_currency=data.get("currency", "USD"),
            )

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get account info: {e}")
            raise RuntimeError(f"Alpaca account info error: {e}") from e

    async def get_quote(self, symbol: str) -> Optional["Quote"]:
        """Get real-time quote for a symbol.

        Uses Alpaca Data API (v2) for latest trade/quote data.

        Args:
            symbol: Trading symbol (e.g., "AAPL", "BTC/USD")

        Returns:
            Quote object or None if unavailable
        """
        self._ensure_connected()

        try:
            alpaca_symbol = self._normalize_symbol(symbol)
            # Fetch latest trade
            response = await self._client.get(
                f"{self._data_url}/v2/stocks/{alpaca_symbol}/trades/latest"
            )
            response.raise_for_status()
            data = response.json().get("trade", {})

            from ist.data.models import Quote

            return Quote(
                symbol=symbol,
                bid=float(data.get("p", 0.0)),
                ask=float(data.get("p", 0.0)),
                last=float(data.get("p", 0.0)),
                volume=int(data.get("s", 0)),
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            self._last_error = str(e)
            logger.debug(f"Failed to get quote for {symbol}: {e}")
            return None

    async def place_order(self, order: Order) -> OrderResult:
        """Submit order to Alpaca.

        Converts internal Order to Alpaca REST JSON format.
        Supports market, limit, and stop orders.

        Args:
            order: Order to submit

        Returns:
            OrderResult with order ID and status
        """
        self._ensure_connected()

        try:
            alpaca_symbol = self._normalize_symbol(order.symbol)
            payload = self._build_order_payload(order, alpaca_symbol)

            response = await self._client.post(
                "/v2/orders",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            status = self._map_order_status(data.get("status", ""))

            result = OrderResult(
                order_id=data.get("id", ""),
                status=status,
                filled_quantity=float(data.get("filled_qty", 0)),
                remaining_quantity=float(data.get("qty", 0)),
                submit_time=datetime.utcnow(),
            )

            logger.info(
                f"Alpaca order placed: {order.side.name} {order.quantity} "
                f"{order.symbol} -> ID={result.order_id} status={status.name}"
            )
            return result

        except httpx.HTTPStatusError as e:
            self._last_error = f"Alpaca order error: {e.response.text}"
            logger.error(self._last_error)
            return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                error_message=self._last_error,
                submit_time=datetime.utcnow(),
            )
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Order placement failed: {e}")
            return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                error_message=str(e),
                submit_time=datetime.utcnow(),
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: Alpaca order ID

        Returns:
            True if cancellation succeeded
        """
        self._ensure_connected()

        try:
            response = await self._client.delete(
                f"/v2/orders/{order_id}"
            )
            response.raise_for_status()
            logger.info(f"Alpaca order {order_id} cancelled")
            return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Order {order_id} not found")
                return False
            self._last_error = str(e)
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get current status of an order.

        Args:
            order_id: Alpaca order ID

        Returns:
            OrderResult or None if not found
        """
        self._ensure_connected()

        try:
            response = await self._client.get(
                f"/v2/orders/{order_id}"
            )
            response.raise_for_status()
            data = response.json()

            return self._order_data_to_result(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.debug(f"Failed to get order status {order_id}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Failed to get order status {order_id}: {e}")
            return None

    async def get_positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of Position objects
        """
        self._ensure_connected()

        try:
            response = await self._client.get("/v2/positions")
            response.raise_for_status()
            data = response.json()
            positions: list[Position] = []

            for pos in data:
                positions.append(
                    Position(
                        symbol=pos.get("symbol", ""),
                        quantity=float(pos.get("qty", 0)),
                        avg_entry_price=float(pos.get("avg_entry_price", 0)),
                        market_price=float(pos.get("current_price", 0)),
                    )
                )

            return positions

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get positions: {e}")
            return []

    async def get_open_orders(self) -> list[OrderResult]:
        """Get all open orders.

        Returns:
            List of OrderResult for pending orders
        """
        self._ensure_connected()

        try:
            response = await self._client.get(
                "/v2/orders",
                params={"status": "open"},
            )
            response.raise_for_status()
            data = response.json()

            return [
                self._order_data_to_result(order) for order in data
            ]

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def subscribe_trades(
        self,
        symbols: list[str],
        callback: Optional[callable] = None,
    ) -> None:
        """Subscribe to real-time trade updates via WebSocket.

        Starts an async background task that connects to Alpaca
        streaming API and processes trade updates.

        Args:
            symbols: List of symbols to subscribe to
            callback: Async callback for trade data (optional)

        Raises:
            RuntimeError: If not connected
        """
        self._ensure_connected()

        if self._ws_task and not self._ws_task.done():
            logger.warning("WebSocket already connected, cancelling old one")
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        self._ws_task = asyncio.create_task(
            self._ws_stream(symbols, callback)
        )
        logger.info(
            f"Started WebSocket stream for {len(symbols)} symbols"
        )

    async def _ws_stream(
        self,
        symbols: list[str],
        callback: Optional[callable] = None,
    ) -> None:
        """Internal WebSocket streaming loop.

        Connects to Alpaca's real-time trade stream and processes
        incoming trade data. Reconnects automatically on failure.

        Args:
            symbols: List of symbols to stream
            callback: Optional async callback(len(data)) -> None
        """
        import websockets

        ws_url = (
            "wss://stream.data.alpaca.markets/v2/iex"
            if not self.paper
            else "wss://stream.data.sandbox.alpaca.markets/v2/iex"
        )

        while self._connected:
            try:
                async with websockets.connect(ws_url) as ws:
                    # Authenticate
                    auth_msg = {
                        "action": "auth",
                        "key": self.api_key,
                        "secret": self.secret_key,
                    }
                    await ws.send(json.dumps(auth_msg))
                    response = await ws.recv()
                    logger.debug(f"WS auth response: {response}")

                    # Subscribe to trades
                    subscribe_msg = {
                        "action": "subscribe",
                        "trades": [self._normalize_symbol(s)
                                   for s in symbols],
                        "quotes": [],
                        "bars": [],
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info(
                        f"WS subscribed to trades: {symbols}"
                    )

                    # Main loop
                    async for message in ws:
                        data = json.loads(message)
                        if callback and asyncio.iscoroutinefunction(
                            callback
                        ):
                            await callback(data)

            except websockets.ConnectionClosed:
                logger.warning(
                    "WS connection closed, reconnecting in 5s..."
                )
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                logger.info("WS stream cancelled")
                break
            except Exception as e:
                logger.error(f"WS stream error: {e}")
                await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if not self._connected or not self._client:
            raise RuntimeError("Not connected to Alpaca")

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to Alpaca format."""
        # Handle crypto pairs like BTC/USD -> BTCUSD
        symbol = symbol.replace("/", "")
        return symbol.upper()

    def _build_order_payload(
        self, order: Order, alpaca_symbol: str
    ) -> dict[str, Any]:
        """Build Alpaca REST JSON payload for order placement.

        Args:
            order: Internal order object
            alpaca_symbol: Alpaca-formatted symbol

        Returns:
            Dict ready for JSON serialization
        """
        side = "buy" if order.side == OrderSide.BUY else "sell"

        # Map order type
        if order.order_type == OrderType.MARKET:
            return {
                "symbol": alpaca_symbol,
                "qty": str(int(order.quantity)),
                "side": side,
                "type": "market",
                "time_in_force": "gtc",
            }

        elif order.order_type == OrderType.LIMIT and order.limit_price:
            return {
                "symbol": alpaca_symbol,
                "qty": str(int(order.quantity)),
                "side": side,
                "type": "limit",
                "limit_price": str(order.limit_price),
                "time_in_force": "gtc",
            }

        elif order.order_type == OrderType.STOP and order.stop_price:
            return {
                "symbol": alpaca_symbol,
                "qty": str(int(order.quantity)),
                "side": side,
                "type": "stop",
                "stop_price": str(order.stop_price),
                "time_in_force": "gtc",
            }

        # Default market order
        return {
            "symbol": alpaca_symbol,
            "qty": str(int(order.quantity)),
            "side": side,
            "type": "market",
            "time_in_force": "gtc",
        }

    def _order_data_to_result(self, data: dict) -> OrderResult:
        """Convert Alpaca order JSON to OrderResult."""
        return OrderResult(
            order_id=data.get("id", ""),
            status=self._map_order_status(data.get("status", "")),
            filled_quantity=float(data.get("filled_qty", 0)),
            remaining_quantity=(
                float(data.get("qty", 0))
                - float(data.get("filled_qty", 0))
            ),
            avg_fill_price=float(data.get("filled_avg_price", 0)),
            submit_time=datetime.utcnow(),
        )

    @staticmethod
    def _map_order_status(alpaca_status: str) -> OrderStatus:
        """Map Alpaca order status to internal OrderStatus."""
        mapping = {
            "new": OrderStatus.PENDING,
            "accepted": OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIAL_FILL,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.EXPIRED,
            "replaced": OrderStatus.CANCELLED,
            "pending_cancel": OrderStatus.PENDING,
            "pending_replace": OrderStatus.PENDING,
            "rejected": OrderStatus.REJECTED,
            "suspended": OrderStatus.PENDING,
        }
        return mapping.get(alpaca_status, OrderStatus.SUBMITTED)


# Register with factory
BrokerFactory.register("alpaca", AlpacaBrokerAdapter)