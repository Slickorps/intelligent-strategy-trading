"""Technical indicators library.

This package provides a collection of technical analysis indicators
for use in trading strategies. All indicators follow a consistent interface
defined by the BaseIndicator abstract class.

Available Indicators:
    - Moving Averages: SMA, EMA
    - Momentum: RSI, Momentum
    - Trend: MACD
    - Volatility: ATR, BollingerBands

Example:
    ```python
    from ist.strategy.indicators import SMA, IndicatorInput
    import pandas as pd

    # Create and use indicator
    sma = SMA(period=20)
    data = IndicatorInput(close=pd.Series([...]))
    result = sma.calculate(data)
    ```
"""

from ist.strategy.indicators.base import (
    BaseIndicator,
    CachedIndicator,
    IndicatorInput,
    IndicatorProtocol,
    IndicatorResult,
)
from ist.strategy.indicators.moving_averages import SMA, EMA
from ist.strategy.indicators.momentum import RSI

__all__ = [
    # Base classes
    "BaseIndicator",
    "CachedIndicator",
    "IndicatorInput",
    "IndicatorResult",
    "IndicatorProtocol",
    # Moving averages
    "SMA",
    "EMA",
    # Momentum
    "RSI",
]
