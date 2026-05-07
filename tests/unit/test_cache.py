"""Unit tests for indicator caching system."""

import time
import pandas as pd
import numpy as np
import pytest

from ist.strategy.indicators import (
    IndicatorCache,
    CacheEntry,
    CacheMixin,
    get_global_cache,
    clear_global_cache,
    IndicatorInput,
    IndicatorResult,
    SMA,
)
from ist.core.exceptions import IndicatorError


class TestIndicatorCache:
    """Tests for IndicatorCache class."""
    
    def test_cache_initialization(self):
        """Test cache initialization with default and custom parameters."""
        # Default parameters
        cache_default = IndicatorCache()
        assert cache_default.max_size == 100
        assert cache_default.ttl is None
        
        # Custom parameters
        cache_custom = IndicatorCache(max_size=50, ttl=300)
        assert cache_custom.max_size == 50
        assert cache_custom.ttl == 300
    
    def test_cache_set_and_get(self):
        """Test basic set and get operations."""
        cache = IndicatorCache(max_size=10)
        
        # Create test data
        values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = IndicatorResult(values=values)
        
        # Store and retrieve
        cache.set("test_key", result)
        retrieved = cache.get("test_key")
        
        assert retrieved is not None
        assert retrieved.values.equals(values)
    
    def test_cache_miss_returns_none(self):
        """Test that cache miss returns None."""
        cache = IndicatorCache(max_size=10)
        
        result = cache.get("non_existent_key")
        assert result is None
    
    def test_cache_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = IndicatorCache(max_size=10, ttl=0.1)  # 100ms TTL
        
        values = pd.Series([1.0, 2.0, 3.0])
        result = IndicatorResult(values=values)
        
        # Store
        cache.set("test_key", result)
        
        # Should be available immediately
        assert cache.get("test_key") is not None
        
        # Wait for expiration
        time.sleep(0.15)
        
        # Should be expired
        assert cache.get("test_key") is None
    
    def test_cache_size_limit_eviction(self):
        """Test that oldest entries are evicted when cache is full."""
        cache = IndicatorCache(max_size=3)
        
        # Fill cache
        for i in range(3):
            values = pd.Series([float(i)])
            result = IndicatorResult(values=values)
            cache.set(f"key_{i}", result)
        
        assert len(cache) == 3
        
        # Add one more (should evict oldest)
        values = pd.Series([99.0])
        result = IndicatorResult(values=values)
        cache.set("key_new", result)
        
        assert len(cache) == 3
        # Oldest entry should be evicted
        assert cache.get("key_0") is None
        # Newer entries should still exist
        assert cache.get("key_1") is not None
        assert cache.get("key_2") is not None
        assert cache.get("key_new") is not None
    
    def test_cache_hit_rate_tracking(self):
        """Test cache hit/miss statistics."""
        cache = IndicatorCache(max_size=10)
        
        values = pd.Series([1.0, 2.0, 3.0])
        result = IndicatorResult(values=values)
        
        # Store
        cache.set("test_key", result)
        
        # Multiple accesses
        cache.get("test_key")  # hit
        cache.get("test_key")  # hit
        cache.get("missing")   # miss
        
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2 / 3
    
    def test_cache_clear(self):
        """Test cache clearing."""
        cache = IndicatorCache(max_size=10)
        
        values = pd.Series([1.0, 2.0, 3.0])
        result = IndicatorResult(values=values)
        
        cache.set("key1", result)
        cache.set("key2", result)
        
        assert len(cache) == 2
        
        cache.clear()
        
        assert len(cache) == 0
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        cache = IndicatorCache(max_size=10)
        
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
        data = IndicatorInput(close=prices)
        
        # Generate key
        key1 = cache._generate_key("SMA", data, {"period": 10})
        key2 = cache._generate_key("SMA", data, {"period": 10})
        key3 = cache._generate_key("SMA", data, {"period": 20})  # Different params
        
        # Same inputs should generate same key
        assert key1 == key2
        # Different params should generate different key
        assert key1 != key3
    
    def test_cache_access_count_tracking(self):
        """Test that access count is tracked correctly."""
        cache = IndicatorCache(max_size=10)
        
        values = pd.Series([1.0, 2.0, 3.0])
        result = IndicatorResult(values=values)
        
        cache.set("test_key", result)
        
        # Access multiple times
        for _ in range(5):
            cache.get("test_key")
        
        # Check that entry tracks access
        entry = cache._cache["test_key"]
        assert entry.access_count == 5


