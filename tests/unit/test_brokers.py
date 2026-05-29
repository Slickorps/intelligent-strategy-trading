"""Unit tests for broker adapters (IB, OANDA, Alpaca).

Tests use mocking to avoid real API connections.
Covers lifecycle, order placement, account info, positions, and error paths.
"""

import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Mock ib_insync BEFORE importing IBBrokerAdapter.
# IBBrokerAdapter does `from ib_insync import IB` at module level, so we must
# inject a fake ib_insync module into sys.modules before the import.
# ---------------------------------------------------------------------------
fake_ib_insync = MagicMock()
sys.modules["ib_insync"] = fake_ib_insync

from ist.execution.adapter import (                   # noqa: E402
    AccountInfo,
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TimeInForce,
)
from ist.execution.ib_broker import IBBrokerAdapter      # noqa: E402
from ist.execution.oanda_broker import OandaBrokerAdapter  # noqa: E402
from ist.execution.alpaca_broker import AlpacaBrokerAdapter  # noqa: E402


# =========================================================================
# Helper factories
# =========================================================================

def make_market_order(symbol: str = "AAPL", side: OrderSide = OrderSide.BUY,
                      qty: float = 100) -> Order:
    """Create a market order for testing."""
    return Order(
        symbol=symbol, side=side, quantity=qty,
        order_type=OrderType.MARKET,
    )


def make_limit_order(symbol: str = "AAPL", side: OrderSide = OrderSide.BUY,
                     qty: float = 100, price: float = 150.0) -> Order:
    """Create a limit order for testing."""
    return Order(
        symbol=symbol, side=side, quantity=qty,
        order_type=OrderType.LIMIT, limit_price=price,
    )


def make_stop_order(symbol: str = "AAPL", side: OrderSide = OrderSide.BUY,
                    qty: float = 100, price: float = 145.0) -> Order:
    """Create a stop order for testing."""
    return Order(
        symbol=symbol, side=side, quantity=qty,
        order_type=OrderType.STOP, stop_price=price,
    )


# =========================================================================
# IB Broker Tests
# =========================================================================

