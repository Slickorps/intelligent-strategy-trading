# Intelligent Strategy Trading

Professional quantitative trading platform with visual strategy orchestration and multi-asset support.

## Overview

IST (Intelligent Strategy Trading) is a production-grade algorithmic trading platform supporting:

- **Visual Strategy Builder**: Node-graph based strategy construction
- **Multi-Asset Trading**: Forex, Crypto, CFDs, Stocks
- **Event-Driven Backtesting**: Realistic backtesting with slippage and commission
- **Multi-Factor Risk Models**: Monte Carlo simulation, VaR, stress testing
- **ML Factor Engine**: scikit-learn powered machine learning integration
- **Broker Integration**: IB, OANDA, Alpaca adapters

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Core Engine | Python 3.10+ (FastAPI, Pydantic, Pandas) |
| High-Performance Data | Rust (PyO3) |
| Monitoring Service | Go |
| Dashboard | TypeScript + HTML + CSS |
| Database | PostgreSQL |
| Cache | Redis |
| Infrastructure | Docker, Kubernetes, Terraform |
| Monitoring | Prometheus + Grafana |
| CI/CD | GitHub Actions |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Slickorps/intelligent-strategy-trading.git
cd intelligent-strategy-trading

# Install with pip
pip install -e ".[all]"

# Run the API server
uvicorn src.ist.api.main:app --reload

# Or use Docker
docker-compose up -d
```

## API Endpoints

See the [API Reference](api.md) for full endpoint documentation.

## Documentation

- [API Reference](api.md) — REST API endpoints and schemas
- [Configuration](configuration.md) — System configuration and environment variables
- [Deployment](deployment.md) — Production deployment guide
- [Extension Guide](extension.md) — Building custom indicators and strategies
