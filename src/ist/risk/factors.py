"""Multi-factor model engine."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from ist.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FactorResult:
    """Result of factor calculation."""
    
    name: str
    value: float
    score: float  # Normalized score 0-100
    direction: str  # "positive", "negative", "neutral"
    weight: float
    confidence: float  # 0-1 confidence level


class BaseFactor(ABC):
    """Abstract base class for risk factors."""
    
    def __init__(self, name: str, weight: float = 1.0) -> None:
        self.name = name
        self.weight = weight
        self._history: list[float] = []
    
    @abstractmethod
    def calculate(
        self,
        prices: list[float],
        volumes: Optional[list[float]] = None
    ) -> FactorResult:
        """Calculate factor value.
        
        Args:
            prices: Historical price series
            volumes: Optional volume series
            
        Returns:
            Factor result with score and direction
        """
        pass
    
    def reset(self) -> None:
        """Reset factor history."""
        self._history.clear()


class MomentumFactor(BaseFactor):
    """Price momentum factor.
    
    Measures price trend strength over various lookback periods.
    """
    
    def __init__(
        self,
        short_period: int = 20,
        medium_period: int = 60,
        long_period: int = 120,
        **kwargs
    ) -> None:
        super().__init__("momentum", kwargs.get("weight", 0.30))
        self.short_period = short_period
        self.medium_period = medium_period
        self.long_period = long_period
    
    def calculate(
        self,
        prices: list[float],
        volumes: Optional[list[float]] = None
    ) -> FactorResult:
        """Calculate momentum score."""
        if len(prices) < self.long_period:
            return FactorResult(
                name=self.name,
                value=0.0,
                score=50.0,
                direction="neutral",
                weight=self.weight,
                confidence=0.0
            )
        
        current = prices[-1]
        
        # Calculate returns over different periods
        short_ret = (current / prices[-self.short_period] - 1) * 100
        medium_ret = (current / prices[-self.medium_period] - 1) * 100
        long_ret = (current / prices[-self.long_period] - 1) * 100
        
        # Weighted composite momentum
        momentum = (
            short_ret * 0.5 +
            medium_ret * 0.3 +
            long_ret * 0.2
        )
        
        # Normalize to 0-100 score
        # Typical momentum ranges from -20% to +20%
        score = 50 + (momentum / 20) * 50
        score = max(0, min(100, score))
        
        # Determine direction
        if score > 60:
            direction = "positive"
        elif score < 40:
            direction = "negative"
        else:
            direction = "neutral"
        
        return FactorResult(
            name=self.name,
            value=momentum,
            score=score,
            direction=direction,
            weight=self.weight,
            confidence=min(1.0, len(prices) / self.long_period)
        )


class VolatilityFactor(BaseFactor):
    """Volatility regime factor.
    
    Detects high/low volatility periods for risk adjustment.
    """
    
    def __init__(self, period: int = 20, **kwargs) -> None:
        super().__init__("volatility", kwargs.get("weight", 0.25))
        self.period = period
    
    def calculate(
        self,
        prices: list[float],
        volumes: Optional[list[float]] = None
    ) -> FactorResult:
        """Calculate volatility regime score."""
        if len(prices) < self.period + 1:
            return FactorResult(
                name=self.name,
                value=0.0,
                score=50.0,
                direction="neutral",
                weight=self.weight,
                confidence=0.0
            )
        
        # Calculate returns
        returns = [
            (prices[i] / prices[i-1] - 1) * 100
            for i in range(1, len(prices))
        ][-self.period:]
        
        # Calculate volatility (standard deviation)
        volatility = np.std(returns) * np.sqrt(252)  # Annualized
        
        # Compare to historical average
        hist_vol = np.std(returns) if len(returns) > 1 else 0.1
        
        # Score: low volatility = positive (good for entry)
        # High volatility = negative (risk-off)
        # Target volatility around 10-15%
        target_vol = 12.0
        
        if volatility < target_vol * 0.7:
            score = 70 + (target_vol * 0.7 - volatility) / target_vol * 30
            direction = "positive"  # Low vol = opportunity
        elif volatility > target_vol * 1.5:
            score = 30 - (volatility - target_vol * 1.5) / target_vol * 30
            direction = "negative"  # High vol = risk
        else:
            score = 50
            direction = "neutral"
        
        score = max(0, min(100, score))
        
        return FactorResult(
            name=self.name,
            value=volatility,
            score=score,
            direction=direction,
            weight=self.weight,
            confidence=min(1.0, len(prices) / (self.period * 2))
        )


class CorrelationFactor(BaseFactor):
    """Cross-asset correlation factor.
    
    Measures diversification benefit across assets.
    """
    
    def __init__(self, period: int = 60, **kwargs) -> None:
        super().__init__("correlation", kwargs.get("weight", 0.20))
        self.period = period
    
    def calculate(
        self,
        prices: list[float],
        volumes: Optional[list[float]] = None
    ) -> FactorResult:
        """Calculate correlation-based score."""
        # This factor requires multiple asset price series
        # Simplified: use volume-price correlation as proxy
        
        if not volumes or len(volumes) < self.period:
            return FactorResult(
                name=self.name,
                value=0.0,
                score=50.0,
                direction="neutral",
                weight=self.weight,
                confidence=0.0
            )
        
        # Calculate volume-price correlation
        returns = np.diff(np.log(prices[-self.period:]))
        volume_changes = np.diff(np.log(volumes[-self.period:]))
        
        if len(returns) > 0 and len(volume_changes) > 0:
            correlation = np.corrcoef(returns, volume_changes)[0, 1]
        else:
            correlation = 0.0
        
        # High volume-price correlation often precedes moves
        # But for diversification, we want assets with low correlation
        score = 50 - abs(correlation) * 50  # Lower correlation = higher score
        
        direction = "positive" if score > 60 else "neutral"
        
        return FactorResult(
            name=self.name,
            value=correlation,
            score=score,
            direction=direction,
            weight=self.weight,
            confidence=0.5
        )


class TrendFactor(BaseFactor):
    """Trend alignment factor using moving averages."""
    
    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        **kwargs
    ) -> None:
        super().__init__("trend", kwargs.get("weight", 0.25))
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def calculate(
        self,
        prices: list[float],
        volumes: Optional[list[float]] = None
    ) -> FactorResult:
        """Calculate trend alignment score."""
        if len(prices) < self.slow_period:
            return FactorResult(
                name=self.name,
                value=0.0,
                score=50.0,
                direction="neutral",
                weight=self.weight,
                confidence=0.0
            )
        
        # Calculate moving averages
        fast_ma = np.mean(prices[-self.fast_period:])
        slow_ma = np.mean(prices[-self.slow_period:])
        
        # Trend strength
        price_to_fast = (prices[-1] / fast_ma - 1) * 100
        fast_to_slow = (fast_ma / slow_ma - 1) * 100
        
        # Alignment score
        if price_to_fast > 0 and fast_to_slow > 0:
            # Uptrend alignment
            alignment = price_to_fast + fast_to_slow
            score = 50 + min(50, alignment)
            direction = "positive"
        elif price_to_fast < 0 and fast_to_slow < 0:
            # Downtrend alignment
            alignment = abs(price_to_fast) + abs(fast_to_slow)
            score = 50 - min(50, alignment)
            direction = "negative"
        else:
            # Mixed signals
            score = 50
            direction = "neutral"
        
        score = max(0, min(100, score))
        
        return FactorResult(
            name=self.name,
            value=fast_to_slow,
            score=score,
            direction=direction,
            weight=self.weight,
            confidence=min(1.0, len(prices) / self.slow_period)
        )


class MultiFactorModel:
    """Multi-factor model for signal synthesis.
    
    Combines multiple factors into a composite signal.
    """
    
    def __init__(self, factors: Optional[list[BaseFactor]] = None) -> None:
        self.factors = factors or [
            MomentumFactor(),
            VolatilityFactor(),
            CorrelationFactor(),
            TrendFactor()
        ]
    
    def analyze(
        self,
        prices: dict[str, list[float]],
        volumes: Optional[dict[str, list[float]]] = None
    ) -> dict[str, Any]:
        """Analyze assets with all factors.
        
        Args:
            prices: Dictionary of symbol to price history
            volumes: Optional dictionary of symbol to volume history
            
        Returns:
            Dictionary with factor results and composite scores
        """
        results = {}
        
        for symbol, price_history in prices.items():
            vol_history = volumes.get(symbol) if volumes else None
            
            # Calculate all factors
            factor_results = []
            for factor in self.factors:
                result = factor.calculate(price_history, vol_history)
                factor_results.append(result)
            
            # Calculate weighted composite score
            total_weight = sum(r.weight for r in factor_results)
            if total_weight > 0:
                composite_score = sum(
                    r.score * r.weight for r in factor_results
                ) / total_weight
                
                composite_confidence = sum(
                    r.confidence * r.weight for r in factor_results
                ) / total_weight
            else:
                composite_score = 50.0
                composite_confidence = 0.0
            
            # Determine overall direction
            positive_factors = sum(1 for r in factor_results if r.direction == "positive")
            negative_factors = sum(1 for r in factor_results if r.direction == "negative")
            
            if positive_factors > negative_factors + 1:
                overall_direction = "positive"
            elif negative_factors > positive_factors + 1:
                overall_direction = "negative"
            else:
                overall_direction = "neutral"
            
            results[symbol] = {
                "factors": {
                    r.name: {
                        "value": r.value,
                        "score": r.score,
                        "direction": r.direction,
                        "weight": r.weight,
                        "confidence": r.confidence
                    }
                    for r in factor_results
                },
                "composite_score": composite_score,
                "composite_confidence": composite_confidence,
                "direction": overall_direction,
                "recommendation": self._generate_recommendation(
                    composite_score, overall_direction, composite_confidence
                )
            }
        
        return results
    
    def _generate_recommendation(
        self,
        score: float,
        direction: str,
        confidence: float
    ) -> str:
        """Generate trading recommendation."""
        if confidence < 0.3:
            return "insufficient_data"
        
        if direction == "positive" and score > 65:
            return "strong_buy"
        elif direction == "positive" and score > 55:
            return "buy"
        elif direction == "negative" and score < 35:
            return "strong_sell"
        elif direction == "negative" and score < 45:
            return "sell"
        else:
            return "hold"
    
    def reset(self) -> None:
        """Reset all factors."""
        for factor in self.factors:
            factor.reset()