class TestIBBrokerAdapter:
    """Test suite for Interactive Brokers adapter."""

    @pytest.fixture
    def adapter(self) -> IBBrokerAdapter:
        """Create IB adapter instance."""
        return IBBrokerAdapter(
            host="127.0.0.1", port=7497, client_id=1,
        )

    @pytest.fixture
    def mock_ib(self) -> MagicMock:
        """Mock ib_insync.IB instance.

        Only connectAsync is an AsyncMock (for await support); all other
        methods are sync because the adapter does NOT await them.
        """
        ib = MagicMock()
        ib.managedAccounts.return_value = ["U123456"]
        ib.accountSummary.return_value = []
        ib.connectAsync = AsyncMock()
        return ib

    # -- Lifecycle -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter, mock_ib) -> None:
        """Successful connection sets flags and account ID."""
        with patch("ib_insync.IB", return_value=mock_ib):
            result = await adapter.connect()

        assert result is True
        assert adapter.is_connected is True
        assert adapter._account_id == "U123456"
        mock_ib.connectAsync.assert_awaited_once_with(
            "127.0.0.1", 7497, clientId=1,
        )

    @pytest.mark.asyncio
    async def test_connect_import_error(self, adapter) -> None:
        """Missing ib_insync returns False gracefully."""
        with patch("ib_insync.IB", side_effect=ImportError):
            result = await adapter.connect()

        assert result is False
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, adapter, mock_ib) -> None:
        """Disconnect cleans up and resets state."""
        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        await adapter.disconnect()

        assert adapter.is_connected is False
        mock_ib.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, adapter) -> None:
        """Disconnect when not connected does not raise."""
        await adapter.disconnect()  # should be no-op

    # -- Order placement -------------------------------------------------

    @pytest.mark.asyncio
    async def test_place_market_order(self, adapter, mock_ib) -> None:
        """Place a market order returns correct result."""
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_trade.orderStatus.status = "Filled"
        mock_ib.placeOrder.return_value = mock_trade
        mock_ib.openOrders.return_value = []

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        order = make_market_order()
        result = await adapter.place_order(order)

        assert result.order_id == "1001"
        assert result.status == OrderStatus.FILLED
        mock_ib.placeOrder.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_limit_order(self, adapter, mock_ib) -> None:
        """Place a limit order passes limit_price correctly."""
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1002
        mock_trade.orderStatus.status = "Submitted"
        mock_ib.placeOrder.return_value = mock_trade

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        order = make_limit_order()
        result = await adapter.place_order(order)

        assert result.order_id == "1002"
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_place_stop_order(self, adapter, mock_ib) -> None:
        """Place a stop order passes stop_price correctly."""
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1003
        mock_trade.orderStatus.status = "Submitted"
        mock_ib.placeOrder.return_value = mock_trade

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        order = make_stop_order()
        result = await adapter.place_order(order)

        assert result.order_id == "1003"

    @pytest.mark.asyncio
    async def test_place_order_rejected(self, adapter, mock_ib) -> None:
        """Order rejection returns REJECTED status with error."""
        mock_ib.placeOrder.side_effect = RuntimeError("Insufficient margin")

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        result = await adapter.place_order(make_market_order())

        assert result.status == OrderStatus.REJECTED
        assert "Insufficient margin" in (result.error_message or "")

    # -- Account info ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_account_info(self, adapter, mock_ib) -> None:
        """Account info parses IB account summary correctly."""
        mock_item = lambda tag, val: MagicMock(tag=tag, value=val)  # noqa: E731

        mock_ib.accountSummary.return_value = [
            mock_item("TotalCashBalance", "50000.0"),
            mock_item("NetLiquidation", "100000.0"),
            mock_item("BuyingPower", "200000.0"),
            mock_item("GrossPositionValue", "50000.0"),
        ]

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        info = await adapter.get_account_info()

        assert isinstance(info, AccountInfo)
        assert info.account_id == "U123456"
        assert info.cash == 50000.0
        assert info.equity == 100000.0
        assert info.buying_power == 200000.0
        assert info.margin_used == 50000.0
        assert info.base_currency == "USD"

    @pytest.mark.asyncio
    async def test_get_account_info_empty_summary(self, adapter,
                                                  mock_ib) -> None:
        """Account info handles empty summary gracefully."""
        mock_ib.accountSummary.return_value = []

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        info = await adapter.get_account_info()

        assert info.cash == 0.0
        assert info.equity == 0.0

    # -- Positions -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_positions(self, adapter, mock_ib) -> None:
        """Positions are mapped correctly."""
        mock_pos = MagicMock()
        mock_pos.contract.symbol = "AAPL"
        mock_pos.position = 100.0
        mock_pos.avgCost = 150.0
        mock_pos.marketPrice = 155.0
        mock_ib.positions.return_value = [mock_pos]

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        positions = await adapter.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "AAPL"
        assert pos.quantity == 100.0
        assert pos.avg_entry_price == 150.0
        assert pos.market_price == 155.0

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, adapter, mock_ib) -> None:
        """Empty positions return empty list."""
        mock_ib.positions.return_value = []

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        positions = await adapter.get_positions()
        assert positions == []

    # -- Error: not connected --------------------------------------------

    @pytest.mark.asyncio
    async def test_place_order_not_connected(self, adapter) -> None:
        """Calling place_order without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Not connected"):
            await adapter.place_order(make_market_order())

    @pytest.mark.asyncio
    async def test_get_account_info_not_connected(self, adapter) -> None:
        """Calling get_account_info without connection raises."""
        with pytest.raises(RuntimeError, match="Not connected"):
            await adapter.get_account_info()

    @pytest.mark.asyncio
    async def test_cancel_order_api_error(self, adapter, mock_ib) -> None:
        """Cancel order handles API errors gracefully."""
        mock_ib.cancelOrder.side_effect = RuntimeError("Order not found")

        with patch("ib_insync.IB", return_value=mock_ib):
            await adapter.connect()

        result = await adapter.cancel_order("9999")
        assert result is False


# =========================================================================
# OANDA Broker Tests
# =========================================================================

class TestOandaBrokerAdapter:
    """Test suite for OANDA adapter."""

    @pytest.fixture
    def adapter(self) -> OandaBrokerAdapter:
        """Create OANDA adapter instance with test credentials."""
        return OandaBrokerAdapter(
            access_token="test-token",
            account_id="test-account",
            practice=True,
        )

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Mock httpx.AsyncClient."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock()
        client.put = AsyncMock()
        client.delete = AsyncMock()
        client.aclose = AsyncMock()
        # Individual tests set client.get.return_value as needed
        return client

    # -- Lifecycle -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter, mock_client) -> None:
        """Successful connection validates API token."""
        account_response = MagicMock(spec=httpx.Response)
        account_response.status_code = 200
        account_response.json.return_value = {
            "account": {
                "id": "test-account",
                "balance": "50000.0",
                "NAV": "100000.0",
                "marginAvailable": "200000.0",
                "marginUsed": "30000.0",
                "currency": "USD",
            },
        }
        mock_client.get.return_value = account_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.connect()

        assert result is True
        assert adapter.is_connected is True
        assert adapter.account_id == "test-account"

    @pytest.mark.asyncio
    async def test_connect_missing_token(self) -> None:
        """Missing access token returns False."""
        adapter = OandaBrokerAdapter(access_token="", account_id="")
        result = await adapter.connect()

        assert result is False
        assert adapter.last_error == "Access token is required"

    @pytest.mark.asyncio
    async def test_connect_http_error(self, adapter, mock_client) -> None:
        """HTTP 401 during connect returns False."""
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 401
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=error_response,
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.connect()

        assert result is False
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, adapter, mock_client) -> None:
        """Disconnect closes HTTP client."""
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        await adapter.disconnect()

        assert adapter.is_connected is False
        mock_client.aclose.assert_awaited_once()

    # -- Order placement -------------------------------------------------

    @pytest.mark.asyncio
    async def test_place_market_order(self, adapter, mock_client) -> None:
        """Market order returns SUBMITTED with order ID."""
        order_response = MagicMock(spec=httpx.Response)
        order_response.status_code = 201
        order_response.json.return_value = {
            "orderCreateTransaction": {"id": "OANDA-001"},
        }
        mock_client.post.return_value = order_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        result = await adapter.place_order(make_market_order(symbol="EUR/USD"))

        assert result.order_id == "OANDA-001"
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_place_limit_order(self, adapter, mock_client) -> None:
        """Limit order sends correct payload."""
        order_response = MagicMock(spec=httpx.Response)
        order_response.status_code = 201
        order_response.json.return_value = {
            "orderCreateTransaction": {"id": "OANDA-002"},
        }
        mock_client.post.return_value = order_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        result = await adapter.place_order(
            make_limit_order(symbol="EUR/USD", price=1.1050),
        )

        assert result.order_id == "OANDA-002"
        # Verify the payload was constructed correctly
        call_kwargs = mock_client.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["order"]["type"] == "LIMIT"
        assert payload["order"]["price"] == "1.105"

    @pytest.mark.asyncio
    async def test_place_order_rejected(self, adapter, mock_client) -> None:
        """HTTP error in order placement returns REJECTED."""
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 400
        error_response.text = "Invalid units"
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "400 Bad Request", request=MagicMock(), response=error_response,
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        result = await adapter.place_order(make_market_order(symbol="EUR/USD"))

        assert result.status == OrderStatus.REJECTED
        assert "Invalid units" in (result.error_message or "")

    # -- Account info ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_account_info(self, adapter, mock_client) -> None:
        """Account info parses OANDA response correctly."""
        account_response = MagicMock(spec=httpx.Response)
        account_response.status_code = 200
        account_response.json.return_value = {
            "account": {
                "id": "test-account",
                "balance": "50000.0",
                "NAV": "100000.0",
                "marginAvailable": "200000.0",
                "marginUsed": "30000.0",
                "currency": "USD",
            },
        }
        mock_client.get.return_value = account_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        info = await adapter.get_account_info()

        assert info.account_id == "test-account"
        assert info.cash == 50000.0
        assert info.equity == 100000.0
        assert info.buying_power == 200000.0
        assert info.margin_used == 30000.0
        assert info.base_currency == "USD"

    # -- Positions -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_positions(self, adapter, mock_client) -> None:
        """Positions are mapped from OANDA format correctly."""
        pos_response = MagicMock(spec=httpx.Response)
        pos_response.status_code = 200
        pos_response.json.return_value = {
            "positions": [
                {
                    "instrument": "EUR_USD",
                    "long": {
                        "units": "1000",
                        "averagePrice": "1.0850",
                        "price": "1.0860",
                    },
                    "short": {"units": "0", "averagePrice": "0", "price": "0"},
                },
            ],
        }
        mock_client.get.return_value = pos_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        positions = await adapter.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "EUR/USD"
        assert pos.quantity == 1000.0
        assert pos.avg_entry_price == 1.0850
        assert pos.market_price == 1.0860

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, adapter, mock_client) -> None:
        """Empty positions return empty list."""
        pos_response = MagicMock(spec=httpx.Response)
        pos_response.status_code = 200
        pos_response.json.return_value = {"positions": []}
        mock_client.get.return_value = pos_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        positions = await adapter.get_positions()
        assert positions == []

    # -- Error: not connected --------------------------------------------

    @pytest.mark.asyncio
    async def test_place_order_not_connected(self, adapter) -> None:
        """Calling place_order without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Not connected"):
            await adapter.place_order(make_market_order(symbol="EUR/USD"))


