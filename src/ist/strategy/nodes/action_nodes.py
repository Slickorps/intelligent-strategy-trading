"""Trading action nodes."""

from typing import Any, Optional
from enum import Enum

from ist.strategy.nodes.base import (
    NodeExecutionContext,
    NodeInput,
    NodeOutput,
    NodeType,
    StrategyNode,
)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class ActionNode(StrategyNode):
    """Trading action execution node.
    
    Params:
        action: Action type ("buy", "sell", "close", "rebalance")
        size_pct: Position size as percentage of portfolio
        order_type: Order type ("market", "limit")
        time_in_force: "GTC", "IOC", "FOK"
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.ACTION, params)
        self.action = self.params.get("action", "buy")
        self.size_pct = self.params.get("size_pct", 0.05)
        self.order_type = self.params.get("order_type", "market")
        self.time_in_force = self.params.get("time_in_force", "GTC")
        self.symbol = self.params.get("symbol", "EURUSD")
    
    def _setup_inputs(self) -> None:
        self.inputs["trigger"] = NodeInput("trigger", "bool", required=False)
        self.inputs["signal_strength"] = NodeInput("signal_strength", "float", required=False)
        self.inputs["target_price"] = NodeInput("target_price", "float", required=False)
        self.inputs["stop_price"] = NodeInput("stop_price", "float", required=False)
    
    def _setup_outputs(self) -> None:
        self.outputs["order_request"] = NodeOutput("order_request", "dict")
        self.outputs["action_taken"] = NodeOutput("action_taken", "bool")
        self.outputs["position_size"] = NodeOutput("position_size", "float")
        self.outputs["symbol"] = NodeOutput("symbol", "str")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Generate trading action."""
        trigger = self.get_input("trigger")
        
        # If no trigger input, always execute
        if trigger is None:
            trigger = True
        
        if not trigger:
            self.set_output("action_taken", False)
            return True
        
        # Calculate position size with signal strength adjustment
        signal_strength = self.get_input("signal_strength") or 1.0
        adjusted_size = self.size_pct * float(signal_strength)
        
        # Build order request
        order_request = {
            "action": self.action,
            "symbol": self.symbol,
            "side": self._get_side(),
            "size_pct": adjusted_size,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "timestamp": context.timestamp.isoformat(),
        }
        
        # Add optional fields
        target_price = self.get_input("target_price")
        if target_price:
            order_request["target_price"] = float(target_price)
        
        stop_price = self.get_input("stop_price")
        if stop_price:
            order_request["stop_price"] = float(stop_price)
        
        self.set_output("order_request", order_request)
        self.set_output("action_taken", True)
        self.set_output("position_size", adjusted_size)
        self.set_output("symbol", self.symbol)
        
        return True
    
    def _get_side(self) -> str:
        """Determine order side."""
        if self.action == "buy":
            return "buy"
        elif self.action == "sell":
            return "sell"
        elif self.action == "close":
            return "close"
        return "buy"


