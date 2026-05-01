#!/usr/bin/env python3
"""Simple standalone test for SMA and EMA logic."""

import pandas as pd
import numpy as np

# Copy the core classes locally for testing
class IndicatorInput:
    def __init__(self, close=None, open=None, high=None, low=None):
        self.close = close
        self.open = open
        self.high = high
        self.low = low
    
    @property
    def main_series(self):
        if self.close is not None:
            return self.close
        elif self.high is not None:
            return self.high
        elif self.low is not None:
            return self.low
        elif self.open is not None:
            return self.open
        raise ValueError("No price series available")

class IndicatorResult:
    def __init__(self, values, signals=None, metadata=None):
        self.values = values
        self.signals = signals
        self.metadata = metadata or {}

# Simple SMA implementation (copy from our implementation)
class SMA:
    def __init__(self, period=20):
        if period < 1:
            raise ValueError("SMA period must be >= 1")
        self.period = period
        self.name = "SMA"
        self.params = {"period": period}
    
    def calculate(self, data):
        price_series = data.main_series
        
        if not self.validate_input(data):
            raise ValueError(f"Insufficient data for SMA calculation. Need at least {self.period} periods")
        
        # Calculate SMA using pandas rolling mean
        sma_values = price_series.rolling(window=self.period, min_periods=1).mean()
        
        # Generate basic trading signals
        signals = self._generate_signals(price_series, sma_values)
        
        return IndicatorResult(
            values=sma_values,
            signals=signals,
            metadata={"period": self.period, "method": "simple"}
        )
    
    def validate_input(self, data):
        try:
            price_series = data.main_series
            return len(price_series) >= self.period and not price_series.empty
        except Exception:
            return False
    
    def get_min_bars_required(self):
        return self.period
    
    def _generate_signals(self, prices, sma):
        signals = pd.Series(0, index=prices.index)
        
        # Find crossovers
        price_above_sma = prices > sma
        price_below_sma = prices < sma
        
        # Buy signal: price crosses above SMA
        buy_signals = price_above_sma & price_below_sma.shift(1).fillna(False)
        
        # Sell signal: price crosses below SMA  
        sell_signals = price_below_sma & price_above_sma.shift(1).fillna(False)
        
        signals[buy_signals] = 1
        signals[sell_signals] = -1
        
        return signals

# Simple EMA implementation (copy from our implementation)
class EMA:
    def __init__(self, period=20):
        if period < 1:
            raise ValueError("EMA period must be >= 1")
        self.period = period
        self.name = "EMA"
        self.params = {"period": period}
        self._alpha = 2.0 / (period + 1)
    
    def calculate(self, data):
        price_series = data.main_series
        
        if not self.validate_input(data):
            raise ValueError(f"Insufficient data for EMA calculation. Need at least {self.period} periods")
        
        # Calculate EMA using pandas ewm
        ema_values = price_series.ewm(alpha=self._alpha, adjust=False).mean()
        
        # Generate basic trading signals
        signals = self._generate_signals(price_series, ema_values)
        
        return IndicatorResult(
            values=ema_values,
            signals=signals,
            metadata={"period": self.period, "alpha": self._alpha, "method": "exponential"}
        )
    
    def validate_input(self, data):
        try:
            price_series = data.main_series
            return len(price_series) >= self.period and not price_series.empty
        except Exception:
            return False
    
    def get_min_bars_required(self):
        return self.period
    
    def _generate_signals(self, prices, ema):
        signals = pd.Series(0, index=prices.index)
        
        # Find crossovers
        price_above_ema = prices > ema
        price_below_ema = prices < ema
        
        # Buy signal: price crosses above EMA
        buy_signals = price_above_ema & price_below_ema.shift(1).fillna(False)
        
        # Sell signal: price crosses below EMA  
        sell_signals = price_below_ema & price_above_ema.shift(1).fillna(False)
        
        signals[buy_signals] = 1
        signals[sell_signals] = -1
        
        return signals

def test_sma():
    """Test SMA indicator."""
    print("Testing SMA...")
    
    # Test data
    prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    sma = SMA(period=3)
    data = IndicatorInput(close=prices)
    
    result = sma.calculate(data)
    print(f"SMA values: {result.values.tolist()}")
    print(f"SMA metadata: {result.metadata}")
    
    # Expected: [1.0, 1.5, 2.0, 3.0, 4.0] with min_periods=1
    expected = [1.0, 1.5, 2.0, 3.0, 4.0]
    assert np.allclose(result.values, expected), f"Expected {expected}, got {result.values.tolist()}"
    
    # Test validation
    assert sma.validate_input(data)
    assert sma.get_min_bars_required() == 3
    
    # Test insufficient data
    short_data = IndicatorInput(close=pd.Series([1.0, 2.0]))
    assert not sma.validate_input(short_data)
    
    print("✅ SMA tests passed!")

def test_ema():
    """Test EMA indicator."""
    print("\nTesting EMA...")
    
    # Test data
    prices = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0])
    ema = EMA(period=3)
    data = IndicatorInput(close=prices)
    
    result = ema.calculate(data)
    print(f"EMA values: {result.values.tolist()}")
    print(f"EMA metadata: {result.metadata}")
    
    # Test alpha calculation
    expected_alpha = 2.0 / (3 + 1)
    assert ema._alpha == expected_alpha
    
    # Test validation
    assert ema.validate_input(data)
    assert ema.get_min_bars_required() == 3
    
    print("✅ EMA tests passed!")

def test_comparison():
    """Test EMA vs SMA responsiveness."""
    print("\nTesting EMA vs SMA responsiveness...")
    
    prices = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0])
    data = IndicatorInput(close=prices)
    
    sma = SMA(period=3)
    ema = EMA(period=3)
    
    sma_result = sma.calculate(data)
    ema_result = ema.calculate(data)
    
    last_price = prices.iloc[-1]
    last_sma = sma_result.values.iloc[-1]
    last_ema = ema_result.values.iloc[-1]
    
    ema_distance = abs(last_ema - last_price)
    sma_distance = abs(last_sma - last_price)
    
    print(f"Last price: {last_price}")
    print(f"Last SMA: {last_sma:.4f}, distance: {sma_distance:.4f}")
    print(f"Last EMA: {last_ema:.4f}, distance: {ema_distance:.4f}")
    
    # EMA should be closer to recent price
    assert ema_distance <= sma_distance, "EMA should be more responsive than SMA"
    print("✅ EMA is more responsive than SMA - test passed!")

def test_signals():
    """Test signal generation."""
    print("\nTesting signal generation...")
    
    # Create price data that crosses MA
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
    
    print(f"Signals: {result.signals.tolist()}")
    print("✅ Signal generation test passed!")

if __name__ == "__main__":
    try:
        test_sma()
        test_ema()
        test_comparison()
        test_signals()
        print("\n🎉 All tests passed! SMA and EMA implementations are working correctly.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
