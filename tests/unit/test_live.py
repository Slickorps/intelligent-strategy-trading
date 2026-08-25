"""Unit tests for the live trading engine.

Covers LiveTradingConfig/TradingState validation, engine startup and
shutdown, signal processing, risk limits, and the circuit breaker.
"""

from datetime import datetime

import pytest

from ist.core.events import EventType
from ist.core.exceptions import ExecutionError
from ist.data.models import Quote
from ist.execution.adapter import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderResult,
    OrderStatus,
)
from ist.execution.live import (
    LiveTradingConfig,
    LiveTradingEngine,
    TradingMode,
    TradingState,
)
from ist.strategy.executor import StrategyExecutor


class FakeBroker(BrokerAdapter):
    """Configurable in-memory broker for live trading engine tests."""

    def __init__(self) -> None:
        super().__init__("fake")
        self.connect_result: bool = True
        self.equity: float = 100000.0
        self.quote: Quote = Quote(
            timestamp=datetime.utcnow(),
            symbol="EURUSD",
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
        )
        self.place_result: OrderResult = OrderResult(
            order_id="broker-1",
            status=OrderStatus.FILLED,
            filled_quantity=1.0,
            avg_fill_price=1.0,
        )
        self.placed_orders: list[Order] = []

    async def connect(self) -> bool:
        self._connected = self.connect_result
        return self.connect_result

    async def disconnect(self) -> None:
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        return AccountInfo(
            account_id="acc",
            cash=self.equity,
            equity=self.equity,
            buying_power=self.equity * 2,
        )

    async def get_quote(self, symbol: str) -> Quote | None:
        return self.quote

    async def place_order(self, order: Order) -> OrderResult:
        self.placed_orders.append(order)
        return self.place_result

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_order_status(self, order_id: str) -> OrderResult | None:
        return None

    async def get_positions(self) -> list:
        return []

    async def get_open_orders(self) -> list:
        return []


def make_signal(engine: LiveTradingEngine, actions: list, strategy_id: str = "s1"):
    return engine.event_bus.create_event(
        EventType.SIGNAL_GENERATED,
        {"strategy_id": strategy_id, "actions": actions},
        "executor",
    )


class TestLiveTradingConfig:
    def test_defaults(self) -> None:
        cfg = LiveTradingConfig()
        assert cfg.mode == TradingMode.PAPER
        assert cfg.max_positions == 10
        assert cfg.max_orders_per_minute == 10
        assert cfg.circuit_breaker_enabled is True
        assert cfg.circuit_breaker_threshold == 5
        assert cfg.max_position_size_pct == 0.10
        assert cfg.max_daily_loss_pct == 0.02

    def test_custom(self) -> None:
        cfg = LiveTradingConfig(
            mode=TradingMode.LIVE,
            max_positions=3,
            circuit_breaker_enabled=False,
        )
        assert cfg.mode == TradingMode.LIVE
        assert cfg.max_positions == 3
        assert cfg.circuit_breaker_enabled is False


class TestTradingState:
    def test_defaults(self) -> None:
        state = TradingState()
        assert state.is_running is False
        assert state.mode == TradingMode.PAPER
        assert state.orders_submitted == 0
        assert state.orders_filled == 0
        assert state.orders_rejected == 0
        assert state.consecutive_errors == 0
        assert state.circuit_breaker_triggered is False
        assert state.daily_pnl == 0.0


