"""Backtest engine demo.

This example demonstrates the backtest engine functionality.
"""

import asyncio
from datetime import datetime, timedelta

# Mock data provider for demo
class MockDataProvider:
    """Simple mock data provider for demonstration."""
    
    def __init__(self):
        self._data = []
    
    async def get_history(self, symbol, start, end, timeframe="1h"):
        """Generate mock historical data."""
        from ist.data.models import Bar
        
        current = start
        bars = []
        price = 1.0850
        
        while current < end:
            # Generate random price movement
            import random
            change = random.uniform(-0.001, 0.001)
            price += change
            
            bar = Bar(
                timestamp=current,
                symbol=symbol,
                open=price - 0.0001,
                high=price + 0.0002,
                low=price - 0.0002,
                close=price,
                volume=random.randint(10000, 50000)
            )
            bars.append(bar)
            
            # Increment by timeframe
            if timeframe == "1h":
                current += timedelta(hours=1)
            elif timeframe == "1d":
                current += timedelta(days=1)
            else:
                current += timedelta(hours=1)
        
        return bars


def demo_backtest_config():
    """Demonstrate backtest configuration."""
    from ist.backtest import BacktestConfig
    
    print("=" * 60)
    print("Backtest Configuration Demo")
    print("=" * 60)
    
    config = BacktestConfig(
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 12, 31),
        initial_capital=100000.0,
        symbols=["EURUSD", "GBPUSD"],
        timeframe="1h",
        commission_rate=0.001,
        slippage_model="fixed",
        slippage_amount=0.0001
    )
    
    print(f"\nBacktest Period: {config.start_date.date()} to {config.end_date.date()}")
    print(f"Initial Capital: ${config.initial_capital:,.2f}")
    print(f"Symbols: {', '.join(config.symbols)}")
    print(f"Timeframe: {config.timeframe}")
    print(f"Commission Rate: {config.commission_rate:.2%}")
    print(f"Slippage: {config.slippage_model} @ {config.slippage_amount}")
    
    return config


def demo_portfolio():
    """Demonstrate portfolio tracking."""
    from ist.backtest import Portfolio, Position
    from datetime import datetime
    
    print("\n" + "=" * 60)
    print("Portfolio Tracking Demo")
    print("=" * 60)
    
    portfolio = Portfolio(initial_capital=100000.0)
    
    print(f"\nInitial State:")
    print(f"  Cash: ${portfolio.cash:,.2f}")
    print(f"  Equity: ${portfolio.equity:,.2f}")
    
    # Execute some trades
    timestamp = datetime.utcnow()
    
    # Buy EURUSD
    portfolio.execute_order(
        symbol="EURUSD",
        side="buy",
        quantity=10000,
        price=1.0850,
        timestamp=timestamp,
        commission=10.85,
        slippage=1.09
    )
    
    print(f"\nAfter buying 10,000 EURUSD @ 1.0850:")
    print(f"  Cash: ${portfolio.cash:,.2f}")
    print(f"  Equity: ${portfolio.equity:,.2f}")
    
    # Update price
    portfolio.update_prices({"EURUSD": 1.0900})
    
    pos = portfolio.get_position("EURUSD")
    print(f"\nAfter price update to 1.0900:")
    print(f"  Position PnL: ${pos.unrealized_pnl:,.2f}")
    print(f"  Equity: ${portfolio.equity:,.2f}")
    
    # Sell half
    portfolio.execute_order(
        symbol="EURUSD",
        side="sell",
        quantity=5000,
        price=1.0900,
        timestamp=timestamp,
        commission=5.45,
        slippage=0.55
    )
    
    print(f"\nAfter selling 5,000 EURUSD @ 1.0900:")
    print(f"  Cash: ${portfolio.cash:,.2f}")
    print(f"  Equity: ${portfolio.equity:,.2f}")
    print(f"  Realized PnL: ${pos.realized_pnl:,.2f}")
    
    # Get stats
    stats = portfolio.get_stats()
    print(f"\nPortfolio Statistics:")
    print(f"  Total Return: {stats['total_return']:.2%}")
    print(f"  Total Commission: ${stats['total_commission']:,.2f}")
    print(f"  Number of Trades: {stats['num_trades']}")
    print(f"  Leverage: {stats['leverage']:.2f}x")


def demo_analytics():
    """Demonstrate performance analytics."""
    from ist.backtest import PerformanceAnalyzer
    
    print("\n" + "=" * 60)
    print("Performance Analytics Demo")
    print("=" * 60)
    
    # Sample equity curve
    equity_curve = [
        {"date": "2020-01-01", "equity": 100000},
        {"date": "2020-02-01", "equity": 102000},
        {"date": "2020-03-01", "equity": 101000},
        {"date": "2020-04-01", "equity": 104000},
        {"date": "2020-05-01", "equity": 103000},
        {"date": "2020-06-01", "equity": 106000},
        {"date": "2020-07-01", "equity": 105000},
        {"date": "2020-08-01", "equity": 108000},
        {"date": "2020-09-01", "equity": 107000},
        {"date": "2020-10-01", "equity": 110000},
        {"date": "2020-11-01", "equity": 109000},
        {"date": "2020-12-01", "equity": 112000},
    ]
    
    # Sample trades
    trades = [
        {"realized_pnl": 1500},
        {"realized_pnl": -800},
        {"realized_pnl": 2000},
        {"realized_pnl": 1200},
        {"realized_pnl": -300},
    ]
    
    analyzer = PerformanceAnalyzer()
    analyzer.load_data(equity_curve, trades)
    
    metrics = analyzer.calculate_metrics(initial_capital=100000)
    
    print(f"\nPerformance Metrics:")
    print(f"  Total Return: {metrics.total_return:.2%}")
    print(f"  Annualized Return: {metrics.annualized_return:.2%}")
    print(f"  Volatility: {metrics.volatility:.2%}")
    print(f"  Max Drawdown: {metrics.max_drawdown:.2%}")
    print(f"  Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"  Sortino Ratio: {metrics.sortino_ratio:.2f}")
    print(f"  Calmar Ratio: {metrics.calmar_ratio:.2f}")
    
    print(f"\nTrade Metrics:")
    print(f"  Total Trades: {metrics.total_trades}")
    print(f"  Win Rate: {metrics.win_rate:.1%}")
    print(f"  Profit Factor: {metrics.profit_factor:.2f}")
    print(f"  Avg Trade: ${metrics.avg_trade:,.2f}")
    print(f"  Avg Win: ${metrics.avg_win:,.2f}")
    print(f"  Avg Loss: ${metrics.avg_loss:,.2f}")
    print(f"  Expectancy: ${metrics.expectancy:,.2f}")
    
    # Generate report
    report = analyzer.generate_report(metrics)
    print(f"\nQualitative Assessment:")
    print(f"  {report['assessment']}")


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("Intelligent Strategy Trading - Backtest Demo")
    print("=" * 60)
    
    try:
        demo_backtest_config()
        demo_portfolio()
        demo_analytics()
        
        print("\n" + "=" * 60)
        print("Backtest Demo completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
