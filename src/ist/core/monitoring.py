"""Prometheus metrics definitions for the IST trading platform.

System metrics: CPU, memory, disk usage.
Business metrics: order executions, active connections, request latency.
Risk metrics: VaR, max drawdown, position exposure.
"""

import os
import time
from typing import Optional

import psutil
from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest
from prometheus_client import REGISTRY, CollectorRegistry

_registry: CollectorRegistry = REGISTRY


def get_registry() -> CollectorRegistry:
    return _registry


def generate_metrics() -> bytes:
    return generate_latest(_registry)


# ─── System Metrics ───────────────────────────────────────────────

SYSTEM_CPU_USAGE = Gauge(
    "ist_system_cpu_usage_percent",
    "Current CPU usage percentage",
    registry=_registry,
)

SYSTEM_MEMORY_USAGE = Gauge(
    "ist_system_memory_usage_bytes",
    "Current memory usage in bytes (RSS)",
    registry=_registry,
)

SYSTEM_MEMORY_PERCENT = Gauge(
    "ist_system_memory_usage_percent",
    "Current memory usage percentage",
    registry=_registry,
)

SYSTEM_DISK_USAGE = Gauge(
    "ist_system_disk_usage_bytes",
    "Disk usage in bytes for the data directory",
    ["path"],
    registry=_registry,
)

SYSTEM_OPEN_FDS = Gauge(
    "ist_system_open_fds",
    "Number of open file descriptors",
    registry=_registry,
)

SYSTEM_THREAD_COUNT = Gauge(
    "ist_system_thread_count",
    "Number of threads in the process",
    registry=_registry,
)

# ─── Business Metrics ─────────────────────────────────────────────

ORDER_EXECUTED_TOTAL = Counter(
    "ist_orders_executed_total",
    "Total number of orders executed",
    ["strategy", "order_type", "result"],
    registry=_registry,
)

ORDER_LATENCY_SECONDS = Histogram(
    "ist_order_latency_seconds",
    "Order execution latency in seconds",
    ["strategy", "order_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=_registry,
)

ACTIVE_CONNECTIONS = Gauge(
    "ist_active_connections",
    "Number of currently active broker/data connections",
    ["connection_type"],
    registry=_registry,
)

API_REQUESTS_TOTAL = Counter(
    "ist_api_requests_total",
    "Total number of API requests received",
    ["method", "endpoint", "status_code"],
    registry=_registry,
)

API_REQUEST_DURATION_SECONDS = Histogram(
    "ist_api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=_registry,
)

API_REQUESTS_IN_PROGRESS = Gauge(
    "ist_api_requests_in_progress",
    "Number of API requests currently being processed",
    ["method"],
    registry=_registry,
)

# ─── Risk Metrics ─────────────────────────────────────────────────

RISK_VAR_LATEST = Gauge(
    "ist_risk_var_latest",
    "Latest Value-at-Risk estimate",
    ["confidence_level"],
    registry=_registry,
)

RISK_CVAR_LATEST = Gauge(
    "ist_risk_cvar_latest",
    "Latest Conditional Value-at-Risk (Expected Shortfall)",
    ["confidence_level"],
    registry=_registry,
)

RISK_MAX_DRAWDOWN = Gauge(
    "ist_risk_max_drawdown",
    "Current maximum drawdown",
    ["portfolio_id"],
    registry=_registry,
)

RISK_CURRENT_DRAWDOWN = Gauge(
    "ist_risk_current_drawdown",
    "Current drawdown from peak",
    ["portfolio_id"],
    registry=_registry,
)

RISK_POSITION_EXPOSURE = Gauge(
    "ist_risk_position_exposure",
    "Current position exposure",
    ["symbol", "direction"],
    registry=_registry,
)

RISK_SHARPE_RATIO = Gauge(
    "ist_risk_sharpe_ratio",
    "Portfolio Sharpe ratio",
    ["portfolio_id"],
    registry=_registry,
)

RISK_VOLATILITY = Gauge(
    "ist_risk_volatility",
    "Portfolio annualized volatility",
    ["portfolio_id"],
    registry=_registry,
)

# ─── Application Info ─────────────────────────────────────────────

APP_INFO = Info(
    "ist_application",
    "Application metadata",
    registry=_registry,
)

# ─── System Metrics Collection ────────────────────────────────────


def collect_system_metrics() -> None:
    """Update system-level gauges from psutil."""
    try:
        process = psutil.Process(os.getpid())

        SYSTEM_CPU_USAGE.set(process.cpu_percent(interval=None))

        mem_info = process.memory_info()
        SYSTEM_MEMORY_USAGE.set(mem_info.rss)
        SYSTEM_MEMORY_PERCENT.set(process.memory_percent())

        SYSTEM_OPEN_FDS.set(process.num_fds() if hasattr(process, "num_fds") else 0)
        SYSTEM_THREAD_COUNT.set(process.num_threads())
    except Exception:
        logger.debug("Failed to collect system metrics", exc_info=True)


def set_application_info(
    name: str, version: str, environment: str = "production"
) -> None:
    """Set application info labels."""
    APP_INFO.info(
        {
            "name": name,
            "version": version,
            "environment": environment,
        }
    )


def record_api_request(
    method: str,
    endpoint: str,
    status_code: int,
    duration: float,
) -> None:
    """Record an API request for latency and count metrics."""
    API_REQUESTS_TOTAL.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).inc()
    API_REQUEST_DURATION_SECONDS.labels(
        method=method,
        endpoint=endpoint,
    ).observe(duration)


