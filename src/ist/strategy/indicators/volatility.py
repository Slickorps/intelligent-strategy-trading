"""Volatility indicators.

This module implements volatility-based technical indicators including
Average True Range (ATR) and Bollinger Bands.

Volatility indicators measure the magnitude of price fluctuations,
helping identify potential breakouts and risk levels.
"""

import pandas as pd
import numpy as np

from ist.strategy.indicators.base import BaseIndicator, IndicatorInput, IndicatorResult
from ist.core.exceptions import IndicatorError
from ist.core.logging import get_logger

logger = get_logger(__name__)


class ATR(BaseIndicator):
    """Average True Range (ATR).
    
    ATR measures market volatility by calculating the average of true ranges
    over a specified period. True range considers the current period's range
    and gaps from the previous close.
    
    Formula:
        True Range = max(
            High - Low,
            |High - Previous Close|,
            |Low - Previous Close|
        )
        ATR = SMA(True Range, period)  # or EMA with Wilder's smoothing
    
    Args:
        period: Number of periods for calculation (default: 14)
        use_wilder: Use Wilder's smoothing (default: True)
        
    Example:
        ```python
        atr = ATR(period=14)
        data = IndicatorInput(high=high, low=low, close=close)
        result = atr.calculate(data)
        print(result.values)  # ATR values
        ```
    """
    
    def __init__(self, period: int = 14, use_wilder: bool = True) -> None:
        """Initialize ATR indicator.
        
        Args:
            period: Number of periods for calculation (must be >= 1)
            use_wilder: Use Wilder's smoothing (alpha = 1/period)
        """
        if period < 1:
            raise IndicatorError("ATR period must be >= 1")
        
        super().__init__("ATR", {"period": period, "use_wilder": use_wilder})
        self.period = period
        self.use_wilder = use_wilder
        self._alpha = 1.0 / period if use_wilder else 2.0 / (period + 1)
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate ATR values.
        
        Args:
            data: IndicatorInput containing high, low, close prices
            
        Returns:
            IndicatorResult with ATR values
            
        Raises:
            IndicatorError: If calculation fails or required data missing
        """
        try:
            if data.high is None or data.low is None or data.close is None:
                raise IndicatorError("ATR requires high, low, and close price data")
            
            if not self.validate_input(data):
                raise IndicatorError(
                    f"Insufficient data for ATR calculation. Need at least {self.period + 1} periods"
                )
            
            # Calculate true range
            high = data.high
            low = data.low
            close = data.close
            
            # Previous close (shift by 1)
            prev_close = close.shift(1)
            
            # True range components
            tr1 = high - low  # Current period range
            tr2 = (high - prev_close).abs()  # Gap up
            tr3 = (low - prev_close).abs()   # Gap down
            
            # True range is the maximum of the three
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # First ATR value is simple average of first 'period' true ranges
            # Subsequent values use smoothing
            if self.use_wilder:
                # Wilder's smoothing (RMA)
                atr_values = true_range.ewm(alpha=self._alpha, min_periods=self.period).mean()
            else:
                # Standard SMA
                atr_values = true_range.rolling(window=self.period, min_periods=1).mean()
            
            logger.debug(
                f"Calculated ATR({self.period}) for {len(close)} data points"
            )
            
            return IndicatorResult(
                values=atr_values,
                metadata={
                    "period": self.period,
                    "use_wilder": self.use_wilder,
                    "method": "wilder" if self.use_wilder else "sma"
                }
            )
            
        except Exception as e:
            raise IndicatorError(f"ATR calculation failed: {str(e)}")
    
    def validate_input(self, data: IndicatorInput) -> bool:
        """Validate input data for ATR calculation.
        
        Args:
            data: IndicatorInput to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if data.high is None or data.low is None or data.close is None:
                return False
            # Need at least period + 1 data points for true range calculation
            return len(data.close) >= (self.period + 1) and not data.close.empty
        except Exception:
            return False
    
    def get_min_bars_required(self) -> int:
        """Get minimum bars required for ATR calculation."""
        return self.period + 1


