"""Command line interface for IST."""

from pathlib import Path

import typer

from ist.api.client import StrategyClient
from ist.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

app = typer.Typer(help="Intelligent Strategy Trading CLI")


@app.command()
def server(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = True,
    workers: int = 1
) -> None:
    """Start the API server."""
    import uvicorn
    
    logger.info("Starting server", host=host, port=port)
    
    uvicorn.run(
        "ist.api.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers
    )


@app.command()
def quickstart() -> None:
    """Run quick start example."""
    from datetime import date
    
    typer.echo("Starting quickstart example...")
    
    with StrategyClient() as client:
        # Health check
        health = client.health_check()
        typer.echo(f"API Status: {health['data']['status']}")
        
        # Load profile
        profile = client.load_profile("conservative")
        typer.echo(f"Loaded profile: {profile['profile_name']}")
        
        # Create strategy
        result = client.create_strategy(
            name="Quickstart Strategy",
            config=profile,
            description="Created via CLI quickstart"
        )
        strategy_id = result["data"]["id"]
        typer.echo(f"Created strategy: {strategy_id}")
        
        # Run backtest
        backtest = client.run_backtest(
            strategy_id=strategy_id,
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31)
        )
        typer.echo(f"Backtest scheduled: {backtest['data']['backtest_id']}")
        
        # Get results
        results = client.get_backtest_results(backtest["data"]["backtest_id"])
        metrics = results["data"]["metrics"]
        
        typer.echo("\nResults:")
        typer.echo(f"  Total Return: {metrics['total_return']:.2%}")
        typer.echo(f"  Max Drawdown: {metrics['max_drawdown']:.2%}")
        typer.echo(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")


@app.command()
def profiles() -> None:
    """List available strategy profiles."""
    profiles_dir = Path("config/profiles")
    
    if not profiles_dir.exists():
        typer.echo("No profiles found")
        return
    
    typer.echo("Available profiles:")
    for profile_file in profiles_dir.glob("*.json"):
        typer.echo(f"  - {profile_file.stem}")


@app.command()
def validate(
    profile: str = typer.Argument(..., help="Profile name to validate")
) -> None:
    """Validate a strategy profile configuration."""
    import json
    
    profile_path = Path(f"config/profiles/{profile}.json")
    
    if not profile_path.exists():
        typer.echo(f"Profile not found: {profile}", err=True)
        raise typer.Exit(1)
    
    with open(profile_path) as f:
        config = json.load(f)
    
    # Basic validation
    errors = []
    
    if "profile_name" not in config:
        errors.append("Missing 'profile_name'")
    
    allocation = config.get("asset_allocation", {})
    if allocation:
        total = sum(allocation.values())
        if not 0.99 <= total <= 1.01:
            errors.append(f"Asset allocation sums to {total}, should be 1.0")
    
    if errors:
        typer.echo("Validation errors:", err=True)
        for error in errors:
            typer.echo(f"  - {error}", err=True)
        raise typer.Exit(1)
    else:
        typer.echo(f"Profile '{profile}' is valid!")
        typer.echo(f"  Name: {config.get('profile_name')}")
        typer.echo(f"  Target Return: {config.get('target_annual_return')}")
        typer.echo(f"  Max Drawdown: {config.get('max_drawdown_limit')}")


def main() -> None:
    """Entry point."""
    app()
