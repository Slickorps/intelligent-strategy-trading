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
    RSI,
    MACD,
    ATR,
    BollingerBands,
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


class TestRSI:
    """Tests for Relative Strength Index (RSI) indicator."""
    
    def test_rsi_initialization_default(self):
        """Test RSI initialization with default parameters."""
        rsi = RSI()
        assert rsi.name == "RSI"
        assert rsi.period == 14
        assert rsi.overbought == 70.0
        assert rsi.oversold == 30.0
        assert rsi.params == {"period": 14, "overbought": 70.0, "oversold": 30.0}
    
    def test_rsi_initialization_custom(self):
        """Test RSI initialization with custom parameters."""
        rsi = RSI(period=10, overbought=80, oversold=20)
        assert rsi.period == 10
        assert rsi.overbought == 80.0
        assert rsi.oversold == 20.0
    
    def test_rsi_invalid_period_raises_error(self):
        """Test that invalid period raises error."""
        with pytest.raises(IndicatorError):
            RSI(period=1)  # RSI needs at least 2 periods
        with pytest.raises(IndicatorError):
            RSI(period=0)
    
    def test_rsi_invalid_thresholds_raises_error(self):
        """Test that invalid thresholds raise error."""
        # Overbought <= oversold
        with pytest.raises(IndicatorError):
            RSI(overbought=30, oversold=70)
        with pytest.raises(IndicatorError):
            RSI(overbought=30, oversold=30)
        # Thresholds outside 0-100
        with pytest.raises(IndicatorError):
            RSI(overbought=110)
        with pytest.raises(IndicatorError):
            RSI(oversold=-10)
    
    def test_rsi_calculation_basic(self):
        """Test RSI calculation with basic price data."""
        # Create price data with upward trend
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        rsi = RSI(period=5)  # Use shorter period for test
        data = IndicatorInput(close=prices)
        
        result = rsi.calculate(data)
        
        # RSI should be calculated
        assert len(result.values) == len(prices)
        # With upward trend, RSI should be high (close to 100)
        assert result.values.iloc[-1] > 50
        # RSI values should be between 0 and 100
        assert (result.values >= 0).all()
        assert (result.values <= 100).all()
    
    def test_rsi_calculation_downtrend(self):
        """Test RSI calculation during downtrend."""
        # Create price data with downward trend
        prices = pd.Series([20.0, 19.0, 18.0, 17.0, 16.0, 15.0, 14.0, 13.0, 12.0, 11.0, 10.0])
        rsi = RSI(period=5)
        data = IndicatorInput(close=prices)
        
        result = rsi.calculate(data)
        
        # With downward trend, RSI should be low
        assert result.values.iloc[-1] < 50
    
    def test_rsi_insufficient_data_raises_error(self):
        """Test that insufficient data raises error."""
        rsi = RSI(period=10)
        # Need period + 1 data points
        short_data = IndicatorInput(close=pd.Series(range(10)))
        
        with pytest.raises(IndicatorError, match="Insufficient data"):
            rsi.calculate(short_data)
    
    def test_rsi_input_validation(self):
        """Test RSI input validation."""
        rsi = RSI(period=5)
        
        # Valid input (need 6 data points for period=5)
        valid_data = IndicatorInput(close=pd.Series(range(10)))
        assert rsi.validate_input(valid_data)
        
        # Invalid input (too short)
        invalid_data = IndicatorInput(close=pd.Series(range(5)))
        assert not rsi.validate_input(invalid_data)
        
        # Empty data
        empty_data = IndicatorInput(close=pd.Series([]))
        assert not rsi.validate_input(empty_data)
    
    def test_rsi_min_bars_required(self):
        """Test RSI minimum bars requirement."""
        rsi = RSI(period=14)
        # RSI needs period + 1 bars because of diff()
        assert rsi.get_min_bars_required() == 15
    
    def test_rsi_overbought_oversold_checks(self):
        """Test overbought and oversold check methods."""
        rsi = RSI(overbought=70, oversold=30)
        
        assert rsi.is_overbought(75)
        assert rsi.is_overbought(70)
        assert not rsi.is_overbought(69)
        
        assert rsi.is_oversold(25)
        assert rsi.is_oversold(30)
        assert not rsi.is_oversold(31)
    
    def test_rsi_bands_in_result(self):
        """Test that RSI result includes overbought/oversold bands."""
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        rsi = RSI(period=5, overbought=75, oversold=25)
        data = IndicatorInput(close=prices)
        
        result = rsi.calculate(data)
        
        # Result should include upper and lower bands
        assert result.upper_band is not None
        assert result.lower_band is not None
        # Bands should match thresholds
        assert result.upper_band.iloc[0] == 75
        assert result.lower_band.iloc[0] == 25
    
    def test_rsi_signal_generation(self):
        """Test RSI signal generation."""
        # Create price data that enters and exits oversold/overbought zones
        # Pattern: neutral -> oversold -> neutral -> overbought -> neutral
        prices = pd.Series([
            50, 48, 46, 44, 42, 40, 38,  # Downward to oversold
            40, 42, 44, 46, 48, 50, 52,  # Upward to neutral then overbought
            80, 82, 84,                  # Upward to overbought
            82, 80, 78, 76               # Downward back to neutral
        ])
        rsi = RSI(period=5, overbought=70, oversold=30)
        data = IndicatorInput(close=prices)
        
        result = rsi.calculate(data)
        
        # Should have signals
        assert result.signals is not None
        assert len(result.signals) == len(prices)
        
        # Signals should be -1, 0, or 1
        unique_signals = set(result.signals.dropna().unique())
        assert unique_signals.issubset({-1, 0, 1})
        
        # Buy signals should occur when leaving oversold
        # Sell signals should occur when leaving overbought
    
    def test_rsi_signal_description(self):
        """Test RSI signal description method."""
        rsi = RSI(overbought=70, oversold=30)
        
        desc_buy = rsi.get_signal_description(1)
        desc_sell = rsi.get_signal_description(-1)
        desc_hold = rsi.get_signal_description(0)
        
        assert "Buy" in desc_buy or "buy" in desc_buy
        assert "Sell" in desc_sell or "sell" in desc_sell
        assert "Hold" in desc_hold or "hold" in desc_hold or "neutral" in desc_hold
    
    def test_rsi_metadata(self):
        """Test RSI metadata in result."""
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        rsi = RSI(period=3, overbought=80, oversold=20)
        data = IndicatorInput(close=prices)
        
        result = rsi.calculate(data)
        
        assert "period" in result.metadata
        assert "overbought" in result.metadata
        assert "oversold" in result.metadata
        assert "method" in result.metadata
        assert result.metadata["period"] == 3
        assert result.metadata["overbought"] == 80
        assert result.metadata["oversold"] == 20


