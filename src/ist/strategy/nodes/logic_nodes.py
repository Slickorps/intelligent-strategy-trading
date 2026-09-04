"""Logic and condition nodes."""

from typing import Any, Optional

from ist.strategy.nodes.base import (
    NodeExecutionContext,
    NodeInput,
    NodeOutput,
    NodeType,
    StrategyNode,
)


class ConditionNode(StrategyNode):
    """Logical condition evaluation node.
    
    Params:
        condition: Condition type ("cross_above", "cross_below", "above", "below", "equal")
        threshold: Fixed threshold value for comparison
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.CONDITION, params)
        self.condition = self.params.get("condition", "cross_above")
        self.threshold = self.params.get("threshold")
        
        self._prev_value_a: Optional[float] = None
        self._prev_value_b: Optional[float] = None
    
    def _setup_inputs(self) -> None:
        self.inputs["value_a"] = NodeInput("value_a", "float", required=True)
        self.inputs["value_b"] = NodeInput("value_b", "float", required=False)
        self.inputs["historical_a"] = NodeInput("historical_a", "list", required=False)
        self.inputs["historical_b"] = NodeInput("historical_b", "list", required=False)
    
    def _setup_outputs(self) -> None:
        self.outputs["triggered"] = NodeOutput("triggered", "bool")
        self.outputs["direction"] = NodeOutput("direction", "str")
        self.outputs["strength"] = NodeOutput("strength", "float")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Evaluate condition."""
        value_a = self.get_input("value_a")
        value_b = self.get_input("value_b") or self.threshold
        
        if value_a is None:
            return False
        
        if value_b is None:
            value_b = 0.0
        
        triggered = False
        direction = "neutral"
        strength = 0.0
        
        if self.condition == "cross_above":
            triggered = self._check_cross_above(float(value_a), float(value_b))
            direction = "up" if triggered else "neutral"
        elif self.condition == "cross_below":
            triggered = self._check_cross_below(float(value_a), float(value_b))
            direction = "down" if triggered else "neutral"
        elif self.condition == "above":
            triggered = float(value_a) > float(value_b)
            direction = "up"
        elif self.condition == "below":
            triggered = float(value_a) < float(value_b)
            direction = "down"
        elif self.condition == "equal":
            triggered = abs(float(value_a) - float(value_b)) < 0.0001
        elif self.condition == "between":
            lower = self.params.get("lower_threshold", 0)
            upper = self.params.get("upper_threshold", 100)
            triggered = lower <= float(value_a) <= upper
        
        # Calculate strength
        if triggered and value_b != 0:
            strength = abs(value_a - value_b) / abs(value_b)
        
        self.set_output("triggered", triggered)
        self.set_output("direction", direction)
        self.set_output("strength", min(strength, 1.0))
        
        # Store previous values
        self._prev_value_a = float(value_a)
        self._prev_value_b = float(value_b)
        
        return True
    
    def _check_cross_above(self, value_a: float, value_b: float) -> bool:
        """Check if value_a crossed above value_b."""
        if self._prev_value_a is None or self._prev_value_b is None:
            return False
        
        return (self._prev_value_a <= self._prev_value_b and 
                value_a > value_b)
    
    def _check_cross_below(self, value_a: float, value_b: float) -> bool:
        """Check if value_a crossed below value_b."""
        if self._prev_value_a is None or self._prev_value_b is None:
            return False
        
        return (self._prev_value_a >= self._prev_value_b and 
                value_a < value_b)
    
    def reset(self) -> None:
        """Reset condition state."""
        super().reset()
        self._prev_value_a = None
        self._prev_value_b = None


class LogicGateNode(StrategyNode):
    """Boolean logic gate node.
    
    Params:
        gate_type: "AND", "OR", "NOT", "XOR"
        min_inputs: Minimum number of inputs required (for AND)
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        super().__init__(node_id, NodeType.CONDITION, params)
        self.gate_type = self.params.get("gate_type", "AND")
        self.min_inputs = self.params.get("min_inputs", 2)
    
    def _setup_inputs(self) -> None:
        # Dynamic inputs
        for i in range(5):
            self.inputs[f"input_{i}"] = NodeInput(f"input_{i}", "bool", required=False)
    
    def _setup_outputs(self) -> None:
        self.outputs["result"] = NodeOutput("result", "bool")
        self.outputs["input_count"] = NodeOutput("input_count", "int")
        self.outputs["true_count"] = NodeOutput("true_count", "int")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Evaluate logic gate."""
        # Collect boolean inputs
        values = []
        for i in range(5):
            val = self.get_input(f"input_{i}")
            if val is not None:
                values.append(bool(val))
        
        self.set_output("input_count", len(values))
        self.set_output("true_count", sum(values))
        
        if not values:
            self.set_output("result", False)
            return True
        
        if self.gate_type == "AND":
            result = all(values) and len(values) >= self.min_inputs
        elif self.gate_type == "OR":
            result = any(values)
        elif self.gate_type == "NOT":
            result = not values[0] if values else True
        elif self.gate_type == "XOR":
            result = sum(values) == 1
        elif self.gate_type == "NAND":
            result = not all(values)
        else:
            result = False
        
        self.set_output("result", result)
        return True


class ThresholdNode(StrategyNode):
    """Multi-level threshold detector.
    
    Params:
        levels: List of threshold values
        mode: "single" or "band"
    """
    
    def __init__(self, node_id: str, params: Optional[dict] = None) -> None:
        params = params or {}
        self.levels = params.get("levels", [30, 50, 70])
        self.mode = params.get("mode", "single")
        super().__init__(node_id, NodeType.CONDITION, params)
    
    def _setup_inputs(self) -> None:
        self.inputs["value"] = NodeInput("value", "float", required=True)
    
    def _setup_outputs(self) -> None:
        self.outputs["level"] = NodeOutput("level", "int")
        self.outputs["level_name"] = NodeOutput("level_name", "str")
        self.outputs["normalized"] = NodeOutput("normalized", "float")
        
        # Individual level triggers
        for i, level in enumerate(self.levels):
            self.outputs[f"above_{level}"] = NodeOutput(f"above_{level}", "bool")
    
    def execute(self, context: NodeExecutionContext) -> bool:
        """Evaluate thresholds."""
        value = self.get_input("value")
        
        if value is None:
            return False
        
        value = float(value)
        
        # Find current level
        level = 0
        for i, threshold in enumerate(self.levels):
            if value >= threshold:
                level = i + 1
            self.set_output(f"above_{threshold}", value >= threshold)
        
        # Level names
        level_names = ["low", "medium", "high", "extreme"]
        level_name = level_names[min(level, len(level_names) - 1)]
        
        # Normalized value (0-1 across all levels)
        if len(self.levels) >= 2:
            min_val = min(self.levels)
            max_val = max(self.levels)
            normalized = (value - min_val) / (max_val - min_val) if max_val != min_val else 0.5
        else:
            normalized = 0.5
        
        self.set_output("level", level)
        self.set_output("level_name", level_name)
        self.set_output("normalized", max(0.0, min(1.0, normalized)))
        
        return True
