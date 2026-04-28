"""Configuration management using pydantic-settings."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Application
    app_name: str = Field(default="intelligent-strategy-trading")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    
    # API Server
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_workers: int = Field(default=1)
    
    # Data
    data_path: str = Field(default="./data")
    cache_enabled: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=300)
    
    # Database
    database_url: Optional[str] = Field(default=None)
    
    # Redis (optional, for production)
    redis_url: Optional[str] = Field(default=None)
    
    # Risk Management Defaults
    default_simulation_runs: int = Field(default=10000)
    default_confidence_level: float = Field(default=0.95)
    max_drawdown_default_limit: float = Field(default=0.05)
    
    # Backtest
    default_initial_capital: float = Field(default=100000.0)
    default_commission_rate: float = Field(default=0.001)
    
    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create singleton settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
