"""Data models for market data."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class AssetClass(Enum):
    """Supported asset classes."""
    FOREX = "forex"
    INDEX_CFD = "index_cfd"
    COMMODITY = "commodity"
    CRYPTO = "crypto"


@dataclass(frozen=True)
class Tick:
    """Individual price tick."""
    
    timestamp: datetime
    symbol: str
    bid: float
    ask: float
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    
    @property
    def mid(self) -> float:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class Quote:
    """Standard OHLCV quote/bar."""
    
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    
    def __post_init__(self) -> None:
        # Validate OHLC relationships
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("High must be >= open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Low must be <= open, close, and high")


@dataclass(frozen=True)
class Bar(Quote):
    """Alias for Quote - represents a completed bar."""
    pass
