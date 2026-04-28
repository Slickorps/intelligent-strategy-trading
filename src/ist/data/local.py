"""Local file-based data provider for backtesting."""

import os
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

import pandas as pd

from ist.core.config import get_settings
from ist.core.exceptions import DataError
from ist.core.logging import get_logger
from ist.data.models import Bar, Quote, Tick
from ist.data.provider import DataProvider, DataRequest

logger = get_logger(__name__)


class LocalDataProvider(DataProvider):
    """Data provider that reads from local CSV/Parquet files.
    
    File structure expected:
        {data_path}/{symbol}_{timeframe}.{csv|parquet}
    
    Columns required:
        timestamp, open, high, low, close, volume
    """
    
    def __init__(self, data_path: Optional[str] = None) -> None:
        super().__init__("local")
        settings = get_settings()
        self.data_path = Path(data_path or settings.data_path)
        self._cache: dict[str, pd.DataFrame] = {}
    
    async def connect(self) -> bool:
        """Validate data directory exists."""
        if not self.data_path.exists():
            logger.warning(
                "Data path does not exist, creating",
                path=str(self.data_path)
            )
            self.data_path.mkdir(parents=True, exist_ok=True)
        
        self._connected = True
        logger.info(
            "Local data provider connected",
            path=str(self.data_path)
        )
        return True
    
    async def disconnect(self) -> None:
        """Clear cache and disconnect."""
        self._cache.clear()
        self._connected = False
        logger.info("Local data provider disconnected")
    
    def _get_file_path(self, symbol: str, timeframe: str) -> Path:
        """Construct file path for symbol/timeframe."""
        # Try parquet first, then csv
        for ext in ["parquet", "csv"]:
            path = self.data_path / f"{symbol}_{timeframe}.{ext}"
            if path.exists():
                return path
        
        # Default to parquet if neither exists (will fail later)
        return self.data_path / f"{symbol}_{timeframe}.parquet"
    
    def _load_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load data file into cache."""
        cache_key = f"{symbol}_{timeframe}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        file_path = self._get_file_path(symbol, timeframe)
        
        if not file_path.exists():
            raise DataError(
                f"Data file not found: {file_path}",
                details={"symbol": symbol, "timeframe": timeframe}
            )
        
        try:
            if file_path.suffix == ".parquet":
                df = pd.read_parquet(file_path)
            else:
                df = pd.read_csv(file_path, parse_dates=["timestamp"])
            
            # Validate required columns
            required_cols = ["timestamp", "open", "high", "low", "close"]
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                raise DataError(
                    f"Missing required columns: {missing}",
                    details={"file": str(file_path)}
                )
            
            # Ensure volume column exists
            if "volume" not in df.columns:
                df["volume"] = 0
            
            # Sort by timestamp
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            self._cache[cache_key] = df
            logger.info(
                "Loaded data file",
                symbol=symbol,
                timeframe=timeframe,
                rows=len(df)
            )
            
            return df
            
        except Exception as e:
            raise DataError(
                f"Failed to load data file: {e}",
                details={"file": str(file_path)}
            )
    
    async def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get latest quote from file."""
        try:
            df = self._load_data(symbol, "1h")  # Default to hourly
            if len(df) == 0:
                return None
            
            last = df.iloc[-1]
            return Quote(
                timestamp=last["timestamp"],
                symbol=symbol,
                open=float(last["open"]),
                high=float(last["high"]),
                low=float(last["low"]),
                close=float(last["close"]),
                volume=float(last.get("volume", 0))
            )
        except DataError:
            return None
    
    async def get_bars(self, request: DataRequest) -> list[Bar]:
        """Get historical bars from file."""
        df = self._load_data(request.symbol, request.timeframe)
        
        # Apply filters
        if request.start_time:
            df = df[df["timestamp"] >= request.start_time]
        if request.end_time:
            df = df[df["timestamp"] <= request.end_time]
        if request.limit:
            df = df.tail(request.limit)
        
        # Convert to Bar objects
        bars = []
        for _, row in df.iterrows():
            bars.append(Bar(
                timestamp=row["timestamp"],
                symbol=request.symbol,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0))
            ))
        
        return bars
    
    async def stream_ticks(
        self, 
        symbols: list[str]
    ) -> AsyncIterator[Tick]:
        """Not implemented for local provider - no real-time streaming."""
        raise NotImplementedError(
            "LocalDataProvider does not support streaming. "
            "Use this provider for backtesting only."
        )
    
    def list_available_symbols(self) -> list[str]:
        """List all symbols available in data directory."""
        symbols = set()
        
        for file in self.data_path.iterdir():
            if file.suffix in [".csv", ".parquet"]:
                # Extract symbol from filename: SYMBOL_TIMEFRAME.ext
                name = file.stem
                if "_" in name:
                    symbol = name.split("_")[0]
                    symbols.add(symbol)
        
        return sorted(list(symbols))
