"""Unit tests for the Order Management System (OMS).

Covers order creation, validation, submission, cancellation, status
updates, listing, statistics, and lifecycle history tracking.
"""

import pytest

from ist.execution.adapter import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from ist.execution.oms import (
    ManagedOrder,
    OrderEvent,
    OrderManagementSystem,
    OrderState,
)


class FakeBroker(BrokerAdapter):
    """Configurable in-memory broker for OMS tests."""

    def __init__(self) -> None:
        super().__init__("fake")
        self.placed_orders: list[Order] = []
        self.cancelled_ids: list[str] = []
        self.place_result: OrderResult | None = None
        self.cancel_result: bool = True
        self.status_result: OrderResult | None = None

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        return AccountInfo(
            account_id="acc",
            cash=100000.0,
            equity=100000.0,
            buying_power=200000.0,
        )

    async def get_quote(self, symbol: str):
        return None

    async def place_order(self, order: Order) -> OrderResult:
        self.placed_orders.append(order)
        if self.place_result is not None:
            return self.place_result
        return OrderResult(
            order_id="broker-1",
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            avg_fill_price=1.0,
        )

    async def cancel_order(self, order_id: str) -> bool:
        self.cancelled_ids.append(order_id)
        return self.cancel_result

    async def get_order_status(self, order_id: str) -> OrderResult | None:
        return self.status_result

    async def get_positions(self) -> list:
        return []

    async def get_open_orders(self) -> list:
        return []


