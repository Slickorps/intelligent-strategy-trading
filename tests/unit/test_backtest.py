"""Unit tests for backtest engine, portfolio, and analytics."""
import math
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from ist.backtest.analytics import PerformanceAnalyzer, PerformanceMetrics
from ist.backtest.engine import BacktestConfig, BacktestEngine, BacktestState, EventLoop
from ist.backtest.portfolio import Portfolio, Position
from ist.data.models import Bar as BarModel


class TestBacktestConfig:
    def test_default_values(self):
        cfg = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
        )
        assert cfg.initial_capital == 100000.0
        assert cfg.commission_rate == 0.001
        assert cfg.slippage_model == "fixed"
        assert cfg.slippage_amount == 0.0001
        assert cfg.margin_requirement == 0.02
        assert cfg.timeframe == "1h"

    def test_start_after_end_raises(self):
        with pytest.raises(ValueError, match="start_date must be before end_date"):
            BacktestConfig(
                start_date=datetime(2023, 12, 31),
                end_date=datetime(2023, 1, 1),
            )

    def test_same_dates_raises(self):
        dt = datetime(2023, 6, 15)
        with pytest.raises(ValueError, match="start_date must be before end_date"):
            BacktestConfig(start_date=dt, end_date=dt)

    def test_negative_capital_raises(self):
        with pytest.raises(ValueError, match="initial_capital must be positive"):
            BacktestConfig(
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_capital=-100.0,
            )

    def test_zero_capital_raises(self):
        with pytest.raises(ValueError, match="initial_capital must be positive"):
            BacktestConfig(
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_capital=0.0,
            )


class TestBacktestState:
    def test_default_state(self):
        dt = datetime(2023, 1, 1)
        state = BacktestState(timestamp=dt, equity=100000.0, cash=100000.0)
        assert state.equity == 100000.0
        assert state.cash == 100000.0
        assert state.positions == {}
        assert state.daily_returns == []
        assert state.trades == []
        assert state.total_trades == 0
        assert state.winning_trades == 0
        assert state.losing_trades == 0
        assert state.peak_equity == 0.0
        assert state.max_drawdown == 0.0


