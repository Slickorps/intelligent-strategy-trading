"""OANDA broker adapter implementation.

Provides integration with OANDA's REST v20 API for forex trading.
Uses httpx for async HTTP communication.

Usage:
    adapter = OandaBrokerAdapter("your-api-token", account_id="123-456")
    await adapter.connect()
    account = await adapter.get_account_info()
    candles = await adapter.get_candles("EUR_USD", count=100)
"""

import asyncio
from datetime import datetime, timedelta
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

# OANDA REST v20 API endpoints
OANDA_API_PRACTICE = "https://api-fxpractice.oanda.com"
OANDA_API_LIVE = "https://api-fxtrade.oanda.com"


class OandaBrokerAdapter(BrokerAdapter):
    """OANDA REST v20 API adapter.

    Connects to OANDA forex trading platform via REST API.
    Supports both practice (demo) and live environments.

    Args:
        access_token: OANDA API access token (v20)
        account_id: OANDA account ID
        practice: Use practice/demo environment (default True)
    """

    def __init__(
        self,
        access_token: str = "",
        account_id: str = "",
        practice: bool = True,
    ) -> None:
        super().__init__("oanda")
        self.access_token = access_token
        self.account_id = account_id
        self.practice = practice
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url = OANDA_API_PRACTICE if practice else OANDA_API_LIVE
        self._connection_params = {
            "practice": practice,
            "account_id": account_id,
        }

    @property
    def _api_url(self) -> str:
        """Get the base API URL."""
        return f"{self._base_url}/v3"

    def _headers(self) -> dict[str, str]:
        """Get request headers with auth."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def connect(self) -> bool:
        """Establish connection to OANDA API.

        Validates API token by fetching account details.
        Creates an httpx async client for subsequent requests.

        Returns:
            True if authentication succeeded

        Raises:
            ConnectionError: If API token is invalid
        """
        if not self.access_token:
            self._last_error = "Access token is required"
            logger.error(self._last_error)
            return False

        try:
            self._client = httpx.AsyncClient(
                base_url=self._api_url,
                headers=self._headers(),
                timeout=30.0,
            )

            # Validate connection by fetching account info
            response = await self._client.get(
                f"/accounts/{self.account_id}" if self.account_id
                else "/accounts"
            )
            response.raise_for_status()
            data = response.json()

            # Extract account ID if not provided
            if not self.account_id:
                accounts = data.get("accounts", [])
                if accounts:
                    self.account_id = accounts[0]["id"]
                else:
                    self._last_error = "No accounts found"
                    logger.error(self._last_error)
                    return False

            self._connected = True
            self._account_id = self.account_id

            logger.info(
                f"Connected to OANDA {'practice' if self.practice else 'live'}, "
                f"account={self.account_id}"
            )
            return True

        except httpx.HTTPStatusError as e:
            self._last_error = f"OANDA auth failed: {e.response.status_code}"
            logger.error(self._last_error)
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"OANDA connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Close the HTTP client connection."""
        if self._client:
            try:
                await self._client.aclose()
                self._connected = False
                logger.info("Disconnected from OANDA")
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"OANDA disconnect error: {e}")

    async def get_account_info(self) -> AccountInfo:
        """Get OANDA account information.

        Fetches account summary from OANDA API.

        Returns:
            AccountInfo with cash, equity, buying power

        Raises:
            RuntimeError: If not connected or API error
        """
        self._ensure_connected()

        try:
            response = await self._client.get(
                f"/accounts/{self.account_id}"
            )
            response.raise_for_status()
            data = response.json().get("account", {})

            return AccountInfo(
                account_id=self.account_id,
                cash=float(data.get("balance", 0.0)),
                equity=float(data.get("NAV", 0.0)),
                buying_power=float(data.get("marginAvailable", 0.0)),
                margin_used=float(data.get("marginUsed", 0.0)),
                margin_available=float(data.get("marginAvailable", 0.0)),
                base_currency=data.get("currency", "USD"),
            )

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get account info: {e}")
            raise RuntimeError(f"OANDA account info error: {e}") from e

    async def get_quote(self, symbol: str) -> Optional["Quote"]:
        """Get real-time quote for a forex pair.

        Args:
            symbol: Forex pair in OANDA format (e.g., "EUR_USD")

        Returns:
            Quote object or None if unavailable
        """
        self._ensure_connected()

        try:
            oanda_symbol = self._to_oanda_symbol(symbol)
            response = await self._client.get(
                f"/accounts/{self.account_id}/pricing",
                params={"instruments": oanda_symbol},
            )
            response.raise_for_status()
            data = response.json()
            prices = data.get("prices", [])
            if not prices:
                return None

            price = prices[0]
            bid = float(price.get("bids", [{}])[0].get("price", 0.0))
            ask = float(price.get("asks", [{}])[0].get("price", 0.0))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(price.get("closeoutBid", 0.0))
            from ist.data.models import Quote

            return Quote(
                timestamp=datetime.utcnow(),
                symbol=symbol,
                open=mid,
                high=mid,
                low=mid,
                close=mid,
                volume=0.0,
            )

        except Exception as e:
            self._last_error = str(e)
            logger.debug(f"Failed to get quote for {symbol}: {e}")
            return None

    async def place_order(self, order: Order) -> OrderResult:
        """Submit order to OANDA.

        Supports Market, Limit, and Stop orders.
        Converts internal Order to OANDA v20 JSON format.

        Args:
            order: Order to submit

        Returns:
            OrderResult with order ID and status
        """
        self._ensure_connected()

        try:
            oanda_symbol = self._to_oanda_symbol(order.symbol)
            payload = self._build_order_payload(order, oanda_symbol)

            response = await self._client.post(
                f"/accounts/{self.account_id}/orders",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            order_create = data.get("orderCreateTransaction", {})
            order_id = order_create.get("id", "")

            result = OrderResult(
                order_id=order_id,
                status=OrderStatus.SUBMITTED,
                submit_time=datetime.utcnow(),
            )

            logger.info(
                f"OANDA order placed: {order.side.name} {order.quantity} "
                f"{order.symbol} -> ID={order_id}"
            )
            return result

        except httpx.HTTPStatusError as e:
            self._last_error = f"OANDA order error: {e.response.text}"
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
        """Cancel a pending order.

        Args:
            order_id: OANDA order ID to cancel

        Returns:
            True if cancellation succeeded
        """
        self._ensure_connected()

        try:
            response = await self._client.put(
                f"/accounts/{self.account_id}/orders/{order_id}/cancel"
            )
            response.raise_for_status()
            logger.info(f"OANDA order {order_id} cancelled")
            return True

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get current status of an order.

        Args:
            order_id: OANDA order ID

        Returns:
            OrderResult or None if not found
        """
        self._ensure_connected()

        try:
            response = await self._client.get(
                f"/accounts/{self.account_id}/orders/{order_id}"
            )
            response.raise_for_status()
            data = response.json().get("order", {})

            state = data.get("state", "").upper()
            status = self._map_order_state(state)

            return OrderResult(
                order_id=order_id,
                status=status,
                remaining_quantity=float(
                    data.get("units", "0").replace("-", "")
                ),
            )

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
            response = await self._client.get(
                f"/accounts/{self.account_id}/positions"
            )
            response.raise_for_status()
            data = response.json().get("positions", [])
            positions: list[Position] = []

            for pos in data:
                instrument = pos.get("instrument", "")
                long_data = pos.get("long", {})
                short_data = pos.get("short", {})

                long_units = float(long_data.get("units", "0"))
                short_units = float(short_data.get("units", "0"))
                net_units = long_units + short_units

                if net_units == 0:
                    continue

                avg_price = (
                    float(long_data.get("averagePrice", "0"))
                    if long_units != 0
                    else float(short_data.get("averagePrice", "0"))
                )

                positions.append(
                    Position(
                        symbol=self._from_oanda_symbol(instrument),
                        quantity=net_units,
                        avg_entry_price=avg_price,
                        market_price=(
                            float(short_data.get("price", "0"))
                            if net_units < 0
                            else float(long_data.get("price", "0"))
                        ),
                    )
                )

            return positions

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get positions: {e}")
            return []

    async def get_open_orders(self) -> list[OrderResult]:
        """Get all pending orders.

        Returns:
            List of OrderResult for open orders
        """
        self._ensure_connected()

        try:
            response = await self._client.get(
                f"/accounts/{self.account_id}/orders",
                params={"state": "PENDING"},
            )
            response.raise_for_status()
            data = response.json().get("orders", [])
            results: list[OrderResult] = []

            for order in data:
                state = order.get("state", "").upper()
                results.append(
                    OrderResult(
                        order_id=order.get("id", ""),
                        status=self._map_order_state(state),
                        remaining_quantity=abs(
                            float(order.get("units", "0"))
                        ),
                    )
                )

            return results

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def get_candles(
        self,
        symbol: str,
        count: int = 100,
        granularity: str = "H1",
    ) -> list[dict[str, Any]]:
        """Fetch candle/OHLC data for a forex pair.

        Args:
            symbol: Forex pair (e.g., "EUR_USD")
            count: Number of candles to fetch (max 5000)
            granularity: Candle size (S5, S10, M1, M5, M15, M30,
                        H1, H2, H3, H4, H6, H8, H12, D, W, M)

        Returns:
            List of candle dicts with keys: time, open, high, low, close, volume
        """
        self._ensure_connected()

        try:
            oanda_symbol = self._to_oanda_symbol(symbol)
            response = await self._client.get(
                f"/instruments/{oanda_symbol}/candles",
                params={
                    "count": min(count, 5000),
                    "granularity": granularity,
                    "price": "M",  # Midpoint candles
                },
            )
            response.raise_for_status()
            data = response.json().get("candles", [])

            candles: list[dict[str, Any]] = []
            for candle in data:
                mid = candle.get("mid", {})
                candles.append({
                    "time": candle.get("time", ""),
                    "open": float(mid.get("o", 0.0)),
                    "high": float(mid.get("h", 0.0)),
                    "low": float(mid.get("l", 0.0)),
                    "close": float(mid.get("c", 0.0)),
                    "volume": int(candle.get("volume", 0)),
                })

            return candles

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get candles for {symbol}: {e}")
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if not self._connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

    def _to_oanda_symbol(self, symbol: str) -> str:
        """Convert internal symbol format to OANDA format."""
        return symbol.replace("/", "_").upper()

    def _from_oanda_symbol(self, oanda_symbol: str) -> str:
        """Convert OANDA symbol format to internal format."""
        return oanda_symbol.replace("_", "/")

    def _build_order_payload(
        self, order: Order, oanda_symbol: str
    ) -> dict[str, Any]:
        """Build OANDA v20 JSON payload for order placement.

        Args:
            order: Internal order object
            oanda_symbol: OANDA-formatted symbol

        Returns:
            Dict ready for JSON serialization
        """
        units = int(order.quantity)
        if order.side == OrderSide.SELL:
            units = -units

        if order.order_type == OrderType.MARKET:
            return {
                "order": {
                    "type": "MARKET",
                    "instrument": oanda_symbol,
                    "units": str(units),
                    "timeInForce": "FOK",
                }
            }

        elif order.order_type == OrderType.LIMIT and order.limit_price:
            return {
                "order": {
                    "type": "LIMIT",
                    "instrument": oanda_symbol,
                    "units": str(units),
                    "price": str(order.limit_price),
                    "timeInForce": "GTC",
                }
            }

        elif order.order_type == OrderType.STOP and order.stop_price:
            return {
                "order": {
                    "type": "STOP",
                    "instrument": oanda_symbol,
                    "units": str(units),
                    "price": str(order.stop_price),
                    "timeInForce": "GTC",
                }
            }

        # Default market order
        return {
            "order": {
                "type": "MARKET",
                "instrument": oanda_symbol,
                "units": str(units),
                "timeInForce": "FOK",
            }
        }

    @staticmethod
    def _map_order_state(state: str) -> OrderStatus:
        """Map OANDA order state to internal OrderStatus."""
        mapping = {
            "PENDING": OrderStatus.PENDING,
            "FILLED": OrderStatus.FILLED,
            "TRIGGERED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
            "MARKET": OrderStatus.SUBMITTED,
            "LIMIT": OrderStatus.PENDING,
            "STOP": OrderStatus.PENDING,
        }
        return mapping.get(state, OrderStatus.SUBMITTED)


# Register with factory
BrokerFactory.register("oanda", OandaBrokerAdapter)