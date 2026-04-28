"""Python client for IST API."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import httpx


class StrategyClient:
    """Client for interacting with IST API."""
    
    def __init__(
        self, 
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
    
    def _request(
        self, 
        method: str, 
        path: str, 
        **kwargs: Any
    ) -> dict:
        """Make HTTP request and handle response."""
        url = f"{self.base_url}{path}"
        response = self._client.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def health_check(self) -> dict:
        """Check API health."""
        return self._request("GET", "/health")
    
    def load_profile(self, profile_name: str) -> dict[str, Any]:
        """Load strategy profile from config file."""
        config_path = Path(f"config/profiles/{profile_name}.json")
        
        if not config_path.exists():
            raise FileNotFoundError(f"Profile not found: {config_path}")
        
        with open(config_path) as f:
            return json.load(f)
    
    def create_strategy(
        self, 
        name: str,
        config: dict[str, Any],
        description: Optional[str] = None
    ) -> dict:
        """Create a new strategy."""
        # Build nodes from config
        nodes_config = config.get("strategy_nodes", {})
        
        payload = {
            "name": name,
            "description": description,
            "profile_name": config.get("profile_name"),
            "target_annual_return": config.get("target_annual_return"),
            "max_drawdown_limit": config.get("max_drawdown_limit"),
            "asset_allocation": config.get("asset_allocation"),
            "risk_management": config.get("risk_management"),
            "nodes": [
                {
                    "id": n["id"],
                    "type": n["type"],
                    "params": n.get("params", {}),
                    "position": n.get("position")
                }
                for n in nodes_config.get("nodes", [])
            ],
            "connections": [
                {
                    "from": c["from"],
                    "to": c["to"]
                }
                for c in nodes_config.get("connections", [])
            ]
        }
        
        return self._request("POST", "/strategies", json=payload)
    
    def list_strategies(self) -> dict:
        """List all strategies."""
        return self._request("GET", "/strategies")
    
    def get_strategy(self, strategy_id: str) -> dict:
        """Get strategy details."""
        return self._request("GET", f"/strategies/{strategy_id}")
    
    def get_strategy_flowchart(self, strategy_id: str) -> dict:
        """Get strategy flowchart data."""
        return self._request("GET", f"/strategies/{strategy_id}/flowchart")
    
    def delete_strategy(self, strategy_id: str) -> dict:
        """Delete a strategy."""
        return self._request("DELETE", f"/strategies/{strategy_id}")
    
    def run_backtest(
        self,
        strategy_id: str,
        start_date: date,
        end_date: date,
        initial_capital: float = 100000.0,
        symbols: Optional[list[str]] = None,
        timeframe: str = "1h"
    ) -> dict:
        """Run a backtest for a strategy."""
        payload = {
            "strategy_id": strategy_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "initial_capital": initial_capital,
            "symbols": symbols or [],
            "timeframe": timeframe
        }
        
        return self._request("POST", "/backtest/run", json=payload)
    
    def get_backtest_status(self, backtest_id: str) -> dict:
        """Get backtest status."""
        return self._request("GET", f"/backtest/{backtest_id}/status")
    
    def get_backtest_results(self, backtest_id: str) -> dict:
        """Get backtest results."""
        return self._request("GET", f"/backtest/{backtest_id}/results")
    
    def run_simulation(
        self,
        simulation_runs: int = 10000,
        confidence_level: float = 0.95,
        portfolio_config: Optional[dict] = None
    ) -> dict:
        """Run Monte Carlo simulation."""
        payload = {
            "simulation_runs": simulation_runs,
            "confidence_level": confidence_level
        }
        if portfolio_config:
            payload["portfolio_config"] = portfolio_config
        
        return self._request("POST", "/risk/simulate", json=payload)
    
    def run_stress_test(
        self,
        scenarios: list[str],
        portfolio_config: Optional[dict] = None
    ) -> dict:
        """Run stress test scenarios."""
        payload = {"scenarios": scenarios}
        if portfolio_config:
            payload["portfolio_config"] = portfolio_config
        
        return self._request("POST", "/risk/stress-test", json=payload)
    
    def close(self) -> None:
        """Close HTTP client."""
        self._client.close()
    
    def __enter__(self) -> "StrategyClient":
        return self
    
    def __exit__(self, *args: Any) -> None:
        self.close()


# Convenience alias
BacktestRunner = StrategyClient
