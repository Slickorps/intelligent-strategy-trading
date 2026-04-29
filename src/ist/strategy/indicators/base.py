"""Base classes for technical indicators.

This module defines the abstract interface for all technical indicators
in the platform, ensuring consistent API and behavior.

Example:
    ```python
    from ist.strategy.indicators import SMA, IndicatorInput
    import pandas as pd
    
    # Create indicator instance
    sma = SMA(period=20)
    
    # Prepare input data
    data = pd.Series([1, 2, 3, 4, 5, ...])
    input_data = IndicatorInput(close=data)
    
    # Calculate indicator
    result = sma.calculate(input_data)
    print(result.values)  # SMA values
    print(result.signals)  # Trading signals (optional)
    ```
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

import pandas as pd
import numpy as np

from ist.core.exceptions import IndicatorError
from ist.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class IndicatorInput:
    """Standardized input data for technical indicators.
    
    This dataclass encapsulates all possible input data types that indicators
    may need, providing a consistent interface across different indicator types.
    
    Attributes:
        open: Opening prices (for indicators using OHLC)
        high: High prices
        low: Low prices
        close: Closing prices (most common input)
        volume: Trading volume
        timestamp: Timestamps for each data point
    """
    
    open: Optional[pd.Series] = None
    high: Optional[pd.Series] = None
    low: Optional[pd.Series] = None
    close: Optional[pd.Series] = None
    volume: Optional[pd.Series] = None
    timestamp: Optional[pd.DatetimeIndex] = None
    
    def __post_init__(self) -> None:
        """Validate that at least one price series is provided."""
        price_series = [self.open, self.high, self.low, self.close]
        if not any(s is not None for s in price_series):
            raise IndicatorError(
                "At least one price series (open, high, low, close) must be provided"
            )
    
    @property
    def main_series(self) -> pd.Series:
        """Get the primary price series for calculation.
        
        Returns close if available, otherwise falls back to other price series.
        """
        if self.close is not None:
            return self.close
        elif self.high is not None:
            return self.high
        elif self.low is not None:
            return self.low
        elif self.open is not None:
            return self.open
        raise IndicatorError("No price series available")
    
    def __len__(self) -> int:
        """Return length of the main series."""
        return len(self.main_series)


@dataclass
class IndicatorResult:
    """Results from technical indicator calculation.
    
    Attributes:
        values: Primary indicator values (e.g., SMA line, RSI values)
        upper_band: Upper threshold/band (e.g., Bollinger upper band, RSI overbought)
        lower_band: Lower threshold/band (e.g., Bollinger lower band, RSI oversold)
        signal_line: Secondary line (e.g., MACD signal line)
        histogram: Derived values (e.g., MACD histogram, Bollinger bandwidth)
        signals: Trading signals generated (1=buy, -1=sell, 0=hold)
        metadata: Additional indicator-specific data
    """
    
    values: pd.Series
    upper_band: Optional[pd.Series] = None
    lower_band: Optional[pd.Series] = None
    signal_line: Optional[pd.Series] = None
    histogram: Optional[pd.Series] = None
    signals: Optional[pd.Series] = None
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Ensure all series have the same index."""
        reference_index = self.values.index
        
        for name, series in [
            ("upper_band", self.upper_band),
            ("lower_band", self.lower_band),
            ("signal_line", self.signal_line),
            ("histogram", self.histogram),
            ("signals", self.signals),
        ]:
            if series is not None and not series.index.equals(reference_index):
                raise IndicatorError(
                    f"{name} series index does not match values index"
                )
    
    @property
    def last_value(self) -> float:
        """Get the most recent indicator value."""
        return float(self.values.iloc[-1])
    
    @property
    def is_ready(self) -> bool:
        """Check if indicator has enough data to be valid."""
        return len(self.values) > 0 and not self.values.isna().all()


