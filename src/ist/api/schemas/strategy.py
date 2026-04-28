"""Strategy-related API schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, validator

from ist.data.models import AssetClass


class NodeDefinition(BaseModel):
    """Strategy node definition."""
    
    id: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    position: Optional[dict[str, float]] = None  # x, y for visualization


class ConnectionDefinition(BaseModel):
    """Connection between nodes."""
    
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    
    class Config:
        populate_by_name = True


class StrategyCreate(BaseModel):
    """Request to create a new strategy."""
    
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    profile_name: Optional[str] = None
    target_annual_return: Optional[str] = None
    max_drawdown_limit: Optional[str] = None
    asset_allocation: Optional[dict[str, float]] = None
    risk_management: Optional[dict[str, Any]] = None
    nodes: list[NodeDefinition] = Field(default_factory=list)
    connections: list[ConnectionDefinition] = Field(default_factory=list)
    
    @validator("asset_allocation")
    def validate_allocation(cls, v: Optional[dict[str, float]]) -> Optional[dict[str, float]]:
        if v is not None:
            total = sum(v.values())
            if not 0.99 <= total <= 1.01:
                raise ValueError(f"Asset allocation must sum to 1.0, got {total}")
        return v


class StrategyResponse(BaseModel):
    """Strategy response."""
    
    id: str
    name: str
    description: Optional[str] = None
    status: str = "draft"  # draft, active, paused, archived
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class StrategyFlowchart(BaseModel):
    """Strategy flowchart data for visualization."""
    
    strategy_id: str
    strategy_name: str
    nodes: list[NodeDefinition]
    connections: list[ConnectionDefinition]
    is_valid: bool
    validation_errors: list[str] = Field(default_factory=list)
