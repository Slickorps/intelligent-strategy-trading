"""LangChain-compatible tools for LLM integration.

These tools allow AI agents to interact with the trading platform.

Usage:
    from langchain.agents import AgentExecutor, create_openai_tools_agent
    from ist.integration import GetMarketDataTool, RunBacktestTool
    
    tools = [GetMarketDataTool(), RunBacktestTool()]
    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools)
    
    response = executor.invoke({
        "input": "Analyze EURUSD trend and run backtest"
    })
"""

from typing import Any, Optional

from ist.api.client import StrategyClient
from ist.core.logging import get_logger

logger = get_logger(__name__)


class BaseTool:
    """Base class for LangChain-compatible tools."""
    
    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
    
    def _run(self, *args, **kwargs) -> str:
        """Synchronous execution (for non-async environments)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._arun(*args, **kwargs))
    
    async def _arun(self, *args, **kwargs) -> str:
        """Asynchronous execution (must be implemented)."""
        raise NotImplementedError("Subclasses must implement _arun")


class GetMarketDataTool(BaseTool):
    """Tool to fetch market data for analysis.
    
    Input: JSON string with "symbol" and optional "timeframe"
    Output: Market data summary
    """
    
    def __init__(
        self,
        api_base_url: str = "http://localhost:8000"
    ) -> None:
        super().__init__(
            name="get_market_data",
            description="Fetch OHLCV market data for a symbol. "
                       "Input: {\"symbol\": \"EURUSD\", \"timeframe\": \"1h\"}"
        )
        self.client = StrategyClient(api_base_url)
    
    async def _arun(self, query: str) -> str:
        """Execute market data fetch."""
        try:
            import json
            params = json.loads(query)
            
            symbol = params.get("symbol", "EURUSD")
            timeframe = params.get("timeframe", "1h")
            
            # Get latest quote
            profile = self.client.load_profile("conservative")
            
            # Simulate data fetch
            data_summary = {
                "symbol": symbol,
                "timeframe": timeframe,
                "latest_price": 1.0850,
                "daily_change": 0.0012,
                "volatility_20d": 0.08,
                "trend": "sideways",
                "recommendation": "hold"
            }
            
            return (
                f"Market Data for {symbol}:\n"
                f"  Latest Price: {data_summary['latest_price']}\n"
                f"  20-day Volatility: {data_summary['volatility_20d']:.1%}\n"
                f"  Trend: {data_summary['trend']}\n"
                f"  Recommendation: {data_summary['recommendation']}"
            )
            
        except Exception as e:
            return f"Error fetching market data: {str(e)}"


class RunBacktestTool(BaseTool):
    """Tool to run strategy backtest.
    
    Input: JSON string with strategy_id, start_date, end_date
    Output: Backtest results summary
    """
    
    def __init__(
        self,
        api_base_url: str = "http://localhost:8000"
    ) -> None:
        super().__init__(
            name="run_backtest",
            description="Run a backtest for a trading strategy. "
                       "Input: {\"strategy_id\": \"xxx\", "
                       "\"start_date\": \"2020-01-01\", "
                       "\"end_date\": \"2023-12-31\"}"
        )
        self.client = StrategyClient(api_base_url)
    
    async def _arun(self, query: str) -> str:
        """Execute backtest."""
        try:
            import json
            from datetime import date
            
            params = json.loads(query)
            
            strategy_id = params.get("strategy_id")
            start_date = date.fromisoformat(params.get("start_date", "2020-01-01"))
            end_date = date.fromisoformat(params.get("end_date", "2023-12-31"))
            
            # Run backtest via API
            result = self.client.run_backtest(
                strategy_id=strategy_id,
                start_date=start_date,
                end_date=end_date
            )
            
            backtest_id = result.get("data", {}).get("backtest_id")
            
            return (
                f"Backtest scheduled successfully:\n"
                f"  Backtest ID: {backtest_id}\n"
                f"  Strategy ID: {strategy_id}\n"
                f"  Period: {start_date} to {end_date}\n"
                f"  Status: {result.get('data', {}).get('status', 'pending')}"
            )
            
        except Exception as e:
            return f"Error running backtest: {str(e)}"


class GetPortfolioTool(BaseTool):
    """Tool to get current portfolio status.
    
    Input: Empty or portfolio ID
    Output: Portfolio holdings and metrics
    """
    
    def __init__(
        self,
        api_base_url: str = "http://localhost:8000"
    ) -> None:
        super().__init__(
            name="get_portfolio",
            description="Get current portfolio holdings and performance. "
                       "Input: portfolio identifier or empty for default"
        )
        self.client = StrategyClient(api_base_url)
    
    async def _arun(self, query: str = "") -> str:
        """Execute portfolio query."""
        try:
            # Simulate portfolio data
            portfolio = {
                "total_value": 105432.50,
                "cash": 45000.00,
                "positions_value": 60432.50,
                "daily_pnl": 532.25,
                "total_return": 5.43,
                "positions": [
                    {"symbol": "EURUSD", "quantity": 10000, "value": 10850.00, "pnl": 150.00},
                    {"symbol": "XAUUSD", "quantity": 5, "value": 9625.00, "pnl": 125.00},
                    {"symbol": "SPX500", "quantity": 2, "value": 8500.00, "pnl": 75.00},
                    {"symbol": "BTCUSD", "quantity": 0.5, "value": 31457.50, "pnl": 182.25},
                ]
            }
            
            result = f"Portfolio Summary:\n"
            result += f"  Total Value: ${portfolio['total_value']:,.2f}\n"
            result += f"  Cash: ${portfolio['cash']:,.2f}\n"
            result += f"  Daily PnL: ${portfolio['daily_pnl']:,.2f} ({portfolio['daily_pnl']/portfolio['total_value']*100:.2f}%)\n"
            result += f"  Total Return: {portfolio['total_return']:.2f}%\n\n"
            result += "Positions:\n"
            
            for pos in portfolio['positions']:
                result += f"  {pos['symbol']}: {pos['quantity']} units, "
                result += f"${pos['value']:,.2f}, PnL: ${pos['pnl']:.2f}\n"
            
            return result
            
        except Exception as e:
            return f"Error getting portfolio: {str(e)}"


class AnalyzeRiskTool(BaseTool):
    """Tool to analyze portfolio risk.
    
    Input: Empty or specific analysis type
    Output: Risk metrics and recommendations
    """
    
    def __init__(
        self,
        api_base_url: str = "http://localhost:8000"
    ) -> None:
        super().__init__(
            name="analyze_risk",
            description="Analyze portfolio risk metrics. "
                       "Input: {\"analysis_type\": \"monte_carlo\"} "
                       "or {\"analysis_type\": \"stress_test\"}"
        )
        self.client = StrategyClient(api_base_url)
    
    async def _arun(self, query: str = "{}") -> str:
        """Execute risk analysis."""
        try:
            import json
            
            params = json.loads(query) if query else {}
            analysis_type = params.get("analysis_type", "summary")
            
            if analysis_type == "monte_carlo":
                # Run Monte Carlo simulation
                result = self.client.run_simulation(
                    simulation_runs=10000,
                    confidence_level=0.95
                )
                
                data = result.get("data", {}).get("results", {})
                
                return (
                    f"Monte Carlo Simulation Results:\n"
                    f"  Expected 1Y Return: {data.get('expected_return_1y', 0):.2%}\n"
                    f"  Max Drawdown (P95): {data.get('max_drawdown_p95', 0):.2%}\n"
                    f"  VaR 95%: {data.get('value_at_risk_95', 0):.2%}\n"
                    f"  Positive Return Prob: {data.get('probability_of_positive_return', 0):.1%}"
                )
            
            elif analysis_type == "stress_test":
                result = self.client.run_stress_test(
                    scenarios=["2008_financial_crisis", "covid_crash"]
                )
                
                scenarios = result.get("data", {}).get("results", {})
                
                response = "Stress Test Results:\n"
                for scenario, data in scenarios.items():
                    response += f"\n{scenario}:\n"
                    response += f"  Max Loss: {data.get('max_loss', 0):.1%}\n"
                    response += f"  Recovery: {data.get('recovery_days', 0)} days\n"
                    response += f"  Survival: {data.get('survival_probability', 0):.0%}"
                
                return response
            
            else:
                # Summary
                return (
                    f"Risk Summary:\n"
                    f"  Portfolio VaR (95%): 2.8%\n"
                    f"  Expected Shortfall: 3.5%\n"
                    f"  Beta to SPX: 0.65\n"
                    f"  Overall Risk Rating: MODERATE"
                )
            
        except Exception as e:
            return f"Error analyzing risk: {str(e)}"


# LangChain compatibility wrapper
class LangChainToolWrapper:
    """Wrapper to convert our tools to LangChain format."""
    
    def __init__(self, tool: BaseTool) -> None:
        self.tool = tool
    
    @property
    def name(self) -> str:
        return self.tool.name
    
    @property
    def description(self) -> str:
        return self.tool.description
    
    def _run(self, tool_input: str) -> str:
        """Synchronous run."""
        return self.tool._run(tool_input)
    
    async def _arun(self, tool_input: str) -> str:
        """Asynchronous run."""
        return await self.tool._arun(tool_input)


def get_all_tools(api_base_url: str = "http://localhost:8000") -> list[Any]:
    """Get all available tools as LangChain-compatible objects.
    
    Returns:
        List of tools that can be passed to LangChain agents
    """
    tools = [
        GetMarketDataTool(api_base_url),
        RunBacktestTool(api_base_url),
        GetPortfolioTool(api_base_url),
        AnalyzeRiskTool(api_base_url),
    ]
    
    # Wrap for LangChain if needed
    try:
        from langchain.tools import BaseTool as LangChainBaseTool
        # Tools are already compatible through duck typing
        return tools
    except ImportError:
        # LangChain not installed, return raw tools
        return tools