@runtime_checkable
class IndicatorProtocol(Protocol):
    """Protocol defining the indicator interface.
    
    This protocol allows for structural subtyping, enabling indicators
    to be used without explicit inheritance from BaseIndicator.
    """
    
    name: str
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate indicator values from input data."""
        ...
    
    def validate_input(self, data: IndicatorInput) -> bool:
        """Validate that input data is suitable for this indicator."""
        ...


class BaseIndicator(ABC):
    """Abstract base class for all technical indicators.
    
    All technical indicators in the platform must inherit from this class
    and implement the required abstract methods. This ensures consistent
    behavior and API across all indicators.
    
    Attributes:
        name: Human-readable indicator name
        params: Dictionary of indicator parameters
        _cache: Optional cache for calculated values
    
    Example:
        ```python
        class RSI(BaseIndicator):
            def __init__(self, period: int = 14):
                super().__init__("RSI", {"period": period})
                self.period = period
            
            def calculate(self, data: IndicatorInput) -> IndicatorResult:
                # RSI calculation logic
                return IndicatorResult(values=rsi_series)
            
            def validate_input(self, data: IndicatorInput) -> bool:
                return len(data) >= self.period
        ```
    """
    
    def __init__(self, name: str, params: Optional[dict] = None) -> None:
        """Initialize the indicator.
        
        Args:
            name: Human-readable name for the indicator
            params: Dictionary of indicator-specific parameters
        """
        self.name = name
        self.params = params or {}
        self._cache: Optional[IndicatorResult] = None
        self._cache_key: Optional[str] = None
        
        logger.debug(f"Initialized indicator: {name}", params=params)
    
    @abstractmethod
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate indicator values from input data.
        
        This is the primary method that all indicators must implement.
        It takes standardized input data and returns calculated indicator values.
        
        Args:
            data: IndicatorInput containing price/volume data
            
        Returns:
            IndicatorResult with calculated values and optional signals
            
        Raises:
            IndicatorError: If calculation fails or input is invalid
        """
        pass
    
    @abstractmethod
    def validate_input(self, data: IndicatorInput) -> bool:
        """Validate that input data is suitable for this indicator.
        
        Check that the input data has sufficient length, required fields,
        and meets any other criteria for this indicator.
        
        Args:
            data: IndicatorInput to validate
            
        Returns:
            True if input is valid, False otherwise
        """
        pass
    
    def get_min_bars_required(self) -> int:
        """Get the minimum number of bars required for valid calculation.
        
        Returns:
            Minimum number of data points needed
        """
        return 1
    
    def clear_cache(self) -> None:
        """Clear any cached calculation results."""
        self._cache = None
        self._cache_key = None
        logger.debug(f"Cleared cache for {self.name}")
    
    def get_description(self) -> str:
        """Get a human-readable description of the indicator.
        
        Returns:
            Description string including name and parameters
        """
        params_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.name}({params_str})"
    
    def __repr__(self) -> str:
        return self.get_description()
    
    def __str__(self) -> str:
        return self.get_description()


class CachedIndicator(BaseIndicator):
    """Base class for indicators with built-in caching.
    
    Extends BaseIndicator with automatic caching of calculation results.
    Useful for indicators that are expensive to compute and may be
    called multiple times with the same input.
    
    Attributes:
        _cache: Stored calculation result
        _cache_key: Hash key for cache validation
    """
    
    def _generate_cache_key(self, data: IndicatorInput) -> str:
        """Generate a unique cache key for the input data.
        
        Args:
            data: Input data to hash
            
        Returns:
            String hash representing the input state
        """
        # Use hash of the main series values and length
        main_series = data.main_series
        return f"{hash(main_series.values.tobytes())}_{len(main_series)}_{id(self)}"
    
    def calculate_with_cache(self, data: IndicatorInput) -> IndicatorResult:
        """Calculate with automatic caching.
        
        Checks cache first before performing calculation. If cache hit,
        returns cached result. Otherwise, computes and stores result.
        
        Args:
            data: Input data for calculation
            
        Returns:
            IndicatorResult (cached or freshly computed)
        """
        cache_key = self._generate_cache_key(data)
        
        if self._cache is not None and self._cache_key == cache_key:
            logger.debug(f"Cache hit for {self.name}")
            return self._cache
        
        logger.debug(f"Cache miss for {self.name}, calculating...")
        result = self.calculate(data)
        
        self._cache = result
        self._cache_key = cache_key
        
        return result
