"""Live trading engine.

Orchestrates strategy execution with real market data
and order execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional

from ist.core.events import EventBus, EventType
from ist.core.exceptions import ExecutionError
from ist.core.logging import get_logger
from ist.execution.adapter import BrokerAdapter
from ist.execution.oms import OrderManagementSystem, OrderState
from ist.strategy.executor import StrategyExecutor

logger = get_logger(__name__)


class TradingMode(Enum):
    """Trading execution mode."""
    BACKTEST = auto()  # Historical simulation
    PAPER = auto()     # Live data, simulated execution
    LIVE = auto()      # Live data, real execution


@dataclass
class LiveTradingConfig:
    """Configuration for live trading."""
    
    mode: TradingMode = TradingMode.PAPER
    max_positions: int = 10
    max_orders_per_minute: int = 10
    circuit_breaker_enabled: bool = True
    circuit_breaker_threshold: int = 5  # Consecutive errors
    
    # Risk limits
    max_position_size_pct: float = 0.10  # 10% per position
    max_daily_loss_pct: float = 0.02     # 2% daily stop


@dataclass
class TradingState:
    """Current trading state."""
    
    is_running: bool = False
    mode: TradingMode = TradingMode.PAPER
    
    # Statistics
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    
    # Circuit breaker
    consecutive_errors: int = 0
    circuit_breaker_triggered: bool = False
    
    # Daily tracking
    daily_pnl: float = 0.0
    max_daily_pnl: float = 0.0
    
    # Timestamp
    last_update: datetime = field(default_factory=datetime.utcnow)


class LiveTradingEngine:
    """Live trading engine.
    
    Coordinates between:
    - Strategy execution (signals)
    - Order management (OMS)
    - Broker execution
    - Risk management
    
    Usage:
        engine = LiveTradingEngine(
            strategy_executor=strategy_exec,
            broker=paper_broker,
            config=LiveTradingConfig(mode=TradingMode.PAPER)
        )
        
        await engine.start()
        # Engine now processes signals and executes orders
        await engine.stop()
    """
    
    def __init__(
        self,
        strategy_executor: StrategyExecutor,
        broker: BrokerAdapter,
        config: Optional[LiveTradingConfig] = None,
        event_bus: Optional[EventBus] = None
    ) -> None:
        self.strategy_executor = strategy_executor
        self.broker = broker
        self.config = config or LiveTradingConfig()
        self.event_bus = event_bus or EventBus()
        
        # Order management
        self.oms = OrderManagementSystem(broker)
        
        # State
        self.state = TradingState(mode=self.config.mode)
        
        # Position tracking
        self._positions: dict[str, dict] = {}
        
        # Subscribe to signals
        self.event_bus.subscribe(
            EventType.SIGNAL_GENERATED,
            self._on_signal
        )
    
    async def start(self) -> None:
        """Start live trading."""
        logger.info(
            "Starting live trading engine",
            mode=self.config.mode.name
        )
        
        # Connect to broker
        if not self.broker.is_connected:
            connected = await self.broker.connect()
            if not connected:
                raise ExecutionError("Failed to connect to broker")
        
        # Get account info
        account = await self.broker.get_account_info()
        logger.info(
            "Account connected",
            account_id=account.account_id,
            equity=account.equity,
            cash=account.cash
        )
        
        self.state.is_running = True
        self.state.circuit_breaker_triggered = False
        self.state.consecutive_errors = 0
        
        self.event_bus.emit(
            self.event_bus.create_event(
                EventType.STRATEGY_STARTED,
                {"mode": self.config.mode.name},
                "live_trading_engine"
            )
        )
    
    async def stop(self) -> None:
        """Stop live trading."""
        logger.info("Stopping live trading engine")
        
        self.state.is_running = False
        
        # Cancel pending orders
        open_orders = self.oms.get_open_orders()
        for order in open_orders:
            await self.oms.cancel_order(order.internal_id)
        
        # Disconnect
        if self.broker.is_connected:
            await self.broker.disconnect()
        
        self.event_bus.emit(
            self.event_bus.create_event(
                EventType.STRATEGY_STOPPED,
                {"orders_filled": self.state.orders_filled},
                "live_trading_engine"
            )
        )
    
    async def _on_signal(self, event) -> None:
        """Handle trading signal from strategy."""
        if not self.state.is_running:
            return
        
        if self.state.circuit_breaker_triggered:
            logger.warning("Circuit breaker active, ignoring signal")
            return
        
        try:
            strategy_id = event.payload.get("strategy_id")
            actions = event.payload.get("actions", [])
            
            for action in actions:
                await self._process_action(action)
            
            # Reset error count on success
            self.state.consecutive_errors = 0
            
        except Exception as e:
            self.state.consecutive_errors += 1
            logger.error(
                "Error processing signal",
                error=str(e),
                consecutive_errors=self.state.consecutive_errors
            )
            
            # Check circuit breaker
            if (self.config.circuit_breaker_enabled and
                self.state.consecutive_errors >= self.config.circuit_breaker_threshold):
                await self._trigger_circuit_breaker()
    
    async def _process_action(self, action: dict[str, Any]) -> None:
        """Process trading action."""
        symbol = action.get("symbol")
        side_str = action.get("side", "buy")
        size_pct = action.get("size_pct", 0.0)
        
        if not symbol or size_pct <= 0:
            return
        
        # Check risk limits
        if not await self._check_risk_limits(symbol, size_pct):
            logger.warning(
                "Risk limit blocked order",
                symbol=symbol,
                size_pct=size_pct
            )
            return
        
        # Get account info for sizing
        account = await self.broker.get_account_info()
        position_value = account.equity * size_pct
        
        # Get current price
        quote = await self.broker.get_quote(symbol)
        if not quote:
            logger.warning(f"No quote available for {symbol}")
            return
        
        # Calculate quantity
        quantity = position_value / quote.close
        
        # Create order
        try:
            from ist.execution.adapter import OrderSide
            side = OrderSide.BUY if side_str == "buy" else OrderSide.SELL
            
            order_id = self.oms.create_order(
                symbol=symbol,
                side=side,
                quantity=quantity
            )
            
            # Submit order
            result = await self.oms.submit_order(order_id)
            
            self.state.orders_submitted += 1
            
            if result.status.name == "FILLED":
                self.state.orders_filled += 1
            elif result.status.name == "REJECTED":
                self.state.orders_rejected += 1
            
            logger.info(
                "Order processed",
                symbol=symbol,
                side=side_str,
                quantity=quantity,
                status=result.status.name
            )
            
        except Exception as e:
            logger.error(f"Order failed: {e}")
            raise
    
    async def _check_risk_limits(
        self,
        symbol: str,
        size_pct: float
    ) -> bool:
        """Check if order complies with risk limits."""
        # Position size limit
        if size_pct > self.config.max_position_size_pct:
            return False
        
        # Daily loss limit
        if self.state.daily_pnl < -self.config.max_daily_loss_pct:
            return False
        
        # Max positions
        if len(self._positions) >= self.config.max_positions:
            if symbol not in self._positions:
                return False
        
        return True
    
    async def _trigger_circuit_breaker(self) -> None:
        """Trigger circuit breaker on excessive errors."""
        logger.critical(
            "CIRCUIT BREAKER TRIGGERED",
            errors=self.state.consecutive_errors
        )
        
        self.state.circuit_breaker_triggered = True
        
        # Cancel all pending orders
        open_orders = self.oms.get_open_orders()
        for order in open_orders:
            await self.oms.cancel_order(order.internal_id)
        
        # Emit alert
        self.event_bus.emit(
            self.event_bus.create_event(
                EventType.RISK_BREACH,
                {
                    "type": "circuit_breaker",
                    "consecutive_errors": self.state.consecutive_errors
                },
                "live_trading_engine"
            )
        )
    
    async def reset_circuit_breaker(self) -> None:
        """Reset circuit breaker after manual intervention."""
        logger.warning("Circuit breaker reset")
        self.state.circuit_breaker_triggered = False
        self.state.consecutive_errors = 0
    
    def get_status(self) -> dict[str, Any]:
        """Get current engine status."""
        return {
            "is_running": self.state.is_running,
            "mode": self.state.mode.name,
            "orders": {
                "submitted": self.state.orders_submitted,
                "filled": self.state.orders_filled,
                "rejected": self.state.orders_rejected
            },
            "circuit_breaker": {
                "triggered": self.state.circuit_breaker_triggered,
                "consecutive_errors": self.state.consecutive_errors
            },
            "daily_pnl": self.state.daily_pnl,
            "positions": len(self._positions)
        }
    
    def switch_mode(self, mode: TradingMode) -> None:
        """Switch trading mode (requires restart)."""
        if self.state.is_running:
            raise ExecutionError("Cannot switch mode while running. Stop first.")
        
        self.config.mode = mode
        self.state.mode = mode
        
        logger.info(f"Trading mode switched to {mode.name}")