class RebalanceNode(StrategyNode):
    """Portfolio rebalancing action.
    
    Params:
        target_weights: Dict of symbol to target weight
        threshold_pct: Rebalance threshold percentage
        max_deviation: Maximum allowed deviation before forced rebalance
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.ACTION, params)
        self.target_weights = self.params.get("target_weights", {})
        self.threshold_pct = self.params.get("threshold_pct", 3.0)
        self.max_deviation = self.params.get("max_deviation", 10.0)
    
    def _setup_inputs(self) -> None:
        self.inputs["current_weights"] = NodeInput("current_weights", "dict", required=False)
        self.inputs["portfolio_value"] = NodeInput("portfolio_value", "float", required=False)
        self.inputs["trigger"] = NodeInput("trigger", "bool", required=False)
    
    def _setup_outputs(self) -> None:
        self.outputs["rebalance_orders"] = NodeOutput("rebalance_orders", "list")
        self.outputs["deviations"] = NodeOutput("deviations", "dict")
        self.outputs["needs_rebalance"] = NodeOutput("needs_rebalance", "bool")
        self.outputs["total_turnover"] = NodeOutput("total_turnover", "float")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Calculate rebalancing actions."""
        current_weights = self.get_input("current_weights") or {}
        trigger = self.get_input("trigger")
        
        if trigger is False:
            self.set_output("needs_rebalance", False)
            return True
        
        # Calculate deviations
        deviations = {}
        needs_rebalance = False
        max_dev = 0.0
        
        all_symbols = set(current_weights.keys()) | set(self.target_weights.keys())
        
        for symbol in all_symbols:
            current = current_weights.get(symbol, 0.0)
            target = self.target_weights.get(symbol, 0.0)
            deviation = abs(current - target) * 100  # As percentage
            deviations[symbol] = {
                "current": current,
                "target": target,
                "deviation_pct": deviation
            }
            max_dev = max(max_dev, deviation)
            
            if deviation > self.threshold_pct:
                needs_rebalance = True
        
        # Force rebalance if max deviation exceeded
        if max_dev > self.max_deviation:
            needs_rebalance = True
        
        # Generate rebalance orders
        orders = []
        total_turnover = 0.0
        
        if needs_rebalance:
            for symbol, dev_info in deviations.items():
                current = dev_info["current"]
                target = dev_info["target"]
                diff = target - current
                
                if abs(diff) > 0.001:  # Minimum 0.1% difference
                    orders.append({
                        "symbol": symbol,
                        "side": "buy" if diff > 0 else "sell",
                        "target_weight": target,
                        "current_weight": current,
                        "delta": abs(diff)
                    })
                    total_turnover += abs(diff)
        
        self.set_output("rebalance_orders", orders)
        self.set_output("deviations", deviations)
        self.set_output("needs_rebalance", needs_rebalance)
        self.set_output("total_turnover", total_turnover)
        
        return True


class TrailingStopNode(StrategyNode):
    """Trailing stop order management.
    
    Params:
        trail_pct: Trailing percentage
        activation_pct: Activation percentage (optional)
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.ACTION, params)
        self.trail_pct = self.params.get("trail_pct", 3.0)
        self.activation_pct = self.params.get("activation_pct")
        self.symbol = self.params.get("symbol", "EURUSD")
        
        self._highest_price: Optional[float] = None
        self._stop_price: Optional[float] = None
        self._activated = False
    
    def _setup_inputs(self) -> None:
        self.inputs["current_price"] = NodeInput("current_price", "float", required=True)
        self.inputs["position_side"] = NodeInput("position_side", "str", required=True)
        self.inputs["entry_price"] = NodeInput("entry_price", "float", required=False)
    
    def _setup_outputs(self) -> None:
        self.outputs["stop_price"] = NodeOutput("stop_price", "float")
        self.outputs["should_exit"] = NodeOutput("should_exit", "bool")
        self.outputs["activated"] = NodeOutput("activated", "bool")
        self.outputs["distance_pct"] = NodeOutput("distance_pct", "float")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Update trailing stop."""
        current_price = self.get_input("current_price")
        position_side = self.get_input("position_side") or "long"
        entry_price = self.get_input("entry_price")
        
        if current_price is None:
            return False
        
        current_price = float(current_price)
        
        # Initialize or update highest price
        if self._highest_price is None:
            self._highest_price = current_price
        
        # Check activation
        if self.activation_pct and entry_price:
            profit_pct = (current_price - entry_price) / entry_price * 100
            if position_side == "short":
                profit_pct = -profit_pct
            
            self._activated = profit_pct >= self.activation_pct
        else:
            self._activated = True
        
        # Update trailing stop for long positions
        if position_side == "long":
            if current_price > self._highest_price:
                self._highest_price = current_price
                self._stop_price = self._highest_price * (1 - self.trail_pct / 100)
        
        # Update trailing stop for short positions
        else:
            if current_price < self._highest_price:
                self._highest_price = current_price
                self._stop_price = self._highest_price * (1 + self.trail_pct / 100)
        
        # Check if stop triggered
        should_exit = False
        if self._activated and self._stop_price:
            if position_side == "long":
                should_exit = current_price <= self._stop_price
            else:
                should_exit = current_price >= self._stop_price
        
        # Calculate distance to stop
        distance_pct = 0.0
        if self._stop_price:
            distance_pct = abs(current_price - self._stop_price) / current_price * 100
        
        self.set_output("stop_price", self._stop_price)
        self.set_output("should_exit", should_exit)
        self.set_output("activated", self._activated)
        self.set_output("distance_pct", distance_pct)
        
        return True
    
    def reset(self) -> None:
        """Reset trailing stop state."""
        super().reset()
        self._highest_price = None
        self._stop_price = None
        self._activated = False
