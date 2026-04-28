"""Technical indicator nodes."""

from typing import Any, Optional

from ist.strategy.nodes.base import (
    NodeExecutionContext,
    NodeInput,
    NodeOutput,
    NodeType,
    StrategyNode,
)


class IndicatorNode(StrategyNode):
    """Generic technical indicator node.
    
    Params:
        indicator: Indicator name ("SMA", "EMA", "RSI", "MACD")
        period: Primary period
        period2: Secondary period (for multi-period indicators)
        period3: Tertiary period
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.INDICATOR, params)
        self.indicator = self.params.get("indicator", "SMA")
        self.period = self.params.get("period", 14)
        self.period2 = self.params.get("period2", 26)
        self.period3 = self.params.get("period3", 9)
        
        self._history: list[float] = []
    
    def _setup_inputs(self) -> None:
        self.inputs["price"] = NodeInput("price", "float", required=True)
    
    def _setup_outputs(self) -> None:
        """Setup outputs based on indicator type."""
        if self.indicator == "MACD":
            self.outputs["macd"] = NodeOutput("macd", "float")
            self.outputs["signal"] = NodeOutput("signal", "float")
            self.outputs["histogram"] = NodeOutput("histogram", "float")
        elif self.indicator in ["RSI", "STOCH"]:
            self.outputs["value"] = NodeOutput("value", "float")
            self.outputs["overbought"] = NodeOutput("overbought", "bool")
            self.outputs["oversold"] = NodeOutput("oversold", "bool")
        else:
            # SMA, EMA, etc.
            self.outputs["value"] = NodeOutput("value", "float")
            self.outputs["slope"] = NodeOutput("slope", "float")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Calculate indicator value."""
        price = self.get_input("price")
        
        if price is None:
            return False
        
        self._history.append(float(price))
        
        if len(self._history) > max(self.period, self.period2, self.period3) * 2:
            self._history = self._history[-max(self.period, self.period2, self.period3) * 2:]
        
        result = self._calculate()
        
        if self.indicator == "MACD":
            self.set_output("macd", result.get("macd", 0.0))
            self.set_output("signal", result.get("signal", 0.0))
            self.set_output("histogram", result.get("histogram", 0.0))
        elif self.indicator in ["RSI", "STOCH"]:
            value = result.get("value", 50.0)
            self.set_output("value", value)
            self.set_output("overbought", value > 70)
            self.set_output("oversold", value < 30)
        else:
            value = result.get("value", price)
            self.set_output("value", value)
            
            # Calculate slope
            if len(self._history) >= 2:
                slope = (price - self._history[-2]) / self._history[-2] * 100
            else:
                slope = 0.0
            self.set_output("slope", slope)
        
        return True
    
    def _calculate(self) -> dict[str, float]:
        """Calculate indicator value."""
        if not self._history:
            return {"value": 0.0}
        
        if self.indicator == "SMA":
            return self._calculate_sma()
        elif self.indicator == "EMA":
            return self._calculate_ema()
        elif self.indicator == "RSI":
            return self._calculate_rsi()
        elif self.indicator == "MACD":
            return self._calculate_macd()
        else:
            return {"value": self._history[-1]}
    
    def _calculate_sma(self) -> dict[str, float]:
        """Calculate Simple Moving Average."""
        if len(self._history) < self.period:
            return {"value": sum(self._history) / len(self._history)}
        
        sma = sum(self._history[-self.period:]) / self.period
        return {"value": sma}
    
    def _calculate_ema(self) -> dict[str, float]:
        """Calculate Exponential Moving Average."""
        if len(self._history) < self.period:
            return {"value": sum(self._history) / len(self._history)}
        
        multiplier = 2.0 / (self.period + 1)
        ema = sum(self._history[:self.period]) / self.period
        
        for price in self._history[self.period:]:
            ema = (price - ema) * multiplier + ema
        
        return {"value": ema}
    
    def _calculate_rsi(self) -> dict[str, float]:
        """Calculate Relative Strength Index."""
        if len(self._history) < self.period + 1:
            return {"value": 50.0}
        
        gains = []
        losses = []
        
        for i in range(1, len(self._history)):
            change = self._history[i] - self._history[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period
        
        if avg_loss == 0:
            return {"value": 100.0}
        
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return {"value": rsi}
    
    def _calculate_macd(self) -> dict[str, float]:
        """Calculate MACD indicator."""
        fast_period = self.period
        slow_period = self.period2
        signal_period = self.period3
        
        if len(self._history) < slow_period:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
        
        # Calculate EMAs
        def ema(data, period):
            multiplier = 2.0 / (period + 1)
            result = sum(data[:period]) / period
            for price in data[period:]:
                result = (price - result) * multiplier + result
            return result
        
        ema_fast = ema(self._history, fast_period)
        ema_slow = ema(self._history, slow_period)
        
        macd_line = ema_fast - ema_slow
        
        # Signal line (EMA of MACD)
        # Need MACD history
        macd_history = getattr(self, '_macd_history', [])
        macd_history.append(macd_line)
        
        if len(macd_history) > signal_period * 2:
            macd_history = macd_history[-signal_period * 2:]
        
        self._macd_history = macd_history
        
        if len(macd_history) < signal_period:
            signal_line = macd_line
        else:
            signal_line = ema(macd_history, signal_period)
        
        histogram = macd_line - signal_line
        
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram
        }
    
    def reset(self) -> None:
        """Reset indicator state."""
        super().reset()
        self._history.clear()
        self._macd_history = []
