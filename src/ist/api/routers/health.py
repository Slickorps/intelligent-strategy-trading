"""Health check endpoints."""

import os
from datetime import datetime
from typing import Any

import psutil
from fastapi import APIRouter, status

from ist.api.schemas.base import BaseResponse
from ist.core.config import get_settings

router = APIRouter()


def _check_component(name: str, check_fn) -> dict[str, Any]:
    try:
        result = check_fn()
        return {"status": "healthy", **result}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


def _check_database() -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        return {"status": "disabled", "message": "No database configured"}
    return {"message": "ok"}


def _check_redis() -> dict[str, Any]:
    settings = get_settings()
    if not settings.redis_url:
        return {"status": "disabled", "message": "No Redis configured"}
    return {"message": "ok"}


def _check_system() -> dict[str, Any]:
    process = psutil.Process(os.getpid())
    mem = process.memory_info()
    return {
        "cpu_percent": process.cpu_percent(interval=None),
        "memory_rss_mb": round(mem.rss / (1024 * 1024), 2),
        "memory_percent": round(process.memory_percent(), 2),
        "threads": process.num_threads(),
        "open_fds": process.num_fds() if hasattr(process, "num_fds") else 0,
    }


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
    "/health/detail",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Detailed health check",
    description="Returns detailed health status of all system components"
)
async def health_detail() -> BaseResponse[dict]:
    """Detailed health check with component status."""
    settings = get_settings()

    components = {
        "database": _check_component("database", _check_database),
        "redis": _check_component("redis", _check_redis),
        "system": _check_component("system", _check_system),
    }

    overall_healthy = all(
        c.get("status") in ("healthy", "disabled")
        for c in components.values()
    )

    return BaseResponse(
        success=overall_healthy,
        data={
            "status": "healthy" if overall_healthy else "degraded",
            "version": settings.app_version,
            "timestamp": datetime.utcnow().isoformat(),
            "components": components,
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
