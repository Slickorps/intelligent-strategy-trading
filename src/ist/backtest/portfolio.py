"""Portfolio and position tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Position:
    """Represents a trading position."""
    
    symbol: str
    quantity: float  # Positive for long, negative for short
    avg_entry_price: float
    entry_time: datetime
    
    # Track multiple entries (for averaging)
    entries: list[dict] = field(default_factory=list)
    
    # Current state
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def __post_init__(self) -> None:
        if not self.entries:
            self.entries.append({
                "quantity": self.quantity,
                "price": self.avg_entry_price,
                "time": self.entry_time
            })
    
    @property
    def side(self) -> str:
        """Position side."""
        return "long" if self.quantity > 0 else "short" if self.quantity < 0 else "flat"
    
    @property
    def is_long(self) -> bool:
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        return self.quantity < 0
    
    @property
    def is_flat(self) -> bool:
        return abs(self.quantity) < 0.0001
    
    @property
    def market_value(self, current_price: float = 0.0) -> float:
        """Calculate market value at given price."""
        return abs(self.quantity) * current_price
    
    def update_price(self, current_price: float) -> None:
        """Update unrealized PnL with current price."""
        if self.avg_entry_price > 0:
            price_diff = current_price - self.avg_entry_price
            if self.is_short:
                price_diff = -price_diff
            self.unrealized_pnl = self.quantity * price_diff
    
    def add_quantity(
        self,
        quantity: float,
        price: float,
        timestamp: datetime
    ) -> None:
        """Add to position (increase or partial close)."""
        new_quantity = self.quantity + quantity
        
        if self.quantity * new_quantity < 0:
            # Direction change - close and reverse
            close_qty = -self.quantity
            self.realized_pnl += close_qty * (price - self.avg_entry_price)
            
            # Reverse position
            self.quantity = new_quantity
            self.avg_entry_price = price
            self.entries = [{"quantity": new_quantity, "price": price, "time": timestamp}]
        else:
            # Same direction - average cost
            total_value = self.quantity * self.avg_entry_price + quantity * price
            self.quantity = new_quantity
            self.avg_entry_price = total_value / self.quantity if self.quantity != 0 else 0
            self.entries.append({"quantity": quantity, "price": price, "time": timestamp})
    
    def close(self, price: float, timestamp: datetime) -> dict:
        """Close position and return trade summary."""
        if self.is_flat:
            return {}
        
        # Calculate realized PnL
        if self.is_long:
            pnl = self.quantity * (price - self.avg_entry_price)
        else:
            pnl = abs(self.quantity) * (self.avg_entry_price - price)
        
        self.realized_pnl += pnl
        
        trade_summary = {
            "symbol": self.symbol,
            "entry_price": self.avg_entry_price,
            "exit_price": price,
            "quantity": abs(self.quantity),
            "side": self.side,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": timestamp.isoformat(),
            "realized_pnl": pnl,
            "return_pct": (price - self.avg_entry_price) / self.avg_entry_price * 100
            if self.avg_entry_price > 0 else 0
        }
        
        # Reset position
        self.quantity = 0
        self.unrealized_pnl = 0
        
        return trade_summary


@dataclass
class Portfolio:
    """Portfolio state tracking."""
    
    initial_capital: float
    base_currency: str = "USD"
    
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    
    # Transaction history
    trades: list[dict] = field(default_factory=list)
    
    # Statistics
    total_commission: float = 0.0
    total_slippage: float = 0.0
    
    def __post_init__(self) -> None:
        self.cash = self.initial_capital
    
    @property
    def equity(self) -> float:
        """Total portfolio value."""
        position_value = sum(
            pos.unrealized_pnl for pos in self.positions.values()
        )
        return self.cash + position_value
    
    @property
    def buying_power(self) -> float:
        """Available buying power."""
        return self.cash
    
    @property
    def leverage(self) -> float:
        """Current leverage (position value / equity)."""
        position_exposure = sum(
            abs(pos.quantity * pos.avg_entry_price)
            for pos in self.positions.values()
        )
        equity = self.equity
        return position_exposure / equity if equity > 0 else 0
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol."""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """Check if has active position."""
        pos = self.positions.get(symbol)
        return pos is not None and not pos.is_flat
    
    def update_prices(self, prices: dict[str, float]) -> None:
        """Update all positions with current prices."""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)
    
    def execute_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        timestamp: datetime,
        commission: float = 0.0,
        slippage: float = 0.0
    ) -> dict:
        """Execute order and update portfolio."""
        # Calculate signed quantity
        signed_qty = quantity if side == "buy" else -quantity
        
        # Calculate costs
        order_value = quantity * price
        total_cost = order_value + commission + slippage
        
        # Update cash
        if side == "buy":
            self.cash -= total_cost
        else:
            self.cash += (order_value - commission - slippage)
        
        # Update or create position
        if symbol not in self.positions:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=0.0,
                avg_entry_price=0.0,
                entry_time=timestamp
            )
        
        pos = self.positions[symbol]
        pos.add_quantity(signed_qty, price, timestamp)
        
        # Track costs
        self.total_commission += commission
        self.total_slippage += slippage
        
        # Record trade
        trade = {
            "timestamp": timestamp.isoformat(),
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "value": order_value,
            "commission": commission,
            "slippage": slippage,
            "cash_after": self.cash,
            "equity_after": self.equity
        }
        self.trades.append(trade)
        
        # Clean up flat positions
        if pos.is_flat:
            del self.positions[symbol]
        
        return trade
    
    def close_position(
        self,
        symbol: str,
        price: float,
        timestamp: datetime
    ) -> Optional[dict]:
        """Close position for symbol."""
        pos = self.positions.get(symbol)
        if not pos or pos.is_flat:
            return None
        
        # Get trade summary before closing
        trade_summary = pos.close(price, timestamp)
        
        # Update cash
        if pos.is_long:
            self.cash += pos.quantity * price
        else:
            self.cash -= abs(pos.quantity) * price
        
        # Remove position
        del self.positions[symbol]
        
        return trade_summary
    
    def get_allocation(self) -> dict[str, float]:
        """Get current asset allocation."""
        equity = self.equity
        if equity == 0:
            return {}
        
        allocation = {"cash": self.cash / equity}
        
        for symbol, pos in self.positions.items():
            if pos.avg_entry_price > 0:
                allocation[symbol] = (
                    abs(pos.quantity) * pos.avg_entry_price
                ) / equity
        
        return allocation
    
    def get_stats(self) -> dict[str, float]:
        """Get portfolio statistics."""
        equity = self.equity
        
        return {
            "cash": self.cash,
            "equity": equity,
            "total_return": (equity - self.initial_capital) / self.initial_capital,
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
            "num_positions": len(self.positions),
            "num_trades": len(self.trades),
            "leverage": self.leverage
        }
