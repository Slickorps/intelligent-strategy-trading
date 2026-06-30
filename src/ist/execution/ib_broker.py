"""Interactive Brokers adapter implementation.

Provides integration with Interactive Brokers TWS/IB Gateway API.
Uses ib_insync library for async IB API communication.

Usage:
    adapter = IBBrokerAdapter("127.0.0.1", 7497, client_id=1)
    await adapter.connect()
    account = await adapter.get_account_info()
    order_result = await adapter.place_order(order)
"""

import asyncio
from datetime import datetime
from typing import Any, Optional

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
    TimeInForce,
)

logger = get_logger(__name__)


class IBBrokerAdapter(BrokerAdapter):
    """Interactive Brokers TWS/IB Gateway adapter.

    Connects to either TWS (live) or IB Gateway via the IB API.
    Manages connection lifecycle, order execution, account queries.

    Args:
        host: IB host (default "127.0.0.1")
        port: IB port (TWS: 7497 live / 7496 paper; Gateway: 4002 live / 4001 paper)
        client_id: Unique client identifier (must be unique per connection)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
    ) -> None:
        super().__init__("interactive_brokers")
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib: Any = None
        self._req_id: int = 0
        self._connection_params = {
            "host": host,
            "port": port,
            "client_id": client_id,
        }

    def _next_req_id(self) -> int:
        """Generate unique request ID."""
        self._req_id += 1
        return self._req_id

    async def connect(self) -> bool:
        """Establish connection to IB TWS/Gateway.

        Uses ib_insync's async connect. On success, sets connected flag
        and retrieves account ID.

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If connection fails after retries
        """
        try:
            from ib_insync import IB

            self._ib = IB()
            await self._ib.connectAsync(
                self.host, self.port, clientId=self._client_id()
            )
            self._connected = True

            # Retrieve account info
            managed_accounts = self._ib.managedAccounts()
            if managed_accounts:
                self._account_id = managed_accounts[0]

            logger.info(
                f"Connected to IB at {self.host}:{self.port}, "
                f"account={self._account_id}"
            )
            return True

        except ImportError:
            logger.error(
                "ib_insync not installed. Run: pip install ib_insync"
            )
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"IB connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Close connection to IB TWS/Gateway."""
        if self._ib and self._connected:
            try:
                self._ib.disconnect()
                self._connected = False
                logger.info("Disconnected from IB")
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"IB disconnect error: {e}")

    async def get_account_info(self) -> AccountInfo:
        """Get IB account information.

        Fetches account summary including cash balance, equity,
        buying power, and margin details.

        Returns:
            AccountInfo with account details

        Raises:
            RuntimeError: If not connected
        """
        self._ensure_connected()

        try:
            account_summary = self._ib.accountSummary()
            cash = 0.0
            equity = 0.0
            buying_power = 0.0
            margin_used = 0.0

            for item in account_summary:
                tag = item.tag
                value = float(item.value) if item.value else 0.0
                if tag == "TotalCashBalance":
                    cash = value
                elif tag == "NetLiquidation":
                    equity = value
                elif tag == "BuyingPower":
                    buying_power = value
                elif tag == "GrossPositionValue":
                    margin_used = value

            return AccountInfo(
                account_id=self._account_id or "unknown",
                cash=cash,
                equity=equity,
                buying_power=buying_power,
                margin_used=margin_used,
                margin_available=buying_power - margin_used,
                base_currency="USD",
            )

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get account info: {e}")
            raise RuntimeError(f"IB account info error: {e}") from e

    async def get_quote(self, symbol: str) -> Optional["Quote"]:
        """Get real-time quote for a symbol from IB.

        Args:
            symbol: Trading symbol (e.g., "AAPL", "EUR.USD")

        Returns:
            Quote object or None if unavailable
        """
        self._ensure_connected()

        try:
            from ib_insync import Contract

            contract = self._resolve_contract(symbol)
            ticker = self._ib.reqMktData(contract, "", False, False)

            # Wait briefly for data
            await asyncio.sleep(0.5)

            if ticker and ticker.last:
                return self._ticker_to_quote(ticker, symbol)
            return None

        except Exception as e:
            self._last_error = str(e)
            logger.debug(f"Failed to get quote for {symbol}: {e}")
            return None

    async def place_order(self, order: Order) -> OrderResult:
        """Submit order to IB.

        Converts internal Order to IB-specific order format
        and submits via IB API. Supports Market, Limit, and Stop orders.

        Args:
            order: Order to submit

        Returns:
            OrderResult with order ID and status

        Raises:
            RuntimeError: If order submission fails
        """
        self._ensure_connected()

        try:
            from ib_insync import Contract, LimitOrder, MarketOrder, StopOrder

            contract = self._resolve_contract(order.symbol)
            ib_order = self._to_ib_order(order)
            trade = self._ib.placeOrder(contract, ib_order)

            # Map IB trade status to internal status
            status = self._map_order_status(trade.orderStatus.status)

            result = OrderResult(
                order_id=str(trade.order.orderId),
                status=status,
                submit_time=datetime.utcnow(),
            )

            logger.info(
                f"IB order placed: {order.side.name} {order.quantity} "
                f"{order.symbol} -> ID={result.order_id} status={status.name}"
            )
            return result

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
            order_id: IB order ID to cancel

        Returns:
            True if cancellation was successful
        """
        self._ensure_connected()

        try:
            trade = self._ib.cancelOrder(int(order_id))
            if trade:
                logger.info(f"Order {order_id} cancelled")
                return True
            return False

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get current status of an order.

        Args:
            order_id: IB order ID

        Returns:
            OrderResult or None if not found
        """
        self._ensure_connected()

        try:
            fills = self._ib.fills()
            for fill in fills:
                if str(fill.execution.orderId) == order_id:
                    return OrderResult(
                        order_id=order_id,
                        status=OrderStatus.FILLED,
                        filled_quantity=float(fill.execution.shares),
                        avg_fill_price=float(fill.execution.avgPrice),
                        commission=float(fill.commissionReport.commission),
                        fill_time=fill.execution.time,
                    )

            # Check open orders
            open_orders = self._ib.openOrders()
            for trade in open_orders:
                if str(trade.order.orderId) == order_id:
                    return OrderResult(
                        order_id=order_id,
                        status=self._map_order_status(
                            trade.orderStatus.status
                        ),
                        remaining_quantity=float(trade.order.remainingQuantity),
                    )

            return None

        except Exception as e:
            self._last_error = str(e)
            logger.debug(f"Failed to get order status {order_id}: {e}")
            return None

    async def get_positions(self) -> list[Position]:
        """Get all current positions.

        Returns:
            List of Position objects
        """
        self._ensure_connected()

        try:
            ib_positions = self._ib.positions()
            positions: list[Position] = []

            for pos in ib_positions:
                positions.append(
                    Position(
                        symbol=pos.contract.symbol,
                        quantity=float(pos.position),
                        avg_entry_price=float(pos.avgCost),
                        market_price=float(pos.marketPrice),
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
            List of OrderResult for all pending orders
        """
        self._ensure_connected()

        try:
            trades = self._ib.openOrders()
            results: list[OrderResult] = []

            for trade in trades:
                results.append(
                    OrderResult(
                        order_id=str(trade.order.orderId),
                        status=self._map_order_status(
                            trade.orderStatus.status
                        ),
                        remaining_quantity=float(trade.order.remainingQuantity),
                    )
                )

            return results

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to get open orders: {e}")
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Raise if not connected to IB."""
        if not self._connected or not self._ib:
            raise RuntimeError("Not connected to Interactive Brokers")

    def _client_id(self) -> int:
        """Return client ID (compatible with both int and str usage)."""
        return self.client_id

    def _resolve_contract(self, symbol: str) -> Any:
        """Resolve an IB contract for the given symbol."""
        from ib_insync import Stock

        # Detect forex pairs
        if "." in symbol:
            parts = symbol.split(".")
            # Simplified forex contract
            from ib_insync import Forex

            return Forex(parts[0])

        return Stock(symbol, "SMART", "USD")

    def _to_ib_order(self, order: Order) -> Any:
        """Convert internal Order to ib_insync order object."""
        from ib_insync import LimitOrder, MarketOrder, StopOrder

        action = "BUY" if order.side == OrderSide.BUY else "SELL"

        if order.order_type == OrderType.MARKET:
            return MarketOrder(action, order.quantity)
        elif order.order_type == OrderType.LIMIT and order.limit_price:
            return LimitOrder(action, order.quantity, order.limit_price)
        elif order.order_type == OrderType.STOP and order.stop_price:
            return StopOrder(action, order.quantity, order.stop_price)
        else:
            # Default to market
            return MarketOrder(action, order.quantity)

    def _ticker_to_quote(self, ticker: Any, symbol: str) -> "Quote":
        """Convert ib_insync ticker to internal Quote."""
        from datetime import datetime

        from ist.data.models import Quote

        last = float(ticker.last) if ticker.last else 0.0
        return Quote(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            open=last,
            high=last,
            low=last,
            close=last,
            volume=float(ticker.volume) if ticker.volume else 0.0,
        )

    @staticmethod
    def _map_order_status(ib_status: str) -> OrderStatus:
        """Map IB status string to internal OrderStatus enum."""
        mapping = {
            "PendingSubmit": OrderStatus.PENDING,
            "PreSubmitted": OrderStatus.PENDING,
            "Submitted": OrderStatus.SUBMITTED,
            "ApiPending": OrderStatus.PENDING,
            "ApiCancelled": OrderStatus.CANCELLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Filled": OrderStatus.FILLED,
            "Inactive": OrderStatus.REJECTED,
            "PendingCancel": OrderStatus.CANCELLED,
        }
        return mapping.get(ib_status, OrderStatus.SUBMITTED)


# Register with factory
BrokerFactory.register("interactive_brokers", IBBrokerAdapter)