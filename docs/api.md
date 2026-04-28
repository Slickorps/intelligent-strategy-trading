# API Documentation

## Overview

Intelligent Strategy Trading Platform provides a RESTful API for:
- Strategy management
- Backtesting
- Portfolio analysis
- Risk assessment

**Base URL**: `http://localhost:8000`

**OpenAPI/Swagger UI**: `http://localhost:8000/docs`

**ReDoc**: `http://localhost:8000/redoc`

---

## Authentication

Currently, the API does not require authentication. For production deployment, implement:

```
Authorization: Bearer <token>
```

---

## Health Check

### GET /health

Check API health status.

**Response**:
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "0.1.0",
    "timestamp": "2024-01-15T09:30:00Z"
  }
}
```

### GET /version

Get API version information.

**Response**:
```json
{
  "success": true,
  "data": {
    "app_name": "intelligent-strategy-trading",
    "version": "0.1.0",
    "debug": false
  }
}
```

---

## Strategies

### GET /strategies

List all trading strategies.

**Response**:
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid-string",
      "name": "Conservative Strategy",
      "description": "Long-term wealth preservation",
      "status": "active",
      "config": {...},
      "created_at": "2024-01-10T08:00:00Z",
      "updated_at": "2024-01-15T09:30:00Z"
    }
  ],
  "message": "Found 1 strategies"
}
```

### POST /strategies

Create a new trading strategy.

**Request**:
```json
{
  "name": "My Strategy",
  "description": "Golden cross strategy",
  "profile_name": "balanced",
  "target_annual_return": "8% - 12%",
  "max_drawdown_limit": "8%",
  "asset_allocation": {
    "forex_majors": 0.40,
    "index_cfds": 0.30,
    "gold_commodities": 0.20,
    "crypto_bluechips": 0.10
  },
  "nodes": [
    {
      "id": "data_source",
      "type": "DataSourceNode",
      "params": {"symbol": "EURUSD", "timeframe": "1h"}
    },
    {
      "id": "sma_50",
      "type": "IndicatorNode",
      "params": {"indicator": "SMA", "period": 50}
    },
    {
      "id": "buy_action",
      "type": "ActionNode",
      "params": {"action": "buy", "size_pct": 0.05}
    }
  ],
  "connections": [
    {"from": "data_source", "to": "sma_50"},
    {"from": "sma_50", "to": "buy_action"}
  ]
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "id": "uuid-string",
    "name": "My Strategy",
    "description": "Golden cross strategy",
    "status": "draft",
    "config": {...},
    "created_at": "2024-01-15T09:30:00Z",
    "updated_at": "2024-01-15T09:30:00Z"
  },
  "message": "Strategy created successfully"
}
```

### GET /strategies/{id}

Get strategy details.

**Path Parameters**:
- `id` (string, required): Strategy ID

**Response**: Single strategy object (same as list items)

### GET /strategies/{id}/flowchart

Get strategy flowchart visualization data.

**Path Parameters**:
- `id` (string, required): Strategy ID

**Response**:
```json
{
  "success": true,
  "data": {
    "strategy_id": "uuid-string",
    "strategy_name": "My Strategy",
    "nodes": [
      {
        "id": "data_source",
        "type": "DataSourceNode",
        "params": {"symbol": "EURUSD"},
        "position": {"x": 100, "y": 100}
      }
    ],
    "connections": [
      {"from": "data_source", "to": "sma_50"}
    ],
    "is_valid": true,
    "validation_errors": []
  }
}
```

### DELETE /strategies/{id}

Delete a strategy.

**Path Parameters**:
- `id` (string, required): Strategy ID

**Response**:
```json
{
  "success": true,
  "data": {"deleted": "uuid-string"},
  "message": "Strategy deleted successfully"
}
```

---

## Backtest

### POST /backtest/run

Start a backtest for a strategy.

