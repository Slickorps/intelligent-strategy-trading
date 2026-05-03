"""Trend indicators.

This module implements trend-following technical indicators including
Moving Average Convergence Divergence (MACD).

Trend indicators help identify the direction and strength of price trends.
"""

import pandas as pd
import numpy as np

from ist.strategy.indicators.base import BaseIndicator, IndicatorInput, IndicatorResult
from ist.core.exceptions import IndicatorError
from ist.core.logging import get_logger

logger = get_logger(__name__)


class MACD(BaseIndicator):
    """Moving Average Convergence Divergence (MACD).
    
    MACD is a trend-following momentum indicator that shows the relationship
    between two exponential moving averages of prices. It consists of:
    - MACD Line: Difference between fast and slow EMAs
    - Signal Line: EMA of the MACD Line
    - Histogram: Difference between MACD and Signal lines
    
    Formula:
        MACD Line = EMA(fast_period) - EMA(slow_period)
        Signal Line = EMA(MACD Line, signal_period)
        Histogram = MACD Line - Signal Line
    
    Args:
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
        signal_period: Signal line EMA period (default: 9)
        
    Example:
        ```python
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        data = IndicatorInput(close=price_series)
        result = macd.calculate(data)
        print(result.values)      # MACD line
        print(result.signal_line) # Signal line
        print(result.histogram)   # Histogram
        ```
    """
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> None:
        """Initialize MACD indicator.
        
        Args:
            fast_period: Fast EMA period (must be < slow_period)
            slow_period: Slow EMA period
            signal_period: Signal line EMA period
        """
        if fast_period >= slow_period:
            raise IndicatorError("Fast period must be less than slow period")
        if fast_period < 1 or slow_period < 1 or signal_period < 1:
            raise IndicatorError("All periods must be >= 1")
        
        super().__init__("MACD", {
            "fast_period": fast_period,
            "slow_period": slow_period,
            "signal_period": signal_period
        })
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        
        # Calculate alpha values for EMAs
        self._fast_alpha = 2.0 / (fast_period + 1)
        self._slow_alpha = 2.0 / (slow_period + 1)
        self._signal_alpha = 2.0 / (signal_period + 1)
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate MACD values.
        
        Args:
            data: IndicatorInput containing price data
            
        Returns:
            IndicatorResult with MACD line, signal line, and histogram
            
        Raises:
            IndicatorError: If calculation fails
        """
        try:
            price_series = data.main_series
            
            if not self.validate_input(data):
                raise IndicatorError(
                    f"Insufficient data for MACD calculation. Need at least {self.slow_period} periods"
                )
            
            # Calculate fast and slow EMAs
            fast_ema = price_series.ewm(alpha=self._fast_alpha, adjust=False).mean()
            slow_ema = price_series.ewm(alpha=self._slow_alpha, adjust=False).mean()
            
            # Calculate MACD line
            macd_line = fast_ema - slow_ema
            
            # Calculate signal line (EMA of MACD line)
            signal_line = macd_line.ewm(alpha=self._signal_alpha, adjust=False).mean()
            
            # Calculate histogram
            histogram = macd_line - signal_line
            
            # Generate trading signals
            signals = self._generate_signals(macd_line, signal_line)
            
            logger.debug(
                f"Calculated MACD({self.fast_period},{self.slow_period},{self.signal_period}) "
                f"for {len(price_series)} data points"
            )
            
            return IndicatorResult(
                values=macd_line,
                signal_line=signal_line,
                histogram=histogram,
                signals=signals,
                metadata={
                    "fast_period": self.fast_period,
                    "slow_period": self.slow_period,
                    "signal_period": self.signal_period,
                    "method": "ema"
                }
            )
            
        except Exception as e:
            raise IndicatorError(f"MACD calculation failed: {str(e)}")
    
    def validate_input(self, data: IndicatorInput) -> bool:
        """Validate input data for MACD calculation.
        
        Args:
            data: IndicatorInput to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            price_series = data.main_series
            # Need at least slow_period data points
            return len(price_series) >= self.slow_period and not price_series.empty
        except Exception:
            return False
    
    def get_min_bars_required(self) -> int:
        """Get minimum bars required for MACD calculation."""
        return self.slow_period
    
    def is_golden_cross(self, macd_line: pd.Series, signal_line: pd.Series, index: int = -1) -> bool:
        """Check if MACD line crosses above signal line (golden cross).
        
        Args:
            macd_line: MACD line values
            signal_line: Signal line values
            index: Index to check (default: -1 for latest)
            
        Returns:
            True if golden cross occurred at index
        """
        if index == -1:
            idx = len(macd_line) - 1
        else:
            idx = index
        
        if idx < 1:
            return False
        
        # Current: MACD > Signal, Previous: MACD < Signal
        current_above = macd_line.iloc[idx] > signal_line.iloc[idx]
        previous_below = macd_line.iloc[idx - 1] < signal_line.iloc[idx - 1]
        
        return current_above and previous_below
    
    def is_death_cross(self, macd_line: pd.Series, signal_line: pd.Series, index: int = -1) -> bool:
        """Check if MACD line crosses below signal line (death cross).
        
        Args:
            macd_line: MACD line values
            signal_line: Signal line values
            index: Index to check (default: -1 for latest)
            
        Returns:
            True if death cross occurred at index
        """
        if index == -1:
            idx = len(macd_line) - 1
        else:
            idx = index
        
        if idx < 1:
            return False
        
        # Current: MACD < Signal, Previous: MACD > Signal
        current_below = macd_line.iloc[idx] < signal_line.iloc[idx]
        previous_above = macd_line.iloc[idx - 1] > signal_line.iloc[idx - 1]
        
        return current_below and previous_above
    
    def get_crossover_type(self, macd_line: pd.Series, signal_line: pd.Series, index: int = -1) -> str:
        """Get the type of crossover at the given index.
        
        Args:
            macd_line: MACD line values
            signal_line: Signal line values
            index: Index to check (default: -1 for latest)
            
        Returns:
            'golden' for golden cross, 'death' for death cross, 'none' for no crossover
        """
        if self.is_golden_cross(macd_line, signal_line, index):
            return "golden"
        elif self.is_death_cross(macd_line, signal_line, index):
            return "death"
        return "none"
    
    def _generate_signals(self, macd_line: pd.Series, signal_line: pd.Series) -> pd.Series:
        """Generate trading signals based on MACD crossovers.
        
        Signals:
            - Buy (1): Golden cross (MACD crosses above signal)
            - Sell (-1): Death cross (MACD crosses below signal)
            - Hold (0): Otherwise
        
        Args:
            macd_line: MACD line values
            signal_line: Signal line values
            
        Returns:
            Series with trading signals (1=buy, -1=sell, 0=hold)
        """
        signals = pd.Series(0, index=macd_line.index)
        
        # Find crossovers
        macd_above_signal = macd_line > signal_line
        macd_below_signal = macd_line < signal_line
        
        # Golden cross: MACD crosses above signal
        golden_cross = macd_above_signal & macd_below_signal.shift(1).fillna(False).infer_objects(copy=False)
        signals[golden_cross] = 1
        
        # Death cross: MACD crosses below signal
        death_cross = macd_below_signal & macd_above_signal.shift(1).fillna(False).infer_objects(copy=False)
        signals[death_cross] = -1
        
        return signals
    
    def get_signal_description(self, signal: int) -> str:
        """Get human-readable description of a MACD signal.
        
        Args:
            signal: Signal value (1, -1, or 0)
            
        Returns:
            Description string
        """
        descriptions = {
            1: "Buy signal - MACD golden cross (MACD crosses above signal line)",
            -1: "Sell signal - MACD death cross (MACD crosses below signal line)",
            0: "Hold - No crossover signal"
        }
        return descriptions.get(signal, "Unknown signal")
