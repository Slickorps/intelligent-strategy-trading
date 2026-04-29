"""Custom exceptions for the Intelligent Strategy Trading platform."""


class ISTError(Exception):
    """Base exception for all platform errors."""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(ISTError):
    """Raised when configuration is invalid."""
    pass


class ValidationError(ISTError):
    """Raised when data validation fails."""
    pass


class StrategyError(ISTError):
    """Raised when strategy execution encounters an error."""
    pass


class NodeError(StrategyError):
    """Raised when a strategy node encounters an error."""
    pass


class GraphError(StrategyError):
    """Raised when strategy graph validation fails."""
    pass


class ExecutionError(ISTError):
    """Raised when trade execution fails."""
    pass


class RiskError(ISTError):
    """Raised when risk limits are breached."""
    pass


class SimulationError(RiskError):
    """Raised when Monte Carlo simulation fails."""
    pass


class DataError(ISTError):
    """Raised when data operations fail."""
    pass


class BacktestError(ISTError):
    """Raised when backtest operations fail."""
    pass


class IndicatorError(ISTError):
    """Raised when technical indicator calculation fails."""
    pass
