"""Data source nodes for market data input."""

from typing import Any, Optional

from ist.data.models import Bar
from ist.strategy.nodes.base import (
    NodeExecutionContext,
    NodeOutput,
    NodeType,
    StrategyNode,
)


class DataSourceNode(StrategyNode):
    """Node that provides market data input.
    
    Params:
        symbol: Trading symbol (e.g., "EURUSD")
        timeframe: Data timeframe (e.g., "1h", "1d")
        source: Data source identifier
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.DATA_SOURCE, params)
        self.symbol = self.params.get("symbol", "EURUSD")
        self.timeframe = self.params.get("timeframe", "1h")
    
    def _setup_inputs(self) -> None:
        """Data source has no inputs - it's a source node."""
        pass
    
    def _setup_outputs(self) -> None:
        """Provide OHLCV data and current price."""
        self.outputs["bar"] = NodeOutput("bar", "Bar")
        self.outputs["open"] = NodeOutput("open", "float")
        self.outputs["high"] = NodeOutput("high", "float")
        self.outputs["low"] = NodeOutput("low", "float")
        self.outputs["close"] = NodeOutput("close", "float")
        self.outputs["volume"] = NodeOutput("volume", "float")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Extract data from execution context."""
        bar_data = context.bar_data
        
        if bar_data is None:
            return False
        
        # Set outputs from bar data
        self.set_output("bar", bar_data)
        self.set_output("open", bar_data.get("open", 0.0))
        self.set_output("high", bar_data.get("high", 0.0))
        self.set_output("low", bar_data.get("low", 0.0))
        self.set_output("close", bar_data.get("close", 0.0))
        self.set_output("volume", bar_data.get("volume", 0.0))
        
        return True


class MultiDataSourceNode(StrategyNode):
    """Node that provides data for multiple symbols.
    
    Params:
        symbols: List of trading symbols
        timeframe: Data timeframe
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.DATA_SOURCE, params)
        self.symbols = self.params.get("symbols", ["EURUSD"])
        self.timeframe = self.params.get("timeframe", "1h")
    
    def _setup_inputs(self) -> None:
        pass
    
    def _setup_outputs(self) -> None:
        """Provide data dictionary keyed by symbol."""
        self.outputs["data_by_symbol"] = NodeOutput("data_by_symbol", "dict")
        self.outputs["symbol_list"] = NodeOutput("symbol_list", "list")
        
        # Individual symbol outputs
        for symbol in self.symbols:
            self.outputs[f"{symbol}_close"] = NodeOutput(f"{symbol}_close", "float")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Extract multi-symbol data from context."""
        data = context.custom_data.get("multi_bars", {})
        
        self.set_output("data_by_symbol", data)
        self.set_output("symbol_list", self.symbols)
        
        for symbol in self.symbols:
            bar = data.get(symbol, {})
            self.set_output(f"{symbol}_close", bar.get("close", 0.0))
        
        return True


class DataFilterNode(StrategyNode):
    """Filter and transform data.
    
    Params:
        filter_type: Type of filter ("sma", "ema", "range")
        period: Filter period
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.TRANSFORM, params)
        self.filter_type = self.params.get("filter_type", "sma")
        self.period = self.params.get("period", 14)
    
    def _setup_inputs(self) -> None:
        self.inputs["data"] = NodeInput("data", "float", required=True)
        self.inputs["historical"] = NodeInput("historical", "list", required=False)
    
    def _setup_outputs(self) -> None:
        self.outputs["filtered"] = NodeOutput("filtered", "float")
        self.outputs["trend"] = NodeOutput("trend", "str")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Apply filter to input data."""
        data = self.get_input("data")
        historical = self.get_input("historical") or []
        
        if data is None:
            return False
        
        # Simple filtering logic (placeholder for full implementation)
        if self.filter_type == "sma":
            if len(historical) >= self.period:
                filtered = sum(historical[-self.period:]) / self.period
            else:
                filtered = data
        else:
            filtered = data
        
        self.set_output("filtered", filtered)
        
        # Determine trend
        if filtered > data * 1.001:
            trend = "up"
        elif filtered < data * 0.999:
            trend = "down"
        else:
            trend = "neutral"
        
        self.set_output("trend", trend)
        
        return True


# Import needed for type hints
from ist.strategy.nodes.base import NodeInput