class TestMACD:
    """Tests for Moving Average Convergence Divergence (MACD) indicator."""
    
    def test_macd_initialization_default(self):
        """Test MACD initialization with default parameters."""
        macd = MACD()
        assert macd.name == "MACD"
        assert macd.fast_period == 12
        assert macd.slow_period == 26
        assert macd.signal_period == 9
        assert macd.params == {"fast_period": 12, "slow_period": 26, "signal_period": 9}
    
    def test_macd_initialization_custom(self):
        """Test MACD initialization with custom parameters."""
        macd = MACD(fast_period=5, slow_period=15, signal_period=5)
        assert macd.fast_period == 5
        assert macd.slow_period == 15
        assert macd.signal_period == 5
    
    def test_macd_invalid_periods_raises_error(self):
        """Test that invalid periods raise error."""
        # Fast >= slow
        with pytest.raises(IndicatorError):
            MACD(fast_period=26, slow_period=12)
        with pytest.raises(IndicatorError):
            MACD(fast_period=26, slow_period=26)
        # Period < 1
        with pytest.raises(IndicatorError):
            MACD(fast_period=0)
        with pytest.raises(IndicatorError):
            MACD(slow_period=0)
        with pytest.raises(IndicatorError):
            MACD(signal_period=0)
    
    def test_macd_calculation_structure(self):
        """Test MACD calculation produces correct structure."""
        # Create sufficient price data
        prices = pd.Series([10.0 + i * 0.5 for i in range(50)])
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        data = IndicatorInput(close=prices)
        
        result = macd.calculate(data)
        
        # Check all components exist
        assert result.values is not None  # MACD line
        assert result.signal_line is not None
        assert result.histogram is not None
        assert result.signals is not None
        
        # Check lengths match
        assert len(result.values) == len(prices)
        assert len(result.signal_line) == len(prices)
        assert len(result.histogram) == len(prices)
        assert len(result.signals) == len(prices)
        
        # Histogram = MACD - Signal
        expected_histogram = result.values - result.signal_line
        pd.testing.assert_series_equal(result.histogram, expected_histogram)
    
    def test_macd_calculation_values(self):
        """Test MACD calculation produces reasonable values."""
        # Create price data with clear trend
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0] * 5)
        macd = MACD(fast_period=3, slow_period=6, signal_period=2)
        data = IndicatorInput(close=prices)
        
        result = macd.calculate(data)
        
        # MACD line should be calculated
        assert not result.values.isna().all()
        # In uptrend, fast EMA > slow EMA, so MACD should be positive
        assert result.values.iloc[-1] > 0
    
    def test_macd_insufficient_data_raises_error(self):
        """Test that insufficient data raises error."""
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        short_data = IndicatorInput(close=pd.Series(range(20)))
        
        with pytest.raises(IndicatorError, match="Insufficient data"):
            macd.calculate(short_data)
    
    def test_macd_input_validation(self):
        """Test MACD input validation."""
        macd = MACD(fast_period=3, slow_period=6, signal_period=2)
        
        # Valid input (need at least slow_period data points)
        valid_data = IndicatorInput(close=pd.Series(range(10)))
        assert macd.validate_input(valid_data)
        
        # Invalid input (too short)
        invalid_data = IndicatorInput(close=pd.Series(range(5)))
        assert not macd.validate_input(invalid_data)
        
        # Empty data
        empty_data = IndicatorInput(close=pd.Series([]))
        assert not macd.validate_input(empty_data)
    
    def test_macd_min_bars_required(self):
        """Test MACD minimum bars requirement."""
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        assert macd.get_min_bars_required() == 26
    
    def test_macd_golden_cross_detection(self):
        """Test golden cross detection."""
        # MACD line crossing above signal line
        macd_line = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 4.0])
        signal_line = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
        
        macd = MACD()
        
        # Golden cross at index 5 (MACD goes from below to above signal)
        assert macd.is_golden_cross(macd_line, signal_line, index=5)
        # Not a golden cross at index 6 (already above)
        assert not macd.is_golden_cross(macd_line, signal_line, index=6)
        # Not a golden cross at index 4 (still below)
        assert not macd.is_golden_cross(macd_line, signal_line, index=4)
    
    def test_macd_death_cross_detection(self):
        """Test death cross detection."""
        # MACD line crossing below signal line
        macd_line = pd.Series([4.0, 3.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0])
        signal_line = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
        
        macd = MACD()
        
        # Death cross at index 5 (MACD goes from above to below signal)
        assert macd.is_death_cross(macd_line, signal_line, index=5)
        # Not a death cross at index 6 (already below)
        assert not macd.is_death_cross(macd_line, signal_line, index=6)
        # Not a death cross at index 4 (still above)
        assert not macd.is_death_cross(macd_line, signal_line, index=4)
    
    def test_macd_crossover_type(self):
        """Test crossover type detection."""
        macd_line = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 4.0])
        signal_line = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
        
        macd = MACD()
        
        assert macd.get_crossover_type(macd_line, signal_line, index=5) == "golden"
        assert macd.get_crossover_type(macd_line, signal_line, index=6) == "none"
        
        # Test death cross
        macd_line2 = pd.Series([4.0, 3.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0])
        signal_line2 = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
        
        assert macd.get_crossover_type(macd_line2, signal_line2, index=5) == "death"
    
    def test_macd_signal_generation(self):
        """Test MACD trading signal generation."""
        # Create price data that produces crossovers
        prices = pd.Series([
            10, 12, 14, 16, 18,  # Uptrend
            17, 16, 15, 14, 13,  # Downtrend
            14, 15, 16, 17, 18,  # Uptrend
        ])
        macd = MACD(fast_period=3, slow_period=6, signal_period=2)
        data = IndicatorInput(close=prices)
        
        result = macd.calculate(data)
        
        # Should have signals
        assert result.signals is not None
        assert len(result.signals) == len(prices)
        
        # Signals should be -1, 0, or 1
        unique_signals = set(result.signals.dropna().unique())
        assert unique_signals.issubset({-1, 0, 1})
        
        # Should have at least one buy or sell signal
        assert (result.signals != 0).any()
    
    def test_macd_signal_description(self):
        """Test MACD signal description method."""
        macd = MACD()
        
        desc_buy = macd.get_signal_description(1)
        desc_sell = macd.get_signal_description(-1)
        desc_hold = macd.get_signal_description(0)
        
        assert "Buy" in desc_buy or "buy" in desc_buy
        assert "golden" in desc_buy.lower() or "crosses above" in desc_buy.lower()
        assert "Sell" in desc_sell or "sell" in desc_sell
        assert "death" in desc_sell.lower() or "crosses below" in desc_sell.lower()
        assert "Hold" in desc_hold or "hold" in desc_hold or "No" in desc_hold
    
    def test_macd_metadata(self):
        """Test MACD metadata in result."""
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0] * 3)
        macd = MACD(fast_period=5, slow_period=10, signal_period=3)
        data = IndicatorInput(close=prices)
        
        result = macd.calculate(data)
        
        assert "fast_period" in result.metadata
        assert "slow_period" in result.metadata
        assert "signal_period" in result.metadata
        assert "method" in result.metadata
        assert result.metadata["fast_period"] == 5
        assert result.metadata["slow_period"] == 10
        assert result.metadata["signal_period"] == 3
        assert result.metadata["method"] == "ema"


