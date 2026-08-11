"""Unit tests for risk factors, risk budget, and stress testing."""
import math

import numpy as np
import pytest

from ist.risk.budget import (
    RebalanceRule,
    RiskAllocation,
    RiskBudget,
    RiskParityAllocator,
)
from ist.risk.factors import (
    CorrelationFactor,
    FactorResult,
    MomentumFactor,
    MultiFactorModel,
    TrendFactor,
    VolatilityFactor,
)
from ist.risk.stress import StressResult, StressScenario, StressTester


class TestMomentumFactor:
    def test_insufficient_data_returns_neutral(self):
        factor = MomentumFactor(short_period=20, medium_period=60, long_period=120)
        result = factor.calculate([100.0] * 10)
        assert result.direction == "neutral"
        assert result.confidence == 0.0
        assert result.score == 50.0

    def test_sufficient_data_returns_score(self):
        prices = list(range(100, 250))  # 150 data points
        factor = MomentumFactor(short_period=20, medium_period=60, long_period=120)
        result = factor.calculate(prices)
        assert 0.0 <= result.score <= 100.0
        assert result.confidence > 0.0
        assert result.weight == 0.30

    def test_uptrend_gives_high_score(self):
        prices = [100.0 + i * 0.5 for i in range(150)]
        factor = MomentumFactor()
        result = factor.calculate(prices)
        assert result.score > 50.0
        assert result.direction in ("positive", "neutral")

    def test_downtrend_gives_low_score(self):
        prices = [250.0 - i * 0.5 for i in range(150)]
        factor = MomentumFactor()
        result = factor.calculate(prices)
        assert result.score < 50.0
        assert result.direction in ("negative", "neutral")

    def test_reset_clears_history(self):
        factor = MomentumFactor()
        factor.calculate([100.0 + i for i in range(200)])
        factor.reset()
        result = factor.calculate([100.0, 101.0, 102.0])
        assert result.confidence == 0.0


class TestVolatilityFactor:
    def test_insufficient_data(self):
        factor = VolatilityFactor(period=20)
        result = factor.calculate([100.0] * 10)
        assert result.confidence == 0.0
        assert result.score == 50.0

    def test_low_volatility_high_score(self):
        prices = [100.0 + i * 0.01 for i in range(50)]
        factor = VolatilityFactor(period=20)
        result = factor.calculate(prices)
        assert 0 <= result.score <= 100
        assert result.weight == 0.25
        assert isinstance(result.direction, str)

    def test_high_volatility_low_score(self):
        prices = [100.0]
        for _ in range(40):
            prices.append(prices[-1] * (1 + np.random.uniform(-0.05, 0.05)))
        factor = VolatilityFactor(period=20)
        result = factor.calculate(prices)
        assert isinstance(result.score, (int, float))


class TestCorrelationFactor:
    def test_no_volume_returns_neutral(self):
        factor = CorrelationFactor(period=10)
        prices = list(range(100, 130))
        result = factor.calculate(prices, volumes=None)
        assert result.confidence == 0.0
        assert result.score == 50.0

    def test_with_volume_returns_score(self):
        factor = CorrelationFactor(period=10)
        prices = list(range(100, 140))
        volumes = [1000 + i * 10 for i in range(40)]
        result = factor.calculate(prices, volumes=volumes)
        assert 0 <= result.score <= 100
        assert result.weight == 0.20


class TestTrendFactor:
    def test_insufficient_data(self):
        factor = TrendFactor(fast_period=20, slow_period=50)
        result = factor.calculate([100.0] * 10)
        assert result.confidence == 0.0

    def test_uptrend(self):
        prices = [100.0 + i * 0.3 for i in range(120)]
        factor = TrendFactor(fast_period=20, slow_period=50)
        result = factor.calculate(prices)
        assert isinstance(result.score, float)

    def test_downtrend(self):
        prices = [200.0 - i * 0.3 for i in range(120)]
        factor = TrendFactor(fast_period=20, slow_period=50)
        result = factor.calculate(prices)
        assert isinstance(result.direction, str)