class TestOrderManagementSystem:
    @pytest.fixture
    def broker(self) -> FakeBroker:
        return FakeBroker()

    @pytest.fixture
    def oms(self, broker) -> OrderManagementSystem:
        return OrderManagementSystem(broker)

    # -- Creation & validation -------------------------------------------

    def test_create_order_returns_id_and_validates(self, oms) -> None:
        order_id = oms.create_order("EURUSD", OrderSide.BUY, 1000)

        assert order_id
        managed = oms.get_order(order_id)
        assert isinstance(managed, ManagedOrder)
        assert managed.state == OrderState.VALIDATED
        assert managed.order.symbol == "EURUSD"
        assert managed.order.side == OrderSide.BUY
        assert managed.order.quantity == 1000
        assert managed.order.order_type == OrderType.MARKET
        assert managed.order.time_in_force == TimeInForce.GTC

    @pytest.mark.parametrize("quantity", [0, -1, -100.5])
    def test_create_order_invalid_quantity_raises(self, oms, quantity) -> None:
        with pytest.raises(ValueError, match="Quantity must be positive"):
            oms.create_order("EURUSD", OrderSide.BUY, quantity)

    def test_create_order_empty_symbol_raises(self, oms) -> None:
        with pytest.raises(ValueError, match="Symbol is required"):
            oms.create_order("", OrderSide.BUY, 1000)

    def test_create_limit_order_requires_price(self, oms) -> None:
        with pytest.raises(ValueError, match="Limit price required"):
            oms.create_order(
                "EURUSD", OrderSide.BUY, 1000, order_type=OrderType.LIMIT,
            )

    def test_create_stop_order_requires_price(self, oms) -> None:
        with pytest.raises(ValueError, match="Stop price required"):
            oms.create_order(
                "EURUSD", OrderSide.BUY, 1000, order_type=OrderType.STOP,
            )

    def test_create_limit_order_with_price(self, oms) -> None:
        oid = oms.create_order(
            "EURUSD", OrderSide.BUY, 1000,
            order_type=OrderType.LIMIT, limit_price=1.1,
        )
        assert oms.get_order(oid).order.limit_price == 1.1

    def test_get_order_unknown_returns_none(self, oms) -> None:
        assert oms.get_order("missing") is None

    # -- Submission ------------------------------------------------------

    @pytest.mark.asyncio
    async def test_submit_order_filled(self, oms, broker) -> None:
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        result = await oms.submit_order(oid)

        assert result.status == OrderStatus.FILLED
        managed = oms.get_order(oid)
        assert managed.state == OrderState.FILLED
        assert managed.broker_order_id == "broker-1"
        assert managed.submitted_at is not None
        assert managed.completed_at is not None
        stats = oms.get_statistics()
        assert stats["total_submitted"] == 1
        assert stats["total_filled"] == 1

    @pytest.mark.asyncio
    async def test_submit_order_pending(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-2", status=OrderStatus.PENDING,
        )
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)

        assert oms.get_order(oid).state == OrderState.PENDING

    @pytest.mark.asyncio
    async def test_submit_order_rejected(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-3",
            status=OrderStatus.REJECTED,
            error_message="No liquidity",
        )
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        result = await oms.submit_order(oid)

        assert result.status == OrderStatus.REJECTED
        assert oms.get_order(oid).state == OrderState.REJECTED
        assert oms.get_statistics()["total_rejected"] == 1

    @pytest.mark.asyncio
    async def test_submit_order_in_invalid_state_raises(self, oms, broker) -> None:
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)  # now FILLED

        with pytest.raises(ValueError, match="Cannot submit order in state"):
            await oms.submit_order(oid)

    @pytest.mark.asyncio
    async def test_submit_order_unknown_raises(self, oms) -> None:
        with pytest.raises(ValueError, match="Order not found"):
            await oms.submit_order("missing")

    @pytest.mark.asyncio
    async def test_submit_order_broker_error_records_error(self, oms, broker) -> None:
        async def boom(order: Order) -> OrderResult:
            raise RuntimeError("down")

        broker.place_order = boom
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)

        with pytest.raises(RuntimeError, match="down"):
            await oms.submit_order(oid)

        assert oms.get_order(oid).state == OrderState.ERROR

    # -- Cancellation ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-4", status=OrderStatus.PENDING,
        )
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)

        ok = await oms.cancel_order(oid)

        assert ok is True
        managed = oms.get_order(oid)
        assert managed.state == OrderState.CANCELLED
        assert managed.completed_at is not None
        assert oms.get_statistics()["total_cancelled"] == 1
        assert broker.cancelled_ids == ["broker-4"]

    @pytest.mark.asyncio
    async def test_cancel_order_without_broker_id_returns_false(self, oms) -> None:
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        ok = await oms.cancel_order(oid)

        assert ok is False
        assert oms.get_order(oid).state == OrderState.CANCEL_REQUESTED

    @pytest.mark.asyncio
    async def test_cancel_filled_order_returns_false(self, oms) -> None:
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)  # filled

        ok = await oms.cancel_order(oid)

        assert ok is False
        assert oms.get_order(oid).state == OrderState.FILLED

    @pytest.mark.asyncio
    async def test_cancel_order_broker_rejects(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-5", status=OrderStatus.PENDING,
        )
        broker.cancel_result = False
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)

        ok = await oms.cancel_order(oid)

        assert ok is False
        assert oms.get_order(oid).state == OrderState.CANCEL_REQUESTED

    # -- Status polling --------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_status_no_broker_id_returns_none(self, oms) -> None:
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        assert await oms.update_order_status(oid) is None

    @pytest.mark.asyncio
    async def test_update_status_to_filled(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-6", status=OrderStatus.PENDING,
        )
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)

        broker.status_result = OrderResult(
            order_id="broker-6",
            status=OrderStatus.FILLED,
            filled_quantity=1000,
            avg_fill_price=1.05,
        )
        result = await oms.update_order_status(oid)

        assert result.status == OrderStatus.FILLED
        assert oms.get_order(oid).state == OrderState.FILLED
        assert oms.get_statistics()["total_filled"] == 1

    @pytest.mark.asyncio
    async def test_update_status_to_partial_fill(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-7", status=OrderStatus.PENDING,
        )
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)

        broker.status_result = OrderResult(
            order_id="broker-7",
            status=OrderStatus.PARTIAL_FILL,
            filled_quantity=500,
            remaining_quantity=500,
        )
        await oms.update_order_status(oid)

        assert oms.get_order(oid).state == OrderState.PARTIAL_FILL

    @pytest.mark.asyncio
    async def test_update_status_to_cancelled(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-8", status=OrderStatus.PENDING,
        )
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)

        broker.status_result = OrderResult(
            order_id="broker-8", status=OrderStatus.CANCELLED,
        )
        await oms.update_order_status(oid)

        assert oms.get_order(oid).state == OrderState.CANCELLED

    @pytest.mark.asyncio
    async def test_update_status_to_expired(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-9", status=OrderStatus.PENDING,
        )
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)

        broker.status_result = OrderResult(
            order_id="broker-9", status=OrderStatus.EXPIRED,
        )
        await oms.update_order_status(oid)

        managed = oms.get_order(oid)
        assert managed.state == OrderState.EXPIRED
        assert managed.completed_at is not None

    # -- Listing & lookup ------------------------------------------------

    def test_list_orders_all_and_filter_by_state(self, oms) -> None:
        oms.create_order("EURUSD", OrderSide.BUY, 1000)
        oms.create_order("GBPUSD", OrderSide.SELL, 500)

        assert len(oms.list_orders()) == 2
        assert len(oms.list_orders(state=OrderState.VALIDATED)) == 2
        assert len(oms.list_orders(state=OrderState.FILLED)) == 0

    def test_list_orders_filter_by_symbol(self, oms) -> None:
        oms.create_order("EURUSD", OrderSide.BUY, 1000)
        oms.create_order("GBPUSD", OrderSide.SELL, 500)

        assert len(oms.list_orders(symbol="EURUSD")) == 1
        assert len(oms.list_orders(symbol="ZZZZZ")) == 0

    def test_get_open_orders_empty(self, oms) -> None:
        assert oms.get_open_orders() == []

    @pytest.mark.asyncio
    async def test_get_open_orders_partial_fill(self, oms, broker) -> None:
        broker.place_result = OrderResult(
            order_id="broker-x", status=OrderStatus.PENDING,
        )
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)
        broker.status_result = OrderResult(
            order_id="broker-x",
            status=OrderStatus.PARTIAL_FILL,
            filled_quantity=500,
            remaining_quantity=500,
        )
        await oms.update_order_status(oid)

        open_orders = oms.get_open_orders()

        assert len(open_orders) == 1
        assert open_orders[0].internal_id == oid

    @pytest.mark.asyncio
    async def test_get_order_by_broker_id(self, oms) -> None:
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        await oms.submit_order(oid)

        found = oms.get_order_by_broker_id("broker-1")
        assert found is not None
        assert found.internal_id == oid
        assert oms.get_order_by_broker_id("unknown") is None

    # -- History & statistics -------------------------------------------

    def test_get_order_history(self, oms) -> None:
        oid = oms.create_order("EURUSD", OrderSide.BUY, 1000)
        history = oms.get_order_history(oid)

        assert isinstance(history, list)
        assert all(isinstance(e, OrderEvent) for e in history)
        assert [e.state for e in history] == [
            OrderState.CREATED, OrderState.VALIDATED,
        ]

    def test_statistics_defaults(self, oms) -> None:
        assert oms.get_statistics() == {
            "total_created": 0,
            "total_submitted": 0,
            "total_filled": 0,
            "total_cancelled": 0,
            "total_rejected": 0,
        }

    def test_statistics_tracks_created(self, oms) -> None:
        oms.create_order("EURUSD", OrderSide.BUY, 1000)
        oms.create_order("GBPUSD", OrderSide.SELL, 500)

        assert oms.get_statistics()["total_created"] == 2


class TestManagedOrder:
    def test_add_event_updates_state(self) -> None:
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=10)
        managed = ManagedOrder(
            internal_id="i1", client_order_id="c1", order=order,
        )

        managed.add_event(OrderState.SUBMITTED, "sent")

        assert managed.state == OrderState.SUBMITTED
        assert len(managed.events) == 1
        assert managed.events[0].state == OrderState.SUBMITTED
        assert managed.events[0].description == "sent"