class TestATR:
    """Tests for Average True Range (ATR) indicator."""
    
    def test_atr_initialization_default(self):
        """Test ATR initialization with default parameters."""
        atr = ATR()
        assert atr.name == "ATR"
        assert atr.period == 14
        assert atr.use_wilder == True
        assert atr.params == {"period": 14, "use_wilder": True}
    
    def test_atr_initialization_custom(self):
        """Test ATR initialization with custom parameters."""
        atr = ATR(period=10, use_wilder=False)
        assert atr.period == 10
        assert atr.use_wilder == False
        assert atr.params == {"period": 10, "use_wilder": False}
    
    def test_atr_invalid_period_raises_error(self):
        """Test that invalid period raises error."""
        with pytest.raises(IndicatorError):
            ATR(period=0)
        with pytest.raises(IndicatorError):
            ATR(period=-5)
    
    def test_atr_calculation_basic(self):
        """Test ATR calculation with basic price data."""
        high = pd.Series([12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0])
        low = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        close = pd.Series([11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0])
        
        atr = ATR(period=5)
        data = IndicatorInput(high=high, low=low, close=close)
        
        result = atr.calculate(data)
        
        # ATR should be calculated
        assert len(result.values) == len(close)
        # ATR should be positive
        assert (result.values > 0).all()
        # First value uses simple average of first period
        assert not pd.isna(result.values.iloc[5])
    
    def test_atr_requires_ohlc_data(self):
        """Test that ATR requires high, low, close data."""
        atr = ATR(period=5)
        
        # Missing high
        with pytest.raises(IndicatorError):
            data = IndicatorInput(low=pd.Series([1, 2, 3]), close=pd.Series([2, 3, 4]))
            atr.calculate(data)
        
        # Missing low
        with pytest.raises(IndicatorError):
            data = IndicatorInput(high=pd.Series([3, 4, 5]), close=pd.Series([2, 3, 4]))
            atr.calculate(data)
    
    def test_atr_insufficient_data_raises_error(self):
        """Test that insufficient data raises error."""
        atr = ATR(period=10)
        high = pd.Series(range(10))
        low = pd.Series(range(10))
        close = pd.Series(range(10))
        short_data = IndicatorInput(high=high, low=low, close=close)
        
        with pytest.raises(IndicatorError, match="Insufficient data"):
            atr.calculate(short_data)
    
    def test_atr_input_validation(self):
        """Test ATR input validation."""
        atr = ATR(period=5)
        
        # Valid input (need period + 1 data points)
        high = pd.Series(range(15))
        low = pd.Series(range(15))
        close = pd.Series(range(15))
        valid_data = IndicatorInput(high=high, low=low, close=close)
        assert atr.validate_input(valid_data)
        
        # Invalid input (too short)
        high_short = pd.Series(range(5))
        low_short = pd.Series(range(5))
        close_short = pd.Series(range(5))
        invalid_data = IndicatorInput(high=high_short, low=low_short, close=close_short)
        assert not atr.validate_input(invalid_data)
    
    def test_atr_min_bars_required(self):
        """Test ATR minimum bars requirement."""
        atr = ATR(period=14)
        # ATR needs period + 1 bars for true range calculation
        assert atr.get_min_bars_required() == 15
    
    def test_atr_wilder_vs_sma(self):
        """Test ATR with Wilder's smoothing vs SMA."""
        high = pd.Series([12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0])
        low = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        close = pd.Series([11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0])
        data = IndicatorInput(high=high, low=low, close=close)
        
        atr_wilder = ATR(period=5, use_wilder=True)
        atr_sma = ATR(period=5, use_wilder=False)
        
        result_wilder = atr_wilder.calculate(data)
        result_sma = atr_sma.calculate(data)
        
        # Both should produce valid results
        assert len(result_wilder.values) == len(close)
        assert len(result_sma.values) == len(close)
        
        # Metadata should reflect method
        assert result_wilder.metadata["method"] == "wilder"
        assert result_sma.metadata["method"] == "sma"
    
    def test_atr_metadata(self):
        """Test ATR metadata in result."""
        high = pd.Series([12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0])
        low = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        close = pd.Series([11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0])
        
        atr = ATR(period=5, use_wilder=True)
        data = IndicatorInput(high=high, low=low, close=close)
        
        result = atr.calculate(data)
        
        assert "period" in result.metadata
        assert "use_wilder" in result.metadata
        assert "method" in result.metadata
        assert result.metadata["period"] == 5
        assert result.metadata["use_wilder"] == True


