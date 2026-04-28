"""Risk management demo.

This example demonstrates risk management features:
- Risk budget allocation
- Multi-factor analysis
- Monte Carlo simulation
- Stress testing
"""

import numpy as np

from ist.risk import (
    RiskBudget,
    RebalanceRule,
    MomentumFactor,
    VolatilityFactor,
    MultiFactorModel,
    PathSimulator,
    SimulationConfig,
    StressTester,
)


def demo_risk_budget():
    """Demonstrate risk budget management."""
    print("=" * 60)
    print("Risk Budget Management Demo")
    print("=" * 60)
    
    # Create risk budget
    rebalance_rule = RebalanceRule(
        enabled=True,
        threshold_pct=3.0,
        frequency="daily"
    )
    
    risk_budget = RiskBudget(
        total_risk_budget=0.05,  # 5% max portfolio risk
        diversification_factor=0.85,
        rebalancing=rebalance_rule
    )
    
    # Set target allocation
    target_weights = {
        "EURUSD": 0.40,
        "XAUUSD": 0.20,
        "SPX500": 0.30,
        "BTCUSD": 0.10
    }
    
    risk_budget.set_target_weights(target_weights)
    
    print("\nTarget Allocation:")
    for symbol, weight in target_weights.items():
        print(f"  {symbol}: {weight:.1%}")
    
    # Update with volatility estimates
    volatilities = {
        "EURUSD": 0.08,
        "XAUUSD": 0.15,
        "SPX500": 0.16,
        "BTCUSD": 0.45
    }
    
    risk_budget.update_risk_estimates(volatilities)
    
    print("\nRisk Budget Allocation:")
    summary = risk_budget.get_portfolio_risk_summary()
    for symbol, alloc in summary["allocations"].items():
        print(f"  {symbol}:")
        print(f"    Weight: {alloc['weight']:.1%}")
        print(f"    Risk Budget: {alloc['risk_budget']:.2%}")
        print(f"    Current Risk: {alloc['current_risk']:.2%}")
        print(f"    Utilization: {alloc['utilization']:.1%}")
    
    # Check rebalancing
    current_weights = {
        "EURUSD": 0.42,
        "XAUUSD": 0.18,
        "SPX500": 0.31,
        "BTCUSD": 0.09
    }
    
    needs_rebalance, deviations, triggered = risk_budget.check_rebalance_needed(
        current_weights
    )
    
    print(f"\nRebalance Check:")
    print(f"  Needs Rebalance: {needs_rebalance}")
    print(f"  Triggered By: {triggered}")
    print(f"  Deviations: {deviations}")


def demo_multi_factor():
    """Demonstrate multi-factor model."""
    print("\n" + "=" * 60)
    print("Multi-Factor Model Demo")
    print("=" * 60)
    
    # Create factor model
    model = MultiFactorModel()
    
    # Generate sample price data
    np.random.seed(42)
    
    prices = {
        "EURUSD": [1.08 + i * 0.001 + np.random.normal(0, 0.002) for i in range(100)],
        "XAUUSD": [1500 + i * 0.5 + np.random.normal(0, 5) for i in range(100)],
    }
    
    # Analyze
    results = model.analyze(prices)
    
    print("\nFactor Analysis Results:")
    for symbol, result in results.items():
        print(f"\n{symbol}:")
        print(f"  Composite Score: {result['composite_score']:.1f}")
        print(f"  Direction: {result['direction']}")
        print(f"  Recommendation: {result['recommendation']}")
        print(f"  Confidence: {result['composite_confidence']:.1%}")
        
        print("  Factor Breakdown:")
        for factor_name, factor_data in result['factors'].items():
            print(f"    {factor_name}: {factor_data['score']:.1f} "
                  f"({factor_data['direction']})")


def demo_monte_carlo():
    """Demonstrate Monte Carlo simulation."""
    print("\n" + "=" * 60)
    print("Monte Carlo Simulation Demo")
    print("=" * 60)
    
    # Configure simulation
    config = SimulationConfig(
        num_simulations=10000,
        time_horizon=252,  # 1 year
        initial_capital=100000.0,
        confidence_level=0.95,
        random_seed=42
    )
    
    simulator = PathSimulator(config)
    
    # Run simulation
    results = simulator.simulate(
        mean_return=0.08,  # 8% annual return
        volatility=0.12,   # 12% volatility
        target_return=0.05  # Check probability of 5% return
    )
    
    print(f"\nSimulation Results ({config.num_simulations:,} runs):")
    print(f"  Mean Return: {results.mean_return:.2%}")
    print(f"  Median Return: {results.median_return:.2%}")
    print(f"  Std Deviation: {results.std_return:.2%}")
    
    print(f"\nPercentile Returns:")
    print(f"  5th Percentile: {results.p5_return:.2%}")
    print(f"  25th Percentile: {results.p25_return:.2%}")
    print(f"  75th Percentile: {results.p75_return:.2%}")
    print(f"  95th Percentile: {results.p95_return:.2%}")
    
    print(f"\nRisk Metrics:")
    print(f"  Max Drawdown (P95): {results.max_drawdown_p95:.2%}")
    print(f"  VaR 95%: {results.var_95:.2%}")
    print(f"  VaR 99%: {results.var_99:.2%}")
    print(f"  CVaR 95%: {results.cvar_95:.2%}")
    
    print(f"\nProbabilities:")
    print(f"  Positive Return: {results.prob_positive:.1%}")
    print(f"  Achieve 5%+ Return: {results.prob_target_return:.1%}")


def demo_stress_test():
    """Demonstrate stress testing."""
    print("\n" + "=" * 60)
    print("Stress Testing Demo")
    print("=" * 60)
    
    tester = StressTester(max_drawdown_limit=0.15)
    
    portfolio_value = 100000.0
    portfolio_vol = 0.12
    
    # Run predefined scenarios
    results = tester.run_all_scenarios(
        portfolio_value,
        portfolio_vol,
        portfolio_beta=1.0
    )
    
    print("\nStress Test Results:")
    for scenario_name, result in results.items():
        print(f"\n{result.scenario_name}:")
        print(f"  Max Loss: {result.max_loss:.2%}")
        print(f"  Final Equity: ${result.final_equity:,.2f}")
        print(f"  Drawdown: {result.drawdown:.2%}")
        print(f"  Recovery (est): {result.recovery_days} days")
        print(f"  Survival Probability: {result.survival_probability:.1%}")
        print(f"  Breaches Limit: {result.breaches_limits}")
        
        if result.recommendations:
            print(f"  Recommendations:")
            for rec in result.recommendations:
                print(f"    - {rec}")
    
    # Get summary
    summary = tester.get_scenario_summary(results)
    print(f"\nOverall Summary:")
    print(f"  Scenarios Run: {summary['num_scenarios']}")
    print(f"  Breach Rate: {summary['breach_rate']:.1%}")
    print(f"  Resilience: {summary['overall_resilience'].upper()}")
    print(f"  Worst Case: {summary['worst_case']['scenario']} "
          f"({summary['worst_case']['drawdown']:.1%})")


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("Intelligent Strategy Trading - Risk Management Demo")
    print("=" * 60)
    
    try:
        demo_risk_budget()
        demo_multi_factor()
        demo_monte_carlo()
        demo_stress_test()
        
        print("\n" + "=" * 60)
        print("Risk Management Demo completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
