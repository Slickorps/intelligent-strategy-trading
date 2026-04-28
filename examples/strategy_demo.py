"""Strategy execution demo.

This example demonstrates how to:
1. Create a strategy graph from configuration
2. Execute the strategy on market data
3. Visualize the strategy flowchart
"""

import json
from datetime import datetime

from ist.strategy import StrategyGraph, StrategyExecutor
from ist.visualization import generate_flowchart


def create_sample_strategy() -> dict:
    """Create a sample strategy configuration."""
    return {
        "name": "Golden Cross Strategy",
        "version": "1.0",
        "nodes": [
            {
                "id": "eurusd_data",
                "type": "DataSourceNode",
                "params": {
                    "symbol": "EURUSD",
                    "timeframe": "1h",
                    "position": {"x": 100, "y": 200}
                }
            },
            {
                "id": "sma_50",
                "type": "IndicatorNode",
                "params": {
                    "indicator": "SMA",
                    "period": 50,
                    "position": {"x": 300, "y": 150}
                }
            },
            {
                "id": "sma_200",
                "type": "IndicatorNode",
                "params": {
                    "indicator": "SMA",
                    "period": 200,
                    "position": {"x": 300, "y": 250}
                }
            },
            {
                "id": "golden_cross",
                "type": "ConditionNode",
                "params": {
                    "condition": "cross_above",
                    "position": {"x": 500, "y": 200}
                }
            },
            {
                "id": "risk_filter",
                "type": "RiskNode",
                "params": {
                    "max_position_pct": 0.05,
                    "position": {"x": 700, "y": 200}
                }
            },
            {
                "id": "buy_action",
                "type": "ActionNode",
                "params": {
                    "action": "buy",
                    "size_pct": 0.03,
                    "symbol": "EURUSD",
                    "position": {"x": 900, "y": 200}
                }
            }
        ],
        "connections": [
            {"from": "eurusd_data", "to": "sma_50", "from_output": "close", "to_input": "price"},
            {"from": "eurusd_data", "to": "sma_200", "from_output": "close", "to_input": "price"},
            {"from": "sma_50", "to": "golden_cross", "from_output": "value", "to_input": "value_a"},
            {"from": "sma_200", "to": "golden_cross", "from_output": "value", "to_input": "value_b"},
            {"from": "golden_cross", "to": "risk_filter", "from_output": "triggered", "to_input": "signal"},
            {"from": "risk_filter", "to": "buy_action", "from_output": "approved", "to_input": "trigger"},
        ]
    }


def demo_graph_creation():
    """Demonstrate strategy graph creation."""
    print("=" * 60)
    print("Strategy Graph Creation Demo")
    print("=" * 60)
    
    config = create_sample_strategy()
    
    # Create graph from config
    graph = StrategyGraph.from_config("demo-001", config)
    
    # Validate
    is_valid, errors = graph.validate()
    
    print(f"\nGraph ID: {graph.graph_id}")
    print(f"Name: {graph.name}")
    print(f"Nodes: {len(graph.get_nodes())}")
    print(f"Valid: {is_valid}")
    
    if not is_valid:
        print("\nValidation Errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\nExecution Order:")
        for i, node_id in enumerate(graph._execution_order, 1):
            print(f"  {i}. {node_id}")
    
    return graph


def demo_strategy_execution(graph: StrategyGraph):
    """Demonstrate strategy execution."""
    print("\n" + "=" * 60)
    print("Strategy Execution Demo")
    print("=" * 60)
    
    # Create executor
    executor = StrategyExecutor()
    
    # Add and start strategy
    executor.add_strategy("demo-strategy", graph)
    executor.start_strategy("demo-strategy")
    
    # Simulate market data
    bar_data = {
        "symbol": "EURUSD",
        "timestamp": datetime.utcnow().isoformat(),
        "open": 1.0850,
        "high": 1.0865,
        "low": 1.0845,
        "close": 1.0860,
        "volume": 15420
    }
    
    # Execute
    result = executor.execute_strategy("demo-strategy", bar_data)
    
    print(f"\nExecution Time: {result.timestamp}")
    print(f"Success: {result.success}")
    
    if result.error_message:
        print(f"Error: {result.error_message}")
    
    print(f"\nActions Generated: {len(result.actions)}")
    for i, action in enumerate(result.actions, 1):
        print(f"  {i}. {action}")
    
    print("\nNode States:")
    for node_id, state in result.node_states.items():
        print(f"  - {node_id}: {state}")


def demo_flowchart_visualization(graph: StrategyGraph):
    """Demonstrate flowchart generation."""
    print("\n" + "=" * 60)
    print("Flowchart Visualization Demo")
    print("=" * 60)
    
    # Get flowchart data
    graph_data = graph.get_flowchart_data()
    
    # Generate visualization data
    flowchart = generate_flowchart(graph_data, auto_layout=True)
    
    print(f"\nFlowchart: {flowchart['name']}")
    print(f"Valid: {flowchart['is_valid']}")
    print(f"Nodes: {len(flowchart['nodes'])}")
    print(f"Edges: {len(flowchart['edges'])}")
    
    print("\nNodes:")
    for node in flowchart['nodes']:
        pos = node['position']
        print(f"  - {node['label']} ({node['type']}) at ({pos['x']:.0f}, {pos['y']:.0f})")
    
    print("\nSample node data:")
    if flowchart['nodes']:
        node = flowchart['nodes'][0]
        print(json.dumps(node, indent=2))


def main():
    """Run all demos."""
    try:
        # Create strategy graph
        graph = demo_graph_creation()
        
        # Execute strategy
        demo_strategy_execution(graph)
        
        # Generate visualization
        demo_flowchart_visualization(graph)
        
        print("\n" + "=" * 60)
        print("Demo completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
