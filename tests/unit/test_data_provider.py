"""Unit tests for the local file-based data provider."""

from datetime import datetime
from pathlib import Path

import pytest

from ist.core.exceptions import DataError
from ist.data.local import LocalDataProvider
from ist.data.models import Bar, Quote
from ist.data.provider import DataRequest


def write_csv(path: Path, symbol: str = "EURUSD", timeframe: str = "1h") -> Path:
    """Write a small OHLCV CSV file for testing."""
    rows = [
        ("2024-01-01T00:00:00", 1.0, 1.1, 0.9, 1.05, 100),
        ("2024-01-01T01:00:00", 1.05, 1.2, 1.0, 1.1, 110),
        ("2024-01-01T02:00:00", 1.1, 1.3, 1.05, 1.2, 120),
    ]
    lines = ["timestamp,open,high,low,close,volume"]
    lines += [f"{ts},{o},{h},{lo},{c},{v}" for ts, o, h, lo, c, v in rows]
    file = path / f"{symbol}_{timeframe}.csv"
    file.write_text("\n".join(lines))
    return file


class TestLocalDataProviderLifecycle:
    @pytest.mark.asyncio
    async def test_connect_creates_dir_and_connects(self, tmp_path) -> None:
        provider = LocalDataProvider(data_path=str(tmp_path / "data"))
        assert provider.is_connected is False

        result = await provider.connect()

        assert result is True
        assert provider.is_connected is True
        assert (tmp_path / "data").exists()

    @pytest.mark.asyncio
    async def test_disconnect_clears_cache(self, tmp_path) -> None:
        write_csv(tmp_path)
        provider = LocalDataProvider(data_path=str(tmp_path))
        await provider.connect()
        provider._load_data("EURUSD", "1h")
        assert len(provider._cache) == 1

        await provider.disconnect()

        assert provider.is_connected is False
        assert provider._cache == {}

    def test_get_file_path_prefers_parquet(self, tmp_path) -> None:
        provider = LocalDataProvider(data_path=str(tmp_path))
        (tmp_path / "EURUSD_1h.csv").write_text("")
        (tmp_path / "EURUSD_1h.parquet").write_text("")

        path = provider._get_file_path("EURUSD", "1h")

        assert path.suffix == ".parquet"

    def test_get_file_path_defaults_to_parquet(self, tmp_path) -> None:
        provider = LocalDataProvider(data_path=str(tmp_path))
        path = provider._get_file_path("EURUSD", "1h")
        assert path.name == "EURUSD_1h.parquet"


class TestLocalDataProviderLoading:
    def test_load_data_caches_dataframe(self, tmp_path) -> None:
        write_csv(tmp_path)
        provider = LocalDataProvider(data_path=str(tmp_path))

        df = provider._load_data("EURUSD", "1h")

        assert len(df) == 3
        assert "EURUSD_1h" in provider._cache
        assert provider._load_data("EURUSD", "1h") is df

    def test_load_data_missing_file_raises(self, tmp_path) -> None:
        provider = LocalDataProvider(data_path=str(tmp_path))
        with pytest.raises(DataError, match="Data file not found"):
            provider._load_data("EURUSD", "1h")

    def test_load_data_missing_columns_raises(self, tmp_path) -> None:
        (tmp_path / "BAD_1h.csv").write_text("timestamp,open,close\n2024-01-01,1,1\n")
        provider = LocalDataProvider(data_path=str(tmp_path))
        with pytest.raises(DataError, match="Missing required columns"):
            provider._load_data("BAD", "1h")

    def test_load_data_adds_default_volume(self, tmp_path) -> None:
        (tmp_path / "XAU_1h.csv").write_text(
            "timestamp,open,high,low,close\n2024-01-01T00:00:00,1,1,1,1\n",
        )
        provider = LocalDataProvider(data_path=str(tmp_path))

        df = provider._load_data("XAU", "1h")

        assert "volume" in df.columns
        assert df["volume"].iloc[0] == 0


class TestLocalDataProviderQuotes:
    @pytest.mark.asyncio
    async def test_get_quote_returns_latest(self, tmp_path) -> None:
        write_csv(tmp_path)
        provider = LocalDataProvider(data_path=str(tmp_path))

        quote = await provider.get_quote("EURUSD")

        assert isinstance(quote, Quote)
        assert quote.symbol == "EURUSD"
        assert quote.close == 1.2

    @pytest.mark.asyncio
    async def test_get_quote_missing_file_returns_none(self, tmp_path) -> None:
        provider = LocalDataProvider(data_path=str(tmp_path))
        assert await provider.get_quote("EURUSD") is None

    @pytest.mark.asyncio
    async def test_get_quote_empty_file_returns_none(self, tmp_path) -> None:
        (tmp_path / "EURUSD_1h.csv").write_text(
            "timestamp,open,high,low,close,volume\n",
        )
        provider = LocalDataProvider(data_path=str(tmp_path))
        assert await provider.get_quote("EURUSD") is None


class TestLocalDataProviderBars:
    @pytest.mark.asyncio
    async def test_get_bars_returns_all(self, tmp_path) -> None:
        write_csv(tmp_path)
        provider = LocalDataProvider(data_path=str(tmp_path))

        bars = await provider.get_bars(DataRequest(symbol="EURUSD", timeframe="1h"))

        assert len(bars) == 3
        assert all(isinstance(b, Bar) for b in bars)
        assert bars[0].open == 1.0
        assert bars[-1].close == 1.2

    @pytest.mark.asyncio
    async def test_get_bars_applies_limit(self, tmp_path) -> None:
        write_csv(tmp_path)
        provider = LocalDataProvider(data_path=str(tmp_path))

        bars = await provider.get_bars(
            DataRequest(symbol="EURUSD", timeframe="1h", limit=1),
        )

        assert len(bars) == 1
        assert bars[0].close == 1.2

    @pytest.mark.asyncio
    async def test_get_bars_applies_start_time_filter(self, tmp_path) -> None:
        write_csv(tmp_path)
        provider = LocalDataProvider(data_path=str(tmp_path))

        bars = await provider.get_bars(
            DataRequest(
                symbol="EURUSD",
                timeframe="1h",
                start_time=datetime(2024, 1, 1, 1, 0, 0),
            ),
        )

        assert len(bars) == 2
        assert bars[0].open == 1.05

    @pytest.mark.asyncio
    async def test_get_bars_applies_end_time_filter(self, tmp_path) -> None:
        write_csv(tmp_path)
        provider = LocalDataProvider(data_path=str(tmp_path))

        bars = await provider.get_bars(
            DataRequest(
                symbol="EURUSD",
                timeframe="1h",
                end_time=datetime(2024, 1, 1, 0, 0, 0),
            ),
        )

        assert len(bars) == 1
        assert bars[0].close == 1.05


class TestLocalDataProviderMisc:
    @pytest.mark.asyncio
    async def test_stream_ticks_not_implemented(self, tmp_path) -> None:
        provider = LocalDataProvider(data_path=str(tmp_path))
        with pytest.raises(NotImplementedError):
            await provider.stream_ticks(["EURUSD"])

    def test_list_available_symbols(self, tmp_path) -> None:
        write_csv(tmp_path, symbol="EURUSD", timeframe="1h")
        write_csv(tmp_path, symbol="GBPUSD", timeframe="4h")
        provider = LocalDataProvider(data_path=str(tmp_path))

        assert provider.list_available_symbols() == ["EURUSD", "GBPUSD"]
