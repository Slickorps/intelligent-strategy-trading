"""Strategy management endpoints."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from ist.api.schemas.base import BaseResponse, ErrorResponse
from ist.api.schemas.strategy import (
    StrategyCreate,
    StrategyResponse,
    StrategyFlowchart,
    NodeDefinition,
    ConnectionDefinition,
)
from ist.core.exceptions import ValidationError
from ist.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# In-memory storage for MVP (replace with database in production)
_strategies: dict[str, dict[str, Any]] = {}


@router.post(
    "",
    response_model=BaseResponse[StrategyResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create strategy",
    description="Create a new trading strategy with visual node configuration"
)
async def create_strategy(request: StrategyCreate) -> BaseResponse[StrategyResponse]:
    """Create a new strategy."""
    try:
        strategy_id = str(uuid4())
        now = datetime.utcnow()
        
        # Build config from request
        config = {
            "profile_name": request.profile_name or request.name,
            "target_annual_return": request.target_annual_return,
            "max_drawdown_limit": request.max_drawdown_limit,
            "asset_allocation": request.asset_allocation,
            "risk_management": request.risk_management,
            "strategy_nodes": {
                "version": "1.0",
                "nodes": [
                    {
                        "id": node.id,
                        "type": node.type,
                        "params": node.params,
                        "position": node.position
                    }
                    for node in request.nodes
                ],
                "connections": [
                    {
                        "from": conn.from_node,
                        "to": conn.to_node
                    }
                    for conn in request.connections
                ]
            }
        }
        
        strategy = {
            "id": strategy_id,
            "name": request.name,
            "description": request.description,
            "status": "draft",
            "config": config,
            "created_at": now,
            "updated_at": now,
        }
        
        _strategies[strategy_id] = strategy
        
        logger.info(
            "Strategy created",
            strategy_id=strategy_id,
            name=request.name
        )
        
        return BaseResponse(
            success=True,
            data=StrategyResponse(**strategy),
            message="Strategy created successfully"
        )
        
    except Exception as e:
        logger.error("Failed to create strategy", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "",
    response_model=BaseResponse[list[StrategyResponse]],
    status_code=status.HTTP_200_OK,
    summary="List strategies",
    description="List all trading strategies"
)
async def list_strategies() -> BaseResponse[list[StrategyResponse]]:
    """List all strategies."""
    strategies = [
        StrategyResponse(**s) for s in _strategies.values()
    ]
    
    return BaseResponse(
        success=True,
        data=strategies,
        message=f"Found {len(strategies)} strategies"
    )


@router.get(
    "/{strategy_id}",
    response_model=BaseResponse[StrategyResponse],
    status_code=status.HTTP_200_OK,
    summary="Get strategy",
    description="Get strategy details by ID"
)
async def get_strategy(strategy_id: str) -> BaseResponse[StrategyResponse]:
    """Get a specific strategy."""
    strategy = _strategies.get(strategy_id)
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy {strategy_id} not found"
        )
    
    return BaseResponse(
        success=True,
        data=StrategyResponse(**strategy)
    )


@router.get(
    "/{strategy_id}/flowchart",
    response_model=BaseResponse[StrategyFlowchart],
    status_code=status.HTTP_200_OK,
    summary="Get strategy flowchart",
    description="Get visualization data for strategy flowchart"
)
async def get_strategy_flowchart(
    strategy_id: str
) -> BaseResponse[StrategyFlowchart]:
    """Get flowchart data for strategy visualization."""
    strategy = _strategies.get(strategy_id)
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy {strategy_id} not found"
        )
    
    # Extract node data from config
    nodes_config = strategy["config"].get("strategy_nodes", {})
    
    nodes = [
        NodeDefinition(
            id=n["id"],
            type=n["type"],
            params=n.get("params", {}),
            position=n.get("position")
        )
        for n in nodes_config.get("nodes", [])
    ]
    
    connections = [
        ConnectionDefinition(from_node=c["from"], to_node=c["to"])
        for c in nodes_config.get("connections", [])
    ]
    
    # Basic validation
    validation_errors = []
    node_ids = {n.id for n in nodes}
    
    for conn in connections:
        if conn.from_node not in node_ids:
            validation_errors.append(f"Connection from unknown node: {conn.from_node}")
        if conn.to_node not in node_ids:
            validation_errors.append(f"Connection to unknown node: {conn.to_node}")
    
    is_valid = len(validation_errors) == 0 and len(nodes) > 0
    
    return BaseResponse(
        success=True,
        data=StrategyFlowchart(
            strategy_id=strategy_id,
            strategy_name=strategy["name"],
            nodes=nodes,
            connections=connections,
            is_valid=is_valid,
            validation_errors=validation_errors
        )
    )


@router.delete(
    "/{strategy_id}",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Delete strategy",
    description="Delete a strategy by ID"
)
async def delete_strategy(strategy_id: str) -> BaseResponse[dict]:
    """Delete a strategy."""
    if strategy_id not in _strategies:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy {strategy_id} not found"
        )
    
    del _strategies[strategy_id]
    
    logger.info("Strategy deleted", strategy_id=strategy_id)
    
    return BaseResponse(
        success=True,
        data={"deleted": strategy_id},
        message="Strategy deleted successfully"
    )