def record_order_execution(
    strategy: str,
    order_type: str,
    result: str,
    latency: float,
) -> None:
    """Record an order execution event."""
    ORDER_EXECUTED_TOTAL.labels(
        strategy=strategy,
        order_type=order_type,
        result=result,
    ).inc()
    ORDER_LATENCY_SECONDS.labels(
        strategy=strategy,
        order_type=order_type,
    ).observe(latency)


def set_active_connections(connection_type: str, count: int) -> None:
    """Update active connection count gauge."""
    ACTIVE_CONNECTIONS.labels(connection_type=connection_type).set(count)


def update_risk_metrics(
    var_value: Optional[float] = None,
    cvar_value: Optional[float] = None,
    max_drawdown_value: Optional[float] = None,
    current_drawdown_value: Optional[float] = None,
    sharpe_ratio_value: Optional[float] = None,
    volatility_value: Optional[float] = None,
    confidence_level: float = 0.95,
    portfolio_id: str = "default",
) -> None:
    """Update risk-related gauges."""
    if var_value is not None:
        RISK_VAR_LATEST.labels(
            confidence_level=str(confidence_level)
        ).set(var_value)
    if cvar_value is not None:
        RISK_CVAR_LATEST.labels(
            confidence_level=str(confidence_level)
        ).set(cvar_value)
    if max_drawdown_value is not None:
        RISK_MAX_DRAWDOWN.labels(portfolio_id=portfolio_id).set(
            max_drawdown_value
        )
    if current_drawdown_value is not None:
        RISK_CURRENT_DRAWDOWN.labels(portfolio_id=portfolio_id).set(
            current_drawdown_value
        )
    if sharpe_ratio_value is not None:
        RISK_SHARPE_RATIO.labels(portfolio_id=portfolio_id).set(
            sharpe_ratio_value
        )
    if volatility_value is not None:
        RISK_VOLATILITY.labels(portfolio_id=portfolio_id).set(
            volatility_value
        )


def set_position_exposure(symbol: str, direction: str, exposure: float) -> None:
    """Record position exposure for a symbol."""
    RISK_POSITION_EXPOSURE.labels(symbol=symbol, direction=direction).set(
        exposure
    )


def clear_position_exposure(symbol: str, direction: str) -> None:
    """Remove position exposure metric for a symbol."""
    try:
        RISK_POSITION_EXPOSURE.remove(symbol, direction)
    except KeyError:
        logger.debug("Failed to remove position exposure metric", exc_info=True)
