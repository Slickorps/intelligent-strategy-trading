"""Abstract broker adapter interface.

This module defines the interface for connecting to real trading APIs.
Implementations for specific brokers (Interactive Brokers, OANDA, etc.)
should inherit from BrokerAdapter.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional

from ist.data.models import Quote
from ist.core.logging import get_logger

logger = get_logger(__name__)


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = auto()
    SELL = auto()


class OrderType(Enum):
    """Order type enumeration."""
    MARKET = auto()
    LIMIT = auto()
    STOP = auto()
    STOP_LIMIT = auto()


class OrderStatus(Enum):
    """Order lifecycle status."""
    PENDING = auto()
    SUBMITTED = auto()
    PARTIAL_FILL = auto()
    FILLED = auto()
    CANCELLED = auto()
    REJECTED = auto()
    EXPIRED = auto()


class TimeInForce(Enum):
    """Time in force options."""
    GTC = auto()  # Good Till Cancelled
    IOC = auto()  # Immediate or Cancel
    FOK = auto()  # Fill or Kill
    DAY = auto()  # Day order


@dataclass
class Order:
    """Trading order data structure."""
    
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    
    # Optional parameters
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    
    # Metadata
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class OrderResult:
    """Result of order submission or fill."""
    
    order_id: str
    status: OrderStatus
    
    # Fill details
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0
    avg_fill_price: float = 0.0
    
    # Costs
    commission: float = 0.0
    slippage: float = 0.0
    
    # Timing
    submit_time: Optional[datetime] = None
    fill_time: Optional[datetime] = None
    
    # Error info
    error_message: Optional[str] = None


@dataclass
class Position:
    """Broker position information."""
    
    symbol: str
    quantity: float
    avg_entry_price: float
    market_price: float
    
    # Calculated fields
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def __post_init__(self) -> None:
        self.market_value = abs(self.quantity) * self.market_price
        if self.avg_entry_price > 0:
            self.unrealized_pnl = (
                self.quantity * (self.market_price - self.avg_entry_price)
            )


@dataclass
class AccountInfo:
    """Account information from broker."""
    
    account_id: str
    cash: float
    equity: float
    buying_power: float
    
    # Margin info (if applicable)
    margin_used: float = 0.0
    margin_available: float = 0.0
    
    # Currency
    base_currency: str = "USD"


class BrokerAdapter(ABC):
    """Abstract base class for broker API adapters.
    
    This interface allows switching between different brokers:
    - Interactive Brokers (IB Gateway)
    - OANDA (forex)
    - Alpaca (stocks/crypto)
    - Custom/paper trading
    
    Implementation Guide:
    1. Create new file: src/ist/execution/your_broker.py
    2. Inherit from BrokerAdapter
    3. Implement all abstract methods
    4. Handle connection/auth in connect()
    5. Map internal Order to broker-specific format in place_order()
    6. Convert broker responses to OrderResult
    
    Example:
        class InteractiveBrokersAdapter(BrokerAdapter):
            def __init__(self, host, port, client_id):
                super().__init__("interactive_brokers")
                self.host = host
                self.port = port
                self.client_id = client_id
                self._ib = None
            
            async def connect(self) -> bool:
                from ib_insync import IB
                self._ib = IB()
                await self._ib.connectAsync(self.host, self.port, self.client_id)
                self._connected = True
                return True
            
            async def place_order(self, order: Order) -> OrderResult:
                # Convert to IB order format
                ib_order = MarketOrder(order.side.name, order.quantity)
                trade = self._ib.placeOrder(contract, ib_order)
                return OrderResult(...)
    """
    
    def __init__(self, broker_name: str) -> None:
        self.broker_name = broker_name
        self._connected = False
        self._account_id: Optional[str] = None
        self._last_error: Optional[str] = None
        self._connection_params: dict[str, Any] = {}
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to broker."""
        return self._connected
    
    @property
    def last_error(self) -> Optional[str]:
        """Get last error message."""
        return self._last_error
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to broker.
        
        Returns:
            True if connection successful
            
        Raises:
            ConnectionError: If connection fails
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to broker."""
        pass
    
    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Get account information.
        
        Returns:
            AccountInfo with cash, equity, buying power
        """
        pass
    
    @abstractmethod
    async def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get real-time quote for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Quote or None if unavailable
        """
        pass
    
    @abstractmethod
    async def place_order(self, order: Order) -> OrderResult:
        """Submit order to broker.
        
        Args:
            order: Order to submit
            
        Returns:
            OrderResult with status and fill info
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation successful
        """
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get current order status.
        
        Args:
            order_id: Order ID to query
            
        Returns:
            OrderResult or None if not found
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get current positions.
        
        Returns:
            List of Position objects
        """
        pass
    
    @abstractmethod
    async def get_open_orders(self) -> list[OrderResult]:
        """Get list of open orders.
        
        Returns:
            List of OrderResult for pending orders
        """
        pass
    
    async def reconnect(self) -> bool:
        """Attempt to reconnect if disconnected."""
        if self._connected:
            return True
        
        logger.warning(f"Attempting to reconnect to {self.broker_name}")
        
        try:
            return await self.connect()
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Reconnection failed: {e}")
            return False
    
    def health_check(self) -> dict[str, Any]:
        """Check adapter health status."""
        return {
            "broker": self.broker_name,
            "connected": self._connected,
            "account_id": self._account_id,
            "last_error": self._last_error,
        }


class BrokerFactory:
    """Factory for creating broker adapters.
    
    Usage:
        factory = BrokerFactory()
        adapter = factory.create("paper", initial_capital=100000)
        
        # Or for real broker (after implementing)
        adapter = factory.create("interactive_brokers", 
                                host="127.0.0.1", port=7497)
    """
    
    _adapters: dict[str, type[BrokerAdapter]] = {}
    
    @classmethod
    def register(
        cls,
        name: str,
        adapter_class: type[BrokerAdapter]
    ) -> None:
        """Register a broker adapter."""
        cls._adapters[name] = adapter_class
        logger.info(f"Registered broker adapter: {name}")
    
    @classmethod
    def create(cls, name: str, **kwargs) -> BrokerAdapter:
        """Create broker adapter instance."""
        if name not in cls._adapters:
            raise ValueError(
                f"Unknown broker: {name}. "
                f"Available: {list(cls._adapters.keys())}"
            )
        
        adapter_class = cls._adapters[name]
        return adapter_class(**kwargs)
    
    @classmethod
    def list_available(cls) -> list[str]:
        """List available broker adapters."""
        return list(cls._adapters.keys())
