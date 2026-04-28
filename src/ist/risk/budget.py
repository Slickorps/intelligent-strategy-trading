"""Risk budget and allocation management."""

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from ist.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RiskAllocation:
    """Risk budget allocation for an asset."""
    
    symbol: str
    weight: float  # Portfolio weight
    risk_budget: float  # Risk budget allocation
    current_risk: float  # Current risk estimate
    utilization: float = 0.0  # Current utilization of budget
    
    @property
    def is_over_budget(self) -> bool:
        """Check if risk exceeds budget."""
        return self.current_risk > self.risk_budget


@dataclass
class RebalanceRule:
    """Rebalancing rule configuration."""
    
    enabled: bool = True
    threshold_pct: float = 3.0  # Deviation threshold to trigger
    frequency: str = "daily"  # daily, weekly, monthly
    tolerance_pct: float = 0.5  # Minimum trade size
    max_turnover_pct: float = 20.0  # Maximum turnover per rebalance


class RiskBudget:
    """Dynamic risk budget management.
    
    Implements risk parity and dynamic rebalancing strategies.
    """
    
    def __init__(
        self,
        total_risk_budget: float = 0.05,  # 5% max portfolio risk
        diversification_factor: float = 0.85,
        rebalancing: Optional[RebalanceRule] = None
    ) -> None:
        self.total_risk_budget = total_risk_budget
        self.diversification_factor = diversification_factor
        self.rebalancing = rebalancing or RebalanceRule()
        
        self._allocations: dict[str, RiskAllocation] = {}
        self._target_weights: dict[str, float] = {}
    
    def set_target_weights(self, weights: dict[str, float]) -> None:
        """Set target asset allocation weights."""
        total = sum(weights.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        
        self._target_weights = weights.copy()
        self._calculate_risk_budgets()
    
    def _calculate_risk_budgets(self) -> None:
        """Calculate risk budgets based on target weights."""
        if not self._target_weights:
            return
        
        # Apply diversification benefit
        effective_budget = self.total_risk_budget * self.diversification_factor
        
        total_weight = sum(self._target_weights.values())
        
        for symbol, weight in self._target_weights.items():
            # Allocate risk budget proportionally by weight
            # with consideration for concentration
            concentration_penalty = 1.0 + (weight - 0.25) * 0.5 if weight > 0.25 else 1.0
            
            risk_budget = (
                effective_budget * 
                (weight / total_weight) * 
                concentration_penalty
            )
            
            self._allocations[symbol] = RiskAllocation(
                symbol=symbol,
                weight=weight,
                risk_budget=risk_budget,
                current_risk=0.0
            )
    
    def update_risk_estimates(
        self,
        volatilities: dict[str, float],
        correlations: Optional[np.ndarray] = None
    ) -> None:
        """Update current risk estimates for assets."""
        if correlations is not None:
            # Calculate portfolio risk using covariance matrix
            symbols = list(self._allocations.keys())
            weights = np.array([self._allocations[s].weight for s in symbols])
            
            # Build covariance matrix from volatilities and correlations
            vols = np.array([volatilities.get(s, 0.1) for s in symbols])
            cov_matrix = np.outer(vols, vols) * correlations
            
            portfolio_var = np.dot(weights.T, np.dot(cov_matrix, weights))
            portfolio_risk = np.sqrt(portfolio_var)
            
            # Allocate portfolio risk to individual assets (marginal contribution)
            for i, symbol in enumerate(symbols):
                if symbol in self._allocations:
                    marginal_risk = np.dot(cov_matrix[i], weights) / portfolio_risk
                    self._allocations[symbol].current_risk = marginal_risk * portfolio_risk
        else:
            # Simple individual risk estimates
            for symbol, vol in volatilities.items():
                if symbol in self._allocations:
                    self._allocations[symbol].current_risk = vol
        
        # Update utilization
        for alloc in self._allocations.values():
            alloc.utilization = (
                alloc.current_risk / alloc.risk_budget 
                if alloc.risk_budget > 0 else 0.0
            )
    
    def check_rebalance_needed(
        self,
        current_weights: dict[str, float]
    ) -> tuple[bool, dict[str, float], list[str]]:
        """Check if rebalancing is needed.
        
        Returns:
            Tuple of (needs_rebalance, deviations, triggered_by)
        """
        if not self.rebalancing.enabled:
            return False, {}, []
        
        deviations = {}
        triggered = []
        
        # Check weight deviations
        for symbol, target in self._target_weights.items():
            current = current_weights.get(symbol, 0.0)
            deviation = abs(current - target) * 100  # As percentage
            deviations[symbol] = deviation
            
            if deviation > self.rebalancing.threshold_pct:
                triggered.append(symbol)
        
        # Check risk budget deviations
        for symbol, alloc in self._allocations.items():
            if alloc.utilization > 1.0:
                triggered.append(f"{symbol}_risk")
        
        needs_rebalance = len(triggered) > 0
        
        return needs_rebalance, deviations, triggered
    
    def calculate_rebalance_trades(
        self,
        current_weights: dict[str, float],
        portfolio_value: float
    ) -> list[dict[str, Any]]:
        """Calculate trades needed for rebalancing."""
        trades = []
        total_turnover = 0.0
        
        # Calculate required changes
        for symbol, target in self._target_weights.items():
            current = current_weights.get(symbol, 0.0)
            delta = target - current
            
            # Skip if below tolerance
            if abs(delta) < self.rebalancing.tolerance_pct / 100:
                continue
            
            trade_value = delta * portfolio_value
            
            trades.append({
                "symbol": symbol,
                "side": "buy" if delta > 0 else "sell",
                "target_weight": target,
                "current_weight": current,
                "delta": delta,
                "trade_value": abs(trade_value)
            })
            
            total_turnover += abs(delta)
        
        # Check turnover limit
        if total_turnover > self.rebalancing.max_turnover_pct / 100:
            # Scale down trades proportionally
            scale = (self.rebalancing.max_turnover_pct / 100) / total_turnover
            for trade in trades:
                trade["delta"] *= scale
                trade["trade_value"] *= scale
        
        return trades
    
    def get_portfolio_risk_summary(self) -> dict[str, Any]:
        """Get summary of portfolio risk."""
        if not self._allocations:
            return {}
        
        total_utilization = sum(
            alloc.utilization for alloc in self._allocations.values()
        ) / len(self._allocations) if self._allocations else 0
        
        over_budget = [
            alloc.symbol for alloc in self._allocations.values()
            if alloc.is_over_budget
        ]
        
        return {
            "total_risk_budget": self.total_risk_budget,
            "diversification_benefit": 1.0 - self.diversification_factor,
            "effective_budget": self.total_risk_budget * self.diversification_factor,
            "average_utilization": total_utilization,
            "assets_over_budget": over_budget,
            "num_assets": len(self._allocations),
            "allocations": {
                symbol: {
                    "weight": alloc.weight,
                    "risk_budget": alloc.risk_budget,
                    "current_risk": alloc.current_risk,
                    "utilization": alloc.utilization
                }
                for symbol, alloc in self._allocations.items()
            }
        }


class RiskParityAllocator:
    """Risk parity portfolio allocator.
    
    Allocates capital such that each asset contributes
    equally to portfolio risk.
    """
    
    def __init__(self, target_risk: float = 0.10) -> None:
        self.target_risk = target_risk
    
    def calculate_weights(
        self,
        volatilities: dict[str, float],
        correlations: Optional[np.ndarray] = None
    ) -> dict[str, float]:
        """Calculate risk parity weights.
        
        Args:
            volatilities: Asset volatilities (annualized)
            correlations: Correlation matrix
            
        Returns:
            Dictionary of symbol to weight
        """
        symbols = list(volatilities.keys())
        n = len(symbols)
        
        if n == 0:
            return {}
        
        if n == 1:
            return {symbols[0]: 1.0}
        
        # Build covariance matrix
        vols = np.array([volatilities[s] for s in symbols])
        
        if correlations is not None:
            cov = np.outer(vols, vols) * correlations
        else:
            cov = np.diag(vols ** 2)
        
        # Risk parity optimization (simplified)
        # Target: equal risk contribution from each asset
        # RC_i = w_i * (Cov * w)_i / sqrt(w' * Cov * w) = 1/n
        
        # Iterative approach
        weights = np.ones(n) / n  # Start with equal weights
        
        for _ in range(100):  # Max iterations
            # Calculate portfolio variance
            port_var = np.dot(weights.T, np.dot(cov, weights))
            port_vol = np.sqrt(port_var)
            
            # Calculate marginal contributions
            marginal = np.dot(cov, weights) / port_vol
            
            # Calculate risk contributions
            risk_contrib = weights * marginal
            
            # Target: equal contributions
            target_contrib = port_vol / n
            
            # Update weights
            new_weights = weights * target_contrib / (risk_contrib + 1e-10)
            new_weights = new_weights / np.sum(new_weights)  # Normalize
            
            # Check convergence
            if np.max(np.abs(new_weights - weights)) < 1e-6:
                break
            
            weights = new_weights
        
        return {symbols[i]: float(weights[i]) for i in range(n)}
