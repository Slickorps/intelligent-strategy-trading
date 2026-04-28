"""Backtest-related API schemas."""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    """Request to run a backtest."""
    
    strategy_id: str
    start_date: date
    end_date: date
    initial_capital: float = Field(default=100000.0, gt=0)
    symbols: list[str] = Field(default_factory=list)
    timeframe: str = Field(default="1h")
    
    # Optional overrides from strategy config
    commission_rate: Optional[float] = Field(default=None, ge=0)
    slippage_model: Optional[str] = None


class BacktestStatus(BaseModel):
    """Backtest execution status."""
    
    backtest_id: str
    status: str  # pending, running, completed, failed
    progress_pct: float = Field(default=0.0, ge=0, le=100)
    current_date: Optional[datetime] = None
    message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class PerformanceMetrics(BaseModel):
    """Performance statistics."""
    
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    volatility: float
    win_rate: float
    profit_factor: float
    avg_trade: float
    total_trades: int
    winning_trades: int
    losing_trades: int


class BacktestResults(BaseModel):
    """Detailed backtest results."""
    
    backtest_id: str
    strategy_id: str
    metrics: PerformanceMetrics
    equity_curve: list[dict[str, Any]]  # timestamp, equity
    trades: list[dict[str, Any]]
    daily_returns: list[dict[str, Any]]
    monthly_returns: list[dict[str, Any]]


class BacktestResponse(BaseModel):
    """Backtest creation response."""
    
    backtest_id: str
    status: str
    estimated_completion: Optional[datetime] = None
