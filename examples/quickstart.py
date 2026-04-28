"""Quickstart example for Intelligent Strategy Trading platform.

This example demonstrates:
1. Loading a strategy profile
2. Creating a strategy via API
3. Running a backtest
4. Analyzing results
"""

import json
from datetime import date
from pathlib import Path

# Note: This example requires the API server to be running:
#   uvicorn ist.api.main:app --reload
#
# Or use the client directly without server for local testing


def load_profile(profile_name: str) -> dict:
    """Load strategy profile from JSON file."""
    config_path = Path(f"config/profiles/{profile_name}.json")
    
    with open(config_path) as f:
        return json.load(f)


def print_profile_summary(profile: dict) -> None:
    """Print profile overview."""
    print(f"Profile: {profile['profile_name']}")
    print(f"Target Return: {profile['target_annual_return']}")
    print(f"Max Drawdown: {profile['max_drawdown_limit']}")
    print(f"\nAsset Allocation:")
    
    for asset, weight in profile['asset_allocation'].items():
        print(f"  - {asset}: {weight:.1%}")
    
    print(f"\nRisk Management:")
    risk = profile.get('risk_management', {})
    print(f"  - Simulation runs: {risk.get('path_simulation_runs', 10000):,}")
    print(f"  - Dynamic sizing: {risk.get('dynamic_position_sizing', False)}")


def show_strategy_nodes(profile: dict) -> None:
    """Display strategy node graph."""
    nodes = profile.get('strategy_nodes', {})
    
    print(f"\nStrategy Nodes (v{nodes.get('version', '1.0')}):")
    print(f"  Total nodes: {len(nodes.get('nodes', []))}")
    print(f"  Connections: {len(nodes.get('connections', []))}")
    
    print("\n  Node Types:")
    for node in nodes.get('nodes', []):
        print(f"    - [{node['type']}] {node['id']}")
    
    print("\n  Data Flow:")
    for conn in nodes.get('connections', []):
        print(f"    {conn['from']} -> {conn['to']}")


def main() -> None:
    """Run quickstart example."""
    print("=" * 60)
    print("Intelligent Strategy Trading - Quickstart Example")
    print("=" * 60)
    
    # Load conservative profile
    print("\n1. Loading Strategy Profile")
    print("-" * 40)
    profile = load_profile("conservative")
    print_profile_summary(profile)
    
    # Show strategy structure
    print("\n2. Strategy Visualization")
    print("-" * 40)
    show_strategy_nodes(profile)
    
    # API usage example (requires server running)
    print("\n3. API Usage Example")
    print("-" * 40)
    print("""
To use the API client:

    from ist.api.client import StrategyClient
    from datetime import date
    
    client = StrategyClient("http://localhost:8000")
    
    # Create strategy from profile
    result = client.create_strategy(
        name="My Conservative Strategy",
        config=profile
    )
    strategy_id = result['data']['id']
    
    # Run backtest
    backtest = client.run_backtest(
        strategy_id=strategy_id,
        start_date=date(2020, 1, 1),
        end_date=date(2023, 12, 31)
    )
    
    # Get results
    results = client.get_backtest_results(backtest['data']['backtest_id'])
    metrics = results['data']['metrics']
    
    print(f"Total Return: {metrics['total_return']:.2%}")
    print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
    print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
""")
    
    print("\n4. CLI Usage")
    print("-" * 40)
    print("""
Command line usage:

    # Start API server
    ist server
    
    # Or with uvicorn directly
    uvicorn ist.api.main:app --reload
    
    # Run quickstart
    ist quickstart
    
    # List profiles
    ist profiles
    
    # Validate profile
    ist validate conservative
""")
    
    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