class BollingerBands(BaseIndicator):
    """Bollinger Bands.
    
    Bollinger Bands consist of a middle band (SMA) and two outer bands
    (standard deviations away from the middle band). They help identify
    overbought/oversold conditions and volatility.
    
    Formula:
        Middle Band = SMA(close, period)
        Upper Band = Middle Band + (std_dev * multiplier)
        Lower Band = Middle Band - (std_dev * multiplier)
        Bandwidth = (Upper - Lower) / Middle
        %b = (Close - Lower) / (Upper - Lower)
    
    Args:
        period: Number of periods for SMA (default: 20)
        multiplier: Standard deviation multiplier (default: 2.0)
        
    Example:
        ```python
        bb = BollingerBands(period=20, multiplier=2.0)
        data = IndicatorInput(close=price_series)
        result = bb.calculate(data)
        print(result.values)       # Middle band (SMA)
        print(result.upper_band)   # Upper band
        print(result.lower_band)   # Lower band
        print(result.histogram)    # Bandwidth
        ```
    """
    
    def __init__(self, period: int = 20, multiplier: float = 2.0) -> None:
        """Initialize Bollinger Bands indicator.
        
        Args:
            period: Number of periods for SMA (must be >= 2)
            multiplier: Standard deviation multiplier (must be > 0)
        """
        if period < 2:
            raise IndicatorError("Bollinger Bands period must be >= 2")
        if multiplier <= 0:
            raise IndicatorError("Multiplier must be > 0")
        
        super().__init__("BollingerBands", {"period": period, "multiplier": multiplier})
        self.period = period
        self.multiplier = multiplier
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate Bollinger Bands values.
        
        Args:
            data: IndicatorInput containing price data
            
        Returns:
            IndicatorResult with middle, upper, lower bands, bandwidth
            
        Raises:
            IndicatorError: If calculation fails
        """
        try:
            price_series = data.main_series
            
            if not self.validate_input(data):
                raise IndicatorError(
                    f"Insufficient data for Bollinger Bands calculation. Need at least {self.period} periods"
                )
            
            # Calculate middle band (SMA)
            middle_band = price_series.rolling(window=self.period, min_periods=1).mean()
            
            # Calculate standard deviation
            std_dev = price_series.rolling(window=self.period, min_periods=1).std()
            
            # Calculate upper and lower bands
            upper_band = middle_band + (std_dev * self.multiplier)
            lower_band = middle_band - (std_dev * self.multiplier)
            
            # Calculate bandwidth (% of middle band)
            bandwidth = ((upper_band - lower_band) / middle_band) * 100
            bandwidth = bandwidth.replace([np.inf, -np.inf], np.nan)
            
            # Calculate %b (position within bands)
            percent_b = (price_series - lower_band) / (upper_band - lower_band)
            percent_b = percent_b.replace([np.inf, -np.inf], np.nan)
            
            # Generate signals based on %b
            signals = self._generate_signals(percent_b)
            
            logger.debug(
                f"Calculated BollingerBands({self.period},{self.multiplier}) "
                f"for {len(price_series)} data points"
            )
            
            return IndicatorResult(
                values=middle_band,
                upper_band=upper_band,
                lower_band=lower_band,
                histogram=bandwidth,  # Bandwidth stored in histogram field
                signals=signals,
                metadata={
                    "period": self.period,
                    "multiplier": self.multiplier,
                    "percent_b": percent_b,
                    "method": "sma"
                }
            )
            
        except Exception as e:
            raise IndicatorError(f"Bollinger Bands calculation failed: {str(e)}")
    
    def validate_input(self, data: IndicatorInput) -> bool:
        """Validate input data for Bollinger Bands calculation.
        
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
        """Get minimum bars required for Bollinger Bands calculation."""
        return self.period
    
    def is_price_above_upper(self, price: float, upper_band: float) -> bool:
        """Check if price is above upper band (overbought).
        
        Args:
            price: Current price
            upper_band: Upper band value
            
        Returns:
            True if price is above upper band
        """
        return price > upper_band
    
    def is_price_below_lower(self, price: float, lower_band: float) -> bool:
        """Check if price is below lower band (oversold).
        
        Args:
            price: Current price
            lower_band: Lower band value
            
        Returns:
            True if price is below lower band
        """
        return price < lower_band
    
    def get_percent_b(self, price: float, upper: float, lower: float) -> float:
        """Calculate %b value (position within bands).
        
        %b = 0 at lower band, 1 at upper band, 0.5 at middle band
        
        Args:
            price: Current price
            upper: Upper band value
            lower: Lower band value
            
        Returns:
            %b value
        """
        if upper == lower:
            return 0.5  # Avoid division by zero
        return (price - lower) / (upper - lower)
    
    def get_bandwidth(self, upper: float, lower: float, middle: float) -> float:
        """Calculate bandwidth as percentage of middle band.
        
        Args:
            upper: Upper band value
            lower: Lower band value
            middle: Middle band value
            
        Returns:
            Bandwidth percentage
        """
        if middle == 0:
            return 0.0
        return ((upper - lower) / middle) * 100
    
    def _generate_signals(self, percent_b: pd.Series) -> pd.Series:
        """Generate trading signals based on %b position.
        
        Signals:
            - Buy (1): Price touches or crosses below lower band (%b <= 0)
            - Sell (-1): Price touches or crosses above upper band (%b >= 1)
            - Hold (0): Otherwise
        
        Args:
            percent_b: %b values series
            
        Returns:
            Series with trading signals (1=buy, -1=sell, 0=hold)
        """
        signals = pd.Series(0, index=percent_b.index)
        
        # Buy signal: %b crosses below 0 (or touches lower band)
        buy_condition = (percent_b <= 0) & (percent_b.shift(1) > 0).fillna(False).infer_objects(copy=False)
        signals[buy_condition] = 1
        
        # Sell signal: %b crosses above 1 (or touches upper band)
        sell_condition = (percent_b >= 1) & (percent_b.shift(1) < 1).fillna(False).infer_objects(copy=False)
        signals[sell_condition] = -1
        
        return signals
    
    def get_signal_description(self, signal: int) -> str:
        """Get human-readable description of a Bollinger Bands signal.
        
        Args:
            signal: Signal value (1, -1, or 0)
            
        Returns:
            Description string
        """
        descriptions = {
            1: f"Buy signal - Price at or below lower band (oversold bounce)",
            -1: f"Sell signal - Price at or above upper band (overbought pullback)",
            0: f"Hold - Price within bands"
        }
        return descriptions.get(signal, "Unknown signal")
