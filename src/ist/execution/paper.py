"""Paper trading implementation for simulation.

Simulates trade execution using real or delayed market data
without actual capital at risk.
"""

from datetime import datetime
from typing import Any, Optional

from ist.execution.adapter import (
    BrokerAdapter,
    Order,
    OrderResult,
    OrderStatus,
    OrderType,
    AccountInfo,
    Position,
    Quote,
)
from ist.data.models import Quote as DataQuote
from ist.data.provider import DataProvider
from ist.core.logging import get_logger

logger = get_logger(__name__)


class PaperBroker(BrokerAdapter):
    """Paper trading broker implementation.
    
    Simulates order execution using market data.
    Tracks positions and PnL without real money.
    
    Usage:
        broker = PaperBroker(
            data_provider=local_provider,
            initial_capital=100000.0,
            commission_rate=0.001,
            slippage_model="fixed",
            slippage_amount=0.0001
        )
        await broker.connect()
        
        order = Order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            quantity=10000,
            order_type=OrderType.MARKET
        )
        result = await broker.place_order(order)
    """
    
    def __init__(
        self,
        data_provider: DataProvider,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.001,
        slippage_model: str = "fixed",
        slippage_amount: float = 0.0001,
        fill_probability: float = 1.0,
        partial_fill_threshold: float = 100000  # Large orders may partially fill
    ) -> None:
        super().__init__("paper_trading")
        
        self.data_provider = data_provider
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_model = slippage_model
        self.slippage_amount = slippage_amount
        self.fill_probability = fill_probability
        self.partial_fill_threshold = partial_fill_threshold
        
        # Paper trading state
        self._cash: float = initial_capital
        self._equity: float = initial_capital
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderResult] = {}
        self._order_counter: int = 0
    
    async def connect(self) -> bool:
        """Connect to data provider."""
        try:
            connected = await self.data_provider.connect()
            self._connected = connected
            
            if connected:
                logger.info(
                    "Paper broker connected",
                    initial_capital=self.initial_capital
                )
            
            return connected
            
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Paper broker connection failed: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from data provider."""
        await self.data_provider.disconnect()
        self._connected = False
        logger.info("Paper broker disconnected")
    
    async def get_account_info(self) -> AccountInfo:
        """Get paper account info."""
        # Update equity based on positions
        await self._update_equity()
        
        return AccountInfo(
            account_id="paper_account",
            cash=self._cash,
            equity=self._equity,
            buying_power=self._cash * 2,  # 2:1 leverage for paper
            base_currency="USD"
        )
    
    async def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get quote from data provider."""
        quote = await self.data_provider.get_quote(symbol)
        
        if quote is None:
            return None
        
        return Quote(
            symbol=quote.symbol,
            bid=quote.bid if hasattr(quote, 'bid') else quote.close,
            ask=quote.ask if hasattr(quote, 'ask') else quote.close,
            bid_size=0.0,
            ask_size=0.0,
            last=quote.close,
            last_size=0.0,
            timestamp=quote.timestamp
        )
    
    async def place_order(self, order: Order) -> OrderResult:
        """Simulate order execution."""
        self._order_counter += 1
        order_id = f"paper_{self._order_counter}"
        
        # Get current market price
        quote = await self.get_quote(order.symbol)
        
        if quote is None:
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                error_message="No market data available"
            )
        
        # Determine fill price with slippage
        fill_price = self._calculate_fill_price(order, quote)
        
        # Check fill probability (simulate occasional no-fills)
        import random
        if random.random() > self.fill_probability:
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                error_message="Order not filled (simulated)"
            )
        
        # Calculate costs
        order_value = order.quantity * fill_price
        commission = order_value * self.commission_rate
        
        # Check buying power for buys
        if order.side.name == "BUY":
            if order_value + commission > self._cash:
                return OrderResult(
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    error_message="Insufficient funds"
                )
        
        # Execute order
        fill_time = datetime.utcnow()
        
        # Update cash
        if order.side.name == "BUY":
            self._cash -= order_value + commission
        else:
            self._cash += order_value - commission
        
        # Update positions
        await self._update_position(order, fill_price)
        
        # Create result
        result = OrderResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            remaining_quantity=0.0,
            avg_fill_price=fill_price,
            commission=commission,
            slippage=self._calculate_slippage(order, quote),
            submit_time=order.timestamp,
            fill_time=fill_time
        )
        
        self._orders[order_id] = result
        
        logger.info(
            "Paper order filled",
            order_id=order_id,
            symbol=order.symbol,
            side=order.side.name,
            quantity=order.quantity,
            price=fill_price
        )
        
        return result
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order (paper orders fill immediately)."""
        if order_id in self._orders:
            result = self._orders[order_id]
            if result.status == OrderStatus.PENDING:
                result.status = OrderStatus.CANCELLED
                return True
        return False
    
    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get order status."""
        return self._orders.get(order_id)
    
    async def get_positions(self) -> list[Position]:
        """Get current positions."""
        # Update position prices
        for symbol, position in self._positions.items():
            quote = await self.get_quote(symbol)
            if quote:
                position.market_price = quote.last
                position.market_value = abs(position.quantity) * quote.last
                if position.avg_entry_price > 0:
                    position.unrealized_pnl = (
                        position.quantity * (quote.last - position.avg_entry_price)
                    )
        
        return list(self._positions.values())
    
    async def get_open_orders(self) -> list[OrderResult]:
        """Get open orders (paper orders fill immediately)."""
        # Paper trading fills immediately, so no open orders
        return [
            result for result in self._orders.values()
            if result.status in (OrderStatus.PENDING, OrderStatus.PARTIAL_FILL)
        ]
    
    def _calculate_fill_price(self, order: Order, quote: Quote) -> float:
        """Calculate fill price with slippage."""
        base_price = quote.last
        
        if order.side.name == "BUY":
            # Buy at ask or higher
            base_price = quote.ask if quote.ask > 0 else quote.last
            slippage = base_price * self.slippage_amount
            return base_price + slippage
        else:
            # Sell at bid or lower
            base_price = quote.bid if quote.bid > 0 else quote.last
            slippage = base_price * self.slippage_amount
            return base_price - slippage
    
    def _calculate_slippage(self, order: Order, quote: Quote) -> float:
        """Calculate slippage amount."""
        fill_price = self._calculate_fill_price(order, quote)
        reference = quote.last
        return abs(fill_price - reference) * order.quantity
    
    async def _update_position(self, order: Order, fill_price: float) -> None:
        """Update position after fill."""
        symbol = order.symbol
        
        if symbol not in self._positions:
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=0.0,
                avg_entry_price=0.0,
                market_price=fill_price
            )
        
        pos = self._positions[symbol]
        
        # Calculate signed quantity
        signed_qty = order.quantity if order.side.name == "BUY" else -order.quantity
        new_qty = pos.quantity + signed_qty
        
        # Update average entry
        if new_qty != 0:
            if pos.quantity * new_qty > 0:
                # Adding to position
                total_cost = (pos.quantity * pos.avg_entry_price +
                             signed_qty * fill_price)
                pos.avg_entry_price = abs(total_cost / new_qty)
            else:
                # Reducing or reversing
                if abs(new_qty) > 0.0001:
                    pos.avg_entry_price = fill_price
        
        pos.quantity = new_qty
        pos.market_price = fill_price
        
        # Remove if flat
        if abs(pos.quantity) < 0.0001:
            del self._positions[symbol]
    
    async def _update_equity(self) -> None:
        """Update equity based on positions."""
        position_value = 0.0
        
        for symbol, pos in self._positions.items():
            quote = await self.get_quote(symbol)
            if quote:
                position_value += pos.quantity * quote.last
        
        self._equity = self._cash + position_value
    
    def get_trade_history(self) -> list[OrderResult]:
        """Get all executed orders."""
        return list(self._orders.values())
    
    def reset(self) -> None:
        """Reset paper trading state."""
        self._cash = self.initial_capital
        self._equity = self.initial_capital
        self._positions.clear()
        self._orders.clear()
        self._order_counter = 0
        logger.info("Paper broker state reset")
