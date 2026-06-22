"""End-to-end integration test for full strategy backtest flow."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from ist.backtest.engine import BacktestConfig, BacktestEngine
from ist.data.models import Bar as BarModel
from ist.strategy.executor import ExecutionResult, StrategyExecutor


class TestFullBacktestFlow:
    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        return provider

    @pytest.fixture
    def executor(self):
        return StrategyExecutor()

    @pytest.fixture
    def engine(self, executor, mock_provider):
        return BacktestEngine(executor, mock_provider)

    @pytest.mark.asyncio
    async def test_empty_backtest_completes(self, engine, mock_provider):
        mock_provider.get_history = AsyncMock(return_value=[])
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 31),
            symbols=["AAPL"],
        )
        engine.setup("e2e-empty", config)
        result = await engine.run()
        assert result["status"] == "completed"
        assert result["backtest_id"] == "e2e-empty"
        assert result["final_equity"] == config.initial_capital
        assert "equity_curve" in result

    @pytest.mark.asyncio
    async def test_backtest_with_buy_and_hold(self, engine, mock_provider):
        bars = [
            BarModel(
                timestamp=datetime(2023, 1, i, 10),
                symbol="AAPL",
                open=150.0 + i * 2,
                high=152.0 + i * 2,
                low=149.0 + i * 2,
                close=151.0 + i * 2,
                volume=10000.0,
            )
            for i in range(1, 21)
        ]
        mock_provider.get_history = AsyncMock(return_value=bars)

        buy_action = {"symbol": "AAPL", "side": "buy", "size_pct": 1.0}
        exec_result = ExecutionResult(
            timestamp=datetime(2023, 1, 2),
            actions=[buy_action],
            node_states={},
            success=True,
        )
        engine.strategy_executor.execute_all = MagicMock(
            return_value={"s1": exec_result}
        )

        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 21),
            symbols=["AAPL"],
            slippage_amount=0.0,
            commission_rate=0.0,
        )
        engine.setup("e2e-buyhold", config)
        result = await engine.run()
        assert result["status"] == "completed"
        assert result["total_trades"] == 20

    @pytest.mark.asyncio
    async def test_backtest_handles_strategy_errors(self, engine, mock_provider):
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
        mock_provider.get_history = AsyncMock(return_value=bars)

        exec_result = ExecutionResult(
            timestamp=datetime(2023, 1, 2),
            actions=[],
            node_states={},
            success=False,
            error_message="Strategy computation failed",
        )
        engine.strategy_executor.execute_all = MagicMock(
            return_value={"s1": exec_result}
        )

        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 6),
            symbols=["AAPL"],
        )
        engine.setup("e2e-err", config)
        result = await engine.run()
        assert result["status"] == "completed"
        assert result["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_backtest_config_end_to_end(self, engine, mock_provider):
        mock_provider.get_history = AsyncMock(return_value=[])
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 6, 30),
            initial_capital=250000.0,
            symbols=["EURUSD", "GBPUSD"],
            timeframe="4h",
            commission_rate=0.0005,
            slippage_model="fixed",
            slippage_amount=0.0002,
            margin_requirement=0.05,
        )
        engine.setup("e2e-config", config)
        result = await engine.run()
        assert result["config"]["initial_capital"] == 250000.0
        assert result["config"]["symbols"] == ["EURUSD", "GBPUSD"]

    @pytest.mark.asyncio
    async def test_backtest_large_config_survives(self, engine, mock_provider):
        mock_provider.get_history = AsyncMock(return_value=[])
        config = BacktestConfig(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=1000000.0,
            symbols=[f"ASSET_{i}" for i in range(20)],
        )
        engine.setup("e2e-large", config)
        result = await engine.run()
        assert result["status"] == "completed"
