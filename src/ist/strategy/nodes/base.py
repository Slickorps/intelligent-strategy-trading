"""Base classes for strategy nodes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional

from ist.core.exceptions import NodeError
from ist.core.logging import get_logger

logger = get_logger(__name__)


class NodeType(Enum):
    """Types of strategy nodes."""
    DATA_SOURCE = auto()
    INDICATOR = auto()
    CONDITION = auto()
    ACTION = auto()
    RISK = auto()
    TRANSFORM = auto()


class NodeState(Enum):
    """Execution state of a node."""
    IDLE = auto()
    RUNNING = auto()
    COMPLETED = auto()
    ERROR = auto()


@dataclass
class NodeInput:
    """Input slot for a node."""
    name: str
    data_type: str = "any"
    required: bool = True
    value: Any = None
    connected_from: Optional[str] = None  # node_id


@dataclass
class NodeOutput:
    """Output slot for a node."""
    name: str
    data_type: str = "any"
    value: Any = None


@dataclass
class NodeExecutionContext:
    """Context passed during node execution."""
    timestamp: datetime
    bar_data: Optional[dict] = None
    portfolio_state: Optional[dict] = None
    market_regime: Optional[str] = None
    custom_data: dict = field(default_factory=dict)


class StrategyNode(ABC):
    """Abstract base class for all strategy nodes.
    
    Nodes form a directed acyclic graph (DAG) that represents
    the strategy logic flow.
    """
    
    def __init__(
        self,
        node_id: str,
        node_type: NodeType,
        params: Optional[dict] = None
    ) -> None:
        self.node_id = node_id
        self.node_type = node_type
        self.params = params or {}
        
        self.inputs: dict[str, NodeInput] = {}
        self.outputs: dict[str, NodeOutput] = {}
        self.state = NodeState.IDLE
        self.last_executed: Optional[datetime] = None
        self.error_message: Optional[str] = None
        
        self._setup_inputs()
        self._setup_outputs()
    
    @abstractmethod
    def _setup_inputs(self) -> None:
        """Define input slots for this node."""
        pass
    
    @abstractmethod
    def _setup_outputs(self) -> None:
        """Define output slots for this node."""
        pass
    
    @abstractmethod
    def execute(self, context: NodeExecutionContext) -> bool:
        """Execute the node's logic.
        
        Args:
            context: Execution context with market data and state
            
        Returns:
            True if execution successful, False otherwise
        """
        pass
    
    def get_input(self, name: str) -> Any:
        """Get input value by name."""
        if name not in self.inputs:
            raise NodeError(
                f"Input '{name}' not found on node {self.node_id}",
                details={"node_id": self.node_id, "input": name}
            )
        return self.inputs[name].value
    
    def set_input(self, name: str, value: Any) -> None:
        """Set input value by name."""
        if name not in self.inputs:
            raise NodeError(
                f"Input '{name}' not found on node {self.node_id}",
                details={"node_id": self.node_id, "input": name}
            )
        self.inputs[name].value = value
    
    def set_output(self, name: str, value: Any) -> None:
        """Set output value by name."""
        if name not in self.outputs:
            raise NodeError(
                f"Output '{name}' not found on node {self.node_id}",
                details={"node_id": self.node_id, "output": name}
            )
        self.outputs[name].value = value
    
    def get_output(self, name: str) -> Any:
        """Get output value by name."""
        if name not in self.outputs:
            raise NodeError(
                f"Output '{name}' not found on node {self.node_id}",
                details={"node_id": self.node_id, "output": name}
            )
        return self.outputs[name].value
    
    def reset(self) -> None:
        """Reset node state for new execution cycle."""
        self.state = NodeState.IDLE
        self.error_message = None
        for inp in self.inputs.values():
            inp.value = None
        for out in self.outputs.values():
            out.value = None
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize node to dictionary."""
        return {
            "id": self.node_id,
            "type": self.node_type.name,
            "params": self.params,
            "inputs": {
                name: {
                    "type": inp.data_type,
                    "required": inp.required,
                    "connected_from": inp.connected_from
                }
                for name, inp in self.inputs.items()
            },
            "outputs": {
                name: {"type": out.data_type}
                for name, out in self.outputs.items()
            },
            "state": self.state.name
        }
