"""Risk management nodes."""

from typing import Any, Optional

from ist.strategy.nodes.base import (
    NodeExecutionContext,
    NodeInput,
    NodeOutput,
    NodeType,
    StrategyNode,
)


class RiskNode(StrategyNode):
    """Risk management filter node.
    
    Params:
        max_position_pct: Maximum position size as percentage
        max_daily_loss: Maximum daily loss limit
        correlation_limit: Maximum correlation with existing positions
        volatility_cap: Maximum volatility allowed for entry
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.RISK, params)
        self.max_position_pct = self.params.get("max_position_pct", 0.10)
        self.max_daily_loss = self.params.get("max_daily_loss")
        self.correlation_limit = self.params.get("correlation_limit", 0.8)
        self.volatility_cap = self.params.get("volatility_cap", 0.5)
        self.volatility_adjustment = self.params.get("volatility_adjustment", True)
    
    def _setup_inputs(self) -> None:
        self.inputs["signal"] = NodeInput("signal", "any", required=True)
        self.inputs["position_size"] = NodeInput("position_size", "float", required=False)
        self.inputs["portfolio_value"] = NodeInput("portfolio_value", "float", required=False)
        self.inputs["current_positions"] = NodeInput("current_positions", "list", required=False)
        self.inputs["daily_pnl"] = NodeInput("daily_pnl", "float", required=False)
        self.inputs["atr"] = NodeInput("atr", "float", required=False)
        self.inputs["symbol"] = NodeInput("symbol", "str", required=False)
    
    def _setup_outputs(self) -> None:
        self.outputs["approved"] = NodeOutput("approved", "bool")
        self.outputs["adjusted_size"] = NodeOutput("adjusted_size", "float")
        self.outputs["reject_reason"] = NodeOutput("reject_reason", "str")
        self.outputs["risk_score"] = NodeOutput("risk_score", "float")
        self.outputs["checks_passed"] = NodeOutput("checks_passed", "list")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Evaluate risk checks."""
        signal = self.get_input("signal")
        position_size = self.get_input("position_size") or 0.0
        daily_pnl = self.get_input("daily_pnl") or 0.0
        atr = self.get_input("atr") or 0.0
        symbol = self.get_input("symbol") or ""
        
        checks_passed = []
        reject_reason = None
        
        # Check 1: Position size limit
        if position_size > self.max_position_pct:
            reject_reason = f"Position size {position_size:.2%} exceeds limit {self.max_position_pct:.2%}"
            self._set_rejected(reject_reason, checks_passed)
            return True
        
        checks_passed.append("position_size")
        
        # Check 2: Daily loss limit
        if self.max_daily_loss and daily_pnl < -self.max_daily_loss:
            reject_reason = f"Daily loss ${abs(daily_pnl):.2f} exceeds limit ${self.max_daily_loss:.2f}"
            self._set_rejected(reject_reason, checks_passed)
            return True
        
        checks_passed.append("daily_loss")
        
        # Check 3: Volatility cap
        if atr and self.volatility_cap:
            price = self.get_input("portfolio_value") or 1.0
            if price > 0:
                volatility_pct = atr / price
                if volatility_pct > self.volatility_cap:
                    reject_reason = f"Volatility {volatility_pct:.2%} exceeds cap {self.volatility_cap:.2%}"
                    self._set_rejected(reject_reason, checks_passed)
                    return True
        
        checks_passed.append("volatility")
        
        # Calculate volatility-adjusted position size
        adjusted_size = position_size
        if self.volatility_adjustment and atr:
            # Reduce size as volatility increases
            portfolio_value = self.get_input("portfolio_value") or 100000
            volatility_factor = max(0.5, 1.0 - (atr / portfolio_value * 100))
            adjusted_size = position_size * volatility_factor
        
        # Calculate risk score (0-100)
        risk_score = 0.0
        risk_score += min(50, position_size / self.max_position_pct * 50)
        if self.max_daily_loss:
            risk_score += min(30, abs(daily_pnl) / self.max_daily_loss * 30)
        if atr:
            risk_score += min(20, atr / 100 * 20)
        
        # Approve signal
        self.set_output("approved", signal is not None)
        self.set_output("adjusted_size", adjusted_size)
        self.set_output("reject_reason", reject_reason or "")
        self.set_output("risk_score", min(100, risk_score))
        self.set_output("checks_passed", checks_passed)
        
        return True
    
    def _set_rejected(
        self, 
        reason: str, 
        checks_passed: list
    ) -> None:
        """Set outputs for rejected signal."""
        self.set_output("approved", False)
        self.set_output("adjusted_size", 0.0)
        self.set_output("reject_reason", reason)
        self.set_output("risk_score", 100.0)
        self.set_output("checks_passed", checks_passed)


class DrawdownProtectionNode(StrategyNode):
    """Portfolio drawdown protection.
    
    Params:
        max_drawdown_pct: Maximum allowed drawdown
        action: "reduce_size", "stop_trading", "hedge"
        reduction_factor: Size reduction factor when triggered
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.RISK, params)
        self.max_drawdown_pct = self.params.get("max_drawdown_pct", 5.0)
        self.action = self.params.get("action", "reduce_size")
        self.reduction_factor = self.params.get("reduction_factor", 0.5)
    
    def _setup_inputs(self) -> None:
        self.inputs["current_drawdown"] = NodeInput("current_drawdown", "float", required=True)
        self.inputs["peak_equity"] = NodeInput("peak_equity", "float", required=False)
        self.inputs["current_equity"] = NodeInput("current_equity", "float", required=False)
    
    def _setup_outputs(self) -> None:
        self.outputs["triggered"] = NodeOutput("triggered", "bool")
        self.outputs["action"] = NodeOutput("action", "str")
        self.outputs["size_multiplier"] = NodeOutput("size_multiplier", "float")
        self.outputs["urgency"] = NodeOutput("urgency", "str")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Evaluate drawdown protection."""
        current_drawdown = self.get_input("current_drawdown")
        
        if current_drawdown is None:
            return False
        
        current_drawdown = float(current_drawdown) * 100  # Convert to percentage
        
        triggered = current_drawdown >= self.max_drawdown_pct
        
        # Determine urgency
        if current_drawdown >= self.max_drawdown_pct * 2:
            urgency = "critical"
        elif current_drawdown >= self.max_drawdown_pct * 1.5:
            urgency = "high"
        elif triggered:
            urgency = "medium"
        else:
            urgency = "normal"
        
        # Calculate size multiplier
        if triggered:
            if self.action == "stop_trading":
                size_multiplier = 0.0
            elif self.action == "reduce_size":
                # More drawdown = more reduction
                excess_dd = current_drawdown - self.max_drawdown_pct
                reduction = min(0.9, excess_dd / 10)  # Cap at 90% reduction
                size_multiplier = max(0.1, 1.0 - reduction)
            elif self.action == "hedge":
                size_multiplier = 1.0  # Maintain size but hedge
            else:
                size_multiplier = 1.0
        else:
            size_multiplier = 1.0
        
        self.set_output("triggered", triggered)
        self.set_output("action", self.action if triggered else "none")
        self.set_output("size_multiplier", size_multiplier)
        self.set_output("urgency", urgency)
        
        return True
