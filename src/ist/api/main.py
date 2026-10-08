"""FastAPI application entry point."""

import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ist.api.routers import (
    backtest,
    health,
    ml_factors,
    portfolio,
    risk,
    strategies,
    websocket,
)
from ist.api.schemas.base import ErrorResponse
from ist.api.websocket_manager import WebSocketHub, attach_event_bus
from ist.core.config import get_settings
from ist.core.events import EventBus
from ist.core.exceptions import ISTError
from ist.core.logging import configure_logging, get_logger
from ist.core.monitoring import (
    API_REQUESTS_IN_PROGRESS,
    collect_system_metrics,
    generate_metrics,
    record_api_request,
    set_application_info,
)

logger = get_logger(__name__)

# Paths that stay reachable without an API key (probes, docs, metrics).
AUTH_EXEMPT_PATHS = frozenset({
    "/",
    "/health",
    "/health/detail",
    "/version",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
})


def _error_payload(code: str, message: str, details: dict | None = None) -> dict:
    """Serialize a unified, sanitized error response body."""
    return ErrorResponse.from_exception(
        code=code,
        message=message,
        details=details,
    ).model_dump(mode="json")


def _extract_api_key(request: Request) -> str | None:
    """Read an API key from the X-API-Key header or Authorization: Bearer."""
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    configure_logging()
    settings = get_settings()

    set_application_info(
        name=settings.app_name,
        version=settings.app_version,
        environment="production" if not settings.debug else "development",
    )
    collect_system_metrics()

    logger.info(
        "Starting Intelligent Strategy Trading API",
        version=settings.app_version,
        debug=settings.debug,
    )

    # Initialize shared resources
    app.state.event_bus = EventBus()
    attach_event_bus(app.state.websocket_hub, app.state.event_bus)

    yield

    # Shutdown
    logger.info("Shutting down API")


def create_app() -> FastAPI:
    """Factory function to create FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Intelligent Strategy Trading API",
        description="Professional quantitative trading platform with visual strategy orchestration",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Real-time WebSocket hub (shared across connections)
    app.state.websocket_hub = WebSocketHub()

    # Request metrics middleware
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start_time = time.monotonic()
        method = request.method
        endpoint = request.url.path

        API_REQUESTS_IN_PROGRESS.labels(method=method).inc()

        try:
            response: Response = await call_next(request)
            duration = time.monotonic() - start_time
            record_api_request(
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
                duration=duration,
            )
            return response
        except Exception as exc:
            duration = time.monotonic() - start_time
            record_api_request(
                method=method,
                endpoint=endpoint,
                status_code=500,
                duration=duration,
            )
            raise exc
        finally:
            API_REQUESTS_IN_PROGRESS.labels(method=method).dec()

    # API key authentication middleware (enabled only when api_key is configured)
    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next):
        api_key = get_settings().api_key
        if api_key and request.url.path not in AUTH_EXEMPT_PATHS:
            provided = _extract_api_key(request)
            if not provided or not secrets.compare_digest(provided, api_key):
                logger.warning(
                    "Unauthorized API request",
                    path=request.url.path,
                    method=request.method,
                )
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=_error_payload(
                        "unauthorized", "Missing or invalid API key",
                    ),
                )
        return await call_next(request)

    # CORS middleware must be outermost so preflight and error responses
    # (e.g. 401) still carry the CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus metrics endpoint
    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint():
        collect_system_metrics()
        return PlainTextResponse(
            content=generate_metrics().decode("utf-8"),
            media_type="text/plain; version=0.0.4",
        )

    # ------------------------------------------------------------------
    # Exception handlers: unified responses that never leak internals
    # ------------------------------------------------------------------

    @app.exception_handler(ISTError)
    async def ist_error_handler(request: Request, exc: ISTError):
        logger.warning("Application error", path=request.url.path, error=exc.message)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_payload(
                "application_error", exc.message, exc.details or None,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                "validation_error",
                "Request validation failed",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(f"http_{exc.status_code}", message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                "internal_server_error", "An internal error occurred",
            ),
        )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])
    app.include_router(backtest.router, prefix="/backtest", tags=["Backtest"])
    app.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
    app.include_router(risk.router, prefix="/risk", tags=["Risk"])
    app.include_router(ml_factors.router, prefix="/risk", tags=["ML Factors"])
    app.include_router(websocket.router, tags=["WebSocket"])

    return app


# Global app instance for uvicorn
app = create_app()
