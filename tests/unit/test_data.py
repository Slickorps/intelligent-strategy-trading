"""Tests for data layer."""

import pytest
from datetime import datetime

from ist.data.models import AssetClass, Bar, Quote, Tick


class TestDataModels:
    """Test data model classes."""
    
    def test_tick_mid_price(self) -> None:
        """Test tick mid price calculation."""
        tick = Tick(
            timestamp=datetime.utcnow(),
            symbol="EURUSD",
            bid=1.0850,
            ask=1.0852
        )
        assert tick.mid == pytest.approx(1.0851)
    
    def test_quote_validation(self) -> None:
        """Test quote OHLC validation."""
        now = datetime.utcnow()
        
        # Valid quote
        quote = Quote(
            timestamp=now,
            symbol="EURUSD",
            open=1.0850,
            high=1.0860,
            low=1.0840,
            close=1.0855
        )
        assert quote.open == 1.0850
        
        # Invalid: high < close
        with pytest.raises(ValueError):
            Quote(
                timestamp=now,
                symbol="EURUSD",
                open=1.0850,
                high=1.0840,  # Invalid
                low=1.0840,
                close=1.0855
            )
    
    def test_asset_class_enum(self) -> None:
        """Test asset class enumeration."""
        assert AssetClass.FOREX.value == "forex"
        assert AssetClass.CRYPTO.value == "crypto"
