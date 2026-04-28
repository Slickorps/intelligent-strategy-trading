"""Caching layer for market data."""

from datetime import datetime, timedelta
from typing import Optional

from ist.data.models import Quote


class DataCache:
    """Simple in-memory cache for market data with TTL."""
    
    def __init__(self, default_ttl_seconds: int = 300) -> None:
        self._cache: dict[str, dict] = {}
        self._default_ttl = default_ttl_seconds
    
    def _make_key(self, symbol: str, data_type: str) -> str:
        """Create cache key."""
        return f"{data_type}:{symbol}"
    
    def get(self, symbol: str, data_type: str = "quote") -> Optional[Quote]:
        """Get cached data if not expired."""
        key = self._make_key(symbol, data_type)
        entry = self._cache.get(key)
        
        if entry is None:
            return None
        
        # Check TTL
        cached_at = entry.get("cached_at")
        if cached_at is None:
            return None
        
        ttl = entry.get("ttl", self._default_ttl)
        if datetime.utcnow() - cached_at > timedelta(seconds=ttl):
            # Expired
            del self._cache[key]
            return None
        
        return entry.get("data")
    
    def set(
        self, 
        symbol: str, 
        data: Quote, 
        data_type: str = "quote",
        ttl_seconds: Optional[int] = None
    ) -> None:
        """Cache data with TTL."""
        key = self._make_key(symbol, data_type)
        self._cache[key] = {
            "data": data,
            "cached_at": datetime.utcnow(),
            "ttl": ttl_seconds or self._default_ttl
        }
    
    def invalidate(self, symbol: str, data_type: Optional[str] = None) -> None:
        """Invalidate cache entries."""
        if data_type:
            key = self._make_key(symbol, data_type)
            self._cache.pop(key, None)
        else:
            # Invalidate all types for symbol
            keys_to_remove = [
                k for k in self._cache.keys() 
                if k.endswith(f":{symbol}")
            ]
            for key in keys_to_remove:
                self._cache.pop(key, None)
    
    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_entries = len(self._cache)
        expired = 0
        now = datetime.utcnow()
        
        for entry in self._cache.values():
            cached_at = entry.get("cached_at")
            ttl = entry.get("ttl", self._default_ttl)
            if cached_at and (now - cached_at > timedelta(seconds=ttl)):
                expired += 1
        
        return {
            "total_entries": total_entries,
            "expired_entries": expired,
            "valid_entries": total_entries - expired
        }
