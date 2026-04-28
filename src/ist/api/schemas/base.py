"""Base schema definitions."""

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Standard pagination parameters."""
    
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""
    
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorDetail(BaseModel):
    """Error detail information."""
    
    code: str
    message: str
    field: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class ErrorResponse(BaseResponse):
    """Standard error response."""
    
    success: bool = False
    error: Optional[ErrorDetail] = None
    
    @classmethod
    def from_exception(
        cls,
        code: str,
        message: str,
        details: Optional[dict] = None
    ) -> "ErrorResponse":
        """Create error response from exception."""
        return cls(
            success=False,
            error=ErrorDetail(
                code=code,
                message=message,
                details=details
            )
        )
