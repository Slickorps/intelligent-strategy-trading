"""Abstract data provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Optional

from ist.data.models import Bar, Quote, Tick


@dataclass
class DataRequest:
    """Request parameters for market data."""
    
    symbol: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: Optional[int] = None
    timeframe: str = "1h"  # 1m, 5m, 15m, 1h, 4h, 1d


class DataProvider(ABC):
    """Abstract base class for data providers.
    
    This interface allows switching between different data sources:
    - Local CSV/Parquet files (backtesting)
    - Real-time APIs (live trading)
    - Database connections (enterprise deployments)
    """
    
    def __init__(self, name: str) -> None:
        self.name = name
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        """Check if provider is connected."""
        return self._connected
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to data source.
        
        Returns:
            True if connection successful
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to data source."""
        pass
    
    @abstractmethod
    async def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get latest quote for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Latest quote or None if unavailable
        """
        pass
    
    @abstractmethod
    async def get_bars(
        self, 
        request: DataRequest
    ) -> list[Bar]:
        """Get historical bars.
        
        Args:
            request: Data request parameters
            
        Returns:
            List of historical bars
        """
        pass
    
    @abstractmethod
    async def stream_ticks(
        self, 
        symbols: list[str]
    ) -> AsyncIterator[Tick]:
        """Stream real-time ticks for symbols.
        
        Args:
            symbols: List of symbols to stream
            
        Yields:
            Ticks as they arrive
        """
        pass
    
    async def get_history(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1h"
    ) -> list[Bar]:
        """Convenience method for historical data."""
        request = DataRequest(
            symbol=symbol,
            start_time=start,
            end_time=end,
            timeframe=timeframe
        )
        return await self.get_bars(request)
