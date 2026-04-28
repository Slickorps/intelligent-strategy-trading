"""Health check endpoints."""

from datetime import datetime

from fastapi import APIRouter, status

from ist.api.schemas.base import BaseResponse
from ist.core.config import get_settings

router = APIRouter()


@router.get(
    "/health",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Returns service health status"
)
async def health_check() -> BaseResponse[dict]:
    """Health check endpoint."""
    settings = get_settings()
    
    return BaseResponse(
        success=True,
        data={
            "status": "healthy",
            "version": settings.app_version,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


@router.get(
    "/version",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Get version info",
    description="Returns API version and system information"
)
async def get_version() -> BaseResponse[dict]:
    """Get API version information."""
    settings = get_settings()
    
    return BaseResponse(
        success=True,
        data={
            "app_name": settings.app_name,
            "version": settings.app_version,
            "debug": settings.debug,
        }
    )
