# Extension Guide: Adding Real Broker Integrations

This document explains how to extend the platform to connect to real trading APIs.

## Architecture Overview

The execution layer uses an adapter pattern:

```
Strategy Engine -> BrokerAdapter (abstract) -> [Your Broker Implementation]
```

## Step 1: Implement BrokerAdapter

Create a new file `src/execution/your_broker.py`:

```python
from ist.execution.adapter import BrokerAdapter
from ist.execution.models import Order, OrderResult, Position
from ist.data.models import Quote


class YourBrokerAdapter(BrokerAdapter):
    """Adapter for Your Broker API."""
    
    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__("your_broker")
        self.api_key = api_key
        self.api_secret = api_secret
        self._client = None  # Initialize your broker's SDK client
    
    async def connect(self) -> bool:
        """Establish connection to broker."""
        # Initialize and authenticate
        self._client = YourBrokerClient(self.api_key, self.api_secret)
        await self._client.authenticate()
        self._connected = True
        return True
    
    async def disconnect(self) -> None:
        """Close connection."""
        if self._client:
            await self._client.close()
        self._connected = False
    
    async def get_quote(self, symbol: str) -> Quote:
        """Get latest quote."""
        raw_quote = await self._client.get_market_data(symbol)
        return Quote(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            open=raw_quote.open,
            high=raw_quote.high,
            low=raw_quote.low,
            close=raw_quote.last,
            volume=raw_quote.volume
        )
    
    async def place_order(self, order: Order) -> OrderResult:
        """Submit order to broker."""
        # Map internal Order to broker's format
        broker_order = {
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "type": order.order_type.value,
            # ... map other fields
        }
        
        result = await self._client.submit_order(broker_order)
        
        return OrderResult(
            order_id=result.id,
            status=result.status,
            filled_quantity=result.filled_qty,
            avg_price=result.avg_price,
            commission=result.commission
        )
    
    async def get_positions(self) -> list[Position]:
        """Get current positions."""
        raw_positions = await self._client.get_positions()
        return [
            Position(
                symbol=p.symbol,
                quantity=p.quantity,
                avg_entry_price=p.avg_entry,
                unrealized_pnl=p.unrealized_pnl
            )
            for p in raw_positions
        ]
```

## Step 2: Register Adapter

Update `src/execution/factory.py` (create if not exists):

```python
from ist.execution.adapter import BrokerAdapter
from ist.execution.paper import PaperBroker
from ist.execution.your_broker import YourBrokerAdapter


class BrokerFactory:
    """Factory for creating broker adapters."""
    
    @staticmethod
    def create(broker_type: str, **kwargs) -> BrokerAdapter:
        if broker_type == "paper":
            return PaperBroker(**kwargs)
        elif broker_type == "your_broker":
            return YourBrokerAdapter(**kwargs)
        else:
            raise ValueError(f"Unknown broker type: {broker_type}")
```

## Step 3: Configure API Keys

Add to `.env`:

```
YOUR_BROKER_API_KEY=your_key_here
YOUR_BROKER_API_SECRET=your_secret_here
YOUR_BROKER_ACCOUNT_ID=your_account
```

## Step 4: Switch Data Provider

For live trading, switch from `LocalDataProvider` to real-time data:

```python
from ist.data.your_broker_data import YourBrokerDataProvider

# In your configuration or startup code
data_provider = YourBrokerDataProvider(
    api_key=settings.your_broker_api_key
)
```

## Step 5: Update Strategy Configuration

Add broker selection to strategy config:

```json
{
  "execution": {
    "broker": "your_broker",
    "mode": "live",  // paper, live
    "risk_limits": {
      "max_daily_loss": 1000,
      "circuit_breaker": true
    }
  }
}
```

## Supported Broker Examples

### Interactive Brokers

```python
from ib_insync import IB, Stock, MarketOrder

class IBAdapter(BrokerAdapter):
    async def connect(self):
        self._ib = IB()
        await self._ib.connectAsync('127.0.0.1', 7497, clientId=1)
```

### OANDA

```python
import oandapyV20

class OandaAdapter(BrokerAdapter):
    async def connect(self):
        self._client = oandapyV20.API(access_token=self.token)
```

### Alpaca

```python
from alpaca_trade_api import REST

class AlpacaAdapter(BrokerAdapter):
    async def connect(self):
        self._api = REST(self.api_key, self.api_secret)
```

## Testing Your Adapter

```python
@pytest.mark.asyncio
async def test_your_broker_adapter():
    adapter = YourBrokerAdapter(
        api_key="test_key",
        api_secret="test_secret"
    )
    
    # Connect
    connected = await adapter.connect()
    assert connected
    
    # Get quote
    quote = await adapter.get_quote("EURUSD")
    assert quote.symbol == "EURUSD"
    assert quote.bid > 0
    
    # Disconnect
    await adapter.disconnect()
```

## Deployment Considerations

1. **API Rate Limits**: Implement rate limiting in your adapter
2. **Connection Resilience**: Add automatic reconnection logic
3. **Order Validation**: Pre-validate orders before submission
4. **Audit Logging**: Log all API calls for compliance
5. **Circuit Breaker**: Stop trading on consecutive errors
