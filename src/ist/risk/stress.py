"""Stress testing framework."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import numpy as np

from ist.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StressScenario:
    """Definition of a stress test scenario."""
    
    name: str
    description: str
    
    # Market condition adjustments
    return_shock: float = 0.0  # Immediate return shock (e.g., -0.20 for -20%)
    volatility_multiplier: float = 1.0
    correlation_spike: bool = False
    
    # Duration parameters
    shock_duration_days: int = 1
    recovery_periods: int = 60  # Days to recover
    
    # Historical replay parameters (if using historical scenario)
    historical_period: Optional[tuple[datetime, datetime]] = None


@dataclass
class StressResult:
    """Results of stress test."""
    
    scenario_name: str
    
    # Portfolio impact
    max_loss: float
    final_equity: float
    drawdown: float
    
    # Recovery metrics
    recovery_days: int
    survival_probability: float
    
    # Risk metrics under stress
    stressed_var_95: float
    stressed_var_99: float
    
    # Assessment
    breaches_limits: bool
    recommendations: list[str]


class StressTester:
    """Portfolio stress testing framework."""
    
    # Predefined historical scenarios
    HISTORICAL_SCENARIOS = {
        "2008_financial_crisis": StressScenario(
            name="2008 Financial Crisis",
            description="Global financial crisis with equity markets down ~50%",
            return_shock=-0.45,
            volatility_multiplier=3.0,
            correlation_spike=True,
            shock_duration_days=30,
            recovery_periods=400,
            historical_period=(datetime(2008, 9, 1), datetime(2009, 3, 1))
        ),
        "covid_crash": StressScenario(
            name="COVID-19 Crash",
            description="March 2020 market crash with rapid recovery",
            return_shock=-0.35,
            volatility_multiplier=4.0,
            correlation_spike=True,
            shock_duration_days=20,
            recovery_periods=150,
            historical_period=(datetime(2020, 2, 20), datetime(2020, 4, 30))
        ),
        "taper_tantrum": StressScenario(
            name="2013 Taper Tantrum",
            description="Bond market reaction to Fed tapering announcement",
            return_shock=-0.15,
            volatility_multiplier=1.5,
            correlation_spike=False,
            shock_duration_days=60,
            recovery_periods=100,
            historical_period=(datetime(2013, 5, 1), datetime(2013, 9, 1))
        ),
        "crypto_winter": StressScenario(
            name="Crypto Winter",
            description="Extended crypto bear market with -80% drawdowns",
            return_shock=-0.70,
            volatility_multiplier=2.0,
            correlation_spike=False,
            shock_duration_days=180,
            recovery_periods=365,
            historical_period=(datetime(2021, 11, 1), datetime(2022, 11, 1))
        ),
        "flash_crash": StressScenario(
            name="Flash Crash",
            description="Intraday crash with rapid intraday recovery",
            return_shock=-0.10,
            volatility_multiplier=5.0,
            correlation_spike=True,
            shock_duration_days=1,
            recovery_periods=5,
            historical_period=(datetime(2010, 5, 6), datetime(2010, 5, 7))
        ),
    }
    
    def __init__(
        self,
        max_drawdown_limit: float = 0.15,
        var_limit: float = 0.10
    ) -> None:
        self.max_drawdown_limit = max_drawdown_limit
        self.var_limit = var_limit
    
    def run_scenario(
        self,
        scenario: StressScenario,
        portfolio_value: float,
        portfolio_volatility: float,
        portfolio_beta: float = 1.0
    ) -> StressResult:
        """Run single stress test scenario.
        
        Args:
            scenario: Stress scenario definition
            portfolio_value: Current portfolio value
            portfolio_volatility: Current portfolio volatility
            portfolio_beta: Portfolio market beta
            
        Returns:
            Stress test results
        """
        logger.info(
            "Running stress test",
            scenario=scenario.name,
            shock=scenario.return_shock
        )
        
        # Calculate portfolio loss under scenario
        # Apply beta-adjusted shock
        adjusted_shock = scenario.return_shock * portfolio_beta
        
        # Multi-day shock
        if scenario.shock_duration_days > 1:
            # Compounding daily shocks
            daily_shock = adjusted_shock / scenario.shock_duration_days
            compounded_loss = (1 + daily_shock) ** scenario.shock_duration_days - 1
            max_loss = compounded_loss
        else:
            max_loss = adjusted_shock
        
        # Account for volatility expansion
        stressed_vol = portfolio_volatility * scenario.volatility_multiplier
        vol_adjustment = stressed_vol * 0.1  # Additional 10% of vol as tail risk
        
        max_loss = min(0, max_loss - vol_adjustment)
        
        # Calculate final equity
        final_equity = portfolio_value * (1 + max_loss)
        drawdown = abs(max_loss)
        
        # Estimate recovery time
        recovery_days = self._estimate_recovery(
            drawdown,
            portfolio_volatility,
            scenario.recovery_periods
        )
        
        # Calculate survival probability
        survival_prob = self._calculate_survival_probability(
            drawdown,
            self.max_drawdown_limit
        )
        
        # Calculate stressed VaR
        stressed_var_95 = 1.645 * stressed_vol  # 95% confidence
        stressed_var_99 = 2.326 * stressed_vol  # 99% confidence
        
        # Check limits
        breaches = drawdown > self.max_drawdown_limit
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            scenario, drawdown, survival_prob, breaches
        )
        
        return StressResult(
            scenario_name=scenario.name,
            max_loss=max_loss,
            final_equity=final_equity,
            drawdown=drawdown,
            recovery_days=recovery_days,
            survival_probability=survival_probability,
            stressed_var_95=stressed_var_95,
            stressed_var_99=stressed_var_99,
            breaches_limits=breaches,
            recommendations=recommendations
        )
    
    def run_all_scenarios(
        self,
        portfolio_value: float,
        portfolio_volatility: float,
        portfolio_beta: float = 1.0
    ) -> dict[str, StressResult]:
        """Run all predefined scenarios."""
        results = {}
        
        for name, scenario in self.HISTORICAL_SCENARIOS.items():
            results[name] = self.run_scenario(
                scenario,
                portfolio_value,
                portfolio_volatility,
                portfolio_beta
            )
        
        return results
    
    def custom_shock_test(
        self,
        shocks: dict[str, float],  # Symbol to shock amount
        weights: dict[str, float],
        correlations: Optional[np.ndarray] = None
    ) -> dict[str, Any]:
        """Run custom shock test on specific assets.
        
        Args:
            shocks: Dict of symbol to shock percentage
            weights: Portfolio weights
            correlations: Correlation matrix
            
        Returns:
            Custom shock results
        """
        symbols = list(shocks.keys())
        
        # Calculate portfolio impact
        individual_impacts = {
            s: shocks[s] * weights.get(s, 0) for s in symbols
        }
        
        # Account for correlations
        if correlations is not None and len(symbols) > 1:
            # Increase impact based on correlations
            total_shock = sum(individual_impacts.values())
            avg_corr = np.mean(correlations[np.triu_indices_from(correlations, k=1)])
            correlation_penalty = 1 + avg_corr * 0.5
            portfolio_impact = total_shock * correlation_penalty
        else:
            portfolio_impact = sum(individual_impacts.values())
        
        return {
            "individual_shocks": shocks,
            "individual_impacts": individual_impacts,
            "portfolio_impact": portfolio_impact,
            "portfolio_loss_pct": abs(portfolio_impact),
            "risk_concentration": max(individual_impacts.values()) / abs(portfolio_impact)
            if portfolio_impact != 0 else 0
        }
    
    def _estimate_recovery(
        self,
        drawdown: float,
        volatility: float,
        max_recovery: int
    ) -> int:
        """Estimate recovery time in days."""
        if drawdown == 0:
            return 0
        
        # Simplified recovery estimate
        # Assume average return of volatility / 2
        avg_daily_return = volatility / 2 / 252
        
        if avg_daily_return <= 0:
            return max_recovery
        
        # Days to recover: ln(1/(1-dd)) / daily_return
        days = np.log(1 / (1 - drawdown)) / avg_daily_return
        
        return min(int(days), max_recovery)
    
    def _calculate_survival_probability(
        self,
        drawdown: float,
        limit: float
    ) -> float:
        """Calculate probability of surviving the drawdown."""
        if drawdown <= limit:
            return 1.0
        
        # Exponential decay of survival probability beyond limit
        excess = drawdown - limit
        survival = np.exp(-excess * 5)  # Steep penalty for excess drawdown
        
        return max(0.0, min(1.0, survival))
    
    def _generate_recommendations(
        self,
        scenario: StressScenario,
        drawdown: float,
        survival_prob: float,
        breaches: bool
    ) -> list[str]:
        """Generate recommendations based on stress results."""
        recommendations = []
        
        if breaches:
            recommendations.append(
                f"CRITICAL: Scenario '{scenario.name}' exceeds max drawdown limit. "
                f"Reduce position sizes or add hedges."
            )
        
        if survival_prob < 0.8:
            recommendations.append(
                f"High risk: Survival probability only {survival_prob:.1%}. "
                f"Consider de-risking strategies."
            )
        
        if scenario.volatility_multiplier > 2.0:
            recommendations.append(
                f"Volatility spike expected. Ensure liquidity buffers are adequate."
            )
        
        if not recommendations:
            recommendations.append(
                f"Portfolio resilient to '{scenario.name}' scenario."
            )
        
        return recommendations
    
    def get_scenario_summary(
        self,
        results: dict[str, StressResult]
    ) -> dict[str, Any]:
        """Generate summary across all stress tests."""
        worst_scenario = max(results.items(), key=lambda x: x[1].drawdown)
        best_scenario = min(results.items(), key=lambda x: x[1].drawdown)
        
        avg_drawdown = np.mean([r.drawdown for r in results.values()])
        avg_recovery = np.mean([r.recovery_days for r in results.values()])
        
        num_breaches = sum(1 for r in results.values() if r.breaches_limits)
        
        return {
            "num_scenarios": len(results),
            "num_breaches": num_breaches,
            "breach_rate": num_breaches / len(results) if results else 0,
            "worst_case": {
                "scenario": worst_scenario[0],
                "drawdown": worst_scenario[1].drawdown,
                "recovery_days": worst_scenario[1].recovery_days
            },
            "best_case": {
                "scenario": best_scenario[0],
                "drawdown": best_scenario[1].drawdown
            },
            "average_drawdown": avg_drawdown,
            "average_recovery_days": avg_recovery,
            "overall_resilience": "high" if num_breaches == 0 else
                                  "medium" if num_breaches <= 2 else "low"
        }
