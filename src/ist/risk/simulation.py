"""Monte Carlo path simulation."""

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ist.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SimulationConfig:
    """Configuration for Monte Carlo simulation."""
    
    num_simulations: int = 10000
    time_horizon: int = 252  # Trading days (1 year)
    initial_capital: float = 100000.0
    confidence_level: float = 0.95
    random_seed: Optional[int] = None
    
    # Return distribution parameters
    distribution: str = "normal"  # normal, t, empirical
    degrees_of_freedom: int = 5  # For t-distribution


@dataclass
class SimulationResults:
    """Results of Monte Carlo simulation."""
    
    # Summary statistics
    mean_return: float
    median_return: float
    std_return: float
    
    # Percentile returns
    p5_return: float
    p25_return: float
    p75_return: float
    p95_return: float
    
    # Risk metrics
    max_drawdown_p95: float
    var_95: float  # Value at Risk
    var_99: float
    cvar_95: float  # Conditional VaR (Expected Shortfall)
    cvar_99: float
    
    # Probabilities
    prob_positive: float
    prob_target_return: float
    
    # All paths (optional, for visualization)
    all_paths: Optional[np.ndarray] = None


class PathSimulator:
    """Monte Carlo path simulator.
    
    Generates random return paths for portfolio simulation
    and risk assessment.
    """
    
    def __init__(self, config: Optional[SimulationConfig] = None) -> None:
        self.config = config or SimulationConfig()
        
        if self.config.random_seed is not None:
            np.random.seed(self.config.random_seed)
    
    def simulate(
        self,
        mean_return: float,
        volatility: float,
        target_return: Optional[float] = None
    ) -> SimulationResults:
        """Run Monte Carlo simulation.
        
        Args:
            mean_return: Expected annualized return (decimal)
            volatility: Expected annualized volatility (decimal)
            target_return: Target return for probability calculation
            
        Returns:
            Simulation results with risk metrics
        """
        logger.info(
            "Starting Monte Carlo simulation",
            num_sims=self.config.num_simulations,
            horizon=self.config.time_horizon
        )
        
        # Convert annual to daily parameters
        daily_mean = mean_return / 252
        daily_vol = volatility / np.sqrt(252)
        
        # Generate random returns
        returns = self._generate_returns(daily_mean, daily_vol)
        
        # Calculate cumulative returns
        cumulative_returns = self._calculate_paths(returns)
        
        # Calculate metrics
        final_returns = cumulative_returns[:, -1]
        
        # Calculate drawdowns for all paths
        max_drawdowns = self._calculate_drawdowns(cumulative_returns)
        
        # Build results
        results = self._build_results(
            final_returns,
            max_drawdowns,
            cumulative_returns,
            target_return
        )
        
        logger.info(
            "Simulation completed",
            mean_return=f"{results.mean_return:.2%}",
            var_95=f"{results.var_95:.2%}"
        )
        
        return results
    
    def _generate_returns(
        self,
        daily_mean: float,
        daily_vol: float
    ) -> np.ndarray:
        """Generate random daily returns."""
        shape = (self.config.num_simulations, self.config.time_horizon)
        
        if self.config.distribution == "normal":
            returns = np.random.normal(daily_mean, daily_vol, shape)
            
        elif self.config.distribution == "t":
            # Student's t-distribution (fatter tails)
            t_returns = np.random.standard_t(
                self.config.degrees_of_freedom,
                shape
            )
            # Scale to match desired mean and vol
            t_std = np.sqrt(
                self.config.degrees_of_freedom /
                (self.config.degrees_of_freedom - 2)
            ) if self.config.degrees_of_freedom > 2 else 1.0
            returns = daily_mean + daily_vol * t_returns / t_std
            
        elif self.config.distribution == "empirical":
            # Bootstrap from historical returns
            # Placeholder - would need historical data
            returns = np.random.normal(daily_mean, daily_vol, shape)
        else:
            returns = np.random.normal(daily_mean, daily_vol, shape)
        
        return returns
    
    def _calculate_paths(self, returns: np.ndarray) -> np.ndarray:
        """Calculate cumulative return paths."""
        # Convert returns to cumulative wealth
        # Wealth_t = Capital * prod(1 + r_i)
        wealth_factors = np.cumprod(1 + returns, axis=1)
        cumulative_returns = (wealth_factors - 1)
        return cumulative_returns
    
    def _calculate_drawdowns(
        self,
        cumulative_returns: np.ndarray
    ) -> np.ndarray:
        """Calculate maximum drawdown for each path."""
        wealth = 1 + cumulative_returns
        
        # Running maximum
        running_max = np.maximum.accumulate(wealth, axis=1)
        
        # Drawdown
        drawdown = (running_max - wealth) / running_max
        
        # Max drawdown per path
        max_drawdown = np.max(drawdown, axis=1)
        
        return max_drawdown
    
    def _build_results(
        self,
        final_returns: np.ndarray,
        max_drawdowns: np.ndarray,
        paths: np.ndarray,
        target_return: Optional[float]
    ) -> SimulationResults:
        """Build simulation results from raw data."""
        # Basic statistics
        mean_ret = np.mean(final_returns)
        median_ret = np.median(final_returns)
        std_ret = np.std(final_returns)
        
        # Percentiles
        p5 = np.percentile(final_returns, 5)
        p25 = np.percentile(final_returns, 25)
        p75 = np.percentile(final_returns, 75)
        p95 = np.percentile(final_returns, 95)
        
        # Drawdown percentiles
        max_dd_p95 = np.percentile(max_drawdowns, 95)
        
        # Value at Risk
        var_95 = np.percentile(final_returns, 5)  # 5th percentile
        var_99 = np.percentile(final_returns, 1)  # 1st percentile
        
        # Conditional VaR (Expected Shortfall)
        cvar_95 = np.mean(final_returns[final_returns <= var_95])
        cvar_99 = np.mean(final_returns[final_returns <= var_99])
        
        # Probabilities
        prob_positive = np.mean(final_returns > 0)
        
        prob_target = 0.0
        if target_return is not None:
            prob_target = np.mean(final_returns >= target_return)
        
        return SimulationResults(
            mean_return=mean_ret,
            median_return=median_ret,
            std_return=std_ret,
            p5_return=p5,
            p25_return=p25,
            p75_return=p75,
            p95_return=p95,
            max_drawdown_p95=max_dd_p95,
            var_95=-var_95,  # Convert to positive number for display
            var_99=-var_99,
            cvar_95=-cvar_95 if not np.isnan(cvar_95) else 0.0,
            cvar_99=-cvar_99 if not np.isnan(cvar_99) else 0.0,
            prob_positive=prob_positive,
            prob_target_return=prob_target,
            all_paths=paths if self.config.num_simulations <= 1000 else None
        )
    
    def analyze_scenarios(
        self,
        mean_return: float,
        volatility: float,
        scenarios: list[dict[str, Any]]
    ) -> dict[str, SimulationResults]:
        """Run simulation for multiple scenarios.
        
        Args:
            mean_return: Base expected return
            volatility: Base volatility
            scenarios: List of scenario dicts with adjustments
            
        Returns:
            Dictionary mapping scenario name to results
        """
        results = {}
        
        for scenario in scenarios:
            name = scenario.get("name", "unnamed")
            
            # Apply scenario adjustments
            adjusted_return = mean_return * scenario.get("return_factor", 1.0)
            adjusted_vol = volatility * scenario.get("vol_factor", 1.0)
            
            # Temporarily adjust config
            original_dist = self.config.distribution
            if "distribution" in scenario:
                self.config.distribution = scenario["distribution"]
            
            # Run simulation
            sim_results = self.simulate(adjusted_return, adjusted_vol)
            results[name] = sim_results
            
            # Restore config
            self.config.distribution = original_dist
        
        return results


