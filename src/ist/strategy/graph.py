"""Strategy graph management and DAG validation."""

from typing import Any, Optional
from collections import deque

import networkx as nx

from ist.core.exceptions import GraphError, NodeError
from ist.core.logging import get_logger
from ist.strategy.nodes.base import (
    NodeExecutionContext,
    NodeState,
    StrategyNode,
)
from ist.strategy.nodes.data_nodes import DataSourceNode, MultiDataSourceNode
from ist.strategy.nodes.indicator_nodes import IndicatorNode
from ist.strategy.nodes.logic_nodes import ConditionNode, LogicGateNode, ThresholdNode
from ist.strategy.nodes.action_nodes import ActionNode, RebalanceNode, TrailingStopNode
from ist.strategy.nodes.risk_nodes import RiskNode, DrawdownProtectionNode

logger = get_logger(__name__)


class NodeConnection:
    """Connection between two nodes."""
    
    def __init__(
        self,
        from_node: str,
        to_node: str,
        from_output: str = "",
        to_input: str = ""
    ) -> None:
        self.from_node = from_node
        self.to_node = to_node
        self.from_output = from_output or "value"
        self.to_input = to_input or "data"
    
    def to_dict(self) -> dict[str, str]:
        return {
            "from": self.from_node,
            "to": self.to_node,
            "from_output": self.from_output,
            "to_input": self.to_input,
        }


