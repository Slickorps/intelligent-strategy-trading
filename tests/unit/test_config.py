"""Unit tests for application settings (pydantic-settings)."""

import pytest
from pydantic import ValidationError

from ist.core.config import Settings, get_settings


class TestSettingsDefaults:
    def test_app_defaults(self) -> None:
        s = Settings()
        assert s.app_name == "intelligent-strategy-trading"
        assert s.app_version == "0.1.0"
        assert s.debug is False

    def test_api_defaults(self) -> None:
        s = Settings()
        assert s.api_host == "0.0.0.0"
        assert s.api_port == 8000
        assert s.api_workers == 1

    def test_data_defaults(self) -> None:
        s = Settings()
        assert s.data_path == "./data"
        assert s.cache_enabled is True
        assert s.cache_ttl_seconds == 300

    def test_optional_defaults_are_none(self) -> None:
        s = Settings()
        assert s.database_url is None
        assert s.redis_url is None

    def test_risk_defaults(self) -> None:
        s = Settings()
        assert s.default_simulation_runs == 10000
        assert s.default_confidence_level == 0.95
        assert s.max_drawdown_default_limit == 0.05

    def test_backtest_defaults(self) -> None:
        s = Settings()
        assert s.default_initial_capital == 100000.0
        assert s.default_commission_rate == 0.001

    def test_logging_defaults(self) -> None:
        s = Settings()
        assert s.log_level == "INFO"
        assert s.log_format == "json"


class TestSettingsEnvOverride:
    def test_env_overrides_api_port(self, monkeypatch) -> None:
        monkeypatch.setenv("API_PORT", "9000")
        assert Settings().api_port == 9000

    def test_env_overrides_debug(self, monkeypatch) -> None:
        monkeypatch.setenv("DEBUG", "true")
        assert Settings().debug is True

    def test_env_overrides_app_name(self, monkeypatch) -> None:
        monkeypatch.setenv("APP_NAME", "my-app")
        assert Settings().app_name == "my-app"

    def test_env_unknown_variable_ignored(self, monkeypatch) -> None:
        monkeypatch.setenv("UNKNOWN_SETTING", "value")
        s = Settings()
        assert "unknown_setting" not in s.model_dump()

    def test_env_invalid_int_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("API_PORT", "not-a-number")
        with pytest.raises(ValidationError):
            Settings()


class TestGetSettings:
    def test_returns_settings_instance(self) -> None:
        assert isinstance(get_settings(), Settings)

    def test_singleton_returns_same_instance(self) -> None:
        assert get_settings() is get_settings()