class TestLiveTradingEngine:
    @pytest.fixture
    def broker(self) -> FakeBroker:
        return FakeBroker()

    @pytest.fixture
    def executor(self) -> StrategyExecutor:
        return StrategyExecutor()

    @pytest.fixture
    def engine(self, executor, broker) -> LiveTradingEngine:
        return LiveTradingEngine(strategy_executor=executor, broker=broker)

    # -- Construction ----------------------------------------------------

    def test_init_creates_oms_and_state(self, engine, broker) -> None:
        assert engine.broker is broker
        assert engine.config.mode == TradingMode.PAPER
        assert engine.state.mode == TradingMode.PAPER
        assert engine.state.is_running is False
        assert engine.oms is not None
        assert engine.oms.broker is broker

    # -- Start / stop ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_start_success(self, engine) -> None:
        await engine.start()

        assert engine.state.is_running is True
        assert engine.broker.is_connected is True
        assert engine.state.circuit_breaker_triggered is False
        assert engine.state.consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_start_connect_failure_raises(self, engine) -> None:
        engine.broker.connect_result = False
        with pytest.raises(ExecutionError, match="Failed to connect"):
            await engine.start()
        assert engine.state.is_running is False

    @pytest.mark.asyncio
    async def test_stop_disconnects_and_stops(self, engine) -> None:
        await engine.start()
        await engine.stop()

        assert engine.state.is_running is False
        assert engine.broker.is_connected is False

    @pytest.mark.asyncio
    async def test_stop_without_start_does_not_raise(self, engine) -> None:
        await engine.stop()
        assert engine.state.is_running is False

    # -- Signal handling -------------------------------------------------

    @pytest.mark.asyncio
    async def test_on_signal_ignored_when_not_running(self, engine) -> None:
        event = make_signal(
            engine, [{"symbol": "EURUSD", "side": "buy", "size_pct": 0.05}],
        )
        await engine._on_signal(event)

        assert engine.state.orders_submitted == 0

    @pytest.mark.asyncio
    async def test_on_signal_ignored_when_circuit_breaker(self, engine) -> None:
        engine.state.is_running = True
        engine.state.circuit_breaker_triggered = True
        event = make_signal(
            engine, [{"symbol": "EURUSD", "side": "buy", "size_pct": 0.05}],
        )
        await engine._on_signal(event)

        assert engine.state.orders_submitted == 0

    @pytest.mark.asyncio
    async def test_on_signal_processes_action(self, engine) -> None:
        engine.state.is_running = True
        event = make_signal(
            engine, [{"symbol": "EURUSD", "side": "buy", "size_pct": 0.05}],
        )
        await engine._on_signal(event)

        assert engine.state.orders_submitted == 1
        assert engine.state.orders_filled == 1
        assert engine.state.consecutive_errors == 0

    # -- Action processing ----------------------------------------------

    @pytest.mark.asyncio
    async def test_process_action_missing_symbol(self, engine) -> None:
        engine.state.is_running = True
        await engine._process_action({"side": "buy", "size_pct": 0.05})

        assert engine.state.orders_submitted == 0

    @pytest.mark.asyncio
    async def test_process_action_zero_size(self, engine) -> None:
        engine.state.is_running = True
        await engine._process_action(
            {"symbol": "EURUSD", "side": "buy", "size_pct": 0.0},
        )

        assert engine.state.orders_submitted == 0

    @pytest.mark.asyncio
    async def test_process_action_exceeds_position_size_limit(self, engine) -> None:
        engine.state.is_running = True
        await engine._process_action(
            {"symbol": "EURUSD", "side": "buy", "size_pct": 0.50},
        )

        assert engine.state.orders_submitted == 0

    @pytest.mark.asyncio
    async def test_process_action_rejected_order(self, engine) -> None:
        engine.state.is_running = True
        engine.broker.place_result = OrderResult(
            order_id="broker-2",
            status=OrderStatus.REJECTED,
            error_message="nope",
        )
        await engine._process_action(
            {"symbol": "EURUSD", "side": "buy", "size_pct": 0.05},
        )

        assert engine.state.orders_submitted == 1
        assert engine.state.orders_rejected == 1

    # -- Risk limits -----------------------------------------------------

    @pytest.mark.asyncio
    async def test_risk_limits_position_size(self, engine) -> None:
        assert await engine._check_risk_limits("EURUSD", 0.50) is False
        assert await engine._check_risk_limits("EURUSD", 0.05) is True

    @pytest.mark.asyncio
    async def test_risk_limits_daily_loss(self, engine) -> None:
        engine.state.daily_pnl = -0.05
        assert await engine._check_risk_limits("EURUSD", 0.05) is False

    @pytest.mark.asyncio
    async def test_risk_limits_max_positions(self, engine) -> None:
        for i in range(engine.config.max_positions):
            engine._positions[f"SYM{i}"] = {}

        assert await engine._check_risk_limits("NEW", 0.05) is False
        assert await engine._check_risk_limits("SYM0", 0.05) is True

    # -- Circuit breaker -------------------------------------------------

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggered_after_threshold(self, engine) -> None:
        engine.state.is_running = True
        engine.state.consecutive_errors = engine.config.circuit_breaker_threshold - 1

        async def boom(order: Order) -> OrderResult:
            raise RuntimeError("down")

        engine.broker.place_order = boom
        event = make_signal(
            engine, [{"symbol": "EURUSD", "side": "buy", "size_pct": 0.05}],
        )
        await engine._on_signal(event)

        assert engine.state.consecutive_errors == engine.config.circuit_breaker_threshold
        assert engine.state.circuit_breaker_triggered is True

    @pytest.mark.asyncio
    async def test_trigger_circuit_breaker(self, engine) -> None:
        engine.state.is_running = True
        await engine._trigger_circuit_breaker()
        assert engine.state.circuit_breaker_triggered is True

    @pytest.mark.asyncio
    async def test_reset_circuit_breaker(self, engine) -> None:
        await engine._trigger_circuit_breaker()
        await engine.reset_circuit_breaker()

        assert engine.state.circuit_breaker_triggered is False
        assert engine.state.consecutive_errors == 0

    # -- Status & mode ---------------------------------------------------

    def test_get_status(self, engine) -> None:
        status = engine.get_status()
        assert status["is_running"] is False
        assert status["mode"] == "PAPER"
        assert status["orders"]["submitted"] == 0
        assert status["circuit_breaker"]["triggered"] is False
        assert status["positions"] == 0

    @pytest.mark.asyncio
    async def test_switch_mode_while_running_raises(self, engine) -> None:
        await engine.start()
        with pytest.raises(ExecutionError, match="Cannot switch mode"):
            engine.switch_mode(TradingMode.LIVE)

    def test_switch_mode_when_stopped(self, engine) -> None:
        engine.switch_mode(TradingMode.LIVE)

        assert engine.config.mode == TradingMode.LIVE
        assert engine.state.mode == TradingMode.LIVE
