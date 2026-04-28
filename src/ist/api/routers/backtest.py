"""Backtest endpoints."""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from ist.api.schemas.base import BaseResponse
from ist.api.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    BacktestStatus,
    BacktestResults,
    PerformanceMetrics,
)
from ist.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# In-memory backtest storage
_backtests: dict[str, dict[str, Any]] = {}


@router.post(
    "/run",
    response_model=BaseResponse[BacktestResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run backtest",
    description="Start a new backtest for a strategy"
)
async def run_backtest(request: BacktestRequest) -> BaseResponse[BacktestResponse]:
    """Start a backtest."""
    backtest_id = str(uuid4())
    now = datetime.utcnow()
    
    # Estimate completion (placeholder logic)
    days = (request.end_date - request.start_date).days
    estimated_seconds = min(days * 0.1, 300)  # Cap at 5 minutes
    
    backtest = {
        "backtest_id": backtest_id,
        "strategy_id": request.strategy_id,
        "status": "pending",
        "progress_pct": 0.0,
        "started_at": now,
        "estimated_completion": now + timedelta(seconds=estimated_seconds),
    }
    
    _backtests[backtest_id] = {
        **backtest,
        "request": request.dict(),
        "results": None,
        "completed_at": None,
    }
    
    logger.info(
        "Backtest scheduled",
        backtest_id=backtest_id,
        strategy_id=request.strategy_id,
        start=request.start_date,
        end=request.end_date
    )
    
    return BaseResponse(
        success=True,
        data=BacktestResponse(
            backtest_id=backtest_id,
            status="pending",
            estimated_completion=backtest["estimated_completion"]
        ),
        message="Backtest scheduled"
    )


@router.get(
    "/{backtest_id}/status",
    response_model=BaseResponse[BacktestStatus],
    status_code=status.HTTP_200_OK,
    summary="Get backtest status",
    description="Get current status of a running backtest"
)
async def get_backtest_status(
    backtest_id: str
) -> BaseResponse[BacktestStatus]:
    """Get backtest status."""
    backtest = _backtests.get(backtest_id)
    
    if not backtest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest {backtest_id} not found"
        )
    
    return BaseResponse(
        success=True,
        data=BacktestStatus(
            backtest_id=backtest_id,
            status=backtest["status"],
            progress_pct=backtest.get("progress_pct", 0),
            current_date=backtest.get("current_date"),
            message=backtest.get("message"),
            started_at=backtest["started_at"],
            completed_at=backtest.get("completed_at")
        )
    )


@router.get(
    "/{backtest_id}/results",
    response_model=BaseResponse[BacktestResults],
    status_code=status.HTTP_200_OK,
    summary="Get backtest results",
    description="Get detailed results of a completed backtest"
)
async def get_backtest_results(
    backtest_id: str
) -> BaseResponse[BacktestResults]:
    """Get backtest results."""
    backtest = _backtests.get(backtest_id)
    
    if not backtest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest {backtest_id} not found"
        )
    
    # Return placeholder results for MVP
    # In real implementation, this would come from executed backtest
    placeholder_metrics = PerformanceMetrics(
        total_return=0.125,
        annualized_return=0.042,
        max_drawdown=0.038,
        sharpe_ratio=1.35,
        sortino_ratio=1.85,
        calmar_ratio=1.10,
        volatility=0.028,
        win_rate=0.58,
        profit_factor=1.65,
        avg_trade=125.50,
        total_trades=156,
        winning_trades=90,
        losing_trades=66
    )
    
    return BaseResponse(
        success=True,
        data=BacktestResults(
            backtest_id=backtest_id,
            strategy_id=backtest["strategy_id"],
            metrics=placeholder_metrics,
            equity_curve=[],
            trades=[],
            daily_returns=[],
            monthly_returns=[]
        )
    )


@router.get(
    "",
    response_model=BaseResponse[list[BacktestStatus]],
    status_code=status.HTTP_200_OK,
    summary="List backtests",
    description="List all backtests"
)
async def list_backtests() -> BaseResponse[list[BacktestStatus]]:
    """List all backtests."""
    backtests = [
        BacktestStatus(
            backtest_id=b["backtest_id"],
            status=b["status"],
            progress_pct=b.get("progress_pct", 0),
            current_date=b.get("current_date"),
            message=b.get("message"),
            started_at=b["started_at"],
            completed_at=b.get("completed_at")
        )
        for b in _backtests.values()
    ]
    
    return BaseResponse(
        success=True,
        data=backtests,
        message=f"Found {len(backtests)} backtests"
    )