class StrategyGraph:
    """Directed Acyclic Graph representing a strategy.
    
    Manages node connections, execution order, and data flow.
    """
    
    NODE_TYPE_MAP = {
        "DataSourceNode": DataSourceNode,
        "MultiDataSourceNode": MultiDataSourceNode,
        "IndicatorNode": IndicatorNode,
        "ConditionNode": ConditionNode,
        "LogicGateNode": LogicGateNode,
        "ThresholdNode": ThresholdNode,
        "ActionNode": ActionNode,
        "RebalanceNode": RebalanceNode,
        "TrailingStopNode": TrailingStopNode,
        "RiskNode": RiskNode,
        "DrawdownProtectionNode": DrawdownProtectionNode,
    }
    
    def __init__(self, graph_id: str, name: str = "") -> None:
        self.graph_id = graph_id
        self.name = name
        
        # NetworkX directed graph for topology management
        self._graph = nx.DiGraph()
        
        # Node storage
        self._nodes: dict[str, StrategyNode] = {}
        self._connections: list[NodeConnection] = []
        
        # Execution order (computed by topological sort)
        self._execution_order: list[str] = []
        self._is_valid = False
        self._validation_errors: list[str] = []
    
    def add_node(self, node: StrategyNode) -> None:
        """Add a node to the graph."""
        self._nodes[node.node_id] = node
        self._graph.add_node(node.node_id, node=node)
        self._is_valid = False  # Invalidate execution order
        
        logger.debug(
            "Node added to graph",
            graph_id=self.graph_id,
            node_id=node.node_id,
            node_type=node.node_type.name
        )
    
    def add_connection(
        self,
        from_node: str,
        to_node: str,
        from_output: str = "",
        to_input: str = ""
    ) -> None:
        """Add a connection between nodes."""
        # Validate nodes exist
        if from_node not in self._nodes:
            raise GraphError(
                f"Source node '{from_node}' not found",
                details={"from": from_node, "to": to_node}
            )
        if to_node not in self._nodes:
            raise GraphError(
                f"Target node '{to_node}' not found",
                details={"from": from_node, "to": to_node}
            )
        
        connection = NodeConnection(
            from_node, to_node, from_output, to_input
        )
        self._connections.append(connection)
        self._graph.add_edge(from_node, to_node, connection=connection)
        self._is_valid = False
        
        logger.debug(
            "Connection added",
            graph_id=self.graph_id,
            from_node=from_node,
            to_node=to_node
        )
    
    def remove_node(self, node_id: str) -> None:
        """Remove a node and its connections."""
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._graph.remove_node(node_id)
            
            # Remove related connections
            self._connections = [
                c for c in self._connections
                if c.from_node != node_id and c.to_node != node_id
            ]
            self._is_valid = False
    
    def get_node(self, node_id: str) -> Optional[StrategyNode]:
        """Get node by ID."""
        return self._nodes.get(node_id)
    
    def get_nodes(self) -> dict[str, StrategyNode]:
        """Get all nodes."""
        return self._nodes.copy()
    
    def validate(self) -> tuple[bool, list[str]]:
        """Validate the graph structure.
        
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        # Check for empty graph
        if not self._nodes:
            errors.append("Graph has no nodes")
        
        # Check for cycles
        try:
            list(nx.topological_sort(self._graph))
        except nx.NetworkXUnfeasible:
            cycles = list(nx.simple_cycles(self._graph))
            errors.append(f"Graph contains cycles: {cycles}")
        
        # Check for disconnected nodes
        if self._nodes:
            connected_nodes = set()
            for edge in self._graph.edges():
                connected_nodes.update(edge)
            
            disconnected = set(self._nodes.keys()) - connected_nodes
            # Source nodes (no inputs) are allowed to be disconnected
            source_nodes = {
                nid for nid, node in self._nodes.items()
                if not node.inputs
            }
            disconnected = disconnected - source_nodes
            
            if disconnected:
                errors.append(f"Disconnected nodes (no connections): {disconnected}")
        
        # Validate connections match node inputs/outputs
        for conn in self._connections:
            from_node = self._nodes.get(conn.from_node)
            to_node = self._nodes.get(conn.to_node)
            
            if from_node and conn.from_output:
                if conn.from_output not in from_node.outputs:
                    errors.append(
                        f"Invalid connection: {conn.from_node}.{conn.from_output} "
                        f"-> output not found"
                    )
            
            if to_node and conn.to_input:
                if conn.to_input not in to_node.inputs:
                    errors.append(
                        f"Invalid connection: -> {conn.to_node}.{conn.to_input} "
                        f"input not found"
                    )
        
        self._is_valid = len(errors) == 0
        self._validation_errors = errors
        
        if self._is_valid:
            # Compute execution order
            self._execution_order = list(nx.topological_sort(self._graph))
        
        return self._is_valid, errors
    
    def execute(self, context: NodeExecutionContext) -> dict[str, Any]:
        """Execute the strategy graph.
        
        Args:
            context: Execution context with market data
            
        Returns:
            Dictionary of action outputs
        """
        if not self._is_valid:
            valid, errors = self.validate()
            if not valid:
                raise GraphError(
                    "Cannot execute invalid graph",
                    details={"errors": errors}
                )
        
        # Reset all nodes
        for node in self._nodes.values():
            node.reset()
        
        # Execute nodes in topological order
        action_outputs = {}
        
        for node_id in self._execution_order:
            node = self._nodes[node_id]
            
            # Propagate inputs from connected nodes
            for conn in self._connections:
                if conn.to_node == node_id:
                    source_node = self._nodes.get(conn.from_node)
                    if source_node:
                        value = source_node.get_output(conn.from_output)
                        node.set_input(conn.to_input, value)
            
            # Execute node
            try:
                node.state = NodeState.RUNNING
                success = node.execute(context)
                node.state = NodeState.COMPLETED if success else NodeState.ERROR
                node.last_executed = context.timestamp
                
                if not success:
                    logger.warning(
                        "Node execution failed",
                        graph_id=self.graph_id,
                        node_id=node_id
                    )
                
            except Exception as e:
                node.state = NodeState.ERROR
                node.error_message = str(e)
                logger.error(
                    "Node execution error",
                    graph_id=self.graph_id,
                    node_id=node_id,
                    error=str(e)
                )
                raise NodeError(
                    f"Node {node_id} execution failed: {e}",
                    details={"node_id": node_id}
                ) from e
            
            # Collect action outputs
            if node.node_type.name == "ACTION":
                action_outputs[node_id] = {
                    "action_taken": node.get_output("action_taken"),
                    "order_request": node.get_output("order_request"),
                }
        
        return action_outputs
    
    @classmethod
    def from_config(cls, graph_id: str, config: dict[str, Any]) -> "StrategyGraph":
        """Create graph from configuration dictionary.
        
        Config format:
        {
            "version": "1.0",
            "nodes": [
                {"id": "node1", "type": "IndicatorNode", "params": {...}},
                ...
            ],
            "connections": [
                {"from": "node1", "to": "node2", "from_output": "", "to_input": ""},
                ...
            ]
        }
        """
        graph = cls(graph_id, config.get("name", ""))
        
        # Create nodes
        for node_config in config.get("nodes", []):
            node_id = node_config["id"]
            node_type = node_config["type"]
            params = node_config.get("params", {})
            
            # Get node class
            node_class = cls.NODE_TYPE_MAP.get(node_type)
            if not node_class:
                raise GraphError(
                    f"Unknown node type: {node_type}",
                    details={"node_id": node_id, "type": node_type}
                )
            
            # Create node instance
            node = node_class(node_id, params)
            graph.add_node(node)
        
        # Create connections
        for conn_config in config.get("connections", []):
            graph.add_connection(
                from_node=conn_config["from"],
                to_node=conn_config["to"],
                from_output=conn_config.get("from_output", ""),
                to_input=conn_config.get("to_input", "")
            )
        
        # Validate
        graph.validate()
        
        return graph
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize graph to dictionary."""
        return {
            "graph_id": self.graph_id,
            "name": self.name,
            "is_valid": self._is_valid,
            "validation_errors": self._validation_errors,
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "connections": [conn.to_dict() for conn in self._connections],
            "execution_order": self._execution_order,
        }
    
    def get_flowchart_data(self) -> dict[str, Any]:
        """Get data for flowchart visualization."""
        nodes_data = []
        for node_id, node in self._nodes.items():
            node_dict = node.to_dict()
            # Add execution info
            node_dict["execution_state"] = node.state.name
            node_dict["last_executed"] = (
                node.last_executed.isoformat() if node.last_executed else None
            )
            nodes_data.append(node_dict)
        
        return {
            "graph_id": self.graph_id,
            "name": self.name,
            "is_valid": self._is_valid,
            "validation_errors": self._validation_errors,
            "nodes": nodes_data,
            "connections": [conn.to_dict() for conn in self._connections],
        }