**Request**:
```json
{
  "strategy_id": "uuid-string",
  "start_date": "2020-01-01",
  "end_date": "2023-12-31",
  "initial_capital": 100000.0,
  "symbols": ["EURUSD", "XAUUSD"],
  "timeframe": "1h",
  "commission_rate": 0.001,
  "slippage_model": "fixed"
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "backtest_id": "uuid-string",
    "status": "pending",
    "estimated_completion": "2024-01-15T09:35:00Z"
  },
  "message": "Backtest scheduled"
}
```

### GET /backtest

List all backtests.

**Response**:
```json
{
  "success": true,
  "data": [
    {
      "backtest_id": "uuid-string",
      "status": "completed",
      "progress_pct": 100.0,
      "started_at": "2024-01-15T09:30:00Z",
      "completed_at": "2024-01-15T09:33:00Z"
    }
  ]
}
```

### GET /backtest/{id}/status

Get backtest status.

**Path Parameters**:
- `id` (string, required): Backtest ID

**Response**:
```json
{
  "success": true,
  "data": {
    "backtest_id": "uuid-string",
    "status": "running",
    "progress_pct": 45.5,
    "current_date": "2022-06-15T00:00:00Z",
    "message": "Processing 2022-06-15",
    "started_at": "2024-01-15T09:30:00Z",
    "completed_at": null
  }
}
```

### GET /backtest/{id}/results

Get backtest results.

**Path Parameters**:
- `id` (string, required): Backtest ID

**Response**:
```json
{
  "success": true,
  "data": {
    "backtest_id": "uuid-string",
    "strategy_id": "uuid-string",
    "metrics": {
      "total_return": 0.125,
      "annualized_return": 0.042,
      "max_drawdown": 0.038,
      "sharpe_ratio": 1.35,
      "sortino_ratio": 1.85,
      "calmar_ratio": 1.10,
      "volatility": 0.028,
      "win_rate": 0.58,
      "profit_factor": 1.65,
      "avg_trade": 125.50,
      "total_trades": 156,
      "winning_trades": 90,
      "losing_trades": 66
    },
    "equity_curve": [
      {"timestamp": "2020-01-01T00:00:00Z", "equity": 100000.0},
      {"timestamp": "2020-01-02T00:00:00Z", "equity": 100150.0}
    ],
    "trades": [...],
    "daily_returns": [...],
    "monthly_returns": [...]
  }
}
```

---

## Portfolio

### POST /portfolio/analyze

Analyze portfolio configuration.

**Request**:
```json
{
  "asset_allocation": {
    "forex_majors": 0.40,
    "index_cfds": 0.30,
    "gold_commodities": 0.20,
    "crypto_bluechips": 0.10
  }
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "analysis": {
      "current_allocation": {...},
      "risk_score": 0.45,
      "diversification_index": 0.72,
      "concentration_risk": "low"
    },
    "recommendations": [
      "Consider reducing forex exposure by 5%",
      "Add emerging market index for diversification"
    ]
  }
}
```

### POST /portfolio/rebalance/check

Check if portfolio needs rebalancing.

**Request**:
```json
{
  "target_weights": {
    "forex_majors": 0.40,
    "index_cfds": 0.30,
    "gold_commodities": 0.20,
    "crypto_bluechips": 0.10
  },
  "current_weights": {
    "forex_majors": 0.42,
    "index_cfds": 0.28,
    "gold_commodities": 0.20,
    "crypto_bluechips": 0.10
  },
  "rebalance_threshold": 3.0
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "needs_rebalance": true,
    "threshold": 3.0,
    "deviations": {
      "forex_majors": 2.0,
      "index_cfds": 2.0
    },
    "triggered_by": ["forex_majors", "index_cfds"]
  }
}
```

---

## Risk Management

### POST /risk/simulate

Run Monte Carlo simulation.