class PortfolioSimulator:
    """Simulate portfolio with multiple assets."""
    
    def __init__(self, config: Optional[SimulationConfig] = None) -> None:
        self.config = config or SimulationConfig()
    
    def simulate_portfolio(
        self,
        weights: dict[str, float],
        mean_returns: dict[str, float],
        volatilities: dict[str, float],
        correlation_matrix: Optional[np.ndarray] = None
    ) -> SimulationResults:
        """Simulate multi-asset portfolio.
        
        Args:
            weights: Asset weights
            mean_returns: Expected returns per asset
            volatilities: Volatilities per asset
            correlation_matrix: Correlation matrix (if None, assume independent)
            
        Returns:
            Portfolio simulation results
        """
        symbols = list(weights.keys())
        n_assets = len(symbols)
        n_sims = self.config.num_simulations
        horizon = self.config.time_horizon
        
        # Convert to arrays
        w = np.array([weights[s] for s in symbols])
        mu = np.array([mean_returns[s] for s in symbols])
        sigma = np.array([volatilities[s] for s in symbols])
        
        # Build covariance matrix
        if correlation_matrix is not None:
            cov = np.outer(sigma, sigma) * correlation_matrix
        else:
            cov = np.diag(sigma ** 2)
        
        # Generate correlated returns
        # Cholesky decomposition
        L = np.linalg.cholesky(cov + np.eye(n_assets) * 1e-10)
        
        # Generate random returns
        z = np.random.standard_normal((n_sims, horizon, n_assets))
        
        # Correlated returns
        daily_returns = np.zeros((n_sims, horizon, n_assets))
        for t in range(horizon):
            daily_returns[:, t, :] = z[:, t, :] @ L.T + mu / 252
        
        # Portfolio returns
        portfolio_returns = np.sum(daily_returns * w, axis=2)
        
        # Calculate paths
        cumulative_returns = np.cumprod(1 + portfolio_returns, axis=1) - 1
        final_returns = cumulative_returns[:, -1]
        
        # Calculate drawdowns
        wealth = 1 + cumulative_returns
        running_max = np.maximum.accumulate(wealth, axis=1)
        drawdown = (running_max - wealth) / running_max
        max_drawdowns = np.max(drawdown, axis=1)
        
        # Build results (simplified version)
        return SimulationResults(
            mean_return=np.mean(final_returns),
            median_return=np.median(final_returns),
            std_return=np.std(final_returns),
            p5_return=np.percentile(final_returns, 5),
            p25_return=np.percentile(final_returns, 25),
            p75_return=np.percentile(final_returns, 75),
            p95_return=np.percentile(final_returns, 95),
            max_drawdown_p95=np.percentile(max_drawdowns, 95),
            var_95=-np.percentile(final_returns, 5),
            var_99=-np.percentile(final_returns, 1),
            cvar_95=0.0,
            cvar_99=0.0,
            prob_positive=np.mean(final_returns > 0),
            prob_target_return=0.0
        )
