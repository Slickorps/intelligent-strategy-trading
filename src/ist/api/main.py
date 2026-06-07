"""FastAPI application entry point."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from ist.core.config import get_settings
from ist.core.events import EventBus
from ist.core.logging import configure_logging, get_logger
from ist.core.monitoring import (
    API_REQUESTS_IN_PROGRESS,
    collect_system_metrics,
    generate_metrics,
    record_api_request,
    set_application_info,
)
from ist.api.routers import health, strategies, backtest, portfolio, risk, ml_factors

logger = get_logger(__name__)


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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    # Prometheus metrics endpoint
    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint():
        collect_system_metrics()
        return PlainTextResponse(
            content=generate_metrics().decode("utf-8"),
            media_type="text/plain; version=0.0.4",
        )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])
    app.include_router(backtest.router, prefix="/backtest", tags=["Backtest"])
    app.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
    app.include_router(risk.router, prefix="/risk", tags=["Risk"])
    app.include_router(ml_factors.router, prefix="/risk", tags=["ML Factors"])

    return app


# Global app instance for uvicorn
app = create_app()
