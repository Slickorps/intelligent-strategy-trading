# Configuration Guide

## Strategy Profiles

Strategy profiles are JSON configuration files that define:
- Investment objectives (target returns, risk limits)
- Asset allocation weights
- Rebalancing parameters
- Risk management settings
- Visual strategy node definitions

### Profile Structure

```json
{
  "profile_name": "Profile Name",
  "target_annual_return": "8% - 12%",
  "max_drawdown_limit": "5%",
  "asset_allocation": {
    "forex_majors": 0.40,
    "gold_commodities": 0.20,
    "index_cfds": 0.30,
    "crypto_bluechips": 0.10
  },
  "rebalancing": {
    "enabled": true,
    "threshold_pct": 3.0,
    "frequency": "daily"
  },
  "risk_management": {
    "path_simulation_runs": 10000,
    "confidence_level": 0.95,
    "stress_test_scenarios": ["2008_financial_crisis", "covid_crash"],
    "dynamic_position_sizing": true,
    "max_position_size_pct": 0.15
  },
  "strategy_nodes": {
    "version": "1.0",
    "nodes": [...],
    "connections": [...]
  }
}
```

### Asset Allocation

Asset classes must sum to approximately 1.0 (100%):
- `forex_majors`: Major currency pairs (EUR/USD, GBP/USD, etc.)
- `gold_commodities`: Precious metals and commodities
- `index_cfds`: Stock index contracts (SPX500, etc.)
- `crypto_bluechips`: Cryptocurrencies (BTC, ETH, etc.)

### Strategy Nodes

The visual strategy builder uses a node-graph approach:

**Node Types:**
- `DataSourceNode`: Market data input
- `IndicatorNode`: Technical indicators (SMA, EMA, RSI, MACD, etc.)
- `ConditionNode`: Logical conditions (crossover, threshold)
- `RiskNode`: Risk management checks
- `ActionNode`: Trading actions (buy, sell, rebalance)

**Connection Format:**
```json
{
  "from": "source_node_id",
  "to": "target_node_id"
}
```

### Risk Management Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `path_simulation_runs` | Monte Carlo simulation iterations | 10000 |
| `confidence_level` | Statistical confidence level | 0.95 |
| `stress_test_scenarios` | Historical scenarios to test | ["2008_financial_crisis"] |
| `max_position_size_pct` | Maximum single position size | 0.15 |
| `volatility_target` | Target portfolio volatility | 0.10 |

## Environment Variables

See `.env.example` for all available configuration options.