class TestEventLoop:
    def _make_bar(self, symbol: str, ts: datetime, price: float) -> BarModel:
        return BarModel(
            timestamp=ts,
            symbol=symbol,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price * 1.005,
            volume=1000.0,
        )

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.get_history = AsyncMock(return_value=[])
        return provider

    @pytest.mark.asyncio
    async def test_load_data_empty_symbols(self, mock_provider):
        loop = EventLoop(mock_provider)
        await loop.load_data([], datetime(2023, 1, 1), datetime(2023, 1, 10))
        assert loop._timeline == []
        assert loop.get_progress() == 0.0

    @pytest.mark.asyncio
    async def test_load_data_single_symbol(self, mock_provider):
        bars = [
            self._make_bar("AAPL", datetime(2023, 1, i), 150.0 + i)
            for i in range(1, 6)
        ]
        mock_provider.get_history = AsyncMock(return_value=bars)
        loop = EventLoop(mock_provider)
        await loop.load_data(
            ["AAPL"], datetime(2023, 1, 1), datetime(2023, 1, 6)
        )
        assert len(loop._timeline) == 5
        assert loop.get_progress() == 0.0

    @pytest.mark.asyncio
    async def test_load_data_multi_symbol(self, mock_provider):
        bars_aapl = [
            self._make_bar("AAPL", datetime(2023, 1, i, 10), 150.0)
            for i in range(1, 4)
        ]
        bars_msft = [
            self._make_bar("MSFT", datetime(2023, 1, i, 10), 300.0)
            for i in range(1, 4)
        ]

        async def get_history(symbol, start, end, timeframe):
            if symbol == "AAPL":
                return bars_aapl
            return bars_msft

        mock_provider.get_history = get_history
        loop = EventLoop(mock_provider)
        await loop.load_data(
            ["AAPL", "MSFT"], datetime(2023, 1, 1), datetime(2023, 1, 6)
        )
        assert len(loop._timeline) == 3

    def test_next_returns_none_when_empty(self, mock_provider):
        loop = EventLoop(mock_provider)
        assert loop.next() is None

    @pytest.mark.asyncio
    async def test_next_returns_bars_in_order(self, mock_provider):
        bars = [
            self._make_bar("AAPL", datetime(2023, 1, i, 10), 100.0 + i)
            for i in range(1, 4)
        ]
        mock_provider.get_history = AsyncMock(return_value=bars)
        loop = EventLoop(mock_provider)
        await loop.load_data(
            ["AAPL"], datetime(2023, 1, 1), datetime(2023, 1, 5)
        )
        ts1, d1 = loop.next()
        assert ts1 is not None
        assert "AAPL" in d1
        ts2, d2 = loop.next()
        ts3, d3 = loop.next()
        assert loop.next() is None
        assert loop.is_complete

    def test_peek_does_not_advance(self, mock_provider):
        loop = EventLoop(mock_provider)
        loop._timeline = [datetime(2023, 1, 1, 10), datetime(2023, 1, 2, 10)]
        loop._current_index = 0
        assert loop.peek() == loop._timeline[0]
        assert loop.peek() == loop._timeline[0]
        assert loop._current_index == 0

    def test_peek_returns_none_when_empty(self, mock_provider):
        loop = EventLoop(mock_provider)
        assert loop.peek() is None

    def test_peek_returns_none_when_complete(self, mock_provider):
        loop = EventLoop(mock_provider)
        loop._timeline = [datetime(2023, 1, 1)]
        loop._current_index = 1
        assert loop.peek() is None

    def test_reset(self, mock_provider):
        loop = EventLoop(mock_provider)
        loop._timeline = [datetime(2023, 1, 1), datetime(2023, 1, 2)]
        loop._current_index = 2
        assert loop.is_complete
        loop.reset()
        assert loop._current_index == 0
        assert not loop.is_complete

    def test_get_progress_mid(self, mock_provider):
        loop = EventLoop(mock_provider)
        loop._timeline = [datetime(2023, 1, 1)] * 4
        loop._current_index = 2
        assert loop.get_progress() == 0.5

    def test_get_progress_complete(self, mock_provider):
        loop = EventLoop(mock_provider)
        loop._timeline = [datetime(2023, 1, 1)] * 4
        loop._current_index = 4
        assert loop.get_progress() == 1.0
        assert loop.is_complete


