"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ist.core.config import get_settings
from ist.core.events import EventBus
from ist.core.logging import configure_logging, get_logger
from ist.api.routers import health, strategies, backtest, portfolio, risk, ml_factors

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    configure_logging()
    settings = get_settings()
    
    logger.info(
        "Starting Intelligent Strategy Trading API",
        version=settings.app_version,
        debug=settings.debug
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
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