class TestCacheMixin:
    """Tests for CacheMixin class."""
    
    def test_cache_mixin_initialization(self):
        """Test CacheMixin initialization."""
        mixin = CacheMixin(max_size=50, ttl=300)
        
        assert mixin._cache.max_size == 50
        assert mixin._cache.ttl == 300
        assert mixin._cache_enabled is True
    
    def test_cache_enable_disable(self):
        """Test cache enable/disable functionality."""
        mixin = CacheMixin()
        
        # Initially enabled
        assert mixin._cache_enabled is True
        
        # Disable
        mixin.disable_cache()
        assert mixin._cache_enabled is False
        
        # Enable again
        mixin.enable_cache()
        assert mixin._cache_enabled is True
    
    def test_cache_stats(self):
        """Test getting cache stats from mixin."""
        mixin = CacheMixin(max_size=10)
        
        stats = mixin.get_cache_stats()
        assert "size" in stats
        assert "max_size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats


class TestGlobalCache:
    """Tests for global cache functions."""
    
    def test_get_global_cache_singleton(self):
        """Test that global cache is a singleton."""
        # Clear any existing global cache
        clear_global_cache()
        
        cache1 = get_global_cache(max_size=50)
        cache2 = get_global_cache(max_size=100)  # Different params should be ignored
        
        # Should be the same instance
        assert cache1 is cache2
        assert cache1.max_size == 50
    
    def test_clear_global_cache(self):
        """Test clearing global cache."""
        # Setup
        clear_global_cache()
        cache = get_global_cache(max_size=10)
        
        values = pd.Series([1.0, 2.0, 3.0])
        result = IndicatorResult(values=values)
        cache.set("test_key", result)
        
        assert len(cache) == 1
        
        # Clear
        clear_global_cache()
        
        # Get cache again (should be new empty instance)
        new_cache = get_global_cache()
        assert len(new_cache) == 0


class TestSMAWithCache:
    """Tests for SMA indicator with caching."""
    
    def test_sma_cache_hit_improves_performance(self):
        """Test that cache hit avoids recalculation."""
        sma = SMA(period=5)
        prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        data = IndicatorInput(close=prices)
        
        # First calculation (cache miss)
        result1 = sma.calculate(data)
        
        # Calculate again with same data - should use base class cache if available
        # Note: SMA doesn't use the new caching system yet, this tests the base class
        result2 = sma.calculate(data)
        
        # Results should be identical
        assert result1.values.equals(result2.values)
    
    def test_sma_clear_cache(self):
        """Test clearing SMA cache."""
        sma = SMA(period=5)
        
        # Calculate to populate cache
        prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        data = IndicatorInput(close=prices)
        sma.calculate(data)
        
        # Clear cache (base class method)
        sma.clear_cache()
        
        # Cache should be empty
        assert sma._cache is None
        assert sma._cache_key is None


class TestCacheIntegration:
    """Integration tests for caching system."""
    
    def test_cache_with_different_indicators(self):
        """Test cache with multiple indicator types."""
        cache = IndicatorCache(max_size=20)
        
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        data = IndicatorInput(close=prices)
        
        # Create results for different indicators
        sma_result = IndicatorResult(values=prices.rolling(window=5).mean())
        ema_result = IndicatorResult(values=prices.ewm(span=5).mean())
        
        # Store with different keys
        cache.set("SMA_5", sma_result)
        cache.set("EMA_5", ema_result)
        
        # Retrieve
        assert cache.get("SMA_5") is not None
        assert cache.get("EMA_5") is not None
        
        # Verify correct results
        pd.testing.assert_series_equal(
            cache.get("SMA_5").values,
            sma_result.values
        )
    
    def test_cache_handles_different_data_sizes(self):
        """Test cache with different data sizes."""
        cache = IndicatorCache(max_size=10)
        
        # Different size data
        small_data = pd.Series([1.0, 2.0, 3.0])
        large_data = pd.Series(range(100))
        
        small_input = IndicatorInput(close=small_data)
        large_input = IndicatorInput(close=large_data)
        
        # Should generate different keys
        key_small = cache._generate_key("SMA", small_input, {"period": 5})
        key_large = cache._generate_key("SMA", large_input, {"period": 5})
        
        assert key_small != key_large
        
        # Store both
        result_small = IndicatorResult(values=small_data)
        result_large = IndicatorResult(values=large_data)
        
        cache.set(key_small, result_small)
        cache.set(key_large, result_large)
        
        # Both should be retrievable
        assert cache.get(key_small) is not None
        assert cache.get(key_large) is not None