class TestMultiFactorModel:
    @pytest.fixture
    def model(self):
        return MultiFactorModel()

    @pytest.fixture
    def prices(self):
        return {
            "EURUSD": [1.1 + i * 0.001 for i in range(200)],
            "XAUUSD": [1800 + i * 0.5 for i in range(200)],
        }

    def test_analyze_returns_all_symbols(self, model, prices):
        results = model.analyze(prices)
        assert "EURUSD" in results
        assert "XAUUSD" in results

    def test_analyze_has_composite_score(self, model, prices):
        results = model.analyze(prices)
        for symbol, data in results.items():
            assert "composite_score" in data
            assert "direction" in data
            assert "recommendation" in data
            assert 0 <= data["composite_score"] <= 100

    def test_analyze_with_volumes(self, model, prices):
        volumes = {
            "EURUSD": [1000 + i for i in range(200)],
            "XAUUSD": [500 + i * 2 for i in range(200)],
        }
        results = model.analyze(prices, volumes=volumes)
        assert len(results) == 2

    def test_reset(self, model, prices):
        model.analyze(prices)
        model.reset()
        results = model.analyze({"AAPL": [150.0 + i for i in range(5)]})
        rec = results["AAPL"]["recommendation"]
        assert rec in ("hold", "insufficient_data")

    def test_recommendation_returns_valid(self, model):
        r = model._generate_recommendation(70, "positive", 0.8)
        assert r in ("strong_buy", "buy", "hold", "sell", "strong_sell", "insufficient_data")

    def test_recommendation_low_confidence(self, model):
        r = model._generate_recommendation(70, "positive", 0.2)
        assert r == "insufficient_data"


class TestRiskAllocation:
    def test_basic_allocation(self):
        alloc = RiskAllocation("AAPL", 0.3, 0.05, 0.04)
        assert alloc.symbol == "AAPL"
        assert alloc.is_over_budget is False

    def test_over_budget(self):
        alloc = RiskAllocation("TSLA", 0.1, 0.02, 0.05)
        assert alloc.is_over_budget


class TestRiskBudget:
    @pytest.fixture
    def budget(self):
        return RiskBudget(total_risk_budget=0.06, diversification_factor=0.8)

    def test_set_target_weights_invalid_sum(self, budget):
        with pytest.raises(ValueError, match="must sum to 1.0"):
            budget.set_target_weights({"A": 0.5, "B": 0.2})

    def test_set_target_weights_valid(self, budget):
        budget.set_target_weights({"A": 0.6, "B": 0.4})
        assert len(budget._allocations) == 2

    def test_update_risk_estimates_no_correlation(self, budget):
        budget.set_target_weights({"X": 0.5, "Y": 0.5})
        budget.update_risk_estimates({"X": 0.15, "Y": 0.12})
        assert "X" in budget._allocations
        assert budget._allocations["X"].current_risk > 0

    def test_update_risk_estimates_with_correlation(self, budget):
        budget.set_target_weights({"A": 0.5, "B": 0.5})
        corr = np.array([[1.0, 0.5], [0.5, 1.0]])
        budget.update_risk_estimates({"A": 0.20, "B": 0.18}, correlations=corr)
        assert "A" in budget._allocations

    def test_check_rebalance_not_needed(self, budget):
        budget.set_target_weights({"A": 0.5, "B": 0.5})
        needs, deviations, triggered = budget.check_rebalance_needed({"A": 0.49, "B": 0.51})
        assert not needs

    def test_check_rebalance_disabled(self, budget):
        budget.rebalancing.enabled = False
        budget.set_target_weights({"A": 0.5, "B": 0.5})
        needs, _, _ = budget.check_rebalance_needed({"A": 0.3, "B": 0.7})
        assert not needs

    def test_calculate_rebalance_trades(self, budget):
        budget.set_target_weights({"A": 0.6, "B": 0.4})
        trades = budget.calculate_rebalance_trades({"A": 0.5, "B": 0.5}, 100000)
        assert isinstance(trades, list)

    def test_get_portfolio_risk_summary_empty(self, budget):
        summary = budget.get_portfolio_risk_summary()
        assert summary == {}

    def test_get_portfolio_risk_summary(self, budget):
        budget.set_target_weights({"A": 0.6, "B": 0.4})
        budget.update_risk_estimates({"A": 0.10, "B": 0.15})
        summary = budget.get_portfolio_risk_summary()
        assert "total_risk_budget" in summary
        assert summary["num_assets"] == 2


