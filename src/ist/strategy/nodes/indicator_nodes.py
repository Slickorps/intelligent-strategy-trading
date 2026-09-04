"""Technical indicator nodes.

These nodes delegate all calculations to the standalone indicator classes
in :mod:`ist.strategy.indicators`, keeping the node layer focused on
execution orchestration and signal routing.
"""

from typing import Any, Optional

import pandas as pd

from ist.strategy.indicators.base import IndicatorInput
from ist.strategy.indicators.moving_averages import SMA as _SMA, EMA as _EMA
from ist.strategy.indicators.momentum import RSI as _RSI
from ist.strategy.indicators.trend import MACD as _MACD
from ist.strategy.indicators.volatility import ATR as _ATR, BollingerBands as _BB
from ist.strategy.nodes.base import (
    NodeExecutionContext,
    NodeInput,
    NodeOutput,
    NodeType,
    StrategyNode,
)


class IndicatorNode(StrategyNode):
    """Generic technical indicator node.

    Delegates all calculations to the standalone indicator classes
    in ``ist.strategy.indicators.`` keeping this layer focused on
    streaming-input accumulation, execution orchestration, and output routing.

    Params:
        indicator: Indicator name ("SMA", "EMA", "RSI", "MACD",
                   "BollingerBands", "ATR")
        period: Primary period
        period2: Secondary period (for multi-period indicators)
        period3: Tertiary period
    """

    # Map indicator name → (factory, needs OHLC)
    _INDICATOR_REGISTRY = {
        "SMA": lambda p: _SMA(period=p[0]),
        "EMA": lambda p: _EMA(period=p[0]),
        "RSI": lambda p: _RSI(period=p[0]),
        "MACD": lambda p: _MACD(
            fast_period=p[0],
            slow_period=p[1],
            signal_period=p[2],
        ),
        "ATR": lambda p: _ATR(period=p[0]),
        "BollingerBands": lambda p: _BB(period=p[0]),
    }

    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        params = params or {}
        self.indicator = params.get("indicator", "SMA")
        self.period = params.get("period", 14)
        self.period2 = params.get("period2", 26)
        self.period3 = params.get("period3", 9)

        self._history: list[float] = []
        super().__init__(node_id, NodeType.INDICATOR, params)
        self._indicator_instance = self._build_indicator()

    def _build_indicator(self):
        """Instantiate the standalone indicator class (lazy-fallback)."""
        factory = self._INDICATOR_REGISTRY.get(self.indicator)
        if factory is None:
            return None
        try:
            return factory((self.period, self.period2, self.period3))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Node I/O plumbing (unchanged public contract)
    # ------------------------------------------------------------------

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
            self.outputs["value"] = NodeOutput("value", "float")
            self.outputs["slope"] = NodeOutput("slope", "float")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, context: NodeExecutionContext) -> bool:
        """Calculate indicator value using the standalone indicator class."""
        price = self.get_input("price")
        if price is None:
            return False

        self._history.append(float(price))
        # Cap history size to 2× the longest period
        max_period = max(self.period, self.period2, self.period3)
        if len(self._history) > max_period * 2:
            self._history = self._history[-max_period * 2:]

        # ---- delegate to standalone indicator ----
        result = self._calculate()

        if self.indicator == "MACD":
            self.set_output("macd", result.get("macd", 0.0))
            self.set_output("signal", result.get("signal", 0.0))
            self.set_output("histogram", result.get("histogram", 0.0))
        elif self.indicator in ("RSI", "STOCH"):
            value = result.get("value", 50.0)
            self.set_output("value", value)
            self.set_output("overbought", value > 70)
            self.set_output("oversold", value < 30)
        else:
            value = result.get("value", price)
            self.set_output("value", value)
            if len(self._history) >= 2:
                self.set_output("slope", (price - self._history[-2]) / self._history[-2] * 100)
            else:
                self.set_output("slope", 0.0)

        return True

    # ------------------------------------------------------------------
    # Delegation helpers
    # ------------------------------------------------------------------

    def _calculate(self) -> dict[str, float]:
        """Run the registered standalone indicator and extract last values."""
        if not self._history or self._indicator_instance is None:
            return {"value": 0.0}

        series = pd.Series(self._history, dtype=float)
        inp = IndicatorInput(close=series)

        try:
            result = self._indicator_instance.calculate(inp)
        except Exception:
            # Graceful fallback – keep old behaviour
            return {"value": float(self._history[-1])}

        if self.indicator == "MACD":
            return {
                "macd": float(result.values.iloc[-1]),
                "signal": float(result.signal_line.iloc[-1]) if result.signal_line is not None else 0.0,
                "histogram": float(result.histogram.iloc[-1]) if result.histogram is not None else 0.0,
            }
        elif self.indicator in ("RSI", "STOCH"):
            return {"value": float(result.values.iloc[-1])}
        else:
            return {"value": float(result.values.iloc[-1])}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset indicator state."""
        super().reset()
        self._history.clear()
        self._indicator_instance = self._build_indicator()
