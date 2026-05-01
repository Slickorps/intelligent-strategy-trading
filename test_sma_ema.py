#!/usr/bin/env python3
"""Simple test script for SMA and EMA indicators."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np

# Test the indicators directly
from ist.strategy.indicators.moving_averages import SMA, EMA
from ist.strategy.indicators.base import IndicatorInput

def test_sma():
    """Test SMA indicator."""
    print("Testing SMA...")
    
    # Test data
    prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    sma = SMA(period=3)
    data = IndicatorInput(close=prices)
    
    result = sma.calculate(data)
    print(f"SMA values: {result.values}")
    print(f"SMA metadata: {result.metadata}")
    
    # Test validation
    assert sma.validate_input(data)
    assert sma.get_min_bars_required() == 3
    
    # Test insufficient data
    short_data = IndicatorInput(close=pd.Series([1.0, 2.0]))
    assert not sma.validate_input(short_data)
    
    print("SMA tests passed!")

def test_ema():
    """Test EMA indicator."""
    print("\nTesting EMA...")
    
    # Test data
    prices = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0])
    ema = EMA(period=3)
    data = IndicatorInput(close=prices)
    
    result = ema.calculate(data)
    print(f"EMA values: {result.values}")
    print(f"EMA metadata: {result.metadata}")
    
    # Test alpha calculation
    expected_alpha = 2.0 / (3 + 1)
    assert ema._alpha == expected_alpha
    
    # Test validation
    assert ema.validate_input(data)
    assert ema.get_min_bars_required() == 3
    
    print("EMA tests passed!")

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
    print(f"Last SMA: {last_sma}, distance: {sma_distance}")
    print(f"Last EMA: {last_ema}, distance: {ema_distance}")
    
    # EMA should be closer to recent price
    assert ema_distance <= sma_distance
    print("EMA is more responsive than SMA - test passed!")

if __name__ == "__main__":
    try:
        test_sma()
        test_ema()
        test_comparison()
        print("\n🎉 All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