class TestBacktestEngine:
    @pytest.fixture
    def mock_strategy_executor(self):
        from ist.strategy.executor import ExecutionResult
        exec_result = ExecutionResult(
            timestamp=datetime(2023, 1, 2),
            actions=[],
            node_states={},
            success=True,
        )
        executor = MagicMock()
        executor.execute_all.return_value = {"strategy_1": exec_result}
        return executor

    @pytest.fixture
    def mock_data_provider(self):
        provider = MagicMock()
        provider.get_history = AsyncMock(return_value=[])
        return provider

    @pytest.fixture
    def engine(self, mock_strategy_executor, mock_data_provider):
        return BacktestEngine(mock_strategy_executor, mock_data_provider)

    @pytest.fixture
    def config(self):
        return BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 10),
            symbols=["AAPL"],
        )

    @pytest.mark.asyncio
    async def test_run_without_setup_raises(self, engine):
        with pytest.raises(RuntimeError, match="not configured"):
            await engine.run()

    @pytest.mark.asyncio
    async def test_setup_initializes_state(self, engine, config):
        engine.setup("bt-001", config)
        assert engine._status == "configured"
        assert engine.state is not None
        assert engine.state.equity == config.initial_capital
        assert engine.state.cash == config.initial_capital
        assert engine.state.peak_equity == config.initial_capital

    @pytest.mark.asyncio
    async def test_run_with_empty_data_completes(self, engine, config):
        engine.setup("bt-empty", config)
        result = await engine.run()
        assert result["backtest_id"] == "bt-empty"
        assert result["status"] == "completed"
        assert result["final_equity"] == config.initial_capital
        assert result["total_return"] == 0.0
        assert result["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_run_with_bar_data(self, mock_data_provider, mock_strategy_executor, config):
        bars = [
            BarModel(
                timestamp=datetime(2023, 1, i, 10),
                symbol="AAPL",
                open=150.0 + i,
                high=152.0 + i,
                low=149.0 + i,
                close=151.0 + i,
                volume=10000.0,
            )
            for i in range(1, 6)
        ]
        mock_data_provider.get_history = AsyncMock(return_value=bars)

        engine = BacktestEngine(mock_strategy_executor, mock_data_provider)
        engine.setup("bt-bars", config)
        result = await engine.run()
        assert result["status"] == "completed"
        assert result["total_trades"] == 0
        assert len(result["equity_curve"]) > 0

    @pytest.mark.asyncio
    async def test_run_with_trading_action(
        self, mock_data_provider, mock_strategy_executor, config
    ):
        bars = [
            BarModel(
                timestamp=datetime(2023, 1, i, 10),
                symbol="AAPL",
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=10000.0,
            )
            for i in range(1, 6)
        ]
        mock_data_provider.get_history = AsyncMock(return_value=bars)

        action = {"symbol": "AAPL", "side": "buy", "size_pct": 0.1}
        from ist.strategy.executor import ExecutionResult
        exec_result = ExecutionResult(
            timestamp=datetime(2023, 1, 2),
            actions=[action],
            node_states={},
            success=True,
        )
        mock_strategy_executor.execute_all.return_value = {"s1": exec_result}

        engine = BacktestEngine(mock_strategy_executor, mock_data_provider)
        config.slippage_amount = 0.0
        config.commission_rate = 0.0
        engine.setup("bt-trade", config)
        result = await engine.run()
        assert result["total_trades"] == 5  # one per bar

    @pytest.mark.asyncio
    async def test_high_concurrency_many_trades(
        self, mock_data_provider, mock_strategy_executor, config
    ):
        start = datetime(2023, 1, 3, 10, 0)
        bars = [
            BarModel(
                timestamp=start + timedelta(hours=i),
                symbol="AAPL",
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=10000.0,
            )
            for i in range(100)
        ]
        mock_data_provider.get_history = AsyncMock(return_value=bars)

        action = {"symbol": "AAPL", "side": "buy", "size_pct": 0.01}
        from ist.strategy.executor import ExecutionResult
        exec_result = ExecutionResult(
            timestamp=datetime(2023, 1, 2),
            actions=[action],
            node_states={},
            success=True,
        )
        mock_strategy_executor.execute_all.return_value = {"s1": exec_result}

        engine = BacktestEngine(mock_strategy_executor, mock_data_provider)
        config.slippage_amount = 0.0
        config.commission_rate = 0.0
        engine.setup("bt-mass", config)
        result = await engine.run()
        assert result["total_trades"] == 100

    @pytest.mark.asyncio
    async def test_extreme_slippage(self, mock_data_provider, mock_strategy_executor, config):
        bars = [
            BarModel(
                timestamp=datetime(2023, 1, i, 10),
                symbol="AAPL",
                open=150.0,
                high=152.0,
                low=149.0,
                close=150.0,
                volume=10000.0,
            )
            for i in range(1, 4)
        ]
        mock_data_provider.get_history = AsyncMock(return_value=bars)

        action = {"symbol": "AAPL", "side": "buy", "size_pct": 0.5}
        from ist.strategy.executor import ExecutionResult
        exec_result = ExecutionResult(
            timestamp=datetime(2023, 1, 2),
            actions=[action],
            node_states={},
            success=True,
        )
        mock_strategy_executor.execute_all.return_value = {"s1": exec_result}

        engine = BacktestEngine(mock_strategy_executor, mock_data_provider)
        config.slippage_amount = 0.05  # 5% extreme slippage
        config.commission_rate = 0.01  # 1% commission
        engine.setup("bt-slip", config)
        result = await engine.run()
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_position_tracking_buy_sell(
        self, mock_data_provider, mock_strategy_executor, config
    ):
        bars = [
            BarModel(
                timestamp=datetime(2023, 1, i, 10),
                symbol="AAPL",
                open=150.0,
                high=152.0,
                low=149.0,
                close=150.0,
                volume=10000.0,
            )
            for i in range(1, 5)
        ]
        mock_data_provider.get_history = AsyncMock(return_value=bars)

        from ist.strategy.executor import ExecutionResult
        buy_action = {"symbol": "AAPL", "side": "buy", "size_pct": 0.4}
        sell_action = {"symbol": "AAPL", "side": "sell", "size_pct": 0.5}

        calls = 0

        def execute_all(bar_data, portfolio_state):
            nonlocal calls
            calls += 1
            if calls <= 2:
                return {"s1": ExecutionResult(datetime(2023, 1, 2), [buy_action], {}, True)}
            else:
                return {"s1": ExecutionResult(datetime(2023, 1, 4), [sell_action], {}, True)}

        mock_strategy_executor.execute_all.side_effect = execute_all

        engine = BacktestEngine(mock_strategy_executor, mock_data_provider)
        config.slippage_amount = 0.0
        config.commission_rate = 0.0
        engine.setup("bt-pos", config)
        result = await engine.run()
        assert result["status"] == "completed"
        assert result["total_trades"] == 4

    def test_get_status_idle(self, engine):
        status = engine.get_status()
        assert status["status"] == "idle"
        assert status["progress"] == 0

    def test_get_status_after_setup(self, engine, config):
        engine.setup("bt-status", config)
        status = engine.get_status()
        assert status["status"] == "configured"

    def test_stop(self, engine):
        engine.stop()
        assert engine._status == "stopped"

    def test_process_action_unknown_symbol_no_op(self, engine, config):
        engine.setup("bt-unk", config)
        bars = {}
        engine._process_action({"symbol": "UNKNOWN", "side": "buy", "size_pct": 0.1}, bars)
        assert engine.state.total_trades == 0


class TestPortfolio:
    @pytest.fixture
    def portfolio(self):
        return Portfolio(initial_capital=100000.0)

    @pytest.fixture
    def timestamp(self):
        return datetime(2023, 1, 2, 10, 0)

    def test_initial_equity_equals_capital(self, portfolio):
        assert portfolio.equity == 100000.0
        assert portfolio.cash == 100000.0

    def test_buy_order_creates_position(self, portfolio, timestamp):
        trade = portfolio.execute_order("AAPL", "buy", 100, 150.0, timestamp)
        assert portfolio.has_position("AAPL")
        pos = portfolio.get_position("AAPL")
        assert pos.quantity == 100
        assert pos.avg_entry_price == 150.0
        assert portfolio.cash < 100000.0
        assert trade["symbol"] == "AAPL"

    def test_sell_order_closes_position(self, portfolio, timestamp):
        portfolio.execute_order("AAPL", "buy", 100, 150.0, timestamp)
        portfolio.execute_order("AAPL", "sell", 100, 155.0, timestamp)
        assert not portfolio.has_position("AAPL")

    def test_execute_order_with_commission(self, portfolio, timestamp):
        portfolio.execute_order(
            "AAPL", "buy", 100, 200.0, timestamp, commission=10.0
        )
        assert portfolio.total_commission == 10.0
        assert portfolio.cash < 100000 - 20000 - 10 + 1  # approximate

    def test_update_prices_updates_unrealized_pnl(self, portfolio, timestamp):
        portfolio.execute_order("AAPL", "buy", 100, 150.0, timestamp)
        portfolio.update_prices({"AAPL": 160.0})
        pos = portfolio.get_position("AAPL")
        assert pos.unrealized_pnl > 0

    def test_get_stats(self, portfolio, timestamp):
        portfolio.execute_order("AAPL", "buy", 100, 150.0, timestamp)
        stats = portfolio.get_stats()
        assert stats["num_trades"] == 1
        assert stats["num_positions"] == 1
        assert "equity" in stats
        assert "total_return" in stats

    def test_get_allocation(self, portfolio, timestamp):
        portfolio.execute_order("AAPL", "buy", 100, 150.0, timestamp)
        alloc = portfolio.get_allocation()
        assert "cash" in alloc
        assert "AAPL" in alloc

    def test_buying_power(self, portfolio, timestamp):
        portfolio.execute_order("AAPL", "buy", 50, 100.0, timestamp)
        assert portfolio.buying_power > 0
        assert portfolio.buying_power < 100000


class TestPosition:
    @pytest.fixture
    def timestamp(self):
        return datetime(2023, 1, 2, 10, 0)

    def test_create_long_position(self, timestamp):
        pos = Position("AAPL", 100, 150.0, timestamp)
        assert pos.is_long
        assert not pos.is_short
        assert pos.side == "long"

    def test_create_short_position(self, timestamp):
        pos = Position("AAPL", -100, 150.0, timestamp)
        assert pos.is_short
        assert pos.side == "short"

    def test_close_long_position(self, timestamp):
        pos = Position("AAPL", 100, 150.0, timestamp)
        summary = pos.close(160.0, timestamp)
        assert pos.is_flat
        assert summary["realized_pnl"] > 0
        assert summary["symbol"] == "AAPL"

    def test_close_short_position(self, timestamp):
        pos = Position("AAPL", -100, 150.0, timestamp)
        summary = pos.close(140.0, timestamp)
        assert pos.is_flat
        assert summary["realized_pnl"] > 0

    def test_close_flat_position_returns_empty(self, timestamp):
        pos = Position("AAPL", 0, 150.0, timestamp)
        assert pos.close(160.0, timestamp) == {}

    def test_add_quantity_same_direction(self, timestamp):
        pos = Position("AAPL", 100, 150.0, timestamp)
        pos.add_quantity(50, 160.0, timestamp)
        assert pos.quantity == 150
        expected_avg = (100 * 150.0 + 50 * 160.0) / 150.0
        assert math.isclose(pos.avg_entry_price, expected_avg)

    def test_add_quantity_reverses_direction(self, timestamp):
        pos = Position("AAPL", 100, 150.0, timestamp)
        pos.add_quantity(-200, 160.0, timestamp)
        assert pos.quantity == -100
        assert pos.avg_entry_price == 160.0

    def test_update_price_long(self, timestamp):
        pos = Position("AAPL", 100, 150.0, timestamp)
        pos.update_price(155.0)
        assert pos.unrealized_pnl == 500.0

    def test_update_price_short(self, timestamp):
        pos = Position("AAPL", -100, 150.0, timestamp)
        pos.update_price(140.0)
        assert pos.unrealized_pnl != 0

    def test_market_value(self, timestamp):
        pos = Position("AAPL", 100, 150.0, timestamp)
        assert pos.market_value() == 0.0
        pos.update_price(160.0)
        assert pos.market_value(160.0) == 16000.0


class TestPerformanceAnalyzer:
    def test_empty_data_returns_default_metrics(self):
        analyzer = PerformanceAnalyzer()
        metrics = analyzer.calculate_metrics(100000.0)
        assert metrics.total_return == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.total_trades == 0

    def test_single_day_returns_default_metrics(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [{"date": "2023-01-01", "equity": 100000.0}], []
        )
        metrics = analyzer.calculate_metrics(100000.0)
        assert metrics.total_return == 0.0

    def test_two_days_profit(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [
                {"date": "2023-01-01", "equity": 100000.0},
                {"date": "2023-01-02", "equity": 105000.0},
            ],
            [],
        )
        metrics = analyzer.calculate_metrics(100000.0)
        assert metrics.total_return == 0.05
        assert metrics.annualized_return > 0

    def test_two_days_loss(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [
                {"date": "2023-01-01", "equity": 100000.0},
                {"date": "2023-01-02", "equity": 95000.0},
            ],
            [],
        )
        metrics = analyzer.calculate_metrics(100000.0)
        assert metrics.total_return == -0.05
        assert metrics.max_drawdown > 0

    def test_trade_metrics_with_wins_and_losses(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [
                {"date": "2023-01-01", "equity": 100000.0},
                {"date": "2023-01-02", "equity": 105000.0},
            ],
            [
                {"realized_pnl": 500.0},
                {"realized_pnl": -200.0},
                {"realized_pnl": 300.0},
            ],
        )
        metrics = analyzer.calculate_metrics(100000.0)
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.win_rate == 2 / 3
        assert metrics.profit_factor > 1.0

    def test_profit_factor_no_losses(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [
                {"date": "2023-01-01", "equity": 100000.0},
                {"date": "2023-01-02", "equity": 105000.0},
            ],
            [
                {"realized_pnl": 500.0},
                {"realized_pnl": 300.0},
            ],
        )
        metrics = analyzer.calculate_metrics(100000.0)
        assert metrics.profit_factor == float("inf")

    def test_max_drawdown_calculation(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [
                {"date": "2023-01-01", "equity": 100000.0},
                {"date": "2023-01-02", "equity": 110000.0},
                {"date": "2023-01-03", "equity": 95000.0},
                {"date": "2023-01-04", "equity": 105000.0},
            ],
            [],
        )
        metrics = analyzer.calculate_metrics(100000.0)
        assert 0 < metrics.max_drawdown < 1
        assert metrics.max_drawdown_duration > 0

    def test_generate_report_returns_dict(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [
                {"date": "2023-01-01", "equity": 100000.0},
                {"date": "2023-01-02", "equity": 102000.0},
            ],
            [{"realized_pnl": 500.0}],
        )
        metrics = analyzer.calculate_metrics(100000.0)
        report = analyzer.generate_report(metrics)
        assert "summary" in report
        assert "risk_metrics" in report
        assert "trade_metrics" in report
        assert "assessment" in report

    def test_get_monthly_returns_empty(self):
        analyzer = PerformanceAnalyzer()
        assert analyzer.get_monthly_returns() == []

    def test_get_monthly_returns_single_month(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [
                {"date": "2023-01-01", "equity": 100000.0},
                {"date": "2023-01-15", "equity": 101000.0},
            ],
            [],
        )
        returns = analyzer.get_monthly_returns()
        assert returns == []

    def test_get_monthly_returns_two_months(self):
        analyzer = PerformanceAnalyzer()
        analyzer.load_data(
            [
                {"date": "2023-01-15", "equity": 100000.0},
                {"date": "2023-01-31", "equity": 101000.0},
                {"date": "2023-02-15", "equity": 103000.0},
            ],
            [],
        )
        returns = analyzer.get_monthly_returns()
        assert len(returns) == 1
        assert returns[0]["month"] == "2023-02"
        assert returns[0]["return"] > 0

    def test_expectancy_property(self):
        metrics = PerformanceMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=0.6,
            avg_win=100.0,
            avg_loss=-80.0,
        )
        expected = 0.6 * 100.0 + 0.4 * -80.0
        assert math.isclose(metrics.expectancy, expected)

    def test_expectancy_zero_trades(self):
        metrics = PerformanceMetrics()
        assert metrics.expectancy == 0.0