class TestBollingerBands:
    """Tests for Bollinger Bands indicator."""
    
    def test_bb_initialization_default(self):
        """Test Bollinger Bands initialization with default parameters."""
        bb = BollingerBands()
        assert bb.name == "BollingerBands"
        assert bb.period == 20
        assert bb.multiplier == 2.0
        assert bb.params == {"period": 20, "multiplier": 2.0}
    
    def test_bb_initialization_custom(self):
        """Test Bollinger Bands initialization with custom parameters."""
        bb = BollingerBands(period=10, multiplier=1.5)
        assert bb.period == 10
        assert bb.multiplier == 1.5
    
    def test_bb_invalid_params_raises_error(self):
        """Test that invalid parameters raise error."""
        with pytest.raises(IndicatorError):
            BollingerBands(period=1)  # Period must be >= 2
        with pytest.raises(IndicatorError):
            BollingerBands(period=0)
        with pytest.raises(IndicatorError):
            BollingerBands(multiplier=0)  # Multiplier must be > 0
        with pytest.raises(IndicatorError):
            BollingerBands(multiplier=-1)
    
    def test_bb_calculation_structure(self):
        """Test Bollinger Bands calculation produces correct structure."""
        # Create price data
        prices = pd.Series([10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0, 16.0, 15.0])
        
        bb = BollingerBands(period=5, multiplier=2.0)
        data = IndicatorInput(close=prices)
        
        result = bb.calculate(data)
        
        # Check all components exist
        assert result.values is not None  # Middle band (SMA)
        assert result.upper_band is not None
        assert result.lower_band is not None
        assert result.histogram is not None  # Bandwidth
        assert result.signals is not None
        
        # Check lengths match
        assert len(result.values) == len(prices)
        assert len(result.upper_band) == len(prices)
        assert len(result.lower_band) == len(prices)
        assert len(result.histogram) == len(prices)
    
    def test_bb_band_relationships(self):
        """Test Bollinger Bands mathematical relationships."""
        prices = pd.Series([10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0, 16.0, 15.0])
        
        bb = BollingerBands(period=5, multiplier=2.0)
        data = IndicatorInput(close=prices)
        
        result = bb.calculate(data)
        
        # Upper band should be >= middle band
        assert (result.upper_band >= result.values).all()
        # Lower band should be <= middle band
        assert (result.lower_band <= result.values).all()
        # Upper band should be >= lower band
        assert (result.upper_band >= result.lower_band).all()
    
    def test_bb_calculation_values(self):
        """Test Bollinger Bands calculation produces reasonable values."""
        # Create price data with known values
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        
        bb = BollingerBands(period=5, multiplier=2.0)
        data = IndicatorInput(close=prices)
        
        result = bb.calculate(data)
        
        # Middle band should be SMA
        expected_middle = prices.rolling(window=5, min_periods=1).mean().iloc[-1]
        assert abs(result.values.iloc[-1] - expected_middle) < 0.01
    
    def test_bb_insufficient_data_raises_error(self):
        """Test that insufficient data raises error."""
        bb = BollingerBands(period=10)
        short_data = IndicatorInput(close=pd.Series(range(5)))
        
        with pytest.raises(IndicatorError, match="Insufficient data"):
            bb.calculate(short_data)
    
    def test_bb_input_validation(self):
        """Test Bollinger Bands input validation."""
        bb = BollingerBands(period=5)
        
        # Valid input
        valid_data = IndicatorInput(close=pd.Series(range(10)))
        assert bb.validate_input(valid_data)
        
        # Invalid input (too short)
        invalid_data = IndicatorInput(close=pd.Series(range(3)))
        assert not bb.validate_input(invalid_data)
        
        # Empty data
        empty_data = IndicatorInput(close=pd.Series([]))
        assert not bb.validate_input(empty_data)
    
    def test_bb_min_bars_required(self):
        """Test Bollinger Bands minimum bars requirement."""
        bb = BollingerBands(period=20)
        assert bb.get_min_bars_required() == 20
    
    def test_bb_percent_b_calculation(self):
        """Test %b calculation methods."""
        bb = BollingerBands(period=5, multiplier=2.0)
        
        # Test get_percent_b method
        percent_b = bb.get_percent_b(price=15.0, upper=20.0, lower=10.0)
        assert percent_b == 0.5  # Halfway between lower and upper
        
        percent_b_lower = bb.get_percent_b(price=10.0, upper=20.0, lower=10.0)
        assert percent_b_lower == 0.0  # At lower band
        
        percent_b_upper = bb.get_percent_b(price=20.0, upper=20.0, lower=10.0)
        assert percent_b_upper == 1.0  # At upper band
        
        # Edge case: upper == lower
        percent_b_edge = bb.get_percent_b(price=15.0, upper=10.0, lower=10.0)
        assert percent_b_edge == 0.5  # Should return 0.5 to avoid division by zero
    
    def test_bb_bandwidth_calculation(self):
        """Test bandwidth calculation methods."""
        bb = BollingerBands(period=5, multiplier=2.0)
        
        # Test get_bandwidth method
        bandwidth = bb.get_bandwidth(upper=22.0, lower=18.0, middle=20.0)
        assert bandwidth == 20.0  # ((22-18)/20) * 100 = 20%
        
        # Edge case: middle == 0
        bandwidth_zero = bb.get_bandwidth(upper=2.0, lower=-2.0, middle=0.0)
        assert bandwidth_zero == 0.0
    
    def test_bb_price_position_checks(self):
        """Test price position relative to bands."""
        bb = BollingerBands(period=5, multiplier=2.0)
        
        # Above upper band
        assert bb.is_price_above_upper(price=25.0, upper_band=22.0)
        assert not bb.is_price_above_upper(price=20.0, upper_band=22.0)
        
        # Below lower band
        assert bb.is_price_below_lower(price=15.0, lower_band=18.0)
        assert not bb.is_price_below_lower(price=20.0, lower_band=18.0)
    
    def test_bb_signal_generation(self):
        """Test Bollinger Bands trading signal generation."""
        # Create price data that touches bands
        prices = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 20.0, 16.0, 12.0, 8.0, 12.0, 16.0])
        
        bb = BollingerBands(period=5, multiplier=1.5)
        data = IndicatorInput(close=prices)
        
        result = bb.calculate(data)
        
        # Should have signals
        assert result.signals is not None
        assert len(result.signals) == len(prices)
        
        # Signals should be -1, 0, or 1
        unique_signals = set(result.signals.dropna().unique())
        assert unique_signals.issubset({-1, 0, 1})
    
    def test_bb_signal_description(self):
        """Test Bollinger Bands signal description method."""
        bb = BollingerBands()
        
        desc_buy = bb.get_signal_description(1)
        desc_sell = bb.get_signal_description(-1)
        desc_hold = bb.get_signal_description(0)
        
        assert "Buy" in desc_buy or "buy" in desc_buy
        assert "Sell" in desc_sell or "sell" in desc_sell
        assert "Hold" in desc_hold or "hold" in desc_hold or "within" in desc_hold
    
    def test_bb_metadata(self):
        """Test Bollinger Bands metadata in result."""
        prices = pd.Series([10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0, 16.0, 15.0])
        bb = BollingerBands(period=5, multiplier=2.0)
        data = IndicatorInput(close=prices)
        
        result = bb.calculate(data)
        
        assert "period" in result.metadata
        assert "multiplier" in result.metadata
        assert "method" in result.metadata
        assert "percent_b" in result.metadata
        assert result.metadata["period"] == 5
        assert result.metadata["multiplier"] == 2.0
        assert result.metadata["method"] == "sma"
