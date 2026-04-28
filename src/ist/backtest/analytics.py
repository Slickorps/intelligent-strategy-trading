"""Performance analytics and metrics calculation."""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import pandas as pd


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    
    # Return metrics
    total_return: float = 0.0
    annualized_return: float = 0.0
    
    # Risk metrics
    volatility: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0  # days
    
    # Risk-adjusted returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    
    # Drawdown recovery
    recovery_factor: float = 0.0
    
    @property
    def expectancy(self) -> float:
        """Expected return per trade."""
        if self.total_trades == 0:
            return 0.0
        return (self.win_rate * self.avg_win +
                (1 - self.win_rate) * self.avg_loss)


class PerformanceAnalyzer:
    """Analyze backtest performance."""
    
    def __init__(self) -> None:
        self.equity_curve: list[dict] = []
        self.trades: list[dict] = []
    
    def load_data(
        self,
        equity_curve: list[dict],
        trades: list[dict]
    ) -> None:
        """Load backtest data for analysis."""
        self.equity_curve = equity_curve
        self.trades = trades
    
    def calculate_metrics(
        self,
        initial_capital: float,
        risk_free_rate: float = 0.02
    ) -> PerformanceMetrics:
        """Calculate all performance metrics."""
        if not self.equity_curve or len(self.equity_curve) < 2:
            return PerformanceMetrics()
        
        # Extract equity values
        equity_values = [e["equity"] for e in self.equity_curve]
        
        # Calculate returns
        total_return = (equity_values[-1] - initial_capital) / initial_capital
        
        # Calculate daily returns
        daily_returns = []
        for i in range(1, len(equity_values)):
            ret = (equity_values[i] - equity_values[i-1]) / equity_values[i-1]
            daily_returns.append(ret)
        
        # Annualized metrics (252 trading days)
        trading_days = len(daily_returns)
        if trading_days > 0:
            mean_daily_return = sum(daily_returns) / trading_days
            annualized_return = (1 + mean_daily_return) ** 252 - 1
            
            # Volatility
            if len(daily_returns) > 1:
                variance = sum(
                    (r - mean_daily_return) ** 2 for r in daily_returns
                ) / (len(daily_returns) - 1)
                daily_vol = math.sqrt(variance)
                volatility = daily_vol * math.sqrt(252)
            else:
                volatility = 0.0
        else:
            annualized_return = 0.0
            volatility = 0.0
        
        # Sharpe ratio
        if volatility > 0:
            sharpe = (annualized_return - risk_free_rate) / volatility
        else:
            sharpe = 0.0
        
        # Sortino ratio (downside deviation only)
        downside_returns = [r for r in daily_returns if r < 0]
        if downside_returns:
            downside_mean = sum(downside_returns) / len(downside_returns)
            downside_variance = sum(
                (r - downside_mean) ** 2 for r in downside_returns
            ) / len(downside_returns)
            downside_dev = math.sqrt(downside_variance) * math.sqrt(252)
            sortino = (annualized_return - risk_free_rate) / downside_dev if downside_dev > 0 else 0.0
        else:
            sortino = 0.0
        
        # Max drawdown
        max_dd, dd_duration = self._calculate_max_drawdown(equity_values)
        
        # Calmar ratio
        calmar = annualized_return / max_dd if max_dd > 0 else 0.0
        
        # Trade metrics
        trade_metrics = self._calculate_trade_metrics()
        
        # Recovery factor
        recovery = total_return / max_dd if max_dd > 0 else 0.0
        
        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            max_drawdown=max_dd,
            max_drawdown_duration=dd_duration,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            recovery_factor=recovery,
            **trade_metrics
        )
    
    def _calculate_max_drawdown(
        self,
        equity_values: list[float]
    ) -> tuple[float, int]:
        """Calculate maximum drawdown and duration."""
        max_dd = 0.0
        max_dd_duration = 0
        
        peak = equity_values[0]
        peak_idx = 0
        
        for i, value in enumerate(equity_values):
            if value > peak:
                peak = value
                peak_idx = i
            
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
                max_dd_duration = i - peak_idx
        
        return max_dd, max_dd_duration
    
    def _calculate_trade_metrics(self) -> dict[str, Any]:
        """Calculate trade-related metrics."""
        if not self.trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_trade": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0
            }
        
        total = len(self.trades)
        
        # Calculate realized PnL for each trade
        pnls = []
        gross_profit = 0.0
        gross_loss = 0.0
        
        for trade in self.trades:
            # Simplified PnL calculation
            pnl = trade.get("realized_pnl", 0.0)
            pnls.append(pnl)
            
            if pnl > 0:
                gross_profit += pnl
            else:
                gross_loss += abs(pnl)
        
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        
        winning = len(wins)
        losing = len(losses)
        
        win_rate = winning / total if total > 0 else 0.0
        
        avg_trade = sum(pnls) / total if total > 0 else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float('inf')
        )
        
        return {
            "total_trades": total,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": win_rate,
            "avg_trade": avg_trade,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor
        }
    
    def generate_report(self, metrics: PerformanceMetrics) -> dict[str, Any]:
        """Generate comprehensive report."""
        return {
            "summary": {
                "total_return": f"{metrics.total_return:.2%}",
                "annualized_return": f"{metrics.annualized_return:.2%}",
                "sharpe_ratio": f"{metrics.sharpe_ratio:.2f}",
                "max_drawdown": f"{metrics.max_drawdown:.2%}",
                "win_rate": f"{metrics.win_rate:.1%}",
                "total_trades": metrics.total_trades
            },
            "risk_metrics": {
                "volatility": f"{metrics.volatility:.2%}",
                "sortino_ratio": f"{metrics.sortino_ratio:.2f}",
                "calmar_ratio": f"{metrics.calmar_ratio:.2f}",
                "max_drawdown_duration": f"{metrics.max_drawdown_duration} days",
                "recovery_factor": f"{metrics.recovery_factor:.2f}"
            },
            "trade_metrics": {
                "total_trades": metrics.total_trades,
                "winning_trades": metrics.winning_trades,
                "losing_trades": metrics.losing_trades,
                "win_rate": f"{metrics.win_rate:.1%}",
                "avg_trade": f"${metrics.avg_trade:,.2f}",
                "avg_win": f"${metrics.avg_win:,.2f}",
                "avg_loss": f"${metrics.avg_loss:,.2f}",
                "profit_factor": f"{metrics.profit_factor:.2f}",
                "expectancy": f"${metrics.expectancy:,.2f}"
            },
            "assessment": self._assess_performance(metrics)
        }
    
    def _assess_performance(self, metrics: PerformanceMetrics) -> str:
        """Provide qualitative assessment."""
        scores = []
        
        # Sharpe ratio assessment
        if metrics.sharpe_ratio > 1.5:
            scores.append("Excellent risk-adjusted returns")
        elif metrics.sharpe_ratio > 1.0:
            scores.append("Good risk-adjusted returns")
        elif metrics.sharpe_ratio < 0.5:
            scores.append("Poor risk-adjusted returns")
        
        # Win rate assessment
        if metrics.win_rate > 0.55:
            scores.append("Strong win rate")
        elif metrics.win_rate < 0.4:
            scores.append("Low win rate - consider risk management")
        
        # Drawdown assessment
        if metrics.max_drawdown > 0.2:
            scores.append("High drawdown - consider reducing position sizes")
        elif metrics.max_drawdown < 0.05:
            scores.append("Excellent drawdown control")
        
        # Profit factor
        if metrics.profit_factor > 2.0:
            scores.append("Strong profit factor")
        elif metrics.profit_factor < 1.0:
            scores.append("Losing strategy - needs improvement")
        
        if not scores:
            return "Average performance - no major strengths or weaknesses"
        
        return "; ".join(scores)
    
    def get_monthly_returns(self) -> list[dict]:
        """Calculate monthly returns from equity curve."""
        if not self.equity_curve:
            return []
        
        # Group by month
        monthly_data: dict[str, list[float]] = {}
        
        for entry in self.equity_curve:
            date = entry.get("date")
            equity = entry.get("equity")
            
            if isinstance(date, str):
                date = datetime.fromisoformat(date).date()
            
            month_key = date.strftime("%Y-%m") if hasattr(date, 'strftime') else str(date)[:7]
            
            if month_key not in monthly_data:
                monthly_data[month_key] = []
            monthly_data[month_key].append(equity)
        
        # Calculate monthly returns
        months = sorted(monthly_data.keys())
        monthly_returns = []
        
        for i, month in enumerate(months):
            if i == 0:
                continue
            
            prev_equity = monthly_data[months[i-1]][-1]
            curr_equity = monthly_data[month][-1]
            
            ret = (curr_equity - prev_equity) / prev_equity
            
            monthly_returns.append({
                "month": month,
                "return": ret,
                "start_equity": prev_equity,
                "end_equity": curr_equity
            })
        
        return monthly_returns
