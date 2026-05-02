"""Momentum indicators.

This module implements momentum-based technical indicators including
Relative Strength Index (RSI).

Momentum indicators measure the speed and magnitude of price movements,
helping identify overbought and oversold conditions.
"""

import pandas as pd
import numpy as np

from ist.strategy.indicators.base import BaseIndicator, IndicatorInput, IndicatorResult
from ist.core.exceptions import IndicatorError
from ist.core.logging import get_logger

logger = get_logger(__name__)


class RSI(BaseIndicator):
    """Relative Strength Index (RSI).
    
    RSI is a momentum oscillator that measures the speed and magnitude of
    recent price changes. It oscillates between 0 and 100, with values
    above 70 typically considered overbought and values below 30 oversold.
    
    Formula:
        RS = Average Gain / Average Loss
        RSI = 100 - (100 / (1 + RS))
    
    Args:
        period: Number of periods for calculation (default: 14)
        overbought: Overbought threshold (default: 70)
        oversold: Oversold threshold (default: 30)
        
    Example:
        ```python
        rsi = RSI(period=14)
        data = IndicatorInput(close=price_series)
        result = rsi.calculate(data)
        print(result.values)  # RSI values (0-100)
        print(result.signals)  # Trading signals
        ```
    """
    
    def __init__(
        self,
        period: int = 14,
        overbought: float = 70.0,
        oversold: float = 30.0
    ) -> None:
        """Initialize RSI indicator.
        
        Args:
            period: Number of periods for calculation (must be >= 2)
            overbought: Overbought threshold (default: 70)
            oversold: Oversold threshold (default: 30)
        """
        if period < 2:
            raise IndicatorError("RSI period must be >= 2")
        if overbought <= oversold:
            raise IndicatorError("Overbought threshold must be greater than oversold threshold")
        if not (0 <= overbought <= 100) or not (0 <= oversold <= 100):
            raise IndicatorError("RSI thresholds must be between 0 and 100")
        
        super().__init__("RSI", {
            "period": period,
            "overbought": overbought,
            "oversold": oversold
        })
        self.period = period
        self.overbought = overbought
        self.oversold = oversold
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate RSI values.
        
        Args:
            data: IndicatorInput containing price data
            
        Returns:
            IndicatorResult with RSI values (0-100)
            
        Raises:
            IndicatorError: If calculation fails
        """
        try:
            price_series = data.main_series
            
            if not self.validate_input(data):
                raise IndicatorError(
                    f"Insufficient data for RSI calculation. Need at least {self.period + 1} periods"
                )
            
            # Calculate price changes
            delta = price_series.diff()
            
            # Separate gains and losses
            gains = delta.clip(lower=0)
            losses = (-delta).clip(lower=0)
            
            # Calculate average gains and losses using Wilder's smoothing
            avg_gains = gains.ewm(alpha=1/self.period, min_periods=self.period).mean()
            avg_losses = losses.ewm(alpha=1/self.period, min_periods=self.period).mean()
            
            # Calculate RS and RSI
            rs = avg_gains / avg_losses
            rsi_values = 100 - (100 / (1 + rs))
            
            # Handle division by zero (when avg_losses is 0)
            rsi_values = rsi_values.fillna(100)
            
            # Generate signals based on overbought/oversold levels
            signals = self._generate_signals(rsi_values)
            
            logger.debug(
                f"Calculated RSI({self.period}) for {len(price_series)} data points"
            )
            
            return IndicatorResult(
                values=rsi_values,
                upper_band=pd.Series(self.overbought, index=price_series.index),
                lower_band=pd.Series(self.oversold, index=price_series.index),
                signals=signals,
                metadata={
                    "period": self.period,
                    "overbought": self.overbought,
                    "oversold": self.oversold,
                    "method": "wilder_smoothing"
                }
            )
            
        except Exception as e:
            raise IndicatorError(f"RSI calculation failed: {str(e)}")
    
    def validate_input(self, data: IndicatorInput) -> bool:
        """Validate input data for RSI calculation.
        
        Args:
            data: IndicatorInput to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            price_series = data.main_series
            # RSI needs period + 1 data points because of diff()
            return len(price_series) >= (self.period + 1) and not price_series.empty
        except Exception:
            return False
    
    def get_min_bars_required(self) -> int:
        """Get minimum bars required for RSI calculation."""
        return self.period + 1
    
    def is_overbought(self, rsi_value: float) -> bool:
        """Check if RSI value indicates overbought condition.
        
        Args:
            rsi_value: RSI value to check
            
        Returns:
            True if overbought, False otherwise
        """
        return rsi_value >= self.overbought
    
    def is_oversold(self, rsi_value: float) -> bool:
        """Check if RSI value indicates oversold condition.
        
        Args:
            rsi_value: RSI value to check
            
        Returns:
            True if oversold, False otherwise
        """
        return rsi_value <= self.oversold
    
    def _generate_signals(self, rsi_values: pd.Series) -> pd.Series:
        """Generate trading signals based on RSI levels.
        
        Signals:
            - Buy (1): RSI crosses above oversold level (leaving oversold zone)
            - Sell (-1): RSI crosses below overbought level (leaving overbought zone)
            - Hold (0): Otherwise
        
        Args:
            rsi_values: RSI values series
            
        Returns:
            Series with trading signals (1=buy, -1=sell, 0=hold)
        """
        signals = pd.Series(0, index=rsi_values.index)
        
        # Identify overbought and oversold conditions
        overbought_condition = rsi_values >= self.overbought
        oversold_condition = rsi_values <= self.oversold
        
        # Buy signal: RSI crosses above oversold level (leaving oversold zone)
        leaving_oversold = (~oversold_condition) & oversold_condition.shift(1).fillna(False).infer_objects(copy=False)
        signals[leaving_oversold] = 1
        
        # Sell signal: RSI crosses below overbought level (leaving overbought zone)
        leaving_overbought = (~overbought_condition) & overbought_condition.shift(1).fillna(False).infer_objects(copy=False)
        signals[leaving_overbought] = -1
        
        return signals
    
    def get_signal_description(self, signal: int) -> str:
        """Get human-readable description of an RSI signal.
        
        Args:
            signal: Signal value (1, -1, or 0)
            
        Returns:
            Description string
        """
        descriptions = {
            1: f"Buy signal - RSI leaving oversold zone (<{self.oversold})",
            -1: f"Sell signal - RSI leaving overbought zone (>{self.overbought})",
            0: f"Hold - RSI in neutral zone ({self.oversold}-{self.overbought})"
        }
        return descriptions.get(signal, "Unknown signal")
