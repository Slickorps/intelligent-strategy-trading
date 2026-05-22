# Intelligent Strategy Trading

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)
![Go](https://img.shields.io/badge/go-1.21+-00ADD8.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6.svg)
![HTML](https://img.shields.io/badge/HTML-5-E34F26.svg)
![CSS](https://img.shields.io/badge/CSS-3-1572B6.svg)
![Shell](https://img.shields.io/badge/Shell-Bash-4EAA25.svg)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)
![License](https://img.shields.io/badge/license-MIT-yellow.svg)
![Status](https://img.shields.io/badge/status-beta-orange.svg)

> **Professional Multi-Asset Trading Platform with Visual Strategy Orchestration**

A quantitative trading infrastructure engineered for portfolio management and cyclical asset allocation. Unlike high-frequency systems, this platform emphasizes **multi-factor modeling**, **dynamic risk budgeting**, and **path simulation** to achieve sustainable returns within controlled risk parameters.

## Key Features

- **Visual Strategy Logic**: Node-based strategy builder inspired by dataflow programming paradigms
- **Multi-Factor Modeling**: Comprehensive factor analysis including momentum, volatility, and cross-asset correlation
- **Dynamic Risk Budget**: Automatic rebalancing with configurable deviation thresholds
- **Monte Carlo Simulation**: 10,000+ path simulations for drawdown probability analysis
- **Stress Testing**: Historical scenario replay (2008 crisis, COVID crash)
- **Multi-Asset Support**: Forex majors, index CFDs, commodities, crypto bluechips
- **AI/Quant Integration**: Native LangChain tools for LLM-powered analysis

## Quick Start

Install the package:

```bash
pip install -e ".[all]"
```

Start the API server:

```bash
uvicorn ist.api.main:app --reload
```

Execute your first backtest in 10 lines:

```python
from ist.api.client import StrategyClient

client = StrategyClient("http://localhost:8000")

# Load conservative wealth preservation profile
profile = client.load_profile("conservative")

# Run backtest on 4 years of data
result = client.backtest.run(
    strategy_config=profile,
    start_date="2020-01-01",
    end_date="2023-12-31"
)

print(f"Total Return: {result.total_return:.2%}")
print(f"Max Drawdown: {result.max_drawdown:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
```

## Supported Markets & Data Schema

All market data follows a standardized OHLCV format:

| Asset Class | Symbol Format | Example | Description |
|-------------|---------------|---------|-------------|
| **Forex Majors** | `CCYCCY` | `EURUSD` | Major currency pairs |
| **Index CFDs** | `XXX000` | `SPX500` | Stock index contracts |
| **Commodities** | `XXXUSD` | `XAUUSD` | Precious metals, energy |
| **Crypto** | `CCCUSD` | `BTCUSD` | Bluechip cryptocurrencies |

### Standard API Response Format

```json
{
  "timestamp": "2024-01-15T09:30:00Z",
  "symbol": "EURUSD",
  "open": 1.0850,
  "high": 1.0865,
  "low": 1.0845,
  "close": 1.0860,
  "volume": 15420
}
```

## Configuration Templates

Define your personalized asset allocation via JSON configuration:

```json
{
  "profile_name": "Long-term Wealth Growth",
  "target_annual_return": "8% - 12%",
  "max_drawdown_limit": "5%",
  "asset_allocation": {
    "forex_majors": 0.40,
    "gold_commodities": 0.20,
    "index_cfds": 0.30,
    "crypto_bluechips": 0.10
  },
  "risk_management": {
    "dynamic_rebalancing": true,
    "rebalance_threshold": "3%",
    "path_simulation_runs": 10000,
    "stress_test_scenario": "2008_financial_crisis_replayed"
  },
  "strategy_nodes": {
    "version": "1.0",
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
        "id": "sma_200",
        "type": "IndicatorNode",
        "params": {"indicator": "SMA", "period": 200}
      },
      {
        "id": "golden_cross",
        "type": "ConditionNode",
        "params": {"condition": "cross_above"}
      },
      {
        "id": "long_entry",
        "type": "ActionNode",
        "params": {"action": "buy", "size_pct": 0.05}
      }
    ],
    "connections": [
      {"from": "data_source", "to": "sma_50"},
      {"from": "data_source", "to": "sma_200"},
      {"from": "sma_50", "to": "golden_cross"},
      {"from": "sma_200", "to": "golden_cross"},
      {"from": "golden_cross", "to": "long_entry"}
    ]
  }
}
```

**Interpretation**: Allocates 40% to forex majors with dynamic rebalancing enabled. System validates through 10,000 path simulations to ensure max drawdown remains within 5% limit.

## AI & Quantitative Integration

The platform exposes LangChain-compatible tools for LLM integration:

```python
from langchain.agents import AgentExecutor, create_openai_tools_agent
from ist.integration.langchain_tools import (
    GetMarketDataTool,
    RunBacktestTool,
    GetPortfolioTool,
    AnalyzeRiskTool
)

tools = [
    GetMarketDataTool(),
    RunBacktestTool(),
    GetPortfolioTool(),
    AnalyzeRiskTool()
]

# Create agent for autonomous analysis
agent = create_openai_tools_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)

response = executor.invoke({
    "input": "Analyze current EURUSD trend and backtest a momentum strategy"
})
```

### Vector Database Integration

Store and query strategy performance, market regimes, and research notes:

```python
from ist.integration.vector_store import StrategyMemory

memory = StrategyMemory()
memory.store_strategy_result(
    strategy_id="trend_following_v1",
    result=backtest_result,
    metadata={"market_regime": "trending", "sharpe": 1.85}
)

# Query similar successful strategies
similar = memory.query_similar_strategies(
    target_sharpe=1.80,
    n_results=5
)
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   API Layer     │────▶│  Strategy Engine│────▶│  Visualization  │
│   (FastAPI)     │     │  (Node Graph)   │     │  (Flowchart)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   Risk Engine   │◀───▶│  Backtest Engine│
│ (Monte Carlo)   │     │ (Event-driven)  │
└─────────────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   Data Layer    │     │  Execution Layer│
│ (Provider API)  │     │ (Paper/Live)    │
└─────────────────┘     └─────────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/strategies` | GET/POST | List/create strategies |
| `/strategies/{id}/flowchart` | GET | Get strategy visualization data |
| `/strategies/{id}/backtest` | POST | Run backtest |
| `/backtest/{id}/results` | GET | Retrieve backtest results |
| `/portfolio/analyze` | POST | Portfolio risk analysis |
| `/risk/simulate` | POST | Monte Carlo simulation |

Full API documentation available at `/docs` (Swagger UI) when server is running.

## Development

```bash
# Clone repository
git clone https://github.com/yourusername/intelligent-strategy-trading.git
cd intelligent-strategy-trading

# Install with development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --cov=ist

# Type checking
mypy src/

# Linting
ruff check src/
ruff format src/
```

## Roadmap

- [x] Core API foundation
- [x] Visual strategy nodes
- [x] Event-driven backtest engine
- [x] Multi-factor risk modeling
- [x] Monte Carlo path simulation
- [ ] Live broker integrations (Interactive Brokers, OANDA)
- [ ] WebSocket real-time data
- [ ] Web-based visual editor
- [ ] Machine learning factor integration

## Docker Deployment

```bash
# Quick start
docker-compose up -d

# With PostgreSQL and Redis
docker-compose --profile production up -d

# Access API
curl http://localhost:8000/health
```

See [docs/deployment.md](docs/deployment.md) for detailed deployment options.

## License

MIT License - see [LICENSE](LICENSE) file.

---

**Disclaimer**: This software is for educational and research purposes. Trading financial instruments carries significant risk. Past performance does not guarantee future results.