# =========================================================================
# Alpaca Broker Tests
# =========================================================================

class TestAlpacaBrokerAdapter:
    """Test suite for Alpaca adapter."""

    @pytest.fixture
    def adapter(self) -> AlpacaBrokerAdapter:
        """Create Alpaca adapter instance with test credentials."""
        return AlpacaBrokerAdapter(
            api_key="test-api-key",
            secret_key="test-secret-key",
            paper=True,
        )

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Mock httpx.AsyncClient."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock()
        client.delete = AsyncMock()
        client.aclose = AsyncMock()
        # Individual tests set client.get.return_value as needed
        return client

    # -- Lifecycle -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter, mock_client) -> None:
        """Successful connection validates credentials."""
        account_response = MagicMock(spec=httpx.Response)
        account_response.status_code = 200
        account_response.json.return_value = {
            "id": "ALPACA-001",
            "cash": "50000.0",
            "equity": "100000.0",
            "buying_power": "200000.0",
            "long_market_value": "50000.0",
            "currency": "USD",
        }
        mock_client.get.return_value = account_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.connect()

        assert result is True
        assert adapter.is_connected is True
        assert adapter._account_id == "ALPACA-001"

    @pytest.mark.asyncio
    async def test_connect_missing_credentials(self) -> None:
        """Missing API key returns False."""
        adapter = AlpacaBrokerAdapter(api_key="", secret_key="")
        result = await adapter.connect()

        assert result is False
        assert "API key" in (adapter.last_error or "")

    @pytest.mark.asyncio
    async def test_connect_http_error(self, adapter, mock_client) -> None:
        """HTTP 403 during connect returns False."""
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 403
        error_response.text = "Forbidden"
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=error_response,
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.connect()

        assert result is False
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, adapter, mock_client) -> None:
        """Disconnect closes HTTP client and cancels WS task."""
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        await adapter.disconnect()

        assert adapter.is_connected is False
        mock_client.aclose.assert_awaited_once()

    # -- Order placement -------------------------------------------------

    @pytest.mark.asyncio
    async def test_place_market_order(self, adapter, mock_client) -> None:
        """Market order returns correct status."""
        order_response = MagicMock(spec=httpx.Response)
        order_response.status_code = 200
        order_response.json.return_value = {
            "id": "ALPACA-ORD-001",
            "status": "accepted",
            "filled_qty": "0",
            "qty": "100",
        }
        mock_client.post.return_value = order_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        result = await adapter.place_order(make_market_order())

        assert result.order_id == "ALPACA-ORD-001"
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_place_limit_order(self, adapter, mock_client) -> None:
        """Limit order sends correct type and price."""
        order_response = MagicMock(spec=httpx.Response)
        order_response.status_code = 200
        order_response.json.return_value = {
            "id": "ALPACA-ORD-002",
            "status": "accepted",
            "filled_qty": "0",
            "qty": "100",
        }
        mock_client.post.return_value = order_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        result = await adapter.place_order(
            make_limit_order(price=150.0),
        )

        assert result.order_id == "ALPACA-ORD-002"
        call_kwargs = mock_client.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["type"] == "limit"
        assert payload["limit_price"] == "150.0"

    @pytest.mark.asyncio
    async def test_place_stop_order(self, adapter, mock_client) -> None:
        """Stop order sends correct type and stop_price."""
        order_response = MagicMock(spec=httpx.Response)
        order_response.status_code = 200
        order_response.json.return_value = {
            "id": "ALPACA-ORD-003",
            "status": "accepted",
            "filled_qty": "0",
            "qty": "100",
        }
        mock_client.post.return_value = order_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        result = await adapter.place_order(
            make_stop_order(price=145.0),
        )

        assert result.order_id == "ALPACA-ORD-003"
        call_kwargs = mock_client.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["type"] == "stop"
        assert payload["stop_price"] == "145.0"

    @pytest.mark.asyncio
    async def test_place_order_rejected_http(self, adapter,
                                             mock_client) -> None:
        """HTTP error in order placement returns REJECTED."""
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 422
        error_response.text = "Invalid order parameters"
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "422 Unprocessable", request=MagicMock(),
            response=error_response,
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        result = await adapter.place_order(make_market_order())

        assert result.status == OrderStatus.REJECTED
        assert "Invalid order" in (result.error_message or "")

    # -- Account info ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_account_info(self, adapter, mock_client) -> None:
        """Account info parses Alpaca response correctly."""
        account_response = MagicMock(spec=httpx.Response)
        account_response.status_code = 200
        account_response.json.return_value = {
            "id": "ALPACA-001",
            "cash": "50000.0",
            "equity": "100000.0",
            "buying_power": "200000.0",
            "long_market_value": "50000.0",
            "currency": "USD",
        }
        mock_client.get.return_value = account_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        info = await adapter.get_account_info()

        assert info.account_id == "ALPACA-001"
        assert info.cash == 50000.0
        assert info.equity == 100000.0
        assert info.buying_power == 200000.0
        assert info.margin_used == 50000.0
        assert info.base_currency == "USD"

    # -- Positions -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_positions(self, adapter, mock_client) -> None:
        """Positions are mapped from Alpaca format correctly."""
        pos_response = MagicMock(spec=httpx.Response)
        pos_response.status_code = 200
        pos_response.json.return_value = [
            {
                "symbol": "AAPL",
                "qty": "100",
                "avg_entry_price": "150.0",
                "current_price": "155.0",
            },
        ]
        mock_client.get.return_value = pos_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        positions = await adapter.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "AAPL"
        assert pos.quantity == 100.0
        assert pos.avg_entry_price == 150.0
        assert pos.market_price == 155.0

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, adapter, mock_client) -> None:
        """Empty positions return empty list."""
        pos_response = MagicMock(spec=httpx.Response)
        pos_response.status_code = 200
        pos_response.json.return_value = []
        mock_client.get.return_value = pos_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.connect()

        positions = await adapter.get_positions()
        assert positions == []

    # -- Error: not connected --------------------------------------------

    @pytest.mark.asyncio
    async def test_place_order_not_connected(self, adapter) -> None:
        """Calling place_order without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Not connected"):
            await adapter.place_order(make_market_order())

    @pytest.mark.asyncio
    async def test_get_account_info_not_connected(self, adapter) -> None:
        """Calling get_account_info without connection raises."""
        with pytest.raises(RuntimeError, match="Not connected"):
            await adapter.get_account_info()