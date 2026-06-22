"""Unit tests for risk simulation (Monte Carlo, VaR, stress testing)."""
import numpy as np
import pytest

from ist.risk.simulation import (
    PathSimulator,
    PortfolioSimulator,
    SimulationConfig,
    SimulationResults,
)


class TestSimulationConfig:
    def test_default_values(self):
        cfg = SimulationConfig()
        assert cfg.num_simulations == 10000
        assert cfg.time_horizon == 252
        assert cfg.initial_capital == 100000.0
        assert cfg.confidence_level == 0.95
        assert cfg.random_seed is None
        assert cfg.distribution == "normal"

    def test_custom_values(self):
        cfg = SimulationConfig(
            num_simulations=5000,
            time_horizon=126,
            initial_capital=50000.0,
            confidence_level=0.99,
            random_seed=42,
            distribution="t",
            degrees_of_freedom=7,
        )
        assert cfg.num_simulations == 5000
        assert cfg.time_horizon == 126
        assert cfg.distribution == "t"
        assert cfg.degrees_of_freedom == 7


class TestPathSimulator:
    @pytest.fixture
    def config_seeded(self):
        return SimulationConfig(num_simulations=1000, random_seed=42)

    @pytest.fixture
    def config_large(self):
        return SimulationConfig(num_simulations=2000, random_seed=99)

    def test_simulate_normal_distribution(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.08, volatility=0.20)
        assert isinstance(result, SimulationResults)
        assert -1.0 < result.mean_return < 2.0
        med, mn = result.median_return, result.mean_return
        assert med < mn or med > mn
        assert result.p5_return < result.median_return < result.p95_return

    def test_simulate_t_distribution(self):
        config = SimulationConfig(
            num_simulations=1000,
            random_seed=42,
            distribution="t",
            degrees_of_freedom=5,
        )
        sim = PathSimulator(config)
        result = sim.simulate(mean_return=0.08, volatility=0.20)
        assert isinstance(result, SimulationResults)
        assert result.std_return > 0
        assert result.mean_return < 0.5

    def test_simulate_with_target_return(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.08, volatility=0.20, target_return=0.05)
        assert 0.0 <= result.prob_target_return <= 1.0
        assert result.prob_positive > 0.0

    def test_simulate_high_volatility_increases_risk(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result_low_vol = sim.simulate(mean_return=0.08, volatility=0.10)
        result_high_vol = sim.simulate(mean_return=0.08, volatility=0.50)
        assert result_high_vol.p5_return < result_low_vol.p5_return
        assert result_high_vol.var_95 > result_low_vol.var_95

    def test_simulate_negative_mean_returns(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=-0.05, volatility=0.15)
        assert result.mean_return < 0
        assert result.prob_positive < 0.5

    def test_var_values_are_positive(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.08, volatility=0.20)
        assert result.var_95 >= 0
        assert result.var_99 >= 0
        assert result.cvar_95 >= result.var_95
        assert result.cvar_99 >= result.var_99

    def test_var_99_greater_than_var_95(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.08, volatility=0.20)
        assert result.var_99 >= result.var_95

    def test_max_drawdown_in_range(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.08, volatility=0.20)
        assert 0.0 <= result.max_drawdown_p95 <= 1.0

    def test_prob_positive_sensible(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.10, volatility=0.15)
        assert result.prob_positive > 0.5

    def test_seed_reproducibility(self):
        config1 = SimulationConfig(num_simulations=1000, random_seed=42)
        sim1 = PathSimulator(config1)
        result1 = sim1.simulate(mean_return=0.08, volatility=0.20)

        config2 = SimulationConfig(num_simulations=1000, random_seed=42)
        sim2 = PathSimulator(config2)
        result2 = sim2.simulate(mean_return=0.08, volatility=0.20)

        np.testing.assert_allclose(result1.mean_return, result2.mean_return, rtol=0.01)
        np.testing.assert_allclose(result1.var_95, result2.var_95, rtol=0.01)

    def test_different_seeds_different_results(self):
        config1 = SimulationConfig(num_simulations=5000, random_seed=42)
        sim1 = PathSimulator(config1)
        result1 = sim1.simulate(mean_return=0.08, volatility=0.20)

        config2 = SimulationConfig(num_simulations=5000, random_seed=9999)
        sim2 = PathSimulator(config2)
        result2 = sim2.simulate(mean_return=0.08, volatility=0.20)

        diff_mean = abs(result1.mean_return - result2.mean_return)
        assert diff_mean > 0

    def test_all_paths_stored_for_small_n(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.08, volatility=0.20)
        assert result.all_paths is not None
        assert result.all_paths.shape == (1000, 252)

    def test_all_paths_not_stored_for_large_n(self, config_large):
        sim = PathSimulator(config_large)
        result = sim.simulate(mean_return=0.08, volatility=0.20)
        assert result.all_paths is None

    def test_zero_volatility_constant_returns(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.0, volatility=0.0)
        assert abs(result.mean_return) < 1e-6
        assert abs(result.std_return) < 1e-6
        assert result.var_95 == 0.0

    def test_analyze_scenarios(self, config_seeded):
        sim = PathSimulator(config_seeded)
        scenarios = [
            {"name": "base", "return_factor": 1.0, "vol_factor": 1.0},
            {"name": "bear", "return_factor": 0.5, "vol_factor": 2.0},
            {"name": "bull", "return_factor": 1.5, "vol_factor": 0.5},
        ]
        results = sim.analyze_scenarios(
            mean_return=0.10, volatility=0.20, scenarios=scenarios
        )
        assert "base" in results
        assert "bear" in results
        assert "bull" in results
        assert results["bear"].mean_return < results["base"].mean_return
        assert results["bull"].mean_return > results["base"].mean_return
        assert results["bear"].var_95 > results["base"].var_95

    def test_analyze_scenarios_with_distribution(self, config_seeded):
        sim = PathSimulator(config_seeded)
        scenarios = [
            {
                "name": "t_dist",
                "return_factor": 1.0,
                "vol_factor": 1.0,
                "distribution": "t",
            }
        ]
        results = sim.analyze_scenarios(
            mean_return=0.10, volatility=0.20, scenarios=scenarios
        )
        assert "t_dist" in results
        assert isinstance(results["t_dist"], SimulationResults)

    def test_simulation_results_fields_are_populated(self, config_seeded):
        sim = PathSimulator(config_seeded)
        result = sim.simulate(mean_return=0.08, volatility=0.20)
        for field in [
            "mean_return",
            "median_return",
            "std_return",
            "p5_return",
            "p25_return",
            "p75_return",
            "p95_return",
            "max_drawdown_p95",
            "var_95",
            "var_99",
            "cvar_95",
            "cvar_99",
            "prob_positive",
        ]:
            assert hasattr(result, field)


class TestPortfolioSimulator:
    @pytest.fixture
    def config(self):
        return SimulationConfig(num_simulations=500, random_seed=42)

    def test_simulate_two_assets(self, config):
        sim = PortfolioSimulator(config)
        result = sim.simulate_portfolio(
            weights={"AAPL": 0.6, "MSFT": 0.4},
            mean_returns={"AAPL": 0.12, "MSFT": 0.10},
            volatilities={"AAPL": 0.25, "MSFT": 0.20},
        )
        assert isinstance(result, SimulationResults)
        assert result.mean_return != 0
        assert result.std_return > 0

    def test_simulate_single_asset(self, config):
        sim = PortfolioSimulator(config)
        result = sim.simulate_portfolio(
            weights={"BTC": 1.0},
            mean_returns={"BTC": 0.15},
            volatilities={"BTC": 0.60},
        )
        assert isinstance(result, SimulationResults)
        assert result.cvar_95 == 0.0
        assert result.cvar_99 == 0.0

    def test_simulate_with_correlation(self, config):
        sim = PortfolioSimulator(config)
        corr = np.array([[1.0, 0.5], [0.5, 1.0]])
        result = sim.simulate_portfolio(
            weights={"A": 0.5, "B": 0.5},
            mean_returns={"A": 0.10, "B": 0.10},
            volatilities={"A": 0.20, "B": 0.20},
            correlation_matrix=corr,
        )
        assert result.var_95 > 0

    def test_simulate_with_negative_correlation(self, config):
        sim = PortfolioSimulator(config)
        corr = np.array([[1.0, -0.7], [-0.7, 1.0]])
        result = sim.simulate_portfolio(
            weights={"A": 0.5, "B": 0.5},
            mean_returns={"A": 0.10, "B": 0.10},
            volatilities={"A": 0.20, "B": 0.20},
            correlation_matrix=corr,
        )
        assert result.mean_return != 0
        assert result.var_95 > 0

    def test_multi_asset_prob_positive(self):
        np.random.seed(42)
        config = SimulationConfig(num_simulations=5000, random_seed=99)
        PathSimulator(config)
        sim = PortfolioSimulator(config)
        result = sim.simulate_portfolio(
            weights={"X": 0.5, "Y": 0.5},
            mean_returns={"X": 0.15, "Y": 0.13},
            volatilities={"X": 0.20, "Y": 0.18},
        )
        assert 0.0 <= result.prob_positive <= 1.0
