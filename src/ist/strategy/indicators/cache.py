"""Caching utilities for technical indicators.

This module provides caching mechanisms for indicator calculations,
improving performance when the same calculations are repeated.
"""

import hashlib
import time
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from functools import wraps

import pandas as pd
import numpy as np

from ist.strategy.indicators.base import IndicatorInput, IndicatorResult
from ist.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with metadata.
    
    Attributes:
        result: Cached indicator result
        timestamp: When the entry was created
        access_count: Number of times accessed
        last_accessed: Last access timestamp
    """
    result: IndicatorResult
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)


class IndicatorCache:
    """Cache manager for indicator calculations.
    
    Provides a centralized cache with TTL (time-to-live) support,
    size limits, and hit/miss statistics.
    
    Attributes:
        max_size: Maximum number of entries in cache
        ttl: Time-to-live in seconds (None for no expiration)
        _cache: Internal cache storage
        _hits: Cache hit counter
        _misses: Cache miss counter
    
    Example:
        ```python
        cache = IndicatorCache(max_size=100, ttl=300)  # 5 minute TTL
        
        # Store result
        cache.set(cache_key, indicator_result)
        
        # Retrieve result
        result = cache.get(cache_key)
        if result is not None:
            print("Cache hit!")
        ```
    """
    
    def __init__(self, max_size: int = 100, ttl: Optional[float] = None) -> None:
        """Initialize cache manager.
        
        Args:
            max_size: Maximum number of cache entries
            ttl: Time-to-live in seconds (None for no expiration)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, indicator_name: str, data: IndicatorInput, params: Dict[str, Any]) -> str:
        """Generate a unique cache key.
        
        Args:
            indicator_name: Name of the indicator
            data: Input data
            params: Indicator parameters
            
        Returns:
            Unique cache key string
        """
        # Hash the data values
        main_series = data.main_series
        data_hash = hashlib.md5(main_series.values.tobytes()).hexdigest()[:16]
        
        # Include parameters in key
        params_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
        
        key = f"{indicator_name}_{data_hash}_{len(main_series)}_{params_str}"
        return key
    
    def get(self, key: str) -> Optional[IndicatorResult]:
        """Retrieve item from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached result or None if not found/expired
        """
        if key not in self._cache:
            self._misses += 1
            return None
        
        entry = self._cache[key]
        
        # Check TTL
        if self.ttl is not None:
            if time.time() - entry.timestamp > self.ttl:
                del self._cache[key]
                self._misses += 1
                return None
        
        # Update access stats
        entry.access_count += 1
        entry.last_accessed = time.time()
        self._hits += 1
        
        logger.debug(f"Cache hit for key: {key[:20]}...")
        return entry.result
    
    def set(self, key: str, result: IndicatorResult) -> None:
        """Store item in cache.
        
        Args:
            key: Cache key
            result: Result to cache
        """
        # Evict oldest entries if cache is full
        if len(self._cache) >= self.max_size:
            self._evict_oldest()
        
        self._cache[key] = CacheEntry(result=result)
        logger.debug(f"Cached result for key: {key[:20]}...")
    
    def _evict_oldest(self) -> None:
        """Remove oldest entries when cache is full."""
        if not self._cache:
            return
        
        # Find entry with oldest timestamp
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].timestamp)
        del self._cache[oldest_key]
        logger.debug(f"Evicted oldest cache entry: {oldest_key[:20]}...")
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "ttl": self.ttl
        }
    
    def __len__(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)


# Global cache instance
_global_cache: Optional[IndicatorCache] = None


def get_global_cache(max_size: int = 100, ttl: Optional[float] = None) -> IndicatorCache:
    """Get or create global cache instance.
    
    Args:
        max_size: Maximum cache size
        ttl: Time-to-live in seconds
        
    Returns:
        Global cache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = IndicatorCache(max_size=max_size, ttl=ttl)
    return _global_cache


def clear_global_cache() -> None:
    """Clear the global cache."""
    global _global_cache
    if _global_cache is not None:
        _global_cache.clear()


def cached_indicator(max_size: int = 100, ttl: Optional[float] = None):
    """Decorator to cache indicator calculations.
    
    This decorator wraps an indicator's calculate method with caching.
    
    Args:
        max_size: Maximum cache size
        ttl: Time-to-live in seconds
        
    Example:
        ```python
        class MyIndicator(BaseIndicator):
            @cached_indicator(max_size=50, ttl=300)
            def calculate(self, data: IndicatorInput) -> IndicatorResult:
                # ... calculation logic
                return result
        ```
    """
    def decorator(calculate_method):
        cache = IndicatorCache(max_size=max_size, ttl=ttl)
        
        @wraps(calculate_method)
        def wrapper(self, data: IndicatorInput) -> IndicatorResult:
            # Generate cache key
            key = cache._generate_key(self.name, data, self.params)
            
            # Try to get from cache
            cached_result = cache.get(key)
            if cached_result is not None:
                return cached_result
            
            # Calculate and cache
            result = calculate_method(self, data)
            cache.set(key, result)
            return result
        
        # Attach cache reference for external access
        wrapper._cache = cache
        return wrapper
    return decorator


class CacheMixin:
    """Mixin to add caching support to any indicator.
    
    This mixin provides caching functionality that can be added to
    any indicator class. It maintains backward compatibility with
    existing indicator implementations.
    
    Example:
        ```python
        class MyIndicator(BaseIndicator, CacheMixin):
            def __init__(self, period=14):
                super().__init__("MyIndicator", {"period": period})
                CacheMixin.__init__(self, max_size=100, ttl=300)
                self.period = period
            
            def calculate(self, data: IndicatorInput) -> IndicatorResult:
                return self._calculate_with_cache(data, self._do_calculation)
            
            def _do_calculation(self, data: IndicatorInput) -> IndicatorResult:
                # Actual calculation logic
                return result
        ```
    """
    
    def __init__(self, max_size: int = 100, ttl: Optional[float] = None) -> None:
        """Initialize cache mixin.
        
        Args:
            max_size: Maximum cache size
            ttl: Time-to-live in seconds
        """
        self._cache = IndicatorCache(max_size=max_size, ttl=ttl)
        self._cache_enabled = True
    
    def _calculate_with_cache(
        self,
        data: IndicatorInput,
        calculation_func
    ) -> IndicatorResult:
        """Calculate with cache support.
        
        Args:
            data: Input data
            calculation_func: Function to perform actual calculation
            
        Returns:
            IndicatorResult (cached or calculated)
        """
        if not self._cache_enabled:
            return calculation_func(data)
        
        # Generate cache key
        key = self._cache._generate_key(self.name, data, self.params)
        
        # Try cache
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        
        # Calculate and store
        result = calculation_func(data)
        self._cache.set(key, result)
        return result
    
    def clear_cache(self) -> None:
        """Clear this indicator's cache."""
        self._cache.clear()
    
    def enable_cache(self) -> None:
        """Enable caching."""
        self._cache_enabled = True
    
    def disable_cache(self) -> None:
        """Disable caching."""
        self._cache_enabled = False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.get_stats()