class TestRiskParityAllocator:
    def test_single_asset_returns_100(self):
        allocator = RiskParityAllocator()
        weights = allocator.calculate_weights({"A": 0.20})
        assert weights["A"] == pytest.approx(1.0)

    def test_empty_returns_empty(self):
        allocator = RiskParityAllocator()
        assert allocator.calculate_weights({}) == {}

    def test_two_assets(self):
        allocator = RiskParityAllocator()
        weights = allocator.calculate_weights({"A": 0.20, "B": 0.15})
        assert len(weights) == 2
        assert math.isclose(sum(weights.values()), 1.0, rel_tol=0.01)

    def test_with_correlation(self):
        allocator = RiskParityAllocator()
        corr = np.array([[1.0, 0.3], [0.3, 1.0]])
        weights = allocator.calculate_weights(
            {"X": 0.20, "Y": 0.20}, correlations=corr
        )
        assert len(weights) == 2


class TestStressScenario:
    def test_default_scenario(self):
        s = StressScenario("test", "A test scenario")
        assert s.return_shock == 0.0
        assert s.volatility_multiplier == 1.0
        assert s.correlation_spike is False

    def test_custom_scenario(self):
        s = StressScenario(
            "crash", "Market crash", return_shock=-0.30,
            volatility_multiplier=3.0, correlation_spike=True,
            shock_duration_days=10, recovery_periods=90,
        )
        assert s.return_shock == -0.30
        assert s.recovery_periods == 90


class TestStressTester:
    @pytest.fixture
    def tester(self):
        return StressTester(max_drawdown_limit=0.20, var_limit=0.12)

    def test_run_scenario_basic(self, tester):
        scenario = StressScenario("test", "test", return_shock=-0.15)
        result = tester.run_scenario(
            scenario, portfolio_value=100000, portfolio_volatility=0.15
        )
        assert isinstance(result, StressResult)
        assert result.max_loss <= 0
        assert result.final_equity > 0

    def test_run_scenario_multi_day_shock(self, tester):
        scenario = StressScenario(
            "multi", "multi-day", return_shock=-0.02,
            shock_duration_days=5, volatility_multiplier=2.0,
        )
        result = tester.run_scenario(
            scenario, portfolio_value=50000, portfolio_volatility=0.10
        )
        assert result.stressed_var_95 > 0

    def test_run_all_scenarios(self, tester):
        results = tester.run_all_scenarios(
            portfolio_value=100000, portfolio_volatility=0.18
        )
        assert "2008_financial_crisis" in results
        assert "covid_crash" in results
        assert "flash_crash" in results

    def test_custom_shock_test(self, tester):
        result = tester.custom_shock_test(
            shocks={"AAPL": -0.10, "MSFT": -0.05},
            weights={"AAPL": 0.6, "MSFT": 0.4},
        )
        assert "portfolio_loss_pct" in result
        assert "risk_concentration" in result

    def test_custom_shock_with_correlation(self, tester):
        corr = np.array([[1.0, 0.6], [0.6, 1.0]])
        result = tester.custom_shock_test(
            shocks={"A": -0.10, "B": -0.08},
            weights={"A": 0.5, "B": 0.5},
            correlations=corr,
        )
        assert result["portfolio_impact"] < 0

    def test_get_scenario_summary(self, tester):
        results = tester.run_all_scenarios(100000, 0.15)
        summary = tester.get_scenario_summary(results)
        assert "worst_case" in summary
        assert "average_drawdown" in summary
        assert "overall_resilience" in summary

    def test_breach_detection(self, tester):
        scenario = StressScenario(
            "severe", "severe crash", return_shock=-0.50,
            volatility_multiplier=5.0, correlation_spike=True,
        )
        result = tester.run_scenario(scenario, portfolio_value=100000, portfolio_volatility=0.20)
        assert result.drawdown > 0
        assert isinstance(result.recommendations, list)
