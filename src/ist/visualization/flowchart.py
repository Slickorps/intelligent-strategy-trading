"""Flowchart visualization data structures."""

from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class NodeVisual:
    """Visual representation of a strategy node."""
    id: str
    type: str
    label: str
    x: float = 0.0
    y: float = 0.0
    width: float = 120.0
    height: float = 60.0
    color: str = "#3b82f6"  # Default blue
    icon: Optional[str] = None
    status: str = "idle"  # idle, running, completed, error
    params: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "position": {"x": self.x, "y": self.y},
            "size": {"width": self.width, "height": self.height},
            "style": {
                "backgroundColor": self.color,
                "borderColor": self._get_border_color(),
                "borderWidth": 2 if self.status == "running" else 1,
            },
            "icon": self.icon,
            "status": self.status,
            "params": self.params,
        }
    
    def _get_border_color(self) -> str:
        """Get border color based on status."""
        colors = {
            "idle": "#9ca3af",
            "running": "#f59e0b",
            "completed": "#10b981",
            "error": "#ef4444",
        }
        return colors.get(self.status, "#9ca3af")


@dataclass
class ConnectionVisual:
    """Visual representation of a node connection."""
    id: str
    source: str
    target: str
    source_handle: str = ""
    target_handle: str = ""
    animated: bool = False
    color: str = "#6b7280"
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "sourceHandle": self.source_handle,
            "targetHandle": self.target_handle,
            "animated": self.animated,
            "style": {
                "stroke": self.color,
                "strokeWidth": 2 if self.animated else 1,
            },
        }


class FlowchartBuilder:
    """Builds flowchart visualization data from strategy graphs."""
    
    # Node type to visual properties
    NODE_STYLES = {
        "DATA_SOURCE": {
            "color": "#10b981",  # Green
            "icon": "database",
            "label_prefix": "📊 ",
        },
        "INDICATOR": {
            "color": "#3b82f6",  # Blue
            "icon": "activity",
            "label_prefix": "📈 ",
        },
        "CONDITION": {
            "color": "#f59e0b",  # Amber
            "icon": "git-branch",
            "label_prefix": "⚡ ",
        },
        "RISK": {
            "color": "#ef4444",  # Red
            "icon": "shield",
            "label_prefix": "🛡️ ",
        },
        "ACTION": {
            "color": "#8b5cf6",  # Purple
            "icon": "play",
            "label_prefix": "▶️ ",
        },
        "TRANSFORM": {
            "color": "#6b7280",  # Gray
            "icon": "filter",
            "label_prefix": "🔧 ",
        },
    }
    
    def __init__(self) -> None:
        self.nodes: list[NodeVisual] = []
        self.connections: list[ConnectionVisual] = []
    
    def from_strategy_graph(self, graph_data: dict[str, Any]) -> dict[str, Any]:
        """Build flowchart from strategy graph data."""
        self.nodes = []
        self.connections = []
        
        # Process nodes
        for node_data in graph_data.get("nodes", []):
            visual = self._create_node_visual(node_data)
            self.nodes.append(visual)
        
        # Process connections
        for i, conn_data in enumerate(graph_data.get("connections", [])):
            visual = self._create_connection_visual(i, conn_data)
            self.connections.append(visual)
        
        return {
            "graph_id": graph_data.get("graph_id", ""),
            "name": graph_data.get("name", ""),
            "is_valid": graph_data.get("is_valid", False),
            "validation_errors": graph_data.get("validation_errors", []),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [c.to_dict() for c in self.connections],
            "viewport": {
                "x": 0,
                "y": 0,
                "zoom": 1,
            },
        }
    
    def _create_node_visual(self, node_data: dict[str, Any]) -> NodeVisual:
        """Create visual node from node data."""
        node_type = node_data.get("type", "TRANSFORM")
        node_id = node_data.get("id", "unknown")
        params = node_data.get("params", {})
        
        # Get style properties
        style = self.NODE_STYLES.get(node_type, self.NODE_STYLES["TRANSFORM"])
        
        # Get position from params or use default layout
        position = params.get("position", {})
        x = position.get("x", 100.0)
        y = position.get("y", 100.0)
        
        # Create label
        label = params.get("name", node_id)
        label = style["label_prefix"] + label
        
        # Get execution status
        status = node_data.get("execution_state", "idle").lower()
        
        return NodeVisual(
            id=node_id,
            type=node_type,
            label=label,
            x=x,
            y=y,
            color=style["color"],
            icon=style["icon"],
            status=status,
            params=params,
        )
    
    def _create_connection_visual(
        self,
        index: int,
        conn_data: dict[str, Any]
    ) -> ConnectionVisual:
        """Create visual connection from connection data."""
        source = conn_data.get("from", "")
        target = conn_data.get("to", "")
        
        return ConnectionVisual(
            id=f"e{index}-{source}-{target}",
            source=source,
            target=target,
            source_handle=conn_data.get("from_output", ""),
            target_handle=conn_data.get("to_input", ""),
            animated=False,
        )
    
    def auto_layout(self, flowchart: dict[str, Any]) -> dict[str, Any]:
        """Apply automatic layout to flowchart nodes.
        
        Simple layered layout based on node type:
        - Data sources on left
        - Indicators next
        - Conditions in middle
        - Risk nodes right of conditions
        - Actions on far right
        """
        nodes = flowchart.get("nodes", [])
        
        # Group by type
        columns = {
            "DATA_SOURCE": [],
            "INDICATOR": [],
            "TRANSFORM": [],
            "CONDITION": [],
            "RISK": [],
            "ACTION": [],
        }
        
        for node in nodes:
            node_type = node.get("type", "TRANSFORM")
            if node_type in columns:
                columns[node_type].append(node)
            else:
                columns["TRANSFORM"].append(node)
        
        # Position nodes
        column_width = 200
        row_height = 100
        start_x = 100
        
        col_index = 0
        for col_name, col_nodes in columns.items():
            if not col_nodes:
                continue
            
            x = start_x + col_index * column_width
            
            for row_index, node in enumerate(col_nodes):
                y = 100 + row_index * row_height
                node["position"] = {"x": x, "y": y}
            
            col_index += 1
        
        return flowchart


def generate_flowchart(
    graph_data: dict[str, Any],
    auto_layout: bool = True
) -> dict[str, Any]:
    """Generate flowchart visualization data from strategy graph.
    
    This is the main entry point for creating flowchart data
    that can be rendered by frontend libraries like React Flow.
    
    Args:
        graph_data: Strategy graph data
        auto_layout: Whether to apply automatic layout
        
    Returns:
        Flowchart data ready for visualization
    """
    builder = FlowchartBuilder()
    flowchart = builder.from_strategy_graph(graph_data)
    
    if auto_layout:
        flowchart = builder.auto_layout(flowchart)
    
    return flowchart
