"""Moving averages indicators.

This module implements various moving average indicators including
Simple Moving Average (SMA) and Exponential Moving Average (EMA).

Moving averages are fundamental technical indicators that help identify
trends by smoothing price data over a specified period.
"""

import pandas as pd
import numpy as np

from ist.strategy.indicators.base import BaseIndicator, IndicatorInput, IndicatorResult
from ist.core.exceptions import IndicatorError
from ist.core.logging import get_logger

logger = get_logger(__name__)


class SMA(BaseIndicator):
    """Simple Moving Average (SMA).
    
    SMA calculates the arithmetic mean of a given set of prices over a specified
    number of periods. It's one of the most basic and widely used technical indicators.
    
    Formula:
        SMA = (Sum of prices over N periods) / N
    
    Args:
        period: Number of periods for calculation (default: 20)
        
    Example:
        ```python
        sma = SMA(period=20)
        data = IndicatorInput(close=price_series)
        result = sma.calculate(data)
        print(result.values)  # SMA values
        ```
    """
    
    def __init__(self, period: int = 20) -> None:
        """Initialize SMA indicator.
        
        Args:
            period: Number of periods for calculation (must be >= 1)
        """
        if period < 1:
            raise IndicatorError("SMA period must be >= 1")
        
        super().__init__("SMA", {"period": period})
        self.period = period
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate SMA values.
        
        Args:
            data: IndicatorInput containing price data
            
        Returns:
            IndicatorResult with SMA values
            
        Raises:
            IndicatorError: If calculation fails
        """
        try:
            price_series = data.main_series
            
            if not self.validate_input(data):
                raise IndicatorError(f"Insufficient data for SMA calculation. Need at least {self.period} periods")
            
            # Calculate SMA using pandas rolling mean
            sma_values = price_series.rolling(window=self.period, min_periods=1).mean()
            
            # Generate basic trading signals
            signals = self._generate_signals(price_series, sma_values)
            
            logger.debug(f"Calculated SMA({self.period}) for {len(price_series)} data points")
            
            return IndicatorResult(
                values=sma_values,
                signals=signals,
                metadata={"period": self.period, "method": "simple"}
            )
            
        except Exception as e:
            raise IndicatorError(f"SMA calculation failed: {str(e)}")
    
    def validate_input(self, data: IndicatorInput) -> bool:
        """Validate input data for SMA calculation.
        
        Args:
            data: IndicatorInput to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            price_series = data.main_series
            return len(price_series) >= self.period and not price_series.empty
        except Exception:
            return False
    
    def get_min_bars_required(self) -> int:
        """Get minimum bars required for SMA calculation."""
        return self.period
    
    def _generate_signals(self, prices: pd.Series, sma: pd.Series) -> pd.Series:
        """Generate basic trading signals based on SMA crossovers.
        
        Args:
            prices: Original price series
            sma: SMA values
            
        Returns:
            Series with trading signals (1=buy, -1=sell, 0=hold)
        """
        signals = pd.Series(0, index=prices.index)
        
        # Find crossovers
        price_above_sma = prices > sma
        price_below_sma = prices < sma
        
        # Buy signal: price crosses above SMA
        buy_signals = price_above_sma & price_below_sma.shift(1).fillna(False).infer_objects(copy=False)
        
        # Sell signal: price crosses below SMA  
        sell_signals = price_below_sma & price_above_sma.shift(1).fillna(False).infer_objects(copy=False)
        
        signals[buy_signals] = 1
        signals[sell_signals] = -1
        
        return signals


class EMA(BaseIndicator):
    """Exponential Moving Average (EMA).
    
    EMA gives more weight to recent prices, making it more responsive to
    new information compared to SMA. The weighting decreases exponentially
    for older prices.
    
    Formula:
        EMA_today = (Price_today * α) + (EMA_yesterday * (1 - α))
        where α = 2 / (N + 1), N = period
    
    Args:
        period: Number of periods for calculation (default: 20)
        
    Example:
        ```python
        ema = EMA(period=20)
        data = IndicatorInput(close=price_series)
        result = ema.calculate(data)
        print(result.values)  # EMA values
        ```
    """
    
    def __init__(self, period: int = 20) -> None:
        """Initialize EMA indicator.
        
        Args:
            period: Number of periods for calculation (must be >= 1)
        """
        if period < 1:
            raise IndicatorError("EMA period must be >= 1")
        
        super().__init__("EMA", {"period": period})
        self.period = period
        self._alpha = 2.0 / (period + 1)  # Smoothing factor
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate EMA values.
        
        Args:
            data: IndicatorInput containing price data
            
        Returns:
            IndicatorResult with EMA values
            
        Raises:
            IndicatorError: If calculation fails
        """
        try:
            price_series = data.main_series
            
            if not self.validate_input(data):
                raise IndicatorError(f"Insufficient data for EMA calculation. Need at least {self.period} periods")
            
            # Calculate EMA using pandas ewm
            ema_values = price_series.ewm(alpha=self._alpha, adjust=False).mean()
            
            # Generate basic trading signals
            signals = self._generate_signals(price_series, ema_values)
            
            logger.debug(f"Calculated EMA({self.period}) for {len(price_series)} data points")
            
            return IndicatorResult(
                values=ema_values,
                signals=signals,
                metadata={"period": self.period, "alpha": self._alpha, "method": "exponential"}
            )
            
        except Exception as e:
            raise IndicatorError(f"EMA calculation failed: {str(e)}")
    
    def validate_input(self, data: IndicatorInput) -> bool:
        """Validate input data for EMA calculation.
        
        Args:
            data: IndicatorInput to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            price_series = data.main_series
            return len(price_series) >= self.period and not price_series.empty
        except Exception:
            return False
    
    def get_min_bars_required(self) -> int:
        """Get minimum bars required for EMA calculation."""
        return self.period
    
    def _generate_signals(self, prices: pd.Series, ema: pd.Series) -> pd.Series:
        """Generate basic trading signals based on EMA crossovers.
        
        Args:
            prices: Original price series
            ema: EMA values
            
        Returns:
            Series with trading signals (1=buy, -1=sell, 0=hold)
        """
        signals = pd.Series(0, index=prices.index)
        
        # Find crossovers
        price_above_ema = prices > ema
        price_below_ema = prices < ema
        
        # Buy signal: price crosses above EMA
        buy_signals = price_above_ema & price_below_ema.shift(1).fillna(False).infer_objects(copy=False)
        
        # Sell signal: price crosses below EMA  
        sell_signals = price_below_ema & price_above_ema.shift(1).fillna(False).infer_objects(copy=False)
        
        signals[buy_signals] = 1
        signals[sell_signals] = -1
        
        return signals
