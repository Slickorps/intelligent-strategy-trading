"""Unit tests for technical indicators library."""

import numpy as np
import pandas as pd
import pytest

from ist.core.exceptions import IndicatorError
from ist.strategy.indicators import (
    BaseIndicator,
    CachedIndicator,
    IndicatorInput,
    IndicatorResult,
    SMA,
    EMA,
)


class TestIndicatorInput:
    """Tests for IndicatorInput data class."""
    
    def test_create_with_close(self):
        """Test creating IndicatorInput with close prices."""
        data = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        input_data = IndicatorInput(close=data)
        
        assert len(input_data) == 5
        assert input_data.main_series.equals(data)
    
    def test_create_without_any_prices_raises_error(self):
        """Test that creating without any price series raises error."""
        with pytest.raises(IndicatorError):
            IndicatorInput()
    
    def test_create_with_ohlc(self):
        """Test creating with full OHLC data."""
        input_data = IndicatorInput(
            open=pd.Series([1.0, 2.0, 3.0]),
            high=pd.Series([2.0, 3.0, 4.0]),
            low=pd.Series([0.5, 1.5, 2.5]),
            close=pd.Series([1.5, 2.5, 3.5]),
        )
        
        assert len(input_data) == 3
        assert input_data.close is not None


class TestIndicatorResult:
    """Tests for IndicatorResult data class."""
    
    def test_create_basic_result(self):
        """Test creating basic indicator result."""
        values = pd.Series([10.0, 20.0, 30.0])
        result = IndicatorResult(values=values)
        
        assert result.last_value == 30.0
        assert result.is_ready
    
    def test_create_with_bands(self):
        """Test creating result with upper/lower bands."""
        values = pd.Series([10.0, 20.0, 30.0])
        upper = pd.Series([15.0, 25.0, 35.0])
        lower = pd.Series([5.0, 15.0, 25.0])
        
        result = IndicatorResult(
            values=values,
            upper_band=upper,
            lower_band=lower,
        )
        
        assert result.upper_band is not None
        assert result.lower_band is not None
    
    def test_mismatched_index_raises_error(self):
        """Test that mismatched series indices raise error."""
        values = pd.Series([10.0, 20.0, 30.0], index=[0, 1, 2])
        upper = pd.Series([15.0, 25.0, 35.0], index=[0, 1, 3])  # Different index
        
        with pytest.raises(IndicatorError):
            IndicatorResult(values=values, upper_band=upper)


