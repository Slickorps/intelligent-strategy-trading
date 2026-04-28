"""Event-driven backtest engine."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, Callable

import pandas as pd

from ist.core.events import EventBus, EventType
from ist.core.logging import get_logger
from ist.data.models import Bar
from ist.data.provider import DataProvider
from ist.strategy.executor import StrategyExecutor

logger = get_logger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""
    
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100000.0
    symbols: list[str] = field(default_factory=list)
    timeframe: str = "1h"
    
    # Execution settings
    commission_rate: float = 0.001  # 0.1%
    slippage_model: str = "fixed"  # fixed, percentage
    slippage_amount: float = 0.0001  # 1 pip for forex
    
    # Risk settings
    margin_requirement: float = 0.02  # 50:1 leverage
    
    def __post_init__(self) -> None:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")


@dataclass
class BacktestState:
    """Current state of backtest execution."""
    
    timestamp: datetime
    equity: float
    cash: float
    positions: dict[str, dict] = field(default_factory=dict)
    
    # Daily tracking
    daily_returns: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    
    # Statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # High water mark
    peak_equity: float = 0.0
    max_drawdown: float = 0.0


class EventLoop:
    """Event loop for backtest execution.
    
    Simulates market events in chronological order.
    """
    
    def __init__(
        self,
        data_provider: DataProvider,
        event_bus: Optional[EventBus] = None
    ) -> None:
        self.data_provider = data_provider
        self.event_bus = event_bus or EventBus()
        self._timeline: list[datetime] = []
        self._current_index: int = 0
        self._bar_data: dict[datetime, dict[str, Bar]] = {}
    
    async def load_data(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str = "1h"
    ) -> None:
        """Load historical data for simulation."""
        logger.info(
            "Loading backtest data",
            symbols=symbols,
            start=start,
            end=end,
            timeframe=timeframe
        )
        
        all_bars: dict[datetime, dict[str, Bar]] = {}
        
        for symbol in symbols:
            bars = await self.data_provider.get_history(
                symbol, start, end, timeframe
            )
            
            for bar in bars:
                if bar.timestamp not in all_bars:
                    all_bars[bar.timestamp] = {}
                all_bars[bar.timestamp][symbol] = bar
        
        self._bar_data = all_bars
        self._timeline = sorted(all_bars.keys())
        
        logger.info(
            "Data loaded",
            total_bars=len(self._timeline),
            date_range=f"{self._timeline[0]} to {self._timeline[-1]}"
            if self._timeline else "empty"
        )
    
    def next(self) -> Optional[tuple[datetime, dict[str, Bar]]]:
        """Get next timestamp and bar data."""
        if self._current_index >= len(self._timeline):
            return None
        
        timestamp = self._timeline[self._current_index]
        bars = self._bar_data.get(timestamp, {})
        
        self._current_index += 1
        
        return timestamp, bars
    
    def peek(self) -> Optional[datetime]:
        """Preview next timestamp without advancing."""
        if self._current_index >= len(self._timeline):
            return None
        return self._timeline[self._current_index]
    
    def reset(self) -> None:
        """Reset event loop to beginning."""
        self._current_index = 0
    
    def get_progress(self) -> float:
        """Get execution progress (0.0 to 1.0)."""
        if not self._timeline:
            return 0.0
        return self._current_index / len(self._timeline)
    
    @property
    def is_complete(self) -> bool:
        """Check if all events processed."""
        return self._current_index >= len(self._timeline)


class BacktestEngine:
    """Main backtest engine.
    
    Orchestrates data loading, event simulation,
    strategy execution, and result tracking.
    """
    
    def __init__(
        self,
        strategy_executor: StrategyExecutor,
        data_provider: DataProvider,
        event_bus: Optional[EventBus] = None
    ) -> None:
        self.strategy_executor = strategy_executor
        self.data_provider = data_provider
        self.event_bus = event_bus or EventBus()
        
        self.event_loop = EventLoop(data_provider, event_bus)
        self.config: Optional[BacktestConfig] = None
        self.state: Optional[BacktestState] = None
        
        self._backtest_id: Optional[str] = None
        self._status: str = "idle"  # idle, running, completed, failed
        self._error_message: Optional[str] = None
    
    def setup(
        self,
        backtest_id: str,
        config: BacktestConfig
    ) -> None:
        """Configure backtest run."""
        self._backtest_id = backtest_id
        self.config = config
        
        # Initialize state
        self.state = BacktestState(
            timestamp=config.start_date,
            equity=config.initial_capital,
            cash=config.initial_capital,
            peak_equity=config.initial_capital
        )
        
        self._status = "configured"
        
        logger.info(
            "Backtest configured",
            backtest_id=backtest_id,
            symbols=config.symbols,
            capital=config.initial_capital
        )
    
    async def run(
        self,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> dict[str, Any]:
        """Execute backtest.
        
        Args:
            progress_callback: Optional callback for progress updates
            
        Returns:
            Backtest results dictionary
        """
        if not self.config or not self.state:
            raise RuntimeError("Backtest not configured. Call setup() first.")
        
        self._status = "running"
        
        try:
            # Load data
            await self.event_loop.load_data(
                self.config.symbols,
                self.config.start_date,
                self.config.end_date,
                self.config.timeframe
            )
            
            self.event_loop.reset()
            
            # Main event loop
            while not self.event_loop.is_complete:
                result = self.event_loop.next()
                if result is None:
                    break
                
                timestamp, bars = result
                
                # Update state timestamp
                self.state.timestamp = timestamp
                
                # Prepare bar data for strategy
                bar_data = self._prepare_bar_data(bars)
                
                # Execute strategies
                portfolio_state = self._get_portfolio_state()
                
                execution_results = self.strategy_executor.execute_all(
                    bar_data,
                    portfolio_state
                )
                
                # Process actions
                for strategy_id, exec_result in execution_results.items():
                    if exec_result.success:
                        for action in exec_result.actions:
                            self._process_action(action, bars)
                
                # Update portfolio value
                self._update_portfolio_value(bars)
                
                # Track daily returns
                self._track_daily_return()
                
                # Progress callback
                if progress_callback:
                    progress_callback(self.event_loop.get_progress())
            
            self._status = "completed"
            
            return self._generate_results()
            
        except Exception as e:
            self._status = "failed"
            self._error_message = str(e)
            logger.error("Backtest failed", error=str(e))
            raise
    
    def _prepare_bar_data(self, bars: dict[str, Bar]) -> dict[str, Any]:
        """Convert bars to strategy input format."""
        bar_data = {
            "timestamp": self.state.timestamp.isoformat(),
            "bars": {}
        }
        
        for symbol, bar in bars.items():
            bar_data["bars"][symbol] = {
                "symbol": bar.symbol,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume
            }
        
        # Also provide primary symbol data at top level
        if self.config and self.config.symbols:
            primary = self.config.symbols[0]
            if primary in bars:
                bar = bars[primary]
                bar_data.update({
                    "symbol": bar.symbol,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                })
        
        return bar_data
    
    def _get_portfolio_state(self) -> dict[str, Any]:
        """Get current portfolio state for strategies."""
        return {
            "cash": self.state.cash,
            "equity": self.state.equity,
            "positions": self.state.positions,
            "timestamp": self.state.timestamp.isoformat()
        }
    
    def _process_action(
        self,
        action: dict[str, Any],
        bars: dict[str, Bar]
    ) -> None:
        """Process trading action from strategy."""
        symbol = action.get("symbol", "")
        side = action.get("side", "")
        size_pct = action.get("size_pct", 0.0)
        
        if symbol not in bars:
            return
        
        bar = bars[symbol]
        
        # Calculate position size
        position_value = self.state.equity * size_pct
        
        # Apply slippage
        if side == "buy":
            fill_price = bar.close * (1 + self.config.slippage_amount)
        else:
            fill_price = bar.close * (1 - self.config.slippage_amount)
        
        # Calculate quantity (for forex, this is units)
        quantity = position_value / fill_price
        
        # Calculate commission
        commission = position_value * self.config.commission_rate
        
        # Update cash
        if side == "buy":
            self.state.cash -= position_value + commission
        else:
            self.state.cash += position_value - commission
        
        # Update positions
        if symbol not in self.state.positions:
            self.state.positions[symbol] = {
                "quantity": 0.0,
                "avg_entry": 0.0,
                "unrealized_pnl": 0.0
            }
        
        pos = self.state.positions[symbol]
        
        if side == "buy":
            # Add to position
            total_cost = pos["quantity"] * pos["avg_entry"] + quantity * fill_price
            pos["quantity"] += quantity
            pos["avg_entry"] = total_cost / pos["quantity"] if pos["quantity"] > 0 else 0
        else:
            # Reduce position
            pos["quantity"] -= quantity
            if pos["quantity"] <= 0.0001:  # Close position
                del self.state.positions[symbol]
        
        # Record trade
        trade = {
            "timestamp": self.state.timestamp.isoformat(),
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": fill_price,
            "value": position_value,
            "commission": commission,
            "equity": self.state.equity
        }
        self.state.trades.append(trade)
        self.state.total_trades += 1
    
    def _update_portfolio_value(self, bars: dict[str, Bar]) -> None:
        """Update portfolio equity based on current prices."""
        position_value = 0.0
        
        for symbol, pos in self.state.positions.items():
            if symbol in bars:
                price = bars[symbol].close
                value = pos["quantity"] * price
                position_value += value
                
                # Calculate unrealized PnL
                if pos["avg_entry"] > 0:
                    pos["unrealized_pnl"] = (price - pos["avg_entry"]) * pos["quantity"]
        
        self.state.equity = self.state.cash + position_value
        
        # Update peak and drawdown
        if self.state.equity > self.state.peak_equity:
            self.state.peak_equity = self.state.equity
        
        current_dd = (self.state.peak_equity - self.state.equity) / self.state.peak_equity
        self.state.max_drawdown = max(self.state.max_drawdown, current_dd)
    
    def _track_daily_return(self) -> None:
        """Track daily returns for analytics."""
        # Only record once per day
        if not self.state.daily_returns:
            should_record = True
        else:
            last_date = self.state.daily_returns[-1]["date"]
            current_date = self.state.timestamp.date()
            should_record = current_date != last_date
        
        if should_record:
            self.state.daily_returns.append({
                "date": self.state.timestamp.date(),
                "equity": self.state.equity
            })
    
    def _generate_results(self) -> dict[str, Any]:
        """Generate final backtest results."""
        if not self.state:
            return {}
        
        # Calculate returns
        total_return = (
            self.state.equity - self.config.initial_capital
        ) / self.config.initial_capital
        
        # Calculate daily return stats
        daily_returns = []
        for i in range(1, len(self.state.daily_returns)):
            prev = self.state.daily_returns[i-1]["equity"]
            curr = self.state.daily_returns[i]["equity"]
            daily_returns.append((curr - prev) / prev)
        
        # Calculate Sharpe (simplified, assuming 252 trading days)
        if daily_returns:
            mean_return = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)
            std_dev = variance ** 0.5
            sharpe = (mean_return * 252) / (std_dev * (252 ** 0.5)) if std_dev > 0 else 0
        else:
            sharpe = 0
        
        return {
            "backtest_id": self._backtest_id,
            "status": self._status,
            "config": {
                "start_date": self.config.start_date.isoformat(),
                "end_date": self.config.end_date.isoformat(),
                "initial_capital": self.config.initial_capital,
                "symbols": self.config.symbols
            },
            "final_equity": self.state.equity,
            "total_return": total_return,
            "max_drawdown": self.state.max_drawdown,
            "sharpe_ratio": sharpe,
            "total_trades": self.state.total_trades,
            "trades": self.state.trades,
            "equity_curve": self.state.daily_returns
        }
    
    def get_status(self) -> dict[str, Any]:
        """Get current backtest status."""
        return {
            "backtest_id": self._backtest_id,
            "status": self._status,
            "progress": self.event_loop.get_progress() if self.event_loop else 0,
            "current_timestamp": self.state.timestamp.isoformat() if self.state else None,
            "current_equity": self.state.equity if self.state else None,
            "error": self._error_message
        }
    
    def stop(self) -> None:
        """Stop running backtest."""
        self._status = "stopped"
        logger.info("Backtest stopped", backtest_id=self._backtest_id)