**Request**:
```json
{
  "simulation_runs": 10000,
  "confidence_level": 0.95,
  "expected_return": 0.08,
  "volatility": 0.12,
  "time_horizon": 252,
  "initial_capital": 100000
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "simulation_runs": 10000,
    "confidence_level": 0.95,
    "results": {
      "expected_return_1y": 0.085,
      "expected_return_5y": 0.52,
      "max_drawdown_p95": 0.048,
      "max_drawdown_p99": 0.082,
      "probability_of_positive_return": 0.78,
      "probability_of_target_return": 0.62,
      "value_at_risk_95": 0.035,
      "value_at_risk_99": 0.058
    },
    "path_percentiles": {
      "p5": -0.12,
      "p25": 0.02,
      "p50": 0.095,
      "p75": 0.18,
      "p95": 0.35
    }
  },
  "message": "Simulation completed with 10,000 runs"
}
```

### POST /risk/stress-test

Run stress test scenarios.

**Request**:
```json
{
  "scenarios": [
    "2008_financial_crisis",
    "covid_crash",
    "taper_tantrum"
  ],
  "portfolio_value": 100000,
  "portfolio_volatility": 0.12
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "scenarios_tested": ["2008_financial_crisis", "covid_crash"],
    "results": {
      "2008_financial_crisis": {
        "max_loss": -0.125,
        "recovery_days": 180,
        "survival_probability": 0.95,
        "breaches_risk_limit": false
      },
      "covid_crash": {
        "max_loss": -0.085,
        "recovery_days": 90,
        "survival_probability": 0.98,
        "breaches_risk_limit": false
      }
    },
    "overall_resilience": "high"
  },
  "message": "Stress test completed for 2 scenarios"
}
```

### POST /risk/budget/calculate

Calculate dynamic risk budget allocation.

**Request**:
```json
{
  "total_risk_budget": 0.05,
  "asset_allocation": {
    "forex_majors": 0.40,
    "index_cfds": 0.30,
    "gold_commodities": 0.20,
    "crypto_bluechips": 0.10
  }
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "total_risk_budget": 0.05,
    "risk_allocation_by_asset": {
      "forex_majors": 0.017,
      "index_cfds": 0.0128,
      "gold_commodities": 0.0085,
      "crypto_bluechips": 0.0042
    },
    "diversification_benefit": 0.15,
    "portfolio_var_95": 0.035
  }
}
```

---

## Error Handling

All errors follow this format:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input parameters",
    "field": "asset_allocation",
    "details": {
      "total_weight": 1.10,
      "expected": 1.00
    }
  },
  "timestamp": "2024-01-15T09:30:00Z"
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Input validation failed |
| `NOT_FOUND` | 404 | Resource not found |
| `INTERNAL_ERROR` | 500 | Server internal error |
| `STRATEGY_ERROR` | 400 | Strategy execution failed |
| `RISK_BREACH` | 400 | Risk limit exceeded |

---

## Rate Limiting

Production deployments should implement rate limiting:

- **Default**: 100 requests per minute per IP
- **Backtest**: 5 concurrent backtests per user
- **Simulation**: Max 100,000 simulation runs per request

---

## WebSocket (Future)

Real-time data streaming (planned):

```
ws://localhost:8000/ws/market-data
ws://localhost:8000/ws/trade-updates
```

---

## SDK Examples

### Python

```python
from ist.api.client import StrategyClient

client = StrategyClient("http://localhost:8000")

# Create strategy
result = client.create_strategy(
    name="My Strategy",
    config=profile
)

# Run backtest
backtest = client.run_backtest(
    strategy_id=result["data"]["id"],
    start_date=date(2020, 1, 1),
    end_date=date(2023, 12, 31)
)
```

### cURL

```bash
# Health check
curl http://localhost:8000/health

# Create strategy
curl -X POST http://localhost:8000/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Strategy",
    "asset_allocation": {"forex_majors": 1.0},
    "nodes": [],
    "connections": []
  }'

# Run backtest
curl -X POST http://localhost:8000/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "xxx",
    "start_date": "2020-01-01",
    "end_date": "2023-12-31"
  }'
```

---

**Last Updated**: 2024-01-15