class MockIndicator(BaseIndicator):
    """Mock indicator for testing BaseIndicator."""
    
    def __init__(self, period: int = 10):
        super().__init__("Mock", {"period": period})
        self.period = period
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Simple mock calculation."""
        values = data.main_series.rolling(window=self.period).mean()
        return IndicatorResult(values=values)
    
    def validate_input(self, data: IndicatorInput) -> bool:
        """Check if enough data."""
        return len(data) >= self.period
    
    def get_min_bars_required(self) -> int:
        return self.period


class TestBaseIndicator:
    """Tests for BaseIndicator abstract class."""
    
    def test_indicator_initialization(self):
        """Test indicator initialization."""
        indicator = MockIndicator(period=20)
        
        assert indicator.name == "Mock"
        assert indicator.params == {"period": 20}
        assert indicator.period == 20
    
    def test_indicator_description(self):
        """Test indicator description string."""
        indicator = MockIndicator(period=20)
        desc = indicator.get_description()
        
        assert "Mock" in desc
        assert "period=20" in desc
    
    def test_indicator_calculation(self):
        """Test basic calculation flow."""
        indicator = MockIndicator(period=3)
        data = IndicatorInput(close=pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]))
        
        result = indicator.calculate(data)
        
        assert isinstance(result, IndicatorResult)
        assert len(result.values) == 5
    
    def test_input_validation(self):
        """Test input validation."""
        indicator = MockIndicator(period=10)
        
        # Valid input
        valid_data = IndicatorInput(close=pd.Series(range(15)))
        assert indicator.validate_input(valid_data)
        
        # Invalid input (too short)
        invalid_data = IndicatorInput(close=pd.Series(range(5)))
        assert not indicator.validate_input(invalid_data)
    
    def test_cache_operations(self):
        """Test cache clear operation."""
        indicator = MockIndicator(period=3)
        
        # Initially cache is empty
        assert indicator._cache is None
        
        # Clear cache (should not raise)
        indicator.clear_cache()
        assert indicator._cache is None


class SimpleCachedIndicator(CachedIndicator):
    """Simple cached indicator for testing."""
    
    def __init__(self):
        super().__init__("CachedMock", {})
        self.calc_count = 0
    
    def calculate(self, data: IndicatorInput) -> IndicatorResult:
        """Track calculation calls."""
        self.calc_count += 1
        return IndicatorResult(values=data.main_series * 2)
    
    def validate_input(self, data: IndicatorInput) -> bool:
        return True


class TestCachedIndicator:
    """Tests for CachedIndicator."""
    
    def test_cache_hit_avoids_recalculation(self):
        """Test that cache hit avoids recalculation."""
        indicator = SimpleCachedIndicator()
        data = IndicatorInput(close=pd.Series([1.0, 2.0, 3.0]))
        
        # First call should calculate
        result1 = indicator.calculate_with_cache(data)
        assert indicator.calc_count == 1
        
        # Second call with same data should use cache
        result2 = indicator.calculate_with_cache(data)
        assert indicator.calc_count == 1  # No additional calculation
        
        # Results should be identical
        assert result1.values.equals(result2.values)
    
    def test_cache_miss_on_different_data(self):
        """Test that different data triggers recalculation."""
        indicator = SimpleCachedIndicator()
        
        data1 = IndicatorInput(close=pd.Series([1.0, 2.0, 3.0]))
        data2 = IndicatorInput(close=pd.Series([4.0, 5.0, 6.0]))
        
        indicator.calculate_with_cache(data1)
        assert indicator.calc_count == 1
        
        indicator.calculate_with_cache(data2)
        assert indicator.calc_count == 2  # New calculation
    
    def test_clear_cache(self):
        """Test cache clearing."""
        indicator = SimpleCachedIndicator()
        data = IndicatorInput(close=pd.Series([1.0, 2.0, 3.0]))
        
        # Calculate and cache
        indicator.calculate_with_cache(data)
        assert indicator._cache is not None
        
        # Clear cache
        indicator.clear_cache()
        assert indicator._cache is None
        assert indicator._cache_key is None


class TestIndicatorProtocol:
    """Tests for indicator protocol compliance."""
    
    def test_mock_indicator_follows_protocol(self):
        """Test that MockIndicator follows IndicatorProtocol."""
        indicator = MockIndicator(period=10)
        
        # Should have required attributes and methods
        assert hasattr(indicator, 'name')
        assert hasattr(indicator, 'calculate')
        assert hasattr(indicator, 'validate_input')
        assert callable(indicator.calculate)
        assert callable(indicator.validate_input)


class TestSMA:
    """Tests for Simple Moving Average (SMA) indicator."""
    
    def test_sma_initialization(self):
        """Test SMA initialization with default and custom periods."""
        # Default period
        sma_default = SMA()
        assert sma_default.name == "SMA"
        assert sma_default.period == 20
        assert sma_default.params == {"period": 20}
        
        # Custom period
        sma_custom = SMA(period=10)
        assert sma_custom.period == 10
        assert sma_custom.params == {"period": 10}
    
    def test_sma_invalid_period_raises_error(self):
        """Test that invalid period raises error."""
        with pytest.raises(IndicatorError):
            SMA(period=0)
        with pytest.raises(IndicatorError):
            SMA(period=-5)
    
    def test_sma_calculation(self):
        """Test SMA calculation accuracy."""
        # Test data: [1, 2, 3, 4, 5]
        # SMA(3): [nan, nan, 2, 3, 4]
        prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        sma = SMA(period=3)
        data = IndicatorInput(close=prices)
        
        result = sma.calculate(data)
        
        # Check values (first 2 should be NaN with min_periods=1, but we use min_periods=1)
        expected_values = [1.0, 1.5, 2.0, 3.0, 4.0]  # With min_periods=1
        np.testing.assert_array_almost_equal(result.values.values, expected_values)
        
        # Check metadata
        assert result.metadata["period"] == 3
        assert result.metadata["method"] == "simple"
    
    def test_sma_insufficient_data_raises_error(self):
        """Test that insufficient data raises error."""
        sma = SMA(period=10)
        short_data = IndicatorInput(close=pd.Series([1.0, 2.0, 3.0]))
        
        with pytest.raises(IndicatorError, match="Insufficient data"):
            sma.calculate(short_data)
    
    def test_sma_input_validation(self):
        """Test SMA input validation."""
        sma = SMA(period=5)
        
        # Valid input
        valid_data = IndicatorInput(close=pd.Series(range(10)))
        assert sma.validate_input(valid_data)
        
        # Invalid input (too short)
        invalid_data = IndicatorInput(close=pd.Series(range(3)))
        assert not sma.validate_input(invalid_data)
        
        # Empty data
        empty_data = IndicatorInput(close=pd.Series([]))
        assert not sma.validate_input(empty_data)
    
    def test_sma_signal_generation(self):
        """Test SMA trading signal generation."""
        # Create price data that crosses SMA
        prices = pd.Series([10, 11, 12, 11, 10, 9, 10, 11, 12])  # Price goes down then up
        sma = SMA(period=3)
        data = IndicatorInput(close=prices)
        
        result = sma.calculate(data)
        
        # Should have signals
        assert result.signals is not None
        assert len(result.signals) == len(prices)
        
        # Signals should be -1, 0, or 1
        unique_signals = set(result.signals.dropna().unique())
        assert unique_signals.issubset({-1, 0, 1})
    
    def test_sma_min_bars_required(self):
        """Test SMA minimum bars requirement."""
        sma = SMA(period=15)
        assert sma.get_min_bars_required() == 15


class TestEMA:
    """Tests for Exponential Moving Average (EMA) indicator."""
    
    def test_ema_initialization(self):
        """Test EMA initialization with default and custom periods."""
        # Default period
        ema_default = EMA()
        assert ema_default.name == "EMA"
        assert ema_default.period == 20
        assert ema_default.params == {"period": 20}
        
        # Custom period
        ema_custom = EMA(period=10)
        assert ema_custom.period == 10
        assert ema_custom.params == {"period": 10}
        # Alpha should be 2/(period+1)
        expected_alpha = 2.0 / (10 + 1)
        assert ema_custom._alpha == expected_alpha
    
    def test_ema_invalid_period_raises_error(self):
        """Test that invalid period raises error."""
        with pytest.raises(IndicatorError):
            EMA(period=0)
        with pytest.raises(IndicatorError):
            EMA(period=-5)
    
    def test_ema_calculation(self):
        """Test EMA calculation accuracy."""
        # Simple test data
        prices = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0])
        ema = EMA(period=3)
        data = IndicatorInput(close=prices)
        
        result = ema.calculate(data)
        
        # EMA should be calculated correctly
        assert len(result.values) == len(prices)
        assert not result.values.isna().all()
        
        # EMA should be more responsive than SMA (closer to recent prices)
        sma = SMA(period=3)
        sma_result = sma.calculate(data)
        
        # Last EMA should be closer to last price than SMA
        last_price = prices.iloc[-1]
        last_ema = result.values.iloc[-1]
        last_sma = sma_result.values.iloc[-1]
        
        ema_distance = abs(last_ema - last_price)
        sma_distance = abs(last_sma - last_price)
        
        # EMA should be closer to recent price (smaller distance)
        assert ema_distance <= sma_distance
        
        # Check metadata
        assert result.metadata["period"] == 3
        assert result.metadata["method"] == "exponential"
        assert "alpha" in result.metadata
    
    def test_ema_insufficient_data_raises_error(self):
        """Test that insufficient data raises error."""
        ema = EMA(period=10)
        short_data = IndicatorInput(close=pd.Series([1.0, 2.0, 3.0]))
        
        with pytest.raises(IndicatorError, match="Insufficient data"):
            ema.calculate(short_data)
    
    def test_ema_input_validation(self):
        """Test EMA input validation."""
        ema = EMA(period=5)
        
        # Valid input
        valid_data = IndicatorInput(close=pd.Series(range(10)))
        assert ema.validate_input(valid_data)
        
        # Invalid input (too short)
        invalid_data = IndicatorInput(close=pd.Series(range(3)))
        assert not ema.validate_input(invalid_data)
        
        # Empty data
        empty_data = IndicatorInput(close=pd.Series([]))
        assert not ema.validate_input(empty_data)
    
    def test_ema_signal_generation(self):
        """Test EMA trading signal generation."""
        # Create price data that crosses EMA
        prices = pd.Series([10, 11, 12, 11, 10, 9, 10, 11, 12])  # Price goes down then up
        ema = EMA(period=3)
        data = IndicatorInput(close=prices)
        
        result = ema.calculate(data)
        
        # Should have signals
        assert result.signals is not None
        assert len(result.signals) == len(prices)
        
        # Signals should be -1, 0, or 1
        unique_signals = set(result.signals.dropna().unique())
        assert unique_signals.issubset({-1, 0, 1})
    
    def test_ema_min_bars_required(self):
        """Test EMA minimum bars requirement."""
        ema = EMA(period=15)
        assert ema.get_min_bars_required() == 15
    
    def test_ema_alpha_calculation(self):
        """Test EMA alpha (smoothing factor) calculation."""
        # Test different periods
        test_cases = [
            (2, 2.0/3),    # α = 2/(2+1) = 2/3
            (5, 2.0/6),    # α = 2/(5+1) = 1/3
            (10, 2.0/11),  # α = 2/(10+1) = 2/11
            (20, 2.0/21),  # α = 2/(20+1) = 2/21
        ]
        
        for period, expected_alpha in test_cases:
            ema = EMA(period=period)
            np.testing.assert_almost_equal(ema._alpha, expected_alpha)
